from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pr_factory.agents.llm import get_embedder
from pr_factory.context.indexers.code_parser import ParsedChunk, get_source_files, parse_file
from pr_factory.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class QdrantIndexConfig:
    collection_name: str = "pr_factory_code_chunks"
    vector_name: str = "dense"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_path: str | None = None
    recreate: bool = False
    batch_size: int = 64

    @classmethod
    def from_env(cls) -> "QdrantIndexConfig":
        return cls(
            collection_name=os.getenv("PR_FACTORY_QDRANT_COLLECTION", "pr_factory_code_chunks"),
            qdrant_url=os.getenv("QDRANT_URL") or None,
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            qdrant_path=os.getenv("PR_FACTORY_QDRANT_PATH") or ":memory:",
            recreate=os.getenv("PR_FACTORY_QDRANT_RECREATE", "false").lower() == "true",
        )


class QdrantCodeIndexer:
    """Index parsed repository chunks into Qdrant dense vectors with lexical payload."""

    def __init__(self, config: QdrantIndexConfig | None = None, embedder: Any | None = None, client: Any | None = None) -> None:
        self.config = config or QdrantIndexConfig.from_env()
        self.embedder = embedder or get_embedder()
        self.client = client or self._build_client()

    def index_repository(self, repo_path: str | Path, *, repo_name: str | None = None, commit: str | None = None) -> int:
        repo = Path(repo_path)
        chunks = self.parse_repository(repo)
        if not chunks:
            return 0
        self.ensure_collection(self._embedding_dimension(chunks[0].content))
        points = []
        for chunk in chunks:
            rel_path = Path(chunk.source).resolve().relative_to(repo.resolve()).as_posix()
            payload = {
                "repo": repo_name or repo.name,
                "commit": commit,
                "path": rel_path,
                "name": chunk.name,
                "type": chunk.type,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "text": chunk.content,
                "lexical_text": self._lexical_text(rel_path, chunk),
            }
            point_id = self._point_id(repo_name or repo.name, commit or "working-tree", rel_path, chunk.start_line, chunk.end_line)
            points.append(self._point(point_id, self.embedder.embed_query(chunk.content), payload))

        for start in range(0, len(points), self.config.batch_size):
            self.client.upsert(
                collection_name=self.config.collection_name,
                points=points[start : start + self.config.batch_size],
            )
        logger.info("Indexed %s chunks from %s into Qdrant collection %s", len(points), repo, self.config.collection_name)
        return len(points)

    def parse_repository(self, repo_path: str | Path) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        for file_path in get_source_files(repo_path):
            try:
                chunks.extend(parse_file(file_path))
            except (OSError, ValueError) as error:
                logger.debug("Skipping %s during indexing: %s", file_path, error)
        return chunks

    def ensure_collection(self, vector_size: int) -> None:
        from qdrant_client import models

        existing = {collection.name for collection in self.client.get_collections().collections}
        if self.config.collection_name in existing and self.config.recreate:
            self.client.delete_collection(self.config.collection_name)
            existing.remove(self.config.collection_name)
        if self.config.collection_name in existing:
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config={
                self.config.vector_name: models.VectorParams(size=vector_size, distance=models.Distance.COSINE)
            },
        )

    def _build_client(self):
        from qdrant_client import QdrantClient

        if self.config.qdrant_url:
            return QdrantClient(
                url=self.config.qdrant_url,
                api_key=self.config.qdrant_api_key,
                check_compatibility=False,
            )
        return QdrantClient(path=self.config.qdrant_path or ":memory:")

    def _embedding_dimension(self, text: str) -> int:
        return len(self.embedder.embed_query(text))

    def _point(self, point_id: str, vector: list[float], payload: dict[str, Any]):
        from qdrant_client import models

        return models.PointStruct(id=point_id, vector={self.config.vector_name: vector}, payload=payload)

    @staticmethod
    def _point_id(*parts: Any) -> str:
        raw = "|".join(str(part) for part in parts)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return str(uuid.UUID(hex=digest[:32]))

    @staticmethod
    def _lexical_text(rel_path: str, chunk: ParsedChunk) -> str:
        return f"{rel_path}\n{chunk.name}\n{chunk.type}\n{chunk.content}".lower()

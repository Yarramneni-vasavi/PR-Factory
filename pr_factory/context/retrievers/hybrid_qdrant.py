from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any

from pr_factory.agents.llm import get_embedder
from pr_factory.context.indexers.hybrid_qdrant import QdrantIndexConfig
from pr_factory.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class HybridSearchResult:
    content: str
    path: str
    name: str
    type: str
    start_line: int
    end_line: int
    semantic_score: float
    lexical_score: float
    combined_score: float


class QdrantHybridRetriever:
    """Retrieve code chunks with Qdrant semantic search plus lexical reranking."""

    def __init__(
        self,
        config: QdrantIndexConfig | None = None,
        embedder: Any | None = None,
        client: Any | None = None,
        lexical_weight: float = 0.35,
    ) -> None:
        self.config = config or QdrantIndexConfig.from_env()
        self.embedder = embedder or get_embedder()
        self.client = client or self._build_client()
        self.lexical_weight = lexical_weight

    def retrieve(self, query: str, *, k: int = 8, repo: str | None = None, commit: str | None = None) -> list[HybridSearchResult]:
        logger.info("Retrieving top %s Qdrant context chunks for repo=%s commit=%s", k, repo, commit)
        vector = self.embedder.embed_query(query)
        query_filter = self._filter(repo=repo, commit=commit)
        raw_results = self._query(vector=vector, limit=max(k * 4, k), query_filter=query_filter)
        terms = _terms(query)
        results: list[HybridSearchResult] = []
        for point in raw_results:
            payload = point.payload or {}
            lexical_score = _lexical_score(terms, str(payload.get("lexical_text") or payload.get("text") or ""))
            semantic_score = float(getattr(point, "score", 0.0) or 0.0)
            combined = (semantic_score * (1.0 - self.lexical_weight)) + (lexical_score * self.lexical_weight)
            results.append(
                HybridSearchResult(
                    content=str(payload.get("text") or ""),
                    path=str(payload.get("path") or payload.get("source") or ""),
                    name=str(payload.get("name") or ""),
                    type=str(payload.get("type") or ""),
                    start_line=int(payload.get("start_line") or 0),
                    end_line=int(payload.get("end_line") or 0),
                    semantic_score=semantic_score,
                    lexical_score=lexical_score,
                    combined_score=combined,
                )
            )
        results.sort(key=lambda item: item.combined_score, reverse=True)
        logger.info("Retrieved %s Qdrant context chunks", len(results[:k]))
        return results[:k]

    def _query(self, *, vector: list[float], limit: int, query_filter: Any | None) -> list[Any]:
        try:
            return self.client.query_points(
                collection_name=self.config.collection_name,
                query=vector,
                using=self.config.vector_name,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            ).points
        except AttributeError:
            return self.client.search(
                collection_name=self.config.collection_name,
                query_vector=(self.config.vector_name, vector),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

    def _filter(self, *, repo: str | None, commit: str | None):
        if not repo and not commit:
            return None
        from qdrant_client import models

        must = []
        if repo:
            must.append(models.FieldCondition(key="repo", match=models.MatchValue(value=repo)))
        if commit:
            must.append(models.FieldCondition(key="commit", match=models.MatchValue(value=commit)))
        return models.Filter(must=must)

    def _build_client(self):
        from qdrant_client import QdrantClient

        if self.config.qdrant_url:
            return QdrantClient(
                url=self.config.qdrant_url,
                api_key=self.config.qdrant_api_key,
                check_compatibility=False,
            )
        return QdrantClient(path=self.config.qdrant_path or ":memory:")


def retrieve(query: str, k: int = 8, *, repo: str | None = None, commit: str | None = None) -> list[dict[str, Any]]:
    """Convenience retrieval function using environment Qdrant config."""

    return [result.__dict__ for result in QdrantHybridRetriever().retrieve(query, k=k, repo=repo, commit=commit)]


def _terms(text: str) -> list[str]:
    seen = set()
    terms: list[str] = []
    for term in re.findall(r"[A-Za-z_][A-Za-z0-9_.$:/-]{2,}", text.lower()):
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _lexical_score(terms: list[str], text: str) -> float:
    if not terms or not text:
        return 0.0
    hits = sum(1 for term in terms if term in text.lower())
    return min(1.0, hits / math.sqrt(len(terms)))

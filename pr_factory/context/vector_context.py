from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pr_factory.agents.llm import get_embedder
from pr_factory.context.indexers.hybrid_qdrant import QdrantCodeIndexer, QdrantIndexConfig
from pr_factory.context.retrievers.hybrid_qdrant import HybridSearchResult, QdrantHybridRetriever
from pr_factory.observability import get_logger
from pr_factory.repo_investigation import RepositoryInvestigation

logger = get_logger(__name__)


def qdrant_enabled() -> bool:
    return os.getenv("PR_FACTORY_USE_QDRANT", "true").strip().lower() not in {"0", "false", "no", "off"}


def retrieve_vector_context(
    *,
    repo_path: str | Path,
    repo_name: str,
    commit: str | None,
    investigation: RepositoryInvestigation,
) -> list[dict[str, Any]]:
    if not qdrant_enabled():
        logger.info("Qdrant vector context disabled")
        return []

    query = build_vector_query(investigation)
    if not query:
        return []

    top_k = int(os.getenv("PR_FACTORY_QDRANT_TOP_K", "8"))
    config = QdrantIndexConfig.from_env()
    try:
        return _index_and_retrieve(config, repo_path=repo_path, repo_name=repo_name, commit=commit, query=query, top_k=top_k)
    except Exception as error:  # noqa: BLE001 - vector context is optional augmentation.
        logger.exception("Qdrant vector context failed: %s", error)
        if config.qdrant_url:
            logger.warning("Retrying Qdrant vector context with local embedded Qdrant because remote URL failed")
            local_config = QdrantIndexConfig(
                collection_name=config.collection_name,
                vector_name=config.vector_name,
                qdrant_path=config.qdrant_path or ":memory:",
                recreate=config.recreate,
                batch_size=config.batch_size,
            )
            try:
                return _index_and_retrieve(local_config, repo_path=repo_path, repo_name=repo_name, commit=commit, query=query, top_k=top_k)
            except Exception as fallback_error:  # noqa: BLE001
                logger.exception("Local embedded Qdrant fallback failed: %s", fallback_error)
        return []


def _index_and_retrieve(
    config: QdrantIndexConfig,
    *,
    repo_path: str | Path,
    repo_name: str,
    commit: str | None,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    embedder = get_embedder()
    indexer = QdrantCodeIndexer(config=config, embedder=embedder)
    indexed = indexer.index_repository(repo_path, repo_name=repo_name, commit=commit)
    retriever = QdrantHybridRetriever(config=config, embedder=embedder, client=indexer.client)
    results = retriever.retrieve(query, k=top_k, repo=repo_name, commit=commit)
    logger.info("Qdrant indexed %s chunks and retrieved %s vector context chunks", indexed, len(results))
    return [_result_to_dict(result) for result in results]


def build_vector_query(investigation: RepositoryInvestigation) -> str:
    parts = list(investigation.search_terms[:40])
    for candidate in investigation.candidate_files[:5]:
        parts.append(candidate.path)
        parts.extend(candidate.matched_terms[:8])
    return "\n".join(dict.fromkeys(part for part in parts if part))


def _result_to_dict(result: HybridSearchResult) -> dict[str, Any]:
    data = asdict(result)
    data["source"] = "qdrant"
    return data

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Any

from pr_factory.agents.json_utils import model_json_schema_text


DEFAULT_AGENT_MODEL = "gpt-5.5"
DEFAULT_EMBEDDING_MODEL = "hash-384"


def agent_model() -> str:
    return os.getenv("PR_FACTORY_AGENT_MODEL") or os.getenv("PR_FACTORY_SIGNAL_AGENT_MODEL", DEFAULT_AGENT_MODEL)


class HermesAgentLLM:
    """Small LangChain-compatible backend using Hermes' AIAgent.

    It implements the subset our planner/coder agents need: invoke() and
    with_structured_output(). This keeps orchestration LangChain-friendly while
    avoiding langchain-openai/OpenAI SDK version conflicts with Hermes Agent.
    """

    def __init__(self, model: str | None = None, schema: type | None = None) -> None:
        self.model = model or agent_model()
        self.schema = schema

    def with_structured_output(self, schema: type) -> "HermesAgentLLM":
        return HermesAgentLLM(model=self.model, schema=schema)

    def invoke(self, prompt: str) -> str:
        from run_agent import AIAgent

        final_prompt = prompt
        if self.schema is not None:
            final_prompt = (
                f"{prompt}\n\nReturn only strict JSON matching this schema:\n"
                f"{model_json_schema_text(self.schema)}"
            )
        agent = AIAgent(model=self.model, quiet_mode=True, enabled_toolsets=[])
        return agent.chat(final_prompt)


@dataclass(frozen=True)
class HashEmbedder:
    """Deterministic local embedder for offline indexing and tests."""

    dimension: int = 384

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[A-Za-z0-9_.:/-]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector
        return [value / norm for value in vector]


class OpenAIEmbedder:
    """OpenAI-compatible embedding adapter with LangChain-style methods."""

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        from openai import OpenAI

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [list(item.embedding) for item in response.data]


def get_embedder(provider: str | None = None, model: str | None = None, **kwargs: Any):
    """Return an embedder with embed_query/embed_documents methods.

    Defaults to a deterministic local hash embedder so Qdrant indexing works in
    offline/dev environments. Set PR_FACTORY_EMBEDDINGS_PROVIDER=openai to use
    an OpenAI-compatible embeddings endpoint.
    """

    provider = (provider or os.getenv("PR_FACTORY_EMBEDDINGS_PROVIDER", "hash")).strip().lower()
    model = model or os.getenv("PR_FACTORY_EMBEDDINGS_MODEL", DEFAULT_EMBEDDING_MODEL)
    if provider == "hash":
        dimension = int(os.getenv("PR_FACTORY_EMBEDDINGS_DIM", "384"))
        return HashEmbedder(dimension=dimension)
    if provider == "openai":
        return OpenAIEmbedder(
            model=model,
            api_key=kwargs.get("api_key") or os.getenv("PR_FACTORY_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=kwargs.get("base_url") or os.getenv("PR_FACTORY_LLM_BASE_URL"),
        )
    raise ValueError(f"Unsupported embeddings provider: {provider}")


def build_langchain_chat_model(**overrides: Any):
    """Create the planner/coder LLM backend.

    Default: HermesAgentLLM, which is LangChain-compatible for our use and avoids
    dependency conflicts. Set PR_FACTORY_LLM_BACKEND=openai to opt into
    langchain-openai when your environment supports it.
    """

    backend = os.getenv("PR_FACTORY_LLM_BACKEND", "hermes").strip().lower()
    model = overrides.pop("model", None) or agent_model()
    if backend != "openai":
        return HermesAgentLLM(model=model)

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as error:
        raise RuntimeError(
            "PR_FACTORY_LLM_BACKEND=openai requires langchain-openai. Install a "
            "version compatible with this environment or unset PR_FACTORY_LLM_BACKEND "
            "to use the Hermes backend."
        ) from error

    kwargs: dict[str, Any] = {"model": model, "temperature": overrides.pop("temperature", 0)}
    base_url = overrides.pop("base_url", None) or os.getenv("PR_FACTORY_LLM_BASE_URL")
    api_key = overrides.pop("api_key", None) or os.getenv("PR_FACTORY_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    kwargs.update(overrides)
    return ChatOpenAI(**kwargs)

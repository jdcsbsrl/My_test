"""Local semantic retrieval support for KB v3.0.

The module is intentionally dependency-light: it uses sentence-transformers
when configured and installed, otherwise falls back to a deterministic hashing
embedder so the RAG contract can be tested in CI and offline workspaces.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.auto_test.core.config_manager import EnvironmentType, EnvironmentSecurityError

from .path_utils import find_project_root


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,2}")


@dataclass(frozen=True)
class SemanticConfig:
    enabled: bool = False
    provider: str = "hashing"
    model_name: str = "BAAI/bge-small-zh-v1.5"
    vector_store_path: str = "assets/knowledge_base/index/vector/vector_store.json"
    dimension: int = 384
    similarity_threshold: float = 0.12
    top_k: int = 5

    @classmethod
    def from_env(cls) -> "SemanticConfig":
        return cls(
            enabled=os.getenv("RAG_SEMANTIC_ENABLED", "0").lower() in ("1", "true", "yes"),
            provider=os.getenv("RAG_EMBEDDING_PROVIDER", "hashing").lower(),
            model_name=os.getenv("RAG_EMBEDDING_MODEL", cls.model_name),
            vector_store_path=os.getenv("RAG_VECTOR_STORE_PATH", cls.vector_store_path),
            dimension=int(os.getenv("RAG_EMBEDDING_DIM", str(cls.dimension))),
            similarity_threshold=float(os.getenv("RAG_SIMILARITY_THRESHOLD", str(cls.similarity_threshold))),
            top_k=int(os.getenv("RAG_TOP_K", str(cls.top_k))),
        )


def validate_rag_environment(env: str | None = None) -> str:
    current = env or os.getenv("TEST_ENV", "test")
    if not EnvironmentType.is_allowed(current):
        raise EnvironmentSecurityError(
            "环境安全异常: RAG 向量化与生成仅允许在 test, test_env, uat 环境执行。"
            f"当前环境: {current}"
        )
    return current


class HashingEmbeddingProvider:
    """Small deterministic embedder used as an offline fallback."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.name = "hashing"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.name = "sentence-transformers"
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]


def build_embedding_provider(config: SemanticConfig) -> Any:
    if config.provider in {"sentence-transformers", "sentence_transformers"}:
        try:
            return SentenceTransformerEmbeddingProvider(config.model_name)
        except Exception:
            return HashingEmbeddingProvider(config.dimension)
    return HashingEmbeddingProvider(config.dimension)


class LocalVectorStore:
    """Append-replace JSON vector store for PoC and local development."""

    def __init__(self, path: str | Path) -> None:
        root = Path(find_project_root(__file__))
        self.path = Path(path)
        if not self.path.is_absolute():
            self.path = root / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "updated_at": None, "items": []}
        with self.path.open(encoding="utf-8") as f:
            return json.load(f)

    def save_items(self, items: list[dict[str, Any]]) -> None:
        payload = {"version": 1, "updated_at": time.time(), "items": items}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def upsert_items(self, new_items: list[dict[str, Any]], source_file: str | None = None) -> int:
        payload = self.load()
        old_items = payload.get("items", [])
        if source_file:
            old_items = [item for item in old_items if item.get("source_file") != source_file]
        by_id = {item["id"]: item for item in old_items}
        for item in new_items:
            by_id[item["id"]] = item
        self.save_items(list(by_id.values()))
        return len(new_items)

    def search(self, query_vector: list[float], top_k: int, threshold: float) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in self.load().get("items", []):
            score = cosine_similarity(query_vector, item.get("embedding", []))
            if score >= threshold:
                result = {key: value for key, value in item.items() if key != "embedding"}
                result["similarity_score"] = score
                results.append(result)
        results.sort(key=lambda item: item["similarity_score"], reverse=True)
        return results[:top_k]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def chunk_to_text(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata", {})
    content = chunk.get("content", chunk)
    return json.dumps({"metadata": metadata, "content": content}, ensure_ascii=False, sort_keys=True)


class SemanticIndexer:
    def __init__(self, config: SemanticConfig | None = None) -> None:
        self.config = config or SemanticConfig.from_env()
        self.provider = build_embedding_provider(self.config)
        self.store = LocalVectorStore(self.config.vector_store_path)

    def index_chunks(self, chunks: list[dict[str, Any]], source_file: str | None = None) -> int:
        validate_rag_environment()
        texts = [chunk_to_text(chunk) for chunk in chunks]
        vectors = self.provider.embed(texts) if texts else []
        items: list[dict[str, Any]] = []
        for chunk, text, vector in zip(chunks, texts, vectors):
            metadata = chunk.get("metadata", {})
            chunk_id = str(chunk.get("chunk_id") or metadata.get("chunk_id") or hashlib.sha1(text.encode()).hexdigest())
            items.append(
                {
                    "id": chunk_id,
                    "chunk_id": chunk_id,
                    "source_file": source_file or metadata.get("source_file") or metadata.get("file_title", ""),
                    "metadata": metadata,
                    "content": chunk.get("content", chunk),
                    "snippet": text[:240],
                    "embedding_provider": getattr(self.provider, "name", "unknown"),
                    "embedding": vector,
                }
            )
        return self.store.upsert_items(items, source_file=source_file)

    def search(self, keyword: str, top_k: int | None = None, threshold: float | None = None) -> list[dict[str, Any]]:
        validate_rag_environment()
        query_vector = self.provider.embed([keyword])[0]
        return self.store.search(
            query_vector,
            top_k=top_k or self.config.top_k,
            threshold=self.config.similarity_threshold if threshold is None else threshold,
        )

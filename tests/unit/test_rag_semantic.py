import pytest

from modules.auto_test.core.config_manager import EnvironmentSecurityError
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
from modules.trae_test.utils.rag_semantic import SemanticConfig, SemanticIndexer, validate_rag_environment


def test_validate_rag_environment_blocks_production():
    with pytest.raises(EnvironmentSecurityError):
        validate_rag_environment("production")


def test_semantic_indexer_uses_local_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    config = SemanticConfig(
        enabled=True,
        provider="hashing",
        vector_store_path=str(tmp_path / "vector_store.json"),
        similarity_threshold=0.01,
        top_k=3,
    )
    indexer = SemanticIndexer(config)

    indexed = indexer.index_chunks(
        [
            {
                "chunk_id": "sales-order-approval",
                "metadata": {"file_title": "销售模块"},
                "content": {"rule_name": "销售订单审核", "rule_description": "销售订单提交后需要审核"},
            },
            {
                "chunk_id": "purchase-stock",
                "metadata": {"file_title": "采购模块"},
                "content": {"rule_name": "采购入库", "rule_description": "采购单完成后生成入库记录"},
            },
        ],
        source_file="sales.json",
    )

    results = indexer.search("销售订单审核", top_k=1, threshold=0.01)

    assert indexed == 2
    assert results[0]["chunk_id"] == "sales-order-approval"
    assert results[0]["similarity_score"] > 0


def test_knowledge_retriever_hybrid_merges_semantic_and_lexical(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", str(tmp_path / "vector_store.json"))
    monkeypatch.setenv("RAG_SIMILARITY_THRESHOLD", "0.01")

    indexer = SemanticIndexer(SemanticConfig.from_env())
    indexer.index_chunks(
        [
            {
                "chunk_id": "sales-order-submit",
                "metadata": {"file_title": "销售模块"},
                "content": {"rule_name": "销售订单提交", "rule_description": "提交后进入审核状态"},
            }
        ],
        source_file="sales.json",
    )

    retriever = KnowledgeRetriever()
    retriever.search_by_inverted_index = lambda keyword, top_k=10: [
        {
            "chunk_id": "sales-order-submit",
            "similarity_score": 0.8,
            "content": {"rule_name": "销售订单提交"},
        }
    ]

    results = retriever.retrieve("销售订单提交", mode="hybrid")

    assert results
    assert results[0]["chunk_id"] == "sales-order-submit"
    assert set(results[0]["retrieval_sources"]) == {"semantic", "lexical"}
    assert results[0]["hybrid_score"] > 0

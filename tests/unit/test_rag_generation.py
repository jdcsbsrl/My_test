import json

import pytest

from modules.auto_test.core.config_manager import EnvironmentSecurityError
from modules.trae_test.utils.rag_generation import (
    LLMAPIStyle,
    LocalRuleRAGCaseGenerator,
    RAGGenerationEvaluator,
    SelfHostedLLMRAGCaseGenerator,
    case_contains_points,
)
from modules.trae_test.utils.template_builder import ALL_FIELDS


class StubRetriever:
    def retrieve(self, keyword, mode="auto"):
        assert mode == "hybrid"
        return [
            {
                "chunk_id": "sales-balance",
                "content": {
                    "rule_name": "余额付款约束",
                    "rule_description": "客户余额不足时不能完成付款",
                },
            }
        ]


def test_local_rule_generator_returns_15_standard_fields(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    generator = LocalRuleRAGCaseGenerator(retriever=StubRetriever())

    case = generator.generate_case("客户余额不足能否付款")

    assert list(case.keys()) == ALL_FIELDS
    assert "余额付款约束" in case["预期结果"]
    assert "客户余额" in case["预期结果"]


def test_case_contains_points_scores_expected_points():
    matched, hit_rate = case_contains_points(
        {"用例名称": "测试余额付款", "预期结果": "余额付款约束；客户余额不足时不能付款"},
        ["余额付款约束", "客户余额", "库存"],
    )

    assert matched == ["余额付款约束", "客户余额"]
    assert hit_rate == 2 / 3


def test_generation_evaluator_blocks_low_quality_local_case(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    evaluator = RAGGenerationEvaluator(
        generator=LocalRuleRAGCaseGenerator(retriever=StubRetriever()),
        point_threshold=0.6,
        score_threshold=50,
    )

    result = evaluator.evaluate_one("客户余额不足能否付款", ["余额付款约束", "客户余额"])

    assert result.audit_passed is False
    assert result.point_hit_rate == 1.0
    assert result.quality_score < 85
    assert result.original_score == 70
    assert result.optimized_score == result.final_score
    assert result.cold_start is True
    assert result.optimization_attempts == 3
    assert result.passed is False


def test_self_hosted_llm_provider_requires_private_endpoint(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    monkeypatch.setenv("RAG_LLM_ENDPOINT", "https://api.example.com/generate")

    with pytest.raises(EnvironmentSecurityError):
        SelfHostedLLMRAGCaseGenerator(retriever=StubRetriever())


def test_self_hosted_llm_provider_blocks_link_local_metadata_endpoint(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    monkeypatch.setenv("RAG_LLM_ENDPOINT", "http://169.254.169.254/latest/meta-data")

    with pytest.raises(EnvironmentSecurityError):
        SelfHostedLLMRAGCaseGenerator(retriever=StubRetriever())


def test_self_hosted_llm_provider_parses_15_field_case(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    monkeypatch.setenv("RAG_LLM_ENDPOINT", "http://127.0.0.1:11434/generate")
    provider = SelfHostedLLMRAGCaseGenerator(retriever=StubRetriever())
    raw = {
        "case": {
            "用例目录": "销售模块",
            "用例名称": "测试余额付款",
            "前置条件": "已登录",
            "用例步骤": "1. 打开销售订单\n2. 发起付款",
            "预期结果": "余额付款约束；客户余额不足时不能付款",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "高",
            "创建人": "余小龙",
            "优先级": "P1",
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "客户余额不足能否付款",
        }
    }

    case = provider._parse_case(json.dumps(raw, ensure_ascii=False))

    assert list(case.keys()) == ALL_FIELDS
    assert case["创建人"] == "余小龙"
    assert case["需求ID"] == ""


def test_self_hosted_llm_provider_builds_ollama_payload(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    provider = SelfHostedLLMRAGCaseGenerator(
        retriever=StubRetriever(),
        endpoint="http://127.0.0.1:11434/api/generate",
        api_style=LLMAPIStyle.OLLAMA.value,
        model="qwen2.5:7b",
    )

    payload = provider._build_payload("生成销售测试用例")

    assert payload["model"] == "qwen2.5:7b"
    assert payload["prompt"] == "生成销售测试用例"
    assert payload["stream"] is False


def test_self_hosted_llm_provider_parses_ollama_response(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    provider = SelfHostedLLMRAGCaseGenerator(
        retriever=StubRetriever(),
        endpoint="http://127.0.0.1:11434/api/generate",
        api_style=LLMAPIStyle.OLLAMA.value,
    )
    case_json = json.dumps(
        {
            "用例目录": "销售模块",
            "用例名称": "测试余额付款",
            "用例步骤": "1. 发起付款",
            "预期结果": "余额付款约束",
            "用例等级": "高",
            "优先级": "P1",
            "创建人": "余小龙",
        },
        ensure_ascii=False,
    )

    case = provider._parse_case(json.dumps({"response": f"```json\n{case_json}\n```"}, ensure_ascii=False))

    assert case["用例名称"] == "测试余额付款"
    assert case["创建人"] == "余小龙"


def test_self_hosted_llm_provider_parses_openai_compatible_response(monkeypatch):
    monkeypatch.setenv("TEST_ENV", "test")
    provider = SelfHostedLLMRAGCaseGenerator(
        retriever=StubRetriever(),
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        api_style=LLMAPIStyle.OPENAI_COMPATIBLE.value,
    )
    content = json.dumps(
        {
            "用例目录": "销售模块",
            "用例名称": "测试币种更换",
            "用例步骤": "1. 更换币种",
            "预期结果": "币种更换约束",
            "用例等级": "高",
            "优先级": "P1",
        },
        ensure_ascii=False,
    )
    raw = {"choices": [{"message": {"content": content}}]}

    case = provider._parse_case(json.dumps(raw, ensure_ascii=False))

    assert case["用例名称"] == "测试币种更换"
    assert case["创建人"] == "余小龙"

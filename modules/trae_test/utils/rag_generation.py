"""RAG-backed test case generation evaluation primitives."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from ipaddress import ip_address
from typing import Any, Protocol
from urllib.parse import urlparse

from modules.auto_test.core.config_manager import EnvironmentSecurityError
from modules.trae_test.orchestrator.audit_gateway import AuditGateway
from modules.trae_test.orchestrator.config import AuditConfig

from .knowledge_retriever import KnowledgeRetriever
from .template_builder import ALL_FIELDS
from .test_case_strategy import TestCaseScoreEngine, TestCaseStrategy

DEFAULT_CASE_CREATOR = "余小龙"
DEFAULT_LLM_TIMEOUT = 60
DEFAULT_LLM_MODEL = "local-rag-generator"


@dataclass(frozen=True)
class GenerationEvalResult:
    query: str
    generated_case: dict[str, Any]
    expected_points: list[str]
    matched_points: list[str]
    point_hit_rate: float
    audit_passed: bool
    audit_errors: list[dict[str, str]]
    audit_warnings: list[dict[str, str]]
    quality_score: float
    passed: bool


class RAGCaseGenerator(Protocol):
    provider_name: str

    def generate_case(self, query: str) -> dict[str, Any]:
        ...


class RAGGenerationProvider(str, Enum):
    LOCAL_RULE = "local-rule"
    SELF_HOSTED_LLM = "self-hosted-llm"


class LLMAPIStyle(str, Enum):
    GENERIC = "generic"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai-compatible"


def context_to_text(results: list[dict[str, Any]], limit: int = 3) -> str:
    snippets: list[str] = []
    for item in results[:limit]:
        content = item.get("content", item)
        snippets.append(summarize_content(content))
    return "\n".join(snippets)


def summarize_content(content: Any) -> str:
    if isinstance(content, dict):
        values = []
        for key in (
            "rule_name",
            "rule_description",
            "rule_content",
            "description",
            "title",
            "name",
        ):
            value = content.get(key)
            if value:
                values.append(str(value))
        if values:
            return "；".join(values)
    text = json.dumps(content, ensure_ascii=False, sort_keys=True) if not isinstance(content, str) else content
    text = re.sub(r'["{}\[\],:]+', " ", text)
    return re.sub(r"\s+", " ", text).strip()


def case_contains_points(case: dict[str, Any], expected_points: list[str]) -> tuple[list[str], float]:
    blob = "\n".join(str(case.get(field, "")) for field in ALL_FIELDS)
    matched = [point for point in expected_points if point and point in blob]
    if not expected_points:
        return [], 0.0
    return matched, len(matched) / len(expected_points)


def infer_scenario_type(text: str) -> str:
    if any(keyword in text for keyword in ("必须", "仅", "不可", "不能", "禁止", "边界", "不足")):
        return "boundary"
    if any(keyword in text for keyword in ("失败", "异常", "错误", "报错", "无效")):
        return "exception"
    return "normal"


class LocalRuleRAGCaseGenerator:
    """Local deterministic provider used until a self-hosted LLM is wired in."""

    provider_name = RAGGenerationProvider.LOCAL_RULE.value

    def __init__(self, retriever: KnowledgeRetriever | None = None, creator: str | None = None) -> None:
        self.retriever = retriever or KnowledgeRetriever()
        self.creator = creator or os.getenv("RAG_TEST_CASE_CREATOR", DEFAULT_CASE_CREATOR)

    def generate_case(self, query: str) -> dict[str, Any]:
        retrieved = self.retriever.retrieve(query, mode="hybrid")
        context = context_to_text(retrieved if isinstance(retrieved, list) else [])
        rule_text = context or query
        scenario_type = infer_scenario_type(rule_text)
        steps, expected = TestCaseStrategy.generate_case_content(
            test_point=query,
            business_rule=rule_text[: TestCaseStrategy._BUSINESS_RULE_CONTENT_LENGTH],
            scenario_type=scenario_type,
        )
        if context:
            expected = f"{expected}\n3. 符合知识库规则：{context[:240]}"
        case = {
            "用例目录": "销售模块 - RAG生成评估",
            "用例名称": f"测试_{query}"[:50],
            "需求ID": "",
            "前置条件": "系统已正常启动，用户已登录并具备销售模块权限",
            "用例步骤": steps,
            "预期结果": expected,
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "高",
            "创建人": self.creator,
            "优先级": "P1",
            "是否可自动化": "是",
            "关联缺陷ID": "",
            "回归测试标识": "是",
            "知识库关联": query,
        }
        return {field: case.get(field, "") for field in ALL_FIELDS}


class SelfHostedLLMRAGCaseGenerator:
    """Self-hosted LLM provider for release-gate evaluation.

    Supported HTTP styles:
      generic: POST {"prompt": "..."} -> 15-field JSON object or {"case": {...}}
      ollama: POST {"model": "...", "prompt": "...", "stream": false}
      openai-compatible: POST {"model": "...", "messages": [...]}
    """

    provider_name = RAGGenerationProvider.SELF_HOSTED_LLM.value

    def __init__(
        self,
        retriever: KnowledgeRetriever | None = None,
        endpoint: str | None = None,
        timeout: int | None = None,
        creator: str | None = None,
        api_style: str | None = None,
        model: str | None = None,
    ) -> None:
        self.retriever = retriever or KnowledgeRetriever()
        self.endpoint = endpoint or os.getenv("RAG_LLM_ENDPOINT", "")
        self.timeout = timeout or int(os.getenv("RAG_LLM_TIMEOUT", str(DEFAULT_LLM_TIMEOUT)))
        self.creator = creator or os.getenv("RAG_TEST_CASE_CREATOR", DEFAULT_CASE_CREATOR)
        self.api_style = LLMAPIStyle(api_style or os.getenv("RAG_LLM_API_STYLE", LLMAPIStyle.GENERIC.value))
        self.model = model or os.getenv("RAG_LLM_MODEL", DEFAULT_LLM_MODEL)
        if not self.endpoint:
            raise ValueError("RAG_LLM_ENDPOINT is required when provider=self-hosted-llm")
        if not self._is_local_or_private_endpoint(self.endpoint):
            raise EnvironmentSecurityError("RAG_LLM_ENDPOINT must be local or intranet self-hosted")

    @staticmethod
    def _is_local_or_private_endpoint(endpoint: str) -> bool:
        host = urlparse(endpoint).hostname or ""
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        if host.endswith((".local", ".corp", ".internal")):
            return True
        try:
            parsed = ip_address(host)
            if parsed.is_link_local or parsed.is_multicast or parsed.is_unspecified or parsed.is_reserved:
                return False
            return parsed.is_private or parsed.is_loopback
        except ValueError:
            return False

    def generate_case(self, query: str) -> dict[str, Any]:
        retrieved = self.retriever.retrieve(query, mode="hybrid")
        context = context_to_text(retrieved if isinstance(retrieved, list) else [], limit=5)
        prompt = self._build_prompt(query, context)
        payload = json.dumps(self._build_payload(prompt), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"self-hosted LLM request failed: {exc}") from exc
        return self._parse_case(raw)

    def _build_payload(self, prompt: str) -> dict[str, Any]:
        if self.api_style == LLMAPIStyle.OLLAMA:
            return {"model": self.model, "prompt": prompt, "stream": False}
        if self.api_style == LLMAPIStyle.OPENAI_COMPATIBLE:
            return {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "只返回JSON对象，不要Markdown。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            }
        return {"prompt": prompt}

    def _build_prompt(self, query: str, context: str) -> str:
        fields = "、".join(ALL_FIELDS)
        return (
            "你是ERP销售模块测试用例生成器。只返回一个JSON对象，不要Markdown。\n"
            f"必须包含且仅包含以下15个字段：{fields}。\n"
            f"创建人必须填写：{self.creator}；优先级必须是P0/P1/P2；用例等级必须是高/中/低。\n"
            f"测试需求：{query}\n"
            f"RAG知识上下文：{context}\n"
        )

    def _parse_case(self, raw: str) -> dict[str, Any]:
        data = json.loads(raw)
        data = self._extract_case_payload(data)
        if isinstance(data, str):
            data = json.loads(self._strip_json_fence(data))
            data = self._extract_case_payload(data)
        if isinstance(data, dict) and "case" in data and isinstance(data["case"], dict):
            data = data["case"]
        if not isinstance(data, dict):
            raise ValueError("LLM response must be a JSON object")
        data["创建人"] = data.get("创建人") or self.creator
        return {field: data.get(field, "") for field in ALL_FIELDS}

    @staticmethod
    def _extract_case_payload(data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("response"), str):
            return data["response"]
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            content = data["message"].get("content")
            if isinstance(content, str):
                return content
        if isinstance(data, dict) and isinstance(data.get("choices"), list) and data["choices"]:
            first = data["choices"][0]
            if isinstance(first, dict):
                message = first.get("message", {})
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
        return data

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        return stripped.strip()


def build_rag_case_generator(provider: str, retriever: KnowledgeRetriever | None = None) -> RAGCaseGenerator:
    provider_value = RAGGenerationProvider(provider)
    if provider_value == RAGGenerationProvider.LOCAL_RULE:
        return LocalRuleRAGCaseGenerator(retriever=retriever)
    return SelfHostedLLMRAGCaseGenerator(retriever=retriever)


class RAGGenerationEvaluator:
    def __init__(
        self,
        generator: RAGCaseGenerator | None = None,
        audit_gateway: AuditGateway | None = None,
        score_engine: TestCaseScoreEngine | None = None,
        point_threshold: float = 0.6,
        score_threshold: float = 50.0,
    ) -> None:
        self.generator = generator or LocalRuleRAGCaseGenerator()
        self.audit_gateway = audit_gateway or AuditGateway(
            AuditConfig(interactive_mode=False, auto_approve=True)
        )
        self.score_engine = score_engine or TestCaseScoreEngine()
        self.point_threshold = point_threshold
        self.score_threshold = score_threshold

    def evaluate_one(self, query: str, expected_points: list[str]) -> GenerationEvalResult:
        case = self.generator.generate_case(query)
        quality_score = self.score_engine.score(case)
        audit_result = self.audit_gateway.audit([case], "test_case", {"block_on_fail": False})
        matched, point_hit_rate = case_contains_points(case, expected_points)
        passed = (
            audit_result.passed
            and quality_score >= self.score_threshold
            and point_hit_rate >= self.point_threshold
        )
        return GenerationEvalResult(
            query=query,
            generated_case=case,
            expected_points=expected_points,
            matched_points=matched,
            point_hit_rate=round(point_hit_rate, 4),
            audit_passed=audit_result.passed,
            audit_errors=audit_result.errors,
            audit_warnings=audit_result.warnings,
            quality_score=quality_score,
            passed=passed,
        )

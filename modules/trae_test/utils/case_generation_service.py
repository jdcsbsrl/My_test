"""Requirement-to-delivery service using existing retrieval, providers and audit."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from .template_builder import ALL_FIELDS, LEGACY_RUNTIME_FIELDS
from .runtime_quality import attach_runtime_quality, read_runtime_quality
from .test_case_strategy import TestCaseOptimizer, TestCaseScoreEngine


def apply_field_policy(case: dict, rules: dict) -> dict:
    """Only configured fixed fields and single-value fields are forced."""
    for field, rule in rules.items():
        if field not in ALL_FIELDS or not isinstance(rule, dict):
            continue
        values = rule.get("valid_values", [])
        if rule.get("fixed", False) or len(values) == 1:
            value = rule.get("default_value", values[0] if values else None)
            if value is None or (values and value not in values):
                raise ValueError(f"Invalid fixed-field policy: {field}")
            case[field] = value
        elif not case.get(field) and "default_value" in rule:
            case[field] = rule["default_value"]
    return case


class RetrievedContext:
    def __init__(self, items):
        self.items = items

    def retrieve(self, *args, **kwargs):
        return deepcopy(self.items)


class CaseGenerationService:
    def __init__(self, retriever=None, gateway=None, rules=None, provider_factory=None):
        from .knowledge_retriever import KnowledgeRetriever
        from ..orchestrator.audit_gateway import AuditGateway
        from ..orchestrator.audit_rules import RuleManager

        self.retriever = retriever or KnowledgeRetriever()
        self.gateway = gateway or AuditGateway()
        self.rules = rules if rules is not None else RuleManager().get_field_value_rules()
        self.provider_factory = provider_factory

    def generate(
        self,
        requirement: str,
        requirement_id: str,
        *,
        provider: str = "local-rule",
        priority: str = "P1",
        candidate: dict | None = None,
        user_evidence: str | None = None,
    ) -> dict:
        if not requirement.strip():
            raise ValueError("需求正文不能为空")
        if user_evidence is not None and (not isinstance(user_evidence, str) or not user_evidence.strip()):
            raise ValueError("用户提供的业务依据必须是非空文本")
        try:
            items = self.retriever.retrieve(requirement, mode="hybrid")
            if not items:
                items = self.retriever.search_business_rules(requirement)
        except (FileNotFoundError, OSError):
            self.retriever.refresh_registry()
            items = self.retriever.retrieve(requirement, mode="hybrid")
        # Exceptions propagate as retrieval errors, never become default test cases.
        if not items and user_evidence is None:
            return {
                "status": "missing_knowledge",
                "cases": [],
                "questions": ["没有检索到业务依据，请补充该需求的业务规则或缩小需求范围。"],
            }
        if isinstance(items, dict):
            items = [{"id": key, "content": value} for key, value in items.items()]
        if not isinstance(items, list):
            raise ValueError("Unsupported KnowledgeRetriever response")
        items = deepcopy(items)
        if user_evidence is not None:
            digest = sha256(user_evidence.encode("utf-8")).hexdigest()
            items.append(
                {
                    "id": "user-requirement:" + digest,
                    "source_type": "user_requirement",
                    "revision": digest,
                    "content": {"description": user_evidence},
                }
            )
        from .rag_generation import LocalRuleRAGCaseGenerator, SelfHostedLLMRAGCaseGenerator
        from ..orchestrator.release_quality_gate import ReleaseQualityGate

        factories = {"local-rule": LocalRuleRAGCaseGenerator, "self-hosted-llm": SelfHostedLLMRAGCaseGenerator}
        factory = self.provider_factory or factories[provider]
        if candidate is not None:
            if not isinstance(candidate, dict):
                raise ValueError("Candidate must be a case object")
            # A local Agent can submit a draft through the same policy/audit pipeline.
            # Never trust runtime approval flags supplied by a draft.
            case = {field: deepcopy(candidate.get(field, "")) for field in ALL_FIELDS}
            for key in ("_runtime_coverage_matrix", "_runtime_rule_binding"):
                if key in candidate:
                    if not isinstance(candidate[key], dict):
                        raise ValueError(f"{key} must be an object")
                    case[key] = deepcopy(candidate[key])
        else:
            if provider == "local-rule" and self.provider_factory is None:
                return {
                    "status": "generation_failed",
                    "cases": [],
                    "questions": [],
                    "sources": items,
                    "generation_errors": [
                        "local-rule是评估基线，不具备从任意需求生成可执行步骤的能力。"
                        "请由本地Agent提交候选内容，或使用已配置的self-hosted-llm；无需确认固定字段。"
                    ],
                }
            generator = factory(retriever=RetrievedContext(items))
            case = generator.generate_case(requirement)
        case["需求ID"] = requirement_id
        case["优先级"] = priority
        apply_field_policy(case, self.rules)
        scorer = TestCaseScoreEngine()
        scorer.record_score(case, "original")
        TestCaseOptimizer(scorer).optimize(case)
        scorer.record_score(case, "optimized")
        scorer.record_score(case, "final")
        case["质量评分"] = read_runtime_quality(case).final_score
        result = self.gateway.audit([case], "test_case", {"block_on_fail": False, "knowledge_sources": items})
        quality = read_runtime_quality(case)
        quality.final_audit_passed = result.passed
        quality.needs_human_review = not result.passed
        attach_runtime_quality(case, quality)
        for field in LEGACY_RUNTIME_FIELDS:
            case.pop(field, None)
        errors = [issue for issue in result.issues if issue.severity == "error"]
        release_decision = ReleaseQualityGate().evaluate(
            cases=[case], audit_result=result, release_scope="generation", require_regression=False
        )
        # A model formatting/field failure is a generation defect, not a question the user must approve.
        information_rules = {"TC_EVIDENCE_REQUIRED", "REQ_COVERAGE_INCOMPLETE", "REQ_SCOPE_BOUNDARY_VIOLATION"}
        questions = list(dict.fromkeys(issue.message for issue in errors if issue.rule_id in information_rules))
        return {
            "status": "ready" if result.passed else "needs_information" if questions else "generation_failed",
            "cases": [case],
            "audit": result.to_dict(),
            "questions": questions,
            "generation_errors": [issue.message for issue in errors if issue.rule_id not in information_rules],
            "sources": items,
            "semantic_status": (
                "contract_checked"
                if result.passed and case.get("_runtime_rule_binding", {}).get("digest")
                else "unverified"
            ),
            "release_decision": release_decision.to_dict(),
        }

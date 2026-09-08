"""User supplied evidence stays distinct from retrieved knowledge."""

import pytest

from modules.trae_test.utils.case_generation_service import CaseGenerationService
from tools.case_generator_cli import generate_case


class EmptyKnowledge:
    def retrieve(self, *args, **kwargs):
        return []

    def search_business_rules(self, *args, **kwargs):
        return []


def test_empty_knowledge_still_blocks_without_explicit_evidence():
    result = CaseGenerationService(retriever=EmptyKnowledge()).generate("需求", "")
    assert result["status"] == "missing_knowledge"


def test_explicit_evidence_has_provenance_but_does_not_invent_cases():
    result = CaseGenerationService(retriever=EmptyKnowledge()).generate("需求", "", user_evidence="客户停用后账号停用")
    assert result["status"] == "generation_failed"
    source = result["sources"][0]
    assert source["source_type"] == "user_requirement"
    assert source["id"].startswith("user-requirement:")
    assert source["content"] == {"description": "客户停用后账号停用"}
    assert "query_contracts" not in source["content"]


def test_retrieval_errors_are_not_hidden_by_user_evidence():
    class BrokenKnowledge(EmptyKnowledge):
        def retrieve(self, *args, **kwargs):
            raise RuntimeError("retrieval unavailable")

    with pytest.raises(RuntimeError, match="retrieval unavailable"):
        CaseGenerationService(retriever=BrokenKnowledge()).generate("需求", "", user_evidence="依据")


@pytest.mark.parametrize("evidence", ["", "  ", {}, 12])
def test_invalid_user_evidence_rejected(evidence):
    with pytest.raises(ValueError, match="非空文本"):
        CaseGenerationService(retriever=EmptyKnowledge()).generate("需求", "", user_evidence=evidence)


def test_cli_passes_user_evidence_to_generation_service(monkeypatch):
    received = {}

    class Service:
        def generate(self, *args, **kwargs):
            received.update(kwargs)
            return {"status": "missing_knowledge", "cases": [], "questions": []}

    monkeypatch.setattr("modules.trae_test.utils.case_generation_service.CaseGenerationService", lambda: Service())
    assert generate_case("销售", "客户管理", requirement="需求", user_evidence="用户依据") == 2
    assert received["user_evidence"] == "用户依据"

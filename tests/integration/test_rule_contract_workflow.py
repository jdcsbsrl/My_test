"""Finite semantic contract and change-selection acceptance on synthetic knowledge."""

from copy import deepcopy

import pytest

from fixtures.mock_order_scenario import MockKnowledgeAPI, candidate, REQUIREMENT_ID, RULES
from modules.trae_test.utils.case_generation_service import CaseGenerationService
from modules.trae_test.utils.case_registry import CaseRegistry
from modules.trae_test.utils.case_health import case_health
from modules.trae_test.utils.rule_contracts import impact_plan
from modules.trae_test.utils.rule_contracts import evaluate_assertions


@pytest.fixture
def service(monkeypatch):
    from modules.trae_test.utils import dir_validator

    monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: {"销售": {"订单处理": ["销售订单"]}})
    return CaseGenerationService(retriever=MockKnowledgeAPI())


@pytest.mark.parametrize("fault", ["source", "revision", "assertion", "coverage", "binding", "expected"])
def test_invalid_contract_is_blocked_without_fixed_field_questions(service, fault):
    draft = candidate("exact")
    if fault == "source":
        draft["_runtime_rule_binding"]["source_id"] = "missing"
    elif fault == "revision":
        draft["_runtime_rule_binding"]["revision"] = "obsolete"
    elif fault == "assertion":
        draft["_runtime_rule_binding"]["assertions"] = [{"field": "rows", "op": "count_range", "value": [24, 24]}]
    elif fault == "coverage":
        draft["_runtime_coverage_matrix"]["business_rules"] = []
    elif fault == "binding":
        draft.pop("_runtime_rule_binding")
    else:
        draft["预期结果"] = "1. 显示订单列表\n2. 记录数量为24"
    result = service.generate(RULES["exact"], REQUIREMENT_ID, candidate=draft)
    assert result["status"] != "ready"
    assert any(error["code"] == "TC_RULE_CONTRACT" for error in result["audit"]["errors"])
    assert result["semantic_status"] == "unverified"


def test_rule_change_selects_only_affected_case_and_preserves_history(service, tmp_path):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    ids = {}
    for kind in RULES:
        result = service.generate(RULES[kind], REQUIREMENT_ID, candidate=candidate(kind))
        assert result["status"] == "ready"
        assert result["semantic_status"] == "contract_checked"
        ids[kind], _ = registry.save(result["cases"][0], REQUIREMENT_ID)
    assert case_health(registry)["similar_candidates"] == []
    sources = MockKnowledgeAPI().retrieve("all")
    assert impact_plan(registry, sources)["selected_case_ids"] == []
    changed = deepcopy(sources)
    next(rule for rule in changed[0]["content"]["query_contracts"] if rule["id"] == "status")["revision"] = "2"
    plan = impact_plan(registry, changed)
    assert plan["selected_case_ids"] == [ids["status"]]
    assert len(registry.list_cases(active_only=False)) == 7


def test_changed_rule_version_does_not_reuse_old_pass(service, tmp_path):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    result = service.generate(RULES["status"], REQUIREMENT_ID, candidate=candidate("status"))
    old = result["cases"][0]
    case_id, version = registry.save(old, REQUIREMENT_ID)
    registry.record_execution(case_id, version, "PASS", "synthetic-evidence.xml")
    sources = MockKnowledgeAPI().retrieve("all")
    next(rule for rule in sources[0]["content"]["query_contracts"] if rule["id"] == "status")["revision"] = "2"
    service.retriever.retrieve = lambda *args, **kwargs: sources
    draft = candidate("status")
    draft["_runtime_rule_binding"]["revision"] = "2"
    result = service.generate(RULES["status"], REQUIREMENT_ID, candidate=draft)
    assert result["status"] == "ready"
    assert registry.save(result["cases"][0], REQUIREMENT_ID, case_id=case_id, reason="rule updated")[1] == 2
    assert registry.list_cases()[0]["last_status"] is None
    assert registry.list_cases(active_only=False)[0]["last_status"] == "PASS"


def test_changed_rule_includes_related_p0(service, tmp_path):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    ids = {}
    for kind in ("basic", "status"):
        result = service.generate(
            RULES[kind], REQUIREMENT_ID, candidate=candidate(kind), priority="P0" if kind == "basic" else "P1"
        )
        ids[kind], _ = registry.save(result["cases"][0], REQUIREMENT_ID)
    sources = MockKnowledgeAPI().retrieve("all")
    next(rule for rule in sources[0]["content"]["query_contracts"] if rule["id"] == "status")["revision"] = "2"
    assert set(impact_plan(registry, sources)["selected_case_ids"]) == set(ids.values())


@pytest.mark.parametrize("kind", list(RULES))
def test_structured_assertions_execute_on_mock_data(kind):
    from fixtures.mock_order_scenario import query_response
    from modules.auto_test.core.regression_checks import order_rows

    filters = {
        "exact": {"orderNo": "MOCK-ORDER-001"},
        "fuzzy": {"orderNo": "MOCK-ORDER"},
        "status": {"orderStatus": "1"},
        "combined": {"orderNo": "MOCK-ORDER", "orderStatus": "1"},
        "empty": {"orderNo": "NO-MATCH"},
    }.get(kind, {})
    payload = {"pageSize": 10, **filters}
    rows = order_rows(query_response(payload))
    second = order_rows(query_response({"pageNum": 2, "pageSize": 10}))
    rule = next(r for r in MockKnowledgeAPI().retrieve("all")[0]["content"]["query_contracts"] if r["id"] == kind)
    evaluate_assertions(rows, rule["assertions"], next_rows=second)
    if kind == "empty":
        evaluate_assertions([], rule["assertions"], next_rows=[])
    else:
        with pytest.raises(AssertionError):
            evaluate_assertions([], rule["assertions"], next_rows=[])

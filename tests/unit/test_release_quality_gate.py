"""Unit contracts for the independent release quality gate."""

from types import SimpleNamespace

from modules.trae_test.orchestrator.release_quality_gate import (
    BLOCKED,
    INCOMPLETE,
    READY_FOR_DELIVERY,
    REQUIRES_REVIEW,
    ReleaseQualityGate,
)


def case(*, priority="P1", score=100, final_audit_passed=True, needs_review=False):
    return {
        "用例名称": "订单查询",
        "优先级": priority,
        "质量评分": score,
        "知识库关联": "订单查询规则",
        "_runtime_quality": {
            "final_audit_passed": final_audit_passed,
            "needs_human_review": needs_review,
        },
    }


def report(*statuses, planned=None):
    return SimpleNamespace(
        results=[{"test_name": f"case-{index}", "status": status} for index, status in enumerate(statuses)],
        planned_count=planned if planned is not None else len(statuses),
    )


def test_generation_gate_does_not_use_score_as_a_blocker():
    result = ReleaseQualityGate().evaluate(cases=[case(score=40)], release_scope="generation")

    assert result.status == READY_FOR_DELIVERY
    assert result.can_deliver is True
    assert result.warnings[0]["code"] == "STRUCTURAL_SCORE_LOW"


def test_release_scope_requires_p0_even_when_structure_passes():
    result = ReleaseQualityGate().evaluate(cases=[case()], release_scope="release")

    assert result.status == BLOCKED
    assert any(issue["code"] == "P0_NOT_PRESENT" for issue in result.blocking_issues)


def test_release_scope_blocks_p0_failure():
    result = ReleaseQualityGate().evaluate(
        cases=[case(priority="P0")],
        audit_result={"errors": []},
        regression_report=report("FAIL"),
        release_scope="release",
    )

    assert result.status == BLOCKED
    assert any(issue["code"] == "REGRESSION_FAILED" for issue in result.blocking_issues)


def test_missing_regression_is_incomplete_not_success():
    result = ReleaseQualityGate().evaluate(cases=[case()], release_scope="module")

    assert result.status == INCOMPLETE
    assert result.can_deliver is False


def test_blocked_regression_requires_review():
    result = ReleaseQualityGate().evaluate(cases=[case()], regression_report=report("BLOCKED"), release_scope="module")

    assert result.status == REQUIRES_REVIEW
    assert result.required_review[0]["code"] == "REGRESSION_NOT_VERIFIED"


def test_registered_p0_name_matches_versioned_execution_result():
    registered = case(priority="P0")
    registered["_registered_name"] = "TC-001 v2"
    result = ReleaseQualityGate().evaluate(
        cases=[registered],
        regression_report=SimpleNamespace(results=[{"test_name": "TC-001 v2", "status": "PASS"}], planned_count=1),
        release_scope="module",
    )

    assert result.status == READY_FOR_DELIVERY


def test_audit_errors_always_block():
    result = ReleaseQualityGate().evaluate(cases=[case()], audit_result={"errors": [{"code": "TC_RULE_CONTRACT"}]})

    assert result.status == BLOCKED
    assert result.can_deliver is False

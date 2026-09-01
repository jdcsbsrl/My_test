from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")


def test_quality_gate_documents_use_85_and_reject_lower_scores():
    content = "\n".join(
        _read(name) for name in ("AGENT_RULES.md", "TRAE_TEST_WORKFLOW.md", "PROJECT_ARTIFACT_PLACEMENT.md")
    )

    assert "最终评分 < 85" in content
    assert "最终评分 >= 85" in content
    assert "评分低于 85" in content
    assert "冷启动评分只能作为临时评分" in content
    assert "原始评分、优化后评分和最终评分" in content


def test_quality_document_contract_requires_business_and_page_object_detail():
    content = _read("PROJECT_ARTIFACT_PLACEMENT.md")

    for fragment in (
        "业务知识和页面对象分点描述",
        "前置条件至少 2 个分点",
        "执行步骤至少 3 个分点",
        "预期结果至少 2 个分点",
        "页面对象、动作",
        "覆盖矩阵",
        "AuditAgent",
        "适量回归按变更风险执行",
        "P0 用例必须执行",
        "_runtime_quality",
        "_runtime_coverage_matrix",
        "score_history",
        "正式Excel仍严格保持15列",
    ):
        assert fragment in content


def test_quality_document_contract_forbids_legacy_thresholds_in_active_rules():
    for name in ("AGENT_RULES.md", "TRAE_TEST_WORKFLOW.md"):
        content = _read(name)
        assert "评分 < 70" not in content
        assert "评分 < 60" not in content

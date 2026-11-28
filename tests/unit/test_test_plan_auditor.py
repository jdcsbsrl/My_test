from pathlib import Path

from modules.trae_test.orchestrator.audit_engine import AuditEngine
from modules.trae_test.orchestrator.audit_models import AuditResult
from modules.trae_test.orchestrator.auditors.test_plan_auditor import TestPlanAuditor
from modules.trae_test.orchestrator.config import AuditType

VALID_PLAN = """# 需求测试计划

## 摘要
需求范围与风险。

## 需求与场景矩阵
| 场景 ID | 需求 ID | 证据 ID | 覆盖维度 | 优先级 | 账号/权限 | 页面入口 | 数据/状态 | 步骤（页面对象 + 动作 + 数据） | 可观察预期 | 测试方式 | 覆盖状态 | 依据状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | R1 | E1 | 正常场景 | 待确认 | 待确认 | 待确认 | 待确认 | 页面对象和动作 | 可观察结果 | 手工 | covered | 有依据 |

## 七维覆盖自查
| 基础维度 | 状态 | 关联场景或不适用理由 |
|---|---|---|
| 业务规则 | covered | S1 |
| 业务对象 | covered | S1 |
| 正常场景 | covered | S1 |
| 异常场景 | needs_confirmation | 待确认 |
| 边界场景 | needs_confirmation | 待确认 |
| 回滚场景 | not_applicable | 无状态回滚 |
| 排除项 | not_applicable | 暂无 |

## 覆盖自查
每项需求均映射或说明原因。

## 排除项和未决问题
暂无。

## 回归范围
根据影响域选择。
"""


def test_plan_auditor_accepts_markdown_plan_without_case_schema():
    result = TestPlanAuditor().audit(VALID_PLAN)

    assert result.passed
    assert result.audit_type == AuditType.TEST_PLAN
    assert any("不代表业务语义" in suggestion for suggestion in result.suggestions)


def test_plan_auditor_validates_workspace_path_and_plan_name(tmp_path: Path):
    plan_path = tmp_path / "workspace" / "20261118" / "需求R1销售筛选_测试计划.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(VALID_PLAN, encoding="utf-8")

    result = TestPlanAuditor().audit(plan_path, {"project_root": tmp_path})

    assert result.passed


def test_plan_auditor_rejects_missing_sections_and_coverage_dimensions():
    incomplete = """## 摘要
正文提到 ## 需求与场景矩阵、## 七维覆盖自查、## 覆盖自查、## 排除项和未决问题、## 回归范围。
场景 ID、需求 ID、证据 ID、覆盖维度、优先级、账号/权限、页面入口、数据/状态、页面对象、可观察预期、测试方式、覆盖状态、依据状态。
业务规则、业务对象、正常场景、异常场景、边界场景、回滚场景、排除项。
"""
    result = TestPlanAuditor().audit(incomplete)

    assert not result.passed
    assert any(issue.rule_id == "TEST_PLAN_SECTION_MISSING" for issue in result.issues)
    assert any(issue.rule_id == "TEST_PLAN_MATRIX_FIELD_MISSING" for issue in result.issues)
    assert any(issue.rule_id == "TEST_PLAN_COVERAGE_DIMENSION_MISSING" for issue in result.issues)


def test_plan_auditor_rejects_invalid_output_location_and_name(tmp_path: Path):
    invalid_path = tmp_path / "docs" / "plan.md"
    invalid_path.parent.mkdir()
    invalid_path.write_text(VALID_PLAN, encoding="utf-8")

    result = TestPlanAuditor().audit(invalid_path, {"project_root": tmp_path})

    assert not result.passed
    assert any(issue.rule_id == "TEST_PLAN_PATH_INVALID" for issue in result.issues)
    assert any(issue.rule_id == "TEST_PLAN_NAME_INVALID" for issue in result.issues)


def test_audit_engine_auto_selects_test_plan_type_for_plan_file(tmp_path: Path):
    plan_path = tmp_path / "workspace" / "20261118" / "需求R1销售筛选_测试计划.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(VALID_PLAN, encoding="utf-8")
    engine = AuditEngine()

    selected = engine._auto_select_audit_types(str(plan_path))
    result = engine.audit(str(plan_path), AuditType.ALL, {"project_root": tmp_path})

    assert selected == [AuditType.TEST_PLAN]
    assert result.passed


def test_audit_engine_uses_distinct_test_plan_audit_type():
    result = AuditEngine().audit(VALID_PLAN, AuditType.TEST_PLAN)

    assert isinstance(result, AuditResult)
    assert result.passed
    assert result.audit_type == AuditType.TEST_PLAN

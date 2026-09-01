"""测试审核引擎"""

from modules.trae_test.orchestrator.audit_engine import AuditEngine, AuditType
from modules.trae_test.orchestrator.audit_models import AuditResult
from modules.trae_test.utils.template_builder import ALL_FIELDS
from modules.trae_test.utils.excel_generator import ExcelGenerator
from openpyxl import Workbook


class TestAuditEngine:
    def test_auto_select_filter_all(self):
        """验证 _auto_select_audit_types 始终过滤 AuditType.ALL"""
        engine = AuditEngine()

        test_targets = ["test", {"key": "value"}, ["item"], 123, None]

        for target in test_targets:
            audit_types = engine._auto_select_audit_types(target)
            assert (
                AuditType.ALL not in audit_types
            ), f"_auto_select_audit_types({type(target).__name__}) 返回了 AuditType.ALL"

    def test_audit_all_no_recursion(self):
        """测试 _auto_select_audit_types 返回多种类型时不会递归"""
        engine = AuditEngine()

        # 直接测试 _auto_select_audit_types 方法的过滤逻辑
        audit_types = engine._auto_select_audit_types("test")
        assert AuditType.ALL not in audit_types, "过滤逻辑未生效"

        # 测试完整调用链路
        result = engine.audit("test", AuditType.ALL)
        assert result is not None

    def test_auto_select_returns_expected_types(self):
        """测试 _auto_select_audit_types 返回预期的审核类型"""
        engine = AuditEngine()

        # 字符串 target 应该触发某些审核类型
        types = engine._auto_select_audit_types("test string")
        assert isinstance(types, list)
        assert len(types) > 0

    def test_audit_file_path_accepts_date_directory(self, tmp_path):
        """Excel 文件应允许直接存放在 workspace/YYYYMMDD/ 下"""
        engine = AuditEngine()
        result = AuditResult()
        path = tmp_path / "workspace" / "20260727" / "需求demo.xlsx"

        engine._audit_file_path(str(path), result)

        assert not [issue for issue in result.issues if issue.rule_id == "FILE_PATH_INVALID"]

    def test_audit_file_path_rejects_legacy_formal_directory(self, tmp_path):
        """新规范不再允许 formal/draft 子目录作为 Excel 输出位置"""
        engine = AuditEngine()
        result = AuditResult()
        path = tmp_path / "workspace" / "20260727" / "formal" / "需求demo.xlsx"

        engine._audit_file_path(str(path), result)

        assert [issue for issue in result.issues if issue.rule_id == "FILE_PATH_INVALID"]

    def test_excel_all_audit_runs_business_auditor_after_structure_validation(self, tmp_path, monkeypatch):
        """Excel路径的ALL审核不能只校验表头，必须继续执行用例业务审核。"""
        path = tmp_path / "workspace" / "20260727" / "需求demo.xlsx"
        path.parent.mkdir(parents=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(ALL_FIELDS)
        sheet.append(
            [
                "产品 - 产品中心 - 库存SKU",
                "库存SKU用例",
                "100",
                "条件",
                "步骤",
                "结果",
                "功能",
                "正常",
                "中",
                "测试人",
                "P1",
                "是",
                "是",
                "库存知识",
                90,
            ]
        )
        workbook.save(path)
        monkeypatch.setattr(ExcelGenerator, "validate_excel", staticmethod(lambda _path: (True, "")))

        class FakeAuditor:
            def audit(self, *_args, **_kwargs):
                result = AuditResult()
                result.add_error("REQ_COVERAGE_INCOMPLETE", "覆盖矩阵缺失", "需求级覆盖")
                return result

        engine = AuditEngine()
        monkeypatch.setattr(engine, "_get_auditor", lambda auditor_type: FakeAuditor())
        result = engine.audit(str(path), AuditType.ALL)

        assert any(issue.rule_id == "REQ_COVERAGE_INCOMPLETE" for issue in result.issues)
        assert result.passed is False

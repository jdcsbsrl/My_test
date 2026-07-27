"""测试审核引擎"""

from modules.trae_test.orchestrator.audit_engine import AuditEngine, AuditType
from modules.trae_test.orchestrator.audit_models import AuditResult


class TestAuditEngine:
    def test_auto_select_filter_all(self):
        """验证 _auto_select_audit_types 始终过滤 AuditType.ALL"""
        engine = AuditEngine()
        
        test_targets = ["test", {"key": "value"}, ["item"], 123, None]
        
        for target in test_targets:
            audit_types = engine._auto_select_audit_types(target)
            assert AuditType.ALL not in audit_types, \
                f"_auto_select_audit_types({type(target).__name__}) 返回了 AuditType.ALL"

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

"""测试审核审批模块"""

from modules.trae_test.orchestrator.audit_approver import AuditApprover
from modules.trae_test.orchestrator.config import AuditConfig


class TestAuditApprover:
    def test_create_approver(self):
        config = AuditConfig()
        approver = AuditApprover(config)
        assert approver is not None

    def test_needs_approval_code_generation(self):
        config = AuditConfig(interactive_mode=False, auto_approve=False)
        approver = AuditApprover(config)
        context = {
            "action": "generate",
            "target": "test.py",
            "purpose": "生成代码",
        }
        # 操作类型为 CODE_GENERATION 始终需要审批
        needs = approver.needs_approval(context)
        assert needs is True

    def test_needs_approval_read_only(self):
        config = AuditConfig(interactive_mode=False, auto_approve=False)
        approver = AuditApprover(config)
        context = {
            "action": "read",
            "target": "test.py",
            "purpose": "读取文件",
        }
        needs = approver.needs_approval(context)
        assert needs is False

    def test_not_ci_non_interactive(self):
        import os

        original_ci = os.environ.get("CI")
        if "CI" in os.environ:
            del os.environ["CI"]
        try:
            config = AuditConfig(interactive_mode=False, auto_approve=False)
            approver = AuditApprover(config)
            assert approver._is_ci is False
        finally:
            if original_ci is not None:
                os.environ["CI"] = original_ci

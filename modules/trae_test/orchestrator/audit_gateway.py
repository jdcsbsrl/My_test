"""审核网关 - 所有审核请求的统一入口

职责：
- 整合 AuditEngine + AuditApprover + AuditLogger + RuleManager
- 提供 audit() 作为统一入口方法（兼容旧 API）
- 解决"局部强、全局散"问题：CLI、编排器、生成导出、知识库更新、自动化测试
  都通过此网关进入审核系统
- 支持可配置的阻断策略
"""

from datetime import datetime
from typing import Any

from .audit_models import AuditIssue, AuditResult
from .audit_engine import AuditEngine
from .audit_approver import AuditApprover
from .audit_logger import AuditLogger
from .audit_rules import RuleManager
from .config import AuditConfig, AuditType


class AuditGateway:
    """审核网关 - 统一入口

    所有审核请求都应通过此网关进入，确保：
    1. 操作前审批统一处理
    2. 审核结果统一持久化
    3. 阻断策略统一配置
    4. 审核规则统一管理

    使用方式：
        gateway = AuditGateway()
        result = gateway.audit(target, AuditType.TEST_CASE, context={...})

        # 或使用便捷方法
        gateway.audit_test_cases(cases)
    """

    def __init__(self, config: AuditConfig = None, notify_callback=None):
        self.config = config or AuditConfig()

        # 内部组件
        self.engine = AuditEngine(self.config)
        self.approver = AuditApprover(self.config, notify_callback)
        self.logger = AuditLogger()
        self.rule_manager = RuleManager()

        self.notify_callback = notify_callback or print

    def audit(self, target: Any, audit_type: AuditType = AuditType.ALL, context: dict = None) -> AuditResult:
        """统一审核入口

        Args:
            target: 审核目标
            audit_type: 审核类型
            context: 审核上下文（可包含 language, block_on_fail 等）

        Returns:
            AuditResult: 审核结果
        """
        start_time = datetime.now()
        context = context or {}

        # 1. 检查审核是否启用
        if not self.config.enabled:
            result = AuditResult(execution_time=0.0, audit_type=audit_type)
            result.passed = True
            return result

        # 2. 标准化审核类型
        audit_type_enum = self._normalize_audit_type(audit_type)

        # 3. 操作前审批（如果需要）
        if self.approver.needs_approval(context):
            approval_result = self.approver.request_approval(context)
            if not approval_result["approved"]:
                result = AuditResult(passed=False)
                result.issues.append(
                    AuditIssue(
                        severity="error",
                        rule_id="OPERATION_NOT_APPROVED",
                        category="approval",
                        message=f"操作未获得用户批准: {approval_result['reason']}",
                    )
                )
                result.execution_time = (datetime.now() - start_time).total_seconds()
                result.audit_type = audit_type_enum
                self.logger.log(result, context)
                return result

        # 4. 执行审核
        result = self.engine.audit(target, audit_type_enum, context)
        result.audit_type = audit_type_enum
        result.execution_time = (datetime.now() - start_time).total_seconds()

        # 5. 持久化日志
        self.logger.log(result, context)

        # 6. 检查阻断策略
        block_on_fail = context.get("block_on_fail", self.config.enforce_hard_block)
        if not result.passed and block_on_fail:
            from .audit_agent_enhanced import AuditFailedException

            error_report = self._generate_error_report(result, audit_type_enum)
            raise AuditFailedException(error_report)

        return result

    # --- 便捷方法 ---

    def audit_test_cases(self, test_cases: list[dict], context: dict | None = None) -> AuditResult:
        """审核测试用例"""
        return self.audit(test_cases, AuditType.TEST_CASE, context or {})

    def audit_code(self, code: Any, language: str = "python") -> AuditResult:
        """审核代码"""
        return self.audit(code, AuditType.CODE, {"language": language})

    def audit_security(self, target: Any) -> AuditResult:
        """安全审核"""
        return self.audit(target, AuditType.SECURITY)

    def audit_environment(self, env_config: Any) -> AuditResult:
        """环境审核"""
        return self.audit(env_config, AuditType.ENVIRONMENT)

    def audit_impact(self, changes: Any, context: dict) -> AuditResult:
        """影响分析"""
        return self.audit(changes, AuditType.IMPACT, context)

    # --- 内部方法 ---

    def _normalize_audit_type(self, audit_type: Any) -> AuditType:
        """标准化审核类型"""
        if isinstance(audit_type, AuditType):
            return audit_type
        if isinstance(audit_type, str):
            audit_type_lower = audit_type.lower()
            for member in AuditType:
                if member.value == audit_type_lower or member.name.lower() == audit_type_lower:
                    return member
        return AuditType.ALL

    def _generate_error_report(self, result: AuditResult, audit_type: AuditType) -> str:
        """生成错误报告"""
        audit_type_str = audit_type.value if hasattr(audit_type, "value") else str(audit_type)
        lines = [
            "=" * 80,
            f"审核失败报告 - {audit_type_str}",
            "=" * 80,
            f"时间: {result.timestamp}",
            f"执行时间: {result.execution_time:.2f}秒",
            "",
            f"错误数量: {len(result.errors)}",
            f"警告数量: {len(result.warnings)}",
            "",
            "-" * 80,
            "错误详情:",
            "-" * 80,
        ]

        for i, error in enumerate(result.errors, start=1):
            lines.append(f"{i}. [{error['code']}] {error['message']}")
            if error.get("location"):
                lines.append(f"   位置: {error['location']}")

        if result.warnings:
            lines.extend(["", "-" * 80, "警告详情:", "-" * 80])
            for i, warning in enumerate(result.warnings, start=1):
                lines.append(f"{i}. [{warning['code']}] {warning['message']}")
                if warning.get("location"):
                    lines.append(f"   位置: {warning['location']}")

        if result.suggestions:
            lines.extend(["", "-" * 80, "修正建议:", "-" * 80])
            for i, suggestion in enumerate(result.suggestions, start=1):
                lines.append(f"{i}. {suggestion}")

        lines.extend(["", "=" * 80])
        return "\n".join(lines)

    def get_summary(self) -> dict:
        """获取审核摘要统计"""
        return self.logger.get_summary()

    def query_logs(self, **kwargs) -> list[dict]:
        """查询审核历史"""
        return self.logger.query(**kwargs)

"""增强的审核Agent - 全能实时审核系统

审核Agent作为全能的质量监督者，覆盖：
1. 测试用例审核：格式、字段、命名、路径
2. 代码规范审核：编码规范、代码风格，最佳实践
3. 环境审核：依赖配置、环境变量、权限设置
4. 影响分析：代码变更影响范围、兼容性测试
5. 安全审核：敏感信息、数据保护、合规性
6. 操作前审核：代码生成、文件夹创建、文件写入等操作前的审批

特性：
- 实时审核（不是事后审核）
- 硬阻断机制（审核失败立即停止）
- 审核类型自动识别
- 审核结果回调
- 审核日志详细记录
- 操作前审批机制：需要用户明确允许才能执行敏感操作

架构：
- 本文件作为门面层（Facade），对外 API 保持不变
- 内部委托给 AuditEngine + AuditApprover + AuditLogger + RuleManager
"""

import os
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from .audit_models import AuditResult
from .audit_approver import AuditApprover
from .audit_engine import AuditEngine
from .audit_rules import RuleManager
from .config import AuditConfig, AuditType

# AuditResult 定义已迁移至 audit_models.py
# 保留此处的导入以保持向后兼容。
# 新代码应直接从 .audit_models import AuditResult, AuditIssue


class OperationType(Enum):
    """操作类型枚举"""

    CODE_GENERATION = "code_generation"  # 代码生成
    FOLDER_CREATION = "folder_creation"  # 文件夹创建
    FILE_WRITE = "file_write"  # 文件写入
    FILE_DELETE = "file_delete"  # 文件删除
    FILE_MODIFY = "file_modify"  # 文件修改
    WORKFLOW_EXECUTION = "workflow_execution"  # 工作流执行
    DATA_EXPORT = "data_export"  # 数据导出
    CONFIG_CHANGE = "config_change"  # 配置变更
    UNKNOWN = "unknown"

    @classmethod
    def from_context(cls, context: dict) -> "OperationType":
        """从上下文推断操作类型"""
        action = context.get("action", "").lower()
        target = context.get("target", "").lower()

        if "generate" in action or "create_code" in action:
            return cls.CODE_GENERATION
        elif "create" in action and ("folder" in target or "directory" in target):
            return cls.FOLDER_CREATION
        elif "write" in action or "save" in action:
            return cls.FILE_WRITE
        elif "delete" in action:
            return cls.FILE_DELETE
        elif "modify" in action or "update" in action:
            return cls.FILE_MODIFY
        elif "execute" in action and "workflow" in target:
            return cls.WORKFLOW_EXECUTION
        elif "export" in action:
            return cls.DATA_EXPORT
        elif "config" in target or "setting" in target:
            return cls.CONFIG_CHANGE

        return cls.UNKNOWN


class AuditAgent:
    """审核Agent - 全能实时审核系统（门面类）

    保持对外 API 不变（audit(), audit_test_cases(), audit_code(), 等），
    内部委托给 AuditEngine + AuditApprover + AuditLogger + RuleManager。
    """

    def __init__(self, config: AuditConfig = None, notify_callback: Callable | None = None):
        """初始化增强审核Agent

        Args:
            config: 审核配置
            notify_callback: 通知回调函数
        """
        self.config = config or AuditConfig()
        self.notify_callback = notify_callback or print
        self.audit_logs: list[dict[str, Any]] = []
        self.user_approved = False  # 用户是否已批准当前操作

        # 内部组件
        self._engine = AuditEngine(self.config)
        self._approver = AuditApprover(self.config, self.notify_callback)
        self._rule_manager = RuleManager()

        # 自动检测是否为 CI 环境
        self._is_ci = os.getenv("CI", "").lower() in ("true", "1", "yes")

        # 延迟初始化的审计日志持久化实例
        self._audit_logger_instance = None

    @property
    def _audit_logger(self):
        """延迟加载 AuditLogger 实例（避免导入时依赖）"""
        if self._audit_logger_instance is None:
            from .audit_logger import AuditLogger

            self._audit_logger_instance = AuditLogger()
        return self._audit_logger_instance

    # ============================================================
    # 核心审核入口
    # ============================================================

    def audit(self, target: Any, audit_type: AuditType = AuditType.ALL, context: dict = None) -> AuditResult:
        """全能审核入口

        Args:
            target: 审核目标（可以是测试用例、代码、配置等）
            audit_type: 审核类型（支持AuditType枚举或字符串）
            context: 审核上下文

        Returns:
            AuditResult: 审核结果
        """
        start_time = datetime.now()
        context = context or {}

        # 如果审核被禁用，直接返回通过
        if not self.config.enabled:
            result = AuditResult()
            result.passed = True
            result.execution_time = 0.0
            result.audit_type = audit_type
            return result

        # 统一转换audit_type为AuditType枚举
        audit_type_enum = self._normalize_audit_type(audit_type)

        # 操作前审批：如果是需要审批的操作，先询问用户
        if self._needs_approval(context):
            approval_result = self._approver.request_approval(context)
            self.user_approved = approval_result["approved"]
            if not approval_result["approved"]:
                result = AuditResult()
                result.passed = False
                result.add_error(
                    "OPERATION_NOT_APPROVED", f"操作未获得用户批准: {approval_result['reason']}", severity="error"
                )
                result.execution_time = (datetime.now() - start_time).total_seconds()
                result.audit_type = audit_type_enum
                self._log_audit(audit_type_enum, result, context)
                return result

        # 委托给引擎审核
        result = self._engine.audit(target, audit_type_enum, context)

        # 计算执行时间（如果引擎未设置）
        if result.execution_time == 0.0:
            result.execution_time = (datetime.now() - start_time).total_seconds()
        result.audit_type = audit_type_enum

        # 记录审核日志
        self._log_audit(audit_type_enum, result, context)

        # 如果启用硬阻断且审核失败，抛出异常
        if not result.passed and self.config.enforce_hard_block:
            self._handle_audit_failure(result, audit_type_enum)

        return result

    def _normalize_audit_type(self, audit_type: Any) -> AuditType:
        """将审核类型统一转换为AuditType枚举

        Args:
            audit_type: 审核类型（AuditType枚举或字符串）

        Returns:
            AuditType: 标准化后的审核类型枚举
        """
        if isinstance(audit_type, AuditType):
            return audit_type

        if isinstance(audit_type, str):
            audit_type_lower = audit_type.lower()
            for enum_member in AuditType:
                if enum_member.value == audit_type_lower or enum_member.name.lower() == audit_type_lower:
                    return enum_member

        return AuditType.ALL

    # ============================================================
    # 审批逻辑（委托给 AuditApprover）
    # ============================================================

    def _needs_approval(self, context: dict) -> bool:
        """判断操作是否需要用户审批

        Args:
            context: 操作上下文

        Returns:
            bool: 是否需要审批
        """
        return self._approver.needs_approval(context)

    def _prompt_user_approval(self) -> bool:
        """统一的用户审批交互逻辑

        Returns:
            bool: 用户是否批准
        """
        return self._approver._prompt_user_approval()

    def _request_user_approval(self, context: dict) -> dict[str, Any]:
        """请求用户审批操作

        Args:
            context: 操作上下文

        Returns:
            Dict: 审批结果
        """
        return self._approver.request_approval(context)

    def _build_approval_message(self, operation_type: OperationType, action: str, target: str, purpose: str) -> str:
        """构建审批请求消息

        Args:
            operation_type: 操作类型
            action: 操作动作
            target: 操作目标
            purpose: 操作目的

        Returns:
            str: 审批消息
        """
        return self._approver._build_approval_message(operation_type, action, target, purpose)

    def _log_operation_request(self, operation_type: OperationType, action: str, target: str, purpose: str):
        """记录操作请求日志

        Args:
            operation_type: 操作类型
            action: 操作动作
            target: 操作目标
            purpose: 操作目的
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation_type": operation_type.value,
            "action": action,
            "target": target,
            "purpose": purpose,
            "status": "pending_approval",
            "approved": self.user_approved,
        }

        print(f"\n 记录操作请求: {operation_type.value} -> {target}")
        self.audit_logs.append(log_entry)

    def audit_before_operation(self, action: str, target: str, purpose: str = "") -> bool:
        """操作前审核 - 明确告知用户操作目的并请求批准

        Args:
            action: 操作动作（如：generate, create, delete, modify）
            target: 操作目标（如：文件路径、目录名称、配置项）
            purpose: 操作目的（为什么要执行此操作）

        Returns:
            bool: 是否获得批准
        """
        result = self._approver.prompt_before_operation(action, target, purpose)
        self.user_approved = result
        return result

    # ============================================================
    # 具体审核方法（委托给 AuditEngine）
    # ============================================================

    def audit_test_cases(self, test_cases: Any, context: dict | None = None) -> AuditResult:
        """审核测试用例

        Args:
            test_cases: 测试用例列表或其他对象

        Returns:
            AuditResult: 审核结果
        """
        context = {"strict_level": self.config.strict_level, **(context or {})}
        result = self._engine.audit(test_cases, AuditType.TEST_CASE, context)
        # 记录日志（兼容旧代码）
        if result.execution_time > 0:
            self._log_audit(AuditType.TEST_CASE, result, context)
        return result

    def audit_code(self, code: Any, language: str = "python") -> AuditResult:
        """审核代码规范

        Args:
            code: 代码内容（字符串或文件路径）
            language: 编程语言

        Returns:
            AuditResult: 审核结果
        """
        context = {"language": language}
        result = self._engine.audit(code, AuditType.CODE, context)
        if result.execution_time > 0:
            self._log_audit(AuditType.CODE, result, context)
        return result

    def audit_environment(self, env_config: dict) -> AuditResult:
        """审核环境配置

        Args:
            env_config: 环境配置字典

        Returns:
            AuditResult: 审核结果
        """
        result = self._engine.audit(env_config, AuditType.ENVIRONMENT, {})
        if result.execution_time > 0:
            self._log_audit(AuditType.ENVIRONMENT, result, {})
        return result

    def audit_impact(self, changes: Any, context: dict) -> AuditResult:
        """审核代码变更影响

        Args:
            changes: 代码变更内容
            context: 变更上下文

        Returns:
            AuditResult: 审核结果
        """
        result = self._engine.audit(changes, AuditType.IMPACT, context)
        if result.execution_time > 0:
            self._log_audit(AuditType.IMPACT, result, context)
        return result

    def audit_security(self, target: Any) -> AuditResult:
        """安全审核

        Args:
            target: 审核目标（代码或配置）

        Returns:
            AuditResult: 审核结果
        """
        result = self._engine.audit(target, AuditType.SECURITY, {})
        if result.execution_time > 0:
            self._log_audit(AuditType.SECURITY, result, {})
        return result

    # ============================================================
    # 日志管理
    # ============================================================

    def _log_audit(self, audit_type: AuditType, result: AuditResult, context: dict = None):
        """记录审核日志

        Args:
            audit_type: 审核类型
            result: 审核结果
            context: 审核上下文
        """
        log_entry = {
            "timestamp": result.timestamp,
            "audit_type": audit_type.value if isinstance(audit_type, AuditType) else audit_type,
            "result": result.to_dict(),
            "context": context or {},
        }

        # detailed_logging 控制日志详细程度
        if self.config.detailed_logging:
            log_entry["detailed"] = True
        else:
            log_entry["detailed"] = False
            log_entry.pop("result", None)

        self.audit_logs.append(log_entry)

        # 持久化到 SQLite（无论日志详细程度，完整结果始终写入数据库）
        try:
            self._audit_logger.log(result, context)
        except Exception as e:
            # 日志持久化失败不应影响审核主流程
            print(f"[AuditAgent] 日志持久化失败: {e}")

        # 调用通知回调
        if not result.passed and self.notify_callback:
            audit_type_str = audit_type.value if isinstance(audit_type, AuditType) else audit_type
            self.notify_callback(f"审核失败 [{audit_type_str}]: {len(result.errors)}个错误")

    # ============================================================
    # 硬阻断机制
    # ============================================================

    def _handle_audit_failure(self, result: AuditResult, audit_type: AuditType):
        """处理审核失败

        Args:
            result: 审核结果
            audit_type: 审核类型

        Raises:
            AuditFailedException: 审核失败异常
        """
        error_types = {
            AuditType.TEST_CASE: "TestCaseAuditException",
            AuditType.CODE: "CodeAuditException",
            AuditType.ENVIRONMENT: "EnvironmentAuditException",
            AuditType.SECURITY: "SecurityAuditException",
        }

        exception_type = error_types.get(audit_type, "AuditFailedException")

        # 生成详细的错误报告
        error_report = self.generate_error_report(result, audit_type)

        # 调用通知回调
        if self.notify_callback:
            self.notify_callback(error_report)

        # 抛出异常
        raise AuditFailedException(error_report)

    # ============================================================
    # 报告生成
    # ============================================================

    def generate_error_report(self, result: AuditResult, audit_type: AuditType) -> str:
        """生成错误报告

        Args:
            result: 审核结果
            audit_type: 审核类型

        Returns:
            str: 错误报告文本
        """
        audit_type_str = audit_type.value if isinstance(audit_type, AuditType) else audit_type
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
            lines.extend(
                [
                    "",
                    "-" * 80,
                    "警告详情:",
                    "-" * 80,
                ]
            )

            for i, warning in enumerate(result.warnings, start=1):
                lines.append(f"{i}. [{warning['code']}] {warning['message']}")
                if warning["location"]:
                    lines.append(f"   位置: {warning['location']}")

        if result.suggestions:
            lines.extend(
                [
                    "",
                    "-" * 80,
                    "修正建议:",
                    "-" * 80,
                ]
            )

            for i, suggestion in enumerate(result.suggestions, start=1):
                lines.append(f"{i}. {suggestion}")

        lines.extend(
            [
                "",
                "=" * 80,
            ]
        )

        return "\n".join(lines)

    def generate_report(self, output_path: str | None = None) -> str:
        """生成审核报告

        Args:
            output_path: 输出文件路径

        Returns:
            str: 报告文本
        """
        lines = [
            "=" * 80,
            "审核报告",
            "=" * 80,
            f"审核时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"审核次数: {len(self.audit_logs)}",
            "",
        ]

        for i, log in enumerate(self.audit_logs, start=1):
            result = log["result"]
            status = "[通过]" if result["passed"] else "[未通过]"
            lines.append(f"{i}. [{log['audit_type']}] {status}")
            lines.append(f"   时间: {log['timestamp']}")
            lines.append(f"   错误: {result['error_count']}, 警告: {result['warning_count']}")

        lines.extend(
            [
                "",
                "=" * 80,
            ]
        )

        report_text = "\n".join(lines)

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_text)

        return report_text

    def get_audit_summary(self) -> dict[str, Any]:
        """获取审核摘要

        Returns:
            Dict: 审核摘要
        """
        total = len(self.audit_logs)
        passed = sum(1 for log in self.audit_logs if log["result"]["passed"])
        failed = total - passed

        return {
            "total_audits": total,
            "passed_audits": passed,
            "failed_audits": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
        }


class AuditFailedException(Exception):
    """审核失败异常"""

    def __init__(self, message: str, audit_result: AuditResult = None):
        super().__init__(message)
        self.audit_result = audit_result


# 全局实例
audit_agent = AuditAgent()

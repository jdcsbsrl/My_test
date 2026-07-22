"""异常处理系统 - 多Agent协同工作系统

提供：
- 异常类定义
- 异常处理器
- 用户通知机制
"""

from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any


class ExceptionSeverity(Enum):
    """异常严重程度"""

    LOW = "low"  # 低：不影响执行
    MEDIUM = "medium"  # 中：部分功能受影响
    HIGH = "high"  # 高：主要功能受影响
    CRITICAL = "critical"  # 严重：系统不可用


class AgentException(Exception):
    """Agent基础异常"""

    def __init__(
        self, message: str, severity: ExceptionSeverity = ExceptionSeverity.MEDIUM, details: dict[str, Any] = None
    ):
        super().__init__(message)
        self.severity = severity
        self.details = details or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.__class__.__name__,
            "message": str(self),
            "severity": self.severity.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class TestCaseAuditException(AgentException):
    """测试用例审核异常"""

    def __init__(self, message: str, details: dict[str, Any] = None):
        super().__init__(message, severity=ExceptionSeverity.HIGH, details=details)


class CodeAuditException(AgentException):
    """代码规范审核异常"""

    def __init__(self, message: str, details: dict[str, Any] = None):
        super().__init__(message, severity=ExceptionSeverity.HIGH, details=details)


class EnvironmentAuditException(AgentException):
    """环境审核异常"""

    def __init__(self, message: str, details: dict[str, Any] = None):
        super().__init__(message, severity=ExceptionSeverity.HIGH, details=details)


class SecurityAuditException(AgentException):
    """安全审核异常"""

    def __init__(self, message: str, details: dict[str, Any] = None):
        super().__init__(message, severity=ExceptionSeverity.CRITICAL, details=details)


class AuditFailedException(AgentException):
    """审核失败异常"""

    def __init__(self, message: str, audit_result: Any = None, details: dict[str, Any] = None):
        details = details or {}
        if audit_result:
            details["audit_result"] = audit_result.to_dict() if hasattr(audit_result, "to_dict") else audit_result

        super().__init__(message, severity=ExceptionSeverity.HIGH, details=details)
        self.audit_result = audit_result


class MaxRetriesExceededException(AgentException):
    """超过最大重试次数异常"""

    def __init__(
        self,
        message: str,
        max_retries: int = 0,
        total_attempts: int = 0,
        last_exception: Exception = None,
        details: dict[str, Any] = None,
    ):
        details = details or {}
        details.update(
            {
                "max_retries": max_retries,
                "total_attempts": total_attempts,
                "last_exception": str(last_exception) if last_exception else None,
            }
        )

        super().__init__(message, severity=ExceptionSeverity.HIGH, details=details)
        self.max_retries = max_retries
        self.total_attempts = total_attempts
        self.last_exception = last_exception


class WorkflowExecutionException(AgentException):
    """工作流执行异常"""

    def __init__(self, message: str, workflow_id: str = "", details: dict[str, Any] = None):
        details = details or {}
        details["workflow_id"] = workflow_id

        super().__init__(message, severity=ExceptionSeverity.CRITICAL, details=details)
        self.workflow_id = workflow_id


class AgentNotFoundException(AgentException):
    """Agent未找到异常"""

    def __init__(self, agent_type: str, details: dict[str, Any] = None):
        message = f"未找到Agent: {agent_type}"
        details = details or {}
        details["agent_type"] = agent_type

        super().__init__(message, severity=ExceptionSeverity.HIGH, details=details)
        self.agent_type = agent_type


class ValidationException(AgentException):
    """验证异常"""

    def __init__(self, message: str, field: str = "", details: dict[str, Any] = None):
        details = details or {}
        details["field"] = field

        super().__init__(message, severity=ExceptionSeverity.MEDIUM, details=details)
        self.field = field


class NotificationException(AgentException):
    """通知异常"""

    def __init__(self, message: str, notification_type: str = "", details: dict[str, Any] = None):
        details = details or {}
        details["notification_type"] = notification_type

        super().__init__(message, severity=ExceptionSeverity.LOW, details=details)


class ExceptionHandler:
    """异常处理器

    处理异常、记录日志、通知用户。
    """

    def __init__(self, notify_callback: Callable | None = None):
        """初始化异常处理器

        Args:
            notify_callback: 通知回调函数
        """
        self.notify_callback = notify_callback
        self.exception_history: list[dict[str, Any]] = []

    def handle_exception(self, exception: Exception, context: dict[str, Any] = None) -> dict[str, Any]:
        """处理异常

        Args:
            exception: 异常
            context: 上下文信息

        Returns:
            Dict: 处理结果
        """
        context = context or {}

        # 构建异常信息
        exception_info = {
            "timestamp": datetime.now().isoformat(),
            "type": type(exception).__name__,
            "message": str(exception),
            "context": context,
        }

        # 如果是AgentException，添加详细信息
        if isinstance(exception, AgentException):
            exception_info.update(
                {
                    "severity": exception.severity.value,
                    "details": exception.details,
                    "should_notify": self.should_notify_user(exception),
                }
            )

        # 记录到历史
        self.exception_history.append(exception_info)

        # 处理异常
        if isinstance(exception, AgentException):
            return self._handle_agent_exception(exception, context)
        else:
            return self._handle_generic_exception(exception, context)

    def _handle_agent_exception(self, exception: AgentException, context: dict[str, Any]) -> dict[str, Any]:
        """处理Agent异常

        Args:
            exception: Agent异常
            context: 上下文

        Returns:
            Dict: 处理结果
        """
        result = {
            "handled": True,
            "severity": exception.severity.value,
            "should_notify": self.should_notify_user(exception),
            "should_retry": self.should_retry(exception),
            "recovery_suggestions": self.generate_recovery_suggestions(exception),
        }

        # 根据严重程度决定是否通知
        if result["should_notify"] and self.notify_callback:
            self._notify_user(exception)

        return result

    def _handle_generic_exception(self, exception: Exception, context: dict[str, Any]) -> dict[str, Any]:
        """处理通用异常

        Args:
            exception: 异常
            context: 上下文

        Returns:
            Dict: 处理结果
        """
        result = {
            "handled": True,
            "severity": ExceptionSeverity.MEDIUM.value,
            "should_notify": True,
            "should_retry": False,
            "recovery_suggestions": ["请检查错误信息并重试"],
        }

        if self.notify_callback:
            self._notify_user(exception)

        return result

    def should_notify_user(self, exception: Exception) -> bool:
        """判断是否应该通知用户

        Args:
            exception: 异常

        Returns:
            bool: 是否通知
        """
        # 严重异常必须通知
        if isinstance(exception, SecurityAuditException):
            return True

        if isinstance(exception, WorkflowExecutionException):
            return True

        if isinstance(exception, MaxRetriesExceededException):
            return True

        if isinstance(exception, AuditFailedException):
            # 多次审核失败才通知
            audit_result = getattr(exception, "audit_result", None)
            if audit_result and hasattr(audit_result, "errors"):
                # 如果错误数量超过3个，通知用户
                if len(audit_result.errors) > 3:
                    return True

        # 中等及以上严重程度通知
        if isinstance(exception, AgentException):
            if exception.severity in [ExceptionSeverity.HIGH, ExceptionSeverity.CRITICAL]:
                return True

        return False

    def should_retry(self, exception: Exception) -> bool:
        """判断是否应该重试

        Args:
            exception: 异常

        Returns:
            bool: 是否重试
        """
        # 审核异常可以重试
        if isinstance(exception, AuditFailedException):
            return True

        # 环境异常可以重试
        if isinstance(exception, EnvironmentAuditException):
            return True

        # 验证异常不需要重试
        if isinstance(exception, ValidationException):
            return False

        # 安全异常不需要重试
        if isinstance(exception, SecurityAuditException):
            return False

        return True

    def generate_recovery_suggestions(self, exception: Exception) -> list[str]:
        """生成恢复建议

        Args:
            exception: 异常

        Returns:
            list[str]: 建议列表
        """
        suggestions = []

        if isinstance(exception, TestCaseAuditException):
            suggestions.extend(
                ["请检查测试用例格式是否符合规范", "确保所有必需字段都已填写", "检查用例名称是否为空或重复"]
            )

        elif isinstance(exception, CodeAuditException):
            suggestions.extend(["请检查代码是否符合编码规范", "确保代码没有语法错误", "检查导入语句是否正确"])

        elif isinstance(exception, EnvironmentAuditException):
            suggestions.extend(["请检查环境配置是否正确", "确保所有依赖已安装", "检查环境变量是否设置正确"])

        elif isinstance(exception, SecurityAuditException):
            suggestions.extend(["请检查是否存在敏感信息泄露", "确保所有密码和密钥已加密", "检查SQL注入和命令注入风险"])

        elif isinstance(exception, AuditFailedException):
            suggestions.extend(["请查看详细的审核报告", "根据错误提示修正问题", "修正后重新提交审核"])

        elif isinstance(exception, MaxRetriesExceededException):
            suggestions.extend(["已达到最大重试次数", "请检查问题原因", "可能需要人工介入"])

        elif isinstance(exception, WorkflowExecutionException):
            suggestions.extend(["请检查工作流配置", "确保所有必需的Agent已注册", "检查工作流步骤定义是否正确"])

        else:
            suggestions.append("请查看错误信息并重试")

        return suggestions

    def _notify_user(self, exception: Exception):
        """通知用户

        Args:
            exception: 异常
        """
        if not self.notify_callback:
            return

        try:
            # 构建通知消息
            message = self._format_notification_message(exception)

            # 调用回调
            self.notify_callback(message)

        except Exception as e:
            # 通知失败不影响主流程
            print(f"通知用户失败: {str(e)}")

    def _format_notification_message(self, exception: Exception) -> str:
        """格式化通知消息

        Args:
            exception: 异常

        Returns:
            str: 通知消息
        """
        lines = [
            f"⚠️ 异常通知 - {type(exception).__name__}",
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"消息: {str(exception)}",
        ]

        # 添加恢复建议
        suggestions = self.generate_recovery_suggestions(exception)
        if suggestions:
            lines.append("")
            lines.append("建议:")
            for suggestion in suggestions:
                lines.append(f"  - {suggestion}")

        return "\n".join(lines)

    def notify_user(self, title: str, data: Any = None):
        """主动通知用户

        Args:
            title: 标题
            data: 数据
        """
        if not self.notify_callback:
            return

        message = f"📢 {title}"
        if data:
            if isinstance(data, dict):
                message += "\n"
                for key, value in data.items():
                    message += f"\n  {key}: {value}"
            else:
                message += f"\n{data}"

        self.notify_callback(message)

    def get_exception_history(self, limit: int = 10, severity: ExceptionSeverity = None) -> list[dict[str, Any]]:
        """获取异常历史

        Args:
            limit: 返回数量限制
            severity: 过滤严重程度

        Returns:
            list[dict]: 异常历史
        """
        history = self.exception_history

        # 按严重程度过滤
        if severity:
            history = [e for e in history if e.get("severity") == severity.value]

        # 限制数量
        return history[-limit:]

    def get_statistics(self) -> dict[str, Any]:
        """获取异常统计

        Returns:
            Dict: 统计信息
        """
        total = len(self.exception_history)

        # 按类型统计
        by_type = {}
        for e in self.exception_history:
            type_name = e.get("type", "Unknown")
            by_type[type_name] = by_type.get(type_name, 0) + 1

        # 按严重程度统计
        by_severity = {}
        for e in self.exception_history:
            severity = e.get("severity", "unknown")
            by_severity[severity] = by_severity.get(severity, 0) + 1

        return {"total_exceptions": total, "by_type": by_type, "by_severity": by_severity}

    def clear_history(self):
        """清除历史记录"""
        self.exception_history.clear()

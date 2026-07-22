import os
from dataclasses import dataclass, field
from typing import Any

AUTHORIZATION_ENV_VAR = "AUTO_TEST_AUTHORIZED"
AUTHORIZATION_TOKEN = "AUTHORIZED"


@dataclass
class ExecutionAuthorization:
    authorized: bool = False
    authorized_by: str | None = None
    authorized_at: str | None = None

    def require_authorization(self) -> None:
        if not self.authorized:
            raise ExecutionAuthorizationError(
                f"执行授权异常: 当前测试执行未经授权。\n"
                f"根据项目规范，任何自动化测试的执行必须获得项目负责人的明确许可。\n"
                f"如需执行测试，请联系项目负责人获取授权。\n"
                f"设置环境变量 {AUTHORIZATION_ENV_VAR}={AUTHORIZATION_TOKEN} 以授权执行。"
            )


@dataclass
class SensitiveOperationReport:
    test_name: str
    operation_type: str
    target_entities: list[str] = field(default_factory=list)
    estimated_impact: str = "未知"
    execution_plan: str = "待确定"

    def generate_report(self) -> str:
        return (
            f"\n{'='*60}\n"
            f"敏感操作执行汇报\n"
            f"{'='*60}\n"
            f"测试用例: {self.test_name}\n"
            f"操作类型: {self.operation_type}\n"
            f"涉及实体: {', '.join(self.target_entities) if self.target_entities else '未指定'}\n"
            f"预计影响: {self.estimated_impact}\n"
            f"执行计划: {self.execution_plan}\n"
            f"{'='*60}\n"
            f"请确认是否继续执行该敏感操作。\n"
        )


class ExecutionAuthorizationError(Exception):
    pass


class SensitiveOperationError(Exception):
    pass


class ExecutionAuthManager:
    _instance: "ExecutionAuthManager | None" = None

    def __new__(cls) -> "ExecutionAuthManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._authorization = ExecutionAuthorization()
            cls._instance._check_env_authorization()
        return cls._instance

    def _check_env_authorization(self) -> None:
        auth_env = os.getenv(AUTHORIZATION_ENV_VAR, "")
        if auth_env == AUTHORIZATION_TOKEN:
            self._authorization.authorized = True
            self._authorization.authorized_by = os.getenv("AUTHORIZED_BY", "环境变量授权")
            self._authorization.authorized_at = os.getenv("AUTHORIZED_AT", "未知时间")

    @property
    def authorization(self) -> ExecutionAuthorization:
        return self._authorization

    def is_authorized(self) -> bool:
        return self._authorization.authorized

    def get_authorization_status(self) -> dict[str, Any]:
        return {
            "authorized": self._authorization.authorized,
            "authorized_by": self._authorization.authorized_by,
            "authorized_at": self._authorization.authorized_at,
        }

    def report_sensitive_operation(
        self,
        test_name: str,
        operation_type: str,
        target_entities: list[str] | None = None,
        estimated_impact: str | None = None,
    ) -> SensitiveOperationReport:
        report = SensitiveOperationReport(
            test_name=test_name,
            operation_type=operation_type,
            target_entities=target_entities or [],
            estimated_impact=estimated_impact or "未知",
        )
        raise SensitiveOperationError(report.generate_report())


def get_auth_manager() -> ExecutionAuthManager:
    return ExecutionAuthManager()


def check_authorization() -> None:
    manager = get_auth_manager()
    manager.authorization.require_authorization()


def report_sensitive_operation(
    test_name: str,
    operation_type: str,
    target_entities: list[str] | None = None,
    estimated_impact: str | None = None,
) -> None:
    manager = get_auth_manager()
    manager.report_sensitive_operation(
        test_name=test_name,
        operation_type=operation_type,
        target_entities=target_entities,
        estimated_impact=estimated_impact,
    )

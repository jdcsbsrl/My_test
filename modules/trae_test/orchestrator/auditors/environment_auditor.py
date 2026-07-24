"""环境配置审核器"""

import re
from typing import Any

from ..audit_models import AuditResult
from ..config import AuditType
from ..audit_rules import RuleManager


class EnvironmentAuditor:
    """环境配置审核器"""

    def __init__(self, rule_manager: RuleManager | None = None):
        """初始化环境配置审核器

        Args:
            rule_manager: 可选的 RuleManager 实例
        """
        self.rule_manager = rule_manager or RuleManager()

    def audit(self, env_config: dict) -> AuditResult:
        """审核环境配置

        Args:
            env_config: 环境配置字典

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.ENVIRONMENT

        if not env_config:
            result.add_warning("ENV_CONFIG_EMPTY", "环境配置为空")
            return result

        # 检查必需的配置项
        required_keys = ["python_version", "dependencies"]

        for key in required_keys:
            if key not in env_config:
                result.add_warning("ENV_MISSING_KEY", f"缺少必需的配置项: {key}")

        # 检查Python版本
        python_version = env_config.get("python_version", "")
        if python_version:
            if not re.match(r"^\d+\.\d+(\.\d+)?$", python_version):
                result.add_warning(
                    "ENV_INVALID_PYTHON_VERSION",
                    f"Python版本格式不正确: {python_version}",
                )

        # 检查依赖列表
        dependencies = env_config.get("dependencies", [])
        if not isinstance(dependencies, list):
            result.add_error("ENV_DEPENDENCIES_NOT_LIST", "dependencies必须是列表格式")
        elif len(dependencies) == 0:
            result.add_warning("ENV_NO_DEPENDENCIES", "没有定义任何依赖")

        # 检查环境变量
        env_vars = env_config.get("env_vars", {})
        if env_vars:
            for key, value in env_vars.items():
                if not key.isupper():
                    result.add_warning(
                        "ENV_VAR_LOWERCASE",
                        f"环境变量名应使用大写: {key}",
                    )

        # 检查知识库验证结果（兼容 kb_manager 的 audit_target 格式）
        if "verification_type" in env_config:
            failed_files = env_config.get("failed_files", 0)
            errors = env_config.get("errors", [])

            if failed_files > 0:
                result.add_error(
                    "KB_VERIFICATION_FAILED",
                    f"知识库验证失败，{failed_files}个文件验证未通过",
                    severity="error",
                )

            if errors:
                for error in errors[:5]:
                    result.add_error("KB_VERIFICATION_ERROR", error, severity="error")

        return result

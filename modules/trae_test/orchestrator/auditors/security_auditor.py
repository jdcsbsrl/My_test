"""安全审核器"""

import os
import re
from pathlib import Path
from typing import Any

from ..audit_models import AuditResult
from ..config import AuditType
from ..audit_rules import RuleManager


class SecurityAuditor:
    """安全审核器"""

    def __init__(self, rule_manager: RuleManager | None = None):
        """初始化安全审核器

        Args:
            rule_manager: 可选的 RuleManager 实例
        """
        self.rule_manager = rule_manager or RuleManager()

    def audit(self, target: Any) -> AuditResult:
        """安全审核

        增强：增加上下文判断能力，减少误报

        Args:
            target: 审核目标（代码或配置）

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.SECURITY

        # 获取代码内容
        code = ""
        if isinstance(target, (str, Path)) and os.path.isfile(str(target)):
            try:
                with open(target, encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                result.add_error("SECURITY_READ_ERROR", f"无法读取文件: {str(e)}")
                return result
        elif isinstance(target, str):
            code = target

        if not code:
            result.add_warning("SECURITY_EMPTY", "审核内容为空")
            return result

        # 检查敏感信息（使用 RuleManager 的敏感信息规则）
        self._check_sensitive_patterns(code, result)

        # 检查硬编码密码
        self._check_hardcoded_passwords(code, result)

        # 检查SQL注入风险
        self._check_sql_injection(code, result)

        # 检查命令注入风险
        self._check_command_injection(code, result)

        return result

    def _check_sensitive_patterns(self, code: str, result: AuditResult):
        """使用 RuleManager 的敏感信息规则检查

        Args:
            code: 代码内容
            result: 审核结果
        """
        try:
            patterns = self.rule_manager.get_sensitive_patterns()
        except Exception:
            patterns = self._default_sensitive_patterns()

        for pattern, info_type in patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                result.add_error(
                    "SECURITY_SENSITIVE_INFO",
                    f"检测到敏感信息: {info_type}",
                    f"位置: {match.group()[:50]}...",
                )

    def _check_hardcoded_passwords(self, code: str, result: AuditResult):
        """检查硬编码密码

        Args:
            code: 代码内容
            result: 审核结果
        """
        # 排除 xxx/***/null 等占位符值（与 _check_sensitive_patterns 保持一致）
        if re.search(r'password\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', code, re.IGNORECASE):
            result.add_error("SECURITY_HARDCODED_PASSWORD", "检测到硬编码密码")

    def _check_sql_injection(self, code: str, result: AuditResult):
        """检查SQL注入风险

        Args:
            code: 代码内容
            result: 审核结果
        """
        if re.search(r'\.execute\s*\(\s*["\'].*\+.*["\']', code):
            result.add_warning(
                "SECURITY_SQL_INJECTION_RISK",
                "检测到SQL语句字符串拼接，可能存在SQL注入风险，建议使用参数化查询",
            )

    def _check_command_injection(self, code: str, result: AuditResult):
        """检查命令注入风险

        Args:
            code: 代码内容
            result: 审核结果
        """
        cmd_injection_pattern = (
            r"(?:os\.system|os\.popen|subprocess\.call|subprocess\.run|subprocess\.Popen|eval|exec)\s*\("
        )
        if re.search(cmd_injection_pattern, code):
            result.add_warning(
                "SECURITY_COMMAND_INJECTION_RISK",
                "检测到高危函数调用，可能存在命令注入风险，请谨慎处理外部输入",
            )

    @staticmethod
    def _default_sensitive_patterns() -> list[tuple[str, str]]:
        """默认敏感信息模式（兜底）

        Returns:
            (正则表达式, 类型名称) 元组列表
        """
        return [
            (r'password\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "password"),
            (r'passwd\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "passwd"),
            (r'pwd\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "pwd"),
            (r'api[_-]?key\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "api_key"),
            (r'secret\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "secret"),
            (r'token\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{10,}["\']', "token"),
            (r"Bearer\s+[A-Za-z0-9\-_]{20,}", "bearer_token"),
        ]

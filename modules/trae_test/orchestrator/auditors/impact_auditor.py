"""影响分析审核器"""

from typing import Any

from ..audit_models import AuditResult
from ..config import AuditType
from ..audit_rules import RuleManager


class ImpactAuditor:
    """影响分析审核器"""

    def __init__(self, rule_manager: RuleManager | None = None):
        """初始化影响分析审核器

        Args:
            rule_manager: 可选的 RuleManager 实例
        """
        self.rule_manager = rule_manager or RuleManager()

    def audit(self, changes: Any, context: dict) -> AuditResult:
        """审核代码变更影响

        Args:
            changes: 代码变更内容
            context: 变更上下文（文件路径、变更类型等）

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.IMPACT

        file_path = context.get("file_path", "")

        # 检查是否是核心文件
        core_files = ["core/__init__.py", "core/config_manager.py", "core/environment.py", "__init__.py"]

        if any(core in file_path for core in core_files):
            result.add_warning("IMPACT_CORE_FILE", f"修改了核心文件: {file_path}", file_path)
            result.add_suggestion("核心文件变更需要额外测试，请确保运行完整测试套件")

        # 检查变更的文件数量
        if isinstance(changes, list) and len(changes) > 10:
            result.add_warning("IMPACT_MANY_FILES", f"变更涉及{len(changes)}个文件，影响范围较大")
            result.add_suggestion("大量文件变更建议分批提交和测试")

        # 检查是否有破坏性变更
        destructive_keywords = ["delete", "drop", "remove", "truncate"]
        changes_str = str(changes).lower()

        for keyword in destructive_keywords:
            if keyword in changes_str:
                result.add_warning("IMPACT_DESTRUCTIVE_CHANGE", f"检测到破坏性关键词: {keyword}")
                break

        return result

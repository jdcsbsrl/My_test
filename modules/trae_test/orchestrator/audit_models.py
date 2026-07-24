"""审核结果模型 - 值对象定义

提供 AuditIssue 值对象和重构的 AuditResult 模型，
替代原始 audit_agent_enhanced.py 中 errors/warnings dict 方案。

变更历史：
    - v1.0 (2026-07-24): 初始版本，新增 AuditIssue 值对象，重构 AuditResult
      保留 errors/warnings 作为 property，保持 to_dict() 向后兼容
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class AuditIssue:
    """审核问题值对象

    表示一条具体的审核发现，包含严重程度、规则标识、分类等结构化信息。

    Attributes:
        severity: 严重程度 ("error" / "warning" / "manual_review")
        rule_id: 规则ID，如 "TC_FIELD_CREATOR_INVALID"
        category: 分类，如 "field_value" / "style" / "security" / "env" / "impact"
        message: 人类可读的描述信息
        location: 代码位置/字段名称/文件路径
        fix_hint: 修复建议（可选）
        confidence: 置信度，0.0~1.0
    """

    severity: str  # "error" / "warning" / "manual_review"
    rule_id: str  # 规则ID
    category: str  # 分类
    message: str  # 描述信息
    location: str = ""  # 代码位置
    fix_hint: str | None = None  # 修复建议
    confidence: float = 1.0  # 置信度


@dataclass
class AuditResult:
    """审核结果模型

    重构后的 AuditResult，用 issues: list[AuditIssue] 替代原始的
    errors + warnings 双列表方案，同时通过 property 保持向后兼容。

    使用方式:
        result = AuditResult()
        result.add_error("ERR001", "错误描述", "location")
        result.add_warning("WARN001", "警告描述", "location")

        # 新方式（推荐）:
        from .audit_models import AuditIssue
        result.issues.append(AuditIssue(
            severity="error",
            rule_id="ERR001",
            category="field_value",
            message="错误描述",
            location="location"
        ))
    """

    issues: list[AuditIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    score: float | None = None  # 质量评分（0-100），由 TestCaseScoreEngine 集成
    audit_type: Any = None  # AuditType 枚举
    timestamp: str = ""
    execution_time: float = 0.0
    _forced_passed: bool | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """自动填充时间戳"""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def passed(self) -> bool:
        """审核是否通过

        优先尊重显式设置（通过 setter），否则从 issues 动态计算。
        当 issues 中存在 severity="error" 的问题时，审核不通过。
        """
        if self._forced_passed is not None:
            return self._forced_passed
        return all(i.severity != "error" for i in self.issues)

    @passed.setter
    def passed(self, value: bool):
        """显式设置 passed 值（覆盖动态计算）"""
        self._forced_passed = value

    @property
    def errors(self) -> list[dict[str, str]]:
        """从 issues 中筛选 severity="error" 的问题，返回与原始兼容的 dict 列表"""
        return [
            {"code": issue.rule_id, "message": issue.message, "location": issue.location}
            for issue in self.issues
            if issue.severity == "error"
        ]

    @errors.setter
    def errors(self, value: list[dict[str, str]]):
        """errors setter（保持向后兼容，支持 mock 场景中直接赋值）"""
        # 移除原有 error 级别的问题
        self.issues = [i for i in self.issues if i.severity != "error"]
        # 添加新问题
        for entry in value:
            self.issues.append(
                AuditIssue(
                    severity="error",
                    rule_id=entry.get("code", ""),
                    category="legacy",
                    message=entry.get("message", ""),
                    location=entry.get("location", ""),
                )
            )
        # passed 由 property 动态计算，无需手动设置

    @property
    def warnings(self) -> list[dict[str, str]]:
        """从 issues 中筛选 severity="warning" 的问题，返回与原始兼容的 dict 列表"""
        return [
            {"code": issue.rule_id, "message": issue.message, "location": issue.location}
            for issue in self.issues
            if issue.severity == "warning"
        ]

    @warnings.setter
    def warnings(self, value: list[dict[str, str]]):
        """warnings setter（保持向后兼容，支持 mock 场景中直接赋值）"""
        # 移除原有 warning 级别的问题
        self.issues = [i for i in self.issues if i.severity != "warning"]
        # 添加新问题
        for entry in value:
            self.issues.append(
                AuditIssue(
                    severity="warning",
                    rule_id=entry.get("code", ""),
                    category="legacy",
                    message=entry.get("message", ""),
                    location=entry.get("location", ""),
                )
            )

    # --- 向后兼容方法（标记为 deprecated） ---

    def add_error(self, code: str, message: str, location: str = "", severity: str = "error"):
        """添加错误或警告

        .. deprecated::
            推荐直接使用 ``issues.append(AuditIssue(...))`` 替代。

        Args:
            code: 错误代码 / 规则ID
            message: 错误消息
            location: 错误位置
            severity: 严重程度 ("error" / "warning")
        """
        self.issues.append(
            AuditIssue(
                severity=severity,
                rule_id=code,
                category="legacy",
                message=message,
                location=location,
            )
        )

    def add_warning(self, code: str, message: str, location: str = "", severity: str = "warning"):
        """添加警告

        .. deprecated::
            推荐使用 ``issues.append(AuditIssue(...))`` 替代。

        Args:
            code: 警告代码 / 规则ID
            message: 警告消息
            location: 警告位置
            severity: 严重程度（默认 "warning"）
        """
        self.add_error(code, message, location, severity)

    def add_suggestion(self, suggestion: str):
        """添加改进建议

        Args:
            suggestion: 改进建议文本
        """
        self.suggestions.append(suggestion)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式（与原始输出完全一致）

        用于外部 API 返回，保持向后兼容。
        """
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "suggestion_count": len(self.suggestions),
            "audit_type": self.audit_type.value if hasattr(self.audit_type, "value") else self.audit_type,
            "timestamp": self.timestamp,
            "execution_time": self.execution_time,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """转换为存储用字典格式（完整序列化所有字段）

        用于内部存储（如数据库），包含完整的 AuditIssue 字段，
        不丢失 severity/rule_id/category/location/fix_hint/confidence。
        """
        data = asdict(self)
        data.pop("_forced_passed", None)
        if hasattr(self.audit_type, "value"):
            data["audit_type"] = self.audit_type.value
        return data

    def __str__(self) -> str:
        """字符串表示"""
        status = "[通过]" if self.passed else "[未通过]"
        return (
            f"审核结果: {status}\n"
            f"错误: {len(self.errors)}个, 警告: {len(self.warnings)}个\n"
            f"耗时: {self.execution_time:.2f}秒"
        )

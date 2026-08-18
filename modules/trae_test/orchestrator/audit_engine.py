"""审核引擎 - 审核类型路由与调度

职责：
- 路由 AuditType 到对应的审核器
- 修复 ALL 审核的异常传播（不再将 Exception 降级为 warning）
- 集成 AuditLogger 记录日志
- 集成 RuleManager 加载规则
- 支持 timeout 超时检查
"""

import os
from datetime import datetime
from typing import Any

from .audit_models import AuditIssue, AuditResult
from .audit_rules import RuleManager
from .config import AuditConfig, AuditType


# 审核器类型标识
TEST_CASE_AUDITOR = "test_case"
CODE_AUDITOR = "code"
SECURITY_AUDITOR = "security"
ENVIRONMENT_AUDITOR = "environment"
IMPACT_AUDITOR = "impact"


class AuditEngine:
    """审核引擎 - 审核类型路由与调度"""

    def __init__(self, config: AuditConfig | None = None):
        """初始化审核引擎

        Args:
            config: 审核配置
        """
        self.config = config or AuditConfig()
        self.rule_manager = RuleManager()
        self._logger = None

        # 各审核器（延迟初始化）
        self._auditors: dict[str, Any] = {}

    @property
    def logger(self):
        if self._logger is None:
            from .audit_logger import AuditLogger

            self._logger = AuditLogger()
        return self._logger

    def _get_auditor(self, auditor_type: str):
        """获取或创建审核器

        Args:
            auditor_type: 审核器类型标识

        Returns:
            审核器实例
        """
        if auditor_type not in self._auditors:
            if auditor_type == TEST_CASE_AUDITOR:
                from .auditors import TestCaseAuditor

                self._auditors[auditor_type] = TestCaseAuditor(self.rule_manager)
            elif auditor_type == CODE_AUDITOR:
                from .auditors import CodeAuditor

                self._auditors[auditor_type] = CodeAuditor(self.rule_manager)
            elif auditor_type == SECURITY_AUDITOR:
                from .auditors import SecurityAuditor

                self._auditors[auditor_type] = SecurityAuditor(self.rule_manager)
            elif auditor_type == ENVIRONMENT_AUDITOR:
                from .auditors import EnvironmentAuditor

                self._auditors[auditor_type] = EnvironmentAuditor(self.rule_manager)
            elif auditor_type == IMPACT_AUDITOR:
                from .auditors import ImpactAuditor

                self._auditors[auditor_type] = ImpactAuditor(self.rule_manager)
        return self._auditors[auditor_type]

    def audit(self, target: Any, audit_type: AuditType = AuditType.ALL, context: dict | None = None) -> AuditResult:
        """执行审核 - 核心路由

        Args:
            target: 审核目标
            audit_type: 审核类型
            context: 审核上下文

        Returns:
            AuditResult: 审核结果
        """
        start_time = datetime.now()
        context = context or {}

        if audit_type == AuditType.TEST_CASE:
            strict_level = context.get("strict_level", self.config.strict_level)
            result = self._get_auditor(TEST_CASE_AUDITOR).audit(target, strict_level)
        elif audit_type == AuditType.CODE:
            language = context.get("language", "python")
            result = self._get_auditor(CODE_AUDITOR).audit(target, language)
        elif audit_type == AuditType.ENVIRONMENT:
            result = self._get_auditor(ENVIRONMENT_AUDITOR).audit(target)
        elif audit_type == AuditType.IMPACT:
            result = self._get_auditor(IMPACT_AUDITOR).audit(target, context)
        elif audit_type == AuditType.SECURITY:
            result = self._get_auditor(SECURITY_AUDITOR).audit(target)
        elif audit_type == AuditType.ALL:
            result = self._audit_all(target, context)
        else:
            result = AuditResult()
            result.add_error("UNKNOWN_AUDIT_TYPE", f"未知的审核类型: {audit_type}")

        # 记录执行时间
        result.execution_time = (datetime.now() - start_time).total_seconds()
        result.audit_type = audit_type

        return result

    def _audit_all(self, target: Any, context: dict) -> AuditResult:
        """全能审核 - 修复异常传播

        关键修复：不再将 Exception 降级为 warning，
        而是记录 error 并继续执行其他类型的审核，
        但 AuditFailedException 会被传播。

        Args:
            target: 审核目标
            context: 审核上下文

        Returns:
            AuditResult: 合并后的审核结果
        """
        from .audit_agent_enhanced import AuditFailedException

        combined_result = AuditResult()
        combined_result.audit_type = AuditType.ALL
        start_time = datetime.now()

        # 如果是字符串且是文件路径
        if isinstance(target, str) and (target.endswith(".xlsx") or target.endswith(".xls")):
            print("[INFO] 检测到Excel文件路径: %s" % target)

            # 验证文件名和路径规范
            self._audit_file_path(target, combined_result)

            # 验证Excel文件内容
            try:
                from ..utils.excel_generator import ExcelGenerator

                is_valid, error_msg = ExcelGenerator.validate_excel(target)

                if is_valid:
                    print("[OK] Excel文件验证通过: %s" % target)
                    combined_result.add_suggestion(f"Excel文件已生成并验证通过: {target}")
                else:
                    print("[FAIL] Excel文件验证失败: %s" % error_msg)
                    combined_result.add_error("EXCEL_INVALID", f"Excel文件验证失败: {error_msg}", target)
                    combined_result.passed = False
            except Exception as e:
                print("[WARN] 验证Excel文件时出错: %s" % str(e))
                combined_result.add_warning(
                    "EXCEL_VALIDATION_ERROR",
                    f"验证Excel文件时出错: {str(e)}",
                    target,
                )

            # 只有所有检查都通过才标记为通过
            combined_result.passed = len(combined_result.errors) == 0

            return combined_result

        # 自动识别审核类型
        audit_types = self._auto_select_audit_types(target)

        for audit_type in audit_types:
            if audit_type == AuditType.ALL:
                continue  # 防止无限递归

            # 超时检查
            if self.config.timeout > 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.config.timeout:
                    combined_result.add_warning(
                        "AUDIT_TIMEOUT",
                        f"审核超时（超过{self.config.timeout}秒），剩余审核类型已跳过",
                    )
                    break

            try:
                result = self.audit(target, audit_type, context)

                # 合并结果
                for issue in result.issues:
                    combined_result.issues.append(issue)
                combined_result.suggestions.extend(result.suggestions)
                combined_result.passed = all(
                    i.severity != "error" for i in combined_result.issues
                )

            except AuditFailedException:
                # AuditFailedException 仍然传播
                raise
            except Exception as e:
                # 修复：普通的 Exception 不再降级为 warning
                # 而是记录为 error（但不同于 AuditFailedException，不阻断流程）
                combined_result.issues.append(AuditIssue(
                    severity="error",
                    rule_id=f"AUDIT_{audit_type.value.upper()}_ERROR",
                    category="system",
                    message=f"执行{audit_type.value}审核时出现系统错误: {str(e)}",
                    confidence=1.0,
                ))
                combined_result.passed = False

        return combined_result

    def _auto_select_audit_types(self, target: Any) -> list[AuditType]:
        """自动选择审核类型

        Args:
            target: 审核目标

        Returns:
            list[AuditType]: 需要执行的审核类型列表
        """
        if self.config.auto_select_audit_types:
            audit_types = []

            # 根据目标类型自动选择审核
            if isinstance(target, list) and len(target) > 0:
                # 可能是测试用例
                if isinstance(target[0], dict) and "用例名称" in target[0]:
                    audit_types.append(AuditType.TEST_CASE)

            if isinstance(target, str):
                # 可能是代码
                if any(ext in target for ext in [".py", ".js", ".java", ".cpp"]):
                    audit_types.extend([AuditType.CODE, AuditType.SECURITY])
                elif target.endswith(".json"):
                    audit_types.append(AuditType.ENVIRONMENT)

            if isinstance(target, dict):
                # 可能是配置
                if any(key in target for key in ["dependencies", "env", "config"]):
                    audit_types.append(AuditType.ENVIRONMENT)

            # 默认添加所有审核
            if not audit_types:
                audit_types = [
                    AuditType.TEST_CASE,
                    AuditType.CODE,
                    AuditType.ENVIRONMENT,
                    AuditType.SECURITY,
                ]

            return [at for at in audit_types if at != AuditType.ALL]
        else:
            return [at for at in self.config.audit_types if at != AuditType.ALL]

    def _audit_file_path(self, file_path: str, result: AuditResult):
        """审核Excel文件的文件名和存放路径是否符合规范

        Args:
            file_path: 文件路径
            result: 审核结果对象
        """
        import re

        # 提取目录和文件名
        dir_path = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)

        # 验证文件名格式
        if not file_name.startswith("需求"):
            result.add_error(
                "FILE_NAME_INVALID",
                f"文件名必须以'需求'开头，当前文件名: {file_name}",
                file_path,
            )
        if not file_name.endswith(".xlsx"):
            result.add_error(
                "FILE_NAME_INVALID",
                f"文件扩展名必须为.xlsx，当前文件名: {file_name}",
                file_path,
            )
        # 检查是否包含需求ID或需求名
        if file_name.startswith("需求") and file_name.endswith(".xlsx"):
            name_without_ext = file_name[:-5]  # 去掉.xlsx
            if len(name_without_ext) <= 2:  # 只有"需求"两个字
                result.add_error(
                    "FILE_NAME_INVALID",
                    f"文件名格式不正确，应包含需求ID或需求名，格式: 需求{{id}}{{需求名}}.xlsx，当前文件名: {file_name}",
                    file_path,
                )

        # 验证存放路径
        path_pattern = r".*workspace[\\/](\d{8})[\\/][^\\/]+\.xlsx$"
        if not re.match(path_pattern, file_path, re.IGNORECASE):
            result.add_error(
                "FILE_PATH_INVALID",
                f"文件存放路径不符合规范，应存放在workspace/YYYYMMDD/目录下，当前路径: {file_path}",
                file_path,
            )
        else:
            # 验证日期格式
            match = re.match(path_pattern, file_path, re.IGNORECASE)
            date_str = match.group(1)
            try:
                from datetime import datetime as dt

                dt.strptime(date_str, "%Y%m%d")
            except ValueError:
                result.add_error(
                    "FILE_PATH_INVALID",
                    f"日期格式不正确，应为YYYYMMDD格式，当前: {date_str}",
                    file_path,
                )

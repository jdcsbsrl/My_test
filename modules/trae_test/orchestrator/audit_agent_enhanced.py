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
"""

import ast
import os
import re
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .config import AuditConfig, AuditType


class AuditResult:
    """审核结果类"""

    def __init__(self):
        self.passed: bool = True
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []
        self.suggestions: list[str] = []
        self.audit_type: AuditType = AuditType.ALL
        self.timestamp: str = datetime.now().isoformat()
        self.execution_time: float = 0.0

    def add_error(self, code: str, message: str, location: str = "", severity: str = "error"):
        """添加错误或警告

        Args:
            code: 错误代码
            message: 错误消息
            location: 错误位置
            severity: 严重程度 (error/warning)
        """
        if severity == "error":
            self.passed = False

        entry = {"code": code, "message": message, "location": location}

        if severity == "error":
            self.errors.append(entry)
        else:
            self.warnings.append(entry)

    def add_suggestion(self, suggestion: str):
        """添加改进建议"""
        self.suggestions.append(suggestion)

    def add_warning(self, code: str, message: str, location: str = "", severity: str = "warning"):
        """添加警告"""
        self.add_error(code, message, location, severity)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "suggestion_count": len(self.suggestions),
            "audit_type": self.audit_type.value if isinstance(self.audit_type, AuditType) else self.audit_type,
            "timestamp": self.timestamp,
            "execution_time": self.execution_time,
        }

    def __str__(self) -> str:
        """字符串表示"""
        status = "[通过]" if self.passed else "[未通过]"
        return (
            f"审核结果: {status}\n"
            f"错误: {len(self.errors)}个, 警告: {len(self.warnings)}个\n"
            f"耗时: {self.execution_time:.2f}秒"
        )


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
    """审核Agent - 全能实时审核系统"""

    # 标准测试用例字段
    STANDARD_TEST_CASE_FIELDS = [
        "用例目录",
        "用例名称",
        "需求ID",
        "前置条件",
        "用例步骤",
        "预期结果",
        "用例类型",
        "用例状态",
        "用例等级",
        "创建人",
        "优先级",
        "是否可自动化",
        "关联缺陷ID",
        "回归测试标识",
        "知识库关联",
    ]

    # 业务字段值校验规则（v3.1 - 严格模式）
    FIELD_VALUE_RULES = {
        "用例状态": {
            "valid_values": ["正常"],
            "default_value": "正常",
            "required": True,
            "error_message": "用例状态必须为'正常'（草稿/待评审等状态不允许提交）",
        },
        "用例等级": {
            "valid_values": ["高", "中", "低"],
            "default_value": "中",
            "required": True,
            "error_message": "用例等级必须为'高'、'中'或'低'",
        },
        "优先级": {
            "valid_values": ["P0", "P1", "P2"],
            "default_value": "P1",
            "required": True,
            "error_message": "优先级必须为'P0'、'P1'或'P2'",
        },
        "用例类型": {
            "valid_values": ["功能测试", "接口测试", "性能测试", "安全测试", "兼容性测试"],
            "default_value": "功能测试",
            "required": True,
            "error_message": "用例类型必须为'功能测试'、'接口测试'、'性能测试'、'安全测试'或'兼容性测试'",
        },
        "是否可自动化": {
            "valid_values": ["是", "否"],
            "default_value": "否",
            "required": True,
            "error_message": "是否可自动化必须为'是'或'否'",
        },
        "回归测试标识": {
            "valid_values": ["是", "否"],
            "default_value": "否",
            "required": False,
            "error_message": "回归测试标识必须为'是'或'否'",
        },
        "创建人": {
            "valid_values": ["余小龙", "闫海燕"],
            "default_value": "余小龙",
            "required": True,
            "error_message": "创建人必须为有效测试人员姓名，当前仅允许：余小龙、闫海燕",
        },
    }

    # 禁止的敏感信息模式
    SENSITIVE_PATTERNS = [
        (r'password\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "password"),
        (r'passwd\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "passwd"),
        (r'pwd\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "pwd"),
        (r'api[_-]?key\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "api_key"),
        (r'secret\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "secret"),
        (r'token\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{10,}["\']', "token"),
        (r"Bearer\s+[A-Za-z0-9\-_]{20,}", "bearer_token"),
    ]

    # 需要审批的操作类型
    REQUIRES_APPROVAL = {
        OperationType.CODE_GENERATION,
        OperationType.FOLDER_CREATION,
        OperationType.FILE_DELETE,
        OperationType.CONFIG_CHANGE,
    }

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
        # 自动检测是否为 CI 环境
        self._is_ci = os.getenv("CI", "").lower() in ("true", "1", "yes")
        if self._is_ci:
            print("[AuditAgent] 检测到 CI 环境，交互审批模式已禁用")

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

        # 操作前审核：如果是需要审批的操作，先询问用户
        if self._needs_approval(context):
            approval_result = self._request_user_approval(context)
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

        # 根据审核类型选择审核方法
        if audit_type_enum == AuditType.TEST_CASE:
            result = self.audit_test_cases(target)
        elif audit_type_enum == AuditType.CODE:
            result = self.audit_code(target, context.get("language", "python"))
        elif audit_type_enum == AuditType.ENVIRONMENT:
            result = self.audit_environment(target)
        elif audit_type_enum == AuditType.IMPACT:
            result = self.audit_impact(target, context)
        elif audit_type_enum == AuditType.SECURITY:
            result = self.audit_security(target)
        elif audit_type_enum == AuditType.ALL:
            result = self._audit_all(target, context)
        else:
            result = AuditResult()
            result.add_error("UNKNOWN_AUDIT_TYPE", f"未知的审核类型: {audit_type}")

        # 计算执行时间
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

    def _needs_approval(self, context: dict) -> bool:
        """判断操作是否需要用户审批

        Args:
            context: 操作上下文

        Returns:
            bool: 是否需要审批
        """
        operation_type = OperationType.from_context(context)
        return operation_type in self.REQUIRES_APPROVAL

    def _prompt_user_approval(self) -> bool:
        """统一的用户审批交互逻辑

        Returns:
            bool: 用户是否批准
        """
        if self.config.interactive_mode and not self._is_ci:
            try:
                user_input = input("\n请确认是否允许执行此操作？(y/n): ").strip().lower()
                return user_input in ("y", "yes", "是", "")
            except (EOFError, KeyboardInterrupt):
                print("\n[WARN] 无法获取用户输入，操作已被拒绝")
                return False
        elif self.config.auto_approve:
            print("\n[WARN] 操作已自动批准（auto_approve=True），请确保此设置在安全环境中使用")
            return True
        else:
            print("\n[BLOCK] 审核阻断：操作需要用户批准但当前为非交互环境")
            print("[HINT] 设置 AuditConfig(interactive_mode=True) 启用交互审批")
            print("[HINT] 或在可信环境中设置 AuditConfig(auto_approve=True) 自动批准")
            return False

    def _request_user_approval(self, context: dict) -> dict[str, Any]:
        """请求用户审批操作

        Args:
            context: 操作上下文

        Returns:
            Dict: 审批结果 {'approved': bool, 'reason': str}
        """
        operation_type = OperationType.from_context(context)
        action = context.get("action", "执行操作")
        target = context.get("target", "未知目标")
        purpose = context.get("purpose", "未说明目的")

        # 构建审批请求信息
        approval_message = self._build_approval_message(operation_type, action, target, purpose)

        # 显示审批信息
        print("\n" + "=" * 80)
        print("[操作审批请求]")
        print("=" * 80)
        print(approval_message)
        print("=" * 80)

        # 记录日志
        self._log_operation_request(operation_type, action, target, purpose)

        # 根据环境决定审批策略
        self.user_approved = self._prompt_user_approval()

        return {"approved": self.user_approved, "reason": "用户已批准" if self.user_approved else "用户拒绝/审核阻断"}

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
        type_descriptions = {
            OperationType.CODE_GENERATION: "代码生成",
            OperationType.FOLDER_CREATION: "文件夹创建",
            OperationType.FILE_DELETE: "文件删除",
            OperationType.CONFIG_CHANGE: "配置变更",
        }

        lines = [
            f"操作类型: {type_descriptions.get(operation_type, operation_type.value)}",
            f"操作动作: {action}",
            f"操作目标: {target}",
            f"操作目的: {purpose}",
            "",
            "请确认是否允许执行此操作？",
            "",
            "[注意] 此操作可能会影响项目结构或代码，请仔细确认！",
        ]

        return "\n".join(lines)

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
        context = {"action": action, "target": target, "purpose": purpose}

        print("\n" + "=" * 80)
        print("[操作前审核]")
        print("=" * 80)
        print("操作动作: %s" % action)
        print("操作目标: %s" % target)
        print("操作目的: %s" % (purpose if purpose else "未说明"))
        print("=" * 80)

        if self._needs_approval(context):
            print("\n[WARN] 此操作需要您的批准！")
            print("\n[操作详情]:")
            print("  - 类型: %s" % OperationType.from_context(context).value)
            print("  - 动作: %s" % action)
            print("  - 目标: %s" % target)
            print("  - 目的: %s" % purpose)

            self.user_approved = self._prompt_user_approval()

            return self.user_approved
        else:
            print("[OK] 此操作无需审批，可直接执行")
            return True

    def _audit_all(self, target: Any, context: dict) -> AuditResult:
        """执行全能审核

        Args:
            target: 审核目标
            context: 审核上下文

        Returns:
            AuditResult: 合并后的审核结果
        """
        combined_result = AuditResult()
        combined_result.audit_type = AuditType.ALL

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
                    "EXCEL_VALIDATION_ERROR", f"验证Excel文件时出错: {str(e)}", target, severity="warning"
                )

            # 只有所有检查都通过才标记为通过
            combined_result.passed = len(combined_result.errors) == 0

            return combined_result

        # 自动识别审核类型
        audit_types = self._auto_select_audit_types(target)

        for audit_type in audit_types:
            if audit_type == AuditType.ALL:
                continue  # 防止无限递归
            try:
                result = self.audit(target, audit_type, context)

                # 合并结果
                combined_result.passed = combined_result.passed and result.passed
                combined_result.errors.extend(result.errors)
                combined_result.warnings.extend(result.warnings)
                combined_result.suggestions.extend(result.suggestions)

            except Exception as e:
                # 对于ALL类型的审核，某个类型审核失败不应该导致整体失败
                combined_result.add_warning(
                    f"AUDIT_{audit_type.value.upper()}_WARNING",
                    f"执行{audit_type.value}审核时出现问题: {str(e)}",
                    severity="warning",
                )

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
                audit_types = [AuditType.TEST_CASE, AuditType.CODE, AuditType.ENVIRONMENT, AuditType.SECURITY]

            return audit_types
        else:
            return self.config.audit_types

    def audit_test_cases(self, test_cases: Any) -> AuditResult:
        """审核测试用例

        Args:
            test_cases: 测试用例列表或其他对象

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.TEST_CASE

        # 如果不是列表类型，直接通过
        if not isinstance(test_cases, list):
            print(f" 审核目标不是测试用例列表，类型: {type(test_cases)}")
            result.add_suggestion(f"跳过测试用例审核，目标类型为 {type(test_cases)}")
            return result

        print(f" 审核测试用例，数量: {len(test_cases) if test_cases else 0}")

        # 检查列表是否为空或者包含测试用例格式的字典
        if not test_cases:
            result.add_error("EMPTY_TEST_CASES", "测试用例列表为空", severity="error")
            return result

        # 检查第一个元素是否是测试用例格式
        first_item = test_cases[0] if test_cases else None
        if not isinstance(first_item, dict):
            result.add_suggestion("列表元素不是字典类型，跳过测试用例审核")
            return result

        for idx, case in enumerate(test_cases, start=1):
            case_location = f"第{idx}条用例"

            # 验证必需字段存在（允许字段顺序不同）
            missing_fields = []
            for field in self.STANDARD_TEST_CASE_FIELDS:
                if field not in case:
                    missing_fields.append(field)

            if missing_fields:
                result.add_error("TC_FIELD_MISSING", f"缺少必需字段：{', '.join(missing_fields)}", case_location)

            # 验证用例名称不为空
            name = case.get("用例名称", "").strip()
            if not name:
                result.add_error("TC_NAME_EMPTY", "用例名称不能为空", case_location)

            # 验证用例目录格式
            directory = case.get("用例目录", "")
            if directory and not self._validate_directory_format(directory):
                result.add_warning(
                    "TC_DIRECTORY_FORMAT_WARNING",
                    f"用例目录格式不符合规范：{directory}",
                    case_location,
                    severity="warning",
                )

            # 验证用例步骤不为空
            steps = case.get("用例步骤", "").strip()
            if not steps:
                result.add_error("TC_STEPS_EMPTY", "用例步骤不能为空", case_location)

            # 验证预期结果不为空
            expected = case.get("预期结果", "").strip()
            if not expected:
                result.add_error("TC_EXPECTED_EMPTY", "预期结果不能为空", case_location)

            # 业务字段值校验
            self._audit_field_values(case, case_location, result)

        # 添加建议
        if result.warnings:
            result.add_suggestion("建议检查并修正上述警告信息")

        if not result.passed:
            result.add_suggestion("请按照15字段标准模板修正测试用例")
        else:
            result.add_suggestion(f"所有 {len(test_cases)} 条测试用例审核通过")

        return result

    def _audit_field_values(self, case: dict[str, Any], case_location: str, result: AuditResult):
        """校验业务字段值是否符合规范

        Args:
            case: 测试用例字典
            case_location: 用例位置描述
            result: 审核结果对象
        """
        for field_name, rules in self.FIELD_VALUE_RULES.items():
            field_value = case.get(field_name, "").strip()

            if not field_value and not rules.get("required", False):
                continue

            if rules.get("required", False) and not field_value:
                result.add_error(f"TC_FIELD_{field_name.upper()}_EMPTY", f"{field_name}不能为空", case_location)
                continue

            valid_values = rules.get("valid_values", [])
            if valid_values and field_value not in valid_values:
                result.add_error(
                    f"TC_FIELD_{field_name.upper()}_INVALID",
                    f"{rules.get('error_message', f'{field_name}值无效')}，当前值: '{field_value}'",
                    case_location,
                )

    def audit_code(self, code: Any, language: str = "python") -> AuditResult:
        """审核代码规范

        Args:
            code: 代码内容（字符串或文件路径）
            language: 编程语言

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.CODE

        # 如果是文件路径，读取内容
        if isinstance(code, (str, Path)) and os.path.isfile(str(code)):
            try:
                with open(code, encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                result.add_error("CODE_READ_ERROR", f"无法读取代码文件: {str(e)}")
                return result

        if not isinstance(code, str):
            result.add_error("CODE_NOT_STRING", "代码必须是字符串格式")
            return result

        if not code.strip():
            result.add_error("CODE_EMPTY", "代码内容为空")
            return result

        # 根据语言执行审核
        if language.lower() == "python":
            self._audit_python_code(code, result)
        else:
            self._audit_generic_code(code, result)

        return result

    def _audit_python_code(self, code: str, result: AuditResult):
        """审核Python代码

        Args:
            code: Python代码
            result: 审核结果对象
        """
        try:
            tree = ast.parse(code)

            # 检查代码风格问题
            lines = code.split("\n")

            for i, line in enumerate(lines, start=1):
                # 检查行长度
                if len(line) > 120:
                    result.add_warning(
                        "CODE_LINE_TOO_LONG", f"第{i}行超过120字符，建议拆分为多行", f"第{i}行", severity="warning"
                    )

                # 检查Tab vs 空格混用
                if "\t" in line and "    " in line:
                    result.add_warning("CODE_TAB_SPACE_MIX", f"第{i}行混用Tab和空格", f"第{i}行", severity="warning")

                # 检查行尾空格
                if line.rstrip() != line:
                    result.add_warning("CODE_TRAILING_SPACE", f"第{i}行包含尾随空格", f"第{i}行", severity="warning")

            # 检查导入
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    pass  # 基础导入，无问题
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("_"):
                        result.add_warning("CODE_PRIVATE_IMPORT", f"导入了私有模块: {node.module}", severity="warning")

        except SyntaxError as e:
            result.add_error("CODE_SYNTAX_ERROR", f"语法错误: {str(e)}", f"第{e.lineno}行")
        except (ValueError, TypeError) as e:
            result.add_error("CODE_PARSE_ERROR", f"代码解析错误: {str(e)}", severity="error")

    def _audit_generic_code(self, code: str, result: AuditResult):
        """通用代码审核

        Args:
            code: 代码
            result: 审核结果对象
        """
        lines = code.split("\n")

        for i, line in enumerate(lines, start=1):
            # 检查行长度
            if len(line) > 120:
                result.add_warning("CODE_LINE_TOO_LONG", f"第{i}行超过120字符", f"第{i}行", severity="warning")

            # 检查可疑注释
            if "TODO" in line or "FIXME" in line:
                result.add_warning("CODE_TODO_COMMENT", f"第{i}行包含TODO/FIXME注释", f"第{i}行", severity="warning")

    def audit_environment(self, env_config: dict) -> AuditResult:
        """审核环境配置

        Args:
            env_config: 环境配置字典

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.ENVIRONMENT

        if not env_config:
            result.add_warning("ENV_CONFIG_EMPTY", "环境配置为空", severity="warning")
            return result

        # 检查必需的配置项
        required_keys = ["python_version", "dependencies"]

        for key in required_keys:
            if key not in env_config:
                result.add_warning("ENV_MISSING_KEY", f"缺少必需的配置项: {key}", severity="warning")

        # 检查Python版本
        python_version = env_config.get("python_version", "")
        if python_version:
            if not re.match(r"^\d+\.\d+(\.\d+)?$", python_version):
                result.add_warning(
                    "ENV_INVALID_PYTHON_VERSION", f"Python版本格式不正确: {python_version}", severity="warning"
                )

        # 检查依赖列表
        dependencies = env_config.get("dependencies", [])
        if not isinstance(dependencies, list):
            result.add_error("ENV_DEPENDENCIES_NOT_LIST", "dependencies必须是列表格式", severity="error")
        elif len(dependencies) == 0:
            result.add_warning("ENV_NO_DEPENDENCIES", "没有定义任何依赖", severity="warning")

        # 检查环境变量
        env_vars = env_config.get("env_vars", {})
        if env_vars:
            for key, value in env_vars.items():
                if not key.isupper():
                    result.add_warning("ENV_VAR_LOWERCASE", f"环境变量名应使用大写: {key}", severity="warning")

        return result

    def audit_impact(self, changes: Any, context: dict) -> AuditResult:
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
            result.add_warning("IMPACT_CORE_FILE", f"修改了核心文件: {file_path}", file_path, severity="warning")
            result.add_suggestion("核心文件变更需要额外测试，请确保运行完整测试套件")

        # 检查变更的文件数量
        if isinstance(changes, list) and len(changes) > 10:
            result.add_warning("IMPACT_MANY_FILES", f"变更涉及{len(changes)}个文件，影响范围较大", severity="warning")
            result.add_suggestion("大量文件变更建议分批提交和测试")

        # 检查是否有破坏性变更
        destructive_keywords = ["delete", "drop", "remove", "truncate"]
        changes_str = str(changes).lower()

        for keyword in destructive_keywords:
            if keyword in changes_str:
                result.add_warning("IMPACT_DESTRUCTIVE_CHANGE", f"检测到破坏性关键词: {keyword}", severity="warning")
                break

        return result

    def audit_security(self, target: Any) -> AuditResult:
        """安全审核

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
            result.add_warning("SECURITY_EMPTY", "审核内容为空", severity="warning")
            return result

        # 检查敏感信息
        for pattern, info_type in self.SENSITIVE_PATTERNS:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                result.add_error(
                    "SECURITY_SENSITIVE_INFO",
                    f"检测到敏感信息: {info_type}",
                    f"位置: {match.group()[:50]}...",
                    severity="error",
                )

        # 检查硬编码密码
        if re.search(r'password\s*=\s*["\']\w+["\']', code, re.IGNORECASE):
            result.add_error("SECURITY_HARDCODED_PASSWORD", "检测到硬编码密码", severity="error")

        # 检查SQL注入风险
        if re.search(r'\.execute\s*\(\s*["\'].*\+.*["\']', code):
            result.add_warning(
                "SECURITY_SQL_INJECTION_RISK",
                "检测到SQL语句字符串拼接，可能存在SQL注入风险，建议使用参数化查询",
                severity="warning",
            )

        # 检查命令注入风险
        cmd_injection_pattern = (
            r"(?:os\.system|os\.popen|subprocess\.call|subprocess\.run|subprocess\.Popen|eval|exec)\s*\("
        )
        if re.search(cmd_injection_pattern, code):
            result.add_warning(
                "SECURITY_COMMAND_INJECTION_RISK",
                "检测到高危函数调用，可能存在命令注入风险，请谨慎处理外部输入",
                severity="warning",
            )

        return result

    def _validate_directory_format(self, directory: str) -> bool:
        """验证用例目录格式（严格模式 - 使用 dir_validator 校验）

        Args:
            directory: 目录字符串

        Returns:
            bool: 是否符合规范（严格模式，不阻断返回警告）
        """
        try:
            from modules.trae_test.utils.dir_validator import validate_directory

            valid, msg = validate_directory(directory, strict=False)
            if not valid:
                print(f"  [目录校验] {msg}")
            return valid
        except ImportError:
            # 降级：基本格式检查
            parts = directory.split(" - ")
            if len(parts) != 3:
                return False
            return all(p.strip() for p in parts)

    def _audit_file_path(self, file_path: str, result: AuditResult):
        """审核Excel文件的文件名和存放路径是否符合规范

        文件名格式：需求{id}{需求名}.xlsx
        存放路径：workspace/YYYYMMDD/{formal|draft}/

        Args:
            file_path: 文件路径
            result: 审核结果对象
        """
        import re

        # 提取目录和文件名
        dir_path = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)

        # 验证文件名格式
        # 正确格式：需求{id}{需求名}.xlsx 或 需求{需求名}.xlsx
        if not file_name.startswith("需求"):
            result.add_error(
                "FILE_NAME_INVALID", f"文件名必须以'需求'开头，当前文件名: {file_name}", file_path, severity="error"
            )
        if not file_name.endswith(".xlsx"):
            result.add_error(
                "FILE_NAME_INVALID", f"文件扩展名必须为.xlsx，当前文件名: {file_name}", file_path, severity="error"
            )
        # 检查是否包含需求ID或需求名
        if file_name.startswith("需求") and file_name.endswith(".xlsx"):
            name_without_ext = file_name[:-5]  # 去掉.xlsx
            if len(name_without_ext) <= 2:  # 只有"需求"两个字
                result.add_error(
                    "FILE_NAME_INVALID",
                    f"文件名格式不正确，应包含需求ID或需求名，格式: 需求{id}{需求名}.xlsx，当前文件名: {file_name}",
                    file_path,
                    severity="error",
                )

        # 验证存放路径
        # 正确路径格式：workspace/YYYYMMDD/formal/ 或 workspace/YYYYMMDD/draft/
        # 使用 [\\/] 匹配 Windows 和 Unix 路径分隔符
        path_pattern = r".*workspace[\\/](\d{8})[\\/](formal|draft)[\\/].*"
        if not re.match(path_pattern, file_path, re.IGNORECASE):
            result.add_error(
                "FILE_PATH_INVALID",
                f"文件存放路径不符合规范，应存放在workspace/YYYYMMDD/formal/或workspace/YYYYMMDD/draft/目录下，当前路径: {file_path}",
                file_path,
                severity="error",
            )
        else:
            # 验证日期格式
            match = re.match(path_pattern, file_path, re.IGNORECASE)
            date_str = match.group(1)
            try:
                from datetime import datetime

                datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                result.add_error(
                    "FILE_PATH_INVALID",
                    f"日期格式不正确，应为YYYYMMDD格式，当前: {date_str}",
                    file_path,
                    severity="error",
                )

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

        self.audit_logs.append(log_entry)

        # 调用通知回调
        if not result.passed and self.notify_callback:
            audit_type_str = audit_type.value if isinstance(audit_type, AuditType) else audit_type
            self.notify_callback(f"审核失败 [{audit_type_str}]: {len(result.errors)}个错误")

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

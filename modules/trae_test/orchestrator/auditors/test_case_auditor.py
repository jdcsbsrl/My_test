"""测试用例审核器"""

import re
from typing import Any

from ..audit_models import AuditResult
from ..config import AuditType
from ..audit_rules import RuleManager


class TestCaseAuditor:
    """测试用例审核器"""

    # 标准测试用例字段（15字段）
    REQUIRED_FIELDS = [
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

    # 业务字段值校验规则（兜底，优先使用 RuleManager）
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

    def __init__(self, rule_manager: RuleManager | None = None):
        """初始化测试用例审核器

        Args:
            rule_manager: 可选的 RuleManager 实例，未传入时使用默认实例
        """
        self.rule_manager = rule_manager or RuleManager()

    def audit(self, test_cases: list[dict], strict_level: int = 3) -> AuditResult:
        """审核测试用例

        功能：
        1. 检查是否为列表
        2. 检查必需字段完整性（15字段）
        3. 检查字段值合法性（使用 RuleManager 或硬编码规则）
        4. 集成质量评分（RuleManager.score_test_case）
        5. 命名规范检查（严格模式下）
        6. 字段长度检查（最严格模式下）

        Args:
            test_cases: 测试用例列表
            strict_level: 审核严格程度（1-5）

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.TEST_CASE

        # 检查是否为列表
        if not isinstance(test_cases, list):
            print(f" 审核目标不是测试用例列表，类型: {type(test_cases)}")
            result.add_suggestion(f"跳过测试用例审核，目标类型为 {type(test_cases)}")
            return result

        print(f" 审核测试用例，数量: {len(test_cases) if test_cases else 0}")

        # 检查列表是否为空
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

            # 必需字段检查
            self._check_required_fields(case, case_location, result)

            # 字段值合法性检查
            self._check_field_values(case, case_location, result)

            # 严格模式检查
            if strict_level >= 4:
                self._check_naming(case, case_location, result)
            if strict_level >= 5:
                self._check_field_length(case, case_location, result)

            # 集成质量评分
            try:
                score = self.rule_manager.score_test_case(case)
                if result.score is None or score < result.score:
                    result.score = score
            except Exception:
                pass

        # 添加建议
        if result.warnings:
            result.add_suggestion("建议检查并修正上述警告信息")

        if not result.passed:
            result.add_suggestion("请按照15字段标准模板修正测试用例")
        else:
            result.add_suggestion(f"所有 {len(test_cases)} 条测试用例审核通过")

        return result

    def _check_required_fields(self, case: dict, case_location: str, result: AuditResult):
        """检查必需字段完整性

        Args:
            case: 测试用例字典
            case_location: 用例位置描述
            result: 审核结果
        """
        # 验证必需字段存在
        missing_fields = []
        for field in self.REQUIRED_FIELDS:
            if field not in case:
                missing_fields.append(field)

        if missing_fields:
            result.add_error(
                "TC_FIELD_MISSING", f"缺少必需字段：{', '.join(missing_fields)}", case_location
            )

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
            )

        # 验证用例步骤不为空
        steps = case.get("用例步骤", "").strip()
        if not steps:
            result.add_error("TC_STEPS_EMPTY", "用例步骤不能为空", case_location)

        # 验证预期结果不为空
        expected = case.get("预期结果", "").strip()
        if not expected:
            result.add_error("TC_EXPECTED_EMPTY", "预期结果不能为空", case_location)

    def _check_field_values(self, case: dict, case_location: str, result: AuditResult):
        """校验业务字段值是否符合规范

        Args:
            case: 测试用例字典
            case_location: 用例位置描述
            result: 审核结果
        """
        # 优先使用 RuleManager 的规则，兜底使用内置规则
        try:
            field_rules = self.rule_manager.get_field_value_rules()
        except Exception:
            field_rules = self.FIELD_VALUE_RULES

        if not field_rules:
            field_rules = self.FIELD_VALUE_RULES

        for field_name, rules in field_rules.items():
            field_value = case.get(field_name, "").strip()

            if not field_value and not rules.get("required", False):
                continue

            if rules.get("required", False) and not field_value:
                result.add_error(
                    f"TC_FIELD_{field_name.upper()}_EMPTY",
                    f"{field_name}不能为空",
                    case_location,
                )
                continue

            valid_values = rules.get("valid_values", [])
            if valid_values and field_value not in valid_values:
                result.add_error(
                    f"TC_FIELD_{field_name.upper()}_INVALID",
                    f"{rules.get('error_message', f'{field_name}值无效')}，当前值: '{field_value}'",
                    case_location,
                )

    def _check_naming(self, case: dict, case_location: str, result: AuditResult):
        """严格模式（level >= 4）：审计字段命名规范和字段顺序

        Args:
            case: 测试用例字典
            case_location: 用例位置描述
            result: 审核结果
        """
        expected_order = self.REQUIRED_FIELDS
        actual_keys = list(case.keys())

        # 检查是否有非标准字段
        for key in actual_keys:
            if key not in expected_order and key not in ("",):
                result.add_warning(
                    "TC_FIELD_UNKNOWN",
                    f"发现非标准字段: '{key}'，标准字段请使用中文名称",
                    case_location,
                )

        # 检查字段顺序
        present_expected = [f for f in expected_order if f in actual_keys]
        present_actual = [f for f in actual_keys if f in expected_order]

        if present_expected != present_actual:
            result.add_warning(
                "TC_FIELD_ORDER",
                f"字段顺序与建议顺序不一致，建议顺序: {', '.join(present_expected)}",
                case_location,
            )

    def _check_field_length(self, case: dict, case_location: str, result: AuditResult):
        """最严格模式（level >= 5）：审计字段值长度和特殊字符

        Args:
            case: 测试用例字典
            case_location: 用例位置描述
            result: 审核结果
        """
        for field_name, field_value in case.items():
            if not isinstance(field_value, str) or not field_value.strip():
                continue

            # 检查字段值长度
            if len(field_value) > 500:
                result.add_warning(
                    "TC_FIELD_TOO_LONG",
                    f"字段 '{field_name}' 值过长（{len(field_value)}字符），建议控制在 500 字符以内",
                    case_location,
                )

            # 检查不可见特殊字符
            invisible_chars = re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", field_value)
            if invisible_chars:
                result.add_warning(
                    "TC_FIELD_SPECIAL_CHARS",
                    f"字段 '{field_name}' 包含不可见控制字符: {[hex(ord(c)) for c in set(invisible_chars)]}",
                    case_location,
                )

    def _validate_directory_format(self, directory: str) -> bool:
        """验证用例目录格式

        Args:
            directory: 目录字符串

        Returns:
            bool: 是否符合规范
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

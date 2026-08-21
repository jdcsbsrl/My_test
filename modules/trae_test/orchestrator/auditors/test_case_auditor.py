"""测试用例审核器"""

import re

from ..audit_models import AuditResult
from ..config import AuditType
from ..audit_rules import FINAL_SCORE_THRESHOLD, RuleManager
from ...utils.template_builder import ALL_FIELDS


class TestCaseAuditor:
    """测试用例审核器"""

    MIN_PRECONDITION_COUNT = 2
    MIN_STEP_COUNT = 3
    MIN_EXPECTED_COUNT = 2
    _POINT_PATTERN = re.compile(r"^\s*(?:\d+[\.、)]|[-*•])\s*.+")
    _ACTION_PATTERN = re.compile(r"(点击|双击|选择|输入|填写|勾选|清空|打开|进入|切换|提交|保存|删除|查询|搜索|上传|下载|展开|收起|确认|取消|登录|退出|拖动|悬停)")
    _OBJECT_PATTERN = re.compile(r"(页面|页|按钮|输入框|文本框|下拉框|选择框|复选框|单选框|表格|列表|弹窗|菜单|导航|标签|字段|列|链接|图标|区域|模块|订单|商品|客户|库存)")
    _VAGUE_PATTERN = re.compile(r"^(?:执行(?:相关|对应)?操作|进入相关页面|检查结果|操作成功|符合预期|页面正常|系统正常|数据正确|验证成功)[。；;！! ]*$")

    # 标准测试用例字段（15字段）
    REQUIRED_FIELDS = list(ALL_FIELDS)

    # 业务字段值校验规则（兜底，优先使用 RuleManager）
    FIELD_VALUE_RULES = {
        "用例状态": {
            "valid_values": ["正常"],
            "default_value": "正常",
            "required": True,
            "error_message": "用例状态只能为'正常'，审核和评分状态不得写入该字段",
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

    def audit(self, test_cases: list[dict], strict_level: int = 3, context: dict | None = None) -> AuditResult:
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

            # 业务内容检查：格式通过不代表用例可执行，内容问题必须阻断
            self._check_business_content(case, case_location, result)

            # 严格模式检查
            if strict_level >= 4:
                self._check_naming(case, case_location, result)
            if strict_level >= 5:
                self._check_field_length(case, case_location, result)

            # 集成质量评分
            try:
                final_score = case.get("最终评分")
                quality_score = case.get("质量评分")
                if final_score in (None, "") and quality_score in (None, ""):
                    raise ValueError("质量评分字段为空")
                score = float(final_score if final_score not in (None, "") else quality_score)
                if quality_score not in (None, "") and abs(float(quality_score) - score) > 0.01:
                    self._business_error(
                        result,
                        "TC_SCORE_SOURCE_MISMATCH",
                        f"最终评分({score:.2f})与质量评分({float(quality_score):.2f})不一致，必须使用同一评分版本",
                        case_location,
                    )
                case["质量评分"] = score
                case["最终评分"] = score
                result.score = score
                if score < FINAL_SCORE_THRESHOLD:
                    self._business_error(
                        result,
                        "TC_SCORE_BELOW_GATE",
                        f"最终质量评分为{score:.2f}分，低于85分交付门槛，必须优化后重新审核",
                        case_location,
                    )
            except Exception:
                self._business_error(
                    result,
                    "TC_SCORE_UNAVAILABLE",
                    "无法计算最终质量评分，禁止绕过评分门禁通过审核",
                    case_location,
                )

        # 需求级审核必须在单条用例审核完成后执行；覆盖元数据只存在运行时上下文，
        # 不改变生成器核心和正式15列表头。
        self._audit_requirement_coverage(test_cases, context or {}, result)

        # 添加建议
        if result.warnings:
            result.add_suggestion("建议检查并修正上述警告信息")

        if not result.passed:
            result.add_suggestion("请按照15字段标准模板修正测试用例")
        else:
            result.add_suggestion(f"所有 {len(test_cases)} 条测试用例审核通过")

        return result

    def _audit_requirement_coverage(self, test_cases: list[dict], context: dict, result: AuditResult):
        """审核需求级覆盖矩阵，防止“单条质量达标但整体覆盖不足”。

        context 约定：
        {
            "coverage_matrix": [
                {"id": "R1", "priority": "P0", "required_scenarios": ["正常", "异常"]}
            ],
            "excluded_scope": ["WMS", "质检"],
            "requires_rollback": True,
        }
        用例可通过运行时字段 ``覆盖规则ID``、``场景类型``、``回滚标识`` 提供映射，
        这些字段不会进入正式Excel模板。
        """
        matrix = context.get("coverage_matrix") or context.get("requirement_matrix") or []
        # 支持已有运行时 CoverageMatrix；不把运行时字段写入正式15列。
        if not matrix:
            runtime_matrices = [case.get("_runtime_coverage_matrix") for case in test_cases if case.get("_runtime_coverage_matrix")]
            if runtime_matrices:
                runtime = runtime_matrices[0] or {}
                matrix = [{"id": rule, "priority": "P1"} for rule in runtime.get("business_rules", [])]
                if runtime.get("normal_scenarios"):
                    for item in matrix:
                        item["required_scenarios"] = list(runtime.get("normal_scenarios", []))
        if context.get("require_requirement_coverage") and not matrix:
            self._business_error(result, "REQ_COVERAGE_MATRIX_MISSING", "已启用需求级审核，但未提供覆盖矩阵", "需求级覆盖")
            return
        excluded_scope = context.get("excluded_scope") or context.get("excluded_scopes") or []
        if not matrix and not excluded_scope and not context.get("requires_rollback"):
            return

        def values(case: dict, *names: str) -> set[str]:
            raw = next((case.get(name) for name in names if case.get(name) not in (None, "")), "")
            if isinstance(raw, (list, tuple, set)):
                return {str(v).strip() for v in raw if str(v).strip()}
            return {v.strip() for v in re.split(r"[,，;；\n|]", str(raw)) if v.strip()}

        mapped = []
        for case in test_cases:
            mapped.append({
                "rules": values(case, "覆盖规则ID", "覆盖规则", "coverage_rule_ids"),
                "scenarios": values(case, "场景类型", "场景标签", "scenario_type"),
                "priority": values(case, "优先级", "priority"),
                "rollback": values(case, "回滚标识", "是否回滚场景", "rollback")
                or (set() if not any(k in case for k in ("回滚标识", "是否回滚场景", "rollback")) else {"否"}),
                "text": " ".join(str(v) for v in case.values()),
            })

        covered_rule_ids = set().union(*(item["rules"] for item in mapped)) if mapped else set()
        valid_rules = []
        for rule in matrix:
            if not isinstance(rule, dict):
                self._business_error(result, "REQ_COVERAGE_MATRIX_INVALID", "需求覆盖矩阵中的规则必须是对象，不能使用字符串或其他类型", "需求级覆盖")
                continue
            rule_id = str(rule.get("id") or rule.get("rule_id") or "").strip()
            if not rule_id:
                self._business_error(result, "REQ_COVERAGE_MATRIX_INVALID", "需求覆盖矩阵规则缺少 id 或 rule_id", "需求级覆盖")
                continue
            valid_rules.append(rule)
            rule_cases = [item for item in mapped if rule_id in item["rules"]]
            if not rule_cases:
                self._business_error(result, "REQ_COVERAGE_INCOMPLETE", f"需求规则 {rule_id} 没有对应测试用例覆盖", "需求级覆盖")
                continue
            required_scenarios = {str(v).strip() for v in (rule.get("required_scenarios") or rule.get("scenarios") or []) if str(v).strip()}
            present_scenarios = set().union(*(item["scenarios"] for item in rule_cases))
            missing_scenarios = required_scenarios - present_scenarios
            if missing_scenarios:
                code = "REQ_P0_SCENARIO_MISSING" if str(rule.get("priority", "")).upper() == "P0" else "REQ_SCENARIO_MISSING"
                self._business_error(result, code, f"需求规则 {rule_id} 缺少场景覆盖：{', '.join(sorted(missing_scenarios))}", "需求级覆盖")

        if context.get("requires_rollback"):
            has_rollback = any(item["rollback"] & {"是", "有", "true", "True", "回滚"} or "回滚" in item["text"] for item in mapped)
            if not has_rollback:
                self._business_error(result, "REQ_ROLLBACK_SCENARIO_MISSING", "需求涉及跨对象或跨模块变更，但未提供回滚场景", "需求级覆盖")

        for excluded in excluded_scope:
            term = str(excluded).strip()
            if term and any(term.lower() in item["text"].lower() for item in mapped):
                self._business_error(result, "REQ_SCOPE_BOUNDARY_VIOLATION", f"用例包含需求明确排除的范围：{term}", "需求级范围")

        if matrix:
            expected_rule_ids = {str(r.get("id") or r.get("rule_id")).strip() for r in valid_rules}
            coverage = len(covered_rule_ids & expected_rule_ids) / max(1, len(expected_rule_ids))
            result.add_suggestion(f"需求规则覆盖率：{coverage:.0%}")
            threshold = context.get("coverage_threshold")
            if threshold is not None:
                try:
                    threshold = float(threshold)
                except (TypeError, ValueError):
                    self._business_error(result, "REQ_COVERAGE_THRESHOLD_INVALID", "覆盖率门槛必须是0到1之间的数字", "需求级覆盖")
                else:
                    if not 0 <= threshold <= 1:
                        self._business_error(result, "REQ_COVERAGE_THRESHOLD_INVALID", "覆盖率门槛必须是0到1之间的数字", "需求级覆盖")
                    elif coverage < threshold:
                        self._business_error(result, "REQ_COVERAGE_BELOW_THRESHOLD", f"需求规则覆盖率为{coverage:.0%}，低于要求的{threshold:.0%}", "需求级覆盖")

    @classmethod
    def _split_points(cls, value: object) -> list[str]:
        """将换行/编号/项目符号内容解析为独立条目。"""
        if not isinstance(value, str):
            return []
        lines = [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]
        points = []
        for line in lines:
            normalized = re.sub(r"^\s*(?:\d+[\.、)]|[-*•])\s*", "", line).strip()
            if normalized:
                points.append(normalized)
        return points

    def _business_error(self, result: AuditResult, rule_id: str, message: str, location: str):
        result.add_error(rule_id, message, location, severity="error")

    def _check_business_content(self, case: dict, case_location: str, result: AuditResult):
        """审核前置条件、步骤和预期结果是否能指导测试人员实际操作。"""
        preconditions = self._split_points(case.get("前置条件", ""))
        steps = self._split_points(case.get("用例步骤", ""))
        expected = self._split_points(case.get("预期结果", ""))

        if not preconditions:
            self._business_error(result, "TC_PRECONDITIONS_REQUIRED", "前置条件必须分点描述，且至少包含2条可验证条件", case_location)
        elif len(preconditions) < self.MIN_PRECONDITION_COUNT:
            self._business_error(result, "TC_PRECONDITIONS_MIN_COUNT", f"前置条件至少需要{self.MIN_PRECONDITION_COUNT}条，当前为{len(preconditions)}条", case_location)

        if len(steps) < self.MIN_STEP_COUNT:
            self._business_error(result, "TC_STEPS_MIN_COUNT", f"执行步骤至少需要{self.MIN_STEP_COUNT}条，当前为{len(steps)}条；每条必须独立分点", case_location)
        if len(expected) < self.MIN_EXPECTED_COUNT:
            self._business_error(result, "TC_EXPECTED_MIN_COUNT", f"预期结果至少需要{self.MIN_EXPECTED_COUNT}条，当前为{len(expected)}条；每条必须独立分点", case_location)

        for field_name, points, rule_id in (
            ("前置条件", preconditions, "TC_PRECONDITION_VAGUE"),
            ("用例步骤", steps, "TC_STEP_VAGUE"),
            ("预期结果", expected, "TC_EXPECTED_VAGUE"),
        ):
            for point in points:
                if self._VAGUE_PATTERN.match(point):
                    self._business_error(result, rule_id, f"{field_name}内容过于粗糙，必须说明具体业务对象、动作或可观察结果：{point}", case_location)

        for step_number, step in enumerate(steps, start=1):
            if not self._ACTION_PATTERN.search(step):
                self._business_error(result, "TC_STEP_ACTION_REQUIRED", f"第{step_number}步缺少明确操作动作，应描述点击、输入、选择、提交等具体动作：{step}", case_location)
            if not self._OBJECT_PATTERN.search(step):
                self._business_error(result, "TC_STEP_PAGE_OBJECT_REQUIRED", f"第{step_number}步缺少页面对象，应明确页面、按钮、输入框、列表等操作对象：{step}", case_location)
            if re.search(r"(输入|填写|选择|搜索|查询|上传)", step) and not re.search(r"[：:]|['\"]|“[^”]+”|\b\d+\b|\S+数据|测试", step):
                self._business_error(result, "TC_STEP_DATA_REQUIRED", f"第{step_number}步包含数据操作但未给出具体测试数据：{step}", case_location)

        for expected_number, expectation in enumerate(expected, start=1):
            if not re.search(r"(打开|显示|提示|生成|保存|更新|变为|状态|数量|金额|订单号|记录|可见|不可见|成功|失败|阻止|禁止|校验|一致)", expectation):
                self._business_error(result, "TC_EXPECTED_OBSERVABLE_REQUIRED", f"第{expected_number}条预期结果不可观察或验证，应描述页面、提示、状态、数据或记录变化：{expectation}", case_location)

        precondition_text = " ".join(preconditions)
        step_text = " ".join(steps)
        if preconditions and steps:
            referenced_terms = set(re.findall(r"[“\"]([^”\"]+)[”\"]", step_text))
            missing_terms = [term for term in referenced_terms if term not in precondition_text and len(term) >= 2]
            if missing_terms:
                self._business_error(result, "TC_PRECONDITION_STEP_INCONSISTENT", f"步骤引用的业务数据/对象未在前置条件中说明：{', '.join(missing_terms)}", case_location)

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
        if not directory or not self._validate_directory_format(directory):
            result.add_error(
                "TC_DIRECTORY_INVALID",
                f"用例目录不能为空且必须匹配知识库导航层级：{directory or '<空>'}",
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

            # 审核阶段必须使用严格模式；宽容模式只适合交互式提示，不能作为交付门禁。
            valid, msg = validate_directory(directory, strict=True)
            if not valid:
                print(f"  [目录校验] {msg}")
            return valid
        except ImportError:
            # 降级：基本格式检查
            parts = directory.split(" - ")
            if len(parts) != 3:
                return False
            return all(p.strip() for p in parts)

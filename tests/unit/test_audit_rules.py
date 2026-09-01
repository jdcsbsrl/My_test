"""测试审核规则管理器"""

import time


class TestRuleManager:
    def test_default_rules_exist(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rules = RuleManager.default_field_value_rules()
        assert "用例状态" in rules
        assert "用例等级" in rules
        assert "优先级" in rules
        assert "用例类型" in rules
        assert "是否可自动化" in rules
        assert "回归测试标识" in rules
        assert "创建人" in rules

    def test_default_sensitive_patterns(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        patterns = RuleManager.default_sensitive_patterns()
        assert len(patterns) >= 7
        pattern_types = [p[1] for p in patterns]
        assert "password" in pattern_types
        assert "token" in pattern_types
        assert "api_key" in pattern_types

    def test_validate_field_value_valid(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager()
        valid, msg = rm.validate_field_value("用例状态", "正常")
        assert valid is True

    def test_validate_field_value_invalid(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager()
        valid, msg = rm.validate_field_value("用例状态", "草稿")
        assert valid is False
        assert "只能" in msg

    def test_validate_unknown_field(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager()
        valid, msg = rm.validate_field_value("不存在的字段", "值")
        assert valid is True  # 未知字段默认通过

    def test_get_field_valid_values(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager()
        values = rm.get_field_valid_values("用例等级")
        assert values == ["高", "中", "低"]

    def test_score_test_case(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager()
        case = {
            "用例名称": "测试",
            "用例步骤": "步骤1\n步骤2\n步骤3",
            "预期结果": "结果1\n结果2",
        }
        score = rm.score_test_case(case)
        assert 0 <= score <= 100

    def test_cache_ttl(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager(cache_ttl=1)
        # 第一次调用会加载
        v1 = rm.get_field_valid_values("用例状态")
        # 第二次应使用缓存
        v2 = rm.get_field_valid_values("用例状态")
        assert v1 == v2
        time.sleep(1.1)
        # 缓存过期后刷新
        v3 = rm.get_field_valid_values("用例状态")
        assert v3 == ["正常"]

    def test_refresh_clears_cache(self):
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager()
        rm.get_field_valid_values("用例状态")
        rm.refresh()
        assert rm._cache == {}
        assert rm._cache_timestamps == {}

    def test_cache_cleanup(self):
        """测试过期缓存自动清理"""
        from modules.trae_test.orchestrator.audit_rules import RuleManager

        rm = RuleManager(cache_ttl=1)
        rm._cache["test_key"] = "test_value"
        rm._cache_timestamps["test_key"] = time.time() - 2

        rm._is_cache_valid("test_key")

        assert "test_key" not in rm._cache
        assert "test_key" not in rm._cache_timestamps


class TestCaseBusinessContentAudit:
    @staticmethod
    def _case(**overrides):
        case = {
            "用例目录": "测试用例/销售",
            "用例名称": "创建销售订单",
            "需求ID": "REQ-1",
            "前置条件": "1. 使用具有订单创建权限的账号登录系统\n2. 系统中存在测试客户和测试商品",
            "用例步骤": "1. 点击“销售订单”菜单\n2. 点击“新建订单”按钮\n3. 在“客户名称”下拉框选择“测试客户A”\n4. 点击“提交”按钮",
            "预期结果": "1. 页面打开销售订单列表\n2. 系统提示订单创建成功并生成订单号\n3. 订单状态显示为待支付",
        }
        case.update(overrides)
        return case

    def test_business_ready_content_passes(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit([self._case()])
        codes = {issue.rule_id for issue in result.issues}
        assert "TC_STEP_PAGE_OBJECT_REQUIRED" not in codes
        assert "TC_EXPECTED_OBSERVABLE_REQUIRED" not in codes

    def test_requires_pointwise_minimums(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit([self._case(前置条件="已登录", 用例步骤="进入页面", 预期结果="成功")])
        codes = {issue.rule_id for issue in result.issues if issue.severity == "error"}
        assert {"TC_PRECONDITIONS_MIN_COUNT", "TC_STEPS_MIN_COUNT", "TC_EXPECTED_MIN_COUNT"} <= codes

    def test_rejects_rough_steps_and_unobservable_results(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit(
            [self._case(用例步骤="1. 执行相关操作\n2. 检查结果\n3. 进入相关页面", 预期结果="1. 符合预期\n2. 页面正常")]
        )
        codes = {issue.rule_id for issue in result.issues if issue.severity == "error"}
        assert "TC_STEP_VAGUE" in codes
        assert "TC_EXPECTED_VAGUE" in codes
        assert result.passed is False

    def test_requires_page_object_action_and_data(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit([self._case(用例步骤="1. 打开页面\n2. 输入客户\n3. 提交")])
        codes = {issue.rule_id for issue in result.issues if issue.severity == "error"}
        assert "TC_STEP_PAGE_OBJECT_REQUIRED" in codes
        assert "TC_STEP_DATA_REQUIRED" in codes


class TestRequirementCoverageAudit:
    @staticmethod
    def _case(rule_id="R1", priority="P0", scenario="正常", **overrides):
        case = {
            "用例目录": "测试用例/销售",
            "用例名称": f"覆盖{rule_id}",
            "需求ID": "REQ-1",
            "前置条件": "1. 使用有权限账号登录销售系统\n2. 系统已准备测试客户和测试商品",
            "用例步骤": "1. 点击“销售订单”菜单\n2. 点击“新建订单”按钮\n3. 在“客户名称”下拉框选择“测试客户A”",
            "预期结果": "1. 页面打开销售订单页面\n2. 系统提示订单创建成功并生成订单号",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "高",
            "创建人": "余小龙",
            "优先级": priority,
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "销售订单规则",
            "质量评分": 90,
            "覆盖规则ID": rule_id,
            "场景类型": scenario,
        }
        case.update(overrides)
        return case

    @staticmethod
    def _codes(result):
        return {issue.rule_id for issue in result.issues if issue.severity == "error"}

    def test_p0_and_p1_rules_are_checked_for_coverage(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        cases = [self._case("R0", priority="P2"), self._case("R1", priority="P1")]
        result = TestCaseAuditor().audit(
            cases,
            context={
                "coverage_matrix": [
                    {"id": "R0", "priority": "P0", "required_scenarios": ["正常"]},
                    {"id": "R1", "priority": "P1", "required_scenarios": ["正常"]},
                ],
                "coverage_threshold": 1.0,
            },
        )
        assert "REQ_COVERAGE_INCOMPLETE" not in self._codes(result)
        assert "REQ_COVERAGE_BELOW_THRESHOLD" not in self._codes(result)

    def test_missing_rule_and_scenario_block_coverage(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit(
            [self._case("R0", scenario="正常")],
            context={
                "coverage_matrix": [
                    {"id": "R0", "priority": "P0", "required_scenarios": ["正常", "异常"]},
                    {"id": "R1", "priority": "P1", "required_scenarios": ["正常"]},
                ],
                "coverage_threshold": 1.0,
            },
        )
        codes = self._codes(result)
        assert "REQ_P0_SCENARIO_MISSING" in codes
        assert "REQ_COVERAGE_INCOMPLETE" in codes
        assert "REQ_COVERAGE_BELOW_THRESHOLD" in codes

    def test_rollback_and_excluded_scope_are_blocking(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit(
            [self._case("R1", 知识库关联="销售订单；WMS")],
            context={
                "coverage_matrix": [{"id": "R1", "priority": "P1", "required_scenarios": ["正常"]}],
                "requires_rollback": True,
                "excluded_scope": ["WMS"],
            },
        )
        codes = self._codes(result)
        assert "REQ_ROLLBACK_SCENARIO_MISSING" in codes
        assert "REQ_SCOPE_BOUNDARY_VIOLATION" in codes

    def test_invalid_coverage_matrix_is_blocking(self):
        from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

        result = TestCaseAuditor().audit(
            [self._case()],
            context={"coverage_matrix": ["R1", {"priority": "P1"}]},
        )
        assert "REQ_COVERAGE_MATRIX_INVALID" in self._codes(result)

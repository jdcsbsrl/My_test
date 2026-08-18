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
        assert "必须" in msg

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

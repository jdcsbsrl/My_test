from modules.trae_test.utils.business_rule_extractor import BusinessRuleExtractor


class TestBusinessRuleExtractor:

    def test_initialization(self):
        extractor = BusinessRuleExtractor()
        assert extractor is not None

    def test_extract_rules_from_dict(self):
        extractor = BusinessRuleExtractor()
        content = {"business_rules": [{"rule_id": "R001", "rule": "规则1"}, {"rule_id": "R002", "rule": "规则2"}]}

        rules = extractor.extract_rules(content)
        assert isinstance(rules, list)
        assert len(rules) == 2
        assert rules[0]["rule_id"] == "R001"

    def test_extract_rules_from_nested_dict(self):
        extractor = BusinessRuleExtractor()
        content = {"data": {"nested": {"rules": [{"rule": "嵌套规则"}]}}}

        rules = extractor.extract_rules(content)
        assert isinstance(rules, list)
        assert len(rules) == 1

    def test_extract_rules_no_rules(self):
        extractor = BusinessRuleExtractor()
        content = {"data": "no rules here"}

        rules = extractor.extract_rules(content)
        assert isinstance(rules, list)
        assert len(rules) == 0

    def test_match_keyword_in_rule_string(self):
        extractor = BusinessRuleExtractor()

        assert extractor.match_keyword_in_rule("包含关键词的规则", "关键词") is True
        assert extractor.match_keyword_in_rule("不包含的规则", "关键词") is False

    def test_match_keyword_in_rule_dict(self):
        extractor = BusinessRuleExtractor()
        rule = {"rule": "规则内容", "description": "包含关键词的描述", "name": "规则名称"}

        assert extractor.match_keyword_in_rule(rule, "关键词") is True
        assert extractor.match_keyword_in_rule(rule, "不存在") is False

    def test_match_keyword_in_rule_list(self):
        extractor = BusinessRuleExtractor()
        rule = [{"rule": "规则1"}, {"rule": "包含关键词的规则"}]

        assert extractor.match_keyword_in_rule(rule, "关键词") is True

    def test_match_keyword_empty(self):
        extractor = BusinessRuleExtractor()

        assert extractor.match_keyword_in_rule("任何内容", "") is True

    def test_search_rules_in_content(self):
        extractor = BusinessRuleExtractor()
        content = {
            "business_rules": [
                {"rule": "销售规则", "description": "销售相关"},
                {"rule": "采购规则", "description": "采购相关"},
            ]
        }

        results = extractor.search_rules_in_content(content, "销售")
        assert len(results) == 1
        assert results[0]["rule"] == "销售规则"

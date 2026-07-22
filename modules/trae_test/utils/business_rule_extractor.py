"""知识库业务规则提取器"""

from typing import Any


class BusinessRuleExtractor:
    """业务规则提取器 - 从文件内容中智能提取和搜索业务规则"""

    def __init__(self):
        self.rule_field_names = [
            "business_rules",
            "rules",
            "validations",
            "validation_rules",
            "business_rules_list",
            "rules_list",
            "rule_items",
        ]

    def extract_rules(self, content: dict[str, Any]) -> list[Any]:
        """从文件内容中智能提取业务规则

        Args:
            content: 文件内容（JSON结构）

        Returns:
            规则列表
        """
        rules = []

        def search_rules(data, path=""):
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    if key.lower() in [name.lower() for name in self.rule_field_names]:
                        if isinstance(value, list):
                            rules.extend(value)
                    elif isinstance(value, (dict, list)):
                        search_rules(value, current_path)
            elif isinstance(data, list):
                for item in data:
                    search_rules(item, path)

        search_rules(content)

        return rules

    def match_keyword_in_rule(self, rule: Any, keyword: str) -> bool:
        """检查规则中是否包含关键词

        Args:
            rule: 规则（字符串或字典）
            keyword: 搜索关键词

        Returns:
            是否匹配
        """
        if not keyword:
            return True

        keyword = keyword.lower()

        if isinstance(rule, str):
            return keyword in rule.lower()

        elif isinstance(rule, dict):
            fields_to_check = [
                "rule",
                "rule_id",
                "name",
                "title",
                "description",
                "condition",
                "action",
                "business_rule",
                "valid_rule",
            ]

            for field in fields_to_check:
                value = rule.get(field, "")
                if isinstance(value, str) and keyword in value.lower():
                    return True

            for value in rule.values():
                if isinstance(value, str) and keyword in value.lower():
                    return True
                elif isinstance(value, (dict, list)):
                    if self.match_keyword_in_rule(value, keyword):
                        return True

        elif isinstance(rule, list):
            for item in rule:
                if self.match_keyword_in_rule(item, keyword):
                    return True

        return False

    def search_rules_in_content(self, content: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
        """在文件内容中搜索匹配关键词的业务规则

        Args:
            content: 文件内容（JSON结构）
            keyword: 搜索关键词

        Returns:
            匹配的规则列表
        """
        rules = self.extract_rules(content)
        matched = []

        for rule in rules:
            if self.match_keyword_in_rule(rule, keyword):
                matched.append(rule)

        return matched

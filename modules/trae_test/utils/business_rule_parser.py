"""业务规则解析器 - 从结构化知识库中提取原始测试场景

核心功能：
- 解析 pages[].test_points → 正常流程场景
- 解析 pages[].business_rules → 验证场景
- 解析 core_constraints → 边界条件和异常场景
- 解析 batch_operations → 批量操作场景
- 解析全链路业务流程 → 端到端场景
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RawScenario:
    """原始测试场景 - 从知识库直接提取"""

    source: str
    module: str
    page_path: str
    test_point: str
    business_rule: str | None = None
    constraint: str | None = None
    operation: str | None = None
    parameters: dict[str, Any] | None = None
    scenario_type_hint: str | None = None


class BusinessRuleParser:
    """业务规则解析器

    从结构化知识库JSON中提取原始测试场景，为后续的场景分类和用例生成提供基础数据。
    """

    def __init__(self):
        self.scenarios: list[RawScenario] = []

    def parse_knowledge(self, knowledge: Any) -> list[RawScenario]:
        """解析知识库，提取原始测试场景

        Args:
            knowledge: 知识库内容（支持dict或list类型）

        Returns:
            原始测试场景列表
        """
        self.scenarios = []

        if isinstance(knowledge, list):
            self._parse_knowledge_list(knowledge)
        elif isinstance(knowledge, dict):
            self._parse_knowledge_dict(knowledge)

        return self.scenarios

    def _parse_knowledge_dict(self, knowledge: dict[str, Any]) -> None:
        """解析字典类型的知识库"""
        module = knowledge.get("module", knowledge.get("title", "未知模块"))
        if isinstance(module, str):
            module = module.split("模块")[0] if "模块" in module else module
        else:
            module = "未知模块"

        if "pages" in knowledge:
            for page in knowledge["pages"]:
                page_path = page.get("path", "")
                self._parse_page(page, module, page_path)

        if "core_constraints" in knowledge:
            self._parse_core_constraints(knowledge["core_constraints"], module)

        if "batch_operations" in knowledge:
            self._parse_batch_operations(knowledge["batch_operations"], module)

        if "forward_sales_flow" in knowledge:
            self._parse_forward_sales_flow(knowledge["forward_sales_flow"], module)

        if "reverse_return_flow" in knowledge:
            self._parse_reverse_return_flow(knowledge["reverse_return_flow"], module)

        if "refund_flow" in knowledge:
            self._parse_refund_flow(knowledge["refund_flow"], module)

        if "stages" in knowledge:
            self._parse_stages(knowledge["stages"], module)

        if "learned_requirements" in knowledge:
            self._parse_learned_requirements(knowledge["learned_requirements"], module)

    def _parse_knowledge_list(self, knowledge_list: list[dict[str, Any]]) -> None:
        """解析列表类型的知识库结果"""
        for item in knowledge_list:
            if not isinstance(item, dict):
                continue

            module = item.get("module", item.get("file_title", item.get("source_file", "未知模块")))
            if isinstance(module, str):
                module = module.split("模块")[0] if "模块" in module else module
            else:
                module = "未知模块"

            rule = item.get("rule", "")
            title = item.get("title", "")
            description = item.get("description", "")
            snippet = item.get("snippet", "")
            content = item.get("content", {})

            test_point = ""
            business_rule = ""

            if rule:
                test_point = rule
                business_rule = rule
            elif title:
                test_point = title
                business_rule = description if description else title
            elif snippet:
                test_point = snippet
                business_rule = snippet
            elif isinstance(content, dict):
                content_text = str(content)[:100]
                test_point = content_text
                business_rule = content_text

            if not test_point:
                continue

            scenario_type = self._infer_scenario_type_from_rule(test_point)

            page_path = item.get("file_title", "") or item.get("module", "")

            scenario = RawScenario(
                source="list_result",
                module=module,
                page_path=page_path,
                test_point=test_point,
                business_rule=business_rule,
                scenario_type_hint=scenario_type,
            )
            self.scenarios.append(scenario)

    def _parse_page(self, page: dict[str, Any], module: str, page_path: str) -> None:
        """解析页面数据"""
        if "test_points" in page:
            self._parse_test_points(page["test_points"], module, page_path, page.get("business_rules", []))

        if "business_rules" in page:
            self._parse_business_rules(page["business_rules"], module, page_path)

    def _parse_test_points(
        self, test_points: list[str], module: str, page_path: str, business_rules: list[str] = None
    ) -> None:
        """解析页面测试要点"""
        business_rules = business_rules or []
        for tp in test_points:
            rule_match = self._find_matching_rule(tp, business_rules)
            scenario = RawScenario(
                source="test_points",
                module=module,
                page_path=page_path,
                test_point=tp,
                business_rule=rule_match,
                scenario_type_hint="normal",
            )
            self.scenarios.append(scenario)

    def _parse_business_rules(self, business_rules: list[str], module: str, page_path: str) -> None:
        """解析业务规则"""
        for rule in business_rules:
            scenario_type = self._infer_scenario_type_from_rule(rule)
            scenario = RawScenario(
                source="business_rules",
                module=module,
                page_path=page_path,
                test_point=rule,
                business_rule=rule,
                scenario_type_hint=scenario_type,
            )
            self.scenarios.append(scenario)

    def _parse_core_constraints(self, constraints: list[dict[str, Any]], module: str) -> None:
        """解析核心约束条件"""
        for constraint in constraints:
            name = constraint.get("name", "")
            rule = constraint.get("rule", "")
            description = constraint.get("description", "")
            impact = constraint.get("impact", "")

            full_rule = f"{name}: {rule}"
            if description:
                full_rule += f" ({description})"

            scenario_normal = RawScenario(
                source="core_constraints",
                module=module,
                page_path=impact if impact else module,
                test_point=f"验证{name}正常流程",
                business_rule=full_rule,
                constraint=rule,
                scenario_type_hint="normal",
            )
            self.scenarios.append(scenario_normal)

            scenario_boundary = RawScenario(
                source="core_constraints",
                module=module,
                page_path=impact if impact else module,
                test_point=f"{name}边界条件验证",
                business_rule=full_rule,
                constraint=rule,
                scenario_type_hint="boundary",
            )
            self.scenarios.append(scenario_boundary)

            scenario_exception = RawScenario(
                source="core_constraints",
                module=module,
                page_path=impact if impact else module,
                test_point=f"{name}异常场景验证",
                business_rule=full_rule,
                constraint=rule,
                scenario_type_hint="exception",
            )
            self.scenarios.append(scenario_exception)

    def _parse_batch_operations(self, operations: dict[str, list[str]], module: str) -> None:
        """解析批量操作"""
        for status, ops in operations.items():
            for op in ops:
                if op == "不可批量处理":
                    continue
                scenario = RawScenario(
                    source="batch_operations",
                    module=module,
                    page_path=f"{module}-{status}",
                    test_point=f"{status}状态-{op}",
                    operation=op,
                    parameters={"status": status},
                    scenario_type_hint="normal",
                )
                self.scenarios.append(scenario)

    def _parse_forward_sales_flow(self, flow: dict[str, Any], module: str) -> None:
        """解析正向销售流程"""
        for step_key, step_data in flow.items():
            if isinstance(step_data, dict) and "core_operations" in step_data:
                for op in step_data["core_operations"]:
                    operation = op.get("operation", "")
                    path = op.get("path", "")
                    description = op.get("description", "")
                    scenario = RawScenario(
                        source="forward_sales_flow",
                        module=module,
                        page_path=path if path else module,
                        test_point=f"{step_data.get('name', '')}-{operation}",
                        business_rule=description,
                        operation=operation,
                        scenario_type_hint="normal",
                    )
                    self.scenarios.append(scenario)

    def _parse_reverse_return_flow(self, flow: dict[str, Any], module: str) -> None:
        """解析逆向退货流程"""
        steps = flow.get("steps", [])
        constraints = flow.get("constraints", [])
        prerequisite = flow.get("prerequisite", "")

        scenario = RawScenario(
            source="reverse_return_flow",
            module=module,
            page_path=f"{module}-销售退货单",
            test_point="退货退款全流程",
            business_rule=f"前置条件: {prerequisite}",
            parameters={"steps": steps, "constraints": constraints},
            scenario_type_hint="e2e",
        )
        self.scenarios.append(scenario)

    def _parse_refund_flow(self, flow: dict[str, Any], module: str) -> None:
        """解析退款流程"""
        steps = flow.get("steps", [])
        prerequisites = flow.get("prerequisites", [])

        scenario = RawScenario(
            source="refund_flow",
            module=module,
            page_path=f"{module}-客户退款",
            test_point="客户退款全流程",
            business_rule="; ".join(prerequisites),
            parameters={"steps": steps},
            scenario_type_hint="e2e",
        )
        self.scenarios.append(scenario)

    def _parse_stages(self, stages: list[dict[str, Any]], module: str) -> None:
        """解析全链路阶段"""
        for stage in stages:
            stage_name = stage.get("name", "")
            steps = stage.get("steps", [])
            verification = stage.get("verification", [])

            scenario = RawScenario(
                source="stages",
                module=module,
                page_path=f"全链路-{stage_name}",
                test_point=f"{stage_name}",
                business_rule="; ".join([v.get("module", "") + ": " + v.get("action", "") for v in steps]),
                parameters={"steps": steps, "verification": verification},
                scenario_type_hint="e2e",
            )
            self.scenarios.append(scenario)

    def _parse_learned_requirements(self, requirements: list[dict[str, Any]], module: str) -> None:
        """解析已学习需求"""
        for req in requirements:
            req_id = req.get("id", "")
            title = req.get("title", "")
            description = req.get("description", "")

            scenario = RawScenario(
                source="learned_requirements",
                module=module,
                page_path=f"{module}-需求{req_id}",
                test_point=title,
                business_rule=description,
                parameters={"req_id": req_id},
                scenario_type_hint="normal",
            )
            self.scenarios.append(scenario)

    def _find_matching_rule(self, test_point: str, business_rules: list[str]) -> str | None:
        """查找与测试要点匹配的业务规则"""
        for rule in business_rules:
            if any(keyword in test_point for keyword in ["物流交运", "SKU匹配", "标记发货", "转WMS", "退款"]):
                if keyword_match(test_point, rule):
                    return rule
        return None

    def _infer_scenario_type_from_rule(self, rule: str) -> str:
        """从规则描述推断场景类型"""
        if any(kw in rule for kw in ["必须", "仅", "不可", "不能", "禁止"]):
            return "boundary"
        if any(kw in rule for kw in ["失败", "异常", "错误", "提示"]):
            return "exception"
        return "normal"


def keyword_match(text1: str, text2: str) -> bool:
    """判断两个文本是否有关键词匹配"""
    keywords = ["物流交运", "SKU匹配", "标记发货", "转WMS", "退款", "订单", "审核", "配货", "发货"]
    for kw in keywords:
        if kw in text1 and kw in text2:
            return True
    return False


DEFAULT_PARSER = BusinessRuleParser()


def parse_knowledge(knowledge: dict[str, Any]) -> list[RawScenario]:
    """便捷函数：解析知识库"""
    return DEFAULT_PARSER.parse_knowledge(knowledge)

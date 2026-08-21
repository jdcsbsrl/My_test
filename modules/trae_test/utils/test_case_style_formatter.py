"""测试用例样式格式化器 - 格式化为15字段标准用例

核心功能：
- 使用 user_style_learning 样式规范
- 生成量化的预期结果
- 生成符合规范的用例步骤
- 输出标准15字段测试用例
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .template_builder import ALL_FIELDS
from .test_case_strategy import TestCaseScenario

logger = logging.getLogger(__name__)


class TestCaseStyleFormatter:
    """测试用例样式格式化器

    根据知识库中的 user_style_learning 样式规范，将测试场景格式化为15字段标准用例。
    """

    ALL_FIELDS = ALL_FIELDS  # 单一定义源：template_builder.ALL_FIELDS

    CASE_TYPE_MAP = {"normal": "功能测试", "boundary": "功能测试", "exception": "功能测试", "e2e": "集成测试"}

    REGRESSION_MAP = {"高": "冒烟测试", "中": "全量回归", "低": "不回归"}

    def __init__(self):
        pass

    def format(self, scenario: TestCaseScenario) -> dict[str, Any]:
        """格式化为15字段测试用例

        Args:
            scenario: 测试场景

        Returns:
            15字段标准测试用例

        Raises:
            TypeError: scenario 不是 TestCaseScenario 实例时抛出
        """
        if not isinstance(scenario, TestCaseScenario):
            raise TypeError(f"Expected TestCaseScenario instance, got {type(scenario).__name__}")

        case = {}

        case["用例目录"] = self._format_case_directory(scenario)
        case["用例名称"] = self._format_case_name(scenario)
        case["需求ID"] = self._format_requirement_id(scenario)
        case["前置条件"] = self._format_preconditions(scenario)
        case["用例步骤"] = self._format_steps(scenario)
        case["预期结果"] = self._format_expected_results(scenario)
        case["用例类型"] = self._format_case_type(scenario)
        case["用例状态"] = "正常"
        case["用例等级"] = scenario.case_level
        case["创建人"] = "余小龙"
        case["优先级"] = scenario.priority
        case["是否可自动化"] = scenario.automation_flag
        case["回归测试标识"] = self._format_regression_flag(scenario)
        case["知识库关联"] = self._format_knowledge_association(scenario)
        case["质量评分"] = 0.0

        logger.debug("格式化完成: %s", case.get("用例名称", "未命名"))
        return case

    def format_batch(self, scenarios: list[TestCaseScenario]) -> list[dict[str, Any]]:
        """批量格式化测试用例

        Args:
            scenarios: 测试场景列表

        Returns:
            15字段标准测试用例列表（跳过无效项并记录警告）
        """
        if not scenarios:
            logger.warning("format_batch 收到空列表")
            return []

        result = []
        for i, scenario in enumerate(scenarios):
            if not isinstance(scenario, TestCaseScenario):
                logger.warning("第 %d 项不是 TestCaseScenario 实例 (type=%s)，已跳过", i, type(scenario).__name__)
                continue
            try:
                result.append(self.format(scenario))
            except Exception as e:
                logger.error("格式化第 %d 项失败: %s", i, e)

        logger.info("批量格式化完成: %d/%d 成功", len(result), len(scenarios))
        return result

    def _format_case_directory(self, scenario: TestCaseScenario) -> str:
        """格式化用例目录"""
        path = scenario.page_path
        if "→" in path:
            return path.replace("→", " - ")
        if "/" in path:
            return path.replace("/", " - ")
        if path and scenario.module and scenario.module not in path:
            return f"{scenario.module} - {path}"
        return path or ""

    def _format_case_name(self, scenario: TestCaseScenario) -> str:
        """格式化用例名称"""
        name = scenario.case_name
        if len(name) > 50:
            name = name[:50]
        return name

    def _format_requirement_id(self, scenario: TestCaseScenario) -> str:
        """从业务规则中精确提取需求ID

        优先匹配 r'需求[：:]?\\s*(\\d+)' 格式，避免将规则中所有数字拼凑在一起。
        """
        for rule in scenario.business_rules:
            match = re.search(r"需求[：:]?\s*(\d+)", rule)
            if match:
                req_id = match.group(1)[:10]
                logger.debug("提取到需求ID: %s", req_id)
                return req_id
        return ""

    def _format_preconditions(self, scenario: TestCaseScenario) -> str:
        """格式化前置条件"""
        if not scenario.preconditions:
            return ""

        lines = []
        for i, precondition in enumerate(scenario.preconditions, 1):
            if i == 1:
                lines.append(f"{i}. {precondition}")
            else:
                lines.append(f"  {i}. {precondition}")

        return "\n".join(lines)

    def _format_steps(self, scenario: TestCaseScenario) -> str:
        """格式化用例步骤"""
        if not scenario.steps:
            return ""

        lines = []
        for i, step in enumerate(scenario.steps, 1):
            if i == 1:
                lines.append(f"{i}. {step}")
            else:
                lines.append(f"  {i}. {step}")

        return "\n".join(lines)

    def _format_expected_results(self, scenario: TestCaseScenario) -> str:
        """格式化预期结果（量化）"""
        if not scenario.expected_results:
            return ""

        lines = []
        for i, result in enumerate(scenario.expected_results, 1):
            if i == 1:
                lines.append(f"{i}. {result}")
            else:
                lines.append(f"  {i}. {result}")

        return "\n".join(lines)

    def _format_case_type(self, scenario: TestCaseScenario) -> str:
        """格式化用例类型"""
        return self.CASE_TYPE_MAP.get(scenario.scenario_type, "功能测试")

    def _format_regression_flag(self, scenario: TestCaseScenario) -> str:
        """格式化回归测试标识"""
        return self.REGRESSION_MAP.get(scenario.case_level, "全量回归")

    def _format_knowledge_association(self, scenario: TestCaseScenario) -> str:
        """格式化知识库关联"""
        if scenario.business_rules:
            return (
                scenario.business_rules[0][:30] if len(scenario.business_rules[0]) > 30 else scenario.business_rules[0]
            )
        return scenario.module


DEFAULT_FORMATTER = TestCaseStyleFormatter()


def format_case(scenario: TestCaseScenario) -> dict[str, Any]:
    """便捷函数：格式化单个测试用例"""
    return DEFAULT_FORMATTER.format(scenario)


def format_cases(scenarios: list[TestCaseScenario]) -> list[dict[str, Any]]:
    """便捷函数：批量格式化测试用例"""
    return DEFAULT_FORMATTER.format_batch(scenarios)

"""测试用例生成器 - 15字段标准格式生成

核心功能：
- 从知识库检索业务规则和需求
- 自动生成符合规范的测试用例
- 支持15字段标准输出格式
- 与ExcelGenerator协同工作
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from .dir_validator import _load_module_hierarchy
from .excel_generator import ExcelGenerator
from .knowledge_retriever import KnowledgeRetriever
from .template_builder import ensure_template
from .test_case_strategy import TestCaseStrategy

logger = logging.getLogger(__name__)


class TestCaseGenerator:
    """测试用例生成器

    负责根据知识库内容生成标准化的测试用例，确保输出符合15字段规范。
    """

    def __init__(self, retriever: KnowledgeRetriever | None = None):
        """初始化测试用例生成器

        Args:
            retriever: 知识检索器实例，若为None则自动创建
        """
        self.retriever = retriever or KnowledgeRetriever()
        self.excel_generator = ExcelGenerator()

    def generate_cases(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """根据关键词从知识库生成测试用例

        Args:
            keyword: 检索关键词
            limit: 返回用例数量限制（1~200）

        Returns:
            测试用例列表，每个用例包含15个标准字段

        Raises:
            ValueError: 参数校验不通过时
        """
        # ── 输入验证 ─────────────────────────────────────────
        if not keyword or not keyword.strip():
            raise ValueError("检索关键词不能为空")
        if limit < 1 or limit > 200:
            raise ValueError(f"limit 必须在 1~200 之间，收到: {limit}")
        keyword = keyword.strip()
        # ──────────────────────────────────────────────────────

        knowledge = self.retriever.retrieve(keyword)
        if not knowledge:
            return []

        # ── 历史用例学习 ─────────────────────────────────────
        try:
            historical_cases = self.retriever.search_historical_cases(keyword, top_k=3)
            if not isinstance(historical_cases, list):
                historical_cases = None
        except Exception:
            historical_cases = None
        # ──────────────────────────────────────────────────────

        cases = []

        if isinstance(knowledge, dict):
            for key, value in list(knowledge.items())[:limit]:
                case = self._build_case_from_knowledge(keyword, key, value, historical_cases)
                cases.append(case)
        elif isinstance(knowledge, list):
            for item in knowledge[:limit]:
                case = self._build_case_from_knowledge(keyword, str(item.get("id", len(cases))), item, historical_cases)
                cases.append(case)

        return cases

    @staticmethod
    def _infer_scenario_type(keyword: str, knowledge_str: str) -> str:
        """从关键词和知识内容推断场景类型"""
        text = f"{keyword} {knowledge_str}"
        if any(kw in text for kw in ("必须", "仅", "不可", "不能", "禁止", "边界")):
            return "boundary"
        if any(kw in text for kw in ("失败", "异常", "错误", "报错", "无效")):
            return "exception"
        return "normal"

    def _build_case_from_knowledge(
        self, keyword: str, case_id: str, knowledge: Any, historical_cases: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """从知识条目构建测试用例

        Args:
            keyword: 检索关键词
            case_id: 用例标识
            knowledge: 知识条目内容
            historical_cases: 历史相似用例列表（可选），用于学习优化

        Returns:
            完整的15字段测试用例
        """
        knowledge_str = str(knowledge) if not isinstance(knowledge, str) else knowledge

        hierarchy = _load_module_hierarchy()
        case_directory = ""
        for top, second_map in hierarchy.items():
            if keyword == top or top in keyword or keyword in top:
                second_keys = list(second_map.keys())
                if second_keys:
                    third_list = second_map.get(second_keys[0], [])
                    if third_list:
                        case_directory = f"{top} - {second_keys[0]} - {third_list[0]}"
                break

        # ── 场景类型推断 ─────────────────────────────────────
        scenario_type = self._infer_scenario_type(keyword, knowledge_str)
        # ──────────────────────────────────────────────────────

        # ── 优先级计算 ───────────────────────────────────────
        priority_p = TestCaseStrategy.determine_priority_simple(
            test_point=keyword,
            business_rule=knowledge_str[:TestCaseStrategy._CASE_NAME_MAX_LENGTH],
            constraint="",
            scenario_type=scenario_type,
        )
        priority_map = {"P0": "高", "P1": "高", "P2": "中", "P3": "中"}
        priority = priority_map.get(priority_p, "中")
        # ──────────────────────────────────────────────────────

        # ── 步骤与预期结果智能生成 ────────────────────────────
        steps_str, expected_str = TestCaseStrategy.generate_case_content(
            test_point=keyword,
            business_rule=knowledge_str[:TestCaseStrategy._BUSINESS_RULE_CONTENT_LENGTH],
            scenario_type=scenario_type,
        )
        # ──────────────────────────────────────────────────────

        # ── 历史用例学习：若匹配到相似用例，取其高频模式 ────
        if historical_cases:
            # 提取历史用例中出现的步骤关键词，用于丰富步骤描述
            historical_step_keywords: set = set()
            for hc in historical_cases:
                for line in hc.get("steps", "").split("\n"):
                    line = line.strip()
                    # 跳过纯编号行和空行
                    if line and not line.startswith("验证") and len(line) > 4:
                        historical_step_keywords.add(line)
            # 如果历史步骤中存在策略未覆盖的有意义描述，追加到步骤末尾
            current_steps = set(
                line.strip().lstrip("0123456789. ").strip() for line in steps_str.split("\n") if line.strip()
            )
            extra_steps = [s for s in historical_step_keywords if s.strip() not in current_steps and len(s) >= 4]
            if extra_steps:
                steps_str += "\n" + "\n".join(
                    f"{steps_str.count(chr(10)) + i + 2}. {s}" for i, s in enumerate(extra_steps[:2])
                )
        # ──────────────────────────────────────────────────────

        return {
            "用例目录": case_directory,
            "用例名称": f"测试_{keyword}_{case_id}",
            "需求ID": "",
            "前置条件": "系统已正常启动，用户已登录",
            "用例步骤": steps_str,
            "预期结果": expected_str,
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": priority_p,
            "创建人": "余小龙",
            "优先级": priority,
            "是否可自动化": "是",
            "关联缺陷ID": "",
            "回归测试标识": "否",
            "知识库关联": keyword,
        }

    def export_to_excel(self, cases: list[dict[str, Any]], output_path: str | None = None, extra_fields: list[str] | None = None) -> str:
        """导出测试用例到Excel文件

        Args:
            cases: 测试用例列表
            output_path: 输出路径，若为None则使用默认路径
            extra_fields: 额外导出字段列表（可选），如 ["状态", "regeneration_count"]

        Returns:
            导出文件的路径
        """
        ensure_template()

        return self.excel_generator.generate(cases, output_path, extra_fields=extra_fields)

    def generate_and_export(self, keyword: str, limit: int = 10, output_path: str | None = None, extra_fields: list[str] | None = None) -> str:
        """生成测试用例并导出到Excel（包含评分和审核）

        Args:
            keyword: 检索关键词
            limit: 返回用例数量限制
            output_path: 输出路径
            extra_fields: 额外导出字段列表（可选）

        Returns:
            导出文件的路径
        """
        from modules.trae_test.utils.test_case_strategy import TestCaseScoreEngine
        from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent

        cases = self.generate_cases(keyword, limit)

        score_engine = TestCaseScoreEngine()
        for case in cases:
            case["质量评分"] = score_engine.score(case)

        agent = AuditAgent()
        audit_result = agent.audit_test_cases(cases)
        if not audit_result.passed:
            logger.warning(f"测试用例审核未通过: {audit_result.errors}")

        return self.export_to_excel(cases, output_path, extra_fields=extra_fields)


DEFAULT_CREATOR = TestCaseGenerator()


def generate_cases(keyword: str, limit: int = 10) -> list[dict[str, Any]]:
    """便捷函数：生成测试用例

    Args:
        keyword: 检索关键词
        limit: 返回用例数量限制

    Returns:
        测试用例列表
    """
    return DEFAULT_CREATOR.generate_cases(keyword, limit)

"""测试用例生成器 - 15字段标准格式生成

核心功能：
- 从知识库检索业务规则和需求
- 自动生成符合规范的测试用例
- 支持15字段标准输出格式
- 与ExcelGenerator协同工作
"""

from __future__ import annotations

import logging
from typing import Any

from .dir_validator import _load_module_hierarchy
from .excel_generator import ExcelGenerator
from .knowledge_retriever import KnowledgeRetriever
from .template_builder import ensure_template
from .test_case_strategy import TestCaseOptimizer, TestCaseScoreEngine, TestCaseStrategy
from .coverage_matrix import CoverageMatrix, build_requirement_coverage_matrix


QUALITY_SCORE_GATE = 85.0
MAX_AUTO_OPTIMIZATION_ATTEMPTS = 3

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
        # 需求级覆盖矩阵只保存在运行时，不改变每条用例的15字段结构。
        self.last_coverage_matrix = CoverageMatrix()

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

        knowledge = self.retriever.retrieve(keyword, mode="hybrid")
        if not knowledge:
            knowledge = self.retriever.retrieve(keyword)
        if not knowledge:
            self.last_coverage_matrix = CoverageMatrix()
            return []

        self.last_coverage_matrix = build_requirement_coverage_matrix(keyword, knowledge)

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

    def get_coverage_matrix(self) -> dict[str, list[str]]:
        """返回最近一次生成任务的需求级覆盖矩阵快照。"""
        return self.last_coverage_matrix.to_dict()

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
        case_directory = self._match_case_directory(keyword, hierarchy)

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
        case_level_map = {"P0": "高", "P1": "高", "P2": "中", "P3": "中"}
        case_level = case_level_map.get(priority_p, "中")
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
            "用例等级": case_level,
            "创建人": "余小龙",
            "优先级": priority_p,
            "是否可自动化": "是",
            "回归测试标识": "否",
            "知识库关联": f"{keyword}\n{knowledge_str[:8000]}",
            "质量评分": 0.0,
        }

    @staticmethod
    def _derive_coverage_matrix(keyword: str, knowledge: str, scenario_type: str) -> dict[str, str]:
        text = f"{keyword} {knowledge}"
        dimensions = {"场景类型": scenario_type}
        groups = {
            "单对象": ("单个", "单条", "单sku", "单 SKU"),
            "多对象": ("多个", "批量", "多sku", "多 SKU"),
            "多仓库": ("多仓", "多个仓库", "按仓库"),
            "多明细": ("多明细", "多个明细", "部分明细", "明细"),
            "状态": ("状态", "处理中", "待", "已发货", "未发货"),
            "失败": ("失败", "异常", "错误", "回滚", "拦截"),
        }
        for dimension, keywords in groups.items():
            if any(value.lower() in text.lower() for value in keywords):
                dimensions[dimension] = "已识别"
        return dimensions

    @staticmethod
    def _match_case_directory(keyword: str, hierarchy: dict[str, dict[str, list[str]]]) -> str:
        """根据关键词从导航层级反向匹配最具体的合法目录。

        需求通常只包含三级菜单名（如“库存SKU”），不能要求用户同时输入一级、
        二级模块名；因此优先按三级菜单命中，再回退到二级、一级匹配。
        """
        normalized = "".join(str(keyword or "").lower().split())
        candidates: list[tuple[int, str]] = []
        for top, second_map in hierarchy.items():
            top_norm = "".join(top.lower().split())
            if top_norm and top_norm in normalized:
                candidates.append((1, f"{top} - {next(iter(second_map), '')} - {next(iter(second_map.values()), [''])[0]}"))
            for second, thirds in (second_map or {}).items():
                second_norm = "".join(second.lower().split())
                if second_norm and second_norm in normalized:
                    for third in thirds or []:
                        candidates.append((2, f"{top} - {second} - {third}"))
                for third in thirds or []:
                    third_norm = "".join(str(third).lower().split())
                    if third_norm and third_norm in normalized:
                        candidates.append((3, f"{top} - {second} - {third}"))
        if candidates:
            return max(candidates, key=lambda item: (item[0], len(item[1])))[1]
        return ""

    def export_to_excel(
        self,
        cases: list[dict[str, Any]],
        output_path: str | None = None,
        extra_fields: list[str] | None = None,
    ) -> str:
        """导出测试用例到Excel文件

        Args:
            cases: 测试用例列表
            output_path: 输出路径，若为None则使用默认路径
            extra_fields: 已废弃；正式Excel固定为15字段

        Returns:
            导出文件的路径
        """
        ensure_template()

        # 导出是最终交付动作，禁止绕过评分和最终审核门禁。
        not_ready = [
            case.get("用例名称", "未命名用例")
            for case in cases
            if case.get("最终审核通过") is not True
            or float(case.get("最终评分", case.get("质量评分", 0)) or 0) < QUALITY_SCORE_GATE
            or case.get("用例状态") != "正常"
        ]
        if not_ready:
            raise RuntimeError(
                f"最终审核未通过，禁止导出 {len(not_ready)} 条用例；"
                f"评分门槛为{QUALITY_SCORE_GATE:g}分"
            )

        return self.excel_generator.generate(cases, output_path, extra_fields=extra_fields)

    def generate_and_export(
        self,
        keyword: str,
        limit: int = 10,
        output_path: str | None = None,
        extra_fields: list[str] | None = None,
        block_on_audit_fail: bool = True,
    ) -> str:
        """生成测试用例并导出到Excel（包含评分和审核）

        Args:
            keyword: 检索关键词
            limit: 返回用例数量限制
            output_path: 输出路径
            extra_fields: 额外导出字段列表（可选）
            block_on_audit_fail: 保留兼容参数；当前最终审核未通过时始终阻断导出

        Returns:
            导出文件的路径
        """
        from modules.trae_test.orchestrator.audit_gateway import AuditGateway
        cases = self.generate_cases(keyword, limit)
        score_engine = TestCaseScoreEngine()
        optimizer = TestCaseOptimizer(score_engine)
        for case in cases:
            self._score_and_optimize(case, score_engine, optimizer)

        # 使用 AuditGateway 统一入口
        gateway = AuditGateway()
        context = {"block_on_fail": True}
        audit_result = gateway.audit(cases, "test_case", context)

        for case in cases:
            canonical_score = float(case.get("最终评分", case.get("质量评分", 0)) or 0)
            case["最终评分"] = canonical_score
            case["质量评分"] = canonical_score
            case["最终审核通过"] = bool(audit_result.passed) and canonical_score >= QUALITY_SCORE_GATE
            case["用例状态"] = "正常"
            case["needs_human_review"] = not case["最终审核通过"]

        if not audit_result.passed or any(not case["最终审核通过"] for case in cases):
            raise RuntimeError(f"审核未通过，导出已阻断：{len(audit_result.errors)}个错误")

        return self.export_to_excel(cases, output_path, extra_fields=extra_fields)

    @staticmethod
    def _score_and_optimize(
        case: dict[str, Any], score_engine: TestCaseScoreEngine, optimizer: TestCaseOptimizer
    ) -> dict[str, Any]:
        """记录不可覆盖的评分轨迹，并在低于85分时自动优化或退回人工。"""
        original = float(score_engine.score(case))
        case.setdefault("原始评分", original)
        execution_count = int(case.get("execution_count", 0) or 0)
        cold_start_threshold = int(getattr(score_engine, "_COLD_START_THRESHOLD", 10) or 10)
        case["是否冷启动评分"] = execution_count < cold_start_threshold
        case["评分置信度"] = round(float(score_engine._calculate_confidence(execution_count)), 4)
        case["评分历史"] = list(case.get("评分历史", []))
        case["评分历史"].append({"阶段": "original", "评分": original})
        current = original
        for attempt in range(1, MAX_AUTO_OPTIMIZATION_ATTEMPTS + 1):
            if current >= QUALITY_SCORE_GATE:
                break
            optimizer.optimize(case, target_score=QUALITY_SCORE_GATE)
            current = float(score_engine.score(case))
            case["评分历史"].append({"阶段": f"optimized_{attempt}", "评分": current})
        case["优化后评分"] = current
        case["最终评分"] = current
        case["质量评分"] = current
        case["优化次数"] = max(0, len(case["评分历史"]) - 1)
        case["用例状态"] = "正常"
        case["needs_human_review"] = current < QUALITY_SCORE_GATE
        case["最终审核通过"] = False
        return case


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

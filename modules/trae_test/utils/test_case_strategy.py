"""测试用例策略生成器 - 根据业务规则分类生成测试场景

核心功能：
- 场景分类：正常流程、边界条件、异常场景、全链路
- 优先级判定：P0/P1/P2
- 用例等级判定：高/中/低
- 生成完整的测试场景数据结构
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .business_rule_parser import RawScenario
from .runtime_quality import attach_runtime_quality, read_runtime_quality

logger = logging.getLogger(__name__)

_config_cache: dict | None = None

P0_KEYWORDS = ["系统无法登录", "核心业务流程完全阻断", "数据丢失", "安全漏洞", "全链路"]
P1_KEYWORDS = [
    "订单拉取",
    "SKU匹配",
    "物流交运",
    "标记发货",
    "客户账单",
    "采购补货",
    "采购入库",
    "客户应收",
    "余额付款",
    "到账核销",
    "SKU创建",
    "组合SKU",
    "报价配置",
    "核心功能",
    "高频使用",
    "财务金额",
    "多系统联动",
]
P2_KEYWORDS = ["排序", "筛选", "导出", "边界条件", "异常场景", "UI展示", "辅助功能", "低频使用"]
HIGH_LEVEL_KEYWORDS = P1_KEYWORDS + P0_KEYWORDS
MEDIUM_LEVEL_KEYWORDS = ["边界条件", "异常场景", "审核", "验证"]
LOW_LEVEL_KEYWORDS = ["展示", "显示", "查看"]


@dataclass
class TestCaseScenario:
    """测试场景 - 经过分类和策略处理"""

    scenario_type: str
    module: str
    page_path: str
    case_name: str
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    expected_results: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    priority: str = "P1"
    case_level: str = "高"
    automation_flag: str = "是"
    # 运行时覆盖信息，不进入正式15列Excel。
    coverage_dimensions: list[str] = field(default_factory=list)
    coverage_matrix: dict[str, str] = field(default_factory=dict)


class TestCaseStrategy:
    """测试用例策略生成器

    根据业务规则分类生成测试场景，包含场景分类、优先级判定、用例等级判定等功能。
    """

    P0_KEYWORDS = P0_KEYWORDS
    P1_KEYWORDS = P1_KEYWORDS
    P2_KEYWORDS = P2_KEYWORDS
    HIGH_LEVEL_KEYWORDS = HIGH_LEVEL_KEYWORDS
    MEDIUM_LEVEL_KEYWORDS = MEDIUM_LEVEL_KEYWORDS
    LOW_LEVEL_KEYWORDS = LOW_LEVEL_KEYWORDS

    # 魔法数字（可维护性）
    _CASE_NAME_MAX_LENGTH = 30
    _BUSINESS_RULE_CONTENT_LENGTH = 200
    _MAX_PRECONDITIONS_COUNT = 3
    _MAX_STEPS_COUNT = 8
    _UPGRADE_THRESHOLD_P1_TO_P0 = 3
    _UPGRADE_THRESHOLD_P2_TO_P1 = 2
    _PRECONDITIONS_UPGRADE_FACTOR = 2

    def __init__(self):
        self.scenarios: list[TestCaseScenario] = []
        self._load_keywords_from_config()

    @staticmethod
    def _get_config_path() -> str:
        """获取策略配置文件路径"""
        from pathlib import Path

        return str(Path(__file__).resolve().parents[3] / "configs" / "strategy_config.yaml")

    def _load_keywords_from_config(self):
        """从 YAML 配置文件加载关键词列表，加载失败时使用内置关键词

        使用模块级缓存，避免重复读取文件
        """
        global _config_cache

        try:
            import yaml
        except ImportError:
            logger.debug("PyYAML 未安装，使用内置关键词")
            return

        if _config_cache is not None:
            config = _config_cache
        else:
            config_path = self._get_config_path()
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                _config_cache = config
            except FileNotFoundError:
                logger.debug(f"配置文件不存在: {config_path}，使用内置关键词")
                return
            except Exception as e:
                logger.warning(f"加载策略配置失败: {e}，使用内置关键词")
                return

        kw = config.get("priority_keywords", {})
        if kw.get("P0"):
            self.P0_KEYWORDS = kw["P0"]
        if kw.get("P1"):
            self.P1_KEYWORDS = kw["P1"]
        if kw.get("P2"):
            self.P2_KEYWORDS = kw["P2"]
        if kw.get("case_level_high"):
            self.HIGH_LEVEL_KEYWORDS = kw["case_level_high"]
        if kw.get("case_level_medium"):
            self.MEDIUM_LEVEL_KEYWORDS = kw["case_level_medium"]
        if kw.get("case_level_low"):
            self.LOW_LEVEL_KEYWORDS = kw["case_level_low"]

        logger.debug("已从配置文件加载关键词")

    @classmethod
    def reload_config(cls) -> None:
        """重新加载配置文件（热更新）

        用于配置文件修改后无需重启即可生效
        """
        global _config_cache
        _config_cache = None
        # 创建新实例触发重新加载
        cls()._load_keywords_from_config()
        logger.info("策略配置已重新加载")

    def generate_scenarios(self, raw_scenarios: list[RawScenario], limit: int = 20) -> list[TestCaseScenario]:
        """生成测试场景

        Args:
            raw_scenarios: 原始测试场景列表
            limit: 返回场景数量限制

        Returns:
            测试场景列表
        """
        self.scenarios = []

        for raw in raw_scenarios:
            if len(self.scenarios) >= limit:
                break
            scenario_type = self._classify_scenario(raw)
            case_name = self._generate_case_name(raw, scenario_type)
            preconditions = self._generate_preconditions(raw)
            steps = self._generate_steps(raw, scenario_type)
            expected_results = self._generate_expected_results(raw, scenario_type)
            business_rules = self._extract_business_rules(raw)
            priority = self._determine_priority(raw, scenario_type)
            case_level = self._determine_case_level(raw, scenario_type)
            coverage_matrix = self._derive_coverage_matrix(raw, scenario_type)

            scenario = TestCaseScenario(
                scenario_type=scenario_type,
                module=raw.module,
                page_path=raw.page_path,
                case_name=case_name,
                preconditions=preconditions,
                steps=steps,
                expected_results=expected_results,
                business_rules=business_rules,
                priority=priority,
                case_level=case_level,
                automation_flag="是" if scenario_type != "e2e" else "否",
                coverage_dimensions=list(coverage_matrix),
                coverage_matrix=coverage_matrix,
            )
            self.scenarios.append(scenario)

        return self.scenarios

    @staticmethod
    def _derive_coverage_matrix(raw: RawScenario, scenario_type: str) -> dict[str, str]:
        """从场景文本登记覆盖维度。

        这是需求级覆盖矩阵的轻量入口：只登记需求文本明确出现的维度，
        不臆造业务规则；结果仅用于运行时追踪，不改变正式15列字段。
        """
        text = " ".join(
            str(value or "")
            for value in (raw.test_point, raw.business_rule, raw.constraint, raw.operation, raw.page_path)
        )
        dimensions: dict[str, str] = {"场景类型": scenario_type}
        keyword_groups = {
            "单对象": ("单个", "单条", "单sku", "单 SKU"),
            "多对象": ("多个", "批量", "多sku", "多 SKU"),
            "多仓库": ("多仓", "多个仓库", "按仓库"),
            "多明细": ("多明细", "多个明细", "部分明细", "明细"),
            "状态": ("状态", "处理中", "待", "已发货", "未发货"),
            "失败": ("失败", "异常", "错误", "回滚", "拦截"),
        }
        for dimension, keywords in keyword_groups.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                dimensions[dimension] = "已识别"
        return dimensions

    def _classify_scenario(self, raw: RawScenario) -> str:
        """分类场景类型"""
        if raw.scenario_type_hint:
            return raw.scenario_type_hint

        if raw.source == "stages":
            return "e2e"
        if raw.source == "reverse_return_flow":
            return "e2e"
        if raw.source == "refund_flow":
            return "e2e"

        if raw.source == "core_constraints":
            if "边界" in raw.test_point:
                return "boundary"
            if "异常" in raw.test_point:
                return "exception"
            return "normal"

        if any(kw in raw.test_point for kw in ["必须", "仅", "不可", "不能"]):
            return "boundary"

        if any(kw in raw.test_point for kw in ["失败", "异常", "错误"]):
            return "exception"

        return "normal"

    def _generate_case_name(self, raw: RawScenario, scenario_type: str) -> str:
        """生成用例名称"""
        type_suffix = {"normal": "正常流程", "boundary": "边界条件", "exception": "异常场景", "e2e": "全链路"}.get(
            scenario_type, ""
        )

        test_point_clean = raw.test_point[:self._CASE_NAME_MAX_LENGTH] if len(raw.test_point) > self._CASE_NAME_MAX_LENGTH else raw.test_point

        if raw.operation:
            return f"{raw.operation}-{test_point_clean}-{type_suffix}"

        return f"{test_point_clean}-{type_suffix}"

    def _generate_preconditions(self, raw: RawScenario) -> list[str]:
        """生成前置条件"""
        preconditions = []

        if raw.scenario_type_hint == "e2e":
            preconditions.append("系统已完成所有前置配置")
            preconditions.append("测试用户已登录系统")
            return preconditions

        if raw.page_path:
            preconditions.append(f"进入{raw.page_path}页面")

        if raw.business_rule:
            rule_lower = raw.business_rule.lower()
            if "登录" in raw.business_rule:
                preconditions.append("用户已登录系统")
            if "权限" in raw.business_rule:
                preconditions.append("用户拥有相关操作权限")
            if "状态" in raw.business_rule:
                preconditions.append("订单处于对应状态")
            if "已完成" in raw.business_rule:
                preconditions.append("相关前置操作已完成")

        if raw.constraint:
            preconditions.append(f"满足约束条件: {raw.constraint}")

        if not preconditions:
            preconditions.append("系统已正常启动，用户已登录")

        return preconditions[:self._MAX_PRECONDITIONS_COUNT]

    def _generate_steps(self, raw: RawScenario, scenario_type: str) -> list[str]:
        """生成用例步骤（不带编号，由格式化器统一添加）"""
        steps = []

        if scenario_type == "e2e":
            if raw.parameters and "steps" in raw.parameters:
                for step_info in raw.parameters["steps"]:
                    if isinstance(step_info, dict):
                        action = step_info.get("action", step_info.get("description", ""))
                        if action:
                            steps.append(action)
                    elif isinstance(step_info, str):
                        steps.append(step_info)
            if steps:
                steps.append("验证全流程结果")
            return steps[:self._MAX_STEPS_COUNT]

        if raw.test_point:
            tp = raw.test_point
            if "→" in tp:
                parts = tp.split("→")
                for part in parts:
                    part = part.strip()
                    if part:
                        if "勾选" in part or "选择" in part or "点击" in part:
                            steps.append(part)
                        else:
                            steps.append(f"执行{part}")
            else:
                steps.append("进入相关功能页面")
                action_keywords = ["操作", "处理", "验证", "设置", "创建", "编辑", "删除", "匹配"]
                for kw in action_keywords:
                    if kw in tp:
                        steps.append(f"执行{kw}操作")
                        break
                else:
                    steps.append(f"执行{tp}相关操作")
                steps.append("验证操作结果")

        if scenario_type == "boundary":
            steps.insert(-1, "在边界条件下执行操作")

        if scenario_type == "exception":
            steps.insert(-1, "在异常条件下执行操作")
            steps.append("验证系统异常处理")

        return steps

    def _generate_expected_results(self, raw: RawScenario, scenario_type: str) -> list[str]:
        """生成预期结果（量化）"""
        results = []

        if scenario_type == "e2e":
            if raw.parameters and "verification" in raw.parameters:
                for v in raw.parameters["verification"]:
                    if isinstance(v, str):
                        results.append(v)
                    elif isinstance(v, dict):
                        results.append(v.get("description", v.get("module", "") + "操作成功"))
            if not results:
                results.append("全流程执行成功")
            return results

        if raw.business_rule:
            rule = raw.business_rule
            rule_lower = rule.lower()

            if "成功" in rule or "完成" in rule:
                results.append("操作执行成功")

            if "状态" in rule:
                results.append("状态变更符合预期")

            if scenario_type == "normal":
                results.append(f"{raw.test_point}功能正常工作")
                if raw.business_rule:
                    results.append(f"符合业务规则: {rule[:30]}")

            elif scenario_type == "boundary":
                if raw.constraint:
                    results.append(f"边界条件下{raw.constraint}验证通过")
                results.append("系统在边界条件下正常响应")

            elif scenario_type == "exception":
                if raw.constraint:
                    results.append(f"违反{raw.constraint}时系统拒绝操作")
                results.append("系统弹出明确的错误提示")
                results.append("数据状态保持不变")

        if raw.operation:
            results.append(f"{raw.operation}操作完成")

        if not results:
            results.append("功能正常工作，符合业务规则")

        return results[:3]

    def _extract_business_rules(self, raw: RawScenario) -> list[str]:
        """提取业务规则"""
        rules = []
        if raw.business_rule:
            rules.append(raw.business_rule)
        if raw.constraint:
            rules.append(raw.constraint)
        return rules

    def _determine_priority(self, raw: RawScenario, scenario_type: str) -> str:
        """判定优先级（关键词匹配 + 复杂度因子升档）"""
        text = f"{raw.test_point} {raw.business_rule or ''} {raw.page_path}"

        if scenario_type == "e2e":
            return "P0"

        # ── 基础判定：关键词匹配 ─────────────────────────────
        base = "P1"
        for kw in self.P0_KEYWORDS:
            if kw in text:
                base = "P0"
                break
        if base == "P1":
            for kw in self.P1_KEYWORDS:
                if kw in text:
                    base = "P1"
                    break
            else:
                for kw in self.P2_KEYWORDS:
                    if kw in text:
                        base = "P2"
                        break
                else:
                    if scenario_type == "boundary" or scenario_type == "exception":
                        base = "P2"
                    else:
                        base = "P1"

        # ── 复杂度升档（仅在基础判定为 P1/P2 时生效） ────────
        if base in ("P1", "P2"):
            upgrade_score = 0
            # 因子1：约束条件数量（每个 +1）
            if raw.constraint:
                upgrade_score += 1
            # 因子2：前置条件数（>=2 时 +1）
            preconditions = self._generate_preconditions(raw)
            if len(preconditions) >= 2:
                upgrade_score += 1
            # 因子3：跨模块/全链路特征
            if raw.page_path and "跨模块" in raw.page_path:
                upgrade_score += 1
            if raw.module and "多模块" in raw.module:
                upgrade_score += 1
            # 因子4：业务规则含金额/核心字段
            if raw.business_rule and any(kw in raw.business_rule for kw in ("金额", "价格", "库存", "权限")):
                upgrade_score += 1

            # 升档逻辑：>=2 则 P2→P1, >=3 则 P1→P0
            if upgrade_score >= self._UPGRADE_THRESHOLD_P1_TO_P0 and base == "P1":
                return "P0"
            if upgrade_score >= self._UPGRADE_THRESHOLD_P2_TO_P1 and base == "P2":
                return "P1"

        return base

    def _determine_case_level(self, raw: RawScenario, scenario_type: str) -> str:
        """判定用例等级"""
        text = f"{raw.test_point} {raw.business_rule or ''}"

        for kw in self.HIGH_LEVEL_KEYWORDS:
            if kw in text:
                return "高"

        for kw in self.MEDIUM_LEVEL_KEYWORDS:
            if kw in text:
                return "中"

        for kw in self.LOW_LEVEL_KEYWORDS:
            if kw in text:
                return "低"

        if scenario_type == "e2e":
            return "高"

        priority_level_map = {"P0": "高", "P1": "高", "P2": "中"}
        return priority_level_map.get(self._determine_priority(raw, scenario_type), "中")

    @staticmethod
    def determine_priority_simple(
        test_point: str,
        business_rule: str = "",
        page_path: str = "",
        constraint: str = "",
        module: str = "",
        scenario_type: str = "normal",
    ) -> str:
        """简化的优先级判定入口（无需构造 RawScenario）

        供 test_case_generator 等外部模块直接调用。
        """
        from .business_rule_parser import RawScenario

        raw = RawScenario(
            source="auto",
            module=module,
            page_path=page_path,
            operation="",
            test_point=test_point,
            business_rule=business_rule,
            constraint=constraint,
        )
        strategy = TestCaseStrategy()
        return strategy._determine_priority(raw, scenario_type)

    @staticmethod
    def generate_case_content(
        test_point: str,
        business_rule: str = "",
        page_path: str = "",
        constraint: str = "",
        module: str = "",
        scenario_type: str = "normal",
    ) -> tuple[str, str]:
        """简化的用例内容生成（步骤 + 预期结果），无需构造 RawScenario

        Returns:
            (steps_str, expected_str) — 已编号、以换行符连接的格式化字符串
        """
        from .business_rule_parser import RawScenario

        raw = RawScenario(
            source="auto",
            module=module,
            page_path=page_path,
            operation="",
            test_point=test_point,
            business_rule=business_rule,
            constraint=constraint,
        )
        strategy = TestCaseStrategy()

        steps = strategy._generate_steps(raw, scenario_type)
        expected = strategy._generate_expected_results(raw, scenario_type)

        def _join_numbered(items):
            return "\n".join(f"{i}. {s}" for i, s in enumerate(items, 1))

        return _join_numbered(steps), _join_numbered(expected)


DEFAULT_STRATEGY = TestCaseStrategy()


def generate_scenarios(raw_scenarios: list[RawScenario], limit: int = 20) -> list[TestCaseScenario]:
    """便捷函数：生成测试场景"""
    return DEFAULT_STRATEGY.generate_scenarios(raw_scenarios, limit)


class TestCaseScoreEngine:
    """测试用例评分引擎（含冷启动保护机制）

    五维度评分：
    - 覆盖率(30%)：用例覆盖的业务规则数量
    - 完整性(25%)：用例步骤和预期结果的完整性
    - 优先级(20%)：用例优先级等级
    - 可执行性(15%)：用例可自动化执行的程度
    - 可维护性(10%)：用例描述的清晰度和规范性

    冷启动保护：
    - 历史执行次数 < 10时，仅使用静态维度评分（覆盖率+完整性）
    - 给予中等偏下基准分50分，强制触发人工审查
    """

    WEIGHTS = {
        "coverage": 0.30,
        "completeness": 0.25,
        "priority": 0.20,
        "executability": 0.15,
        "maintainability": 0.10,
    }

    # 冷启动保护配置
    FINAL_SCORE_THRESHOLD = 85.0
    _COLD_START_THRESHOLD = 10
    _COLD_START_BASE_SCORE = 50
    _COVERAGE_BASELINE_EMPTY = 30
    _COVERAGE_BASELINE_SHORT_KEYWORD = 40
    _COVERAGE_SHORT_KEYWORD_LENGTH = 10
    _COVERAGE_SCORE_MULTIPLIER = 10
    _COMPLETENESS_STEPS_THRESHOLD_HIGH = 3
    _COMPLETENESS_STEPS_THRESHOLD_LOW = 1
    _COMPLETENESS_EXPECTED_THRESHOLD = 2
    _STATIC_DIMENSIONS = ["coverage", "completeness"]  # 静态质量维度

    @classmethod
    def is_final_score_qualified(cls, score: float | None) -> bool:
        """判断评分是否达到最终交付门槛。"""
        return score is not None and score >= cls.FINAL_SCORE_THRESHOLD

    def score_with_metadata(self, case: dict[str, Any]) -> dict[str, Any]:
        """返回评分及其交付语义，冷启动分不得单独作为最终交付依据。"""
        execution_count = case.get("execution_count", 0)
        is_cold_start = execution_count < self._COLD_START_THRESHOLD
        score = self.score(case)
        return {
            "score": score,
            "is_cold_start": is_cold_start,
            "confidence": self._calculate_confidence(execution_count),
            "is_final_score_qualified": self.is_final_score_qualified(score) and not is_cold_start,
            "threshold": self.FINAL_SCORE_THRESHOLD,
        }

    def record_score(self, case: dict[str, Any], stage: str) -> float:
        """记录评分到 ``_runtime_quality``，不污染正式 15 字段。"""
        metadata = self.score_with_metadata(case)
        score = metadata["score"]
        if stage not in {"original", "optimized", "final"}:
            raise ValueError(f"不支持的评分阶段: {stage}")
        runtime = read_runtime_quality(case)
        if stage == "original":
            runtime.original_score = score
        elif stage == "optimized":
            runtime.optimized_score = score
        else:
            runtime.final_score = score
            runtime.final_audit_passed = False
        runtime.score_threshold = self.FINAL_SCORE_THRESHOLD
        runtime.is_cold_start = metadata["is_cold_start"]
        runtime.confidence = metadata["confidence"]
        if stage == "final":
            runtime.needs_human_review = not metadata["is_final_score_qualified"]
        runtime.score_history.append({"stage": stage, "score": score})
        attach_runtime_quality(case, runtime)
        return score

    def score(self, case: dict[str, Any]) -> float:
        """计算用例综合得分（0-100）

        含冷启动保护机制：当用例历史执行次数不足时，采用简化评分策略
        """
        execution_count = case.get("execution_count", 0)
        confidence = self._calculate_confidence(execution_count)

        # 冷启动保护：执行次数不足时，仅使用静态维度评分
        if execution_count < self._COLD_START_THRESHOLD:
            return self._cold_start_score(case, confidence)

        # 正常评分逻辑
        scores = {
            "coverage": self._score_coverage(case),
            "completeness": self._score_completeness(case),
            "priority": self._score_priority(case),
            "executability": self._score_executability(case),
            "maintainability": self._score_maintainability(case),
        }

        # 应用置信度权重调整
        weights = self._adjust_weights_by_confidence(confidence)

        total_score = sum(scores[dimension] * weights[dimension] for dimension in self.WEIGHTS)

        return round(total_score, 2)

    def _calculate_confidence(self, execution_count: int) -> float:
        """计算评分置信度（0.0-1.0）

        置信度随执行次数增加而提升，达到阈值后稳定在1.0
        """
        return min(execution_count / self._COLD_START_THRESHOLD, 1.0)

    def _cold_start_score(self, case: dict[str, Any], confidence: float) -> float:
        """冷启动期评分策略（优化版）

        当历史执行数据不足时：
        - 仅使用静态质量维度评分（覆盖率 + 完整性）
        - 不给予保底及格分，而是给予中等偏下的基准分（50分）
        - 这样能敏锐捕捉"新写的烂用例"，强制触发人工审查

        评分公式：最终分数 = 静态分数 × 置信度 + 基准分 × (1 - 置信度)
        - 执行次数=0 → 分数≈50分（强制审查）
        - 执行次数=5 → 分数≈静态分×0.5 + 50×0.5
        - 执行次数=10 → 进入正常评分流程
        """
        # 静态维度评分（覆盖率 + 完整性）
        static_score = self._score_coverage(case) * 0.5 + self._score_completeness(case) * 0.5

        # 根据静态评分质量动态调整基准分
        base_score = self._COLD_START_BASE_SCORE
        if static_score >= 80:
            base_score = 70
        elif static_score >= 60:
            base_score = 60

        # 置信度加权：置信度越低，分数越接近基准分
        final_score = static_score * confidence + base_score * (1 - confidence)

        return round(final_score, 2)

    def _adjust_weights_by_confidence(self, confidence: float) -> dict[str, float]:
        """根据置信度动态调整各维度权重

        置信度低时：
        - 静态维度（覆盖率、完整性）权重增加
        - 动态维度（优先级、可执行性、可维护性）权重减少
        """
        if confidence >= 1.0:
            return self.WEIGHTS

        dynamic_scale = confidence
        static_scale = 1.0 + (1.0 - confidence) * 0.5

        adjusted_weights = {}
        for dimension, weight in self.WEIGHTS.items():
            if dimension in self._STATIC_DIMENSIONS:
                adjusted_weights[dimension] = weight * static_scale
            else:
                adjusted_weights[dimension] = weight * dynamic_scale

        # 归一化权重
        total = sum(adjusted_weights.values())
        return {k: v / total for k, v in adjusted_weights.items()}

    def _score_coverage(self, case: dict[str, Any]) -> float:
        """评分：覆盖率（0-100）"""
        knowledge = case.get("知识库关联", "")
        if not knowledge:
            return self._COVERAGE_BASELINE_EMPTY
        # 仅存关键词（如"销售订单"）时给予基准分，避免被过度惩罚
        if len(knowledge) < self._COVERAGE_SHORT_KEYWORD_LENGTH:
            return self._COVERAGE_BASELINE_SHORT_KEYWORD
        return min(100, len(knowledge) * self._COVERAGE_SCORE_MULTIPLIER)

    def _score_completeness(self, case: dict[str, Any]) -> float:
        """评分：完整性（0-100）"""
        steps = case.get("用例步骤", "")
        expected = case.get("预期结果", "")

        step_count = len([s for s in steps.split("\n") if s.strip()]) if steps else 0
        expected_count = len([e for e in expected.split("\n") if e.strip()]) if expected else 0

        score = 0
        if step_count >= self._COMPLETENESS_STEPS_THRESHOLD_HIGH:
            score += 50
        elif step_count >= self._COMPLETENESS_STEPS_THRESHOLD_LOW:
            score += 25

        if expected_count >= self._COMPLETENESS_EXPECTED_THRESHOLD:
            score += 50
        elif expected_count >= 1:
            score += 25

        return score

    def _score_priority(self, case: dict[str, Any]) -> float:
        """评分：优先级（0-100）

        读取"优先级"字段（P0/P1/P2/P3），而非"用例等级"（高/中/低）
        """
        priority_map = {"P0": 100, "P1": 75, "P2": 50, "P3": 25}
        priority = case.get("优先级")
        if priority not in priority_map:
            priority = case.get("用例等级", "P2")
        return priority_map.get(priority, 50)

    def _score_executability(self, case: dict[str, Any]) -> float:
        """评分：可执行性（0-100）"""
        automation_flag = case.get("是否可自动化", "否")
        if automation_flag == "是":
            return 80
        return 40

    def _score_maintainability(self, case: dict[str, Any]) -> float:
        """评分：可维护性（0-100）"""
        case_name = case.get("用例名称", "")
        if len(case_name) >= 10 and len(case_name) <= 50:
            return 80
        return 50


class TestCaseOptimizer:
    """测试用例优化器"""

    def __init__(self, score_engine: TestCaseScoreEngine | None = None):
        self.score_engine = score_engine or TestCaseScoreEngine()
        self._optimization_rules: list[Callable] = [
            self._optimize_steps,
            self._optimize_expected_results,
            self._optimize_case_name,
        ]

    def optimize(self, case: dict[str, Any], target_score: float | None = None) -> dict[str, Any]:
        """优化用例直到达到目标分数"""
        if target_score is None:
            target_score = self.score_engine.FINAL_SCORE_THRESHOLD
        current_score = self.score_engine.score(case)
        if current_score >= target_score:
            return case

        for rule in self._optimization_rules:
            case = rule(case)

        return case

    def _optimize_steps(self, case: dict[str, Any]) -> dict[str, Any]:
        """优化用例步骤"""
        steps = case.get("用例步骤", "")
        step_list = [s.strip() for s in steps.split("\n") if s.strip()]

        if len(step_list) < 3:
            step_list.append("验证操作结果")
            if len(step_list) < 3:
                step_list.insert(0, "进入相关功能页面")

        case["用例步骤"] = "\n".join(f"{i}. {s}" for i, s in enumerate(step_list, 1))
        return case

    def _optimize_expected_results(self, case: dict[str, Any]) -> dict[str, Any]:
        """优化预期结果"""
        expected = case.get("预期结果", "")
        expected_list = [e.strip() for e in expected.split("\n") if e.strip()]

        if len(expected_list) < 2:
            expected_list.append("操作执行成功")

        case["预期结果"] = "\n".join(f"{i}. {e}" for i, e in enumerate(expected_list, 1))
        return case

    def _optimize_case_name(self, case: dict[str, Any]) -> dict[str, Any]:
        """优化用例名称"""
        case_name = case.get("用例名称", "")
        if len(case_name) < 10:
            case_name = f"测试_{case_name}_{datetime.now().strftime('%Y%m%d')}"
        elif len(case_name) > 50:
            case_name = case_name[:50]

        case["用例名称"] = case_name
        return case


class TestCaseRegenerationLoop:
    """测试用例自动重生闭环（含熔断机制，防止死亡螺旋）

    并发安全说明：
    - 当前版本为单机单进程模式，使用线程锁保证线程安全
    - 如果未来扩展为多进程/分布式模式，需要使用：
      1. 数据库原子操作（SELECT ... FOR UPDATE）
      2. 或分布式锁（如Redis锁）
      3. 或文件锁（fcntl/flock）

    熔断机制：
    - 单条用例最大重生次数：3次
    - 熔断冷却期：3600秒（1小时）
    - 达到上限后自动标记为 needs_human_review
    - 发送人工介入告警
    """

    # 审计轨迹保留在运行时字典中，不得扩展正式15字段 Excel 表头。
    AUDIT_FIELDS: tuple[str, ...] = ()

    def __init__(
        self,
        generator: TestCaseGenerator | None = None,
        score_engine: TestCaseScoreEngine | None = None,
        optimizer: TestCaseOptimizer | None = None,
    ):
        # 延迟导入避免循环引用
        from .test_case_generator import TestCaseGenerator

        self.generator = generator or TestCaseGenerator()
        self.score_engine = score_engine or TestCaseScoreEngine()
        self.optimizer = optimizer or TestCaseOptimizer()
        self._min_score_threshold = TestCaseScoreEngine.FINAL_SCORE_THRESHOLD
        self._max_regeneration_attempts = 3  # 单条用例最大重生次数
        self._cool_down_period = 3600  # 熔断冷却期（秒），防止短时间内重复重生

        # 线程级锁（使用可重入锁，支持同一线程多次获取，避免死锁风险）
        self._lock = threading.RLock()

        # 文件锁（用于多进程场景，可选）
        self._lock_file = None

    def _acquire_lock(self, case_id: str) -> None:
        """获取锁（线程级 + 可选文件级）"""
        self._lock.acquire()

        # 如果需要多进程支持，启用文件锁
        if self._lock_file is not None:
            try:
                import fcntl

                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass

    def _release_lock(self) -> None:
        """释放锁"""
        if self._lock_file is not None:
            try:
                import fcntl

                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        self._lock.release()

    def enable_multi_process_support(self, lock_file_path: str | None = None) -> None:
        """启用多进程支持（创建文件锁）"""
        if lock_file_path is None:
            lock_file_path = "/tmp/test_case_regeneration.lock"

        try:
            self._lock_file = open(lock_file_path, "w")
            logger.info(f"Multi-process support enabled with lock file: {lock_file_path}")
        except Exception as e:
            logger.warning(f"Failed to enable multi-process support: {e}")

    def generate_and_optimize(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """生成用例并自动优化，形成闭环"""
        cases = self.generator.generate_cases(keyword, limit)

        optimized_cases = []
        for case in cases:
            # 使用锁保护熔断检查和重生操作，防止并发问题
            case_id = str(id(case))
            self._acquire_lock(case_id)

            try:
                # 检查是否已达到重生上限或处于冷却期
                if self._is_circuit_broken(case):
                    case["用例状态"] = "正常"
                    runtime = read_runtime_quality(case)
                    runtime.needs_human_review = True
                    attach_runtime_quality(case, runtime)
                    self.score_engine.record_score(case, "final")
                    case["质量评分"] = read_runtime_quality(case).final_score or 0.0
                    self._send_human_review_alert(case)
                    optimized_cases.append(case)
                    continue

                optimized_case = self._regenerate_until_qualified(case)
                optimized_cases.append(optimized_case)
            finally:
                self._release_lock()

        return optimized_cases

    def run(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """生成用例并自动优化，形成闭环（兼容调用接口）"""
        return self.generate_and_optimize(keyword, limit)

    def generate_and_export(self, keyword: str, limit: int = 10, output_path: str | None = None) -> str:
        """生成用例并导出到Excel（审计字段仅保留在运行时）

        Args:
            keyword: 检索关键词
            limit: 返回用例数量限制
            output_path: 输出路径（可选）

        Returns:
            导出文件的路径
        """
        from .excel_generator import ExcelGenerator

        cases = self.generate_and_optimize(keyword, limit)
        if any(case.get("用例状态") != "正常" or case.get("质量评分", 0) < self._min_score_threshold for case in cases):
            raise RuntimeError("存在未达到最终评分门槛的用例，禁止导出")
        return ExcelGenerator.generate(cases, output_path=output_path or "")

    def _regenerate_until_qualified(self, case: dict[str, Any]) -> dict[str, Any]:
        """循环优化直到达标或达到重生上限"""
        regeneration = dict(case.get("_runtime_regeneration") or {})
        regeneration_count = int(regeneration.get("count", 0) or 0)
        runtime_quality = read_runtime_quality(case)
        if runtime_quality.original_score is None:
            self.score_engine.record_score(case, "original")

        for _ in range(self._max_regeneration_attempts):
            score = self.score_engine.score(case)
            if score >= self._min_score_threshold:
                self.score_engine.record_score(case, "final")
                case["质量评分"] = read_runtime_quality(case).final_score or 0.0
                case["_runtime_regeneration"] = {
                    "count": regeneration_count,
                    "last_regenerated_at": datetime.now().isoformat(),
                }
                case["用例状态"] = "正常"
                runtime = read_runtime_quality(case)
                runtime.needs_human_review = False
                attach_runtime_quality(case, runtime)
                return case

            if read_runtime_quality(case).original_score is None:
                self.score_engine.record_score(case, "original")
            case = self.optimizer.optimize(case, target_score=self._min_score_threshold)
            self.score_engine.record_score(case, "optimized")
            regeneration_count += 1

        # 达到重生上限，触发熔断
        self.score_engine.record_score(case, "final")
        case["质量评分"] = read_runtime_quality(case).final_score or 0.0
        case["_runtime_regeneration"] = {
            "count": regeneration_count,
            "last_regenerated_at": datetime.now().isoformat(),
        }
        case["用例状态"] = "正常"
        runtime = read_runtime_quality(case)
        runtime.needs_human_review = True
        attach_runtime_quality(case, runtime)
        self._send_human_review_alert(case)

        return case

    def _is_circuit_broken(self, case: dict[str, Any]) -> bool:
        """检查是否触发熔断"""
        regeneration_count = int((case.get("_runtime_regeneration") or {}).get("count", 0) or 0)

        # 检查重生次数是否达到上限
        if regeneration_count >= self._max_regeneration_attempts:
            return True

        # 检查是否处于冷却期
        last_regenerated = (case.get("_runtime_regeneration") or {}).get("last_regenerated_at")
        if last_regenerated:
            try:
                last_time = datetime.fromisoformat(last_regenerated)
                if (datetime.now() - last_time).total_seconds() < self._cool_down_period:
                    return True
            except Exception:
                pass

        return False

    def _send_human_review_alert(self, case: dict[str, Any]) -> None:
        """发送人工介入告警"""
        logger.warning(
            f"用例触发人工审核: {case.get('用例名称', '未知')}, "
            f"评分: {case.get('质量评分', 0)}, "
            f"重生次数: {(case.get('_runtime_regeneration') or {}).get('count', 0)}"
        )
        # 可选：发送邮件/钉钉/企微告警
        # alert_service.send_alert(case)

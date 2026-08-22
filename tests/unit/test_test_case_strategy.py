"""单元测试：test_case_strategy.py 扩展功能 - 测试用例评分与自动重生闭环

测试范围：
- TestCaseScoreEngine（五维度评分 + 冷启动保护）
- TestCaseOptimizer（用例优化）
- TestCaseRegenerationLoop（自动重生闭环 + 熔断机制）
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from modules.trae_test.utils.test_case_strategy import (
    TestCaseOptimizer as OptimizerUnderTest,
    TestCaseRegenerationLoop as RegenerationLoopUnderTest,
)
from modules.trae_test.utils.test_case_strategy import (
    TestCaseScoreEngine as TSEngine,
)
from modules.trae_test.utils.business_rule_parser import RawScenario
from modules.trae_test.utils.test_case_strategy import TestCaseStrategy
from modules.trae_test.utils.runtime_quality import read_runtime_quality


class TestScoreEngine:
    """测试用例评分引擎 - 参考值测试数据集

    已知输入输出：
    TC-001: 覆盖100(30%), 完整100(25%), P1-75(20%), 可执行80(15%), 可维护80(10%), 执行20 → 90.0
    TC-002: 执行次数5 → 冷启动保护
    TC-003: 覆盖100(30%), 完整100(25%), P0-100(20%), 可执行80(15%), 可维护80(10%), 执行30 → 95.0
    TC-005: 覆盖40(30%), 完整100(25%), P1-75(20%), 可执行80(15%), 可维护50(10%), 执行10 → 69.0
    """

    TC_001 = {
        "知识库关联": "测试业务规则12345678",
        "用例步骤": "1. 步骤1\n2. 步骤2\n3. 步骤3",
        "预期结果": "1. 结果1\n2. 结果2",
        "用例等级": "P1",
        "是否可自动化": "是",
        "用例名称": "测试用例001_正常流程",
        "execution_count": 20,
    }

    TC_002 = {
        "知识库关联": "规则",
        "用例步骤": "1. 步骤1",
        "预期结果": "",
        "用例等级": "P2",
        "是否可自动化": "否",
        "用例名称": "测试",
        "execution_count": 5,
    }

    TC_003 = {
        "知识库关联": "ABCDEFGHIJ",
        "用例步骤": "1. 步骤1\n2. 步骤2\n3. 步骤3",
        "预期结果": "1. 结果1\n2. 结果2",
        "用例等级": "P0",
        "是否可自动化": "是",
        "用例名称": "测试用例003_全链路正常流程",
        "execution_count": 30,
    }

    TC_005 = {
        "知识库关联": "业务规则",
        "用例步骤": "1. 步骤1\n2. 步骤2\n3. 步骤3",
        "预期结果": "1. 结果1\n2. 结果2",
        "用例等级": "P1",
        "是否可自动化": "是",
        "用例名称": "测试用例005",
        "execution_count": 10,
    }

    def setup_method(self):
        self.engine = TSEngine()

    def test_score_normal_case(self):
        """测试正常用例评分"""
        score = self.engine.score(self.TC_001)
        assert score == 90.0

    def test_score_cold_start(self):
        """测试冷启动评分（执行次数不足时强制触发审查）"""
        score = self.engine.score(self.TC_002)
        assert score <= 50  # 冷启动基准分50

    def test_score_high_quality(self):
        """测试高质量用例评分"""
        score = self.engine.score(self.TC_003)
        assert score == 95.0

    def test_score_with_confidence(self):
        """测试置信度边界（执行次数=10时进入正常评分）"""
        score = self.engine.score(self.TC_005)
        assert score == 69.0

    def test_score_cold_start_zero_executions(self):
        """测试执行次数为0时的冷启动评分"""
        case = dict(self.TC_002)
        case["execution_count"] = 0
        score = self.engine.score(case)
        # 执行次数=0时，分数应接近基准分50
        assert round(score) == 50

    def test_score_coverage_no_knowledge(self):
        """测试覆盖率评分（无知识库关联）"""
        case = {"知识库关联": ""}
        score = self.engine._score_coverage(case)
        assert score == 30

    def test_score_coverage_with_knowledge(self):
        """测试覆盖率评分（有知识库关联）"""
        case = {"知识库关联": "A" * 10}
        score = self.engine._score_coverage(case)
        assert score == 100

    def test_score_completeness_empty(self):
        """测试完整性评分（空步骤和预期）"""
        case = {"用例步骤": "", "预期结果": ""}
        score = self.engine._score_completeness(case)
        assert score == 0

    def test_score_priority_p0(self):
        """测试P0优先级映射"""
        case = {"用例等级": "P0"}
        score = self.engine._score_priority(case)
        assert score == 100

    def test_score_priority_p2(self):
        """测试P2优先级映射"""
        case = {"用例等级": "P2"}
        score = self.engine._score_priority(case)
        assert score == 50

    def test_score_priority_unknown(self):
        """测试未知优先级默认值"""
        case = {"用例等级": "unknown"}
        score = self.engine._score_priority(case)
        assert score == 50

    def test_score_executability_yes(self):
        """测试可自动化评分"""
        case = {"是否可自动化": "是"}
        score = self.engine._score_executability(case)
        assert score == 80

    def test_score_executability_no(self):
        """测试不可自动化评分"""
        case = {"是否可自动化": "否"}
        score = self.engine._score_executability(case)
        assert score == 40

    def test_score_maintainability_good(self):
        """测试好名字的可维护性"""
        case = {"用例名称": "测试用例名称_正常流程"}
        score = self.engine._score_maintainability(case)
        assert score == 80

    def test_score_maintainability_short(self):
        """测试短名称的可维护性"""
        case = {"用例名称": "测试"}
        score = self.engine._score_maintainability(case)
        assert score == 50

    def test_cold_start_base_score(self):
        """测试冷启动基准分"""
        assert self.engine._COLD_START_BASE_SCORE == 50
        assert self.engine._COLD_START_THRESHOLD == 10

    def test_calculate_confidence_full(self):
        """测试满置信度"""
        assert self.engine._calculate_confidence(10) == 1.0
        assert self.engine._calculate_confidence(20) == 1.0

    def test_calculate_confidence_partial(self):
        """测试部分置信度"""
        assert self.engine._calculate_confidence(5) == 0.5
        assert self.engine._calculate_confidence(0) == 0.0

    def test_strategy_registers_coverage_dimensions(self):
        strategy = TestCaseStrategy()
        raw = RawScenario(
            source="business_rules",
            module="产品",
            page_path="产品-产品中心-库存SKU",
            test_point="批量处理多个SKU，按多个仓库校验多明细，失败需要回滚",
            business_rule="处理中状态也要校验",
            scenario_type_hint="exception",
        )

        scenarios = strategy.generate_scenarios([raw], limit=1)

        assert len(scenarios) == 1
        assert scenarios[0].coverage_matrix["场景类型"] == "exception"
        assert {"多对象", "多仓库", "多明细", "状态", "失败"}.issubset(
            set(scenarios[0].coverage_dimensions)
        )

    def test_strategy_limit_is_preserved_with_coverage_registration(self):
        strategy = TestCaseStrategy()
        raw = RawScenario(source="business_rules", module="产品", page_path="库存SKU", test_point="批量处理多个SKU")

        scenarios = strategy.generate_scenarios([raw, raw], limit=1)

        assert len(scenarios) == 1


class TestCaseOptimizerTests:
    """测试用例优化器"""

    def setup_method(self):
        self.engine = TSEngine()
        self.optimizer = OptimizerUnderTest(self.engine)

    def test_optimize_already_good(self):
        """测试已达标用例不优化"""
        case = {
            "知识库关联": "A" * 10,
            "用例步骤": "1. 步骤1\n2. 步骤2\n3. 步骤3",
            "预期结果": "1. 结果1\n2. 结果2",
            "用例等级": "P0",
            "是否可自动化": "是",
            "用例名称": "测试用例名称",
            "execution_count": 20,
        }
        original_steps = case["用例步骤"]
        result = self.optimizer.optimize(case, target_score=80)
        assert result["用例步骤"] == original_steps  # 不应修改

    def test_optimize_steps_short(self):
        """测试补充短步骤"""
        case = {"用例步骤": "1. 步骤1"}
        result = self.optimizer._optimize_steps(case)
        assert len(result["用例步骤"].split("\n")) >= 2

    def test_optimize_expected_empty(self):
        """测试补充空预期结果"""
        case = {"预期结果": ""}
        result = self.optimizer._optimize_expected_results(case)
        assert len(result["预期结果"].split("\n")) >= 1

    def test_optimize_case_name_short(self):
        """测试补充短用例名称"""
        case = {"用例名称": "短名称"}
        result = self.optimizer._optimize_case_name(case)
        assert len(result["用例名称"]) >= 10

    def test_optimize_case_name_long(self):
        """测试截断长用例名称"""
        case = {"用例名称": "非" * 30}
        result = self.optimizer._optimize_case_name(case)
        assert len(result["用例名称"]) <= 50


class TestRegenerationLoop:
    """测试自动重生闭环"""

    def test_circuit_breaker_trigger(self):
        """测试熔断机制触发"""
        generator = Mock()
        generator.generate_cases.return_value = [{"用例名称": "test_case"}]

        loop = RegenerationLoopUnderTest(generator=generator)

        # Mock评分始终返回低分
        loop.score_engine.score = Mock(return_value=55)

        result = loop.generate_and_optimize("test", limit=1)

        assert result[0]["用例状态"] == "正常"
        assert read_runtime_quality(result[0]).needs_human_review is True
        assert result[0]["_runtime_regeneration"]["count"] >= 3

    def test_qualified_case(self):
        """测试合格用例"""
        generator = Mock()
        generator.generate_cases.return_value = [{"用例名称": "test_case"}]

        loop = RegenerationLoopUnderTest(generator=generator)

        # Mock评分始终返回高分
        loop.score_engine.score = Mock(return_value=85)

        result = loop.generate_and_optimize("test", limit=1)

        assert result[0]["用例状态"] == "正常"
        assert read_runtime_quality(result[0]).needs_human_review is False
        assert "质量评分" in result[0]

    def test_cool_down_period(self):
        """测试冷却期机制"""
        loop = RegenerationLoopUnderTest()

        case = {
            "用例名称": "test_case",
            "_runtime_regeneration": {
                "count": 3,
                "last_regenerated_at": datetime.now().isoformat(),
            },
        }

        assert loop._is_circuit_broken(case) is True

    def test_no_cool_down_after_period(self):
        """测试冷却期过后不再熔断"""
        loop = RegenerationLoopUnderTest()

        case = {
            "用例名称": "test_case",
            "_runtime_regeneration": {
                "count": 2,
                "last_regenerated_at": (datetime.now() - timedelta(hours=2)).isoformat(),
            },
        }

        assert loop._is_circuit_broken(case) is False

    def test_zero_regeneration_count(self):
        """测试初始状态不熔断"""
        loop = RegenerationLoopUnderTest()

        case = {
            "用例名称": "test_case",
            "regeneration_count": 0,
        }

        assert loop._is_circuit_broken(case) is False

    @patch("modules.trae_test.utils.test_case_strategy.logger")
    def test_human_review_alert(self, mock_logger):
        """测试人工审核告警"""
        loop = RegenerationLoopUnderTest()

        loop._send_human_review_alert(
            {
                "用例名称": "test_case",
                "质量评分": 55,
                "_runtime_regeneration": {"count": 3},
            }
        )

        mock_logger.warning.assert_called_once()

    def test_acquire_release_lock(self):
        """测试锁的获取和释放"""
        loop = RegenerationLoopUnderTest()

        try:
            loop._acquire_lock("test_case")
            loop._release_lock()
        except Exception as e:
            pytest.fail(f"锁操作失败: {e}")

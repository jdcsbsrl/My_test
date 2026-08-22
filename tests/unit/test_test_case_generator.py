from unittest.mock import Mock, patch

from modules.trae_test.utils.test_case_generator import (
    DEFAULT_CREATOR,
    TestCaseGenerator as GeneratorUnderTest,
    generate_cases,
)
from modules.trae_test.utils.template_builder import ALL_FIELDS
from modules.trae_test.utils.runtime_quality import read_runtime_quality


class TestTestCaseGenerator:

    def test_initialization(self):
        generator = GeneratorUnderTest()
        assert generator is not None
        assert generator.retriever is not None
        assert generator.excel_generator is not None

    def test_initialization_with_custom_retriever(self):
        mock_retriever = Mock()
        generator = GeneratorUnderTest(retriever=mock_retriever)
        assert generator.retriever == mock_retriever

    def test_generate_cases_with_dict_response(self):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = {
            "rule1": "业务规则1内容",
            "rule2": "业务规则2内容",
            "rule3": "业务规则3内容",
        }

        generator = GeneratorUnderTest(retriever=mock_retriever)
        cases = generator.generate_cases("销售", limit=2)

        assert len(cases) == 2
        mock_retriever.retrieve.assert_called_once_with("销售", mode="hybrid")

        for case in cases:
            assert isinstance(case, dict)
            assert "用例目录" in case
            assert "用例名称" in case
            assert "用例步骤" in case
            assert "预期结果" in case
            assert "用例类型" in case
            assert "用例等级" in case
            assert "优先级" in case
            assert list(case) == ALL_FIELDS
            assert case["质量评分"] == 0.0

    def test_generate_cases_with_list_response(self):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = [
            {"id": "req001", "content": "需求1"},
            {"id": "req002", "content": "需求2"},
        ]

        generator = GeneratorUnderTest(retriever=mock_retriever)
        cases = generator.generate_cases("采购")

        assert len(cases) == 2
        assert cases[0]["用例名称"] == "测试_采购_req001"

    def test_generate_cases_empty_response(self):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = {}

        generator = GeneratorUnderTest(retriever=mock_retriever)
        cases = generator.generate_cases("测试")

        assert len(cases) == 0

    def test_generate_cases_limit(self):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = {f"rule{i}": f"规则{i}" for i in range(20)}

        generator = GeneratorUnderTest(retriever=mock_retriever)
        cases = generator.generate_cases("测试", limit=5)

        assert len(cases) == 5

    def test_generate_cases_default_limit(self):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = {f"rule{i}": f"规则{i}" for i in range(15)}

        generator = GeneratorUnderTest(retriever=mock_retriever)
        cases = generator.generate_cases("测试")

        assert len(cases) == 10

    def test_derive_coverage_matrix_marks_explicit_dimensions(self):
        matrix = GeneratorUnderTest._derive_coverage_matrix(
            "库存SKU批量采购计划", "批量处理多个SKU，按多个仓库校验多明细，失败后回滚", "exception"
        )

        assert matrix["场景类型"] == "exception"
        assert {"多对象", "多仓库", "多明细", "失败"}.issubset(matrix)
        assert len(ALL_FIELDS) == 15

    def test_build_case_from_knowledge(self):
        with patch("modules.trae_test.utils.test_case_generator._load_module_hierarchy") as mock_load:
            mock_load.return_value = {"销售": {"订单处理": ["销售订单"]}}
            generator = GeneratorUnderTest()
            case = generator._build_case_from_knowledge("销售", "case001", {"rule": "内容"})

            assert case["用例目录"] == "销售 - 订单处理 - 销售订单"
            assert case["用例名称"] == "测试_销售_case001"
            assert "销售" in case["用例步骤"]
            assert "销售" in case["预期结果"]
            assert case["用例类型"] == "功能测试"
            assert case["用例等级"] == "高"
            assert case["优先级"] == "P1"
            assert case["是否可自动化"] == "是"
            assert case["知识库关联"].startswith("销售")
            assert "内容" in case["知识库关联"]

    def test_export_to_excel(self, tmp_path):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = {"rule1": "内容"}

        mock_excel_generator = Mock()
        mock_excel_generator.generate.return_value = str(tmp_path / "output.xlsx")

        generator = GeneratorUnderTest(retriever=mock_retriever)
        generator.excel_generator = mock_excel_generator

        cases = generator.generate_cases("测试")
        for case in cases:
            case["质量评分"] = 90
            case["用例状态"] = "正常"
            runtime = read_runtime_quality(case)
            runtime.final_score = 90
            runtime.final_audit_passed = True
            runtime.needs_human_review = False
            case["_runtime_quality"] = runtime.to_dict()
            case["_runtime_quality_version"] = "1.0"
        output_path = generator.export_to_excel(cases, str(tmp_path / "output.xlsx"))

        mock_excel_generator.generate.assert_called_once()
        assert output_path == str(tmp_path / "output.xlsx")

    def test_generate_and_export(self, tmp_path):
        mock_retriever = Mock()
        mock_retriever.retrieve.return_value = {"rule1": "内容"}

        mock_excel_generator = Mock()
        mock_excel_generator.generate.return_value = str(tmp_path / "output.xlsx")

        generator = GeneratorUnderTest(retriever=mock_retriever)
        generator.excel_generator = mock_excel_generator

        with patch("modules.trae_test.orchestrator.audit_gateway.AuditGateway") as gateway_cls, \
             patch("modules.trae_test.utils.test_case_generator.TestCaseScoreEngine") as score_cls:
            gateway_cls.return_value.audit.return_value.passed = True
            gateway_cls.return_value.audit.return_value.errors = []
            score_cls.return_value.score.return_value = 90
            score_cls.return_value._COLD_START_THRESHOLD = 10
            score_cls.return_value._calculate_confidence.return_value = 0.0
            generator.generate_and_export("测试")

        mock_retriever.retrieve.assert_called_once()
        mock_excel_generator.generate.assert_called_once()

    def test_generate_cases_convenience_function(self):
        result = generate_cases("测试", limit=5)
        assert isinstance(result, list)

    def test_default_creator(self):
        assert DEFAULT_CREATOR is not None
        assert isinstance(DEFAULT_CREATOR, GeneratorUnderTest)

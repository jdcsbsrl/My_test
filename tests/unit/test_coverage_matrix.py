from modules.trae_test.utils.coverage_matrix import (
    CoverageMatrix,
    attach_coverage_matrix,
    read_coverage_matrix,
)


def test_matrix_normalizes_values_and_deduplicates() -> None:
    matrix = CoverageMatrix(
        business_rules=["规则A", "规则A", " ", 1],
        business_objects=["SKU"],
        normal_scenarios=["正常"],
    )

    assert matrix.business_rules == ["规则A", "1"]
    assert matrix.to_dict()["business_objects"] == ["SKU"]


def test_attach_writes_runtime_only_fields() -> None:
    case = {"用例名称": "示例", "质量评分": 90}
    attach_coverage_matrix(case, CoverageMatrix(business_rules=["规则A"]))

    assert case["用例名称"] == "示例"
    assert case["质量评分"] == 90
    assert case["_runtime_coverage_matrix"] == {
        "business_rules": ["规则A"],
        "business_objects": [],
        "normal_scenarios": [],
        "abnormal_scenarios": [],
        "boundary_scenarios": [],
        "rollback_scenarios": [],
        "exclusions": [],
    }
    assert case["_runtime_coverage_matrix_version"] == "1.0"


def test_read_and_missing_coverage_are_deterministic() -> None:
    case = {}
    attach_coverage_matrix(
        case,
        {
            "business_rules": ["规则A", "规则B"],
            "exclusions": ["WMS"],
            "unknown": ["ignored"],
        },
    )

    matrix = read_coverage_matrix(case)
    assert matrix.business_rules == ["规则A", "规则B"]
    assert matrix.missing_from({"business_rules": ["规则A"]}) == {
        "business_rules": ["规则B"],
        "exclusions": ["WMS"],
    }


def test_missing_runtime_matrix_returns_empty_matrix() -> None:
    assert read_coverage_matrix({}).to_dict() == {
        "business_rules": [],
        "business_objects": [],
        "normal_scenarios": [],
        "abnormal_scenarios": [],
        "boundary_scenarios": [],
        "rollback_scenarios": [],
        "exclusions": [],
    }


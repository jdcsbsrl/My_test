import pytest

from modules.auto_test.core.export_requirement_1003531 import (
    assert_complete_sku_pages,
    expected_page_rows,
    task_conditions,
)


@pytest.mark.unit
@pytest.mark.requirement("1003531")
def test_page_sizes_cover_full_and_tail_pages():
    assert expected_page_rows(0) == []
    assert expected_page_rows(5000) == [5000]
    assert expected_page_rows(5001) == [5000, 1]
    assert expected_page_rows(73808) == [5000] * 14 + [3808]


@pytest.mark.unit
@pytest.mark.requirement("1003531")
def test_task_conditions_accept_json_or_object():
    assert task_conditions({"taskConditions": '{"salesStatusList":["2"]}'}) == {"salesStatusList": ["2"]}
    assert task_conditions({"taskConditions": {"searchMode": "3"}}) == {"searchMode": "3"}
    with pytest.raises(ValueError):
        task_conditions({"taskConditions": None})


@pytest.mark.unit
@pytest.mark.requirement("1003531")
def test_full_pages_detect_overlap_and_task_difference():
    assert_complete_sku_pages([["A", "B"], ["C"]], ["C", "A", "B"], 3, 2)
    with pytest.raises(AssertionError):
        assert_complete_sku_pages([["A", "B"], ["B"]], ["A", "B", "C"], 3, 2)

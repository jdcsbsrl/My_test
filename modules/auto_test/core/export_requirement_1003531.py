"""Pure assertions shared by requirement 1003531 export regressions."""

import json

PAGE_SIZE = 5000


def expected_page_rows(total: int, page_size: int = PAGE_SIZE) -> list[int]:
    if total < 0 or page_size <= 0:
        raise ValueError("Invalid export pagination inputs")
    return [min(page_size, total - offset) for offset in range(0, total, page_size)]


def task_conditions(post_data: dict) -> dict:
    value = post_data.get("taskConditions")
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("Export task request lacks object taskConditions")
    return value


def assert_complete_sku_pages(
    pages: list[list[str]], task_skus: list[str], total: int, page_size: int = PAGE_SIZE
) -> None:
    expected = expected_page_rows(total, page_size)
    if [len(page) for page in pages] != expected:
        raise AssertionError("Export page row counts differ from pagination")
    flattened = [sku for page in pages for sku in page]
    if len(flattened) != len(set(flattened)) or len(flattened) != total:
        raise AssertionError("Export pages contain duplicate or missing SKUs")
    if set(flattened) != set(task_skus) or len(task_skus) != len(set(task_skus)):
        raise AssertionError("Full export task differs from paged real-time exports")

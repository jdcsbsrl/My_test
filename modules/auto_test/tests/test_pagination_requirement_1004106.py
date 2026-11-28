"""Read-only pagination regression for requirement 1004106."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, expect

from modules.auto_test.core.config_manager import ConfigManager

PAGE_SIZES = (20, 100, 300, 500, 1000, 2000)
_SIZE_PATTERN = re.compile(r"(?<!\d)(2000|1000|500|300|100|20)(?!\d)")


def _size_control(page: Page):
    control = page.locator(".el-pagination__sizes:visible").first
    expect(control).to_be_visible(timeout=30000)
    return control


def _selected_size(control) -> int:
    selected = control.locator(".el-select__selected-item:visible").first
    candidates = [control.inner_text(), control.text_content() or ""]
    if selected.count():
        candidates.extend([selected.inner_text(), selected.text_content() or ""])
    for input_element in control.locator("input:visible").all():
        try:
            candidates.extend([input_element.input_value(), input_element.get_attribute("aria-label") or ""])
        except Exception:
            continue
    for text in candidates:
        match = _SIZE_PATTERN.search(text)
        if match:
            return int(match.group(1))
    diagnostics = control.evaluate("""element => ({
            html: element.innerHTML,
            inputs: [...element.querySelectorAll('input')].map(input => ({
                value: input.value,
                ariaLabel: input.getAttribute('aria-label'),
                placeholder: input.placeholder,
            })),
        })""")
    raise AssertionError(f"无法从分页选择器读取当前每页条数: {diagnostics!r}")


def _option_sizes(page: Page, control) -> list[int]:
    native_select = control.locator("select:visible").first
    if native_select.count():
        labels = native_select.locator("option").all_inner_texts()
        values = []
        for label in labels:
            match = _SIZE_PATTERN.search(label)
            if match:
                values.append(int(match.group(1)))
        return values

    trigger = control.locator(".el-select__wrapper:visible").first
    if not trigger.count():
        trigger = control.locator(".el-select:visible").first
    assert trigger.count(), "分页每页条数下拉框缺少可操作控件"
    trigger.click()
    options = page.locator(".el-select-dropdown__item:visible")
    expect(options.first).to_be_visible(timeout=10000)
    labels = options.all_inner_texts()
    page.keyboard.press("Escape")
    expect(options.first).not_to_be_visible(timeout=10000)
    values = []
    for label in labels:
        match = _SIZE_PATTERN.search(label)
        if match:
            values.append(int(match.group(1)))
    return values


def _request_field(request, field: str) -> int | None:
    payload = None
    try:
        payload = request.post_data_json
    except Exception:
        try:
            payload = request.url
        except Exception:
            return None

    if isinstance(payload, str):
        try:
            pairs = parse_qs(urlsplit(payload).query)
            values = pairs.get(field) or []
            return int(values[0]) if values else None
        except Exception:
            return None
    if isinstance(payload, dict):
        if field in payload:
            try:
                return int(payload[field])
            except (TypeError, ValueError):
                return None
        for value in payload.values():
            if isinstance(value, dict):
                found = _request_field_from_mapping(value, field)
                if found is not None:
                    return found
    try:
        values = parse_qs(urlsplit(request.url).query).get(field) or []
        return int(values[0]) if values else None
    except Exception:
        return None


def _request_field_from_mapping(payload: dict, field: str) -> int | None:
    if field in payload:
        try:
            return int(payload[field])
        except (TypeError, ValueError):
            return None
    for value in payload.values():
        if isinstance(value, dict):
            found = _request_field_from_mapping(value, field)
            if found is not None:
                return found
    return None


def _response_rows(payload) -> list | None:
    if isinstance(payload, dict):
        for key in ("rows", "records", "list", "items", "dataList"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            if isinstance(value, list):
                return value
            found = _response_rows(value)
            if found is not None:
                return found
    elif isinstance(payload, list):
        return payload
    return None


def _response_rows_count(payload) -> int | None:
    rows = _response_rows(payload)
    return len(rows) if rows is not None else None


def _response_total(payload) -> int | None:
    if isinstance(payload, dict):
        for key in ("total", "totalCount", "totalRows", "recordsTotal"):
            value = payload.get(key)
            if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
                return int(value)
        for value in payload.values():
            found = _response_total(value)
            if found is not None:
                return found
    return None


def _response_summary(response) -> dict:
    payload = response.json()
    rows = _response_rows(payload)
    row_fingerprint = None
    if rows is not None:
        canonical_rows = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
        row_fingerprint = hashlib.sha256(canonical_rows.encode("utf-8")).hexdigest()
    return {
        "url_path": urlsplit(response.url).path,
        "status": response.status,
        "page_size": _request_field(response.request, "pageSize"),
        "page_num": _request_field(response.request, "pageNum"),
        "rows": _response_rows_count(payload),
        "rows_fingerprint": row_fingerprint,
        "total": _response_total(payload),
    }


def _is_pagination_response(response, *, size: int, endpoint_fragment: str, page_num: int | None = None) -> bool:
    request = response.request
    if endpoint_fragment not in response.url:
        return False
    if _request_field(request, "pageSize") != size:
        return False
    if page_num is not None and _request_field(request, "pageNum") != page_num:
        return False
    try:
        return _response_rows_count(response.json()) is not None
    except Exception:
        return False


def _select_size(page: Page, control, size: int, *, endpoint_fragment: str) -> dict | None:
    if _selected_size(control) == size:
        return None

    response_info = None
    native_select = control.locator("select:visible").first
    if native_select.count():
        option = native_select.locator("option").filter(has_text=_SIZE_PATTERN).all()
        matching = next(
            (
                item
                for item in option
                if (match := _SIZE_PATTERN.search(item.inner_text())) and int(match.group(1)) == size
            ),
            None,
        )
        assert matching is not None, f"下拉框缺少每页 {size} 条选项"
        with page.expect_response(
            lambda response: _is_pagination_response(response, size=size, endpoint_fragment=endpoint_fragment),
            timeout=30000,
        ) as response_info:
            native_select.select_option(matching.get_attribute("value"))
    else:
        trigger = control.locator(".el-select__wrapper:visible").first
        if not trigger.count():
            trigger = control.locator(".el-select:visible").first
        choices = page.locator(".el-select-dropdown__item:visible")
        if not choices.count():
            trigger.click()
        expect(choices.first).to_be_visible(timeout=10000)
        labels = choices.all_inner_texts()
        match = next(
            (
                index
                for index, label in enumerate(labels)
                if (found := _SIZE_PATTERN.search(label)) and int(found.group(1)) == size
            ),
            None,
        )
        assert match is not None, f"下拉框缺少每页 {size} 条选项；当前可见选项: {labels!r}"
        with page.expect_response(
            lambda response: _is_pagination_response(response, size=size, endpoint_fragment=endpoint_fragment),
            timeout=30000,
        ) as response_info:
            choices.nth(match).click()
        expect(choices.first).not_to_be_visible(timeout=10000)

    expect(control).to_contain_text(_SIZE_PATTERN, timeout=30000)
    assert _selected_size(control) == size, f"分页选择器没有切换为每页 {size} 条"
    return _response_summary(response_info.value)


def _total_count(page: Page) -> int:
    total = page.locator(".el-pagination__total:visible").first
    expect(total).to_be_visible(timeout=10000)
    text = total.inner_text()
    match = re.search(r"([\d,]+)", text)
    assert match, f"无法读取分页总数: {text!r}"
    return int(match.group(1).replace(",", ""))


def _visible_rows(page: Page) -> list[str]:
    if page.locator(".el-table__empty-block:visible").count():
        return []
    selectors = (
        ".el-table__body-wrapper:visible tbody tr.el-table__row:visible",
        ".el-table__body-wrapper:visible tbody tr:visible",
        ".ant-table-tbody:visible > tr:visible",
        ".order-block:visible",
    )
    for selector in selectors:
        rows = page.locator(selector)
        if rows.count():
            return [" ".join(row.inner_text().split()) for row in rows.all()]
    return []


def _active_page(pagination) -> str:
    active = pagination.locator(
        ".el-pager .number.is-active:visible, .el-pager li.is-active:visible, .el-pager li.active:visible"
    ).first
    if active.count():
        return active.inner_text().strip()
    return ""


def _next_button(pagination):
    button = pagination.locator(".btn-next:visible, button[aria-label='下一页']:visible").first
    expect(button).to_be_visible(timeout=10000)
    return button


def _previous_button(pagination):
    button = pagination.locator(".btn-prev:visible, button[aria-label='上一页']:visible").first
    expect(button).to_be_visible(timeout=10000)
    return button


def _verify_page(
    page: Page,
    config,
    route_name: str,
    route: str,
    endpoint_fragment: str,
    expected_initial_size: int | None,
) -> None:
    base = config.base_url.rstrip("/")
    if base.endswith("/index"):
        base = base[: -len("/index")]
    with page.expect_response(
        lambda response: endpoint_fragment in response.url
        and _request_field(response.request, "pageSize") is not None
        and _response_rows_count(response.json()) is not None,
        timeout=30000,
    ) as initial_response_info:
        page.goto(f"{base}/{route}", wait_until="domcontentloaded")
    control = _size_control(page)
    initial_size = _selected_size(control)
    failures: list[str] = []
    if expected_initial_size is not None and initial_size != expected_initial_size:
        failures.append(f"默认每页条数应为{expected_initial_size}，实际为{initial_size}")
    elif expected_initial_size is None and initial_size not in PAGE_SIZES:
        failures.append(f"记忆的每页条数{initial_size}不在支持选项{list(PAGE_SIZES)}中")
    available_sizes = _option_sizes(page, control)
    if available_sizes != list(PAGE_SIZES):
        failures.append(f"分页选项应为{list(PAGE_SIZES)}，实际为{available_sizes}")
    baseline_total = _total_count(page)
    if baseline_total <= 20:
        pytest.fail(
            f"BLOCKED: {route_name} 当前只有 {baseline_total} 条记录，"
            "至少需要21条 test 数据才能验证下一页和返回上一页"
        )
    initial_response = _response_summary(initial_response_info.value)
    response_by_size = {initial_response["page_size"]: initial_response}
    observations = []
    try:
        for size in PAGE_SIZES:
            try:
                response = _select_size(page, control, size, endpoint_fragment=endpoint_fragment)
            except Exception as exc:
                failures.append(f"选择每页{size}条失败: {type(exc).__name__}: {exc}")
                continue
            if response is not None:
                response_by_size[size] = response
            response = response or response_by_size.get(size)
            if response is None:
                failures.append(f"每页{size}条缺少对应的列表响应")
                continue
            total = _total_count(page)
            if total != baseline_total:
                failures.append(f"切换到每页{size}条后总数变化: {baseline_total} -> {total}")
            response_rows = response["rows"]
            response_total = response["total"] if response["total"] is not None else total
            expected_rows = min(size, response_total)
            if response_rows != expected_rows:
                failures.append(
                    f"每页{size}条的列表响应应含{expected_rows}行，实际{response_rows}行，"
                    f"响应总数{response_total}，页面总数{total}"
                )
            if response_total != total:
                failures.append(f"每页{size}条时页面总数{total}与列表响应总数{response_total}不一致")
            observations.append(response)

        _select_size(page, control, 20, endpoint_fragment=endpoint_fragment)
        first_page_response = response_by_size.get(20)
        pagination = page.locator(".el-pagination:visible").first
        next_button = _next_button(pagination)
        previous_button = _previous_button(pagination)
        if baseline_total > 20:
            if next_button.is_disabled():
                failures.append("总数大于20时下一页按钮被禁用")
            else:
                with page.expect_response(
                    lambda response: _is_pagination_response(
                        response, size=20, page_num=2, endpoint_fragment=endpoint_fragment
                    ),
                    timeout=30000,
                ) as second_response_info:
                    next_button.click()
                active_page = pagination.locator(
                    ".el-pager .number.is-active:visible, .el-pager li.is-active:visible, .el-pager li.active:visible"
                ).first
                expect(active_page).to_have_text("2", timeout=30000)
                second_response = _response_summary(second_response_info.value)
                if second_response["rows"] != min(20, baseline_total - 20):
                    failures.append(f"第二页响应应含{min(20, baseline_total - 20)}行，实际{second_response['rows']}行")
                if (
                    first_page_response is None
                    or second_response["rows_fingerprint"] == first_page_response["rows_fingerprint"]
                ):
                    failures.append("第二页列表记录内容与第一页完全相同")
                with page.expect_response(
                    lambda response: _is_pagination_response(
                        response, size=20, page_num=1, endpoint_fragment=endpoint_fragment
                    ),
                    timeout=30000,
                ) as first_response_info:
                    previous_button.click()
                expect(active_page).to_have_text("1", timeout=30000)
                first_response = _response_summary(first_response_info.value)
                if first_response["rows"] != min(20, baseline_total):
                    failures.append(f"返回第一页响应应含{min(20, baseline_total)}行，实际{first_response['rows']}行")
                if (
                    first_page_response is None
                    or first_response["rows_fingerprint"] != first_page_response["rows_fingerprint"]
                ):
                    failures.append("返回第一页后的列表记录与首次第一页响应不一致")
        elif not next_button.is_disabled():
            failures.append("总数不超过20时下一页按钮未禁用")
    finally:
        try:
            if _selected_size(control) != initial_size:
                _select_size(page, control, initial_size, endpoint_fragment=endpoint_fragment)
        except Exception as exc:
            failures.append(f"恢复初始每页条数{initial_size}失败: {type(exc).__name__}")

    print(
        f"{route_name}: initial={initial_size}, total={baseline_total}, sizes={list(PAGE_SIZES)}, "
        f"responses={observations}, failures={failures}"
    )
    assert not failures, "; ".join(failures)


@pytest.fixture
def pagination_logged_in_page(request: pytest.FixtureRequest, config_manager: ConfigManager) -> Page:
    """Reuse the shared login fixture, but only after confirming this is test."""

    if config_manager.env != "test":
        pytest.skip("需求1004106仅允许在 test 环境执行；保留当前 pytest 环境配置")
    return request.getfixturevalue("logged_in_page")


def _run_page_pagination(
    page: Page,
    config: ConfigManager,
    route_name: str,
    route: str,
    endpoint_fragment: str,
    expected_initial_size: int | None,
) -> None:
    _verify_page(page, config, route_name, route, endpoint_fragment, expected_initial_size)


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1004106")
def test_sales_order_pagination(pagination_logged_in_page: Page, config_manager: ConfigManager) -> None:
    _run_page_pagination(
        pagination_logged_in_page,
        config_manager,
        "销售订单",
        "sales/order/saleOrder",
        "batchListNew",
        None,
    )


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1004106")
def test_platform_exception_pagination(pagination_logged_in_page: Page, config_manager: ConfigManager) -> None:
    _run_page_pagination(
        pagination_logged_in_page,
        config_manager,
        "同步平台异常",
        "sales/exception/platException",
        "selectExceptionNew",
        20,
    )

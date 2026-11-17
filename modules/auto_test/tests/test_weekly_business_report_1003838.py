"""Regression coverage for weekly business report requirement 1003838."""

from __future__ import annotations

import os
import re
import uuid
import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest
import requests
from playwright.sync_api import Browser, TimeoutError as PlaywrightTimeoutError, expect

from modules.auto_test.api.weekly_business_report_api import WeeklyBusinessReportAPI
from modules.auto_test.core.weekly_business_report_checks import (
    amount,
    direct_currency_expectation,
    is_declining_customer,
    is_main_customer,
    is_weekly_report_unshipped_order,
    payment_abnormal_bills,
    unshipped_order_ready_percent,
    unshipped_order_ready_percent_from_stock_marks,
)
from modules.auto_test.pages.weekly_business_report_page import (
    CUSTOMER_REPORT_TABS,
    WEEKLY_REPORT_TABS,
    WeeklyBusinessReportPage,
)

REPORT_TYPES = {
    "1": "主要客户情况",
    "2": "销量下降客户情况",
    "3": "付款异常客户",
    "4": "上周新增客户",
    "5": "上上周新增客户回访",
}
MONEY_FIELDS = (
    "receivableAmount",
    "paidButNotReceiveAmount",
    "actualUnpaidAmount",
    "receivableInPeriodAmount",
    "receivableOutPeriodAmount",
    "shippedAmount",
    "unshippedAmount",
)
AMOUNT_TOLERANCE = Decimal("0.02")


def _role() -> str:
    role = os.getenv("WEEKLY_REPORT_ROLE", "").strip().lower()
    assert role in {"admin", "manager", "sales"}, (
        "Set WEEKLY_REPORT_ROLE explicitly to admin, manager, or sales; "
        "the account role is not inferred from its username"
    )
    return role


def _api(session, api_base_url: str) -> WeeklyBusinessReportAPI:
    return WeeklyBusinessReportAPI(session, api_base_url)


@pytest.fixture
def administrator_http_client(browser: Browser, config_manager):
    """Create a separate admin session for read-only role-scope comparisons."""
    if _role() == "admin":
        yield None
        return

    from modules.auto_test.core.secret_provider import get_secret
    from modules.auto_test.pages.login_page import LoginPage

    username = get_secret("ADMIN_USERNAME", environment=config_manager.env)
    password = get_secret("ADMIN_PASSWORD", environment=config_manager.env)
    assert username and password, "Administrator credentials are required for weekly-report role comparisons"

    context = browser.new_context()
    page = context.new_page()
    login_capture: dict[str, object] = {}

    def capture(response) -> None:
        if "/auth/login" not in response.url or response.status != 200:
            return
        try:
            body = response.json()
            if body.get("code") == 200:
                login_capture["body"] = body
                login_capture["clientid"] = response.request.all_headers().get("clientid")
        except (ValueError, AttributeError):
            return

    page.on("response", capture)
    session = requests.Session()
    try:
        assert LoginPage(page, config=config_manager).login(username, password), "Administrator login failed"
        body = login_capture.get("body") or {}
        data = body.get("data") or {} if isinstance(body, dict) else {}
        token = data.get("token") or data.get("access_token") if isinstance(data, dict) else None
        assert token, "Administrator login did not provide an API token"
        session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        if login_capture.get("clientid"):
            session.headers["clientid"] = str(login_capture["clientid"])
        for cookie in context.cookies():
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )
        yield session
    finally:
        session.close()
        context.close()


def _latest_reports(api: WeeklyBusinessReportAPI) -> tuple[str, list[dict]]:
    rows = api.list_reports()
    assert rows, "The current account cannot access any weekly reports"
    starts = [str(row.get("weekStartDate") or "")[:10] for row in rows]
    assert all(starts), "Weekly report list contains a row without weekStartDate"
    latest = max(starts)
    reports = [row for row in rows if str(row.get("weekStartDate"))[:10] == latest]
    assert reports, f"No report rows found for latest week {latest}"
    return latest, reports


def _sixth_group_reports(reports: list[dict]) -> list[dict]:
    return [
        report
        for report in reports
        if re.search(r"(?:六|6)\s*组", re.sub(r"\s+", "", str(report.get("deptName") or "")))
    ]


def _report_for_ui_scope(reports: list[dict]) -> dict:
    """Use the authorized six-group report for every configured role."""
    matches = _sixth_group_reports(reports)
    assert len(matches) == 1, f"Expected exactly one latest six-group report for {_role()}; found {len(matches)}"
    return matches[0]


def _visible_exact_text_counts(page, values: list[str]) -> dict[str, int]:
    return page.evaluate(
        """values => {
      const isVisible = element => {
        const style = window.getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0;
      };
      return Object.fromEntries(values.map(value => [value,
        Array.from(document.querySelectorAll('*')).filter(element =>
          element.children.length === 0 && element.textContent.trim() === value && isVisible(element)
        ).length
      ]));
    }""",
        values,
    )


def _choose_search_option(page, placeholder: str, value: str) -> bool:
    search_value_lengths = []
    page.keyboard.press("Escape")
    if not page.locator(".keyword-select-popover:visible, .el-select-dropdown:visible").count():
        controls = page.locator(f"input[placeholder='{placeholder}']:visible")
        if controls.count():
            controls.first.click()
        else:
            label = page.get_by_text(placeholder, exact=True).first
            select_wrapper = label.locator(
                "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' el-select ')][1]"
            )
            if select_wrapper.count():
                select_wrapper.click()
            else:
                label.click(force=True)
    page.locator(".keyword-select-popover:visible, .el-select-dropdown:visible").last.wait_for(
        state="visible", timeout=10000
    )
    popover = page.locator(".keyword-select-popover:visible").last
    if popover.count():
        popup_search = popover.locator("input:visible").first
        if popup_search.count() and popup_search.is_editable():
            popup_search.click()
            popup_search.fill(value)
            search_value_lengths.append(popup_search.input_value().__len__())
            page.wait_for_timeout(300)
            search_value_lengths.append(popup_search.input_value().__len__())
            if popup_search.input_value() != value:
                popup_search.press_sequentially(value, delay=30)
                search_value_lengths.append(popup_search.input_value().__len__())
        options = popover.locator(".keyword-item")
    else:
        dropdown_search = page.locator(".el-select-dropdown:visible input:visible").last
        if dropdown_search.count() and dropdown_search.is_editable():
            dropdown_search.fill(value)
        options = page.locator(".el-select-dropdown__item:visible, [role='option']:visible")
    option = options.filter(has_text=value).first
    try:
        option.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        from modules.trae_test.utils.runtime_paths import runtime_dir

        screenshot_dir = runtime_dir("reports") / "sales_report_regression"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / "search-option-empty.png"), full_page=True)
        input_diagnostics = page.locator(".keyword-select-popover input:visible").evaluate_all(
            "elements => elements.map(element => ({placeholder: element.getAttribute('placeholder'), "
            "readonly: element.readOnly, disabled: element.disabled, value_length: element.value.length, "
            "class_name: element.className}))"
        )
        page._weekly_report_filter_input_diagnostics = {
            "inputs": input_diagnostics,
            "search_value_lengths": search_value_lengths,
            "option_count": options.count(),
        }
        return False
    option.click()
    return True


def _filter_value_candidates(value: str, field: str) -> list[str]:
    candidates = [value]
    if field in {"storeHeadNames", "salesCountry"}:
        for part in re.split(r"[,，;；、|\n]+", value):
            part = re.sub(r"\s*[（(].*$", "", part)
            part = re.sub(r"\s*[:：].*$", "", part).strip()
            if part:
                candidates.append(part)
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _select_source_option(
    page,
    placeholder: str,
    rows: list[dict],
    field: str,
    *,
    contains: bool = False,
    exclude_source: bool = False,
) -> list[dict]:
    page.keyboard.press("Escape")
    if not page.locator(".keyword-select-popover:visible, .el-select-dropdown:visible").count():
        controls = page.locator(f"input[placeholder='{placeholder}']:visible")
        if controls.count():
            controls.first.click()
        else:
            label = page.get_by_text(placeholder, exact=True).first
            wrapper = label.locator(
                "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' el-select ')][1]"
            )
            if wrapper.count():
                wrapper.click()
            else:
                label.click(force=True)
    page.locator(".keyword-select-popover:visible, .el-select-dropdown:visible").last.wait_for(
        state="visible", timeout=10000
    )
    popover = page.locator(".keyword-select-popover:visible").last
    options = (
        popover.locator(".keyword-item")
        if popover.count()
        else page.locator(".el-select-dropdown__item:visible, [role='option']:visible")
    )
    search_candidates = list(
        dict.fromkeys(
            candidate for row in rows for candidate in _filter_value_candidates(str(row.get(field) or ""), field)
        )
    )
    popup_search = popover.locator("input:visible").first if popover.count() else page.locator("input:visible").last
    if popover.count() and popup_search.count() and popup_search.is_editable() and not exclude_source:
        for candidate in search_candidates:
            if options.count():
                break
            popup_search.fill(candidate)
            page.wait_for_timeout(300)
    try:
        options.first.wait_for(state="visible", timeout=15000)
        expect(options.first).to_have_text(re.compile(r"\S"), timeout=5000)
    except PlaywrightTimeoutError as exc:
        from modules.trae_test.utils.runtime_paths import runtime_dir

        screenshot_dir = runtime_dir("reports") / "sales_report_regression"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / f"{placeholder}-filter-options.png"), full_page=True)
        visible_inputs = page.locator("input:visible").evaluate_all(
            "elements => elements.map(element => ({placeholder: element.getAttribute('placeholder'), "
            "readonly: element.readOnly, valueLength: element.value.length}))"
        )
        raise AssertionError(
            f"{placeholder} filter menu did not expose option text "
            f"(visible_popover={page.locator('.keyword-select-popover:visible').count()}, "
            f"visible_element_dropdown={page.locator('.el-select-dropdown:visible').count()}, "
            f"option_count={options.count()}, visible_inputs={visible_inputs})"
        ) from exc
    option_texts = options.all_inner_texts()

    def _try_options(labels: list[str]) -> list[dict] | None:
        for option_text in labels:
            label = " ".join(option_text.split())
            if not label or label == "全部":
                continue
            expected = [
                row
                for row in rows
                if (
                    label in str(row.get(field) or "")
                    if contains
                    else " ".join(str(row.get(field) or "").split()) == label
                )
            ]
            if exclude_source:
                if expected:
                    continue
            elif not expected or len(expected) == len(rows):
                continue
            options.filter(has_text=label).first.click()
            return expected
        return None

    selected_rows = _try_options(option_texts)
    if selected_rows is not None:
        return selected_rows

    if popup_search.count() and popup_search.is_editable() and not exclude_source:
        for candidate in search_candidates:
            popup_search.fill("")
            popup_search.fill(candidate)
            page.wait_for_timeout(300)
            option_texts = options.all_inner_texts()
            selected_rows = _try_options(option_texts)
            if selected_rows is not None:
                return selected_rows

    if exclude_source:
        raise AssertionError(f"{placeholder} has no option outside the report's source values")
    if placeholder == "款期类型":
        from modules.trae_test.utils.runtime_paths import runtime_dir

        screenshot_dir = runtime_dir("reports") / "sales_report_regression"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / "term-filter-options.png"), full_page=True)
        normalized_options = {" ".join(value.split()) for value in option_texts}
        matching_source_rows = sum(" ".join(str(row.get(field) or "").split()) in normalized_options for row in rows)
        normalized_source_values = sorted(
            {
                re.sub(r"\d+", "#", " ".join(str(row.get(field) or "").split()))
                for row in rows
                if row.get(field) not in (None, "", [], {})
            }
        )
        raise AssertionError(
            f"{placeholder} options do not match source values "
            f"(visible_option_count={options.count()}, source_rows={len(rows)}, "
            f"matching_source_rows={matching_source_rows}, "
            f"source_values={normalized_source_values}, "
            f"visible_options={sorted(normalized_options)}, "
            f"screenshot=term-filter-options.png)"
        )
    raise AssertionError(f"{placeholder} options do not distinguish the source customers")


def _close(actual, expected: Decimal, *, field: str, row_number: int, dept_name: str) -> None:
    parsed = amount(actual)
    if abs(parsed - expected) > AMOUNT_TOLERANCE:
        raise AssertionError(
            f"{dept_name} payment row {row_number} field {field} differs from the source "
            f"by more than {AMOUNT_TOLERANCE} (report={parsed}, source={expected}, delta={parsed - expected})"
        )


@pytest.mark.api
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003838")
def test_latest_week_admin_can_read_the_sixth_group_snapshot(
    authenticated_http_client, api_base_url: str, config_manager
) -> None:
    """Pin test-environment write scenarios to the latest sixth-group report only."""
    assert config_manager.env == "test", "六组周报写入场景只允许在 TEST 环境执行"
    assert _role() == "admin", "Sixth-group snapshot discovery requires the administrator role"
    api = _api(authenticated_http_client, api_base_url)
    latest_start, report_rows = _latest_reports(api)
    matches = _sixth_group_reports(report_rows)
    assert len(matches) == 1, f"Expected one sixth-group report in week {latest_start}; found {len(matches)}"

    report_row = matches[0]
    report = api.get_report(report_row["id"])
    assert str(report.get("weekStartDate"))[:10] == latest_start
    detail_rows = report.get("detailList") or []
    assert detail_rows, "Latest sixth-group report has no detail rows"
    section_types = {str(row.get("sectionType")) for row in detail_rows}
    assert {"1", "3"} <= section_types, "Latest sixth-group report is missing main-customer or payment-abnormal rows"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.requirement("1003838")
def test_customer_detail_displays_payment_credit_for_sixth_group_sample(
    authenticated_http_client,
    api_base_url: str,
    logged_in_page,
    config_manager,
) -> None:
    assert config_manager.env in {"test", "uat"}
    assert _role() == "admin", "Customer detail sample selection requires the administrator role"
    api = _api(authenticated_http_client, api_base_url)
    _, reports = _latest_reports(api)
    report_row = _report_for_ui_scope(reports)
    report = api.get_report(report_row["id"])
    main_row = next(
        (row for row in report.get("detailList") or [] if str(row.get("sectionType")) == "1" and row.get("customerId")),
        None,
    )
    assert main_row, "Six-group report has no main-customer record with a customerId"
    customer_detail = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    customer_detail.navigate_to(f"/sales/salesSetting/StoreCustomerDetail/{main_row['customerId']}")
    payment_credit_label = logged_in_page.locator(".el-form-item__label").filter(has_text=re.compile(r"付款信用"))
    expect(payment_credit_label).to_have_count(1, timeout=30000)
    expect(payment_credit_label).to_be_visible()
    payment_credit_item = payment_credit_label.locator(
        "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' el-form-item ')][1]"
    )
    payment_credit_control = payment_credit_item.locator(".el-form-item__content .el-select")
    expect(payment_credit_control).to_be_visible()


def _business_oper_log_snapshot(session, api_base_url: str, business_key: str) -> tuple[int | None, tuple[str, ...]]:
    response = session.get(
        f"{api_base_url.rstrip('/')}/oms-admin/system/businessOperLog/list",
        params={"businessKey": business_key, "pageNum": 1, "pageSize": 10},
        timeout=(10, 45),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != 200:
        raise AssertionError("Customer business-operation log query returned an unsuccessful API envelope")
    data = payload.get("data")
    rows = payload.get("rows")
    total = payload.get("total")
    if isinstance(data, dict):
        rows = rows if isinstance(rows, list) else data.get("rows") or data.get("records")
        total = total if total is not None else data.get("total")
    elif isinstance(data, list):
        rows = rows if isinstance(rows, list) else data
    if not isinstance(rows, list):
        raise AssertionError("Customer business-operation log response is missing its row list")
    fingerprints = tuple(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows)
    try:
        total_count = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_count = None
    return total_count, fingerprints


def _report_payment_credit_widget(page, customer_no: str):
    row = page.locator(".virtual-pro-table__row:visible").filter(has_text=customer_no).first
    expect(row).to_be_visible(timeout=10000)
    placeholder = row.get_by_text("请选择付款信用", exact=True)
    if placeholder.count():
        return placeholder.first.locator(
            "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' report-select-preview ')][1]"
        )
    for label in ("优秀", "一般", "差劲"):
        selected = row.get_by_text(label, exact=True)
        if selected.count():
            return selected.first.locator(
                "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' report-select-preview ')][1]"
            )
    raise AssertionError("The report row has no recognizable payment-credit selector")


def _select_report_payment_credit(page, widget, label: str | None) -> None:
    if label is None:
        widget.hover()
        clear_control = widget.locator(".el-select__clear:visible")
        if clear_control.count():
            clear_control.first.click()
            return
        input_control = widget.locator("input").first
        if input_control.count():
            input_control.click()
            input_control.press("Control+a")
            input_control.press("Backspace")
        placeholder = widget.get_by_text("请选择付款信用", exact=True)
        expect(placeholder).to_be_visible(timeout=5000)
        return

    assert label in {"优秀", "一般", "差劲"}, f"Unsupported payment-credit label: {label}"
    widget.click()
    options = page.locator(".el-select-dropdown__item:visible")
    expect(options.filter(has_text=re.compile(rf"^{re.escape(label)}$"))).to_be_visible(timeout=5000)
    options.filter(has_text=re.compile(rf"^{re.escape(label)}$")).click()


def _save_report_payment_credit(
    page,
    *,
    override_customer_id: str | None = None,
    override_customer_no: str | None = None,
    override_credit: str | None = None,
) -> None:
    save_button = page.get_by_role("button", name="保存", exact=True).last
    expect(save_button).to_be_visible(timeout=10000)

    patched_rows = 0

    def _override_saved_credit(route) -> None:
        nonlocal patched_rows
        request = route.request
        if (
            override_customer_id
            and request.method.upper() in {"POST", "PUT", "PATCH"}
            and "queryworkplan" not in request.url.lower()
            and "/auth/" not in request.url.lower()
        ):
            try:
                payload = request.post_data_json
            except Exception:
                payload = None

            def _replace_credit(value) -> None:
                nonlocal patched_rows
                if isinstance(value, dict):
                    matches_customer = str(value.get("customerId") or "") == override_customer_id
                    matches_number = (
                        bool(override_customer_no) and str(value.get("customerNo") or "") == override_customer_no
                    )
                    if (matches_customer or matches_number) and "paymentCredit" in value:
                        value["paymentCredit"] = override_credit
                        patched_rows += 1
                    for child in value.values():
                        _replace_credit(child)
                elif isinstance(value, list):
                    for child in value:
                        _replace_credit(child)

            _replace_credit(payload)
            if patched_rows:
                route.continue_(post_data=json.dumps(payload, ensure_ascii=False))
                return
        route.continue_()

    page.route("**/*", _override_saved_credit)
    with page.expect_response(
        lambda response: "/oms-report/weekly/report" in response.url.lower()
        and response.request.method.upper() == "PUT",
        timeout=20000,
    ) as response_info:
        save_button.click()
    response = response_info.value
    page.unroute("**/*", _override_saved_credit)
    if override_customer_id:
        assert (
            patched_rows >= 1
        ), "The weekly-report save payload did not contain a matching customer paymentCredit field"
    payload = response.json()
    assert response.status == 200, f"Weekly report payment-credit save returned HTTP {response.status}"
    assert (
        isinstance(payload, dict) and payload.get("code") == 200
    ), "Weekly report payment-credit save returned an unsuccessful API envelope"


def _refresh_weekly_report_snapshot(page, report_id: str, api: WeeklyBusinessReportAPI) -> None:
    report_page = WeeklyBusinessReportPage(page)
    report_page.open_detail(report_id)
    button = page.get_by_role("button", name=re.compile("更新周报")).first
    expect(button).to_be_visible(timeout=10000)
    with page.expect_response(
        lambda response: "/oms-report/weekly/report/refreshReportById" in response.url
        and response.request.method.upper() == "PUT",
        timeout=45000,
    ) as response_info:
        button.click()
    response = response_info.value
    assert response.status == 200, f"Report refresh restore returned HTTP {response.status}"
    payload = response.json()
    assert (
        isinstance(payload, dict) and payload.get("code") == 200
    ), "Report refresh restore returned an unsuccessful API envelope"
    api.get_report(report_id)


def _customer_profile_payment_credit(
    page, config_manager, customer_id: str
) -> tuple[WeeklyBusinessReportPage, str | None]:
    customer_page = WeeklyBusinessReportPage(page, config=config_manager)
    customer_page.navigate_to(f"/sales/salesSetting/StoreCustomerDetail/{customer_id}")
    label = page.locator(".el-form-item__label").filter(has_text=re.compile(r"付款信用"))
    expect(label).to_have_count(1, timeout=30000)
    item = label.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' el-form-item ')][1]")
    control = item.locator(".el-form-item__content .el-select")
    expect(control).to_be_visible(timeout=10000)
    current = control.evaluate("""element => {
            const selected = element.querySelector('.el-select__selected-item');
            const input = element.querySelector('input');
            return (selected && selected.textContent || input && input.value || '').trim();
        }""")
    return customer_page, current if current in {"优秀", "一般", "差劲"} else None


def _set_customer_profile_payment_credit(page, config_manager, customer_id: str, label: str | None) -> None:
    _customer_page, _ = _customer_profile_payment_credit(page, config_manager, customer_id)
    form_label = page.locator(".el-form-item__label").filter(has_text=re.compile(r"付款信用"))
    item = form_label.locator(
        "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' el-form-item ')][1]"
    )
    control = item.locator(".el-form-item__content .el-select")
    if label is None:
        control.hover()
        clear_control = control.locator(".el-select__clear:visible")
        if clear_control.count():
            clear_control.first.click()
        else:
            input_control = control.locator("input").first
            input_control.click()
            input_control.press("Control+a")
            input_control.press("Backspace")
    else:
        control.click()
        options = page.locator(".el-select-dropdown__item:visible")
        expect(options.filter(has_text=re.compile(rf"^{re.escape(label)}$"))).to_be_visible(timeout=5000)
        options.filter(has_text=re.compile(rf"^{re.escape(label)}$")).click()

    save_button = page.get_by_role("button", name="保存", exact=True).last
    expect(save_button).to_be_visible(timeout=10000)
    with page.expect_response(
        lambda response: response.request.method.upper() in {"POST", "PUT", "PATCH"}
        and "/auth/" not in response.url.lower(),
        timeout=20000,
    ) as response_info:
        save_button.click()
    response = response_info.value
    assert response.status == 200, f"Customer payment-credit restore returned HTTP {response.status}"
    payload = response.json()
    assert (
        isinstance(payload, dict) and payload.get("code") == 200
    ), "Customer payment-credit restore returned an unsuccessful API envelope"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_weekly_payment_credit_change_updates_customer_and_logs(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    """Change a weekly credit and verify profile propagation/log creation; restore TEST data afterwards."""
    assert config_manager.env == "test", "付款信用写入回归只允许在 TEST 环境执行"
    assert _role() == "manager", "付款信用写入和业务日志核对使用六组组长账号"
    api = _api(authenticated_http_client, api_base_url)
    _, report_rows = _latest_reports(api)
    report_row = _report_for_ui_scope(report_rows)
    report_id = str(report_row["id"])
    report = api.get_report(report_id)
    current_week = str(report.get("weekStartDate") or report_row.get("weekStartDate") or "")[:10]
    assert current_week, "Latest sixth-group report has no week start date"
    previous_week = (date.fromisoformat(current_week) - timedelta(days=7)).isoformat()
    all_report_rows = api.list_reports(page_size=1000)
    previous_report_rows = [
        row
        for row in all_report_rows
        if str(row.get("weekStartDate") or "")[:10] == previous_week
        and str(row.get("deptName") or "") == str(report_row.get("deptName") or "")
    ]
    if len(previous_report_rows) != 1:
        pytest.skip(
            f"NO_SAMPLE: expected one previous-week report for the same group; found {len(previous_report_rows)}"
        )
    previous_report = api.get_report(previous_report_rows[0]["id"])
    source_row = next(
        (
            row
            for row in report.get("detailList") or []
            if str(row.get("sectionType")) == "1" and row.get("customerId") and row.get("customerNo")
        ),
        None,
    )
    assert source_row, "Latest six-group report has no main-customer payment-credit sample"
    customer_id = str(source_row["customerId"])
    previous_source_row = next(
        (
            row
            for row in previous_report.get("detailList") or []
            if str(row.get("sectionType")) == "1" and str(row.get("customerId")) == customer_id
        ),
        None,
    )
    if not previous_source_row:
        pytest.skip("NO_SAMPLE: the latest main-customer sample does not exist in the previous-week report")
    original_report_credit = source_row.get("paymentCredit")
    previous_report_credit = previous_source_row.get("paymentCredit")
    assert original_report_credit in (
        None,
        "",
        "优秀",
        "一般",
        "差劲",
    ), "Weekly report contains an unsupported payment-credit value; preserve data and review its mapping"
    original_report_label = original_report_credit if original_report_credit in {"优秀", "一般", "差劲"} else None
    original_detail_signature = Counter(
        (
            str(row.get("sectionType")),
            str(row.get("customerId") or ""),
            str(row.get("customerNo") or ""),
        )
        for row in report.get("detailList") or []
    )

    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    _original_profile_page, original_profile_credit = _customer_profile_payment_credit(
        logged_in_page, config_manager, customer_id
    )
    if original_profile_credit != original_report_label:
        # If a prior interrupted run left a report-only credit, align the shared TEST snapshot
        # with the existing customer value through the real save request before retrying.
        report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
        report_page.open_detail(report_id)
        report_page.select_tab("主要客户情况")
        _report_payment_credit_widget(logged_in_page, str(source_row["customerNo"]))
        _save_report_payment_credit(
            logged_in_page,
            override_customer_id=customer_id,
            override_customer_no=str(source_row["customerNo"]),
            override_credit=original_profile_credit,
        )
        aligned_report = api.get_report(report_id)
        aligned_credit = next(
            (
                row.get("paymentCredit")
                for row in aligned_report.get("detailList") or []
                if str(row.get("sectionType")) == "1" and str(row.get("customerId")) == customer_id
            ),
            None,
        )
        assert (
            aligned_credit in (None, "")
            if original_profile_credit is None
            else aligned_credit == original_profile_credit
        )
        pytest.skip("Existing report/customer credit mismatch was aligned; rerun against the restored TEST state")
    target_credit = next(
        (
            value
            for value in ("优秀", "一般", "差劲")
            if value != original_profile_credit and value != previous_report_credit
        ),
        None,
    )
    if target_credit is None:
        pytest.skip("NO_SAMPLE: no available credit value differs from both the profile and previous-week report")
    log_before = _business_oper_log_snapshot(authenticated_http_client, api_base_url, customer_id)
    restore_required = False

    def _open_credit_row():
        report_page.open_detail(report_id)
        report_page.select_tab("主要客户情况")
        return _report_payment_credit_widget(logged_in_page, str(source_row["customerNo"]))

    try:
        credit_widget = _open_credit_row()
        _select_report_payment_credit(logged_in_page, credit_widget, target_credit)
        restore_required = True
        _save_report_payment_credit(logged_in_page)

        report_after_credit = api.get_report(report_id)
        updated_detail_signature = Counter(
            (
                str(row.get("sectionType")),
                str(row.get("customerId") or ""),
                str(row.get("customerNo") or ""),
            )
            for row in report_after_credit.get("detailList") or []
        )
        assert (
            updated_detail_signature == original_detail_signature
        ), "Saving one payment-credit value removed or added unrelated report customer rows"
        weekly_report_credit_after_update = next(
            (
                row.get("paymentCredit")
                for row in report_after_credit.get("detailList") or []
                if str(row.get("sectionType")) == "1" and str(row.get("customerId")) == customer_id
            ),
            None,
        )
        weekly_report_credit_persisted = weekly_report_credit_after_update == target_credit
        _, updated_profile_credit = _customer_profile_payment_credit(logged_in_page, config_manager, customer_id)
        log_after_update = _business_oper_log_snapshot(authenticated_http_client, api_base_url, customer_id)
        before_count, before_rows = log_before
        after_count, after_rows = log_after_update
        added_log = (after_count is not None and before_count is not None and after_count > before_count) or bool(
            Counter(after_rows) - Counter(before_rows)
        )

        profile_updated = updated_profile_credit == target_credit
        print(
            "[weekly_report_payment_credit] "
            f"weekly_report_value_persisted={weekly_report_credit_persisted} "
            f"customer_profile_updated={profile_updated} first_change_logged={added_log} "
            f"previous_week_credit={previous_report_credit!r} target_credit={target_credit!r} "
            f"before_total={before_count} after_change_total={after_count} "
            f"before_rows={len(before_rows)} after_change_rows={len(after_rows)}"
        )
        assert weekly_report_credit_persisted and profile_updated and added_log, (
            "Weekly report payment-credit propagation/log contract failed "
            f"(report_credit_after={weekly_report_credit_after_update!r}, expected={target_credit!r}, "
            f"profile_before={original_profile_credit!r}, profile_after={updated_profile_credit!r}, "
            f"expected={target_credit!r}, first_change_logged={added_log}, "
            f"before_total={before_count}, after_change_total={after_count}, "
            f"before_rows={len(before_rows)}, after_change_rows={len(after_rows)})"
        )
    finally:
        if restore_required:
            _, restored_profile_credit = _customer_profile_payment_credit(logged_in_page, config_manager, customer_id)
            if restored_profile_credit != original_profile_credit:
                _set_customer_profile_payment_credit(
                    logged_in_page, config_manager, customer_id, original_profile_credit
                )
            _, final_profile_credit = _customer_profile_payment_credit(logged_in_page, config_manager, customer_id)
            assert (
                final_profile_credit == original_profile_credit
            ), "TEST customer payment-credit value was not restored after the regression"
            report_page.open_detail(report_id)
            report_page.select_tab("主要客户情况")
            _report_payment_credit_widget(logged_in_page, str(source_row["customerNo"]))
            _save_report_payment_credit(
                logged_in_page,
                override_customer_id=customer_id,
                override_customer_no=str(source_row["customerNo"]),
                override_credit=original_report_credit,
            )
            _refresh_weekly_report_snapshot(logged_in_page, report_id, api)
            restored_report = api.get_report(report_id)
            restored_credit = next(
                (
                    row.get("paymentCredit")
                    for row in restored_report.get("detailList") or []
                    if str(row.get("sectionType")) == "1" and str(row.get("customerId")) == customer_id
                ),
                None,
            )
            if original_report_credit in (None, ""):
                assert restored_credit in (None, ""), "Weekly report payment credit was not restored to blank"
            else:
                assert restored_credit == original_report_credit, "Weekly report payment credit was not restored"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_partial_weekly_report_save_keeps_omitted_customer_rows(
    authenticated_http_client, api_base_url, logged_in_page, config_manager
) -> None:
    """Send one existing detail row in a TEST report save and verify omitted rows remain stored."""
    assert config_manager.env == "test", "周报部分保存回归只允许在 TEST 环境执行"
    assert _role() == "manager", "周报部分保存回归使用六组组长账号"
    api = _api(authenticated_http_client, api_base_url)
    _, report_rows = _latest_reports(api)
    report_row = _report_for_ui_scope(report_rows)
    report_id = str(report_row["id"])
    report_before = api.get_report(report_id)
    original_details = report_before.get("detailList") or []
    assert (
        len(original_details) > 1
    ), "Latest six-group report needs multiple customer rows for partial-save verification"
    target_row = next(
        (
            row
            for row in original_details
            if str(row.get("sectionType")) == "1" and row.get("customerId") and row.get("customerNo")
        ),
        None,
    )
    assert target_row, "Latest six-group report has no main-customer row to save"
    target_customer_id = str(target_row["customerId"])

    def _signature(rows: list[dict]) -> Counter:
        return Counter(
            (
                str(row.get("sectionType")),
                str(row.get("customerId") or ""),
                str(row.get("customerNo") or ""),
            )
            for row in rows
        )

    original_signature = _signature(original_details)
    full_payload: dict | None = None
    submitted_detail_count = 0
    saved_partial_signature: Counter | None = None
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(report_id)
    report_page.select_tab("主要客户情况")

    def _submit_only_one_detail(route) -> None:
        nonlocal full_payload, submitted_detail_count
        request = route.request
        if request.method.upper() != "PUT" or "/oms-report/weekly/report" not in request.url.lower():
            route.continue_()
            return
        try:
            payload = json.loads(request.post_data or "")
        except (ValueError, TypeError):
            route.continue_()
            return
        detail_lists = []

        def _locate_details(node) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("detailList"), list):
                    detail_lists.append(node["detailList"])
                for child in node.values():
                    _locate_details(child)
            elif isinstance(node, list):
                for child in node:
                    _locate_details(child)

        _locate_details(payload)
        if not detail_lists:
            route.continue_()
            return
        full_payload = json.loads(json.dumps(payload, ensure_ascii=False))
        candidate_rows = [
            row
            for detail_list in detail_lists
            for row in detail_list
            if isinstance(row, dict)
            and str(row.get("customerId") or "") == target_customer_id
            and str(row.get("sectionType")) == "1"
        ]
        assert len(candidate_rows) == 1, "Weekly report save payload lacks a unique target main-customer row"
        target_only = [candidate_rows[0]]
        submitted_detail_count = len(target_only)

        def _replace_lists(node) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("detailList"), list):
                    node["detailList"] = target_only
                for child in node.values():
                    _replace_lists(child)
            elif isinstance(node, list):
                for child in node:
                    _replace_lists(child)

        _replace_lists(payload)
        route.continue_(post_data=json.dumps(payload, ensure_ascii=False))

    logged_in_page.route("**/*", _submit_only_one_detail)
    try:
        save_button = logged_in_page.get_by_role("button", name="保存", exact=True).last
        expect(save_button).to_be_visible(timeout=10000)
        with logged_in_page.expect_response(
            lambda response: "/oms-report/weekly/report" in response.url.lower()
            and response.request.method.upper() == "PUT",
            timeout=20000,
        ) as response_info:
            save_button.click()
        response = response_info.value
        assert response.status == 200, f"Partial weekly report save returned HTTP {response.status}"
        response_body = response.json()
        assert (
            isinstance(response_body, dict) and response_body.get("code") == 200
        ), "Partial weekly report save returned an unsuccessful API envelope"
        assert full_payload is not None, "Test did not capture the full payload needed to restore the report"
        assert submitted_detail_count < len(
            original_details
        ), "Test did not reduce the outgoing detail list before submitting the partial save"
        partial_result = api.get_report(report_id)
        saved_partial_signature = _signature(partial_result.get("detailList") or [])
        assert (
            saved_partial_signature == original_signature
        ), "Saving a subset of weekly report details deleted or altered omitted customer rows"
    finally:
        logged_in_page.unroute("**/*", _submit_only_one_detail)
        if full_payload is not None:
            restore_response = authenticated_http_client.put(
                f"{api_base_url.rstrip('/')}/oms-report/weekly/report",
                json=full_payload,
                timeout=(10, 90),
            )
            restore_response.raise_for_status()
            restore_body = restore_response.json()
            assert (
                isinstance(restore_body, dict) and restore_body.get("code") == 200
            ), "Full weekly report payload could not be restored after partial-save regression"
            restored = api.get_report(report_id)
            assert (
                _signature(restored.get("detailList") or []) == original_signature
            ), "Weekly report rows were not restored after partial-save regression"

    print(
        "[weekly_report_partial_save] "
        f"submitted_details={submitted_detail_count} original_details={len(original_details)} "
        f"rows_preserved={saved_partial_signature == original_signature}"
    )
    assert submitted_detail_count == 1, "Test did not submit exactly one customer detail row"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_tenth_group_export_name_and_contents(
    logged_in_page, authenticated_http_client, api_base_url, config_manager
) -> None:
    """Download the latest tenth-group report, validate the normalized filename and a source customer row."""
    assert config_manager.env == "test", "周报导出回归只允许在 TEST 环境执行"
    assert _role() == "admin", "周报导出回归使用管理员账号"
    api = _api(authenticated_http_client, api_base_url)
    latest_start, reports = _latest_reports(api)
    tenth_group_reports = [
        row for row in reports if re.search(r"(?:十|10)\s*组", re.sub(r"\s+", "", str(row.get("deptName") or "")))
    ]
    assert (
        len(tenth_group_reports) == 1
    ), f"Expected one tenth-group report for the latest week {latest_start}; found {len(tenth_group_reports)}"
    report_row = tenth_group_reports[0]
    report = api.get_report(report_row["id"])
    sample_customer = next(
        (str(row["customerNo"]) for row in report.get("detailList") or [] if row.get("customerNo")),
        None,
    )
    assert sample_customer, "Latest tenth-group report has no customer number to verify in the export"

    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.navigate_to("/sales/salesReport/weeklyBusinessReport")
    export_button = logged_in_page.get_by_role("button", name="导出周报", exact=True)
    expect(export_button.first).to_be_visible(timeout=20000)
    list_rows = logged_in_page.locator("tr.vxe-body--row:visible")
    matching_rows = [
        row
        for row in list_rows.all()
        if latest_start in " ".join(row.inner_text().split())
        and re.search(r"(?:十|10)\s*组", re.sub(r"\s+", "", row.inner_text()))
    ]
    assert len(matching_rows) == 1, (
        f"Weekly report list does not show exactly one tenth-group row for {latest_start}; "
        f"visible_rows={list_rows.count()}"
    )
    row_export = matching_rows[0].get_by_role("button", name="导出周报", exact=True)
    expect(row_export).to_be_visible(timeout=10000)

    with logged_in_page.expect_download(timeout=120000) as download_info:
        row_export.click()
    download = download_info.value
    filename = download.suggested_filename
    assert "业务 10 组" in filename, f"Export filename did not normalize tenth-group digits: {filename!r}"
    assert "业务十组" not in filename, "Export filename still contains Chinese numeral group naming"

    from modules.trae_test.utils.runtime_paths import runtime_dir

    destination = runtime_dir("downloads") / f"weekly_report_1003838_{uuid.uuid4().hex[:10]}.xlsx"
    try:
        download.save_as(str(destination))
        from openpyxl import load_workbook

        workbook = load_workbook(destination, read_only=True, data_only=True)
        try:
            workbook_values = [
                str(value)
                for worksheet in workbook.worksheets
                for row in worksheet.iter_rows(values_only=True)
                for value in row
                if value is not None
            ]
        finally:
            workbook.close()
        assert workbook_values, "Weekly report export workbook has no cell contents"
        assert any(
            sample_customer == value or sample_customer in value for value in workbook_values
        ), "Latest tenth-group export does not contain a customer number from its source weekly report"
    finally:
        destination.unlink(missing_ok=True)
    print(
        "[weekly_report_export] "
        f"week={latest_start} filename_normalized=True workbook_cells={len(workbook_values)} "
        "source_customer_present=True"
    )


@pytest.mark.api
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_latest_week_admin_reports_match_source_receivable_bills(
    authenticated_http_client, api_base_url: str, config_manager
) -> None:
    """Reconcile payment-abnormal rows in the latest week to source bills.

    This is read-only and uses each report's own end date, so it validates the
    saved historical snapshot instead of comparing it with today's open bills.
    WEEKLY_REPORT_GROUP_SCOPE=sixth limits a local run to the sixth group; CI defaults to all groups.
    """
    assert config_manager.env == "test", "需求1003838自动化周报回归仅允许在 TEST 环境执行"
    assert _role() == "admin", "Latest-week source-bill reconciliation requires the admin role"
    api = _api(authenticated_http_client, api_base_url)
    latest_start, report_rows = _latest_reports(api)
    group_scope = os.getenv("WEEKLY_REPORT_GROUP_SCOPE", "all").strip().lower()
    if group_scope == "sixth":
        report_rows = _sixth_group_reports(report_rows)
        assert len(report_rows) == 1, f"Expected one latest sixth-group report; found {len(report_rows)}"
    else:
        assert group_scope == "all", "WEEKLY_REPORT_GROUP_SCOPE must be 'all' or 'sixth'"

    source_cache: dict[tuple[str, str], list[dict]] = {}
    section_counts: Counter[str] = Counter()
    total_details = 0
    total_payment_rows = 0
    direct_currency_rows = 0
    fx_unverified_rows = 0
    fx_candidate_fields: set[str] = set()
    raw_balance_rows = 0
    source_mismatches: list[str] = []

    for report_row in report_rows:
        report_id = report_row.get("id")
        assert report_id, f"Latest report {latest_start} has no id"
        report = api.get_report(report_id)
        assert str(report.get("weekStartDate"))[:10] == latest_start
        report_end = str(report.get("weekEndDate") or "")[:10]
        assert report_end, f"Report {report_id} has no weekEndDate"
        details = report.get("detailList") or []
        total_details += len(details)
        section_counts.update(str(row.get("sectionType")) for row in details)

        by_section: dict[str, list[dict]] = {
            section_type: [row for row in details if str(row.get("sectionType")) == section_type]
            for section_type in REPORT_TYPES
        }
        main_rows = by_section["1"]
        main_avg = [amount(row.get("recentOneWeekAvgOrder")) for row in main_rows]
        assert main_avg == sorted(
            main_avg, reverse=True
        ), f"{report.get('deptName')} main-customer rows are not sorted by last-week average descending"
        for row_number, row in enumerate(main_rows, start=1):
            assert is_main_customer(
                row.get("recentOneWeekAvgOrder"), row.get("recentTwoWeekAvgOrder")
            ), f"{report.get('deptName')} main-customer row {row_number} has no positive average in either week"

        for row_number, row in enumerate(by_section["2"], start=1):
            assert is_declining_customer(
                row.get("recentOneWeekAvgOrder"), row.get("recentTwoWeekAvgOrder")
            ), f"{report.get('deptName')} declining-customer row {row_number} does not meet the strict decline rule"

        payment_rows = by_section["3"]
        payment_customer_nos = [str(row.get("customerNo") or "") for row in payment_rows]
        assert all(payment_customer_nos), f"{report.get('deptName')} has a payment row without customerNo"
        assert len(payment_customer_nos) == len(
            set(payment_customer_nos)
        ), f"{report.get('deptName')} splits a payment-abnormal customer into multiple rows"

        for row_number, row in enumerate(payment_rows, start=1):
            total_payment_rows += 1
            customer_no = str(row["customerNo"])
            customer_id = row.get("customerId")
            for field in MONEY_FIELDS:
                assert field in row, f"{report.get('deptName')} payment row {row_number} is missing {field}"
                try:
                    amount(row.get(field))
                except Exception as exc:
                    value = row.get(field)
                    value_type = type(value).__name__
                    value_length = len(str(value)) if value is not None else 0
                    raise AssertionError(
                        f"{report.get('deptName')} payment row {row_number} field {field} is not numeric "
                        f"(type={value_type}, length={value_length})"
                    ) from exc
            _close(
                row.get("receivableAmount"),
                amount(row.get("paidButNotReceiveAmount")) + amount(row.get("actualUnpaidAmount")),
                field="receivableAmount components",
                row_number=row_number,
                dept_name=str(report.get("deptName") or report_id),
            )
            _close(
                row.get("receivableAmount"),
                amount(row.get("shippedAmount")) + amount(row.get("unshippedAmount")),
                field="shipped + unshipped",
                row_number=row_number,
                dept_name=str(report.get("deptName") or report_id),
            )
            _close(
                row.get("receivableAmount"),
                amount(row.get("receivableInPeriodAmount")) + amount(row.get("receivableOutPeriodAmount")),
                field="in-period + out-of-period",
                row_number=row_number,
                dept_name=str(report.get("deptName") or report_id),
            )

            cache_key = (str(customer_id or ""), customer_no)
            if cache_key not in source_cache:
                raw_bills = api.list_customer_bills(
                    customer_id=customer_id,
                    customer_no=customer_no,
                    end_receivable_date=report_end,
                )
                raw_balance_rows += sum(
                    all(
                        field in bill and bill[field] not in (None, "")
                        for field in (
                            "receivableAmount",
                            "receivedAmount",
                            "paidButNotReceive",
                            "balanceAmount",
                        )
                    )
                    for bill in raw_bills
                )
                source_cache[cache_key] = payment_abnormal_bills(
                    raw_bills,
                    report_end=report_end,
                    customer_id=customer_id,
                    customer_no=customer_no,
                )
            bills = source_cache[cache_key]
            if not bills:
                source_mismatches.append(
                    f"{report.get('deptName')} customerNo={customer_no} has no matching source receivable bills"
                )
                continue

            dates = sorted(str(bill.get("receivableDate"))[:10] for bill in bills if bill.get("receivableDate"))
            expected_date = f"{dates[0]}~{dates[-1]}" if dates else report_end
            if str(row.get("pendingPaymentBillDate") or "") != expected_date:
                source_mismatches.append(
                    f"{report.get('deptName')} customerNo={customer_no} pendingPaymentBillDate "
                    f"report={row.get('pendingPaymentBillDate')} source={expected_date}"
                )

            source_currencies = {str(bill.get("currency")) for bill in bills if bill.get("currency")}
            report_currency = str(row.get("receivableCurrency") or "")
            if len(source_currencies) == 1 and (not report_currency or report_currency in source_currencies):
                direct_currency_rows += 1
                expected = direct_currency_expectation(bills, report_end=report_end)
                field_differences: dict[str, dict[str, str]] = {}
                for field in MONEY_FIELDS:
                    report_value = amount(row.get(field))
                    source_value = amount(expected[field])
                    delta = report_value - source_value
                    if abs(delta) > AMOUNT_TOLERANCE:
                        field_differences[field] = {
                            "report": str(report_value),
                            "source": str(source_value),
                            "delta": str(delta),
                        }
                if field_differences:
                    report_amounts = {name: str(amount(row.get(name))) for name in MONEY_FIELDS}
                    source_components = {
                        name: str(sum((amount(bill.get(name)) for bill in bills), Decimal("0")))
                        for name in (
                            "receivableAmount",
                            "receivedAmount",
                            "balanceAmount",
                            "paidButNotReceive",
                            "unpaid",
                        )
                    }
                    source_summary = {
                        "bill_count": len(bills),
                        "undated_bill_count": sum(not bill.get("receivableDate") for bill in bills),
                        "report_currency": report_currency,
                        "source_currencies": sorted(source_currencies),
                        "source_components": source_components,
                        "source_update_fields": {
                            field: max(
                                (str(bill.get(field) or "") for bill in bills if bill.get(field)),
                                default="",
                            )
                            for field in ("updateTime", "updateDate", "updatedAt", "modifyTime", "modifiedAt")
                            if any(bill.get(field) for bill in bills)
                        },
                        "report_time_fields": {
                            field: report[field]
                            for field in report
                            if any(token in field.lower() for token in ("updatetime", "updatedat", "modifytime"))
                        },
                    }
                    source_mismatches.append(
                        f"{report.get('deptName')} customerNo={customer_no} field_differences={field_differences}, "
                        f"report_amounts={report_amounts}, source_summary={source_summary}"
                    )
            else:
                fx_unverified_rows += 1
                fx_candidate_fields.update(
                    field
                    for bill in bills
                    for field in bill
                    if any(token in field.lower() for token in ("rate", "exchange", "currency"))
                )

    assert total_details > 0, f"Latest week {latest_start} has no report details"
    assert total_payment_rows > 0, f"Latest week {latest_start} has no payment-abnormal rows to reconcile"
    print(
        "[weekly_report] "
        f"week={latest_start} scope={group_scope} groups={len(report_rows)} details={total_details} "
        f"payment_rows={total_payment_rows} source_bills={sum(map(len, source_cache.values()))} "
        f"direct_currency_rows={direct_currency_rows} fx_unverified_rows={fx_unverified_rows} "
        f"fx_candidate_fields={sorted(fx_candidate_fields)} raw_balance_rows={raw_balance_rows} "
        f"sections={dict(section_counts)}"
    )
    if source_mismatches:
        print(f"[weekly_report_source_mismatches] count={len(source_mismatches)}")
        for mismatch in source_mismatches:
            print(f"[weekly_report_source_mismatch] {mismatch}")
    assert not source_mismatches, f"Latest-week source-bill reconciliation found {len(source_mismatches)} mismatch(es)"


@pytest.mark.api
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_sixth_group_small_order_samples_match_unshipped_readiness_ratio(
    authenticated_http_client, api_base_url: str, config_manager
) -> None:
    """Reconcile packing readiness with order-level stock marks for small TEST samples."""
    assert config_manager.env == "test", "订单配齐比例源数据核对只允许在 TEST 环境执行"
    assert _role() == "admin", "订单配齐比例源数据核对使用管理员账号"
    api = _api(authenticated_http_client, api_base_url)
    _, reports = _latest_reports(api)
    sixth_reports = _sixth_group_reports(reports)
    assert len(sixth_reports) == 1, f"Expected one latest sixth-group report; found {len(sixth_reports)}"
    report = api.get_report(sixth_reports[0]["id"])
    report_end = str(report.get("weekEndDate") or "")[:10]
    payment_rows = [
        row
        for row in report.get("detailList") or []
        if str(row.get("sectionType")) == "3" and row.get("customerId") and row.get("customerNo")
    ]
    assert report_end and payment_rows, "Latest sixth-group report has no cutoff date or payment rows"

    order_path = f"{api_base_url.rstrip('/')}/oms-admin/sales/order/batchListNew"
    small_samples: list[tuple[int, dict]] = []
    customer_order_counts: list[tuple[str, int]] = []
    for row in payment_rows:
        response = authenticated_http_client.post(
            order_path,
            json={
                "pageNum": 1,
                "pageSize": 1,
                "orderByColumn": "",
                "isAsc": "",
                "orderId": "",
                "orderNo": "",
                "customerId": row["customerId"],
                "customerNo": row["customerNo"],
                "orderStatus": "",
                "storeIds": "",
            },
            timeout=(10, 60),
        )
        response.raise_for_status()
        body = response.json()
        table = ((body.get("data") or {}).get("tableDataInfo") or {}) if isinstance(body, dict) else {}
        assert body.get("code") == 200, "Sales-order count query returned an unsuccessful business response"
        try:
            total = int(table.get("total"))
        except (TypeError, ValueError) as exc:
            raise AssertionError("Sales-order count response is missing a numeric total") from exc
        customer_order_counts.append((str(row["customerNo"]), total))
        if 0 <= total <= 100:
            small_samples.append((total, row))

    if not small_samples:
        pytest.skip("NO_SAMPLE: no sixth-group customer has a complete order set of 100 orders or fewer")

    verified_customers = 0
    verified_unshipped_orders = 0
    no_unshipped_order_samples = 0
    incomplete_source_customers: list[str] = []
    ratio_mismatches: list[str] = []
    for expected_total, row in sorted(
        small_samples,
        key=lambda candidate: (candidate[0], str(candidate[1].get("customerNo") or "")),
    ):
        response = authenticated_http_client.post(
            order_path,
            json={
                "pageNum": 1,
                "pageSize": max(100, expected_total),
                "orderByColumn": "",
                "isAsc": "",
                "orderId": "",
                "orderNo": "",
                "customerId": row["customerId"],
                "customerNo": row["customerNo"],
                "orderStatus": "",
                "storeIds": "",
            },
            timeout=(10, 60),
        )
        response.raise_for_status()
        body = response.json()
        table = ((body.get("data") or {}).get("tableDataInfo") or {}) if isinstance(body, dict) else {}
        orders = table.get("rows") if isinstance(table, dict) else None
        assert isinstance(orders, list), "Sales-order response is missing its row list"
        assert int(table.get("total") or 0) == expected_total == len(orders), (
            f"Sales-order page is incomplete for customer {row['customerNo']} "
            f"(expected={expected_total}, returned={len(orders)}, total={table.get('total')})"
        )
        assert all(
            str(order.get("customerId") or "") == str(row["customerId"])
            or str(order.get("customerNo") or "") == str(row["customerNo"])
            for order in orders
        ), f"Sales-order query returned another customer's order for {row['customerNo']}"
        assert all(
            str(order.get("deliveryStatus")) in {"0", "10", "20", "30"} for order in orders
        ), f"Sales-order response contains an unknown delivery status for {row['customerNo']}"

        # The source SQL defines unshipped orders by order_status, not deliveryStatus.
        unshipped_orders = [order for order in orders if is_weekly_report_unshipped_order(order.get("orderStatus"))]
        raw_order_numbers = [str(order.get("orderNo") or "") for order in unshipped_orders]
        order_numbers = list(dict.fromkeys(number for number in raw_order_numbers if number))
        if len(order_numbers) != len(unshipped_orders):
            incomplete_source_customers.append(str(row["customerNo"]))
            continue
        expected_ratio = unshipped_order_ready_percent_from_stock_marks(
            order.get("outStockMark") for order in unshipped_orders
        )
        if unshipped_orders and expected_ratio is None:
            incomplete_source_customers.append(str(row["customerNo"]))
            continue
        if unshipped_orders:
            verified_unshipped_orders += len(unshipped_orders)
        else:
            no_unshipped_order_samples += 1
            expected_ratio = unshipped_order_ready_percent([])

        report_value = row.get("unshippedOrderReadyRate")
        if expected_ratio is None:
            if report_value not in (None, ""):
                ratio_mismatches.append(
                    f"{row['customerNo']}: report={report_value!r}, source=None, unshipped_orders=0"
                )
        else:
            displayed = Decimal(str(report_value).strip().removesuffix("%"))
            if displayed != expected_ratio:
                ratio_mismatches.append(
                    f"{row['customerNo']}: report={displayed}, source={expected_ratio}, "
                    f"unshipped_orders={len(unshipped_orders)}"
                )
        verified_customers += 1

    print(
        "[weekly_report_readiness_ratio] "
        f"week={str(report.get('weekStartDate'))[:10]} verified_customers={verified_customers} "
        f"verified_unshipped_orders={verified_unshipped_orders} "
        f"no_unshipped_order_customers={no_unshipped_order_samples} "
        f"incomplete_source_customers={len(incomplete_source_customers)} "
        f"incomplete_customer_nos={incomplete_source_customers} mismatches={ratio_mismatches} "
        f"customer_order_counts={customer_order_counts}"
    )
    assert not ratio_mismatches, f"Weekly readiness ratio differs from SQL source order details: {ratio_mismatches}"
    if incomplete_source_customers:
        pytest.skip(
            "SOURCE_INCOMPLETE: sales-order list has missing or unknown outStockMark values for "
            f"customers {incomplete_source_customers}; cannot reconcile ratio to source SQL"
        )
    assert (
        verified_customers > 0
    ), "NO_SAMPLE: no small sixth-group customer had a complete source order/detail set for packing-ratio check"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003838")
def test_report_tabs_and_customer_searches_are_available(
    authenticated_http_client, api_base_url: str, logged_in_page, ui_base_url, config_manager
) -> None:
    """Check report tabs and verify customer-number filtering on populated sections."""
    assert config_manager.env in {"test", "uat"}
    api = _api(authenticated_http_client, api_base_url)
    _, rows = _latest_reports(api)
    report_row = _report_for_ui_scope(rows)
    report = api.get_report(report_row["id"])
    customer_nos_by_section: dict[str, list[str]] = {}
    for row in report.get("detailList") or []:
        section_type = str(row.get("sectionType"))
        customer_no = row.get("customerNo")
        if section_type in REPORT_TYPES and customer_no:
            customer_nos_by_section.setdefault(section_type, [])
            if str(customer_no) not in customer_nos_by_section[section_type]:
                customer_nos_by_section[section_type].append(str(customer_no))

    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(report_row["id"])

    visible_tabs = [" ".join(text.split()) for text in report_page.visible_tabs()]
    for name in WEEKLY_REPORT_TABS:
        assert name in visible_tabs, f"Missing weekly report tab: {name}"
    assert "全部" not in visible_tabs, "The retired 全部 tab must not return"

    observed_placeholders: set[str] = set()
    missing_customer_searches = []
    section_for_tab = {tab_name: section_type for section_type, tab_name in REPORT_TYPES.items()}
    searched_sections: set[str] = set()
    for tab_name in CUSTOMER_REPORT_TABS:
        report_page.select_tab(tab_name)
        placeholders = report_page.visible_input_placeholders() | report_page.visible_search_filter_labels()
        observed_placeholders.update(placeholders)
        if not placeholders.intersection({"客户名", "客户名称"}):
            missing_customer_searches.append(f"{tab_name}: customer name")
        if not placeholders.intersection({"客户编号", "客户编码"}):
            missing_customer_searches.append(f"{tab_name}: customer number")

        section_type = section_for_tab[tab_name]
        customer_nos = customer_nos_by_section.get(section_type, [])
        if customer_nos:
            customer_no = customer_nos[0]
            number_filter = logged_in_page.locator(
                "input[placeholder='客户编号']:visible, input[placeholder='客户编码']:visible"
            ).first
            expect(number_filter).to_be_visible(timeout=5000)
            initial_counts = _visible_exact_text_counts(logged_in_page, customer_nos)
            if len(customer_nos) > 1:
                assert sum(count > 0 for count in initial_counts.values()) > 1, (
                    f"{tab_name} has multiple source customers but the unfiltered UI did not render multiple rows "
                    f"(visible_source_customers={sum(count > 0 for count in initial_counts.values())})"
                )
            number_filter.fill(customer_no)
            logged_in_page.get_by_role("button", name="搜索", exact=True).click()
            filtered_counts = _visible_exact_text_counts(logged_in_page, customer_nos)
            assert filtered_counts[customer_no] == 1, (
                f"{tab_name} customer-number search did not retain exactly one matching customer "
                f"(initial_visible_counts={sorted(initial_counts.values())}, "
                f"filtered_visible_counts={sorted(filtered_counts.values())})"
            )
            assert all(count == 0 for code, count in filtered_counts.items() if code != customer_no), (
                f"{tab_name} customer-number search left other report customers visible "
                f"(initial_visible_counts={sorted(initial_counts.values())}, "
                f"filtered_visible_counts={sorted(filtered_counts.values())})"
            )
            searched_sections.add(section_type)
            reset = logged_in_page.get_by_role("button", name="重置", exact=True).first
            if reset.count() and reset.is_visible():
                reset.click()
                logged_in_page.wait_for_timeout(300)

        section_rows = [
            row
            for row in report.get("detailList") or []
            if str(row.get("sectionType")) == section_type and row.get("customerNo")
        ]
        if not section_rows:
            print(f"[weekly_report_customer_name_filter] tab={tab_name} status=NO_SAMPLE")
            continue
        all_codes = list(dict.fromkeys(str(row.get("customerNo")) for row in section_rows))
        name_rows = [row for row in section_rows if str(row.get("customerName") or "").strip()]
        assert name_rows, f"{tab_name} has no customer-name sample for filtering"
        name_candidates = list(dict.fromkeys(str(row.get("customerName")).strip() for row in name_rows))
        customer_name = min(
            name_candidates,
            key=lambda name: sum(str(row.get("customerName") or "").strip() == name for row in name_rows),
        )
        expected_name_codes = list(
            dict.fromkeys(
                str(row.get("customerNo"))
                for row in name_rows
                if str(row.get("customerName") or "").strip() == customer_name
            )
        )
        name_placeholder = next(
            (value for value in ("客户名", "客户名称") if value in placeholders),
            None,
        )
        assert name_placeholder, f"{tab_name} customer-name filter input is not visible"
        assert _choose_search_option(
            logged_in_page, name_placeholder, customer_name
        ), f"{tab_name} customer-name picker did not offer source customer {customer_name!r}"
        logged_in_page.get_by_role("button", name="搜索", exact=True).click()
        name_filtered_counts = _visible_exact_text_counts(logged_in_page, all_codes)
        assert all(name_filtered_counts.get(code, 0) == 1 for code in expected_name_codes), (
            f"{tab_name} customer-name search omitted a matching source customer "
            f"(name={customer_name!r}, expected={expected_name_codes}, visible={name_filtered_counts})"
        )
        assert all(name_filtered_counts.get(code, 0) == 0 for code in all_codes if code not in expected_name_codes), (
            f"{tab_name} customer-name search retained customers outside the matching source set "
            f"(name={customer_name!r}, expected={expected_name_codes}, visible={name_filtered_counts})"
        )
        reset = logged_in_page.get_by_role("button", name="重置", exact=True).first
        if reset.count() and reset.is_visible():
            reset.click()
            logged_in_page.wait_for_timeout(300)

    assert not missing_customer_searches, (
        f"Customer search controls are missing: {missing_customer_searches}; "
        f"observed placeholders={sorted(observed_placeholders)}"
    )
    assert searched_sections, "No populated customer section could be searched by customer number"
    assert observed_placeholders.intersection({"店长", "请选择店长"}), "No store-manager search was rendered"
    assert "款期类型" in observed_placeholders, "No payment-term-type search was rendered"
    assert "国家" in observed_placeholders, "No country search was rendered"

    payment_rows = [row for row in report.get("detailList") or [] if str(row.get("sectionType")) == "3"]
    assert len(payment_rows) > 1, "Six-group payment-abnormal tab lacks multiple customer samples"
    filter_cases = (
        ("付款异常客户", "款期类型", "accountPeriod", False, False),
        ("主要客户情况", "国家", "salesCountry", True, True),
        ("付款异常客户", "店长", "storeHeadNames", True, False),
    )
    for tab_name, placeholder, source_field, contains, exclude_source in filter_cases:
        report_page.select_tab(tab_name)
        source_rows = [
            row for row in report.get("detailList") or [] if str(row.get("sectionType")) == section_for_tab[tab_name]
        ]
        assert source_rows, f"No {tab_name} sample is available for the {placeholder} filter"
        target_row = next(
            (row for row in source_rows if row.get(source_field) not in (None, "", [], {})),
            None,
        )
        assert target_row is not None, f"Six-group {tab_name} rows lack values for {placeholder} filter"
        expected_rows = _select_source_option(
            logged_in_page,
            placeholder,
            source_rows,
            source_field,
            contains=contains,
            exclude_source=exclude_source,
        )
        expected_codes = list(
            dict.fromkeys(str(row.get("customerNo")) for row in expected_rows if row.get("customerNo"))
        )
        all_codes = list(dict.fromkeys(str(row.get("customerNo")) for row in source_rows if row.get("customerNo")))
        if exclude_source:
            assert not expected_codes, f"The chosen {placeholder} exclusion option unexpectedly matched report rows"
        else:
            assert expected_codes and len(expected_codes) < len(all_codes), (
                f"Six-group samples do not distinguish {placeholder} filtering "
                f"(expected={len(expected_codes)}, total={len(all_codes)})"
            )
        logged_in_page.get_by_role("button", name="搜索", exact=True).click()
        logged_in_page.wait_for_timeout(500)
        filtered_counts = _visible_exact_text_counts(logged_in_page, all_codes)
        if exclude_source:
            assert all(
                count == 0 for count in filtered_counts.values()
            ), f"{placeholder} filter retained customers after selecting an out-of-source option"
            reset = logged_in_page.get_by_role("button", name="重置", exact=True).first
            if reset.count() and reset.is_visible():
                reset.click()
                logged_in_page.wait_for_timeout(500)
            continue
        assert all(filtered_counts.get(code, 0) == 1 for code in expected_codes), (
            f"{placeholder} filter omitted a source-matching customer "
            f"(expected={len(expected_codes)}, visible={sum(count > 0 for count in filtered_counts.values())})"
        )
        assert all(
            filtered_counts.get(code, 0) == 0 for code in all_codes if code not in expected_codes
        ), f"{placeholder} filter retained a customer outside its source-matching set"
        reset = logged_in_page.get_by_role("button", name="重置", exact=True).first
        if reset.count() and reset.is_visible():
            reset.click()
            logged_in_page.wait_for_timeout(500)

    main_row = next(
        (row for row in report.get("detailList") or [] if str(row.get("sectionType")) == "1" and row.get("customerNo")),
        None,
    )
    if main_row:
        report_page.select_tab("主要客户情况")
        payment_credit_placeholder = logged_in_page.get_by_text("请选择付款信用", exact=True).first
        expect(payment_credit_placeholder).to_be_visible(timeout=10000)
        payment_credit_placeholder.click()
        credit_options = logged_in_page.locator(".el-select-dropdown__item:visible")
        expect(credit_options).to_have_count(3, timeout=10000)
        credit_option_labels = {" ".join(label.split()) for label in credit_options.all_inner_texts()}
        assert {"优秀", "一般", "差劲"} <= credit_option_labels, "Payment-credit select is missing a supported value"
        logged_in_page.keyboard.press("Escape")


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_empty_latest_sections_use_historical_sixth_group_samples_when_available(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    """Search older six-group reports for empty latest-week sections; report NO_SAMPLE when none exist."""
    assert config_manager.env == "test", "历史周报样本回退只允许在 TEST 环境执行"
    assert _role() == "admin", "历史周报样本回退使用管理员账号"
    api = _api(authenticated_http_client, api_base_url)
    latest_start, latest_rows = _latest_reports(api)
    latest_report_row = _report_for_ui_scope(latest_rows)
    latest_report = api.get_report(latest_report_row["id"])
    detail_cache = {str(latest_report_row["id"]): latest_report}
    latest_section_types = {
        str(row.get("sectionType")) for row in latest_report.get("detailList") or [] if row.get("customerNo")
    }
    target_types = ("2", "4", "5")
    missing_types = [section_type for section_type in target_types if section_type not in latest_section_types]
    if not missing_types:
        print(
            "[weekly_report_historical_section_sample] "
            f"latest_week={latest_start} status=LATEST_HAS_ALL_TARGET_SECTIONS"
        )
        return

    report_rows: list[dict] = []
    page_num = 1
    page_size = 1000
    while page_num <= 20:
        page_rows = api.list_reports(page_num=page_num, page_size=page_size)
        report_rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        page_num += 1
    assert page_num <= 20, "Historical weekly-report lookup reached its bounded pagination limit"

    historical_sixth_group = sorted(
        _sixth_group_reports(report_rows),
        key=lambda row: str(row.get("weekStartDate") or "")[:10],
        reverse=True,
    )
    unique_weeks: set[str] = set()
    recent_sixth_group_reports = []
    for row in historical_sixth_group:
        week_start = str(row.get("weekStartDate") or "")[:10]
        if not week_start or week_start in unique_weeks:
            continue
        unique_weeks.add(week_start)
        recent_sixth_group_reports.append(row)
        if len(recent_sixth_group_reports) == 52:
            break

    samples: dict[str, tuple[dict, list[dict]]] = {}
    for section_type in missing_types:
        for row in recent_sixth_group_reports:
            report_id = str(row["id"])
            if report_id not in detail_cache:
                detail_cache[report_id] = api.get_report(row["id"])
            section_rows = [
                detail
                for detail in detail_cache[report_id].get("detailList") or []
                if str(detail.get("sectionType")) == section_type and detail.get("customerNo")
            ]
            if section_rows:
                samples[section_type] = (row, section_rows)
                break

    for section_type in missing_types:
        tab_name = REPORT_TYPES[section_type]
        sample = samples.get(section_type)
        if sample is None:
            print(
                "[weekly_report_historical_section_sample] "
                f"section={tab_name} status=NO_SAMPLE "
                f"searched_sixth_group_weeks={len(recent_sixth_group_reports)}"
            )
            continue

        report_row, section_rows = sample
        report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
        report_page.open_detail(report_row["id"])
        report_page.select_tab(tab_name)
        customer_codes = list(dict.fromkeys(str(row["customerNo"]) for row in section_rows))
        number_placeholder = next(
            (
                placeholder
                for placeholder in ("客户编号", "客户编码")
                if placeholder
                in (report_page.visible_input_placeholders() | report_page.visible_search_filter_labels())
            ),
            None,
        )
        assert number_placeholder, f"Historical {tab_name} sample has no customer-number search control"
        number_input = logged_in_page.locator(f"input[placeholder='{number_placeholder}']:visible").first
        number_input.fill(customer_codes[0])
        logged_in_page.get_by_role("button", name="搜索", exact=True).click()
        number_counts = _visible_exact_text_counts(logged_in_page, customer_codes)
        assert number_counts.get(customer_codes[0], 0) == 1, (
            f"Historical {tab_name} customer-number search did not retain its matching row "
            f"(visible_matches={sum(value > 0 for value in number_counts.values())})"
        )
        assert all(
            number_counts.get(code, 0) == 0 for code in customer_codes[1:]
        ), f"Historical {tab_name} customer-number search retained nonmatching customers"

        reset = logged_in_page.get_by_role("button", name="重置", exact=True).first
        if reset.count() and reset.is_visible():
            reset.click()
            logged_in_page.wait_for_timeout(300)

        named_rows = [row for row in section_rows if str(row.get("customerName") or "").strip()]
        assert named_rows, f"Historical {tab_name} section has no customer-name sample"
        name_counts = Counter(str(row["customerName"]).strip() for row in named_rows)
        customer_name = min(name_counts, key=name_counts.get)
        expected_name_codes = list(
            dict.fromkeys(
                str(row["customerNo"]) for row in named_rows if str(row["customerName"]).strip() == customer_name
            )
        )
        placeholders = report_page.visible_input_placeholders() | report_page.visible_search_filter_labels()
        name_placeholder = next((value for value in ("客户名", "客户名称") if value in placeholders), None)
        assert name_placeholder and _choose_search_option(
            logged_in_page, name_placeholder, customer_name
        ), f"Historical {tab_name} customer-name search did not offer the source sample"
        logged_in_page.get_by_role("button", name="搜索", exact=True).click()
        name_counts_by_code = _visible_exact_text_counts(logged_in_page, customer_codes)
        assert all(
            name_counts_by_code.get(code, 0) == 1 for code in expected_name_codes
        ), f"Historical {tab_name} customer-name search omitted matching source customers"
        assert all(
            name_counts_by_code.get(code, 0) == 0 for code in customer_codes if code not in expected_name_codes
        ), f"Historical {tab_name} customer-name search retained nonmatching customers"
        print(
            "[weekly_report_historical_section_sample] "
            f"section={tab_name} status=FILTERS_VERIFIED "
            f"week={str(report_row.get('weekStartDate'))[:10]} samples={len(section_rows)}"
        )


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003838")
def test_payment_abnormal_tab_renders_all_required_amount_columns(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    assert config_manager.env in {"test", "uat"}
    api = _api(authenticated_http_client, api_base_url)
    _, rows = _latest_reports(api)
    report_row = _report_for_ui_scope(rows)
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(report_row["id"])
    report_page.select_tab("付款异常客户")
    rendered_text = logged_in_page.locator("body").inner_text()
    expected_columns = (
        "上周日均单量",
        "已付未到账金额",
        "实际未付金额",
        "应收货款",
        "待付款账单日期",
        "款期类型",
        "已发货金额",
        "未发货金额",
        "未发货订单配齐比例",
    )
    missing = [column for column in expected_columns if column not in rendered_text]
    assert not missing, f"Payment-abnormal report is missing columns: {missing}"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003838")
def test_ctrl_f_finds_customer_numbers_across_populated_report_sections(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    """Use the report's Ctrl+F control to find a customer number from each populated section."""
    assert config_manager.env in {"test", "uat"}
    api = _api(authenticated_http_client, api_base_url)
    _, rows = _latest_reports(api)
    report_row = _report_for_ui_scope(rows)
    report_id = report_row["id"]
    report = api.get_report(report_id)
    detail_rows = report.get("detailList") or []
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)

    report_page.open_detail(report_id)
    representative_customer_nos: dict[str, str] = {}
    for row in detail_rows:
        section_type = str(row.get("sectionType"))
        customer_no = row.get("customerNo")
        if section_type in REPORT_TYPES and customer_no:
            representative_customer_nos.setdefault(section_type, str(customer_no))

    assert representative_customer_nos, "Latest weekly report has no customer rows to search"
    search = report_page.open_ctrl_f_search()
    counter = logged_in_page.get_by_text(re.compile(r"^\d+/\d+$"), exact=True).first
    for section_type, customer_no in representative_customer_nos.items():
        search.fill(customer_no)
        expect(counter).to_have_text(re.compile(r"^[1-9]\d*/[1-9]\d*$"), timeout=10000)


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_ctrl_f_finds_all_customer_numbers_and_visible_report_values_in_six_group(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    """Search all source customer numbers and every source value rendered in the selected tab."""
    assert config_manager.env == "test", "完整 Ctrl+F 内容回归只允许在 TEST 环境执行"
    assert _role() == "admin", "完整 Ctrl+F 内容回归使用管理员读取六组周报"
    api = _api(authenticated_http_client, api_base_url)
    _, rows = _latest_reports(api)
    report_id = _report_for_ui_scope(rows)["id"]
    report = api.get_report(report_id)
    detail_rows = report.get("detailList") or []
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(report_id)
    logged_in_page.wait_for_timeout(750)

    search_values: set[str] = set()
    section_for_tab = {tab_name: section_type for section_type, tab_name in REPORT_TYPES.items()}
    for row in detail_rows:
        customer_no = row.get("customerNo")
        if customer_no:
            search_values.add(str(customer_no).strip())

    for tab_name in CUSTOMER_REPORT_TABS:
        report_page.select_tab(tab_name)
        logged_in_page.wait_for_timeout(400)
        body_text = " ".join(logged_in_page.locator("body").inner_text().split())
        section_type = section_for_tab[tab_name]
        section_rows = [row for row in detail_rows if str(row.get("sectionType")) == section_type]
        for row in section_rows:
            for field, value in row.items():
                field_name = field.lower()
                if (
                    value in (None, "", [], {})
                    or field_name == "sectiontype"
                    or field_name.endswith("id")
                    or any(
                        token in field_name for token in ("createtime", "updatetime", "modifytime", "delete", "flag")
                    )
                ):
                    continue
                candidates: set[str] = set()
                if isinstance(value, str):
                    candidates.add(" ".join(value.split()))
                elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    candidates.add(str(value).strip())
                    if "amount" in field_name or "percent" in field_name or "ratio" in field_name:
                        numeric = amount(value)
                        candidates.add(f"{numeric:.2f}")
                        candidates.add(f"{numeric:.2f}%")
                elif isinstance(value, (list, tuple)):
                    candidates.update(" ".join(str(item).split()) for item in value if isinstance(item, str))
                for candidate in candidates:
                    if len(candidate) >= 2 and candidate in body_text:
                        search_values.add(candidate)

    report_page.select_tab("工作计划")
    logged_in_page.wait_for_timeout(400)
    for value in logged_in_page.locator("textarea:visible").evaluate_all(
        "elements => elements.map(element => element.value || '')"
    ):
        normalized = " ".join(value.split())
        if len(normalized) >= 2:
            search_values.add(normalized)

    assert search_values, "No source customer numbers or rendered report/work-plan text was available to search"
    search = report_page.open_ctrl_f_search()
    counter = logged_in_page.get_by_text(re.compile(r"^\d+/\d+$"), exact=True).first
    missing = []
    for value in sorted(search_values):
        search.fill(value)
        try:
            expect(counter).to_have_text(re.compile(r"^[1-9]\d*/[1-9]\d*$"), timeout=2500)
        except AssertionError:
            missing.append(value[:120])
    assert not missing, (
        f"Ctrl+F did not find {len(missing)} of {len(search_values)} rendered report/work-plan values; "
        f"examples={missing[:10]}"
    )
    print(
        f"[weekly_report_ctrl_f] report_id={report_id} source_details={len(detail_rows)} "
        f"customer_numbers={len({str(row.get('customerNo')) for row in detail_rows if row.get('customerNo')})} "
        f"searched_values={len(search_values)}"
    )


@pytest.mark.ui
@pytest.mark.auth
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003838")
def test_work_plan_selector_is_scoped_to_the_configured_role(
    authenticated_http_client,
    administrator_http_client,
    api_base_url: str,
    logged_in_page,
    config_manager,
) -> None:
    """Verify managers/admins can select multiple people and sellers only themselves."""
    assert config_manager.env in {"test", "uat"}
    role = _role()
    api = _api(authenticated_http_client, api_base_url)
    latest_start, rows = _latest_reports(api)
    admin_api = api if role == "admin" else _api(administrator_http_client, api_base_url)
    admin_latest_start, admin_rows = _latest_reports(admin_api)
    assert latest_start == admin_latest_start, "Role and administrator are not reading the same latest week"

    user_report_row = _report_for_ui_scope(rows)
    report_key = str(user_report_row.get("deptId") or user_report_row.get("id"))
    admin_report_row = next(
        (row for row in admin_rows if str(row.get("deptId") or row.get("id")) == report_key),
        None,
    )
    assert admin_report_row is not None, "Administrator has no matching business-group weekly report"
    user_report = api.get_report(user_report_row["id"])
    admin_report = admin_api.get_report(admin_report_row["id"])
    user_customer_ids = {
        str(row.get("customerId") or row.get("customerNo"))
        for row in user_report.get("detailList", [])
        if str(row.get("sectionType")) in REPORT_TYPES
    }
    admin_customer_ids = {
        str(row.get("customerId") or row.get("customerNo"))
        for row in admin_report.get("detailList", [])
        if str(row.get("sectionType")) in REPORT_TYPES
    }
    assert user_customer_ids, f"{role} cannot access any customer rows in the latest weekly report"
    assert user_customer_ids <= admin_customer_ids, f"{role} can see customer rows absent from the administrator report"
    if role == "sales":
        assert (
            user_customer_ids < admin_customer_ids
        ), "Salesperson sees the full business-group customer set; salesperson customer scope is not restricted"

    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(user_report_row["id"])
    report_page.select_tab("工作计划")
    edit_content = logged_in_page.get_by_text("填写内容", exact=True)
    if edit_content.count() and edit_content.first.is_visible():
        edit_content.first.click()
    assert logged_in_page.get_by_text("填写人", exact=True).is_visible()

    selector = report_page.work_plan_person_selector()
    assert selector.count() and selector.is_visible(), "Work-plan assignee selector is missing or hidden"
    selector.click()
    person_input = logged_in_page.locator("input[placeholder*='选择人员']:visible").first
    if person_input.count():
        person_input.click()
        person_input.press("ArrowDown")
        person_input.press("Enter")
    popover = logged_in_page.locator(".keyword-select-popover:visible")
    popover.wait_for(state="visible", timeout=10000)
    options = popover.locator(".keyword-item")
    option_count = options.count()
    assert option_count >= 1, "Work-plan assignee list is empty"
    if role in {"admin", "manager"}:
        assert option_count > 1, f"{role} cannot select another person for the work plan"
        current_value = " ".join(selector.inner_text().split())
        candidate = next(
            (option for option in options.all() if " ".join(option.inner_text().split()) != current_value),
            None,
        )
        assert candidate is not None, f"{role} has no distinct work-plan member to inspect"
        selected_person = " ".join(candidate.inner_text().split())
        with logged_in_page.expect_response(
            lambda response: "queryworkplan" in response.url.lower(), timeout=15000
        ) as plan_response_info:
            candidate.click()
        plan_response = plan_response_info.value
        assert plan_response.status == 200, f"{role} member work-plan query returned HTTP {plan_response.status}"
        response_body = plan_response.json()
        assert (
            isinstance(response_body, dict) and response_body.get("code") == 200
        ), f"{role} member work-plan query returned an unsuccessful API envelope"
        assert selected_person and selected_person in " ".join(
            selector.inner_text().split()
        ), f"{role} work-plan selector did not retain the selected member"
    else:
        assert option_count == 1, f"sales account can select {option_count} work-plan assignees instead of itself"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_current_user_work_plan_save_is_visible_to_admin_and_restored(
    browser: Browser,
    authenticated_http_client,
    administrator_http_client,
    api_base_url: str,
    logged_in_page,
    config_manager,
) -> None:
    """Write the current manager/salesperson plan, verify reload/admin visibility, and restore it."""
    assert config_manager.env == "test", "工作计划写入回归只允许在 TEST 环境执行"
    current_role = _role()
    assert current_role in {"manager", "sales"}, "工作计划写入回归使用六组组长或业务员账号"

    from modules.auto_test.core.secret_provider import get_secret
    from modules.auto_test.pages.login_page import LoginPage

    manager_api = _api(authenticated_http_client, api_base_url)
    _, report_rows = _latest_reports(manager_api)
    report_row = _report_for_ui_scope(report_rows)
    report_id = str(report_row["id"])
    manager_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)

    def _manager_name_from_header(page) -> str | None:
        lines = [line.strip() for line in page.locator("body").inner_text().splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if "业务主管" not in line:
                continue
            value = re.split(r"[:：]", line, maxsplit=1)
            if len(value) == 2 and value[1].strip() not in {"", "-", "—"}:
                return value[1].strip()
            if index + 1 < len(lines) and lines[index + 1] not in {"-", "—"}:
                return lines[index + 1]
        return None

    def _open_and_select_person(
        page, report_page: WeeklyBusinessReportPage, candidates: list[str], *, selector_role: str | None = None
    ):
        report_page.open_detail(report_id)
        report_page.select_tab("工作计划")
        selector = report_page.work_plan_person_selector()
        effective_role = selector_role or current_role
        if effective_role in {"manager", "sales"}:
            # The page defaults to the logged-in employee. Keep that selection: choosing a member
            # from the dropdown switches the plan to read-only for a manager/salesperson.
            selected_name = " ".join(selector.inner_text().split())
            assert selected_name, f"{effective_role} page did not default the assignee to the current user"
            edit_content = page.get_by_text("填写内容", exact=True)
            if edit_content.count() and edit_content.first.is_visible():
                edit_content.first.click()
        else:
            selector.click()
            popover = page.locator(".keyword-select-popover:visible")
            popover.wait_for(state="visible", timeout=10000)
            search = popover.locator("input:visible").first
            options = popover.locator(".keyword-item")
            labels = [" ".join(label.split()) for label in options.all_inner_texts()]
            selected_name = None
            for candidate in candidates:
                if search.count() and search.is_editable():
                    search.fill(candidate)
                    page.wait_for_timeout(300)
                labels = [" ".join(label.split()) for label in options.all_inner_texts()]
                matches = [label for label in labels if label == candidate]
                if not matches:
                    matches = [label for label in labels if candidate and candidate in label]
                if len(matches) != 1:
                    continue
                selected_name = matches[0]
                break
            if selected_name:
                option = options.filter(has_text=re.compile(re.escape(selected_name)))
                expect(option).to_have_count(1, timeout=5000)
                option.click()
        assert selected_name, (
            f"Could not uniquely match the current six-group {current_role} to a work-plan assignee; "
            f"candidate_count={len(candidates)}"
        )
        textareas = page.locator("textarea:visible")
        if effective_role in {"manager", "sales"}:
            expect(textareas).to_have_count(4, timeout=10000)
            for index in range(textareas.count()):
                expect(textareas.nth(index)).to_be_enabled(timeout=10000)
        return textareas, selected_name

    def _save_plan(page, textareas, values: list[str], request_log: list[tuple[str, str]]) -> None:
        for index, value in enumerate(values):
            textareas.nth(index).fill(value)
        save_button = page.get_by_role("button", name="保存", exact=True)
        expect(save_button).to_be_visible()
        start_count = len(request_log)
        with page.expect_response(
            lambda response: response.request.method.upper() in {"POST", "PUT", "PATCH"}
            and "queryworkplan" not in response.url.lower()
            and any(token in response.url.lower() for token in ("weekly", "workplan", "work_plan", "plan")),
            timeout=15000,
        ) as save_response_info:
            save_button.click()
        save_response = save_response_info.value
        assert save_response.status == 200, (
            f"工作计划保存接口返回 HTTP {save_response.status}: " f"{save_response.url.split('?', 1)[0]}"
        )
        save_payload = save_response.json()
        assert isinstance(save_payload, dict) and save_payload.get("code") == 200, (
            "工作计划保存接口业务响应失败: " f"{save_response.url.split('?', 1)[0]}"
        )
        new_writes = request_log[start_count:]
        assert any(method in {"POST", "PUT", "PATCH"} for method, _ in new_writes), "工作计划保存没有触发写请求"

    manager_page.open_detail(report_id)
    report_snapshot = manager_api.get_report(report_id)
    manager_candidates = []
    header_name = _manager_name_from_header(logged_in_page)
    if header_name:
        manager_candidates.append(header_name)
    for source in (report_row, report_snapshot):
        for key, value in source.items():
            if any(token in key.lower() for token in ("manager", "leader", "principal", "owner", "head", "user")):
                if isinstance(value, str) and value.strip() not in {"", "-", "—"}:
                    manager_candidates.append(value.strip())
    login_name = os.getenv("TEST_USERNAME", "").strip()
    if login_name:
        manager_candidates.append(login_name)
    manager_candidates = list(dict.fromkeys(manager_candidates))
    assert manager_candidates, "No manager identity candidate is available for safe work-plan selection"
    request_log: list[tuple[str, str]] = []
    work_plan_urls: list[str] = []
    work_plan_response_markers: list[bool] = []

    def _capture_plan_write(request) -> None:
        url = request.url.lower()
        if (
            "queryworkplan" not in url
            and request.method.upper() in {"POST", "PUT", "PATCH"}
            and any(token in url for token in ("weekly", "workplan", "work_plan", "plan"))
        ):
            request_log.append((request.method.upper(), request.url.split("?", 1)[0]))
        if "queryworkplan" in url:
            work_plan_urls.append(request.url)

    def _capture_manager_plan_response(response) -> None:
        if "queryworkplan" not in response.url.lower():
            return
        try:
            work_plan_response_markers.append(marker in response.text())
        except Exception:
            work_plan_response_markers.append(False)

    logged_in_page.on("request", _capture_plan_write)
    logged_in_page.on("response", _capture_manager_plan_response)
    baseline_values: list[str] | None = None
    restore_required = False
    marker = f"自动化回归1003838-{current_role}-{uuid.uuid4().hex[:10]}"

    try:
        textareas, selected_manager = _open_and_select_person(logged_in_page, manager_page, manager_candidates)
        baseline_values = textareas.evaluate_all("elements => elements.map(element => element.value || '')")
        assert len(baseline_values) == 4
        updated_values = list(baseline_values)
        updated_values[0] = f"{baseline_values[0]}\n{marker}".strip()
        _save_plan(logged_in_page, textareas, updated_values, request_log)
        restore_required = True

        textareas, selected_manager = _open_and_select_person(logged_in_page, manager_page, [selected_manager])
        expect(textareas.first).to_have_value(updated_values[0], timeout=10000)
        assert marker in textareas.first.input_value(), "Manager work plan did not persist after page reload"
        assert work_plan_urls, "Reload did not issue a work-plan query request"
        assert any(work_plan_response_markers), "Reloaded work-plan API response does not contain the saved marker"

        plan_search = manager_page.open_ctrl_f_search()
        plan_search.fill(marker)
        plan_search_counter = logged_in_page.get_by_text(re.compile(r"^\d+/\d+$"), exact=True).first
        expect(plan_search_counter).to_have_text(re.compile(r"^[1-9]\d*/[1-9]\d*$"), timeout=10000)

        admin_username = get_secret("ADMIN_USERNAME", environment=config_manager.env)
        admin_password = get_secret("ADMIN_PASSWORD", environment=config_manager.env)
        assert admin_username and admin_password, "管理员凭证缺少，无法验证工作计划跨角色查看"
        admin_context = browser.new_context()
        try:
            admin_page = admin_context.new_page()
            assert LoginPage(admin_page, config=config_manager).login(
                admin_username, admin_password
            ), "管理员登录失败，无法验证工作计划跨角色查看"
            admin_plan_responses: list[str] = []

            def _capture_admin_plan_response(response) -> None:
                if "queryworkplan" in response.url.lower():
                    try:
                        admin_plan_responses.append(response.text())
                    except Exception:
                        admin_plan_responses.append("")

            admin_page.on("response", _capture_admin_plan_response)
            admin_report_page = WeeklyBusinessReportPage(admin_page, config=config_manager)
            admin_textareas, _ = _open_and_select_person(
                admin_page, admin_report_page, [selected_manager], selector_role="admin"
            )
            admin_page.wait_for_timeout(500)
            admin_values = admin_textareas.evaluate_all("elements => elements.map(element => element.value || '')")
            admin_body_contains_marker = marker in admin_page.locator("body").inner_text()
            if marker not in admin_values and not admin_body_contains_marker and work_plan_urls:
                direct_admin_response = administrator_http_client.get(work_plan_urls[-1], timeout=(10, 60))
                assert direct_admin_response.status_code == 200, "管理员工作计划查询接口未返回 HTTP 200"
                admin_plan_responses.append(direct_admin_response.text)
            admin_api_contains_marker = any(marker in body for body in admin_plan_responses)
            assert marker in admin_values or admin_body_contains_marker, (
                "管理员页面没有显示组长保存的工作计划 "
                f"(admin_query_contains_marker={admin_api_contains_marker}, "
                f"admin_query_count={len(admin_plan_responses)}, manager_query_count={len(work_plan_urls)})"
            )
        finally:
            admin_context.close()
    finally:
        if restore_required and baseline_values is not None:
            restored_fields, _ = _open_and_select_person(logged_in_page, manager_page, [selected_manager])
            _save_plan(logged_in_page, restored_fields, baseline_values, request_log)
            verified_fields, _ = _open_and_select_person(logged_in_page, manager_page, [selected_manager])
            restored_values = verified_fields.evaluate_all("elements => elements.map(element => element.value || '')")
            assert restored_values == baseline_values, "工作计划回归结束后未能恢复原始内容"


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_sales_average_threshold_is_remembered_after_search_and_reload(
    authenticated_http_client,
    api_base_url: str,
    logged_in_page,
    config_manager,
) -> None:
    """Save the numeric search preference, reload, verify it, and restore the prior value."""
    assert config_manager.env == "test", "搜索数字记忆回归只允许在 TEST 环境执行"
    assert _role() == "manager", "搜索数字记忆回归必须使用六组组长账号"
    api = _api(authenticated_http_client, api_base_url)
    _, reports = _latest_reports(api)
    report_row = _report_for_ui_scope(reports)
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_id = report_row["id"]
    report_page.open_detail(report_id)
    report_page.select_tab("主要客户情况")

    threshold = logged_in_page.locator("input[placeholder='非负整数']:visible").first
    expect(threshold).to_be_visible(timeout=10000)
    original_value = threshold.input_value()
    test_value = "9" if original_value != "9" else "8"
    search_button = logged_in_page.get_by_role("button", name="搜索", exact=True).first
    restore_required = False

    def _search_and_reload(value: str) -> str:
        report_page.open_detail(report_id)
        report_page.select_tab("主要客户情况")
        field = logged_in_page.locator("input[placeholder='非负整数']:visible").first
        expect(field).to_be_visible(timeout=10000)
        field.fill(value)
        logged_in_page.get_by_role("button", name="搜索", exact=True).first.click()
        logged_in_page.wait_for_timeout(500)
        report_page.open_detail(report_id)
        report_page.select_tab("主要客户情况")
        field = logged_in_page.locator("input[placeholder='非负整数']:visible").first
        expect(field).to_be_visible(timeout=10000)
        return field.input_value()

    try:
        restore_required = True
        actual = _search_and_reload(test_value)
        assert actual == test_value, "Numeric search condition was not remembered after search and reload"
    finally:
        if restore_required:
            restored = _search_and_reload(original_value)
            assert restored == original_value, "Numeric search condition was not restored to its original value"


def _verify_refresh_button_write(page, api, report_id, button_name: str, endpoint: str) -> dict:
    button = page.get_by_role("button", name=re.compile(button_name)).first
    expect(button).to_be_visible(timeout=15000)
    with page.expect_response(
        lambda response: endpoint.lower() in response.url.lower() and response.request.method.upper() == "PUT",
        timeout=45000,
    ) as response_info:
        button.click()
    response = response_info.value
    assert response.status == 200, f"{button_name} returned HTTP {response.status}"
    body = response.json()
    assert isinstance(body, dict), f"{button_name} returned a non-object response"
    if body.get("code") != 200 and "仅允许刷新上周周报" in str(body.get("msg") or ""):
        reason = str(body.get("msg") or "server rejected the report period").strip()[:200]
        pytest.skip(f"The shared latest report is outside the server's refresh-eligible week: {reason}")
    assert body.get("code") == 200, f"{button_name} returned an unsuccessful response"
    persisted = api.get_report(report_id)
    assert str(persisted.get("id")) == str(report_id), f"{button_name} did not persist to the selected report"
    assert persisted.get("detailList"), f"{button_name} left the selected report without detail rows"
    return body


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_refresh_weekly_report_button_writes_to_the_sixth_group_report(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    """Verify weekly refresh uses its PUT endpoint when the latest report is eligible."""
    assert config_manager.env == "test", "周报刷新写入回归只允许在 TEST 环境执行"
    assert _role() == "admin", "周报刷新写入回归必须使用管理员账号"
    api = _api(authenticated_http_client, api_base_url)
    _, report_rows = _latest_reports(api)
    report_id = _report_for_ui_scope(report_rows)["id"]
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(report_id)
    _verify_refresh_button_write(
        logged_in_page,
        api,
        report_id,
        "更新周报",
        "/oms-report/weekly/report/refreshReportById",
    )


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_refresh_payment_abnormal_button_writes_to_the_sixth_group_report(
    authenticated_http_client, api_base_url: str, logged_in_page, config_manager
) -> None:
    """Verify payment-abnormal refresh uses its direct-write PUT endpoint."""
    assert config_manager.env == "test", "付款异常信息刷新回归只允许在 TEST 环境执行"
    assert _role() == "admin", "付款异常信息刷新回归必须使用管理员账号"
    api = _api(authenticated_http_client, api_base_url)
    _, report_rows = _latest_reports(api)
    report_id = _report_for_ui_scope(report_rows)["id"]
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(report_id)
    report_page.select_tab("付款异常客户")
    report_before = api.get_report(report_id)
    non_payment_rows_before = Counter(
        (
            str(row.get("sectionType")),
            str(row.get("customerId") or ""),
            str(row.get("customerNo") or ""),
        )
        for row in report_before.get("detailList") or []
        if str(row.get("sectionType")) != "3"
    )
    assert non_payment_rows_before, "Latest report has no non-payment rows to protect during payment refresh"
    _verify_refresh_button_write(
        logged_in_page,
        api,
        report_id,
        "更新付款异常客户信息",
        "/oms-report/weekly/report/refreshPaymentAbnormalById",
    )
    report_after = api.get_report(report_id)
    non_payment_rows_after = Counter(
        (
            str(row.get("sectionType")),
            str(row.get("customerId") or ""),
            str(row.get("customerNo") or ""),
        )
        for row in report_after.get("detailList") or []
        if str(row.get("sectionType")) != "3"
    )
    assert (
        non_payment_rows_after == non_payment_rows_before
    ), "Updating payment-abnormal information changed the non-payment customer rows"

"""Read-only regression coverage for weekly business report requirement 1003838."""

from __future__ import annotations

import os
import re
from collections import Counter
from decimal import Decimal

import pytest
import requests
from playwright.sync_api import Browser, expect

from modules.auto_test.api.weekly_business_report_api import WeeklyBusinessReportAPI
from modules.auto_test.core.weekly_business_report_checks import (
    amount,
    direct_currency_expectation,
    is_declining_customer,
    is_main_customer,
    payment_abnormal_bills,
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


def _close(actual, expected: Decimal, *, field: str, row_number: int, dept_name: str) -> None:
    parsed = amount(actual)
    if abs(parsed - expected) > AMOUNT_TOLERANCE:
        raise AssertionError(
            f"{dept_name} payment row {row_number} field {field} differs from the source "
            f"by more than {AMOUNT_TOLERANCE}"
        )


@pytest.mark.api
@pytest.mark.regression
@pytest.mark.p1
@pytest.mark.slow
@pytest.mark.requirement("1003838")
def test_latest_week_admin_reports_match_source_receivable_bills(
    authenticated_http_client, api_base_url: str, config_manager
) -> None:
    """Reconcile every payment-abnormal row in the latest week to source bills.

    This is read-only and uses each report's own end date, so it validates the
    saved historical snapshot instead of comparing it with today's open bills.
    """
    assert config_manager.env == "test", "需求1003838自动化周报回归仅允许在 TEST 环境执行"
    assert _role() == "admin", "Full latest-week, all-group reconciliation requires the admin role"
    api = _api(authenticated_http_client, api_base_url)
    latest_start, report_rows = _latest_reports(api)

    source_cache: dict[tuple[str, str], list[dict]] = {}
    section_counts: Counter[str] = Counter()
    total_details = 0
    total_payment_rows = 0
    direct_currency_rows = 0
    raw_balance_rows = 0

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
                        for field in ("receivableAmount", "receivedAmount", "balanceAmount")
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
            assert bills, f"{report.get('deptName')} payment row {row_number} has no matching source receivable bills"

            dates = sorted(str(bill.get("receivableDate"))[:10] for bill in bills if bill.get("receivableDate"))
            expected_date = f"{dates[0]}~{dates[-1]}" if dates else report_end
            if str(row.get("pendingPaymentBillDate") or "") != expected_date:
                raise AssertionError(
                    f"{report.get('deptName')} payment row {row_number} has an unexpected pending bill date"
                )

            source_currencies = {str(bill.get("currency")) for bill in bills if bill.get("currency")}
            report_currency = str(row.get("receivableCurrency") or "")
            if len(source_currencies) == 1 and (not report_currency or report_currency in source_currencies):
                direct_currency_rows += 1
                expected = direct_currency_expectation(bills, report_end=report_end)
                for field in MONEY_FIELDS:
                    _close(
                        row.get(field),
                        expected[field],
                        field=field,
                        row_number=row_number,
                        dept_name=str(report.get("deptName") or report_id),
                    )

    assert total_details > 0, f"Latest week {latest_start} has no report details"
    assert total_payment_rows > 0, f"Latest week {latest_start} has no payment-abnormal rows to reconcile"
    print(
        "[weekly_report] "
        f"week={latest_start} groups={len(report_rows)} details={total_details} "
        f"payment_rows={total_payment_rows} source_bills={sum(map(len, source_cache.values()))} "
        f"direct_currency_rows={direct_currency_rows} raw_balance_rows={raw_balance_rows} "
        f"sections={dict(section_counts)}"
    )


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
    report = api.get_report(rows[0]["id"])
    customer_no_by_section: dict[str, str] = {}
    for row in report.get("detailList") or []:
        section_type = str(row.get("sectionType"))
        customer_no = row.get("customerNo")
        if section_type in REPORT_TYPES and customer_no:
            customer_no_by_section.setdefault(section_type, str(customer_no))

    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(rows[0]["id"])

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
        print(f"[weekly_report][filters] tab={tab_name} filters={sorted(placeholders)}")
        if not placeholders.intersection({"客户名", "客户名称"}):
            missing_customer_searches.append(f"{tab_name}: customer name")
        if not placeholders.intersection({"客户编号", "客户编码"}):
            missing_customer_searches.append(f"{tab_name}: customer number")

        section_type = section_for_tab[tab_name]
        customer_no = customer_no_by_section.get(section_type)
        if customer_no:
            number_filter = logged_in_page.locator(
                "input[placeholder='客户编号']:visible, input[placeholder='客户编码']:visible"
            ).first
            expect(number_filter).to_be_visible(timeout=5000)
            number_filter.fill(customer_no)
            logged_in_page.get_by_role("button", name="搜索", exact=True).click()
            matching_row = (
                logged_in_page.locator(".el-table__body-wrapper:visible tbody tr.el-table__row:visible")
                .filter(has_text=customer_no)
                .first
            )
            expect(matching_row).to_be_visible(timeout=10000)
            result_rows = logged_in_page.locator(".el-table__body-wrapper:visible tbody tr.el-table__row:visible")
            expect(result_rows).to_have_count(1, timeout=10000)
            searched_sections.add(section_type)
            reset = logged_in_page.get_by_role("button", name="重置", exact=True).first
            if reset.count() and reset.is_visible():
                reset.click()

    assert not missing_customer_searches, (
        f"Customer search controls are missing: {missing_customer_searches}; "
        f"observed placeholders={sorted(observed_placeholders)}"
    )
    assert searched_sections, "No populated customer section could be searched by customer number"
    assert observed_placeholders.intersection({"店长", "请选择店长"}), "No store-manager search was rendered"
    assert "款期类型" in observed_placeholders, "No payment-term-type search was rendered"
    assert "国家" in observed_placeholders, "No country search was rendered"


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
    report_page = WeeklyBusinessReportPage(logged_in_page, config=config_manager)
    report_page.open_detail(rows[0]["id"])
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
    report_id = rows[0]["id"]
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

    user_report_row = rows[0]
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
    else:
        assert option_count == 1, f"sales account can select {option_count} work-plan assignees instead of itself"

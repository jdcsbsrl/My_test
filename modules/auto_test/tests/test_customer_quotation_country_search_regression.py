"""Requirement 1003782: read-only UI regression with explicit UAT sample oracle."""

import json
import os

import pytest

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.secret_provider import get_secret
from modules.auto_test.drivers.browser_driver import BrowserDriver
from modules.auto_test.pages.customer_quotation_country_search_page import CustomerQuotationCountrySearchPage
from modules.auto_test.pages.login_page import LoginPage


def _samples() -> list[dict]:
    raw = os.getenv("TEST_QUOTATION_COUNTRY_SAMPLES", "")
    if not raw:
        pytest.fail("BLOCKED: 缺少 TEST_QUOTATION_COUNTRY_SAMPLES；不能用空结果证明国家筛选正确")
    samples = json.loads(raw)
    if not isinstance(samples, list) or not samples:
        pytest.fail("BLOCKED: 报价国家样本必须是非空数组")
    for sample in samples:
        if not all(sample.get(key) for key in ("customer_no", "continent", "country", "negative_country")):
            pytest.fail("BLOCKED: 每个样本必须有客户编号、大洲、命中国家和不命中国家")
    return samples


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
def test_customer_quotation_country_filter_matches_channel_country() -> None:
    config = get_config("test")
    username = get_secret("USERNAME", environment="test")
    password = get_secret("PASSWORD", environment="test")
    if not username or not password:
        pytest.fail("BLOCKED: test 环境管理员账号不可用")
    samples = _samples()
    driver = BrowserDriver(config=config)
    browser = driver.start_browser(browser="chromium", headless=True, slow_mo=0)
    context = browser.new_context(viewport={"width": 1600, "height": 950})
    try:
        page = context.new_page()
        assert LoginPage(page, config=config).login(username, password), "test 环境登录失败"
        quotation = CustomerQuotationCountrySearchPage(page, config.base_url)
        for sample in samples:
            quotation.open()
            customer_no = sample["customer_no"]
            quotation.customer_number(customer_no)
            quotation.search()
            baseline = quotation.visible_customer_numbers()
            if sum(customer_no in row for row in baseline) != 1:
                pytest.fail(f"BLOCKED: 基线查询未唯一定位报价 {customer_no}")
            quotation.open()
            quotation.customer_number(customer_no)
            quotation.select_path(sample["continent"], sample["country"])
            quotation.search()
            rows = quotation.visible_customer_numbers()
            assert sum(customer_no in row for row in rows) == 1, f"应命中且仅出现一次: {customer_no}"
            quotation.open()
            quotation.customer_number(customer_no)
            quotation.select_path(sample["continent"], sample["negative_country"])
            quotation.search()
            rows = quotation.visible_customer_numbers()
            assert all(customer_no not in row for row in rows), f"不应命中: {customer_no}"
            page.close()
            page = context.new_page()
            quotation = CustomerQuotationCountrySearchPage(page, config.base_url)
    finally:
        context.close()
        driver.shutdown_browser()

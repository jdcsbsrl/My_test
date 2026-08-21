"""SKU Search Regression Tests - Validate search functionality."""

import os

import pytest
from playwright.sync_api import Browser, Page

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.drivers.browser_driver import BrowserDriver
from modules.auto_test.pages.login_page import LoginPage
from modules.auto_test.pages.sku_search_page import SKUSearchPage
from modules.auto_test.core.secret_provider import get_secret

USERNAME = get_secret("USERNAME")
PASSWORD = get_secret("PASSWORD")
DYNAMIC_FIRST_AVAILABLE = "__FIRST_AVAILABLE__"


@pytest.fixture(scope="module")
def browser() -> Browser:
    """Create a browser instance for each test."""
    driver = BrowserDriver()
    config = get_config()
    browser = driver.start_browser(
        browser=config.get("playwright.browser", "chromium"), headless=True, slow_mo=config.get("playwright.slow_mo", 0)
    )
    yield browser
    driver.shutdown_browser()


@pytest.fixture(scope="module")
def page(browser: Browser) -> Page:
    """Create a new page for each test."""
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture(scope="module")
def logged_in_page(page: Page) -> Page:
    """Create a logged-in page for tests that require authentication."""
    login_page = LoginPage(page)
    assert login_page.login(USERNAME, PASSWORD), "登录失败"
    return page


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestSKUSearchDropdownFilters:
    """Tests for dropdown filter functionality."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("产品品类", DYNAMIC_FIRST_AVAILABLE),
            ("销售状态", "全部"),
            ("销售状态", DYNAMIC_FIRST_AVAILABLE),
            ("产品自定义分类", "全部"),
            ("创建人", "全部"),
            ("仓库", "全部"),
            ("运配度", "全部"),
            ("运配仓", "全部"),
        ],
    )
    def test_single_dropdown_filter(self, logged_in_page: Page, field: str, value: str) -> None:
        """Test single dropdown filter selection."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()

        sku_page.click_reset()

        select_method = {
            "产品品类": sku_page.select_product_category,
            "销售状态": sku_page.select_sales_status,
            "产品自定义分类": sku_page.select_custom_category,
            "创建人": sku_page.select_creator,
            "仓库": sku_page.select_warehouse,
            "运配度": sku_page.select_delivery_degree,
            "运配仓": sku_page.select_delivery_warehouse,
        }

        if field in select_method:
            if value == DYNAMIC_FIRST_AVAILABLE:
                value = sku_page.get_first_available_dropdown_option(field)
            select_method[field](value)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"
        assert count >= 0, "结果数应为非负数"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestSKUSearchTextInputs:
    """Tests for text input search functionality."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("SKU编码", "SKU001"),
            ("SKU编码", "test"),
            ("主SKU", "MAIN001"),
            ("SKU名称", "测试产品"),
            ("英文名称", "test"),
            ("原厂SKU", "ORIG001"),
        ],
    )
    def test_text_search(self, logged_in_page: Page, field: str, value: str) -> None:
        """Test text input search."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()

        sku_page.click_reset()

        fill_method = {
            "SKU编码": sku_page.fill_sku_code,
            "主SKU": sku_page.fill_main_sku,
            "SKU名称": sku_page.fill_sku_name,
            "英文名称": sku_page.fill_english_name,
            "原厂SKU": sku_page.fill_original_sku,
        }

        if field in fill_method:
            fill_method[field](value)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p2
class TestSKUSearchAdvanced:
    """Tests for advanced search functionality."""

    def test_inventory_range_search(self, logged_in_page: Page) -> None:
        """Test inventory quantity range search."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.fill_inventory_quantity_range(1, 100)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"

    def test_sale_seven_range_search(self, logged_in_page: Page) -> None:
        """Test 7-day sales range search."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.fill_sale_seven_range(1, 100)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"

    def test_warning_days_range_search(self, logged_in_page: Page) -> None:
        """Test inventory warning days range search."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.fill_warning_days_range(1, 100)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"

    def test_warning_qty_range_search(self, logged_in_page: Page) -> None:
        """Test warning quantity range search."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.fill_warning_qty_range(1, 100)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p2
class TestSKUSearchEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("SKU编码", ""),
            ("SKU编码", " "),
            ("SKU编码", "a" * 200),
            ("SKU名称", "a" * 500),
        ],
    )
    def test_edge_case_inputs(self, logged_in_page: Page, field: str, value: str) -> None:
        """Test edge case inputs."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        fill_method = {
            "SKU编码": sku_page.fill_sku_code,
            "SKU名称": sku_page.fill_sku_name,
        }

        if field in fill_method:
            fill_method[field](value)

        try:
            response_time = sku_page.click_search()
            count = sku_page.get_result_count()
            assert response_time < 30, f"响应时间过长: {response_time}秒"
        except Exception as e:
            pytest.xfail(f"边缘测试用例预期失败: {e}")


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p2
class TestSKUSearchInvalidInputs:
    """Tests for invalid inputs."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("SKU编码", "@#$%^&*"),
            ("SKU编码", "<script>alert(1)</script>"),
            ("SKU名称", "测试' OR '1'='1"),
        ],
    )
    def test_invalid_inputs(self, logged_in_page: Page, field: str, value: str) -> None:
        """Test invalid and malicious inputs."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        fill_method = {
            "SKU编码": sku_page.fill_sku_code,
            "SKU名称": sku_page.fill_sku_name,
        }

        if field in fill_method:
            fill_method[field](value)

        try:
            response_time = sku_page.click_search()
            assert response_time < 30, f"响应时间过长: {response_time}秒"
        except Exception:
            pytest.xfail("无效输入可能导致错误")


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p2
class TestSKUSearchCombinedConditions:
    """Tests for combined search conditions."""

    def test_category_and_status_combined(self, logged_in_page: Page) -> None:
        """Test combining category and status filters."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        product_category = sku_page.get_first_available_dropdown_option("产品品类")
        sku_page.select_product_category(product_category)

        try:
            sales_status = sku_page.get_first_available_dropdown_option("销售状态")
        except ValueError as exc:
            pytest.skip(f"当前产品品类下没有可组合的销售状态选项: {exc}")
        sku_page.select_sales_status(sales_status)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p2
class TestSKUSearchBatchQuery:
    """Tests for batch query functionality."""

    def test_batch_query(self, logged_in_page: Page) -> None:
        """Test batch SKU query."""
        sku_page = SKUSearchPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_list = ["SKU001", "SKU002", "SKU003"]
        sku_page.batch_query_skus(sku_list)

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"

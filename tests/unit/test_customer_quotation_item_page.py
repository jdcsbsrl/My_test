from unittest.mock import Mock, patch

import pytest

from modules.auto_test.pages.customer_quotation_item_page import CustomerQuotationItemPage, CustomerQuotationTarget


def test_target_builds_exact_customer_detail_route() -> None:
    target = CustomerQuotationTarget("2098293645745000450", "2098284914160373762", "DG42884", "yxl_0911")
    assert target.path_and_query() == (
        "/oms-ui/sales/customerQuotes/customerQuotationItem/2098293645745000450"
        "?customer=2098284914160373762&customerNo=DG42884&customerName=yxl_0911"
    )


@pytest.mark.parametrize("quotation_id,customer_id", [("../other", "123"), ("123", "x")])
def test_target_rejects_invalid_ids(quotation_id: str, customer_id: str) -> None:
    with pytest.raises(ValueError):
        CustomerQuotationTarget(quotation_id, customer_id, "DG42884", "yxl_0911")


def test_identity_rejects_other_page_before_reading_customer_fields() -> None:
    target = CustomerQuotationTarget("2098293645745000450", "2098284914160373762", "DG42884", "yxl_0911")
    page = Mock(url="https://erptest.dayoneerp.com/oms-ui/sales/customerQuotes/customerQuotationItem/other")
    config = Mock(base_url="https://erptest.dayoneerp.com/oms-ui/index", env="test")
    with patch("modules.auto_test.pages.base_page.SelfHealingLocator"):
        detail = CustomerQuotationItemPage(page, target, config=config)
    with pytest.raises(AssertionError, match="不是授权"):
        detail.assert_identity()
    page.get_by_role.assert_not_called()


def test_identity_rejects_other_customer_on_same_page() -> None:
    target = CustomerQuotationTarget("2098293645745000450", "2098284914160373762", "DG42884", "yxl_0911")
    page = Mock(
        url="https://erptest.dayoneerp.com/oms-ui/sales/customerQuotes/customerQuotationItem/2098293645745000450"
        "?customer=999&customerNo=DG42884&customerName=yxl_0911"
    )
    config = Mock(base_url="https://erptest.dayoneerp.com/oms-ui/index", env="test")
    with patch("modules.auto_test.pages.base_page.SelfHealingLocator"):
        detail = CustomerQuotationItemPage(page, target, config=config)
    with pytest.raises(AssertionError, match="不是授权"):
        detail.assert_identity()
    page.get_by_role.assert_not_called()


def test_open_rejects_production_before_navigation() -> None:
    target = CustomerQuotationTarget("2098293645745000450", "2098284914160373762", "DG42884", "yxl_0911")
    page = Mock()
    config = Mock(base_url="https://example.com/oms-ui/index", env="production")
    with patch("modules.auto_test.pages.base_page.SelfHealingLocator"):
        detail = CustomerQuotationItemPage(page, target, config=config)
    with pytest.raises(ValueError, match="test/uat"):
        detail.open()
    page.goto.assert_not_called()

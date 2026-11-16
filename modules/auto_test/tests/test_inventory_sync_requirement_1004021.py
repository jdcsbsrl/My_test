"""UI contract regression for inventory sync requirement 1004021."""

from __future__ import annotations

import re

import allure
import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.inventory_rule_page import InventoryRulePage

RULE_NAME = "1113新增规则"
NONPAYMENT_TOOLTIP = "取值逻辑：待处理、配货中、发货中、取消发货、待付款(手动设置计算缺口的订单)，不含 hold 订单"
INCLUDE_PAYMENT_TOOLTIP = "取值逻辑：待处理、配货中、发货中、取消发货、待付款(全部待付款订单)，不含 hold 订单"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p0
@pytest.mark.requirement(id="1004021")
@allure.feature("ERP库存同步")
@allure.story("需求1004021未发货数量口径")
def test_rule_names_tooltips_and_mutual_exclusion(logged_in_page: Page, config_manager) -> None:
    rule_page = InventoryRulePage(logged_in_page, rule_name=RULE_NAME, config=config_manager)
    rule_page.navigate()
    dialog = rule_page.open_editor()

    try:
        labels = [" ".join(text.split()) for text in dialog.locator(".el-checkbox").all_inner_texts()]
        assert any(re.search(r"未发货订单数量\s*[（(]不含未付款[）)]", label) for label in labels), labels
        assert any(re.search(r"未发货订单数量\s*[（(]含未付款[）)]", label) for label in labels), labels

        tooltip_texts = [" ".join(text.split()).lower() for text in rule_page.tooltip_texts(dialog)]
        assert any(
            _normalize_tooltip(NONPAYMENT_TOOLTIP) in _normalize_tooltip(text) for text in tooltip_texts
        ), f"未找到不含未付款注释: {tooltip_texts}"
        assert any(
            _normalize_tooltip(INCLUDE_PAYMENT_TOOLTIP) in _normalize_tooltip(text) for text in tooltip_texts
        ), f"未找到含未付款注释: {tooltip_texts}"

        without_unpaid = rule_page.option_checkbox(dialog, include_unpaid=False)
        with_unpaid = rule_page.option_checkbox(dialog, include_unpaid=True)
        assert rule_page.option_is_checked(without_unpaid) != rule_page.option_is_checked(
            with_unpaid
        ), "两个互斥口径应且只能有一个选中"

        rule_page.select_option(with_unpaid)
        assert rule_page.option_is_checked(with_unpaid), "切换到含未付款后该选项应选中"
        assert not rule_page.option_is_checked(without_unpaid), "含未付款选中后应自动取消不含未付款"

        rule_page.select_option(without_unpaid)
        assert rule_page.option_is_checked(without_unpaid), "切换到不含未付款后该选项应选中"
        assert not rule_page.option_is_checked(with_unpaid), "不含未付款选中后应自动取消含未付款"
    finally:
        rule_page.cancel_editor(dialog)


def _normalize_tooltip(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")").lower()

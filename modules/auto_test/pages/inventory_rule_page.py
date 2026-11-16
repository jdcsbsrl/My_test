"""Page object for the ERP inventory synchronization rules."""

from __future__ import annotations

import re

import allure
from playwright.sync_api import Locator, Page

from modules.auto_test.pages.base_page import BasePage


class InventoryRulePage(BasePage):
    ROUTE = "product/productCenter/inventoryRule"
    DIALOG_SELECTOR = ".el-dialog:visible, [role=dialog]:visible"

    def __init__(self, page: Page, *, rule_name: str = "1113新增规则", config=None) -> None:
        super().__init__(page, config=config)
        self.rule_name = rule_name

    @allure.step("打开库存同步规则页面")
    def navigate(self) -> None:
        self.navigate_to(self.ROUTE)
        self.wait_for_business_ready(
            ['button:visible:has-text("搜索")'],
            page_name="库存同步规则页面",
            required_selectors=[".el-table__row"],
        )

    def rule_row(self) -> Locator:
        matches = self.page.locator(".el-table__row").filter(has_text=self.rule_name)
        if matches.count() != 1:
            raise AssertionError(f"规则名称 {self.rule_name} 应唯一匹配一行，实际为 {matches.count()}")
        row = matches.first
        row.wait_for(state="visible", timeout=30000)
        return row

    @allure.step("打开库存同步规则编辑弹窗")
    def open_editor(self) -> Locator:
        row = self.rule_row()
        edit = row.get_by_text("编辑", exact=True).first
        if edit.count() == 0:
            edit = row.get_by_role("button", name=re.compile("编辑")).first
        if edit.count() != 1:
            raise AssertionError(f"规则 {self.rule_name} 行中应存在唯一编辑入口，实际为 {edit.count()}")
        edit.click()
        dialog = self.page.locator(self.DIALOG_SELECTOR).first
        dialog.wait_for(state="visible", timeout=20000)
        return dialog

    @staticmethod
    def _option_pattern(include_unpaid: bool) -> re.Pattern[str]:
        suffix = "含未付款" if include_unpaid else "不含未付款"
        return re.compile(rf"未发货订单数量\s*[（(]\s*{suffix}\s*[）)]")

    def option_checkbox(self, dialog: Locator, *, include_unpaid: bool) -> Locator:
        checkbox = dialog.locator(".el-checkbox").filter(has_text=self._option_pattern(include_unpaid))
        if checkbox.count() != 1:
            raise AssertionError(
                f"库存同步规则弹窗中应存在唯一未发货数量选项: include_unpaid={include_unpaid}, "
                f"actual={checkbox.count()}"
            )
        return checkbox

    @staticmethod
    def option_is_checked(checkbox: Locator) -> bool:
        return checkbox.locator('input[type="checkbox"]').is_checked()

    def select_option(self, checkbox: Locator) -> None:
        if not self.option_is_checked(checkbox):
            checkbox.click()

    @allure.step("读取未付款统计注释")
    def tooltip_texts(self, dialog: Locator) -> list[str]:
        texts: set[str] = set()
        triggers = dialog.locator(".el-tooltip, .el-tooltip__trigger")
        for trigger in triggers.all():
            try:
                trigger.hover(timeout=1500)
                for tooltip in self.page.locator(
                    ".el-tooltip__popper:visible, [role=tooltip]:visible"
                ).all_inner_texts():
                    normalized = " ".join(tooltip.split())
                    if "取值逻辑" in normalized:
                        texts.add(normalized)
            except Exception:
                continue
        return sorted(texts)

    @allure.step("关闭规则编辑弹窗且不保存")
    def cancel_editor(self, dialog: Locator) -> None:
        cancel = dialog.get_by_role("button", name=re.compile(r"取\s*消|取消")).last
        if cancel.count() != 1:
            raise AssertionError("规则编辑弹窗未找到取消按钮")
        cancel.click()
        dialog.wait_for(state="hidden", timeout=10000)

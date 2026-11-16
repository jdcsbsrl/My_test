"""Page object for the weekly business report detail screen."""

from __future__ import annotations

from playwright.sync_api import Locator

from modules.auto_test.pages.base_page import BasePage

WEEKLY_REPORT_TABS = (
    "主要客户情况",
    "销量下降客户情况",
    "付款异常客户",
    "上周新增客户",
    "上上周新增客户回访",
    "工作计划",
)
CUSTOMER_REPORT_TABS = WEEKLY_REPORT_TABS[:-1]


class WeeklyBusinessReportPage(BasePage):
    def open_detail(self, report_id: int | str) -> None:
        if not str(report_id).isdigit() or int(report_id) <= 0:
            raise ValueError("report_id must be a positive integer")
        self.navigate_to(f"/sales/salesReport/weeklyBusinessReportDetails/{report_id}")
        self.wait_for_business_ready(
            [".el-tabs__header", "[role='tablist']"],
            page_name="业务组周报详情",
            required_selectors=[".el-tabs__item:visible, [role='tab']:visible"],
            initial_timeout=30000,
            retry_timeout=45000,
        )

    def _tab_locator(self, name: str) -> Locator:
        tabs = self.page.locator(".el-tabs__item:visible, [role='tab']:visible")
        return tabs.filter(has_text=name).first

    def visible_tabs(self) -> list[str]:
        return self.page.locator(".el-tabs__item:visible, [role='tab']:visible").all_text_contents()

    def select_tab(self, name: str) -> None:
        if name not in WEEKLY_REPORT_TABS:
            raise ValueError(f"Unsupported weekly report tab: {name}")
        tab = self._tab_locator(name)
        tab.wait_for(state="visible", timeout=15000)
        tab.click()

    def open_ctrl_f_search(self) -> Locator:
        """Open the report's own Ctrl+F search, which spans report categories."""
        self.page.keyboard.press("Control+f")
        search = self.page.get_by_placeholder("在全部周报分类中查找", exact=True)
        search.wait_for(state="visible", timeout=10000)
        return search

    def visible_input_placeholders(self) -> set[str]:
        return {
            value.strip()
            for value in self.page.locator("input:visible").evaluate_all(
                "elements => elements.map(element => element.getAttribute('placeholder') || '')"
            )
            if value and value.strip()
        }

    def visible_search_filter_labels(self) -> set[str]:
        """Read filter labels from the visible search form, including custom selects."""
        return set(self.page.evaluate("""() => {
                  const expected = new Set(
                    ['店长', '请选择店长', '客户名', '客户名称', '客户编号', '客户编码', '款期类型', '国家']
                  );
                  const isVisible = element => {
                    const style = window.getComputedStyle(element);
                    return (
                      style.display !== 'none' &&
                      style.visibility !== 'hidden' &&
                      element.getClientRects().length > 0
                    );
                  };
                  const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
                  const searchButton = buttons.find(element => isVisible(element) && element.innerText.trim() === '搜索');
                  if (!searchButton) return [];
                  for (
                    let root = searchButton.parentElement;
                    root && root !== document.body;
                    root = root.parentElement
                  ) {
                    const labels = new Set(
                      Array.from(root.querySelectorAll('*'))
                        .filter(element => isVisible(element) && element.children.length === 0)
                        .map(element => element.textContent.trim())
                        .filter(text => expected.has(text))
                    );
                    if (labels.has('客户编号') || labels.has('客户编码')) return Array.from(labels);
                  }
                  return [];
                }"""))

    def work_plan_person_selector(self) -> Locator:
        label = self.page.get_by_text("填写人", exact=True).first
        if label.count():
            row = label.locator("xpath=..")
            selector = row.locator(".el-select:visible, [role='combobox']:visible").first
            if selector.count():
                return selector
            wrapper = row.locator("div.w-240px:visible").first
            if wrapper.count():
                return wrapper
        hidden_input = self.page.locator("input[placeholder*='选择人员']").first
        if hidden_input.count():
            return hidden_input.locator("xpath=..")
        return self.page.locator(".el-select:visible").first

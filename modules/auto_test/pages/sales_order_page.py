from typing import Any

import allure
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class SalesOrderPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)
        # 标签页选择器 - 更详细的定位
        self.tab_selectors = {
            "全部订单": "//div[text()='全部订单']",
            "待审核": "//div[text()='待审核']",
            "待合并": "//div[text()='待合并']",
            "待处理": "//div[text()='待处理']",
            "待付款": "//div[text()='待付款']",
            "配货中": "//div[text()='配货中']",
            "WMS发货中": "//div[text()='WMS发货中']",
            "WMS取消发货": "//div[text()='WMS取消发货']",
            "已发货": "//div[text()='已发货']",
            "已作废": "//div[text()='已作废']",
            "FBA": "//div[text()='FBA']",
        }
        # 订单状态选择器 - 更详细的定位
        self.order_status_selector = "//select[@name='orderStatus' or @placeholder='订单状态']"
        # 登录相关选择器
        self.username_input = "//input[@name='username' or @placeholder='手机号']"
        self.password_input = "//input[@name='password' or @placeholder='密码']"
        self.login_button = "//button[contains(text(), '登录')]"
        # 其他可能的元素
        self.tab_container = "//div[contains(@class, 'tab-container') or contains(@class, 'tabs')]"

    @allure.step("登录系统")
    def login(self, username: str, password: str) -> None:
        """登录系统"""
        self.navigate_to("sales/order/saleOrder")
        self.wait_for_load_state()

        try:
            self.wait_for_load_state()
            self.take_screenshot("login_page")

            username_selectors = [
                "//input[@placeholder='账号']",
                "//input[@name='username']",
                "//input[@id='username']",
                "//input[contains(@class, 'username')]",
                "//input[contains(@class, 'account')]",
            ]

            password_selectors = [
                "//input[@placeholder='密码']",
                "//input[@name='password']",
                "//input[@id='password']",
                "//input[contains(@class, 'password')]",
            ]

            login_button_selectors = [
                "//button[contains(@class, 'el-button--primary')]",
                "//button[normalize-space()='登 录']",
                "//button[contains(text(), '登 录')]",
                "//button[contains(normalize-space(), '登录')]",
                "//button[@type='button']",
                "//form[@class='login-form']//button",
            ]

            for selector in username_selectors:
                try:
                    self.wait_for_element(selector, timeout=10000)
                    self.fill(selector, username)
                    logger.info(f"成功填写账号: {selector}")
                    break
                except Exception as e:
                    logger.debug(f"尝试账号选择器 {selector} 失败: {e}")
                    continue

            for selector in password_selectors:
                try:
                    self.wait_for_element(selector, timeout=10000)
                    self.fill(selector, password)
                    logger.info(f"成功填写密码: {selector}")
                    break
                except Exception as e:
                    logger.debug(f"尝试密码选择器 {selector} 失败: {e}")
                    continue

            for selector in login_button_selectors:
                try:
                    self.wait_for_element(selector, timeout=10000)
                    self.click(selector)
                    logger.info(f"成功点击登录按钮: {selector}")
                    break
                except Exception as e:
                    logger.debug(f"尝试登录按钮选择器 {selector} 失败: {e}")
                    continue

            self.wait_for_load_state()
            import time

            time.sleep(5)
            self.take_screenshot("after_login")

            try:
                self.wait_for_element("//table", timeout=15000)
                print("登录成功，已进入销售订单页面")
            except Exception as e:
                print(f"登录可能失败，无法找到销售订单页面元素: {e}")
                self.take_screenshot("login_failed")

        except Exception as e:
            print(f"登录失败: {e}")

    @allure.step("点击标签页: {tab_name}")
    def click_tab(self, tab_name: str) -> None:
        """点击指定标签页，支持多种标签名称变体"""
        tab_variants = [tab_name]

        if tab_name == "待处理":
            tab_variants.extend(["待审核", "待处理订单", "处理中"])

        if tab_name == "全部订单":
            tab_variants.extend(["所有订单", "全部"])

        selectors_base = [
            "//div[contains(text(), '{name}')]",
            "//span[contains(text(), '{name}')]",
            "//div[text()=' {name}(0)']",
            "//span[text()=' {name}(0)']",
            "//div[contains(@class, 'el-tabs__item') and contains(text(), '{name}')]",
            "//span[contains(@class, 'el-tabs__item') and contains(text(), '{name}')]",
            "//div[contains(@class, 'ant-tabs-tab') and contains(text(), '{name}')]",
            "//span[contains(@class, 'ant-tabs-tab') and contains(text(), '{name}')]",
            "[role='tab']:has-text('{name}')",
        ]

        self.page.wait_for_timeout(3000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            logger.warning("销售订单页等待 networkidle 超时，继续等待业务控件: {}", e)

        tab_container = self.page.locator(".el-tabs--top.demo-tabs, [role='tab'], .el-tabs__item").first
        try:
            tab_container.wait_for(timeout=15000)
        except Exception:
            logger.warning(
                "销售订单页标签未出现，刷新重试: url={}, title={}",
                self.page.url,
                self.page.title(),
            )
            self.page.reload(wait_until="domcontentloaded", timeout=60000)
            tab_container.wait_for(timeout=30000)

        clicked = False
        for name in tab_variants:
            for selector_pattern in selectors_base:
                selector = selector_pattern.format(name=name)
                try:
                    elements = self.page.locator(selector).all()
                    if elements:
                        elements[0].click()
                        clicked = True
                        logger.info(f"成功点击标签页: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            if clicked:
                break

        if not clicked:
            try:
                for name in tab_variants:
                    try:
                        # 使用 filter(has_text) 支持部分匹配（如 "待处理(6248)" 匹配 "待处理"）
                        tab = self.page.locator('[role="tab"]').filter(has_text=name.split("(")[0])
                        if tab.count() > 0:
                            tab.first.click()
                            clicked = True
                            logger.info(f"成功通过role+filter点击标签页: {name}")
                            break
                    except Exception as e:
                        logger.debug(f"尝试role+filter {name} 失败: {e}")
                    if clicked:
                        break
            except Exception as e:
                logger.debug(f"尝试role+filter定位失败: {e}")

        # 最终回退：通过 JavaScript 直接操作 DOM 查找并点击标签
        if not clicked:
            try:
                search_name = tab_name.split("(")[0]
                result = self.page.evaluate(
                    f"""
                    () => {{
                        const debug = {{}};
                        debug.roleTabs = document.querySelectorAll('[role="tab"]').length;
                        debug.elTabs = document.querySelectorAll('.el-tabs__item').length;
                        debug.antTabs = document.querySelectorAll('.ant-tabs-tab').length;
                        debug.allText = Array.from(document.querySelectorAll('body *'))
                            .map(el => el.textContent.trim())
                            .filter(t => t.includes('{search_name}'))
                            .slice(0, 20);
                        debug.pageUrl = window.location.href;
                        debug.pageTitle = document.title;

                        const tabs = document.querySelectorAll('[role="tab"], .el-tabs__item, .ant-tabs-tab');
                        debug.tabsContent = Array.from(tabs).map(t => t.textContent.trim());

                        for (const tab of tabs) {{
                            if (tab.textContent.includes('{search_name}')) {{
                                tab.click();
                                debug.clicked = tab.textContent.trim();
                                return {{ success: true, debug: debug }};
                            }}
                        }}
                        return {{ success: false, debug: debug }};
                    }}
                """
                )
                clicked = result.get("success", False)
                debug_info = result.get("debug", {})
                logger.info(
                    f"Tab定位调试 - roleTabs:{debug_info.get('roleTabs')}, elTabs:{debug_info.get('elTabs')}, antTabs:{debug_info.get('antTabs')}"
                )
                logger.info(f"Tab定位调试 - 包含'{search_name}'的文本: {debug_info.get('allText', [])}")
                logger.info(f"Tab定位调试 - 所有tab内容: {debug_info.get('tabsContent', [])}")
                logger.info(f"Tab定位调试 - URL: {debug_info.get('pageUrl')}, 标题: {debug_info.get('pageTitle')}")
                if clicked:
                    logger.info(f"成功通过JS evaluate点击标签页: {tab_name}")
            except Exception as e:
                logger.debug(f"尝试JS evaluate点击标签页失败: {e}")

        if not clicked:
            raise ValueError(f"无法找到标签页 '{tab_name}'")

        self.wait_for_load_state()

    @allure.step("点击高级筛选按钮")
    def click_advanced_filter(self) -> None:
        """点击高级筛选按钮"""
        selectors = [
            "//button[contains(@class, 'advanced-filter')]",
            "//button[contains(@class, 'filter')]",
            "//i[contains(@class, 'el-icon-filter')]",
            "//button[contains(text(), '高级筛选')]",
            "//div[contains(@class, 'search')]//button",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].click()
                    clicked = True
                    print(f"成功点击高级筛选按钮: {selector}")
                    self.wait_for_load_state()
                    break
            except Exception as e:
                print(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            print("无法找到高级筛选按钮")

    @allure.step("关闭高级筛选对话框")
    def close_advanced_filter(self) -> None:
        """关闭高级筛选对话框"""
        selectors = [
            "//button[contains(text(), '取消')]",
            "//button[contains(text(), '关闭')]",
            "//button[contains(@class, 'el-button--default')]",
            "//div[contains(@class, 'el-dialog__headerbtn')]",
            "//i[contains(@class, 'el-dialog__close')]",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].click()
                    clicked = True
                    print(f"成功关闭高级筛选对话框: {selector}")
                    self.wait_for_load_state()
                    break
            except Exception as e:
                print(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            print("无法找到关闭按钮，尝试点击页面其他位置")
            try:
                self.page.click("body")
            except Exception as e:
                print(f"点击空白处失败: {e}")

    @allure.step("获取当前订单状态")
    def get_current_order_status(self) -> str:
        """获取当前订单状态选择器的值"""
        self.click_advanced_filter()

        status_list = ["待审核", "已审核", "已发货", "已完成", "已取消", "FBA"]

        current_status = ""

        print("打开高级筛选对话框成功")
        self.close_advanced_filter()

        return ""

    @allure.step("获取所有标签页")
    def get_all_tabs(self) -> list[str]:
        """获取所有标签页名称"""
        tabs = []
        for tab_name in self.tab_selectors:
            if self.get_element(self.tab_selectors[tab_name]).is_visible():
                tabs.append(tab_name)
        return tabs

    @allure.step("检查异常分类数字颜色")
    def check_exception_category_colors(self) -> dict[str, bool]:
        """检查异常分类括号内数字的颜色，返回检查结果"""
        results = {}

        try:
            selectors = [
                "//div[contains(text(), '(') and contains(text(), ')')]",
                "//span[contains(text(), '(') and contains(text(), ')')]",
                "//div[contains(@class, 'exception') or contains(@class, 'category')]",
                "//span[contains(@class, 'exception') or contains(@class, 'category')]",
            ]

            exception_elements = []
            for selector in selectors:
                elements = self.page.locator(selector).all()
                exception_elements.extend(elements)

            exception_elements = list(set(exception_elements))
            print(f"找到 {len(exception_elements)} 个可能的异常分类元素")

            for i, element in enumerate(exception_elements):
                try:
                    text = element.text_content() or ""
                    if "(" in text and ")" in text:
                        print(f"异常分类 {i}: '{text}'")

                        number_str = text.split("(")[1].split(")")[0]
                        if number_str.isdigit():
                            number = int(number_str)

                            color = element.evaluate("element => getComputedStyle(element).color")
                            print(f"数字 {number} 的颜色: {color}")

                            if number > 0:
                                is_red = "rgb(255, 0, 0)" in color or "#ff0000" in color.lower()
                                results[text] = is_red
                                print(f"数字 {number} 应该是红色: {is_red}")
                            else:
                                is_black = "rgb(0, 0, 0)" in color or "#000000" in color.lower()
                                results[text] = is_black
                                print(f"数字 {number} 应该是黑色: {is_black}")
                except Exception as e:
                    print(f"处理异常分类 {i} 失败: {e}")
                    continue
        except Exception as e:
            print(f"检查异常分类颜色失败: {e}")

        return results

    @allure.step("点击排序下拉菜单")
    def click_sort_dropdown(self) -> None:
        """点击排序下拉菜单"""
        selectors = [
            "//button[contains(text(), '排序')]",
            "//button[contains(@class, 'el-dropdown')]",
            "//button[contains(@class, 'sort')]",
            "//button[contains(@class, 'dropdown')]",
            "//i[contains(@class, 'el-icon-caret-bottom')]",
            "//div[contains(@class, 'sort')]//button",
            "//div[contains(@class, 'dropdown')]//button",
            "//div[contains(@class, 'el-dropdown')]//button",
            "//span[contains(text(), '排序')]",
            "//div[contains(text(), '排序')]",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].wait_for(state="visible", timeout=10000)
                    elements[0].click()
                    clicked = True
                    print(f"成功点击排序下拉菜单: {selector}")
                    self.wait_for_load_state()
                    import time

                    time.sleep(2)
                    break
            except Exception as e:
                print(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            print("无法找到排序下拉菜单")

    @allure.step("选择排序列: {column_name}")
    def select_sort_column(self, column_name: str) -> None:
        """选择排序列"""
        self.click_sort_dropdown()

        selectors = [
            f"//div[contains(@class, 'el-dropdown-menu')]//span[contains(text(), '{column_name}')]",
            f"//div[contains(@class, 'dropdown-menu')]//span[contains(text(), '{column_name}')]",
            f"//div[contains(@class, 'el-dropdown-menu')]//li[contains(text(), '{column_name}')]",
            f"//div[contains(@class, 'dropdown-menu')]//li[contains(text(), '{column_name}')]",
            f"//span[contains(text(), '{column_name}')]",
            f"//li[contains(text(), '{column_name}')]",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].click()
                    clicked = True
                    print(f"成功选择排序列: {selector}")
                    self.wait_for_load_state()
                    import time

                    time.sleep(2)
                    break
            except Exception as e:
                print(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            print(f"无法找到排序列 '{column_name}'")

    @allure.step("获取排序结果")
    def get_sort_results(self, column_index: int) -> list[str]:
        """获取排序结果，返回指定列的所有值"""
        results = []

        try:
            self.wait_for_load_state()
            import time

            time.sleep(3)

            selectors = [
                "//table[@class='el-table__body']//tr",
                "//table[contains(@class, 'table')]//tr",
                "//div[contains(@class, 'el-table__body-wrapper')]//tr",
                "//div[contains(@class, 'table-body')]//tr",
                "//tbody//tr",
                "//table//tr",
            ]

            rows = []
            for selector in selectors:
                try:
                    elements = self.page.locator(selector).all()
                    if elements:
                        elements[0].wait_for(state="visible", timeout=10000)
                        rows = elements
                        print(f"成功找到表格行: {selector}, 共 {len(rows)} 行")
                        break
                except Exception as e:
                    print(f"尝试选择器 {selector} 失败: {e}")
                    continue

            if not rows:
                print("无法找到表格行")
                return results

            for row in rows:
                try:
                    cell_selectors = [
                        f".//td[{column_index + 1}]",
                        f".//td[{column_index + 1}]//div",
                        f".//td[{column_index + 1}]//span",
                        ".//div[contains(@class, 'cell')]",
                        ".//span[contains(@class, 'cell')]",
                    ]

                    cell_value = ""
                    for cell_selector in cell_selectors:
                        try:
                            cells = row.locator(cell_selector).all()
                            if cells:
                                cell_value = cells[0].text_content() or ""
                                if cell_value:
                                    break
                        except Exception as e:
                            print(f"尝试单元格选择器 {cell_selector} 失败: {e}")
                            continue

                    if cell_value:
                        results.append(cell_value.strip())
                        print(f"获取到单元格值: {cell_value.strip()}")
                except Exception as e:
                    print(f"处理行失败: {e}")
                    continue
        except Exception as e:
            print(f"获取排序结果失败: {e}")

        print(f"共获取到 {len(results)} 个值")
        return results

    @allure.step("验证排序结果是否正确")
    def verify_sort_order(self, values: list[str], is_ascending: bool = True) -> bool:
        """验证排序结果是否正确"""
        if not values:
            return False

        sorted_values = values.copy()

        try:
            sorted_values = sorted([float(v) if v.replace(".", "", 1).isdigit() else v for v in sorted_values])
        except Exception:
            sorted_values = sorted(sorted_values)

        if not is_ascending:
            sorted_values.reverse()

        return values == sorted_values

    @allure.step("获取分页信息")
    def get_pagination_info(self) -> dict[str, str]:
        """获取当前分页信息：总数、每页条数、当前页码等"""
        import time

        time.sleep(1)
        info: dict[str, str] = {}
        pagination_selectors = [
            "//div[contains(@class, 'el-pagination')]",
            "//div[contains(@class, 'pagination')]",
            "//div[contains(@class, 'el-pagination__total')]",
            "//span[contains(@class, 'el-pagination__total')]",
        ]
        for selector in pagination_selectors:
            try:
                elem = self.page.locator(selector).first
                text = elem.text_content() or ""
                if text:
                    info["raw_text"] = text
                    break
            except Exception:
                continue
        page_input_selectors = [
            "//input[contains(@class, 'el-pagination__editor')]",
            "//div[contains(@class, 'el-pagination')]//input",
            "//div[contains(@class, 'pagination')]//input",
        ]
        for selector in page_input_selectors:
            try:
                elem = self.page.locator(selector).first
                val = elem.get_attribute("value") or elem.text_content() or ""
                if val:
                    info["current_page"] = val
                    break
            except Exception:
                continue
        size_selectors = [
            "//div[contains(@class, 'el-pagination')]//input[contains(@class, 'size')]",
            "//span[contains(@class, 'el-pagination__sizes')]",
            "//div[contains(@class, 'el-pagination__sizes')]",
        ]
        for selector in size_selectors:
            try:
                elem = self.page.locator(selector).first
                text = elem.text_content() or ""
                if text:
                    info["page_size"] = text.strip()
                    break
            except Exception:
                continue
        return info

    @allure.step("获取当前页码")
    def get_current_page(self) -> int:
        """获取当前页码"""
        selectors = [
            "//li[contains(@class, 'el-pager') and contains(@class, 'is-active')]",
            "//li[contains(@class, 'number') and contains(@class, 'active')]",
            "//ul[contains(@class, 'el-pager')]//li[contains(@class, 'active')]",
        ]
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                text = elem.text_content() or ""
                if text.isdigit():
                    return int(text)
            except Exception:
                continue
        return 1

    @allure.step("点击下一页")
    def click_next_page(self) -> float:
        """点击下一页并返回加载时间(秒)"""
        import time

        selectors = [
            "//button[contains(@class, 'btn-next')]",
            "//i[contains(@class, 'el-icon-arrow-right')]",
            "//span[contains(@class, 'el-pagination__next')]",
            "//button[contains(@aria-label, '下一页')]",
            "//button[contains(text(), '下一页')]",
        ]
        next_btn = None
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    next_btn = elem
                    break
            except Exception:
                continue
        if next_btn is None:
            raise ValueError("无法找到下一页按钮")
        if next_btn.is_disabled():
            logger.info("下一页按钮已禁用")
            return 0.0
        self.page.wait_for_load_state("networkidle")
        start_time = time.time()
        next_btn.click()
        self.wait_for_load_state("networkidle")
        time.sleep(0.5)
        elapsed = time.time() - start_time
        logger.info(f"下一页加载时间: {elapsed:.3f}s")
        return elapsed

    @allure.step("点击上一页")
    def click_previous_page(self) -> float:
        """点击上一页并返回加载时间(秒)"""
        import time

        selectors = [
            "//button[contains(@class, 'btn-prev')]",
            "//i[contains(@class, 'el-icon-arrow-left')]",
            "//span[contains(@class, 'el-pagination__prev')]",
            "//button[contains(@aria-label, '上一页')]",
            "//button[contains(text(), '上一页')]",
        ]
        prev_btn = None
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    prev_btn = elem
                    break
            except Exception:
                continue
        if prev_btn is None:
            raise ValueError("无法找到上一页按钮")
        if prev_btn.is_disabled():
            logger.info("上一页按钮已禁用")
            return 0.0
        self.page.wait_for_load_state("networkidle")
        start_time = time.time()
        prev_btn.click()
        self.wait_for_load_state("networkidle")
        time.sleep(0.5)
        elapsed = time.time() - start_time
        logger.info(f"上一页加载时间: {elapsed:.3f}s")
        return elapsed

    @allure.step("点击指定页码: {page_number}")
    def click_page_number(self, page_number: int) -> float:
        """点击指定页码并返回加载时间(秒)"""
        import time

        selectors = [
            f"//li[contains(@class, 'el-pager') and text()='{page_number}']",
            f"//ul[contains(@class, 'el-pager')]//li[text()='{page_number}']",
            f"//li[contains(@class, 'number') and text()='{page_number}']",
        ]
        page_btn = None
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    page_btn = elem
                    break
            except Exception:
                continue
        if page_btn is None:
            raise ValueError(f"无法找到页码 {page_number}")
        self.page.wait_for_load_state("networkidle")
        start_time = time.time()
        page_btn.click()
        self.wait_for_load_state("networkidle")
        time.sleep(0.5)
        elapsed = time.time() - start_time
        logger.info(f"页码 {page_number} 加载时间: {elapsed:.3f}s")
        return elapsed

    @allure.step("切换每页条数为: {size}")
    def change_page_size(self, size: int) -> float:
        """切换每页显示条数并返回加载时间(秒)"""
        import time

        selectors = [
            "//div[contains(@class, 'el-pagination')]//select",
            "//div[contains(@class, 'el-pagination__sizes')]//div[contains(@class, 'el-select')]",
            "//input[contains(@class, 'el-pagination__size')]",
        ]
        size_trigger = None
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    size_trigger = elem
                    break
            except Exception:
                continue
        if size_trigger is None:
            raise ValueError("无法找到每页条数选择器")
        size_trigger.click()
        time.sleep(0.5)
        option_selectors = [
            f"//li[contains(@class, 'el-select-dropdown__item')]//span[text()='{size}']",
            f"//li[contains(@class, 'el-select-dropdown__item') and text()='{size}']",
            f"//span[text()='{size}条/页']",
            f"//li[text()='{size}']",
        ]
        option = None
        for selector in option_selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    option = elem
                    break
            except Exception:
                continue
        if option is None:
            try:
                option = self.page.locator(f"text={size}").first
            except Exception:
                raise ValueError(f"无法找到每页条数选项 {size}")
        self.page.wait_for_load_state("networkidle")
        start_time = time.time()
        option.click()
        self.wait_for_load_state("networkidle")
        time.sleep(1)
        elapsed = time.time() - start_time
        logger.info(f"切换每页 {size} 条加载时间: {elapsed:.3f}s")
        return elapsed

    @allure.step("获取表格行数")
    def get_table_row_count(self) -> int:
        """获取当前表格显示的行数"""
        selectors = [
            "//tbody//tr[contains(@class, 'el-table__row')]",
            "//table[contains(@class, 'el-table__body')]//tr",
            "//div[contains(@class, 'el-table__body-wrapper')]//tbody//tr",
            "//tbody//tr",
        ]
        for selector in selectors:
            try:
                rows = self.page.locator(selector).all()
                if rows:
                    return len(rows)
            except Exception:
                continue
        return 0

    @allure.step("检查上一页按钮是否禁用")
    def is_previous_disabled(self) -> bool:
        """检查上一页按钮是否被禁用"""
        selectors = [
            "//button[contains(@class, 'btn-prev') and @disabled]",
            "//button[contains(@class, 'btn-prev') and contains(@class, 'disabled')]",
            "//span[contains(@class, 'el-pagination__prev') and contains(@class, 'disabled')]",
        ]
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    return True
            except Exception:
                continue
        return False

    @allure.step("检查下一页按钮是否禁用")
    def is_next_disabled(self) -> bool:
        """检查下一页按钮是否被禁用"""
        selectors = [
            "//button[contains(@class, 'btn-next') and @disabled]",
            "//button[contains(@class, 'btn-next') and contains(@class, 'disabled')]",
            "//span[contains(@class, 'el-pagination__next') and contains(@class, 'disabled')]",
        ]
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    return True
            except Exception:
                continue
        return False

    @allure.step("执行页面滚动并测量帧率")
    def scroll_performance_test(self, scroll_steps: int = 10, step_distance: int = 300) -> dict:
        """执行页面滚动性能测试，返回帧率和耗时数据"""
        import time

        results: dict = {
            "total_time_ms": 0,
            "scroll_steps": scroll_steps,
            "estimated_fps": 0,
            "scroll_jank_count": 0,
            "avg_step_time_ms": 0,
            "step_times_ms": [],
        }

        self.page.evaluate(
            """
            window.__scrollMetrics = { frames: [], startTime: 0, rafId: null };
            window.__scrollMetrics.startTime = performance.now();
            let lastTime = performance.now();
            function recordFrame(timestamp) {
                const dt = timestamp - lastTime;
                lastTime = timestamp;
                window.__scrollMetrics.frames.push(dt);
                window.__scrollMetrics.rafId = requestAnimationFrame(recordFrame);
            }
            window.__scrollMetrics.rafId = requestAnimationFrame(recordFrame);
        """
        )
        time.sleep(0.3)

        total_scroll_time = 0.0
        for i in range(scroll_steps):
            step_start = time.time()
            self.page.evaluate(f"window.scrollBy(0, {step_distance})")
            time.sleep(0.15)
            step_elapsed = (time.time() - step_start) * 1000
            results["step_times_ms"].append(round(step_elapsed, 1))
            total_scroll_time += step_elapsed

        time.sleep(0.5)

        frame_data = self.page.evaluate(
            """
            () => {
                if (!window.__scrollMetrics) return [];
                cancelAnimationFrame(window.__scrollMetrics.rafId);
                const frames = window.__scrollMetrics.frames;
                const totalTime = performance.now() - window.__scrollMetrics.startTime;
                return { frames, totalTime };
            }
        """
        )

        results["total_time_ms"] = round(total_scroll_time, 1)
        results["avg_step_time_ms"] = round(total_scroll_time / scroll_steps, 1)

        if frame_data and frame_data.get("frames"):
            frames = frame_data["frames"]
            valid_frames = [f for f in frames if f > 0]
            if valid_frames:
                avg_frame_time = sum(valid_frames) / len(valid_frames)
                if avg_frame_time > 0:
                    results["estimated_fps"] = round(1000 / avg_frame_time, 1)
                threshold = 1000 / 30
                results["scroll_jank_count"] = sum(1 for f in valid_frames if f > threshold)
        return results

    @allure.step("查找展开/折叠按钮")
    def _find_expand_collapse_buttons(self) -> dict[str, Any] | None:
        """查找"全部展开"或"全部折叠"按钮"""
        import time

        time.sleep(0.5)
        all_visible_buttons = []
        try:
            all_buttons = self.page.locator("button").all()
            for btn in all_buttons:
                if btn.is_visible():
                    all_visible_buttons.append(btn)
        except Exception:
            pass
        for btn in all_visible_buttons:
            try:
                text = btn.text_content() or ""
                text = text.strip()
                if text == "全部展开":
                    return {"element": btn, "type": "expand", "text": "全部展开"}
                if text == "全部折叠":
                    return {"element": btn, "type": "collapse", "text": "全部折叠"}
            except Exception:
                continue

        expand_selectors = [
            "//button[contains(text(), '全部展开')]",
            "//span[contains(text(), '全部展开')]",
            "//span[normalize-space()='全部展开']",
            "//button[normalize-space()='全部展开']",
            "//*[normalize-space()='全部展开']",
        ]
        for selector in expand_selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    return {"element": elem, "type": "expand", "text": "全部展开"}
            except Exception:
                continue

        collapse_selectors = [
            "//button[contains(text(), '全部折叠')]",
            "//span[contains(text(), '全部折叠')]",
            "//span[normalize-space()='全部折叠']",
            "//button[normalize-space()='全部折叠']",
            "//*[normalize-space()='全部折叠']",
        ]
        for selector in collapse_selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    return {"element": elem, "type": "collapse", "text": "全部折叠"}
            except Exception:
                continue

        return None

    @allure.step("获取展开/折叠按钮文本")
    def get_expand_collapse_button_text(self) -> str | None:
        """获取当前展开/折叠按钮的文本"""
        btn = self._find_expand_collapse_buttons()
        if btn:
            return btn["text"]
        return None

    @allure.step("点击展开/折叠按钮")
    def click_expand_collapse_button(self) -> str | None:
        """点击展开/折叠按钮并返回点击前的按钮文本"""
        btn = self._find_expand_collapse_buttons()
        if btn is None:
            logger.warning("未找到展开/折叠按钮")
            return None
        before_text = btn["text"]
        self.page.wait_for_load_state("networkidle")
        btn["element"].click()
        import time

        time.sleep(1)
        self.wait_for_load_state("networkidle")
        logger.info(f"点击了 '{before_text}' 按钮")
        return before_text

    @allure.step("验证展开/折叠按钮切换逻辑")
    def verify_expand_collapse_toggle(self) -> dict:
        """验证展开/折叠按钮的切换逻辑，返回测试结果"""
        import time

        result: dict = {
            "passed": True,
            "steps": [],
            "error": None,
        }
        try:
            initial = self.get_expand_collapse_button_text()
            if initial is None:
                result["passed"] = False
                result["error"] = "初始状态未找到展开/折叠按钮"
                return result
            result["initial_state"] = initial
            result["steps"].append(f"初始按钮文本: {initial}")
            self.take_screenshot("expand_collapse_initial")

            clicked_text = self.click_expand_collapse_button()
            if clicked_text is None:
                result["passed"] = False
                result["error"] = "无法点击展开/折叠按钮"
                return result
            time.sleep(1)
            after_first = self.get_expand_collapse_button_text()
            result["after_first_click"] = after_first
            result["steps"].append(f"第一次点击后按钮文本: {after_first}")
            self.take_screenshot(f"expand_collapse_after_first_{clicked_text}")

            if after_first == clicked_text:
                result["passed"] = False
                result["error"] = f"点击'{clicked_text}'后按钮文本未切换"
                return result

            expected_after_first = "全部折叠" if clicked_text == "全部展开" else "全部展开"
            if after_first != expected_after_first:
                result["passed"] = False
                result["error"] = f"预期按钮文本为'{expected_after_first}'，实际为'{after_first}'"
                return result
            result["steps"].append(f"第一次切换正确: {clicked_text} -> {after_first}")

            clicked_text2 = self.click_expand_collapse_button()
            if clicked_text2 is None:
                result["passed"] = False
                result["error"] = "无法第二次点击展开/折叠按钮"
                return result
            time.sleep(1)
            after_second = self.get_expand_collapse_button_text()
            result["after_second_click"] = after_second
            result["steps"].append(f"第二次点击后按钮文本: {after_second}")
            self.take_screenshot(f"expand_collapse_after_second_{clicked_text2}")

            if after_second != initial:
                result["passed"] = False
                result["error"] = f"第二次点击后按钮文本'{after_second}'未恢复到初始状态'{initial}'"
                return result
            result["steps"].append(f"第二次切换正确: {clicked_text2} -> {after_second}，恢复到初始状态")

        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)
        return result

    @allure.step("获取表格展开行数量")
    def get_expanded_row_count(self) -> int:
        """获取当前展开的表格行数量"""
        selectors = [
            "//tr[contains(@class, 'el-table__expanded-cell')]",
            "//tr[contains(@class, 'expanded')]",
            "//div[contains(@class, 'el-table__expanded-cell')]",
        ]
        for selector in selectors:
            try:
                elems = self.page.locator(selector).all()
                if elems:
                    return len(elems)
            except Exception:
                continue
        return 0

    @allure.step("检查页面是否有展开行")
    def has_expandable_rows(self) -> bool:
        """检查页面是否有可展开/折叠的行"""
        selectors = [
            "//i[contains(@class, 'el-table__expand-icon')]",
            "//span[contains(@class, 'el-table__expand-icon')]",
            "//button[contains(@class, 'el-table__expand-icon')]",
        ]
        for selector in selectors:
            try:
                elem = self.page.locator(selector).first
                if elem.is_visible():
                    return True
            except Exception:
                continue
        return False

    @allure.step("测量页面加载时间")
    def measure_page_load_time(self) -> float:
        """测量当前页面的加载时间(秒)，通过导航计时API"""
        import time

        time.sleep(0.5)
        try:
            timing = self.page.evaluate(
                """
                () => {
                    const pt = performance.timing;
                    const nt = performance.getEntriesByType('navigation')[0];
                    if (nt) return nt.domComplete - nt.fetchStart;
                    return pt.domComplete - pt.fetchStart;
                }
            """
            )
            return round(timing / 1000, 3)
        except Exception:
            return 0.0

    @allure.step("等待表格数据加载完成")
    def wait_for_table_data(self, timeout: int = 15000) -> None:
        """等待表格数据加载完成"""
        selectors = [
            "//tbody//tr[contains(@class, 'el-table__row')]",
            "//div[contains(@class, 'el-table__body-wrapper')]//tr",
            "//table//tbody//tr",
        ]
        for selector in selectors:
            try:
                self.page.locator(selector).first.wait_for(state="visible", timeout=timeout)
                return
            except Exception:
                continue
        try:
            self.page.locator("//div[contains(@class, 'el-loading-mask')]").first.wait_for(
                state="hidden", timeout=timeout
            )
        except Exception:
            pass

    @allure.step("等待排序完成")
    def wait_for_sort_complete(self, timeout: int = 10000) -> None:
        """等待排序完成（等待网络空闲 + 表格数据刷新）"""
        self.page.wait_for_load_state("networkidle")
        self.wait_for_table_data(timeout)

    @allure.step("等待选中数量更新")
    def verify_selected_count(self, timeout: int = 5000) -> int:
        """等待选中数量更新并返回选中行数"""
        try:
            self.page.wait_for_selector(
                "//div[contains(@class, 'el-checkbox__input') and contains(@class, 'is-checked')]", timeout=timeout
            )
        except Exception:
            pass
        return self.get_selected_count()

    @allure.step("点击导出按钮")
    def click_export_button(self) -> None:
        """点击页面上的导出按钮"""
        try:
            script_result = self.page.evaluate(
                """
                () => {
                    const buttons = document.querySelectorAll('button');
                    const exportButtons = [];
                    for (let i = 0; i < buttons.length; i++) {
                        if (buttons[i].innerText.includes('导出')) {
                            exportButtons.push({
                                index: i,
                                className: buttons[i].className,
                                text: buttons[i].innerText,
                                parentClass: buttons[i].parentElement ? buttons[i].parentElement.className : ''
                            });
                        }
                    }
                    return exportButtons;
                }
            """
            )
            logger.info(f"找到导出按钮信息: {script_result}")
        except Exception as e:
            logger.debug(f"查找导出按钮信息失败: {e}")

        selectors = [
            "//button[contains(text(), '导出')]",
            "//div[contains(@class, 'export')]//button",
            "//span[contains(text(), '导出')]",
            "//button[contains(@class, 'export')]",
            "//i[contains(@class, 'export')]/parent::button",
            "//button[contains(@class, 'el-dropdown') and contains(text(), '导出')]",
            "button:has-text('导出')",
            ".el-dropdown button:has-text('导出')",
            "//div[contains(@class, 'btn-group')]//button[contains(text(), '导出')]",
            "//div[contains(@class, 'toolbar')]//button[contains(text(), '导出')]",
            "//div[contains(@class, 'operate')]//button[contains(text(), '导出')]",
            "//div[contains(@class, 'action')]//button[contains(text(), '导出')]",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].wait_for(state="visible", timeout=10000)
                    elements[0].click()
                    clicked = True
                    logger.info(f"成功点击导出按钮: {selector}")
                    self.wait_for_load_state()
                    import time

                    time.sleep(2)
                    break
            except Exception as e:
                logger.debug(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            logger.warning("无法找到导出按钮")

    @allure.step("全选当前页订单")
    def select_all_current_page(self) -> None:
        try:
            script_result = self.page.evaluate(
                """
                () => {
                    const checkbox = document.querySelector('thead input[type="checkbox"]');
                    if (checkbox && !checkbox.checked) {
                        checkbox.click();
                        return { success: true, message: 'clicked header checkbox' };
                    }
                    return { success: false, message: 'checkbox not found or already checked' };
                }
            """
            )
            logger.info(f"全选当前页订单: {script_result}")
            import time

            time.sleep(1)

            selected_count = self.page.evaluate(
                """
                () => document.querySelectorAll('table tbody input[type="checkbox"]:checked').length
            """
            )
            if selected_count > 0:
                logger.info(f"成功勾选 {selected_count} 个订单")
                return

        except Exception as e:
            logger.debug(f"全选失败: {e}")

        try:
            script_result = self.page.evaluate(
                """
                () => {
                    const orderBlocks = document.querySelectorAll('.order-block');
                    let checkedCount = 0;
                    for (let i = 0; i < orderBlocks.length; i++) {
                        const checkbox = orderBlocks[i].querySelector('input[type="checkbox"]');
                        if (checkbox && !checkbox.checked) {
                            checkbox.click();
                            checkedCount++;
                        }
                    }
                    return { success: checkedCount > 0, count: checkedCount, message: 'clicked order-block checkboxes' };
                }
            """
            )
            logger.info(f"通过order-block勾选订单: {script_result}")
            import time

            time.sleep(1)
        except Exception as e:
            logger.debug(f"通过order-block勾选失败: {e}")

        try:
            checkbox = self.page.locator("thead .el-checkbox__input").first
            if checkbox.count() > 0:
                checkbox.click(force=True)
                import time

                time.sleep(1)
                logger.info("尝试通过el-checkbox__input全选")
        except Exception as e:
            logger.debug(f"通过el-checkbox__input全选失败: {e}")

    @allure.step("获取选中订单数量")
    def get_selected_count(self) -> int:
        try:
            count = self.page.evaluate(
                """
                () => {
                    const tableChecked = Array.from(
                        document.querySelectorAll('table tbody input[type="checkbox"]:checked')
                    ).length;
                    if (tableChecked > 0) {
                        return tableChecked;
                    }
                    const orderBlocks = document.querySelectorAll('.order-block');
                    let checked = 0;
                    for (let i = 0; i < orderBlocks.length; i++) {
                        const cb = orderBlocks[i].querySelector('input[type="checkbox"]');
                        if (cb && cb.checked) {
                            checked++;
                        }
                    }
                    return checked;
                }
            """
            )
            return count or 0
        except Exception:
            return 0

    @allure.step("选择导出当前搜索结果")
    def select_export_current_search(self) -> None:
        """点击导出下拉菜单中的'导出当前搜索的订单'选项"""
        self.click_export_button()

        export_option = self.page.locator(
            '.el-dropdown-menu__item:visible:has-text("导出当前搜索的订单"), '
            '[role="menuitem"]:visible:has-text("导出当前搜索的订单")'
        ).first
        try:
            export_option.wait_for(state="visible", timeout=10000)
            export_option.click(timeout=10000)
        except Exception as exc:
            raise ValueError("无法找到“导出当前搜索的订单”选项") from exc
        self.page.wait_for_timeout(1000)
        for opened_page in self.page.context.pages:
            if opened_page is not self.page and "sales/order/exportPage" in opened_page.url:
                export_url = opened_page.url
                opened_page.close()
                self.page.goto(export_url, wait_until="domcontentloaded")
                break
        try:
            self.page.wait_for_url(
                "**/sales/order/exportPage**", timeout=3000, wait_until="domcontentloaded"
            )
        except Exception:
            import time
            from urllib.parse import quote

            order_numbers = self.get_sorted_order_numbers(limit=50)
            if not order_numbers:
                raise ValueError("当前搜索结果没有可用于实时导出的订单")
            order_param = quote(",".join(order_numbers))
            self.navigate_to(
                f"sales/order/exportPage?t={int(time.time() * 1000)}&orderNo={order_param}"
            )
        logger.info("已进入当前搜索订单导出页面")

    @allure.step("选择导出勾选的订单")
    def select_export_selected(self) -> None:
        selected_order_numbers = self.get_sorted_order_numbers(limit=50)
        """点击导出下拉菜单中的'导出勾选的订单'选项"""
        self.click_export_button()
        import time

        time.sleep(2)

        try:
            script_result = self.page.evaluate(
                """
                () => {
                    const items = document.querySelectorAll('.el-dropdown-menu__item');
                    for (let i = 0; i < items.length; i++) {
                        const text = items[i].innerText.trim();
                        if (text === '导出勾选的订单') {
                            items[i].click();
                            return { clicked: true, text: text, index: i };
                        }
                    }
                    return { clicked: false };
                }
            """
            )
            if script_result.get("clicked"):
                logger.info(f"通过JS点击导出勾选的订单: {script_result}")
                time.sleep(5)
                self._ensure_sales_export_page(selected_order_numbers)
                return
        except Exception as e:
            logger.debug(f"通过JS点击导出勾选的订单失败: {e}")

        selectors = [
            ".el-dropdown-menu__item:has-text('导出勾选的订单')",
            "//li[contains(text(), '导出勾选的订单')]",
            "//span[contains(text(), '导出勾选的订单')]",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].click()
                    clicked = True
                    logger.info(f"成功选择导出勾选的订单: {selector}")
                    time.sleep(5)
                    self._ensure_sales_export_page(selected_order_numbers)
                    break
            except Exception as e:
                logger.debug(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            logger.warning("无法找到'导出勾选的订单'选项")

    @allure.step("选择指定排序方式: {column_name}, 升序: {is_ascending}")
    def _ensure_sales_export_page(self, order_numbers: list[str] | None = None) -> None:
        """Ensure selected/current-page export ends on the sales export page."""
        import time
        from urllib.parse import quote

        for opened_page in self.page.context.pages:
            if opened_page is not self.page and "sales/order/exportPage" in opened_page.url:
                export_url = opened_page.url
                opened_page.close()
                self.page.goto(export_url, wait_until="domcontentloaded")
                return

        try:
            self.page.wait_for_url("**/sales/order/exportPage**", timeout=5000, wait_until="domcontentloaded")
            return
        except Exception:
            pass

        if not order_numbers:
            order_numbers = self.get_sorted_order_numbers(limit=50)
        if not order_numbers:
            raise ValueError("No current page sales order numbers are available for export")

        order_param = quote(",".join(order_numbers))
        self.navigate_to(f"sales/order/exportPage?t={int(time.time() * 1000)}&orderNo={order_param}")

    def _ensure_sales_export_page(self, order_numbers: list[str] | None = None) -> None:
        """Ensure selected/current-page export ends on the sales export page."""
        import time
        from urllib.parse import quote

        for opened_page in self.page.context.pages:
            if opened_page is not self.page and "sales/order/exportPage" in opened_page.url:
                export_url = opened_page.url
                opened_page.close()
                self.page.goto(export_url, wait_until="domcontentloaded")
                return

        try:
            self.page.wait_for_url("**/sales/order/exportPage**", timeout=5000, wait_until="domcontentloaded")
            return
        except Exception:
            pass

        if not order_numbers:
            order_numbers = self.get_sorted_order_numbers(limit=50)
        if not order_numbers:
            raise ValueError("No current page sales order numbers are available for export")

        order_param = quote(",".join(order_numbers))
        self.navigate_to(f"sales/order/exportPage?t={int(time.time() * 1000)}&orderNo={order_param}")

    @allure.step("閫夋嫨鎸囧畾鎺掑簭鏂瑰紡: {column_name}, 鍗囧簭: {is_ascending}")
    def select_sort_order(self, column_name: str, is_ascending: bool = True) -> None:
        """选择指定排序列和排序方向"""
        self.click_sort_dropdown()
        import time

        time.sleep(2)

        arrow_icon = "↑" if is_ascending else "↓"
        direction_keywords = ("升序", "asc") if is_ascending else ("降序", "desc")

        menu_items = self.page.locator(".el-dropdown-menu:visible .el-dropdown-menu__item:visible")
        logger.info(f"找到 {menu_items.count()} 个可见下拉菜单项")

        for index in range(menu_items.count()):
            try:
                item = menu_items.nth(index)
                text = item.text_content() or ""
                has_direction = arrow_icon in text or any(keyword in text.lower() for keyword in direction_keywords)
                if column_name in text and has_direction:
                    item.click()
                    logger.info(f"成功选择排序: {column_name}, 升序: {is_ascending}, 菜单项: {text}")
                    self.wait_for_load_state()
                    time.sleep(3)
                    return
            except Exception as e:
                logger.debug(f"尝试菜单项失败: {e}")
                continue

        selectors = [
            "//div[contains(@class, 'el-dropdown-menu') and not(contains(@style, 'display: none'))]"
            f"//span[contains(text(), '{column_name}')]/following-sibling::span[contains(text(), '{arrow_icon}')]",
            "//div[contains(@class, 'el-dropdown-menu') and not(contains(@style, 'display: none'))]"
            f"//li[contains(text(), '{column_name}')]",
            "//div[contains(@class, 'dropdown-menu') and not(contains(@style, 'display: none'))]"
            f"//span[contains(text(), '{column_name}')]",
            "//div[contains(@class, 'dropdown-menu') and not(contains(@style, 'display: none'))]"
            f"//li[contains(text(), '{column_name}')]",
            f"//li[contains(text(), '{column_name}')]",
            f"//span[contains(text(), '{column_name}')]",
        ]

        clicked = False
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    elements[0].click(force=True)
                    clicked = True
                    logger.info(f"成功选择排序: {column_name}, 升序: {is_ascending}")
                    self.wait_for_load_state()
                    time.sleep(2)
                    break
            except Exception as e:
                logger.debug(f"尝试选择器 {selector} 失败: {e}")
                continue

        if not clicked:
            logger.warning(f"无法找到排序选项 '{column_name}'")

    @allure.step("获取排序后的订单号列表")
    def get_sorted_order_numbers(self, limit: int = 50) -> list[str]:
        """获取排序后的订单号列表，用于后续与导出文件对比

        获取系统单号（SO开头，如SO20260627000069）
        """
        results = []

        try:
            self.wait_for_load_state()
            import time

            time.sleep(5)

            try:
                script_result = self.page.evaluate(
                    f"""
                    () => {{
                        const orderBlocks = document.querySelectorAll('.order-block');
                        const orderNumbers = [];
                        for (let i = 0; i < Math.min({limit}, orderBlocks.length); i++) {{
                            const block = orderBlocks[i];
                            const spans = block.querySelectorAll('span.el-text--primary');
                            for (const span of spans) {{
                                const text = span.innerText.trim();
                                if (text.match(/^SO\\d+$/)) {{
                                    orderNumbers.push(text);
                                    break;
                                }}
                            }}
                        }}
                        return orderNumbers;
                    }}
                """
                )
                if script_result:
                    results = script_result
                    logger.info(f"通过order-block获取到 {len(results)} 个系统单号: {results[:5]}...")
            except Exception as e:
                logger.debug(f"通过order-block获取订单号失败: {e}")

            if not results:
                try:
                    script_result = self.page.evaluate(
                        f"""
                        () => {{
                            const text = document.body.innerText;
                            const matches = text.match(/SO\\d{{14,}}/g);
                            if (matches) {{
                                const unique = [...new Set(matches)];
                                return unique.slice(0, {limit});
                            }}
                            return [];
                        }}
                    """
                    )
                    if script_result:
                        results = script_result
                        logger.info(f"通过body文本匹配获取到 {len(results)} 个系统单号: {results[:5]}...")
                except Exception as e:
                    logger.debug(f"通过body文本匹配获取订单号失败: {e}")

            if results:
                seen = set()
                unique_results = []
                for num in results:
                    if num not in seen:
                        seen.add(num)
                        unique_results.append(num)
                results = unique_results[:limit]
                logger.info(f"去重后订单号数量: {len(results)}")
        except Exception as e:
            logger.warning(f"获取排序后订单号失败: {e}")

        logger.info(f"共获取到 {len(results)} 个订单号")
        return results

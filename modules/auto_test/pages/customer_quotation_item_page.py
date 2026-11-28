"""Read-only customer quotation detail page and explored flow contracts.

Flow contracts describe observed UI behavior; they do not execute mutations.
See docs/CUSTOMER_QUOTATION_ITEM_AUTOTEST.md for evidence and open questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import parse_qs, urlencode, urlsplit

from playwright.sync_api import Page, expect

from modules.auto_test.pages.base_page import BasePage


class FlowEvidence(str, Enum):
    OBSERVED = "observed"
    ENTRY_ONLY = "entry_only"


@dataclass(frozen=True)
class QuotationFlowContract:
    key: str
    entry: str
    evidence: FlowEvidence
    observation: str
    future_checks: tuple[str, ...]


# These records are a discovery index, not runnable cases or product expectations.
QUOTATION_FLOW_CONTRACTS: tuple[QuotationFlowContract, ...] = (
    QuotationFlowContract(
        "create",
        "新增报价",
        FlowEvidence.OBSERVED,
        "重复 SKU、数量和赠品标识的候选行在新增报价结果中被拦截，未新增行。",
        ("失败原因", "刷新后的行数和原行状态"),
    ),
    QuotationFlowContract(
        "create_v2",
        "新增报价2.0",
        FlowEvidence.OBSERVED,
        "重复候选行在新增报价结果中被拦截，未新增行。",
        ("2.0 的确认步骤", "失败原因", "刷新后的行数"),
    ),
    QuotationFlowContract(
        "edit",
        "编辑",
        FlowEvidence.OBSERVED,
        "历史观察：重复条件被拦截但更新时间变化。开发称已修复，2026-10-23 复验遭遇服务未找到。",
        ("拦截提示", "原行属性", "刷新后的更新时间应不变"),
    ),
    QuotationFlowContract(
        "edit_v2",
        "编辑2.0",
        FlowEvidence.OBSERVED,
        "历史观察：复核/确认保存后重复条件被拦截但更新时间变化；修复尚待复验。",
        ("复核步骤", "拦截提示", "原行属性", "刷新后的更新时间应不变"),
    ),
    QuotationFlowContract(
        "copy",
        "复制",
        FlowEvidence.OBSERVED,
        "复制已有非赠品行形成重复键时被结果页拦截，未新增行。",
        ("来源行保持不变", "刷新后的行数"),
    ),
    QuotationFlowContract(
        "copy_v2",
        "复制2.0",
        FlowEvidence.OBSERVED,
        "复制已有非赠品行形成重复键时被结果页拦截，未新增行。",
        ("2.0 的确认步骤", "来源行保持不变", "刷新后的行数"),
    ),
    QuotationFlowContract(
        "import_original",
        "导入原始报价表",
        FlowEvidence.OBSERVED,
        "先映射表头再上传完整表；上传后异步解析。带格式的空白尾行曾导致数量为空错误。",
        ("解析任务终态", "错误文件", "刷新后的新增或合并结果", "重复项问题本轮暂不处理"),
    ),
    QuotationFlowContract(
        "import_template",
        "根据系统模板导入",
        FlowEvidence.ENTRY_ONLY,
        "仅确认菜单入口存在，上传和结果流程未探索。",
        ("模板字段", "上传流程", "解析任务和持久化结果"),
    ),
    QuotationFlowContract(
        "delete",
        "删除",
        FlowEvidence.ENTRY_ONLY,
        "仅确认入口存在，未验证删除流程。",
        ("数据所有权", "删除确认", "刷新后的结果"),
    ),
)


@dataclass(frozen=True)
class CustomerQuotationTarget:
    quotation_id: str
    customer_id: str
    customer_no: str
    customer_name: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]+", self.quotation_id) or not re.fullmatch(r"[0-9]+", self.customer_id):
            raise ValueError("报价单和客户 ID 必须为十进制数字")
        if not self.customer_no or not self.customer_name:
            raise ValueError("客户编号和名称不能为空")

    def path_and_query(self) -> str:
        path = f"/oms-ui/sales/customerQuotes/customerQuotationItem/{self.quotation_id}"
        query = urlencode(
            {
                "customer": self.customer_id,
                "customerNo": self.customer_no,
                "customerName": self.customer_name,
            }
        )
        return f"{path}?{query}"


class CustomerQuotationItemPage(BasePage):
    """Only navigation and observations on one explicitly supplied target."""

    def __init__(self, page: Page, target: CustomerQuotationTarget, *, config=None) -> None:
        super().__init__(page, config=config)
        self.target = target

    @staticmethod
    def explored_flows() -> tuple[QuotationFlowContract, ...]:
        """Return UI knowledge without touching the browser or enabling writes."""
        return QUOTATION_FLOW_CONTRACTS

    def open(self) -> None:
        if getattr(self.config, "env", None) not in {"test", "uat"}:
            raise ValueError("客户报价明细只允许在 test/uat 环境访问")
        origin = urlsplit(self.base_url)
        if origin.scheme != "https" or not origin.netloc:
            raise ValueError("客户报价明细仅允许在已配置的 HTTPS 测试环境访问")
        self.navigate_to(f"{origin.scheme}://{origin.netloc}{self.target.path_and_query()}")
        self.assert_identity()

    def assert_identity(self) -> None:
        expected_path = self.target.path_and_query().split("?", 1)[0]
        current = urlsplit(self.page.url)
        expected_query = {
            "customer": [self.target.customer_id],
            "customerNo": [self.target.customer_no],
            "customerName": [self.target.customer_name],
        }
        if current.path != expected_path or parse_qs(current.query) != expected_query:
            raise AssertionError("当前页面不是授权的客户报价明细")
        expect(self.page.get_by_role("textbox", name="客户名称")).to_have_value(self.target.customer_name)
        expect(self.page.get_by_role("textbox", name="客户编号")).to_have_value(self.target.customer_no)

    def quotation_count(self) -> int:
        self.assert_identity()
        text = self.page.get_by_text(re.compile(r"^共\s*\d+\s*条$")).inner_text()
        match = re.fullmatch(r"共\s*(\d+)\s*条", text.strip())
        if match is None:
            raise AssertionError(f"无法解析报价明细总数: {text!r}")
        return int(match.group(1))

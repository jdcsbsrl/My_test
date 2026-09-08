"""Synthetic order-query requirements and transport; no ERP data or credentials."""

import json
from copy import deepcopy

import requests

from modules.trae_test.utils.template_builder import ALL_FIELDS

REQUIREMENT_ID = "MOCK-ORDER-QUERY"
RULES = {
    "basic": "订单列表分页查询返回可见记录，每页最多10条",
    "exact": "按订单号精确查询只返回该订单",
    "fuzzy": "按订单号关键字查询只返回包含该关键字的订单",
    "status": "按订单状态查询只返回匹配状态的订单",
    "combined": "订单号关键字和订单状态组合查询同时满足两个条件",
    "empty": "无匹配订单时返回空结果并明确表示无数据",
    "pagination": "固定数据集的第一页和第二页订单号不重叠",
}
ORDERS = tuple(
    {"orderNo": f"MOCK-ORDER-{i:03d}", "orderStatus": str(i % 2), "sku": f"MOCK-SKU-{i % 3:03d}"} for i in range(1, 25)
)


def query_response(payload, *, ignore_filters=False, empty=False, business_code=200):
    rows = [] if empty else [deepcopy(row) for row in ORDERS]
    if not ignore_filters:
        for key in ("orderNo", "orderStatus", "sku"):
            if key in payload:
                value = str(payload[key])
                rows = [row for row in rows if (value in str(row[key]) if key == "orderNo" else str(row[key]) == value)]
    size = payload.get("pageSize", 10)
    start = (payload.get("pageNum", 1) - 1) * size
    response = requests.Response()
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(
        {
            "code": business_code,
            "data": {"tableDataInfo": {"code": 200, "rows": rows[start : start + size], "total": len(rows)}},
        }
    ).encode()
    return response


class MockKnowledgeAPI:
    def retrieve(self, requirement, mode="hybrid"):
        assertions = {
            "basic": [{"field": "rows", "op": "count_range", "value": [10, 10]}],
            "exact": [
                {"field": "orderNo", "op": "eq", "value": "MOCK-ORDER-001"},
                {"field": "rows", "op": "count_range", "value": [1, 1]},
            ],
            "fuzzy": [
                {"field": "orderNo", "op": "contains", "value": "MOCK-ORDER"},
                {"field": "rows", "op": "count_range", "value": [10, 10]},
            ],
            "status": [{"field": "orderStatus", "op": "eq", "value": "1"}],
            "combined": [
                {"field": "orderNo", "op": "contains", "value": "MOCK-ORDER"},
                {"field": "orderStatus", "op": "eq", "value": "1"},
                {"field": "rows", "op": "count_range", "value": [10, 10]},
            ],
            "empty": [{"field": "rows", "op": "count_range", "value": [0, 0]}],
            "pagination": [{"field": "orderNo", "op": "disjoint", "value": "next_page"}],
        }
        contracts = [
            {
                "id": kind,
                "revision": "1",
                "object": "Mock订单列表",
                "scenario": "正常",
                "assertions": assertions[kind],
                "expected_text": candidate(kind)["预期结果"],
            }
            for kind in RULES
        ]
        return [
            {"id": "MOCK-RULES", "content": {"description": "；".join(RULES.values()), "query_contracts": contracts}}
        ]


def candidate(kind):
    case = dict.fromkeys(ALL_FIELDS, "")
    steps = {
        "basic": "2. 查询订单列表：pageNum=1、pageSize=10",
        "exact": "2. 查询订单列表：orderNo=MOCK-ORDER-001、pageNum=1、pageSize=10",
        "fuzzy": "2. 查询订单列表：orderNo=MOCK-ORDER、pageNum=1、pageSize=10",
        "status": "2. 查询订单列表：orderStatus=1、pageNum=1、pageSize=10",
        "combined": "2. 查询订单列表：orderNo=MOCK-ORDER、orderStatus=1、pageNum=1、pageSize=10",
        "empty": "2. 查询订单列表：orderNo=NO-MATCH、pageNum=1、pageSize=10",
        "pagination": "2. 查询订单列表：分别使用pageNum=1和2、pageSize=10",
    }
    expected = {
        "basic": "2. 第一页记录数量为10，订单号从MOCK-ORDER-001至MOCK-ORDER-010",
        "exact": "2. 记录数量为1，订单号为MOCK-ORDER-001",
        "fuzzy": "2. 记录数量为10，所有订单号均包含MOCK-ORDER",
        "status": "2. 记录数量为10，订单状态均为1",
        "combined": "2. 记录数量为10，所有订单号均包含MOCK-ORDER且订单状态均为1",
        "empty": "2. 记录数量为0，并明确显示无匹配订单",
        "pagination": "2. 两页记录数量均为10，两页订单号没有重叠",
    }
    case.update(
        {
            "用例目录": "销售 - 订单处理 - 销售订单",
            "用例名称": "Mock验收：" + RULES[kind],
            "前置条件": "1. 已启用Mock查询服务，使用虚构订单数据，不连接真实ERP\n2. 固定24条订单MOCK-ORDER-001至024，奇数订单状态1、偶数订单状态0，按编号升序",
            "用例步骤": "1. 打开Mock订单查询测试入口\n" + steps[kind] + "\n3. 打开返回的订单列表并核对记录",
            "预期结果": "1. HTTP状态和业务状态码均为200\n" + expected[kind],
            "用例类型": "接口测试",
            "用例状态": "任意模型值",
            "用例等级": "中",
            "创建人": "余小龙",
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "Mock规则：" + RULES[kind],
        }
    )
    case["_runtime_coverage_matrix"] = {
        "business_rules": [kind],
        "business_objects": ["Mock订单列表"],
        "normal_scenarios": ["正常"],
        "abnormal_scenarios": [],
        "boundary_scenarios": [],
        "rollback_scenarios": [],
        "exclusions": ["真实ERP"],
    }
    case["_runtime_rule_binding"] = {"source_id": "MOCK-RULES", "rule_id": kind, "revision": "1", "scenario": "正常"}
    return case

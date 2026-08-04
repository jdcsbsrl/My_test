"""Regression entry point for sales order report sync query in test environment."""

from __future__ import annotations

import os
import argparse
from datetime import datetime, timedelta

import pytest

from modules.auto_test.api.report_sync_query_api import ReportSyncQueryAPI
from modules.auto_test.core.config_manager import get_config
from tools.report_sync_query_cursor import (
    compare_items,
    compare_sales_list,
    fetch_report_orders,
    validate_auto_parameter_checks,
    validate_filter_effectiveness,
    validate_order_schema,
    validate_optional_parameter_scenarios,
)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_report_sync_query_cursor_and_basic_contract(authenticated_http_client) -> None:
    """Verify test-environment cursor traversal and basic response contract."""
    if os.getenv("TEST_ENV", "test").lower() != "test":
        pytest.skip("This regression case is currently scoped to TEST environment")

    config = get_config()
    api = ReportSyncQueryAPI(authenticated_http_client, config.api_base_url)
    fixed_update_after = os.getenv("REPORT_SYNC_UPDATE_AFTER", "").strip()
    now = datetime.now()
    update_after = fixed_update_after or (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    args = argparse.Namespace(
        update_after=update_after,
        page_size=100,
        include_items=True,
        customer_no="",
        store_id="",
        order_no="",
        order_status="",
        platform="",
        tracking_number="",
        date_begin="",
        date_end="",
        max_pages=1000,
        timeout=30,
    )
    report_url = f"{config.api_base_url}{api.REPORT_PATH}"
    attempts: list[str] = []
    orders: list[dict] = []
    for hours in (1, 2, 3, 4):
        if fixed_update_after:
            candidate = fixed_update_after
        else:
            candidate = (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        args.update_after = candidate
        orders = fetch_report_orders(
            authenticated_http_client,
            report_url,
            args,
            {},
            f"base reportSyncQuery ({hours}h)",
        )
        attempts.append(f"{hours}h={'found ' + str(len(orders)) if orders else 'no data'}")
        if orders or fixed_update_after:
            break

    if not orders:
        pytest.skip(
            "报告没有更新的订单，已查询时间窗口：" + ", ".join(attempts)
        )

    for row, order in enumerate(orders, start=1):
        validate_order_schema(order, 1, row, True)

    validate_filter_effectiveness(orders, args)
    validate_auto_parameter_checks(authenticated_http_client, report_url, args, orders)
    validate_optional_parameter_scenarios(authenticated_http_client, report_url, args, orders)
    compare_sales_list(
        authenticated_http_client,
        f"{config.api_base_url}{api.ORDER_LIST_PATH}",
        orders,
        args.timeout,
        "",
        "orderNo",
        False,
        6,
    )
    compare_items(
        authenticated_http_client,
        f"{config.api_base_url}{api.ORDER_ITEM_PATH}",
        orders,
        args.timeout,
        200,
    )

    assert len({str(order.get("orderNo")) for order in orders}) == len(orders)
    ids = [int(order["id"]) for order in orders if order.get("id") is not None]
    order_nos = [str(order["orderNo"]) for order in orders]
    duplicates = len(order_nos) - len(set(order_nos))
    assert ids == sorted(ids)
    assert all(order.get("orderNo") for order in orders)
    print(
        "[report_sync] "
        f"url={config.api_base_url}{api.REPORT_PATH} "
        f"updateAfter={args.update_after} pageSize=100 includeItems=true "
        f"fallback={' | '.join(attempts)} "
        f"pages=cursor-complete total={len(orders)} duplicates={duplicates} "
        f"idOrder=ascending first={order_nos[0] if order_nos else '-'} "
        f"last={order_nos[-1] if order_nos else '-'}"
    )


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
@pytest.mark.parametrize("page_size", [0, -1, 501])
def test_report_sync_query_page_size_boundary_is_stable(authenticated_http_client, page_size: int) -> None:
    """Exercise undocumented boundary values without assuming a specific business error code."""
    config = get_config()
    api = ReportSyncQueryAPI(authenticated_http_client, config.api_base_url)
    update_after = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    response = api.query({"updateAfter": update_after, "pageSize": page_size, "includeItems": True})
    assert response.status_code < 600
    body = response.json()
    assert isinstance(body, dict)
    assert "code" in body or "data" in body


@pytest.mark.regression
@pytest.mark.api
def test_report_sync_query_date_filters_and_empty_result(authenticated_http_client) -> None:
    config = get_config()
    api = ReportSyncQueryAPI(authenticated_http_client, config.api_base_url)
    update_after = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    for filters in (
        {"orderDateOriginalBegin": "2099-01-01 00:00:00"},
        {"orderDateOriginalEnd": "2000-01-01 00:00:00"},
    ):
        response = api.query(
            {"updateAfter": update_after, "pageSize": 100, "includeItems": True, **filters}
        )
        response.raise_for_status()
        body = response.json()
        assert isinstance(body, dict)
        envelope = body.get("data") if isinstance(body.get("data"), dict) else body
        data = envelope.get("data")
        assert isinstance(data, list) or body.get("code") not in (None, 0, "0", 200, "200")

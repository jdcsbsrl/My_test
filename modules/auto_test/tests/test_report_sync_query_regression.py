"""Regression tests for sales order report sync query in TEST."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from modules.auto_test.api.report_sync_query_api import ReportSyncQueryAPI


def _update_after() -> str:
    return (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def _orders_or_skip(api: ReportSyncQueryAPI, payload: dict) -> tuple[list[dict], str]:
    attempts: list[str] = []
    now = datetime.now()
    for hours in (1, 2, 3, 4):
        update_after = (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        orders = api.query_all({**payload, "updateAfter": update_after})
        attempts.append(f"{hours}h={len(orders)}")
        if orders:
            print(f"[report_sync] updateAfter={update_after} fallback={','.join(attempts)}")
            return orders, update_after
    pytest.skip("报告没有更新的订单，已查询最近4小时：" + ",".join(attempts))


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_report_sync_query_full_regression(authenticated_http_client, api_base_url: str) -> None:
    api = ReportSyncQueryAPI(authenticated_http_client, api_base_url)
    orders, update_after = _orders_or_skip(api, {"pageSize": 100, "includeItems": True})
    order_nos = [str(row.get("orderNo")) for row in orders]
    ids = [int(row["id"]) for row in orders if row.get("id") is not None]
    assert len(order_nos) == len(set(order_nos)), "duplicate orders returned"
    assert ids == sorted(ids), "order ids are not ascending"
    assert all(row.get("orderNo") for row in orders)

    sample = next((row for row in orders if row.get("customerNo")), orders[0])
    checks = {
        "customerNo": sample.get("customerNo"),
        "storeId": sample.get("storeId"),
        "orderNo": sample.get("orderNo"),
        "orderStatus": sample.get("orderStatus"),
        "platform": sample.get("platform"),
        "trackingNumber": sample.get("trackingNumber"),
    }
    for field, value in checks.items():
        if value in (None, ""):
            continue
        filtered, _ = api.query_page({"updateAfter": update_after, "pageSize": 100, "includeItems": True, field: value})
        assert filtered, f"{field} filter returned no orders"
        assert all(str(row.get(field)) == str(value) for row in filtered)
        print(f"[report_sync] {field}={value} count={len(filtered)} example={filtered[0].get('orderNo')}")

    for page_size in (1, 100, 500):
        page, envelope = api.query_page({"updateAfter": _update_after(), "pageSize": page_size, "includeItems": True})
        assert len(page) <= page_size
        assert isinstance(envelope["hasMore"], bool)

    no_items, _ = api.query_page({"updateAfter": _update_after(), "pageSize": 100, "includeItems": False})
    assert all(row.get("salesOrderItemVoList") in (None, []) or "salesOrderItemVoList" not in row for row in no_items)

    empty, envelope = api.query_page({"updateAfter": "2099-01-01 00:00:00", "pageSize": 100, "includeItems": True})
    assert empty == []
    assert envelope["hasMore"] is False

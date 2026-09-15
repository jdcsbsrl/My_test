"""Regression tests for sales order report sync query in TEST."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
import requests

from modules.auto_test.api.report_sync_query_api import (
    CursorPaginationError,
    ReportSyncQueryBusinessError,
    ReportSyncQueryAPI,
)


_TIME_FIELDS = ("sendDate", "platformShipTime", "storeDate")
_TRANSSTOCKUP_ALIASES = ("transstockupTime", "transStockupTime")
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _lookback_minutes() -> list[int]:
    """Return adaptive windows, defaulting from one hour down to five minutes."""
    raw_minutes = os.getenv("REPORT_SYNC_LOOKBACK_MINUTES", "").strip()
    if raw_minutes:
        values = []
        for raw_value in raw_minutes.split(","):
            try:
                minutes = int(float(raw_value.strip()))
                if minutes > 0 and minutes not in values:
                    values.append(minutes)
            except ValueError:
                continue
        if values:
            return values
    return [60, 15, 5]


def _update_after(minutes: int = 60) -> str:
    return (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _orders_with_adaptive_window(api: ReportSyncQueryAPI, payload: dict) -> tuple[list[dict], str]:
    """Fetch a bounded sample without draining a potentially huge report.

    The report endpoint may contain millions of historical orders and can
    continue returning pages even for a narrow ``updateAfter`` window.  This
    regression verifies query/filter behavior, not exhaustive data export, so
    one page is sufficient and prevents CI from spending tens of minutes
    walking an unbounded result set.
    """
    attempts: list[str] = []
    now = datetime.now()
    windows = _lookback_minutes()
    for minutes in windows:
        update_after = (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            orders, envelope = api.query_page({**payload, "updateAfter": update_after})
        except CursorPaginationError as exc:
            attempts.append(f"{minutes}m=分页未收敛({exc})")
            continue
        except ReportSyncQueryBusinessError as exc:
            attempts.append(f"{minutes}m=接口业务失败({exc})")
            continue
        except requests.exceptions.Timeout as exc:
            attempts.append(f"{minutes}m=接口超时({exc})")
            continue
        attempts.append(f"{minutes}m={len(orders)}(hasMore={envelope['hasMore']})")
        if orders:
            print(f"[report_sync] updateAfter={update_after} fallback={','.join(attempts)}")
            return orders, update_after
    raise AssertionError("报告查询在所有自适应时间窗口均未得到可用订单: " + ",".join(attempts))


def _assert_new_time_field_contract(orders: list[dict]) -> None:
    """Validate the requirement-1002990 fields on real report rows.

    ``storeDate`` is a retained historical field.  Its presence and value
    type are checked, but an empty value is valid and must not be interpreted
    as a signing time.  The stock-up field accepts the interface spelling
    ``transStockupTime`` and the legacy consumer spelling ``transstockupTime``.
    """
    non_empty: dict[str, int] = {field: 0 for field in (*_TIME_FIELDS, "transstockupTime")}

    for index, row in enumerate(orders, start=1):
        for field in _TIME_FIELDS:
            assert field in row, f"row {index} missing required field {field}"
            value = row[field]
            assert value is None or isinstance(value, str), f"row {index} field {field} has invalid type"
            if isinstance(value, str) and value:
                datetime.strptime(value, _TIME_FORMAT)
                non_empty[field] += 1

        present_aliases = [field for field in _TRANSSTOCKUP_ALIASES if field in row]
        assert present_aliases, f"row {index} missing transstockupTime/transStockupTime"
        if len(present_aliases) == 2:
            assert row[present_aliases[0]] == row[present_aliases[1]], (
                f"row {index} has conflicting transstockupTime aliases"
            )
        trans_value = row[present_aliases[0]]
        assert trans_value is None or isinstance(trans_value, str), (
            f"row {index} field {present_aliases[0]} has invalid type"
        )
        if isinstance(trans_value, str) and trans_value:
            datetime.strptime(trans_value, _TIME_FORMAT)
            non_empty["transstockupTime"] += 1

    print(f"[report_sync][new_time_fields] rows={len(orders)} non_empty={non_empty}")


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_report_sync_query_full_regression(authenticated_http_client, api_base_url: str) -> None:
    api = ReportSyncQueryAPI(authenticated_http_client, api_base_url)
    orders, update_after = _orders_with_adaptive_window(api, {"pageSize": 100, "includeItems": True})
    order_nos = [str(row.get("orderNo")) for row in orders]
    ids = [int(row["id"]) for row in orders if row.get("id") is not None]
    assert len(order_nos) == len(set(order_nos)), "duplicate orders returned"
    assert ids == sorted(ids), "order ids are not ascending"
    assert all(row.get("orderNo") for row in orders)
    _assert_new_time_field_contract(orders)

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
        page, envelope = api.query_page({"updateAfter": _update_after(15), "pageSize": page_size, "includeItems": True})
        assert len(page) <= page_size
        assert isinstance(envelope["hasMore"], bool)

    no_items, _ = api.query_page({"updateAfter": _update_after(15), "pageSize": 100, "includeItems": False})
    assert all(row.get("salesOrderItemVoList") in (None, []) or "salesOrderItemVoList" not in row for row in no_items)

    empty, envelope = api.query_page({"updateAfter": "2099-01-01 00:00:00", "pageSize": 100, "includeItems": True})
    assert empty == []
    assert envelope["hasMore"] is False

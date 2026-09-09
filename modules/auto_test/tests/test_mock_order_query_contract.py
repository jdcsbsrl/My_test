"""Offline contract checks; all HTTP calls are intercepted before the network."""

import pytest
import requests

from fixtures.mock_order_scenario import query_response
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.regression_checks import QueryCheck, order_rows, verify_pagination, verify_query
from modules.auto_test.facades.api.sales_order_facade import SalesOrderFacade


@pytest.fixture
def mock_orders(monkeypatch):
    def request(session, method, url, **kwargs):
        assert method == "POST" and url.endswith("/batchListNew")
        return query_response(kwargs["json"])

    monkeypatch.setattr(requests.Session, "request", request)
    client = APIClient()
    client.set_body_logging(False)
    try:
        yield SalesOrderFacade(client)
    finally:
        client.close()


def test_basic(mock_orders):
    rows = order_rows(mock_orders.query_orders(page_size=10))
    verify_query(rows, QueryCheck("basic", {}))
    assert [row["orderNo"] for row in rows] == [f"MOCK-ORDER-{i:03d}" for i in range(1, 11)]


def test_exact(mock_orders):
    rows = order_rows(mock_orders.query_orders(page_size=10, orderNo="MOCK-ORDER-001"))
    verify_query(rows, QueryCheck("exact", {"orderNo": "MOCK-ORDER-001"}))
    assert len(rows) == 1


def test_status(mock_orders):
    rows = order_rows(mock_orders.query_orders(page_size=10, orderStatus="1"))
    verify_query(rows, QueryCheck("status", {"orderStatus": "1"}))
    assert len(rows) == 10


def test_fuzzy_query_requires_every_row_to_contain_keyword(mock_orders):
    rows = order_rows(mock_orders.query_orders(page_size=10, orderNo="MOCK-ORDER-0"))
    verify_query(
        rows,
        QueryCheck(
            "fuzzy",
            {"orderNo": "MOCK-ORDER-0"},
            assertions=({"field": "orderNo", "op": "contains", "value": "MOCK-ORDER-0"},),
        ),
    )
    assert len(rows) == 10


def test_combined_query_checks_all_predicates(mock_orders):
    rows = order_rows(mock_orders.query_orders(page_size=10, orderNo="MOCK-ORDER", orderStatus="1"))
    verify_query(
        rows,
        QueryCheck(
            "combined",
            {"orderNo": "MOCK-ORDER", "orderStatus": "1"},
            assertions=(
                {"field": "orderNo", "op": "contains", "value": "MOCK-ORDER"},
                {"field": "orderStatus", "op": "eq", "value": "1"},
            ),
        ),
    )


def test_empty_query_is_allowed_only_when_contract_says_so(mock_orders):
    rows = order_rows(mock_orders.query_orders(page_size=10, orderNo="NO-MATCH"))
    verify_query(
        rows,
        QueryCheck(
            "empty",
            {"orderNo": "NO-MATCH"},
            assertions=({"field": "rows", "op": "count_range", "value": [0, 0]},),
            allow_empty=True,
        ),
    )


def test_pagination_contract_checks_identity_disjointness(mock_orders):
    first = order_rows(mock_orders.query_orders(page_num=1, page_size=10))
    second = order_rows(mock_orders.query_orders(page_num=2, page_size=10))
    verify_pagination(
        first,
        second,
        QueryCheck(
            "pagination",
            {},
            assertions=(
                {"field": "rows", "op": "count_range", "value": [10, 10]},
                {"field": "orderNo", "op": "disjoint", "value": "next_page"},
            ),
        ),
    )


def test_pagination(mock_orders):
    first = order_rows(mock_orders.query_orders(page_num=1, page_size=10))
    second = order_rows(mock_orders.query_orders(page_num=2, page_size=10))
    assert len(first) == len(second) == 10
    assert {row["orderNo"] for row in first}.isdisjoint(row["orderNo"] for row in second)

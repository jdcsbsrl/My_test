from __future__ import annotations

from decimal import Decimal

import pytest

from modules.auto_test.api.inventory_sync_order_api import InventorySyncOrderAPI


class _Response:
    def __init__(self, body: dict) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _Session:
    def __init__(self, bodies: list[dict]) -> None:
        self.bodies = bodies
        self.payloads: list[dict] = []

    def post(self, url: str, *, json: dict, timeout: tuple[int, int]) -> _Response:
        self.payloads.append(json)
        return _Response(self.bodies.pop(0))


@pytest.mark.unit
def test_order_api_normalizes_header_hold_and_combination_lines() -> None:
    session = _Session(
        [
            {
                "code": 200,
                "data": {
                    "tableDataInfo": {
                        "total": 2,
                        "rows": [
                            {"orderNo": "ORDER-8", "orderStatus": "8", "isHold": None, "storeName": "STORE"},
                            {"orderNo": "ORDER-5", "orderStatus": "5", "isHold": "0", "storeName": "STORE"},
                        ],
                    }
                },
            },
            {
                "code": 200,
                "data": {
                    "ORDER-8": [
                        {"itemId": "STOCK-SKU", "quantity": 3, "deficitFlag": None},
                        {"itemId": "CHILD-SKU", "groupSkuId": "COMBO-SKU", "groupSkuQty": 2},
                    ],
                    "ORDER-5": [
                        {"itemId": "STOCK-SKU", "quantity": 4, "deficitFlag": 0},
                        {
                            "groupSkuId": "COMBO-SKU",
                            "groupSkuQty": 1,
                            "detail": [{"deficitFlag": 0}, {"deficitFlag": 0}],
                        },
                    ],
                },
            },
        ]
    )
    api = InventorySyncOrderAPI(session, "https://example.test/api")

    lines = api.fetch_order_lines(["ORDER-8", "ORDER-5", "ORDER-8"])

    assert [
        (line.status, line.sku, line.quantity, line.is_hold, line.deficit_flag, line.store_name) for line in lines
    ] == [
        ("8", "STOCK-SKU", Decimal("3"), False, None, "STORE"),
        ("8", "COMBO-SKU", Decimal("2"), False, None, "STORE"),
        ("5", "STOCK-SKU", Decimal("4"), False, 0, "STORE"),
        ("5", "COMBO-SKU", Decimal("1"), False, 0, "STORE"),
    ]
    assert session.payloads[0]["orderNoList"] == ["ORDER-8", "ORDER-5"]
    assert session.payloads[1]["orderNoList"] == ["ORDER-8", "ORDER-5"]


@pytest.mark.unit
def test_order_api_inherits_unpaid_combination_flag_from_component_rows() -> None:
    session = _Session(
        [
            {
                "code": 200,
                "data": {
                    "tableDataInfo": {
                        "total": 1,
                        "rows": [{"orderNo": "ORDER-5", "orderStatus": "5", "isHold": "0", "storeName": "STORE"}],
                    }
                },
            },
            {
                "code": 200,
                "data": {
                    "ORDER-5": [
                        {
                            "groupSkuId": "COMBO-SKU",
                            "groupSkuQty": 2,
                            "detail": [{"deficitFlag": 1}, {"deficitFlag": "1"}],
                        }
                    ]
                },
            },
        ]
    )

    lines = InventorySyncOrderAPI(session, "https://example.test/api").fetch_order_lines(["ORDER-5"])

    assert len(lines) == 1
    assert (lines[0].sku, lines[0].quantity, lines[0].deficit_flag) == ("COMBO-SKU", Decimal("2"), 1)


@pytest.mark.unit
def test_order_api_blocks_incomplete_seed_order_list() -> None:
    session = _Session(
        [
            {
                "code": 200,
                "data": {"tableDataInfo": {"total": 1, "rows": [{"orderNo": "ORDER-1", "orderStatus": "0"}]}},
            }
        ]
    )

    with pytest.raises(AssertionError, match="缺少 1 条订单"):
        InventorySyncOrderAPI(session, "https://example.test").fetch_order_lines(["ORDER-1", "ORDER-2"])


@pytest.mark.unit
def test_order_api_rejects_unknown_hold_flag() -> None:
    session = _Session(
        [
            {
                "code": 200,
                "data": {
                    "tableDataInfo": {
                        "total": 1,
                        "rows": [{"orderNo": "ORDER-1", "orderStatus": "0", "isHold": "maybe"}],
                    }
                },
            }
        ]
    )

    with pytest.raises(AssertionError, match="isHold 值不在已知范围"):
        InventorySyncOrderAPI(session, "https://example.test").fetch_order_lines(["ORDER-1"])


@pytest.mark.unit
def test_order_api_rejects_invalid_deficit_flag() -> None:
    session = _Session(
        [
            {
                "code": 200,
                "data": {"tableDataInfo": {"total": 1, "rows": [{"orderNo": "ORDER-1", "orderStatus": "5"}]}},
            },
            {"code": 200, "data": {"ORDER-1": [{"itemId": "SKU", "quantity": 1, "deficitFlag": 2}]}},
        ]
    )

    with pytest.raises(AssertionError, match="deficitFlag 仅允许 0 或 1"):
        InventorySyncOrderAPI(session, "https://example.test").fetch_order_lines(["ORDER-1"])

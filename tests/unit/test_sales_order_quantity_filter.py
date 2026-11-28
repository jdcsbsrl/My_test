from modules.auto_test.core.sales_order_quantity_filter import (
    OrderProductMetrics,
    metrics_by_order,
    order_product_metrics,
)


def test_order_product_metrics_counts_distinct_products_and_quantity() -> None:
    items = [
        {"itemId": "SKU-A", "quantity": 1, "platformQuantity": 2},
        {"itemId": "SKU-B", "quantity": 1, "platformQuantity": 3},
    ]
    assert order_product_metrics(items) == OrderProductMetrics(sku_types=2, total_quantity=2)


def test_order_product_metrics_prefers_erp_quantity() -> None:
    items = [
        {"itemId": "SKU-A", "quantity": 1, "platformQuantity": 2},
        {"itemId": "GIFT", "quantity": 1, "platformQuantity": None},
    ]

    assert order_product_metrics(items) == OrderProductMetrics(sku_types=2, total_quantity=2)


def test_order_product_metrics_expands_group_components() -> None:
    items = [
        {
            "groupSkuId": "GROUP-A",
            "platformQuantity": 2,
            "detail": [
                {"itemId": "SKU-A", "quantity": 2},
                {"itemId": "SKU-B", "quantity": 2},
            ],
        }
    ]
    assert order_product_metrics(items) == OrderProductMetrics(sku_types=2, total_quantity=4)


def test_order_product_metrics_counts_stock_and_group_sku_as_two_products() -> None:
    items = [
        {"itemId": "STOCK-A", "quantity": 1, "platformQuantity": None},
        {
            "groupSkuId": "GROUP-A",
            "groupSkuQty": 1,
            "platformQuantity": None,
            "detail": [
                {"itemId": "COMPONENT-1", "quantity": 1},
                {"itemId": "COMPONENT-2", "quantity": 1},
                {"itemId": "COMPONENT-3", "quantity": 1},
            ],
        },
    ]

    assert order_product_metrics(items) == OrderProductMetrics(sku_types=4, total_quantity=4)


def test_metrics_by_order_rejects_invalid_payload() -> None:
    try:
        metrics_by_order({"data": []})
    except AssertionError as exc:
        assert "data对象" in str(exc)
    else:
        raise AssertionError("invalid payload must be rejected")

from unittest.mock import Mock

import pytest

from modules.auto_test.api.openapi_client import OpenAPIClient

pytestmark = pytest.mark.unit


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASE_URL", "https://openapi.example.test")
    instance = OpenAPIClient("app-key", "app-secret", Mock())
    instance.attach_request_info = Mock()
    instance.post = Mock(return_value=Mock())
    return instance


def test_get_auth_headers_returns_app_credentials(api):
    assert api._get_auth_headers() == {
        "Content-Type": "application/json",
        "X-App-Key": "app-key",
        "X-App-Secret": "app-secret",
    }


@pytest.mark.parametrize(
    ("method_name", "suffix"),
    [
        ("query_logistics_page", "/oms-admin/system/customerApiResource/openapi/logistics/queryLogisticsPage"),
        ("query_bill_page", "/oms-admin/system/customerApiResource/openapi/order/queryBillPage"),
        ("query_bill_item", "/oms-admin/system/customerApiResource/openapi/order/queryBillItem"),
        ("query_quotation_page", "/oms-admin/system/customerApiResource/openapi/order/queryQuotationPage"),
        ("query_order_page", "/oms-admin/system/customerApiResource/openapi/order/queryOrderPage"),
        ("query_sku_stock_page", "/oms-admin/system/customerApiResource/openapi/order/querySkuStockPage"),
    ],
)
def test_openapi_methods_post_to_expected_endpoint(api, method_name, suffix):
    payload = {"pageNum": 1}

    result = getattr(api, method_name)(payload)

    assert result is api.post.return_value
    api.post.assert_called_once_with(
        f"https://openapi.example.test{suffix}",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-App-Key": "app-key",
            "X-App-Secret": "app-secret",
        },
    )
    api.attach_request_info.assert_called_once_with(api.post.return_value)


def test_openapi_methods_default_empty_payload(api):
    api.query_order_page()

    assert api.post.call_args.kwargs["json"] == {}


def test_openapi_keeps_credentials_in_headers_and_payload_in_json(api):
    api.query_order_page({"token": "token-value", "password": "password-value"})

    call = api.post.call_args
    assert call.kwargs["json"] == {"token": "token-value", "password": "password-value"}
    assert "token" not in call.kwargs.get("params", {})
    assert "password" not in call.kwargs.get("params", {})
    assert call.kwargs["headers"]["X-App-Key"] == "app-key"
    assert call.kwargs["headers"]["X-App-Secret"] == "app-secret"


def test_openapi_rejects_base_url_with_query_without_echoing_it(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASE_URL", "https://openapi.example.test?token=secret-value")
    api = OpenAPIClient("app-key", "app-secret", Mock())

    with pytest.raises(ValueError) as excinfo:
        api.query_order_page()

    assert "secret-value" not in str(excinfo.value)
    assert "token=secret-value" not in str(excinfo.value)

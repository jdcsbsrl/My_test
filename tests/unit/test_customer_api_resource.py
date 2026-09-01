from unittest.mock import Mock

import pytest

from modules.auto_test.api.customer_api_resource import CustomerApiResourceAPI

pytestmark = pytest.mark.unit


@pytest.fixture
def api():
    instance = CustomerApiResourceAPI(Mock())
    instance.attach_request_info = Mock()
    return instance


def test_list_posts_expected_query_params(api):
    response = Mock()
    api.post = Mock(return_value=response)

    result = api.list(
        page_num=3,
        page_size=20,
        api_code="SKU",
        api_name="Stock",
        path="/stock",
        method="POST",
        description="inventory",
        owner="qa",
    )

    assert result is response
    api.post.assert_called_once_with(
        "/system/customerApiResource/list",
        params={
            "pageNum": 3,
            "pageSize": 20,
            "orderByColumn": "",
            "isAsc": "",
            "apiCode": "SKU",
            "apiName": "Stock",
            "path": "/stock",
            "method": "POST",
            "description": "inventory",
            "owner": "qa",
        },
    )
    api.attach_request_info.assert_called_once_with(response)


def test_list_omits_empty_optional_filters_but_keeps_sorting(api):
    response = Mock()
    api.post = Mock(return_value=response)

    result = api.list(
        api_code="",
        api_name=None,
        path="",
        method=None,
        description="",
        order_by_column="apiCode",
        is_asc="asc",
    )

    assert result is response
    api.post.assert_called_once_with(
        "/system/customerApiResource/list",
        params={
            "pageNum": 1,
            "pageSize": 10,
            "orderByColumn": "apiCode",
            "isAsc": "asc",
        },
    )
    api.attach_request_info.assert_called_once_with(response)


@pytest.mark.parametrize(
    ("method_name", "transport", "expected_endpoint", "payload"),
    [
        ("get_by_id", "get", "/system/customerApiResource/8", 8),
        ("add", "post", "/system/customerApiResource", {"apiName": "new"}),
        ("edit", "put", "/system/customerApiResource", {"id": 8}),
    ],
)
def test_resource_actions_call_expected_endpoint(api, method_name, transport, expected_endpoint, payload):
    response = Mock()
    setattr(api, transport, Mock(return_value=response))

    result = getattr(api, method_name)(payload)

    assert result is response
    getattr(api, transport).assert_called_once()
    assert getattr(api, transport).call_args.args[0] == expected_endpoint
    api.attach_request_info.assert_called_once_with(response)


def test_delete_uses_base_http_delete_without_recursing(api):
    response = Mock()
    api.client.delete = Mock(return_value=response)

    result = api.delete([8, 9])

    assert result is response
    api.client.delete.assert_called_once_with("/system/customerApiResource/[8, 9]")
    api.attach_request_info.assert_called_once_with(response)


def test_export_posts_filters_as_params(api):
    response = Mock()
    api.post = Mock(return_value=response)

    result = api.export(method="GET", apiCode="ORDER")

    assert result is response
    api.post.assert_called_once_with(
        "/system/customerApiResource/export",
        params={"method": "GET", "apiCode": "ORDER"},
    )


def test_export_allows_empty_filter_params(api):
    response = Mock()
    api.post = Mock(return_value=response)

    result = api.export()

    assert result is response
    api.post.assert_called_once_with("/system/customerApiResource/export", params={})
    api.attach_request_info.assert_called_once_with(response)

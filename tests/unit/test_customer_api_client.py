from unittest.mock import Mock

import pytest

from modules.auto_test.api.customer_api_client import CustomerApiClientAPI


pytestmark = pytest.mark.unit


@pytest.fixture
def api():
    instance = CustomerApiClientAPI(Mock())
    instance.attach_request_info = Mock()
    return instance


def test_list_builds_expected_query_params(api):
    response = Mock()
    api.get = Mock(return_value=response)

    result = api.list(
        page_num=2,
        page_size=50,
        customer_name="Acme",
        customer_id="C001",
        app_name="Portal",
        app_key="key-1",
        status=0,
        extra="kept",
    )

    assert result is response
    api.get.assert_called_once_with(
        "/system/customerApiClient/list",
        params={
            "pageNum": 2,
            "pageSize": 50,
            "orderByColumn": "",
            "isAsc": "",
            "customerName": "Acme",
            "customerId": "C001",
            "appName": "Portal",
            "appKey": "key-1",
            "status": 0,
            "extra": "kept",
        },
    )
    api.attach_request_info.assert_called_once_with(response)


def test_list_omits_empty_optional_filters_but_keeps_sorting(api):
    response = Mock()
    api.get = Mock(return_value=response)

    result = api.list(
        customer_name="",
        customer_id=None,
        app_name="",
        app_key=None,
        status=None,
        order_by_column="createTime",
        is_asc="desc",
    )

    assert result is response
    api.get.assert_called_once_with(
        "/system/customerApiClient/list",
        params={
            "pageNum": 1,
            "pageSize": 10,
            "orderByColumn": "createTime",
            "isAsc": "desc",
        },
    )
    api.attach_request_info.assert_called_once_with(response)


@pytest.mark.parametrize(
    ("method_name", "transport", "expected_endpoint", "payload"),
    [
        ("get_by_id", "get", "/system/customerApiClient/12", 12),
        ("add", "post", "/system/customerApiClient", {"name": "new"}),
        ("edit", "put", "/system/customerApiClient/edit", {"id": 12}),
        ("stop_app_secret", "put", "/system/customerApiClient/edit/stopAppSecret", [1, 2]),
        ("generate_secret", "get", "/system/customerApiClient/get", None),
        ("reset_secret", "get", "/system/customerApiClient/updateSecret", None),
    ],
)
def test_customer_client_actions_call_expected_endpoint(api, method_name, transport, expected_endpoint, payload):
    response = Mock()
    setattr(api, transport, Mock(return_value=response))

    if method_name == "stop_app_secret":
        result = CustomerApiClientAPI.stop_app_secret.__wrapped__(api, payload)
    elif payload is None:
        result = getattr(api, method_name)()
    else:
        result = getattr(api, method_name)(payload)

    assert result is response
    call = getattr(api, transport).call_args
    assert call.args[0] == expected_endpoint
    api.attach_request_info.assert_called_once_with(response)


def test_delete_uses_base_http_delete_without_recursing(api):
    response = Mock()
    api.client.delete = Mock(return_value=response)

    result = api.delete([1, 2])

    assert result is response
    api.client.delete.assert_called_once_with("/system/customerApiClient/[1, 2]")
    api.attach_request_info.assert_called_once_with(response)


def test_export_posts_filters_as_params(api):
    response = Mock()
    api.post = Mock(return_value=response)

    result = api.export(status=1, appName="Portal")

    assert result is response
    api.post.assert_called_once_with(
        "/system/customerApiClient/export",
        params={"status": 1, "appName": "Portal"},
    )


def test_export_allows_empty_filter_params(api):
    response = Mock()
    api.post = Mock(return_value=response)

    result = api.export()

    assert result is response
    api.post.assert_called_once_with("/system/customerApiClient/export", params={})
    api.attach_request_info.assert_called_once_with(response)

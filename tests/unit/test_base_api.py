from unittest.mock import Mock, patch

import pytest

from modules.auto_test.api.base_api import BaseAPI


pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    return Mock()


@pytest.mark.parametrize(
    ("method_name", "endpoint", "kwargs"),
    [
        ("get", "/items", {"params": {"page": 1}}),
        ("post", "/items", {"json": {"name": "demo"}}),
        ("put", "/items/1", {"json": {"name": "changed"}}),
        ("patch", "/items/1", {"json": {"enabled": True}}),
        ("delete", "/items/1", {"headers": {"X-Test": "yes"}}),
    ],
)
def test_http_methods_delegate_to_client(client, method_name, endpoint, kwargs):
    expected_response = object()
    getattr(client, method_name).return_value = expected_response
    api = BaseAPI(client)

    result = getattr(api, method_name)(endpoint, **kwargs)

    assert result is expected_response
    getattr(client, method_name).assert_called_once_with(endpoint, **kwargs)


def test_attach_request_info_delegates_to_reporting_helper(client):
    response = Mock()
    api = BaseAPI(client)

    with patch("modules.auto_test.api.base_api.attach_request_info") as attach:
        api.attach_request_info(response)

    attach.assert_called_once_with(response)

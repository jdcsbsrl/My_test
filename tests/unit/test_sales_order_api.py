from unittest.mock import Mock

import pytest

from modules.auto_test.api.sales_order_api import SalesOrderAPI


pytestmark = pytest.mark.unit


@pytest.fixture
def api(monkeypatch):
    client = Mock()
    facade = Mock()
    monkeypatch.setattr("modules.auto_test.api.sales_order_api.SalesOrderFacade", Mock(return_value=facade))
    with pytest.warns(DeprecationWarning):
        instance = SalesOrderAPI(client)
    return instance, facade


def test_batch_list_new_delegates_to_facade(api):
    instance, facade = api
    payload = {"pageNum": 1}
    facade.batch_list_new.return_value = Mock()

    result = instance.batch_list_new(payload)

    assert result is facade.batch_list_new.return_value
    facade.batch_list_new.assert_called_once_with(payload)


def test_query_orders_delegates_to_facade(api):
    instance, facade = api
    facade.query_orders.return_value = Mock()

    result = instance.query_orders(2, 50, orderNo="SO-1")

    assert result is facade.query_orders.return_value
    facade.query_orders.assert_called_once_with(2, 50, orderNo="SO-1")


def test_export_orders_delegates_to_facade(api):
    instance, facade = api
    payload = {"status": "new"}
    facade.export_orders.return_value = Mock()

    result = instance.export_orders(payload)

    assert result is facade.export_orders.return_value
    facade.export_orders.assert_called_once_with(payload)

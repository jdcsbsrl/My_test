from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules.auto_test.facades.api.auth_facade import AuthFacade as ApiAuthFacade
from modules.auto_test.facades.api.sales_order_facade import SalesOrderFacade as ApiSalesOrderFacade
from modules.auto_test.facades.inventory_sku_facade import InventorySKUFacade
from modules.auto_test.facades.sales_order_facade import SalesOrderFacade as UiSalesOrderFacade

pytestmark = pytest.mark.unit


class DummyResponse:
    def __init__(self, payload=None):
        self._payload = payload or {"code": 200, "data": {"token": "token-1"}}
        self.status_code = 200

    def json(self):
        return self._payload


class DummyApiClient:
    def __init__(self):
        self.post_calls = []
        self.default_headers = None

    def post(self, endpoint, json=None, headers=None):
        self.post_calls.append({"endpoint": endpoint, "json": json, "headers": headers})
        return DummyResponse()

    def set_default_api_headers(self, **kwargs):
        self.default_headers = kwargs


def test_api_sales_order_query_orders_builds_default_payload(monkeypatch):
    monkeypatch.setattr(
        "modules.auto_test.facades.api.sales_order_facade.get_config",
        lambda: SimpleNamespace(
            get=lambda key, default=None: "/sales/order" if key == "api.sales_order_resource" else default
        ),
    )
    monkeypatch.setattr("modules.auto_test.facades.api.sales_order_facade.attach_request_info", lambda response: None)
    client = DummyApiClient()
    facade = ApiSalesOrderFacade(client)

    response = facade.query_orders(page_num=2, page_size=50, status="paid")

    assert response.status_code == 200
    assert client.post_calls == [
        {
            "endpoint": "/sales/order/batchListNew",
            "json": {
                "pageNum": 2,
                "pageSize": 50,
                "orderByColumn": "",
                "isAsc": "",
                "status": "paid",
            },
            "headers": None,
        }
    ]


def test_api_sales_order_export_orders_uses_configured_endpoint(monkeypatch):
    monkeypatch.setattr(
        "modules.auto_test.facades.api.sales_order_facade.get_config",
        lambda: SimpleNamespace(
            get=lambda key, default=None: "/custom/order" if key == "api.sales_order_resource" else default
        ),
    )
    monkeypatch.setattr("modules.auto_test.facades.api.sales_order_facade.attach_request_info", lambda response: None)
    client = DummyApiClient()
    facade = ApiSalesOrderFacade(client)

    facade.export_orders({"ids": [1, 2]})

    assert client.post_calls == [
        {
            "endpoint": "/custom/order/batch/orderExport",
            "json": {"ids": [1, 2]},
            "headers": None,
        }
    ]


def test_api_auth_facade_builds_headers_and_applies_defaults(monkeypatch):
    auth_config = SimpleNamespace(
        clientid="client-1",
        encrypt_key="encrypt-key",
        isencrypt="true",
        content_language="zh_CN",
        origin="https://erp.test",
        user_agent="pytest",
    )
    secrets = SimpleNamespace(get_auth_config=MagicMock(return_value=auth_config))
    monkeypatch.setattr(
        "modules.auto_test.facades.api.auth_facade.get_config",
        lambda: SimpleNamespace(api_base_url="https://erp.test/api", get=lambda key, default=None: default),
    )
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_secret_manager", lambda: secrets)
    client = DummyApiClient()
    facade = ApiAuthFacade(client)

    headers = facade.build_login_headers()
    facade.apply_default_api_headers(env="uat")

    assert headers["clientid"] == "client-1"
    assert headers["encrypt-key"] == "encrypt-key"
    assert headers["content-type"] == "application/json;charset=UTF-8"
    assert client.default_headers == {"content_type": "application/json;charset=UTF-8", "clientid": "client-1"}
    secrets.get_auth_config.assert_any_call(api_base_url="https://erp.test/api")
    secrets.get_auth_config.assert_any_call(api_base_url="https://erp.test/api", env="uat")


def test_api_auth_login_uses_secret_password_and_attaches_response(monkeypatch):
    auth_config = SimpleNamespace(
        clientid="client-1",
        encrypt_key="encrypt-key",
        isencrypt="true",
        content_language="zh_CN",
        origin="https://erp.test",
        user_agent="pytest",
    )
    secrets = SimpleNamespace(
        get_auth_config=MagicMock(return_value=auth_config),
        get_credentials=MagicMock(return_value=SimpleNamespace(username="alice")),
        get_api_login_password_payload=MagicMock(return_value="encrypted-password"),
    )
    attached = []
    monkeypatch.setattr(
        "modules.auto_test.facades.api.auth_facade.get_config",
        lambda: SimpleNamespace(
            api_base_url="https://erp.test/api",
            get=lambda key, default=None: "/login" if key == "api.auth_login_path" else default,
        ),
    )
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_secret_manager", lambda: secrets)
    monkeypatch.setattr(
        "modules.auto_test.facades.api.auth_facade.attach_request_info", lambda response: attached.append(response)
    )
    client = DummyApiClient()
    facade = ApiAuthFacade(client)

    response = facade.login()

    assert response.status_code == 200
    assert client.post_calls[0]["endpoint"] == "/login"
    assert client.post_calls[0]["json"] == {"password": "encrypted-password"}
    assert client.post_calls[0]["headers"]["clientid"] == "client-1"
    assert attached == [response]


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"code": 200, "data": {"token": "token-a"}}, "token-a"),
        ({"code": 200, "data": {"access_token": "token-b"}}, "token-b"),
    ],
)
def test_api_auth_get_token_accepts_supported_token_fields(monkeypatch, payload, expected):
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_config", lambda: SimpleNamespace())
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_secret_manager", lambda: SimpleNamespace())
    facade = ApiAuthFacade(DummyApiClient())
    facade.login = MagicMock(return_value=DummyResponse(payload))

    assert facade.get_token() == expected


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"code": 200, "data": {}}, "token"),
        ({"code": 401, "msg": "bad credentials"}, "bad credentials"),
    ],
)
def test_api_auth_get_token_raises_for_missing_token_or_failure(monkeypatch, payload, message):
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_config", lambda: SimpleNamespace())
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_secret_manager", lambda: SimpleNamespace())
    facade = ApiAuthFacade(DummyApiClient())
    facade.login = MagicMock(return_value=DummyResponse(payload))

    with pytest.raises(ValueError, match=message):
        facade.get_token()


def test_ui_sales_order_facade_orchestrates_navigation(monkeypatch):
    order_page = MagicMock()
    page_cls = MagicMock(return_value=order_page)
    monkeypatch.setattr("modules.auto_test.facades.sales_order_facade.SalesOrderPage", page_cls)

    page = MagicMock()
    facade = UiSalesOrderFacade(page)
    facade.navigate_to_sales_order()

    page_cls.assert_called_once_with(page)
    order_page.navigate_to.assert_called_once_with("sales/order/saleOrder")
    order_page.wait_for_load_state.assert_called_once_with()
    order_page.wait_for_table_data.assert_called_once_with()


def test_ui_sales_order_facade_export_selected_handles_export_page_load_failure(monkeypatch):
    order_page = MagicMock()
    export_page = MagicMock()
    export_page.wait_for_export_page.return_value = False
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderPage", MagicMock(return_value=order_page)
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderExportPage", MagicMock(return_value=export_page)
    )

    page = MagicMock()
    facade = UiSalesOrderFacade(page)

    assert facade.export_selected() == {"success": False, "error": "导出页面加载失败"}
    order_page.select_export_selected.assert_called_once_with()


def test_ui_sales_order_facade_export_with_sort_adds_context(monkeypatch, tmp_path):
    order_page = MagicMock()
    order_page.verify_selected_count.return_value = 3
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderPage", MagicMock(return_value=order_page)
    )

    facade = UiSalesOrderFacade(MagicMock())
    facade.select_sort = MagicMock()
    facade.set_page_size = MagicMock(return_value=1.25)
    facade.select_all_current_page = MagicMock()
    facade.get_sorted_order_numbers = MagicMock(return_value=["SO-2", "SO-1"])
    facade.export_selected = MagicMock(return_value={"success": True, "file_path": "orders.xlsx"})

    result = facade.export_with_sort_and_page_size("createdTime", False, 20, False, ["systemNo"], str(tmp_path), "tpl")

    assert result == {
        "success": True,
        "file_path": "orders.xlsx",
        "sort_column": "createdTime",
        "is_ascending": False,
        "page_size": 20,
        "page_set_elapsed": 1.25,
        "selected_count": 3,
        "page_order_numbers": ["SO-2", "SO-1"],
    }
    facade.export_selected.assert_called_once_with(
        select_all_fields=False, fields=["systemNo"], download_dir=str(tmp_path), template_name="tpl"
    )


def test_inventory_sku_facade_search_by_sku_ensures_page_and_returns_results(monkeypatch):
    sku_page = MagicMock()
    sku_page.page = SimpleNamespace(url="https://erp.test/other")
    sku_page.click_search.return_value = 0.75
    sku_page.get_result_count.return_value = 2
    sku_page.get_search_results.return_value = [{"sku": "SKU-1"}, {"sku": "SKU-2"}]
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )

    facade = InventorySKUFacade(MagicMock())
    result = facade.search_by_sku("SKU")

    sku_page.navigate_to_search_page.assert_called_once_with()
    sku_page.click_reset.assert_called_once_with()
    sku_page.fill_sku_code.assert_called_once_with("SKU")
    assert result == {"keyword": "SKU", "elapsed": 0.75, "count": 2, "results": [{"sku": "SKU-1"}, {"sku": "SKU-2"}]}


def test_inventory_sku_facade_export_current_search_reports_field_selection_failure(monkeypatch):
    sku_page = MagicMock()
    export_page = MagicMock()
    export_page.wait_for_export_page.return_value = True
    export_page.select_fields.return_value = 0
    export_page.get_selected_field_count.return_value = 1
    export_page.download_to.return_value = {"success": True, "file_size": 10}
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventoryExportPage", MagicMock(return_value=export_page)
    )

    facade = InventorySKUFacade(MagicMock())

    result = facade.export_current_search(select_all_fields=False, fields=["missing"])

    assert result["success"] is True
    sku_page.select_export_current_search.assert_called_once_with()
    export_page.deselect_all_fields.assert_called_once_with()
    export_page.select_all_fields.assert_called_once_with()


def test_inventory_sku_facade_export_with_page_size_adds_counts(monkeypatch):
    sku_page = MagicMock()
    sku_page.set_page_size.return_value = 0.5
    sku_page.get_result_count.return_value = 12
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )

    page = MagicMock()
    facade = InventorySKUFacade(page)
    facade.export_current_search = MagicMock(return_value={"success": True})

    result = facade.export_with_page_size(10, select_all_fields=False, fields=["sku"], download_dir="downloads")

    assert result == {
        "success": True,
        "page_size": 10,
        "page_set_elapsed": 0.5,
        "result_count": 12,
        "selected_count": 10,
    }
    page.wait_for_load_state.assert_called_once_with("networkidle")
    facade.export_current_search.assert_called_once_with(
        select_all_fields=False, fields=["sku"], download_dir="downloads"
    )


def test_inventory_sku_facade_pagination_navigation_exercises_next_and_back(monkeypatch):
    sku_page = MagicMock()
    sku_page.get_current_page.side_effect = [1, 2, 1]
    sku_page.get_total_pages.return_value = 3
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )

    result = InventorySKUFacade(MagicMock()).verify_pagination_navigation()

    assert result == {
        "initial_page": 1,
        "total_pages": 3,
        "after_next": 2,
        "after_back": 1,
        "navigation_works": True,
    }
    sku_page.click_next_page.assert_called_once_with()
    sku_page.goto_page.assert_called_once_with(1)


def test_api_sales_order_batch_list_new_attaches_response(monkeypatch):
    monkeypatch.setattr(
        "modules.auto_test.facades.api.sales_order_facade.get_config",
        lambda: SimpleNamespace(get=lambda key, default=None: default),
    )
    attached = []
    monkeypatch.setattr("modules.auto_test.facades.api.sales_order_facade.attach_request_info", attached.append)
    client = DummyApiClient()
    facade = ApiSalesOrderFacade(client)

    response = facade.batch_list_new({"pageNum": 1})

    assert response.status_code == 200
    assert client.post_calls[0]["endpoint"] == "/oms-admin/sales/order/batchListNew"
    assert attached == [response]


def test_api_auth_login_falls_back_when_credentials_missing(monkeypatch):
    auth_config = SimpleNamespace(
        clientid="client-1",
        encrypt_key="encrypt-key",
        isencrypt="true",
        content_language="zh_CN",
        origin="https://erp.test",
        user_agent="pytest",
    )
    secrets = SimpleNamespace(
        get_auth_config=MagicMock(return_value=auth_config),
        get_credentials=MagicMock(side_effect=ValueError("missing username")),
        get_api_login_password_payload=MagicMock(return_value="encrypted-password"),
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.api.auth_facade.get_config",
        lambda: SimpleNamespace(api_base_url="https://erp.test/api", get=lambda key, default=None: default),
    )
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_secret_manager", lambda: secrets)
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.attach_request_info", lambda response: None)
    client = DummyApiClient()

    response = ApiAuthFacade(client).login()

    assert response.status_code == 200
    assert client.post_calls[0]["endpoint"] == "/oms-admin/auth/login"
    assert client.post_calls[0]["json"] == {"password": "encrypted-password"}


def test_api_auth_login_uses_explicit_username_and_password(monkeypatch):
    auth_config = SimpleNamespace(
        clientid="client-1",
        encrypt_key="encrypt-key",
        isencrypt="true",
        content_language="zh_CN",
        origin="https://erp.test",
        user_agent="pytest",
    )
    secrets = SimpleNamespace(
        get_auth_config=MagicMock(return_value=auth_config),
        get_credentials=MagicMock(),
        get_api_login_password_payload=MagicMock(),
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.api.auth_facade.get_config",
        lambda: SimpleNamespace(api_base_url="https://erp.test/api", get=lambda key, default=None: default),
    )
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.get_secret_manager", lambda: secrets)
    monkeypatch.setattr("modules.auto_test.facades.api.auth_facade.attach_request_info", lambda response: None)
    client = DummyApiClient()

    ApiAuthFacade(client).login(username="alice", password="plain-password")

    assert client.post_calls[0]["json"] == {"password": "plain-password"}
    secrets.get_credentials.assert_not_called()
    secrets.get_api_login_password_payload.assert_not_called()


def test_ui_sales_order_facade_export_selected_success_with_fields_and_ensures(monkeypatch, tmp_path):
    order_page = MagicMock()
    export_page = MagicMock()
    export_page.wait_for_export_page.return_value = True
    export_page.select_export_template.return_value = True
    export_page.download_to.return_value = {"success": True, "file_path": "orders.xlsx"}
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderPage", MagicMock(return_value=order_page)
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderExportPage", MagicMock(return_value=export_page)
    )
    monkeypatch.setattr("modules.auto_test.facades.sales_order_facade.time.sleep", lambda seconds: None)
    monkeypatch.setattr("modules.auto_test.facades.sales_order_facade.time.time", lambda: 12345)

    page = MagicMock()
    result = UiSalesOrderFacade(page).export_selected(
        select_all_fields=False,
        fields=["systemNo"],
        ensure_fields=["amount", "currency"],
        download_dir=str(tmp_path),
        template_name="tpl",
    )

    assert result["success"] is True
    assert result["export_type"] == "selected"
    assert result["select_all_fields"] is False
    assert result["template_name"] == "tpl"
    assert result["ensure_fields"] == ["amount", "currency"]
    export_page.select_fields.assert_called_once_with(["systemNo"])
    assert export_page.select_field.call_args_list[0].args == ("amount",)
    assert export_page.select_field.call_args_list[1].args == ("currency",)
    export_page.download_to.assert_called_once_with(f"{tmp_path}/sales_order_selected_12345.xlsx", timeout=180000)


def test_ui_sales_order_facade_export_selected_selects_all_fields(monkeypatch, tmp_path):
    export_page = MagicMock()
    export_page.wait_for_export_page.return_value = True
    export_page.select_export_template.return_value = False
    export_page.download_to.return_value = {"success": True}
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderPage", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.sales_order_facade.SalesOrderExportPage", MagicMock(return_value=export_page)
    )
    monkeypatch.setattr("modules.auto_test.facades.sales_order_facade.time.time", lambda: 99)

    result = UiSalesOrderFacade(MagicMock()).export_selected(select_all_fields=True, download_dir=str(tmp_path))

    assert result["success"] is True
    assert result["select_all_fields"] is True
    export_page.select_all_fields.assert_called_once_with()
    export_page.select_fields.assert_not_called()


def test_inventory_sku_facade_export_current_search_success_with_selected_fields(monkeypatch, tmp_path):
    sku_page = MagicMock()
    export_page = MagicMock()
    export_page.page = MagicMock()
    export_page.wait_for_export_page.return_value = True
    export_page.select_fields.return_value = 2
    export_page.download_to.return_value = {"success": True, "file_path": "sku.xlsx"}
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventoryExportPage", MagicMock(return_value=export_page)
    )
    monkeypatch.setattr("modules.auto_test.facades.inventory_sku_facade.time.time", lambda: 456)

    result = InventorySKUFacade(MagicMock()).export_current_search(
        select_all_fields=False, fields=["sku", "warehouse"], download_dir=str(tmp_path)
    )

    assert result["success"] is True
    assert result["export_type"] == "current_search"
    assert result["select_all_fields"] is False
    export_page.deselect_all_fields.assert_called_once_with()
    export_page.select_fields.assert_called_once_with(["sku", "warehouse"])
    export_page.download_to.assert_called_once_with(f"{tmp_path}/inventory_sku_456.xlsx", timeout=180000)
    assert sku_page.page is export_page.page


def test_inventory_sku_facade_export_selected_success_selects_all(monkeypatch, tmp_path):
    export_page = MagicMock()
    export_page.wait_for_export_page.return_value = True
    export_page.download_to.return_value = {"success": True}
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventoryExportPage", MagicMock(return_value=export_page)
    )
    monkeypatch.setattr("modules.auto_test.facades.inventory_sku_facade.time.time", lambda: 789)

    result = InventorySKUFacade(MagicMock()).export_selected(select_all_fields=True, download_dir=str(tmp_path))

    assert result == {"success": True, "export_type": "selected", "select_all_fields": True}
    export_page.select_first_template_if_available.assert_called_once_with()
    export_page.select_all_fields.assert_called_once_with()
    export_page.download_to.assert_called_once_with(f"{tmp_path}/inventory_sku_selected_789.xlsx", timeout=180000)


def test_inventory_sku_facade_export_selected_reports_load_failure(monkeypatch):
    export_page = MagicMock()
    export_page.wait_for_export_page.return_value = False
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventoryExportPage", MagicMock(return_value=export_page)
    )

    result = InventorySKUFacade(MagicMock()).export_selected()

    assert result["success"] is False
    export_page.download_to.assert_not_called()


def test_inventory_sku_facade_pagination_navigation_skips_single_page(monkeypatch):
    sku_page = MagicMock()
    sku_page.get_current_page.return_value = 1
    sku_page.get_total_pages.return_value = 1
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )

    result = InventorySKUFacade(MagicMock()).verify_pagination_navigation()

    assert result["navigation_works"] is True
    assert result["total_pages"] == 1
    sku_page.click_next_page.assert_not_called()


def test_inventory_sku_facade_verify_helpers_delegate_to_page(monkeypatch):
    sku_page = MagicMock()
    sku_page.is_header_checkbox_checked.return_value = False
    sku_page.get_current_page_row_count.return_value = 25
    monkeypatch.setattr(
        "modules.auto_test.facades.inventory_sku_facade.InventorySKUPage", MagicMock(return_value=sku_page)
    )

    facade = InventorySKUFacade(MagicMock())

    assert facade.verify_select_all_state(expected=True) is False
    assert facade.verify_page_size(expected_size=10) is True


def test_ui_sales_order_verify_export_file_reports_missing_file():
    result = UiSalesOrderFacade.verify_export_file("missing-orders.xlsx")

    assert result["valid"] is False
    assert "error" in result


def test_ui_sales_order_verify_export_file_reads_excel_metadata(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    file_path = tmp_path / "orders.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["systemNo", "amount"])
    sheet.append(["SO-1", 100])
    workbook.save(file_path)

    result = UiSalesOrderFacade.verify_export_file(str(file_path))

    assert result["valid"] is True
    assert result["row_count"] == 2
    assert result["col_count"] == 2
    assert result["headers"][:2] == ["systemNo", "amount"]


def test_ui_sales_order_verify_export_order_consistency_reports_missing_file():
    result = UiSalesOrderFacade.verify_export_order_consistency("missing-orders.xlsx", ["SO-1"])

    assert result["success"] is False
    assert "error" in result


def test_ui_sales_order_verify_export_order_consistency_handles_empty_expected(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    file_path = tmp_path / "orders.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["systemNo"])
    sheet.append(["SO-1"])
    workbook.save(file_path)

    result = UiSalesOrderFacade.verify_export_order_consistency(str(file_path), [], order_number_column_name="systemNo")

    assert result["success"] is True
    assert result["export_count"] == 1
    assert result["order_column"] == "systemNo"


def test_ui_sales_order_verify_export_order_consistency_deduplicates_and_matches(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    file_path = tmp_path / "orders.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["systemNo"])
    sheet.append(["SO-1"])
    sheet.append(["SO-1"])
    sheet.append(["SO-2"])
    workbook.save(file_path)

    result = UiSalesOrderFacade.verify_export_order_consistency(
        str(file_path), ["SO-1", "SO-2"], order_number_column_name="systemNo"
    )

    assert result["success"] is True
    assert result["export_count"] == 3
    assert result["export_unique_count"] == 2
    assert result["matching_count"] == 2
    assert result["deduplicated"] is True


def test_ui_sales_order_verify_export_order_consistency_reports_mismatches(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    file_path = tmp_path / "orders.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["systemNo"])
    sheet.append(["SO-2"])
    workbook.save(file_path)

    result = UiSalesOrderFacade.verify_export_order_consistency(
        str(file_path), ["SO-1"], order_number_column_name="systemNo", deduplicate=False
    )

    assert result["success"] is False
    assert result["mismatched_positions"] == [{"position": 1, "expected": "SO-1", "actual": "SO-2"}]
    assert result["deduplicated"] is False


def test_inventory_sku_verify_export_file_reports_missing_file():
    result = InventorySKUFacade.verify_export_file("missing-sku.xlsx")

    assert result["valid"] is False
    assert "error" in result


def test_inventory_sku_verify_export_file_reads_excel_metadata(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    file_path = tmp_path / "sku.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["sku", "warehouse"])
    sheet.append(["SKU-1", "WH-1"])
    workbook.save(file_path)

    result = InventorySKUFacade.verify_export_file(str(file_path))

    assert result["valid"] is True
    assert result["row_count"] == 2
    assert result["col_count"] == 2
    assert result["headers"][:2] == ["sku", "warehouse"]

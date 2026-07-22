import warnings
from typing import Any

import requests

from modules.auto_test.api.base_api import BaseAPI
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.facades.api.sales_order_facade import SalesOrderFacade


class SalesOrderAPI(BaseAPI):
    """Deprecated: use SalesOrderFacade."""

    def __init__(self, client: APIClient | None = None) -> None:
        super().__init__(client)
        warnings.warn(
            "SalesOrderAPI is deprecated; use SalesOrderFacade from modules.auto_test.facades.api.sales_order_facade.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._facade = SalesOrderFacade(self.client)

    def batch_list_new(self, payload: dict[str, Any]) -> requests.Response:
        return self._facade.batch_list_new(payload)

    def query_orders(
        self,
        page_num: int = 1,
        page_size: int = 100,
        **filters: Any,
    ) -> requests.Response:
        return self._facade.query_orders(page_num, page_size, **filters)

    def export_orders(self, payload: dict[str, Any]) -> requests.Response:
        return self._facade.export_orders(payload)

"""Auto Test Pages Module - Page Object Model for UI testing."""

from .base_page import BasePage
from .login_page import LoginPage
from .sales_order_page import SalesOrderPage
from .sku_search_page import SKUSearchPage

__all__ = ["BasePage", "LoginPage", "SKUSearchPage", "SalesOrderPage"]

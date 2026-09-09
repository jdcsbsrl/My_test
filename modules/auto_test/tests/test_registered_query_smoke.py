"""Read-only query contract available for binding to an audited case."""

import os

import pytest

from modules.auto_test.core.regression_checks import execute_sales_queries
from modules.auto_test.core.regression_session import regression_session
from modules.auto_test.facades.api.sales_order_facade import SalesOrderFacade
from tools.report_generator import TestReportGenerator as Report


@pytest.mark.api
@pytest.mark.core
def test_sales_order_query_smoke():
    report = Report()
    with regression_session(os.environ.get("TEST_ENV", "test")) as client:
        execute_sales_queries(SalesOrderFacade(client), report, scope="smoke")
    if report.exit_code == 2:
        pytest.skip("Sales order baseline data unavailable; verification incomplete")
    assert report.exit_code == 0, "Sales order list business contract failed"

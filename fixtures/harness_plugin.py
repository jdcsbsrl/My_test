"""Single source of truth for pytest hooks and harness fixtures."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from playwright.sync_api import Page

from modules.auto_test.core.agent_feedback import append_auto_failure_record
from modules.auto_test.core.agent_loader import bootstrap_agent_workspace, repo_root
from modules.auto_test.core.agent_phases import resolve_agent_phase
from modules.auto_test.core.agent_specialization import resolve_agent_domain
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import ConfigManager, get_config
from modules.auto_test.core.execution_auth import check_authorization, get_auth_manager, report_sensitive_operation
from modules.auto_test.core.harness_metrics import HarnessMetricsRecorder, default_metrics_path, metrics_enabled
from modules.auto_test.core.logger import get_logger, setup_logger
from modules.auto_test.drivers.browser_driver import BrowserDriver

setup_logger()
logger = get_logger()

_metrics = None


def pytest_configure(config: pytest.Config) -> None:
    global _metrics
    try:
        phase = resolve_agent_phase()
        domain = resolve_agent_domain()
        info = bootstrap_agent_workspace(phase=phase, domain=domain)
        n = len(info.get("documents", []))
        rec = info.get("recommended_documents") or []
        if info.get("ok"):
            logger.info(
                "Agent workspace bootstrap: manifest OK (%s documents, phase=%s, domain=%s, recommended=%s)",
                n,
                info.get("phase"),
                info.get("domain"),
                rec[:5],
            )
        else:
            logger.warning("Agent workspace bootstrap: missing paths %s", info.get("missing"))
        ps = info.get("progress_summary")
        if ps:
            logger.info("Agent progress summary: %s", ps)
        adv = info.get("context_advisory")
        if adv:
            logger.warning("%s", adv)
    except Exception as exc:
        logger.warning("Agent workspace bootstrap skipped: %s", exc)

    try:
        if metrics_enabled():
            _metrics = HarnessMetricsRecorder(default_metrics_path(repo_root()))
            _metrics.session_start(pytest_version=pytest.__version__, cwd=os.getcwd())
    except Exception as exc:
        logger.debug("harness metrics init skipped: %s", exc)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    global _metrics
    if _metrics is not None and report.when == "call":
        try:
            keywords: list[str] = []
            try:
                node = getattr(report, "node", None)
                if node is not None and hasattr(node, "keywords"):
                    keywords = sorted(node.keywords)
            except Exception:
                keywords = []
            _metrics.test_call_report(
                nodeid=report.nodeid,
                outcome=report.outcome,
                duration=getattr(report, "duration", None),
                keywords=keywords,
            )
        except Exception as exc:
            logger.debug("harness metrics: %s", exc)

    if os.getenv("AGENT_FEEDBACK_AUTO", "").lower() not in ("1", "true", "yes"):
        return
    if report.when != "call" or not report.failed:
        return
    try:
        append_auto_failure_record(report)
    except Exception as exc:
        logger.debug("agent feedback: %s", exc)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _metrics
    if _metrics is None:
        return
    try:
        _metrics.session_end(exitstatus=exitstatus)
    except Exception as exc:
        logger.debug("harness metrics finish: %s", exc)
    finally:
        _metrics = None


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--env",
        action="store",
        default="test",
        help="Config profile: test, test_env (dedicated test stack), uat (not: prod)",
    )
    parser.addoption("--browser", action="store", default="chromium", help="Browser: chromium, firefox, webkit")
    parser.addoption("--headed", action="store_true", default=False, help="Run browser in headed mode")
    parser.addoption("--slow-mo", action="store", default="0", help="Slow motion delay in milliseconds")
    parser.addoption("--skip-auth", action="store_true", default=False, help="Skip authorization check (for debugging)")


@pytest.fixture(scope="session", autouse=True)
def load_config(request: pytest.FixtureRequest) -> None:
    env = request.config.getoption("--env")

    ConfigManager._instance = None
    get_config(env)
    logger.info(f"Test environment loaded: {env}")


@pytest.fixture(scope="session", autouse=True)
def check_execution_authorization(request: pytest.FixtureRequest) -> None:
    skip_auth = request.config.getoption("--skip-auth")
    if skip_auth:
        logger.warning("授权检查已通过 --skip-auth 跳过")
        return

    auth_manager = get_auth_manager()
    status = auth_manager.get_authorization_status()

    if not status["authorized"]:
        check_authorization()


@pytest.fixture(scope="session")
def api_client() -> APIClient:
    client = APIClient()
    yield client
    client.close()


def _create_sales_order_facade(api_client: APIClient) -> SalesOrderFacade:
    """创建已认证的 SalesOrderFacade 实例。"""
    from modules.auto_test.facades.auth_facade import AuthFacade
    from modules.auto_test.facades.sales_order_facade import SalesOrderFacade

    auth = AuthFacade(api_client)
    auth.apply_default_api_headers()
    token = auth.get_token()
    api_client.set_auth_token(token)
    return SalesOrderFacade(api_client)


@pytest.fixture(scope="function")
def sales_order_facade(api_client: APIClient):
    """Authenticated SalesOrderFacade for a single test."""
    return _create_sales_order_facade(api_client)


@pytest.fixture(scope="class")
def sales_order_facade_class(api_client: APIClient):
    """Class-scoped authenticated facade (shared session client)."""
    yield _create_sales_order_facade(api_client)


@pytest.fixture(scope="session")
def browser_driver_session(request: pytest.FixtureRequest) -> Generator[BrowserDriver, None, None]:
    """One BrowserDriver / browser process for the whole test session."""
    browser = request.config.getoption("--browser")
    headed = request.config.getoption("--headed")
    slow_mo = int(request.config.getoption("--slow-mo"))
    driver = BrowserDriver()
    driver.start_browser(browser=browser, headless=not headed, slow_mo=slow_mo)
    yield driver
    driver.shutdown_browser()


@pytest.fixture(scope="function")
def browser_page(request: pytest.FixtureRequest, browser_driver_session: BrowserDriver) -> Page:
    """Fresh BrowserContext + Page per test; trace on failure."""
    context, page = browser_driver_session.new_context_and_page()

    yield page

    trace_path = None
    if request.node.rep_call.failed if hasattr(request.node, "rep_call") else False:
        trace_path = f"reports/traces/trace-{request.node.name}.zip"

    browser_driver_session.close_context(context, trace_path=trace_path)


def pytest_runtest_setup(item: pytest.Item) -> None:
    sensitive_marker = item.get_closest_marker("sensitive")
    if sensitive_marker:
        operation_type = sensitive_marker.kwargs.get("operation", "增删改操作")
        target_entities = sensitive_marker.kwargs.get("entities", [])
        estimated_impact = sensitive_marker.kwargs.get("impact", "可能影响数据完整性")

        report_sensitive_operation(
            test_name=item.name,
            operation_type=operation_type,
            target_entities=target_entities,
            estimated_impact=estimated_impact,
        )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

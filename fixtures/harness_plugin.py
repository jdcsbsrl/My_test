"""Single pytest entry point for the auto-test harness.

This module owns the hooks and shared fixtures for every test path.  In
particular, browser contexts/pages and HTTP clients are deliberately function
scoped; only the browser process and immutable authentication state are
session scoped inside one pytest worker.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import requests
from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from modules.auto_test.core.agent_feedback import append_auto_failure_record
from modules.auto_test.core.agent_loader import bootstrap_agent_workspace
from modules.auto_test.core.agent_phases import resolve_agent_phase
from modules.auto_test.core.agent_specialization import resolve_agent_domain
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import ConfigManager, get_config
from modules.auto_test.core.execution_auth import (
    AUTHORIZATION_ENV_VAR,
    ExecutionAuthManager,
    check_authorization,
    get_auth_manager,
    report_sensitive_operation,
)
from modules.auto_test.core.harness_metrics import HarnessMetricsRecorder, metrics_enabled
from modules.auto_test.core.secret_provider import get_secret
from modules.auto_test.core.test_data_factory import (
    DatabaseDataGenerator,
    EnhancedTestDataFactory,
    SchemaBasedFactory,
)
from modules.auto_test.core.test_data_lifecycle import TestDataLifecycleManager
from modules.auto_test.core.token_manager import TokenManager, get_token_manager
from modules.auto_test.drivers.browser_driver import BrowserDriver
from modules.auto_test.pages.login_page import LoginPage
from modules.trae_test.utils.runtime_paths import runtime_dir

load_dotenv()


def _safe_runtime_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return cleaned or "unknown"


def _safe_artifact_name(name: str) -> str:
    if not name or name in {".", ".."} or any(separator in name for separator in ("/", "\\", ":")):
        raise ValueError(f"Artifact name must not contain path separators: {name!r}")
    return name


def _worker_id() -> str:
    return _safe_runtime_component(os.getenv("PYTEST_XDIST_WORKER", "master"))


def _run_id(config: pytest.Config | None = None) -> str:
    state = getattr(config, "_harness_state", None) if config is not None else None
    if isinstance(state, dict) and state.get("run_id"):
        return str(state["run_id"])
    return _safe_runtime_component(os.getenv("TEST_RUN_ID") or os.getenv("PYTEST_XDIST_TESTRUNUID") or "local")


def _runtime_reports_dir(config: pytest.Config | None = None) -> Path:
    target = runtime_dir("reports") / "runs" / _run_id(config) / _worker_id()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _runtime_screenshots_dir(config: pytest.Config | None = None) -> Path:
    target = _runtime_reports_dir(config) / "screenshots"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _state(config: pytest.Config) -> dict[str, Any]:
    state = getattr(config, "_harness_state", None)
    if not isinstance(state, dict):
        state = {"attempts": {}, "results": [], "metrics": None, "run_id": _run_id()}
        config._harness_state = state
    return state


def _ensure_runtime_directories(config: pytest.Config | None = None) -> None:
    for directory in (
        runtime_dir("cache") / "pytest",
        runtime_dir("cache") / "ruff",
        runtime_dir("downloads"),
        runtime_dir("uploads"),
        _runtime_reports_dir(config),
        runtime_dir("sheet_build"),
    ):
        directory.mkdir(parents=True, exist_ok=True)


def pytest_configure(config: pytest.Config) -> None:
    """Initialize fresh per-session state and worker-isolated artifacts."""
    config._harness_state = {
        "attempts": {},
        "results": [],
        "metrics": None,
        "run_id": _safe_runtime_component(
            os.getenv("TEST_RUN_ID") or os.getenv("PYTEST_XDIST_TESTRUNUID") or f"local-{uuid.uuid4().hex}"
        ),
    }
    state = _state(config)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

    config._test_run_metadata = {
        "run_id": state["run_id"],
        "worker_id": _worker_id(),
        "environment": os.getenv("TEST_ENV", "test"),
        "browser": os.getenv("PLAYWRIGHT_BROWSER_CHANNEL", "chromium"),
        "commit_sha": os.getenv("GITHUB_SHA", "local"),
    }
    _ensure_runtime_directories(config)
    with (_runtime_reports_dir(config) / "test-run.json").open("w", encoding="utf-8") as stream:
        json.dump(config._test_run_metadata, stream, ensure_ascii=False, indent=2)

    try:
        phase = resolve_agent_phase()
        domain = resolve_agent_domain()
        info = bootstrap_agent_workspace(phase=phase, domain=domain)
        if info.get("ok"):
            logger.info(
                "Agent workspace bootstrap: manifest OK (%s documents, phase=%s, domain=%s, recommended=%s)",
                len(info.get("documents", [])),
                info.get("phase"),
                info.get("domain"),
                (info.get("recommended_documents") or [])[:5],
            )
        else:
            logger.warning("Agent workspace bootstrap: missing paths %s", info.get("missing"))
        if info.get("progress_summary"):
            logger.info("Agent progress summary: %s", info["progress_summary"])
        if info.get("context_advisory"):
            logger.warning("%s", info["context_advisory"])
    except Exception as exc:
        logger.warning("Agent workspace bootstrap skipped: %s", exc)

    try:
        if metrics_enabled():
            metrics = HarnessMetricsRecorder(_runtime_reports_dir(config) / "harness_metrics" / "events.jsonl")
            metrics.session_start(pytest_version=pytest.__version__, cwd=os.getcwd())
            state["metrics"] = metrics
    except Exception as exc:
        logger.debug("harness metrics init skipped: %s", exc)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Finalize worker-local reports and release singleton state."""
    config = session.config
    state = _state(config)
    results = state.get("results", [])
    summary = {"passed": 0, "failed": 0, "flaky_passed": 0, "categories": {}}
    for result in results:
        if result.get("status") == "flaky_passed":
            summary["flaky_passed"] += 1
        elif result.get("outcome") == "passed":
            summary["passed"] += 1
        elif result.get("outcome") == "failed":
            summary["failed"] += 1
        category = result.get("failure_category")
        if category:
            summary["categories"][category] = summary["categories"].get(category, 0) + 1
    summary.update({"exitstatus": exitstatus, "run_id": state.get("run_id"), "worker_id": _worker_id()})
    try:
        _ensure_runtime_directories(config)
        with (_runtime_reports_dir(config) / "test-summary.json").open("w", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2)
        metrics = state.get("metrics")
        if metrics is not None:
            metrics.session_end(exitstatus=exitstatus)
    except Exception as exc:
        logger.debug("harness session finalization: %s", exc)
    finally:
        state["metrics"] = None
        state["attempts"].clear()
        state["results"].clear()
        ConfigManager._instance = None
        TokenManager.reset()
        ExecutionAuthManager._instance = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Record reports once per item and expose rep_call during fixture teardown."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
    if report.when != "call":
        return
    state = _state(item.config)
    attempts = state["attempts"]
    attempts[item.nodeid] = attempts.get(item.nodeid, 0) + 1
    count = attempts[item.nodeid]
    metadata = getattr(item.config, "_test_run_metadata", {})
    payload = {
        **metadata,
        "nodeid": item.nodeid,
        "outcome": report.outcome,
        "attempt": count,
        "failure_category": _classify_failure(report) if report.failed else None,
    }
    if count > 1 and report.outcome == "passed":
        payload["status"] = "flaky_passed"
        report.user_properties.append(("flaky_passed", "true"))
    _ensure_runtime_directories(item.config)
    with (_runtime_reports_dir(item.config) / "test-attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    state["results"].append(payload)

    metrics = state.get("metrics")
    if metrics is not None:
        try:
            metrics.test_call_report(
                nodeid=report.nodeid,
                outcome=report.outcome,
                duration=getattr(report, "duration", None),
                keywords=sorted(item.keywords),
            )
        except Exception as exc:
            logger.debug("harness metrics: %s", exc)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if os.getenv("AGENT_FEEDBACK_AUTO", "").lower() in {"1", "true", "yes"} and report.when == "call" and report.failed:
        try:
            append_auto_failure_record(report)
        except Exception as exc:
            logger.debug("agent feedback: %s", exc)


def _classify_failure(report: pytest.TestReport) -> str:
    text = str(getattr(report, "longrepr", "")).lower()
    if "timeout" in text:
        return "timeout"
    if any(token in text for token in ("401", "403", "authentication", "login")):
        return "authentication_failure"
    if any(token in text for token in ("connectionerror", "connecttimeout", "502", "503", "504")):
        return "environment_failure"
    if any(token in text for token in ("assertionerror", "assert ")):
        return "product_or_test_assertion"
    return "unknown"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--env", action="store", default="test", help="Config profile: test, test_env, uat")
    parser.addoption("--browser", action="store", default="chromium", help="Browser: chromium, firefox, webkit")
    parser.addoption("--headed", action="store_true", default=False, help="Run browser in headed mode")
    parser.addoption("--slow-mo", action="store", default="0", help="Slow motion delay in milliseconds")
    parser.addoption(
        "--skip-auth",
        action="store_true",
        default=False,
        help="Deprecated safety option; using it is rejected",
    )


@pytest.fixture(scope="session", autouse=True)
def load_config(request: pytest.FixtureRequest) -> None:
    """Load a fresh environment configuration for each pytest session."""
    ConfigManager._instance = None
    get_config(request.config.getoption("--env"))


@pytest.fixture(scope="session", autouse=True)
def check_execution_authorization(request: pytest.FixtureRequest) -> None:
    _require_execution_authorization(request)


def _require_execution_authorization(request: pytest.FixtureRequest) -> None:
    """Require explicit authorization; malformed or missing state is denied."""
    if request.config.getoption("--skip-auth"):
        raise pytest.UsageError("--skip-auth is disabled; explicit execution authorization is mandatory")

    # The manager is process-global. Reset it at the session boundary so a
    # prior pytest invocation cannot authorize this one through stale memory.
    ExecutionAuthManager._instance = None
    try:
        status = get_auth_manager().get_authorization_status()
    except Exception:
        raise
    if not isinstance(status, dict) or status.get("authorized") is not True:
        check_authorization()
        raise pytest.UsageError("Test execution authorization was not explicitly granted")
    if not os.getenv(AUTHORIZATION_ENV_VAR, "").strip():
        raise pytest.UsageError("Test execution authorization is missing")


@pytest.fixture(scope="session")
def config_manager() -> ConfigManager:
    return get_config()


def _close_database_data_generator(generator: DatabaseDataGenerator | None) -> None:
    if generator is None:
        return
    db_helper = getattr(generator, "db_helper", None)
    if db_helper is None:
        return
    try:
        close = getattr(db_helper, "close", None)
        if callable(close):
            close()
    finally:
        generator.db_helper = None


@pytest.fixture(scope="function")
def test_data_factory():
    factory = EnhancedTestDataFactory()
    try:
        yield factory
    finally:
        _close_database_data_generator(getattr(factory, "_generators", {}).get("database"))


@pytest.fixture(scope="function")
def data_lifecycle(config_manager: ConfigManager):
    manager = TestDataLifecycleManager(env=config_manager.env)
    try:
        yield manager
    finally:
        manager.execute_cleanup()


@pytest.fixture(scope="function")
def database_data_generator():
    generator = DatabaseDataGenerator()
    try:
        yield generator
    finally:
        _close_database_data_generator(generator)


@pytest.fixture(scope="function")
def schema_factory() -> SchemaBasedFactory:
    return SchemaBasedFactory()


@pytest.fixture(scope="session")
def browser(request: pytest.FixtureRequest, config_manager: ConfigManager) -> Browser:
    driver = BrowserDriver(run_id=_run_id(request.config), worker_id=_worker_id())
    driver.start_browser(
        browser=config_manager.get("playwright.browser", "chromium"),
        headless=config_manager.get("playwright.headless", True),
        slow_mo=config_manager.get("playwright.slow_mo", 0),
    )
    try:
        yield driver.browser
    finally:
        driver.shutdown_browser()


@pytest.fixture(scope="function")
def context(
    request: pytest.FixtureRequest,
    browser: Browser,
    config_manager: ConfigManager,
    authenticated_storage_state: str,
):
    viewport = config_manager.get("playwright.viewport", {"width": 1920, "height": 1080})
    options: dict[str, Any] = {
        "viewport": viewport,
        "accept_downloads": True,
        "record_video_dir": None,
        "record_video_size": None,
        "storage_state": authenticated_storage_state,
    }
    if config_manager.get("playwright.video", "off") in {"on", "retain-on-failure"}:
        options["record_video_dir"] = str(_runtime_reports_dir(request.config) / "videos")
        options["record_video_size"] = viewport
    browser_context = browser.new_context(**options)
    trace_started = False
    try:
        if config_manager.get("playwright.trace", "off") in {"on", "retain-on-failure", "on-first-retry"}:
            browser_context.tracing.start(screenshots=True, snapshots=True, sources=True)
            trace_started = True
        yield browser_context
    finally:
        errors: list[Exception] = []
        if trace_started:
            trace_path = _runtime_reports_dir(request.config) / "traces" / f"test_trace_{uuid.uuid4().hex[:8]}.zip"
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                browser_context.tracing.stop(path=str(trace_path))
            except Exception as exc:
                errors.append(exc)
        try:
            browser_context.close()
        except Exception as exc:
            errors.append(exc)
        if errors:
            raise RuntimeError("Browser context teardown failed") from errors[0]


@pytest.fixture(scope="session")
def _authenticated_session(
    request: pytest.FixtureRequest,
    browser: Browser,
    config_manager: ConfigManager,
    tmp_path_factory,
    test_user_credentials: dict[str, str],
) -> dict[str, Any]:
    """Authenticate once and expose all session-level authentication artifacts."""
    auth_dir = tmp_path_factory.mktemp("playwright-auth")
    auth_file = auth_dir / "state.json"
    for attempt in range(2):
        auth_context = None
        auth_page = None
        login_result: dict[str, Any] = {}
        try:
            auth_context = browser.new_context(
                viewport=config_manager.get("playwright.viewport", {"width": 1920, "height": 1080})
            )
            auth_page = auth_context.new_page()

            def handle_response(response) -> None:
                if "/auth/login" in response.url:
                    try:
                        login_result["response"] = response.json()
                        headers = response.request.all_headers()
                        login_result["clientid"] = headers.get("clientid") or headers.get("client-id")
                    except Exception:
                        pass

            auth_page.on("response", handle_response)
            if not LoginPage(auth_page).login(test_user_credentials["username"], test_user_credentials["password"]):
                raise RuntimeError("登录流程未成功返回")
            if "response" not in login_result:
                raise RuntimeError("Failed to capture login API response")
            _assert_authenticated_page(auth_page, config_manager.base_url, timeout=30000)
            auth_context.storage_state(path=str(auth_file))
            login_response = login_result["response"]
            login_response["_clientid"] = login_result.get("clientid")
            login_response["_cookies"] = auth_page.context.cookies()
            return {"storage_state": str(auth_file), "login_response": login_response}
        except Exception as exc:
            if auth_page is not None:
                _capture_authentication_diagnostic(auth_page, f"session-{attempt + 1}", request.config)
            if attempt == 1:
                pytest.fail(f"Unable to create authenticated session: {exc}")
        finally:
            if auth_page is not None:
                try:
                    auth_page.close()
                except Exception:
                    logger.debug("failed to close authentication page", exc_info=True)
            if auth_context is not None:
                try:
                    auth_context.close()
                except Exception:
                    logger.debug("failed to close authentication context", exc_info=True)
    raise AssertionError("unreachable")


@pytest.fixture(scope="function")
def page(context: BrowserContext) -> Page:
    browser_page = context.new_page()
    try:
        yield browser_page
    finally:
        browser_page.close()


@pytest.fixture(scope="function")
def logged_in_page(request: pytest.FixtureRequest, page: Page, config_manager: ConfigManager) -> Page:
    credentials = _credentials()
    try:
        _assert_authenticated_page(page, config_manager.base_url, timeout=60000)
    except Exception as exc:
        logger.warning("认证状态失效，尝试在当前 context 重新登录: %s", exc)
        try:
            if not LoginPage(page).login(credentials["username"], credentials["password"]):
                raise RuntimeError("重新登录未成功返回")
            _assert_authenticated_page(page, config_manager.base_url, timeout=30000)
        except Exception as retry_exc:
            _capture_authentication_diagnostic(page, "logged-in-page", request.config)
            pytest.fail(f"认证状态无效，重新登录失败: {retry_exc}")
    yield page


def _credentials() -> dict[str, str]:
    username = get_secret("USERNAME")
    password = get_secret("PASSWORD")
    if not username or not password:
        pytest.fail("TEST_USERNAME and/or TEST_PASSWORD not set")
    return {"username": str(username), "password": str(password)}


def _assert_authenticated_page(page: Page, base_url: str, timeout: int) -> None:
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1000)
    if "/login" in page.url.lower():
        raise RuntimeError(f"页面被重定向到登录页: {page.url}")
    if base_url and not page.url.startswith(base_url.rstrip("/")):
        raise RuntimeError(f"页面未停留在目标应用: {page.url}")


def _capture_authentication_diagnostic(page: Page, label: str, config: pytest.Config | None = None) -> None:
    try:
        path = _runtime_screenshots_dir(config) / f"authentication-{label}-{uuid.uuid4().hex[:8]}.png"
        page.screenshot(path=str(path), full_page=True)
        with (_runtime_reports_dir(config) / "authentication-failure.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"label": label, "url": page.url}, ensure_ascii=False) + "\n")
    except Exception:
        pass


@pytest.fixture(scope="function")
def login_page(page: Page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture(scope="session")
def test_user_credentials() -> dict[str, str]:
    return _credentials()


@pytest.fixture(scope="function")
def temp_report_dir(tmp_path: Path) -> Path:
    report_dir = tmp_path / "reports"
    report_dir.mkdir(exist_ok=True)
    return report_dir


@pytest.fixture(scope="session")
def api_base_url(config_manager: ConfigManager) -> str:
    return config_manager.api_base_url


@pytest.fixture(scope="session")
def ui_base_url(config_manager: ConfigManager) -> str:
    return config_manager.base_url


@pytest.fixture(scope="session")
def token_manager() -> TokenManager:
    return get_token_manager()


@pytest.fixture(scope="session")
def authenticated_storage_state(_authenticated_session: dict[str, Any]) -> str:
    return _authenticated_session["storage_state"]


@pytest.fixture(scope="session")
def login_response(
    _authenticated_session: dict[str, Any],
) -> dict:
    return _authenticated_session["login_response"]


@pytest.fixture(scope="session")
def login_token(login_response: dict) -> str:
    if login_response.get("code") == 200:
        data = login_response.get("data") or {}
        token = data.get("token") or data.get("access_token")
        if token:
            return str(token)
    pytest.fail("Failed to extract token from login response")


@pytest.fixture(scope="function")
def http_client():
    session = requests.Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def authenticated_http_client(http_client, login_token: str, login_response: dict) -> requests.Session:
    clientid = login_response.get("_clientid") or get_secret("CLIENTID")
    http_client.headers.update({"Authorization": f"Bearer {login_token}", "Content-Type": "application/json"})
    if clientid:
        http_client.headers["clientid"] = clientid
    for cookie in login_response.get("_cookies", []):
        http_client.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )
    try:
        yield http_client
    finally:
        # The owning http_client fixture performs the actual close.
        http_client.headers.pop("Authorization", None)


@pytest.fixture(scope="function")
def api_client() -> APIClient:
    client = APIClient()
    try:
        yield client
    finally:
        client.close()


def _create_sales_order_facade(api_client: APIClient):
    from modules.auto_test.facades.auth_facade import AuthFacade
    from modules.auto_test.facades.sales_order_facade import SalesOrderFacade

    auth = AuthFacade(api_client)
    auth.apply_default_api_headers()
    api_client.set_auth_token(auth.get_token())
    return SalesOrderFacade(api_client)


@pytest.fixture(scope="function")
def sales_order_facade(api_client: APIClient):
    return _create_sales_order_facade(api_client)


@pytest.fixture(scope="function")
def sales_order_facade_class(api_client: APIClient):
    yield _create_sales_order_facade(api_client)


@pytest.fixture(scope="session")
def browser_driver_session(request: pytest.FixtureRequest):
    driver = BrowserDriver(run_id=_run_id(request.config), worker_id=_worker_id())
    driver.start_browser(
        browser=request.config.getoption("--browser"),
        headless=not request.config.getoption("--headed"),
        slow_mo=int(request.config.getoption("--slow-mo")),
    )
    try:
        yield driver
    finally:
        driver.shutdown_browser()


@pytest.fixture(scope="function")
def browser_page(request: pytest.FixtureRequest, browser_driver_session: BrowserDriver) -> Page:
    context, page = browser_driver_session.new_context_and_page()
    trace_path = None
    try:
        yield page
    finally:
        if getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed:
            trace_dir = _runtime_reports_dir(request.config) / "traces"
            trace_dir.mkdir(parents=True, exist_ok=True)
            trace_path = str(trace_dir / f"trace-{_safe_runtime_component(request.node.nodeid)}.zip")
        browser_driver_session.close_context(context, page=page, trace_path=trace_path)


@pytest.fixture(scope="function")
def auto_cleanup():
    cleanup_items: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def add_cleanup(func, *args, **kwargs) -> None:
        cleanup_items.append((func, args, kwargs))

    yield add_cleanup
    failures: list[Exception] = []
    for func, args, kwargs in reversed(cleanup_items):
        try:
            if func(*args, **kwargs) is False:
                raise RuntimeError(f"Cleanup callback returned False: {func!r}")
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise RuntimeError(f"{len(failures)} cleanup callback(s) failed") from failures[0]


@pytest.fixture(scope="function")
def screenshot_helper(page: Page, request: pytest.FixtureRequest):
    def take_screenshot(name: str) -> str:
        safe_name = _safe_artifact_name(name)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = _runtime_screenshots_dir(request.config) / f"{safe_name}_{timestamp}_{uuid.uuid4().hex[:6]}.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)

    return take_screenshot


def pytest_runtest_setup(item: pytest.Item) -> None:
    sensitive_marker = item.get_closest_marker("sensitive")
    if sensitive_marker:
        report_sensitive_operation(
            test_name=item.name,
            operation_type=sensitive_marker.kwargs.get("operation", "增删改操作"),
            target_entities=sensitive_marker.kwargs.get("entities", []),
            estimated_impact=sensitive_marker.kwargs.get("impact", "可能影响数据完整性"),
        )


try:
    from modules.auto_test.core.logger import get_logger, setup_logger

    setup_logger()
    logger = get_logger()
except Exception:  # pragma: no cover - logging must never prevent collection
    import logging

    logger = logging.getLogger(__name__)

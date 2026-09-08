"""Environment-scoped authentication for a single CLI regression run."""

from contextlib import contextmanager
from urllib.parse import urlsplit

from .api_client import APIClient
from .config_manager import get_environment
from .execution_auth import check_authorization
from .secret_provider import get_secret


def _browser_authentication(config) -> dict:
    from modules.auto_test.drivers.browser_driver import BrowserDriver
    from modules.auto_test.pages.login_page import LoginPage

    username = get_secret("USERNAME", environment=config.env)
    password = get_secret("PASSWORD", environment=config.env)
    if not username or not password:
        raise RuntimeError("Environment login credentials are missing")
    driver = BrowserDriver(config=config)
    captured = {}
    origin = urlsplit(config.api_base_url)

    def capture(response):
        target = urlsplit(response.url)
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
            return
        if not target.path.endswith("/auth/login") or response.status != 200:
            return
        try:
            body = response.json()
            data = body.get("data") or {}
            token = data.get("token") or data.get("access_token")
            clientid = response.request.all_headers().get("clientid")
            if body.get("code") == 200 and token and clientid:
                captured.update(token=token, clientid=clientid)
        except (ValueError, AttributeError):
            return

    try:
        browser = driver.start_browser(browser="chromium", headless=True, slow_mo=0)
        # No tracing, storage-state files, or credential screenshots for this session.
        context = browser.new_context()
        page = context.new_page()
        page.on("response", capture)
        if not LoginPage(page, config=config).login(username, password) or not captured:
            raise RuntimeError("Browser authentication did not return a usable session")
        captured["cookies"] = context.cookies(config.api_base_url)
        return captured
    finally:
        driver.shutdown_browser()


@contextmanager
def regression_session(env_name: str, *, force_login: bool = False):
    """Keep browser-derived credentials in memory and close HTTP resources on failure."""
    if env_name not in {"test", "uat"}:
        raise ValueError("Only test/uat are allowed")
    check_authorization()
    config = get_environment(env_name)
    token = get_secret("TOKEN", environment=env_name)
    clientid = get_secret("CLIENTID", environment=env_name)
    credentials = {"token": token, "clientid": clientid, "cookies": []}
    if force_login or not token or not clientid:
        credentials = _browser_authentication(config)
    client = APIClient(config.api_base_url)
    try:
        # Facades constructed within this context must use this same validated
        # environment, rather than resolve the process-default TEST_ENV again.
        client._test_erp_environment_config = config
        client.set_body_logging(False)
        client.set_auth_token(credentials["token"])
        client.set_header("clientid", credentials["clientid"])
        for cookie in credentials["cookies"]:
            client.session.cookies.set(
                cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path", "/")
            )
        yield client
    finally:
        client.clear_auth()
        client.session.headers.pop("clientid", None)
        client.session.cookies.clear()
        delattr(client, "_test_erp_environment_config")
        credentials.clear()
        client.close()

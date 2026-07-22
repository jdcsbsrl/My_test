import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _origin_from_api_base(api_base_url: str) -> str:
    p = urlparse(api_base_url)
    return f"{p.scheme}://{p.netloc}"


@dataclass
class Credentials:
    username: str
    password: str


@dataclass
class AuthConfig:
    clientid: str
    encrypt_key: str
    isencrypt: str
    content_language: str
    origin: str
    user_agent: str


class SecretManager:
    _instance: "SecretManager | None" = None

    def __new__(cls) -> "SecretManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._secrets_cache: dict[str, Any] = {}

    def get_credentials(self, key: str = "default") -> Credentials:
        cache_key = f"credentials_{key}"
        if cache_key in self._secrets_cache:
            return self._secrets_cache[cache_key]

        username = os.getenv("TEST_USERNAME")
        password = os.getenv("TEST_PASSWORD")

        if not username or not password:
            raise ValueError(
                "Credentials not found in environment variables. "
                "Please set TEST_USERNAME and TEST_PASSWORD in .env file."
            )

        credentials = Credentials(username=username, password=password)
        self._secrets_cache[cache_key] = credentials
        return credentials

    def get_auth_config(self, *, api_base_url: str | None = None, env: str | None = None) -> AuthConfig:
        cache_key = f"auth_config_{api_base_url or 'default'}_{env or 'default'}"
        if cache_key in self._secrets_cache:
            return self._secrets_cache[cache_key]

        from modules.auto_test.core.config_manager import get_config

        if env is None:
            try:
                cfg = get_config()
                env = cfg.env
            except Exception:
                env = "test"

        cfg_base = api_base_url or get_config(env).api_base_url

        clientid = os.getenv(f"TEST_{env.upper()}_CLIENTID") or os.getenv("TEST_CLIENTID")
        encrypt_key = os.getenv(f"TEST_{env.upper()}_ENCRYPT_KEY") or os.getenv("TEST_ENCRYPT_KEY")
        isencrypt = os.getenv(f"TEST_{env.upper()}_ISENCRYPT") or os.getenv("TEST_ISENCRYPT", "true")
        content_language = os.getenv(f"TEST_{env.upper()}_CONTENT_LANGUAGE") or os.getenv(
            "TEST_CONTENT_LANGUAGE", "zh_CN"
        )
        origin = os.getenv(f"TEST_{env.upper()}_ORIGIN") or os.getenv("TEST_ORIGIN") or _origin_from_api_base(cfg_base)
        user_agent = os.getenv(f"TEST_{env.upper()}_USER_AGENT") or os.getenv(
            "TEST_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        if not clientid:
            raise ValueError(
                f"TEST_{env.upper()}_CLIENTID (or TEST_CLIENTID) must be set in the environment or .env file."
            )
        if not encrypt_key:
            raise ValueError(
                f"TEST_{env.upper()}_ENCRYPT_KEY (or TEST_ENCRYPT_KEY) not found in environment variables. "
                "Please set it in .env file."
            )

        auth_config = AuthConfig(
            clientid=clientid,
            encrypt_key=encrypt_key,
            isencrypt=isencrypt,
            content_language=content_language,
            origin=origin,
            user_agent=user_agent,
        )
        self._secrets_cache[cache_key] = auth_config
        return auth_config

    def get_api_login_password_payload(self) -> str:
        """JSON `password` field for auth login (often a pre-encrypted value from the real client)."""
        cache_key = "api_login_password_payload"
        if cache_key in self._secrets_cache:
            return str(self._secrets_cache[cache_key])

        value = os.getenv("TEST_ENCRYPTED_LOGIN_PASSWORD") or os.getenv("TEST_PASSWORD")
        if not value:
            raise ValueError("Set TEST_ENCRYPTED_LOGIN_PASSWORD or TEST_PASSWORD for the login API request body.")
        self._secrets_cache[cache_key] = value
        return value

    def get_proxy(self) -> str | None:
        if "proxy" in self._secrets_cache:
            return self._secrets_cache["proxy"]

        proxy = os.getenv("TEST_PROXY")
        self._secrets_cache["proxy"] = proxy
        return proxy

    def get_api_key(self, key_name: str = "default") -> str | None:
        env_key = f"API_KEY_{key_name.upper()}"
        return os.getenv(env_key)

    def clear_cache(self) -> None:
        self._secrets_cache.clear()


def get_secret_manager() -> SecretManager:
    return SecretManager()

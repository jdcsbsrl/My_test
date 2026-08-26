"""Token manager for storing and retrieving authentication tokens."""

from dataclasses import dataclass
from datetime import datetime

from modules.auto_test.core.logger import get_logger

logger = get_logger()


@dataclass
class TokenInfo:
    token: str
    env: str
    username: str
    obtained_at: str
    expires_in: int = 7200


class TokenManager:
    _instance: "TokenManager | None" = None

    def __new__(cls) -> "TokenManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._tokens: dict[str, TokenInfo] = {}
        # Tokens are intentionally process-local. Persisting bearer tokens creates a
        # reusable credential artifact on disk and makes cleanup/error handling unsafe.
        self._token_file = None
        self._load_tokens()

    def _load_tokens(self) -> None:
        # Kept as a no-op for API compatibility with older callers.
        return

    def _save_tokens(self) -> None:
        # Deliberately do not write tokens to files, logs, or other persistent stores.
        return

    def save_token(self, env: str, token: str, username: str, expires_in: int = 7200) -> None:
        env = str(env).strip().lower()
        if env not in {"test", "test_env", "uat"}:
            raise ValueError(f"Token caching is not allowed for environment: {env}")
        if not token or expires_in <= 0:
            raise ValueError("A non-empty token and positive expiry are required")
        self._tokens[env] = TokenInfo(
            token=str(token),
            env=env,
            username=str(username),
            obtained_at=datetime.now().isoformat(),
            expires_in=expires_in,
        )
        self._save_tokens()
        logger.info("已保存 %s 环境的 token", env.upper())

    def get_token(self, env: str) -> str | None:
        env = str(env).strip().lower()
        if env not in {"test", "test_env", "uat"}:
            return None
        info = self._tokens.get(env)
        if info:
            if self._is_token_valid(info):
                logger.info("获取到 %s 环境的有效 token", env.upper())
                return info.token
            else:
                logger.warning("%s 环境的 token 已过期", env.upper())
        return None

    def get_token_info(self, env: str) -> TokenInfo | None:
        return self._tokens.get(str(env).strip().lower())

    def _is_token_valid(self, info: TokenInfo) -> bool:
        try:
            obtained_time = datetime.fromisoformat(info.obtained_at)
            elapsed = (datetime.now() - obtained_time).total_seconds()
            return elapsed < info.expires_in
        except Exception:
            return False

    def clear_token(self, env: str) -> None:
        env = str(env).strip().lower()
        if env in self._tokens:
            del self._tokens[env]
            self._save_tokens()
            logger.info("已清除 %s 环境的 token", env.upper())

    def clear_all_tokens(self) -> None:
        self._tokens.clear()
        logger.info("已清除所有 token")

    def get_all_tokens(self) -> dict[str, TokenInfo]:
        return self._tokens.copy()

    def get_env_vars(self, env: str) -> dict[str, str]:
        env = str(env).strip().lower()
        token = self.get_token(env)
        if not token:
            return {}
        info = self._tokens[env]
        return {
            f"{env.upper()}_TOKEN": token,
            f"{env.upper()}_USERNAME": info.username,
            f"{env.upper()}_OBTAINED_AT": info.obtained_at,
        }

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance._tokens.clear()
        cls._instance = None


def get_token_manager() -> TokenManager:
    return TokenManager()

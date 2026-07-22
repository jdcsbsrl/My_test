"""Token manager for storing and retrieving authentication tokens."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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
        self._token_file = Path(__file__).parent.parent.parent / ".auth_tokens.json"
        self._load_tokens()

    def _load_tokens(self) -> None:
        if self._token_file.exists():
            try:
                with open(self._token_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for env, token_data in data.items():
                        self._tokens[env] = TokenInfo(
                            token=token_data["token"],
                            env=token_data["env"],
                            username=token_data["username"],
                            obtained_at=token_data["obtained_at"],
                            expires_in=token_data.get("expires_in", 7200),
                        )
                logger.info("已加载 %d 个环境的 token", len(self._tokens))
            except Exception as e:
                logger.error("加载 token 文件失败: %s", e)

    def _save_tokens(self) -> None:
        try:
            data = {}
            for env, info in self._tokens.items():
                data[env] = {
                    "token": info.token,
                    "env": info.env,
                    "username": info.username,
                    "obtained_at": info.obtained_at,
                    "expires_in": info.expires_in,
                }
            with open(self._token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("已保存 token 到文件")
        except Exception as e:
            logger.error("保存 token 文件失败: %s", e)

    def save_token(self, env: str, token: str, username: str, expires_in: int = 7200) -> None:
        self._tokens[env] = TokenInfo(
            token=token, env=env, username=username, obtained_at=datetime.now().isoformat(), expires_in=expires_in
        )
        self._save_tokens()
        logger.info("已保存 %s 环境的 token", env.upper())

    def get_token(self, env: str) -> str | None:
        info = self._tokens.get(env)
        if info:
            if self._is_token_valid(info):
                logger.info("获取到 %s 环境的有效 token", env.upper())
                return info.token
            else:
                logger.warning("%s 环境的 token 已过期", env.upper())
        return None

    def get_token_info(self, env: str) -> TokenInfo | None:
        return self._tokens.get(env)

    def _is_token_valid(self, info: TokenInfo) -> bool:
        try:
            obtained_time = datetime.fromisoformat(info.obtained_at)
            elapsed = (datetime.now() - obtained_time).total_seconds()
            return elapsed < info.expires_in
        except Exception:
            return False

    def clear_token(self, env: str) -> None:
        if env in self._tokens:
            del self._tokens[env]
            self._save_tokens()
            logger.info("已清除 %s 环境的 token", env.upper())

    def clear_all_tokens(self) -> None:
        self._tokens.clear()
        if self._token_file.exists():
            self._token_file.unlink()
        logger.info("已清除所有 token")

    def get_all_tokens(self) -> dict[str, TokenInfo]:
        return self._tokens.copy()

    def get_env_vars(self, env: str) -> dict[str, str]:
        token = self.get_token(env)
        if not token:
            return {}
        info = self._tokens[env]
        return {
            f"{env.upper()}_TOKEN": token,
            f"{env.upper()}_USERNAME": info.username,
            f"{env.upper()}_OBTAINED_AT": info.obtained_at,
        }


def get_token_manager() -> TokenManager:
    return TokenManager()

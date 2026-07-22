"""Load ``.env`` from the repository root and validate variables for targeted flows."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_NAMES_PLAINTEXT_LOGIN: tuple[str, ...] = (
    "TEST_USERNAME",
    "TEST_PASSWORD",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_dotenv_from_repo_root(*, override: bool = False, required: bool = True) -> Path | None:
    """Load ``<repo>/.env`` into ``os.environ``.

    If ``required`` is False and the file is missing, returns ``None`` (OS env / CI vars still apply).
    """
    path = repo_root() / ".env"
    if not path.is_file():
        if required:
            raise FileNotFoundError(
                f"未找到项目根目录下的 `.env` 文件：{path}\n"
                "请复制 `.env.example` 为 `.env`，至少填写 TEST_USERNAME 与 TEST_PASSWORD；"
                "或在 CI/本机环境中直接导出同名变量。"
            )
        return None
    load_dotenv(path, override=override)
    return path


def require_plaintext_login_credentials() -> None:
    """Ensure ``TEST_USERNAME`` / ``TEST_PASSWORD`` are set (after optional ``.env`` load)."""
    missing = [k for k in _ENV_NAMES_PLAINTEXT_LOGIN if not (os.getenv(k) or "").strip()]
    if missing:
        raise RuntimeError(
            "浏览器登录回归需要账号与明文口令，请配置以下之一：\n"
            "  1) 项目根目录 `.env` 中的 TEST_USERNAME、TEST_PASSWORD；或\n"
            "  2) 在运行环境中导出上述变量。\n"
            "缺失项：\n" + "\n".join(f"  - {name}" for name in missing)
        )

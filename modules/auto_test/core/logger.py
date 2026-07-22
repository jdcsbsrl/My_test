import sys
from pathlib import Path

from loguru import logger

from modules.auto_test.core.config_manager import get_config


def setup_logger() -> None:
    config = get_config()
    log_level = config.get("log.level", "INFO")
    log_format = config.get(
        "log.format",
        "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format=log_format,
        colorize=True,
    )

    logger.add(
        logs_dir / "test_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level=log_level,
        format=log_format,
        encoding="utf-8",
    )

    logger.add(
        logs_dir / "error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="ERROR",
        format=log_format,
        encoding="utf-8",
    )


def get_logger():
    return logger

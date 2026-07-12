from __future__ import annotations

import logging
import os
from pathlib import Path

LOGGER_NAME = "pr_factory"
DEFAULT_LOG_FILE = "pr_factory.log"
_CONFIGURED = False


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_log_file() -> Path:
    raw_path = os.getenv("PR_FACTORY_LOG_FILE", DEFAULT_LOG_FILE).strip() or DEFAULT_LOG_FILE
    path = Path(raw_path)
    if not path.is_absolute():
        path = repo_root() / path
    return path


def configure_logging(*, force: bool = False) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(LOGGER_NAME)
    if _CONFIGURED and not force:
        return logger

    log_file = get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level_name = os.getenv("PR_FACTORY_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    level = getattr(logging, level_name, logging.INFO)

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file for handler in logger.handlers):
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    logger.setLevel(level)
    logger.propagate = False
    _CONFIGURED = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")

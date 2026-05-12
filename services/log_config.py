"""应用日志：`paperpilot.*` 写入 `logs/` 下滚动文件，级别由 `LOG_LEVEL` 控制（默认 INFO）。"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR_ENV = "PAPERPILOT_LOG_DIR"
# 单文件约 5MB，保留若干备份，避免占满磁盘
_ROTATE_BYTES = 5 * 1024 * 1024
_ROTATE_BACKUP = 5

_SERVICE_FILES = {
    "api": "backend.log",
    "streamlit": "streamlit.log",
}


def level_from_env(default: str = "INFO") -> int:
    name = (os.getenv("LOG_LEVEL") or default).upper().strip()
    return getattr(logging, name, logging.INFO)


def _formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )


def ensure_paperpilot_logging(
    *,
    service: str = "api",
    name: str = "paperpilot",
) -> logging.Logger:
    """
    为 `paperpilot` 及其子 logger 配置日志文件（默认目录 `logs/`）。
    `service`: `api` -> `backend.log`，`streamlit` -> `streamlit.log`。
    若设置环境变量 `LOG_TO_CONSOLE=1`（或 true/yes），则同时输出到 stderr。
    同一进程内可重复调用，仅在首次为根 logger 添加 handler。
    """
    log = logging.getLogger(name)
    level = level_from_env()
    log.setLevel(level)
    if log.handlers:
        return log

    log_dir = (os.getenv(LOG_DIR_ENV) or "logs").strip() or "logs"
    os.makedirs(log_dir, exist_ok=True)
    basename = _SERVICE_FILES.get(service, f"{service}.log")
    path = os.path.join(log_dir, basename)

    file_handler = RotatingFileHandler(
        path,
        maxBytes=_ROTATE_BYTES,
        backupCount=_ROTATE_BACKUP,
        encoding="utf-8",
    )
    file_handler.setFormatter(_formatter())
    log.addHandler(file_handler)

    console = (os.getenv("LOG_TO_CONSOLE") or "").strip().lower()
    if console in ("1", "true", "yes", "on"):
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(_formatter())
        log.addHandler(sh)

    log.propagate = False
    return log

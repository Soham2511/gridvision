"""Structured JSON logging configuration for GridVision."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_ROOT = PROJECT_ROOT / "logs"


class JsonLogFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, default=str)


def setup_logging(
    level: int = logging.INFO,
    log_root: str | Path | None = None,
) -> logging.Logger:
    """Write structured logs to stdout and a rotating endpoint log file."""
    logger = logging.getLogger("gridvision")
    logger.setLevel(level)
    resolved_log_root = Path(
        log_root or os.getenv("GRIDVISION_LOG_DIR", DEFAULT_LOG_ROOT)
    ).expanduser().resolve()
    endpoint_log = resolved_log_root / "endpoints" / "api.jsonl"
    endpoint_log.parent.mkdir(parents=True, exist_ok=True)
    formatter = JsonLogFormatter()

    if not any(getattr(handler, "_gridvision_console", False) for handler in logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        setattr(console_handler, "_gridvision_console", True)
        logger.addHandler(console_handler)

    if not any(
        getattr(handler, "baseFilename", None) == str(endpoint_log)
        for handler in logger.handlers
    ):
        file_handler = RotatingFileHandler(
            endpoint_log,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

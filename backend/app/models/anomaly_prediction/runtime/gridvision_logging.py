"""Shared console and rotating-file logging setup for GridVision processes."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]


def configure_logging(
    log_path: str | Path | None = None,
    level: str | None = None,
) -> Path:
    """Configure idempotent project logging and return the active log file path."""
    destination = Path(
        log_path
        or os.environ.get(
            "GRIDVISION_LOG_FILE",
            ROOT / "logs" / "training" / "anomaly_prediction.log",
        )
    ).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, (level or os.environ.get(
        "GRIDVISION_LOG_LEVEL", "INFO"
    )).upper()))
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    if not any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    ):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)

    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).resolve() == destination
        for handler in root_logger.handlers
    ):
        file_handler = RotatingFileHandler(
            destination,
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    return destination

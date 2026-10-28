"""SQL helpers shared by government-grid ETL and training."""

from __future__ import annotations

from pathlib import Path


def sql_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'

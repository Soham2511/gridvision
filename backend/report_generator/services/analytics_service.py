"""Deterministic descriptive analytics with source paths and methods."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from report_generator.schemas.analysis_schema import DeterministicAnalytics, DerivedMetric
from report_generator.services.json_analyzer import _date_like


def _walk(data: Any, path: str = "$"):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(data, list):
        for value in data:
            yield from _walk(value, f"{path}[*]")
    else:
        yield path, data


def _metric_id(path: str, name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in f"{path}_{name}")
    return safe.strip("_")[:120]


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


class DeterministicAnalyticsEngine:
    def __init__(self, *, max_metrics_per_path: int = 8, max_groups: int = 50) -> None:
        self.max_metrics_per_path = max_metrics_per_path
        self.max_groups = max_groups

    def calculate(self, data: Any) -> DeterministicAnalytics:
        numeric: dict[str, list[float | int]] = defaultdict(list)
        limitations: list[str] = []
        for path, value in _walk(data):
            if _finite_number(value):
                numeric[path].append(value)
        metrics: list[DerivedMetric] = []
        for path, values in sorted(numeric.items()):
            summary: list[tuple[str, float | int, str]] = [
                ("count", len(values), "count finite numeric values at the same JSON path"),
                ("minimum", min(values), "minimum finite numeric value at the same JSON path"),
                ("maximum", max(values), "maximum finite numeric value at the same JSON path"),
            ]
            try:
                median = statistics.median(values)
                if _finite_number(median):
                    summary.append(("median", median, "median of finite numeric values at the same JSON path"))
                else:
                    limitations.append(f"Median omitted for {path}: result exceeded finite numeric range.")
            except (OverflowError, ValueError):
                limitations.append(f"Median omitted for {path}: result exceeded finite numeric range.")
            for name, calculate, method in (
                ("sum", lambda: sum(values), "sum finite numeric values at the same JSON path"),
                ("mean", lambda: statistics.fmean(values), "arithmetic mean of finite numeric values at the same JSON path"),
            ):
                try:
                    result = calculate()
                    if _finite_number(result):
                        summary.append((name, result, method))
                    else:
                        limitations.append(f"{name.title()} omitted for {path}: result exceeded finite numeric range.")
                except (OverflowError, ValueError):
                    limitations.append(f"{name.title()} omitted for {path}: result exceeded finite numeric range.")
            for name, value, method in summary[: self.max_metrics_per_path]:
                metrics.append(
                    DerivedMetric(
                        metric_id=_metric_id(path, name),
                        name=f"{name.title()} for {path}",
                        value=value,
                        source_fields=[path],
                        method=method,
                        sample_count=len(values),
                    )
                )

        comparisons = self._grouped_comparisons(data)
        if numeric and not metrics:
            limitations.append("Numeric fields were present but no supported metric could be calculated.")
        if not numeric:
            limitations.append("No finite numeric values were available for deterministic statistics.")
        return DeterministicAnalytics(metrics=metrics, comparison_tables=comparisons, limitations=limitations)

    def _grouped_comparisons(self, data: Any) -> list[dict[str, Any]]:
        comparisons: list[dict[str, Any]] = []
        stack = [("$", data)]
        while stack:
            path, value = stack.pop()
            if isinstance(value, dict):
                stack.extend((f"{path}.{key}", child) for key, child in value.items())
            elif isinstance(value, list):
                stack.extend((f"{path}[*]", child) for child in value)
                records = [row for row in value if isinstance(row, dict)]
                if len(records) < 2 or len(records) != len(value):
                    continue
                keys = sorted(set().union(*(row.keys() for row in records)))
                dimensions = [
                    key for key in keys
                    if any(isinstance(row.get(key), str) for row in records)
                ]
                measures = [
                    key for key in keys
                    if any(_finite_number(row.get(key)) for row in records)
                ]
                for dimension in dimensions:
                    for measure in measures:
                        grouped: dict[str, list[float | int]] = defaultdict(list)
                        for row in records:
                            key = row.get(dimension)
                            number = row.get(measure)
                            if isinstance(key, str) and _finite_number(number):
                                grouped[key].append(number)
                        if len(grouped) < 2 or len(grouped) > self.max_groups:
                            continue
                        rows = []
                        for category, numbers in sorted(grouped.items()):
                            try:
                                total = sum(numbers)
                                mean = statistics.fmean(numbers)
                                if not _finite_number(total) or not _finite_number(mean):
                                    continue
                                rows.append([category, len(numbers), total, mean])
                            except (OverflowError, ValueError):
                                continue
                        if len(rows) < 2:
                            continue
                        comparisons.append(
                            {
                                "title": f"{measure} grouped by {dimension}",
                                "source_fields": [f"{path}[*].{dimension}", f"{path}[*].{measure}"],
                                "method": "group finite numeric values by exact string category; report count, sum, and mean",
                                "columns": [dimension, "count", "sum", "mean"],
                                "rows": rows,
                            }
                        )
            if len(comparisons) >= 100:
                return comparisons[:100]
        return comparisons

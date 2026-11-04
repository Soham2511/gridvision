"""Domain-neutral recursive JSON structure inspection."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from report_generator.schemas.analysis_schema import FieldProfile, JSONAnalysis


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unsupported"


def _date_like(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 8:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        pass
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


class JSONStructureAnalyzer:
    def __init__(self, *, max_fields: int = 5000, max_examples: int = 5) -> None:
        self.max_fields = max_fields
        self.max_examples = max_examples

    def analyze(self, data: Any) -> JSONAnalysis:
        type_counts: dict[str, Counter[str]] = defaultdict(Counter)
        null_counts: Counter[str] = Counter()
        missing_counts: Counter[str] = Counter()
        examples: dict[str, list[str]] = defaultdict(list)
        array_lengths: list[dict[str, Any]] = []
        object_count = 0
        array_count = 0
        date_counts: Counter[str] = Counter()
        array_records: list[tuple[str, list[dict[str, Any]]]] = []
        stack: list[tuple[Any, str, int]] = [(data, "$", 0)]

        while stack:
            value, path, absent = stack.pop()
            kind = _kind(value)
            type_counts[path][kind] += 1
            if absent:
                null_counts[path] += absent
            if value is None:
                null_counts[path] += 1
                continue
            if kind == "object":
                object_count += 1
                for key, child in reversed(list(value.items())):
                    stack.append((child, f"{path}.{key}", 0))
            elif kind == "array":
                array_count += 1
                array_lengths.append({"path": path, "length": len(value)})
                if value and all(isinstance(item, dict) for item in value):
                    array_records.append((path, value))
                    present = set().union(*(item.keys() for item in value))
                    for key in present:
                        missing = sum(1 for item in value if key not in item)
                        if missing:
                            missing_counts[f"{path}[*].{key}"] += missing
                for child in reversed(value):
                    stack.append((child, f"{path}[*]", 0))
            elif kind == "string":
                if _date_like(value):
                    date_counts[path] += 1
                if len(examples[path]) < self.max_examples:
                    examples[path].append(value[:120])
            elif kind in {"number", "boolean"}:
                if len(examples[path]) < self.max_examples:
                    examples[path].append(str(value))

        paths = sorted(type_counts)
        if len(paths) > self.max_fields:
            raise ValueError("JSON structure exceeds the configured field limit")
        fields = [
            FieldProfile(
                path=path,
                type_counts=dict(type_counts[path]),
                null_count=null_counts[path],
                missing_count=missing_counts[path],
                examples=examples[path],
            )
            for path in paths
        ]

        grouping_candidates: set[str] = set()
        relationships: list[dict[str, str]] = []
        for array_path, records in array_records:
            keys = sorted(set().union(*(row.keys() for row in records)))
            numeric_keys = [
                key for key in keys
                if any(isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
                       for row in records)
            ]
            categorical_keys = [
                key for key in keys
                if any(isinstance(row.get(key), str) and not _date_like(row[key])
                       for row in records)
            ]
            date_keys = [
                key for key in keys
                if any(_date_like(row.get(key)) for row in records)
            ]
            grouping_candidates.update(f"{array_path}[*].{key}" for key in categorical_keys)
            for dimension in categorical_keys + date_keys:
                for measure in numeric_keys:
                    relationships.append(
                        {
                            "records": array_path,
                            "dimension": f"{array_path}[*].{dimension}",
                            "measure": f"{array_path}[*].{measure}",
                            "relationship": "shared_record_grouping_candidate",
                        }
                    )

        return JSONAnalysis(
            root_type=_kind(data),
            object_count=object_count,
            array_count=array_count,
            array_lengths=array_lengths,
            fields=fields,
            grouping_candidates=sorted(grouping_candidates),
            date_candidates=sorted(date_counts),
            potential_relationships=relationships[:500],
        )

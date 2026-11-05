"""Opt-in Tavily search for current or locally unavailable public guidance."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from ai.anamoly.config import get_settings
from ai.anamoly.tools.registry import ToolDefinition, ToolRegistry


def _tavily_search(arguments: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.tavily_api_key:
        raise RuntimeError(
            "Tavily search is unavailable: configure TAVILY_API_KEY or the local "
            "tavily/api.key secret file."
        )
    query = arguments["query"].strip()
    if not query or len(query) > 400:
        raise ValueError("Search query must contain 1 to 400 characters.")
    if re.search(r"\b(?:meter|customer|account)\s*[-:#]?\s*\d+", query, re.IGNORECASE):
        raise ValueError("Customer- or meter-specific queries are not sent to Tavily.")
    body = json.dumps(
        {
            "api_key": settings.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.request_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Tavily search failed: {exc}") from exc
    results = payload.get("results", [])
    return {
        "source": "external_web",
        "items": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "published_date": item.get("published_date"),
            }
            for item in results
        ],
    }


def register_web_search_tool(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="tavily_web_search",
            description=(
                "Search current public regulations or safety guidance when local "
                "knowledge is insufficient. Results are not automatically ingested."
            ),
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_tavily_search,
            allowed_personas=frozenset({"household", "commercial", "government"}),
            requires_authenticated_principal=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="tavily_extract_content",
            description="Extract selected public webpage content for current guidance.",
            input_schema={
                "type": "object",
                "properties": {"urls": {"type": "array"}},
                "required": ["urls"],
                "additionalProperties": False,
            },
            handler=_tavily_extract,
            allowed_personas=frozenset({"household", "commercial", "government"}),
            requires_authenticated_principal=False,
        )
    )


def _tavily_extract(arguments: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    urls = arguments["urls"]
    if not settings.tavily_api_key:
        raise RuntimeError(
            "Tavily extraction is unavailable: configure TAVILY_API_KEY or the local "
            "tavily/api.key secret file."
        )
    if not urls or len(urls) > 5 or any(not isinstance(url, str) for url in urls):
        raise ValueError("Provide between one and five webpage URLs.")
    if any(not url.startswith("https://") for url in urls):
        raise ValueError("Tavily extraction accepts HTTPS URLs only.")
    body = json.dumps(
        {"api_key": settings.tavily_api_key, "urls": urls}
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tavily.com/extract",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.request_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Tavily extraction failed: {exc}") from exc
    return {"source": "external_web", "items": payload.get("results", [])}

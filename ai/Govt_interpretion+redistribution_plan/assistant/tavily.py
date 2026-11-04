from __future__ import annotations

import csv
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .providers import _create_ssl_context
from ..paths import PROJECT_ROOT, TAVILY_API_KEY_PATH, configured_path

WORKSPACE_ROOT = PROJECT_ROOT
DEFAULT_TAVILY_KEY_PATH = TAVILY_API_KEY_PATH
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyError(RuntimeError):
    """Sanitized error from Tavily configuration or search requests."""


def _read_tavily_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    key_path = configured_path("TAVILY_API_KEY_FILE", DEFAULT_TAVILY_KEY_PATH)
    if not key_path.is_file():
        raise TavilyError(
            "Tavily API key not found. Set TAVILY_API_KEY or configure "
            "TAVILY_API_KEY_FILE."
        )
    try:
        key = key_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TavilyError("Unable to read the configured Tavily API key file.") from exc
    if not key:
        raise TavilyError("The configured Tavily API key file is empty.")
    return key


def search_web(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
    """Search external references without mixing them into internal energy data."""
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Web search query must not be empty.")
    if not 1 <= max_results <= 10:
        raise ValueError("max_results must be between 1 and 10.")
    body = json.dumps(
        {
            "api_key": _read_tavily_key(),
            "query": cleaned_query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
            context=_create_ssl_context(),
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            message = "Tavily rejected the configured API key."
        elif exc.code == 429:
            message = "Tavily rate limit reached; wait before trying again."
        else:
            message = f"Tavily search failed (HTTP {exc.code})."
        raise TavilyError(message) from exc
    except urllib.error.URLError as exc:
        raise TavilyError(f"Unable to reach Tavily: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ssl.SSLError) as exc:
        raise TavilyError("Tavily returned an invalid response.") from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise TavilyError("Tavily response is missing search results.")
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        title, url, content = item.get("title"), item.get("url"), item.get("content")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (title, url, content)
        ):
            continue
        if not url.startswith(("https://", "http://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(
            {
                "title": title.strip()[:300],
                "url": url.strip()[:2000],
                "content": content.strip()[:1600],
            }
        )
        if len(sources) == max_results:
            break
    return sources


def format_search_results(query: str, sources: list[dict[str, str]]) -> str:
    if not sources:
        return f"No web sources were returned for: {query}"
    lines = [
        f"External web research for: {query}",
        "These sources are separate from the project's internal 2018 energy data.",
    ]
    for index, source in enumerate(sources, start=1):
        lines.extend(
            [
                f"[{index}] {source['title']}",
                source["content"],
                f"Source: {source['url']}",
            ]
        )
    return "\n".join(lines)


def save_search_results_csv(
    sources: list[dict[str, str]],
    *,
    output_dir: str | Path,
) -> Path:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "web_research_sources.csv"
    temporary_path = path.with_suffix(".csv.tmp")
    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["title", "url", "content"])
            writer.writeheader()
            writer.writerows(sources)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path

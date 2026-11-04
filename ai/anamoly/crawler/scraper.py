"""Respectful, incremental crawler for configured authoritative domains."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ai.anamoly.config import get_settings
from ai.anamoly.ingestion.document_loader import _VisibleTextParser

DEFAULT_DOMAINS = ("energy.gov", "ferc.gov", "dps.ny.gov", "nyc.gov", "osha.gov")
DEFAULT_SEEDS = (
    "https://www.energy.gov/",
    "https://www.ferc.gov/",
    "https://dps.ny.gov/electric",
    "https://www.nyc.gov/",
    "https://www.osha.gov/",
)
USER_AGENT = "GridVisionKnowledgeBot/1.0 (+https://gridvision.example/contact)"


class _LinkParser(_VisibleTextParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.metadata: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            values = {key.lower(): value for key, value in attrs if value}
            name = (values.get("name") or values.get("property") or "").lower()
            content = values.get("content")
            if name and content:
                self.metadata[name] = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        super().handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        super().handle_data(data)
        if self.in_title and data.strip():
            self.title_parts.append(data.strip())


def _configured_list(env_name: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(env_name)
    return tuple(part.strip() for part in value.split(",") if part.strip()) if value else fallback


def _allowed(url: str, domains: tuple[str, ...]) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


class KnowledgeCrawler:
    def __init__(
        self,
        *,
        domains: tuple[str, ...] | None = None,
        seed_urls: tuple[str, ...] | None = None,
        rate_limit_seconds: float = 1.0,
    ) -> None:
        self.domains = domains or _configured_list(
            "GRIDVISION_ANOMALY_CRAWLER_ALLOWED_DOMAINS", DEFAULT_DOMAINS
        )
        self.seed_urls = seed_urls or _configured_list(
            "GRIDVISION_ANOMALY_CRAWLER_SEED_URLS", DEFAULT_SEEDS
        )
        self.rate_limit_seconds = max(rate_limit_seconds, 0.5)
        settings = get_settings()
        self.output_root = settings.raw_knowledge_base_path / "crawled"
        self.web_root = self.output_root / "web_pages"
        self.pdf_root = self.output_root / "pdfs"
        self.manifest_path = self.output_root / "manifest.jsonl"
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._seen_urls: set[str] = set()

    def _robots_allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(f"{root}/robots.txt")
            try:
                parser.read()
            except (OSError, urllib.error.URLError):
                return False
            self._robots[root] = parser
        return self._robots[root].can_fetch(USER_AGENT, url)

    def _fetch(self, url: str) -> tuple[bytes, str]:
        if not _allowed(url, self.domains):
            raise ValueError(f"URL is outside the configured domain allowlist: {url}")
        if not self._robots_allowed(url):
            raise PermissionError(f"robots.txt disallows or could not verify URL: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            payload = response.read(20 * 1024 * 1024 + 1)
        if len(payload) > 20 * 1024 * 1024:
            raise ValueError(f"Downloaded resource exceeds 20 MiB: {url}")
        time.sleep(self.rate_limit_seconds)
        return payload, content_type

    def _append_manifest(self, item: dict[str, Any]) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _save(self, url: str, payload: bytes, content_type: str, title: str) -> dict[str, Any] | None:
        digest = hashlib.sha256(payload).hexdigest()
        if self.manifest_path.is_file():
            with self.manifest_path.open(encoding="utf-8") as manifest:
                for line in manifest:
                    if line.strip() and json.loads(line).get("sha256") == digest:
                        return None
        is_pdf = content_type == "application/pdf" or url.lower().endswith(".pdf")
        destination_root = self.pdf_root if is_pdf else self.web_root
        destination_root.mkdir(parents=True, exist_ok=True)
        published = ""
        publisher = urllib.parse.urlparse(url).hostname or ""
        if is_pdf:
            filename = f"{digest}.pdf"
            destination = destination_root / filename
            destination.write_bytes(payload)
        else:
            parser = _LinkParser()
            parser.feed(payload.decode("utf-8", errors="replace"))
            page_title = title or " ".join(parser.title_parts) or urllib.parse.urlparse(url).netloc
            published = next(
                (
                    parser.metadata[name]
                    for name in (
                        "article:published_time",
                        "date",
                        "dc.date",
                        "dcterms.created",
                    )
                    if parser.metadata.get(name)
                ),
                "",
            )
            publisher = parser.metadata.get("publisher", publisher)
            slug = re.sub(r"[^A-Za-z0-9_-]+", "_", page_title).strip("_")[:100] or "page"
            filename = f"{slug}_{digest[:12]}.txt"
            destination = destination_root / filename
            destination.write_text("\n".join(parser.parts), encoding="utf-8")
        item = {
            "url": url,
            "title": title or filename.rsplit("_", 1)[0],
            "content_type": content_type,
            "local_path": destination.relative_to(self.output_root).as_posix(),
            "sha256": digest,
            "source_domain": urllib.parse.urlparse(url).hostname,
            "publisher": publisher,
            "publication_date": published,
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._append_manifest(item)
        return item

    def crawl(self, *, max_pages: int = 50) -> dict[str, Any]:
        if max_pages < 1 or max_pages > 500:
            raise ValueError("max_pages must be between 1 and 500.")
        queue = list(self.seed_urls)
        collected: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        while queue and len(self._seen_urls) < max_pages:
            url = queue.pop(0)
            normalized = urllib.parse.urldefrag(url)[0]
            if normalized in self._seen_urls:
                continue
            self._seen_urls.add(normalized)
            try:
                payload, content_type = self._fetch(normalized)
                item = self._save(normalized, payload, content_type, "")
                if item:
                    collected.append(item)
                if content_type in {"text/html", "application/xhtml+xml"}:
                    parser = _LinkParser()
                    parser.feed(payload.decode("utf-8", errors="replace"))
                    for href in parser.links:
                        target = urllib.parse.urljoin(normalized, href)
                        if _allowed(target, self.domains) and target not in self._seen_urls:
                            queue.append(target)
            except (OSError, ValueError, PermissionError, urllib.error.URLError) as exc:
                failures.append({"url": normalized, "error": str(exc)})
        return {
            "status": "completed" if not failures else "partial_failure",
            "visited": len(self._seen_urls),
            "collected": collected,
            "failures": failures,
            "manifest": str(self.manifest_path),
        }

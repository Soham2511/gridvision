"""Deterministic HTML/PDF reports from existing server-owned service results."""

from __future__ import annotations

import html
import io
import json
from typing import Any


class ReportRenderError(RuntimeError):
    pass


class ReportService:
    VERSION = "gridvision-report.v1"

    @staticmethod
    def render_html(title: str, payload: dict[str, Any], sources: list[dict[str, Any]]) -> bytes:
        safe_title = html.escape(title)
        safe_payload = html.escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        source_rows = "".join(
            "<li>" + html.escape(str(source.get("dataset", source.get("sourceId", "source"))))
            + " — " + html.escape(str(source.get("datasetVersion", "version unavailable")))
            + " (" + html.escape(str(source.get("provenance", "project source"))) + ")</li>"
            for source in sources
        )
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{safe_title}</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#172033}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1rem}}.notice{{border-left:4px solid #d97706;padding:1rem;background:#fffbeb}}</style>
</head><body><main><h1>{safe_title}</h1><p class="notice">Generated from historical project sources. This is not live telemetry, a utility bill, or a fault diagnosis.</p>
<h2>Report data</h2><pre>{safe_payload}</pre><h2>Sources</h2><ul>{source_rows}</ul>
<h2>Method and limitations</h2><p>Values are read from existing GridVision source and model services. Missing values remain unavailable. Generated narrative is disabled unless an approved provider is configured.</p>
<p>Report renderer: {html.escape(ReportService.VERSION)}</p></main></body></html>"""
        return document.encode("utf-8")

    @staticmethod
    def render_pdf(title: str, payload: dict[str, Any], sources: list[dict[str, Any]]) -> bytes:
        data_block = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data_block, dict):
            try:
                from report_generator.services.consumption_analytics import (
                    ConsumptionReportCalculator,
                    is_consumption_report,
                )
                from report_generator.services.pdf_renderer import PDFReportRenderer
                if is_consumption_report(data_block):
                    analysis = ConsumptionReportCalculator.calculate(data_block)
                    return PDFReportRenderer().render_consumption_report(analysis)
            except Exception:
                pass

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
            from xml.sax.saxutils import escape
        except ImportError as exc:
            raise ReportRenderError("PDF support is optional; install requirements-ai.txt.") from exc

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, title=title)
        styles = getSampleStyleSheet()
        story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 14)]
        text = json.dumps(payload, ensure_ascii=True, indent=2, default=str)
        for line in text.splitlines():
            story.append(Paragraph(escape(line).replace(" ", "&nbsp;"), styles["Code"]))
        story.extend([Spacer(1, 14), Paragraph("Sources", styles["Heading2"])])
        for source in sources:
            label = " — ".join(
                str(source.get(key, "")) for key in ("dataset", "datasetVersion", "provenance")
            )
            story.append(Paragraph(escape(label), styles["BodyText"]))
        doc.build(story)
        return buffer.getvalue()

"""Safe, data-driven HTML rendering from a validated report document."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from report_generator.schemas.report_schema import ReportDocument


_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


class HTMLReportRenderer:
    def __init__(self) -> None:
        self.environment = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, report: ReportDocument) -> bytes:
        template = self.environment.get_template("report.html")
        css = (_TEMPLATE_DIR / "report.css").read_text(encoding="utf-8")
        return template.render(report=report, css=css).encode("utf-8")

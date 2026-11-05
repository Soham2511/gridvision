"""End-to-end JSON analysis, narrative, validation, and artifact workflow."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.ai.storage import PrivateFileStore, PrivateStorageError
from pydantic import ValidationError
from report_generator.config import ReportGeneratorSettings
from report_generator.schemas.analysis_schema import DeterministicAnalytics
from report_generator.schemas.input_schema import GenerateReportRequest
from report_generator.schemas.report_schema import (
    ReportDocument,
    ReportMetric,
    ReportSection,
    ReportTable,
)
from report_generator.services.analytics_service import DeterministicAnalyticsEngine
from report_generator.services.consumption_analytics import (
    ConsumptionReportCalculator,
    MonthlyConsumptionAnalysis,
    is_anomaly_report,
    is_consumption_report,
)
from report_generator.services.html_renderer import HTMLReportRenderer
from report_generator.services.json_analyzer import JSONStructureAnalyzer
from report_generator.services.llm_provider import (
    ReportLLMProvider,
    ReportProviderError,
    RetryableReportProviderError,
)
from report_generator.services.pdf_renderer import PDFReportRenderer, PDFRenderError
from report_generator.services.report_planner import (
    ReportPlanningError,
    build_prompt,
    plan_report,
)
from report_generator.storage.report_storage import ReportRepository, ReportStorageError

logger = logging.getLogger("gridvision.report_generator")


class ReportGenerationError(RuntimeError):
    def __init__(
        self, message: str, code: str, status_code: int = 503, report_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.report_id = report_id


_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?%?")


def _number_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for match in _NUMBER.finditer(value):
        token = match.group(0).replace(",", "").removesuffix("%")
        tokens.add(token)
        if token.isdigit():
            tokens.add(str(int(token)))
        else:
            try:
                num = float(token)
                if num.is_integer():
                    tokens.add(str(int(num)))
            except ValueError:
                pass
    return tokens


def _source_numbers(data: Any) -> set[str]:
    found: set[str] = set()
    stack = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            found.update(_number_tokens(str(value)))
        elif isinstance(value, str):
            found.update(_number_tokens(value))
    return found


_COMMON_ALLOWED_NUMBERS = {str(i) for i in range(32)} | {"00", "24", "60"}


def _validate_narrative_numbers(
    plan, data: Any, analytics: DeterministicAnalytics, instructions: str | None = None
) -> None:
    allowed = _source_numbers(data)
    allowed.update(_COMMON_ALLOWED_NUMBERS)
    for metric in analytics.metrics:
        allowed.update(_number_tokens(str(metric.value)))
    if instructions:
        allowed.update(_number_tokens(instructions))
    texts = [plan.title, plan.subtitle or "", plan.executive_summary, plan.conclusion or ""]
    texts.extend(plan.limitations)
    for section in plan.sections:
        texts.append(section.title)
        texts.extend(section.content)
        texts.extend(section.observations)
    unsupported = set().union(*(_number_tokens(text) for text in texts)) - allowed
    if unsupported:
        raise ReportPlanningError(
            f"Report narrative included numerical values not found in source data or calculations: {', '.join(sorted(unsupported)[:5])}"
        )


class JSONReportGenerator:
    def __init__(
        self,
        *,
        settings: ReportGeneratorSettings,
        provider: ReportLLMProvider | None,
        repository: ReportRepository,
        artifact_store: PrivateFileStore,
        html_renderer: HTMLReportRenderer | None = None,
        pdf_renderer: PDFReportRenderer | None = None,
        analyzer: JSONStructureAnalyzer | None = None,
        analytics: DeterministicAnalyticsEngine | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.repository = repository
        self.artifact_store = artifact_store
        self.html_renderer = html_renderer or HTMLReportRenderer()
        self.pdf_renderer = pdf_renderer or PDFReportRenderer()
        self.analyzer = analyzer or JSONStructureAnalyzer()
        self.analytics = analytics or DeterministicAnalyticsEngine()

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.enabled,
            "provider": self.settings.provider,
            "provider_configured": self.provider is not None,
            "status": "ready" if self.settings.enabled and self.provider else "unavailable",
        }

    def generate(self, request: GenerateReportRequest, *, owner_key: str) -> dict[str, Any]:
        report_id = uuid.uuid4().hex
        generated_at = datetime.now(timezone.utc)
        try:
            self.repository.create_pending(report_id, owner_key, generated_at.isoformat())
        except ReportStorageError as exc:
            raise ReportGenerationError(
                "Report metadata storage is unavailable", "REPORT_STORAGE_UNAVAILABLE"
            ) from exc
        try:
            if not self.settings.enabled:
                raise ReportGenerationError("Report generation is disabled", "REPORT_GENERATOR_DISABLED")

            if is_consumption_report(request.data):
                consumption_analysis = ConsumptionReportCalculator.calculate(request.data)
                report = self._consumption_document(report_id, generated_at, consumption_analysis)
                html_content = self.html_renderer.render(report)
                if len(html_content) > self.settings.max_artifact_bytes:
                    raise ReportGenerationError("HTML report exceeds the configured size limit", "REPORT_ARTIFACT_TOO_LARGE", 413)
                self.artifact_store.initialize()
                html_id = self.artifact_store.store(html_content)
                pdf_id = None
                error_code = None
                status = "complete"
                if "pdf" in request.output_formats:
                    try:
                        pdf_content = self.pdf_renderer.render_consumption_report(consumption_analysis, report_id=report_id)
                        if len(pdf_content) > self.settings.max_artifact_bytes:
                            raise PDFRenderError("PDF report exceeds configured size limit")
                        pdf_id = self.artifact_store.store(pdf_content)
                    except Exception:
                        status = "partial"
                        error_code = "PDF_RENDER_FAILED"
                self.repository.finish(
                    report_id,
                    owner_key,
                    title=report.title,
                    status=status,
                    html_artifact_id=html_id,
                    pdf_artifact_id=pdf_id,
                    error_code=error_code,
                    limitations=report.limitations,
                )
                logger.info(
                    "report_generation_complete",
                    extra={"event": {"report_id": report_id, "status": status, "format_count": 1 + int(pdf_id is not None), "type": "consumption"}},
                )
                return {
                    "report_id": report_id,
                    "title": report.title,
                    "status": status,
                    "generated_at": generated_at.isoformat(),
                    "html_url": f"/api/v1/report-generator/reports/{report_id}/html",
                    "pdf_url": f"/api/v1/report-generator/reports/{report_id}/pdf" if pdf_id else None,
                }

            if is_anomaly_report(request.data):
                report = self._anomaly_document(report_id, generated_at, request.data)
                html_content = self.html_renderer.render(report)
                if len(html_content) > self.settings.max_artifact_bytes:
                    raise ReportGenerationError("HTML report exceeds the configured size limit", "REPORT_ARTIFACT_TOO_LARGE", 413)
                self.artifact_store.initialize()
                html_id = self.artifact_store.store(html_content)
                pdf_id = None
                error_code = None
                status = "complete"
                if "pdf" in request.output_formats:
                    try:
                        pdf_content = self.pdf_renderer.render_anomaly_report(request.data, report_id=report_id)
                        if len(pdf_content) > self.settings.max_artifact_bytes:
                            raise PDFRenderError("PDF report exceeds configured size limit")
                        pdf_id = self.artifact_store.store(pdf_content)
                    except Exception:
                        status = "partial"
                        error_code = "PDF_RENDER_FAILED"
                self.repository.finish(
                    report_id,
                    owner_key,
                    title=report.title,
                    status=status,
                    html_artifact_id=html_id,
                    pdf_artifact_id=pdf_id,
                    error_code=error_code,
                    limitations=report.limitations,
                )
                logger.info(
                    "report_generation_complete",
                    extra={"event": {"report_id": report_id, "status": status, "format_count": 1 + int(pdf_id is not None), "type": "anomaly_rectification"}},
                )
                return {
                    "report_id": report_id,
                    "title": report.title,
                    "status": status,
                    "generated_at": generated_at.isoformat(),
                    "html_url": f"/api/v1/report-generator/reports/{report_id}/html",
                    "pdf_url": f"/api/v1/report-generator/reports/{report_id}/pdf" if pdf_id else None,
                }

            if self.provider is None:
                raise ReportGenerationError("No report generation provider is configured", "REPORT_PROVIDER_UNAVAILABLE")
            analysis = self.analyzer.analyze(request.data)
            analytics = self.analytics.calculate(request.data)
            prompt = build_prompt(request.data, analysis, analytics, request.instructions)
            if len(prompt) > self.settings.max_prompt_chars:
                raise ReportGenerationError(
                    "Prepared report input exceeds the configured analysis limit",
                    "REPORT_PROMPT_TOO_LARGE",
                    413,
                )
            attempt = 0
            current_prompt = prompt
            while attempt <= self.settings.max_provider_retries:
                attempt += 1
                try:
                    plan = plan_report(
                        self.provider,
                        current_prompt,
                        timeout_seconds=self.settings.provider_timeout_seconds,
                        max_output_chars=self.settings.max_output_chars,
                        max_retries=0,
                    )
                    _validate_narrative_numbers(plan, request.data, analytics, request.instructions)
                    break
                except (ReportPlanningError, RetryableReportProviderError) as exc:
                    if attempt > self.settings.max_provider_retries:
                        raise
                    if "numerical values" in str(exc):
                        current_prompt = (
                            prompt
                            + f"\n\nCRITICAL RETRY INSTRUCTION: Your previous response contained unverified numbers ({str(exc).split(':')[-1].strip()}). "
                            "Do NOT include any numerical figures, statistics, or counts not directly present in input_data_untrusted or authoritative_calculations. "
                            "Use qualitative words instead of numbers."
                        )
            report = self._document(report_id, generated_at, plan, analytics)
            html_content = self.html_renderer.render(report)
            if len(html_content) > self.settings.max_artifact_bytes:
                raise ReportGenerationError("HTML report exceeds the configured size limit", "REPORT_ARTIFACT_TOO_LARGE", 413)
            self.artifact_store.initialize()
            html_id = self.artifact_store.store(html_content)
            pdf_id = None
            error_code = None
            status = "complete"
            if "pdf" in request.output_formats:
                try:
                    pdf_content = self.pdf_renderer.render(report)
                    if len(pdf_content) > self.settings.max_artifact_bytes:
                        raise PDFRenderError("PDF report exceeds configured size limit")
                    pdf_id = self.artifact_store.store(pdf_content)
                except Exception:
                    status = "partial"
                    error_code = "PDF_RENDER_FAILED"
            self.repository.finish(
                report_id,
                owner_key,
                title=report.title,
                status=status,
                html_artifact_id=html_id,
                pdf_artifact_id=pdf_id,
                error_code=error_code,
                limitations=report.limitations,
            )
            logger.info(
                "report_generation_complete",
                extra={"event": {"report_id": report_id, "status": status, "format_count": 1 + int(pdf_id is not None)}},
            )
            return {
                "report_id": report_id,
                "title": report.title,
                "status": status,
                "generated_at": generated_at.isoformat(),
                "html_url": f"/api/v1/report-generator/reports/{report_id}/html",
                "pdf_url": f"/api/v1/report-generator/reports/{report_id}/pdf" if pdf_id else None,
            }
        except ReportGenerationError as exc:
            try:
                self.repository.fail(report_id, owner_key, exc.code)
            except ReportStorageError:
                logger.error(
                    "report_failure_status_persistence_failed",
                    extra={"event": {"report_id": report_id}},
                )
            exc.report_id = report_id
            raise
        except ReportProviderError as exc:
            try:
                self.repository.fail(report_id, owner_key, exc.code)
            except ReportStorageError:
                logger.error(
                    "report_failure_status_persistence_failed",
                    extra={"event": {"report_id": report_id}},
                )
            status_code = 503 if isinstance(exc, ReportProviderError) and exc.code == "REPORT_PROVIDER_UNAVAILABLE" else 502
            raise ReportGenerationError(str(exc), exc.code, status_code, report_id) from exc
        except ReportPlanningError as exc:
            code = "REPORT_CONTENT_INVALID" if "numerical values" in str(exc) or "valid report plan" in str(exc) else "REPORT_CONTENT_FAILED"
            message = "The report provider returned content that failed validation." if code == "REPORT_CONTENT_INVALID" else "Report content could not be generated"
            self.repository.fail(report_id, owner_key, code)
            raise ReportGenerationError(message, code, 502, report_id) from exc
        except (PrivateStorageError, ReportStorageError, OSError, ValueError, ValidationError) as exc:
            try:
                self.repository.fail(report_id, owner_key, "REPORT_GENERATION_FAILED")
            except ReportStorageError:
                pass
            raise ReportGenerationError(
                "Report could not be generated", "REPORT_GENERATION_FAILED", report_id=report_id
            ) from exc
        except Exception as exc:
            try:
                self.repository.fail(report_id, owner_key, "REPORT_GENERATION_FAILED")
            except ReportStorageError:
                pass
            logger.error(
                "report_generation_failed",
                extra={"event": {"report_id": report_id, "error_code": "REPORT_GENERATION_FAILED"}},
            )
            raise ReportGenerationError(
                "Report could not be generated", "REPORT_GENERATION_FAILED", report_id=report_id
            ) from exc

    def _document(self, report_id, generated_at, plan, analytics) -> ReportDocument:
        metrics = [
            ReportMetric(
                name=metric.name,
                value=metric.value,
                units=metric.units,
                source_fields=metric.source_fields,
                methodology=f"{metric.method}; sample count: {metric.sample_count}",
            )
            for metric in analytics.metrics
        ]
        sections = [
            ReportSection(
                title=section.title,
                order=index,
                content=section.content,
                observations=section.observations,
            )
            for index, section in enumerate(plan.sections)
        ]
        next_order = len(sections)
        if metrics:
            sections.append(
                ReportSection(
                    title="Deterministic statistics",
                    order=next_order,
                    content=["Statistics below were calculated directly from finite numeric values at each source field path."],
                    metrics=metrics,
                )
            )
            next_order += 1
        for comparison in analytics.comparison_tables:
            sections.append(
                ReportSection(
                    title=comparison["title"],
                    order=next_order,
                    tables=[ReportTable(
                        title=comparison["title"],
                        columns=comparison["columns"],
                        rows=comparison["rows"],
                    )],
                    content=[f"Source fields: {', '.join(comparison['source_fields'])}. Method: {comparison['method']}"],
                )
            )
            next_order += 1
        limitations = list(dict.fromkeys(plan.limitations + analytics.limitations))
        return ReportDocument(
            report_id=report_id,
            title=plan.title,
            subtitle=plan.subtitle,
            generated_at=generated_at,
            executive_summary=plan.executive_summary,
            sections=sections,
            metrics=metrics,
            observations=[],
            conclusion=plan.conclusion,
            limitations=limitations,
        )

    def _consumption_document(
        self, report_id: str, generated_at: datetime, analysis: MonthlyConsumptionAnalysis
    ) -> ReportDocument:
        entity_label = f" for OBJECTID {analysis.entity_id}" if analysis.entity_id is not None else ""
        title = f"Monthly Energy Consumption Report{entity_label}"
        subtitle = f"{analysis.persona.title()} consumption analysis for period {analysis.period_start} to {analysis.period_end}"

        bill_str = f"₹{analysis.estimated_monthly_bill_inr:,.2f}" if analysis.estimated_monthly_bill_inr is not None else "unavailable"
        summary = (
            f"Monthly electricity consumption report{entity_label} covering {analysis.period_start} to {analysis.period_end}. "
            f"Total energy consumption was {analysis.total_monthly_kwh:,.2f} kWh across {analysis.days_returned} observed calendar days, "
            f"averaging {analysis.avg_daily_kwh:,.2f} kWh/day. Estimated monthly electricity bill is {bill_str}."
        )

        s1 = ReportSection(
            title="Monthly Consumption Overview",
            order=1,
            content=[
                f"Total monthly consumption: {analysis.total_monthly_kwh:,.2f} kWh across {analysis.days_returned} calendar days.",
                f"Average daily consumption: {analysis.avg_daily_kwh:,.2f} kWh/day.",
                f"Peak hourly consumption: {analysis.peak_hourly.value_kwh:.2f} kWh ({analysis.peak_hourly.timestamp_or_date})." if analysis.peak_hourly else "Peak hourly: Unavailable.",
                f"Peak daily consumption: {analysis.peak_daily.value_kwh:.2f} kWh ({analysis.peak_daily.timestamp_or_date}).",
                f"Lowest hourly consumption: {analysis.lowest_hourly.value_kwh:.2f} kWh ({analysis.lowest_hourly.timestamp_or_date})." if analysis.lowest_hourly else "Lowest hourly: Unavailable.",
                f"Lowest daily consumption: {analysis.lowest_daily.value_kwh:.2f} kWh ({analysis.lowest_daily.timestamp_or_date}).",
                f"Estimated monthly electricity bill: {bill_str}.",
            ],
            observations=[
                f"Average daily consumption was {analysis.avg_daily_kwh:.2f} kWh/day across {analysis.days_returned} days.",
            ],
        )

        peak_hr_str = f"{analysis.peak_hour.hour_label} ({analysis.peak_hour.average_kwh:.2f} kWh avg)" if analysis.peak_hour and analysis.peak_hour.average_kwh is not None else "N/A"
        lowest_hr_str = f"{analysis.lowest_hour.hour_label} ({analysis.lowest_hour.average_kwh:.2f} kWh avg)" if analysis.lowest_hour and analysis.lowest_hour.average_kwh is not None else "N/A"
        s2 = ReportSection(
            title="Average Hourly Consumption Pattern",
            order=2,
            content=[
                "Average electricity consumption across each of the 24 hours of the day computed from valid source observations.",
                f"Diurnal peak consumption occurs during hour {peak_hr_str}.",
                f"Diurnal minimum consumption occurs during hour {lowest_hr_str}.",
            ],
            observations=[
                f"Highest average consumption hour: {peak_hr_str}.",
                f"Lowest average consumption hour: {lowest_hr_str}.",
            ],
        )

        s3 = ReportSection(
            title="Daily Consumption Trend",
            order=3,
            content=[
                f"Daily aggregated energy consumption across the entire reporting month ({analysis.period_start} to {analysis.period_end}).",
                f"Monthly average reference consumption: {analysis.avg_daily_kwh:.2f} kWh/day.",
                f"Highest consumption day: {analysis.highest_day.date_str} ({analysis.highest_day.total_kwh:.2f} kWh).",
                f"Lowest consumption day: {analysis.lowest_day.date_str} ({analysis.lowest_day.total_kwh:.2f} kWh).",
            ],
            observations=[
                f"Highest consumption day: {analysis.highest_day.date_str} with {analysis.highest_day.total_kwh:.2f} kWh.",
                f"Lowest consumption day: {analysis.lowest_day.date_str} with {analysis.lowest_day.total_kwh:.2f} kWh.",
            ],
        )

        ww = analysis.weekday_weekend
        diff_str = f"{ww.diff_pct:+.2f}%" if ww.diff_pct is not None else "N/A"
        s4 = ReportSection(
            title="Weekday vs Weekend Comparison",
            order=4,
            content=[
                f"Weekday (Mon-Fri) total: {ww.weekday.total_kwh:,.2f} kWh over {ww.weekday.days_count} days (daily average: {ww.weekday.avg_daily_kwh:.2f} kWh/day, peak: {ww.weekday.peak_daily_kwh:.2f} kWh on {ww.weekday.peak_date or 'N/A'}).",
                f"Weekend (Sat-Sun) total: {ww.weekend.total_kwh:,.2f} kWh over {ww.weekend.days_count} days (daily average: {ww.weekend.avg_daily_kwh:.2f} kWh/day, peak: {ww.weekend.peak_daily_kwh:.2f} kWh on {ww.weekend.peak_date or 'N/A'}).",
                f"Weekend daily average differs by {diff_str} compared to weekday daily average.",
            ],
            observations=[
                f"Weekday daily average: {ww.weekday.avg_daily_kwh:.2f} kWh/day.",
                f"Weekend daily average: {ww.weekend.avg_daily_kwh:.2f} kWh/day.",
            ],
        )

        week_lines = [
            f"{w.week_label} ({w.start_date} to {w.end_date}, {w.days_count} days{', partial week' if w.is_partial else ''}): {w.total_kwh:,.2f} kWh (daily average: {w.avg_daily_kwh:.2f} kWh/day)."
            for w in analysis.weekly_summary
        ]
        s5 = ReportSection(
            title="Weekly Consumption Summary",
            order=5,
            content=[
                "Energy consumption aggregated by calendar week. Partial weeks at start or end of month are normalized with daily averages.",
                *week_lines,
            ],
        )

        cs = analysis.consistency
        s6 = ReportSection(
            title="Consumption Consistency",
            order=6,
            content=[
                f"Mean daily consumption: {cs.mean_daily_kwh:.2f} kWh/day.",
                f"Standard deviation of daily consumption: {cs.std_dev_daily_kwh:.2f} kWh/day.",
                f"Coefficient of variation (CV): {cs.cv_percent:.2f}%.",
                f"Consumption variability range: {cs.variability_range_kwh:.2f} kWh ({cs.variability_category}).",
                *cs.explanations,
            ],
        )

        bill = analysis.bill
        bill_lines = [
            f"Total energy consumption: {bill.total_consumption_kwh:,.2f} kWh.",
            f"Configured tariff rate: ₹{bill.tariff_inr_per_kwh:.2f}/kWh." if bill.tariff_inr_per_kwh else "Tariff rate: Unconfigured.",
            f"Energy charges: ₹{bill.energy_charges_inr:,.2f}." if bill.energy_charges_inr is not None else "Energy charges: Unavailable.",
            f"Fixed charges: ₹{bill.fixed_charges_inr:.2f}." if bill.fixed_charges_inr is not None else "Fixed charges: None.",
            f"Taxes and surcharges: ₹{bill.taxes_and_surcharges_inr:.2f}." if bill.taxes_and_surcharges_inr is not None else "Taxes: None.",
            f"Estimated total bill: ₹{bill.estimated_total_bill_inr:,.2f}." if bill.estimated_total_bill_inr is not None else "Estimated total bill: Unavailable.",
            bill.tariff_notes,
        ]
        s7 = ReportSection(
            title="Electricity Bill Breakdown",
            order=7,
            content=bill_lines,
        )

        doc = ReportDocument(
            report_id=report_id,
            title=title,
            subtitle=subtitle,
            generated_at=generated_at,
            executive_summary=summary,
            sections=[s1, s2, s3, s4, s5, s6, s7],
            observations=[
                f"Monthly total energy consumption: {analysis.total_monthly_kwh:,.2f} kWh across {analysis.days_returned} observed calendar days.",
            ],
            limitations=[
                "Calculated from verified historical Silver energy observations. Not live telemetry or official utility tax invoice.",
                analysis.bill.tariff_notes,
            ],
        )
        setattr(doc, "_analysis", analysis)
        return doc

    def _anomaly_document(
        self, report_id: str, generated_at: datetime, payload: dict[str, Any]
    ) -> ReportDocument:
        event_id = str(payload.get("event_id", "N/A"))
        customer_id = payload.get("customer_id")
        customer_name = str(payload.get("customer_name") or (f"Consumer ID {customer_id}" if customer_id else "Authorized Stakeholder"))
        anomaly_type = str(payload.get("anomaly_type") or payload.get("dominant_anomaly_type") or "Anomaly Event")
        severity_info = payload.get("severity") or {}
        sev_level = str(severity_info.get("level", "MEDIUM")).upper()
        sev_score = float(severity_info.get("score", 0.0))
        details = payload.get("event_details") or {}
        scope = str(details.get("scope", "SINGLE_CUSTOMER"))
        start_time = str(details.get("start_time", "N/A"))
        end_time = str(details.get("end_time", "N/A"))
        duration_hours = float(details.get("duration_hours", 0.0))
        affected_count = int(details.get("affected_customer_count", 1))

        causes = payload.get("probable_causes") or []
        actions = payload.get("corrective_actions") or []
        preventions = payload.get("preventive_recommendations") or []
        limitations = payload.get("limitations") or ["Derived deterministically from GridVision model inference."]

        title = f"Anomaly Incident & Rectification Report: {event_id}"
        subtitle = f"{sev_level} Severity ({sev_score:.2f}) · {customer_name} · {anomaly_type}"
        summary = (
            f"Automated incident brief for anomaly event {event_id} ({anomaly_type}). "
            f"Assessed at {sev_level} severity with normalized score {sev_score:.3f}. "
            f"Duration: {duration_hours:.2f} hours affecting {affected_count} consumer(s) in scope {scope}."
        )

        metrics = [
            ReportMetric(
                name="Severity Score",
                value=f"{sev_score:.3f} ({sev_level})",
                units="normalized [0-1]",
                source_fields=["severity.score", "severity.level"],
                methodology="Model confidence and reconstruction error thresholding",
            ),
            ReportMetric(
                name="Event Duration",
                value=f"{duration_hours:.2f}",
                units="hours",
                source_fields=["event_details.duration_hours"],
                methodology="Temporal span between first and last anomalous observations",
            ),
            ReportMetric(
                name="Affected Meters",
                value=str(affected_count),
                units="meters",
                source_fields=["event_details.affected_customer_count"],
                methodology="Spatial H3 cluster aggregation",
            ),
        ]

        sections = [
            ReportSection(
                title="1. Incident Overview & Localized Scope",
                order=1,
                content=[
                    f"Anomaly Event ID: {event_id}",
                    f"Primary Anomaly Classification: {anomaly_type}",
                    f"Incident Window: {start_time} to {end_time} ({duration_hours:.2f} hours)",
                    f"Geographic & Grid Scope: {scope} ({affected_count} customer meter(s))",
                ],
                observations=[
                    f"Severity classified as {sev_level} based on anomalous load variance."
                ],
            ),
            ReportSection(
                title="2. Probable Causes (Physics & Operational Evidence)",
                order=2,
                content=[f"Cause {i+1}: {c}" for i, c in enumerate(causes)] or ["No specific probable causes recorded."],
                observations=causes[:3],
            ),
            ReportSection(
                title="3. Immediate Corrective Action Plan",
                order=3,
                content=[f"Step {i+1}: {a}" for i, a in enumerate(actions)] or ["No immediate corrective actions required."],
                observations=actions[:3],
            ),
            ReportSection(
                title="4. Long-Term Preventive & Resilience Recommendations",
                order=4,
                content=[f"Recommendation {i+1}: {p}" for i, p in enumerate(preventions)] or ["Routine maintenance schedule recommended."],
                observations=preventions[:3],
            ),
        ]

        doc = ReportDocument(
            report_id=report_id,
            generated_at=generated_at,
            title=title,
            subtitle=subtitle,
            executive_summary=summary,
            metrics=metrics,
            sections=sections,
            observations=[],
            conclusion="Immediate field verification recommended for identified causes according to Action Plan steps.",
            limitations=limitations,
        )
        setattr(doc, "_anomaly_payload", payload)
        return doc

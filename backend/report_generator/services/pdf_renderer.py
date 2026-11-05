"""ReportLab PDF rendering for GridVision reports, including the Customer Monthly Energy Consumption Report."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from report_generator.schemas.report_schema import ReportDocument, ReportTable
from report_generator.services.consumption_analytics import (
    MonthlyConsumptionAnalysis,
)
from report_generator.services.consumption_charts import (
    COLOR_BG,
    COLOR_BORDER,
    COLOR_LIGHT_TEAL,
    COLOR_LOWEST,
    COLOR_NAVY,
    COLOR_PEAK,
    COLOR_TEAL,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    build_daily_trend_chart,
    build_hourly_pattern_chart,
    build_weekday_weekend_chart,
    build_weekly_summary_chart,
)


class PDFRenderError(RuntimeError):
    """The optional PDF backend is unavailable or failed to render."""


class PDFReportRenderer:
    @staticmethod
    def _paragraph(text: object) -> str:
        return escape(str(text)).replace("\n", "<br/>")

    def render(
        self,
        report: ReportDocument,
        analysis: MonthlyConsumptionAnalysis | None = None,
        anomaly_payload: dict[str, Any] | None = None,
    ) -> bytes:
        """Render a report document, delegated monthly consumption report, or anomaly report to PDF."""
        if anomaly_payload is not None:
            return self.render_anomaly_report(anomaly_payload, report_id=report.report_id)

        if analysis is not None:
            return self.render_consumption_report(analysis, report_id=report.report_id)

        if hasattr(report, "_anomaly_payload") and getattr(report, "_anomaly_payload") is not None:
            return self.render_anomaly_report(getattr(report, "_anomaly_payload"), report_id=report.report_id)

        # Check if the ReportDocument contains a consumption report
        is_consumption = (
            "consumption" in report.title.casefold()
            or any("consumption" in s.title.casefold() for s in report.sections)
        )
        if hasattr(report, "_analysis") and getattr(report, "_analysis") is not None:
            return self.render_consumption_report(getattr(report, "_analysis"), report_id=report.report_id)

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:
            raise PDFRenderError("PDF support is not installed") from exc

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title=report.title,
            author="GridVision",
        )
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="ReportSmall", parent=styles["BodyText"], fontSize=8, leading=10))
        story = [
            Paragraph(self._paragraph(report.title), styles["Title"]),
            Spacer(1, 5 * mm),
        ]
        if report.subtitle:
            story.extend([Paragraph(self._paragraph(report.subtitle), styles["Heading2"]), Spacer(1, 3 * mm)])
        story.extend([
            Paragraph(f"Generated {self._paragraph(report.generated_at.isoformat())}", styles["ReportSmall"]),
            Spacer(1, 7 * mm),
            Paragraph("Executive summary", styles["Heading1"]),
            Paragraph(self._paragraph(report.executive_summary), styles["BodyText"]),
        ])
        if report.metrics:
            story.extend([Spacer(1, 5 * mm), Paragraph("Calculated metrics", styles["Heading1"])])
            story.append(self._table(
                Table,
                TableStyle,
                Paragraph,
                ["Metric", "Value", "Units", "Source fields", "Method"],
                [[m.name, m.value, m.units or "", ", ".join(m.source_fields), m.methodology]
                 for m in report.metrics],
                colors,
                styles,
            ))
        for section in sorted(report.sections, key=lambda item: item.order):
            story.extend([Spacer(1, 6 * mm), Paragraph(self._paragraph(section.title), styles["Heading1"])])
            for paragraph in section.content:
                story.append(Paragraph(self._paragraph(paragraph), styles["BodyText"]))
            for observation in section.observations:
                story.append(Paragraph("• " + self._paragraph(observation), styles["BodyText"]))
            for metric in section.metrics:
                story.append(Paragraph(
                    self._paragraph(f"{metric.name}: {metric.value} {metric.units or ''} — {metric.methodology}"),
                    styles["BodyText"],
                ))
            for table in section.tables:
                story.append(Paragraph(self._paragraph(table.title), styles["Heading2"]))
                story.append(self._report_table(table, Table, TableStyle, Paragraph, colors, styles))
        if report.observations:
            story.extend([Spacer(1, 6 * mm), Paragraph("Observations", styles["Heading1"])])
            story.extend(Paragraph("• " + self._paragraph(item), styles["BodyText"]) for item in report.observations)
        if report.conclusion:
            story.extend([Spacer(1, 6 * mm), Paragraph("Conclusion", styles["Heading1"]), Paragraph(self._paragraph(report.conclusion), styles["BodyText"])])
        if report.limitations:
            story.extend([Spacer(1, 6 * mm), Paragraph("Limitations", styles["Heading1"])])
            story.extend(Paragraph("• " + self._paragraph(item), styles["BodyText"]) for item in report.limitations)

        def footer(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#667085"))
            canvas.drawString(18 * mm, 10 * mm, f"GridVision report · {report.report_id}")
            canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
            canvas.restoreState()

        try:
            doc.build(story, onFirstPage=footer, onLaterPages=footer)
        except Exception as exc:
            raise PDFRenderError("PDF report rendering failed") from exc
        return buffer.getvalue()

    def render_consumption_report(
        self,
        analysis: MonthlyConsumptionAnalysis,
        report_id: str | None = None,
    ) -> bytes:
        """Render the exact 7-section GridVision Monthly Energy Consumption PDF report."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import (
                PageBreak,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:
            raise PDFRenderError("PDF support is not installed") from exc

        report_id_str = report_id or "demo-report"
        gen_date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

        buffer = io.BytesIO()
        margin = 36.0  # 0.5 in / 12.7 mm
        usable_width = A4[0] - 2 * margin  # ~523.27 pt

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title="GridVision Monthly Energy Consumption Report",
            author="GridVision Energy Intelligence",
        )

        styles = getSampleStyleSheet()

        # Custom Typography Styles
        style_banner_title = ParagraphStyle(
            name="GVBannerTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.white,
        )
        style_banner_sub = ParagraphStyle(
            name="GVBannerSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=COLOR_TEAL,
        )
        style_section_heading = ParagraphStyle(
            name="GVSectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=COLOR_NAVY,
            spaceAfter=3,
        )
        style_intro_text = ParagraphStyle(
            name="GVIntroText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_TEXT_MUTED,
            spaceAfter=4,
        )
        style_card_label = ParagraphStyle(
            name="GVCardLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=COLOR_TEXT_MUTED,
        )
        style_card_val = ParagraphStyle(
            name="GVCardVal",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=COLOR_NAVY,
        )
        style_card_sub = ParagraphStyle(
            name="GVCardSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=COLOR_TEAL,
        )
        style_table_cell = ParagraphStyle(
            name="GVTableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_TEXT_MAIN,
        )
        style_table_cell_bold = ParagraphStyle(
            name="GVTableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_NAVY,
        )
        style_table_header = ParagraphStyle(
            name="GVTableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_NAVY,
        )

        story = []

        # =========================================================================
        # PAGE 1: BRANDING BANNER, METADATA, SECTION 1 & SECTION 2
        # =========================================================================

        # 1. Top Branding Banner
        banner_content = [
            [
                Paragraph("<b>GRIDVISION</b><br/><font color='#00A396' size='7.5'>ENERGY INTELLIGENCE PLATFORM</font>", style_banner_title),
                Paragraph("<para align='right'><b>MONTHLY ENERGY CONSUMPTION REPORT</b><br/><font color='#94A3B8' size='7.5'>Official Customer Summary</font></para>", style_banner_title),
            ]
        ]
        banner_table = Table(banner_content, colWidths=[usable_width * 0.5, usable_width * 0.5])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 4))

        # 2. Metadata Strip
        entity_display = f"OBJECTID {analysis.entity_id}" if analysis.entity_id is not None else "Cohort Aggregate"
        meta_data = [
            [
                Paragraph(f"<b>Customer / Building:</b> {self._paragraph(entity_display)}", style_table_cell),
                Paragraph(f"<b>Consumer Type:</b> {self._paragraph(analysis.persona.title())}", style_table_cell),
                Paragraph(f"<b>Reporting Period:</b> {analysis.period_start} – {analysis.period_end}", style_table_cell),
                Paragraph(f"<b>Generated:</b> {gen_date_str}", style_table_cell),
            ]
        ]
        meta_table = Table(meta_data, colWidths=[usable_width * 0.25] * 4)
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # -------------------------------------------------------------------------
        # SECTION 1: MONTHLY CONSUMPTION OVERVIEW
        # -------------------------------------------------------------------------
        story.append(Paragraph("1. Monthly Consumption Overview", style_section_heading))
        story.append(Paragraph("Key monthly electricity consumption indicators and estimated billing for the reporting cycle.", style_intro_text))

        # Row 1 KPI cards: Total Monthly, Average Daily, Estimated Bill
        bill_display = f"₹{analysis.estimated_monthly_bill_inr:,.2f}" if analysis.estimated_monthly_bill_inr is not None else "Unconfigured"
        kpi_r1 = [
            [
                Paragraph("TOTAL CONSUMPTION", style_card_label),
                Paragraph("AVERAGE DAILY USAGE", style_card_label),
                Paragraph("ESTIMATED MONTHLY BILL", style_card_label),
            ],
            [
                Paragraph(f"{analysis.total_monthly_kwh:,.2f} <font size='8' color='#00A396'>kWh</font>", style_card_val),
                Paragraph(f"{analysis.avg_daily_kwh:,.2f} <font size='8' color='#00A396'>kWh/day</font>", style_card_val),
                Paragraph(bill_display, style_card_val),
            ],
            [
                Paragraph(f"{analysis.days_returned} observed calendar days", style_card_sub),
                Paragraph(f"Normalized across {analysis.days_returned} days", style_card_sub),
                Paragraph(f"Rate: ₹{analysis.bill.tariff_inr_per_kwh:.2f}/kWh" if analysis.bill.tariff_inr_per_kwh else "Tariff unavailable", style_card_sub),
            ],
        ]
        t_kpi_r1 = Table(kpi_r1, colWidths=[usable_width / 3.0] * 3)
        t_kpi_r1.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t_kpi_r1)
        story.append(Spacer(1, 4))

        # Row 2 KPI cards: Peak Consumption (Hourly & Daily) and Lowest Consumption (Hourly & Daily)
        peak_hr_str = f"<b>Peak Hourly:</b> {analysis.peak_hourly.value_kwh:.2f} kWh ({analysis.peak_hourly.timestamp_or_date})" if analysis.peak_hourly else "<b>Peak Hourly:</b> Unavailable"
        peak_dy_str = f"<b>Peak Daily:</b> {analysis.peak_daily.value_kwh:.2f} kWh ({analysis.peak_daily.timestamp_or_date})"

        low_hr_str = f"<b>Lowest Hourly:</b> {analysis.lowest_hourly.value_kwh:.2f} kWh ({analysis.lowest_hourly.timestamp_or_date})" if analysis.lowest_hourly else "<b>Lowest Hourly:</b> Unavailable"
        low_dy_str = f"<b>Lowest Daily:</b> {analysis.lowest_daily.value_kwh:.2f} kWh ({analysis.lowest_daily.timestamp_or_date})"

        kpi_r2 = [
            [
                Paragraph("PEAK CONSUMPTION (HOURLY & DAILY)", style_card_label),
                Paragraph("LOWEST CONSUMPTION (HOURLY & DAILY)", style_card_label),
            ],
            [
                Paragraph(f"{peak_hr_str}<br/>{peak_dy_str}", style_table_cell),
                Paragraph(f"{low_hr_str}<br/>{low_dy_str}", style_table_cell),
            ],
        ]
        t_kpi_r2 = Table(kpi_r2, colWidths=[usable_width / 2.0] * 2)
        t_kpi_r2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t_kpi_r2)
        story.append(Spacer(1, 8))

        # -------------------------------------------------------------------------
        # SECTION 2: AVERAGE HOURLY CONSUMPTION PATTERN
        # -------------------------------------------------------------------------
        story.append(Paragraph("2. Average Hourly Consumption Pattern", style_section_heading))
        story.append(Paragraph(
            "Average consumption across each of the 24 hours of the day computed from valid observations. "
            "Missing readings are preserved rather than assumed zero.",
            style_intro_text,
        ))

        # 24-hour vector bar chart
        hourly_chart = build_hourly_pattern_chart(analysis.hourly_pattern, width=usable_width, height=105)
        story.append(hourly_chart)
        story.append(Spacer(1, 3))

        # Hourly highlight callout chips
        peak_hr_label = f"{analysis.peak_hour.hour_label} ({analysis.peak_hour.average_kwh:.2f} kWh avg)" if analysis.peak_hour and analysis.peak_hour.average_kwh is not None else "N/A"
        lowest_hr_label = f"{analysis.lowest_hour.hour_label} ({analysis.lowest_hour.average_kwh:.2f} kWh avg)" if analysis.lowest_hour and analysis.lowest_hour.average_kwh is not None else "N/A"
        valid_hrs_count = sum(1 for p in analysis.hourly_pattern if p.average_kwh is not None)

        hourly_chips = [
            [
                Paragraph(f"<b>Peak Hour:</b> <font color='#EA580C'>{peak_hr_label}</font>", style_table_cell),
                Paragraph(f"<b>Lowest Hour:</b> <font color='#16A34A'>{lowest_hr_label}</font>", style_table_cell),
                Paragraph(f"<b>Observed Hours:</b> {valid_hrs_count} of 24 diurnal hours observed", style_table_cell),
            ]
        ]
        t_h_chips = Table(hourly_chips, colWidths=[usable_width / 3.0] * 3)
        t_h_chips.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_h_chips)

        # End of Page 1
        story.append(PageBreak())

        # =========================================================================
        # PAGE 2: SECTION 3 & SECTION 4
        # =========================================================================

        # -------------------------------------------------------------------------
        # SECTION 3: DAILY CONSUMPTION TREND
        # -------------------------------------------------------------------------
        story.append(Paragraph("3. Daily Consumption Trend", style_section_heading))
        story.append(Paragraph(
            "Daily aggregated electricity consumption across the entire reporting month. "
            "The horizontal dashed reference line marks the monthly average daily consumption.",
            style_intro_text,
        ))

        # Daily Trend Chart
        daily_chart = build_daily_trend_chart(analysis.daily_trend, analysis.avg_daily_kwh, width=usable_width, height=115)
        story.append(daily_chart)
        story.append(Spacer(1, 3))

        # Daily Highlights Callout Table
        daily_summary_data = [
            [
                Paragraph("<b>Highest Consumption Day</b>", style_table_header),
                Paragraph("<b>Lowest Consumption Day</b>", style_table_header),
                Paragraph("<b>Average Daily Reference</b>", style_table_header),
            ],
            [
                Paragraph(f"<font color='#EA580C'><b>{analysis.highest_day.date_str}</b></font> — {analysis.highest_day.total_kwh:.2f} kWh", style_table_cell),
                Paragraph(f"<font color='#16A34A'><b>{analysis.lowest_day.date_str}</b></font> — {analysis.lowest_day.total_kwh:.2f} kWh", style_table_cell),
                Paragraph(f"<font color='#D97706'><b>Reference Line:</b></font> {analysis.avg_daily_kwh:.2f} kWh/day", style_table_cell),
            ],
        ]
        t_daily_summary = Table(daily_summary_data, colWidths=[usable_width / 3.0] * 3)
        t_daily_summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (0, 1), (-1, 1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_daily_summary)
        story.append(Spacer(1, 10))

        # -------------------------------------------------------------------------
        # SECTION 4: WEEKDAY VS WEEKEND COMPARISON
        # -------------------------------------------------------------------------
        story.append(Paragraph("4. Weekday vs Weekend Comparison", style_section_heading))
        story.append(Paragraph(
            "Comparison of consumption patterns between business weekdays (Monday–Friday) and weekend days (Saturday–Sunday) using actual calendar timestamps.",
            style_intro_text,
        ))

        # Weekday vs Weekend Comparison Chart
        ww_chart = build_weekday_weekend_chart(analysis.weekday_weekend, width=usable_width, height=105)
        story.append(ww_chart)
        story.append(Spacer(1, 4))

        # Weekday vs Weekend Detailed Table
        ww = analysis.weekday_weekend
        diff_label = f"{ww.diff_pct:+.2f}%" if ww.diff_pct is not None else "N/A"
        ww_table_data = [
            [
                Paragraph("<b>Category</b>", style_table_header),
                Paragraph("<b>Days Count</b>", style_table_header),
                Paragraph("<b>Total Consumption</b>", style_table_header),
                Paragraph("<b>Average Daily</b>", style_table_header),
                Paragraph("<b>Peak Daily (Date)</b>", style_table_header),
            ],
            [
                Paragraph("<b>Weekdays (Mon–Fri)</b>", style_table_cell_bold),
                Paragraph(f"{ww.weekday.days_count} days", style_table_cell),
                Paragraph(f"{ww.weekday.total_kwh:,.2f} kWh", style_table_cell),
                Paragraph(f"{ww.weekday.avg_daily_kwh:,.2f} kWh/day", style_table_cell),
                Paragraph(f"{ww.weekday.peak_daily_kwh:.2f} kWh ({ww.weekday.peak_date or 'N/A'})", style_table_cell),
            ],
            [
                Paragraph("<b>Weekends (Sat–Sun)</b>", style_table_cell_bold),
                Paragraph(f"{ww.weekend.days_count} days", style_table_cell),
                Paragraph(f"{ww.weekend.total_kwh:,.2f} kWh", style_table_cell),
                Paragraph(f"{ww.weekend.avg_daily_kwh:,.2f} kWh/day", style_table_cell),
                Paragraph(f"{ww.weekend.peak_daily_kwh:.2f} kWh ({ww.weekend.peak_date or 'N/A'})", style_table_cell),
            ],
            [
                Paragraph("<b>Difference (Weekend vs Weekday)</b>", style_table_cell_bold),
                Paragraph("—", style_table_cell),
                Paragraph(f"{ww.weekend.total_kwh - ww.weekday.total_kwh:+,.2f} kWh", style_table_cell),
                Paragraph(f"{diff_label} daily average", style_table_cell_bold),
                Paragraph(f"{ww.weekend.peak_daily_kwh - ww.weekday.peak_daily_kwh:+.2f} kWh peak diff", style_table_cell),
            ],
        ]
        t_ww = Table(ww_table_data, colWidths=[usable_width * 0.26, usable_width * 0.16, usable_width * 0.19, usable_width * 0.19, usable_width * 0.20])
        t_ww.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (0, 1), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_ww)

        # End of Page 2
        story.append(PageBreak())

        # =========================================================================
        # PAGE 3: SECTION 5, SECTION 6 & SECTION 7
        # =========================================================================

        # -------------------------------------------------------------------------
        # SECTION 5: WEEKLY CONSUMPTION SUMMARY
        # -------------------------------------------------------------------------
        story.append(Paragraph("5. Weekly Consumption Summary", style_section_heading))
        story.append(Paragraph(
            "Weekly consumption aggregated by calendar week. Partial weeks at the start and end of the month are explicitly indicated with daily averages for normalized comparison.",
            style_intro_text,
        ))

        # Weekly Bar Chart
        weekly_chart = build_weekly_summary_chart(analysis.weekly_summary, width=usable_width, height=95)
        story.append(weekly_chart)
        story.append(Spacer(1, 3))

        # Weekly Table
        weekly_table_data = [
            [
                Paragraph("<b>Calendar Week</b>", style_table_header),
                Paragraph("<b>Date Range</b>", style_table_header),
                Paragraph("<b>Days</b>", style_table_header),
                Paragraph("<b>Week Status</b>", style_table_header),
                Paragraph("<b>Total Consumption</b>", style_table_header),
                Paragraph("<b>Daily Average</b>", style_table_header),
            ]
        ]
        for w in analysis.weekly_summary:
            status_text = "<font color='#0284C7'>Partial Week</font>" if w.is_partial else "Full Week (7 days)"
            weekly_table_data.append([
                Paragraph(f"<b>{w.week_label}</b>", style_table_cell_bold),
                Paragraph(f"{w.start_date} – {w.end_date}", style_table_cell),
                Paragraph(f"{w.days_count} days", style_table_cell),
                Paragraph(status_text, style_table_cell),
                Paragraph(f"{w.total_kwh:,.2f} kWh", style_table_cell),
                Paragraph(f"{w.avg_daily_kwh:,.2f} kWh/day", style_table_cell),
            ])
        t_weekly = Table(weekly_table_data, colWidths=[usable_width * 0.16, usable_width * 0.24, usable_width * 0.12, usable_width * 0.18, usable_width * 0.15, usable_width * 0.15])
        t_weekly.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (0, 1), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_weekly)
        story.append(Spacer(1, 8))

        # -------------------------------------------------------------------------
        # SECTION 6: CONSUMPTION CONSISTENCY
        # -------------------------------------------------------------------------
        story.append(Paragraph("6. Consumption Consistency", style_section_heading))

        cs = analysis.consistency
        consistency_table_data = [
            [
                Paragraph("<b>Metric</b>", style_table_header),
                Paragraph("<b>Calculated Value</b>", style_table_header),
                Paragraph("<b>Metric Description & Interpretation</b>", style_table_header),
            ],
            [
                Paragraph("<b>Mean Daily Consumption</b>", style_table_cell_bold),
                Paragraph(f"<b>{cs.mean_daily_kwh:,.2f}</b> kWh/day", style_table_cell),
                Paragraph("Arithmetic average of daily consumption across all observed calendar days.", style_table_cell),
            ],
            [
                Paragraph("<b>Standard Deviation (&sigma;)</b>", style_table_cell_bold),
                Paragraph(f"<b>{cs.std_dev_daily_kwh:,.2f}</b> kWh/day", style_table_cell),
                Paragraph("Measures absolute day-to-day dispersion around the monthly average.", style_table_cell),
            ],
            [
                Paragraph("<b>Coefficient of Variation (CV)</b>", style_table_cell_bold),
                Paragraph(f"<b>{cs.cv_percent:.2f}%</b>", style_table_cell_bold),
                Paragraph("Ratio of standard deviation to mean (CV = &sigma; / &mu; &times; 100%). Scale-independent variability index.", style_table_cell),
            ],
            [
                Paragraph("<b>Consumption Range</b>", style_table_cell_bold),
                Paragraph(f"<b>{cs.variability_range_kwh:,.2f}</b> kWh", style_table_cell),
                Paragraph(f"Spread between highest day ({analysis.highest_day.total_kwh:.2f} kWh) and lowest day ({analysis.lowest_day.total_kwh:.2f} kWh).", style_table_cell),
            ],
            [
                Paragraph("<b>Variability Assessment</b>", style_table_cell_bold),
                Paragraph(f"<font color='#00A396'><b>{cs.variability_category}</b></font>", style_table_cell_bold),
                Paragraph("Descriptive classification reflecting consistency of daily energy consumption habits without arbitrary scoring thresholds.", style_table_cell),
            ],
        ]
        t_consistency = Table(consistency_table_data, colWidths=[usable_width * 0.28, usable_width * 0.22, usable_width * 0.50])
        t_consistency.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (0, 1), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_consistency)
        story.append(Spacer(1, 8))

        # -------------------------------------------------------------------------
        # SECTION 7: ELECTRICITY BILL BREAKDOWN
        # -------------------------------------------------------------------------
        story.append(Paragraph("7. Electricity Bill Breakdown", style_section_heading))

        bill = analysis.bill
        if bill.is_available:
            bill_table_data = [
                [
                    Paragraph("<b>Billing Component</b>", style_table_header),
                    Paragraph("<b>Calculation Basis / Rate</b>", style_table_header),
                    Paragraph("<b>Amount (INR)</b>", style_table_header),
                ],
                [
                    Paragraph("Energy Consumption", style_table_cell),
                    Paragraph(f"{bill.total_consumption_kwh:,.2f} kWh &times; ₹{bill.tariff_inr_per_kwh:.2f}/kWh", style_table_cell),
                    Paragraph(f"₹{bill.energy_charges_inr:,.2f}", style_table_cell),
                ],
                [
                    Paragraph("Fixed Monthly Charges", style_table_cell),
                    Paragraph("Not configured in source profile", style_table_cell),
                    Paragraph("₹0.00", style_table_cell),
                ],
                [
                    Paragraph("Taxes and Regulatory Fees", style_table_cell),
                    Paragraph("Not configured in source profile", style_table_cell),
                    Paragraph("₹0.00", style_table_cell),
                ],
                [
                    Paragraph("<b>Estimated Total Electricity Bill</b>", style_table_cell_bold),
                    Paragraph("<b>Inclusive of configured energy charges</b>", style_table_cell_bold),
                    Paragraph(f"<b>₹{bill.estimated_total_bill_inr:,.2f}</b>", style_card_val),
                ],
            ]
        else:
            bill_table_data = [
                [
                    Paragraph("<b>Billing Component</b>", style_table_header),
                    Paragraph("<b>Calculation Basis / Rate</b>", style_table_header),
                    Paragraph("<b>Amount (INR)</b>", style_table_header),
                ],
                [
                    Paragraph("Energy Consumption", style_table_cell),
                    Paragraph(f"{bill.total_consumption_kwh:,.2f} kWh", style_table_cell),
                    Paragraph("Tariff unconfigured", style_table_cell),
                ],
                [
                    Paragraph("<b>Estimated Total Electricity Bill</b>", style_table_cell_bold),
                    Paragraph("<b>Tariff information unavailable</b>", style_table_cell_bold),
                    Paragraph("<b>Unavailable</b>", style_card_val),
                ],
            ]

        t_bill = Table(bill_table_data, colWidths=[usable_width * 0.35, usable_width * 0.40, usable_width * 0.25])
        t_bill.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (0, 1), (-1, -2), COLOR_BG),
            ("BACKGROUND", (0, -1), (-1, -1), COLOR_LIGHT_TEAL),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_bill)
        story.append(Spacer(1, 4))

        # Tariff Notes Box
        t_note = Table([[Paragraph(f"<b>Tariff Configuration & Disclaimer:</b> {self._paragraph(bill.tariff_notes)}", style_intro_text)]], colWidths=[usable_width])
        t_note.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_note)

        # Running headers and footers
        def draw_page_decorations(canvas, document):
            canvas.saveState()
            # Footer on all pages
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(COLOR_TEXT_MUTED)
            canvas.drawString(margin, 16, f"GridVision Energy Intelligence · Customer Report · {report_id_str}")
            canvas.drawRightString(A4[0] - margin, 16, f"Page {document.page} of 3")

            # Running header on later pages (Page 2 & 3)
            if document.page > 1:
                canvas.setFont("Helvetica-Bold", 7.5)
                canvas.setFillColor(COLOR_NAVY)
                canvas.drawString(margin, A4[1] - 22, "GRIDVISION")
                canvas.setFont("Helvetica", 7.5)
                canvas.setFillColor(COLOR_TEXT_MUTED)
                canvas.drawString(margin + 55, A4[1] - 22, f"· Monthly Energy Consumption Report · {entity_display}")
                canvas.drawRightString(A4[0] - margin, A4[1] - 22, f"Period: {analysis.period_start} – {analysis.period_end}")
                canvas.setStrokeColor(COLOR_BORDER)
                canvas.setLineWidth(0.5)
                canvas.line(margin, A4[1] - 26, A4[0] - margin, A4[1] - 26)

            canvas.restoreState()

        try:
            doc.build(story, onFirstPage=draw_page_decorations, onLaterPages=draw_page_decorations)
        except Exception as exc:
            raise PDFRenderError(f"PDF consumption report rendering failed: {exc}") from exc

        return buffer.getvalue()

    def _report_table(self, table: ReportTable, Table, TableStyle, Paragraph, colors, styles):
        return self._table(
            Table,
            TableStyle,
            Paragraph,
            table.columns,
            table.rows,
            colors,
            styles,
        )

    def _table(self, Table, TableStyle, Paragraph, headers, rows, colors, styles):
        values = [[Paragraph(self._paragraph(value), styles["ReportSmall"]) for value in headers]]
        values.extend(
            [[Paragraph(self._paragraph(value), styles["ReportSmall"]) for value in row] for row in rows]
        )
        table = Table(values, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#152238")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c7cfdb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def render_anomaly_report(
        self,
        payload: dict[str, Any],
        report_id: str | None = None,
    ) -> bytes:
        """Render a professional, customer-specific Anomaly Rectification PDF report."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
        except ImportError as exc:
            raise PDFRenderError("PDF support is not installed") from exc

        event_id = str(payload.get("event_id", "N/A"))
        run_id = str(payload.get("run_id", "N/A"))
        persona = str(payload.get("persona", "household")).capitalize()
        customer_id = payload.get("customer_id")
        customer_name = str(payload.get("customer_name") or (f"Consumer ID {customer_id}" if customer_id else "Authorized Stakeholder"))
        company_name = str(payload.get("company_name", "GridVision Energy Intelligence"))

        anomaly_type = str(payload.get("anomaly_type") or payload.get("dominant_anomaly_type") or "Anomaly Event")
        severity_info = payload.get("severity") or {}
        sev_score = float(severity_info.get("score", 0.0))
        sev_level = str(severity_info.get("level", "MEDIUM")).upper()

        details = payload.get("event_details") or {}
        start_time = str(details.get("start_time", "N/A"))
        end_time = str(details.get("end_time", "N/A"))
        duration_hours = float(details.get("duration_hours", 0.0))
        affected_count = int(details.get("affected_customer_count", 1))
        scope = str(details.get("scope", "SINGLE_CUSTOMER"))
        coords = details.get("coordinates") or {}
        lat = coords.get("latitude") if isinstance(coords, dict) else getattr(coords, "latitude", None)
        lon = coords.get("longitude") if isinstance(coords, dict) else getattr(coords, "longitude", None)
        coords_str = f"{lat:.4f}, {lon:.4f}" if lat is not None and lon is not None else "N/A"

        causes = payload.get("probable_causes") or []
        actions = payload.get("corrective_actions") or []
        preventions = payload.get("preventive_recommendations") or []
        citations = payload.get("guidance_citations") or []
        limitations = payload.get("limitations") or []
        gen_timestamp = str(payload.get("generated_at", datetime.now(timezone.utc).isoformat()))

        # Determine severity badge styling
        if sev_level == "CRITICAL":
            sev_bg = colors.HexColor("#FEF2F2")
            sev_border = colors.HexColor("#DC2626")
            sev_text = colors.HexColor("#991B1B")
        elif sev_level == "HIGH":
            sev_bg = colors.HexColor("#FFF7ED")
            sev_border = colors.HexColor("#EA580C")
            sev_text = colors.HexColor("#9A3412")
        elif sev_level == "MEDIUM":
            sev_bg = colors.HexColor("#FFFBEB")
            sev_border = colors.HexColor("#D97706")
            sev_text = colors.HexColor("#92400E")
        else:
            sev_bg = colors.HexColor("#F0FDFA")
            sev_border = colors.HexColor("#0D9488")
            sev_text = colors.HexColor("#0F766E")

        buffer = io.BytesIO()
        margin = 36.0  # 0.5 in
        usable_width = A4[0] - 2 * margin

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title=f"GridVision Anomaly Report - {event_id}",
            author="GridVision Energy Intelligence",
        )

        styles = getSampleStyleSheet()

        style_banner_title = ParagraphStyle(
            name="GVAnomBannerTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13.5,
            leading=16.5,
            textColor=colors.white,
        )
        style_section_heading = ParagraphStyle(
            name="GVAnomSectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=COLOR_NAVY,
            spaceAfter=2,
        )
        style_body = ParagraphStyle(
            name="GVAnomBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.5,
            textColor=COLOR_TEXT_MAIN,
        )
        style_body_bold = ParagraphStyle(
            name="GVAnomBodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9.5,
            textColor=COLOR_NAVY,
        )
        style_card_label = ParagraphStyle(
            name="GVAnomCardLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8,
            textColor=COLOR_TEXT_MUTED,
        )
        style_card_val = ParagraphStyle(
            name="GVAnomCardVal",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=COLOR_NAVY,
        )
        style_card_sub = ParagraphStyle(
            name="GVAnomCardSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=6.5,
            leading=8,
            textColor=COLOR_TEAL,
        )
        style_badge = ParagraphStyle(
            name="GVAnomBadge",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10.5,
            alignment=1,
            textColor=sev_text,
        )
        style_subtle = ParagraphStyle(
            name="GVAnomSubtle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=6.5,
            leading=8.5,
            textColor=COLOR_TEXT_MUTED,
        )

        story = []

        # 1. Top Branding Banner
        banner_content = [
            [
                Paragraph("<b>GRIDVISION</b><br/><font color='#00A396' size='7.5'>ENERGY INTELLIGENCE PLATFORM</font>", style_banner_title),
                Paragraph("<para align='right'><b>ANOMALY INCIDENT & RECTIFICATION REPORT</b><br/><font color='#94A3B8' size='7'>Automated Engineering Incident Brief</font></para>", style_banner_title),
            ]
        ]
        banner_table = Table(banner_content, colWidths=[usable_width * 0.45, usable_width * 0.55])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 4))

        # 2. Metadata / Context Strip
        customer_display = f"ID: {customer_id}" if customer_id else "System Aggregate"
        meta_table_content = [
            [
                Paragraph(f"<b>Recipient / Account:</b> {self._paragraph(customer_name)} ({customer_display})", style_body),
                Paragraph(f"<b>Persona Tier:</b> {self._paragraph(persona)}", style_body),
                Paragraph("<b>Severity Level:</b>", style_body_bold),
            ],
            [
                Paragraph(f"<b>Event ID:</b> {self._paragraph(event_id)}  |  <b>Model Run:</b> {self._paragraph(run_id[:16])}...", style_body),
                Paragraph(f"<b>Issued:</b> {self._paragraph(gen_timestamp[:19].replace('T', ' '))}", style_body),
                Paragraph(f"<b>{sev_level} ({sev_score:.2f})</b>", style_badge),
            ]
        ]
        meta_table = Table(meta_table_content, colWidths=[usable_width * 0.50, usable_width * 0.32, usable_width * 0.18])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (1, -1), 0.3, COLOR_BORDER),
            ("BACKGROUND", (2, 0), (2, 1), sev_bg),
            ("BOX", (2, 0), (2, 1), 1.0, sev_border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 5))

        # 3. KPI Cards
        card_w = usable_width / 4.0
        kpi_cells = [
            [
                Paragraph("INCIDENT SEVERITY", style_card_label),
                Paragraph("AFFECTED SCOPE", style_card_label),
                Paragraph("DURATION", style_card_label),
                Paragraph("ANOMALY CATEGORY", style_card_label),
            ],
            [
                Paragraph(f"{sev_level}", style_card_val),
                Paragraph(f"{scope.replace('_', ' ').title()}", style_card_val),
                Paragraph(f"{duration_hours:.2f} hrs", style_card_val),
                Paragraph(f"{anomaly_type[:18]}", style_card_val),
            ],
            [
                Paragraph(f"Normalized Score: {sev_score:.3f}", style_card_sub),
                Paragraph(f"{affected_count} meter(s) impacted", style_card_sub),
                Paragraph(f"{start_time[:10]}", style_card_sub),
                Paragraph("Model Verified", style_card_sub),
            ]
        ]
        kpi_table = Table(kpi_cells, colWidths=[card_w] * 4)
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (0, -1), 0.5, COLOR_BORDER),
            ("BOX", (1, 0), (1, -1), 0.5, COLOR_BORDER),
            ("BOX", (2, 0), (2, -1), 0.5, COLOR_BORDER),
            ("BOX", (3, 0), (3, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 6))

        # 4. Incident Details Table
        story.append(Paragraph("1. Incident Details & Scope", style_section_heading))
        details_rows = [
            [Paragraph("<b>Parameter</b>", style_body_bold), Paragraph("<b>Recorded Value</b>", style_body_bold), Paragraph("<b>Engineering Context</b>", style_body_bold)],
            [Paragraph("Start Time", style_body), Paragraph(self._paragraph(start_time), style_body), Paragraph("Anomaly onset timestamp", style_subtle)],
            [Paragraph("End Time", style_body), Paragraph(self._paragraph(end_time), style_body), Paragraph("Anomaly cessation timestamp", style_subtle)],
            [Paragraph("Duration", style_body), Paragraph(f"{duration_hours:.2f} hours", style_body), Paragraph("Total duration of abnormal window", style_subtle)],
            [Paragraph("Primary Anomaly Type", style_body), Paragraph(self._paragraph(anomaly_type), style_body), Paragraph("Dominant algorithmic classification", style_subtle)],
            [Paragraph("Impacted Scope", style_body), Paragraph(f"{scope} ({affected_count} customer(s))", style_body), Paragraph("Localized spatial containment area", style_subtle)],
        ]
        if coords_str != "N/A":
            details_rows.append([Paragraph("Geo Coordinates", style_body), Paragraph(self._paragraph(coords_str), style_body), Paragraph("H3 cluster centroid", style_subtle)])

        details_table = Table(details_rows, colWidths=[usable_width * 0.28, usable_width * 0.42, usable_width * 0.30])
        details_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(details_table)
        story.append(Spacer(1, 6))

        # 5. Probable Causes (Root Cause Analysis)
        story.append(Paragraph("2. Root Cause Analysis (Physics & Operational Evidence)", style_section_heading))
        cause_items = [[Paragraph(f"• <b>Cause {i+1}:</b> {self._paragraph(c)}", style_body)] for i, c in enumerate(causes)] or [[Paragraph("No specific probable causes recorded.", style_body)]]
        causes_table = Table(cause_items, colWidths=[usable_width])
        causes_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(causes_table)
        story.append(Spacer(1, 6))

        # 6. Corrective Actions (Immediate Operational Plan)
        story.append(Paragraph("3. Immediate Corrective Action Plan", style_section_heading))
        action_items = [[Paragraph(f"<b>Step {i+1}:</b> {self._paragraph(a)}", style_body)] for i, a in enumerate(actions)] or [[Paragraph("No immediate corrective actions required.", style_body)]]
        actions_table = Table(action_items, colWidths=[usable_width])
        actions_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#93C5FD")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BFDBFE")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(actions_table)
        story.append(Spacer(1, 6))

        # 7. Preventive Recommendations
        story.append(Paragraph("4. Long-Term Preventive & Reliability Recommendations", style_section_heading))
        prev_items = [[Paragraph(f"• <b>Rec {i+1}:</b> {self._paragraph(p)}", style_body)] for i, p in enumerate(preventions)] or [[Paragraph("Standard grid monitoring protocols remain active.", style_body)]]
        prev_table = Table(prev_items, colWidths=[usable_width])
        prev_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#86EFAC")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BBF7D0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(prev_table)
        story.append(Spacer(1, 6))

        # 8. Guidance Citations (if any)
        if citations:
            story.append(Paragraph("5. Technical Standards & Regulatory References", style_section_heading))
            cit_rows = [[Paragraph("<b>Standard / Regulation</b>", style_body_bold), Paragraph("<b>Publishing Body</b>", style_body_bold), Paragraph("<b>Clause / Section</b>", style_body_bold)]]
            for cit in citations:
                cit_title = cit.get("title") if isinstance(cit, dict) else getattr(cit, "title", str(cit))
                cit_pub = (cit.get("publisher") if isinstance(cit, dict) else getattr(cit, "publisher", "")) or "Standard Body"
                cit_clause = (cit.get("clause") if isinstance(cit, dict) else getattr(cit, "clause", "")) or "Applicable Section"
                cit_rows.append([Paragraph(self._paragraph(cit_title), style_body), Paragraph(self._paragraph(cit_pub), style_body), Paragraph(self._paragraph(cit_clause), style_body)])
            cit_table = Table(cit_rows, colWidths=[usable_width * 0.45, usable_width * 0.30, usable_width * 0.25])
            cit_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(cit_table)
            story.append(Spacer(1, 6))

        # 9. Engineering Disclaimers & Methodology Notice
        story.append(Paragraph("6. Engineering Notes & Data Provenance", style_section_heading))
        lim_text = " ".join(limitations) if limitations else "Report automatically derived from GridVision machine learning inference and validated sensor telemetry. Not a substitute for certified on-site electrical inspection."
        notice_cell = [[Paragraph(f"<b>Notice:</b> {self._paragraph(lim_text)}", style_subtle)]]
        notice_table = Table(notice_cell, colWidths=[usable_width])
        notice_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FCD34D")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(notice_table)

        # Running header and footer
        def draw_decorations(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 7.0)
            canvas.setFillColor(COLOR_TEXT_MUTED)
            canvas.drawString(margin, 14, f"GridVision Energy Intelligence · Automated Anomaly Rectification Brief · Event {event_id}")
            canvas.drawRightString(A4[0] - margin, 14, f"Page {document.page}")
            if document.page > 1:
                canvas.setFont("Helvetica-Bold", 7.0)
                canvas.setFillColor(COLOR_NAVY)
                canvas.drawString(margin, A4[1] - 20, "GRIDVISION")
                canvas.setFont("Helvetica", 7.0)
                canvas.setFillColor(COLOR_TEXT_MUTED)
                canvas.drawString(margin + 55, A4[1] - 20, f"· Anomaly Rectification Report · {customer_name}")
                canvas.drawRightString(A4[0] - margin, A4[1] - 20, f"Event: {event_id}")
                canvas.setStrokeColor(COLOR_BORDER)
                canvas.setLineWidth(0.5)
                canvas.line(margin, A4[1] - 24, A4[0] - margin, A4[1] - 24)
            canvas.restoreState()

        try:
            doc.build(story, onFirstPage=draw_decorations, onLaterPages=draw_decorations)
        except Exception as exc:
            raise PDFRenderError(f"PDF anomaly report rendering failed: {exc}") from exc

        return buffer.getvalue()

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
    ) -> bytes:
        """Render a report document or delegated monthly consumption report to PDF."""
        if analysis is not None:
            return self.render_consumption_report(analysis, report_id=report.report_id)

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

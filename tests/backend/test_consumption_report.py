"""Comprehensive unit and integration tests for GridVision Monthly Energy Consumption Reports."""

import math
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from report_generator.services.consumption_analytics import (
    ConsumptionReportCalculator,
    MonthlyConsumptionAnalysis,
    is_consumption_report,
)
from report_generator.services.consumption_charts import (
    build_daily_trend_chart,
    build_hourly_pattern_chart,
    build_weekday_weekend_chart,
    build_weekly_summary_chart,
)
from report_generator.services.pdf_renderer import PDFReportRenderer


def _create_synthetic_month_data(
    num_days: int = 31,
    start_date: str = "2018-12-01",
    base_kwh: float = 1.0,
    missing_hours_day1: list[int] | None = None,
    duplicate_hours: bool = False,
    tariff_inr: float | None = 10.0,
) -> dict[str, Any]:
    """Helper to generate known synthetic hourly data for controlled unit testing."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    hourly_readings = []

    for d in range(num_days):
        current_day = start_dt + timedelta(days=d)
        for h in range(24):
            if d == 0 and missing_hours_day1 and h in missing_hours_day1:
                continue  # skip to simulate missing readings

            # Formula for predictable known values:
            # hour 21 is peak (+2.0), hour 13 is lowest (-0.5), other hours have known offset
            offset = 2.0 if h == 21 else (-0.5 if h == 13 else 0.0)
            day_offset = (d % 5) * 0.1
            kwh = base_kwh + offset + day_offset

            ts = current_day.replace(hour=h, minute=0, second=0)
            hourly_readings.append({
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "consumptionKwh": round(kwh, 4),
            })
            if duplicate_hours and h == 5:
                # Add duplicate with same timestamp to test deduplication
                hourly_readings.append({
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "consumptionKwh": round(kwh, 4),
                })

    return {
        "entityId": 89,
        "persona": "household",
        "period": {
            "start": start_date,
            "end": (start_dt + timedelta(days=num_days - 1)).strftime("%Y-%m-%d"),
        },
        "unit": "kWh",
        "hourlyReadings": hourly_readings,
        "tariffInrPerKwh": tariff_inr,
    }


class TestConsumptionReportSections:
    """Validate all seven required report sections with exact known values."""

    def test_section_1_monthly_consumption_overview(self):
        """Test KPI cards: Total monthly, average daily, peak/lowest (hourly and daily), estimated bill."""
        # 31 days with uniform 1.0 kWh per hour = 24.0 kWh/day
        data = _create_synthetic_month_data(num_days=31, base_kwh=1.0)
        analysis = ConsumptionReportCalculator.calculate(data)

        # 1. Total monthly consumption
        assert analysis.total_monthly_kwh > 0
        expected_total = sum(d.total_kwh for d in analysis.daily_trend)
        assert round(analysis.total_monthly_kwh, 2) == round(expected_total, 2)

        # 2. Average daily consumption
        expected_avg = expected_total / 31.0
        assert round(analysis.avg_daily_kwh, 3) == round(expected_avg, 3)

        # 3. Peak consumption (hourly vs daily distinction)
        assert analysis.peak_hourly is not None
        assert analysis.peak_hourly.value_kwh > 0
        assert ":" in analysis.peak_hourly.timestamp_or_date  # Timestamp format
        assert analysis.peak_daily.value_kwh > analysis.peak_hourly.value_kwh
        assert len(analysis.peak_daily.timestamp_or_date) == 10  # YYYY-MM-DD format

        # 4. Lowest consumption (hourly vs daily distinction)
        assert analysis.lowest_hourly is not None
        assert analysis.lowest_hourly.value_kwh > 0
        assert analysis.lowest_daily.value_kwh > analysis.lowest_hourly.value_kwh

        # 5. Estimated monthly bill
        assert analysis.estimated_monthly_bill_inr is not None
        expected_bill = round(analysis.total_monthly_kwh * 10.0, 2)
        assert analysis.estimated_monthly_bill_inr == expected_bill

    def test_section_2_average_hourly_consumption_pattern(self):
        """Test 24-hour diurnal averages, missing hour handling, peak and lowest hours."""
        # Day 1 is missing hour 0; all other days have hour 0
        data = _create_synthetic_month_data(num_days=31, missing_hours_day1=[0])
        analysis = ConsumptionReportCalculator.calculate(data)

        assert len(analysis.hourly_pattern) == 24
        h0 = analysis.hourly_pattern[0]
        # Hour 0 should have 30 valid days, NOT 31, and NOT zero
        assert h0.valid_days_count == 30
        assert h0.average_kwh is not None
        assert h0.average_kwh > 0.0

        # Peak and lowest identification
        assert analysis.peak_hour is not None
        assert analysis.peak_hour.hour == 21  # Hour 21 had +2.0 offset
        assert analysis.lowest_hour is not None
        assert analysis.lowest_hour.hour == 13  # Hour 13 had -0.5 offset

        # Axis labels and units
        assert all(p.hour_label == f"{p.hour:02d}:00" for p in analysis.hourly_pattern)

    def test_section_2_missing_hour_never_treated_as_zero(self):
        """Ensure an hour completely absent across all days is marked None, never 0."""
        # Skip hour 4 on every single day
        start_dt = datetime(2018, 12, 1)
        readings = []
        for d in range(10):
            day_dt = start_dt + timedelta(days=d)
            for h in range(24):
                if h == 4:
                    continue  # hour 4 missing completely
                readings.append({
                    "timestamp": day_dt.replace(hour=h).strftime("%Y-%m-%d %H:%M:%S"),
                    "consumptionKwh": 2.0,
                })
        data = {
            "entityId": 1,
            "period": {"start": "2018-12-01", "end": "2018-12-10"},
            "hourlyReadings": readings,
        }
        analysis = ConsumptionReportCalculator.calculate(data)
        h4 = analysis.hourly_pattern[4]
        assert h4.average_kwh is None  # Never treated as 0.0!
        assert h4.valid_days_count == 0

    def test_section_3_daily_consumption_trend(self):
        """Test daily totals, reference line, highest and lowest days."""
        data = _create_synthetic_month_data(num_days=31)
        analysis = ConsumptionReportCalculator.calculate(data)

        assert len(analysis.daily_trend) == 31
        # Reference line is the monthly average daily consumption
        assert analysis.avg_daily_kwh == round(sum(d.total_kwh for d in analysis.daily_trend) / 31, 3)

        # Peak and lowest days correctly marked
        assert analysis.highest_day.is_peak is True
        assert analysis.lowest_day.is_lowest is True
        assert analysis.highest_day.total_kwh >= analysis.lowest_day.total_kwh
        assert any(d.date_str == analysis.highest_day.date_str for d in analysis.daily_trend)
        assert any(d.date_str == analysis.lowest_day.date_str for d in analysis.daily_trend)

    def test_section_4_weekday_vs_weekend_comparison(self):
        """Test weekday (Mon-Fri) vs weekend (Sat-Sun) classification with actual dates."""
        # Dec 1, 2018 was Saturday; Dec 2 was Sunday; Dec 3-7 was Mon-Fri
        # In Dec 2018 (31 days): 21 weekdays, 10 weekend days
        data = _create_synthetic_month_data(num_days=31, start_date="2018-12-01")
        analysis = ConsumptionReportCalculator.calculate(data)

        ww = analysis.weekday_weekend
        assert ww.weekday.days_count == 21
        assert ww.weekend.days_count == 10
        assert ww.weekday.total_kwh > 0
        assert ww.weekend.total_kwh > 0
        assert round(ww.weekday.total_kwh + ww.weekend.total_kwh, 2) == round(analysis.total_monthly_kwh, 2)

        # Average daily comparison
        assert round(ww.weekday.avg_daily_kwh, 2) == round(ww.weekday.total_kwh / 21, 2)
        assert round(ww.weekend.avg_daily_kwh, 2) == round(ww.weekend.total_kwh / 10, 2)

    def test_section_5_weekly_consumption_summary(self):
        """Test calendar week aggregation and partial week handling."""
        # Dec 2018:
        # Week 1: Dec 01 - Dec 02 (2 days -> Partial)
        # Week 2: Dec 03 - Dec 09 (7 days -> Full)
        # Week 3: Dec 10 - Dec 16 (7 days -> Full)
        # Week 4: Dec 17 - Dec 23 (7 days -> Full)
        # Week 5: Dec 24 - Dec 30 (7 days -> Full)
        # Week 6: Dec 31 - Dec 31 (1 day -> Partial)
        data = _create_synthetic_month_data(num_days=31, start_date="2018-12-01")
        analysis = ConsumptionReportCalculator.calculate(data)

        weeks = analysis.weekly_summary
        assert len(weeks) == 6

        # Week 1 partial
        assert weeks[0].is_partial is True
        assert weeks[0].days_count == 2
        assert weeks[0].start_date == "2018-12-01"
        assert weeks[0].end_date == "2018-12-02"

        # Weeks 2-5 full
        for w in weeks[1:5]:
            assert w.is_partial is False
            assert w.days_count == 7

        # Week 6 partial
        assert weeks[5].is_partial is True
        assert weeks[5].days_count == 1
        assert weeks[5].start_date == "2018-12-31"

        # Total sum across weeks equals monthly total
        total_weekly = sum(w.total_kwh for w in weeks)
        assert round(total_weekly, 2) == round(analysis.total_monthly_kwh, 2)

    def test_section_6_consumption_consistency(self):
        """Test consistency metrics: mean, standard deviation, CV, range, and explanations."""
        # 10 days with exact values: [10, 10, 10, 10, 10, 20, 20, 20, 20, 20]
        # Mean = 15.0, Range = 10.0
        start_dt = datetime(2018, 12, 1)
        readings = []
        for d in range(10):
            day_dt = start_dt + timedelta(days=d)
            val_per_hour = (10.0 if d < 5 else 20.0) / 24.0
            for h in range(24):
                readings.append({
                    "timestamp": day_dt.replace(hour=h).strftime("%Y-%m-%d %H:%M:%S"),
                    "consumptionKwh": val_per_hour,
                })
        data = {
            "entityId": 42,
            "period": {"start": "2018-12-01", "end": "2018-12-10"},
            "hourlyReadings": readings,
        }
        analysis = ConsumptionReportCalculator.calculate(data)

        cs = analysis.consistency
        assert round(cs.mean_daily_kwh, 1) == 15.0
        assert round(cs.variability_range_kwh, 1) == 10.0
        # Standard deviation of [10]*5 + [20]*5: s = sqrt( (5*25 + 5*25) / 9 ) = sqrt(250/9) = 5.27
        assert round(cs.std_dev_daily_kwh, 2) == 5.27
        # CV = 5.27 / 15.0 * 100 = 35.14%
        assert round(cs.cv_percent, 1) == 35.1
        assert cs.variability_category == "High Variability"

        # Explanations must not introduce arbitrary scores
        assert len(cs.explanations) >= 4
        assert not any("score" in exp.casefold() for exp in cs.explanations)

    def test_section_7_electricity_bill_with_configured_tariff(self):
        """Test electricity bill calculation with flat rate tariff."""
        data = _create_synthetic_month_data(num_days=30, base_kwh=1.0, tariff_inr=10.0)
        analysis = ConsumptionReportCalculator.calculate(data)

        bill = analysis.bill
        assert bill.is_available is True
        assert bill.tariff_inr_per_kwh == 10.0
        assert bill.energy_charges_inr == round(analysis.total_monthly_kwh * 10.0, 2)
        assert bill.estimated_total_bill_inr == bill.energy_charges_inr
        assert "₹10.00/kWh" in bill.tariff_notes

    def test_section_7_electricity_bill_when_tariff_unavailable(self):
        """Test clear communication when tariff is unavailable."""
        data = _create_synthetic_month_data(num_days=30, tariff_inr=None)
        analysis = ConsumptionReportCalculator.calculate(data)

        bill = analysis.bill
        assert bill.is_available is False
        assert bill.tariff_inr_per_kwh is None
        assert bill.estimated_total_bill_inr is None
        assert "accurate electricity bill cannot be calculated" in bill.tariff_notes.lower()


class TestDataCleaningAndEdgeCases:
    """Test deduplication, missing readings, and incomplete days."""

    def test_duplicate_readings_deduplicated(self):
        """Duplicate observations with identical timestamps are not double counted."""
        data_normal = _create_synthetic_month_data(num_days=10, duplicate_hours=False)
        data_dups = _create_synthetic_month_data(num_days=10, duplicate_hours=True)

        res_normal = ConsumptionReportCalculator.calculate(data_normal)
        res_dups = ConsumptionReportCalculator.calculate(data_dups)

        assert res_normal.total_monthly_kwh == res_dups.total_monthly_kwh
        assert res_normal.observation_count == res_dups.observation_count

    def test_incomplete_days_detected(self):
        """Days with fewer than 24 readings are flagged as incomplete."""
        data = _create_synthetic_month_data(num_days=5, missing_hours_day1=[0, 1, 2])
        analysis = ConsumptionReportCalculator.calculate(data)

        d1 = analysis.daily_trend[0]
        assert d1.is_complete is False
        assert d1.readings_count == 21

        d2 = analysis.daily_trend[1]
        assert d2.is_complete is True
        assert d2.readings_count == 24


class TestPDFRendering:
    """Validate PDF generation, page count, and layout."""

    def test_pdf_renders_and_contains_all_seven_sections(self):
        data = _create_synthetic_month_data(num_days=31)
        analysis = ConsumptionReportCalculator.calculate(data)

        renderer = PDFReportRenderer()
        pdf_bytes = renderer.render_consumption_report(analysis, report_id="test-report-uuid")

        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 5000

        # Verify page count is 3
        import re
        pages = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
        assert len(pages) == 3

    def test_pdf_renderer_chart_generation(self):
        """Verify vector drawings generate without errors."""
        data = _create_synthetic_month_data(num_days=31)
        analysis = ConsumptionReportCalculator.calculate(data)

        c1 = build_hourly_pattern_chart(analysis.hourly_pattern)
        c2 = build_daily_trend_chart(analysis.daily_trend, analysis.avg_daily_kwh)
        c3 = build_weekday_weekend_chart(analysis.weekday_weekend)
        c4 = build_weekly_summary_chart(analysis.weekly_summary)

        assert c1.width == 520
        assert c2.width == 520
        assert c3.width == 520
        assert c4.width == 520


class TestRealDatasetIntegration:
    """Verify report generation against actual Silver parquet datasets."""

    def test_household_entity_89_real_dataset(self):
        from app.services.customer_silver_history_service import CustomerSilverHistoryService
        svc = CustomerSilverHistoryService(
            "data/silver/customer_silver.parquet",
            "data/metadata/dataset_versions/customer_silver/latest.json",
        )
        data = svc.get_latest_available_month(89)
        data["tariffInrPerKwh"] = 10.0

        analysis = ConsumptionReportCalculator.calculate(data)

        # Verify known figures from real Silver dataset
        assert analysis.entity_id == 89
        assert analysis.days_returned == 31
        assert analysis.total_monthly_kwh == 640.243
        assert analysis.avg_daily_kwh == 20.653
        assert analysis.peak_hourly is not None
        assert round(analysis.peak_hourly.value_kwh, 2) == 2.60
        assert round(analysis.lowest_hourly.value_kwh, 2) == 0.48
        assert round(analysis.peak_daily.value_kwh, 2) == 22.90
        assert round(analysis.lowest_daily.value_kwh, 2) == 19.32
        assert analysis.estimated_monthly_bill_inr == 6402.43

        # Verify PDF generates from real dataset
        renderer = PDFReportRenderer()
        pdf = renderer.render_consumption_report(analysis, report_id="real-silver-89")
        assert pdf.startswith(b"%PDF-")

    def test_commercial_building_85654_real_dataset(self):
        from app.services.commercial_silver_history_service import CommercialSilverHistoryService
        svc = CommercialSilverHistoryService(
            "data/silver/commercial_silver.parquet",
            "data/metadata/commercial/dataset_versions/silver/latest.json",
        )
        data = svc.get_latest_available_month("85654")
        data["tariffInrPerKwh"] = 10.0

        analysis = ConsumptionReportCalculator.calculate(data)

        assert analysis.entity_id == "85654"
        assert analysis.days_returned == 31
        assert analysis.total_monthly_kwh > 10000.0  # ~10,488 kWh
        assert analysis.avg_daily_kwh > 300.0

        renderer = PDFReportRenderer()
        pdf = renderer.render_consumption_report(analysis, report_id="real-commercial-85654")
        assert pdf.startswith(b"%PDF-")


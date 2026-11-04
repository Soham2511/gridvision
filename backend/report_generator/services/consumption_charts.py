"""ReportLab vector charts for GridVision Monthly Energy Consumption Reports.

Generates high-resolution vector charts for:
1. Section 2: 24-Hour Average Hourly Consumption Pattern
2. Section 3: Daily Consumption Trend (with average reference line)
3. Section 4: Weekday vs Weekend Comparison
4. Section 5: Weekly Consumption Summary
"""

from __future__ import annotations

import math
from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Rect, String
from reportlab.lib import colors

from report_generator.services.consumption_analytics import (
    CalendarWeekSummary,
    DailyTrendPoint,
    HourlyPatternPoint,
    WeekdayWeekendComparison,
)

# GridVision Brand Colors
COLOR_NAVY = colors.HexColor("#0B1F33")
COLOR_TEAL = colors.HexColor("#00A396")
COLOR_LIGHT_TEAL = colors.HexColor("#E6F6F5")
COLOR_BG = colors.HexColor("#F8FAFC")
COLOR_BORDER = colors.HexColor("#E2E8F0")
COLOR_GRID = colors.HexColor("#E2E8F0")
COLOR_TEXT_MAIN = colors.HexColor("#1E293B")
COLOR_TEXT_MUTED = colors.HexColor("#64748B")
COLOR_PEAK = colors.HexColor("#EA580C")  # Warm Coral/Orange
COLOR_LOWEST = colors.HexColor("#16A34A")  # Forest Green
COLOR_REF_LINE = colors.HexColor("#D97706")  # Amber for average reference line
COLOR_PARTIAL = colors.HexColor("#38BDF8")  # Sky blue for partial weeks


def build_hourly_pattern_chart(
    hourly_pattern: list[HourlyPatternPoint],
    width: float = 520,
    height: float = 120,
) -> Drawing:
    """Build a 24-hour bar chart displaying average consumption per hour."""
    d = Drawing(width, height)
    # Background card
    d.add(Rect(0, 0, width, height, fillColor=COLOR_BG, strokeColor=COLOR_BORDER, strokeWidth=0.5, rx=4, ry=4))

    # Plot area
    pad_left = 42.0
    pad_right = 16.0
    pad_top = 22.0
    pad_bottom = 26.0

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # Find max value
    valid_vals = [p.average_kwh for p in hourly_pattern if p.average_kwh is not None]
    max_val = max(valid_vals) if valid_vals else 1.0
    y_ceiling = math.ceil(max_val * 1.25 * 10) / 10.0 if max_val > 0 else 1.0
    if y_ceiling <= 0:
        y_ceiling = 1.0

    # Grid lines & Y-axis labels
    y_ticks = 4
    for i in range(y_ticks + 1):
        y_frac = i / y_ticks
        y_pos = pad_bottom + y_frac * plot_h
        val_tick = y_frac * y_ceiling
        d.add(Line(pad_left, y_pos, pad_left + plot_w, y_pos, strokeColor=COLOR_GRID, strokeWidth=0.5))
        d.add(String(pad_left - 6, y_pos - 3, f"{val_tick:.2f}", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="end"))

    # Y-axis title
    d.add(String(pad_left, height - 14, "Average Consumption (kWh)", fontName="Helvetica-Bold", fontSize=7, fillColor=COLOR_NAVY))

    # Legend in top right
    leg_x = width - 180
    leg_y = height - 14
    d.add(Rect(leg_x, leg_y - 2, 7, 7, fillColor=COLOR_PEAK, strokeColor=None))
    d.add(String(leg_x + 10, leg_y, "Peak Hour", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))
    d.add(Rect(leg_x + 55, leg_y - 2, 7, 7, fillColor=COLOR_LOWEST, strokeColor=None))
    d.add(String(leg_x + 65, leg_y, "Lowest Hour", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))
    d.add(Rect(leg_x + 115, leg_y - 2, 7, 7, fillColor=COLOR_TEAL, strokeColor=None))
    d.add(String(leg_x + 125, leg_y, "Hourly Average", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))

    # Bars for 24 hours
    bar_slot_w = plot_w / 24.0
    bar_w = bar_slot_w * 0.72

    for p in hourly_pattern:
        bx = pad_left + p.hour * bar_slot_w + (bar_slot_w - bar_w) / 2.0
        by = pad_bottom

        if p.average_kwh is not None:
            bh = (p.average_kwh / y_ceiling) * plot_h
            if p.is_peak:
                bar_color = COLOR_PEAK
            elif p.is_lowest:
                bar_color = COLOR_LOWEST
            else:
                bar_color = COLOR_TEAL
            d.add(Rect(bx, by, bar_w, bh, fillColor=bar_color, strokeColor=None))
        else:
            # Missing hour: hollow dashed rect to indicate no data rather than 0
            d.add(Rect(bx, by, bar_w, 8, fillColor=colors.HexColor("#CBD5E1"), strokeColor=None))

        # X-axis tick labels every 2 hours
        if p.hour % 2 == 0:
            d.add(String(bx + bar_w / 2.0, pad_bottom - 10, f"{p.hour:02d}", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="middle"))

    # X-axis label
    d.add(String(pad_left + plot_w / 2.0, 4, "Hour of Day (00:00 – 23:00)", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="middle"))
    return d


def build_daily_trend_chart(
    daily_trend: list[DailyTrendPoint],
    avg_daily_kwh: float,
    width: float = 520,
    height: float = 120,
) -> Drawing:
    """Build a daily consumption trend line chart with average reference line."""
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=COLOR_BG, strokeColor=COLOR_BORDER, strokeWidth=0.5, rx=4, ry=4))

    pad_left = 42.0
    pad_right = 16.0
    pad_top = 22.0
    pad_bottom = 26.0

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    vals = [pt.total_kwh for pt in daily_trend]
    max_val = max(vals) if vals else 1.0
    min_val = min(vals) if vals else 0.0

    # Expand ceiling and floor slightly
    y_ceiling = math.ceil(max(max_val, avg_daily_kwh) * 1.25)
    if y_ceiling <= 0:
        y_ceiling = 1.0
    y_floor = 0.0

    # Grid & Y labels
    y_ticks = 4
    for i in range(y_ticks + 1):
        y_frac = i / y_ticks
        y_pos = pad_bottom + y_frac * plot_h
        val_tick = y_floor + y_frac * (y_ceiling - y_floor)
        d.add(Line(pad_left, y_pos, pad_left + plot_w, y_pos, strokeColor=COLOR_GRID, strokeWidth=0.5))
        d.add(String(pad_left - 6, y_pos - 3, f"{val_tick:.1f}", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="end"))

    # Y-axis title
    d.add(String(pad_left, height - 14, "Daily Consumption (kWh/day)", fontName="Helvetica-Bold", fontSize=7, fillColor=COLOR_NAVY))

    # Reference Line (Average Daily Consumption)
    if y_ceiling > y_floor and avg_daily_kwh > 0:
        ref_y = pad_bottom + ((avg_daily_kwh - y_floor) / (y_ceiling - y_floor)) * plot_h
        # Draw dashed line
        dash_len = 4.0
        cx = pad_left
        while cx < pad_left + plot_w:
            d.add(Line(cx, ref_y, min(cx + dash_len, pad_left + plot_w), ref_y, strokeColor=COLOR_REF_LINE, strokeWidth=1.0))
            cx += dash_len * 2.0
        d.add(String(pad_left + plot_w - 4, ref_y + 3, f"Avg: {avg_daily_kwh:.2f} kWh/day", fontName="Helvetica-Bold", fontSize=6.5, fillColor=COLOR_REF_LINE, textAnchor="end"))

    # Legend
    leg_x = width - 170
    leg_y = height - 14
    d.add(Circle(leg_x + 3, leg_y + 1, 3.5, fillColor=COLOR_PEAK, strokeColor=None))
    d.add(String(leg_x + 10, leg_y, "Highest Day", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))
    d.add(Circle(leg_x + 60, leg_y + 1, 3.5, fillColor=COLOR_LOWEST, strokeColor=None))
    d.add(String(leg_x + 67, leg_y, "Lowest Day", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))

    # Daily trend line
    n_days = len(daily_trend)
    step_x = plot_w / max(n_days - 1, 1)

    coords: list[tuple[float, float, DailyTrendPoint]] = []
    for idx, pt in enumerate(daily_trend):
        cx = pad_left + idx * step_x
        cy = pad_bottom + ((pt.total_kwh - y_floor) / (y_ceiling - y_floor)) * plot_h
        coords.append((cx, cy, pt))

    # Draw line segments
    for idx in range(len(coords) - 1):
        x1, y1, _ = coords[idx]
        x2, y2, _ = coords[idx + 1]
        d.add(Line(x1, y1, x2, y2, strokeColor=COLOR_TEAL, strokeWidth=1.5))

    # Draw point markers
    for cx, cy, pt in coords:
        if pt.is_peak:
            d.add(Circle(cx, cy, 4.0, fillColor=COLOR_PEAK, strokeColor=colors.white, strokeWidth=1.0))
        elif pt.is_lowest:
            d.add(Circle(cx, cy, 4.0, fillColor=COLOR_LOWEST, strokeColor=colors.white, strokeWidth=1.0))
        else:
            d.add(Circle(cx, cy, 2.0, fillColor=COLOR_TEAL, strokeColor=None))

        # X-axis day tick labels
        if pt.day_number in (1, 5, 10, 15, 20, 25, 30) or pt == daily_trend[-1]:
            d.add(String(cx, pad_bottom - 10, str(pt.day_number), fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="middle"))

    d.add(String(pad_left + plot_w / 2.0, 4, "Day of Month", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="middle"))
    return d


def build_weekday_weekend_chart(
    comp: WeekdayWeekendComparison,
    width: float = 520,
    height: float = 110,
) -> Drawing:
    """Build a comparison chart comparing Weekday and Weekend metrics."""
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=COLOR_BG, strokeColor=COLOR_BORDER, strokeWidth=0.5, rx=4, ry=4))

    pad_left = 42.0
    pad_right = 16.0
    pad_top = 22.0
    pad_bottom = 24.0

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # Metrics to compare: [Average Daily (kWh/day), Peak Daily (kWh)]
    metrics = [
        ("Average Daily Usage (kWh/day)", comp.weekday.avg_daily_kwh, comp.weekend.avg_daily_kwh),
        ("Peak Daily Consumption (kWh)", comp.weekday.peak_daily_kwh, comp.weekend.peak_daily_kwh),
    ]

    all_vals = [m[1] for m in metrics] + [m[2] for m in metrics]
    max_val = max(all_vals) if all_vals else 1.0
    y_ceiling = math.ceil(max_val * 1.3)
    if y_ceiling <= 0:
        y_ceiling = 1.0

    # Grid
    for i in range(4):
        y_frac = i / 3.0
        y_pos = pad_bottom + y_frac * plot_h
        val_tick = y_frac * y_ceiling
        d.add(Line(pad_left, y_pos, pad_left + plot_w, y_pos, strokeColor=COLOR_GRID, strokeWidth=0.5))
        d.add(String(pad_left - 6, y_pos - 3, f"{val_tick:.1f}", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="end"))

    # Title & Legend
    d.add(String(pad_left, height - 14, "Weekday vs Weekend Consumption Metrics", fontName="Helvetica-Bold", fontSize=7, fillColor=COLOR_NAVY))
    leg_x = width - 180
    leg_y = height - 14
    d.add(Rect(leg_x, leg_y - 2, 7, 7, fillColor=COLOR_NAVY, strokeColor=None))
    d.add(String(leg_x + 10, leg_y, f"Weekdays ({comp.weekday.days_count} days)", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))
    d.add(Rect(leg_x + 85, leg_y - 2, 7, 7, fillColor=COLOR_TEAL, strokeColor=None))
    d.add(String(leg_x + 95, leg_y, f"Weekends ({comp.weekend.days_count} days)", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))

    # Draw grouped bars
    group_w = plot_w / len(metrics)
    bar_w = 34.0
    bar_gap = 6.0

    for idx, (label, wd_val, we_val) in enumerate(metrics):
        group_cx = pad_left + idx * group_w + group_w / 2.0
        wd_x = group_cx - bar_w - bar_gap / 2.0
        we_x = group_cx + bar_gap / 2.0

        wd_h = (wd_val / y_ceiling) * plot_h
        we_h = (we_val / y_ceiling) * plot_h

        d.add(Rect(wd_x, pad_bottom, bar_w, wd_h, fillColor=COLOR_NAVY, strokeColor=None))
        d.add(Rect(we_x, pad_bottom, bar_w, we_h, fillColor=COLOR_TEAL, strokeColor=None))

        # Value text above bars
        d.add(String(wd_x + bar_w / 2.0, pad_bottom + wd_h + 3, f"{wd_val:.2f}", fontName="Helvetica-Bold", fontSize=6.5, fillColor=COLOR_NAVY, textAnchor="middle"))
        d.add(String(we_x + bar_w / 2.0, pad_bottom + we_h + 3, f"{we_val:.2f}", fontName="Helvetica-Bold", fontSize=6.5, fillColor=COLOR_TEAL, textAnchor="middle"))

        # Category label under bars
        d.add(String(group_cx, pad_bottom - 11, label, fontName="Helvetica", fontSize=7, fillColor=COLOR_TEXT_MAIN, textAnchor="middle"))

    return d


def build_weekly_summary_chart(
    weekly_summary: list[CalendarWeekSummary],
    width: float = 520,
    height: float = 110,
) -> Drawing:
    """Build a weekly comparison bar chart showing totals and identifying partial weeks."""
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=COLOR_BG, strokeColor=COLOR_BORDER, strokeWidth=0.5, rx=4, ry=4))

    pad_left = 42.0
    pad_right = 16.0
    pad_top = 22.0
    pad_bottom = 24.0

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    vals = [w.total_kwh for w in weekly_summary]
    max_val = max(vals) if vals else 1.0
    y_ceiling = math.ceil(max_val * 1.3)
    if y_ceiling <= 0:
        y_ceiling = 1.0

    # Grid
    for i in range(4):
        y_frac = i / 3.0
        y_pos = pad_bottom + y_frac * plot_h
        val_tick = y_frac * y_ceiling
        d.add(Line(pad_left, y_pos, pad_left + plot_w, y_pos, strokeColor=COLOR_GRID, strokeWidth=0.5))
        d.add(String(pad_left - 6, y_pos - 3, f"{val_tick:.0f}", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED, textAnchor="end"))

    # Title & Legend
    d.add(String(pad_left, height - 14, "Total Consumption by Calendar Week (kWh)", fontName="Helvetica-Bold", fontSize=7, fillColor=COLOR_NAVY))
    leg_x = width - 170
    leg_y = height - 14
    d.add(Rect(leg_x, leg_y - 2, 7, 7, fillColor=COLOR_TEAL, strokeColor=None))
    d.add(String(leg_x + 10, leg_y, "Full Week (7 days)", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))
    d.add(Rect(leg_x + 85, leg_y - 2, 7, 7, fillColor=COLOR_PARTIAL, strokeColor=None))
    d.add(String(leg_x + 95, leg_y, "Partial Week", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MUTED))

    n_weeks = len(weekly_summary)
    slot_w = plot_w / max(n_weeks, 1)
    bar_w = min(slot_w * 0.55, 38.0)

    for idx, w in enumerate(weekly_summary):
        cx = pad_left + idx * slot_w + slot_w / 2.0
        bx = cx - bar_w / 2.0
        bh = (w.total_kwh / y_ceiling) * plot_h
        b_color = COLOR_PARTIAL if w.is_partial else COLOR_TEAL

        d.add(Rect(bx, pad_bottom, bar_w, bh, fillColor=b_color, strokeColor=None))

        # Value above bar
        d.add(String(cx, pad_bottom + bh + 3, f"{w.total_kwh:.1f}", fontName="Helvetica-Bold", fontSize=6.5, fillColor=b_color, textAnchor="middle"))

        # Week label & partial indicator
        tag = f" ({w.days_count}d)" if w.is_partial else ""
        d.add(String(cx, pad_bottom - 10, f"{w.week_label}{tag}", fontName="Helvetica", fontSize=6.5, fillColor=COLOR_TEXT_MAIN, textAnchor="middle"))

    return d


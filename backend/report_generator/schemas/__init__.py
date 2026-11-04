"""Validated request and report document contracts."""

from .input_schema import GenerateReportRequest
from .report_schema import ReportDocument

__all__ = ["GenerateReportRequest", "ReportDocument"]

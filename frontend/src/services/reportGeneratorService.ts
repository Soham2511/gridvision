import { apiClient } from './apiClient';

export interface JSONReportRequest {
  data: unknown;
  instructions?: string;
  output_formats: Array<'html' | 'pdf'>;
}

export interface JSONReportResult {
  report_id: string;
  title: string;
  status: 'complete' | 'partial';
  generated_at: string;
  html_url: string;
  pdf_url: string | null;
}

export interface ReportGeneratorHealth {
  enabled: boolean;
  provider: string;
  provider_configured: boolean;
  identity_resolver_configured: boolean;
  status: string;
}

class ReportGeneratorService {
  health() {
    return apiClient.get<ReportGeneratorHealth>('/report-generator/health');
  }

  generate(body: JSONReportRequest) {
    return apiClient.postLong<JSONReportResult>('/report-generator/generate', body, 300_000);
  }

  openReport(reportId: string, format: 'html' | 'pdf') {
    const path = `/report-generator/reports/${encodeURIComponent(reportId)}/${format}`;
    window.open(`${apiClient.getBaseUrl()}${path}`, '_blank', 'noopener,noreferrer');
  }
}

export const reportGeneratorService = new ReportGeneratorService();

# JSON report generator API

The blueprint is mounted under `/api/v1/report-generator`.

## Generate

`POST /api/v1/report-generator/generate`

```json
{
  "data": {
    "team": "North",
    "observations": [
      {"period": "2026-01", "category": "A", "value": 12},
      {"period": "2026-02", "category": "B", "value": 18}
    ]
  },
  "instructions": "Write a concise report focused on comparisons.",
  "output_formats": ["html", "pdf"]
}
```

`data` is arbitrary JSON and is not tied to the illustrative field names above.
`instructions` is optional; formats default to HTML and PDF.

Successful response (wrapper fields omitted for brevity):

```json
{
  "report_id": "<opaque-id>",
  "title": "...",
  "status": "complete",
  "generated_at": "...",
  "html_url": "/api/v1/report-generator/reports/<id>/html",
  "pdf_url": "/api/v1/report-generator/reports/<id>/pdf"
}
```

If PDF rendering fails after HTML succeeds, status is `partial` and `pdf_url` is
null. Provider or content failures return a safe error response and are recorded
as failed metadata for the authenticated owner.

## Retrieve

- `GET /api/v1/report-generator/reports/{report_id}` — metadata/status.
- `GET /api/v1/report-generator/reports/{report_id}/html` — HTML artifact.
- `GET /api/v1/report-generator/reports/{report_id}/pdf` — PDF artifact.
- `GET /api/v1/report-generator/health` — enabled/provider/identity readiness.

All report generation and retrieval routes require the trusted identity resolver
to return the same principal that owns the report. The health route exposes only
non-secret readiness booleans and provider name.

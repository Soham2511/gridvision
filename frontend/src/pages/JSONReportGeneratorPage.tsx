import React, { useEffect, useState } from 'react';
import { FileText, RefreshCw } from 'lucide-react';
import {
  reportGeneratorService,
  JSONReportResult,
  ReportGeneratorHealth,
} from '../services/reportGeneratorService';

const SAMPLE_JSON = JSON.stringify(
  {
    group: 'North',
    observations: [
      { period: '2026-01', category: 'A', value: 120 },
      { period: '2026-02', category: 'B', value: 150 },
      { period: '2026-03', category: 'A', value: 180 },
    ],
  },
  null,
  2,
);

export const JSONReportGeneratorPage: React.FC = () => {
  const [jsonText, setJsonText] = useState(SAMPLE_JSON);
  const [instructions, setInstructions] = useState('Create a concise report with supported trends and comparisons.');
  const [includePdf, setIncludePdf] = useState(true);
  const [health, setHealth] = useState<ReportGeneratorHealth | null>(null);
  const [result, setResult] = useState<JSONReportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshHealth = async () => {
    try {
      setHealth(await reportGeneratorService.health());
    } catch {
      setHealth(null);
    }
  };

  useEffect(() => { void refreshHealth(); }, []);

  const generate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setResult(null);
    let data: unknown;
    try {
      data = JSON.parse(jsonText) as unknown;
    } catch {
      setError('Enter valid JSON before generating a report.');
      return;
    }

    setBusy(true);
    try {
      const generated = await reportGeneratorService.generate({
        data,
        instructions: instructions.trim() || undefined,
        output_formats: includePdf ? ['html', 'pdf'] : ['html'],
      });
      setResult(generated);
      await refreshHealth();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Report generation failed.');
      await refreshHealth();
    } finally {
      setBusy(false);
    }
  };

  const ready = health?.enabled && health.provider_configured && health.identity_resolver_configured;

  return (
    <main style={{ display: 'grid', gap: '1rem', maxWidth: 1100, margin: '0 auto', width: '100%' }}>
      <header>
        <h1 className="gv-heading-1">JSON Report Generator</h1>
        <p className="gv-text-subtle">Submit arbitrary JSON and create a structured HTML report with optional PDF output.</p>
      </header>

      <section className="gv-card" aria-live="polite">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <strong>Service readiness</strong>
            <p className="gv-text-subtle" style={{ marginTop: '0.35rem' }}>
              {health
                ? `Provider: ${health.provider || 'none'} · ${health.enabled ? 'enabled' : 'disabled'} · ${health.provider_configured ? 'model configured' : 'model not configured'} · ${health.identity_resolver_configured ? 'identity configured' : 'trusted identity missing'}`
                : 'Backend health is unavailable.'}
            </p>
          </div>
          <button className="gv-button gv-button-secondary" type="button" onClick={() => void refreshHealth()}>
            <RefreshCw size={15} /> Check readiness
          </button>
        </div>
        {!ready && <p role="status" className="gv-text-subtle" style={{ marginTop: '0.7rem' }}>
          Generation needs the backend feature enabled, a configured report provider, and a trusted server-side identity resolver.
        </p>}
      </section>

      <form onSubmit={(event) => void generate(event)} className="gv-card" style={{ display: 'grid', gap: '1rem' }}>
        <label htmlFor="json-report-data"><strong>JSON data</strong></label>
        <textarea
          id="json-report-data"
          value={jsonText}
          onChange={(event) => setJsonText(event.target.value)}
          rows={18}
          spellCheck={false}
          aria-describedby="json-report-help"
          style={{ width: '100%', padding: '0.85rem', border: '1px solid var(--gv-border-medium)', borderRadius: '8px', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.85rem', resize: 'vertical' }}
        />
        <p id="json-report-help" className="gv-text-subtle">The payload is sent to the configured LLM provider for report writing. Do not submit sensitive data unless your provider is approved to process it.</p>

        <label htmlFor="json-report-instructions"><strong>Report instructions (optional)</strong></label>
        <textarea
          id="json-report-instructions"
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          maxLength={4000}
          rows={3}
          style={{ width: '100%', padding: '0.75rem', border: '1px solid var(--gv-border-medium)', borderRadius: '8px', resize: 'vertical' }}
        />

        <label style={{ display: 'flex', gap: '0.55rem', alignItems: 'center' }}>
          <input type="checkbox" checked={includePdf} onChange={(event) => setIncludePdf(event.target.checked)} />
          Also generate PDF
        </label>

        <div>
          <button className="gv-button gv-button-primary" type="submit" disabled={busy}>
            <FileText size={16} /> {busy ? 'Generating…' : 'Generate report'}
          </button>
        </div>
      </form>

      {error && <div role="alert" className="gv-card">{error}</div>}
      {result && <section className="gv-card" aria-live="polite" style={{ display: 'grid', gap: '0.75rem' }}>
        <h2 className="gv-heading-2">{result.title}</h2>
        <p className="gv-text-subtle">Status: {result.status} · Generated {new Date(result.generated_at).toLocaleString()}</p>
        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
          <button className="gv-button gv-button-secondary" type="button" onClick={() => reportGeneratorService.openReport(result.report_id, 'html')}>Open HTML</button>
          {result.pdf_url && <button className="gv-button gv-button-secondary" type="button" onClick={() => reportGeneratorService.openReport(result.report_id, 'pdf')}>Open PDF</button>}
        </div>
      </section>}
    </main>
  );
};

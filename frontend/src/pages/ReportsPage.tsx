import React, { useCallback, useEffect, useState } from 'react';
import { usePersona } from '../context';
import { aiLayerService, ReportRecord } from '../services/aiLayerService';
import { modelService } from '../services/modelService';

export const ReportsPage: React.FC = () => {
  const { currentPersona, activeEntity, setActiveEntity } = usePersona();
  const persona = currentPersona ?? 'household';
  const entityId = persona === 'household' || persona === 'commercial' ? activeEntity : undefined;
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [emailingReportId, setEmailingReportId] = useState<string | null>(null);
  const [emailNotice, setEmailNotice] = useState('');
  const [error, setError] = useState('');
  const [entityLoading, setEntityLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setReports((await aiLayerService.listReports(persona, entityId)).items);
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Report service is unavailable.');
    }
  }, [persona, entityId]);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (persona !== 'household') return;
    let cancelled = false;
    setEntityLoading(true);
    void modelService.getCustomerRecords(200, 0).then((page) => {
      if (cancelled) return;
      const ids = [...new Set(page.items.map((record) => record.entityId))];
      if (ids.length && !ids.includes(activeEntity)) setActiveEntity(ids[0]);
    }).catch(() => {
      if (!cancelled) setError('Household building IDs could not be loaded from the profile source.');
    }).finally(() => {
      if (!cancelled) setEntityLoading(false);
    });
    return () => { cancelled = true; };
  }, [persona, activeEntity, setActiveEntity]);

  const generate = async () => {
    setBusy(true);
    try {
      if ((persona === 'household' || persona === 'commercial') && !entityId) {
        throw new Error('Select an entity in Building Profile before generating its report.');
      }
      await aiLayerService.createReport(persona, entityId);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create report.');
    } finally {
      setBusy(false);
    }
  };

  const download = async (reportId: string, format: 'html' | 'pdf') => {
    try {
      const blob = await aiLayerService.downloadReport(reportId, format, persona, entityId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `gridvision-report-${reportId}.${format}`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Report download failed.');
    }
  };

  const emailReport = async (reportId: string) => {
    setEmailingReportId(reportId);
    setEmailNotice('');
    setError('');
    try {
      const result = await aiLayerService.emailReport(reportId, persona, entityId);
      setEmailNotice(`Report emailed to ${result.recipient}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Report email could not be sent.');
    } finally {
      setEmailingReportId(null);
    }
  };

  return (
    <main style={{ display: 'grid', gap: '1rem', maxWidth: 1000, margin: '0 auto', width: '100%' }}>
      <header>
        <h1 className="gv-heading-1">Reports</h1>
        <p className="gv-text-subtle">{persona === 'government' ? 'Government reports are regional aggregates.' : `Reports use the selected ${persona === 'household' ? 'household Silver OBJECTID' : 'commercial Silver OBJECTID'} from Building Profile.`} Monthly summaries use that entity’s latest available Silver month. Emails continue to the same configured recipient.</p>
      </header>
      <section className="gv-card">
        <h2 className="gv-heading-2">{persona === 'government' ? 'Government analytics' : 'Consumption summary'}</h2>
        <p>The retrieval agent fetches the latest household Silver month or previous commercial month, then the report agent creates a summary.</p>
        {entityId && <p className="gv-text-subtle">Selected entity: {entityId}. Email delivery uses the shared configured recipient.</p>}
        <button className="gv-button gv-button-primary" type="button" onClick={() => void generate()} disabled={busy || entityLoading}>{entityLoading ? 'Loading selected user…' : busy ? 'Preparing…' : 'Generate report'}</button>
      </section>
      {error && <div role="alert" className="gv-card">{error}</div>}
      {emailNotice && <div role="status" className="gv-card">{emailNotice}</div>}
      <section style={{ display: 'grid', gap: '0.75rem' }} aria-label="Saved reports">
        {reports.map((report) => (
          <article key={report.report_id} className="gv-card" style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <div><strong>{report.report_type.replace(/_/g, ' ')}</strong><div className="gv-text-subtle">{report.payload?.metadata?.entityId ? `Entity ${report.payload.metadata.entityId} · ` : ''}{report.payload?.metadata?.period && typeof report.payload.metadata.period === 'object' ? `${report.payload.metadata.period.start} – ${report.payload.metadata.period.end}` : new Date(report.created_at).toLocaleString()}</div></div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="gv-button gv-button-secondary" type="button" onClick={() => void download(report.report_id, 'html')}>HTML</button>
              {report.payload?.pdfArtifactId && <button className="gv-button gv-button-secondary" type="button" onClick={() => void download(report.report_id, 'pdf')}>PDF</button>}
              <button className="gv-button gv-button-secondary" type="button" onClick={() => void emailReport(report.report_id)} disabled={emailingReportId !== null}>
                {emailingReportId === report.report_id ? 'Sending…' : 'Email report'}
              </button>
            </div>
          </article>
        ))}
        {reports.length === 0 && <div className="gv-card">No saved reports in this demo context.</div>}
      </section>
    </main>
  );
};

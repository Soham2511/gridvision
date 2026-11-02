import React from 'react';

type JsonRecord = Record<string, unknown>;

const asRecord = (value: unknown): JsonRecord =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};

const finiteNumber = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

const formatRate = (value: unknown): string => {
  const parsed = finiteNumber(value);
  return parsed === null ? '—' : `${(parsed * 100).toFixed(1)}%`;
};

const formatNumber = (value: unknown, digits = 3): string => {
  const parsed = finiteNumber(value);
  return parsed === null ? '—' : parsed.toLocaleString(undefined, { maximumFractionDigits: digits });
};

const metricCardStyle: React.CSSProperties = {
  border: '1px solid var(--gv-border-subtle)',
  borderRadius: 'var(--gv-radius-md)',
  padding: '0.75rem',
  background: 'var(--gv-bg-surface)',
};

const EvaluationCard: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={metricCardStyle}>
    <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--gv-text-muted)', textTransform: 'uppercase' }}>
      {label}
    </span>
    <strong style={{ display: 'block', marginTop: 4, color: 'var(--gv-text-primary)' }}>{value}</strong>
  </div>
);

interface EvaluationMetricsProps {
  metrics: Record<string, unknown>;
}

export const EvaluationMetrics: React.FC<EvaluationMetricsProps> = ({ metrics }) => {
  const outer = asRecord(metrics);
  const root = asRecord(outer.metrics);
  const evaluation = Object.keys(root).length ? root : outer;
  const detection = asRecord(evaluation.test_detection);
  const classification = asRecord(
    evaluation.test_classification ?? evaluation.validation_classification,
  );
  const localization = asRecord(evaluation.spatial_event_localization);
  const hasMetrics = Object.keys(evaluation).length > 0;

  if (!hasMetrics) {
    return <p className="gv-text-subtle">No saved evaluation metrics are present for this model.</p>;
  }

  return (
    <div style={{ display: 'grid', gap: '1rem' }}>
      <section aria-label="Detection evaluation metrics">
        <h3 className="gv-heading-3" style={{ marginBottom: '0.55rem' }}>Test detection</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(135px, 1fr))', gap: '0.5rem' }}>
          {[
            ['Precision', formatRate(detection.precision)],
            ['Recall', formatRate(detection.recall)],
            ['F1', formatRate(detection.f1)],
            ['PR-AUC', formatRate(detection.pr_auc)],
            ['False alerts / customer', formatNumber(detection.false_alerts_per_customer, 2)],
            ['Event precision', formatRate(detection.event_precision)],
            ['Event recall', formatRate(detection.event_recall)],
            ['Detection delay', finiteNumber(detection.event_detection_delay_hours) === null ? '—' : `${formatNumber(detection.event_detection_delay_hours, 2)} hr`],
            ['Classification macro-F1', formatRate(classification.macro_f1)],
          ].map(([label, value]) => <EvaluationCard key={label} label={label} value={value} />)}
        </div>
      </section>

      <section aria-label="Spatial event localization evaluation">
        <h3 className="gv-heading-3" style={{ marginBottom: '0.55rem' }}>Spatial event localization</h3>
        {!Object.keys(localization).length ? (
          <p className="gv-text-subtle">Event localization evaluation metrics are not available.</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(135px, 1fr))', gap: '0.5rem' }}>
            {[
              ['Event precision', formatRate(localization.event_precision)],
              ['Event recall', formatRate(localization.event_recall)],
              ['Event F1', formatRate(localization.event_f1)],
              ['Detection delay', finiteNumber(localization.event_detection_delay_hours) === null ? '—' : `${formatNumber(localization.event_detection_delay_hours, 2)} hr`],
              ['Matched events', formatNumber(localization.matched_events, 0)],
              ['False events', formatNumber(localization.false_events, 0)],
              ['Missed events', formatNumber(localization.missed_events, 0)],
            ].map(([label, value]) => <EvaluationCard key={label} label={label} value={value} />)}
          </div>
        )}
      </section>
    </div>
  );
};

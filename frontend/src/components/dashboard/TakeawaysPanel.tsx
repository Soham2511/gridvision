import React from 'react';
import { Lightbulb } from 'lucide-react';
import { BusinessInsight } from '../../types/analytics';
import { InsightCard } from '../common/InsightCard';

interface TakeawaysPanelProps {
  insights: BusinessInsight[];
  onActionClick?: (id: string) => void;
}

export const TakeawaysPanel: React.FC<TakeawaysPanelProps> = ({ insights, onActionClick }) => {
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <Lightbulb size={20} color="var(--gv-color-smart-teal)" />
            <h3 className="gv-heading-2">Actionable Business Insights & Optimization</h3>
          </div>
          <p className="gv-text-muted" style={{ marginTop: '0.2rem' }}>
            Algorithmic recommendations derived from forecasting, peak prediction, and segment analytics
          </p>
        </div>
        <span className="gv-badge gv-badge-neutral">
          {insights.length} High-Impact Takeaways
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1.25rem',
        }}
      >
        {insights.map((insight) => (
          <InsightCard key={insight.id} insight={insight} onActionClick={onActionClick} />
        ))}
      </div>
    </div>
  );
};

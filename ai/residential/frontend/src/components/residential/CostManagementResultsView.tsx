import React, { useState } from 'react';
import { CostManagementResult, CostSavingStrategy } from '../../types/residentialFeatures';
import {
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Package,
  ArrowRight,
} from 'lucide-react';

interface CostManagementResultsViewProps {
  result: CostManagementResult;
  onAskFollowUp?: (prompt: string) => void;
  onEditInputs?: () => void;
}

export const CostManagementResultsView: React.FC<CostManagementResultsViewProps> = ({
  result,
  onAskFollowUp,
  onEditInputs,
}) => {
  const [showAudit, setShowAudit] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const data: CostManagementResult = (result as any)?.results || result;

  if (!data || !data.package_recommendations) {
    return (
      <div style={{ padding: '2.5rem', textAlign: 'center', backgroundColor: '#FFFFFF', borderRadius: '12px', border: '1px solid #E2E8F0' }}>
        <p style={{ color: '#EF4444', fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>
          Unable to display cost management recommendations. Unexpected response structure.
        </p>
        {onEditInputs && (
          <button
            type="button"
            onClick={onEditInputs}
            style={{ marginTop: '1rem', padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid #CBD5E1', cursor: 'pointer' }}
          >
            Return to Specifications
          </button>
        )}
      </div>
    );
  }

  const categories = [
    { id: 'all', label: 'All Strategies' },
    { id: 'zero_cost_behavioral', label: 'Zero-Cost Behavioral' },
    { id: 'low_cost_quick_win', label: 'Low-Cost Quick Wins' },
    { id: 'appliance_upgrade', label: 'Appliance Upgrades' },
    { id: 'rooftop_solar', label: 'Rooftop Solar' },
  ];

  const filteredStrategies = selectedCategory === 'all'
    ? data.strategies
    : data.strategies.filter((s) => s.category === selectedCategory);

  const getCategoryBadge = (cat: CostSavingStrategy['category']) => {
    switch (cat) {
      case 'zero_cost_behavioral':
        return { label: 'Zero-Cost Behavioral', bg: '#DCFCE7', text: '#166534' };
      case 'low_cost_quick_win':
        return { label: 'Low-Cost Quick Win', bg: '#EFF6FF', text: '#1E40AF' };
      case 'appliance_upgrade':
        return { label: 'Appliance Upgrade', bg: '#FEF3C7', text: '#92400E' };
      case 'rooftop_solar':
        return { label: 'Rooftop Solar PV', bg: '#FEE2E2', text: '#991B1B' };
      default:
        return { label: cat, bg: '#F1F5F9', text: '#475569' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1rem 1.25rem',
        }}
      >
        <div>
          <span
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: '#10B981',
              backgroundColor: '#ECFDF5',
              padding: '2px 8px',
              borderRadius: '4px',
            }}
          >
            Telemetry-Grounded Savings Plan
          </span>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0B1F33', margin: '0.35rem 0 0 0' }}>
            Personalized Energy Cost Management
          </h2>
        </div>

        {onEditInputs && (
          <button
            type="button"
            onClick={onEditInputs}
            style={{
              padding: '0.45rem 0.85rem',
              borderRadius: '6px',
              border: '1px solid #CBD5E1',
              backgroundColor: '#F8FAFC',
              fontSize: '0.8rem',
              fontWeight: 600,
              color: '#334155',
              cursor: 'pointer',
            }}
          >
            Adjust Budget & Scope
          </button>
        )}
      </div>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0.85rem' }}>
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '10px',
            border: '1px solid #E2E8F0',
            padding: '1rem',
            borderTop: '3px solid #64748B',
          }}
        >
          <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>
            Current Baseline Bill
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0B1F33', marginTop: '0.25rem' }}>
            ₹{Math.round(data.current_monthly_bill_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            {Math.round(data.current_monthly_baseline_kwh)} kWh/month verified
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '10px',
            border: '1px solid #E2E8F0',
            padding: '1rem',
            borderTop: '3px solid #10B981',
          }}
        >
          <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>
            Achievable Monthly Savings
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10B981', marginTop: '0.25rem' }}>
            ₹{Math.round(data.achievable_monthly_savings_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            ₹{Math.round(data.achievable_annual_savings_inr).toLocaleString('en-IN')} / year
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '10px',
            border: '1px solid #E2E8F0',
            padding: '1rem',
            borderTop: '3px solid #087EBD',
          }}
        >
          <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>
            Total Investment Required
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#087EBD', marginTop: '0.25rem' }}>
            ₹{Math.round(data.total_investment_required_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            Across all recommended actions
          </div>
        </div>

        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '10px',
            border: '1px solid #E2E8F0',
            padding: '1rem',
            borderTop: '3px solid #F59E0B',
          }}
        >
          <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>
            Blended Payback
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#D97706', marginTop: '0.25rem' }}>
            {data.blended_payback_years !== undefined ? `${data.blended_payback_years} yrs` : 'Immediate'}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            Weighted capital recovery
          </div>
        </div>
      </div>

      {/* Recommended Package Card */}
      {data.package_recommendations && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '2px solid #00B8A9',
            padding: '1.25rem',
            boxShadow: '0 2px 8px rgba(0, 184, 169, 0.1)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Package size={20} color="#00B8A9" />
              <span style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33' }}>
                {data.package_recommendations.packageName}
              </span>
            </div>
            <div
              style={{
                backgroundColor: '#DCFCE7',
                color: '#15803D',
                fontWeight: 700,
                fontSize: '0.78rem',
                padding: '3px 8px',
                borderRadius: '6px',
              }}
            >
              Cuts bill by {data.package_recommendations.estimatedBillReductionPct}%
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.85rem', marginTop: '0.75rem' }}>
            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>Package Upfront Cost</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0F172A' }}>
                ₹{Math.round(data.package_recommendations.totalUpfrontCostInr).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>Monthly Bill Reduction</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#10B981' }}>
                ₹{Math.round(data.package_recommendations.monthlySavingsInr).toLocaleString('en-IN')} / mo
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>Annual Bill Reduction</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#10B981' }}>
                ₹{Math.round(data.package_recommendations.annualSavingsInr).toLocaleString('en-IN')} / yr
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>Blended Payback</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#087EBD' }}>
                {data.package_recommendations.blendedPaybackYears ? `${data.package_recommendations.blendedPaybackYears} yrs` : 'Instant'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Strategies Filter & List */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0B1F33', margin: 0 }}>
            Ranked Cost-Saving Action Strategies ({filteredStrategies.length})
          </h3>
          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
            {categories.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setSelectedCategory(c.id)}
                style={{
                  padding: '0.35rem 0.65rem',
                  borderRadius: '6px',
                  border: selectedCategory === c.id ? '2px solid #00B8A9' : '1px solid #CBD5E1',
                  backgroundColor: selectedCategory === c.id ? '#E0F7F5' : '#FFFFFF',
                  color: selectedCategory === c.id ? '#00A396' : '#64748B',
                  fontSize: '0.72rem',
                  fontWeight: selectedCategory === c.id ? 700 : 500,
                  cursor: 'pointer',
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {filteredStrategies.map((strat) => {
            const badge = getCategoryBadge(strat.category);
            return (
              <div
                key={strat.strategy_id}
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '10px',
                  border: '1px solid #E2E8F0',
                  padding: '1rem 1.15rem',
                  boxShadow: '0 1px 2px rgba(11, 31, 51, 0.04)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span
                      style={{
                        width: '22px',
                        height: '22px',
                        borderRadius: '50%',
                        backgroundColor: '#F1F5F9',
                        color: '#475569',
                        fontSize: '0.72rem',
                        fontWeight: 800,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      #{strat.priority_rank}
                    </span>
                    <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A' }}>
                      {strat.title}
                    </span>
                  </div>

                  <span
                    style={{
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      backgroundColor: badge.bg,
                      color: badge.text,
                      padding: '2px 8px',
                      borderRadius: '4px',
                    }}
                  >
                    {badge.label}
                  </span>
                </div>

                <p style={{ fontSize: '0.78rem', color: '#475569', margin: '0 0 0.6rem 0', lineHeight: 1.45 }}>
                  {strat.description}
                </p>

                {/* Metrics Row */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1.25rem',
                    backgroundColor: '#F8FAFC',
                    padding: '0.6rem 0.85rem',
                    borderRadius: '6px',
                    fontSize: '0.75rem',
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <span style={{ color: '#64748B' }}>Monthly Savings: </span>
                    <span style={{ fontWeight: 700, color: '#10B981' }}>
                      ₹{Math.round(strat.estimated_monthly_savings_inr).toLocaleString('en-IN')}
                    </span>
                    <span style={{ color: '#64748B' }}> ({Math.round(strat.estimated_monthly_savings_kwh)} kWh)</span>
                  </div>

                  <div>
                    <span style={{ color: '#64748B' }}>Upfront Investment: </span>
                    <span style={{ fontWeight: 700, color: '#0F172A' }}>
                      ₹{Math.round(strat.upfront_investment_inr).toLocaleString('en-IN')}
                    </span>
                  </div>

                  <div>
                    <span style={{ color: '#64748B' }}>Payback: </span>
                    <span style={{ fontWeight: 700, color: '#087EBD' }}>
                      {strat.simple_payback_months ? `${strat.simple_payback_months} months` : 'Immediate'}
                    </span>
                  </div>
                </div>

                {/* Action Steps */}
                <div style={{ marginTop: '0.6rem' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#64748B', marginBottom: '0.25rem' }}>
                    Action Plan:
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.76rem', color: '#334155', lineHeight: 1.5 }}>
                    {strat.action_steps.map((step, idx) => (
                      <li key={idx}>{step}</li>
                    ))}
                  </ul>
                </div>

                {/* Evidence footnote */}
                <div style={{ marginTop: '0.5rem', fontSize: '0.68rem', color: '#64748B', fontStyle: 'italic' }}>
                  Supporting evidence: {strat.supporting_evidence}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Audit Trail */}
      <div
        style={{
          backgroundColor: '#F8FAFC',
          borderRadius: '10px',
          border: '1px solid #E2E8F0',
          padding: '0.85rem 1.15rem',
        }}
      >
        <button
          type="button"
          onClick={() => setShowAudit(!showAudit)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <ShieldCheck size={16} color="#00B8A9" />
            <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#334155' }}>
              Calculation Audit Trail & Telemetry Provenance
            </span>
          </div>
          {showAudit ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        {showAudit && (
          <div style={{ marginTop: '0.85rem', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.74rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#E2E8F0', color: '#334155', textAlign: 'left' }}>
                  <th style={{ padding: '0.4rem' }}>Metric</th>
                  <th style={{ padding: '0.4rem' }}>Calculated Value</th>
                  <th style={{ padding: '0.4rem' }}>Provenance</th>
                  <th style={{ padding: '0.4rem' }}>Methodology</th>
                </tr>
              </thead>
              <tbody>
                {data.audit_trail.map((item, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #CBD5E1' }}>
                    <td style={{ padding: '0.4rem', fontWeight: 600 }}>{item.metric_name}</td>
                    <td style={{ padding: '0.4rem' }}>{String(item.value)} {item.unit || ''}</td>
                    <td style={{ padding: '0.4rem', color: '#087EBD' }}>{item.provenance}</td>
                    <td style={{ padding: '0.4rem' }}>{item.methodology}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Ask Assistant follow-up strip */}
      {onAskFollowUp && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#EFF6FF',
            borderRadius: '10px',
            border: '1px solid #BFDBFE',
            padding: '0.85rem 1.15rem',
          }}
        >
          <span style={{ fontSize: '0.82rem', color: '#1E40AF', fontWeight: 600 }}>
            Want assistance scheduling your appliance upgrade or setting up an implementation roadmap?
          </span>
          <button
            type="button"
            onClick={() => onAskFollowUp(`Please summarize how I can execute the ${data.package_recommendations.packageName} (saving ₹${Math.round(data.package_recommendations.monthlySavingsInr)}/month with ₹${Math.round(data.package_recommendations.totalUpfrontCostInr)} investment). What is my highest priority step?`)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.45rem 0.85rem',
              borderRadius: '6px',
              backgroundColor: '#2563EB',
              color: '#FFFFFF',
              fontSize: '0.78rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <span>Ask Assistant in Chat</span>
            <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};

import React, { useState } from 'react';
import { ApplianceScenarioResult } from '../../types/residentialFeatures';
import {
  TrendingDown,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Leaf,
  ArrowRight,
} from 'lucide-react';

interface ApplianceAnalysisResultsViewProps {
  result: ApplianceScenarioResult;
  onAskFollowUp?: (prompt: string) => void;
  onEditInputs?: () => void;
}

export const ApplianceAnalysisResultsView: React.FC<ApplianceAnalysisResultsViewProps> = ({
  result,
  onAskFollowUp,
  onEditInputs,
}) => {
  const [showAudit, setShowAudit] = useState(false);
  const data: ApplianceScenarioResult = (result as any)?.results || result;

  if (!data || !data.recommendation_verdict) {
    return (
      <div style={{ padding: '2.5rem', textAlign: 'center', backgroundColor: '#FFFFFF', borderRadius: '12px', border: '1px solid #E2E8F0' }}>
        <p style={{ color: '#EF4444', fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>
          Unable to display appliance scenario analysis. Unexpected response structure.
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
              color: '#D97706',
              backgroundColor: '#FEF3C7',
              padding: '2px 8px',
              borderRadius: '4px',
            }}
          >
            Lifecycle Economics Verified
          </span>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0B1F33', margin: '0.35rem 0 0 0' }}>
            Appliance Lifecycle & Upgrade Assessment
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
            Edit Parameters
          </button>
        )}
      </div>

      {/* Recommendation Verdict Card */}
      <div
        style={{
          backgroundColor: '#F0FDF4',
          borderRadius: '10px',
          border: '1px solid #BBF7D0',
          padding: '1rem 1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              backgroundColor: '#10B981',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#FFFFFF',
            }}
          >
            <TrendingDown size={18} />
          </div>
          <div>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: '#166534' }}>
              Financial Verdict
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#14532D' }}>
              {data.recommendation_verdict}
            </div>
          </div>
        </div>

        {data.co2_reduction_kg_per_year > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              backgroundColor: '#DCFCE7',
              padding: '0.35rem 0.75rem',
              borderRadius: '999px',
              fontSize: '0.78rem',
              fontWeight: 700,
              color: '#15803D',
            }}
          >
            <Leaf size={14} color="#15803D" />
            <span>Reduces {data.co2_reduction_kg_per_year.toFixed(1)} kg CO₂ / year</span>
          </div>
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
            borderTop: '3px solid #00B8A9',
          }}
        >
          <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>
            Net Upfront Outlay
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0B1F33', marginTop: '0.25rem' }}>
            ₹{Math.round(data.net_upfront_investment_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            Price minus resale value
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
            Annual Bill Savings
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10B981', marginTop: '0.25rem' }}>
            ₹{Math.round(data.annual_cost_savings_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            {Math.round(data.annual_energy_savings_kwh)} kWh/year saved
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
            Simple Payback
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#087EBD', marginTop: '0.25rem' }}>
            {data.simple_payback_years !== undefined ? `${data.simple_payback_years} yrs` : 'Instant'}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            {data.break_even_year ? `Break-even: Year ${data.break_even_year}` : 'Immediate savings'}
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
            Net 7-Yr Savings
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#D97706', marginTop: '0.25rem' }}>
            ₹{Math.round(data.net_lifetime_savings_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            Over total ownership period
          </div>
        </div>
      </div>

      {/* 7-Year Cumulative Cash Flow Table */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1.25rem',
        }}
      >
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0B1F33', margin: '0 0 0.85rem 0' }}>
          7-Year Operating Cost & Cumulative Savings Trajectory
        </h3>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ backgroundColor: '#F8FAFC', color: '#475569', textAlign: 'left', borderBottom: '1px solid #E2E8F0' }}>
                <th style={{ padding: '0.6rem' }}>Year</th>
                <th style={{ padding: '0.6rem' }}>Baseline Operating (₹)</th>
                <th style={{ padding: '0.6rem' }}>Proposed Operating (₹)</th>
                <th style={{ padding: '0.6rem' }}>Annual Savings (₹)</th>
                <th style={{ padding: '0.6rem' }}>Cumulative Net Cashflow (₹)</th>
              </tr>
            </thead>
            <tbody>
              {data.cashflows.map((cf) => (
                <tr key={cf.year} style={{ borderBottom: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '0.6rem', fontWeight: 700 }}>Year {cf.year}</td>
                  <td style={{ padding: '0.6rem' }}>₹{Math.round(cf.baseline_operating_cost_inr).toLocaleString('en-IN')}</td>
                  <td style={{ padding: '0.6rem' }}>₹{Math.round(cf.proposed_operating_cost_inr).toLocaleString('en-IN')}</td>
                  <td style={{ padding: '0.6rem', color: '#10B981', fontWeight: 600 }}>
                    +₹{Math.round(cf.annual_savings_inr).toLocaleString('en-IN')}
                  </td>
                  <td
                    style={{
                      padding: '0.6rem',
                      fontWeight: 700,
                      color: cf.cumulative_net_savings_inr >= 0 ? '#10B981' : '#EF4444',
                    }}
                  >
                    {cf.cumulative_net_savings_inr >= 0 ? '+' : ''}
                    ₹{Math.round(cf.cumulative_net_savings_inr).toLocaleString('en-IN')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sensitivity Scenarios */}
      {data.sensitivity_scenarios && data.sensitivity_scenarios.length > 0 && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
          }}
        >
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0B1F33', margin: '0 0 0.85rem 0' }}>
            Usage Sensitivity Scenarios
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
            {data.sensitivity_scenarios.map((sc, i) => (
              <div
                key={i}
                style={{
                  backgroundColor: '#F8FAFC',
                  borderRadius: '8px',
                  border: '1px solid #E2E8F0',
                  padding: '0.85rem',
                }}
              >
                <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#0F172A' }}>{sc.scenarioName}</div>
                <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.15rem' }}>
                  {sc.dailyHours} hours daily runtime
                </div>
                <div style={{ fontSize: '1rem', fontWeight: 800, color: '#10B981', marginTop: '0.4rem' }}>
                  ₹{Math.round(sc.annualSavingsInr).toLocaleString('en-IN')}/yr
                </div>
                <div style={{ fontSize: '0.72rem', color: '#475569', marginTop: '0.15rem' }}>
                  Payback: {sc.paybackYears ? `${sc.paybackYears} yrs` : 'Instant'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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
              Engineering Calculation Audit Trail (BEE & CEA Emission Factor)
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
                  <th style={{ padding: '0.4rem' }}>Engineering Standard</th>
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

      {/* Chat follow-up prompt strip */}
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
            Have questions about specific model brands, seasonal usage variations, or financing options?
          </span>
          <button
            type="button"
            onClick={() => onAskFollowUp(`Please summarize the appliance scenario economics: Net outlay ₹${Math.round(data.net_upfront_investment_inr)}, saving ₹${Math.round(data.annual_cost_savings_inr)}/yr, payback ${data.simple_payback_years || 'N/A'} yrs. What are your tips for maximizing efficiency?`)}
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

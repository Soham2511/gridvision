import React, { useState } from 'react';
import { HouseEnergyPlanningResult } from '../../types/residentialFeatures';
import {
  Sun,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Layers,
  ArrowRight,
} from 'lucide-react';

interface HousePlanningResultsViewProps {
  result: HouseEnergyPlanningResult;
  onAskFollowUp?: (prompt: string) => void;
  onEditInputs?: () => void;
}

export const HousePlanningResultsView: React.FC<HousePlanningResultsViewProps> = ({
  result,
  onAskFollowUp,
  onEditInputs,
}) => {
  const [showAudit, setShowAudit] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);

  const data: HouseEnergyPlanningResult = (result as any)?.results || result;
  const plan = data?.recommended_plan;

  if (!data || !plan) {
    return (
      <div style={{ padding: '2.5rem', textAlign: 'center', backgroundColor: '#FFFFFF', borderRadius: '12px', border: '1px solid #E2E8F0' }}>
        <p style={{ color: '#EF4444', fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>
          Unable to display house energy plan. The calculation returned an unexpected response structure.
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
      {/* Top Banner / Actions */}
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
              color: '#087EBD',
              backgroundColor: '#EFF6FF',
              padding: '2px 8px',
              borderRadius: '4px',
            }}
          >
            Engineering Plan Verified
          </span>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0B1F33', margin: '0.35rem 0 0 0' }}>
            New House Energy & Electrical Sizing
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
            Edit Specifications
          </button>
        )}
      </div>

      {/* KPI Cards Row */}
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
            Connected Load
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0B1F33', marginTop: '0.25rem' }}>
            {data.preliminary_connected_load_kw.toFixed(2)} <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>kW</span>
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            Sum of all planned circuits
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
            Diversified Peak Demand
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#087EBD', marginTop: '0.25rem' }}>
            {data.diversified_maximum_demand_kw.toFixed(2)} <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>kW</span>
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            IS 732 residential factor (0.65)
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
            Monthly Consumption
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10B981', marginTop: '0.25rem' }}>
            {Math.round(plan.estimated_monthly_consumption_kwh)} <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>kWh</span>
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            ≈ ₹{Math.round(plan.estimated_monthly_bill_inr).toLocaleString('en-IN')}/mo at ₹10/kWh
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
            Equipment Investment
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#D97706', marginTop: '0.25rem' }}>
            ₹{Math.round(plan.total_equipment_cost_inr).toLocaleString('en-IN')}
          </div>
          <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
            {plan.tier_name} schedule budget
          </div>
        </div>
      </div>

      {/* Recommended Plan Tier Card */}
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
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                color: '#FFFFFF',
                backgroundColor: '#00B8A9',
                padding: '3px 8px',
                borderRadius: '4px',
              }}
            >
              RECOMMENDED TIER
            </span>
            <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#0B1F33' }}>
              {plan.tier_name}
            </span>
          </div>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#00A396' }}>
            {plan.tagline}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem', margin: '1rem 0' }}>
          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#475569', marginBottom: '0.4rem' }}>
              Key Tier Highlights:
            </div>
            <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.82rem', color: '#334155', lineHeight: 1.6 }}>
              {plan.key_features.map((feat, idx) => (
                <li key={idx}>{feat}</li>
              ))}
            </ul>
          </div>

          <div
            style={{
              backgroundColor: '#F8FAFC',
              borderRadius: '8px',
              padding: '0.85rem',
              border: '1px solid #E2E8F0',
            }}
          >
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#475569', marginBottom: '0.5rem' }}>
              Efficiency Economics:
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', padding: '0.2rem 0' }}>
              <span style={{ color: '#64748B' }}>Annual Electricity Bill:</span>
              <span style={{ fontWeight: 700, color: '#0F172A' }}>₹{Math.round(plan.estimated_annual_bill_inr).toLocaleString('en-IN')}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', padding: '0.2rem 0' }}>
              <span style={{ color: '#64748B' }}>Efficiency Savings vs Baseline:</span>
              <span style={{ fontWeight: 700, color: '#10B981' }}>{plan.energy_savings_vs_standard_pct}% Less Energy</span>
            </div>
            {plan.solar_pv_kwp && plan.solar_pv_kwp > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', padding: '0.2rem 0' }}>
                <span style={{ color: '#64748B' }}>Net Monthly Bill (Post Solar):</span>
                <span style={{ fontWeight: 700, color: '#087EBD' }}>
                  ₹{Math.round(plan.net_monthly_bill_inr || 0).toLocaleString('en-IN')}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Equipment Schedule Toggle */}
        <button
          type="button"
          onClick={() => setShowSchedule(!showSchedule)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.5rem 0.85rem',
            borderRadius: '6px',
            border: '1px solid #CBD5E1',
            backgroundColor: '#FFFFFF',
            fontSize: '0.8rem',
            fontWeight: 600,
            color: '#334155',
            cursor: 'pointer',
          }}
        >
          <Layers size={14} />
          <span>{showSchedule ? 'Hide Equipment Schedule' : `View Full Equipment Schedule (${plan.equipment_schedule.length} items)`}</span>
          {showSchedule ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {showSchedule && (
          <div style={{ marginTop: '0.85rem', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#F1F5F9', color: '#475569', textAlign: 'left' }}>
                  <th style={{ padding: '0.5rem' }}>Item</th>
                  <th style={{ padding: '0.5rem' }}>Qty</th>
                  <th style={{ padding: '0.5rem' }}>Power (W)</th>
                  <th style={{ padding: '0.5rem' }}>Efficiency</th>
                  <th style={{ padding: '0.5rem' }}>Daily Hrs</th>
                  <th style={{ padding: '0.5rem' }}>Monthly kWh</th>
                  <th style={{ padding: '0.5rem' }}>Cost (₹)</th>
                </tr>
              </thead>
              <tbody>
                {plan.equipment_schedule.map((eq, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #E2E8F0' }}>
                    <td style={{ padding: '0.5rem', fontWeight: 600 }}>{eq.item_name}</td>
                    <td style={{ padding: '0.5rem' }}>{eq.quantity}</td>
                    <td style={{ padding: '0.5rem' }}>{eq.rated_power_w} W</td>
                    <td style={{ padding: '0.5rem' }}>{eq.efficiency_standard}</td>
                    <td style={{ padding: '0.5rem' }}>{eq.estimated_daily_hours} hrs</td>
                    <td style={{ padding: '0.5rem' }}>{Math.round(eq.estimated_monthly_kwh)} kWh</td>
                    <td style={{ padding: '0.5rem', fontWeight: 600 }}>₹{Math.round(eq.total_cost_inr).toLocaleString('en-IN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Alternative Plans Comparison */}
      {data.alternative_plans && data.alternative_plans.length > 0 && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
          }}
        >
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0B1F33', margin: '0 0 0.85rem 0' }}>
            Alternative Energy Tiers Comparison
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#F8FAFC', color: '#475569', textAlign: 'left', borderBottom: '1px solid #E2E8F0' }}>
                  <th style={{ padding: '0.6rem' }}>Tier</th>
                  <th style={{ padding: '0.6rem' }}>Equipment Cost</th>
                  <th style={{ padding: '0.6rem' }}>Peak Demand</th>
                  <th style={{ padding: '0.6rem' }}>Monthly kWh</th>
                  <th style={{ padding: '0.6rem' }}>Monthly Bill</th>
                  <th style={{ padding: '0.6rem' }}>Efficiency Gain</th>
                </tr>
              </thead>
              <tbody>
                {[plan, ...data.alternative_plans].map((tier, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: '1px solid #F1F5F9',
                      backgroundColor: tier.tier_name === plan.tier_name ? '#F0FDF4' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '0.6rem', fontWeight: 700, color: '#0B1F33' }}>
                      {tier.tier_name}
                      {tier.tier_name === plan.tier_name && (
                        <span style={{ marginLeft: '6px', fontSize: '0.65rem', color: '#00A396', fontWeight: 800 }}>
                          (RECOMMENDED)
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '0.6rem' }}>₹{Math.round(tier.total_equipment_cost_inr).toLocaleString('en-IN')}</td>
                    <td style={{ padding: '0.6rem' }}>{tier.diversified_peak_demand_kw.toFixed(2)} kW</td>
                    <td style={{ padding: '0.6rem' }}>{Math.round(tier.estimated_monthly_consumption_kwh)} kWh</td>
                    <td style={{ padding: '0.6rem', fontWeight: 700 }}>₹{Math.round(tier.estimated_monthly_bill_inr).toLocaleString('en-IN')}</td>
                    <td style={{ padding: '0.6rem', color: '#10B981', fontWeight: 600 }}>{tier.energy_savings_vs_standard_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rooftop Solar PV Analysis (if present) */}
      {data.solar_potential_analysis && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
            borderLeft: '4px solid #F59E0B',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.85rem' }}>
            <Sun size={20} color="#F59E0B" />
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0B1F33', margin: 0 }}>
              Rooftop Solar PV Feasibility (MNRE Guidelines)
            </h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
            <div style={{ backgroundColor: '#FFFBEB', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#B45309', fontWeight: 600 }}>System Size</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#78350F' }}>
                {data.solar_potential_analysis.recommendedSystemKwp} kWp
              </div>
              <div style={{ fontSize: '0.68rem', color: '#92400E' }}>
                On {data.solar_potential_analysis.rooftopAreaAvailableM2} m² area
              </div>
            </div>

            <div style={{ backgroundColor: '#FFFBEB', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#B45309', fontWeight: 600 }}>Monthly Generation</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#78350F' }}>
                {data.solar_potential_analysis.estimatedMonthlyGenerationKwh} kWh
              </div>
              <div style={{ fontSize: '0.68rem', color: '#92400E' }}>4.0 peak sun hours/day</div>
            </div>

            <div style={{ backgroundColor: '#FFFBEB', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#B45309', fontWeight: 600 }}>Net Investment</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#78350F' }}>
                ₹{Math.round(data.solar_potential_analysis.netInvestmentInr).toLocaleString('en-IN')}
              </div>
              <div style={{ fontSize: '0.68rem', color: '#92400E' }}>
                Gross ₹{Math.round(data.solar_potential_analysis.estimatedGrossCostInr).toLocaleString('en-IN')} - Subsidy ₹{Math.round(data.solar_potential_analysis.mnreEstimatedSubsidyInr).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ backgroundColor: '#FFFBEB', padding: '0.75rem', borderRadius: '8px' }}>
              <div style={{ fontSize: '0.7rem', color: '#B45309', fontWeight: 600 }}>Simple Payback</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#78350F' }}>
                {data.solar_potential_analysis.simplePaybackYears ? `${data.solar_potential_analysis.simplePaybackYears} yrs` : 'N/A'}
              </div>
              <div style={{ fontSize: '0.68rem', color: '#92400E' }}>
                Saves ₹{Math.round(data.solar_potential_analysis.estimatedAnnualSavingsInr).toLocaleString('en-IN')}/yr
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Engineering Audit & Methodology Accordion */}
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
              Calculation Audit Trail & Engineering Standards
            </span>
          </div>
          {showAudit ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        {showAudit && (
          <div style={{ marginTop: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            <p style={{ fontSize: '0.74rem', color: '#64748B', margin: 0, lineHeight: 1.5 }}>
              {data.technical_disclaimer}
            </p>
            <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
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
          </div>
        )}
      </div>

      {/* Ask Assistant Follow-up Strip */}
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
            Want to explore financing, equipment brand recommendations, or phase-wise installation?
          </span>
          <button
            type="button"
            onClick={() => onAskFollowUp(`Please analyze my new house energy plan (connected load: ${data.preliminary_connected_load_kw.toFixed(2)} kW, peak demand: ${data.diversified_maximum_demand_kw.toFixed(2)} kW, recommended tier: ${plan.tier_name}). What are the key optimization steps?`)}
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

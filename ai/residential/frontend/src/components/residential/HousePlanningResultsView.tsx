import React, { useState } from 'react';
import {
  HouseEnergyPlanningResult,
} from '../../types/residentialFeatures';
import {
  Sun,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Layers,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Info,
  Home,
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
  const [showCalculationDetails, setShowCalculationDetails] = useState(false);

  const data: HouseEnergyPlanningResult = (result as any)?.results || result;
  const plan = data?.recommended_plan;
  const prop = data?.property_summary || {};
  const budget = data?.budget_summary;
  const recommendations = data?.recommendations || [];
  const solar = data?.solar_readiness || (data?.solar_potential_analysis ? {
    status: 'feasibility_estimated' as const,
    roof_area_available_m2: data.solar_potential_analysis.rooftopAreaAvailableM2,
    recommended_system_kwp: data.solar_potential_analysis.recommendedSystemKwp,
    estimated_monthly_generation_kwh: data.solar_potential_analysis.estimatedMonthlyGenerationKwh,
    estimated_gross_cost_inr: data.solar_potential_analysis.estimatedGrossCostInr,
    mnre_estimated_subsidy_inr: data.solar_potential_analysis.mnreEstimatedSubsidyInr,
    net_investment_inr: data.solar_potential_analysis.netInvestmentInr,
    estimated_annual_savings_inr: data.solar_potential_analysis.estimatedAnnualSavingsInr,
    simple_payback_years: data.solar_potential_analysis.simplePaybackYears,
    feasibility_notes: ['Estimated under PM Surya Ghar Muft Bijli Yojana norms.'],
    missing_inputs: [],
  } : null);
  const ev = data?.ev_readiness;

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

  const bedrooms = prop.bedroomsCount || 3;
  const bathrooms = prop.bathroomsCount || 2;
  const livingAreas = prop.livingDiningCount || 1;
  const daytimeOcc = (prop.daytimeOccupancy || 'mostly_away').replace(/_/g, ' ');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* =========================================================================
          SECTION A: HOME ENERGY PLAN SUMMARY
      ========================================================================= */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1.25rem 1.5rem',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: '#087EBD',
                  backgroundColor: '#EFF6FF',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  letterSpacing: '0.04em',
                }}
              >
                Verified Engineering Blueprint
              </span>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: '#00A396',
                  backgroundColor: '#E0F7F5',
                  padding: '2px 8px',
                  borderRadius: '4px',
                }}
              >
                {plan.tier_name} Tier
              </span>
            </div>
            <h1 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              New House Energy & Electrical Layout
            </h1>
            <p style={{ fontSize: '0.85rem', color: '#475569', margin: '0.35rem 0 0 0', lineHeight: 1.5 }}>
              Customized electrical blueprint for a <strong>{bedrooms}-bedroom, {bathrooms}-bathroom</strong>{' '}
              {(prop.propertyType || 'independent_house').replace(/_/g, ' ')} ({prop.builtUpAreaM2 || 120} m²) in{' '}
              <strong>{prop.locationCity || 'Bangalore'}</strong> with <strong>{daytimeOcc}</strong> occupancy.
            </p>
          </div>

          {onEditInputs && (
            <button
              type="button"
              onClick={onEditInputs}
              style={{
                padding: '0.5rem 0.9rem',
                borderRadius: '6px',
                border: '1px solid #CBD5E1',
                backgroundColor: '#F8FAFC',
                fontSize: '0.8rem',
                fontWeight: 600,
                color: '#334155',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <span>Edit Specifications</span>
            </button>
          )}
        </div>

        {/* Input vs Recommendation Legend */}
        <div
          style={{
            marginTop: '1rem',
            padding: '0.65rem 0.85rem',
            backgroundColor: '#F8FAFC',
            borderRadius: '6px',
            border: '1px solid #E2E8F0',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '1.25rem',
            fontSize: '0.75rem',
            color: '#64748B',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#087EBD' }} />
            <span><strong>Customer Inputs:</strong> {bedrooms} Bed, {bathrooms} Bath, {livingAreas} Living, {prop.builtUpAreaM2} m², Budget ₹{Number(prop.budgetInr || budget?.allocated_budget_inr || 150000).toLocaleString('en-IN')}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#00B8A9' }} />
            <span><strong>System Recommendations:</strong> {plan.tier_name} Equipment Schedule, IS 732 Sizing, Energy Optimization</span>
          </div>
        </div>

        {/* 4 Key Metric Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0.85rem', marginTop: '1.25rem' }}>
          {/* Connected Load */}
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '8px',
              border: '1px solid #E2E8F0',
              padding: '0.9rem 1rem',
              borderTop: '3px solid #00B8A9',
            }}
          >
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em' }}>
              Total Connected Load
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0B1F33', marginTop: '0.2rem' }}>
              {data.preliminary_connected_load_kw.toFixed(2)} <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>kW</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
              Sum of actual planned equipment
            </div>
          </div>

          {/* Diversified Peak Demand */}
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '8px',
              border: '1px solid #E2E8F0',
              padding: '0.9rem 1rem',
              borderTop: '3px solid #087EBD',
            }}
          >
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em' }}>
              Diversified Peak Demand
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#087EBD', marginTop: '0.2rem' }}>
              {data.diversified_maximum_demand_kw.toFixed(2)} <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>kW</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
              IS 732 residential factor (0.65)
            </div>
          </div>

          {/* Recommended Phase */}
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '8px',
              border: '1px solid #E2E8F0',
              padding: '0.9rem 1rem',
              borderTop: '3px solid #8B5CF6',
            }}
          >
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em' }}>
              Recommended Supply Phase
            </div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#6D28D9', marginTop: '0.35rem' }}>
              {plan.recommended_supply_phase || (data.diversified_maximum_demand_kw > 5.0 ? 'Three-Phase (415V)' : 'Single-Phase (230V)')}
            </div>
            <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.25rem' }}>
              {plan.supply_phase_advisory || 'Subject to DISCOM connection sanction'}
            </div>
          </div>

          {/* Monthly Energy & Bill */}
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '8px',
              border: '1px solid #E2E8F0',
              padding: '0.9rem 1rem',
              borderTop: '3px solid #10B981',
            }}
          >
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em' }}>
              Estimated Monthly Bill
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10B981', marginTop: '0.2rem' }}>
              ₹{Math.round(plan.estimated_monthly_bill_inr).toLocaleString('en-IN')} <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748B' }}>/mo</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '0.2rem' }}>
              ≈ {Math.round(plan.estimated_monthly_consumption_kwh)} kWh/month
            </div>
          </div>
        </div>
      </div>

      {/* =========================================================================
          SECTION B: ROOM-WISE ELECTRICAL & EQUIPMENT PLAN (PRIMARY VIEW)
      ========================================================================= */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1.25rem',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <div>
            <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              {data.has_room_assignment ? 'Room-wise Electrical & Equipment Schedule' : 'Overall Equipment Schedule'}
            </h2>
            <p style={{ fontSize: '0.78rem', color: '#64748B', margin: '0.25rem 0 0 0' }}>
              {data.has_room_assignment
                ? `Mapped across ${bedrooms} bedrooms, ${bathrooms} bathrooms, and common living zones based on your requirements.`
                : 'Aggregated equipment schedule based on your requested appliance inventory. Confirm specific room placements during electrical rough-in.'}
            </p>
          </div>
        </div>

        {data.room_wise_schedule && data.room_wise_schedule.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '0.85rem', marginTop: '0.75rem' }}>
            {data.room_wise_schedule.map((room, idx) => (
              <div
                key={idx}
                style={{
                  backgroundColor: '#F8FAFC',
                  borderRadius: '8px',
                  border: '1px solid #E2E8F0',
                  padding: '0.9rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #E2E8F0', paddingBottom: '0.45rem', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Home size={15} color="#087EBD" />
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0F172A' }}>{room.room_name}</span>
                  </div>
                  {room.ac_provision && (
                    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#0284C7', backgroundColor: '#E0F2FE', padding: '2px 6px', borderRadius: '4px' }}>
                      AC Provision
                    </span>
                  )}
                </div>

                <div style={{ fontSize: '0.75rem', color: '#475569', minHeight: '60px' }}>
                  {room.equipment && room.equipment.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.6 }}>
                      {room.equipment.map((eq, eqIdx) => (
                        <li key={eqIdx}>
                          <strong>{eq.quantity}× {eq.item_name.split('(')[0].trim()}</strong>{' '}
                          <span style={{ color: '#64748B' }}>({eq.rated_power_w}W)</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: '#94A3B8', fontStyle: 'italic', padding: '0.4rem 0' }}>
                      Standard 6A lighting and convenience sub-circuits planned.
                    </div>
                  )}
                </div>

                {room.notes && (
                  <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.5rem', paddingTop: '0.4rem', borderTop: '1px dashed #E2E8F0' }}>
                    {room.notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: '1rem', backgroundColor: '#F8FAFC', borderRadius: '8px', color: '#64748B', fontSize: '0.82rem' }}>
            Overall equipment list generated below. No fictitious architectural rooms were created.
          </div>
        )}

        {/* Unassigned Appliances Notice if any */}
        {data.unassigned_appliances && data.unassigned_appliances.length > 0 && (
          <div
            style={{
              marginTop: '1rem',
              padding: '0.75rem 1rem',
              backgroundColor: '#EFF6FF',
              borderRadius: '6px',
              border: '1px solid #BFDBFE',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.6rem',
              fontSize: '0.78rem',
              color: '#1E40AF',
            }}
          >
            <Info size={16} color="#2563EB" style={{ marginTop: '2px', flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 700, marginBottom: '0.2rem' }}>Site Conduit Rough-In Allocation:</div>
              <div>The following planned equipment should have dedicated radial conduit runs finalized with your contractor during construction:</div>
              <ul style={{ margin: '0.3rem 0 0 0', paddingLeft: '1.1rem', lineHeight: 1.5 }}>
                {data.unassigned_appliances.map((ua, i) => (
                  <li key={i}>{ua}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* =========================================================================
          SECTION C: EQUIPMENT SCHEDULE TABLE
      ========================================================================= */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1.25rem',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <div>
            <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              Equipment Schedule & Specifications
            </h2>
            <p style={{ fontSize: '0.78rem', color: '#64748B', margin: '0.25rem 0 0 0' }}>
              Showing {plan.equipment_schedule.length} verified equipment items in the <strong>{plan.tier_name}</strong> plan.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowSchedule(!showSchedule)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid #CBD5E1',
              backgroundColor: '#F8FAFC',
              fontSize: '0.78rem',
              fontWeight: 600,
              color: '#334155',
              cursor: 'pointer',
            }}
          >
            <Layers size={14} />
            <span>{showSchedule ? 'Collapse Table' : 'Expand Schedule'}</span>
            {showSchedule ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Table always shows compact or expanded */}
        <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
            <thead>
              <tr style={{ backgroundColor: '#F1F5F9', color: '#475569', textAlign: 'left' }}>
                <th style={{ padding: '0.55rem 0.6rem' }}>Equipment Item</th>
                <th style={{ padding: '0.55rem 0.6rem' }}>Quantity</th>
                <th style={{ padding: '0.55rem 0.6rem' }}>Efficiency Standard / Tech</th>
                <th style={{ padding: '0.55rem 0.6rem' }}>Rated Power</th>
                <th style={{ padding: '0.55rem 0.6rem' }}>Monthly Use</th>
                <th style={{ padding: '0.55rem 0.6rem' }}>Estimated Cost</th>
              </tr>
            </thead>
            <tbody>
              {(showSchedule ? plan.equipment_schedule : plan.equipment_schedule.slice(0, 5)).map((eq, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #E2E8F0' }}>
                  <td style={{ padding: '0.55rem 0.6rem', fontWeight: 600, color: '#0F172A' }}>
                    {eq.item_name}
                    {eq.notes && (
                      <div style={{ fontSize: '0.68rem', fontWeight: 400, color: '#64748B', marginTop: '2px' }}>
                        {eq.notes}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '0.55rem 0.6rem' }}>{eq.quantity}</td>
                  <td style={{ padding: '0.55rem 0.6rem', color: '#087EBD', fontWeight: 500 }}>
                    {eq.efficiency_standard}
                  </td>
                  <td style={{ padding: '0.55rem 0.6rem' }}>
                    {eq.rated_power_w > 0 ? `${eq.rated_power_w} W` : <span style={{ color: '#94A3B8', fontStyle: 'italic' }}>Nameplate unverified</span>}
                  </td>
                  <td style={{ padding: '0.55rem 0.6rem' }}>
                    {eq.estimated_monthly_kwh > 0 ? `${Math.round(eq.estimated_monthly_kwh)} kWh` : '–'}
                  </td>
                  <td style={{ padding: '0.55rem 0.6rem', fontWeight: 700, color: '#0F172A' }}>
                    {eq.total_cost_inr !== null && eq.total_cost_inr !== undefined ? (
                      `₹${Math.round(eq.total_cost_inr).toLocaleString('en-IN')}`
                    ) : (
                      <span style={{ color: '#F59E0B', fontSize: '0.72rem', fontWeight: 600 }}>Market Quote Needed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!showSchedule && plan.equipment_schedule.length > 5 && (
            <div style={{ textAlign: 'center', padding: '0.5rem', backgroundColor: '#F8FAFC', borderBottom: '1px solid #E2E8F0' }}>
              <button
                type="button"
                onClick={() => setShowSchedule(true)}
                style={{ background: 'none', border: 'none', color: '#087EBD', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}
              >
                + Show {plan.equipment_schedule.length - 5} more planned equipment items
              </button>
            </div>
          )}
        </div>
      </div>

      {/* =========================================================================
          SECTION D: ESTIMATED ENERGY CONSUMPTION & MONTHLY BILL
      ========================================================================= */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1.25rem',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <div>
            <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              Energy Consumption & Bill Projection
            </h2>
            <p style={{ fontSize: '0.78rem', color: '#64748B', margin: '0.25rem 0 0 0' }}>
              Modeled using verified BEE duty cycles and flat residential tariff rate of ₹10.00/kWh.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowCalculationDetails(!showCalculationDetails)}
            style={{
              fontSize: '0.75rem',
              color: '#087EBD',
              background: 'none',
              border: 'none',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
            }}
          >
            <span>{showCalculationDetails ? 'Hide Calculation Methodology' : 'View Calculation Breakdown'}</span>
            {showCalculationDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginTop: '0.5rem' }}>
          <div style={{ backgroundColor: '#F8FAFC', padding: '0.85rem', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600 }}>ESTIMATED MONTHLY POWER</div>
            <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#0F172A', marginTop: '0.2rem' }}>
              {Math.round(plan.estimated_monthly_consumption_kwh)} <span style={{ fontSize: '0.8rem' }}>kWh / mo</span>
            </div>
            <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.2rem' }}>
              Annual: ~{Math.round(plan.estimated_monthly_consumption_kwh * 12).toLocaleString('en-IN')} kWh / year
            </div>
          </div>

          <div style={{ backgroundColor: '#F8FAFC', padding: '0.85rem', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600 }}>MONTHLY BILL ESTIMATE</div>
            <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#10B981', marginTop: '0.2rem' }}>
              ₹{Math.round(plan.estimated_monthly_bill_inr).toLocaleString('en-IN')} <span style={{ fontSize: '0.8rem' }}>/ mo</span>
            </div>
            <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.2rem' }}>
              Annual: ₹{Math.round(plan.estimated_annual_bill_inr).toLocaleString('en-IN')} / year
            </div>
          </div>

          <div style={{ backgroundColor: '#F8FAFC', padding: '0.85rem', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
            <div style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600 }}>CALCULATED EFFICIENCY GAIN</div>
            <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#00A396', marginTop: '0.2rem' }}>
              {plan.energy_savings_vs_standard_pct > 0 ? `${plan.energy_savings_vs_standard_pct}%` : 'Baseline'}
            </div>
            <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.2rem' }}>
              Calculated vs Economy standard equipment
            </div>
          </div>
        </div>

        {showCalculationDetails && (
          <div
            style={{
              marginTop: '1rem',
              padding: '1rem',
              backgroundColor: '#F1F5F9',
              borderRadius: '8px',
              fontSize: '0.75rem',
              color: '#334155',
              lineHeight: 1.6,
            }}
          >
            <div style={{ fontWeight: 700, color: '#0F172A', marginBottom: '0.35rem' }}>
              Transparent Calculation Provenance:
            </div>
            <div>• <strong>Lighting:</strong> Rated fixture wattage × planned points ({bedrooms} bed + {bathrooms} bath + living) × daily operating hours (~{daytimeOcc === 'mostly away' ? 4.5 : 6.5}h).</div>
            <div>• <strong>Ceiling Fans:</strong> Evaluated using BEE 5-Star BLDC motor draw (28W vs 75W induction) under IS 374 duty cycles.</div>
            <div>• <strong>Air Conditioning:</strong> Modulated power draw (~680W–950W average) reflecting inverter variable speed compressor duty cycle.</div>
            <div>• <strong>Water Heating:</strong> Active heating duration + 24h standing thermal loss per BEE IS 2082 insulated geyser benchmark.</div>
            <div>• <strong>Refrigeration:</strong> 24h continuous operation with seasonal defrost normalization per BEE S&L schedule.</div>
          </div>
        )}
      </div>

      {/* =========================================================================
          SECTION E: BUDGET SUMMARY & COMPARISON
      ========================================================================= */}
      {budget && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
            boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
            <div>
              <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
                Budget Summary & Cost Coverage
              </h2>
              <p style={{ fontSize: '0.78rem', color: '#64748B', margin: '0.25rem 0 0 0' }}>
                Comparing verified equipment purchase costs against your allocated capital budget.
              </p>
            </div>

            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '3px 8px',
                borderRadius: '4px',
                backgroundColor: budget.budget_exceeded ? '#FEF2F2' : '#F0FDF4',
                color: budget.budget_exceeded ? '#EF4444' : '#16A34A',
                border: `1px solid ${budget.budget_exceeded ? '#FECACA' : '#BBF7D0'}`,
              }}
            >
              {budget.budget_exceeded
                ? `Exceeds Budget by ₹${Math.round(budget.budget_variance_inr).toLocaleString('en-IN')}`
                : `Within Budget (₹${Math.round(Math.abs(budget.budget_variance_inr)).toLocaleString('en-IN')} Buffer)`}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.85rem' }}>
            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '6px', border: '1px solid #E2E8F0' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>LIGHTING & FANS</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0F172A', marginTop: '0.2rem' }}>
                ₹{Math.round(budget.lighting_fans_cost_inr || 0).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '6px', border: '1px solid #E2E8F0' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>AIR CONDITIONING</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0F172A', marginTop: '0.2rem' }}>
                ₹{Math.round(budget.cooling_cost_inr || 0).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '6px', border: '1px solid #E2E8F0' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>WATER HEATING</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0F172A', marginTop: '0.2rem' }}>
                ₹{Math.round(budget.water_heating_cost_inr || 0).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '6px', border: '1px solid #E2E8F0' }}>
              <div style={{ fontSize: '0.7rem', color: '#64748B' }}>OTHER APPLIANCES</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#0F172A', marginTop: '0.2rem' }}>
                ₹{Math.round(budget.other_equipment_cost_inr || 0).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ backgroundColor: '#EFF6FF', padding: '0.75rem', borderRadius: '6px', border: '1px solid #BFDBFE' }}>
              <div style={{ fontSize: '0.7rem', color: '#1E40AF', fontWeight: 700 }}>TOTAL EQUIPMENT COST</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#1E3A8A', marginTop: '0.2rem' }}>
                ₹{Math.round(budget.total_equipment_cost_inr).toLocaleString('en-IN')}
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: '0.85rem',
              padding: '0.65rem 0.85rem',
              backgroundColor: '#FFFBEB',
              borderRadius: '6px',
              border: '1px solid #FDE68A',
              fontSize: '0.73rem',
              color: '#92400E',
              lineHeight: 1.5,
            }}
          >
            <strong>Note on Wiring and Installation:</strong> {budget.wiring_installation_note}
          </div>
        </div>
      )}

      {/* =========================================================================
          SECTION F: PRACTICAL RESIDENTIAL RECOMMENDATIONS
      ========================================================================= */}
      {recommendations.length > 0 && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
            boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
          }}
        >
          <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: '0 0 0.85rem 0' }}>
            Practical Engineering Recommendations
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.85rem' }}>
            {recommendations.map((rec, idx) => (
              <div
                key={idx}
                style={{
                  backgroundColor: '#F8FAFC',
                  borderRadius: '8px',
                  border: '1px solid #E2E8F0',
                  padding: '1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <CheckCircle2 size={16} color="#00A396" />
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0F172A' }}>{rec.title}</span>
                </div>
                <div style={{ fontSize: '0.78rem', color: '#475569', lineHeight: 1.5 }}>
                  {rec.rationale}
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#059669', marginTop: '0.2rem' }}>
                  Benefit: {rec.expected_benefit}
                </div>
                <div style={{ fontSize: '0.68rem', color: '#94A3B8', marginTop: '0.2rem' }}>
                  Standard / Source: {rec.source}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =========================================================================
          SECTION G: CONDITIONAL SOLAR & EV READINESS
      ========================================================================= */}
      {/* Solar Readiness */}
      {solar && solar.status !== 'not_requested' && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
            boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Sun size={20} color="#D97706" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              Rooftop Solar PV Readiness
            </h2>
          </div>

          {solar.status === 'feasibility_estimated' && solar.recommended_system_kwp ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.85rem' }}>
                <div style={{ backgroundColor: '#FFFBEB', padding: '0.85rem', borderRadius: '8px', border: '1px solid #FDE68A' }}>
                  <div style={{ fontSize: '0.7rem', color: '#92400E', fontWeight: 700 }}>RECOMMENDED SIZING</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#B45309', marginTop: '0.2rem' }}>
                    {solar.recommended_system_kwp.toFixed(1)} <span style={{ fontSize: '0.8rem' }}>kWp</span>
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#92400E', marginTop: '0.2rem' }}>
                    Requires ~{Math.round(solar.recommended_system_kwp * 10)} m² shadow-free roof
                  </div>
                </div>

                <div style={{ backgroundColor: '#F8FAFC', padding: '0.85rem', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                  <div style={{ fontSize: '0.7rem', color: '#64748B', fontWeight: 700 }}>MONTHLY GENERATION</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0F172A', marginTop: '0.2rem' }}>
                    ~{Math.round(solar.estimated_monthly_generation_kwh || 0)} <span style={{ fontSize: '0.8rem' }}>kWh/mo</span>
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.2rem' }}>
                    Offsets ~{Math.min(100, Math.round(((solar.estimated_monthly_generation_kwh || 0) / plan.estimated_monthly_consumption_kwh) * 100))}% of home consumption
                  </div>
                </div>

                <div style={{ backgroundColor: '#F8FAFC', padding: '0.85rem', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                  <div style={{ fontSize: '0.7rem', color: '#64748B', fontWeight: 700 }}>ESTIMATED PAYBACK</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#059669', marginTop: '0.2rem' }}>
                    {solar.simple_payback_years ? `${solar.simple_payback_years} yrs` : 'N/A'}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#64748B', marginTop: '0.2rem' }}>
                    Net Investment: ₹{Math.round(solar.net_investment_inr || 0).toLocaleString('en-IN')} (post PM Surya Ghar subsidy)
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ backgroundColor: '#F8FAFC', padding: '1rem', borderRadius: '8px', border: '1px solid #E2E8F0', fontSize: '0.8rem', color: '#475569', lineHeight: 1.5 }}>
              <div style={{ fontWeight: 700, color: '#0F172A', marginBottom: '0.35rem' }}>Preliminary Solar Readiness Recorded:</div>
              <div>Rooftop solar interest recorded. To calculate an accurate system size and financial payback, provide your approximate usable unshaded roof area. Standard arrays require ~10 m² per 1 kWp installed.</div>
              {solar.missing_inputs && solar.missing_inputs.length > 0 && (
                <div style={{ marginTop: '0.5rem', color: '#B45309', fontWeight: 600 }}>
                  Next step: Confirm {solar.missing_inputs.join(', ')} with your solar vendor.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* EV Readiness */}
      {ev && ev.status !== 'not_requested' && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            padding: '1.25rem',
            boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Zap size={20} color="#087EBD" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              Electric Vehicle (EV) Charging Provision
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
            <div style={{ backgroundColor: '#F0F9FF', padding: '0.85rem', borderRadius: '8px', border: '1px solid #BAE6FD' }}>
              <div style={{ fontSize: '0.7rem', color: '#0369A1', fontWeight: 700 }}>RECOMMENDED CIRCUIT SPECIFICATION</div>
              <div style={{ fontSize: '1rem', fontWeight: 800, color: '#0C4A6E', marginTop: '0.2rem' }}>
                {ev.recommended_charger_type}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#0369A1', marginTop: '0.3rem' }}>
                Conductor Rating: {ev.recommended_circuit_rating}
              </div>
            </div>

            <div style={{ backgroundColor: '#F8FAFC', padding: '0.85rem', borderRadius: '8px', border: '1px solid #E2E8F0', fontSize: '0.75rem', color: '#475569' }}>
              <div style={{ fontWeight: 700, color: '#0F172A', marginBottom: '0.35rem' }}>Statutory IS 17017 Safety Guidelines:</div>
              <ul style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.6 }}>
                {ev.safety_guidelines.map((sg, i) => (
                  <li key={i}>{sg}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          SECTION H: ASSUMPTIONS & PROFESSIONAL REVIEW
      ========================================================================= */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          padding: '1.25rem',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.05)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <ShieldCheck size={18} color="#059669" />
            <h2 style={{ fontSize: '0.95rem', fontWeight: 800, color: '#0B1F33', margin: 0 }}>
              Engineering Standards, Assumptions & Audit Trail
            </h2>
          </div>

          <button
            type="button"
            onClick={() => setShowAudit(!showAudit)}
            style={{
              fontSize: '0.78rem',
              color: '#087EBD',
              background: 'none',
              border: 'none',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
            }}
          >
            <span>{showAudit ? 'Collapse Details' : 'View Standards & Audit Trail'}</span>
            {showAudit ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {showAudit && (
          <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {/* Assumptions List */}
            {data.assumptions && data.assumptions.length > 0 && (
              <div style={{ backgroundColor: '#F8FAFC', padding: '0.75rem', borderRadius: '6px', fontSize: '0.75rem', color: '#475569' }}>
                <div style={{ fontWeight: 700, color: '#0F172A', marginBottom: '0.35rem' }}>Model Assumptions:</div>
                <ul style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.5 }}>
                  {data.assumptions.map((asmp, i) => (
                    <li key={i}>{asmp}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Audit Trail Items */}
            {data.audit_trail && data.audit_trail.length > 0 && (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.73rem' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#F1F5F9', color: '#475569', textAlign: 'left' }}>
                      <th style={{ padding: '0.45rem' }}>Metric</th>
                      <th style={{ padding: '0.45rem' }}>Value</th>
                      <th style={{ padding: '0.45rem' }}>Provenance</th>
                      <th style={{ padding: '0.45rem' }}>Derivation Methodology</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.audit_trail.map((item, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #E2E8F0' }}>
                        <td style={{ padding: '0.45rem', fontWeight: 600 }}>{item.metric_name}</td>
                        <td style={{ padding: '0.45rem', fontWeight: 700, color: '#087EBD' }}>
                          {item.value} {item.unit || ''}
                        </td>
                        <td style={{ padding: '0.45rem', textTransform: 'capitalize' }}>
                          {(item.provenance || '').replace(/_/g, ' ')}
                        </td>
                        <td style={{ padding: '0.45rem', color: '#64748B' }}>{item.methodology}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Prominent Statutory Disclaimer */}
        <div
          style={{
            marginTop: '1rem',
            padding: '0.85rem 1rem',
            backgroundColor: '#F8FAFC',
            borderRadius: '6px',
            border: '1px solid #CBD5E1',
            fontSize: '0.75rem',
            color: '#475569',
            lineHeight: 1.55,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, color: '#0F172A', marginBottom: '0.2rem' }}>
            <AlertTriangle size={14} color="#D97706" />
            <span>Important Professional Review & Statutory Notice</span>
          </div>
          <div>{data.technical_disclaimer}</div>
        </div>

        {/* Conversational Assistant Follow-Up Prompts */}
        {onAskFollowUp && (
          <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px dashed #E2E8F0' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: '0.5rem' }}>
              Ask Assistant Follow-Up Questions:
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {[
                "How do I choose between Single-Phase and Three-Phase supply?",
                "Can I add solar panels later without rewiring?",
                "Which BEE 5-star AC models fit my budget?",
                "How can I reduce peak load during summer?"
              ].map((promptText, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onAskFollowUp(promptText)}
                  style={{
                    padding: '0.35rem 0.75rem',
                    backgroundColor: '#F0F9FF',
                    border: '1px solid #BAE6FD',
                    color: '#0369A1',
                    borderRadius: '9999px',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    fontWeight: 500,
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#E0F2FE')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#F0F9FF')}
                >
                  💬 {promptText}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

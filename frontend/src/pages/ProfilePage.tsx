import React, { useEffect, useState } from 'react';
import { usePersona } from '../context';
import { analyticsService } from '../services/analyticsService';
import { ResidentialMeter, CommercialBuilding, RegionalSite } from '../types/analytics';
import {
  Calendar,
  Clock,
  BarChart2,
  Bell,
  FileText,
  Settings,
  Lightbulb,
  Info,
  Landmark,
  Building2,
  Home,
  CheckCircle2,
  Hash,
  Database,
} from 'lucide-react';

interface ToggleSwitchProps {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
}

const ToggleSwitch: React.FC<ToggleSwitchProps> = ({ id, checked, onChange, ariaLabel }) => {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      style={{
        width: '46px',
        height: '26px',
        borderRadius: '9999px',
        backgroundColor: checked ? '#005E72' : '#CBD5E1',
        border: 'none',
        position: 'relative',
        cursor: 'pointer',
        padding: '3px',
        transition: 'background-color 0.2s ease',
        display: 'inline-flex',
        alignItems: 'center',
        flexShrink: 0,
      }}
    >
      <span
        style={{
          width: '20px',
          height: '20px',
          borderRadius: '50%',
          backgroundColor: '#FFFFFF',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.2)',
          transform: checked ? 'translateX(20px)' : 'translateX(0px)',
          transition: 'transform 0.2s ease',
          display: 'block',
        }}
      />
    </button>
  );
};

export const ProfilePage: React.FC = () => {
  const {
    currentPersona,
    activeEntity,
    energyUnit,
    setEnergyUnit,
    notificationPreferences,
    setNotificationPreferences,
  } = usePersona();

  const [activeMeter, setActiveMeter] = useState<ResidentialMeter | null>(null);
  const [activeBuilding, setActiveBuilding] = useState<CommercialBuilding | null>(null);
  const [activeSite, setActiveSite] = useState<RegionalSite | null>(null);
  const [_isLoading, setIsLoading] = useState(false);

  const isGov = currentPersona === 'government';
  const isComm = currentPersona === 'commercial';
  const isHousehold = !isGov && !isComm;

  const numPart = (activeEntity || '2254213').replace(/METER-/i, '').replace(/meter-/i, '');
  const residentName = `OBJECTID ${numPart}`;

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);

    if (isHousehold) {
      const meterId = (activeEntity || '2254213').replace(/METER-/i, '');
      analyticsService
        .getResidentialMeter(meterId)
        .then((data) => {
          if (!cancelled) setActiveMeter(data);
        })
        .catch(() => {
          if (!cancelled) setActiveMeter(null);
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    } else if (isComm) {
      analyticsService
        .getCommercialBuildings()
        .then((buildings) => {
          if (!cancelled) {
            const found =
              buildings.find(
                (b) => b.buildingId.toLowerCase() === (activeEntity || '').toLowerCase()
              ) || buildings[0];
            setActiveBuilding(found || null);
          }
        })
        .catch(() => {
          if (!cancelled) setActiveBuilding(null);
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    } else if (isGov) {
      analyticsService
        .getRegionalSites()
        .then((sites) => {
          if (!cancelled) {
            const found =
              sites.find(
                (s) => s.siteId.toLowerCase() === (activeEntity || '').toLowerCase()
              ) || sites[0];
            setActiveSite(found || null);
          }
        })
        .catch(() => {
          if (!cancelled) setActiveSite(null);
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    }

    return () => {
      cancelled = true;
    };
  }, [currentPersona, activeEntity, isHousehold, isComm, isGov]);

  const userName = isGov
    ? 'Grid Operations Admin'
    : isComm
    ? `Facility Manager (${activeBuilding?.buildingId || activeEntity || 'Panther_office_1'})`
    : residentName;

  const userInitial = isGov ? 'G' : isComm ? 'C' : 'O';

  const personaLabel = isGov
    ? 'Government & Utilities'
    : isComm
    ? 'Commercial Facility'
    : 'Residential Consumer';

  const PersonaIcon = isGov ? Landmark : isComm ? Building2 : Home;

  const handleToggle = (key: keyof typeof notificationPreferences) => {
    setNotificationPreferences((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
        padding: '0.5rem 0 2rem 0',
      }}
    >
      {/* 1. Page Title & Subtitle */}
      <div>
        <h1
          style={{
            fontSize: '2rem',
            fontWeight: 800,
            color: '#0F172A',
            letterSpacing: '-0.025em',
            margin: 0,
            lineHeight: 1.15,
          }}
        >
          Profile
        </h1>
        <p
          style={{
            fontSize: '0.95rem',
            color: '#64748B',
            marginTop: '6px',
            marginBottom: 0,
          }}
        >
          View your verified account telemetry and manage system preferences.
        </p>
      </div>

      {/* 2. Profile Summary Card */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '14px',
          border: '1px solid #E2E8F0',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
          padding: '1.75rem 2rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '2rem',
        }}
      >
        {/* Left: Avatar + Name + Persona Badge + Identifier */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap' }}>
          {/* Circular Initial Avatar */}
          <div
            style={{
              width: '84px',
              height: '84px',
              borderRadius: '50%',
              backgroundColor: '#D0E8F4',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#0B2538',
              fontSize: '2.5rem',
              fontWeight: 700,
              flexShrink: 0,
              userSelect: 'none',
            }}
          >
            {userInitial}
          </div>

          {/* Details */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
            <h2
              style={{
                fontSize: '1.45rem',
                fontWeight: 700,
                color: '#0F172A',
                margin: 0,
                lineHeight: 1.2,
              }}
            >
              {userName}
            </h2>

            {/* Persona & Entity Badges */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  borderRadius: '8px',
                  backgroundColor: '#E0F2FE',
                  color: '#0284C7',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                }}
              >
                <PersonaIcon size={14} />
                <span>{personaLabel}</span>
              </span>

              {isHousehold && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '8px',
                    backgroundColor: '#F1F5F9',
                    color: '#334155',
                    fontSize: '0.78rem',
                    fontFamily: 'monospace',
                    fontWeight: 700,
                    border: '1px solid #E2E8F0',
                  }}
                >
                  <Hash size={13} color="#64748B" />
                  <span>OBJECTID: {activeMeter?.objectId || numPart}</span>
                </span>
              )}

              {isComm && activeBuilding && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '8px',
                    backgroundColor: '#F1F5F9',
                    color: '#334155',
                    fontSize: '0.78rem',
                    fontFamily: 'monospace',
                    fontWeight: 700,
                    border: '1px solid #E2E8F0',
                  }}
                >
                  <Building2 size={13} color="#64748B" />
                  <span>{activeBuilding.buildingId}</span>
                </span>
              )}

              {isComm && activeBuilding?.siteId && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '8px',
                    backgroundColor: '#FEF3C7',
                    color: '#B45309',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    border: '1px solid #FDE68A',
                  }}
                >
                  <span>Site: {activeBuilding.siteId}</span>
                </span>
              )}

              {isGov && activeSite?.siteId && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '8px',
                    backgroundColor: '#FEF3C7',
                    color: '#B45309',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    border: '1px solid #FDE68A',
                  }}
                >
                  <span>Region: {activeSite.siteId}</span>
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Real Telemetry Sync Details */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
            minWidth: '220px',
            borderLeft: '1px solid #F1F5F9',
            paddingLeft: '2rem',
          }}
        >
          {isHousehold && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Calendar size={20} color="#0F172A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>
                    Last Telemetry Date
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                    {activeMeter?.lastDate || '—'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Clock size={20} color="#0F172A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>
                    Billing Cycle Progress
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                    {activeMeter ? `Day ${activeMeter.elapsedDays} of 30` : '—'}
                  </div>
                </div>
              </div>
            </>
          )}

          {isComm && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Calendar size={20} color="#0F172A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>
                    Last Timestamp
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                    {activeBuilding?.lastTimestamp || '—'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Building2 size={20} color="#0F172A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>
                    Primary Usage
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                    {activeBuilding?.primarySpaceUsage || '—'}
                  </div>
                </div>
              </div>
            </>
          )}

          {isGov && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Calendar size={20} color="#0F172A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>
                    Active Season
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                    {activeSite?.season || 'Summer'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Building2 size={20} color="#0F172A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>
                    Monitored Buildings
                  </div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                    {activeSite ? `${activeSite.buildingCount} Facilities` : '—'}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 3. Verified Telemetry Metadata Section (Strictly Real Data Fields) */}
      {isHousehold && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.75rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Database size={18} color="#005E72" />
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
                  OBJECTID Telemetry & Cycle Metadata
                </h2>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0 }}>
                Verified dataset records for {residentName} (OBJECTID: {activeMeter?.objectId || numPart}).
              </p>
            </div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 12px',
                borderRadius: '9999px',
                backgroundColor: '#DCFCE7',
                color: '#15803D',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
              }}
            >
              <CheckCircle2 size={13} />
              <span>DATASET RECORD (LIVE)</span>
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '1rem',
            }}
          >
            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                OBJECTID
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', fontFamily: 'monospace', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.objectId || numPart}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Physical Parquet Entity Key
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                dailyKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#005E72', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.dailyKwh !== undefined ? `${activeMeter.dailyKwh.toFixed(1)} kWh/day` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Current Daily Consumption
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                actualCycleKwhSoFar
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.actualCycleKwhSoFar !== undefined ? `${activeMeter.actualCycleKwhSoFar.toFixed(1)} kWh` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Cycle Consumption to Date
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                elapsedDays
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.elapsedDays !== undefined ? `${activeMeter.elapsedDays} Days` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Billing Cycle Elapsed
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                targetRemainingKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.targetRemainingKwh !== undefined ? `${activeMeter.targetRemainingKwh.toFixed(1)} kWh` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Cycle Target Remaining
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                predictedRemainingKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.predictedRemainingKwh !== undefined ? `${activeMeter.predictedRemainingKwh.toFixed(1)} kWh` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Model Predicted Remaining
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                estimatedMonthEndKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.estimatedMonthEndKwh !== undefined ? `${activeMeter.estimatedMonthEndKwh.toFixed(1)} kWh` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Estimated Month-End Total
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                estimatedMonthEndBillInr
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#005E72', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.estimatedMonthEndBillInr !== undefined ? `₹${activeMeter.estimatedMonthEndBillInr.toLocaleString()}` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Projected Billing Amount
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                coverageRatio
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#15803D', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.coverageRatio !== undefined ? `${(activeMeter.coverageRatio * 100).toFixed(1)}%` : '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Telemetry Coverage Ratio
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                lastDate
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeMeter?.lastDate || '—'}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Last Telemetry Sync
              </span>
            </div>
          </div>
        </div>
      )}

      {isComm && activeBuilding && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.75rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Database size={18} color="#005E72" />
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
                  Building Telemetry & Facility Metadata
                </h2>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0 }}>
                Verified dataset records for {activeBuilding.buildingId}.
              </p>
            </div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 12px',
                borderRadius: '9999px',
                backgroundColor: '#DCFCE7',
                color: '#15803D',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
              }}
            >
              <CheckCircle2 size={13} />
              <span>DATASET RECORD (LIVE)</span>
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '1rem',
            }}
          >
            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                buildingId
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', fontFamily: 'monospace', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.buildingId}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Building Identifier
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                siteId
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#005E72', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.siteId}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Regional Site Identifier
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                primarySpaceUsage
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.primarySpaceUsage}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Facility Classification
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                sqm
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.sqm.toLocaleString()} m²
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Total Floor Area
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                yearBuilt
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.yearBuilt}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Year Constructed
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                recentDemandKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.recentDemandKwh.toFixed(1)} kWh
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Latest Recorded Demand
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                predictedDemandKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.predictedDemandKwh.toFixed(1)} kWh
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Model Predicted Demand
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                pctError
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#15803D', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.pctError.toFixed(2)}%
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Model Accuracy (Abs Err: {activeBuilding.absErrorKwh.toFixed(1)} kWh)
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                lastTimestamp
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeBuilding.lastTimestamp}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Telemetry Sync Timestamp
              </span>
            </div>
          </div>
        </div>
      )}

      {isGov && activeSite && (
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.75rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Database size={18} color="#005E72" />
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
                  Regional Grid Site Metadata
                </h2>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0 }}>
                Verified dataset records for Region {activeSite.siteId}.
              </p>
            </div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 12px',
                borderRadius: '9999px',
                backgroundColor: '#DCFCE7',
                color: '#15803D',
                fontSize: '0.75rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
              }}
            >
              <CheckCircle2 size={13} />
              <span>DATASET RECORD (LIVE)</span>
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '1rem',
            }}
          >
            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                siteId
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#005E72', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.siteId}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Regional Site Identifier
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                buildingCount
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.buildingCount} Facilities
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Connected Facilities
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                totalDemandKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.totalDemandKwh.toLocaleString()} kWh
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Total Recorded Demand
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                predictedDemandKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.predictedDemandKwh.toLocaleString()} kWh
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Model Projected Demand
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                peakHourKwh
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.peakHourKwh.toLocaleString()} kWh
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Coincident Peak Demand
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                shareOfTotalPct
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#15803D', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.shareOfTotalPct}%
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Grid Capacity Share
              </span>
            </div>

            <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', backgroundColor: '#F8FAFC', border: '1px solid #E2E8F0' }}>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>
                season
              </span>
              <strong style={{ fontSize: '1.1rem', color: '#0F172A', display: 'block', marginTop: '0.35rem' }}>
                {activeSite.season}
              </strong>
              <span style={{ fontSize: '0.72rem', color: '#64748B', marginTop: '2px', display: 'block' }}>
                Active Season Model
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 4. Display Settings & Notification Preferences */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))',
          gap: '1.5rem',
          alignItems: 'stretch',
        }}
      >
        {/* Card 1: Display Settings */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.75rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
            Display Settings
          </h2>
          <p
            style={{
              fontSize: '0.85rem',
              color: '#64748B',
              margin: '6px 0 1.5rem 0',
              lineHeight: 1.4,
            }}
          >
            Choose your preferred units for energy metrics across all dashboards and reports.
          </p>

          {/* Inner Energy Units Selector Box */}
          <div
            style={{
              backgroundColor: '#F8FAFC',
              borderRadius: '10px',
              border: '1px solid #E2E8F0',
              padding: '1.25rem 1.5rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div
                style={{
                  width: '42px',
                  height: '42px',
                  borderRadius: '50%',
                  backgroundColor: '#E0F2FE',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <BarChart2 size={20} color="#005E72" />
              </div>
              <div>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                  Energy Units
                </div>
                <div style={{ fontSize: '0.8rem', color: '#64748B', marginTop: '2px' }}>
                  Select the unit in which energy data is displayed.
                </div>
              </div>
            </div>

            {/* Segmented Button: kWh / MWh */}
            <div
              style={{
                display: 'inline-flex',
                borderRadius: '8px',
                border: '1px solid #CBD5E1',
                overflow: 'hidden',
                backgroundColor: '#FFFFFF',
              }}
            >
              <button
                type="button"
                onClick={() => setEnergyUnit('kWh')}
                style={{
                  padding: '8px 22px',
                  fontSize: '0.85rem',
                  fontWeight: energyUnit === 'kWh' ? 700 : 500,
                  color: energyUnit === 'kWh' ? '#FFFFFF' : '#334155',
                  backgroundColor: energyUnit === 'kWh' ? '#005E72' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                kWh
              </button>
              <button
                type="button"
                onClick={() => setEnergyUnit('MWh')}
                style={{
                  padding: '8px 22px',
                  fontSize: '0.85rem',
                  fontWeight: energyUnit === 'MWh' ? 700 : 500,
                  color: energyUnit === 'MWh' ? '#FFFFFF' : '#334155',
                  backgroundColor: energyUnit === 'MWh' ? '#005E72' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                MWh
              </button>
            </div>
          </div>

          {/* Info Notice Box */}
          <div
            style={{
              backgroundColor: '#F0F9FF',
              border: '1px solid #BAE6FD',
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              marginTop: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
              color: '#0369A1',
              fontSize: '0.82rem',
              fontWeight: 500,
              lineHeight: 1.4,
            }}
          >
            <Info size={16} color="#0284C7" style={{ flexShrink: 0 }} />
            <span>
              This preference will be applied across all dashboards, reports and visualizations.
            </span>
          </div>
        </div>

        {/* Card 2: Notification Preferences */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.75rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
            Notification Preferences
          </h2>
          <p
            style={{
              fontSize: '0.85rem',
              color: '#64748B',
              margin: '6px 0 1.5rem 0',
              lineHeight: 1.4,
            }}
          >
            Choose what you want to be notified about.
          </p>

          {/* Notification Items List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.15rem', flex: 1 }}>
            {/* 1. Demand Alerts */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '50%',
                    backgroundColor: '#E0F2FE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Bell size={18} color="#005E72" />
                </div>
                <div>
                  <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A' }}>
                    Demand Alerts
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', marginTop: '2px' }}>
                    Get notified about unusual demand patterns
                  </div>
                </div>
              </div>
              <ToggleSwitch
                id="toggle-demand-alerts"
                checked={notificationPreferences.demandAlerts}
                onChange={() => handleToggle('demandAlerts')}
                ariaLabel="Toggle Demand Alerts"
              />
            </div>

            {/* 2. Report Notifications */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '50%',
                    backgroundColor: '#E0F2FE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <FileText size={18} color="#005E72" />
                </div>
                <div>
                  <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A' }}>
                    Report Notifications
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', marginTop: '2px' }}>
                    Receive updates on scheduled reports
                  </div>
                </div>
              </div>
              <ToggleSwitch
                id="toggle-report-notifs"
                checked={notificationPreferences.reportNotifications}
                onChange={() => handleToggle('reportNotifications')}
                ariaLabel="Toggle Report Notifications"
              />
            </div>

            {/* 3. System Updates */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '50%',
                    backgroundColor: '#E0F2FE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Settings size={18} color="#005E72" />
                </div>
                <div>
                  <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A' }}>
                    System Updates
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', marginTop: '2px' }}>
                    Get notified about new features and maintenance
                  </div>
                </div>
              </div>
              <ToggleSwitch
                id="toggle-system-updates"
                checked={notificationPreferences.systemUpdates}
                onChange={() => handleToggle('systemUpdates')}
                ariaLabel="Toggle System Updates"
              />
            </div>

            {/* 4. Insights & Tips */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '50%',
                    backgroundColor: '#E0F2FE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Lightbulb size={18} color="#005E72" />
                </div>
                <div>
                  <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A' }}>
                    Insights & Tips
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#64748B', marginTop: '2px' }}>
                    Receive product updates and energy saving tips
                  </div>
                </div>
              </div>
              <ToggleSwitch
                id="toggle-insights-tips"
                checked={notificationPreferences.insightsTips}
                onChange={() => handleToggle('insightsTips')}
                ariaLabel="Toggle Insights & Tips"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

import React, { useEffect, useMemo, useState } from 'react';
import { usePersona, useAuth } from '../context';
import { analyticsService } from '../services/analyticsService';
import { modelService } from '../services/modelService';
import {
  CommercialBuilding,
  ResidentialBuildingProfile,
} from '../types/analytics';
import {
  Calendar,
  Clock,
  MapPin,
  BarChart2,
  Bell,
  FileText,
  Settings,
  Lightbulb,
  Info,
  Landmark,
  Building2,
  Home,
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
  const { user, logout } = useAuth();
  const {
    currentPersona,
    activeEntity,
    setActiveEntity,
    energyUnit,
    setEnergyUnit,
    notificationPreferences,
    setNotificationPreferences,
  } = usePersona();

  // Persona Details Configuration
  const isGov = currentPersona === 'government';
  const isComm = currentPersona === 'commercial';

  const personaLabel = isGov
    ? 'Government & Utilities'
    : isComm
    ? 'Commercial'
    : 'Residential';

  const PersonaIcon = isGov ? Landmark : isComm ? Building2 : Home;

  const locationLabel = isGov
    ? 'Bangalore, India'
    : isComm
    ? 'Mumbai, India'
    : 'New Delhi, India';

  const memberSinceDate = isGov
    ? '12 Jan 2024'
    : isComm
    ? '05 Mar 2024'
    : '18 Jun 2024';

  const lastLoginTimestamp = '19 Oct 2026, 09:15 AM';
  const userName = isGov
    ? 'Government Demo User'
    : isComm
    ? 'Commercial Demo User'
    : 'Residential Demo User';
  const userInitial = userName.charAt(0);
  const [commercialBuildings, setCommercialBuildings] = useState<CommercialBuilding[]>([]);
  const [residentialEntityIds, setResidentialEntityIds] = useState<string[]>([]);
  const [residentialBuildingProfile, setResidentialBuildingProfile] =
    useState<ResidentialBuildingProfile | null>(null);
  const [buildingListLoading, setBuildingListLoading] = useState(false);
  const [buildingProfileLoading, setBuildingProfileLoading] = useState(false);
  const [buildingError, setBuildingError] = useState<string | null>(null);

  useEffect(() => {
    if (currentPersona !== 'household' && currentPersona !== 'commercial') return;

    let cancelled = false;
    setBuildingListLoading(true);
    setBuildingError(null);
    const loadBuildings = async () => {
      try {
        if (currentPersona === 'commercial') {
          const buildings = await analyticsService.getCommercialBuildings();
          if (cancelled) return;
          setCommercialBuildings(buildings);
          const buildingIds = buildings.map((building) => building.buildingId);
          if (buildingIds.length && !buildingIds.includes(activeEntity)) {
            setActiveEntity(buildingIds[0]);
          }
        } else {
          const page = await modelService.getCustomerRecords(200, 0);
          if (cancelled) return;
          const entityIds = Array.from(
            new Set(page.items.map((record) => record.entityId))
          );
          setResidentialEntityIds(entityIds);
          if (entityIds.length && !entityIds.includes(activeEntity)) {
            setActiveEntity(entityIds[0]);
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setBuildingError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load building profiles.'
          );
        }
      } finally {
        if (!cancelled) setBuildingListLoading(false);
      }
    };
    void loadBuildings();
    return () => {
      cancelled = true;
    };
  }, [currentPersona]);

  useEffect(() => {
    if (currentPersona !== 'household' || !activeEntity) {
      setResidentialBuildingProfile(null);
      return;
    }

    let cancelled = false;
    setBuildingProfileLoading(true);
    setBuildingError(null);
    modelService
      .getResidentialBuildingProfile(activeEntity)
      .then((profile) => {
        if (!cancelled) setResidentialBuildingProfile(profile);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setBuildingError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load this residential building profile.'
          );
          setResidentialBuildingProfile(null);
        }
      })
      .finally(() => {
        if (!cancelled) setBuildingProfileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentPersona, activeEntity]);

  const selectedCommercialBuilding = commercialBuildings.find(
    (building) => building.buildingId === activeEntity
  );
  const buildingOptions =
    currentPersona === 'commercial'
      ? commercialBuildings.map((building) => building.buildingId)
      : residentialEntityIds;
  const profileDetails = useMemo(() => {
    if (currentPersona === 'commercial' && selectedCommercialBuilding) {
      const building = selectedCommercialBuilding;
      return [
        ['Building ID', building.buildingId],
        ['General use', building.primarySpaceUsage],
        ['Specific use', building.specificSpaceUsage],
        ['Building type', building.buildingType],
        ['Building area', building.sqm, 'm²'],
        ['Footprint area', building.footprintAreaM2, 'm²'],
        ['Year built', building.yearBuilt],
        ['Grid ID', building.coarseGridId],
        ['IDF', building.idfKw],
        ['Latitude', building.latitude],
        ['Longitude', building.longitude],
        ['Latest observation', building.lastTimestamp],
      ] as Array<[string, string | number | null | undefined, string?]>;
    }
    if (currentPersona === 'household' && residentialBuildingProfile) {
      const building = residentialBuildingProfile;
      return [
        ['Meter / building ID', building.entityId],
        ['Building type', building.buildingType],
        ['Specific use', building.specificUseType],
        ['Use type', building.useType],
        ['Building area', building.buildingAreaM2, 'm²'],
        ['Footprint area', building.footprintAreaM2, 'm²'],
        ['Year built', building.effectiveYearBuilt],
        ['Vintage', building.vintage],
        ['Coarse grid ID', building.gridCoarseId],
        ['Finer grid ID', building.gridFinerId],
        ['IDF', building.idfKw],
        ['Tract ID', building.tractId],
        ['Latitude', building.latitude],
        ['Longitude', building.longitude],
      ] as Array<[string, string | number | null | undefined, string?]>;
    }
    return [];
  }, [currentPersona, residentialBuildingProfile, selectedCommercialBuilding]);

  const formatBuildingValue = (
    value: string | number | null | undefined,
    unit?: string
  ): string => {
    if (value === null || value === undefined || value === '') return 'Not available';
    const formatted =
      typeof value === 'number'
        ? value.toLocaleString(undefined, { maximumFractionDigits: 6 })
        : value;
    return unit ? `${formatted} ${unit}` : formatted;
  };

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
          View your account details and manage your preferences.
        </p>
      </div>

      {/* Centralized Identity Access Card */}
      {user && (
        <section
          aria-label="User identity & authentication details"
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.5rem 1.75rem',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
              marginBottom: '1rem',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A' }}>
                  Authenticated Identity
                </span>
                <span
                  style={{
                    backgroundColor: '#F0FDFA',
                    color: '#0D9488',
                    border: '1px solid #CCFBF1',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    padding: '0.15rem 0.5rem',
                    borderRadius: '999px',
                  }}
                >
                  {user.persona}
                </span>
              </div>
              <p style={{ fontSize: '0.82rem', color: '#64748B', margin: '0.25rem 0 0' }}>
                Secured via signed JWT session and household tenant isolation.
              </p>
            </div>
            <button
              type="button"
              onClick={logout}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                backgroundColor: '#FFF1F2',
                color: '#E11D48',
                border: '1px solid #FFE4E6',
                borderRadius: '8px',
                padding: '0.45rem 0.85rem',
                fontSize: '0.82rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Sign Out
            </button>
          </div>

          <dl
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '1rem',
              margin: 0,
            }}
          >
            <div style={{ borderTop: '1px solid #E2E8F0', paddingTop: '0.75rem' }}>
              <dt style={{ color: '#64748B', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                Username
              </dt>
              <dd style={{ color: '#0F172A', fontSize: '0.92rem', fontWeight: 700, margin: 0 }}>
                {user.username}
              </dd>
            </div>
            <div style={{ borderTop: '1px solid #E2E8F0', paddingTop: '0.75rem' }}>
              <dt style={{ color: '#64748B', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                Email
              </dt>
              <dd style={{ color: '#0F172A', fontSize: '0.92rem', fontWeight: 700, margin: 0 }}>
                {user.email || 'None'}
              </dd>
            </div>
            <div style={{ borderTop: '1px solid #E2E8F0', paddingTop: '0.75rem' }}>
              <dt style={{ color: '#64748B', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                Authorization Role
              </dt>
              <dd style={{ color: '#0F172A', fontSize: '0.92rem', fontWeight: 700, margin: 0 }}>
                {user.role}
              </dd>
            </div>
            <div style={{ borderTop: '1px solid #E2E8F0', paddingTop: '0.75rem' }}>
              <dt style={{ color: '#64748B', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                Authorized Smart Meters
              </dt>
              <dd style={{ color: '#0F172A', fontSize: '0.92rem', fontWeight: 700, margin: 0 }}>
                {user.meters && user.meters.length > 0 ? user.meters.join(', ') : 'None provisioned (Isolated)'}
              </dd>
            </div>
          </dl>
        </section>
      )}

      {(currentPersona === 'household' || currentPersona === 'commercial') && (
        <section
          aria-label="Building profile"
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '14px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.5rem 1.75rem',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
              marginBottom: '1.25rem',
            }}
          >
            <div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
                Selected building details
              </h2>
              <p style={{ fontSize: '0.82rem', color: '#64748B', margin: '0.35rem 0 0' }}>
                Dataset attributes and location for the selected {isComm ? 'building' : 'household'}.
              </p>
            </div>
            {isComm && (
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: '#334155', fontSize: '0.85rem', fontWeight: 700 }}>
                Building ID
                <select
                  aria-label="Select building ID"
                  value={activeEntity}
                  onChange={(event) => setActiveEntity(event.target.value)}
                  disabled={buildingListLoading || buildingOptions.length === 0}
                  style={{ border: '1px solid #CBD5E1', borderRadius: '8px', background: '#FFFFFF', color: '#0B1F33', padding: '0.55rem 0.7rem', minWidth: '150px' }}
                >
                  {buildingOptions.length === 0 && (
                    <option value="">
                      {buildingListLoading ? 'Loading building IDs…' : 'No building IDs'}
                    </option>
                  )}
                  {buildingOptions.map((buildingId) => (
                    <option key={buildingId} value={buildingId}>{buildingId}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {buildingError && (
            <div
              role="alert"
              style={{ border: '1px solid #FECACA', background: '#FEF2F2', color: '#991B1B', borderRadius: '9px', padding: '0.75rem 0.9rem', marginBottom: '1rem' }}
            >
              {buildingError}
            </div>
          )}
          {buildingListLoading || buildingProfileLoading ? (
            <p role="status" style={{ color: '#64748B', margin: 0 }}>
              Loading selected building details…
            </p>
          ) : profileDetails.length ? (
            <dl
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
                gap: '1rem',
                margin: 0,
              }}
            >
              {profileDetails.map(([label, value, unit]) => (
                <div key={label} style={{ borderTop: '1px solid #E2E8F0', paddingTop: '0.75rem' }}>
                  <dt style={{ color: '#64748B', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.3rem' }}>
                    {label}
                  </dt>
                  <dd style={{ color: '#0F172A', fontSize: '0.92rem', fontWeight: 700, margin: 0, overflowWrap: 'anywhere' }}>
                    {formatBuildingValue(value, unit)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : !buildingError ? (
            <p style={{ color: '#64748B', margin: 0 }}>
              No dataset details are available for this building ID.
            </p>
          ) : null}
        </section>
      )}

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
        {/* Left: Avatar + Name + Persona Badge + Location */}
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

            {/* Persona Badge */}
            <div>
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
            </div>

            {/* Location */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                color: '#334155',
                fontSize: '0.88rem',
                fontWeight: 500,
              }}
            >
              <MapPin size={16} color="#64748B" />
              <span>{locationLabel}</span>
            </div>
          </div>
        </div>

        {/* Right: Member Since & Last Login */}
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
          {/* Member Since */}
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
                Member Since
              </div>
              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                {memberSinceDate}
              </div>
            </div>
          </div>

          {/* Last Login */}
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
                Last Login
              </div>
              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                {lastLoginTimestamp}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Bottom Grid: Display Settings & Notification Preferences */}
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

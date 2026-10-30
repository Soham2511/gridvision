import React from 'react';
import { usePersona } from '../context';
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
  const {
    currentPersona,
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
  const userName = 'Rohit Sharma';
  const userInitial = userName.charAt(0);

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

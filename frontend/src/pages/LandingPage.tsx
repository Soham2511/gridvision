import React from 'react';
import { useNavigate } from 'react-router-dom';
import { usePersona, PersonaType } from '../context';
import { TopHeader } from '../layouts/TopHeader';
import {
  Home,
  Building2,
  Map,
  ArrowDownRight,
  ArrowRight,
  Activity,
} from 'lucide-react';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const { setPersona } = usePersona();

  const handleSelectPersona = (persona: PersonaType) => {
    setPersona(persona);
    navigate('/app');
  };

  const personaCards = [
    {
      id: 'household' as PersonaType,
      title: 'Residential',
      description: 'Personal electricity consumption, household demand forecasting, and energy insights.',
      icon: <Home size={18} color="#00A396" />,
      iconBg: 'rgba(0, 163, 150, 0.1)',
    },
    {
      id: 'commercial' as PersonaType,
      title: 'Commercial',
      description: 'Building consumption analytics, peak-hour predictions, and operational forecasting.',
      icon: <Building2 size={18} color="#087EBD" />,
      iconBg: 'rgba(8, 126, 189, 0.1)',
    },
    {
      id: 'government' as PersonaType,
      title: 'Government & Utilities',
      description: 'Regional demand forecasting, grid monitoring, outage alerts, and customer segmentation.',
      icon: <Map size={18} color="#B45309" />,
      iconBg: 'rgba(255, 194, 71, 0.2)',
    },
  ];

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#FBFBFB',
        backgroundImage: `
          linear-gradient(to right, rgba(0, 0, 0, 0.035) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(0, 0, 0, 0.035) 1px, transparent 1px)
        `,
        backgroundSize: '48px 48px',
        backgroundPosition: 'top right',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        color: '#0B1F33',
        fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Top Header with GridVision Branding & Admin Identity */}
      <TopHeader showLogo={true} isAdmin={true} />

      {/* Main Content Area */}
      <main
        style={{
          flex: 1,
          maxWidth: '1240px',
          margin: '0 auto',
          width: '100%',
          padding: '3.5rem 3.5rem 4rem 3.5rem',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        {/* Headline Section */}
        <div style={{ marginBottom: '3.25rem' }}>
          <h1
            style={{
              fontSize: '3.75rem',
              fontWeight: 800,
              lineHeight: 1.12,
              letterSpacing: '-0.03em',
              margin: '0 0 1.25rem 0',
            }}
          >
            <span style={{ display: 'block', color: '#0B1F33' }}>See the signal.</span>
            <span style={{ display: 'block', color: '#00A396' }}>Shape the demand.</span>
          </h1>

          <p
            style={{
              fontSize: '1.05rem',
              color: '#64748B',
              lineHeight: 1.55,
              maxWidth: '520px',
              margin: 0,
            }}
          >
            Explore consumption patterns and demand forecasts through a workspace shaped around your role.
          </p>
        </div>

        {/* Question Subheader */}
        <h2
          style={{
            fontSize: '1.35rem',
            fontWeight: 700,
            color: '#0B1F33',
            margin: '0 0 1.75rem 0',
            letterSpacing: '-0.01em',
          }}
        >
          Where would you like to begin?
        </h2>

        {/* Three Persona Cards Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '1.75rem',
          }}
        >
          {personaCards.map((card) => (
            <div
              key={card.id}
              onClick={() => handleSelectPersona(card.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') handleSelectPersona(card.id);
              }}
              style={{
                backgroundColor: '#FFFFFF',
                borderRadius: '14px',
                border: '1px solid rgba(0, 0, 0, 0.07)',
                padding: '2rem 1.75rem 1.75rem 1.75rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                position: 'relative',
                overflow: 'hidden',
                boxShadow: '0 2px 14px rgba(0, 0, 0, 0.03)',
                cursor: 'pointer',
                transition: 'all 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
                minHeight: '230px',
                boxSizing: 'border-box',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-3px)';
                e.currentTarget.style.boxShadow = '0 10px 28px rgba(0, 0, 0, 0.06)';
                e.currentTarget.style.borderColor = 'rgba(0, 163, 150, 0.3)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 2px 14px rgba(0, 0, 0, 0.03)';
                e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.07)';
              }}
            >
              {/* Decorative Concentric Circular Arc on the right side */}
              <div
                style={{
                  position: 'absolute',
                  width: '230px',
                  height: '230px',
                  borderRadius: '50%',
                  border: '1px solid rgba(0, 0, 0, 0.04)',
                  right: '-75px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  pointerEvents: 'none',
                }}
              />

              <div>
                {/* Icon Container */}
                <div
                  style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    backgroundColor: card.iconBg,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '1.75rem',
                  }}
                >
                  {card.icon}
                </div>

                {/* Card Title */}
                <h3
                  style={{
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    color: '#0B1F33',
                    margin: '0 0 0.65rem 0',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {card.title}
                </h3>

                {/* Card Description */}
                <p
                  style={{
                    fontSize: '0.85rem',
                    color: '#64748B',
                    lineHeight: 1.5,
                    margin: 0,
                    maxWidth: '85%',
                  }}
                >
                  {card.description}
                </p>
              </div>

              {/* Action Link: Enter workspace ↘ */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  marginTop: '2.5rem',
                  color: '#00A396',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  transition: 'gap 0.15s ease',
                }}
              >
                <span>Enter workspace</span>
                <ArrowDownRight size={15} strokeWidth={2.2} />
              </div>
            </div>
          ))}
        </div>

        {/* Dedicated Data & Model Health Platform Option */}
        <div style={{ marginTop: '2.25rem' }}>
          <div
            onClick={() => navigate('/health')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') navigate('/health');
            }}
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '14px',
              border: '1px solid rgba(0, 0, 0, 0.07)',
              padding: '1.4rem 1.75rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              boxShadow: '0 2px 14px rgba(0, 0, 0, 0.03)',
              cursor: 'pointer',
              transition: 'all 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
              flexWrap: 'wrap',
              gap: '1.25rem',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 10px 28px rgba(0, 0, 0, 0.06)';
              e.currentTarget.style.borderColor = 'rgba(0, 163, 150, 0.35)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 2px 14px rgba(0, 0, 0, 0.03)';
              e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.07)';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
              <div
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(0, 163, 150, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Activity size={22} color="#00A396" />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                  <h3
                    style={{
                      fontSize: '1.15rem',
                      fontWeight: 700,
                      color: '#0B1F33',
                      margin: 0,
                      letterSpacing: '-0.01em',
                    }}
                  >
                    Data & Model Health
                  </h3>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      backgroundColor: '#E0F2FE',
                      color: '#0284C7',
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      letterSpacing: '0.04em',
                      textTransform: 'uppercase',
                    }}
                  >
                    Platform Monitoring
                  </span>
                </div>
                <p
                  style={{
                    fontSize: '0.84rem',
                    color: '#64748B',
                    margin: '3px 0 0 0',
                    lineHeight: 1.4,
                  }}
                >
                  Monitor data availability, pipeline health, and model performance across the GridVision platform.
                </p>
              </div>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                color: '#00A396',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            >
              <span>View platform health</span>
              <ArrowRight size={15} strokeWidth={2.2} />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

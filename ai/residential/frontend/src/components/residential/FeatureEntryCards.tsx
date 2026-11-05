import React from 'react';
import { ResidentialFeatureId } from '../../types/residentialFeatures';
import { MessageSquare, Home, Zap, TrendingDown } from 'lucide-react';

interface FeatureCardItem {
  id: ResidentialFeatureId;
  title: string;
  tagline: string;
  description: string;
  icon: React.ReactNode;
  badge?: string;
}

interface FeatureEntryCardsProps {
  activeFeature: ResidentialFeatureId;
  onSelectFeature: (id: ResidentialFeatureId) => void;
}

export const FeatureEntryCards: React.FC<FeatureEntryCardsProps> = ({
  activeFeature,
  onSelectFeature,
}) => {
  const features: FeatureCardItem[] = [
    {
      id: 'general_chat',
      title: 'Conversational Assistant',
      tagline: 'Grounded Household Telemetry Chat',
      description: 'Ask questions about your telemetry, historical patterns, and tariff bill explanations.',
      icon: <MessageSquare size={20} color="#00B8A9" />,
    },
    {
      id: 'house_energy_planning',
      title: 'New House Energy Planning',
      tagline: 'Electrical Load & Tier Sizing',
      description: 'Size connected load, maximum demand, equipment schedules, and solar PV for a property.',
      icon: <Home size={20} color="#087EBD" />,
      badge: 'NBC 2016 / IS 732',
    },
    {
      id: 'appliance_analysis',
      title: 'Appliance Lifecycle & Upgrade',
      tagline: 'TCO, Cashflow & Payback',
      description: 'Evaluate purchase, sale, or star-rating upgrade with 7-year cash flows and sensitivity.',
      icon: <Zap size={20} color="#F59E0B" />,
      badge: 'BEE Benchmarks',
    },
    {
      id: 'cost_management',
      title: 'Personalized Cost Management',
      tagline: 'Multi-Tier Strategy Recommendations',
      description: 'Telemetry-grounded behavioral and equipment strategies to lower monthly bills within budget.',
      icon: <TrendingDown size={20} color="#10B981" />,
      badge: 'CEA 0.82 kg/kWh',
    },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '0.85rem' }}>
      {features.map((f) => {
        const isActive = activeFeature === f.id;
        return (
          <button
            key={f.id}
            type="button"
            onClick={() => onSelectFeature(f.id)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              textAlign: 'left',
              padding: '1rem 1.15rem',
              borderRadius: '12px',
              border: isActive ? '2px solid var(--gv-color-smart-teal)' : '1px solid var(--gv-border-subtle)',
              background: isActive ? '#F0FDF4' : 'var(--gv-bg-surface)',
              boxShadow: isActive ? '0 2px 8px rgba(0, 184, 169, 0.15)' : 'var(--gv-shadow-sm)',
              cursor: 'pointer',
              transition: 'all 0.18s ease',
              position: 'relative',
              outline: 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', marginBottom: '0.5rem' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  background: isActive ? '#E0F7F5' : '#F1F5F9',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {f.icon}
              </div>
              {f.badge && (
                <span
                  style={{
                    fontSize: '0.62rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: '#E2E8F0',
                    color: '#475569',
                  }}
                >
                  {f.badge}
                </span>
              )}
            </div>

            <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--gv-color-midnight-navy)' }}>
              {f.title}
            </div>
            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#00A396', marginTop: '0.15rem' }}>
              {f.tagline}
            </div>
            <div
              style={{
                fontSize: '0.74rem',
                color: 'var(--gv-text-secondary)',
                marginTop: '0.35rem',
                lineHeight: 1.4,
              }}
            >
              {f.description}
            </div>
          </button>
        );
      })}
    </div>
  );
};


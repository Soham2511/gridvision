import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { usePersona, PersonaType } from '../context';
import {
  Home,
  BarChart2,
  MessageSquare,
  User,
  ArrowLeftRight,
  ChevronRight,
  ChevronDown,
  LogOut,
  Layers,
  Building2,
  Map,
  PieChart,
  Cpu,
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const { currentPersona, setPersona } = usePersona();
  const navigate = useNavigate();
  const [showPersonaMenu, setShowPersonaMenu] = useState(false);

  const personaLabel =
    currentPersona === 'commercial'
      ? 'Commercial'
      : currentPersona === 'government'
      ? 'Government'
      : 'Residential';

  const navItems = [
    {
      path: '/app',
      label: 'Dashboard',
      icon: <Home size={18} />,
    },
    {
      path: '/app/historical',
      label: 'Historical Insights',
      icon: <BarChart2 size={18} />,
    },
    ...(currentPersona === 'government'
      ? [
          {
            path: '/app/customers',
            label: 'Customer Segmentation',
            icon: <PieChart size={18} />,
          },
        ]
      : []),
    {
      path: '/app/assistant',
      label: 'AI Assistant',
      icon: <MessageSquare size={18} />,
    },
    {
      path: '/models',
      label: 'Models',
      icon: <Cpu size={18} />,
    },
    {
      path: '/profile',
      label: 'Profile',
      icon: <User size={18} />,
    },
  ];

  const handleSelectPersona = (p: PersonaType) => {
    setPersona(p);
    setShowPersonaMenu(false);
    navigate('/app');
  };

  const handleSwitchPersona = () => {
    setPersona(null);
    navigate('/');
  };

  const handleLogout = () => {
    setPersona(null);
    navigate('/');
  };

  return (
    <aside
      style={{
        width: '240px',
        height: '100vh',
        position: 'sticky',
        top: 0,
        backgroundColor: '#071524',
        color: '#FFFFFF',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        borderRight: '1px solid rgba(255, 255, 255, 0.06)',
        zIndex: 50,
        flexShrink: 0,
        boxSizing: 'border-box',
        padding: '1.25rem 1rem',
      }}
    >
      <div>
        {/* Brand Header */}
        <div
          onClick={() => navigate('/')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.5rem 0.5rem 1.75rem 0.5rem',
            cursor: 'pointer',
          }}
        >
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #00A396, #087EBD)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Layers size={18} color="#FFFFFF" />
          </div>
          <div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, letterSpacing: '-0.02em', color: '#FFFFFF', lineHeight: 1.1 }}>
              Grid<span style={{ color: '#00B8A9' }}>Vision</span>
            </div>
            <div style={{ fontSize: '0.58rem', fontWeight: 700, color: '#00B8A9', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: '2px' }}>
              Energy Intelligence
            </div>
          </div>
        </div>

        {/* Primary Navigation Tabs */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/app'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.65rem 0.85rem',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: isActive ? 600 : 500,
                color: isActive ? '#FFFFFF' : 'rgba(255, 255, 255, 0.7)',
                backgroundColor: isActive ? '#005E72' : 'transparent',
                textDecoration: 'none',
                transition: 'all 0.15s ease',
              })}
            >
              <span style={{ display: 'flex', alignItems: 'center' }}>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Middle & Bottom Section: Switch Persona, Active Persona, Logout */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', paddingBottom: '0.5rem' }}>
        {/* Switch Persona Action Row */}
        <button
          type="button"
          onClick={handleSwitchPersona}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.65rem 0.85rem',
            borderRadius: '8px',
            background: 'transparent',
            border: 'none',
            color: 'rgba(255, 255, 255, 0.7)',
            fontSize: '0.82rem',
            fontWeight: 500,
            cursor: 'pointer',
            textAlign: 'left',
            transition: 'color 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#FFFFFF';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'rgba(255, 255, 255, 0.7)';
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <ArrowLeftRight size={16} />
            <span>Switch Persona</span>
          </div>
          <ChevronRight size={15} color="rgba(255, 255, 255, 0.5)" />
        </button>

        {/* Persona Pill / Selector */}
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={() => setShowPersonaMenu(!showPersonaMenu)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.65rem 0.85rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#FFFFFF',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              {currentPersona === 'commercial' ? (
                <Building2 size={16} color="#FFC247" />
              ) : currentPersona === 'government' ? (
                <Map size={16} color="#00B8A9" />
              ) : (
                <Home size={16} color="#21C7D9" />
              )}
              <span>{personaLabel}</span>
            </div>
            <ChevronDown size={15} color="rgba(255, 255, 255, 0.6)" />
          </button>

          {/* Persona Menu Popup */}
          {showPersonaMenu && (
            <div
              style={{
                position: 'absolute',
                bottom: '100%',
                left: 0,
                right: 0,
                marginBottom: '0.5rem',
                backgroundColor: '#0B1F33',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '8px',
                padding: '0.35rem',
                boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
                zIndex: 60,
              }}
            >
              {(['household', 'commercial', 'government'] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => handleSelectPersona(p)}
                  style={{
                    width: '100%',
                    padding: '0.55rem 0.75rem',
                    borderRadius: '6px',
                    border: 'none',
                    background: currentPersona === p ? '#005E72' : 'transparent',
                    color: '#FFFFFF',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    textAlign: 'left',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}
                >
                  {p === 'household' ? 'Residential' : p === 'commercial' ? 'Commercial' : 'Government & Utilities'}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Logout Button */}
        <button
          type="button"
          onClick={handleLogout}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
            padding: '0.65rem 0.85rem',
            borderRadius: '8px',
            background: 'transparent',
            border: 'none',
            color: 'rgba(255, 255, 255, 0.6)',
            fontSize: '0.82rem',
            fontWeight: 500,
            cursor: 'pointer',
            marginTop: '0.5rem',
            textAlign: 'left',
            transition: 'color 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#FFFFFF';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'rgba(255, 255, 255, 0.6)';
          }}
        >
          <LogOut size={16} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};

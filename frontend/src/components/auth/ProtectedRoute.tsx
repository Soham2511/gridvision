import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export interface ProtectedRouteProps {
  children?: React.ReactNode;
  requiredPersona?: 'RESIDENTIAL' | 'COMMERCIAL' | 'GOVERNMENT';
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredPersona }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          height: '100vh',
          width: '100%',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--gv-bg-page, #F8FAFC)',
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              border: '3px solid rgba(0, 163, 150, 0.2)',
              borderTopColor: 'var(--gv-color-smart-teal, #00A396)',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
              margin: '0 auto 1rem',
            }}
          />
          <p style={{ color: 'var(--gv-text-muted, #64748B)', fontSize: '0.88rem' }}>
            Verifying security session...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  }

  if (requiredPersona && user?.persona !== requiredPersona) {
    return (
      <div
        style={{
          padding: '2rem',
          maxWidth: '500px',
          margin: '4rem auto',
          background: '#FFF5F5',
          border: '1px solid #FED7D7',
          borderRadius: '8px',
          color: '#C53030',
        }}
      >
        <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.1rem', fontWeight: 600 }}>Access Restricted</h3>
        <p style={{ margin: 0, fontSize: '0.9rem' }}>
          This feature requires the <strong>{requiredPersona}</strong> persona. Your current persona is{' '}
          <strong>{user?.persona}</strong>.
        </p>
      </div>
    );
  }

  return children ? <>{children}</> : null;
};


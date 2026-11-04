import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { usePersona } from '../context/usePersona';
import { Lock, User as UserIcon, AlertCircle, ArrowRight, Eye, EyeOff, ShieldCheck, Zap } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectPath = searchParams.get('redirect') || '/app';
  const { login } = useAuth();
  const { setPersona } = usePersona();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!identifier.trim() || !password) {
      setError('Please provide your username or email and password.');
      return;
    }

    setIsSubmitting(true);
    try {
      await login({ identifier: identifier.trim(), password });
      setPersona('household');
      const target = redirectPath && redirectPath !== '/profile' ? redirectPath : '/app';
      navigate(target, { replace: true });
    } catch (err: any) {
      setError(err?.message || 'Invalid username, email, or password.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const fillVerifiedAccount = () => {
    setIdentifier('resident');
    setPassword('GridVision@2026');
    setError(null);
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#F8FAFC',
        backgroundImage: `
          linear-gradient(to right, rgba(0, 0, 0, 0.035) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(0, 0, 0, 0.035) 1px, transparent 1px)
        `,
        backgroundSize: '48px 48px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
      }}
    >
      {/* Brand Header */}
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <Link to="/" style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.65rem' }}>
          <div
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              backgroundColor: '#00A396',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#FFFFFF',
              boxShadow: '0 4px 12px rgba(0, 163, 150, 0.25)',
            }}
          >
            <Zap size={22} />
          </div>
          <span style={{ fontSize: '1.45rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>
            Grid<span style={{ color: '#00A396' }}>Vision</span>
          </span>
        </Link>
        <p style={{ marginTop: '0.5rem', color: '#64748B', fontSize: '0.9rem' }}>
          Residential Energy Intelligence & Centralized IAM
        </p>
      </div>

      {/* Login Card */}
      <div
        style={{
          width: '100%',
          maxWidth: '440px',
          backgroundColor: '#FFFFFF',
          borderRadius: '16px',
          border: '1px solid #E2E8F0',
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01)',
          padding: '2.25rem',
        }}
      >
        <div style={{ marginBottom: '1.75rem' }}>
          <h1 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0F172A', margin: '0 0 0.35rem' }}>
            Sign In to Household
          </h1>
          <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0 }}>
            Enter your credentials to access verified smart telemetry and insights.
          </p>
        </div>

        {/* Demo Account Quick-Fill Pill */}
        <div
          onClick={fillVerifiedAccount}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.65rem 0.85rem',
            marginBottom: '1.5rem',
            backgroundColor: '#F0FDFA',
            border: '1px solid #CCFBF1',
            borderRadius: '10px',
            cursor: 'pointer',
            transition: 'background-color 0.15s ease',
          }}
          title="Click to auto-fill verified initial residential credentials"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldCheck size={16} color="#0D9488" />
            <span style={{ fontSize: '0.8rem', color: '#115E59', fontWeight: 600 }}>
              Use Verified Account: <code>resident</code>
            </span>
          </div>
          <span style={{ fontSize: '0.72rem', color: '#0D9488', fontWeight: 700 }}>
            Auto-fill
          </span>
        </div>

        {error && (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.65rem',
              padding: '0.75rem 0.85rem',
              marginBottom: '1.25rem',
              backgroundColor: '#FEF2F2',
              border: '1px solid #FEE2E2',
              borderRadius: '8px',
              color: '#991B1B',
              fontSize: '0.82rem',
              lineHeight: 1.4,
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>{error}</div>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Identifier Input */}
          <div style={{ marginBottom: '1.25rem' }}>
            <label
              htmlFor="identifier"
              style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: '#334155', marginBottom: '0.4rem' }}
            >
              Username or Email
            </label>
            <div style={{ position: 'relative' }}>
              <UserIcon
                size={16}
                color="#94A3B8"
                style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
              />
              <input
                id="identifier"
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="resident or resident@gridvision.local"
                required
                style={{
                  width: '100%',
                  padding: '0.65rem 0.75rem 0.65rem 2.25rem',
                  fontSize: '0.88rem',
                  border: '1px solid #CBD5E1',
                  borderRadius: '8px',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          {/* Password Input */}
          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <label
                htmlFor="password"
                style={{ fontSize: '0.82rem', fontWeight: 600, color: '#334155' }}
              >
                Password
              </label>
            </div>
            <div style={{ position: 'relative' }}>
              <Lock
                size={16}
                color="#94A3B8"
                style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
              />
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                required
                style={{
                  width: '100%',
                  padding: '0.65rem 2.25rem 0.65rem 2.25rem',
                  fontSize: '0.88rem',
                  border: '1px solid #CBD5E1',
                  borderRadius: '8px',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#94A3B8',
                  padding: 0,
                  display: 'flex',
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            style={{
              width: '100%',
              padding: '0.75rem',
              backgroundColor: '#00A396',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: '8px',
              fontSize: '0.9rem',
              fontWeight: 600,
              cursor: isSubmitting ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              opacity: isSubmitting ? 0.75 : 1,
              transition: 'background-color 0.15s ease',
            }}
          >
            {isSubmitting ? 'Authenticating...' : 'Sign In'}
            {!isSubmitting && <ArrowRight size={16} />}
          </button>
        </form>

        <div style={{ marginTop: '1.5rem', textAlign: 'center', borderTop: '1px solid #F1F5F9', paddingTop: '1.25rem' }}>
          <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0 }}>
            Don't have an account?{' '}
            <Link
              to={`/register?redirect=${encodeURIComponent(redirectPath)}`}
              style={{ color: '#00A396', fontWeight: 600, textDecoration: 'none' }}
            >
              Create Account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};


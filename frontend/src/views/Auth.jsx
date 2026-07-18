import React, { useState } from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { Loader2, ShieldCheck } from 'lucide-react';
import { LedgerLogo } from '../components/ui';
import { persistCredential, setCredential } from '../google-auth';

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
    </svg>
  );
}

export default function Auth() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const login = useGoogleLogin({
    // "implicit" flow returns the access_token directly in the browser;
    // we use it to fetch the id_token from Google's userinfo endpoint so
    // the backend can verify it with Google's public keys.
    flow: 'implicit',
    onSuccess: async (tokenResponse) => {
      try {
        // Exchange the access_token for an id_token via Google userinfo
        const res = await fetch(
          `https://www.googleapis.com/oauth2/v3/userinfo`,
          { headers: { Authorization: `Bearer ${tokenResponse.access_token}` } }
        );
        if (!res.ok) throw new Error('Failed to fetch user info from Google');

        // For the backend we send the access_token as Bearer; Google verifies
        // access_tokens at https://oauth2.googleapis.com/tokeninfo
        persistCredential(tokenResponse.access_token);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    },
    onError: (err) => {
      setError(err.error_description || err.error || 'Google sign-in failed');
      setLoading(false);
    },
  });

  const handleDevSignIn = () => {
    setCredential('dev-user');
    sessionStorage.setItem('g_credential', 'dev-user');
  };

  const handleClick = () => {
    setError(null);
    setLoading(true);

    if (import.meta.env.VITE_AUTH_PROVIDER === 'dev') {
      handleDevSignIn();
      return;
    }

    login();
    // loading is reset in onError; onSuccess navigates away via credential change
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <LedgerLogo size={56} className="auth-logo" />
          <h2>Welcome to Ledger</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: 15, fontWeight: 500 }}>
            Your personal AI finance platform
          </p>
        </div>

        {error && <div className="auth-alert error">{error}</div>}

        <button
          id="google-signin-btn"
          type="button"
          onClick={handleClick}
          disabled={loading}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
            width: '100%',
            padding: '14px 20px',
            marginTop: 8,
            borderRadius: 12,
            border: '1.5px solid var(--border)',
            background: 'var(--surface)',
            color: 'var(--text-primary)',
            fontWeight: 600,
            fontSize: 15,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.7 : 1,
            transition: 'background 0.15s, box-shadow 0.15s, transform 0.1s',
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.currentTarget.style.background = 'var(--surface-raised)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.12)';
              e.currentTarget.style.transform = 'translateY(-1px)';
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'var(--surface)';
            e.currentTarget.style.boxShadow = 'none';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          {loading ? <Loader2 size={20} className="spin" /> : <GoogleIcon />}
          {loading ? 'Signing in…' : 'Continue with Google'}
        </button>

        <div style={{
          marginTop: 32,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          color: 'var(--text-muted)',
          fontSize: 12,
          fontWeight: 500,
        }}>
          <ShieldCheck size={14} /> Secure &amp; Encrypted
        </div>
      </div>
    </div>
  );
}

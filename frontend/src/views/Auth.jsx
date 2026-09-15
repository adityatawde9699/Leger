import React, { useEffect, useRef, useState } from 'react';
import { createGoogleSession, saveGoogleSession } from '../googleAuth';
import { Loader2, ShieldCheck } from 'lucide-react';
import { LedgerLogo } from '../components/ui';

export default function Auth() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const googleButtonRef = useRef(null);
  const isDev = import.meta.env.VITE_AUTH_PROVIDER === 'dev';

  useEffect(() => {
    if (isDev) return undefined;

    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      setError('Google login is not configured. Set VITE_GOOGLE_CLIENT_ID.');
      return undefined;
    }

    const renderGoogleButton = () => {
      if (!window.google?.accounts?.id || !googleButtonRef.current) return;

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: ({ credential }) => {
          setError(null);
          try {
            saveGoogleSession(createGoogleSession(credential));
            window.location.reload();
          } catch (err) {
            setError(err.message || 'Google authentication failed.');
          }
        },
      });
      googleButtonRef.current.replaceChildren();
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        logo_alignment: 'left',
        width: String(Math.min(360, googleButtonRef.current.clientWidth || 360)),
      });
    };

    const script = document.getElementById('google-identity-services');
    if (window.google?.accounts?.id) renderGoogleButton();
    else {
      script?.addEventListener('load', renderGoogleButton, { once: true });
      script?.addEventListener('error', () => setError('Unable to load Google login.'), { once: true });
    }

    return () => script?.removeEventListener('load', renderGoogleButton);
  }, [isDev]);

  const handleDevSignIn = () => {
    setLoading(true);
    setError(null);
    const session = {
      access_token: "dev-user",
      user: { email: "dev@ledger.local" },
    };
    localStorage.setItem("dev-session", JSON.stringify(session));
    window.location.reload();
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
        {isDev ? (
          <button type="button" className="btn-primary full-width" onClick={handleDevSignIn} disabled={loading} style={{ marginTop: '8px', padding: '14px' }}>
            {loading ? <Loader2 size={18} className="spin" /> : 'Continue in development mode'}
          </button>
        ) : (
          <div ref={googleButtonRef} style={{ marginTop: 8, minHeight: 44, display: 'flex', justifyContent: 'center' }} />
        )}
        
        <div style={{ marginTop: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12, fontWeight: 500 }}>
          <ShieldCheck size={14} /> Secure & Encrypted
        </div>
      </div>
    </div>
  );
}

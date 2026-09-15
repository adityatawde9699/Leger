import React, { useEffect, useRef, useState } from 'react';
import { createGoogleSession, saveGoogleSession } from '../googleAuth';
import { ArrowUpRight, ChartNoAxesCombined, Loader2, ScanLine, ShieldCheck, Sparkles } from 'lucide-react';
import { LedgerLogo } from '../components/ui';

export default function Auth() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [googleReady, setGoogleReady] = useState(false);
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
      setGoogleReady(true);
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
      <div className="auth-orb auth-orb-one" />
      <div className="auth-orb auth-orb-two" />

      <main className="auth-shell">
        <section className="auth-story">
          <div className="auth-brand">
            <LedgerLogo size={42} />
            <span>Ledger</span>
          </div>

          <div className="auth-story-copy">
            <div className="auth-kicker"><Sparkles size={14} /> Finance, made clear</div>
            <h1>Your money.<br /><span>Finally in focus.</span></h1>
            <p>Track every rupee, spot patterns early, and make confident decisions with one intelligent financial workspace.</p>

            <div className="auth-feature-list">
              <div className="auth-feature"><ChartNoAxesCombined size={18} /><span>Live spending intelligence</span></div>
              <div className="auth-feature"><ScanLine size={18} /><span>Effortless statement imports</span></div>
              <div className="auth-feature"><Sparkles size={18} /><span>Personal AI guidance</span></div>
            </div>
          </div>

          <div className="auth-preview" aria-hidden="true">
            <div className="auth-preview-top">
              <div>
                <span>MONTHLY OVERVIEW</span>
                <strong>₹84,240</strong>
              </div>
              <div className="auth-preview-growth"><ArrowUpRight size={14} /> 12.4%</div>
            </div>
            <div className="auth-preview-chart">
              {[38, 55, 46, 72, 61, 88, 78, 100].map((height, index) => (
                <i key={index} style={{ height: `${height}%` }} />
              ))}
            </div>
            <div className="auth-preview-meta"><span>Income</span><b>₹1,24,500</b><span>Saved</span><b className="positive">₹40,260</b></div>
          </div>

          <div className="auth-story-foot"><ShieldCheck size={15} /> Private by design · Your financial data stays yours</div>
        </section>

        <section className="auth-form-panel">
          <div className="auth-mobile-brand">
            <LedgerLogo size={38} />
            <span>Ledger</span>
          </div>

          <div className="auth-card">
            <div className="auth-header">
              <div className="auth-secure-label"><span /> Secure access</div>
              <h2>Welcome back</h2>
              <p>Sign in to continue to your financial dashboard.</p>
            </div>

            {error && <div className="auth-alert error" role="alert">{error}</div>}
            {isDev ? (
              <button type="button" className="btn-primary auth-dev-button" onClick={handleDevSignIn} disabled={loading}>
                {loading ? <Loader2 size={18} className="spin" /> : 'Continue in development mode'}
              </button>
            ) : (
              <div className={`auth-google-wrap${googleReady ? ' ready' : ''}`}>
                <div ref={googleButtonRef} className="auth-google-button" />
              </div>
            )}

            <div className="auth-trust-note">
              <ShieldCheck size={17} />
              <span>Google verifies your identity.<br />Ledger never sees your password.</span>
            </div>

            <p className="auth-legal">By continuing, you agree to use Ledger responsibly and keep your account secure.</p>
          </div>

          <div className="auth-form-foot"><span>Encrypted connection</span><i /> <span>Privacy-first finance</span></div>
        </section>
      </main>
    </div>
  );
}

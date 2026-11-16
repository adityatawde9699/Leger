import React, { useEffect, useRef, useState } from 'react';
import { createGoogleSession } from '../googleAuth';
import { ChartNoAxesCombined, Loader2, MessageSquare, ScanLine, ShieldCheck } from 'lucide-react';
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
        callback: async ({ credential }) => {
          setError(null);
          try {
            await createGoogleSession(credential);
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
      <main className="auth-shell">
        <section className="auth-story">
          <div className="auth-brand">
            <LedgerLogo size={20} />
            <span>Ledger</span>
          </div>

          <div className="auth-story-copy">
            <h1>Every rupee you earn and spend, <span>in one ruled ledger</span></h1>
            <p>Import bank statements, see where the month went, and keep budgets, goals and GST records in the same place.</p>

            <div className="auth-feature-list">
              <div className="auth-feature"><ScanLine strokeWidth={1.5} /><span>Statement and receipt imports</span></div>
              <div className="auth-feature"><ChartNoAxesCombined strokeWidth={1.5} /><span>Spending by category and merchant</span></div>
              <div className="auth-feature"><MessageSquare strokeWidth={1.5} /><span>Questions answered from your own transactions</span></div>
            </div>
          </div>

          <div className="auth-preview" aria-hidden="true">
            <div className="auth-preview-top">
              <div>
                <span>Closing balance</span>
                <strong>₹84,240</strong>
              </div>
              <div className="auth-preview-growth">1–17 Nov 2026</div>
            </div>
            <div className="auth-preview-rows">
              {[
                ["1 Nov", "Salary", "Income", "+₹1,24,500", true],
                ["3 Nov", "Prestige Lakeside", "Rent", "−₹22,000"],
                ["6 Nov", "BigBasket", "Groceries", "−₹2,340"],
                ["9 Nov", "Airtel Fiber", "Utilities", "−₹1,178"],
                ["12 Nov", "Swiggy", "Dining", "−₹486"],
              ].map(([d, n, c, a, inc]) => (
                <div className="auth-preview-row" key={d + n}>
                  <span className="d">{d}</span><span className="n">{n}</span><span className="c">{c}</span><span className={`a${inc ? " in" : ""}`}>{a}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="auth-story-foot"><ShieldCheck strokeWidth={1.5} /> Your data stays in your account</div>
        </section>

        <section className="auth-form-panel">
          <div className="auth-mobile-brand">
            <LedgerLogo size={20} />
            <span>Ledger</span>
          </div>

          <div className="auth-card">
            <div className="auth-header">
              <h2>Sign in to Ledger</h2>
              <p>Use your Google account. Ledger never sees your password</p>
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

            <p className="auth-legal">By continuing you agree to use Ledger responsibly and keep your account secure.</p>
          </div>

          <div className="auth-form-foot"><span>Encrypted connection</span></div>
        </section>
      </main>
    </div>
  );
}

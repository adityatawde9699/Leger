import React, { useState } from 'react';
import { signInWithPopup } from 'firebase/auth';
import { firebaseAuth, googleProvider } from '../firebase';
import { Loader2, ShieldCheck } from 'lucide-react';
import { LedgerLogo } from '../components/ui';

export default function Auth() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError(null);

    try {
      if (import.meta.env.VITE_AUTH_PROVIDER === 'dev') {
        const session = {
          access_token: "dev-user",
          user: { email: "dev@ledger.local" },
        };
        localStorage.setItem("dev-session", JSON.stringify(session));
        window.location.reload();
        return;
      }

      await signInWithPopup(firebaseAuth, googleProvider);
    } catch (err) {
      setError(err.message || 'An error occurred during authentication.');
    } finally {
      setLoading(false);
    }
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
        <button type="button" className="btn-primary full-width" onClick={handleGoogleSignIn} disabled={loading} style={{ marginTop: '8px', padding: '14px' }}>
          {loading ? <Loader2 size={18} className="spin" /> : 'Continue with Google'}
        </button>
        
        <div style={{ marginTop: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12, fontWeight: 500 }}>
          <ShieldCheck size={14} /> Secure & Encrypted
        </div>
      </div>
    </div>
  );
}

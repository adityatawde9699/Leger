import React, { useState } from 'react';
import { supabase } from '../supabase';
import { Mail, Lock, Loader2, ShieldCheck } from 'lucide-react';
import { LegerLogo } from '../components/ui';

export default function Auth() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      if (import.meta.env.VITE_AUTH_PROVIDER === 'dev') {
        const session = {
          access_token: "dev-user",
          user: { email: email || "dev@ledger.local" },
        };
        localStorage.setItem("dev-session", JSON.stringify(session));
        window.location.reload();
        return;
      }

      if (isLogin) {
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (error) throw error;
      } else {
        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/`,
          },
        });
        if (error) throw error;
        setMessage('Check your email for the confirmation link!');
      }
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
          <LegerLogo size={56} className="auth-logo" />
          <h2>Welcome to Ledger</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: 15, fontWeight: 500 }}>
            Your personal AI finance platform
          </p>
        </div>

        {error && <div className="auth-alert error">{error}</div>}
        {message && <div className="auth-alert success">{message}</div>}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="form-field" style={{ marginBottom: 0 }}>
            <label className="form-label">Email</label>
            <div className="input-prefix-wrap">
              <Mail size={18} className="input-prefix" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                style={{ paddingLeft: 44, background: 'rgba(255,255,255,0.8)' }}
              />
            </div>
          </div>
          
          <div className="form-field" style={{ marginBottom: 0 }}>
            <label className="form-label">Password</label>
            <div className="input-prefix-wrap">
              <Lock size={18} className="input-prefix" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{ paddingLeft: 44, background: 'rgba(255,255,255,0.8)' }}
              />
            </div>
          </div>

          <button type="submit" className="btn-primary full-width" style={{ marginTop: '8px', padding: '14px' }} disabled={loading}>
            {loading ? <Loader2 size={18} className="spin" /> : isLogin ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <div style={{ marginTop: '32px', textAlign: 'center' }}>
          <button 
            type="button" 
            className="btn-link" 
            onClick={() => setIsLogin(!isLogin)}
          >
            {isLogin ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
          </button>
        </div>
        
        <div style={{ marginTop: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12, fontWeight: 500 }}>
          <ShieldCheck size={14} /> Secure & Encrypted
        </div>
      </div>
    </div>
  );
}

import React from "react";
import { X } from "lucide-react";

// ── Toast ──────────────────────────────────────────────────────────────────────
const ToastCtx = React.createContext(null);

export function useToast() {
  return React.useContext(ToastCtx);
}

let _toastId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = React.useState([]);

  const add = React.useCallback((message, type = "info", duration = 3500) => {
    const id = ++_toastId;
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), duration);
  }, []);

  const remove = (id) => setToasts((t) => t.filter((x) => x.id !== id));

  const DOT = { success: 'var(--positive)', error: 'var(--negative)', info: 'var(--text-muted)' };

  return (
    <ToastCtx.Provider value={add}>
      {children}
      <div className="toast-container">
        {toasts.map(({ id, message, type }) => (
          <div key={id} role={type === 'error' ? 'alert' : 'status'} className="toast">
            <span className="status-dot" style={{ background: DOT[type] || DOT.info }} aria-hidden="true" />
            <span style={{ flex: 1 }}>{message}</span>
            <button className="toast-close" onClick={() => remove(id)} aria-label="Dismiss">
              <X size={14} strokeWidth={1.5} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────────
export function Skeleton({ width = "100%", height = 20, radius = 8 }) {
  return (
    <div
      aria-hidden="true"
      style={{
        width, height, borderRadius: radius,
        background: 'var(--surface-secondary)',
        animation: 'skeleton-pulse 1.6s var(--ease) infinite alternate',
      }}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Skeleton height={13} width="40%" radius={6} />
        <Skeleton height={16} width={16} radius={4} />
      </div>
      <Skeleton height={36} width="65%" radius={8} />
      <Skeleton height={12} width="35%" radius={6} />
    </div>
  );
}

// ── Empty State ────────────────────────────────────────────────────────────────
export function EmptyState({ icon, title, subtitle }) {
  return (
    <div style={{ textAlign: 'center', padding: '56px 24px' }}>
      {icon && <div style={{ display: 'grid', placeItems: 'center', width: 40, height: 40, margin: '0 auto 16px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface-secondary)', color: 'var(--text-muted)' }}>{icon}</div>}
      <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>{title}</div>
      {subtitle && <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{subtitle}</div>}
    </div>
  );
}

// ── Error ──────────────────────────────────────────────────────────────────────
export function ErrorMsg({ message }) {
  if (!message) return null;
  return (
    <div role="alert" className="error-msg">
      {message}
    </div>
  );
}

export function LedgerLogo({ size = 20, className = "" }) {
  // Ledger mark: a flat lime page with an "L" and two ruled entry lines in ink.
  // One solid color, no tile gradient, no glow.
  return (
    <svg className={`logo-icon ${className}`} width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" style={{ flexShrink: 0, display: 'block' }}>
      <rect width="20" height="20" rx="5" fill="var(--primary)" />
      <path d="M6 5v10h4" stroke="var(--primary-ink)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d="M12 11.5h3M12 15h3" stroke="var(--primary-ink)" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

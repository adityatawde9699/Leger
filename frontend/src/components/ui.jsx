import React from "react";

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

  const TYPE_STYLES = {
    success: { background: '#A8FF2F', color: '#0A0A0B', icon: '✓' },
    error:   { background: 'var(--accent)', color: '#FFFFFF', icon: '✕' },
    info:    { background: '#26262D', color: '#FFFFFF', icon: 'ℹ' },
  };

  return (
    <ToastCtx.Provider value={add}>
      {children}
      <div className="toast-container">
        {toasts.map(({ id, message, type }) => {
          const s = TYPE_STYLES[type] || TYPE_STYLES.info;
          return (
            <div
              key={id}
              role="alert"
              className="toast"
              style={{
                background: s.background,
                color: s.color,
                boxShadow: type === 'success' ? '0 10px 30px rgba(168, 255, 47, 0.2)' : 'var(--shadow)'
              }}
            >
              <div style={{ width: 24, height: 24, borderRadius: '6px', background: 'rgba(0,0,0,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, flexShrink: 0 }}>
                {s.icon}
              </div>
              <span style={{ flex: 1 }}>{message}</span>
              <button
                onClick={() => remove(id)}
                aria-label="Dismiss"
                style={{ background: 'none', border: 'none', color: 'inherit', opacity: 0.7, cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1 }}
              >
                ✕
              </button>
            </div>
          );
        })}
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
        background: 'linear-gradient(90deg, #1C1C21 25%, #26262D 50%, #1C1C21 75%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s infinite',
      }}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Skeleton height={13} width="40%" radius={6} />
        <Skeleton height={36} width={36} radius={10} />
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
      <div style={{ fontSize: 40, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>{title}</div>
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

// ── Query gate ─────────────────────────────────────────────────────────────────
// Wraps a TanStack Query result: shows the skeleton while loading, an error
// message with a retry button on failure, or the children once data is ready.
export function QueryGate({ loading, error, onRetry, skeleton, children }) {
  if (loading) return skeleton ?? <CardSkeleton />;
  if (error) {
    return (
      <div style={{ textAlign: "center", padding: "48px 24px" }}>
        <ErrorMsg message={error.message || "Something went wrong."} />
        {onRetry && (
          <button className="btn-secondary" style={{ marginTop: 12 }} onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }
  return children;
}

export function LedgerLogo({ size = 38, className = "" }) {
  // Ledger mark: a bold "L" monogram beside an ascending 3-bar chart (growth /
  // ledger entries). The tallest bar is crimson — the lime + crimson identity.
  const s = size * 0.6;
  return (
    <div
      className={`logo-icon ${className}`}
      style={{
        width: size,
        height: size,
        background: 'linear-gradient(135deg, var(--primary), var(--primary-hover))',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: size > 48 ? '16px' : '10px',
        boxShadow: '0 4px 15px var(--primary-glow)',
        flexShrink: 0,
      }}
    >
      <svg width={s} height={s} viewBox="0 0 32 32" fill="none" aria-hidden="true">
        {/* "L" monogram */}
        <path
          d="M9 6.5 V22.5 H15.5"
          stroke="var(--bg)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Ascending bars — baseline aligns to the foot of the L */}
        <rect x="17.6" y="18"  width="2.8" height="4.5" rx="1.2" fill="var(--bg)" />
        <rect x="22.1" y="14"  width="2.8" height="8.5" rx="1.2" fill="var(--bg)" />
        <rect x="26.6" y="9.5" width="2.8" height="13"  rx="1.2" fill="var(--accent)" />
      </svg>
    </div>
  );
}


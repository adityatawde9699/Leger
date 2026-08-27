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
    success: { background: '#059669', icon: '✓' },
    error:   { background: '#e11d48', icon: '✕' },
    info:    { background: '#4f46e5', icon: 'ℹ' },
  };

  return (
    <ToastCtx.Provider value={add}>
      {children}
      <div
        aria-live="polite"
        style={{
          position: 'fixed', bottom: 32, right: 32,
          display: 'flex', flexDirection: 'column', gap: 12,
          zIndex: 9999, pointerEvents: 'none',
        }}
      >
        {toasts.map(({ id, message, type }) => {
          const s = TYPE_STYLES[type] || TYPE_STYLES.info;
          return (
            <div
              key={id}
              role="alert"
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                minWidth: 300, maxWidth: 420,
                padding: '14px 18px', borderRadius: 16,
                background: s.background, color: 'white',
                fontSize: 15, fontWeight: 600,
                boxShadow: `0 12px 32px ${s.background}40`,
                animation: 'fadeSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                pointerEvents: 'auto',
              }}
            >
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, flexShrink: 0 }}>
                {s.icon}
              </div>
              <span style={{ flex: 1 }}>{message}</span>
              <button
                onClick={() => remove(id)}
                aria-label="Dismiss"
                style={{ background: 'none', border: 'none', color: 'white', opacity: 0.7, cursor: 'pointer', fontSize: 16, padding: 0, lineHeight: 1 }}
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
        background: 'linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%)',
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
    <div role="alert" style={{
      padding: '12px 16px', borderRadius: 12, fontSize: 14, fontWeight: 600,
      background: '#fff1f2', color: '#e11d48', border: '1px solid #fecdd3',
    }}>
      {message}
    </div>
  );
}

export function LegerLogo({ size = 38, className = "" }) {
  return (
    <div 
      className={`logo-icon ${className}`} 
      style={{ 
        width: size, 
        height: size, 
        background: 'linear-gradient(135deg, var(--accent), #c084fc)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: '10px',
        boxShadow: '0 4px 12px rgba(79, 70, 229, 0.3)'
      }}
    >
      <svg 
        width={size * 0.55} 
        height={size * 0.55} 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="white" 
        strokeWidth="2.5" 
        strokeLinecap="round" 
        strokeLinejoin="round"
      >
        {/* The 'L' representing the Ledger */}
        <path d="M6 4v14a2 2 0 0 0 2 2h12" />
        {/* The upward growth node */}
        <path d="M12 14l4-4 4 4" />
        <path d="M16 10V4" />
      </svg>
    </div>
  );
}


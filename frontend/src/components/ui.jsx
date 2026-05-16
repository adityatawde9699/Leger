import React from "react";

// ── Toast context ─────────────────────────────────────────────────────────────
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

  return (
    <ToastCtx.Provider value={add}>
      {children}
      <div className="toast-container" aria-live="polite">
        {toasts.map(({ id, message, type }) => (
          <div key={id} className={`toast toast-${type}`} role="alert">
            <span>{message}</span>
            <button className="toast-close" onClick={() => remove(id)} aria-label="Dismiss">✕</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────────────────
export function Skeleton({ width = "100%", height = 20, radius = 6 }) {
  return (
    <div
      className="skeleton"
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Skeleton height={14} width="40%" />
      <Skeleton height={32} width="60%" />
      <Skeleton height={12} width="30%" />
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────
export function EmptyState({ icon, title, subtitle }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {subtitle && <div className="empty-state-sub">{subtitle}</div>}
    </div>
  );
}

// ── Error message ─────────────────────────────────────────────────────────────
export function ErrorMsg({ message }) {
  if (!message) return null;
  return <div className="error-msg" role="alert">{message}</div>;
}

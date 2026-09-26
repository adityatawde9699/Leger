import React from "react";

export default function CurrencyMismatchNotice({ title, onNavigate }) {
  return (
    <div className="view-dashboard">
      <div className="page-title-block">
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle">Ledger found account currencies that differ from your currency setting.</p>
      </div>
      <div className="card" style={{ padding: 24 }}>
        <h2 style={{ marginTop: 0, color: "var(--text-primary)" }}>Totals are paused until currencies match</h2>
        <p style={{ color: "var(--text-secondary)", lineHeight: 1.6 }}>
          Ledger cannot convert currencies. Combining these accounts would give a misleading balance, chart, or recommendation. Review the currency on each account and your setting before using analysis.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="btn-primary" onClick={() => onNavigate?.("accounts")}>Review accounts</button>
          <button className="btn-secondary" onClick={() => onNavigate?.("profile")}>Currency setting</button>
        </div>
      </div>
    </div>
  );
}

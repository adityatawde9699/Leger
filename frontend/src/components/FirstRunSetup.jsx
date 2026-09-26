import React from "react";
import { apiFetch, money, setCurrencyPreference, setRegionPreference } from "../lib";
import { useToast } from "./ui";
import { ArrowLeft, ArrowRight, Check, Wallet } from "lucide-react";

const REGIONS = [
  ["IN", "India"], ["US", "United States"], ["GB", "United Kingdom"],
  ["CA", "Canada"], ["AU", "Australia"], ["SG", "Singapore"],
  ["AE", "United Arab Emirates"], ["JP", "Japan"], ["CH", "Switzerland"],
  ["CN", "China"], ["HK", "Hong Kong"], ["OTHER", "Other / prefer not to say"],
];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "CAD", "AUD", "JPY", "CHF", "CNY", "HKD"];
const STEPS = ["Your setup", "An account", "A goal", "Start using Ledger"];

export default function FirstRunSetup({ initialProfile, accounts = [], goals = [], onProfileUpdated, onDone, onAddActivity }) {
  const toast = useToast();
  const [step, setStep] = React.useState(0);
  const [saving, setSaving] = React.useState(false);
  const [basics, setBasics] = React.useState({
    region: initialProfile?.region || "IN",
    currency_preference: initialProfile?.currency_preference || "INR",
    income_pattern: initialProfile?.income_pattern || "not_sure",
  });
  const [account, setAccount] = React.useState({ name: "", account_type: "savings", institution: "", balance: "" });
  const [goal, setGoal] = React.useState({ name: "", goal_type: "emergency_fund", target_amount: "", deadline: "" });
  const [createdAccount, setCreatedAccount] = React.useState(false);
  const [createdGoal, setCreatedGoal] = React.useState(false);

  const persistProfile = async (completed) => {
    const saved = await apiFetch("/profile", {
      method: "PUT",
      body: JSON.stringify({
        display_name: initialProfile?.display_name || null,
        currency_preference: basics.currency_preference,
        region: basics.region,
        income_pattern: basics.income_pattern,
        onboarding_completed: completed,
      }),
    });
    setCurrencyPreference(saved.currency_preference);
    setRegionPreference(saved.region);
    onProfileUpdated?.(saved);
    return saved;
  };

  const next = async () => {
    setSaving(true);
    try {
      if (step === 0) await persistProfile(false);
      setStep((current) => Math.min(STEPS.length - 1, current + 1));
    } catch (error) { toast(error.message, "error"); }
    finally { setSaving(false); }
  };

  const saveAccount = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/accounts", {
        method: "POST",
        body: JSON.stringify({ ...account, balance: account.balance || "0", currency: basics.currency_preference }),
      });
      setCreatedAccount(true);
      toast("Account added", "success");
      setStep(2);
    } catch (error) { toast(error.message, "error"); }
    finally { setSaving(false); }
  };

  const saveGoal = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await apiFetch("/goals", {
        method: "POST",
        body: JSON.stringify({ ...goal, current_amount: "0", deadline: goal.deadline || null, status: "active" }),
      });
      setCreatedGoal(true);
      toast("Goal created", "success");
      setStep(3);
    } catch (error) { toast(error.message, "error"); }
    finally { setSaving(false); }
  };

  const finish = async (startActivity = false) => {
    setSaving(true);
    try {
      await persistProfile(true);
      onDone?.();
      if (startActivity) onAddActivity?.();
    } catch (error) { toast(error.message, "error"); }
    finally { setSaving(false); }
  };

  return (
    <section className="card" aria-labelledby="setup-title" style={{ marginBottom: 20, borderTop: "3px solid var(--primary)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 12, display: "grid", placeItems: "center", color: "var(--primary)", background: "var(--positive-soft)" }}><Wallet size={20} /></div>
        <div style={{ flex: 1 }}>
          <div id="setup-title" style={{ color: "var(--text-primary)", fontSize: 18, fontWeight: 800 }}>Set up Ledger for you</div>
          <div style={{ color: "var(--text-muted)", fontSize: 12 }}>Step {step + 1} of {STEPS.length} · Optional steps can be skipped</div>
        </div>
        <button className="btn-secondary" onClick={() => finish()} disabled={saving}>Skip setup</button>
      </div>
      <div aria-hidden="true" style={{ display: "grid", gridTemplateColumns: `repeat(${STEPS.length}, 1fr)`, gap: 5, margin: "14px 0 18px" }}>
        {STEPS.map((label, index) => <div key={label} style={{ height: 4, borderRadius: 4, background: index <= step ? "var(--primary)" : "var(--surface-secondary)" }} />)}
      </div>

      {step === 0 && <div>
        <h2 style={{ margin: "0 0 6px", fontSize: 15, color: "var(--text-primary)" }}>{STEPS[0]}</h2>
          <p style={{ margin: "0 0 14px", fontSize: 12, lineHeight: 1.5, color: "var(--text-secondary)" }}>Choose your region, preferred display currency, and income pattern. Ledger keeps source currencies on records and converts displayed values using reference rates.</p>
        <div className="form-grid-2">
          <label className="form-field"><span className="form-label">Country or region</span><select value={basics.region} onChange={(event) => setBasics((value) => ({ ...value, region: event.target.value }))}>{REGIONS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
          <label className="form-field"><span className="form-label">Currency used for your records</span><select value={basics.currency_preference} onChange={(event) => setBasics((value) => ({ ...value, currency_preference: event.target.value }))}>{CURRENCIES.map((currency) => <option key={currency} value={currency}>{currency}</option>)}</select></label>
        </div>
        <label className="form-field" style={{ marginTop: 8 }}><span className="form-label">How predictable is your income?</span><select value={basics.income_pattern} onChange={(event) => setBasics((value) => ({ ...value, income_pattern: event.target.value }))}><option value="regular">Mostly regular</option><option value="irregular">Irregular or freelance</option><option value="mixed">A mix of regular and variable</option><option value="not_sure">Not sure yet</option></select></label>
        <button className="btn-primary" style={{ marginTop: 16 }} onClick={next} disabled={saving}>{saving ? "Saving…" : "Continue"} <ArrowRight size={15} /></button>
      </div>}

      {step === 1 && <div>
        <h2 style={{ margin: "0 0 6px", fontSize: 15, color: "var(--text-primary)" }}>{accounts.length || createdAccount ? "Your account is ready" : "Add an account (optional)"}</h2>
        {accounts.length || createdAccount ? <><p style={{ color: "var(--text-secondary)", fontSize: 12 }}>You can import a statement and connect transactions to an account later.</p><button className="btn-primary" onClick={() => setStep(2)}>Continue <ArrowRight size={15} /></button></> : <form onSubmit={saveAccount}>
          <p style={{ margin: "0 0 12px", fontSize: 12, lineHeight: 1.5, color: "var(--text-secondary)" }}>A starting balance is a snapshot, not a transaction. You can reconcile it with a bank balance later.</p>
          <div className="form-grid-2"><label className="form-field"><span className="form-label">Account name</span><input required maxLength={128} placeholder="e.g. Main checking" value={account.name} onChange={(event) => setAccount((value) => ({ ...value, name: event.target.value }))} /></label><label className="form-field"><span className="form-label">Account type</span><select value={account.account_type} onChange={(event) => setAccount((value) => ({ ...value, account_type: event.target.value }))}><option value="savings">Savings</option><option value="current">Checking / current</option><option value="wallet">Wallet</option><option value="cash">Cash</option><option value="credit">Credit card</option></select></label></div>
          <div className="form-grid-2"><label className="form-field"><span className="form-label">Bank or institution (optional)</span><input maxLength={128} value={account.institution} onChange={(event) => setAccount((value) => ({ ...value, institution: event.target.value }))} /></label><label className="form-field"><span className="form-label">Current balance ({basics.currency_preference})</span><input required type="number" step="0.01" value={account.balance} onChange={(event) => setAccount((value) => ({ ...value, balance: event.target.value }))} /></label></div>
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}><button className="btn-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save account"}</button><button className="btn-secondary" type="button" onClick={() => setStep(2)}>Skip</button></div>
        </form>}
      </div>}

      {step === 2 && <div>
        <h2 style={{ margin: "0 0 6px", fontSize: 15, color: "var(--text-primary)" }}>{goals.length || createdGoal ? "Your goal is ready" : "Choose one goal (optional)"}</h2>
        {goals.length || createdGoal ? <><p style={{ color: "var(--text-secondary)", fontSize: 12 }}>You can update progress or add another goal from Goals.</p><button className="btn-primary" onClick={() => setStep(3)}>Continue <ArrowRight size={15} /></button></> : <form onSubmit={saveGoal}>
          <p style={{ margin: "0 0 12px", fontSize: 12, lineHeight: 1.5, color: "var(--text-secondary)" }}>A goal gives your money picture a purpose. You can add a target and deadline later too.</p>
          <div className="form-grid-2"><label className="form-field"><span className="form-label">Goal</span><input required maxLength={128} placeholder="e.g. Emergency fund" value={goal.name} onChange={(event) => setGoal((value) => ({ ...value, name: event.target.value }))} /></label><label className="form-field"><span className="form-label">Goal type</span><select value={goal.goal_type} onChange={(event) => setGoal((value) => ({ ...value, goal_type: event.target.value }))}><option value="emergency_fund">Emergency fund</option><option value="debt_payoff">Debt payoff</option><option value="savings">Savings</option><option value="custom">Other</option></select></label></div>
          <div className="form-grid-2"><label className="form-field"><span className="form-label">Target amount ({basics.currency_preference})</span><input required min="0.01" step="0.01" type="number" value={goal.target_amount} onChange={(event) => setGoal((value) => ({ ...value, target_amount: event.target.value }))} /></label><label className="form-field"><span className="form-label">Target date (optional)</span><input type="date" value={goal.deadline} onChange={(event) => setGoal((value) => ({ ...value, deadline: event.target.value }))} /></label></div>
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}><button className="btn-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save goal"}</button><button className="btn-secondary" type="button" onClick={() => setStep(3)}>Skip</button></div>
        </form>}
      </div>}

      {step === 3 && <div>
        <h2 style={{ margin: "0 0 6px", fontSize: 15, color: "var(--text-primary)" }}>Start with the data you have</h2>
        <p style={{ margin: "0 0 14px", fontSize: 12, lineHeight: 1.5, color: "var(--text-secondary)" }}>Add a transaction, paste a bank message, or import a statement. Ledger will show how much history it has before drawing conclusions.</p>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}><button className="btn-primary" onClick={() => finish(true)} disabled={saving}>{saving ? "Finishing…" : "Add or import activity"} <ArrowRight size={15} /></button><button className="btn-secondary" onClick={() => finish()} disabled={saving}><Check size={15} /> Finish for now</button></div>
        <div style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 10 }}>Account: {account.name || accounts[0]?.name || "not added"} · Goal: {goal.name || (goals[0] ? money(goals[0].target_amount) : "not added")}</div>
      </div>}

      {step > 0 && <button className="btn-secondary" style={{ marginTop: 14 }} onClick={() => setStep((current) => Math.max(0, current - 1))}><ArrowLeft size={14} /> Back</button>}
    </section>
  );
}

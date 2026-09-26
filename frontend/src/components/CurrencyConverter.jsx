import React from "react";
import { ArrowRightLeft, RefreshCw } from "lucide-react";
import { apiFetch, money } from "../lib";

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AUD", "CAD", "CHF", "JPY", "SGD", "AED", "ZAR"];

export default function CurrencyConverter({ defaultCurrency = "INR" }) {
  const [amount, setAmount] = React.useState("1000");
  const [base, setBase] = React.useState(defaultCurrency);
  const [quote, setQuote] = React.useState(defaultCurrency === "INR" ? "USD" : "INR");
  const [result, setResult] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  const convert = async (event) => {
    event?.preventDefault();
    setLoading(true); setError("");
    try {
      setResult(await apiFetch(`/currency/convert?amount=${encodeURIComponent(amount)}&base=${base}&quote=${quote}`));
    } catch (err) { setResult(null); setError(err.message || "Could not load a reference rate"); }
    finally { setLoading(false); }
  };

  const swap = () => { setBase(quote); setQuote(base); setResult(null); };

  return (
    <section className="card currency-converter" aria-label="Currency converter">
      <div className="chart-card-header">
        <div><div className="chart-title">Currency converter</div><div className="chart-subtitle">Reference rate only · does not change Ledger records</div></div>
        <ArrowRightLeft size={18} style={{ color: "var(--primary)" }} />
      </div>
      <form className="currency-converter-form" onSubmit={convert}>
        <label><span>Amount</span><input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label><span>From</span><select value={base} onChange={(e) => { setBase(e.target.value); setResult(null); }}>{CURRENCIES.map((code) => <option key={code}>{code}</option>)}</select></label>
        <button className="currency-swap" type="button" onClick={swap} aria-label="Swap currencies"><ArrowRightLeft size={15} /></button>
        <label><span>To</span><select value={quote} onChange={(e) => { setQuote(e.target.value); setResult(null); }}>{CURRENCIES.map((code) => <option key={code}>{code}</option>)}</select></label>
        <button className="btn-primary currency-convert-button" type="submit" disabled={loading}>{loading ? <RefreshCw size={15} className="spin" /> : "Convert"}</button>
      </form>
      {error && <div className="currency-converter-error" role="alert">{error}</div>}
      {result && <div className="currency-converter-result"><strong>{money(result.amount, result.base)} = {money(result.converted, result.quote)}</strong><span>1 {result.base} = {Number(result.rate).toFixed(6)} {result.quote}{result.date ? ` · rate dated ${result.date}` : ""}</span></div>}
    </section>
  );
}

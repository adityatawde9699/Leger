// ── API Base & helpers ────────────────────────────────────────────────────────
export const API_BASE = import.meta.env.PROD ? "/api" : (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000");
let currentToken = import.meta.env.VITE_AUTH_PROVIDER === "dev"
  ? (import.meta.env.VITE_DEV_AUTH_TOKEN || "dev-user")
  : null;

export function setAuthToken(token) {
  currentToken = token;
}

const CURRENCY_STORAGE_KEY = "ledger-display-currency";
const RATE_STORAGE_KEY = "ledger-display-rates";

export function setCurrencyPreference(currency) {
  if (!currency || typeof currency !== "string") return;
  localStorage.setItem(CURRENCY_STORAGE_KEY, currency);
  window.dispatchEvent(new Event("ledger-currency-updated"));
}

export function setDisplayRates(base, rates, date = null) {
  if (!base || !rates) return;
  localStorage.setItem(RATE_STORAGE_KEY, JSON.stringify({ base, rates, date, savedAt: Date.now() }));
  window.dispatchEvent(new Event("ledger-currency-updated"));
}

function convertDisplayAmount(value, sourceCurrency, targetCurrency) {
  if (!sourceCurrency || sourceCurrency === targetCurrency) return Number(value || 0);
  try {
    const saved = JSON.parse(localStorage.getItem(RATE_STORAGE_KEY) || "null");
    if (!saved || saved.base !== sourceCurrency) return Number(value || 0);
    const sourceRate = Number(saved.rates?.[sourceCurrency] || 1);
    const targetRate = Number(saved.rates?.[targetCurrency]);
    if (!Number.isFinite(targetRate) || !sourceRate) return Number(value || 0);
    return Number(value || 0) * targetRate / sourceRate;
  } catch { return Number(value || 0); }
}

export function setRegionPreference(region) {
  if (!region || typeof region !== "string") return;
  localStorage.setItem("ledger-region", region);
}

export function getCurrencyPreference() {
  const currency = localStorage.getItem(CURRENCY_STORAGE_KEY);
  return /^[A-Z]{3}$/.test(currency || "") ? currency : "INR";
}

export function getRecordCurrency() {
  const currency = localStorage.getItem("ledger-record-currency");
  return /^[A-Z]{3}$/.test(currency || "") ? currency : "INR";
}

function getLocalePreference() {
  const locales = { IN: "en-IN", US: "en-US", GB: "en-GB", CA: "en-CA", AU: "en-AU", SG: "en-SG", AE: "en-AE", JP: "ja-JP", CH: "de-CH", CN: "zh-CN", HK: "zh-HK" };
  return locales[localStorage.getItem("ledger-region") || "IN"] || "en";
}

function getToken() {
  return currentToken;
}

export function authHeaders(extra = {}) {
  return {
    ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    ...extra,
  };
}

export async function apiFetch(path, opts = {}) {
  const isFormData = opts.body instanceof FormData;
  const requestOptions = {
    ...opts,
    credentials: "include",
    headers: {
      ...authHeaders(),
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(opts.headers || {}),
    },
  };
  let res = await fetch(`${API_BASE}${path}`, requestOptions);
  if (res.status === 428 && import.meta.env.VITE_AUTH_PROVIDER !== "dev") {
    const { reauthenticate } = await import("./googleAuth");
    await reauthenticate();
    res = await fetch(`${API_BASE}${path}`, requestOptions);
  }
  if (!res.ok) {
    if (res.status === 401 && import.meta.env.VITE_AUTH_PROVIDER !== "dev") {
      window.dispatchEvent(new Event("ledger-session-expired"));
    }
    const responseText = await res.text();
    let message = responseText;
    try {
      const parsed = JSON.parse(responseText);
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch { /* use response text */ }
    throw new Error(message || `HTTP ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("text/event-stream")) return res;
  return res.json();
}

// ── Query keys ───────────────────────────────────────────────────────────────
export const KEYS = {
  transactions:  (params) => ["transactions", params],
  budgets:       ()       => ["budgets"],
  summary:       (month)  => ["summary", month],
  conversations: ()       => ["conversations"],
  messages:      (id)     => ["messages", id],
  importJob:     (id)     => ["importJob", id],
};

// ── Constants shared across components (expanded to 18 categories) ────────────
export const CATEGORIES = [
  "Housing", "Groceries", "Transport", "Dining", "Subscriptions",
  "Shopping", "Health", "Utilities", "Entertainment",
  "Education", "Insurance", "Investments", "Transfers", "Taxes", "Fees",
  "Other", "Salary", "Freelance",
];

export const EXPENSE_CATEGORIES = [
  "Housing", "Groceries", "Transport", "Dining", "Subscriptions",
  "Shopping", "Health", "Utilities", "Entertainment",
  "Education", "Insurance", "Investments", "Transfers", "Taxes", "Fees",
  "Other",
];

export const INCOME_CATEGORIES = ["Salary", "Freelance", "Other"];

// Distinct per-category hues so charts don't collapse different categories into
// the same color. Tuned for the near-black (#0A0A0B) dark surface: bright enough
// to read, evenly spaced around the hue wheel. Semantics are preserved where it
// matters — income (Salary/Freelance) stays green/positive, Taxes/Fees stay red.
export const CATEGORY_COLORS = {
  Housing:       "#60A5FA", // blue
  Groceries:     "#A8FF2F", // lime
  Transport:     "#FBBF24", // amber
  Dining:        "#FB7185", // rose
  Subscriptions: "#C084FC", // violet
  Shopping:      "#F472B6", // pink
  Health:        "#2DD4BF", // teal
  Utilities:     "#94A3B8", // slate
  Entertainment: "#FB923C", // orange
  Education:     "#818CF8", // indigo
  Insurance:     "#4ADE80", // green
  Investments:   "#22D3EE", // cyan
  Transfers:     "#A1A1AA", // zinc
  Taxes:         "#F87171", // red
  Fees:          "#E879F9", // fuchsia
  Other:         "#64748B", // gray
  Salary:        "#34D399", // emerald (income)
  Freelance:     "#FCD34D", // gold (income)
};

// General-purpose categorical palette for charts whose series aren't fixed
// expense categories (e.g. forecast horizons, ad-hoc groupings). Ordered for
// maximum separation between adjacent entries.
export const CHART_PALETTE = [
  "#A8FF2F", // lime
  "#38BDF8", // sky
  "#FB7185", // rose
  "#C084FC", // violet
  "#FBBF24", // amber
  "#2DD4BF", // teal
  "#F472B6", // pink
  "#818CF8", // indigo
  "#FB923C", // orange
  "#4ADE80", // green
  "#22D3EE", // cyan
  "#E879F9", // fuchsia
];

// Stable color for an arbitrary label by hashing it into CHART_PALETTE.
export function paletteColor(key, i) {
  if (typeof i === "number") return CHART_PALETTE[i % CHART_PALETTE.length];
  let h = 0;
  const s = String(key);
  for (let j = 0; j < s.length; j++) h = (h * 31 + s.charCodeAt(j)) >>> 0;
  return CHART_PALETTE[h % CHART_PALETTE.length];
}

export const money = (v, currency = getRecordCurrency()) =>
  (() => {
    const targetCurrency = getCurrencyPreference();
    const requestedCurrency = /^[A-Z]{3}$/.test(currency || "") ? currency : getRecordCurrency();
    // API responses can echo the preferred currency while the numeric value
    // remains in the original record currency. Use the record currency as the
    // source whenever the requested code is the display target.
    const sourceCurrency = requestedCurrency === targetCurrency
      ? getRecordCurrency()
      : requestedCurrency;
    return new Intl.NumberFormat(getLocalePreference(), {
      style: "currency", currency: targetCurrency,
      minimumFractionDigits: 0, maximumFractionDigits: 2,
    }).format(convertDisplayAmount(v, sourceCurrency, targetCurrency));
  })();

export const moneyInCurrency = (v, currency = getCurrencyPreference()) =>
  new Intl.NumberFormat(getLocalePreference(), {
    style: "currency", currency: /^[A-Z]{3}$/.test(currency || "") ? currency : "INR",
    minimumFractionDigits: 0, maximumFractionDigits: 2,
  }).format(Number(v || 0));

export const currencySymbol = (currency = getCurrencyPreference()) =>
  new Intl.NumberFormat(getLocalePreference(), {
    style: "currency", currency: /^[A-Z]{3}$/.test(currency || "") ? currency : "INR",
  }).formatToParts(0).find((part) => part.type === "currency")?.value || currency;

export const compactMoney = (v) =>
  new Intl.NumberFormat(getLocalePreference(), {
    style: "currency", currency: getCurrencyPreference(), notation: "compact",
    maximumFractionDigits: 1,
  }).format(convertDisplayAmount(v, getRecordCurrency(), getCurrencyPreference()));

export const today = () => {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
};

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

// Per-category hues for charts that must tell categories apart. Toned down to
// sit inside the graphite ramp: similar lightness, low chroma, so no single
// category shouts. Income keeps a green, taxes and fees keep a red.
export const CATEGORY_COLORS = {
  Housing:       "#7d9cc4", // slate blue
  Rent:          "#7d9cc4",
  Groceries:     "#9cbf6a", // moss
  Transport:     "#c9a462", // ochre
  Dining:        "#c98a7d", // clay
  Subscriptions: "#a28fc4", // heather
  Shopping:      "#c48aa6", // dusty rose
  Health:        "#6fb3a6", // sage teal
  Utilities:     "#8e9aa8", // pewter
  Entertainment: "#c99a6e", // tan
  Education:     "#8f96c9", // periwinkle
  Insurance:     "#7fb38a", // fern
  Investments:   "#6fa9b8", // steel teal
  Transfers:     "#9a9aa0", // zinc
  Taxes:         "#c97a7a", // brick
  Fees:          "#b58ab8", // mauve
  Other:         "#74747a", // graphite
  Salary:        "#7fbf8f", // income green
  Freelance:     "#b9b46a", // olive gold
};

// Categorical palette for charts whose series aren't fixed categories.
// Same toned family; the brand lime leads.
export const CHART_PALETTE = [
  "#b6e35a", // brand lime (lead series)
  "#7d9cc4",
  "#c98a7d",
  "#a28fc4",
  "#c9a462",
  "#6fb3a6",
  "#c48aa6",
  "#8f96c9",
  "#c99a6e",
  "#7fb38a",
  "#6fa9b8",
  "#b58ab8",
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

// ── Dates, set one way across the app: "5 Nov", "Nov 2026", "1–17 Nov 2026" ──
const _MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function _parts(iso) {
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(iso || ""));
  return m ? { y: +m[1], m: +m[2] - 1, d: m[3] ? +m[3] : null } : null;
}
export function formatDay(iso, { year = false } = {}) {
  const p = _parts(iso);
  if (!p || p.d == null) return String(iso || "");
  return `${p.d} ${_MONTHS[p.m]}${year ? ` ${p.y}` : ""}`;
}
export function formatMonth(iso, { year = true } = {}) {
  const p = _parts(iso);
  if (!p) return String(iso || "");
  return year ? `${_MONTHS[p.m]} ${p.y}` : _MONTHS[p.m];
}
export function formatRange(start, end) {
  const a = _parts(start), b = _parts(end);
  if (!a || !b || a.d == null || b.d == null) return "";
  if (a.y === b.y && a.m === b.m) return a.d === b.d ? formatDay(start, { year: true }) : `${a.d}–${b.d} ${_MONTHS[b.m]} ${b.y}`;
  if (a.y === b.y) return `${a.d} ${_MONTHS[a.m]} – ${b.d} ${_MONTHS[b.m]} ${b.y}`;
  return `${formatDay(start, { year: true })} – ${formatDay(end, { year: true })}`;
}

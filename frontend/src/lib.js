// ── API Base & helpers ────────────────────────────────────────────────────────
export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
let currentToken = "";

export function setAuthToken(token) {
  currentToken = token || "";
}

function getToken() {
  return currentToken;
}

export function authHeaders(extra = {}) {
  const token = getToken();
  return token
    ? { Authorization: `Bearer ${token}`, ...extra }
    : { ...extra };
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const OFFLINE_MSG = "Can't reach the server — it may be waking up.";

// The API sleeps on Render's free tier and can take ~30–50s to wake. If any
// request is still pending after this long, tell the UI to show a banner.
const WAKE_HINT_MS = 3000;
let _waking = false;

function markWaking() {
  if (!_waking) {
    _waking = true;
    window.dispatchEvent(new CustomEvent("api:waking"));
  }
}
function markAwake() {
  if (_waking) {
    _waking = false;
    window.dispatchEvent(new CustomEvent("api:awake"));
  }
}

function friendlyError(status, rawText) {
  let msg = rawText || `HTTP ${status}`;
  try {
    const parsed = JSON.parse(rawText);
    if (parsed && typeof parsed.detail === "string") msg = parsed.detail;
    else if (parsed?.detail) msg = JSON.stringify(parsed.detail);
  } catch { /* not JSON — keep raw text */ }
  if (status >= 500 && (!rawText || rawText.startsWith("<"))) {
    msg = "The server hit an unexpected error. Please try again.";
  }
  return new ApiError(status, msg);
}

const RETRYABLE_STATUSES = new Set([502, 503, 504]);
// Escalating timeouts ride out a Render free-tier cold start (~50s worst case).
const GET_TIMEOUTS_MS = [15000, 30000, 60000];
const GET_BACKOFF_MS = [1000, 2000, 4000];

async function attemptFetch(path, opts, isFormData, timeoutMs) {
  const controller = timeoutMs ? new AbortController() : null;
  const timer = timeoutMs
    ? setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs)
    : null;
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...opts,
      signal: controller ? controller.signal : opts.signal,
      headers: {
        ...authHeaders(),
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(opts.headers || {}),
      },
    });
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function apiFetch(path, opts = {}) {
  const isFormData = opts.body instanceof FormData;
  const method = (opts.method || "GET").toUpperCase();
  const isStream = path.startsWith("/advisor/stream");
  // GETs retry through cold starts; mutations get exactly one attempt so a
  // slow-but-successful write is never duplicated.
  const canRetry = method === "GET" && !isStream;
  const maxAttempts = canRetry ? GET_TIMEOUTS_MS.length : 1;

  const wakeTimer = setTimeout(markWaking, WAKE_HINT_MS);
  try {
    let lastErr = null;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      if (attempt > 0) await new Promise((r) => setTimeout(r, GET_BACKOFF_MS[attempt - 1]));
      const timeoutMs = isStream ? 0
        : canRetry ? GET_TIMEOUTS_MS[attempt]
        : isFormData ? 60000
        : 15000;

      let res;
      try {
        res = await attemptFetch(path, opts, isFormData, timeoutMs);
      } catch (err) {
        if (err?.name === "AbortError" && opts.signal?.aborted) throw err; // caller cancelled
        lastErr = new ApiError(0, OFFLINE_MSG);
        continue; // network error or timeout → retry (or fall through)
      }

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        if (canRetry && RETRYABLE_STATUSES.has(res.status)) {
          lastErr = friendlyError(res.status, errText);
          continue;
        }
        throw friendlyError(res.status, errText);
      }

      const ct = res.headers.get("content-type") || "";
      if (isStream || ct.includes("text/event-stream")) return res;
      if (res.status === 204) return null;
      return res.json();
    }
    throw lastErr || new ApiError(0, OFFLINE_MSG);
  } finally {
    clearTimeout(wakeTimer);
    markAwake();
  }
}

// ── Query keys ───────────────────────────────────────────────────────────────
export const KEYS = {
  transactions:   (params)  => ["transactions", params],
  budgets:        ()        => ["budgets"],
  budgetSuggestions: (range) => ["budgetSuggestions", range],
  summary:        (range)   => ["summary", range],
  anomalies:      (range)   => ["anomalies", range],
  forecast:       ()        => ["forecast"],
  conversations:  ()        => ["conversations"],
  messages:       (id)      => ["messages", id],
  importJob:      (id)      => ["importJob", id],
  profile:        ()        => ["profile"],
  profileStats:   ()        => ["profileStats"],
  accounts:       ()        => ["accounts"],
  portfolios:     ()        => ["portfolios"],
  portfolioSummary: ()      => ["portfolioSummary"],
  portfolioAnalytics: ()    => ["portfolioAnalytics"],
  holdings:       (portfolioId) => ["holdings", portfolioId],
  creditHealth:   ()        => ["creditHealth"],
  benchmarks:     ()        => ["benchmarks"],
  insights:       ()        => ["insights"],
  audit:          (resourceType) => ["audit", resourceType],
  webhooks:       ()        => ["webhooks"],
  gstReport:      ()        => ["gstReport"],
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

export const money = (v) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(Number(v || 0));

export const today = () => new Date().toISOString().slice(0, 10);

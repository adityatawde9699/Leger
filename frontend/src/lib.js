// ── API Base & helpers ────────────────────────────────────────────────────────
export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
let currentToken = import.meta.env.VITE_DEV_AUTH_TOKEN || "dev-user";

export function setAuthToken(token) {
  currentToken = token;
}

function getToken() {
  return currentToken;
}

export function authHeaders(extra = {}) {
  return {
    Authorization: `Bearer ${getToken()}`,
    ...extra,
  };
}

export async function apiFetch(path, opts = {}) {
  const isFormData = opts.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      ...authHeaders(),
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
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

export const money = (v) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(Number(v || 0));

export const today = () => new Date().toISOString().slice(0, 10);

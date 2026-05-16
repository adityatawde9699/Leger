// ── API Base & helpers ────────────────────────────────────────────────────────
export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const DEV_TOKEN = import.meta.env.VITE_DEV_AUTH_TOKEN || "dev-user";

function getToken() {
  return localStorage.getItem("ledger_token") || DEV_TOKEN;
}

export async function apiFetch(path, opts = {}) {
  const isFormData = opts.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${getToken()}`,
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
  transactions: (params) => ["transactions", params],
  budgets: () => ["budgets"],
  summary: (month) => ["summary", month],
  conversations: () => ["conversations"],
  messages: (id) => ["messages", id],
  importJob: (id) => ["importJob", id],
};

// ── Constants shared across components ───────────────────────────────────────
export const CATEGORIES = [
  "Housing","Groceries","Transport","Dining","Subscriptions",
  "Shopping","Health","Utilities","Entertainment","Other","Salary","Freelance",
];
export const EXPENSE_CATEGORIES = CATEGORIES.filter(
  (c) => !["Salary", "Freelance"].includes(c)
);
export const CATEGORY_COLORS = {
  Housing:"#c084fc", Groceries:"#22c55e", Transport:"#38bdf8",
  Dining:"#f97316", Subscriptions:"#a78bfa", Shopping:"#f472b6",
  Health:"#14b8a6", Utilities:"#94a3b8", Entertainment:"#facc15",
  Other:"#9ca3af", Salary:"#4ade80", Freelance:"#84cc16",
};

export const money = (v) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(Number(v || 0));

export const today = () => new Date().toISOString().slice(0, 10);

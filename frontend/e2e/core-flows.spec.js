import { expect, test } from "@playwright/test";

const profile = {
  id: "dev-user", email: "dev@ledger.local", display_name: null, avatar_url: null,
  currency_preference: "USD", region: "US", income_pattern: "irregular",
  onboarding_completed: false, obligations_reviewed_at: null,
};

async function mockLedgerApi(page) {
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.host !== "127.0.0.1:4173" || !url.pathname.startsWith("/api/")) return route.continue();
    const path = url.pathname.slice("/api".length);
    let body = {};
    let status = 200;
    if (path === "/profile" && request.method() === "GET") body = profile;
    else if (path === "/profile" && request.method() === "PUT") body = { ...profile, ...JSON.parse(request.postData() || "{}") };
    else if (path.startsWith("/summary")) body = {
      income: 0, expenses: 0, net: 0, cash_income: 0, cash_expenses: 0, cash_net: 0,
      by_category: {}, by_day: {}, by_month: {}, top_merchants: [], recurring: [], insights: [],
      period_start: null, period_end: null, months_covered: 0,
      data_quality: { transaction_count: 0, pending_transactions: 0, excluded_transactions: 0, failed_imports: 0, uncategorized_count: 0, unassigned_account_count: 0, stale_account_count: 0, warnings: [], coverage: "none", currency_mismatch_count: 0 },
    };
    else if (path === "/daily-position") body = { as_of: "2026-09-25", month_end: "2026-09-30", currency: "USD", income: null, committed_spend: null, flexible_spend: null, cash_available: null, upcoming_obligations: [], reserve_remaining: null, safe_to_spend_estimate: null, status: "unavailable", reasons: ["Add and reconcile a cash, wallet, checking, or savings account."], method: "This is an estimate, not a bank balance.", obligations_reviewed_at: null };
    else if (path.startsWith("/analytics/compare")) body = { status: "insufficient_data", current: { transaction_count: 0 }, previous: { transaction_count: 0 } };
    else if (path === "/analytics/anomalies") body = [];
    else if (path === "/analytics/forecast") body = null;
    else if (path === "/goals" || path === "/imports/jobs" || path === "/recurring" || path === "/accounts" || path === "/budgets" || path === "/categories" || path === "/merchant-aliases") body = path === "/imports/jobs" ? [] : [];
    else if (path === "/daily-position/review") body = { reviewed_at: "2026-09-25T00:00:00Z" };
    else if (path === "/transactions") body = { items: [], next_cursor: null, has_more: false, total_returned: 0 };
    else if (path === "/transactions/split") body = { group_id: "split:test", items: [] };
    else { status = 404; body = { detail: `Unmocked API path ${path}` }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function signedIn(page) {
  await page.addInitScript(() => localStorage.setItem("dev-session", JSON.stringify({ access_token: "dev-user", user: { email: "dev@ledger.local" } })));
  await mockLedgerApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test("first-run setup explains the missing baseline and can be skipped", async ({ page }) => {
  await signedIn(page);
  await expect(page.getByText("Set up Ledger for you", { exact: true })).toBeVisible();
  await expect(page.getByText("Optional steps can be skipped")).toBeVisible();
  await expect(page.getByText("Add and reconcile a cash, wallet, checking, or savings account.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Skip setup" }).click();
  await expect(page.getByRole("heading", { name: "Next action: Add your first transactions" })).toBeVisible();
});

test("quick add is keyboard reachable and closes with Escape", async ({ page }) => {
  await signedIn(page);
  await page.getByRole("button", { name: "Skip setup" }).click();
  const add = page.getByRole("button", { name: "Add transaction" });
  await add.click();
  await expect(page.getByRole("dialog", { name: "Add Transaction" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Amount in USD" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Add Transaction" })).toBeHidden();
  await expect(add).toBeFocused();
});

test("command palette traps focus and restores it on Escape", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signedIn(page);
  const search = page.getByRole("button", { name: "Search" });
  await search.click();
  const dialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Search commands" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(search).toBeFocused();
});

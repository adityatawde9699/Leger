import { expect, test } from "@playwright/test";

const profile = {
  id: "dev-user", email: "dev@ledger.local", display_name: null, avatar_url: null,
  currency_preference: "USD", region: "US", income_pattern: "irregular",
  onboarding_completed: false, obligations_reviewed_at: null,
};

const emptySummary = {
  income: 0, expenses: 0, net: 0, cash_income: 0, cash_expenses: 0, cash_net: 0,
  by_category: {}, by_day: {}, by_month: {}, top_merchants: [], recurring: [], insights: [],
  period_start: null, period_end: null, months_covered: 0,
  data_quality: { transaction_count: 0, pending_transactions: 0, excluded_transactions: 0, failed_imports: 0, uncategorized_count: 0, unassigned_account_count: 0, stale_account_count: 0, warnings: [], coverage: "none", currency_mismatch_count: 0 },
};

async function mockLedgerApi(page, overrides = {}) {
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.host !== "127.0.0.1:4173" || !url.pathname.startsWith("/api/")) return route.continue();
    const path = url.pathname.slice("/api".length);
    let body = {};
    let status = 200;
    const override = overrides[`${request.method()} ${path}`] || overrides[path];
    if (override) {
      const result = override(request);
      return route.fulfill({ status: result.status || 200, contentType: "application/json", body: result.body === undefined ? "" : JSON.stringify(result.body) });
    }
    if (path === "/profile" && request.method() === "GET") body = profile;
    else if (path === "/profile" && request.method() === "PUT") body = { ...profile, ...JSON.parse(request.postData() || "{}") };
    else if (path.startsWith("/summary")) body = emptySummary;
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

async function signedIn(page, overrides) {
  await page.addInitScript(() => localStorage.setItem("dev-session", JSON.stringify({ access_token: "dev-user", user: { email: "dev@ledger.local" } })));
  await mockLedgerApi(page, overrides);
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

test("quick add fits a small phone and covers the bottom navigation", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await signedIn(page);
  await page.getByRole("button", { name: "Skip setup" }).click();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Add Transaction" });
  await expect(sheet).toBeVisible();

  const layout = await sheet.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const clipped = [...el.querySelectorAll("*")].filter((child) => {
      const b = child.getBoundingClientRect();
      if (!b.width) return false;
      for (let p = child.parentElement; p && p !== el; p = p.parentElement) {
        if (getComputedStyle(p).overflowX !== "visible") return false; // scrolls on purpose
      }
      return b.right > box.right + 1 || b.left < box.left - 1;
    }).map((child) => child.textContent.trim().slice(0, 30));
    const bottom = document.elementFromPoint(innerWidth / 2, innerHeight - 10);
    return { clipped, top: box.top, sheetOnTop: el.contains(bottom) };
  });
  expect(layout.clipped).toEqual([]);
  expect(layout.top).toBeGreaterThanOrEqual(0);
  expect(layout.sheetOnTop).toBe(true);
  await expect(page.getByRole("button", { name: "Enter an amount" })).toBeInViewport();
});

test("main views never scroll sideways on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await signedIn(page);
  for (const view of ["dashboard", "budgets", "transactions", "analytics", "advisor", "profile"]) {
    await page.goto(`/?view=${view}`);
    await page.waitForLoadState("networkidle");
    const widest = await page.evaluate(() => Math.max(...[...document.querySelectorAll("main *")].map((el) => {
      for (let p = el.parentElement; p; p = p.parentElement) if (["auto", "scroll"].includes(getComputedStyle(p).overflowX)) return 0;
      return el.getBoundingClientRect().right;
    })));
    expect(widest, `${view} is wider than the screen`).toBeLessThanOrEqual(361);
  }
});

test("a long recommended action stays inside the screen on a phone", async ({ page }) => {
  const longText = "Review Other transactions and adjust the budget or pause discretionary spending until next month";
  const summary = {
    ...emptySummary,
    insight_claims: [{
      id: "claim-1",
      claim: "Other is over budget by GBP 474,422.88: GBP 476,729.13 against a GBP 2,306.25 limit.",
      evidence: { transaction_ids: ["t1", "t2"], method: "sum of posted category expenses compared with the user budget" },
      confidence: "high",
      recommended_action: longText,
    }],
  };
  await page.setViewportSize({ width: 360, height: 740 });
  await signedIn(page, { "/summary": () => ({ body: summary }) });
  await page.getByRole("button", { name: "Skip setup" }).click();

  const card = page.locator(".card").filter({ hasText: "What to look at" });
  await expect(card.getByRole("button", { name: longText })).toBeVisible();
  const overflow = await card.evaluate((el) => {
    const right = Math.min(el.getBoundingClientRect().right, document.documentElement.clientWidth);
    return [...el.querySelectorAll("*")]
      .filter((child) => child.getBoundingClientRect().right > right + 1)
      .map((child) => child.textContent.trim().slice(0, 40));
  });
  expect(overflow).toEqual([]);
});

test("a failed import whose file expired offers upload again and can be dismissed", async ({ page }) => {
  let jobs = [{
    id: "job-1", status: "failed", file_name: "acc.ods", processed_rows: 0, cancel_requested: false,
    error_message: "This import failed. Upload the statement again.", can_retry: false, created_at: "2026-09-18T19:56:13Z",
  }];
  const deleted = [];
  await signedIn(page, {
    "GET /imports/jobs": () => ({ body: jobs }),
    "DELETE /imports/jobs/job-1": () => { deleted.push("job-1"); jobs = []; return { status: 204 }; },
  });
  await page.getByRole("button", { name: "Skip setup" }).click();

  const imports = page.locator(".card").filter({ hasText: "Statement imports" });
  await expect(imports.getByText("acc.ods")).toBeVisible();
  await expect(imports.getByRole("button", { name: "Retry" })).toHaveCount(0);
  await expect(imports.getByRole("button", { name: "Upload again" })).toBeVisible();

  await imports.getByRole("button", { name: "Dismiss import acc.ods" }).click();
  await expect(page.getByText("Statement imports")).toHaveCount(0);
  expect(deleted).toEqual(["job-1"]);
});

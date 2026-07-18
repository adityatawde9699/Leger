// Mirrors backend/app/services/categorizer.py CATEGORIES (must stay in sync
// with frontend/src/lib.js CATEGORIES/EXPENSE_CATEGORIES/INCOME_CATEGORIES).
export const CATEGORIES = [
  "Housing", "Groceries", "Transport", "Dining", "Subscriptions",
  "Shopping", "Health", "Utilities", "Entertainment",
  "Education", "Insurance", "Investments", "Transfers", "Taxes", "Fees",
  "Other", "Salary", "Freelance",
];

export const EXPENSE_CATEGORIES = CATEGORIES.filter((c) => c !== "Salary" && c !== "Freelance");
export const INCOME_CATEGORIES = ["Salary", "Freelance", "Other"];

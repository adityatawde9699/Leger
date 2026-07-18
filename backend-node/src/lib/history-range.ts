import { HttpError } from "./http-error.js";

// Port of backend/app/main.py's _history_start.
export function historyStart(rangeKey: string | null | undefined): string | null {
  const today = new Date();
  const isoDaysAgo = (days: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 10);
  };

  if (rangeKey === "this_month" || rangeKey === "30d") return isoDaysAgo(30);
  if (rangeKey === "current_year") {
    return `${today.getFullYear()}-01-01`;
  }
  if (!rangeKey || rangeKey === "3m") return isoDaysAgo(92);
  if (rangeKey === "1y") return isoDaysAgo(365);
  if (rangeKey === "all") return null;
  throw new HttpError(400, "range must be this_month, 3m, current_year, 1y, or all");
}

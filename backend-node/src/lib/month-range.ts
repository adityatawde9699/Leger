// Port of _month_range in backend/app/main.py — "YYYY-MM" -> [start, end) dates.
export function monthRange(month: string): { start: string; end: string } {
  const [yearStr, monthStr] = month.split("-");
  const year = Number(yearStr);
  const mon = Number(monthStr);
  const start = `${yearStr}-${monthStr}-01`;
  const end = mon === 12 ? `${year + 1}-01-01` : `${year}-${String(mon + 1).padStart(2, "0")}-01`;
  return { start, end };
}

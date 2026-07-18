import { HttpError } from "./http-error.js";

// Port of _cursor_encode/_cursor_decode in backend/app/main.py.
export function cursorEncode(date: string, id: string): string {
  return Buffer.from(`${date}|${id}`, "utf-8").toString("base64url");
}

export function cursorDecode(cursor: string): { date: string; id: string } {
  try {
    const decoded = Buffer.from(cursor, "base64url").toString("utf-8");
    const idx = decoded.lastIndexOf("|");
    if (idx === -1) throw new Error("malformed cursor");
    return { date: decoded.slice(0, idx), id: decoded.slice(idx + 1) };
  } catch {
    throw new HttpError(400, "Invalid cursor");
  }
}

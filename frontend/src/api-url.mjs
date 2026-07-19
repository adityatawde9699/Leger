export function normalizeApiBase(base = "") {
  if (!base) return "";
  return String(base).trim().replace(/\/+$/, "");
}

export function buildApiUrl(path, base = "") {
  const normalizedBase = normalizeApiBase(base || "");
  if (!path) return normalizedBase;

  const normalizedPath = String(path).startsWith("/") ? String(path) : `/${path}`;
  if (!normalizedBase) return normalizedPath;

  return `${normalizedBase}${normalizedPath}`;
}

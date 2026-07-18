// Mirrors FastAPI's HTTPException wire shape: {"detail": "..."} — the
// frontend's apiFetch (frontend/src/lib.js) parses exactly this shape.
export class HttpError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

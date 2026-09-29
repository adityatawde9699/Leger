"""Read-only production smoke check: python scripts/security_smoke.py https://frontend.example"""
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check(origin: str, path: str, expected: int) -> None:
    request = Request(origin.rstrip("/") + path, headers={"Accept": "application/json"})
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as exc:
        response = exc
    except URLError as exc:
        raise SystemExit(f"Cannot reach {path}: {exc.reason}") from exc
    with response:
        if response.status != expected:
            raise SystemExit(f"{path}: expected {expected}, got {response.status}")
        if response.headers.get("X-Content-Type-Options") != "nosniff":
            raise SystemExit(f"{path}: missing nosniff header")
        if not response.headers.get("X-Request-ID"):
            raise SystemExit(f"{path}: missing request ID")
        if not response.headers.get("Strict-Transport-Security"):
            raise SystemExit(f"{path}: missing HSTS")
    print(f"{path}: {expected}, security headers present")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        raise SystemExit("Usage: python scripts/security_smoke.py https://frontend.example")
    check(sys.argv[1], "/api/profile", 401)
    check(sys.argv[1], "/api/docs", 404)

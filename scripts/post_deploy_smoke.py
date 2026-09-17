#!/usr/bin/env python3
"""14.5 post-deploy smoke: health, login, invariants.

Usage:
  python scripts/post_deploy_smoke.py --base-url https://app.example --email u --password p

Checks are imported by backend/tests/test_post_deploy_smoke.py against the
Django test client (no hosted URL required).
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request


def check_health(get) -> None:
    status, body = get("/api/v1/health/")
    if status != 200:
        raise SystemExit(f"health failed: {status} {body}")
    if (body or {}).get("status") not in {"ok", "degraded"}:
        raise SystemExit(f"health status unexpected: {body}")


def check_ready(get) -> None:
    status, body = get("/api/v1/health/?ready=1")
    if status != 200:
        raise SystemExit(f"ready failed: {status} {body}")
    if (body or {}).get("status") not in {"ok", "degraded"}:
        raise SystemExit(f"ready status unexpected: {body}")


def check_login(post, email: str, password: str) -> dict:
    status, body = post("/api/v1/auth/login/", {"email": email, "password": password})
    if status != 200:
        raise SystemExit(f"login failed: {status} {body}")
    if not isinstance(body, dict):
        raise SystemExit("login returned a non-object body")
    return body


def check_invariants(get_auth) -> None:
    status, body = get_auth("/api/v1/invariants/check/")
    if status not in (200, 409):
        raise SystemExit(f"invariants check failed: {status} {body}")
    if status == 409:
        raise SystemExit(f"invariants violated: {body}")


def _json_opener(base_url: str):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(method: str, path: str, body: dict | None = None):
        url = base_url.rstrip("/") + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(req, timeout=20) as resp:
                raw = resp.read()
                payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
                return resp.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                payload = {"detail": raw.decode("utf-8", errors="replace")}
            return exc.code, payload

    return request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post-deploy smoke checks.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--skip-invariants", action="store_true")
    args = parser.parse_args(argv)

    request = _json_opener(args.base_url)
    check_health(lambda path: request("GET", path))
    check_ready(lambda path: request("GET", path))
    check_login(lambda path, body: request("POST", path, body), args.email, args.password)
    if not args.skip_invariants:
        check_invariants(lambda path: request("GET", path))
    print("post-deploy smoke ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

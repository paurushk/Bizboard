"""WP-1: sign in through the normal login form and print ZAP replacer options for that session.

Uses a test login that has no two-step sign-in (the load-tenant sales staff from
seed_load_tenant). Staging is cookie-only (BB-000547), so every request needs the session cookies
and, on POST/PUT/PATCH, a matching X-CSRFToken header. The printed `-z` string tells ZAP to add
both to every request. Before printing, it checks that an unsafe request with these headers gets
past CSRF (a 400 from validation, not "403 CSRF Failed"); otherwise the scan would only test the
CSRF check.

    SCAN_EMAIL=... SCAN_PASSWORD=... python scripts/security/zap/zap_login.py > <scratch>/zap-auth.txt

The output holds a live session: keep it in a scratch folder, never in the repo. The access
cookie lasts 15 minutes, so start the scan straight away.
"""

from __future__ import annotations

import os
import sys
import time

import requests

BASE = os.environ.get("SCAN_BASE", "http://127.0.0.1:8081")


def main() -> int:
    email, password = os.environ.get("SCAN_EMAIL"), os.environ.get("SCAN_PASSWORD")
    if not email or not password:
        sys.exit("SCAN_EMAIL and SCAN_PASSWORD are required")
    # The login throttle answers 429 after a burst; wait it out rather than fail the batch.
    for _ in range(12):
        s = requests.Session()
        r = s.post(f"{BASE}/api/v1/auth/login/", json={"email": email, "password": password}, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(min(60, int(r.headers.get("Retry-After", "30") or 30)))
    if r.status_code != 200:
        sys.exit(f"sign-in failed: HTTP {r.status_code}")
    jar = {c.name: c.value for c in s.cookies}
    if "bb_access" not in jar or "csrftoken" not in jar:
        sys.exit("sign-in gave no session cookies")
    cookie = "; ".join(f"{k}={v}" for k, v in jar.items())
    probe = requests.post(
        f"{BASE}/api/v1/sales/invoices/", json={},
        headers={"Cookie": cookie, "X-CSRFToken": jar["csrftoken"], "Content-Type": "application/json"},
        timeout=60,
    )
    if probe.status_code == 403 and "csrf" in probe.text.lower():
        sys.exit("CSRF check rejected the session headers; the scan would test nothing")
    if probe.status_code in (401, 403):
        sys.exit(f"session not accepted on an unsafe request: HTTP {probe.status_code}")
    rules = [
        ("Cookie", cookie),
        ("X-CSRFToken", jar["csrftoken"]),
    ]
    parts = []
    for i, (name, value) in enumerate(rules):
        parts += [
            f"-config replacer.full_list({i}).description=wp1-{name.lower()}",
            f"-config replacer.full_list({i}).enabled=true",
            f"-config replacer.full_list({i}).matchtype=REQ_HEADER",
            f"-config replacer.full_list({i}).matchstr={name}",
            f"-config replacer.full_list({i}).regex=false",
            f"-config replacer.full_list({i}).replacement={value}",
        ]
    print(" ".join(parts))
    print(f"precheck: unsafe request with session -> HTTP {probe.status_code}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

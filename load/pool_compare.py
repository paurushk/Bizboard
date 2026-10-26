"""Read-mix latency for one stack, to compare with and without PgBouncer (WP-5, BB-068).

Signs in N load-tenant staff (seed_load_tenant --staff N), then keeps CONCURRENCY threads busy on
the k6_mixed read endpoints (invoice list, dashboard, search) for DURATION seconds and prints
p50/p95/p99 per endpoint and overall, plus the error count. No writes.

    LOAD_PASSWORD=... python load/pool_compare.py --base http://127.0.0.1:8081 --label pool
    (restart api/worker/beat without docker-compose.pgbouncer.yml)
    LOAD_PASSWORD=... python load/pool_compare.py --base http://127.0.0.1:8081 --label direct

Record both runs in docs/ops/POSTGRES.md. k6 (k6_slo.js / k6_mixed.js) stays the gate on the host;
this is the quick local A/B that needs no k6 binary.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from collections import defaultdict

import requests

ENDPOINTS = (
    ("invoices", "/api/v1/sales/invoices/?page=1&page_size=50"),
    ("dashboard", "/api/v1/dashboard/"),
    ("search", "/api/v1/search/?q=load"),
)


def staff_email(index: int) -> str:
    # Mirrors accounts.management.commands.seed_load_tenant.load_staff_email.
    return "load-staff@bizboard.local" if index == 1 else f"load-staff-{index:02d}@bizboard.local"


def sign_in(base: str, email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{base}/api/v1/auth/login/", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200 or not s.cookies:
        raise SystemExit(f"sign-in for {email} failed: HTTP {r.status_code}")
    # Staging cookies are Secure, so requests will not send them back over local http; send them
    # as a header the way k6_slo.js does.
    jar = {c.name: c.value for c in s.cookies}
    s.cookies.clear()
    s.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
    if jar.get("csrftoken"):
        s.headers["X-CSRFToken"] = jar["csrftoken"]
    return s


def pct(values, q):
    if not values:
        return float("nan")
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(q / 100 * (len(values) - 1))))
    return values[k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8081")
    ap.add_argument("--label", required=True)
    ap.add_argument("--staff", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--duration", type=int, default=90)
    ap.add_argument("--login-gap", type=float, default=7.0, help="seconds between sign-ins (login throttle)")
    args = ap.parse_args()
    password = os.environ.get("LOAD_PASSWORD")
    if not password:
        raise SystemExit("LOAD_PASSWORD is required")

    sessions = []
    for i in range(1, args.staff + 1):
        if i > 1:
            time.sleep(args.login_gap)
        sessions.append(sign_in(args.base, staff_email(i), password))

    timings = defaultdict(list)
    errors = defaultdict(int)
    lock = threading.Lock()
    stop_at = time.monotonic() + args.duration

    def worker(n: int) -> None:
        s = sessions[n % len(sessions)]
        i = n
        while time.monotonic() < stop_at:
            name, path = ENDPOINTS[i % len(ENDPOINTS)]
            i += 1
            t0 = time.perf_counter()
            try:
                r = s.get(f"{args.base}{path}", timeout=30)
                ok = r.status_code == 200
                code = r.status_code
            except requests.RequestException:
                ok, code = False, "exc"
            ms = (time.perf_counter() - t0) * 1000
            with lock:
                if ok:
                    timings[name].append(ms)
                else:
                    errors[f"{name}:{code}"] += 1

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(args.concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    every = [v for vs in timings.values() for v in vs]
    out = {
        "label": args.label,
        "requests": len(every) + sum(errors.values()),
        "errors": dict(errors),
        "rps": round(len(every) / args.duration, 1),
        "overall_ms": {"p50": round(pct(every, 50)), "p95": round(pct(every, 95)), "p99": round(pct(every, 99))}
        if every else None,
        "by_endpoint_ms": {
            k: {"n": len(v), "p50": round(statistics.median(v)), "p95": round(pct(v, 95))} for k, v in sorted(timings.items())
        },
    }
    print(json.dumps(out, indent=2))
    return 1 if sum(errors.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

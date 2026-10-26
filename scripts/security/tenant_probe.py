"""WP-1: cross-tenant probe through the real stack (nginx -> gunicorn -> app DB role with RLS).

Signs in two test logins from two different companies through the normal login form (both
without two-step: the load-tenant sales staff and the C5 pilot sales staff), then checks:

1. Detail reads. For every GET path in the OpenAPI snapshot with one {id}-style parameter whose
   list path also exists: read up to two of B's ids as B, then request them as A. Expected 404
   (or 403). A 200 is a leak. A's own id is tried too, so "A cannot use this endpoint at all"
   (403 for the role) is reported as inconclusive, not as protected.
2. List filters. List endpoints called as A with B's customer / product / supplier / invoice /
   warehouse id in their declared filter parameters. A leak is any returned row id that is also
   in B's own list for that endpoint.
3. Writes with B's ids. A creates drafts (invoice, quotation, order, purchase bill, receipt) that
   point at B's customer / product / supplier / warehouse, and patches its own draft to B's
   customer. Expected 400/403/404 and nothing saved. A control request with A's own ids shows the
   endpoint works for A, so a rejection is attributable to the foreign id.

Writes create drafts in tenant A: run on LOCAL staging after a pg_dump and restore afterwards.

    A_EMAIL=... A_PASSWORD=... B_EMAIL=... B_PASSWORD=... \
      python scripts/security/tenant_probe.py --base http://127.0.0.1:8081 --out <scratch>/probe.json

Exit status 1 when any leak or accepted foreign write is found.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
PARAM = re.compile(r"\{[^}]+\}")
SKIP = re.compile(r"^/api/v1/(auth|billing|webhooks|public|links|ops|metrics|telegram|email)/")
FILTER_KINDS = {
    "customer": "customer", "customer_id": "customer", "party": "customer",
    "product": "product", "product_id": "product", "item": "product",
    "supplier": "supplier", "supplier_id": "supplier",
    "invoice": "invoice", "sales_invoice": "invoice", "invoice_id": "invoice",
    "warehouse": "warehouse", "godown": "warehouse", "warehouse_id": "warehouse",
}
SOURCES = {
    "customer": "/api/v1/customers/",
    "product": "/api/v1/products/",
    "supplier": "/api/v1/suppliers/",
    "invoice": "/api/v1/sales/invoices/",
    "warehouse": "/api/v1/inventory/warehouses/",
}


class Client:
    def __init__(self, base, email, password, gap):
        self.base, self.gap = base, gap
        for _ in range(12):  # wait out the login throttle instead of failing
            s = requests.Session()
            r = s.post(f"{base}/api/v1/auth/login/", json={"email": email, "password": password}, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(min(60, int(r.headers.get("Retry-After", "30") or 30)))
        if r.status_code != 200:
            sys.exit(f"sign-in failed for {email}: HTTP {r.status_code}")
        jar = {c.name: c.value for c in s.cookies}
        self.company = (r.json().get("data") or {}).get("user", {}).get("companyId")
        # Staging cookies are Secure; send them as a header over local http (as k6_slo.js does).
        self.headers = {
            "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items()),
            "X-CSRFToken": jar.get("csrftoken", ""),
            "Content-Type": "application/json",
        }

    def req(self, method, path, **kw):
        time.sleep(self.gap)
        for _ in range(3):
            try:
                r = requests.request(method, f"{self.base}{path}", headers=self.headers, timeout=60, **kw)
            except requests.RequestException:
                return None
            if r.status_code != 429:
                return r
            time.sleep(float(r.headers.get("Retry-After", "5") or 5))
        return r


def rows(resp):
    if resp is None or resp.status_code != 200:
        return []
    try:
        body = resp.json()
    except ValueError:
        return []
    data = body.get("data", body) if isinstance(body, dict) else body
    if isinstance(data, dict):
        data = data.get("results", data.get("items", []))
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def ids(resp, n=50):
    return [r["id"] for r in rows(resp) if "id" in r][:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8081")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gap", type=float, default=0.25, help="seconds between requests (nginx allows 30 r/s per IP)")
    args = ap.parse_args()
    env = os.environ
    a = Client(args.base, env["A_EMAIL"], env["A_PASSWORD"], args.gap)
    time.sleep(8)  # login throttle
    b = Client(args.base, env["B_EMAIL"], env["B_PASSWORD"], args.gap)
    if a.company == b.company:
        sys.exit("A and B are in the same company")
    spec = json.loads((ROOT / "docs" / "openapi-snapshot.json").read_text(encoding="utf-8"))
    paths = spec["paths"]
    report = {"a_company": a.company, "b_company": b.company, "detail": [], "filters": [], "writes": []}

    # 1. Detail reads.
    for path, ops in sorted(paths.items()):
        if "get" not in ops or SKIP.search(path):
            continue
        params = PARAM.findall(path)
        if len(params) != 1:
            continue
        base = path[: path.index("{")]
        if base not in paths or "get" not in paths[base]:
            continue
        b_ids = ids(b.req("GET", base), 2)
        a_ids = ids(a.req("GET", base), 1)
        if not b_ids:
            report["detail"].append({"path": path, "result": "no B data"})
            continue
        statuses = []
        for oid in b_ids:
            r = a.req("GET", path.replace(params[0], str(oid)))
            statuses.append(r.status_code if r is not None else "err")
        own = None
        if a_ids:
            r = a.req("GET", path.replace(params[0], str(a_ids[0])))
            own = r.status_code if r is not None else "err"
        if any(s == 200 for s in statuses):
            result = "LEAK"
        elif own == 200 or (own is None and all(s == 404 for s in statuses)):
            result = "protected"
        else:
            result = "inconclusive (A cannot use it either)"
        report["detail"].append({"path": path, "b_as_a": statuses, "a_own": own, "result": result})

    # 2. List filters with B's ids.
    b_ref = {k: ids(b.req("GET", src), 3) for k, src in SOURCES.items()}
    for path, ops in sorted(paths.items()):
        if "get" not in ops or PARAM.search(path) or SKIP.search(path):
            continue
        names = [p.get("name") for p in ops["get"].get("parameters", []) if p.get("in") == "query"]
        kinds = {n: FILTER_KINDS[n] for n in names if n in FILTER_KINDS and b_ref.get(FILTER_KINDS[n])}
        if not kinds:
            continue
        b_rows = set(ids(b.req("GET", path), 500))
        for name, kind in kinds.items():
            r = a.req("GET", path, params={name: b_ref[kind][0]})
            got = set(ids(r, 500))
            leak = sorted(got & b_rows)
            report["filters"].append({
                "path": path, "param": name, "status": r.status_code if r is not None else "err",
                "rows": len(got), "result": "LEAK" if leak else "ok", "leaked_ids": leak[:5],
            })

    # 3. Writes with B's ids.
    a_ref = {k: ids(a.req("GET", src), 1) for k, src in SOURCES.items()}
    today = dt.date.today().isoformat()

    def first(ref, kind):
        return (ref.get(kind) or [None])[0]

    def line(product):
        return [{"product": product, "quantity": "1", "unit_price": "10", "gst_rate": "18"}]

    def doc(customer, product, **extra):
        return {"customer": customer, "invoice_date": today, "items": line(product), **extra}

    ac, ap_, aw, asu = first(a_ref, "customer"), first(a_ref, "product"), first(a_ref, "warehouse"), first(a_ref, "supplier")
    bc, bp, bw, bs, bi = (first(b_ref, k) for k in ("customer", "product", "warehouse", "supplier", "invoice"))
    # (label, method, path, body with B's id, control body with A's own ids, [ids that must exist])
    cases = [
        ("sales invoice: B customer", "POST", "/api/v1/sales/invoices/", doc(bc, ap_), doc(ac, ap_), [bc, ac, ap_]),
        ("sales invoice: B product", "POST", "/api/v1/sales/invoices/", doc(ac, bp), doc(ac, ap_), [bp, ac, ap_]),
        ("sales invoice: B godown", "POST", "/api/v1/sales/invoices/", doc(ac, ap_, warehouse=bw),
         doc(ac, ap_, warehouse=aw), [bw, aw, ac, ap_]),
        ("quotation: B customer", "POST", "/api/v1/sales/quotations/", doc(bc, ap_), doc(ac, ap_), [bc, ac, ap_]),
        ("quotation: B product", "POST", "/api/v1/sales/quotations/", doc(ac, bp), doc(ac, ap_), [bp, ac, ap_]),
        ("sales order: B customer", "POST", "/api/v1/sales/orders/", doc(bc, ap_), doc(ac, ap_), [bc, ac, ap_]),
        ("purchase bill: B supplier", "POST", "/api/v1/purchases/invoices/",
         {"supplier": bs, "invoice_date": today, "items": line(ap_)},
         {"supplier": asu, "invoice_date": today, "items": line(ap_)}, [bs, asu, ap_]),
        ("receipt: B customer", "POST", "/api/v1/payments/receipts/",
         {"customer": bc, "amount": "1", "mode": "CASH", "receipt_date": today},
         {"customer": ac, "amount": "1", "mode": "CASH", "receipt_date": today}, [bc, ac]),
    ]
    for label, method, path, foreign, control, needed in cases:
        if any(x is None for x in needed):
            report["writes"].append({"case": label, "result": "skipped (an id is missing for this role)"})
            continue
        ctrl = a.req(method, path, json=control).status_code if control else None
        r = a.req(method, path, json=foreign)
        st = r.status_code if r is not None else "err"
        if st in (200, 201):
            result = "ACCEPTED"
        elif ctrl in (200, 201) or control is None:
            result = "rejected"
        else:
            result = f"inconclusive (control got {ctrl})"
        report["writes"].append({"case": label, "status": st, "control": ctrl, "result": result,
                                 "detail": (r.text[:160] if r is not None and st not in (200, 201) else "")})
    # Patch A's own draft to B's customer.
    a_draft = next((x for x in rows(a.req("GET", "/api/v1/sales/invoices/", params={"status": "DRAFT"})) if x.get("status") == "DRAFT"), None)
    if a_draft and bc:
        r = a.req("PATCH", f"/api/v1/sales/invoices/{a_draft['id']}/", json={"customer": bc})
        st = r.status_code if r is not None else "err"
        report["writes"].append({"case": "patch own draft to B customer", "status": st,
                                 "result": "ACCEPTED" if st in (200, 201) else "rejected"})

    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    det = report["detail"]
    summary = {
        "detail_paths": len(det),
        "detail_protected": sum(1 for x in det if x["result"] == "protected"),
        "detail_inconclusive": sum(1 for x in det if x["result"].startswith("inconclusive")),
        "detail_no_b_data": sum(1 for x in det if x["result"] == "no B data"),
        "detail_LEAKS": [x["path"] for x in det if x["result"] == "LEAK"],
        "filter_checks": len(report["filters"]),
        "filter_LEAKS": [f"{x['path']}?{x['param']}" for x in report["filters"] if x["result"] == "LEAK"],
        "writes": [(x["case"], x.get("status"), x["result"]) for x in report["writes"]],
    }
    print(json.dumps(summary, indent=1))
    bad = summary["detail_LEAKS"] or summary["filter_LEAKS"] or any(x["result"] == "ACCEPTED" for x in report["writes"])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

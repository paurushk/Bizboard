"""WP-1: copy of docs/openapi-snapshot.json that is safe to active-scan on local staging.

ZAP's API scan sends attack payloads to every operation in the spec it is given. This drops the
operations that must not be fuzzed even on local staging: every DELETE, sign-in and session
endpoints (a fuzzed login locks the scan account), billing, payments gateways and webhooks,
anything that sends SMS / email / WhatsApp / Telegram, erasure, ownership and user management,
backups and exports, imports commits, the ops and metrics endpoints, and the public link endpoints.

    python scripts/security/zap/filter_openapi.py <out.json> [--server http://host.docker.internal:8081]
        [--only 'sales|purchases']   # keep only these /api/v1/<area>/ prefixes (scan in batches)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SKIP_PATH = re.compile(
    r"^/api/v1/("
    r"auth/|billing/|payments/gateway|payments/.*(webhook|razorpay|cashfree|payu|refund)|webhooks/|"
    r"telegram/|email/|notifications/send|.*whatsapp|.*sms|.*otp|"
    r"company/(erase|erasure|ownership|transfer|users|members/invite|delete|close)|.*erase|"
    r".*backup|exports/|.*export/|imports/.*(commit|apply)|"
    r"ops/|metrics|client-errors|help-events|public/|links/|integrations/|agents/.*run|"
    r"support/.*(grant|access)"
    r")",
    re.I,
)
SKIP_METHODS = {"delete"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--server", default="http://host.docker.internal:8081")
    ap.add_argument("--only", default="", help="regex of /api/v1/<area>/ prefixes to keep")
    args = ap.parse_args()
    only = re.compile(rf"^/api/v1/({args.only})/") if args.only else None
    spec = json.loads((ROOT / "docs" / "openapi-snapshot.json").read_text(encoding="utf-8"))
    kept, dropped = {}, 0
    for path, ops in spec["paths"].items():
        if SKIP_PATH.search(path) or not path.startswith("/api/v1/") or (only and not only.search(path)):
            dropped += sum(1 for m in ops if m in {"get", "post", "put", "patch", "delete"})
            continue
        safe = {m: v for m, v in ops.items() if m not in SKIP_METHODS}
        dropped += len(ops) - len(safe)
        if any(m in safe for m in ("get", "post", "put", "patch")):
            kept[path] = safe
    spec["paths"] = kept
    spec["servers"] = [{"url": args.server}]
    Path(args.out).write_text(json.dumps(spec), encoding="utf-8")
    n = sum(1 for ops in kept.values() for m in ops if m in {"get", "post", "put", "patch"})
    print(f"kept {len(kept)} paths / {n} operations; dropped {dropped} operations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

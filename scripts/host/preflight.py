#!/usr/bin/env python3
"""WP-4 (BB-080/081/085/087): one PASS/FAIL list for a deployed Bizboard host.

Run on the host after a deploy (the checks marked [host] read the compose stack, sockets and the
backup folder there); from a laptop use --remote to run only the URL checks.

    python3 scripts/host/preflight.py --url https://staging.example.in --env-file .env \
        --compose "-f docker-compose.yml -f docker-compose.prod.yml"
    python3 scripts/host/preflight.py --url https://staging.example.in --remote

Exit status 1 when any check FAILs. MANUAL lines are steps a person confirms; they do not fail
the run. Standard library only, so it runs on a bare VM.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shlex
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

# HOSTED_STAGING.md §2: staging and production refuse to boot (or are unsafe) without these.
REQUIRED_ENV = (
    "DJANGO_ENV", "DJANGO_SECRET_KEY", "POSTGRES_RLS_ENABLED", "APP_DB_USER", "APP_DB_PASSWORD",
    "MFA_ENCRYPTION_KEY", "PLANWAVE_DATA_KEY", "GSP_FERNET_KEY", "OTP_PEPPER", "METRICS_TOKEN",
    "SENTRY_DSN", "SENTRY_RELEASE", "VITE_SENTRY_DSN", "SENTRY_BROWSER_DSN", "NUM_TRUSTED_PROXIES",
    "BACKUP_OFFSITE_CMD", "BACKUP_REQUIRE_OFFSITE",
    # WP-6 game day: without it the backup-age cron and Alertmanager cannot page (/api/v1/ops/alert/).
    "OPS_ALERT_TOKEN",
)
PLACEHOLDER = re.compile(r"(CHANGE_?ME|change-me|REPLACE|your[-_]|example\.com|<.*>|xxx|not-for-prod)", re.I)
# Ports a published host socket may use. 22 = SSH, 80/443 = the edge. Anything else bound to all
# interfaces means a container (or service) is reachable around ufw.
PUBLIC_PORTS_OK = {22, 80, 443}
TLS_MIN_DAYS = 21
BACKUP_MAX_AGE_H = 26

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))


# ---------- pure helpers (unit-tested in backend/tests/test_host_preflight.py) ----------

def parse_env(text: str) -> dict[str, str]:
    env = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def env_problems(env: dict[str, str]) -> list[str]:
    out = []
    for key in REQUIRED_ENV:
        val = env.get(key, "")
        if not val:
            out.append(f"{key} missing")
        elif PLACEHOLDER.search(val):
            out.append(f"{key} is a placeholder")
    if env.get("DJANGO_ENV") not in ("staging", "production"):
        out.append(f"DJANGO_ENV={env.get('DJANGO_ENV')!r} (want staging or production)")
    if env.get("POSTGRES_RLS_ENABLED") not in ("1", "true", "True"):
        out.append("POSTGRES_RLS_ENABLED is not 1")
    if env.get("APP_BIND", "127.0.0.1") not in ("127.0.0.1", "localhost"):
        out.append(f"APP_BIND={env.get('APP_BIND')} (nginx should bind loopback behind the edge)")
    return out


def exposed_listeners(ss_output: str) -> list[str]:
    """Listening TCP sockets bound to every interface on a port outside PUBLIC_PORTS_OK."""
    bad = []
    for line in ss_output.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] != "LISTEN":
            continue
        local = parts[3]
        host, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        if host in ("0.0.0.0", "*", "[::]", "::") and int(port) not in PUBLIC_PORTS_OK:  # noqa: S104 - detecting it
            bad.append(local + (f" {parts[-1]}" if "users:" in parts[-1] else ""))
    return bad


def published_container_ports(docker_ps: str) -> list[str]:
    """`docker ps --format '{{.Names}} {{.Ports}}'` lines that publish on all interfaces."""
    bad = []
    for line in docker_ps.splitlines():
        if "0.0.0.0:" in line or ":::" in line or "[::]:" in line:
            name = line.split()[0] if line.split() else line
            bad.append(name)
    return bad


def newest_backup_age_hours(folder: Path, now: float | None = None) -> float | None:
    files = [p for p in folder.glob("**/*") if p.is_file() and p.suffix in (".age", ".gpg", ".enc")]
    if not files:
        return None
    newest = max(p.stat().st_mtime for p in files)
    return ((now or time.time()) - newest) / 3600


def tls_days_left(not_after: str, now: dt.datetime | None = None) -> int:
    expires = dt.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
    return (expires - (now or dt.datetime.now(dt.timezone.utc))).days


# ---------- checks ----------

def http(url: str, method: str = "GET", headers: dict | None = None, follow: bool = True):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with opener.open(req, timeout=20) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)
    except Exception as e:  # noqa: BLE001 - report, don't crash the list
        return None, {"error": str(e)}


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        record("FAIL", "URL is https", url)
        return
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((parts.hostname, parts.port or 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=parts.hostname) as tls:
                days = tls_days_left(tls.getpeercert()["notAfter"])
        record("PASS" if days >= TLS_MIN_DAYS else "FAIL", "TLS certificate valid", f"{days} days left")
    except Exception as e:  # noqa: BLE001
        record("FAIL", "TLS certificate valid", str(e))
    status, headers = http(f"{url}/api/v1/health/?ready=1")
    record("PASS" if status == 200 else "FAIL", "health ?ready=1 (db, redis, beat heartbeat)", f"HTTP {status}")
    hsts = headers.get("Strict-Transport-Security", "")
    record("PASS" if "max-age=" in hsts else "FAIL", "HSTS header", hsts or "missing")
    pp = headers.get("Permissions-Policy", "")
    record("PASS" if "camera=" in pp else "FAIL", "Permissions-Policy header", pp[:60] or "missing")
    status, headers = http(f"http://{parts.hostname}/", follow=False)
    loc = headers.get("Location", "")
    record("PASS" if status in (301, 302, 307, 308) and loc.startswith("https://") else "FAIL",
           "plain HTTP redirects to HTTPS", f"HTTP {status} -> {loc or '-'}")
    status, _ = http(f"{url}/admin/", follow=False)
    record("PASS" if status in (403, 404) else "MANUAL", "Django admin not public",
           f"HTTP {status}; expected 404 unless ADMIN_ENABLED and restricted at the edge")
    record("MANUAL", "NUM_TRUSTED_PROXIES matches the hop count",
           "curl -H 'X-Forwarded-For: 1.2.3.4' a signed-in request, then check Settings > Security sessions "
           "shows your real IP, not 1.2.3.4 or the proxy (HOSTED_STAGING.md 'Client IP behind proxies')")


def run(cmd: str) -> tuple[int, str]:
    # Operator-run tool; commands are fixed here or come from the operator's own env file.
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)  # noqa: S602
    return p.returncode, (p.stdout + p.stderr).strip()


def check_host(env_file: Path, compose: str, backup_dir: Path) -> None:
    env = parse_env(env_file.read_text(encoding="utf-8")) if env_file.exists() else {}
    if not env:
        record("FAIL", "env file", f"{env_file} missing or empty")
    else:
        problems = env_problems(env)
        record("PASS" if not problems else "FAIL", "required env values", "; ".join(problems) or f"{len(REQUIRED_ENV)} set")
        mode = env_file.stat().st_mode & 0o777
        record("PASS" if mode & 0o077 == 0 else "FAIL", "env file not readable by others", oct(mode))
    dc = f"docker compose --env-file {shlex.quote(str(env_file))} {compose}"
    code, out = run(f"{dc} exec -T api python manage.py shell -c "  # noqa: S608 - fixed SQL, no input
                    "\"from django.db import connection as c; k=c.cursor(); "
                    "k.execute('select current_user, rolsuper, rolbypassrls from pg_roles where rolname=current_user'); print(k.fetchone()); "
                    "k.execute('show statement_timeout'); print(k.fetchone()[0])\"")
    lines = out.splitlines()[-2:] if code == 0 else []
    ok_role = bool(lines) and "False, False" in lines[0]
    record("PASS" if ok_role else "FAIL", "app connects as a role without superuser / BYPASSRLS", lines[0] if lines else out[-200:])
    record("PASS" if lines and lines[-1] == "30s" else "FAIL", "statement_timeout 30s on the app connection",
           lines[-1] if lines else "-")
    code, out = run(f"{dc} exec -T api python manage.py migrate --check")
    record("PASS" if code == 0 else "FAIL", "migrations at head", out.splitlines()[-1] if out else "")
    code, out = run(f"{dc} exec -T worker celery -A config inspect ping --timeout 10")
    record("PASS" if code == 0 and "pong" in out else "FAIL", "worker answers ping", out.splitlines()[-1] if out else "")
    code, out = run("ss -tlnpH 2>/dev/null || ss -tlnp")
    exposed = exposed_listeners(out) if code == 0 else ["ss failed: " + out[-120:]]
    record("PASS" if not exposed else "FAIL", "nothing but 22/80/443 listens on all interfaces", ", ".join(exposed) or "ok")
    code, out = run("docker ps --format '{{.Names}} {{.Ports}}'")
    published = published_container_ports(out) if code == 0 else ["docker ps failed"]
    record("PASS" if not published else "FAIL", "no container publishes on 0.0.0.0 (Docker bypasses ufw)",
           ", ".join(published) or "ok")
    age = newest_backup_age_hours(backup_dir)
    record("PASS" if age is not None and age < BACKUP_MAX_AGE_H else "FAIL", "newest encrypted backup < 26 h",
           "none found" if age is None else f"{age:.1f} h old in {backup_dir}")
    offsite = env.get("BACKUP_OFFSITE_CHECK_CMD", "")
    if offsite:
        code, out = run(offsite)
        record("PASS" if code == 0 else "FAIL", "off-host backup copy exists", out[-120:])
    else:
        record("MANUAL", "off-host backup copy exists", "set BACKUP_OFFSITE_CHECK_CMD (e.g. a bucket listing) to automate")
    record("MANUAL", "error tracking receives events", f"{dc} exec api python manage.py sentry_test_event")
    record("MANUAL", "alert reaches the on-call phone and email", "docs/ops/ALERTS.md test alert")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--remote", action="store_true", help="only the URL checks (from a laptop)")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--compose", default="-f docker-compose.yml -f docker-compose.prod.yml")
    ap.add_argument("--backup-dir", default=os.environ.get("BACKUP_DIR", "/backups"))
    args = ap.parse_args()
    check_url(args.url.rstrip("/"))
    if not args.remote:
        check_host(Path(args.env_file), args.compose, Path(args.backup_dir))
    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        print(f"{status:<6} {name:<{width}}  {detail}")
    fails = sum(1 for s, _, _ in results if s == "FAIL")
    print(f"\n{fails} FAIL, {sum(1 for s, _, _ in results if s == 'PASS')} PASS, "
          f"{sum(1 for s, _, _ in results if s == 'MANUAL')} MANUAL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

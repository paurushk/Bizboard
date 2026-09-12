#!/usr/bin/env bash
# QOS-0020 — edge TLS smoke: run this against the real pilot host after ops
# stands up TLS termination (Caddy/nginx/cloud LB — whichever the deploy
# actually uses; this repo deliberately doesn't pick one, see docker-compose.yml's
# `nginx` service comment). Confirms end-user traffic is actually protected,
# not just that Django is *configured* to expect HTTPS (SECURE_HSTS_SECONDS
# etc. in config/settings.py only take effect once something upstream
# terminates TLS and forwards X-Forwarded-Proto).
#
# Usage:
#   scripts/edge_tls_smoke.sh https://pilot.example.com
#
# Exit 0 = pass, non-zero = fail with the reason on stderr. Wire this into
# ENV_CHECKLIST.md item #1 (TLS) instead of a bare sign-off checkbox.
set -euo pipefail

URL="${1:?Usage: scripts/edge_tls_smoke.sh https://your-pilot-host}"
HOST="$(echo "$URL" | sed -E 's#^[a-zA-Z]+://##; s#/.*##; s#:.*##')"
HTTP_URL="http://${HOST}/"

fail() { echo "FAIL: $1" >&2; exit 1; }

echo "1. HTTPS is reachable and returns a real response..."
https_headers="$(curl -sS -D - -o /dev/null --max-time 10 "$URL" || true)"
[ -n "$https_headers" ] || fail "no response from $URL over HTTPS"
status_line="$(echo "$https_headers" | head -n 1)"
echo "   $status_line"
echo "$status_line" | grep -qE ' (2[0-9]{2}|3[0-9]{2}) ' || fail "unexpected status: $status_line"

echo "2. Plain HTTP redirects to HTTPS (never serves the app over cleartext)..."
http_headers="$(curl -sS -D - -o /dev/null --max-time 10 "$HTTP_URL" || true)"
[ -n "$http_headers" ] || fail "no response from $HTTP_URL over plain HTTP"
http_status="$(echo "$http_headers" | head -n 1)"
echo "   $http_status"
echo "$http_status" | grep -qE ' 30[1278] ' || fail "plain HTTP did not redirect (got: $http_status) — TLS is not enforced at the edge"
location="$(echo "$http_headers" | grep -i '^location:' | tr -d '\r')"
echo "$location" | grep -qi '^location: *https://' || fail "HTTP redirect does not target https:// ($location)"

echo "3. HSTS header is present with a real max-age..."
echo "$https_headers" | grep -qi '^strict-transport-security:' || fail "no Strict-Transport-Security header — SECURE_HSTS_SECONDS in config/settings.py only fires once the edge forwards a correct X-Forwarded-Proto"
hsts="$(echo "$https_headers" | grep -i '^strict-transport-security:' | tr -d '\r')"
echo "   $hsts"
max_age="$(echo "$hsts" | grep -oE 'max-age=[0-9]+' | cut -d= -f2)"
[ -n "$max_age" ] && [ "$max_age" -gt 0 ] || fail "HSTS max-age is missing or zero ($hsts)"

echo "PASS — $URL enforces HTTPS at the edge with HSTS (max-age=${max_age})."

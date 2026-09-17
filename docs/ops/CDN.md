# CDN / cache policy (12.5)

Static-only CDN in front of the SPA. Keep `/api` uncached. **Not** a TLS
design, WAF spec, or CDN vendor contract.

## What the code does

- `web/nginx.conf` serves hashed JS/CSS/fonts as `public, immutable` and
  `index.html` / service-worker scripts as `no-store`. There is no
  `proxy_pass` and no `location /api` in that file.
- Django `RequestIdMiddleware` sets `Cache-Control: no-store, no-cache,
  must-revalidate, private` on every `/api/` response so a shared cache in
  front of the API cannot store tenant JSON.
- `/health/` stays outside `/api/` so an edge can probe liveness without
  treating it as a tenant document.

## What operators still own

Pick a CDN (or none). Pin TLS at the load balancer (Human). Never put a
caching origin in front of `/api` even if the Django header is present —
headers are the belt; topology is the braces.

Gating tests: `tests/errors/test_freeze_gate_contracts.py::test_api_response_carries_hardening_headers`,
`tests/test_ops_templates.py` nginx + this file.

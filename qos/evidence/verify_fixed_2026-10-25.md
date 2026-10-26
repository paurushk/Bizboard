# verify_fixed — 2026-10-25 (browser-guarded items)

Light e2e (chromium, mobile, webkit; mocked API) and golden e2e (live Django + Postgres 17) on an idle machine; failures re-run serially to separate load timeouts.

| Item | Evidence |
|---|---|
| QOS-0007 | web/e2e/a11y.spec.ts J-A11Y-P2-KEYBOARD passed on chromium, mobile and webkit (light run 2026-10-25). |
| QOS-0010 | web/e2e/route-smoke.spec.ts: all routes passed in the serial rerun (first-run failures were load timeouts). |
| QOS-0013 | WebKit project: 74 tests run; the one first-run failure passed in the serial rerun (2026-10-25). |
| QOS-0016 | web/e2e-golden/v95-dashboard-p95.spec.ts passed in the golden run against Django + Postgres 17 (2026-10-25). |
| QOS-0017 | web/e2e/pos-friction.spec.ts passed on chromium and mobile (light run 2026-10-25). |
| QOS-0025 | web/e2e/personas/role-boundaries.spec.ts passed on all projects in the serial rerun (2026-10-25). |
| QOS-0026 | web/e2e/mobile-layout.spec.ts passed on all projects (light run 2026-10-25). |
| QOS-0040 | web/e2e/pos-friction.spec.ts remembered-tender test passed (light run 2026-10-25). |
| QOS-0096 | web/e2e/route-smoke.spec.ts: all routes passed in the serial rerun (2026-10-25). |

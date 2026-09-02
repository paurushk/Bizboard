> **Archived historical checklist.** Authoritative decisioning: `docs/reviews/` (live quality log 2026-09-02).

# BizBoard — PRODUCTION READINESS (pointer)

| Artifact | Role |
|----------|------|
| [`docs/reviews/01_EXECUTIVE_SUMMARY.md`](docs/reviews/01_EXECUTIVE_SUMMARY.md) | Current scores |
| [`docs/reviews/21_PRODUCTION_READINESS.md`](docs/reviews/21_PRODUCTION_READINESS.md) | Readiness narrative |
| [`docs/reviews/QUALITY_AUDIT_LIVE_2026-09-02.md`](docs/reviews/QUALITY_AUDIT_LIVE_2026-09-02.md) | Live defect register |
| [`docs/pilot/FINAL_GATES_10.md`](docs/pilot/FINAL_GATES_10.md) | Non-negotiable for **10/10** |
| [`docs/pilot/GO_NO_GO.md`](docs/pilot/GO_NO_GO.md) | Human sign-off |

## Honest status (2026-09-02)

Wave-16 scores below are **historical** (2026-08-04) and must not be used as a ship gate.

- **Do not treat PR ~8.5 / GST ~8.5 as current.** Re-score after the 2026-09-02 quality audit remediations land in CI.
- **Dogfood:** Conditional with `accounting_enabled` + honesty banners
- **10/10:** Blocked by Final Gates (signed GO_NO_GO, TLS, restore drill, digest verify, Sentry/PagerDuty, live GSP credentials, CA letter)
- **Packaged mobile:** Requires `CAPACITOR_SERVER_URL` / `VITE_APP_ORIGIN` same-origin as the API. JWT cookies stay `SameSite=Lax`. Native push and scanner plugins are **not** shipped.
- **GSTR-4 / CMP-08 / GSTR-6/7/8/9:** worksheets or honesty stubs — **not** GSTN filing engines.

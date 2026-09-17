# Launch evidence pack (G1–G17)

Fill paths and SHAs before the go-meeting. **Do not tick Human boxes here.**
The signed sheet is `docs/ops/RELEASE_CHECKLIST.md` + `docs/pilot/GO_NO_GO.md`.

| Gate | LLM-ready artifact | Human still owns |
|---|---|---|
| G1 Freeze | `python scripts/ops/freeze_baseline.py` digest of `docs/FREEZE_SCOPE.md` | Sign freeze; cut tag |
| G2 Architecture | `docs/architecture.md`, `docs/ops/ADR_TOPOLOGY.md` | Managed PG vs VM |
| G3 Tenant | `backend/tests/tenancy/`, staging `POSTGRES_RLS_ENABLED` | Hosted two-company IDOR |
| G4 Identity | OTP/lockout + `tests/tenancy/test_rbac_matrix.py` | Live SMS or OTP off |
| G5 Integrity | `docs/FREEZE_SCOPE_COVERAGE.md` + invariants | UAT + CA letter |
| G6 Cutover | `docs/ops/CUTOVER.md`, `cutover_recon` | Customer files + T0 |
| G7 Database | `docs/ops/POSTGRES.md`, `deploy/pgbouncer.ini` | Apply on managed PG |
| G8 Billing | quotas, SaaS dunning, recon, DLQ tests | Razorpay live keys |
| G9 Integrations | `docs/ops/INTEGRATIONS.md` + inventory API | Vendor contracts |
| G10 Security | `docs/ops/STRIDE.md`, ZAP skip-job, gitleaks | Pentest + counsel |
| G11 Ops | `ALERTS.md`, `RUNBOOKS.md`, `ONCALL_ROSTER.md`, `OGATE_HUMAN.md`, `OGATE_GREP_WALK.md` | Named on-call + Sentry page received |
| G12 Capacity | k6 advisory + QOS-0003 | Staging soak numbers |
| G13 DR | restore drill + `BCP.md` + `DR_CADENCE.md` | Calendar + dated restore |
| G14 CI/CD | required checks + SHA images | Registry + prod approve |
| G15 Beta | `docs/pilot/FAQS.md`, `BETA_ARCHETYPE_CHECKLIST.md` | Real businesses |
| G16 Legal | `docs/pilot/DPDP_POSTURE.md` inventory only | ToS / DPA / DPIA |
| G17 Launch | this pack + `RELEASE_CHECKLIST.md` | All roles sign |

Env rows: copy `docs/pilot/ENV_CHECKLIST.md`. TLS / SMTP / Sentry still need
a live host. Flag pins: `.env.production.example` Table B keys = 0.

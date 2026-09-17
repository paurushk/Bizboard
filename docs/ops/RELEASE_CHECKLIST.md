# Release checklist (1.5)

Single launch sheet. **Do not tick Human boxes in an LLM session.**

| Gate | Artifact | LLM evidence | Human |
|---|---|---|---|
| G1 Freeze | `FREEZE_SCOPE.md` SHA via `python scripts/ops/freeze_baseline.py` | Script | Sign G1; cut tag |
| G2 Architecture | `docs/architecture.md` + `docs/ops/ADR_TOPOLOGY.md` | Draft | Pick managed PG vs VM |
| G3 Tenant | tenancy tests + staging RLS flag | Tests | Hosted two-company IDOR |
| G4 Identity | OTP/lockout/RBAC matrix | Tests | Live SMS or OTP off |
| G5 Integrity | Freeze coverage map + invariants | Tests | UAT + CA letter |
| G6 Cutover | `docs/ops/CUTOVER.md` + `cutover_recon` | Templates | Customer files + T0 |
| G7 Database | `docs/ops/POSTGRES.md` | Params | Apply on managed PG |
| G8 Billing | quotas, dunning, recon, DLQ | Tests | Razorpay live keys |
| G9 Integrations | inventory API + circuits | Tests | Vendor contracts |
| G10 Security | STRIDE + ZAP skip-job + gitleaks | Drafts/CI | Pentest + counsel |
| G11 Ops | `ALERTS.md` / `RUNBOOKS.md` | Drafts | Named on-call |
| G12 Capacity | k6 advisory + QOS-0003 | Scripts | Staging soak numbers |
| G13 DR | restore drill + `BCP.md` | Scripts | Calendar + dated restore |
| G14 CI/CD | required checks + SHA images | CI | Registry + prod approve |
| G15 Beta | FAQs/training | Copy | Real businesses |
| G16 Legal | DPDP posture only | Inventory | ToS/DPA |
| G17 Launch | this sheet + `GO_NO_GO.md` | Fill evidence | All roles sign |

Env rows: copy `docs/pilot/ENV_CHECKLIST.md` into the go-meeting notes. TLS/SMTP/Sentry still need a live host.

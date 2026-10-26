# Risk register and launch approval (1.4, BB-150)

Engineering keeps this current; the founder owns each residual: **Accept** (sign below), **Fix
first**, or **Block launch**. Refreshed 2026-10-23. L = likelihood, I = impact (H/M/L, Sev-1 =
the worst kind).

| ID | Risk | L | I | Mitigation in place | Residual (2026-10-23) | Founder |
|---|---|---|---|---|---|---|
| R001 | Cross-tenant read or write | M | Sev-1 | `company_id` scoping, IDOR route matrix, Postgres row-level security forced, non-superuser app role | Proven locally and on local staging; hosted run and pentest pending | |
| R002 | Double complete / stock oversell | M | H | `select_for_update`, status machines, Postgres race tests, deadlock fix (FOR NO KEY UPDATE) | Hosted concurrency run pending | |
| R003 | Webhook replay or forged capture | M | H | HMAC, `ProcessedWebhookEvent`, dead-letter queue | Live gateway keys not set | |
| R004 | SaaS billing vs customer receivables mixed up | M | H | Separate dunning and recon modules, tests | Chargeback policy unsigned | |
| R005 | PDF or worker hangs silently | H | M | 409 + FAILED visible, beat heartbeat, alert rules, GlitchTip | On-call named (primary only) | |
| R006 | Backup never restored | M | Sev-1 | Encrypted nightly dump, restore drill script (passed locally) | Drill against real off-host backups pending | |
| R007 | Out-of-scope UI ships in the production image | M | H | Freeze table-B guard; CD build args | Low | |
| R008 | Database role bypasses row-level security | H | Sev-1 | App runs as `NOSUPERUSER NOBYPASSRLS`; startup refuses RLS off in staging/production | Done on local staging; hosted check pending | |
| R009 | Secret committed to git | M | H | gitleaks; env files gitignored; log redaction | Rotate at once if one lands | |
| R010 | Launch without signatures | H | Launch block | Checklists, sign-off pack, this sheet | Signatures below | |
| R011 | One person on call, no backup | H | H | Paging by email + phone push; runbooks; tabletop pack | No cover for illness or travel; name a backup | |
| R012 | Legal documents not published (ToS, privacy policy, DPA, refund policy) | H | Launch block | Acceptance recording built; policy proposals in the sign-off pack | Counsel to write and publish | |
| R013 | GST logic not reviewed by a CA | M | Sev-1 | Automated GST scenarios, worksheet-only filing | CA engagement and sign-off pending | |
| R014 | No independent security test | M | H | CodeQL, Trivy, Dependabot, STRIDE; rate-limit and lockout fixes 2026-10-23 | Pentest on hosted staging pending | |
| R015 | Error tracker on the same host as the app | M | M | Separate-VM mode documented; tracker-down watcher pages | Run it on its own VM in production | |
| R016 | Load behaviour unproven | M | H | k6 scripts fixed and dry-run; Complete query budget | Hosted soak pending; Complete cap decided: 60/min/company (D-11) | |
| R017 | Payments not live | H | H | Sandbox flows tested (152 tests) | Razorpay live account, KYC, test keys | |
| R018 | No real customers yet | H | H | Pilot recruitment pack, parallel-month procedure | Sign 2–3 pilots before general launch | |

## Launch approval

Launch to a limited pilot cohort only when every line is ticked with evidence. A ticked line
needs a dated record (test run, drill log, signature) named in the evidence column.

| # | Gate | Evidence | Ticked by / date |
|---|---|---|---|
| 1 | Release-1 scope signed | `docs/requirements/REQUIREMENTS_BASELINE.md` | |
| 2 | Sign-off pack decided | `docs/roadmap/SIGNOFF_PACK_2026-10-23.md` | |
| 3 | Legal published (ToS, privacy, DPA, refunds) | Counsel; live URLs | |
| 4 | CA sign-off on GST, invoices, SaaS GST | `docs/ca/SAAS_CA_PACK.md` | |
| 5 | Hosted staging passes `HOSTED_STAGING.md` §4 | Execution record there | |
| 6 | Tenant isolation proven on hosted + pentest closed | Pentest report; BB-029/143/144 | |
| 7 | Backups restored from off-host; RPO/RTO met | Drill log; BB-097/145 | |
| 8 | Monitoring and paging reach a person on the host | GlitchTip + alert test-fires; BB-146 | |
| 9 | Load and soak within the signed targets | Dated results file; BB-072/078 | |
| 10 | Payments live and reconciled | Razorpay live; BB-054/147 | |
| 11 | Pilot acceptance criteria agreed | Sign-off pack B-13 | |
| 12 | Risks above accepted or fixed | Founder column filled | |

Approved for limited launch: Founder ____________________  Date __________

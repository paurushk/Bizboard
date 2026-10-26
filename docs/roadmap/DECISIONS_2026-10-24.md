# Founder decisions, 2026-10-24

Recorded from the founder's answers in the working session. Each line names what it changes.
Earlier same-day answers are included so this file is the one place to look.

| # | Question | Decision | What it changes |
| --- | --- | --- | --- |
| D-01 | On-call rota | Founder is primary; no backup yet | `docs/ops/ONCALL_ROSTER.md`; recorded as a risk (no backup) |
| D-02 | Alert recipient | Founder's email, plus phone push (ntfy) | GlitchTip alerts and `OPS_NTFY_URL`; topic kept out of git |
| D-03 | Razorpay | Skipped for now | BB-054, BB-111, BB-147 stay Blocked |
| D-04 | Quotes and orders vs invoice GST (BB-100 F1) | Quotations, sales orders and purchase orders take the same HSN-table GST rate as the bill, with the same notice | `_RATEABLE_DOCS` in `backend/core/services/tax_engine/india.py` |
| D-05 | Team list for pickers (BB-100 F10) | Any active member may read a team list: id, name and role only | `GET /api/v1/company/members/`; `/company/users/` stays owner-only |
| D-06 | Committing this session's work | **Not yet.** Leave everything uncommitted for now | BB-017 and BB-141 keep "not through CI" until a commit and push |
| D-07 | Drafts to write for approval | Hindi FAQ answers, legal first drafts (terms, privacy policy, data processing agreement), NPS/CSAT survey. Not the website or pricing page | BB-100/103 (Hindi review), BB-050/120/121/129 (counsel), BB-136 |
| D-08 | NPS/CSAT survey (was deferred as P-04) | Build it now, behind a feature flag that defaults off | BB-136 |
| D-09 | F2: bills of supply missing from GSTR-1 | Write an options note for the CA; no code change until the CA decides | BB-022, `docs/ca/` |
| D-10 | Load-test logins | `seed_load_tenant` creates 25 staff logins, one per k6 virtual user | BB-072, BB-078, `load/` |
| D-11 | Invoice Complete limit per company | 60 per minute (was 30); purchase bills stay at 30 | `sales_complete` in `backend/config/settings.py`; `load/README.md`; sign-off pack B-6 |
| D-12 | Commit (asked again 2026-10-25) | Not yet | As D-06 |
| D-13 | How long a closed or read-only workspace is kept | **Owner can set it per company; 90 days by default.** Owner is warned before deletion and can export until then; the anonymised 8-year tax copy is kept either way. Deletion runs only once the deployment switch `DATA_RETENTION_ENFORCE` is on (off until counsel confirms); until then it only warns and logs | BB-070, BB-034, legal drafts |
| D-14 | F2: bills of supply in GSTR-1/3B | Build options B + A now, behind a company flag that stays off until the CA agrees: a regular company's Non-GST invoice may hold only nil, exempt or non-GST lines; those invoices are reported in Table 8, Table 13 and GSTR-3B 3.1(c)/(e) | BB-022, `docs/ca/F2_BILLS_OF_SUPPLY_IN_GST_RETURNS.md` |
| D-15 | Website and pricing page | Draft now with the proposed prices marked as draft; do not publish | BB-133 |
| D-16 | GST worksheets on paid plans (they were off, while the trial had them) | **All four plans (Free, Starter, Professional, Enterprise) include GSTR-1 and GSTR-3B worksheets**, so upgrading never takes them away. Worksheets only: GSTN JSON, portal filing and 2B/IMS stay out | `billing/entitlements.py` (`freeze_safe_modules`), migration `billing/0021_paid_plans_gst_worksheets`; BB-005, BB-052, BB-133 |
| D-17 | Downloads for the LLM work plan (`docs/roadmap/LLM_WORK_PLAN_2026-10-25.md`) | Approved: OWASP ZAP image, Prometheus + Alertmanager images, a PgBouncer image | WP-1, WP-5, WP-6 |
| D-18 | Hosting provider for the setup kit | Provider-neutral only for now; provider annex written once chosen | WP-4; BB-080/081/085/087 |
| D-19 | Bizboard referral programme (BB-139, was deferred as G-03) | Build now behind `ENABLE_SAAS_REFERRALS` (off). Reward: **recorded only** — admin lists qualified referrals, founder settles by hand | WP-7 |
| D-20 | Commit, push and PR (asked again) | Not approved. Run every CI gate locally; do not commit or push | WP-8; BB-017 stays open |

Still open for the founder: the sign-off pack (`docs/roadmap/SIGNOFF_PACK_2026-10-23.md`), the
launch approval sheet in `docs/ops/RISK_REGISTER.md`, and when to commit (D-06).

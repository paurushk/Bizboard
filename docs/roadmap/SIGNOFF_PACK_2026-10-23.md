# Founder sign-off pack, 2026-10-23

One sitting closes about 20 readiness rows. Each decision below has a **proposal** built from
what the product already does, the realistic **options**, and the checklist rows it closes.
Write your choice in the last column (or "as proposed"), sign at the bottom, and the rows move to
Passed with this file as evidence. Items marked *(counsel)* or *(CA)* need their wording or
review after your decision; the decision itself is yours.

## Decisions at a glance

| # | Decision | Proposal | Closes | Your choice |
|---|---|---|---|---|
| B-1 | Plans and prices | Keep the seeded plans: Free ₹0 · Starter ₹499 · Professional ₹1,499 · Enterprise ₹4,999 per month, plus 18% GST | BB-005, BB-052 | |
| B-2 | Trial | 14 days, no card, one trial per business (built) | BB-005 | |
| B-3 | Grace after a failed renewal | 7 days of full use with a banner, then read-only; data kept | BB-059 | |
| B-4 | Cancellation and refunds | Cancel any time, effective at period end; no refund for a started month; duplicate or wrong charges refunded in 7 working days *(counsel words it)* | BB-122 | |
| B-5 | Trial-to-paid process | Checklist → founder emails (day 0, 3, 7) → day-12 reminder → read-only at day 14; founder calls engaged trials | BB-137 | |
| B-6 | Performance targets | Sign the table in `docs/ops/SLO.md` as is; Complete cap set to 60/min per company (D-11) | BB-071 | |
| B-7 | Capacity thresholds | Scale when any line in §B-7 holds for its window | BB-079 | |
| B-8 | Backup retention | 30 daily + 12 monthly encrypted off-host; PITR 7 days | BB-096 | |
| B-9 | RPO / RTO | RPO 15 min (PITR), RTO 4 h | BB-098 | |
| B-10 | Support severity and response | P0 2 h · P1 4 business h · P2 1 business day · P3 2 business days | BB-126 | |
| B-11 | Positioning | Statement in §B-11 | BB-130 | |
| B-12 | Segments and channels | ARCH-03 B2B traders first; CA referrals, trade associations, WhatsApp communities | BB-132 | |
| B-13 | Pilot acceptance criteria | Six criteria in §B-13 (pilots agree too) | BB-135 | |
| B-14 | Requirements baseline | `docs/requirements/REQUIREMENTS_BASELINE.md` | BB-004 | |
| B-15 | Known-risk register and launch approval | `docs/ops/RISK_REGISTER.md` (refreshed) and its approval sheet | BB-150 | |

## B-1 Plans and prices (BB-005, BB-052)

Already in `billing/management/commands/seed_plans.py`, enforced by the billing module:

| Plan | Price / month (ex-GST) | Users | Completed bills / month | Storage | API / min | POS |
|---|---|---|---|---|---|---|
| Free | ₹0 | 1 | 30 | 50 MB | 60 | no |
| Starter | ₹499 | 2 | 300 | 500 MB | 120 | yes |
| Professional | ₹1,499 | 5 | 2,000 | 2 GB | 300 | yes |
| Enterprise | ₹4,999 | unlimited | unlimited | unlimited | unlimited | yes |

Options: (a) as above; (b) a pilot offer: first 3 months free for signed pilots, then the list
price; (c) different numbers (edit the seed, one line per plan). Infra cost per tenant at pilot
scale is in `docs/ops/UNIT_ECONOMICS.md`; SaaS GST on these invoices needs the CA (BB-124).

## B-2 Trial (BB-005)

Built: 14 days (`BILLING_TRIAL_DAYS`), no card; 3 days when a live checkout takes a card
(`BILLING_CHECKOUT_TRIAL_DAYS`); one trial per business (fingerprinted, `test_tds_claims_trial_guard.py`).
After the trial the workspace is read-only, never deleted. Options: 14 (proposed) · 30 for
pilots only.

## B-3 Grace after a failed renewal (BB-059)

Today `BILLING_PAST_DUE_GRACE_DAYS=0`: read-only the moment the paid period ends unpaid. A UPI
mandate debit can fail for reasons the customer cannot see (bank downtime, limit), so 0 punishes
honest customers. **Proposal: 7 days** of full use with a banner and the renewal retries, then
read-only; data is kept. Options: 0 · 3 · 7. This is one env value; no code change.

## B-4 Cancellation and refunds (BB-122) *(counsel words it)*

What the product does (`docs/ops/REFUND_CANCELLATION.md`, updated today):
- Cancel (Suspend workspace) any time; you keep working to the end of the paid period, then
  read-only; renewals stop.
- Upgrade: the difference for the rest of the period is charged now (proration is built).
  Downgrade: at the next renewal, no charge now.
- TDS deducted on our invoices is credited to the next renewal or refunded (Form 16A claim).

**Proposal for the policy text:** no refund for a period already started; a duplicate or wrong
charge is refunded to the original method within 7 working days of being reported; annual plans
(if introduced later) refund unused whole months. Counsel turns this into the published policy.

## B-5 Trial-to-paid process (BB-137)

| Day | What happens | Who |
|---|---|---|
| 0 | Sign-up; Getting started checklist on the dashboard (there is no automatic welcome email yet: the founder sends one) | Product + founder |
| 1–7 | If a step is stuck (no first invoice by day 3), a short how-to email | Founder (manual until automated) |
| 7 | "Half your trial" note with what they have done and the plan that fits | Founder |
| 12 | Reminder: read-only in 2 days; one-click plan choice on Billing | Product banner + email |
| 14 | Read-only; data kept; choosing a plan restores editing at once | Product |
| Any | Trials with 10+ invoices get a call from the founder | Founder |

Measure: trials converted to paid each month (`trial_to_paid` on `/admin/ops/saas-metrics/`) against sign-ups that month.

## B-6 Performance targets (BB-071)

Sign the performance table in `docs/ops/SLO.md` (p95: sign-in 500 ms, dashboard 500 ms, Complete
800 ms, lists 2 s, reports 5 s, 200-line import 10 s; error rate < 0.5%) and the availability
SLO (99.5% / 30 days). They are tested on hosted staging (BB-072/078).

**Complete cap: decided 2026-10-24 (D-11): 60 completions per minute per company** (was 30;
purchase bills stay at 30). Load tests pace to it (`load/README.md`).

## B-7 Capacity thresholds (BB-079)

Scale (or investigate) when, on the production host:

| Signal | Threshold | For | Action |
|---|---|---|---|
| CPU | > 70% | 15 min | Add a gunicorn/Celery worker or a bigger VM |
| Memory | > 80% | 15 min | Same; check for a leak first |
| Postgres connections | > 70% of max | 10 min | PgBouncer session pool size, then a bigger DB |
| Disk (DB or media) | > 75% | — | Grow the volume; check retention |
| Celery backlog | > 500 tasks | 10 min | Add a worker (`docs/ops/WORKER_SCALE.md`) |
| p95 over its target (B-6) | sustained | 30 min | Incident review; scale if load-driven |

## B-8 Backup retention (BB-096)

Built: nightly encrypted dump (GPG or age), off-host copy, retention by age never below the newest
7 (`scripts/backup.sh`, default 30 days); the error tracker's database the same way.
**Proposal:** keep 30 daily + 12 monthly (a lifecycle rule on the backup bucket) + managed-Postgres
point-in-time recovery for 7 days. Statutory GST records are kept in the database for 8 years
regardless (tombstone erasure keeps them).

## B-9 RPO / RTO (BB-098)

**Proposal:** RPO 15 minutes (managed Postgres PITR; 24 hours if only the nightly dump survives),
RTO 4 hours to a working app on a new host. The local restore drill took 147 s for restore plus
books check on a laptop (a floor, not a target). Confirmed by the hosted drill (BB-097).

## B-10 Support severity and response (BB-126)

Severities are the ones on the in-app support form:

| Severity | Meaning | First response | Updates |
|---|---|---|---|
| P0 | Business stopped, cannot bill | 2 hours, 09:00–21:00 IST, every day | Every 2 hours until fixed |
| P1 | Money or stock looks wrong | 4 business hours | Daily |
| P2 | Something is broken | 1 business day | On change |
| P3 | A question | 2 business days | — |

With one on-call person these are honest; tighten after a backup is named (`ONCALL_ROSTER.md`).

## B-11 Positioning (BB-130)

> **Bizboard is billing, stock and books for Indian B2B traders, built so the owner, the counter
> staff and the CA work from the same numbers.** Purchase bill to stock and payables in one step,
> GST invoices in under a minute in English or Hindi, receivables that chase themselves, and
> month-end GST worksheets your CA files from. Your data is yours: export everything, any time.

Against Tally/Busy: modern, mobile, multi-user without a server; against Vyapar/Khatabook:
proper books, inventory and GST worksheets for a growing B2B firm.

## B-12 Segments and channels (BB-132)

Primary: ARCH-03 semi-wholesale B2B traders, ₹1–5 Cr turnover, one GSTIN
(`docs/pilot/RECRUITMENT.md` §1). Next: ARCH-01 counter retail with POS, ARCH-04 multi-godown.
Channels, in order: practising CAs who serve 20+ such firms (one CA = many clients); trade
associations (hardware, building materials, pharma distributors); WhatsApp trader communities;
existing Tally/Busy users unhappy with their tool. Track in the pipeline table (RECRUITMENT §5).

## B-13 Pilot acceptance criteria (BB-135) *(pilots agree too)*

A pilot is accepted when, over 4 weeks:
1. Bizboard is the primary billing system for at least 4 weeks.
2. Parallel month: `compare_trial_balance` shows no unexplained difference above ₹1 per account.
3. Their CA prepares one GSTR-1 from the worksheet without re-keying.
4. Staff create an invoice unaided within 10 minutes after onboarding.
5. No open P0/P1 support request older than its target (B-10).
6. Weekly purchase → sale → payment → return loop with no stock or balance mismatch for 2 weeks.

## Sign-off

| Who | Name | Date | Signature |
|---|---|---|---|
| Founder | | | |
| CA (B-1 GST on SaaS, B-4 invoices) | | | |
| Counsel (B-4 policy text) | | | |

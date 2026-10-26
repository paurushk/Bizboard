# ARCH-03 Pilot Recruitment

**Plan ref:** SR-56. **Target:** 4–6 B2B trading firms for a 4-week desktop pilot.

---

## 1. Who we want

| Attribute | Target |
|---|---|
| Trade | Electrical/hardware, building supplies, packaging materials, auto spares |
| Turnover | ₹1–5 Cr/year (firmly regular GST; below the ₹5 Cr e-invoicing mandate) |
| Structure | One legal entity, one GSTIN, one or two locations |
| Team | Owner + a booker/salesperson + an in-house accountant (Munshi) |
| Ops pattern | Vendor bill arrives with the goods; customers on 15–45 day credit; price slabs |
| Tools today | Tally / Busy / Vyapar / spreadsheets — and frustrated with one of them |
| Must have | A practicing CA who will do the month-end review |

## 2. Screening checklist (all yes to proceed)

- [ ] Single legal GSTIN; no interstate branch/stock-transfer need.
- [ ] Enters purchase invoices when the bill arrives with goods (no separate GRN).
- [ ] Owner + CA accept GSTR-1/3B as worksheets for portal filing, not auto-filing.
- [ ] Below ₹5 Cr AATO **or** willing to keep generating IRN / e-way bills in their current tool and record the number in Bizboard.
- [ ] On a desktop/laptop with a normal A4 printer (no thermal/counter setup needed).
- [ ] Willing to run Bizboard as the primary system for 4 weeks and give weekly feedback.
- [ ] Has a CA who will spend ~1 hour on the month-end review.

If any answer is no → not this pilot cohort. Do not bend a guardrail to hit the count.

## 3. Outreach message (adapt per channel)

> **Subject: 4-week pilot — B2B trade billing + ledgers, no cost**
>
> We're running a small closed pilot of Bizboard, a billing + inventory + ledger tool built for
> Indian B2B traders — purchase bill to stock and payables in one step, quotations with price
> slabs, delivery challans, receivables aging, partial payment allocation, and month-end
> GSTR-1/3B + trial balance worksheets your CA can file from.
>
> Looking for 4–6 trading firms (hardware, building supplies, packaging, auto spares), ₹1–5 Cr
> turnover, single GSTIN, who'll use it as their main system for 4 weeks and talk to us weekly.
> No fee. Your data is yours — full export any time, and deletion on request.
>
> Not in this pilot: live GST portal filing, e-invoice/e-way generation, payroll, manufacturing.
>
> 20-minute call to see if it fits?

## 4. Pipeline

Aim for ~15 screened conversations → 6 onboarded → ≥4 completing 4 weeks. Track name, trade,
turnover, screening result, CA confirmed (y/n), onboarded date, status.

## 5. Pipeline tracker

Keep this table current (copy names here only with the business's consent; otherwise use a
code like P-01). Target from §4: ~15 screened → 6 onboarded → ≥4 completing.

| Code | Trade | Turnover band | Old system | Screening (§2) | CA confirmed | Signed (date) | Books imported | Parallel month | Status |
|---|---|---|---|---|---|---|---|---|---|
| P-01 | | | | | | | | | |

## 6. After a pilot signs: import and the parallel month

1. **Agreement:** `PILOT_AGREEMENT_OUTLINE.md`, signed; onboarding call per `ONBOARDING.md`.
2. **Import their books** (support grants the flag per company, with a reason and ticket, via the
   admin action "Grant or revoke a rollout flag"; revoke after cutover):
   - Busy / Vyapar / Marg: `ENABLE_LEGACY_IMPORT`; parties and items exports with the columns in
     `docs/help/LEGACY_IMPORT.md` (macro: `docs/ops/SUPPORT_MACROS.md` → legacy-import).
   - Tally: `ENABLE_TALLY` (granted per pilot, not globally); Tally XML through the import screen.
   - Opening balances as of the cutover date.
3. **Parallel month:** they keep their old system and Bizboard side by side for one full month.
   At month end, export the old system's trial balance and map its ledgers once:
   ```bash
   python manage.py compare_trial_balance --company <id> --as-of <YYYY-MM-DD> \
     --theirs their_tb.xlsx --mapping their_ledgers.csv --tolerance 1.00
   ```
   Every difference over the tolerance is explained (timing, a missed entry, a mapping) before
   the pilot drops the old system. Keep the output with the pilot's record.
4. **Weekly check-in** for the 4 weeks; feedback goes in as tickets (`docs/ops/TICKET_TAXONOMY.md`).
5. **Exit:** at the end they choose to continue, or take the full readable export (Settings) and we
   delete on request.

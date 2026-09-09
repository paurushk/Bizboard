# ARCH-03 Pilot Runbook (Semi-Wholesaler, desktop-first)

**Cohort:** 4–6 B2B trading firms — hardware, building supplies, packaging, auto-spares.
**Turnover band:** ₹1–5 Cr (stay under the ₹5 Cr e-invoicing threshold for pilot 1).
**Duration:** 4 weeks of daily use + one month-end close with each firm's CA.
**Plan ref:** SR-55 in [`../roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md`](../roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md).
Related: [`ONBOARDING.md`](ONBOARDING.md), [`RUNBOOKS.md`](RUNBOOKS.md), [`RECRUITMENT.md`](RECRUITMENT.md).

---

## 0. Pre-flight checklist (before onboarding a firm)

The four guardrails from `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §13 — all must be **yes**:

- [ ] **Single legal GSTIN.** One legal company, one primary GST registration. Inter-state B2B sales via IGST are fine; multi-registration / interstate branch transfers are not.
- [ ] **Bill-accompanied inwarding.** The firm's office enters the purchase invoice when the vendor bill arrives with the goods (no separate GRN step).
- [ ] **Offline statutory worksheets.** The firm and its CA accept that GSTR-1 / GSTR-3B are calculation worksheets for portal filing, not one-click GSP submission.
- [ ] **E-invoice / e-way stays external.** If above ₹5 Cr AATO (or any consignment > ₹50k), the firm keeps generating IRN / e-way bills in its existing utility and records the number against the Bizboard invoice via the manual IRN / EWB status field.

Also confirm: has a practicing CA who will do the month-end review; on a desktop/laptop with a normal A4 printer; willing to run it as the primary system for 4 weeks.

Known limitations to state up front: no fixed assets, no TDS/TCS return filing or certificates, no RCM automation, no composition, no import/BoE landed cost, no plan-limit enforcement (see `ONBOARDING.md` → Scope honesty 2026-09-09b).

---

## 1. Onboarding (the §13 4-step protocol)

**Step 1 — Masters import.** Bulk CSV: Product Master (with HSN + price lists / slabs), Customers (with GSTIN, credit terms in days, credit limit), Suppliers. Review the preview error report before commit. Re-running the same row is idempotent — no double stock, no double party.

**Step 2 — Opening balances.** Opening inventory per item/godown. Opening customer outstanding and supplier payables. Confirm the trial balance is 0 after the opening load.

**Step 3 — Run the Complete Business Loop, daily:**

```
Purchase bill entered → stock ↑ AND AP ↑ (atomic) → quotation with slabs →
sales order confirmed → credit + overdue audit → delivery challan dispatched →
B2B tax invoice → derived customer AR ↑ → customer receipt (with UTR) →
receipt allocated to specific invoices → ledger statement reconciled
```

**Step 4 — Month-end with the CA (P6).** Period close → export GSTR-1 + GSTR-3B worksheets + trial balance + P&L + balance sheet → CA verifies tax splits and TB = 0 and signs off without recalculating.

---

## 2. Cadence

| When | Action |
|---|---|
| Day 1 | Onboarding steps 1–2 on a screen-share; watch the operator, don't narrate. Set expectations + limitations. |
| Days 2–5 | Operator runs step 3 unaided; a 15-min check-in end of day 3 and day 5. Log every stumble verbatim. |
| Weekly | 30-min call: what broke, what was slow, what they worked around. Score against H-01 (ledger reconciliation) and H-03 (offline drafts) so far. |
| Month-end | Step 4 with the CA. Score H-05. |
| Exit | Go / no-go on ARCH-03 as the beachhead; hand telemetry + notes to the scorecard (SR-53). |

---

## 3. What to measure (hypotheses, `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §11)

- **H-01** — zero unexplained balance discrepancies across ≥100 consecutive payment allocations; no corrupted balances needing DB intervention.
- **H-03** — 100% of offline drafts flush on reconnect with zero duplicate invoice numbers or double stock hits.
- **H-05** — the CA files the client's monthly returns directly from Bizboard worksheets without recalculation.
- (**H-02** POS speed / **H-04** FEFO apply to the parallel ARCH-01 / Stage-4 cohorts, not ARCH-03.)

Telemetry that records these automatically is SR-52..54 — until it lands, capture manually in the weekly log.

---

## 4. Escalation & support

Follow [`SUPPORT_SLA.md`](SUPPORT_SLA.md). Blocking bug during the pilot → hot-fix on `feat/scope-revision-2026-09-09b` (or a follow-on), note it in the plan's progress log. Data-loss risk (offline outbox, allocation corruption) is P0 — pause that firm's usage until fixed.

---

## 5. Exit criteria

- 4 weeks of real daily use by ≥4 firms.
- H-01, H-03, H-05 each scored PASS / FAIL / INCONCLUSIVE per firm.
- A written go / no-go on ARCH-03, with the top 5 friction items ranked.

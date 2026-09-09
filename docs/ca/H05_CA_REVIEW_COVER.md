# H-05 — CA Review Cover Sheet

**What this is:** a one-month set of Bizboard worksheets for an independent practising
CA to assess whether they could file a client's monthly GST returns directly from them.
This validates **Hypothesis H-05** in
[`../BUSINESS_ARCHETYPES_AND_PERSONAS.md`](../BUSINESS_ARCHETYPES_AND_PERSONAS.md) §11.
Plan item **SR-50** in
[`../roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md`](../roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md).

## The packet

Generate with `python manage.py seed_h05_demo` (dev/non-prod only). Output lands in
`build/h05_packet/`:

| File | Contents |
|---|---|
| `gstr1_2026-08.json` | GSTR-1 outward-supply worksheet — B2B invoices incl. 2 inter-state (IGST) and 1 with 206C TCS |
| `gstr3b_2026-08.json` | GSTR-3B liability / ITC worksheet built from the same period data |
| `trial_balance_2026-08.json` | Trial balance as of 31 Aug 2026 |
| `profit_and_loss_2026-08.json` | P&L for 01–31 Aug 2026 |
| `balance_sheet_2026-08.json` | Balance sheet as of 31 Aug 2026 |
| `SUMMARY.md` | Human-readable summary + the exact questions below |

The demo company is a building-supplies wholesaler (ARCH-03): 4 products at the slabs
in force on the document date (**5%** natural sand, **18%** cement / fasteners / MCBs;
several invoices carry both), 3 customers (2 Karnataka intra-state, 1 Maharashtra
inter-state), 1 supplier, opening stock, 3 purchase bills, 7 B2B sales invoices,
4 receipts (3 fully allocated, 1 partial), period soft-closed.

## The ask

> **Could you file this client's monthly GSTR-1 and GSTR-3B directly from these
> worksheets — without re-deriving the tax splits or rebuilding the ledgers in
> your own software?**

Please answer each, in writing:

1. **GSTR-1 tax splits.** Do CGST/SGST (intra) vs IGST (inter) allocations match your
   expectation for the listed invoices? Any invoice mis-classified?
2. **GSTR-1 ↔ GSTR-3B tie-out.** Does 3B outward liability reconcile to GSTR-1? Is the
   ITC from the 3 purchase bills reflected correctly in 3B Table 4?
3. **Trial balance.** Does it foot? (`SUMMARY.md` states Dr/Cr and balanced=true/false.)
   Any control account you would not accept as-is?
4. **P&L / balance sheet.** Internally consistent with the TB? Anything you would
   re-classify?
5. **206C TCS invoice (24 Aug).** Is the TCS presented so you can reconcile it to the
   client's 206C collection?
6. **Overall.** PASS (file directly) / FAIL (must recalculate — say what) / INCONCLUSIVE.

## Pass / fail (H-05)

- **Pass:** CA files the client's monthly returns directly from these worksheets, no recalculation.
- **Fail:** CA rejects due to mismatched tax splits, place-of-supply errors, or an imbalanced journal.
- **Inconclusive:** neither — extend with a second month / second reviewer.

## Scope notes (state to the CA)

Offline worksheets only — **not** live GSP portal filing, **not** live IRN/e-way. Out of
pilot scope: composition/CMP-08, RCM, fixed assets, TDS/TCS *returns* and certificates,
import/BoE landed cost. This v1 packet omits opening party balances and credit/debit
notes (CDNR) — added in SR-50 v2.

## Record

| Field | Value |
|---|---|
| CA name / firm | |
| Membership no. | |
| Packet commit SHA | |
| Date reviewed | |
| Verdict (Q6) | PASS / FAIL / INCONCLUSIVE |
| Blocking issues | |
| Signature | |

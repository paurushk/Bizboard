# Accounting Review

## Wave 22 (2026-08-06)

Sales RCM Output GST (695); RCM purchase discount (702); payroll employer (703); opening stock atomicity (705); WO dating (706); TCS under ENABLE_TDS (711); FY vs GST lock (712); BooksHealth coverage (713); unallocate reverse dating (701).

## Code-max (2026-08-05)

**Score: 9.7 / 10.** FY close IS→RE is implemented (BB-000664) — zeros income/expense to 3100; 3200 opening equity stays on BS. True 10/10 still needs signed CA Final Gate / books sign-off.

Closed this pass: dual-ledger bulk AR/AP GL-first; SOFT_CLOSED operational gates; opening stock Dr1400/Cr3200; WO WAVG stamp; H9 FIFO layer restamp; refund reverse_allocation; FY close; PF/ESI/PT + TDS/TCS GL (2261–2266 / 1365).

Dual-ledger remains an opt-in projection (`accounting_enabled`).

## Wave 21 (2026-08-05)

BB-000650/651 DELETE orphans GL; BB-000654 period bypass; BB-000655 alloc date; BB-000664 FY close plug; BB-000682 pay run delete.

## Wave 20 (2026-08-05)

BB-000648 paid invoices cannot be credited; BB-000645 UTR 90-day window.

## Wave 19 missed (2026-08-05)

BB-000599 cgst_amount; BB-000600 cess GL; BB-000609 reverse FKs; BB-000606 AA mocks.

## Wave 19 (2026-08-05)

Manufacturing silent GL (BB-000564); FG list-price receipts (BB-000555); payroll net-to-2100/1100 (BB-000567); AA amount-only match (BB-000570). Dual-ledger ADR-A02 violated by new modules.


**Date:** 2026-08-02 · **Score: 4.5 / 10**

## Design

- **Party ledgers:** derived from documents + allocations (correct for billing MVP).
- **GL:** optional `accounting_enabled` → `PostingService` journals with idempotent purposes.
- **BooksHealth:** compares control vs derived; incomplete coverage of returns/notes.

## Critical / High

| ID | Finding |
|----|---------|
| BB-000010 | RCM posts tax=0 |
| BB-000008 / G26 | Sales returns no GL |
| BB-000011 / G27 | H9 no reverse/repost |
| BB-000016 | Dual ledger divergence |
| G23 | Lumped Output/Input GST (no CGST/SGST/IGST) |
| G29 | Purchases expense vs inventory asset |
| G32 | Double relief return+CN |

## Correct behaviors

- Balanced journal check on post.
- CLOSED period blocks new posts.
- Cancel can reverse journals (invoice path).
- CN outstanding caps exist.

## Verdict

Not Tally-class books. Acceptable as **opt-in projection** only if posting matrix completed and feature-flagged. Default-off is honest; UI presence without flags is not.

## Score: 4.5 / 10


## Wave 8 (2026-08-03)

Critical: purchase H9 missing period/GL (BB-000199); journals HasCompany-only (BB-000200). Medium: `accounting_enabled` via Company PATCH (BB-000216). Prior dual-ledger / purchases→5100 / FIFO gaps remain Deferred/Open as applicable.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

### Wave 13 accounting residuals (verified)

| ID | Finding |
|----|---------|
| BB-000380 | Sales return restores stock+CN; **never reverses COGS/Inventory** |
| BB-000381 | Tally/opening invoices skip GL but remain in AR/AP outstanding + BooksHealth |
| BB-000382 | Unallocated receipts credit AR control GL but not party outstanding |
| BB-000395 | H9 amend re-posts stale COGS after qty change |
| BB-000399 | Purchase charges capitalized into Inventory 1400 |
| BB-000401 | FIFO setting does not drive outbound COGS |
| BB-000426 | Balance sheet folds all-time P&L without year close |
| BB-000427 | RCM purchase notes inventory leg uses grand_total |

**Verdict:** Do not enable `accounting_enabled` for pilot until BB-000380–382 close.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.

---

## Wave 14 missed-findings (2026-08-04)

Appended `BB-000544`…`BB-000549` (6). Open **94**. See MASTER_ISSUE_REGISTER.md.

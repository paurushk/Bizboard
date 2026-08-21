# BizBoard — Tally migration recipe (Phase 7.0)

**Disclaimer:** Guided import/export aid only. Not live Tally sync. Validate with your CA.

## Import (masters CSV or Excel)

1. Export ledgers/stock from Tally to Excel/CSV (UTF-8).
2. Reshape to BizBoard columns:

| column | required | notes |
|--------|----------|-------|
| entity_type | yes | `customer`, `supplier`, or `product` |
| name | yes | editable in Map step |
| phone, gstin, state | no | parties |
| sku, hsn_code, gst_rate | products | sku unique per company; editable in Map |
| purchase_price, selling_price, reorder_level, opening_qty | products | |
| opening_outstanding | parties | creates completed NON_GST `TALLY_OPENING` invoices on commit |

3. Settings → Tally Migration → Upload (.csv / .xlsx) → **Map** (edit names/SKUs) → Commit (auto-saves mapping first).
4. Use **Ignore error rows** when parse errors remain but valid entities should still import; or download the error report CSV.
5. Golden fixture: `backend/tests/fixtures/tally_masters_golden.csv`

### Opening AR/AP

On commit, each customer/supplier with `opening_outstanding > 0` gets a completed NON_GST invoice (`notes=TALLY_OPENING`) so ledgers show the balance. Re-commit skips parties that already have a `TALLY_OPENING` invoice.

**Side effects / exclusions**
- Opening invoices are excluded from dashboard sales/purchases KPIs and daily-summary sales totals.
- Opening invoices skip PDF queue and GST period dirty flags; credit limits are not enforced on opening AR.
- Export aid excludes `TALLY_OPENING` sales so they are not re-imported into Tally.
- Skipped opening stock (already recorded) appears in commit `warnings`.

## Export aid

Settings → Tally Migration → Download sales voucher CSV aid. Import into Tally/CA tools as a **starting point**, not a certified voucher file.

## Support

- Mapping errors appear in preview `errors` and the error-report download.
- Opening stock will skip if the product already has an opening movement.

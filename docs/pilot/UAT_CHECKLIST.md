# Pilot UAT checklist

1. Register company (or use demo) — Owner has all capability flags.
2. Import products / create product with HSN + GST.
3. Create supplier with state → purchase → Complete → stock increases.
4. Create customer with state → sales invoice odd-paise price → UI totals match saved invoice.
5. Partial receipt + allocation → ledger outstanding drops.
6. Sales return → stock restored; outstanding adjusts.
7. Cancel draft OK; staff without `can_cancel_documents` gets 403 on cancel.
8. Blank party state blocks GST Complete (unless assume-local enabled).
9. BEFORE_TAX vs AFTER_TAX discount labels visible on PDF/UI.
10. Dashboard loads; receivables aging present; export requires `can_export`.

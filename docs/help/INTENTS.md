# P0 Help intents

**Status:** Locked for M0. Full Answer / Action / Resolution copy is HR-0.5 (not this file).
**Canonical IDs:** do not rename without a redirect in the resolver.
**Types:** see `HELP_AND_RESOLUTION_PLAN.md` §2c.

| intentId | Type | Job | Migrates from v0 FAQ |
|---|---|---|---|
| `add-gstin` | 1 how-to | Add/change your GSTIN so tax invoices are legal | — (new) |
| `sell-blocked` | 6 diagnostic | Why an item won't add to a bill (no stock / inactive / blocked customer) | `reserved-vs-on-hand` (partial) |
| `cannot-complete-invoice` | 6 diagnostic | Why **Complete** is greyed out or fails | — (new) |
| `wrong-gst-on-invoice` | 6 diagnostic | Wrong CGST+SGST vs IGST, or wrong rate | — (new) |
| `stock-in-another-godown` | 4 fix-it | On-hand looks wrong — stock is in another godown | `stock-shows-but-insufficient` |
| `unit-conversion-rate` | 1 how-to | Set carton↔piece conversion | `unit-conversion-rate`, `base-vs-alternate-unit`, `unit-field-blank-on-edit` |
| `registration-type` | 5 decision | Regular vs Composition vs Unregistered — what changes | — (new; not in v0 despite earlier notes) |
| `payment-wont-allocate` | 6 diagnostic | A receipt won't attach to a bill / shows unapplied | — (new) |
| `edit-completed-invoice` | 8 policy | You can't edit a done bill — use a credit/debit note | — (new) |
| `import-row-errors` | 4 fix-it | Your Excel/Tally import shows red rows | — (new) |
| `pdf-or-share-unavailable` | 2 why-blocked | Invoice PDF / WhatsApp / share missing or failing | — (new) |
| `login-cant-do-this` | 8 policy | "Your login can't do this" — role/permission, ask the Owner | — (new) |
| `purchase-bill-blocked` | 2 why-blocked | Purchase bill will not complete | — (gap close) |
| `books-journal-blocked` | 1 how-to | Journals / books not open | — (gap close) |
| `trial-ended-readonly` | 2 why-blocked | Trial ended / subscription paused — workspace read-only | — (gap close) |
| `offline-outbox-stuck` | 4 fix-it | Offline drafts not syncing | — (gap close) |

## v0 FAQ fold-in (actual files, not the earlier guess)

The five current entries in `web/src/pages/help/faqContent.tsx`:

| v0 `id` | Folds into |
|---|---|
| `unit-conversion-rate` | `unit-conversion-rate` |
| `base-vs-alternate-unit` | `unit-conversion-rate` (concept) |
| `unit-field-blank-on-edit` | `unit-conversion-rate` (same field) |
| `stock-shows-but-insufficient` | `stock-in-another-godown` |
| `reserved-vs-on-hand` | `sell-blocked` + `stock-in-another-godown` |

`registration-type` is a **new** P0. It was never a v0 FAQ.

## Error-code map (M1)

See `CODES.md`. One intent may list several codes; one code maps to one intent.

| intentId | `errorCodes[]` (M1) |
|---|---|
| `add-gstin` | `company_gstin_required` |
| `sell-blocked` | `inactive_product`, `blocked_customer` |
| `cannot-complete-invoice` | `registration_gate`, `place_of_supply_unresolved`, `credit_limit_exceeded`, `sales_rcm_unconfirmed`, `closed_period` |
| `wrong-gst-on-invoice` | `invalid_gst_rate` |
| `stock-in-another-godown` | `insufficient_stock` |
| `unit-conversion-rate` | — (field hint, not an error) |
| `registration-type` | `registration_gate` (also on `cannot-complete-invoice`; error deep-link prefers Complete context) |
| `payment-wont-allocate` | `allocation_exceeds_unallocated`, `allocation_party_mismatch` |
| `edit-completed-invoice` | `completed_immutable` |
| `import-row-errors` | `import_invalid_rows` |
| `pdf-or-share-unavailable` | `pdf_or_share_unavailable` |
| `login-cant-do-this` | `permission_denied` (HTTP 403, not a `BusinessRuleError` site) |

## `nextStep` sketch (destinations; permission via existing caps)

| intentId | Destination | Permission | Staff fallback |
|---|---|---|---|
| `add-gstin` | `/settings/gst` | `owner` | Ask the Owner to add the GSTIN in **Settings → GST**. |
| `sell-blocked` | `/inventory/stock` | `can_manage_inventory` | Ask the Owner to check stock or unblock the customer. |
| `cannot-complete-invoice` | current invoice (`?invoiceId=`) | `can_create_sales` | — |
| `wrong-gst-on-invoice` | current invoice | `can_create_sales` | — |
| `stock-in-another-godown` | `/inventory/stock` | `can_manage_inventory` | Ask the Owner to transfer stock or change the **Godown** on the bill. |
| `unit-conversion-rate` | item form / units settings | `can_manage_inventory` | Ask the Owner to set the conversion rate on the item. |
| `registration-type` | `/settings/gst` | `owner` | Ask the Owner. This is set once at sign-up / GST settings. |
| `payment-wont-allocate` | `/payments` (receipt) | `can_create_sales` | — |
| `edit-completed-invoice` | credit-note create `?invoiceId=` | `can_create_sales` | Ask the Owner. A done bill is changed with a credit note, not by editing. |
| `import-row-errors` | `/settings/import` | `can_import` | Ask the Owner. Import is an Owner/import-cap job. |
| `pdf-or-share-unavailable` | invoice detail `?invoiceId=` | `can_create_sales` | — |
| `login-cant-do-this` | `/settings/users` | `owner` | Ask the Owner. Your login does not include this action. |
| `purchase-bill-blocked` | `/purchases/history` | `can_create_purchases` | Ask someone who can enter purchases to open **Purchases**. |
| `books-journal-blocked` | `/accounting/journals` | `can_post_journals` | Ask the Owner to turn on books and post the journal. |
| `trial-ended-readonly` | `/settings/billing` | `owner` | Ask the Owner to renew in **Settings → Billing**. |
| `offline-outbox-stuck` | `/offline-outbox` | `can_create_sales` | Ask someone who bills on this device to open the offline outbox. |

## HelpHint mount points (7 fields, M1)

`HelpHint` only — never a `PreventionNote` on the same field.

| Slot | Field | intentId |
|---|---|---|
| `registration-type-settings` | GST registration type (settings) | `registration-type` |
| `gstin` | Company / party GSTIN | `add-gstin` |
| `place-of-supply` | Place of supply / party state | `cannot-complete-invoice` |
| `uom` | **Unit of Measure** | `unit-conversion-rate` |
| `conversion-rate` | Conversion rate | `unit-conversion-rate` |
| `tracking-mode` | Batch / serial tracking | — (no P0 intent; hint removed so it does not open `sell-blocked`) |
| `tax-inclusive` | Tax-inclusive price | `wrong-gst-on-invoice` |

## Empty-state links (M1)

| Empty state | intentId |
|---|---|
| Godowns / warehouses | `stock-in-another-godown` |
| First invoice | `cannot-complete-invoice` (or a how-to once authored) |
| Import | `import-row-errors` |
| Customers | `add-gstin` |

## Out of M1 (diagnosis trees — Phase 3)

These six stay as `type: 6` parents; leaves are authored in HR-3.2:

`wrong-gst-on-invoice`, `sell-blocked`, `cannot-complete-invoice`, `import-row-errors`, `payment-wont-allocate`, `pdf-or-share-unavailable`.

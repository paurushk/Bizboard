# Quotations — decisions

**Date:** 2026-10-10
**Source plans:** [QUOTATIONS_CLOSURE_PLAN.md](../plans/QUOTATIONS_CLOSURE_PLAN.md), [QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md](../plans/QUOTATIONS_REVIEW_AND_IMPLEMENTATION_PLAN.md)

Every decision below is **adopted and built**. The "Confirmed by" column is for the
founder: only a person can fill it. The four decisions that change money behaviour (D-1,
D-2, D-3, D-17) were **confirmed by the founder in chat on 2026-10-10**. D-9 to D-11 still
need confirmation before the lifecycle and sharing release is switched on for customers.

| ID | Decision | Built in | Confirmed by (name, date) |
|---|---|---|---|
| D-1 | On a partial conversion, additional charges and invoice discount are shared out by converted taxable value, with cumulative rounding so the documents add up to the quotation to the paisa. | `sales/quotation_conversions.py::header_shares` | Founder, in chat, 2026-10-10 |
| D-2 | Releasing converted quantity (when an order or invoice is deleted or cancelled) is **on by default**; a company can set `QUOTE_CONVERSION_RELEASE` to `false` as a kill switch. | `core/services/feature_flags.py` | Founder, in chat, 2026-10-10 |
| D-3 | A sweep (management command, nightly task) releases rows whose order or invoice is gone or cancelled. Backfilled `UNKNOWN` rows are never swept; an owner reopens those. | `QuotationConversionService.sweep`, `sales.tasks.sweep_quotation_conversions` | Founder, in chat, 2026-10-10 |
| D-4 | A restore rebuilds the conversion ledger from the backup; an old backup without it is backfilled and then checked. A quote that disagrees with its ledger stops the restore. | `accounts/tenant_backup.py` | |
| D-5 | Expired quotes still block a product unit change (they can be converted with confirmation). The message names the quotes, and **Cancel expired quotes** cancels the ones with nothing converted. | `inventory/item_stock.py`, `QuotationViewSet.cancel_expired` | |
| D-6 | Expiry stays **computed** from the validity date (`is_expired`). The backend never had an `EXPIRED` status; it is removed from the web type too. | `QuotationSerializer.get_is_expired` | |
| D-7 | Invoices get no salesperson, channel or address columns. The invoice detail shows them through the source quotation. | `SourceQuotationsMixin` | |
| D-8 | A quotation number is allocated at create. Deleting a draft (API only) leaves a gap; the delete is audited with the number and the series screen says so. | `QuotationViewSet.perform_destroy`, `SeriesSettingsPage` | |
| D-9 | `QUOTE_LIFECYCLE` stays opt-in per company for one pilot, then becomes default after two weeks without defects. | flag unchanged (opt-in) | |
| D-10 | Sharing is a public PDF link plus the WhatsApp share sheet. Sharing a draft moves it to Sent when the lifecycle flag is on. | `sales/quotation_links.py`, `ShareQuotationDialog` | |
| D-11 | "New version" is **Duplicate** into a new draft linked by `copied_from`; the source is not changed. | `QuotationViewSet.duplicate` | |
| D-12 | Quotes are visible to everyone who can view sales, like invoices. The revisions endpoint needs the create-sales permission. | `QuotationViewSet.get_permissions` | |
| D-13 | Campaign revenue counts the whole order or invoice even if lines were added after conversion (documented limit). | `crm/campaigns.py::_won_revenue` | |
| D-14 | The chain-convert endpoint returns 410 after 2026-11-28. Until then it answers with `Deprecation` and `Sunset` headers and is logged. | `QuotationViewSet.convert_chain` (410 not yet switched on) | |
| D-15 | These decisions are recorded here. | this file | |
| D-16 | **Close remaining**: a partly converted quotation can be closed with a reason; it stays Converted, its unconverted quantity stops counting, and an owner can reopen it. | `QuotationConversionService.close_remaining` / `reopen_closed` | |
| D-17 | A line with no taxable value carries no share of charges or discount, unless every line is valueless (then quantities are used). | `header_shares` | Founder, in chat, 2026-10-10 |
| D-18 | When a document comes from several quotations, the earliest is primary and a flag says whether salesperson, channel or address differ. | `SourceQuotationsMixin` | |
| D-19 | Public link rules: expired → 410; revoked, unknown, cancelled or rejected → 404; a converted quote stays readable until its validity date; moving a quote back to draft revokes the link. | `sales/public_quotation_views.py` | |
| D-20 | The stock hint is measured in the company default godown, the one conversion uses. | `StockHintView` | |
| D-21 | R1 coding starts without sign-off; D-1, D-2, D-3 and D-17 are confirmed before R1 is deployed. | process | Satisfied: D-1, D-2, D-3 and D-17 confirmed 2026-10-10 |

## Earlier decisions (D1–D8 of the review plan)

| ID | Decision | Status |
|---|---|---|
| D1 | A deleted draft order or invoice made from a quote, and a cancelled order or invoice made directly from it, give converted quantity back. An invoice made from an order never releases the quote; only the order's own cancellation or deletion does. | Built (WP4) |
| D2 | A released quote that has expired returns to Draft with the Expired indicator; converting it again needs the expiry confirmation. | Built |
| D3 | Sales staff do not see internal cost (`expected_price`). Only people who can view financial reports do. | Built (quote, order, challan lines; revisions) |
| D4 | Lifecycle states are Sent, Accepted, Rejected; expiry is computed. | Built |
| D5 | Chain-convert is deprecated. | Built (headers); 410 after the sunset date |
| D6 | A blocked customer cannot be quoted or converted. | Built |
| D7 | Credit-limit and GST-rate checks run when the order or invoice is made, not on the quote. | Unchanged |
| D8 | Editing a Sent quote moves it back to Draft and keeps a snapshot of what was sent. | Built |

## Facts checked while deciding

- Quotes never enter customer ledger totals or the Day Book; they only appear as rows in the customer transaction list.
- There is no customer-merge feature, so nothing to reconcile. When one is added it must move quotations, their conversions and revisions.
- The mobile app does not use quotations.
- Sales visibility is not scoped by salesperson anywhere in the product, so quotes are not either.
- GST is worked out per invoice, so split documents can differ from the quotation by up to a paisa each. This is how a tax invoice works and is explained in the help.

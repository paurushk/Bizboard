# Quick Order Entry — rollout, rollback and release notes

Plan: [QUICK_ORDER_ENTRY_IMPLEMENTATION_PLAN.md](QUICK_ORDER_ENTRY_IMPLEMENTATION_PLAN.md) · Review: [QUICK_ORDER_ENTRY_REVIEW_2026-10-12.md](QUICK_ORDER_ENTRY_REVIEW_2026-10-12.md)

## What ships without a flag (fixes)
- Quick Entry no longer sends a price or GST rate. The server uses the customer's price list and the product master.
- Sales orders and delivery challans refuse blocked/inactive customers (create, confirm, complete), respect the
  subscription write gate, and accept an `Idempotency-Key` on create (orders also on confirm).
- Order list filters `q`, `customer`, `date_from`, `date_to` now work.
- Orders default their delivery address (`ship_to` → default shipping address → shipping address → billing address)
  and payment terms (customer credit days) when not supplied.
- Orders have a `price_mode` (EXCLUSIVE by default).
- `preview-totals` prices a line from the customer's price list when no `unit_price` is sent.

## What is flagged (per company, default off)
Turn on with `python manage.py grant_company_flag --email <owner> --flag QUICK_ENTRY_ORDER_MODE --on` (use `--off` to roll back; add `--company-id` for a multi-company user, `--force` on production/staging). The flag is stored in the company's `feature_flags` JSON.

| Flag | Effect |
|---|---|
| `QUICK_ENTRY_ORDER_MODE` | Quick Entry can save a **sales order** (otherwise it saves a draft bill). |
| `QUICK_ENTRY_AUTO_CONFIRM` | After saving an order, confirm it. A rule refusal leaves it a draft ("needs approval"). |
| `QUICK_ENTRY_PRICE_PREVIEW` | Lines and totals come from the server preview. Without it the screen shows list prices (when the customer has a price list) and an estimated GST. |

## Before enabling for a company
1. Run `python manage.py list_orders_for_quick_entry_rollout --company <id>`. Open orders for blocked/inactive customers
   will fail at confirm; open orders with no delivery address give blank delivery-route stops. Decide per order.
2. Pilot one or two companies for a week. Check:
   - a sample of 20 Quick Entry documents against the customers' price lists (audit `source = quick_entry`),
   - no duplicate documents (a retry reuses the same idempotency key),
   - the share of orders that stay draft after auto-confirm, and why.
3. Run `python manage.py quick_entry_metrics --company <id> --days 14` for volume, order-vs-bill share, orders still
   draft and per-rep counts, read from audit events (`source = quick_entry`). The insights event list is a database enum,
   so no new telemetry events were added.

## Rollback
- Turn the three flags off for the company. Quick Entry goes back to saving draft bills; nothing else changes.
- The fixes above are not flagged. To undo one, revert its commit; they are independent:
  `core/idempotency.py` (mixin + scopes), `sales/phase1_views.py`, `sales/phase1_serializers.py`,
  `sales/notes_services.py`, `core/services/tax_engine/india.py`, `sales/migrations/0071_salesorder_price_mode.py`.
- Reverting the migration is safe: `price_mode` is a new column with a default.

## Release notes (for support)
- **Where do Quick Entry orders appear?** Under Sales → Sales Orders (when order mode is on) or Sales History (draft bills).
- **"Cannot create an order for a blocked customer."** The customer is blocked or inactive. Unblock them or pick another.
- **"Saved as a draft. Needs approval."** A credit or margin check stopped confirmation. A manager confirms it from Sales Orders.
- **"Saved, but confirming it did not complete."** The connection dropped after saving. The order is a draft; open it and confirm.
- Existing drafts for customers who are blocked now cannot be confirmed; the ops report lists them.
- Hindi strings were written without a native review; ask a Hindi-speaking user to check them before a wide rollout.

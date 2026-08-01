# H9 — Paid / completed invoice correction path (signed decision)

**Decision:** **H9-A** (Owner narrow amend)  
**Date:** 2026-08-01  
**Status:** Implemented in API + Sales UI confirm; binding for Phase 0 pilot

## Rule

| Allowed | Forbidden |
|---------|-----------|
| Owner amends `unit_price`, `discount_percent`, `invoice_discount`, `additional_charges` on COMPLETED with UI confirm → `confirm_amend: true` + `AuditEvent` | Staff amend of completed invoices |
| | Changing quantity, product, or GST rate on completed lines |
| | Using **Sales Return** to “fix a price typo” (distorts stock) |
| | Cancel when payment allocations exist (A10) without reversing money properly |

## Support script

> “Completed invoices are locked for staff. An Owner can amend prices/discounts/charges with an audited confirmation. For wrong quantity/product, use a return (stock) or wait for Credit Notes in Phase 1. Do not return stock to fix a price.”

## Onboarding

Pilot onboarding must state H9-A explicitly (see `ONBOARDING.md`).

## Sign-off

| Role | Name | Date |
|------|------|------|
| PM | | |
| Eng | | |
| CA (aware) | | |

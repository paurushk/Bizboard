# Cutover templates (6.1 / 6.2 / 6.7)

Pilot cutover is **one company at a time**. Excel IDs, not CSV, for any
spreadsheet the customer already uses. Imports in-product accept the supported
Excel templates under Settings → Import.

## 6.1 Opening inventory

| Column | Required | Notes |
|---|---|---|
| SKU | yes | Unique per company |
| Name | yes | |
| Unit | yes | Must exist in masters |
| GST % | yes | Rate the product sells/buys at; not a filing opinion |
| Opening qty | yes | Godown default if blank |
| Unit cost | yes | Running weighted cost (freeze C3 — not perpetual FIFO layers) |
| HSN | no | |

Re-import of the same row is idempotent (A15). Do not complete a purchase to
fake opening stock.

## 6.1b Customers / suppliers

| Column | Required | Notes |
|---|---|---|
| Name | yes | |
| GSTIN | no | Party GSTIN, never the company GSTIN |
| State | yes if GSTIN | Place of supply |
| Phone | no | |
| Credit days | no | Customers |
| Credit limit | no | Customers |
| Opening AR / AP | no | Not this sheet — first invoice + receipt / bill + payment |

## 6.2 Party / item field map

| Their field | BizBoard | Do not map to |
|---|---|---|
| Customer name | Customer.name | Supplier |
| GSTIN | Customer.gstin | Company GSTIN |
| State | Customer.state | Place of supply override without Owner |
| Item code | Product.sku | Barcode-only without SKU |
| Tax % | Product.gst_rate | “HSN suggested rate” as law |
| Opening AR | Not an import — first invoice + receipt | Manual GL journal unless books opt-in |

## 6.7 Rollback

1. Stop writers (`api` `worker` `beat`).
2. Restore the dump taken **immediately before** cutover (`docs/pilot/RUNBOOKS.md`).
3. Bring up the **same** image tag that took the dump.
4. Spot-check: one invoice complete → PDF → ledger; one stock qty.
5. Do not reverse expand-only migrations to “undo” a bad import — restore.

Human signs the cutover window on `GO_NO_GO.md`. This template is not a contract.

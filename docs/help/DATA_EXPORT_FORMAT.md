# Readable data export — format

Settings → Backup → **Download my data (Excel / CSV)** gives the owner a ZIP they can open
without Bizboard. It is separate from the encrypted backup, which is only for restoring into
Bizboard. Built by `accounts/readable_export.py` (WP-DL1).

## What is in the ZIP

| File | What it holds |
|---|---|
| `manifest.json` | `format` (`bizboard-readable-export`), `format_version`, company id/name/GSTIN, `generated_at`, and for every file its `rows`, `bytes` and `sha256` |
| `<section>.csv` | One CSV per section (customers, suppliers, products, sales_invoices, sales_items, purchase_invoices, receipts, journals, …). UTF-8 with a byte-order mark so Excel shows Hindi. First row is the column names. |
| `pdf/<invoice number>.pdf` | The GST tax invoice of each completed sales invoice, up to 500; `manifest.json` → `invoice_pdfs` says how many there were in all |
| `README.txt` | What is in the ZIP, in English and Hindi |

`file_assets.csv` lists your uploaded files (name, type, size), not their contents; download a
file from its record in the app.

Columns are the record's own field names (`id`, `created_at`, `name`, `gstin`, `grand_total`, …);
links to other records end in `_id` and hold that record's `id` from its own CSV. Amounts are in
rupees with two decimals; dates are `YYYY-MM-DD`; times are ISO 8601 with time zone.

## Checking a download

Each file's SHA-256 in `manifest.json` must match the file. On Windows:
`certutil -hashfile customers.csv SHA256`; on Mac or Linux: `shasum -a 256 customers.csv`.

## Versions

`format_version` is `MAJOR.MINOR` (now **1.0**).

- **Minor** (1.0 → 1.1): a column or section is added. Existing columns keep their names and
  meaning, so a sheet or import built on an older export keeps working.
- **Major** (1.x → 2.0): a column is renamed or removed, or its meaning changes. Announced in
  the app's "What's new" at least 30 days before.

`tests/test_readable_export_dl1.py` pins the columns of the main sections
(`tests/snapshots/readable_export_columns.json`); changing them fails CI until the version is
bumped and the snapshot re-recorded.

## Access

Owner only, after their password (and two-step code if on). The ZIP is prepared in the
background; the download link works for 24 hours, then the file is deleted. Each export is
recorded on the privacy request register (`docs/ops/DPDP_REQUESTS.md`).

# Data categories (16.2)

Inventory for counsel. **Not** a privacy policy, DPA, or DPIA. Categories
match `docs/pilot/DPDP_POSTURE.md`.

| Category | Examples | Typical tables |
|---|---|---|
| Identity | owner email/phone, staff accounts | `accounts.User`, `accounts.CompanyUser` |
| Party PII | customer/supplier name, phone, GSTIN, address | `masters.Customer`, `masters.Supplier` |
| Money documents | invoices, challans, receipts, GSTR worksheets | `sales`, `purchases`, `payments`, `reporting` |
| Files | invoice PDFs, import Excel, bill photos | `core.FileAsset` |
| Comms | WhatsApp send status, AR dunning flags | `sales`, `payments` |
| Telemetry | shop-floor events without GSTIN/phone | `insights.ShopFloorEvent` |
| SaaS billing | Razorpay subscription ids, seat counts | `billing.Subscription` — not customer AR |

Request logs hash user/company ids and redact document numbers / GSTIN (`test_request_log_masks_ids_and_carries_no_body`). Card PAN/CVV are never stored (`docs/ops/PCI_SCOPE.md`).

Lawyer drafts the published privacy notice. This file is a product-fact sheet.

# Bizboard — MVP Implementation Plan

**Product:** One-Stop GST Billing & Business Management Platform  
**Version:** 1.1 (Locked MVP — architecture review incorporated)  
**Status:** MVP implemented (backend + web); pilot/CA sign-off pending  
**Last updated:** 2026-07-19  
**Review status:** P0 architecture refinements applied (target commercial quality: myBillBook / Vyapar class)

---

## 1. Locked decisions

### 1.1 Product scope

| Decision | Lock |
|---|---|
| MVP scope | **4 core flows only** — Purchase, Sales & Invoice, Inventory, Dashboard & Basic Reports |
| Accounting in MVP | **Derived ledgers only** via Ledger Service — no physical ledger tables, journals, P&L, Balance Sheet, or GST returns |
| Primary customers | Retail shops, small traders, small wholesalers (**no manufacturers**) |
| Billing modes | GST Invoice, Tax Invoice, Retail Invoice, Non-GST Invoice |
| Documents in MVP | Quotation ✅ · Sales Return ✅ · Purchase Return ✅ · Credit/Debit Note ❌ (Phase 2) |
| POS / barcode | **Yes** — barcode + SKU + name search + fast billing (full POS mode later) |
| Payments | **Record-only** with **allocation** — Cash, UPI, Bank, Card, Credit (no gateway) |
| Sharing | PDF download, Print, WhatsApp, Email (SMS later) |
| Tenancy | Single company + single warehouse per tenant |
| Languages | English first; i18n-ready for Hindi later |
| Go-to-market | **Paid pilot** — 20–50 businesses (no free plan until stable) |

### 1.2 Users & access

| Decision | Lock |
|---|---|
| Roles | Owner/Admin, Sales Staff; inventory permissions configurable |
| Multi-user | Yes |
| Audit | **Activity audit** — Create, Update, Delete, Login, Logout, Import (plus row-level created/updated by + timestamps) |

### 1.3 Platforms

| Order | Platform | MVP? |
|---|---|---|
| 1 | Web | ✅ Launch |
| 2 | Android | Phase 2 |
| 3 | Windows Desktop | Phase 2 |
| 4 | iOS | Later |
| Offline billing | ❌ Online-first MVP |
| Printing | A4 + PDF in MVP; thermal 58/80mm in Phase 2 |

### 1.4 Technology

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Vite + **Material UI (MUI)** + Redux Toolkit / React Query + React Hook Form |
| Backend | Python + Django + Django REST Framework |
| Architecture style | **Service layer + domain business events** (no message broker in MVP) |
| DB / cache / jobs | PostgreSQL + Redis + Celery |
| Auth | Email + password; Mobile + OTP (Google later) |
| Multi-tenancy | Shared DB, **`company_id` on all business tables** |
| GST validation | Format + GST rate + HSN validation (live GSTN later) |
| API | Versioned: **`/api/v1/...`** |
| Dev hosting | Docker Compose |
| Prod hosting | AWS Lightsail / EC2 + PostgreSQL + Redis + Nginx (no Kubernetes) |

### 1.5 Compliance & data

- Engage a **CA** to validate invoice formats, GST calculations, tax rules.
- Day-1 import: Excel/CSV with **Upload → Validate → Preview → Commit → Error report**.
- Invoice template: GST-compliant A4, logo, UPI QR, GSTIN, HSN/SAC, CGST/SGST/IGST breakup, T&C, signature.
- e-Invoice / e-Way Bill = Phase 2.

### 1.6 Success criteria (pilot)

| Metric | Target |
|---|---|
| Pilot businesses | 20–50 |
| Invoice volume | 500+ invoices/day across pilots |
| Invoice generation time | < 10 seconds (save response; PDF may complete async) |
| Successful invoice generation | ≥ 99% |
| Daily active usage (pilots) | > 90% |
| Customer satisfaction | > 4.5 / 5 |

### 1.7 Ideal team

| Role | Count |
|---|---|
| Product Manager | 1 |
| Frontend Developers | 2 |
| Backend Developers | 2 |
| QA Engineer | 1 |
| UI/UX Designer | 1 (part-time) |
| DevOps | 1 (part-time) |

---

## 2. In scope vs out of scope

### 2.1 In scope (MVP)

- Company setup  
- User management (Owner + Sales Staff)  
- Customers (Active / Blocked), Suppliers, Products (Active / Inactive)  
- Purchase management (+ returns) with document statuses  
- Sales & GST/non-GST billing (+ quotations, sales returns) with document statuses  
- Inventory (single warehouse, movement-typed stock ledger; reservation fields reserved for future)  
- Payments: customer receipts, supplier payments, **payment allocation**  
- Dashboard + basic reports via **Reporting Service**  
- Async PDF & A4 printing  
- WhatsApp & Email via **Notification Service** abstraction  
- Excel/CSV import (preview pipeline) & export  
- Universal search (invoice, customer, product/barcode/SKU/name, supplier)  
- Document Number Generator service  
- File Service (logos, PDFs, attachments, imports)  
- Activity audit log  

### 2.2 Out of scope (Phase 2+)

- General ledger, journals, P&L, Balance Sheet  
- GSTR-1 / GSTR-3B filing  
- e-Invoice / IRN, e-Way Bill  
- Manufacturing  
- Multi-warehouse / multi-company  
- Offline billing & sync  
- Payment gateway  
- Thermal printing  
- Tally integration  
- AI assistant / advanced analytics  
- Credit notes / debit notes  
- SMS, Google login, free plan  
- Full message broker / plugin marketplace  
- Materialized reporting warehouse (add only if SQL/reporting views prove insufficient)  

---

## 3. Architecture principles (MVP)

### 3.1 Core principles

1. **Business documents are the only source of truth** — sales, purchases, returns, receipts, supplier payments, adjustments.  
2. **No physical customer/supplier ledger tables** — Ledger Service builds statements dynamically from documents + allocations.  
3. **Domain business events** — completing a document emits events; Inventory, Ledger (read models/balances), Reporting hooks, and Notifications react.  
4. **Append-only stock movements** with explicit **movement types** — never delete movements; correct via adjustment or return documents.  
5. **Atomic document completion** — stock + outstanding side-effects commit in one DB transaction with the document status change.  
6. **Service layer, not fat views** — Sales, Purchase, Inventory, Invoice, Payment, Ledger, Report, Import, Notification, File, DocumentNumber services.  
7. **Async for slow work** — PDF generation after invoice save success; email/WhatsApp via Celery.  
8. **Tenant isolation** — every query scoped by `company_id`.  
9. **API versioning** — all public routes under `/api/v1/`.  
10. **i18n-ready UI strings** even though English-only at launch.  

### 3.2 Business-event architecture (locked)

```
Purchase | Sale | Return | Payment | Adjustment | Opening Stock
                           │
                           ▼
                   Business Event
                           │
         ┌─────────┬───────┼────────┬────────────┐
         ▼         ▼       ▼        ▼            ▼
     Inventory   Ledger  Reporting  Notifications  Audit
     Service   Service   Service     Service
```

MVP implements this as **in-process domain events / service calls inside a DB transaction**, not a separate message broker. A broker can be introduced later without rewriting document modules.

### 3.3 High-level runtime

```
Web (React + MUI)
        │
   /api/v1  REST (DRF + JWT)
        │
 ┌──────┼──────────────────┐
 Auth   Business Services  Reporting Service
        │
 Document Number · File · Notification · Import · Search
        │
 PostgreSQL  ·  Redis  ·  Celery  ·  Object storage
```

### 3.4 Service layer (locked)

| Service | Responsibility |
|---|---|
| **Sales Service** | Quotations, sales invoices, sales returns, status transitions |
| **Purchase Service** | Purchase invoices, purchase returns, status transitions |
| **Invoice Service** | Shared tax/discount/rounding/PDF payload assembly (used by sales/purchase) |
| **Payment Service** | Customer receipts, supplier payments, **allocations** to open documents |
| **Inventory Service** | Stock balances, movements by type, adjustments, reservation fields |
| **Ledger Service** | Dynamic customer/supplier ledger & outstanding (no stored ledger rows) |
| **Report Service** | Registers, dashboards, exports — never raw FE→million-row table scans |
| **Import Service** | Upload → validate → preview → commit → error report |
| **Notification Service** | Single interface: Email, WhatsApp (SMS/Push/In-app stubs for later) |
| **File Service** | Logos, invoice PDFs, attachments, import files |
| **Document Number Service** | Independent sequences for invoice / purchase / quotation / return numbers |
| **Search Service** | Universal search across invoices, customers, products (barcode/SKU/name), suppliers |
| **Audit Service** | Create/Update/Delete/Login/Logout/Import activity log |

---

## 4. Document & entity statuses (locked)

### 4.1 Sales invoice

`Draft` → `Completed` → (`Cancelled` | partially/fully `Returned`)

| Status | Meaning |
|---|---|
| **Draft** | Editable; no stock/ledger effect |
| **Completed** | Number assigned (immutable); stock ↓; outstanding updated; PDF job queued |
| **Cancelled** | Reverses effects per business rules; not silently deletable |
| **Returned** | Linked sales return(s) applied (partial or full) |

### 4.2 Purchase invoice

`Draft` → `Completed` → `Cancelled`

### 4.3 Quotation

`Draft` → `Converted` / `Cancelled` (Converted links to sales invoice)

### 4.4 Returns

Sales/Purchase returns: `Draft` → `Completed` → `Cancelled`

### 4.5 Product

`Active` | `Inactive` — soft lifecycle; **never hard-delete** if referenced.

### 4.6 Customer

`Active` | `Blocked` — blocked customers **cannot** create new invoices.

### 4.7 Supplier / Product soft rules

Prefer inactive/blocked flags over delete. Hard delete only when never referenced (admin edge case).

---

## 5. Business rules (locked)

### 5.1 Sales

- Cannot sell **inactive** product.  
- Cannot create invoice for **blocked** customer.  
- Cannot complete sale that violates negative-stock policy (company setting: block or warn).  
- Invoice number assigned only on **Complete**; thereafter **immutable**.  
- **Completed** invoice cannot be line-edited; corrections via **Sales Return** or **Cancel** (per policy).  
- Draft invoices may be edited freely; drafts do not move stock.  
- Quantity on each line must be **> 0**.  
- Tax calculated automatically from product/company GST settings (CA-approved rules).  

### 5.2 Purchase

- Supplier is **required**.  
- Quantity on each line must be **> 0**.  
- Tax calculated automatically.  
- **Completed** purchase cannot be line-edited; corrections via **Purchase Return** or **Cancel**.  
- Purchase number assigned on Complete; immutable.  

### 5.3 Inventory

- Stock movements are **append-only** — never delete a movement row.  
- Corrections only via **Adjustment**, **Return**, or **Cancel** of source document.  
- Every movement has a **movement_type** (see §7).  
- Balances expose **on_hand**, **reserved**, **available** (`available = on_hand - reserved`; MVP `reserved = 0`).  

### 5.4 Payments

- Customer receipt / supplier payment must have amount **> 0**.  
- Payments may be **unallocated**, **partially allocated**, or **fully allocated**.  
- Allocation total cannot exceed payment amount.  
- Allocation to an invoice cannot exceed that invoice’s open outstanding.  
- Outstanding is derived: `completed invoices ± returns − allocated receipts/payments`.  

### 5.5 Masters & access

- Sales Staff cannot change company GST settings or users (Owner only).  
- Inventory adjustment requires inventory permission.  
- Import commit requires Owner (or explicit import permission).  

---

## 6. Tracking model

Use epics → work items with IDs below.

| Field | Values |
|---|---|
| Priority | `P0` (MVP blocker) · `P1` (MVP polish) · `P2` (Phase 2) |
| Status | `Todo` · `In Progress` · `Blocked` · `Done` · `Deferred` |
| Owner | FE / BE / QA / DevOps / Design / PM / CA |

**Milestones**

| Milestone | Meaning | Exit criteria |
|---|---|---|
| **M0** Foundations | Auth, company, tenancy, services skeleton, CI, `/api/v1` | Login + company create works |
| **M1** Masters | Customers/suppliers/products statuses, import pipeline, search | Pilot data loadable via preview import |
| **M2** Inventory | Movement-typed stock + reservation fields | Stock summary reconciles |
| **M3** Purchase | Draft/Complete/Cancel + returns + supplier payments/allocations | Stock ↑ and payables correct |
| **M4** Sales | Billing, multi-search, quotes, returns, async PDF, share | Invoice save < 10s UX; PDF async |
| **M5** Insights | Report Service dashboards + dynamic ledgers + export | KPIs match documents |
| **M6** Pilot-ready | Hardening, UAT, deploy | 20–50 pilots can onboard |

Suggested calendar for the ideal team: **~10–12 weeks** to M6 (adjust after sprint 0).

---

## 7. Inventory movement types (locked)

Table: `stock_movements` (append-only). Each row includes `movement_type`:

| movement_type | Stock effect |
|---|---|
| `OPENING_STOCK` | ↑ |
| `PURCHASE` | ↑ |
| `SALE` | ↓ |
| `PURCHASE_RETURN` | ↓ |
| `SALES_RETURN` | ↑ |
| `ADJUSTMENT` | ± |

Also store: `company_id`, `product_id`, `quantity`, `unit_cost` (as applicable), `reference_type`, `reference_id`, `created_by`, `created_at`.

**Balance fields (MVP):**

| Field | MVP behavior |
|---|---|
| `on_hand` | Sum of movements |
| `reserved` | Always `0` in MVP; column/API present |
| `available` | `on_hand - reserved` |

---

## 8. Payments & allocation (locked)

Do **not** use a single vague `payments` blob without structure.

### 8.1 Entities

| Entity | Purpose |
|---|---|
| **CustomerReceipt** | Money received from customer (mode, amount, date, reference) |
| **SupplierPayment** | Money paid to supplier |
| **PaymentAllocation** | Links a receipt/payment to one or more open invoices/returns |

### 8.2 Example

```
Sales Invoice  ₹5,000  (Completed)  outstanding 5,000
CustomerReceipt ₹2,000
  └─ PaymentAllocation → Invoice  ₹2,000
Outstanding                 ₹3,000
```

Ledger Service reads invoices, returns, receipts, payments, and allocations to build running balances — **no duplicated ledger rows**.

---

## 9. Reporting approach (locked)

```
Completed business documents
        ↓
  Reporting Service
        ↓
 Dashboard / Registers / Exports
```

Rules:

- UI/API clients **must not** aggregate millions of sales rows ad hoc for dashboard KPIs.  
- MVP: Reporting Service uses **optimized SQL / DB views** (indexes on `company_id`, date, status).  
- Optional later (P2): materialized views or summary tables **if** pilot volume requires it.  
- Customer/Supplier “ledger” screens call **Ledger Service**, not a stored ledger table.  

---

## 10. Epic backlog (trackable)

### Epic E0 — Foundations (M0)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E0.1 | Monorepo / project layout (`backend`, `web`, `docs`) | P0 | DevOps/BE | — | Repos boot locally |
| E0.2 | Docker Compose: Django, Postgres, Redis, Celery, Nginx | P0 | DevOps | E0.1 | `docker compose up` healthy |
| E0.3 | Django project + DRF + env settings + **`/api/v1` routing** | P0 | BE | E0.2 | Migrations run; `/api/v1/health` OK |
| E0.4 | React + Vite + TS + MUI + React Query + routing shell | P0 | FE | E0.1 | App shell renders |
| E0.5 | Auth: email/password + JWT refresh | P0 | BE/FE | E0.3 | Login/logout works |
| E0.6 | Auth: mobile + OTP | P0 | BE/FE | E0.5 | OTP login works |
| E0.7 | Company model + `company_id` tenancy mixin | P0 | BE | E0.5 | All business queries tenant-scoped |
| E0.8 | RBAC: Owner/Admin, Sales Staff + inventory permission flags | P0 | BE/FE | E0.7 | Role gates APIs & nav |
| E0.9 | Standard API envelope + errors + OpenAPI for v1 | P0 | BE | E0.3 | Swagger published under v1 |
| E0.10 | Row audit fields mixin (`created_by`, `updated_by`, timestamps) | P0 | BE | E0.7 | Models inherit mixin |
| E0.11 | **Audit Service** — Create/Update/Delete/Login/Logout/Import events | P0 | BE | E0.5 | Activity log queryable |
| E0.12 | Service layer package skeleton + in-process domain event bus | P0 | BE | E0.3 | Document services can emit events |
| E0.13 | **Document Number Service** (independent sequences per doc type) | P0 | BE | E0.7 | Concurrent-safe unique numbers |
| E0.14 | **File Service** (logo, PDF, attachments, imports) | P0 | BE | E0.7 | Upload/download by company |
| E0.15 | **Notification Service** interface (Email + WhatsApp adapters) | P0 | BE | E0.2 | Send via Celery; SMS/Push stubbed |
| E0.16 | CI: lint, tests, migrate, FE build | P0 | DevOps | E0.2–E0.4 | Pipeline green |
| E0.17 | i18n scaffolding (English default) | P1 | FE | E0.4 | Strings externalized |

---

### Epic E1 — Company & masters (M1)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E1.1 | Company profile: legal name, address, logo, bank, UPI | P0 | BE/FE | E0.7, E0.14 | Settings CRUD |
| E1.2 | GST settings: GSTIN (format), state, registration type, tax rates | P0 | BE/FE/CA | E1.1 | GST/non-GST company modes |
| E1.3 | Financial year config (series owned by Document Number Service) | P0 | BE | E1.1, E0.13 | FY + series configured |
| E1.4 | Customers CRUD + **Active/Blocked** + credit limit/terms | P0 | BE/FE | E0.7 | Blocked cannot be billed |
| E1.5 | Suppliers CRUD + search | P0 | BE/FE | E0.7 | Usable in purchase |
| E1.6 | Products CRUD: SKU, barcode, HSN/SAC, GST, unit, prices, reorder + **Active/Inactive** | P0 | BE/FE | E1.2 | Soft lifecycle; no hard delete when used |
| E1.7 | Categories, brands, units, tax rates masters | P0 | BE/FE | E1.6 | Selectable on products |
| E1.8 | **Import Service** pipeline: Upload → Validate → Preview → Commit → Error report | P0 | BE/FE | E1.4–E1.6 | No blind import |
| E1.9 | User invite/management UI (Owner manages Sales Staff) | P0 | BE/FE | E0.8 | Multi-user per company |
| E1.10 | HSN format + GST rate validation helpers | P0 | BE/CA | E1.2 | Invalid codes rejected |
| E1.11 | **Search Service**: customer, supplier, product (barcode/SKU/name), invoice | P0 | BE/FE | E1.4–E1.6 | Universal search UI |

---

### Epic E2 — Inventory engine (M2)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E2.1 | `stock_movements` append-only + **movement_type** enum | P0 | BE | E1.6, E0.12 | Every movement typed & logged |
| E2.2 | Stock balance: `on_hand`, `reserved` (=0), `available` | P0 | BE | E2.1 | Fast stock reads; future-proof fields |
| E2.3 | Opening stock (import or UI) → `OPENING_STOCK` movement | P0 | BE/FE | E2.1, E1.8 | Opening balances correct |
| E2.4 | Manual stock adjustment (+ reason) → `ADJUSTMENT` | P0 | BE/FE | E2.1 | Adjustment updates on_hand |
| E2.5 | Negative stock policy (block/warn) on available qty | P0 | BE | E2.2 | Enforced on sales complete |
| E2.6 | Low stock / reorder alerts | P0 | BE/FE | E2.2 | Alert list + counts |
| E2.7 | Stock summary + stock movement ledger UI | P0 | BE/FE | E2.1 | Filterable by movement_type |

**Side-effect matrix (on document Complete)**

| Business event | Stock movement | Customer outstanding | Supplier outstanding |
|---|---|---|---|
| Purchase completed | `PURCHASE` ↑ | — | ↑ |
| Purchase return completed | `PURCHASE_RETURN` ↓ | — | ↓ |
| Sales completed | `SALE` ↓ | ↑ (credit/partial) | — |
| Sales return completed | `SALES_RETURN` ↑ | ↓ | — |
| Customer receipt (+ allocation) | — | ↓ | — |
| Supplier payment (+ allocation) | — | — | ↓ |
| Stock adjustment | `ADJUSTMENT` ± | — | — |
| Opening stock | `OPENING_STOCK` ↑ | — | — |

Outstanding is always **derived** by Ledger Service from documents + allocations.

---

### Epic E3 — Purchase management (M3)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E3.1 | Purchase invoice Draft/edit; Complete/Cancel transitions | P0 | BE/FE | E1.5, E2.1, E0.13 | Status machine enforced |
| E3.2 | GST / non-GST purchase tax calculation (Invoice Service) | P0 | BE/CA | E3.1 | Tax lines CA-validated |
| E3.3 | On Complete: emit event → Inventory + outstanding (atomic) | P0 | BE | E3.1, E2.1 | Transactional; rollback safe |
| E3.4 | Purchase return Draft → Complete | P0 | BE/FE | E3.3 | ↓ stock + ↓ outstanding |
| E3.5 | **SupplierPayment** + **PaymentAllocation** | P0 | BE/FE | E3.3 | Partial/full allocate; outstanding correct |
| E3.6 | Purchase register via Report Service; supplier ledger via Ledger Service | P0 | BE/FE | E3.3–E3.5 | Reconciles with documents |
| E3.7 | Attach purchase bill via File Service | P1 | BE/FE | E3.1, E0.14 | File viewable |
| E3.8 | Optional PO (lightweight) | P1 | BE/FE | E3.1 | PO → invoice convert (nice-to-have) |

---

### Epic E4 — Sales & invoice engine (M4)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E4.1 | Fast billing UI: **barcode + SKU + name + product search** | P0 | FE | E1.6, E1.11 | Multi-mode line add |
| E4.2 | Invoice types: GST / Tax / Retail / Non-GST + Draft/Complete/Cancel/Returned | P0 | BE/FE/CA | E1.2, E0.13 | Status + template fields correct |
| E4.3 | Discounts, tax breakup, rounding (Invoice Service) | P0 | BE/CA | E4.2 | CA-approved calc suite |
| E4.4 | On Complete: stock check + atomic SALE movement + outstanding | P0 | BE | E4.2, E2.5 | Save API < 2s; number immutable |
| E4.5 | Quotation create + convert to invoice | P0 | BE/FE | E4.2 | Convert preserves lines |
| E4.6 | Sales return Draft → Complete | P0 | BE/FE | E4.4 | ↑ stock + ↓ outstanding |
| E4.7 | **CustomerReceipt** + **PaymentAllocation** (partial/full) | P0 | BE/FE | E4.4 | Modes: cash/UPI/bank/card/credit |
| E4.8 | **Async PDF**: Complete → success → Celery PDF → notify FE when ready | P0 | BE/FE | E4.3, E0.14, E0.15 | Billing not blocked on PDF |
| E4.9 | Print A4 + PDF download (when ready) | P0 | FE | E4.8 | Print preview works |
| E4.10 | WhatsApp + Email share via Notification Service | P0 | BE/FE | E4.8 | Async delivery + status |
| E4.11 | Sales history filters + universal search hit → invoice | P0 | FE | E4.4, E1.11 | Find invoice quickly |
| E4.12 | Enforce business rules: inactive product, blocked customer, completed immutability | P0 | BE/QA | E4.4, §5 | Negative tests pass |

---

### Epic E5 — Ledger, dashboard & reports (M5)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E5.1 | **Ledger Service**: customer/supplier running ledger + outstanding (dynamic) | P0 | BE | E3.5, E4.7 | Matches document math; **no ledger tables** |
| E5.2 | **Report Service** dashboard KPIs (indexed/view-backed queries) | P0 | BE/FE | E3, E4 | < 2s; not ad-hoc FE scans |
| E5.3 | Sales register, customer sales, product sales | P0 | BE/FE | E4, E5.2 | Date/customer/product filters |
| E5.4 | Purchase register, supplier purchases | P0 | BE/FE | E3, E5.2 | Same |
| E5.5 | Inventory reports: summary, movements by type, low stock, value | P0 | BE/FE | E2 | Matches movements |
| E5.6 | Customer outstanding + ledger UI (Ledger Service) | P0 | BE/FE | E5.1 | Running balance correct |
| E5.7 | Supplier outstanding + ledger UI (Ledger Service) | P0 | BE/FE | E5.1 | Running balance correct |
| E5.8 | Export PDF / Excel / CSV via Report Service | P0 | BE/FE | E5.3–E5.7 | Downloads clean |
| E5.9 | Business alerts strip (low stock, dues) | P1 | FE | E2.6, E5.2 | Actionable links |
| E5.10 | Add materialized/summary tables only if KPI queries miss SLA | P2 | BE | E5.2 | Perf evidence driven |

---

### Epic E6 — UX navigation (cross-cutting)

MVP nav (locked):

```
Dashboard
Sales
  ├── New Invoice (barcode / SKU / name search)
  ├── Sales History
  ├── Quotations
  ├── Receipts
  └── Customers
Purchases
  ├── New Purchase
  ├── Purchase History
  ├── Supplier Payments
  └── Suppliers
Inventory
  ├── Products
  ├── Current Stock
  ├── Stock Adjustment
  └── Low Stock
Reports
  ├── Sales
  ├── Purchases
  ├── Inventory
  ├── Customer Ledger
  └── Supplier Ledger
Settings
  ├── Company
  ├── GST
  ├── Invoice Templates
  ├── Users
  └── Backup / Export
```

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E6.1 | App shell, responsive layout, role-based menu | P0 | FE/Design | E0.8 | Nav matches roles |
| E6.2 | Global search entry point (Search Service) | P0 | FE | E1.11 | Cmd/Ctrl-K or header search |
| E6.3 | Keyboard-friendly billing shortcuts | P1 | FE | E4.1 | Power-user path |
| E6.4 | Empty states + onboarding checklist for pilot | P1 | FE/PM | E1 | First invoice in < 30 min |

---

### Epic E7 — Hardening, compliance, pilot (M6)

| ID | Work item | Pri | Owner | Depends | Done when |
|---|---|---|---|---|---|
| E7.1 | CA review pack: invoice samples + tax calc test matrix | P0 | CA/BE | E4.3, E4.8 | Written CA sign-off |
| E7.2 | Integration tests for event matrix + allocation math + status machines | P0 | BE/QA | E2–E5 | Matrix automated |
| E7.3 | API + UI regression for billing critical path | P0 | QA | E4–E5 | Smoke + critical path green |
| E7.4 | Performance: search, invoice save, async PDF readiness, dashboard | P0 | BE/FE | E4–E5 | Meet targets |
| E7.5 | Security: JWT, RBAC, tenant isolation, input validation | P0 | BE/QA | E0 | Checklist signed |
| E7.6 | Daily DB backup + restore drill | P0 | DevOps | E0.2 | Restore verified |
| E7.7 | Prod deploy: Lightsail/EC2 + Nginx + Gunicorn + Postgres/Redis | P0 | DevOps | E0.16 | Staging + prod live |
| E7.8 | Monitoring (errors, uptime, invoice failure rate, PDF job failures) | P0 | DevOps | E7.7 | Alerts configured |
| E7.9 | Pilot onboarding playbook + paid pilot contracts | P0 | PM | E7.7 | 20–50 businesses process ready |
| E7.10 | UAT with 5 seed pilots → expand to 20–50 | P0 | QA/PM | E7.3 | Issues triaged; CSAT tracked |
| E7.11 | Support runbook (billing/stock/allocation issues) | P1 | PM/QA | E7.10 | Support can resolve |

---

## 11. Suggested delivery phases (calendar)

Assumes ideal team; parallel FE/BE work.

| Weeks | Focus | Milestone |
|---|---|---|
| 1–2 | Foundations, auth, services skeleton, Document Number / File / Notification / Audit, CI | **M0** |
| 2–4 | Masters + statuses, Search, Import preview pipeline, Inventory movements | **M1 + M2** |
| 4–6 | Purchase statuses + supplier payments/allocations + purchase reports | **M3** |
| 6–9 | Sales billing, multi-search, quotes, returns, async PDF, share, receipts/allocations | **M4** |
| 9–10 | Ledger Service, Report Service dashboards, exports, UX polish | **M5** |
| 10–12 | CA sign-off, tests, perf, deploy, UAT, pilot ramp | **M6** |

---

## 12. Core data model (MVP)

### 12.1 Persist (source of truth)

- `users`, `roles`, `company_users`  
- `companies`  
- `customers` (**status**: Active/Blocked)  
- `suppliers`  
- `products` (**status**: Active/Inactive), `categories`, `brands`, `units`, `tax_rates`  
- `document_series` (owned by Document Number Service)  
- `purchase_invoices`, `purchase_items` (**status**)  
- `purchase_returns`, `purchase_return_items` (**status**)  
- `sales_invoices`, `sales_items` (**status**)  
- `quotations`, `quotation_items` (**status**)  
- `sales_returns`, `sales_return_items` (**status**)  
- `stock_movements` (**movement_type**, append-only)  
- `stock_balances` (`on_hand`, `reserved`, `available`) — derived cache OK; rebuildable from movements  
- `customer_receipts`  
- `supplier_payments`  
- `payment_allocations`  
- `files` / `attachments`  
- `otp_challenges`  
- `audit_events` (Create/Update/Delete/Login/Logout/Import)  

All business tables include **`company_id`**.

### 12.2 Do not persist as duplicate truth

| Avoid | Use instead |
|---|---|
| `customer_ledgers` table | **Ledger Service** over invoices/returns/receipts/allocations |
| `supplier_ledgers` table | **Ledger Service** over purchases/returns/payments/allocations |
| Generic unallocated-only `payments` | `customer_receipts` + `supplier_payments` + `payment_allocations` |

Optional **balance caches** (e.g. customer outstanding) are allowed if rebuildable from source documents — never a second manual ledger.

---

## 13. API surface (MVP)

All routes versioned:

```
/api/v1/auth/
/api/v1/company/
/api/v1/customers/
/api/v1/suppliers/
/api/v1/products/
/api/v1/purchases/          # invoices, returns
/api/v1/sales/              # invoices, quotations, returns
/api/v1/payments/receipts/
/api/v1/payments/supplier-payments/
/api/v1/payments/allocations/
/api/v1/inventory/          # balances, movements, adjustments, alerts
/api/v1/ledgers/customers/
/api/v1/ledgers/suppliers/
/api/v1/reports/
/api/v1/dashboard/
/api/v1/search/
/api/v1/imports/
/api/v1/exports/
/api/v1/files/
/api/v1/notifications/      # status/webhooks as needed
/api/v1/audit/
```

REST: `GET | POST | PUT | PATCH | DELETE` with tenant-scoped authorization.

---

## 14. Async PDF flow (locked)

```
Complete Invoice (atomic business post)
        ↓
Return 201/200 success (invoice id, number, status=Completed)
        ↓
Enqueue Celery job: Generate PDF (File Service)
        ↓
Store PDF · update invoice.pdf_status = Ready
        ↓
Notify frontend (poll or websocket later; MVP: poll/status endpoint)
        ↓
User downloads / prints / shares
```

Invoice **save UX must not wait** on PDF rendering. Share actions wait until `pdf_status = Ready` (or generate-on-demand fallback if job failed).

---

## 15. Import flow (locked)

```
Upload file (File Service)
    ↓
Validate schema + business rules
    ↓
Preview (row counts, errors, warnings)
    ↓
User confirms Commit
    ↓
Import Service writes masters / opening stock
    ↓
Error report (downloadable) for failed rows
```

---

## 16. Non-functional targets (MVP)

| Area | Target |
|---|---|
| App launch | < 3s |
| Invoice complete (API response) | < 2s |
| Invoice generation (UX to usable confirmation) | < 10s |
| PDF ready (async) | < 3s typical after complete |
| Search | < 500ms (API) / < 2s (UX) |
| Dashboard (Report Service) | < 2s |
| Uptime | Aim 99.9% in pilot env |
| Security | TLS, hashed passwords, RBAC, tenant isolation |

---

## 17. Test plan (MVP)

| Layer | Must cover |
|---|---|
| Unit | Tax calc, document numbers, stock math by movement_type, allocation math |
| Integration | Event matrix, status machines, blocked/inactive rules, cancel/return paths |
| API | Auth, RBAC, tenant isolation, `/api/v1` contracts |
| UI | Fast billing multi-search, import preview, async PDF, share |
| UAT | Day open → import → purchase → sell (partial pay) → return → ledger/report |
| Regression | Before each pilot cohort expansion |
| Compliance | CA sample invoice pack per major tax scenario |

---

## 18. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Incorrect GST calculation | Legal / trust | CA-owned rule pack + calc test matrix |
| Stock / outstanding drift | Data integrity | Single event posting path; rebuildable balances; reconciliation tests |
| Ledger bugs from dual-write | Integrity | **No ledger tables**; Ledger Service only |
| Slow dashboard at scale | UX | Report Service + indexes/views; materialize only if needed |
| WhatsApp/Email deliverability | Pilot friction | Notification Service retries; PDF download always available |
| Scope creep (accounting/GST returns) | Delay | Strict Phase 2 backlog; PM gate |
| Invoice number races | Duplicates | Document Number Service + DB unique constraints |
| Sync PDF blocking billing | Slow UX | Async PDF (locked) |
| Pilot support overload | Churn | Onboarding checklist + support runbook |

---

## 19. Phase 2 backlog (explicitly deferred)

1. Credit notes / debit notes  
2. Thermal 58mm / 80mm printing  
3. Full POS mode  
4. Offline sync  
5. Android → Desktop → iOS  
6. Payment gateway  
7. GSTR-1 / GSTR-3B  
8. e-Invoice / e-Way Bill  
9. Multi-warehouse / multi-company  
10. Manual accounting module (journals, P&L, BS)  
11. Manufacturing  
12. Tally import/export  
13. Live GSTN verification  
14. SMS / Push / Google login / free plan  
15. AI assistant / forecasting  
16. Full message broker / plugin architecture  
17. Materialized reporting warehouse (if/when SLA requires)  
18. Non-zero inventory reservation / SO reservation workflows  

---

## 20. Definition of Done (global)

A work item is **Done** only when:

1. Code merged with tests for the behavior  
2. Tenant isolation verified  
3. FE and BE contracts match OpenAPI **v1**  
4. Business rules in §5 enforced where applicable  
5. QA signed critical path (if P0)  
6. No open P0 bugs  
7. For tax/invoice items: CA validation where marked  

**MVP release DoD (M6):**

- All P0 items in E0–E7 Done or explicitly waived by PM  
- No physical `customer_ledgers` / `supplier_ledgers` tables in schema  
- Payment allocation supported for partial collections  
- Document statuses and stock movement types in production use  
- Async PDF path live  
- CA sign-off on invoice + tax matrix  
- Staging UAT passed with ≥ 5 seed pilots  
- Prod deploy + backups + monitoring live  
- Pilot onboarding ready for 20–50 paid businesses  
- Success metrics instrumentation in place  

---

## 21. Immediate next actions (pilot hardening)

1. Engage CA for invoice/tax rule pack sign-off.  
2. Finalize WhatsApp approach (Business API vs share-link) and production email provider.  
3. Finalize OTP SMS provider (DEBUG echo only today).  
4. Staging UAT: register → import → purchase → invoice → partial receipt → ledger/report.  
5. Pilot onboarding for 20–50 paid businesses; instrument success metrics.  
6. Production deploy + backups + monitoring.

---

## 22. Review changelog (v1.0 → v1.1)

| Review item | Disposition |
|---|---|
| Remove physical ledger tables; Ledger Service | **Adopted (P0)** |
| Payment receipts + supplier payments + allocation | **Adopted (P0)** |
| Reports via Reporting Service; not raw table scans | **Adopted (P0)** — optimized SQL/views first; materialize later if needed |
| Stock movement types | **Adopted (P0)** |
| Invoice / purchase statuses | **Adopted (P0)** |
| Product Active/Inactive; Customer Active/Blocked | **Adopted (P1 → treated P0 for rules)** |
| Inventory reservation fields (reserved=0) | **Adopted (P1)** |
| Business Rules section | **Adopted (P0)** |
| `/api/v1` versioning | **Adopted (P0)** |
| Async PDF | **Adopted (P0)** |
| Universal search | **Adopted (P0)** |
| Import preview pipeline | **Adopted (P0)** |
| Multi-mode product search (barcode/SKU/name) | **Adopted (P0)** |
| Document Number Service | **Adopted (P0)** |
| Notification Service abstraction | **Adopted (P1/P0 interface)** |
| File Service | **Adopted (P0)** |
| Richer audit events | **Adopted (P0)** |
| Explicit service layer | **Adopted (P0)** |
| Business-event architecture | **Adopted (P0)** — in-process domain events; broker deferred |
| Full message broker / AI / plugins | **Deferred (P2)** — not needed for MVP |

---

## 23. Guiding principle

> Business documents emit events. Inventory, dynamic ledgers, reports, and notifications react. Never enter the same fact twice — and never store a second “ledger truth” that can drift.

---

**Document owner:** Product  
**Change control:** Any addition to §2.1 requires explicit scope change and milestone replan.  
**Architecture gate:** P0 items in §22 must remain satisfied before “Start M0”.

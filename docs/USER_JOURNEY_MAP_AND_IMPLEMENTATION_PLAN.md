# Bizboard End-to-End User Journey Map & Grounded UX Implementation Plan

**Document Version:** 2.0 (Grounded Revision)  
**Date:** 2026-09-30  
**Status:** Journey Hypothesis & Grounded Engineering Delta — Reconciled with live POS hotkeys, `posEnter.ts`, `deviceDraft.ts`, receipt allocations, GSTIN validation, and GSTR-2B.  
**Role:** Principal UX Researcher, Service Designer, and Customer Journey Expert  
**Target Platform:** Bizboard (Web & Capacitor Android Shell / React 18 + TypeScript + Vite + Vitest / Django REST Framework)  
**Design Philosophy:** Evidence-based, implementation-oriented, keyboard-first, zero data loss, offline-resilient, and optimized for sub-second cognitive processing under high-traffic MSME trading conditions.

---

## Table of Contents
1. [Executive Journey Summary](#1-executive-journey-summary)
2. [Persona-wise Journey Maps](#2-persona-wise-journey-maps)
3. [Step-by-Step Hypothesized Journey Tables](#3-step-by-step-hypothesized-journey-tables)
   - [Workflow 1: Rapid Point-of-Sale (POS) Counter Loop](#workflow-1-rapid-point-of-sale-pos-counter-loop)
   - [Workflow 2: B2B Trade Order-to-Cash Loop](#workflow-2-b2b-trade-order-to-cash-loop)
   - [Workflow 3: Inward Procurement & Lot/Expiry Inwarding](#workflow-3-inward-procurement--lotexpiry-inwarding)
   - [Workflow 4: Inter-Godown Stock Transfer & Variance Reconciliation](#workflow-4-inter-godown-stock-transfer--variance-reconciliation)
   - [Workflow 5: Receivables Dunning & Payment Allocation](#workflow-5-receivables-dunning--payment-allocation)
   - [Workflow 6: Period Close & CA Statutory Handshake](#workflow-6-period-close--ca-statutory-handshake)
4. [Pain Point Matrix (Audited Against Current Tree)](#4-pain-point-matrix-audited-against-current-tree)
5. [Emotional Journey Analysis](#5-emotional-journey-analysis)
6. [Drop-off & Friction Analysis (Hypothesized Bottlenecks)](#6-drop-off--friction-analysis-hypothesized-bottlenecks)
7. [Opportunity Map (Service Design Blueprint)](#7-opportunity-map-service-design-blueprint)
8. [Target UX Metrics & Discovery Hypotheses](#8-target-ux-metrics--discovery-hypotheses)
9. [Grounded Engineering Delta & Implementation Plan](#9-grounded-engineering-delta--implementation-plan)
   - [9.1 Architectural Guardrails & Invariants](#91-architectural-guardrails--invariants)
   - [9.2 Reconciled Release & PR Sequencing](#92-reconciled-release--pr-sequencing)
   - [9.3 Technical Specifications by Pull Request](#93-technical-specifications-by-pull-request)
   - [9.4 Storage Conflict Policy: Device Drafts vs. Offline Outbox](#94-storage-conflict-policy-device-drafts-vs-offline-outbox)
   - [9.5 Verification & Automated Test Strategy (Vitest & Playwright)](#95-verification--automated-test-strategy)
   - [9.6 Rollback Strategy & Risk Governance](#96-rollback-strategy--risk-governance)
   - [9.7 Engineering Timeline & Resourcing](#97-engineering-timeline--resourcing)

---

## 1. Executive Journey Summary

**Product Ecosystem:** Bizboard (Integrated MSME Trade, Counter Retail, Multi-Godown & Statutory ERP Platform)  
**Evaluation Scope:** End-to-end operational loops spanning retail counter checkout, B2B order-to-cash, lot/expiry procurement, inter-godown transfers, receivables aging/allocation, and CA tax reconciliation.  
**Research & Service Design Context:** Evaluated against Indian MSME operational realities—noisy bazaars, interrupted workflows, variable 4G connectivity, keyboard-first desktop operators, mobile-first field representatives, and role consolidation (from solo proprietor to departmental trade firms).

```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|                                    EXECUTIVE SERVICE DESIGN HORIZON                                         |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|  FRONTLINE TOUCHPOINTS              CORE TRANSACTION ENGINES                BACK-OFFICE & COMPLIANCE        |
|  • Counter POS (/pos)               • Atomic Inventory & AP                 • Derived AR/AP Real-Time Ledger|
|  • Mobile Field Booker (PWA)        • Multi-Price Slabs & Challans          • Cash/Bank Allocation Engine   |
|  • Warehouse Intake / Barcode       • FEFO Lot / Serial Inwarding           • GSTR-1 / 3B Worksheets & 2B   |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|  PROVEN CAPABILITIES: Atomic document posting; derived ledger; F2 scan focus; F8/F9 session hold/cycle;     |
|  choosePosEnter resolution; allocateOldest on receipts; Gstr2bIngest; auto_round_off; UPI QR generation.    |
|  RESIDUAL UX DELTAS: Focus theft during inline editing; receipt allocation defaults; transfer variance      |
|  accounting; early duplicate bill validation; smart expiry shorthand; CA 1-click audit bundling.           |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```

---

## 2. Persona-wise Journey Maps

```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| PERSONA 1 (P1): "Sethji" — The Managing Proprietor (Economic Buyer & Commercial Anchor)                    |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Context: Operates wholesale/retail trade. Split focus between telephone orders, walk-ins, and cash custody. |
| Emotional Anchor: "Is cash reconciled, are customer credit limits respected, and are tax filings safe?"    |
| Primary Touchpoints: Dashboard, Receivables Aging, Ledger Statements, Owner Credit Overrides.               |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```
```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| PERSONA 2 (P2): "Ramesh" — Frontline Billing Operator (High-Frequency Counter Clerk)                       |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Context: Physical customer waiting at the counter. Zero tolerance for mouse reach or input lag.            |
| Emotional Anchor: "Bill and tender in minimum keystrokes without holding up the queue."                    |
| Primary Touchpoints: Counter POS (/pos), Barcode Listener, Quick Tender (F1/F4/F5/F7), Thermal Print.      |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```
```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| PERSONA 3 (P3): "Vikas" — Field Sales Representative (Traveling Order Booker)                              |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Context: Visiting retail dealers on a two-wheeler; intermittent 4G; entering multi-item orders on mobile.  |
| Emotional Anchor: "Verify customer credit standing and stock availability on the spot before booking."      |
| Primary Touchpoints: Sales Order Editor, Party Credit Exposure, Stock by Godown, WhatsApp Share.           |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```
```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| PERSONA 4 (P4): "Mukesh" — Godown Custodian (Physical Inventory & Logistics Handler)                       |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Context: Dusty warehouse, handheld barcode scanner or tablet, manual carton handling.                      |
| Emotional Anchor: "Inward shipments with accurate batch/expiry dates without clerical friction or errors."  |
| Primary Touchpoints: Purchase Bill Entry (/purchases/new), Stock Transfers (/inventory/transfers).        |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```
```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| PERSONA 5 (P5): "Shastriji" — Resident Bookkeeper ("The Internal Munshi")                                   |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Context: Desk-bound, double-entry background, matching physical bank statements against sales ledgers.     |
| Emotional Anchor: "Every rupee received must be allocated against an invoice with zero untraced balance."  |
| Primary Touchpoints: Purchase Bills, Customer Receipts (/sales/receipts), Allocation Matrix.                |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```
```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| PERSONA 6 (P6): "Agarwal Sir" — External Compliance Consultant (Chartered Accountant / Tax Auditor)         |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Context: Audits numerous MSME clients before monthly statutory deadlines; impatient with inconsistent data.|
| Emotional Anchor: "Extract GSTR-1, GSTR-3B, and Trial Balance in minutes with reconciled ITC."             |
| Primary Touchpoints: Statutory Reports (/reports/gstr1, /reports/trial-balance), GSTR-2B Ingest.          |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```

---

## 3. Step-by-Step Hypothesized Journey Tables

```
Legend for Emotional States:
  🤩 DELIGHT      — Seamless, fast, confidence-inspiring
  😊 CONFIDENT    — Routine operation progressing smoothly
  🤔 UNCERTAIN    — Ambiguous state or missing confirmation
  😰 ANXIOUS      — Risk of financial mismatch, customer dispute, or compliance error
  😡 FRUSTRATED   — Unnecessary re-typing, input focus loss, or blocking modal
```

---

### Workflow 1: Rapid Point-of-Sale (POS) Counter Loop
* **Archetype:** ARCH-01 (Fast Counter Retailer) & ARCH-06 (Serialized Goods Dealer)
* **Actor:** P2 (Counter Clerk), P1 (Proprietor)
* **Goal:** Scan items, tender payment via Dynamic UPI QR or Cash, print thermal receipt.
* **Trigger:** Customer places items on the billing counter.

| Step | Screen / Touchpoint | User Action & Inputs | Underlying Question | Emotion | Identified Friction & Residual Delta | Trust & Delight Moments |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **1. Session Init** | Counter POS (`/pos`) | P2 opens terminal or switches session via `F9`. | *"Is the scanner active? Are held bills intact?"* | 😊 CONFIDENT | Shared counter PC: private browsing or storage quota eviction can drop uncommitted session drafts. | **Trust:** Register balance and held session tabs visible. |
| **2. Barcode Scanning** | Search Input (`searchRef`) | Barcode scanner wedges EAN-13 code directly into item input. | *"Did it register? Did exact code win?"* | 🤩 DELIGHT | `choosePosEnter` already gives exact barcode precedence over fuzzy highlight. **Residual Gap:** Adding a line must not steal focus if clerk deliberately clicked into quantity or discount. | **Delight:** Sub-second item addition with tax and price calculation. |
| **3. Line Adjustment** | Cart Table Row | Adjusts quantity, discount, or selects batch. | *"Will focus jump away if I touch the quantity box?"* | 🤔 UNCERTAIN | Naive focus re-lock effects can steal focus from quantity input back to search input while typing. | **Trust:** Immediate calculation of tax breakdown (CGST + SGST). |
| **4. Customer Assignment** | Customer Auto-suggest (`F3`) | Enters mobile number or leaves as Walk-in. | *"Does customer have credit terms or outstanding balance?"* | 😊 CONFIDENT | Pressing `F3` jumps to customer. Auto-complete works as designed. | **Trust:** Customer outstanding balance badge rendered. |
| **5. Multi-Cart Hold** | Hold Session (`F8`) | Holds current bill to attend next customer; cycles via `F9`. | *"Will this held bill survive a page refresh?"* | 😊 CONFIDENT | `F8` holds and `F9` cycles. **Residual Gap:** Persistence uses `deviceDraft.ts` (`pos-sessions`), which needs strict coordination with the offline outbox on reload. | **Delight:** Immediate switching between multiple carts. |
| **6. Tender Settlement** | Quick Tender (`F1`/`F4`/`F5`/`F7`) | Selects Cash (`F1`), Card (`F4`), UPI (`F5`), or Credit (`F7`). | *"Did payment register accurately?"* | 😊 CONFIDENT | Dynamic UPI QR displays via `POST /api/v1/payments/upi-qr/`. For static physical QR stands, clerk must manually confirm collection. | **Delight:** Instant settlement calculation with change due. |
| **7. Atomic Completion & Print** | Receipt Modal & Thermal Hook | Transaction posts atomically; thermal slip cuts. | *"Did printer cut? Can I reprint if paper jammed?"* | 🤩 DELIGHT | `printPosThermalOrWarn` already executes native ESC/POS with PDF fallback. **Residual Gap:** Need dedicated reprint key (`Ctrl+Alt+P` or `F11`) to re-invoke the hook without leaving `/pos`. | **Moment of Truth:** Atomic ledger, AP/AR, and stock deduction. |

---

### Workflow 2: B2B Trade Order-to-Cash Loop
* **Archetype:** ARCH-03 (Semi-Wholesaler) & ARCH-04 (Multi-Godown Stockist)
* **Actor:** P3 (Field Sales Rep), P1 (Proprietor), P5 (Munshi)
* **Goal:** Create quote, convert to Sales Order, manage credit limits, issue Delivery Challan, generate GST Tax Invoice.
* **Trigger:** Customer calls or WhatsApps a bulk order with 30-day credit terms.

| Step | Screen / Touchpoint | User Action & Inputs | Underlying Question | Emotion | Identified Friction & Residual Delta | Trust & Delight Moments |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **1. Customer Credit Check** | Party Selection | P3 selects customer. Views credit standing. | *"Are they over their credit limit? Can I take this order?"* | 😊 CONFIDENT | `SalesOrderEditorPage.tsx` displays credit limit and outstanding balances. | **Trust:** Clear credit utilization figure. |
| **2. Multi-Line Item Entry** | Order Builder | Selects SKUs, quantity, and tiered wholesale price slab. | *"Which godown has stock? Is pricing accurate?"* | 😊 CONFIDENT | Multi-godown stock availability displayed cleanly. | **Trust:** Instant margin and tax calculation. |
| **3. Credit Hold Handling** | Credit Validation Gate | Order exceeds credit limit. System flags credit hold. | *"Can Sethji authorize this override quickly?"* | 😰 ANXIOUS | Proprietor override exists on `SalesOrderEditorPage.tsx`. **Residual Gap:** Remote field reps need a structured override token/OTP workflow rather than unauthenticated messaging. | **Trust:** System prevents inadvertent bad debt exposure. |
| **4. Delivery Challan (Dispatch)** | Dispatch Management | Stages stock, records transporter name, vehicle number, and LR. | *"Does driver have valid transport documents?"* | 😊 CONFIDENT | Dispatch documentation generated directly from order details. | **Trust:** Driver receives clear dispatch note with quantities. |
| **5. Tax Invoice Conversion** | Convert to Invoice | Converts Challan to Tax Invoice. Derived ledger increments AR. | *"Are HSN codes and GST splits accurate?"* | 🤩 DELIGHT | `web/src/utils/tax.ts` drives Place of Supply split. **Residual Gap:** Validate recipient GSTIN regex on input blur to catch typos early. | **Delight:** 1-click conversion with zero line-item re-entry. |
| **6. Dispatch & WhatsApp Share** | Invoice View | Clicks WhatsApp share with embedded payment link. | *"Did customer receive the invoice?"* | 🤩 DELIGHT | Native `wa.me` sharing already functional. | **Delight:** Professional PDF link and payment QR shared instantly. |

---

### Workflow 3: Inward Procurement & Lot/Expiry Inwarding
* **Archetype:** ARCH-05 (Batch & Expiry Stockist) & ARCH-06 (Serialized Goods Dealer)
* **Actor:** P4 (Godown Custodian), P5 (Resident Munshi)
* **Goal:** Inward stock, record batch/expiry and serials, verify supplier totals, atomically post inventory and AP.
* **Trigger:** Goods delivery arrives at warehouse with physical invoice.

| Step | Screen / Touchpoint | User Action & Inputs | Underlying Question | Emotion | Identified Friction & Residual Delta | Trust & Delight Moments |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **1. Header & Supplier Bill** | New Purchase (`/purchases/new`) | Selects Vendor, enters Supplier Bill # and Bill Date. | *"Is this a duplicate bill already entered?"* | 🤔 UNCERTAIN | `backend/purchases/services.py` rejects duplicate `supplier_bill_number` at complete. **Residual Gap:** Debounce-check duplicate bill number on input blur to avoid late rejection. | **Trust:** Vendor balance and payment terms populated. |
| **2. Batch & Expiry Entry** | Line Item Table | Enters Batch Number, Mfg Date, Expiry Date. | *"Do I have to type full DD/MM/YYYY dates across 40 lines?"* | 😡 FRUSTRATED | Standard date pickers cause high clerical fatigue during bulk intake. **Residual Gap:** Shorthand date parser (`0828` → `31/08/2028`) with strict validation. | **Anxiety:** Fear of mis-keying expiry year and corrupting FEFO picking order. |
| **3. Serial / IMEI Ingestion** | Serial Dialog | Scans carton IMEI barcodes sequentially. | *"Did all serials register? Any duplicates?"* | 😊 CONFIDENT | Barcode scanner wedge inputs handled cleanly with duplicate string checking. | **Delight:** Audio feedback and live count of scanned serials. |
| **4. Penny Round-Off Match** | Summary Footer | Verifies invoice totals against supplier's printed bill. | *"Why is the software off by 35 paise?"* | 😊 CONFIDENT | `auto_round_off` already resolves small rounding differences on purchase documents. | **Trust:** Software total matches paper bill exactly. |
| **5. Atomic Complete & Post** | Save & Complete | Posts purchase bill atomically. Stock and AP increase together. | *"Is stock immediately available for sales?"* | 🤩 DELIGHT | Atomic posting ensures immediate inventory availability across all terminals. | **Moment of Truth:** Zero balance drift; immediate stock visibility. |

---

### Workflow 4: Inter-Godown Stock Transfer & Variance Reconciliation
* **Archetype:** ARCH-04 (Multi-Godown Regional Stockist)
* **Actor:** P4 (Godown Custodian), P1 (Proprietor)
* **Goal:** Transfer stock between godowns, track movement, and reconcile transit variances.
* **Trigger:** Branch warehouse reports low stock on critical SKUs.

| Step | Screen / Touchpoint | User Action & Inputs | Underlying Question | Emotion | Identified Friction & Residual Delta | Trust & Delight Moments |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **1. Transfer Initiation** | Stock Transfers (`/inventory/transfers`) | Selects Source and Destination Godowns. | *"Does source warehouse have uncommitted stock?"* | 😊 CONFIDENT | Uncommitted stock availability displayed clearly per godown. | **Trust:** Prevents over-committing staged inventory. |
| **2. Item Dispatch** | Transfer Editor | Inputs transfer quantities, vehicle/driver details, and posts. | *"Are items deducted from source now?"* | 😊 CONFIDENT | Atomic stock transfer decrements source and increments destination. | **Trust:** Clear transfer challan generated for driver. |
| **3. Transit Tracking** | Transfer List | Monitors transfer status. | *"Has shipment arrived at destination?"* | 🤔 UNCERTAIN | `StockTransfer.Status` is currently `DRAFT`, `COMPLETED`, `CANCELLED`. No formal in-transit state. | **Anxiety:** Driver is on the road; goods are in transit limbo. |
| **4. Receiving & Variance** | Destination Verification | Receiver counts packages and finds damaged/missing items. | *"How do I accept 48 units and write off 2 damaged units?"* | 😰 ANXIOUS | Current system is atomic complete. **Residual Gap:** Multi-step receiving state machine (`IN_TRANSIT` → `RECEIVED_WITH_VARIANCE`) with automated shrinkage ledger debit. | **Delight:** Transparent variance accounting without manual journal entries. |

---

### Workflow 5: Receivables Dunning & Payment Allocation
* **Archetype:** ARCH-03 (Semi-Wholesaler) & ARCH-07 (Commercial Services)
* **Actor:** P5 (Internal Munshi), P1 (Proprietor)
* **Goal:** Review overdue accounts, send reminders, log bank NEFT receipts, and allocate against open invoices.
* **Trigger:** Routine receivables review or incoming bank credit alert.

| Step | Screen / Touchpoint | User Action & Inputs | Underlying Question | Emotion | Identified Friction & Residual Delta | Trust & Delight Moments |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **1. Aging Review** | Receivables Aging | Filters outstanding balances by overdue buckets. | *"Which accounts have the highest overdue exposure?"* | 😰 ANXIOUS | Receivables aging table provides bucketed balances. **Residual Gap:** Direct 1-click drilldown into individual overdue bills. | **Trust:** Clear risk categorization of debtors. |
| **2. Customer Statement** | Party Ledger Statement | Generates customer ledger statement. | *"Is the balance clean? Are there unallocated credits?"* | 😊 CONFIDENT | Derived ledger displays running balance clearly. | **Trust:** Real-time ledger balance without batch job lag. |
| **3. Payment Reminder** | WhatsApp Share | Shares PDF statement with embedded payment link. | *"Will customer understand the statement?"* | 🤩 DELIGHT | Direct WhatsApp sharing with personalized message template. | **Delight:** Instant sharing of professional billing statement. |
| **4. Customer Receipt Entry** | Receipts (`/sales/receipts`) | Enters receipt amount, payment mode, and bank UTR. | *"Which invoices does this payment clear?"* | 😊 CONFIDENT | `ReceiptsPage.tsx` handles receipt creation with UTR and bank allocation. | **Trust:** Bank balance and cash register updated accurately. |
| **5. Invoice Allocation** | Allocation Step | Matches payment against open invoices. | *"Will this apply to oldest debts automatically?"* | 😊 CONFIDENT | `allocateOldest` exists on `ReceiptsPage.tsx`. **Residual Gap:** Make oldest-first allocation the default checked option rather than requiring manual activation. | **Delight:** Open invoices cleared in FIFO order down to the exact rupee. |

---

### Workflow 6: Period Close & CA Statutory Handshake
* **Archetype:** Cross-Archetype (P1 Proprietor, P5 Munshi, P6 External CA)
* **Goal:** Reconcile outward sales (GSTR-1), verify inward ITC against GSTR-2B, confirm Trial Balance equilibrium, export CA audit bundle.
* **Trigger:** Monthly statutory filing deadline (11th / 20th).

| Step | Screen / Touchpoint | User Action & Inputs | Underlying Question | Emotion | Identified Friction & Residual Delta | Trust & Delight Moments |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **1. Pre-Close Audit** | Tax Overview | Reviews outward sales and verifies missing HSN/GSTIN. | *"Are any B2B invoices missing GSTIN or HSN?"* | 😰 ANXIOUS | GSTR-1 worksheets highlight errors. **Residual Gap:** Dedicated pre-filing validation card with direct fix links. | **Trust:** Clear summary of taxable turnover and tax liability. |
| **2. GSTR-1 Sales Report** | GSTR-1 (`/reports/gstr1`) | Validates Table 4 (B2B), Table 7 (B2CS), Table 12 (HSN). | *"Does turnover match Sales Register exactly?"* | 🤩 DELIGHT | GSTR-1 worksheet lines map directly to GST portal tables. | **Delight:** Exact reconciliation with zero tax discrepancies. |
| **3. Inward ITC Reconciliation** | Purchase Register & 2B | Cross-checks Inward Tax against supplier uploads. | *"Are all supplier bills reflected in GSTR-2B?"* | 😊 CONFIDENT | `Gstr2bIngest` and matching engine in `backend/reporting/` already match invoices. | **Trust:** High confidence in eligible ITC claims. |
| **4. Trial Balance Export** | Trial Balance (`/reports/trial-balance`) | Verifies Total Debits == Total Credits; exports reports. | *"Can I download all monthly reports in one archive?"* | 😊 CONFIDENT | Trial balance calculates equilibrium. **Residual Gap:** 1-click endpoint bundling GSTR-1, GSTR-3B, Trial Balance, and Registers into a single ZIP. | **Delight:** Green visual indicator confirming balanced books. |

---

## 4. Pain Point Matrix (Audited Against Current Tree)

| ID | Journey Phase | Affected Personas | Root Cause & Code Reality | Real Impact | Engineering Priority |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **PP-01** | POS Item Entry | P2 (Clerk) | Focus-lock effect reclaims focus unconditionally on cart mutation, interrupting clerks manually editing quantity, discount, or batch. | Input focus stolen mid-keystroke; slows down counter clerks when adjusting line items. | **CRITICAL** |
| **PP-02** | POS Session Storage | P2 (Clerk), P1 (Owner) | Held sessions stored in `localStorage` (`pos-sessions`) can be evicted by private mode or storage quota, and need clear arbitration against offline outbox. | Potential draft loss on shared terminal crash or browser storage wipe. | **CRITICAL** |
| **PP-03** | Mobile Viewport | P3 (Sales Rep) | On viewports < 600px, opening virtual numeric keyboard pushes bottom action buttons offscreen. | Field sales reps must manually collapse keyboard after each field to see totals and save. | **HIGH** |
| **PP-04** | Inward Intake | P4 (Godown), P5 (Munshi) | Lack of smart keyboard date parser requires typing full `DD/MM/YYYY` strings across dozens of batch rows. | Significant clerical fatigue; risk of mis-typing expiry year and corrupting FEFO dispatch logic. | **HIGH** |
| **PP-05** | Receipt Allocation | P5 (Munshi), P1 (Owner) | `allocateOldest` exists on `ReceiptsPage.tsx` but is not enabled by default, leaving some receipts as unallocated advances. | Unallocated receipts float on customer accounts, causing confusion during balance reviews. | **HIGH** |
| **PP-06** | Stock Transfers | P4 (Godown), P1 (Owner) | `StockTransfer.Status` is strictly `DRAFT`, `COMPLETED`, `CANCELLED`; no `IN_TRANSIT` state or receiving variance accounting. | Damaged items in transit cannot be written off to shrinkage directly during transfer receipt. | **HIGH** |
| **PP-07** | Invoice Header | P2 (Clerk), P3 (Sales) | GSTIN format regex runs at document save rather than on field blur in the editor. | Typographical errors in customer GSTIN discovered late in the billing flow. | **MEDIUM** |
| **PP-08** | Inward Duplicate Check | P4 (Godown), P5 (Munshi) | Duplicate `supplier_bill_number` check is enforced at complete in `services.py` rather than on input blur. | Operator discovers duplicate purchase bill only after entering multiple line items. | **MEDIUM** |
| **PP-09** | CA Period Close | P6 (CA), P5 (Munshi) | Monthly statutory reports (GSTR-1, GSTR-3B, Trial Balance, Registers) must be downloaded individually. | CA must download multiple separate files for monthly audit preparation. | **MEDIUM** |
| **PP-10** | Thermal Printing | P2 (Clerk) | POS lacks a dedicated shortcut key to trigger thermal reprint of the last bill without leaving `/pos`. | Counter operator must navigate away to sales invoices list if thermal receipt paper runs out. | **LOW** |

---

## 5. Emotional Journey Analysis

```
OPERATIONAL EMOTIONAL CURVE ACROSS KEY WORKFLOWS

High Delight  +5 |                                (Atomic Complete / Thermal Cut)
                 |                                      ▲
                 |         (Fast Barcode Scan)         / \
Neutral        0 |─────────────▲──────────────────────/───\───────────▲─────────────
                 |            / \                    /     \         / \  (Oldest-First Match)
                 |           /   \  (Focus Stolen)  /       \       /   \
                 |          /     ▼                /         ▼     /     ▼
High Anxiety  -5 |         /     (Batch Prompt)   /     (Credit Block)  (Unallocated Advance)
                 +──────────────────────────────────────────────────────────────────
                   TRIGGER   INPUT   SELECTION   PAYMENT   ALLOCATION  CLOSE
```

### 1. High Anxiety Peaks & Mitigation
- **The Counter Bottleneck (P2):** Anxiety occurs when an input freezes or focus is stolen while customers are queuing. *Mitigation:* Ensure focus lock triggers only on barcode scan additions, never while editing line fields.
- **The Remote Credit Block (P3):** Anxiety occurs when a field representative cannot book an order due to an unexpected credit lock. *Mitigation:* Clear inline credit utilization visibility and structured owner approval workflow.
- **The Month-End Discrepancy (P1 & P5):** Anxiety occurs when Trial Balance does not square before tax deadlines. *Mitigation:* Derived ledger architecture guarantees real-time equilibrium; pre-filing audit card flags missing HSN/GSTIN.

### 2. Cognitive Load Spikes
- **Batch Expiry Shorthand:** Relieve mental fatigue by supporting unambiguous numeric date inputs (`MMYY` / `MMYYYY`).
- **Receipt Allocation:** Eliminate manual math by defaulting to oldest-first invoice allocation.

### 3. Trust-Building Anchors
- **Atomic Posting:** Immediate, synchronous updates to stock and balances upon document completion.
- **Live Currency Subtotals:** Tax-inclusive and tax-exclusive figures formatted via standard currency utilities.

---

## 6. Drop-off & Friction Analysis (Hypothesized Bottlenecks)

*Note: The following metrics represent hypothesized operational friction points to be tracked via instrumentation:*

1. **POS Counter Abandonment:** Hypothesized to occur during peak rush hours due to focus disruption or modal interrupts.
2. **Mobile Order Drop-off:** Hypothesized to occur when virtual keyboards obscure save actions or when unannounced credit limits block completion.
3. **Purchase Intake Postponement:** Purchase bills left in draft status due to tedious date formatting across multi-line invoices.
4. **Unallocated Advance Accumulation:** Occurs when receipt allocations are treated as a secondary manual step rather than defaulted at payment entry.

---

## 7. Opportunity Map (Service Design Blueprint)

```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|                                        SERVICE DESIGN BLUEPRINT                                             |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| FRONTLINE         • Barcode scanner focus lock        • Dynamic UPI QR on terminal  • WhatsApp invoice share|
| TOUCHPOINTS       • Session hold/cycle (F8 / F9)      • Real-time credit chip       • Dedicated reprint key |
+───────────────────┼───────────────────────────────────┼─────────────────────────────┼───────────────────────+
| BACKSTAGE         • Keyboard shortcuts (F1/F4/F5/F7)  • Field sales mobile PWA      • Default oldest-first  |
| PROCESSES         • Smart date parser (MMYY shorthand)• Owner credit override flow  • Early blur validators |
+───────────────────┼───────────────────────────────────┼─────────────────────────────┼───────────────────────+
| SYSTEM ENGINES    • deviceDraft.ts (session drafts)   • Atomic posting engine       • Derived ledger engine |
| & INVARIANTS      • invoiceDraftCache.ts (outbox)     • Gstr2bIngest & 2B matcher   • auto_round_off helper |
+───────────────────┼───────────────────────────────────┼─────────────────────────────┼───────────────────────+
| STRATEGIC VALUE   1. Zero counter focus drop.         1. Secure field credit flow.  1. Zero unallocated cash|
|                   2. Durable multi-cart recovery.     2. Traceable transit variance.2. Rapid CA month-close.|
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```

---

## 8. Target UX Metrics & Discovery Hypotheses

*All metrics are design hypotheses and target benchmarks for validation, not hard release gates:*

| Workflow | Target Metric | Baseline Status | Target UX Hypothesis | Instrumentation Plan |
| :--- | :--- | :--- | :--- | :--- |
| **Counter POS** | Checkout Duration | *Not instrumented* | ≤ 15s per walk-in transaction | Measure timestamp from first scan to thermal print event. |
| **Counter POS** | Keystroke Ergonomics | *Not instrumented* | < 5% mouse interventions on desktop | Telemetry tracking mouse click events vs keydown events in `/pos`. |
| **POS Durability** | Draft Recovery Rate | *Not instrumented* | 100% recovery of held sessions on reload | Track session rehydration events from `deviceDraft.ts`. |
| **Mobile Orders** | Draft-to-Order Conversion | *Not instrumented* | ≥ 95% completion rate | Telemetry logging mobile order init vs completion events. |
| **Inward Intake** | Line Entry Velocity | *Not instrumented* | ≤ 6s per batch-tracked line | Timestamp delta between consecutive line additions in purchase editor. |
| **Collections** | Unallocated Receipt Ratio | *Not instrumented* | ≤ 3% of total receipt INR volume | Query ratio of unallocated receipt balance to total receipts. |
| **Statutory Close** | CA Pack Export Velocity | *Not instrumented* | ≤ 30s for complete monthly bundle | API execution time for bundled audit pack generation. |

---

## 9. Grounded Engineering Delta & Implementation Plan

### 9.1 Architectural Guardrails & Invariants

1. **Derived Ledger Invariant:** Customer and supplier balances are computed dynamically from completed documents and payment allocations. No balance tables exist; no direct mutations to ledgers are permitted.
2. **Atomic Inward & Outward Posting:** `PurchaseInvoice` → `Complete` and `PosPage` → `Complete` atomically mutate stock (`StockMovement`) and accounts payable/receivable in a single database transaction.
3. **Draft Isolation & User Scope:** Local device drafts (`web/src/lib/deviceDraft.ts`) are scoped strictly to `companyId: number` and `userId: number` with a 36-hour TTL. Drafts are uncommitted working memory, separate from the offline outbox.
4. **i18n Parity:** Every user-facing string added to `web/src/i18n/en.ts` must have an exact mirror in `web/src/i18n/hi.ts`, enforced by `web/src/i18n/fullParity.test.ts`.
5. **Currency & Number Formatting:** Currency must be formatted via existing localization helpers (`formatCurrency`), never raw string interpolation.

---

### 9.2 Reconciled Release & PR Sequencing

```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|                                        RECONCILED PR DEPENDENCY GRAPH                                       |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|  SPRINT 1: Ergonomics & POS Durability                                                                      |
|  ┌────────────────────────────────────────────────────────┐                                                 |
|  │ PR-1: POS Focus Guard & Thermal Quick-Reprint Shortcut │                                                 |
|  │ (web/src/pages/pos/PosPage.tsx)                        │                                                 |
|  └────────────────────────────────────────────────────────┘                                                 |
|               │                                                                                             |
|               ▼                                                                                             |
|  ┌────────────────────────────────────────────────────────┐                                                 |
|  │ PR-2: Device Draft Durability & Outbox Reconciliation  │                                                 |
|  │ (web/src/lib/deviceDraft.ts & PosPage session mount)   │                                                 |
|  └────────────────────────────────────────────────────────┘                                                 |
|                                                                                                             |
|  SPRINT 2: Mobile Viewport & Inward Acceleration                                                            |
|  ┌────────────────────────────────────────────────────────┐      ┌────────────────────────────────────────┐ |
|  │ PR-3: Mobile Editor Action Dock & Viewport Guard       │      │ PR-4: Smart Expiry Date Parser & Early │ |
|  │ (web/src/components/billing/DocumentEditorShell.tsx)   │      │ Duplicate Purchase Bill Check          │ |
|  └────────────────────────────────────────────────────────┘      └────────────────────────────────────────┘ |
|                                                                                                             |
|  SPRINT 3: Trade Allocations & Statutory Close                                                              |
|  ┌────────────────────────────────────────────────────────┐      ┌────────────────────────────────────────┐ |
|  │ PR-5: Default Oldest-First Receipt Allocation          │      │ PR-6: CA One-Click Audit Pack Bundler  │ |
|  │ (web/src/pages/sales/ReceiptsPage.tsx)                 │      │ (backend/reporting/ & reports views)   │ |
|  └────────────────────────────────────────────────────────┘      └────────────────────────────────────────┘ |
|                                                                                                             |
|  SPRINT 4: Stock Movement Architecture (Ledger & Inventory)                                                 |
|  ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐ |
|  │ PR-7: Stock Transfer In-Transit State & Transit Variance/Shrinkage Accounting                          │ |
|  │ (backend/inventory/models.py, services.py, views.py & StockTransfer UI)                               │ |
|  └────────────────────────────────────────────────────────────────────────────────────────────────────────┘ |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```

---

### 9.3 Technical Specifications by Pull Request

---

#### PR-1: POS Focus Guard & Thermal Quick-Reprint Shortcut
*Addresses: PP-01, PP-10*  
*Target Files:*  
- `web/src/pages/pos/PosPage.tsx`
- `web/src/pages/pos/PosPage.keyboard.test.tsx`
- `web/src/i18n/en.ts` & `web/src/i18n/hi.ts`

**Context & Audit Finding:**  
`PosPage.tsx` already uses `choosePosEnter` from `posEnter.ts` and handles `F2` (focus scanner), `F8` (hold session), `F9` (cycle sessions), `F1` (Cash), `F4` (Card), `F5/F6` (UPI), `F7` (Credit), and `F10` (Clear).  
Two residual gaps exist:
1. Re-focusing the scanner must only occur after a barcode scan addition when the active element is already the scanner or `document.body`. An unconditional effect on `cart.length` steals focus while a clerk is editing quantity, discount, or batch.
2. If a thermal printer jams, the clerk needs a shortcut to reprint the last completed receipt without leaving the counter.

**Implementation Details:**
1. **Targeted Scanner Focus Reclaim:**  
   Replace any broad cart-length watcher with an explicit focus reclaim executed solely within `onProductScanned`:
   ```typescript
   const onProductScanned = (product: PosEnterProduct) => {
     addProductToCart(product);
     // Reclaim focus only if user was not actively typing in an input field
     const active = document.activeElement;
     const isTypingInRow = active && (active.tagName === 'INPUT' || active.tagName === 'SELECT') && active !== searchRef.current;
     if (!isTypingInRow) {
       searchRef.current?.focus();
       searchRef.current?.select();
     }
   };
   ```
2. **Thermal Quick-Reprint Shortcut (`Ctrl+Alt+P` or `F11`):**  
   `F9` is actively used for session cycling (`switchSession`). Assign quick reprint to `F11` (or `Ctrl+Alt+P` if `F11` is intercepted by browser fullscreen):
   ```typescript
   if (e.key === 'F11' || (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'p')) {
     e.preventDefault();
     if (lastCompletedInvoice) {
       void printPosThermalOrWarn(lastCompletedInvoice);
     }
   }
   ```
3. **i18n Hint Update:**  
   Update `pos.subtitle` in `en.ts` and `hi.ts` to document available shortcuts accurately.

**Acceptance Criteria:**
- Typing a quantity in an existing cart row is not interrupted by scanner focus events.
- Pressing `F11` / `Ctrl+Alt+P` invokes `printPosThermalOrWarn` for the last completed bill.
- `F8` continues to hold session; `F9` continues to cycle held sessions.

---

#### PR-2: Device Draft Durability & Outbox Reconciliation
*Addresses: PP-02*  
*Target Files:*  
- `web/src/lib/deviceDraft.ts`
- `web/src/lib/deviceDraft.test.ts`
- `web/src/pages/pos/PosPage.tsx`
- `web/src/auth/AuthContext.tsx`

**Context & Audit Finding:**  
`deviceDraft.ts` already exists and implements `{ version: 1, savedAt: string, payload: T }` keyed by `bizboard:draft:v1:${companyId}:${userId}:${kind}` with numeric IDs and 36-hour TTL.  
The gap is:
1. Reconciling held session drafts (`pos-sessions`) with the offline outbox (`web/src/offline/invoiceDraftCache.ts`).
2. Graceful user-facing warnings when `localStorage` is unavailable or quota is exceeded on shared counter PCs.

**Implementation Details:**
1. **Outbox vs. Draft Conflict Policy:**  
   - An item queued in `invoiceDraftCache.ts` is a *committed transaction awaiting network sync*.
   - A draft in `deviceDraft.ts` is an *uncommitted working cart*.
   - On POS mount, check whether an active draft session ID matches an ID in `invoiceDraftCache`. If so, purge it from `pos-sessions` to prevent double checkout.
2. **Quota & Private Mode Warning:**  
   When `writeDraft` returns `{ ok: false, reason: 'quota' }`, surface a non-intrusive warning chip in the POS header: `"Draft auto-save disabled (storage full or private browsing)"`.
3. **Session Rehydration Integrity:**  
   On session restore, re-fetch current product prices and stock levels. If an item's price has changed since the draft was saved, show an inline alert: `"Item prices updated to current rates"`.

**Acceptance Criteria:**
- Multi-cart sessions rehydrate reliably across browser refresh for the same user.
- Logging out via `AuthContext.tsx` executes `clearForUser(companyId, userId)`.
- Transactions queued in the offline outbox are never duplicated as uncommitted drafts.

---

#### PR-3: Mobile Editor Action Dock & Viewport Guard
*Addresses: PP-03*  
*Target Files:*  
- `web/src/components/billing/DocumentEditorShell.tsx`
- `web/src/components/billing/DocumentEditorBottomDock.tsx` (New component)
- `web/src/pages/sales/NewInvoicePage.tsx`
- `web/src/i18n/en.ts` & `web/src/i18n/hi.ts`

**Context & Audit Finding:**  
`DocumentEditorShell.tsx` houses standard document actions. On mobile screens (< 600px), opening the soft keyboard pushes bottom save controls offscreen.

**Implementation Details:**
1. **Responsive Bottom Dock Component:**  
   Create `DocumentEditorBottomDock.tsx` utilizing `env(safe-area-inset-bottom)`.
   - Grand total and tax rendered via `formatCurrency(amount)`.
   - Action buttons translated via `useTranslation`: `t('common.saveDraft')`, `t('common.complete')`.
   - Below 600px, retain the primary button in the header row as well, ensuring accessibility if soft keyboards obscure viewport bottoms.
2. **Visual Viewport Resize Handler:**  
   Listen to `window.visualViewport?.addEventListener('resize', ...)` to smoothly scroll active inputs into view when the virtual keyboard opens.
3. **Structured Field Credit Escalation:**  
   When order total exceeds customer credit limit, render credit warning chip. If remote approval is requested, generate an authenticated escalation request token via `POST /api/v1/sales/orders/request-credit-override/` with role check, expiry (15 mins), and audit row.

**Acceptance Criteria:**
- On 375px mobile viewport, invoice total and save action remain visible.
- All copy uses existing i18n keys and passes `fullParity.test.ts`.

---

#### PR-4: Smart Expiry Date Parser & Early Duplicate Bill Check
*Addresses: PP-04, PP-08*  
*Target Files:*  
- `web/src/lib/smartDateParser.ts` (New utility)
- `web/src/lib/smartDateParser.test.ts` (New test suite)
- `web/src/pages/purchases/NewPurchasePage.tsx`

**Context & Audit Finding:**  
Clerks entering 40+ batch rows suffer fatigue typing `DD/MM/YYYY`. Additionally, duplicate purchase bills are currently rejected only at final complete in `backend/purchases/services.py`.

**Implementation Details:**
1. **Strict Date Grammar Parser:**  
   Support unambiguous date shorthand:
   - `MMYY` (4 digits, e.g., `0828` → August 2028, resolves to last day of month `2028-08-31`).
   - `MMYYYY` (6 digits, e.g., `082028` → `2028-08-31`).
   - `DDMMYYYY` (8 digits, e.g., `15082028` → `2028-08-15`).
   - Reject ambiguous inputs (e.g., bare single digits).
   - Reject dates in the past for expiry fields with user feedback: `"Expiry date cannot be in the past"`.
   - Render a visual confirmation pill beside the input: `0828 → Aug 31, 2028`.
2. **Early Duplicate Bill Number Check:**  
   On blur of the `supplier_bill_number` field in `NewPurchasePage.tsx`, trigger a debounced query: `GET /api/v1/purchases/check-duplicate-bill/?supplier_id=...&bill_number=...`. Flag duplicates immediately before the user inputs line items.

**Acceptance Criteria:**
- Typing `0828` automatically expands to `31/08/2028` with preview.
- Past dates are rejected with validation error.
- Existing duplicate supplier bills trigger an amber warning immediately on bill number field blur.

---

#### PR-5: Default Oldest-First Receipt Allocation
*Addresses: PP-05*  
*Target Files:*  
- `web/src/pages/sales/ReceiptsPage.tsx`
- `web/src/pages/sales/ReceiptsPage.test.tsx`

**Context & Audit Finding:**  
`ReceiptsPage.tsx` already contains `allocateOldest: oldestFirst || undefined` calling `createReceipt`. However, `oldestFirst` is not enabled by default, leading to unallocated customer balances.

**Implementation Details:**
1. **Default State Update:**  
   In `ReceiptsPage.tsx`, initialize `oldestFirst` state to `true` by default when a customer with open invoices is selected.
2. **Allocation Breakdown Preview:**  
   Show an inline preview of which invoices will be cleared by the entered receipt amount:
   `"Will settle Inv #104 (₹12,000) in full and Inv #108 (₹8,000) partially."`
3. **Explicit Opt-out:**  
   Allow the bookkeeper to uncheck "Apply to oldest invoices first" if they explicitly intend to log an unallocated customer advance.

**Acceptance Criteria:**
- Creating a customer receipt defaults to oldest-first allocation.
- Invoices are settled in chronological order down to the exact rupee.
- Fully allocated receipts show no residual unallocated advance.

---

#### PR-6: CA One-Click Audit Pack Bundler
*Addresses: PP-09*  
*Target Files:*  
- `backend/reporting/views.py`
- `backend/reporting/urls.py`
- `web/src/pages/reports/TaxReportsPage.tsx`

**Context & Audit Finding:**  
GSTR-1, GSTR-3B worksheets, Sales Registers, and Trial Balance calculations already exist. The CA currently has to navigate to multiple screens and download files individually.

**Implementation Details:**
1. **Backend ZIP Stream Endpoint:**  
   Implement `GET /api/v1/reporting/audit-pack/?period=YYYY-MM`.  
   Streams an in-memory ZIP archive containing:
   - `GSTR1_Worksheet_{period}.xlsx`
   - `GSTR3B_Worksheet_{period}.xlsx`
   - `Trial_Balance_{period}.xlsx`
   - `Sales_Register_{period}.xlsx`
   - `Purchase_Register_{period}.xlsx`
2. **Permissions:** Restrict endpoint to `OWNER`, `ACCOUNTANT`, and external `AUDITOR` roles.
3. **Frontend Action:** Add a primary button on the Tax Reports page: `"Download Complete Monthly CA Pack (ZIP)"`.

**Acceptance Criteria:**
- Single click downloads a verified ZIP archive containing all 5 statutory sheets.
- Period lock and role permissions enforced.

---

#### PR-7: Stock Transfer In-Transit State & Transit Variance/Shrinkage Accounting
*Addresses: PP-06*  
*Target Files:*  
- `backend/inventory/models.py`
- `backend/inventory/services.py`
- `backend/inventory/views.py`
- `web/src/pages/inventory/StockTransferPage.tsx`

**Context & Audit Finding:**  
`StockTransfer.Status` is currently `DRAFT`, `COMPLETED`, `CANCELLED`. In multi-godown distribution, shipments physically move via road transport. Items damaged or lost in transit cannot currently be recorded during receipt without rejecting the whole shipment or creating manual journal vouchers.

**Implementation Details:**
1. **Model & State Machine Extension:**  
   Extend `StockTransfer.Status` choices to include `IN_TRANSIT`.
   - `DRAFT` → `IN_TRANSIT`: Stock decrements from source godown and increments a dedicated system virtual godown `In-Transit Goods`.
   - `IN_TRANSIT` → `COMPLETED`: Receiving custodian inputs `received_quantity` and `damaged_quantity` per line (`received_qty + damaged_qty === shipped_qty`).
2. **Atomic Inventory & Ledger Posting:**  
   - `received_quantity` moves from `In-Transit Goods` to destination godown.
   - `damaged_quantity` moves from `In-Transit Goods` to `Shrinkage/Loss Godown` and generates an atomic ledger debit to `InventoryTransitLossExpense` and credit to `InventoryAsset`.
3. **Derived Ledger Compliance:**  
   Maintains the core invariant: derived balances reflect exact completed movements with zero floating discrepancy.

**Acceptance Criteria:**
- Destination custodian can accept 48 units and mark 2 units as damaged.
- Destination godown receives exactly 48 units; financial loss of 2 units is booked to transit shrinkage expense atomically.

---

### 9.4 Storage Conflict Policy: Device Drafts vs. Offline Outbox

```
+─────────────────────────────────────────────────────────────────────────────+
|                     LOCAL STORAGE ARBITRATION RULES                         |
+─────────────────────────────────────────────────────────────────────────────+
| Store               | Scope                 | Purpose                       |
|─────────────────────┼───────────────────────┼───────────────────────────────|
| deviceDraft.ts      | localStorage (36h TTL)| Uncommitted editor/cart drafts|
| invoiceDraftCache.ts| IndexedDB / outbox    | Committed transactions queued |
|                     |                       | for server background sync    |
+─────────────────────┴───────────────────────┴───────────────────────────────+

Arbitration Logic on App Load:
1. invoiceDraftCache (Outbox) takes precedence. The sync worker attempts background sync.
2. PosPage queries deviceDraft.ts for kind 'pos-sessions'.
3. Any session in deviceDraft whose idempotency key or session ID exists in invoiceDraftCache is purged immediately.
4. Uncommitted held sessions are restored; prices and stock are re-validated via API.
```

---

### 9.5 Verification & Automated Test Strategy

All unit and integration tests run under **Vitest** (web) and **Django Test Runner** (backend). End-to-end tests run under **Playwright**.

```
+─────────────────────────────────────────────────────────────────────────────+
|                             VERIFICATION PIPELINE                           |
+─────────────────────────────────────────────────────────────────────────────+
|  1. Vitest Unit     : smartDateParser.test.ts, deviceDraft.test.ts          |
|  2. i18n Audit       : fullParity.test.ts (100% key match in en.ts & hi.ts) |
|  3. DRF Integration : test_fifo_allocation.py, test_transfer_variance.py   |
|  4. Playwright E2E   : pos-keyboard-flow.spec.ts, mobile-editor.spec.ts     |
+─────────────────────────────────────────────────────────────────────────────+
```

1. **POS Keyboard & Focus Test (`web/src/pages/pos/PosPage.keyboard.test.tsx`):**  
   Assert that dispatching `F2` focuses search input; assert that editing quantity in a line row does not trigger focus theft.
2. **Date Parser Test (`web/src/lib/smartDateParser.test.ts`):**  
   Test cases covering `0828`, `082028`, `15082028`, invalid strings, and rejection of past expiry dates.
3. **Outbox Coexistence Test:**  
   Seed `invoiceDraftCache` with a queued checkout and `deviceDraft` with a held session. Verify that reload does not duplicate or corrupt either store.

---

### 9.6 Rollback Strategy & Risk Governance

| Component | Risk | Rollback Mechanism |
| :--- | :--- | :--- |
| **PR-1 (POS Hotkeys)** | Shortcut conflict on client hardware | Standard Git revert of PR-1. No database migrations involved. |
| **PR-2 (Device Drafts)** | Storage quota exhaustion on legacy terminals | `deviceDraft.ts` catches quota errors and falls back to in-memory sessions without crashing UI. |
| **PR-5 (Default Allocation)** | Operator prefers unallocated advance | Operator unchecks "Apply to oldest invoices first" toggle in UI. |
| **PR-7 (Transfer Variance)** | Ledger discrepancy on partial receipt | DB migration includes backward-compatible status choices; rollback reverts backend PR without data loss. |

---

### 9.7 Engineering Timeline & Resourcing

```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|                                         IMPLEMENTATION TIMELINE                                            |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| Track / Milestone           Days 1–3                Days 4–7                Days 8–12                       |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
| SPRINT 1: POS & Durability  PR-1 Focus & Reprint    PR-2 Draft/Outbox Sync  Vitest & E2E Validation         |
| SPRINT 2: Mobile & Inward   PR-3 Mobile Dock        PR-4 Smart Date Parser  Early Duplicate Bill Check      |
| SPRINT 3: Allocations & CA  PR-5 Default FIFO Alloc PR-6 CA ZIP Bundler     CA User Acceptance Testing      |
| SPRINT 4: Stock Movement    PR-7 Models & Services  PR-7 Transfer UI        Transit Ledger Reconciliation   |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
```

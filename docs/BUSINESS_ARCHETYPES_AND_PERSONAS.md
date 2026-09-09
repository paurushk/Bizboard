# Bizboard: Business Archetype Discovery, Persona Validation & Strategic Roadmap Framework

**Document Version:** 3.2 (Canonical Validation Framework)  
**Status:** Framework for Real-User Validation — aligned to FREEZE_SCOPE.md Scope revision 2026-09-09b (freeze pending ratification)  
**Date:** 2026-09-09  
**Scope:** Canonical reference defining the market discovery methodology, business archetype hypotheses, human personas, buying roles, operational journeys, multi-dimensional readiness, commercial attractiveness, and experimental validation sequence.

> **v3.2 change log (2026-09-09b):** PO scope call on the D6–D14 tranche. **Retained in the frozen build: D9b (per-unit cess), D12 (Capacitor Android shell ships to pilot), D13 (automated right-to-erasure), D14 (LLM bill-extraction hardening).** Demoted to KNOWN LIMITATIONS: D6, D7, D8, D9, D10, D11. Net effect on this document vs v3.1: landed cost / Bill-of-Entry reverts to **out of scope** (Invariant 3, §8); RCM reverts to a **pilot limitation** (ARCH-07 §3); composition (ARCH-02) stays commercially deprioritized. D12 and D13 are cross-cutting delivery / compliance items and change no archetype disposition.
> **v3.1 change log (2026-09-09):** Re-synced with FREEZE_SCOPE.md decisions D6–D14 *(D6–D14 scope superseded in part by v3.2)*. GRN invariant reworded to "not required in the frozen path" (Invariant 1). ARCH-02 reclassified from "disqualified" to "serviceable but commercially deprioritized" (§8). Workflow Readiness downgraded to "in progress — Freeze Gate Phase 2" (§9). ARCH-03 dunning claim corrected to "cadence engine; share-link delivery only" (§8, §13). Added an e-invoice / e-way guardrail to the ARCH-03 pilot and a turnover check to recruiting (§13). Added an INCONCLUSIVE band to the validation hypotheses and split H-04 into FEFO-order (H-04a) vs expiry-block (H-04b) (§11). Flagged ARCH-07's absence from the validation sequence and added an aggregate-timeline note (§12). Replaced LaTeX arrows/symbols with plain text throughout.

---

## Executive Principle: Freeze the Framework, Not the Conclusion

> **"Do not let current code readiness decide the target market. Let code readiness determine where you can cheaply run the experiment; let real-world evidence determine where you should build the business."**

This framework enforces a disciplined progression:
**DISCOVER → FIT → TEST → PROVE → SELECT**

To prevent premature assumptions from hardening into false "facts," this document strictly maintains three epistemic tiers:
1. **Market Archetype:** An observed real-world business operating pattern independent of Bizboard.
2. **Bizboard Archetype Hypothesis:** A testable proposition that a viable population of such businesses exists whose workflows map to Bizboard’s architecture.
3. **Validated Bizboard Segment:** A customer cohort whose operational viability, adoption, retention, and willingness to pay have been repeatedly demonstrated through production usage.

---

## Table of Contents
1. [Architectural Baseline & Frozen Invariants](#1-architectural-baseline--frozen-invariants)
2. [Multi-Dimensional Business Characteristics Framework](#2-multi-dimensional-business-characteristics-framework)
3. [Business Archetype Hypotheses (Customer Segments)](#3-business-archetype-hypotheses-customer-segments)
4. [Real-Human User Personas & Role Consolidation](#4-real-human-user-personas--role-consolidation)
5. [Buyer / User / Influencer Decision-Making Model](#5-buyer--user--influencer-decision-making-model)
6. [Archetype × Persona Interaction & Staffing Matrix](#6-archetype--persona-interaction--staffing-matrix)
7. [Operational Journeys & The Complete Business Loop](#7-operational-journeys--the-complete-business-loop)
8. [Current Product Capability Fit (Supported / Conditional / Out of Scope / Deprioritized)](#8-current-product-capability-fit-supported--conditional--out-of-scope--deprioritized)
9. [Multi-Dimensional Product Readiness Assessment](#9-multi-dimensional-product-readiness-assessment)
10. [Commercial Attractiveness Framework](#10-commercial-attractiveness-framework)
11. [Formal Validation Hypotheses & Pass/Fail Thresholds](#11-formal-validation-hypotheses--passfail-thresholds)
12. [Empirical Validation Sequence](#12-empirical-validation-sequence)
13. [Strategic Pilot Selection & Experimental Roadmap](#13-strategic-pilot-selection--experimental-roadmap)

---

## 1. Architectural Baseline & Frozen Invariants

Every archetype hypothesis and workflow in this document is bounded by the code-level invariants recorded in [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md). **The freeze is not yet ratified.** Of the D6–D14 decision tranche, the **Scope revision 2026-09-09b (PO call)** retains only **D9b (per-unit cess), D12 (Capacitor Android shell ships to pilot), D13 (automated right-to-erasure), and D14 (LLM bill-extraction hardening)** in the frozen build; **D6, D7, D8, D9, D10, D11 are demoted to KNOWN LIMITATIONS** (manual workaround stated to pilot users). Execution of the retained scope + the ARCH-03 pilot path is tracked in [`roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md`](roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md). Treat the invariants below as current intent and re-verify against FREEZE_SCOPE before committing validation bandwidth to any single archetype.

1. **Atomic Inward Intake:** In the frozen purchase path, `PurchaseInvoice` → `Complete` increments inventory (`StockMovement`) and accounts payable (`AP`) atomically, with **no required Goods Receipt Note (GRN) or 3-way matching stage**. *(A standalone GRN capability exists in the codebase but is not part of the frozen pilot purchase flow.)*
2. **Derived Ledger Balances:** There are no customer or supplier balance tables. Balances are derived dynamically from completed documents, credit/debit notes, and payment allocations.
3. **Single Legal Entity & Currency:** The core strictly enforces single-currency (INR) and a single primary legal GSTIN per company. Multi-currency foreign-exchange gain/loss **and** landed-cost duty capitalization into inventory cost layers are out of scope for the pilot. *(FREEZE_SCOPE D10 — Bill-of-Entry / import purchase + landed cost — was briefly scoped in on 2026-09-09, then demoted to a KNOWN LIMITATION in the 2026-09-09b revision. A BoE capability exists in code but is not a pilot deliverable. Workaround: enter import purchases as a domestic purchase bill with duty / landed cost as a charge line.)*
4. **Offline Worksheet Statutory Model:** GSTR-1, GSTR-3B, and CMP-08 operate as calculation worksheets and reconciliation aids; live GSP direct portal filing and live NIC e-invoice generation are disabled/flagged off in the pilot profile. Merchants legally required to issue e-invoices / e-way bills generate them in their existing utility and record the returned IRN / EWB number against the Bizboard document via the manual status field (see §13 Guardrail 4).
5. **Dark Modules:** Manufacturing (BOM/work orders), Payroll, and CRM are disabled (`ENABLE_*=0`) in production.

---

## 2. Multi-Dimensional Business Characteristics Framework

To evaluate businesses systematically rather than relying on loose industry labels, each business pattern is examined across two structural layers: **Operational Dimensions** (how the business runs) and **Commercial Dimensions** (how attractive it is as a software customer).

```
+-------------------------------------------------------------------------------------------------------------+
|                                    BUSINESS CHARACTERISTICS TAXONOMY                                        |
+-------------------------------------------------------------------------------------------------------------+
| LAYER 1: OPERATIONAL STRUCTURE                                                                              |
|   1. Operating Model       : Walk-in Counter | Field Sales | Delivery/Dispatch | Project/Direct Service     |
|   2. Transaction Model     : Immediate Cash/UPI | Short-Term Credit | Milestone Billing | Inward Bills      |
|   3. Inventory Complexity  : None/Service | Simple SKU | Multi-Godown | Batch & Expiry (FEFO) | Serial/IMEI |
|   4. Financial Complexity  : Cash Drawer Only | Derived Ledger (AR/AP) | Full Double-Entry GL | TDS/TCS     |
|   5. Organizational Model  : Solo Operator | Consolidated Staff | Multi-Node Departmental Team              |
|   6. Regulatory Complexity : Unregistered | Composition (CMP-08) | Regular GST (B2C/B2B/E-way) | Licensing   |
|   7. Operating Cadence     : High-Frequency Counter | Batch Wholesale | Periodic / Project-Driven           |
+-------------------------------------------------------------------------------------------------------------+
| LAYER 2: COMMERCIAL ATTRACTIVENESS                                                                          |
|   • Pain Intensity         • Frequency of Pain       • Cost of Current Workaround                           |
|   • Software Penetration   • Switching Difficulty    • Willingness to Pay                                   |
|   • Buyer Accessibility    • Competitive Intensity   • Customer Acquisition Difficulty                      |
|   • Retention Potential    • Expansion Potential     • Referral Potential        • Addressable Market Size  |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 3. Business Archetype Hypotheses (Customer Segments)

The following seven customer archetypes represent **working market hypotheses** inferred from observed business patterns in Indian commerce. Note that External CAs / Tax Practitioners are classified separately as [Ecosystem Stakeholders](#4-real-human-user-personas--role-consolidation), not customer business archetypes.

```
+-------------------------------------------------------------------------------------------------------------+
|                                   CUSTOMER BUSINESS ARCHETYPE HYPOTHESES                                    |
+-------------------------------------------------------------------------------------------------------------+
| Retail & Over-the-Counter                                                                                   |
|   ├── ARCH-01: Fast-Paced Counter Retailer (Specialty Retail / Direct Consumer)                             |
|   └── ARCH-02: Small Composition / Neighborhood Merchant (Low-Compliance Retail) [DEPRIORITIZED]           |
+-------------------------------------------------------------------------------------------------------------+
| B2B Distribution & Trade                                                                                    |
|   ├── ARCH-03: Semi-Wholesaler & Trade Merchant (B2B Credit & Tiered Pricing)                               |
|   └── ARCH-04: Multi-Godown Regional Stockist (Hub & Spoke / Distributed Staging)                           |
+-------------------------------------------------------------------------------------------------------------+
| Specialized Inventory Mechanics                                                                             |
|   ├── ARCH-05: Batch & Expiry-Sensitive Stockist (Pharma & Perishable FMCG)                                 |
|   └── ARCH-06: High-Value Serialized Goods Dealer (Electronics, Appliances & Machinery)                     |
+-------------------------------------------------------------------------------------------------------------+
| Commercial Services & Contracting                                                                           |
|   └── ARCH-07: Light Commercial Service & Spares Contractor (Hybrid Service/Trade)                          |
+-------------------------------------------------------------------------------------------------------------+
```

---

### ARCH-01: Fast-Paced Counter Retailer (Specialty Retail / Direct Consumer)
* **Hypothesis:** Standalone specialty retailers (paints, hardware, footwear, sanitaryware, pet supplies) require fast counter checkout without the overhead of heavy desktop ERPs.
* **Operating Model:** Direct walk-in counter; customer waiting physically at the desk.
* **Transaction Model:** Immediate settlement (Cash, UPI, Card); zero customer credit terms.
* **Inventory Complexity:** Single-location stock; barcode/SKU catalog; tax-inclusive pricing; reorder thresholds.
* **Financial Complexity:** Daily till reconciliation; cash/bank account settlement; no accounts receivable.
* **Organizational Complexity:** Consolidated staff (Proprietor + 1–2 billing assistants).
* **Regulatory Complexity:** Regular GST taxpayer issuing B2C retail invoices; daily aggregate sales reporting.
* **Operating Cadence:** Continuous counter traffic throughout business hours.

### ARCH-02: Small Composition / Neighborhood Merchant (Low-Compliance Retail)
* **Hypothesis:** Small kiosks and provision shops want simple billing and flat tax tracking.
* **Strategic Note:** *Deprioritized for pilot validation due to low willingness to pay, high price sensitivity, and minimal software lock-in.*
* **Operating Model:** Immediate counter purchase; informal customer relationships.
* **Transaction Model:** Cash and static UPI QR. Small informal paper slips ("khata") for trusted neighbors.
* **Inventory Complexity:** Basic item catalog; informal replenishment; no batch/serial/godown tracking.
* **Financial Complexity:** Cash-in-hand tracking; no double-entry books; simple supplier payment records.
* **Organizational Complexity:** Solo operator or family-operated.
* **Regulatory Complexity:** GST Composition Scheme (Turnover tax via quarterly CMP-08, no ITC) or Unregistered.

### ARCH-03: Semi-Wholesaler & Trade Merchant (B2B Credit & Tiered Pricing)
* **Hypothesis:** Regional B2B traders (electrical hardware, building supplies, packaging, auto spares) suffer primary operational pain around credit tracking, price slabs, delivery challans, and receivables aging.
* **Operating Model:** Orders received via phone, WhatsApp, or counter; goods dispatched via transport/tempo.
* **Transaction Model:** 15–45 day credit cycles; partial payment allocations; volume slab discounts; payment links.
* **Inventory Complexity:** High SKU count; wholesale vs. retail price lists; delivery challans before billing.
* **Financial Complexity:** Customer credit limits; aging receivables; TDS (194Q) / TCS (206C); supplier payables.
* **Organizational Complexity:** Distinct commercial functions (Owner, Sales Booker, In-house Accountant).
* **Regulatory Complexity:** Regular GST; B2B invoices with recipient GSTIN validation; E-way bills; HSN reporting.
* **Operating Cadence:** 10–50 high-value multi-item transactions per day.

### ARCH-04: Multi-Godown Regional Stockist (Hub & Spoke Inventory)
* **Hypothesis:** Stockists operating a central showroom with peripheral storage locations suffer severe shrinkage and fulfillment errors without inter-godown transfer tracking.
* **Operating Model:** Central office billing; dispatches staged and fulfilled from peripheral warehouses.
* **Transaction Model:** Mixed B2B credit terms and large bulk cash transactions.
* **Inventory Complexity:** Inter-godown transfers (`StockTransfer`); location-specific reorder levels; physical inventory count variance audits (`StockCountSession`).
* **Financial Complexity:** Centralized AR/AP; location-tagged delivery challans; inventory cost valuations.
* **Organizational Complexity:** Geographically distributed staff (Counter Clerks, Godown Keepers, Central Manager).
* **Regulatory Complexity:** Single GSTIN with multi-premises declarations; transport movement documentation.
* **Operating Cadence:** Continuous dispatches and regular stock transfers.

### ARCH-05: Batch & Expiry-Sensitive Stockist (Pharma & Perishable FMCG)
* **Hypothesis:** Wholesale distributors of pharmaceuticals, packaged food products, or agro-chemicals require strict lot traceability to avoid dispatching expired stock and incurring regulatory penalties.
* **Operating Model:** Inward intake by manufacturer lot; outward fulfillment to retail pharmacies/shops.
* **Transaction Model:** Trade credit with strict return allowances for expired/damaged goods.
* **Inventory Complexity:** Mandatory Batch Number, Manufacturing Date, and Expiry Date on every inward movement; First-Expiry-First-Out (FEFO) picking; automated expiry alert bands; blocking of expired stock.
* **Financial Complexity:** Credit notes tied to physical returns with explicit condition tagging (Sellable vs. Damaged).
* **Organizational Complexity:** Dedicated warehouse handlers accountable for stock loss and shrinkage.
* **Regulatory Complexity:** Stringent statutory licensing (Drug Licenses 20B/21B, FSSAI declarations); batch-traceable GST invoices.
* **Operating Cadence:** Fast inventory turnover; high sensitivity to shelf-life.

### ARCH-06: High-Value Serialized Goods Dealer (Electronics, Appliances & Machinery)
* **Hypothesis:** Commercial dealers of consumer electronics, power tools, water purifiers, or machinery face high financial leakage from warranty fraud and duplicate returns without individual unit tracking.
* **Operating Model:** Walk-in retail showroom combined with institutional/corporate supply.
* **Transaction Model:** Immediate point-of-sale settlement or institutional payment terms; warranty-backed sales.
* **Inventory Complexity:** Individual unit tracking via unique Serial / IMEI numbers; serial history lifecycle (`AVAILABLE` → `SOLD` → `RETURNED`); serial validation during returns.
* **Financial Complexity:** High ticket value; hire-purchase/finance tagging; vendor warranty debit notes.
* **Organizational Complexity:** Technicians/handlers logging individual serial strings during inwarding and dispatch.
* **Regulatory Complexity:** Standard GST with high-value e-invoice and e-way bill compliance thresholds.
* **Operating Cadence:** Moderate transaction count; zero tolerance for serial mismatches.

### ARCH-07: Light Commercial Service & Spares Contractor (Hybrid Service/Trade)
* **Hypothesis:** Maintenance agencies (HVAC, commercial repair, IT networking) struggle with systems that only handle pure inventory or pure service billing.
* **Operating Model:** Job-work, preventive maintenance contracts, on-site service calls.
* **Transaction Model:** Service contracts, milestone invoicing, recurring monthly retainers, payment links.
* **Inventory Complexity:** Minimal stock holding; consumables and replacement spare parts (goods vs. services).
* **Financial Complexity:** Mixed SAC (Service) and HSN (Goods) billing; TDS withholding under Section 194C/194J on collections.
* **Organizational Complexity:** Principal handling client relations, field technicians performing work.
* **Regulatory Complexity:** Regular GST with Place of Supply defined by service performance location; reverse charge (RCM) is common on inbound freight/GTA, legal, and security services — RCM is a **known pilot limitation** (D8 deferred 2026-09-09b): merchants with material RCM exposure are screened out, or record the RCM self-invoice + ITC manually.
* **Operating Cadence:** Low daily transaction volume; periodic project/retainer billing cycles.

---

## 4. Real-Human User Personas & Role Consolidation

Personas represent real human contexts, stress points, and cognitive burdens. Duties are heavily consolidated in Indian MSMEs:

```
+-------------------------------------------------------------------------------------------------------------+
|                                        REAL-HUMAN USER PERSONAS                                             |
+-------------------------------------------------------------------------------------------------------------+
| Customer Personas                                                                                           |
|   • P1: The Managing Proprietor ("The Commercial Anchor / Sethji")                                          |
|   • P2: The Counter Clerk ("The Frontline Billing Operator")                                                |
|   • P3: The Traveling Order Booker ("The Field Sales Representative")                                       |
|   • P4: The Physical Stock Handler ("The Godown Custodian")                                                 |
|   • P5: The Resident Bookkeeper ("The Internal Munshi")                                                     |
+-------------------------------------------------------------------------------------------------------------+
| Ecosystem Stakeholder (Not a Customer Archetype)                                                            |
|   • P6: The External Compliance Consultant ("The Independent CA / Tax Practitioner")                        |
+-------------------------------------------------------------------------------------------------------------+
| Operational Consolidation Models                                                                            |
|   ├── Model A (Solo Operator): P1 performs all roles [Owner + Billing + Stock + Books].                     |
|   ├── Model B (Counter Pair) : P1 (Owner/Admin) + P2 (Billing Assistant).                                   |
|   ├── Model C (Trade Firm)   : P1 (Owner) + P3/P4 (Sales/Dispatch) + P5 (Internal Munshi).                  |
|   └── Model D (Departmental) : Distinct individuals across Counter, Warehouse, Accounts, and External CA.  |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 5. Buyer / User / Influencer Decision-Making Model

Software adoption in small businesses fails when the software caters only to the user while ignoring the buyer, or pleases the buyer while alienating the daily operator.

```
+-------------------------------------------------------------------------------------------------------------+
|                                    DECISION-MAKING & BUYING ROLES MATRIX                                    |
+-------------------------------------------------------------------------------------------------------------+
| Persona                Buying Role            Adoption Motive                    Veto / Blocker Trigger     |
+-------------------------------------------------------------------------------------------------------------+
| P1: Proprietor         Economic Buyer &       Visibility into cash & credit;     High subscription price;   |
|                        Decision Maker         prevents staff theft; peace of mind fear of data loss or lock-in|
|                                                                                                             |
| P2: Counter Clerk      Daily End User         Fast checkout; zero customer line  Complex keystrokes; modal   |
|                                               delays; easy end-of-day till check popups; input latency       |
|                                                                                                             |
| P3: Field Sales Exec   Mobile / Field User    Accurate stock & pricing on go;    Inability to book orders on |
|                                               fast order booking                 spot; hidden credit blocks  |
|                                                                                                             |
| P4: Godown Custodian   Logistics Operator     Simple inwarding; clear batch/     Tedious manual serial typing|
|                                               serial entry; fast count checks    confusing transfer flows    |
|                                                                                                             |
| P5: Resident Munshi    Daily Power User &     Flawless ledger balances; clean    Discrepancy with bank lines;|
|                        Operational Gatekeeper supplier bills; easy allocation    threat to job / familiar UI |
|                                                                                                             |
| P6: External CA        Ecosystem Influencer   Accurate GSTR tax splits; clean    Imbalanced trial balance;   |
|                        & Statutory Gatekeeper Trial Balance; easy Tally export   tampered past-period books  |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 6. Archetype × Persona Interaction & Staffing Matrix

| Business Archetype | Staffing Configuration | Key Personas Involved | Primary Interface Touchpoints | Core Friction Points to Monitor |
| :--- | :--- | :--- | :--- | :--- |
| **ARCH-01: Counter Retailer** | Model B (Counter Pair) | **P1** (Buyer) + **P2** (User) | Counter POS (`/pos`), Barcode Search, Daily Summary | Modal popups, slow print rendering, keyboard focus loss. |
| **ARCH-02: Composition Merchant** | Model A (Solo Operator) | **P1** (Buyer & User) | Bill of Supply Editor, Cash Entry, CMP-08 Sheet | Complex multi-rate tax UI, mandatory GSTIN validations. |
| **ARCH-03: Semi-Wholesale** | Model C (Trade Firm) | **P1** (Buyer) + **P3** (User) + **P5** (User/Gatekeeper) | Quotations, Delivery Challans, Invoices, Allocations | Credit limit bypass, unallocated advances, partial returns. |
| **ARCH-04: Multi-Godown Stockist** | Model D (Departmental) | **P1** (Buyer) + **P4** (User) + **P5** (User) | Stock Transfers, Godown Balances, Count Sessions | In-transit stock discrepancy, warehouse misallocation. |
| **ARCH-05: Batch & Expiry** | Model C or D | **P1** (Buyer) + **P4** (User) + **P5** (User) | Purchase Inward (Batch/Exp), FEFO Outbound, Alerts | Manual expiry entry fatigue, accidental dispatch of expired stock. |
| **ARCH-06: Serialized Dealer** | Model B or C | **P1** (Buyer) + **P2/P4** (User) + **P5** (User) | Serial Number Entry, Warranty Lookup, Returns | Inward bulk serial scanning errors, return serial validation. |
| **ARCH-07: Commercial Services** | Model B or C | **P1** (Buyer/User) + **P5** (User) | Service Invoice Editor, Schedules, Payment Links | SAC vs HSN confusion, TDS deduction logging. |

*Ecosystem Stakeholder **P6 (External CA)** audits outputs across ARCH-01, ARCH-03, ARCH-04, ARCH-05, ARCH-06, and ARCH-07.*

---

## 7. Operational Journeys & The Complete Business Loop

Isolated workflows (e.g., booking an order or scanning an item) are insufficient to validate product-market fit. The software must successfully sustain the **Complete End-to-End Business Loop**.

### The Complete B2B Trade Business Loop (ARCH-03)

```
[Supplier Purchase Bill Entered]
              │
              ▼
[Stock & AP Posted Atomically] ──► [Inventory Available in Godown]
                                                   │
                                                   ▼
                                     [Customer Requests Pricing]
                                                   │
                                                   ▼
                                     [Quotation Drafted with Slabs]
                                                   │
                                                   ▼
                                     [Sales Order Confirmed]
                                                   │
                                                   ▼
                                     [Credit & Overdue Audit Passed]
                                                   │
                                                   ▼
                                     [Delivery Challan Issued & Dispatched]
                                                   │
                                                   ▼
                                     [B2B Tax Invoice Generated]
                                                   │
                                                   ▼
                                     [Derived Customer AR Ledger Increases]
                                                   │
                                                   ▼
                                     [Customer Settles via NEFT/Cheque]
                                                   │
                                                   ▼
                                     [CustomerReceipt Logged with UTR]
                                                   │
                                                   ▼
                                     [Receipt Allocated to Specific Invoices]
                                                   │
                                                   ▼
                                     [Ledger Statement Balanced & Verified]
                                                   │
                                                   ▼
                                     [Period Closed & GSTR-1/3B Worksheets Exported]
```

### The Rapid Point-of-Sale Loop (ARCH-01)

```
[Customer at Counter] ──► [F2: Barcode Scan] ──► [Tax-Inclusive Price Resolved]
                                                              │
                                                              ▼
                                                [Dynamic UPI QR Displayed]
                                                              │
                                                              ▼
                                             [Atomic Single-Action Complete & Settle]
                                             ├─ SalesInvoice Status: COMPLETED
                                             ├─ CustomerReceipt Status: POSTED
                                             ├─ PaymentAllocation: 100% Settled
                                             ├─ StockMovement: SALE (-Qty)
                                             └─ General Ledger: Balanced Journal
                                                              │
                                                              ▼
                                                [Silent Thermal Slip Printed]
```

---

## 8. Current Product Capability Fit (Supported / Conditional / Out of Scope / Deprioritized)

```
+-------------------------------------------------------------------------------------------------------------+
|                                    PRODUCT CAPABILITY FIT CLASSIFICATION                                    |
+-------------------------------------------------------------------------------------------------------------+
| GENUINELY SUPPORTED (Core Match to Code Invariants)                                                         |
|   ├── ARCH-03: Semi-Wholesaler        ── Verified: Quotations, challans, price lists, ledgers, dunning cadence.|
|   ├── ARCH-01: Counter Retailer       ── Verified: Fast POS, barcode lookup, UPI QR, thermal slips.        |
|   └── P6: External CA (Stakeholder)   ── Verified: Balanced TB=0, GSTR worksheets, period locks, audit log. |
+-------------------------------------------------------------------------------------------------------------+
| CONDITIONALLY SUPPORTED (Requires Validation of Specific Boundary Conditions)                               |
|   ├── ARCH-04: Multi-Godown Stockist  ── Boundary: Single GSTIN only; inter-branch transfers are internal.   |
|   ├── ARCH-05: Batch/Expiry Merchant  ── Boundary: General batch/FEFO works; specialized drug forms absent.  |
|   ├── ARCH-06: Serialized Dealer      ── Boundary: Serial flow verified; bulk barcode paste limits apply.    |
|   └── ARCH-07: Commercial Services    ── Boundary: Service items work; no technician dispatch or timesheets. |
+-------------------------------------------------------------------------------------------------------------+
| OUT OF SCOPE — CAPABILITY GAP (Do Not Spend Validation Bandwidth)                                           |
|   ├── High-Speed Supermarkets         ── Unsupported: No weighing scales, pole displays, or cash kickers.   |
|   ├── Discrete Manufacturers          ── Unsupported: Manufacturing module is dark (`ENABLE_MANUFACTURING=0`)|
|   ├── Import-Export / import purchase ── Unsupported for pilot: single-currency INR only; FX gain/loss out. |
|   │                                      BoE + landed-cost capitalization deferred (D10 -> LIM, 2026-09-09b).|
|   └── Multi-State / Multi-GSTIN firms ── Unsupported: One legal company + one primary GSTIN per tenant.     |
|                                          Inter-state IGST sales ARE supported; multi-registration is not.   |
+-------------------------------------------------------------------------------------------------------------+
| SERVICEABLE — COMMERCIALLY DEPRIORITIZED (Not a capability gap; excluded from pilot by choice)              |
|   └── ARCH-02: Small Composition Shop ── Bill of supply + CMP-08 worksheet exist in code (not freeze-gated; |
|                                          D9 -> LIM). Excluded from the pilot for low WTP, high churn, price. |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 9. Multi-Dimensional Product Readiness Assessment

Code completeness is only one component of pilot readiness. A system with complete code can still fail in production due to brittle migration, difficult UX, or accounting rejection.

```
+-------------------------------------------------------------------------------------------------------------+
|                                    MULTI-DIMENSIONAL READINESS FRAMEWORK                                    |
+-------------------------------------------------------------------------------------------------------------+
| Dimension                  Evaluation Question                                     Current Status           |
+-------------------------------------------------------------------------------------------------------------+
| 1. Functional Readiness    Do individual endpoints and state machines pass tests?  VERIFIED (CI green)      |
| 2. Workflow Readiness      Does the complete business loop execute end-to-end?     IN PROGRESS - FG Phase 2 |
| 3. Data Readiness          Can real Excel/CSV masters be cleanly imported?         PROVISIONAL (FG-2e gate) |
| 4. UX Readiness            Can real non-technical staff operate without training? UNTESTED IN PILOT        |
| 5. Reliability             Does it survive network drops and browser restarts?     PARTIAL (offline outbox) |
| 6. Accounting Correctness  Does the derived ledger balance with GL control (TB=0)? VERIFIED (Invariants)    |
| 7. Compliance Confidence   Do practicing CAs accept statutory worksheet outputs?   UNTESTED IN PILOT        |
| 8. Operational Readiness   Can the business run on it daily without manual fixes?  UNTESTED IN PILOT        |
| 9. Commercial Readiness    Will the business renew and pay after the trial?        UNTESTED IN PILOT        |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 10. Commercial Attractiveness Framework

To determine whether Bizboard *should* pursue an archetype (once proven that it *can* serve it), evaluate each archetype across commercial dimensions:

| Commercial Dimension | ARCH-01 (Retail) | ARCH-03 (B2B Trade) | ARCH-04 (Multi-Godown) | ARCH-05 (Batch/Pharma) | ARCH-06 (Serial/Elec) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pain Intensity** | Moderate (speed/tax) | **Extreme** (debt/credit) | High (leakage/transfer) | **Extreme** (expiry loss) | High (warranty fraud) |
| **Frequency of Pain** | Daily (each ticket) | Daily (collections/orders)| Weekly (transfers/counts)| Daily (outbound picking) | Daily (returns/inward) |
| **Current Workaround Cost**| High (lost sales) | **Severe** (bad debts) | Moderate (shrinkage) | **Severe** (write-offs) | Moderate (fraud) |
| **Incumbent Penetration** | Low to Moderate | **High** (Tally/Busy/Vyapar)| High (Busy/Marg/Tally) | Very High (Marg ERP) | Moderate (Tally/Busy) |
| **Switching Difficulty** | Low | Moderate to High | High | Very High | Moderate |
| **Willingness to Pay** | Low to Moderate | **High** | High | **Very High** | High |
| **Buyer Accessibility** | Easy (at counter) | Easy (owner at desk) | Moderate (distributed) | Moderate (stockists) | Easy (showroom) |
| **Retention Potential** | Moderate | **Very High** (data lock) | High | **Very High** | High |
| **Market Size (India)** | Huge (~12M stores) | Large (~3M traders) | Medium (~500k stockists)| Large (~800k pharma/food)| Medium (~600k dealers) |

> **Coverage & sourcing note:** ARCH-02 (commercially deprioritized) and ARCH-07 (secondary exploration, pending milestone-billing / job-work support) are omitted from this comparison by design. The India market-size figures are unverified order-of-magnitude estimates for *relative* prioritization only — not researched TAM values; do not cite them externally.

---

## 11. Formal Validation Hypotheses & Pass/Fail Thresholds

All qualitative assumptions are bound to explicit, testable pass/fail thresholds. A run that lands between the pass and fail bands is recorded as **INCONCLUSIVE** — not a pass — and the experiment is extended (more sessions, larger n) until it resolves one way:

```
+-------------------------------------------------------------------------------------------------------------+
|                                    VALIDATION HYPOTHESES & PASS/FAIL CRITERIA                               |
+-------------------------------------------------------------------------------------------------------------+
| HYPOTHESIS H-01: B2B Ledger Reconciliation Accuracy                                                         |
|   "Derived customer ledgers maintain 100% mathematical consistency with customer statements and resolve     |
|    multi-invoice partial payments without creating orphan balances or confusing the proprietor."           |
|    • Pass Criteria: Zero unexplained balance discrepancies across 100 consecutive payment allocations.      |
|    • Fail Criteria: >= 1 occurrence of corrupted outstanding balances requiring manual database intervention.|
+-------------------------------------------------------------------------------------------------------------+
| HYPOTHESIS H-02: Counter Checkout Usability & Speed                                                         |
|   "A counter clerk can complete a 5-line retail checkout via /pos using only the keyboard and barcode       |
|    scanner within normal retail wait times, without UI focus drops or modal blocking."                      |
|    • Pass Criteria: 90% of checkouts completed in <= 35 seconds without the clerk touching the mouse.       |
|    • Fail Criteria: Clerk reverts to mouse on > 20% of lines due to search focus or popup traps.             |
+-------------------------------------------------------------------------------------------------------------+
| HYPOTHESIS H-03: Offline Outbox Data Integrity                                                              |
|   "The IndexedDB outbox reliably preserves drafted sales during transient internet drops and flushes them   |
|    idempotently upon reconnection without creating duplicate transactions or inventory voids."             |
|    • Pass Criteria: 100% of offline drafts flushed with zero duplicate invoice numbers or double stock hits.|
|    • Fail Criteria: >= 1 lost transaction or duplicate invoice generated post-reconnection.                |
+-------------------------------------------------------------------------------------------------------------+
| HYPOTHESIS H-04a: FEFO Picking Order Enforcement                                                            |
|   "Under automated lot allocation, the system always consumes the earliest-expiry lot first, so handlers    |
|    do not have to reason about shelf life during high-pressure fulfillment cycles."                         |
|    • Pass Criteria: 100% of non-manual lot dispatches consume stock in earliest-expiry-first order.         |
|    • Fail Criteria: >= 1 non-manual dispatch consumes a later-expiry lot while an earlier lot is available. |
+-------------------------------------------------------------------------------------------------------------+
| HYPOTHESIS H-04b: Expired / Near-Expiry Block Policy                                                         |
|   "With the expiry-block policy active, expired (and within-guard-band) stock cannot be completed onto an   |
|    outbound invoice, whether the lot was picked automatically or chosen manually."                          |
|    • Pass Criteria: 100% of attempts to invoice expired stock are rejected while the policy is active.       |
|    • Fail Criteria: >= 1 expired-stock line is successfully completed on an invoice under an active policy.  |
+-------------------------------------------------------------------------------------------------------------+
| HYPOTHESIS H-05: External CA Compliance Acceptance                                                          |
|   "Practicing CAs will accept generated GSTR-1 and GSTR-3B offline calculation worksheets as sufficient to  |
|    execute statutory portal filings without requiring raw ledger recalculations in external software."      |
|    • Pass Criteria: CA files client monthly returns directly from Bizboard worksheets without recalculation.|
|    • Fail Criteria: CA rejects reports due to mismatched tax splits, POS errors, or imbalanced journals.    |
+-------------------------------------------------------------------------------------------------------------+
```

---

## 12. Empirical Validation Sequence

The validation roadmap progresses from isolated operational mechanics to complex trade networks and compliance audits:

```
====================================================================================================
STAGE 1: Isolated Operational & POS Mechanics
         Target Cohort    : ARCH-01 (Single-Counter Specialty Retailers)
         Core Validation  : Single-till checkout speed, barcode ergonomics, thermal slip printing,
                            IndexedDB offline draft outbox resilience.
         Scale & Timing   : 3–5 stores | 2–3 weeks
====================================================================================================
                                      │
                                      ▼
====================================================================================================
STAGE 2: Complete B2B Trade & Credit Cycle
         Target Cohort    : ARCH-03 (Semi-Wholesalers / Small Distributors)
         Core Validation  : The Complete Business Loop (Inward Bill ──► Stock ──► Order ──► Challan
                            ──► Invoice ──► AR Ledger ──► Allocation ──► Month-End).
         Scale & Timing   : 4–6 trading firms | 4 weeks
====================================================================================================
                                      │
                                      ▼
====================================================================================================
STAGE 3: Professional Statutory & Accounting Integrity Audit
         Target Cohort    : P6 (External CAs & Tax Practitioners of Stage 1 & 2 Pilots)
         Core Validation  : GSTR-1 outward tax split, GSTR-3B liability/ITC worksheets,
                            Trial Balance equilibrium (TB=0), period-close tamper resistance.
         Scale & Timing   : 3–5 practicing CAs | 2 weeks (aligned with monthly 1st–20th filing window)
====================================================================================================
                                      │
                                      ▼
====================================================================================================
STAGE 4: Specialized Inventory Mechanics (Multi-Godown, Batch & Serial)
         Target Cohort    : ARCH-04 (Multi-Godown), ARCH-05 (Batch/Pharma), ARCH-06 (Serialized Goods)
         Core Validation  : Inter-godown transfers, physical count variance adjustments,
                            FEFO picking enforcement, individual serial lifecycle tracking.
         Scale & Timing   : 3–5 specialized merchants | 3–4 weeks
====================================================================================================
```

**Not in this sequence — ARCH-07 (Light Commercial Services).** It depends on milestone billing and job-work
features that are outside frozen scope. Revisit as a possible Stage 5 only after Stage 2 confirms the core
trade loop *and* those features are built.

**Aggregate timeline & sequencing.** The four stages run sequentially and sum to roughly **11–15 weeks** of
active fieldwork. Stage 3 additionally needs a fully closed accounting month produced by the Stage 1–2
pilots, so it cannot begin the day Stage 2 fieldwork ends — schedule it against the first clean month-end.

---

## 13. Strategic Pilot Selection & Experimental Roadmap

### Core Strategic Distinction

> **ARCH-03 is the leading pilot hypothesis because it currently has the strongest verified product fit and lowest operational friction; commercial selection remains subject to empirical validation.**

```
                           CODE READINESS vs. OPERATIONAL FRICTION
   100% ┌─────────────────────────────────────────────────────────────┐
        │                                                             │
        │                  [ARCH-03] B2B Semi-Wholesaler              │
        │                  (Leading Pilot Hypothesis)                 │
   C    │                                                             │
   O 80%│       [ARCH-01] Counter Retail                              │
   D    │       (POS edge cases / Hardware friction)                  │
   E    │                                      [ARCH-04] Multi-Godown │
        │                                                             │
   F 60%│                                      [ARCH-05] Batch/Pharma │
   I    │                                                             │
   T    │                                      [ARCH-06] Serialized   │
   % 40%│                                                             │
        │                                                             │
        │  [ARCH-07] Services                                         │
        │                                                             │
     0% └─────────────────────────────────────────────────────────────┘
          HIGH FRICTION ◄──────────────────────────────► LOW FRICTION
                               OPERATIONAL TOLERANCE
```

### Why ARCH-03 is the Leading Pilot Hypothesis

1. **Native Architectural Fit:** The complete transactional pipeline (`PurchaseInvoice` → `Quotation` → `SalesOrder` → `DeliveryChallan` → `SalesInvoice` → `CustomerReceipt` → `PaymentAllocation`) is fully built and covered by verified tests.
2. **Inward Intake Matches Real Life:** B2B traders receive the vendor's commercial bill alongside the physical delivery. Entering a purchase bill to post inventory and AP atomically matches real-world practice without requiring a separate GRN stage.
3. **Working Capital Tooling In Place:** Credit limits, payment terms in days, partial payment allocations, receivables aging, a dunning cadence engine (automated reminder *scheduling*; message delivery is share-link only in the pilot — see FREEZE_SCOPE §G3), and statutory TCS (206C) / TDS (194Q) are implemented.
4. **Lowest Operational Sensitivity:** Operates on standard desktop/laptop browsers with regular A4 laser/inkjet printers. Not exposed to counter queue pressures, thermal printer drivers, or barcode scanner debounce failures.

### Pilot Readiness vs. Commercial Value Comparison

| Archetype | Functional Readiness | Operational Risk | Changes Needed for Pilot | Commercial Attractiveness | Strategic Pilot Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ARCH-03: Semi-Wholesaler** | High (Verified) | **Very Low** | **Near Zero:** Test complete loop with standard desktop. | **High** (Strong WTP, high data lock) | **LEAD PILOT HYPOTHESIS** |
| **ARCH-01: Counter Retailer** | Moderate (POS built) | **High** (Counter speed) | **Low to Medium:** Validate scanner auto-submit & thermal slips. | Moderate (High volume, lower WTP) | **PARALLEL TEST (Stage 1)** |
| **ARCH-04: Multi-Godown** | Moderate (Transfers work)| Moderate (Multi-site) | **Low to Medium:** Pilot hand-holding on transit stock. | High (Strong lock-in) | **STAGE 4 FOLLOW-ON** |
| **ARCH-05: Batch & Expiry** | Moderate (FEFO works) | **High** (Regulatory) | **Medium:** Needs statutory drug forms (Form 20B/21B). | **Very High** (Critical pain) | **DEFER TO STAGE 4** |
| **ARCH-06: Serial Dealer** | Moderate (Serials work) | Moderate (Data entry) | **Medium:** Needs bulk serial scanner paste workflows. | High (High ticket items) | **DEFER TO STAGE 4** |
| **ARCH-07: Services** | Moderate (Service items) | Low (Desk-based) | **Medium:** Missing milestone billing & job-work. | Moderate (Smaller trade fit) | **SECONDARY EXPLORATION** |
| **ARCH-02: Composition Shop**| Moderate (CMP-08 works) | Moderate (Low literacy)| **Low:** Bill of supply ready. | **Very Low** (High churn, low WTP) | **DISQUALIFIED FROM PILOT** |

---

### Guardrails for ARCH-03 Pilot Cohort (No Code Changes Needed)

To guarantee a clean pilot without code changes, onboarding must enforce four operational boundaries:
1. **Single Legal GSTIN:** Target merchants operating under a single primary GST registration (inter-state B2B sales via IGST are fully supported; intra-company inter-branch transfers across states are not).
2. **Bill-Accompanied Inwarding:** The merchant's warehouse/office must enter purchase invoices when the vendor bill arrives with the goods.
3. **Offline Statutory Worksheets:** Advise the merchant and their accountant that GSTR-1 and GSTR-3B summaries are verified calculation worksheets for portal filing, not live one-click GSP submissions.
4. **E-Invoice / E-Way Obligation Stays External:** For merchants above the ₹5 Cr AATO e-invoicing threshold (or any consignment above the ₹50k e-way-bill limit), the merchant keeps generating the IRN / e-way bill in their existing utility and records the returned number against the Bizboard invoice via the manual IRN / EWB status field. Bizboard does not generate live IRNs or e-way bills in the pilot.

---

### Immediate Actionable Next Steps

1. **Recruit 4–6 B2B Trading Pilot Merchants:** Select businesses in hardware, building supplies, packaging materials, or auto-spares doing ₹1 Cr – ₹10 Cr annual turnover. Where a merchant is above the ₹5 Cr e-invoicing threshold, confirm during onboarding that they will keep generating IRNs in their current tool (Guardrail 4).
2. **Execute Onboarding via Standard 4-Step Protocol:**
   * Step 1: Bulk CSV import of Product Master (with HSN & Price Lists), Customers, and Suppliers.
   * Step 2: Establish opening inventory and customer outstanding balances.
   * Step 3: Run the Complete Business Loop daily (Purchase Inward → Quotation → Order → Challan → Invoice → Payment Allocation → Statement).
   * Step 4: Validate month-end tax reporting and trial balance equilibrium with their external CA (P6).
3. **Evaluate Against Hypotheses H-01 & H-05:** Track whether derived ledgers reconcile without error and whether the external CA signs off on statutory worksheets without recalculation.

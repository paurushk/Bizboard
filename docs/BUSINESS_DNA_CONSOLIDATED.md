# BizBoard consolidated reference

**Revision:** 2026-09-26i

One list of market archetypes, user personas, system roles, tracked journeys, workflow chains, and roadmap items.

| Revision | What changed |
|---|---|
| 2026-09-26 | First consolidation of presets, the 14 personas, 68 journeys, WF-01–WF-60, and the PRE-09 / PRE-10 roadmap. |
| 2026-09-26b | Review pass. WF-56 cites D9. WF-54 is recorded as having no test. PRE-03, PRE-04, PRE-05, PRE-07, and PRE-08 gaps are tracked in §6.0. INS-0 is the role prerequisite for P12. SAAS-6 is marked as a tenant-boundary change. |
| 2026-09-26c | Implementation plan for the additional rows: [ADDITIONAL_ROADMAP_IMPLEMENTATION_PLAN_2026-09-26.md](roadmap/ADDITIONAL_ROADMAP_IMPLEMENTATION_PLAN_2026-09-26.md). |
| 2026-09-26d | That plan now requires `rls_bypass` on the vendor-share write, RLS enrollment for every new `company` table, and a hand edit of `test_rbac_matrix.py` for `POLICY_DESK`. |
| 2026-09-26e | INS-0 through INS-11, PRE-R1 through PRE-R5, and SAAS-1 through SAAS-6 are implemented. |
| 2026-09-26f | Test-suite gap plan: [TEST_SUITE_AND_STRATEGY_GAP_PLAN_2026-09-26.md](roadmap/TEST_SUITE_AND_STRATEGY_GAP_PLAN_2026-09-26.md). |
| 2026-09-26g | That plan corrected: manufacturing pack apply succeeds; §7 ids stay `G-`; WF-60 ranges; root coverage audit is archived in Phase 0. |
| 2026-09-26h | Plan code-pass: caps parser and RLS union are Phase 0 tasks, `J-PROJ-P1-MILESTONE` is the 69th journey, D17 is the off-ledger commission book. |
| 2026-09-26i | Gap plan executed: persona days, invariants, isolation probes, WF-54 pin, D17, and the ledger. |

| Section | Count | Nothing dropped |
|---|---|---|
| Operating presets | 10 | PRE-01 through PRE-10 |
| Legacy market codes | 7 | ARCH-01 through ARCH-07 |
| Human personas | 14 | P1 through P14, each with a journey in section 4.2 |
| System roles | 8 | OWNER, MANAGER, SALES_STAFF, INVENTORY_STAFF, ACCOUNTANT, AUDITOR, VIEWER, POLICY_DESK |
| Tracked journeys | 69 | 52 in `qos/journeys.yaml` (the original 51 plus `J-PROJ-P1-MILESTONE`), plus 5 for P7–P10, plus 12 for insurance and SaaS |
| Workflow chains | 60 | WF-01 through WF-60. No chain was removed. New journeys did not invent WF-61. |
| Roadmap items | 23 | INS-0 through INS-11, SAAS-1 through SAAS-6, PRE-R1 through PRE-R5 |

Two ID schemes sit side by side. **ARCH-01 through ARCH-07** are the codes already used in product docs, journeys, and tests. **PRE-01 through PRE-10** are the operating presets. Batch, serial, multi-godown, and composition GST are modifiers on a preset. They are not extra businesses.

Legacy market codes are unchanged. PRE-09 (insurance policy desk) and PRE-10 (BizBoard SaaS) are the additions.

---

## 1. Market archetypes

### 1.1 Operating presets

| Id | Name | Primary loop | Status |
|---|---|---|---|
| PRE-01 | Retail counter | Walk-in, sale, payment, repeat | Live |
| PRE-02 | Wholesale distribution | Order, stock, fulfill, invoice, collect | Live. Lead pilot. |
| PRE-03 | Workshop and repair | Request, job, parts and labour, invoice | Partial. Mixed SAC and HSN works. No job card. |
| PRE-04 | Route delivery | Plan, assign, run the beat, deliver, collect | Partial. Routes exist. Proof of delivery is not its own document. |
| PRE-05 | Relationship selling | Lead or visit, opportunity, quote, order | Partial. CRM is dark unless a deployment flag turns it on. |
| PRE-06 | Contracted recurring service | Contract, scheduled service, invoice, renewal | Partial. Contracts flag and recurring invoices. |
| PRE-07 | Project and milestone | Lead, proposal, project, milestone, invoice | Future. No project or BOQ engine. |
| PRE-08 | Light manufacturing | Demand, buy, produce, dispatch | Dark. Held pack. BOM and work orders only. |
| PRE-09 | Insurance policy desk | Campaign, lead, several policy options, sale, issue, renew, claim | CRM slice exists. A policy record does not. |
| PRE-10 | BizBoard SaaS | Acquire, trial, activate, bill, adopt, expand, renew, win back | Trial, plan, Razorpay, and SaaS dunning exist. The success loop does not. |

PRE-10 is BizBoard selling BizBoard. It is not a pack offered to a shop. A software firm that only invoices its own clients is PRE-06.

### 1.2 Legacy market codes

| Id | Name | Disposition | Where it sits now |
|---|---|---|---|
| ARCH-01 | Fast-paced counter retailer | Supported. Parallel pilot. | PRE-01 |
| ARCH-02 | Composition / neighborhood merchant | Serviceable. Commercially deprioritized. | Regulatory modifier on PRE-01 |
| ARCH-03 | Semi-wholesaler and trade merchant | Supported. Lead pilot. | PRE-02 |
| ARCH-04 | Multi-godown regional stockist | Conditional. One GSTIN. Transfers are internal. | Warehouse modifier on PRE-02 |
| ARCH-05 | Batch and expiry stockist | Conditional. FEFO works. Drug and FSSAI forms are flagged. | Inventory modifier, plus a pharma or food overlay, on PRE-02 |
| ARCH-06 | Serialized high-value dealer | Conditional. Serial lifecycle works. | Inventory modifier, plus an electronics overlay, often with PRE-03 for warranty repair |
| ARCH-07 | Light commercial service and spares | Conditional. No technician dispatch or timesheets on the frozen path. | PRE-03. The AMC slice is PRE-06. |

### 1.3 How a real business is named

| Example | DNA |
|---|---|
| Counter shop | PRE-01, cash and UPI, walk-in, simple stock, regular GST |
| Composition shop | PRE-01 plus the composition GST modifier. Still deprioritized. |
| Regional distributor | PRE-02, credit, field or phone, route fulfillment, one or many godowns, B2B, GST |
| Pharmacy wholesaler | PRE-02 plus batch plus the pharma overlay |
| Appliance dealer | PRE-01 or PRE-02 plus serial. Warranty repair is PRE-03. |
| AMC contractor | PRE-06. A one-off repair with no contract is PRE-03. |
| Insurance agency | PRE-09 |
| BizBoard itself | PRE-10 |

### 1.4 Staffing

| Model | Who is in the room | Fits |
|---|---|---|
| A Solo | P1 does billing, stock, and books | ARCH-02 / PRE-01 with the composition modifier |
| B Counter pair | P1 and P2 | ARCH-01 / PRE-01 |
| C Trade firm | P1, P3 or P4, P5 | ARCH-03, ARCH-05, ARCH-06, ARCH-07 |
| D Departmental | Counter, warehouse, accounts, external CA | ARCH-04 |
| E Insurance desk | P1, P11, P12, P5, P10 | PRE-09 |
| F BizBoard SaaS | P1, P13, P10, P14 | PRE-10 |

### 1.5 Outside these presets

Insurer underwriting, actuarial pricing, and IRDAI statutory filing. Hospital records. Restaurant KOT and tables. A carrier TMS. Marketplaces, creator platforms, and gig dispatch. Hotel property systems. Franchise royalty settlement. Full manufacturing ERP. Payroll as a product. Multi-currency import houses. Supermarket scales, pole displays, and cash-drawer hardware.

A merchant who only needs a GST invoice for one of those businesses still uses PRE-01 or PRE-03 for that invoice.

---

## 2. User personas

There are 14 human personas. P1–P6 are the original firm. P7–P10 cover route, buying, repair, and care. P11–P12 run the insurance desk. P13–P14 run BizBoard’s own SaaS business. Every one of them has at least one journey in section 4.

| Id | Person | Buying or working role | System home | A good day | They block adoption when |
|---|---|---|---|---|---|
| P1 | Managing proprietor / founder | Economic buyer | OWNER | Cash, credit, and growth are visible, and staff cannot quietly alter the books | Price is high, or data feels locked in |
| P2 | Counter clerk | Daily user | SALES_STAFF | Keyboard and scanner checkout. The till matches. | Modals, lag, lost focus |
| P3 | Traveling order booker | Field user | SALES_STAFF | Price and stock on the spot. A credit block is explained. | Cannot book, or the block is silent |
| P4 | Godown custodian | Logistics | INVENTORY_STAFF | Fast inward, batch or serial, transfers and counts that reconcile | Manual serial typing, confusing transfers |
| P5 | Resident bookkeeper | Operational gatekeeper | ACCOUNTANT | Ledgers balance, bills are clean, the bank agrees | Bank lines disagree |
| P6 | External CA | Influencer. Not a customer segment. | AUDITOR | GSTR worksheets, a zero trial balance, Tally export, locked periods | Imbalanced books, or a closed period that can still be edited |
| P7 | Route rider | Field fulfillment | SALES_STAFF, route-scoped | The beat is delivered and cash or UPI is collected | Cannot see the route or record a collection |
| P8 | Buyer | Procurement | INVENTORY_STAFF with purchases | Purchase orders, inward, supplier price, then payables handed to P5 | Re-typing a bill the godown already received |
| P9 | Technician | Workshop and AMC | SALES_STAFF | Job, spare, labour, close | There is no job card, only a counter invoice |
| P10 | Customer care | Claims and tickets | Support flag | A complaint or ticket linked to the customer or policy. The ledger is untouched. | A ticket that changes GST |
| P11 | Policy advisor | PRE-09 seller | SALES_STAFF with CRM | Campaign, lead, compare options, close the sale | Policy options stored as stock SKUs |
| P12 | Policy desk | PRE-09 administration | No role code yet | Issue the policy, diary the renewal, hand a claim to P10 | No policy record after the sale |
| P13 | Customer success | PRE-10 adoption | Vendor staff. No CS workspace yet. | Onboard a tenant, watch activation, save a quiet account | No view of who stalled after signup |
| P14 | SaaS billing admin | PRE-10 subscription | Vendor owner books. Distinct from P5. | Trial, Razorpay, SaaS dunning, seat limits | Customer receivables dunning used for BizBoard’s own subscribers |

### People with no membership

| Actor | Account | Surface |
|---|---|---|
| Paying customer | None by default | `/pay/:token`, customer portal `/portal` |
| Inbound lead | None | `/lead-form/:token` |
| Supplier | None | Purchase bills, payments, statements |
| Referral partner | A party record | A referral code. A partner login does not exist. |

### Who uses which preset

| Preset | People |
|---|---|
| PRE-01 Retail | P1, P2. P5 if the firm has a munshi. P6 at filing. |
| PRE-02 Distribution | P1, P3, P4, P5, P8. P7 when a beat exists. P6 at filing. |
| PRE-03 Workshop | P1, P9, P5. P2 if there is also a parts counter. |
| PRE-04 Route | P1, P7, P4, P5. P3 if orders are booked before the van leaves. |
| PRE-05 Relationship | P1, P3, P10. P5 when an invoice exists. |
| PRE-06 AMC | P1, P9, P5, P10 |
| PRE-07 Project | P1 and P5, when the engine exists |
| PRE-08 Manufacturing | P1, P4, P8. Dark. Not a pilot set. |
| PRE-09 Insurance | P1, P11, P12, P5, P10, P6 at filing |
| PRE-10 BizBoard SaaS | P1, P3 or P11-shaped seller on the vendor CRM, P13, P10, P14 |

---

## 3. System roles

Ground truth: `CompanyUser.Role` and `capability_defaults_for_role`. Personas are the human view of these roles. P2 and P3 share SALES_STAFF.

P12 (policy desk) has no role value. Creating a policy is an in-app write, so INS-4 cannot be permissioned until INS-0 adds a role and a capability for that desk. A referral partner is a party on a referral code, not a membership. A login for that partner is not on this roadmap.

| Role | Default grant |
|---|---|
| OWNER | Everything in company scope, including period close and user admin |
| MANAGER | Sales, purchases, payments, inventory, journals, reports, import, cancel, AI |
| SALES_STAFF | Create sales and take payments. Reports, import, inventory management, journals, and purchases stay off. |
| INVENTORY_STAFF | Inventory and purchases. Sales, payments, reports, and journals stay off. |
| ACCOUNTANT | Journals, purchases, payments, reports, export. Cannot create sales, manage inventory, or import. Period close stays with the owner. |
| AUDITOR | Read financial reports and export. No edits. |
| VIEWER | Read in-scope lists. Financial reports and every mutation stay off by default. |

Capability flags that can be granted on top of a role: `can_manage_inventory`, `can_import`, `can_cancel_documents`, `can_view_financial_reports`, `can_export`, `can_view_ai_insights`, `can_use_ai_assistant`, `can_create_sales`, `can_create_purchases`, `can_create_payments`, `can_post_journals`.

---

## 4. Tracked journeys

### 4.1 Register (68)

`qos/journeys.yaml` holds the original tracked rows plus `J-PROJ-P1-MILESTONE`. Five further rows cover P7–P10. Twelve cover insurance and SaaS. Workflow chains stay at 60. The extra rows are reference journeys. They are not new WF numbers. Shipped desks are API-gated in `backend/tests/personas/`. The ledger is [TEST_CENSUS_LEDGER.md](TEST_CENSUS_LEDGER.md).

| Id | Persona | Archetype | Journey | Evidence |
|---|---|---|---|---|
| J-RETAIL-P2-POS | P2 | ARCH-01 | 5-line counter checkout, keyboard and scanner only | Tested |
| J-RETAIL-P2-POS-SPEED | P2 | ARCH-01 | POS checkout inside the 35-second no-mouse budget | Tested |
| J-RETAIL-P2-OFFLINE | P2 | ARCH-01 | Queue drafts during a drop and flush once on reconnect | Tested |
| J-RETAIL-P2-THERMAL | P2 | ARCH-01 | Thermal slip prints, or degrades cleanly if the printer is absent | Untested |
| J-RETAIL-P1-DAYCLOSE | P1 | ARCH-01 | End-of-day till reconciliation and daily sales summary | Tested |
| J-RETAIL-P1-REORDER | P1 | ARCH-01 | Review reorder thresholds and restock the counter | Untested |
| J-COMP-P1-BOS | P1 | ARCH-02 | Bill of supply with no CGST/SGST/IGST, then CMP-08 | Tested |
| J-TRADE-P1-LOOP | P1 | ARCH-03 | Purchase to stock and AP, order, challan, invoice, AR, receipt, allocation | Tested |
| J-TRADE-P1-INWARD | P1 | ARCH-03 | Vendor bill on delivery posts stock and AP atomically | Tested |
| J-TRADE-P3-QUOTE | P3 | ARCH-03 | Field product and price lookup, quotation with slab price | Tested |
| J-TRADE-P3-CREDITBLOCK | P3 | ARCH-03 | Over-limit order is explained, not silently dropped | Tested |
| J-TRADE-P3-CHALLAN | P3 | ARCH-03 | Delivery challan and dispatch before billing | Tested |
| J-TRADE-P3-FLAKYNET | P3 | ARCH-03 | Book an order over a degraded field connection | Untested |
| J-TRADE-P5-ALLOC | P5 | ARCH-03 | Partial multi-invoice receipt allocation with no orphan balance | Tested |
| J-TRADE-P5-BANKREC | P5 | ARCH-03 | Match bank statement lines to the general ledger | Untested as a persona journey |
| J-TRADE-P5-MONTHEND | P5 | ARCH-03 | Period close, GSTR-1 and 3B worksheets, trial balance zero | Tested |
| J-TRADE-P5-TCS | P5 | ARCH-03 | TCS 206C over threshold: collection, GL, worksheet | Tested |
| J-TRADE-P5-DUNNING | P5 | ARCH-03 | Dunning cadence schedules reminders; merchant sends the share link | Tested |
| J-GODOWN-P4-TRANSFER | P4 | ARCH-04 | Inter-godown transfer nets to zero; in-transit stock is not double-counted | Tested |
| J-GODOWN-P4-COUNT | P4 | ARCH-04 | Physical count session and variance adjustment reconcile to GL | Untested as a persona journey |
| J-GODOWN-P4-REORDER | P4 | ARCH-04 | Location-specific reorder levels flag a low godown | Untested |
| J-GODOWN-P1-MULTI | P1 | ARCH-04 | Three-godown day: balances equal the sum of movements per item, godown, and lot | Tested |
| J-GODOWN-P2-CENTRAL | P2 | ARCH-04 | Central office bills; goods are fulfilled from a peripheral godown | Tested |
| J-BATCH-P4-INWARD | P4 | ARCH-05 | Inward by manufacturer lot: batch, manufacture date, and expiry are mandatory | Tested |
| J-BATCH-P4-FEFO | P4 | ARCH-05 | Dispatch consumes the earliest-expiry lot first | Tested |
| J-BATCH-P4-EXPIREBLOCK | P4 | ARCH-05 | Expired or near-expiry stock cannot be invoiced under an active policy | Untested |
| J-BATCH-P5-RETURNCN | P5 | ARCH-05 | Credit note on a physical return, tagged sellable or damaged | Tested |
| J-BATCH-P1-ALERTS | P1 | ARCH-05 | Review the expiry-alert band and act before stock expires | Tested |
| J-SERIAL-P4-INWARD | P4 | ARCH-06 | Bulk serial ingest with partial-failure semantics | Untested in the journey file |
| J-SERIAL-P2-RETURN | P2 | ARCH-06 | Return checks the serial was sold; a second return is rejected | Tested |
| J-SERIAL-P2-WARRANTY | P2 | ARCH-06 | Warranty lookup by serial at the counter | Untested |
| J-SERIAL-P5-VENDORDN | P5 | ARCH-06 | Vendor warranty debit note against a returned serial | Tested |
| J-SVC-P1-MIXED | P1 | ARCH-07 | Mixed SAC service and HSN goods invoice with correct tax | Tested |
| J-SVC-P5-TDS | P5 | ARCH-07 | TDS 194C/194J withholding on collections, correct GL | Tested |
| J-SVC-P1-RECURRING | P1 | ARCH-07 | Recurring retainer invoice without re-keying | Untested |
| J-SVC-P1-AMC | P1 | ARCH-07 | AMC or maintenance-contract billing schedule | Untested in the journey file |
| J-ONBOARD-P1 | P1 | Cross | Register, guided setup, first invoice | Tested |
| J-ONBOARD-P1-STEPS | P1 | Cross | First invoice reachable in three steps or fewer | Untested |
| J-MIGRATE-P5 | P5 | Cross | Day-zero import of masters and opening balances, numbering continuity | Tested |
| J-CA-P6-AUDIT | P6 | Cross | CA files GSTR-1/3B from worksheets without recalculation | Proxy only |
| J-ROLE-P2-NAV | P2 | Cross | Sales-staff navigation hides every denied action | Untested |
| J-ROLE-P5-NAV | P5 | Cross | Accountant navigation hides sales-create and import | Untested |
| J-A11Y-P2-KEYBOARD | P2 | Cross | Keyboard-only POS and invoice form, with screen-reader labels | Untested |
| J-SCALE-P1-REPORTS | P1 | Cross | Reports and exports over a full year inside a latency budget | Untested |
| J-X-P1-SWITCHCO | P1 | Cross | Switch company; every list re-scopes with no cross-tenant leak | Tested |
| J-X-P5-JOURNAL | P5 | Cross | Create, post, and reverse a manual journal | Tested |
| J-X-P6-TALLY | P6 | Cross | Export books to a Tally-importable file | Tested |
| J-X-P1-PWRESET | P1 | Cross | Password reset and change with rate limiting | Tested |
| J-X-P2-RECEIPT | P2 | Cross | Record a customer receipt and allocate it at the counter | Tested |
| J-X-P1-KPIDRILL | P1 | Cross | Every dashboard KPI reconciles to its drill-down list | Tested |
| J-X-P1-OTP | P1 | Cross | OTP login: request, verify, session; hashed at rest, rate-limited | Tested |
| J-ROUTE-P7-BEAT | P7 | PRE-04 | Assigned stops are delivered or exceptioned, and cash or UPI collected on the beat ties to receipts | API-gated. `test_j_route_p7_beat_requires_receiver_and_does_not_post`. The slip does not create the receipt. |
| J-BUY-P8-PO | P8 | PRE-02 | A purchase order becomes a bill. Stock and payables post together. P5 can pay without retyping the bill. | Purchase order to bill is WF-16 |
| J-JOB-P9-REPAIR | P9 | PRE-03 | A job consumes a spare and labour. The invoice has both SAC and HSN. Spare stock falls. | API-gated. `test_j_job_p9_repair_converts_once_then_posts_stock`. UI is a component test. |
| J-AMC-P9-VISIT | P9 | PRE-06 | A contract due date produces a visit and an invoice without re-keying the retainer | Recurring invoices and contracts exist. The visit link does not. |
| J-CARE-P10-TICKET | P10 | PRE-02 / PRE-03 | A complaint or ticket links to the customer and, for a serial item, to the sold unit. It does not post the ledger. | Boundary. `test_j_care_p10_ticket_has_no_serial`. A ticket has a customer and no serial. |
| J-PROJ-P1-MILESTONE | P1 | PRE-07 | Two milestones become draft service invoices. A stock product on a milestone is rejected. Close waits until each ready milestone is invoiced. | API-gated. `test_j_proj_p1_milestone_invoices_services_and_blocks_close` |
| J-INS-P11-CAMPAIGN | P11 | PRE-09 | Open a campaign, capture a lead from it, and assign it | CRM tested while the flag is on |
| J-INS-P11-OPTIONS | P11 | PRE-09 | Put two or more policy options on one lead and record the one the customer prefers | Missing policy-option object |
| J-INS-P11-SALE | P11 | PRE-09 | Mark the chosen option won and hand it to the desk | A won opportunity does not create a policy |
| J-INS-P12-ISSUE | P12 | PRE-09 | Record insurer, policy number, term, sum insured, and nominee | Missing policy record |
| J-INS-P12-RENEW | P12 | PRE-09 | See policies ending this month and open a renewal lead | Missing renewal diary |
| J-INS-P5-COMMISSION | P5 | PRE-09 | Book insurer commission separately from the customer premium | Customer invoice only |
| J-INS-P10-CLAIM | P10 | PRE-09 | Open a claim ticket on a sold policy without posting GST | Tickets exist. No policy link. |
| J-SAAS-P1-TRIAL | P1 | PRE-10 | Register, receive a trial, and see module flags match the trial plan | Tested |
| J-SAAS-P13-ACTIVATE | P13 | PRE-10 | Tenant finishes setup and posts a first invoice, visible to success | Setup exists. No CS view. |
| J-SAAS-P14-BILL | P14 | PRE-10 | Razorpay conversion, past-due dunning, write block, plan change next cycle | Tested in billing |
| J-SAAS-P10-SUPPORT | P10 | PRE-10 | Handle a tenant ticket without becoming that tenant’s accountant | Tickets live inside one company |
| J-SAAS-P13-WINBACK | P13 | PRE-10 | Tag a churn reason and put the tenant back on a campaign | Missing churn reason |

### 4.2 Every persona has a journey

| Persona | At least one journey in the register |
|---|---|
| P1 Proprietor / founder | J-TRADE-P1-LOOP, J-SAAS-P1-TRIAL |
| P2 Counter clerk | J-RETAIL-P2-POS |
| P3 Order booker | J-TRADE-P3-QUOTE |
| P4 Godown custodian | J-GODOWN-P4-TRANSFER |
| P5 Bookkeeper | J-TRADE-P5-ALLOC, J-INS-P5-COMMISSION |
| P6 External CA | J-CA-P6-AUDIT |
| P7 Route rider | J-ROUTE-P7-BEAT |
| P8 Buyer | J-BUY-P8-PO |
| P9 Technician | J-JOB-P9-REPAIR, J-AMC-P9-VISIT |
| P10 Customer care | J-CARE-P10-TICKET, J-INS-P10-CLAIM, J-SAAS-P10-SUPPORT |
| P11 Policy advisor | J-INS-P11-CAMPAIGN |
| P12 Policy desk | J-INS-P12-ISSUE |
| P13 Customer success | J-SAAS-P13-ACTIVATE |
| P14 SaaS billing admin | J-SAAS-P14-BILL |

### 4.3 Persona-test journeys already in the suite

These are implemented as API persona tests. They overlap the register above.

| Journey | Who | Where | What a day looks like |
|---|---|---|---|
| Kirana golden day | P1, P2 | ARCH-01 | Multi-tender counter billing, low-stock alert, reorder before stockout |
| Distributor golden day | P1, P4 | ARCH-03 / ARCH-04 | Godown rebalance, route billing, credit exposure, collection |
| Pharma golden day | P4, P5 | ARCH-05 | Batch inward, FEFO dispense, near-expiry purchase return |
| Micro vendor cash day | P1 | ARCH-01 / ARCH-02 | Quick cash operating cycle |
| Manufacturing BOM | P1 | Dark module | BOM, work order, raw consumption, WIP |
| CRM lead to order | P3, P4 | Dark CRM | Lead to sales order to challan, plus self-referral guard |
| Growth campaigns | P1, P3 | Dark CRM | Campaign, referral, and pipeline |
| Complaints and tickets | Support roles | Growth OS | Support agent and claims inspector lifecycle |
| Contracts and field service | P1 | ARCH-07 | AMC contract and field-service journey |
| Route sequencing | P1 | ARCH-04 | Suggest a delivery sequence and apply it |
| Insights and promise-to-pay | P1, P5 | Cross | Low stock, credit-near, sale below cost, promise to pay on attention |
| POS shift cash | P2 | ARCH-01 | Counter shift and cash-drawer reconciliation |
| Payroll | P1, P5 | Dark payroll | Pay run posts to the ledger. Sales and godown are denied. |
| E-invoice and e-way | P1, P3 | ARCH-03 | Mark or submit IRN and e-way on an invoice |
| FTUE and help | P1 | Cross | Setup stepper, invite landing, help-code resolution |
| Reporting reconcile | P1, P5 | Cross | Sales register to dashboard and GL; stock valuation; aging to subledger |
| GST guard override | P1 | ARCH-03 | Owner can override a GST guard. The boundary is capability-checked. |
| Bank recon persona | P5 | ARCH-03 | Account-aggregator matching and journal |
| Resilience | All | Cross | Idempotent retry, payload replay, tenant isolation, RBAC matrix |

### 4.4 End-to-end loops

| Loop | Steps |
|---|---|
| PRE-02 / ARCH-03 trade | Supplier bill, stock and payables posted together, quotation with slabs, sales order, credit check, delivery challan, tax invoice, derived receivables, receipt, allocation, statement, period close, GSTR-1 and 3B worksheets |
| PRE-01 / ARCH-01 counter | Barcode, tax-inclusive price, UPI or cash, one action that completes the invoice, posts the receipt, allocates it in full, moves stock, and balances the journal, then a thermal slip |
| ARCH-04 godown | Inward, transfer that nets to zero, central bill fulfilled from another godown, count, variance to the ledger |
| ARCH-05 batch | Lot inward with manufacture and expiry dates, FEFO issue, expired stock blocked, return tagged sellable or damaged, expiry alerts |
| ARCH-06 serial | Serial inward, sale marks it sold, warranty lookup, return only if that serial was sold, vendor debit note. A second return of the same serial is rejected. |
| PRE-03 / ARCH-07 service | Mixed service and spare invoice, TDS on collection, contract or AMC when that flag is on |
| Day zero and month end | Register, setup, import masters and openings, continue the old invoice series. Then allocate, reconcile the bank, close the period, export worksheets. |
| Growth | Public lead, CRM onboarding, opportunity and campaign, quotation, order, complaint or ticket, contract or referral. A self-referral reward is rejected. |
| PRE-09 insurance | Campaign, lead attributed to it, two or more policy options, customer picks one, opportunity won, policy issued, customer premium and insurer commission kept apart, renewal before expiry, claim ticket on that policy |
| PRE-10 SaaS | Register, trial and module flags, setup and first invoice, paid plan on Razorpay, past-due SaaS dunning, write block, plan change next cycle, success watches quiet tenants, churn reason, win-back campaign |

### 4.5 What PRE-09 and PRE-10 may reuse

| Step | Reuse | Leave alone |
|---|---|---|
| Insurance campaign and lead | Campaign, Lead, public form, referral code | A stock quotation treated as a policy |
| Policy options | Opportunity as the container | Opportunity lines tied to a goods product |
| Premium invoice | Sales invoice and receipt, when the customer pays the agency | That same invoice as the commission from the insurer |
| Claim | Support ticket | A credit note, unless money is actually refunded |
| SaaS trial and block | Subscription, plan modules, write-gate middleware | Customer receivables dunning |
| SaaS collect | `billing.dunning` and Razorpay | `payments.dunning`, which chases a merchant’s customers |

---

## 5. Workflow chains

Each chain is an API contract that stock, tax, receivables or payables, and the general ledger still agree at the end.

| Id | Name | Chain |
|---|---|---|
| WF-01 | Intrastate sale | Draft invoice to complete: stock down, CGST/SGST, receivables up, balanced ledger |
| WF-02 | Interstate sale and cess | IGST by place of supply; ad-valorem and per-unit cess |
| WF-03 | Sales return | Stock up, GST reversal, receivables down |
| WF-04 | Purchase | Complete posts stock and payables atomically, input tax credit recorded |
| WF-05 | Purchase return | Stock down, GST reversal, payables down |
| WF-06 | Quotation to invoice | No stock or ledger until the invoice completes |
| WF-07 | Financial credit note | Receivables down, no stock movement |
| WF-08 | Customer debit note | Raises receivables |
| WF-09 | Sales order | Reserve, then convert to invoice or challan |
| WF-10 | Delivery challan then invoice | Challan moves stock without GST or receivables |
| WF-11 | Recurring invoice | Generation is idempotent |
| WF-12 | Purchase credit note | Reduces payables and reverses input tax credit |
| WF-13 | Purchase debit note | Enlarges payables; TDS interaction |
| WF-14 | Sales bill upload | Extract to draft; re-upload is idempotent |
| WF-15 | Purchase bill upload | Same idempotent extract |
| WF-16 | Purchase order to bill | Convert a purchase order into a purchase invoice |
| WF-17 | Gateway webhook | Signature check, replay is a no-op, park on a cancelled or closed period |
| WF-18 | OTP login | Hashed at rest, rate limited |
| WF-19 | POS checkout | Invoice, receipt, full allocation, stock, journal |
| WF-20 | Period close correction | Back-date rejected; sanctioned reverse and re-post |
| WF-21 | Stock transfer | Out and in net to zero; batch and serial identity kept |
| WF-22 | Stock write-off | Valuation down, ledger expense |
| WF-23 | Import products | Idempotent |
| WF-24 | Import customers | Idempotent |
| WF-25 | Import opening stock | Idempotent; a duplicate file is rejected |
| WF-26 | Bank receipt to the ledger | Instrument posts to the linked bank ledger |
| WF-27 | GSTR-1 and 3B tie-out | 3B ties to the outward and purchase registers |
| WF-28 | Two-tenant interleave | No cross-company reads |
| WF-29 | Manual journal | Post and reverse |
| WF-30 | Chart of accounts | Manage accounts |
| WF-31 | Financial year close | Balance sheet equation |
| WF-32 | Opening balances | Receivables, payables, and inventory tie to the opening trial balance |
| WF-33 | Bank reconciliation | Match statement lines; a bare re-commit does not double-match |
| WF-34 | TCS 206C | Collection, ledger, worksheet |
| WF-35 | TDS 194Q | Withholding on purchases |
| WF-36 | TDS/TCS worksheets | Reconcile to the books |
| WF-37 | Gateway refunds | Blocked on live sandbox credentials |
| WF-38 | MDR settlement | Blocked on live sandbox credentials |
| WF-39 | Advance on account | Unallocated receipt, then allocation |
| WF-40 | Bad-debt write-off | Ledger |
| WF-41 | Bank statement import | Match, idempotent replay |
| WF-42 | Dunning schedule | Cadence; send is a share link |
| WF-43 | Invoice cancellation | Reverses the chain |
| WF-44 | Invoice amendment | Reverse and re-post nets to zero; stock stays immutable |
| WF-45 | Registration | Account create; email verify is a separate step |
| WF-46 | Password reset | Rate limited |
| WF-47 | JWT refresh and logout | Session lifecycle |
| WF-48 | Invite to role | Membership with capability defaults |
| WF-49 | Switch company | Context re-scope |
| WF-50 | Sandbox expiry | Paired with erasure |
| WF-51 | Idempotency contract | Replay does not double-post |
| WF-52 | Document numbering | Gap-free serials, year reset |
| WF-53 | Fixed assets | Acquire, depreciate, dispose. Known limitation D6. |
| WF-54 | TDS/TCS certificates | GSTR-7/8 and forms 16A/27D. Known limitation D7. Named in `docs/FREEZE_SCOPE.md`. No test and no stub anywhere in `backend/`. |
| WF-55 | Reverse charge | Self-invoice path. Known limitation D8 for pilot merchants. |
| WF-56 | Composition bill of supply | No tax lines, CMP-08. Known limitation D9. Deprioritized archetype. |
| WF-57 | Bill of entry | Duty and landed cost. Known limitation D10. |
| WF-58 | Plan limits | Entitlement fails closed, and quotas hold |
| WF-59 | Right to erasure | Cascade tenant data; keep statutory tombstones |
| WF-60 | Drug and FSSAI licence | Soft-block complete until a licence is on file, or an override |

---

## 6. Roadmap items

§6.0 records gaps already named on presets that are not Live. Those five rows are not in `docs/PRODUCT_QUALITY_BACKLOG.md`. This file is the tracker for them. §6.1 through §6.3 are the build order for PRE-09, then the policy desk, then PRE-10.

### 6.0 Other presets that are not Live

| Id | Preset | Gap | Where it is tracked |
|---|---|---|---|
| PRE-R1 | PRE-03 Workshop | Job card converts to a draft sales invoice. The card does not post stock or GST. | Shipped. `ENABLE_WORKSHOP`. |
| PRE-R2 | PRE-04 Route | Delivered stops record who received the goods, an optional photo and receipt, and a reprintable slip. | Shipped on the delivery stop. |
| PRE-R3 | PRE-05 Relationship selling | Retail and trade pack confirm does not turn CRM on. The insurance pack is the CRM grant. | Shipped. `docs/ops/DARK_MODULE_GRANT.md`. |
| PRE-R4 | PRE-07 Project | Milestone billing raises one draft invoice per milestone. No BOQ, retention, or RA bill. | Shipped. `ENABLE_PROJECTS`. |
| PRE-R5 | PRE-08 Manufacturing | BOM and work orders exist. The module stays dark and the manufacturing pack stays held. | Shipped as a hold. The pack is still not confirmable. |

### 6.1 Insurance, so PRE-09 can complete a sale

| Id | Feature | Why | Depends on |
|---|---|---|---|
| INS-0 | A role and a capability for P12, the policy desk, that can create a policy and cannot post GST | Role code `POLICY_DESK`, capability `can_manage_policies`. | Shipped. |
| INS-1 | Insurance pack: CRM, campaigns, referrals, and tickets on together | Pack id `insurance`. Retail and trade still skip dark modules. | Shipped. |
| INS-2 | Policy product: insurer, line, tenure, sum insured, premium | Options are not stock SKUs | Shipped. `/api/v1/insurance/products/`. |
| INS-3 | Option set on one lead: two or more products, one marked chosen | The advisor’s actual conversation | Shipped. |
| INS-4 | A won option creates a Policy: number, start, end, nominee, status | The sale has to leave a record | Shipped. |
| INS-5 | Advisor book: my campaigns, my leads, my in-force policies | P11’s home screen | Shipped. `/api/v1/insurance/book/`. |

### 6.2 Insurance, so the desk can administer the policy

| Id | Feature | Why | Depends on |
|---|---|---|---|
| INS-6 | Commission receivable from the insurer, separate from the customer premium | P5 must not mix the two | Shipped. `CommissionReceivable`. |
| INS-7 | Renewal diary: policies ending in N days become a lead on the same campaign family | The book dies without it | Shipped. `/api/v1/insurance/renewals/`. |
| INS-8 | Endorsement and cancellation of a policy, with an audit row | Administration after the sale | Shipped. |
| INS-9 | Claim ticket linked to a policy. No ledger post. | P10’s journey | Shipped. |
| INS-10 | KYC attachments on the policy | The file the insurer asks for | Shipped. |
| INS-11 | POSP or agency licence on the company, same pattern as drug and FSSAI licences | The desk should know the licence is on file | Shipped. Licence types `POSP` and `AGENCY`. |

### 6.3 SaaS, so PRE-10 can run BizBoard

| Id | Feature | Why | Already have |
|---|---|---|---|
| SAAS-1 | Activation event: setup done and first invoice, visible to P13 | Copied into the vendor company when `VENDOR_COMPANY_ID` is set. | Shipped. |
| SAAS-2 | Tenant health: last invoice, last login, quota headroom | Adoption is invisible | Shipped. `/api/v1/billing/vendor/tenants/`. |
| SAAS-3 | Upgrade prompt when a seat or document limit is hit | Expansion is a billing page the owner must find | Shipped on the subscription payload. |
| SAAS-4 | Trial-ending notice before the write gate, distinct from past-due dunning | The block surprises the owner | Shipped. Past-due status does not show this notice. |
| SAAS-5 | Churn reason on suspend, and a win-back campaign on the vendor tenant | J-SAAS-P13-WINBACK | Shipped. Owner suspend requires a reason. |
| SAAS-6 | Vendor support console: P10 reads another tenant’s tickets without becoming that tenant’s accountant | The share row is written inside `rls_bypass()` and enrolled in RLS. `CompanyScopedViewSet` and WF-28 are unchanged. | Shipped. Empty `VENDOR_COMPANY_ID` returns 404. |

### 6.4 On this list, and also off it

On the list: the five non-live preset gaps in §6.0, the agency book (role, sell, issue, renew, commission, claim intake), and BizBoard’s own subscription operations. SAAS-6 is on the list and is the one item that crosses tenant isolation.

Off the list: IRDAI statutory filing, actuarial pricing, insurer underwriting, and a hospital claim adjudicator. Usage-based metered pricing for BizBoard. Plans stay seats, document counts, storage, and modules.

### 6.5 Already shipped, so they are not roadmap rows

| Area | What exists |
|---|---|
| Insurance sell, partial | Campaign, lead, activity, assignment, public lead form, referral code, opportunity with a won stage. CRM is flagged. |
| Insurance money, partial | A GST invoice and receipt when the customer pays the agency |
| Insurance care, partial | Support tickets and complaints, with no policy link |
| SaaS billing | Plan, trial, module flags, seat and document and storage and API quotas, Razorpay subscription, deferred plan switch, past-due SaaS dunning, write gate, usage snapshot |

---

## Sources

Checked against these sources as of revision 2026-09-26b:

- `docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md` v3.2 (2026-09-09) for ARCH-01 through ARCH-07
- `docs/FREEZE_SCOPE.md` scope revision 2026-09-09b for D6, D7, D8, D9, and D10
- `qos/journeys.yaml` for the first 51 journey IDs
- `CompanyUser.Role` and `capability_defaults_for_role` for the seven roles and the eleven capability flags
- `backend/tests/workflows/` for WF-01 through WF-53 and WF-55 through WF-60. WF-54 is the exception: it is named in `FREEZE_SCOPE.md` and `backend/tests/workflows/README.md`, and it has no test.
- `backend/crm/models.py`, `backend/billing/models.py`, and `backend/billing/dunning.py` for what PRE-09 and PRE-10 can already reuse. There is no `Policy` model.
- [roadmap/ADDITIONAL_ROADMAP_IMPLEMENTATION_PLAN_2026-09-26.md](roadmap/ADDITIONAL_ROADMAP_IMPLEMENTATION_PLAN_2026-09-26.md) for how INS-0, PRE-R1 through PRE-R5, and SAAS-6 are built

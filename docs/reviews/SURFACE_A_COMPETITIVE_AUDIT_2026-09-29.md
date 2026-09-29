# BizBoard — Surface A competitive audit (2026-09-29)

**Method.** Current working tree booted bare (SQLite, pilot flag profile from `backend/.env.pilot.example` / `web/.env.pilot.example`; deviations: `OTP_ENABLED=0`, `CELERY_TASK_ALWAYS_EAGER=1`, dev OTP echo on). Two fresh tenants registered; UI driven in the in-app browser for onboarding, dashboard, invoice form, POS, receipts, collections, reports; API driven by script for tax/stock/money jobs. Latencies are localhost SQLite, single user — indicative only.
**Not exercised:** real Postgres, real network, real SMS/e-mail, physical scanner/thermal printer, offline queue replay, Hindi copy review, mobile viewport, Marg / ClearTax / ERPNext / BUSY (no access; pricing only via web search, labelled Customer-reported / secondary where not vendor-official).
Evidence labels: **VP** verified in product · **VC** verified in code · **CO** competitor official · **CR** secondary/customer-reported · **INF** inference · **NO** not observed.

---

## Executive Summary

**Maturity band: Switchable for a narrow archetype.** The narrow archetype is a *Tally/Vyapar-leaving small trader or counter retailer who does not need on-portal filing from the tool and whose CA will work from exports*. It is **not** switchable for a business whose CA wants GSTR working papers, 2B match, or a trial balance on existing history: GSTR screens return 404 on the pilot profile (VP) and books cannot be back-filled from the UI (VP/VC). Core money paths are sound: on ~20 posted documents, intra/inter-state splits, cess, round-off, credit-limit, negative-stock, FEFO batch pick, over-allocation, over-return, purchase return, supplier balance and closed-period blocks all behaved correctly and the post-enable trial balance balanced (VP).

**Beats today:** auto FEFO batch pick on a no-batch line (VP) vs Vyapar/Zoho Free; clear, specific business-rule errors (credit limit, stock, allocation, closed period) with numbers (VP); a 5-step wizard that ends with a *completed real invoice* (VP); strict RBAC for Sales Staff (VP); 500-row import validated in ~1 s with row-numbered errors (VP).

**Loses to:** TallyPrime and BUSY on CA trust + GST working papers; Zoho Books on GST reports/2B/e-invoice at ₹0–₹899/mo (CO); Vyapar on price and counter simplicity (CR).

**Critical weaknesses (trust first):**
1. **Tax engine silently re-rates by a 4-digit HSN starter table.** A ₹3,000 T-shirt was billed at 5% (garments above ₹2,500 are 18% under GST 2.0 — INF from CBIC notification, CA to confirm). "Basmati Rice 5kg" entered at 18% was billed at 0% (table says "non-branded 0%, branded/packed 5%"). (VP; VC `masters/hsn_catalog.py`, `core/services/tax_engine/india.py:apply_effective_gst_rate`.)
2. **Counter dead-end:** POS shows the master rate (₹896), server bills ₹840, sale is rejected with raw `code: pos_totals_mismatch; …confirm_codes…` and the till never updates; retry repeats forever (VP). The designed reconcile dialog did not appear (cause: INF).
3. **No CA path on Surface A:** GSTR-1/3B/2B, GST health, CA pack → 404 (VP). Only TDS/TCS worksheets and CSV registers.
4. **Books are opt-in and not retroactive.** Enabling after documents exist → empty P&L/TB, Inventory GL −₹1,200, period close blocked by `DOCS_GL_*` alerts; UI says "run the accounting backfill" which is a management command (VP; VC `accounting/views.py:38`). Default `accountingEnabled=false` (VP).
5. **Barcode does not work on the main invoice form** (VP; VC `NewInvoicePage.tsx` Autocomplete filters on a label without barcode). Works in POS (VP).
6. **Lump-sum receipt cannot be split across invoices in the UI** (one optional invoice per receipt — VC `ReceiptsPage.tsx`); API can (VP). Collections page has no action and "Customer total" is ₹0.00 for every row (VP).

**Top 10 improvements (customer value → competitive impact):** (1) stop silent re-rating: show "rate changed 12→5 by HSN table" and require confirm, remove price-threshold HSNs from auto-apply; (2) fix POS mismatch: use server preview as the till total and show the reconcile dialog; (3) ship the GSTR-1/3B *worksheet* on the pilot profile, labelled offline; (4) enable books from day one and add UI back-fill; (5) barcode exact-match in invoice/purchase pickers; (6) multi-invoice receipt allocation with "oldest first"; (7) Collections: fix Customer total, add Collect/Remind/Allocate; (8) Tally/Vyapar exit: parties + opening balances import, ledger-opening; (9) partial-commit imports; (10) remove/hide dead menu items (Fixed Assets, Bills of Entry, Telegram) and clear jargon from owner dashboard.

> **Scope update (same day, per founder).** The first pass scored the pilot flag profile only and parked CRM / Customer 360 / after-sales / referrals / insights as "dark". BizBoard is a holistic product, so a second pass ran with those modules **on** (`ENABLE_CRM, CUSTOMER_360, CUSTOMER_PORTAL, COMPLAINTS, SUPPORT_TICKETS, REFERRALS, WORKSHOP, PROJECTS, CONTRACTS, INSURANCE, CUSTOMER_ACTIONS, CROSS_SELL, PREDICTIVE_DUNNING, ACTION_ASSIGNMENT, AI insights`). Results are in **"Growth OS pass"** below. Scores are now reported twice: **Core** (pilot profile) and **Holistic** (growth on). Growth scores are not averaged into Core.
>
> **Headline change:** the holistic product has a real, demonstrable position no primary competitor has (customer, dues, promises, complaints, tickets, AMC, referrals and CRM history on one customer screen, all from data the books already hold). But that screen currently contradicts itself when books are enabled after history exists, so the differentiator is not yet safe to sell. Fix the core numbers first, then lead with it.

---

## Feature Comparison Matrix

Best-competitor tiers/prices: TallyPrime Silver ₹22,500 one-time +18% GST, TSS ₹4,500/yr; Gold ₹67,500 (CR, appadvisor/erpresearch). Zoho Books Free ₹0 (1 user, 1,000 inv/yr), Standard ₹899/mo (₹749 annual, 3 users, e-invoice), Elite ₹5,999/mo (batch, multi-warehouse) (CO zoho.com/in/books/pricing). Vyapar desktop Silver ≈₹3.4k/yr, ≈₹4k desktop+mobile (CR). BUSY Basic ≈₹11k, Standard ≈₹15k one-time (batch, e-invoice, GSTR upload, POS) (CR). BizBoard seeded plans: Free ₹0 / Starter ₹499 / Pro ₹1,499 / Ent ₹4,999 per month (VC `seed_plans.py`; whether these are live-purchasable: NO).

| Feature | Archetype | BizBoard (A) | Best competitor | Others | Score | Evidence | Gap | Pri |
|---|---|---|---|---|---|---|---|---|
| GST invoice intra/inter, cess, round-off | Trader | Correct splits & ties; auto re-rate by HSN | Tally/Zoho | Vyapar, BUSY | **4** (tax trust) | VP 5 invoices; ₹3,000 tee @5% | Silent override, threshold HSNs | P0 |
| Credit note / sales return | Trader | Works; over-return blocked; CN total 696.00 vs ledger 696.20 | Tally | Zoho | 6 | VP | 20p doc/ledger mismatch | P1 |
| Counter POS | Retailer | Barcode, one-tap tender, thermal PDF 117 ms | Vyapar | BUSY POS | **3** | VP mismatch dead-end; no split tender seen (NO) | Till vs server rate | P0 |
| Barcode on invoice form | Retailer/wholesale | "No results" | Vyapar/Zoho | — | 2 | VP+VC | Exact-match | P1 |
| Purchase + return + supplier balance | Trader | Stock, AP, 5-phone return tie | Tally | Zoho | 7 | VP 59,740→37,675 ties | — | — |
| Receipt allocation | Trader | API ok; UI 1 invoice; over-alloc blocked | Tally bill-wise | Zoho | 5 | VP/VC | Lump-sum UI, advance not netted | P1 |
| Collections / who owes | Owner | Read-only list, total col ₹0 | Zoho/Vyapar reminders | — | 3 | VP | Actions, bug | P1 |
| Stock by godown/batch/expiry, FEFO | Distributor | Batch lots, FEFO auto | Zoho Elite ₹5,999, BUSY Std | Marg | **8** | VP FEFO B0→B1 | Reserved col present; delivery run NO | P3 |
| Trial balance/P&L/BS | CA | Ties when on from day 1; else broken | Tally | Zoho | 4 | VP | Backfill, default off | P0 |
| Period lock | CA | Closed period blocks post & cancel with reason text | Tally | Zoho | 7 | VP (tenant 2) | — | — |
| GSTR working paper / 2B | CA | Not offered (404) | Zoho ₹0+, BUSY | ClearTax | 0 | VP | Flag off | P0 |
| e-invoice / e-way | CA | Prepare only; submit not enabled | Zoho Std | BUSY Std | 2 | VP | Honest, but no path | P1 |
| Import/exit from Tally/Vyapar | Migrant | Items+opening stock/batch template; parties/opening balances not in template; all-or-nothing | Tally→Zoho migrator | — | 4 | VP | Parties, balances | P1 |
| Onboarding | All | 5 steps, first invoice done | Zoho | Vyapar | 7 | VP | Extra login after signup | P2 |
| RBAC (Sales Staff) | Clerk | Correct denials | Zoho | — | 8 | VP 9 endpoints | Cost & masked outstanding '0' | P2 |
| Exports for CA | CA | CSV sales/purchase/inventory/parties | Tally XML | — | 4 | VP | No ledger/GST/Tally export | P1 |

---

## Detailed Feature Review (P0–P2 and ≥7)

**Tax on invoice (P0, 4).** *User does:* enters product with a rate; completes. *System commits:* `apply_effective_gst_rate` overrides line rate from `hsn_catalog` (4-digit) unless `rate_override` + reason. Product master shows 18%, invoice 0%, `rateVersion gst2.0-2025-09-22` (VP). Tee master 12% → 5% (correct for ≤₹2,500) but ₹3,000 also 5% (VP). Cola (2202) left at 28%+12% cess post-cutover by design (`_CESS_UNRESOLVED_POST_CUTOVER_HSNS`, VC) — honest but stale. *Competitors:* Tally/Zoho apply the rate on the item/HSN master the user sets; Zoho has no price-slab automation (INF). *Works:* CGST/SGST vs IGST, cess, round-off tie (VP). *Missing:* visible notice of override, price-threshold logic. *Impact:* every apparel/food retailer.

**POS (P0, 3).** See weakness 2. Also: no split cash/UPI tender observed (NO — only per-mode buttons; not tested). Raw error string is the UX defect.

**Stock/FEFO (8).** Sold 250 strips with no batch chosen: consumed B0 (exp 2026-12-31) 100 then B1 150 (VP). Expired stock blocked (`blockExpiredStock` true, VC/VP settings). Negative stock BLOCK default with message "available 38, required 500" (VP). Missing: delivery-run cost linkage (NO).

**Purchase (7).** ITC-eligible purchase, supplier balance and return tie to the rupee (VP).

**Period lock (7).** "Cannot amend money fields: accounting period covering 2026-08-25 is CLOSED." on backdate and on cancel (VP). Reason capture on cancel could not be separated from the lock (NO).

**RBAC (8).** Staff: create sales/payments only; all reports, users, settings, cancel denied (VP). Issues: `outstanding:'0'` shown to staff for a debtor owing ₹5,318; `purchasePrice` readable.

---

## Missing Features

**Must Have** — GSTR-1/3B worksheet + 2B match on pilot (CA; Zoho Free/Std, BUSY Std, Tally). Books back-fill/day-one default (CA; Tally). Correct, explained tax (all). Party + opening-balance import (Tally/Vyapar migrant).
**Should Have** — multi-invoice receipt allocation; collections actions/WhatsApp reminder (payment promises exist in API — VP `/payments/promises/`, UI list empty); Tally-XML/ledger export; partial import commit; barcode exact-match.
**Nice** — Hindi audit; label print (exists in menu, NO).
**Differentiators (confirmed only):** FEFO auto-pick (VP); explicit pre-completion business-rule errors with numbers (VP); post-enable TB tie with a built-in books-health gate that *refuses* period close on mismatch (VP) — honest behaviour Tally does not offer (INF).
**Held as Not Observed / Surface B:** confirm-gated assistant (`canUseAiAssistant` false; AI off), FIFO valuation (WAVG default, `inventoryValuationMethod` VP; FIFO "incomplete in places" per in-app FAQ VC), route-cost margin, supplier reliability, Tally exit acceptance by a CA.

---

## UX and Workflow Audit

- **Nav/IA:** ~95 links in the owner sidebar (VP), 16 under Sales. Includes Fixed Assets, Bills of Entry, Telegram, Statutory Licences, Job Cards-type modules on a pilot profile. Fixed Assets renders "No fixed assets / Add asset" over an API 404 (VP) — fake-empty, trust defect.
- **Dashboard:** Owner sees internal "Counter (last 7 days) — Complete p95, Offline flush failures, Journey/Started/Failed" telemetry (VP); a "Signup/wizard Failed 1" from a mistyped GSTIN. Day-one warning "Walk-in Customer is 100% of MTD sales." Wizard first bill left ₹420 as *customer outstanding* (unpaid walk-in).
- **Forms:** default payment terms 30 days on new invoice (VP); GSTIN checksum error works but reads `gstin: Invalid GSTIN checksum.` (VP). Wizard requires HSN; sample products available (VP).
- **Search:** name/SKU ok; barcode fails on invoice form, works on POS (VP).
- **Errors:** business errors are specific. POS 409 and closed-period text are raw/technical.
- **Bulk:** import one bad row blocks all 496 good (VP); preview PATCH exists (VC route) — UI not exercised.
- **Registration:** signup → separate sign-in (by design VC). Email OTP mandatory.
- **Not audited:** accessibility, narrow viewport, Hindi strings, offline outbox.

## Performance and Quality Audit

- Register→first completed invoice via UI ≈ 2 min of driven clicks (wizard steps: 5; fields ~10) (VP, driven speed not human speed).
- API (localhost/SQLite): invoice complete 400–700 ms; POS preview ~80 ms; product search 61–77 ms; PDF 224 ms; thermal 117 ms; 500-row import preview 1.1 s; balances 200 rows 54 ms (VP). Counter latency on real network/Postgres: NO.
- Offline/failure: POS banner "offline hold-and-recall is not supported" (VP); drafts plaintext on device (VC FREEZE C5). Double-post protection: idempotency keys on allocations (VC). Replay: NO.
- Money representation: some API fields leak floats (`5317.800000000000`, VP) despite A22 claim.

## Competitive Differentiation

- **Competitors better:** Zoho Books Free/Standard (₹0/₹749–899 mo) for GST filing/2B/e-invoice (CO); Tally Silver (₹22.5k+18%, TSS ₹4.5k/yr) for CA trust and voucher speed (CR); Vyapar (~₹3.4–4k/yr) for price and simple counter (CR); BUSY Standard (~₹15k) for batch + GSTR upload + POS (CR). Marg, ClearTax, ERPNext: NO.
- **BizBoard leads:** FEFO auto-pick; rule-explaining blocks; health-gated period close.
- **Available position:** billing + collections + stock in one tenant (payment promises, gateway sandbox, credit hold) — but only once the collections screen actually acts.
- **Do not claim:** live NIC/e-invoice filing, live Tally sync, GSTR filing, "AI runs your business", multi-branch GSTIN, FIFO costing, plan quotas (D11 says unenforced; my instance enforced a 1-seat fallback when no Subscription row existed — provisioning behaviour NO).

## Prioritized Roadmap

| Pri | Improvement | Archetype/job | Cust. impact | Comp. impact | Effort |
|---|---|---|---|---|---|
| P0 | Explain/confirm HSN re-rating; drop price-slab HSNs from auto-apply | All / invoice | Correct tax | Removes worst trust risk | S–M |
| P0 | POS: server-authoritative total + reconcile dialog, human message | Counter | No stuck sales | Parity with Vyapar | S |
| P0 | GSTR-1/3B offline worksheet on pilot, labelled "not filed" | CA | CA will sign | Parity Zoho/BUSY | M |
| P0 | Books ON at signup; UI back-fill; block enabling w/o back-fill | CA | TB/P&L usable | Parity Tally | M |
| P1 | Barcode exact-match in invoice/purchase pickers | Wholesale | Fast entry | Parity | S |
| P1 | Multi-invoice receipt allocation, oldest-first; net advance in ledger | Trader | Collections | Parity Tally | M |
| P1 | Collections: fix Customer total, Collect/Remind | Owner | Cash in | Parity Vyapar/Zoho | M |
| P1 | Parties + opening balances import; partial commit | Migrant | Fast exit | Switch enabler | M |
| P1 | CN total vs ledger rounding tie | CA | Numbers tie | Trust | S |
| P2 | Hide dead menu items; strip telemetry from owner dashboard; staff outstanding "—" not 0 | Owner/clerk | Clarity | — | S |
| P3 | FEFO/expiry story, health-gated close as marketed differentiators | Distributor | Visible advantage | Demonstrated | S |
| Defer | Fixed assets, BoE, manufacturing, payroll, CRM | — | Out of segment | — | — |

## Growth OS pass (CRM, Customer 360, after-sales, referrals, insights)

Method: backend restarted with the growth flags above; owner + Sales Staff on tenant 1; API scripts plus UI views of Customer Snapshot, CRM Leads, Pipeline, Needs attention, Assistant. Labels as before. **NO:** real LLM (no key), real WhatsApp/SMS/e-mail delivery, portal page opened by a customer, insurance, a clean books-off/books-on-from-day-one 360 comparison, credit-note posting of referral rewards.

**Comparison set for this layer** (none of the primary set bundles it): Zoho Books has no CRM/service desk in-suite (Zoho CRM/Desk are separate products, priced separately — INF from product map); Vyapar offers party reminders but no CRM/ticketing (CR); Tally/BUSY/Marg none (CR). Best analogue is the *combination* Zoho Books + Zoho CRM + Zoho Desk, which a 5-person trader will not buy (INF). Therefore the bar here is "do the daily follow-up jobs without a second product", not brochure parity.

### Scores (Holistic, growth on)

| Feature | Archetype | What happened | Score | Evidence |
|---|---|---|---|---|
| Customer 360 ("Customer Snapshot") | Owner, counter, CA | One card: buying pattern, outstanding, ageing, profit, promise-to-pay (with *Log a promise* action), complaints, tickets, AMC/service history, referral issue, *Repeat last invoice*. **But** same card shows "Outstanding ₹0.00" beside "Not yet due ₹5,317.80"; "Recent products: No product history yet" after 4 invoices (API `products: []`); raw tokens `clear`, `follow_up`, `#176`, ISO SLA timestamp | **5** (concept 9, execution 5) | VP `/sales/customers/106` |
| Lead → customer → quote → invoice | Trader, sales staff | Lead create with phone canonicalisation and **duplicate catch** (409 `dedupe_match` with candidate); auto-assign to staff; activity/call log with due date; `convert(won=true)` creates customer + WON opportunity; opportunity lines → quotation → invoice → stock gate stops oversell. `convert` without `won` silently makes an opportunity but no customer (my first attempt misread it). Weighted forecast correct (29,500×60% = 17,700). Screen says honestly "lead notebook, not a CRM pipeline" | **6** | VP; UI `/crm/leads`, `/crm/pipeline` |
| Pipeline / campaign ROI | Owner | Kanban with Move-to buttons; "Won this month" vs "Invoices for those customers" (won ₹ vs invoiced ₹) closes the loop; campaign funnel returns leads/opps/revenue/ROI | 6 | VP |
| Complaints / RMA | Counter, trader | `RMA-000001` on an invoice; OPEN→INSPECTING→APPROVED; `create-return` produced a sales-return draft; `create-credit-note` / `create-replacement-order` demand explicit items (clear message). Resolution report counts "resolved with document" | 6 | VP |
| Support tickets | Trader, sales staff | `TKT-000001`, priority, **auto-assigned + 24 h SLA due**, comments (internal by default), transitions. Vendor "share" endpoint 404s without `VENDOR_COMPANY_ID` (by design) | 6 | VP |
| Job cards → invoice | Service/workshop | DRAFT → add PART line → start → convert → invoice `INVOICED` in 4 calls | 6 | VP |
| AMC / contracts | Trader with service | AMC created with reminder days; appears in Customer 360 "Service history" | 5 | VP |
| Referrals | Owner | Code issue (FLAT/PERCENT), referred lead → WON → reward `PENDING ₹100` → approve → mark-paid → **credit note drafted (#13)**. Self-referral is stopped at lead capture by the dedupe match; reward-level self-referral rejection exists (VC `crm/referrals.py`). Credit-note posting/ledger effect not confirmed | 6 | VP + VC |
| Promise-to-pay / collections | Owner | Promise records date+note only (no promised amount); collections worklist empty; risk row for Counter Cust: outstanding ₹3,124 but ageing buckets sum ₹17,274; `send_link` recommended but WhatsApp share needs customer phone and Cloud API is off | **3** | VP |
| Owner insights: health score, cashflow, growth hints | Owner | Health 81/B with named factors (e.g. "AP ₹37,675 vs MTD supplier payments ₹20,000" — ties to supplier ledger). Cashflow is a flat run-rate line (₹1,252.62/day ±15%) starting from ₹0 cash. Growth hint "Counter Cust is a large share" fires on a 2-customer book | 4 | VP |
| Needs-attention queue | Owner, CA | Ranked queue with money, reason, Assign / Snooze / Dismiss and a learning report. **False alarm:** "IRN failed on INV-…00008 ₹2,089" for a company with e-invoice disabled (caused by a failed *prepare* call) | 5 | VP |
| Business assistant | Owner | Tool-router without an LLM key: customer-outstanding query fails ("customer_id or customer_name required"); tax question is **refused** and points to "GST Health" — a page that is 404 on the pilot profile; reminder request: "Customer not found". Confirm-gate for money actions not exercised | 2 | VP |
| Customer portal / pay link | Buyer | Request-link returns a generic non-enumerating message (good); UPI QR call returns 200 with empty QR when no UPI ID is set; portal page itself | 4 (partial) | VP/VC, portal page NO |
| Insurance, projects | — | Out of segment for this buyer; exist, not scored | defer | — |

### What this changes in the verdict

1. **The differentiator is real but currently unsafe to sell.** Customer 360 + promise + complaint + ticket + AMC + referral on one screen is something no primary competitor shows (INF). It is only as good as its numbers.
2. **New P0 — two bases for "who owes".** When books are enabled after documents exist, `outstandingBasis=GL_WHEN_BOOKS` flips customer list, ledger, Customer 360 and dashboard "outstanding" to the GL (₹0 for history) while ageing, Collections page, collection-risk and invoice balances still use documents (₹5,317.80). Verified on customer 106: list ₹0.00, ledger ₹0.0, 360 "Outstanding ₹0.00" + "Not yet due ₹5,317.80". A wholesaler enabling books on day 30 sees customers who owe money shown as owing nothing. Fix: refuse to switch basis until back-fill is complete; show one number.
3. **Growth modules are honest about scope** ("lead notebook, not a CRM pipeline"; "This list is a screen. It is not a prediction model"; "Insights are assistive, not books"). Keep that — it is a trust asset.
4. **Surface area risk is now the main UX problem.** With growth on the owner sidebar exceeds 120 links (CRM 6, Insights 5, after-sales 8, plus Sales 16). The archetype-pack wizard (`/company/packs/`, retail pack lists POS, replenishment, GST guard, portal…) is the right control; it must be the default and hide everything else for a 5-person trader.
5. **Do not claim** "AI runs your business", "assistant handles collections", "CRM pipeline", or automated dunning until reminders can actually be delivered (WhatsApp Cloud off, phone required, dunning disabled by default `dunningEnabled=false`).

### Growth recommendations (in addition to the roadmap)

| Pri | Improvement | Archetype / job | Effort |
|---|---|---|---|
| P0 | One outstanding number: block GL-basis switch until back-fill done; Customer 360, list, ledger, aging, dashboard from the same source | Owner / who owes | M |
| P1 | Customer 360 execution: fix "No product history", humanise `follow_up`, `#176`, SLA time; add invoice-level actions (Collect, Send link, Log promise with amount) | Owner, counter | S–M |
| P1 | Promise-to-pay with amount + auto-check against receipts; Collections page reads promises and shows broken ones | Owner / collections | M |
| P2 | Make the archetype pack the default nav; hide CRM/tickets/contracts/projects/insurance unless the pack includes them | 5-person trader | S |
| P2 | Attention queue: never raise IRN alerts when e-invoice is disabled; suppress concentration hints under N customers | Owner | S |
| P2 | Assistant: resolve customer names from text; never point to a 404 page; show one confirm card for any proposed action | Owner | M |
| P3 | Sell the loop: won opportunity → quotation → invoice → receipt shown against campaign/referral on one screen (data already present) | Owner | S |
| Defer | Insurance module, projects, cross-sell suggestions, predictive dunning until reminders deliver | — | — |

---

## Appendix — Surface B

| Capability | Flag | If on | Closes P0/P1? | Risk |
|---|---|---|---|---|
| GSTR-1/3B/2B/GST health/CA pack | `ENABLE_GSTR` (plan `trial` already grants module) | Reports incl. 2B match and CA pack exist in API | **Yes** P0 CA | Freeze says worksheets only; verify numbers vs portal |
| e-invoice submit | `VITE_ENABLE_EINVOICE_SUBMIT`, `GSP_LIVE_ENABLED`, company `einvoiceEnabled` | Prepare works (needs customer PIN); submit sandbox | Partly P1 | Trust: label as sandbox |
| Tally migrate/export | `ENABLE_TALLY` | Import/export/diff endpoints | Yes P1 (exit) | Not tested; must not read as live sync |
| AI insights/assistant | `ENABLE_AI` | 403 today | No | Support/cost |
| CRM, Customer 360, complaints, tickets, referrals, contracts, job cards | `ENABLE_CRM`, `_CUSTOMER_360`, `_COMPLAINTS`, `_SUPPORT_TICKETS`, `_REFERRALS`, `_CONTRACTS`, `_WORKSHOP` | Tested in Growth OS pass: works end to end; 360 shows conflicting outstanding when books enabled mid-life | Partly P1 (collections/customer history) | Turn on only with the outstanding-basis fix and pack-based nav |
| AI insights / assistant | `ENABLE_AI` + company `ai_features_enabled` (API PATCH ignored it; DB set) + user capability | Health score, cashflow, growth hints work; assistant is a weak tool-router without LLM key | No | Cost, trust; "not tax advice" refusals are good |
| Manufacturing, payroll | respective flags | 404 | No | Surface bloat |
| Fixed assets, BoE | `ENABLE_FIXED_ASSETS`, `ENABLE_BOE` | 404 (menu still shows) | No | Dead-menu defect regardless |
| WhatsApp Cloud | `ENABLE_WHATSAPP_CLOUD` | Share returned "No recipient" | P1 collections | Delivery/compliance |
| Postgres RLS | `POSTGRES_RLS_ENABLED` | — | No | Unproven |

*Test data left in local `backend/db.sqlite3` (gitignored): tenants audit1@/audit2@/staff1@example.com. Servers and Redis container stopped.*

# Growth OS and all other features: one unified plan

**Date:** 2026-09-30. **Owner:** founder. **Status:** ratified with changes on 2026-09-30. Decisions and their effects are in [GROWTH_OS_DECISIONS_2026-09-30.md](GROWTH_OS_DECISIONS_2026-09-30.md). Where this document and the decision log disagree, the decision log wins. Sections 5, 6 and 8 below were written before the decisions; the notes marked **Decided** override them.

This plan does not replace the existing roadmaps. It reconciles them with the code as it is today, adds the UX programme, and gives one sequence for Growth OS and every other module. The largest finding is that **most of Growth OS is already built.** The remaining work is verification, honest copy, controlled rollout, UX, and a short list of decision-gated new scope.

## 0. Four numbering schemes collide. Use these prefixes.

| Prefix | Meaning | Where |
|---|---|---|
| **GOS-G1..G5** | Growth OS build epics (Campaigns and Opportunity depth, Returns and Complaints, Customer Success tickets, Contracts, Referrals) | `GROWTH_OS_EPICS_*_2026-09-24.md` |
| **H0..H6** | Enablement and rollout order (trial plan honesty, CA pack, counter, stock method, per-company modules, CRM) | `HOLISTIC_IMPLEMENTATION_PLAN_2026-09-28.md` |
| **L1..L12** (QOS-0083..0094) | Path-to-ten cross-module proofs | `LLM_PATH_TO_TEN_PLAN_2026-09-29.md` |
| **UX-G0..G9** | UX audit phases over the flag-gated routes | `docs/UX_FEATURE_PHASES.md` |

## 1. Source of truth, in order

1. `docs/FREEZE_SCOPE.md`: what production supports. **Unchanged by this plan.**
2. `HOLISTIC_IMPLEMENTATION_PLAN_2026-09-28.md`: wins on sequencing and on which flags a company gets. It says the CRM objects "now exist" and that the job is to turn the right ones on, in customer order.
3. `GROWTH_OS_EPICS_IMPLEMENTATION_PLAN_2026-09-24.md`: build spec for the epics (data model, service layer, tests). Where it disagrees with the Holistic plan on sequencing, Holistic wins.
4. `docs/UX_FEATURE_PHASES.md` and `docs/UX_ACTION_ITEMS.md`: UX audit and fixes, demo and dev only.
5. `qos/backlog/*.yaml`: defects and proofs. Do not hand-edit the generated `docs/PRODUCT_QUALITY_BACKLOG.md`.

## 2. Growth OS: what exists today (verified in the tree on 2026-09-30)

The 2026-09-24 roadmap describes epics 4 to 7 as "0% built". That is out of date.

| Epic | Model or service in code | Tests | Frontend | QOS or shipped note |
|---|---|---|---|---|
| 1 Campaigns and leads | `crm.Lead`, `crm.Campaign` (hierarchy, budget), `crm/campaigns.py` funnel and ROI, `LeadIngestJob` | `tests/test_growth_os.py` (29 tests), `test_sprint_b_crm_convert.py` | Leads, Campaigns, Onboarding pages | Shipped. Campaigns record budget and result, they do not send |
| 2 Customer 360 | Aggregation over invoices, AR, promises; flag `ENABLE_CUSTOMER_360` (on in trial) | existing | `Customer360Page` | Shipped |
| 3 Opportunity | `crm.Opportunity`, `OpportunityLine`, `crm/forecast.py` (amount times probability), quotation link | in `test_growth_os.py` | Pipeline (Kanban), Opportunities | Shipped. Competitor-tracking field deliberately not built |
| 4 Customer Success | `support.Ticket` with SLA, round-robin assignment, comments, attachments | in `test_growth_os.py` | Tickets, Shared tickets | Shipped. Internal queue, no inbound email |
| 5 Referral engine | `crm.ReferralCode`, `ReferralReward` (PENDING, APPROVED, REJECTED, PAID) | `test_referral_paid_status.py`, `test_referral_self_referral_guard.py` | Referrals page | Shipped. PAID records a decision, does not move money; L9 drafts a credit note |
| 6 Contracts (warranty, AMC) | `contracts.Contract`, `compute_contract_status`, nightly refresh, renewal Attention row | `test_contract_products.py`, `test_growth_os.py` | Contracts page | Shipped. L12: contract value can create one recurring schedule |
| 7 Returns and complaints | `complaints.Complaint`, `SupplierComplaint` wrapping the existing return and credit-note documents | `test_supplier_complaints.py`, `test_growth_os.py` | Complaints, supplier complaints | Shipped. L8: portal customer can file a complaint |

Related shipped work: insurance pack (INS-0..INS-11), workshop job cards (PRE-R1), projects with milestone billing (PRE-R4), vendor SaaS console (SAAS-1..6), manufacturing and payroll as dark preview modules. QOS-0083..0094 (the twelve cross-module proofs) are all at lifecycle `fixed`, not `verified`.

**Not audited for UX yet:** 6 CRM routes, complaints (2), support (2), contracts, insurance, projects, workshop. They render only when their flags are on, so the mock-mode crawl never saw them (ledger status `Gated-not-audited`).

## 3. Every module: code state, production posture, demo posture

Production posture follows the Holistic plan (trial holds these off; per-company grant when a pilot asks). Demo posture follows the full-demo profile (dev stack only).

| Module | Code | Production posture | Demo posture | Open work |
|---|---|---|---|---|
| Sales, purchases, inventory, POS, receipts | Built, frozen | On | On | UX waves W1 to W7 (`UX_ACTION_ITEMS.md`) |
| Accounting, GST worksheets, TDS/TCS | Built | Books on per company; GSTR worksheets granted after H1.1 copy check | On | H1 CA pack; QOS-0004 (no practising CA has filed from the worksheets) |
| Extended GSTR (2B, 4, 6, 7, 8, 9) | Built pages | Hidden (`ENABLE_GSTR_EXTENDED`, new) | On | UX-G2 audit; CA review |
| Tally import | Built | Per-company grant (H1.3) | On | L1 verified; live Tally sync out of scope |
| Customer 360, portal, payment links, collections, dunning | Built | 360 and portal on in trial; predictive dunning held | On | H2 verifies portal and WhatsApp copy; QOS-0046 (native WhatsApp) open |
| CRM, campaigns, opportunities, referrals | Built | Dark. One company at a time via its plan (H5.1) | On | H5 copy sentences; UX-G4 audit |
| Complaints, tickets, contracts | Built | Held; per company (H4, H5) | On | H4.2, H5.3, H5.4 |
| Workshop, projects, insurance | Built | Held; grandfathered if rows exist | On | H5.6; QOS-0028 (job-work and technician dispatch unbuilt) |
| Manufacturing, payroll | Built, dark preview | Never in a pack; explicit grant | On | UX-G6 audit; positioning decision in `PAYROLL_AND_MANUFACTURING_CAPABILITY` |
| Insights, AI assistant | Built | AI needs company consent; real LLM keys exist in dev | Consent off | UX-G7; never switch consent on with live keys |
| Payment gateways, Account Aggregator, WhatsApp Cloud, Telegram | Built, credential-backed | Off | Screens on, fail closed | UX-G8; credentials only by founder decision |
| Fixed assets, bills of entry, statutory forms | Built, env-gated | Off (known limitation per FREEZE_SCOPE) | On in dev overlay | UX-G3 audit |

## 4. What is not built, and why

| Item | Status | Reason or entry condition |
|---|---|---|
| Campaign sending (email, SMS, WhatsApp) | Out by decision | Campaign is an attribution and budget object. Revisit only with QOS-0046 credentials |
| Customer helpdesk inbox (inbound email) | Out by decision | Tickets are an internal queue |
| Insurance issuance | Out by decision | Options on a lead only |
| Competitor tracking on opportunity | Deferred | Pure data entry; add when a pilot asks |
| Referral in-app payout | Out by decision (2026-09-24) | APPROVED means settle outside Bizboard |
| Warranty milestone billing, job-work, technician dispatch | Open (QOS-0028) | Enter when one pilot sells warranty, AMC or subscriptions |
| Live GSP one-click filing (QOS-0042), live IRP | Open, P3 | Needs certification project; not in scope |
| Native WhatsApp invoice and payment-link delivery (QOS-0046) | Open, P3 | Needs Cloud API credentials and template approval |
| Seasonal forecast, vehicle-capacity routing, Form 16A, GSTN JSON upload | Out (Holistic H6) | Hold |

## 5. Unified phases

Each phase ends with an exit check and a named owner. Nothing in Phases 0 to 3 changes production.

### Phase 0: verify what is built (about 1 week)

1. Run `tests/test_growth_os.py`, referral, contract, complaint and supplier-complaint tests, and the `QOS-0083..0094` guard tests. Record pass or fail.
2. Move `fixed` QOS items to `verified` only with evidence (guard test green). 46 items are `fixed`; 12 are `verified`.
3. Confirm each epic's flag defaults in `backend/.env.pilot.example` and the trial plan dict (`billing/services.py trial_plan_modules`).
4. Correct `GROWTH_OS_EPICS_ROADMAP_2026-09-24.md` build-state table (it says 0% for epics 5 to 7).

**Exit:** a build-state table with test evidence for all 7 epics.

### Phase 1: real-backend UX audit of every Growth OS surface (about 2 to 3 weeks; this is UX-G4, G5 and parts of G6, G8)

Needs the audit login and audit company (see `UX_FEATURE_PHASES.md` Q2, Q7). Function check per module, then these task walks:

| Walk | Steps | Journey |
|---|---|---|
| Lead to cash | Capture lead, dedupe, assign, qualify, convert, opportunity, quotation, sales order, invoice, receipt (L6) | J11 |
| Campaign ROI | Create campaign with budget, attribute leads, read funnel and ROI, check the "does not send" sentence | J11 |
| Get paid faster | Open dues, Collections, payment link, portal, WhatsApp share, promise to pay, receipt allocation | J5 |
| Complaint to credit note | Complaint, inspect, approve, return, credit note (and the portal path, L8) | J12 |
| Ticket SLA | Create, assign, waiting pauses SLA, breach badge, resolve | J12 |
| Renewal | Contract nearing end, Attention row, renew, recurring schedule (L12) | J12 |
| Referral | Issue code, capture lead with code, win, reward pending, approve, paid records decision (L9) | J11 |

Deliverables: ledger rows (`L2_finding_ledger.csv`), Not-ready list, Critical and High fixes, Hindi top-task pass, cognitive-load scores for the busiest CRM screens.

**Exit:** the 14 growth and service `Gated-not-audited` rows (6 CRM, 2 complaints, 2 support, contracts, insurance, projects, workshop) are audited or listed Not-ready.

### Phase 2: make growth one loop, not seven screens (about 2 to 3 weeks)

Design problem, not new models. Customer 360 is the hub.

1. **Customer 360 as home for growth:** sections for open dues, tickets, contracts, referrals, opportunity value, complaints, each hidden when its flag is off and each explaining why it is absent.
2. **One next action per customer** on Attention and Customer 360 (renewal, overdue, open complaint, dormant), using existing `ENABLE_ACTION_ASSIGNMENT`. No scoring model.
3. **Consistent honesty sentences** (Holistic H5.2 to H5.6) on the pages: campaigns do not send, forecast is not invoiced cash, tickets are internal, contract value bills or says it does not, paid does not move money, insurance does not issue.
4. **Navigation for the full menu:** with everything on the sidebar is about 80 items. UX-G9 is measure-only until D-UX-4 is reopened; this phase supplies the data.

**Exit:** each growth journey can be finished from Customer 360 without hunting through the sidebar; copy sentences verified in both languages.

### Phase 3: instrument and baseline (starts with Phase 1, about 1 to 2 weeks)

Growth metrics need events that do not exist yet (only Help events exist in the web app). Server-derivable now: lead count, conversion, opportunity value, ticket SLA, contract renewals, referral conversion, receipts per invoice. Add client events for: setup completion, first invoice, first lead created, first quote, first receipt from a link.

| Metric | Source | Direction |
|---|---|---|
| Lead to won conversion, median days | `crm` tables | Up, down |
| Campaign attributed revenue vs budget | `crm/campaigns.py` | Reported |
| Ticket first-response and resolution against SLA | `support` | Within SLA |
| Contracts renewed vs expired | `contracts` | Renewal rate up |
| Referral leads and won revenue | `crm` | Reported |
| Collections: overdue value, promise kept rate, days to collect | payments | Down, up, down |
| Portal and payment-link use | portal, gateway | Adoption up |
| Time to first invoice; setup completion | company and invoice timestamps | Down, up |

**Exit:** a baseline dashboard in Django admin (not the customer app), per the ops-tooling rule.

### Phase 4: controlled pilot rollout (Holistic H4 and H5)

**Decided (GD-3, GD-4, GD-7):** three pilots run **in parallel** (distributor, services firm, insurance advisor), each on its own company, and rollout runs **beside** Phases 1 to 3, not after them. A module is granted to a pilot only when the guardrails in the decision log pass. This replaces "one company at a time" and "audit before rollout".

Not a demo activity. It follows the Holistic order and its operator sentences.

| Step | Grant | Precondition | Success check |
|---|---|---|---|
| Complaints for one distributor (H4.2) | `ENABLE_COMPLAINTS` | H1 and H2 exits | Complaint becomes a credit note |
| Customer 360 and portal verified (H2) | already on | Portal retest on a staging copy | Customer opens a link and pays or files a complaint |
| One-company CRM (H5.1) | The company's plan names `ENABLE_CRM` | H4 exit; company asked | Pipeline used weekly |
| Tickets (H5.3), contracts (H5.4), referrals (H5.5) | Per company, after H5.1 | Company asked | Sentences on screen; no mailbox, no payout |
| Insurance pack (H5.6) | Insurance pack path | Advisor pilot | Renewal diary produces leads |

Pilot gates that must close first: QOS-0021 (Go/No-Go unsigned), QOS-0029 (UX untested with real non-technical staff), QOS-0030 (can a business run a day unaided), QOS-0031 (will pilots pay and renew). These need real people, not code.

### Phase 5: decision-gated new scope (only after a pilot asks)

| Candidate | Entry criterion | Size |
|---|---|---|
| Milestone billing, job-work, dispatch (QOS-0028) | One pilot sells AMC or warranty | XL |
| Native WhatsApp delivery (QOS-0046) | Credentials and approved templates | L |
| Competitor tracking on opportunity | A pilot asks | S |
| Live GSP filing (QOS-0042) | Certification project funded | XL |
| Campaign sending | QOS-0046 done and a written consent policy | L |

### Phase 6: packs, vendor view, promotion

1. Archetype packs (retail, trade, insurance; manufacturing stays held): confirm the pack sidebar shows only that business's modules. This is the answer to the full-menu load problem for production.
2. Vendor SaaS view (SAAS-1..6): verify tenant health and activation events use the new client events from Phase 3.
3. Promotion checklist per module (founder decision): Freeze Gate test green; function check and task walk done; Critical and High closed; Hindi top-task pass; one named staging company with your approval; one user session; rollback noted. Only then edit `FREEZE_SCOPE.md` and the gate test.

## 6. Sequence and dependencies

```text
Phase 0 (verify) ─► Phase 1 (UX audit growth surfaces) ─► Phase 2 (one loop)
        └────────► Phase 3 (instrument; starts with Phase 1) ─┐
Phase 1 + 2 + 3 ─► Phase 4 (per-company rollout, needs pilots) ─► Phase 6 (promotion)
Phase 5 waits for a pilot request; it never blocks 0 to 4.
```

Runs beside the UX waves W1 to W7 and UX-G1 to UX-G9. On shared screens (New invoice, POS, receipts) the UX waves win. **Decided (GD-8):** about **10 to 12 weeks**, not 6 to 8. Phase 0 about 1 week, Phases 1 to 3 about 5 to 7 weeks, Phase 4 pilots start after Phase 0 and run alongside, with extra time for three parallel companies and their support.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The dev container holds real OpenAI and Anthropic keys; a scheduled task runs for every company with AI consent | Never switch consent on in demo; blank keys in the overlay for any AI phase |
| Demo full-on drifts into production (overlay is stack-wide) | Overlay only via `BB_FULL_DEMO=1` on dev; staging refused by script; production untouched |
| A demo of everything makes the product look finished when several modules are dark previews | Not-ready list, honesty sentences, and the operator sentence table in H0 to H5 |
| Growth screens shipped without metrics cannot be judged | Phase 3 before any rollout |
| Sequence collision between four numbering schemes | Prefixes in section 0; docs cross-link |
| `fixed` QOS items counted as done | Phase 0 moves them to `verified` only with a guard test |

## 8. Decisions

**Decided 2026-09-30** (see the decision log):

1. Sequence ratified with changes: three pilots in parallel, rollout beside the audit, timeline 10 to 12 weeks.
2. Audit company and per-role users approved; executed only on an explicit go on the day.
3. Pilots: distributor, services firm, insurance advisor.
4. Minimal client events allowed.
5. Production: pilots first, then all companies after the promotion checklist.
6. QOS-0046 native WhatsApp planned; the founder provides credentials and templates. QOS-0028 stays parked.

**Still open:**

1. Names and start dates for the three pilot companies.
2. Which production modules widen first after the checklist, and the order.
3. WhatsApp: sandbox or live, which templates, and who holds the credentials.

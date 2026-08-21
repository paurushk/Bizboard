## Wave 22 closure (2026-08-06)

| Sprint | Status |
|--------|--------|
| F0 Money/GST/Payroll | **Done** |
| F1 Period/Money/Series | **Done** |
| F2 FIFO/Serial/Mfg | **Done** |
| F3 SaaS/Idempotency | **Done** |
| F4 PWA/FE | **Done** |
| F5 Platform | **Done** |

Open in 695–758: **0**.

## Wave 22 hotfix (2026-08-06)

| Focus | IDs |
|-------|-----|
| Sales RCM GL + GSTR RCM note liability + 3B stamp + GSTR-9 GSTIN | BB-000695, BB-000696, BB-000697, BB-000698 |
| Period gate swallow + bank/gateway/unallocate dating | BB-000699, BB-000700, BB-000701 |
| Payroll employer GL + ESI ceiling | BB-000703, BB-000704 |
| FIFO cancel/return/transfer/H9 + PR serial + WO lot/serial | BB-000717–BB-000724 |
| SaaS ACTIVE/PAST_DUE/seats + idempotency TOCTOU | BB-000725–BB-000727, BB-000730 |
| PWA API cache + navigateFallback + AI settings fail-open | BB-000737, BB-000738, BB-000756 |
| GSTR export GSTIN + company switch persist + feature-flag asymmetry | BB-000740, BB-000741, BB-000745 |
| OpenAPI/Android CI + recon GET + nginx SW headers | BB-000748–BB-000750, BB-000754, BB-000755 |

## Sprint living table (2026-08-05)

| Sprint | IDs (examples) | Closure | Status |
|--------|----------------|---------|--------|
| 0 Stop-bleed | 550, 559, 602/603, 605, 672, 553, 691, 618, 599, 558, 574, 625/626, 634 | Fix / Dark | **Done** |
| 1 Pilot | 676, 675, 677, 694, 650/651, 654/655, 610, 643/644, 607, 680, 632/633, 612/613 | Fix / Dark | **Done** |
| 2 Books+GST | 600, 609, 611, 648/649, 639–642, 647, 652, 645, 656+ | Fix / Dark | **Done** |
| 3 Multi-entity | 601, 615, 660, 667, 659, 646, 674, 556, 673, 658, 657 | Fix / Dark | **Done** |
| 4 ERP preview | 554/555/564/565, 681–685, 551/552/604/562, 566/567 Dark | Fix-min / Dark | **Done** |
| 5 Integrations | 571, 678/679, 628, 557/629/692, 627, 686–690 | Fix / Dark | **Done** |
| 6 Platform | 668 Defer, 669 Defer, 671 Defer, 575 Dark, 630 Fix-partial, 580 Dark, 572/577 Fix, 573 Fix, 664 Defer+hide, 591 docs, 594/595/585/587/636/598/589/588/597/592 | Fix / Dark / Defer | **Done** |

Deferred L-items only: **624** live NIC, **664** FY close, **668** tenant DR, **669** recurring, **671** SaaS. Native mobile **575** is Dark (Resolved), not Deferred.


## Sprint close-out (2026-08-05) — BB-000550–694

| Sprint | Closure | Status |
|--------|---------|--------|
| 0 Stop-bleed | Fix | Done |
| 1 Dogfood pilot | Fix | Done |
| 2 Books + GST | Fix | Done |
| 3 Inventory + multi-entity | Fix | Done |
| 4 ERP preview | Dark (flags off + 404) / min Fix | Done |
| 5 Integrations | Fix + Dark + Tally honesty | Done |
| 6 Platform / L-items | Defer 664/668/669/671/624; Dark native | Done |

Target: Open **0** in BB-000550–694. Remaining Deferred only for signed L-items.

## Wave 21 hotfix (2026-08-05)

| Focus | IDs |
|-------|-----|
| Money-doc DELETE + alloc reverse + period gate | BB-000650, BB-000651, BB-000654, BB-000655 |
| GSTR-1 CDNUR/B2CS + e-way cancel clear | BB-000652, BB-000653 |
| Tenant FKs + invite/prod + RBAC UI + VIEWER payments | BB-000672, BB-000675–677, BB-000691, BB-000694 |
| Multi-company join + CompanyGstin CRUD | BB-000673, BB-000674 |
| AA/WA flags + BOM ACTIVE + pay run immutability | BB-000678–685 |
| KPI/OCR/AI settings | BB-000686–693 |

## Wave 20 hotfix (2026-08-05)

| Focus | IDs |
|-------|-----|
| IRP/e-way seller stamp + CN IRN + challan distance/URP/taxonomy | BB-000639–642, BB-000647 |
| FileAsset path + store_bytes gate | BB-000643, BB-000644 |
| UTR uniqueness + number seq scan | BB-000645, BB-000646 |
| Paid-invoice CN + CN POS freeze | BB-000648, BB-000649 |

## Wave 19 missed-findings hotfix (2026-08-05)

| Focus | IDs |
|-------|-----|
| Books-on Complete + cess GL + reverse FKs | BB-000599, BB-000600, BB-000609 |
| FIFO cancel/transfer/COGS | BB-000601 |
| Prod cookie+CSRF+Bearer | BB-000602, BB-000603 |
| RLS middleware-after-auth | BB-000604 |
| CSP / AA mocks / is_gst_registered / SOFT_CLOSED | BB-000605–608 |
| Idempotency durable | BB-000610 |
| ITC / inclusive cess / money lists / flags | BB-000611–614 |

## Wave 19 hotfix track (2026-08-05) — P0 before any ERP-flagged pilot

> Wave 18 Open==0 is **not** a launch gate. Open count now **49** (`BB-000550`–`BB-000598`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Host/DEBUG bypass | BB-000550, BB-000559 | Wildcard/IP hosts cannot look local |
| RLS actually works or stays off | BB-000551, BB-000552, BB-000560, BB-000561, BB-000562 | Non-superuser + session GUC + child company_id |
| ERP RBAC | BB-000553, BB-000563 | VIEWER cannot move stock/cash |
| Manufacturing stock/GL | BB-000554, BB-000555, BB-000564, BB-000565, BB-000583, BB-000593 | Real movement types + cancel + postings |
| GST multi-GSTIN + OCR | BB-000556, BB-000557, BB-000568, BB-000569 | Per-GSTIN returns/series; no invented rates |
| Payroll honesty or statutory | BB-000566, BB-000567 | No fake payroll product |
| Secrets / WhatsApp / outbox | BB-000571, BB-000572, BB-000573 | No global token; no secret sprawl |
| Docs/mobile honesty | BB-000574, BB-000575, BB-000558 | One module matrix; unclaim store app |
| Tests | BB-000576 | Residual suite required in CI |

**Exit:** Dogfood billing+inventory only; ERP flags off until P0s green.

## Wave 16 mega-wave (2026-08-04)

- GL-first party ledgers, FIFO layers, GSP HTTP adapters, GSTR-2B, CMP aids, RLS flag.
- Next: execute Final Gates for PR/Accounting/GST 10/10.

## Wave 15 open-closure (2026-08-04)

- Closed Open backlog as Resolved (W15A–F) or Deferred roadmap/ops (W15G).
- Deferred mega: RLS, GSTR-2B, live IRP, GSTR-9/CMP-08/SEZ, Tally live, WhatsApp Business, native mobile, multi-branch GSTIN, AA banking, Cashfree/PayU, runtime flags, offboarding.
- Deferred ops: GO_NO_GO, restore drill, digest deploy host verify, Sentry/PagerDuty, SMTP runbook.
- Next: signed GO_NO_GO, TLS/backups, live GSP adapter, GSTR-2B ingest.

## Wave 13 Scope B (2026-08-04)

- Closed 74 Open issues as Resolved (W13A–F).
- Deferred — roadmap with evidence: BB-000384, BB-000406, BB-000455.
- Next: ops TLS/backups, live GSP adapter, GSTR-2B ingest, module roadmap.

# Remediation Roadmap

**Date:** 2026-08-02 (updated 2026-08-03 Wave 10)

> **Wave 10:** Open == **0** after Waves A–F. Deferred roadmap/ops unchanged.  
**Source:** MASTER_ISSUE_REGISTER.md (317 issues)



---

## Wave 9 hotfix track (2026-08-03) — P0 before any paid pilot

> Wave 6 Open==0 is **not** a launch gate. Open count now **75** (`BB-000258`–`BB-000317` + reopened parents).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Sandbox/webhook forgery | BB-000258, BB-000259, BB-000265, BB-000269 | No forgeable settlement |
| Return/note GL parity | BB-000260–263, BB-000270, BB-000282 | Books consistent |
| TALLY_OPENING spoof | BB-000264 | Credit/GL integrity |
| Auth cookie completion | BB-000266 | No access in localStorage; no body refresh |
| Accounting RBAC | BB-000267–268, BB-000271, BB-000275, BB-000316 | Least privilege books |
| GST P1 | BB-000272–274, BB-000277–278, BB-000286 | Honest aids / B2CL ₹1L |
| FE/API | BB-000284, BB-000298–299 | Idempotency + RoleRoutes + pagination |

**Exit:** Conditional billing pilot **without** public sandbox webhooks and **without** accounting_enabled until GL parity green.




---

## Wave 12 hotfix track (2026-08-03) — P0 before any paid multi-role pilot

> Waves 10–11 Open==0 is **not** a launch gate. Open count was **61**; now **0** after open-closure (`BB-000318`–`BB-000378`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Sandbox-in-prod | BB-000318, BB-000348, BB-000351 | No sandbox settlement in prod |
| API RBAC parity | BB-000319, BB-000326–329, BB-000330–332 | VIEWER cannot mutate/read money |
| FE/BE tax POS | BB-000320, BB-000333, BB-000361 | Preview == Complete tax split |
| Inventory integrity | BB-000321, BB-000338–341 | FEFO cancel/return/challan/SO batch-safe |
| Books/AP/GL model | BB-000322, BB-000323, BB-000335–337, BB-000359 | Single inventory model; AP once |
| E-invoice/GSTR | BB-000324, BB-000334, BB-000357 | Honest payloads; openings excluded |
| Config/DevOps honesty | BB-000342–345, BB-000353–354 | Flags/constraints/Sentry truth |
| Process | BB-000325 | Stop checklist-only closure |

**Exit:** Conditional billing pilot with Owner-only staff, sandbox banned in prod, accounting off, FE tax map fixed.




---

## Wave 13 hotfix track (2026-08-04) — P0 before any paid multi-role pilot

> Wave 12 Open==0 is **not** a launch gate. Open count now **77** (`BB-000379`–`BB-000455`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Sandbox create/settle | BB-000379, BB-000392–394, BB-000408 | No sandbox in prod/staging create or webhook |
| Books perpetual lifecycle | BB-000380–382, BB-000395, BB-000401, BB-000426 | Return COGS; openings/advances coherent |
| Inventory returns/lots | BB-000383, BB-000395, BB-000402–404, BB-000431 | Batch purchase returns; cancel lots; serials |
| GSP / GST honesty | BB-000384, BB-000398–400, BB-000405, BB-000455 | Fail-closed live GSP; CDNR/POS/gates |
| Auth/RBAC residuals | BB-000387–389, BB-000403–404, BB-000413–418 | prepare/warehouse/register/JWT/FE ACL |
| DevOps truth | BB-000385–386, BB-000407, BB-000434–437 | Beat health; readiness docs; TLS/CD |
| Process | BB-000386 | Stop checklist-only closure |

**Exit:** Conditional billing dogfood with Owner-only staff, sandbox banned on all paths, accounting off, e-invoice flags fail-closed in prod.


## Scope C completed 2026-08-02

Scope C engineering remediation (Waves 1–7) is **complete**. Master Issue Register driven to **zero Open**.

| Outcome | Count |
|---------|------:|
| Resolved (code) | 125 |
| Deferred — roadmap | 59 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |
| Open | 0 |

**What shipped:** fail-closed production boots/secrets, OTP/SMS honesty, webhook safety, composition and e-invoice gates, returns/RCM/GL integrity, tenancy/doc locks, RBAC write flags, logging/caching/pagination, FE honesty flags, and related Scope C fixes.

**What remains for GA:** Deferred — ops owner (TLS, CA letter, GO_NO_GO signatures, backups/restore drills, DPDP) and Deferred — roadmap (live GSP/NIC, GSTR-2B engine, SMS vendor, cookie auth, ERP modules, load/a11y/i18n, CD/pen-test program). See Wave 7 notes in MASTER_ISSUE_REGISTER.md and CHANGELOG.md.

**Next:** Phase D compliance GA (funded) and ops gates — not further Scope C Open triage.

---

## Phase A — Stop the bleeding (week 1–2) · P0

| Focus | Issue IDs (examples) | Outcome |
|-------|----------------------|---------|
| Boot/secrets/TLS/mocks | BB-000001, BB-000013, BB-000015 | Safe deploy baseline |
| OTP/SMS honesty | BB-000002, BB-000003, BB-000006 | OTP off or real |
| Webhooks | BB-000004 | No mis-settlement |
| Product honesty / Go | BB-000014, BB-000005 | Flags + GO_NO_GO |
| Composition block | BB-000007 | No illegal tax invoices |

**Exit:** Conditional paid pilot possible for billing-only tier.

## Phase B — Books & GST integrity (week 3–8) · P0/P1

| Focus | Issues | Outcome |
|-------|--------|---------|
| Returns ↔ GSTR ↔ GL | BB-000008 | CDNR + postings |
| RCM GL + tax split CoA | BB-000010, G23 | Correct RCM books |
| ITC provisional labeling / 2B plan | BB-000009 | No false filing claims |
| H9 + period close | BB-000011 | Filed period integrity |
| E-invoice schema | BB-000012 | NIC-valid payload (still sandbox OK) |
| Doc uniqueness / allocations / credit lock | BB-000019–000022 | Money integrity |
| Dual ledger / child company_id | BB-000016–000017 | Tenancy + books |

**Exit:** CA-defensible pilot with clear “aid not file” GSTR.

## Phase C — Hardening (week 9–16) · P1/P2

- RBAC write flags + FE RoleRoutes
- Pagination / virtualization / load test
- Observability + beat + backups automation
- FE god-module split; Zod schemas
- pip-audit fail; pin deps; CD tags
- Share URL allowlist; CSP; JWT accept-risk or cookies
- Assistant allowlist; LLM privacy

## Phase D — Compliance GA (quarter+) · funded

- Live GSP e-invoice/e-way
- GSTR-2B import + ITC register
- Composition CMP-08
- Cess / export / SEZ
- Pen-test + DPDP program

## Phase E — ERP expansion (separate business case)

- Multi-company / multi-GSTIN
- WhatsApp Business
- Manufacturing / Payroll / CRM
- Native mobile / offline POS

## Effort summary

| Phase | Eng-days (est.) |
|-------|----------------:|
| A | 45–60 |
| B | 80–100 |
| C | 80–100 |
| D | 80–120+ |
| E | 200+ each major module |
| **A+B (honest pilot)** | **~200–250** |


---

## Wave 8 — Immediate hotfix track (2026-08-03) · P0

Supersedes “Scope C completed / zero Open” narrative for launch decisions.

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Payment webhook fail-closed | BB-000196, BB-000197, BB-000213 | No sandbox settle without explicit sandbox provider |
| No stub collect URLs | BB-000198, BB-000211 | Real Razorpay or hard error; disable Cashfree/PayU |
| Purchase H9 parity | BB-000199 | Period + GL reverse/repost |
| Accounting RBAC | BB-000200, BB-000201 | Journals/reports capability-gated |
| Process | BB-000254 | Resolved requires adversarial test evidence |

**Exit:** Safe to expose payment webhooks in pilot.

### Wave 8 P1 (week 2–4)

- IDOR: logo/signature, bank recon (BB-000202, BB-000203)
- FE RoleRoutes + payment URL allowlist (BB-000209, BB-000210)
- Dockerfile non-root, `requests` dep, Redis required, ADMIN default off
- Invoice pickers stop fetch-all (BB-000246)
- GSTR-3B remove net_payable_hint ITC subtract (BB-000212)

## Open-closure (2026-08-03)

All previously **Open** engineering backlog items (66 IDs) are **Resolved**. **Open == 0**. Remaining work is **Deferred — roadmap** / **Deferred — ops owner** only.

## Wave 12 open-closure (2026-08-04)

Closed all **61** Wave 12 Open issues (`BB-000318`…`BB-000378`) via W12A–E. **Open == 0.** Deferred roadmap/ops unchanged.
Assert: `_wave12_assert_gates.py`; close: `_wave12_close_open.py`.

---

## Wave 14 hotfix track (2026-08-04) — P0 before any paid payments/books pilot

> Wave 13 Open==0 is **not** a launch gate. Open count now **88** (`BB-000456`–`BB-000543`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Beat / observability truth | BB-000456 | Healthcheck matches heartbeat wire format + key |
| Payments refund integrity | BB-000457, BB-000458, BB-000477 | Void receipts; reopen links; partial policy |
| Books correctness | BB-000459, BB-000460, BB-000466 | Disposal GL; return COGS basis; control recon |
| FE performance / CSP | BB-000463, BB-000464 | Kill fetchAllPages; sync nginx CSP |
| Product honesty | BB-000462, BB-000467–469 | No false ERP/GSP claims |
| Process | BB-000461 | Adversarial residual gates before Open==0 |

**Exit:** Conditional dogfood with refunds disabled, accounting off or Owner-only without FA/returns COGS reliance, beat probe green.

---

## Wave 14 missed-findings hotfix (2026-08-04)

| Focus | IDs |
|-------|-----|
| SQLite prod refuse | BB-000544 |
| Purchase cancel lots | BB-000545 |
| statement_timeout | BB-000546 |
| Cookie-only prod auth | BB-000547 |
| Semantic assert gates | BB-000548 |

> **Wave 17 (2026-08-05):** Deferred mega products → Resolved as MVP. Remaining GA blockers = Final Gates only.

> **Wave 18 (2026-08-05):** Code-possible Deferred/partials closed as MVP. Final Gates still block true 10/10.

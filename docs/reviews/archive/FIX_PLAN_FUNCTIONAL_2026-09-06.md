# Fix Plan — Functional Code Review 2026-09-06

**Findings live in-repo:** [`FUNCTIONAL_CODE_REVIEW_FINDINGS.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS.md) (`CR-001`…`CR-089`). That file is the self-contained register; this plan sequences the work.

**Census (authoritative):** **7 Critical · 31 High · 39 Medium · 12 Low = 89.** Provisional POS-/SALES-/PUR-/STK-/RPT-/ACC-* IDs are retained in the findings file for traceability. **STK-012 / STK-013** were Info/pass (not defects) and are **not** in the 89.

**Pilot-go High scope (important):** “All Highs fixed” is **not** the pilot gate. Pilot requires **Phase 0–1 Highs in A1–A9** only. **CR-002** stays High in the census but is **accepted unfixed until A10** (durable resume in A1 is enough to stop double-complete). Phase 2+ Highs (A10–A13) are post-pilot hardening unless called out in success criteria.

**Relationship to 5 Sep plan:** Do **not** renumber R-IDs. Where a CR confirms an open R-ID (e.g. CR-037 ≈ R-012, CR-069 ≈ R-016), fix once and close **both** trackers in [`FINDINGS_2026-09-05.md`](./FINDINGS_2026-09-05.md) **and** this CR register. Prefer landing CR PRs on current `main` (or after the in-flight R-PR that owns the same files). Do not stack onto abandoned WIP branches.

**Unit of work:** **PRs A1–A14** below (prefix `A` = functional-audit wave to avoid colliding with R-plan PR 1–15).

**Effort legend:** **S** &lt; 2 hours · **M** half-day · **L** 1–2 days · **XL** 3+ days. Applied per-PR in §4.

**Ownership / dates:** This plan does **not** assign people or calendar dates. Cut branches with an owner in the PR description; put target week on your board. Tracker below uses `[ ]` / `[x]` only.

**Branching:** each PR cut from current `main` after listed Depends merge.

**Standing checklists (every money/stock PR):**
1. New money POST → add exact `scope=` string to `MONEY_IDEMPOTENCY_SCOPES` **and** send `Idempotency-Key` from the UI.
2. Re-draw `transaction.atomic` + `select_for_update` covering every row a business check reads; side effects on `on_commit`.
3. Twin-check Sales ↔ Purchase (and note/return/cancel) before merge — including the “Check/Partial” twins listed in the findings doc.
4. Pytest that **fails on main** then passes on the PR for every Critical/High in that PR.

---

## 0. Locked product decisions

| ID | Decision | Who |
|----|----------|-----|
| **CR-002** | **Phase 0 ships durable client resume (CR-001 / A1) only.** Atomic server `POS checkout` is **Phase 2 (A10)** — optional for pilot; not required to stop double-complete. | Engineering default |
| **CR-011** | Till tendered/change audit is **Deferred** (out of pilot). Receipt stays = invoice total. | Product |
| **CR-022** | Partial SO/DC convert stays **known limitation** for pilot; document in help. No partial-qty engine this wave. | Product |
| **CR-032 / CR-033** | **Single policy:** expense freight/BCD in GL (5110) **and** keep inventory layers at taxable/commercial cost **unless** product flips to “capitalize both.” Default this plan: **align layers to GL (do not capitalize charges into unit_cost)** so COGS matches books. Reopen only with product note. | Product + Eng default |
| **CR-043** | Purchase DN for price uplift is **AP/GL only** (no layer restamp) unless H9 amend is used. Document in DN UI. | Engineering default |
| **CR-050** | Under `WARN`, batch/FEFO/transfer/adjust/reserve must **match** unbatched invoice semantics (allow + return warning). `BLOCK` stays hard-fail everywhere. | Engineering default |
| **CR-008** | `ENABLE_POS` remains **UI sugar** for pilot (sales APIs stay). Document in flags README; paid-module gate deferred. | Product |
| **CR-017** | CN/return on fully paid invoice requires **confirm** or auto-unallocate to headroom — do not silent-floor outstanding. | Engineering default |
| **R-030** | Recurring stays draft-only (unchanged). CR-015 only fixes lock skip / catch-up. | Product (5 Sep) |

---

## 1. Phase −1 — Precondition

**Baseline in the findings doc is stale relative to your branch tip.** Numbers below were recorded on build `5ba05c7` (4 failed / 1174 passed / 8 skipped). **Re-run and write the new counts into the A1 PR description before merge** — later PRs must not add failures vs *that* re-recorded baseline.

1. Recreate/use `backend/.venv` on CI Python; `pip install -c constraints.txt -r requirements-dev.txt`.
2. Record baseline: `cd backend && pytest -q` → note fail count (expect ~4 GSP until fixed separately).
3. `cd web && npm test -- --run`.
4. Confirm `postgres-rls` / concurrency tests can run for A3 (return races need Postgres `select_for_update`).
5. Cut `fix/cr-2026-09-a1` from `main` only after baseline is written into the PR description.

GSP failures (`test_gsp_live_without_creds_raises`, `test_bb_000591_competitor_honesty`, sprint_e GSP QR tests) are **not** in A1–A14; track under existing e-invoice/honesty backlog.

---

## 2. How to execute

1. PRs are the unit of merge. One PR = one merge to `main`.
2. Every Critical/High needs a failing-then-passing pytest (and FE vitest where UI-owned).
3. After each High PR: run the touched app’s pytest subset + `test_concurrency_races.py` when locks change.
4. Close twin findings in the same PR when the root cause is shared (e.g. A3 closes CR-014 **and** CR-036).
5. Update [`FUNCTIONAL_CODE_REVIEW_FINDINGS.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS.md) status line per CR when merged (`Fixed in &lt;PR&gt;`) — never renumber CR-IDs.
6. Cross-close R-IDs in [`FINDINGS_2026-09-05.md`](./FINDINGS_2026-09-05.md) when the same defect is fixed.

---

## 3. Phases (each CR in exactly one phase)

| Phase | Goal | Count | CR IDs | Sev mix | Effort | Gate |
|-------|------|------:|--------|---------|--------|------|
| **−1** | Tooling / baseline | — | — | — | S | pytest + vitest baseline recorded |
| **0** | Stop money loss + wrong books at launch | **12** | 001, 003, 004, 014, 036, 048, 049, 060, 062, 063, 069, 078 | 7C · 5H | 3–5 d | Top-10 Criticals green + POS retry + empty-JE impossible |
| **1** | Twin races, notes, permissions, AR list | **11** | 016, 030, 031, 034, 035, 037, 039, 061, 064, 065, 083 | 11H | 2–3 d | Purchase notes idempotent; cancel+CN safe; list=detail AR |
| **2** | POS settlement + period centralization | **10** | 002, 015, 019, 023, 052, 079, 080, 081, 087, 088 | 9H · 1M | 3–4 d | Optional POS checkout endpoint; GST gate inside `PostingService` |
| **3** | Stock policy + landed cost | **8** | 032, 033, 043, 050, 051, 053, 057, 059 | 5H · 3M | 2–3 d | WARN consistent; layers↔GL policy tests |
| **4** | Reporting remainder + dual ledger honesty | **12** | 066, 067, 068, 070, 071, 072, 073, 074, 075, 076, 077, 082 | 5H · 7M | 2–3 d | GSTR HSN/RCM align; export span cap; docs↔GL health |
| **5** | Operator polish (POS/Sales/Purchase medium) | **22** | 005–010, 017–018, 020–022, 024, 026, 038, 040–041, 044–045, 054–056, 084–086 | 22M | 3–4 d | Thermal warn; CN paid confirm; FAQ BoE; scrap/transfer UX |
| **6** | Low / defer | **14** | 011–013, 025, 027–029, 042, 046–047, 058, 089 + **011 Deferred** | 12L · 1M note · 1 Def | 1–2 d | Defense-in-depth only |

**12+11+10+8+12+22+14 = 89** (CR-011 counted in Phase 6 as Deferred line).

---

## 4. PRs (authoritative)

| PR | Phase | CR IDs | Depends | Effort | Risk | Revert |
|----|-------|--------|---------|--------|------|--------|
| **A1** | 0 | 001, 003, 004 | — | **L** | **High** | Revert FE; unpaid invoices may remain — run unpaid recover. |
| **A2** | 0 | 078, 088 | — | **M** | **High** | Revert BE; scan for empty POSTED JEs and delete/repost. |
| **A3** | 0 | 014, 036 | — | **M** | **High** | Revert BE; Postgres concurrency tests required. |
| **A4** | 0 | 063, 069, 065 | — | **M** | **High** | Revert reporting; CA worksheets change — communicate. |
| **A5** | 0 | 060, 062 | — | **L** | **High** | Revert; dashboard/stock numbers change. |
| **A6** | 0 | 048, 049 | — | **M** | Medium | Revert inventory serial transition. |
| **A7** | 1 | 030, 031, 037, 039 | — | **M** | **High** | Revert; closes R-012 for note/PO paths. |
| **A8** | 1 | 016, 061, 064 | A5 helpful | **M** | Medium | Revert serializers/dashboard. |
| **A9** | 1 | 034, 035, 083 | A7 | **L** | **High** | Revert cancel/TDS note paths. |
| **A10** | 2 | 002 *(optional)*, 015, 019, 023, 052, 079, 080, 081, 087 | A1 for 002 | **XL** | **High** | Feature-flag POS checkout if shipped. |
| **A11** | 3 | 032, 033, 043, 050, 051 | §0 policy | **L** | **High** | May change historical layer costs — migration note. |
| **A12** | 3 | 053, 057, 059 | — | **M** | Medium | Revert inventory edge paths. |
| **A13** | 4 | 066–068, 070–077, 082 | A4, A5 | **L** | Medium | Revert reports/health. |
| **A14** | 5+6 | Remaining Medium/Low in §3 Phases 5–6 (incl. CR-011 Deferred) | A1–A13 as needed | **XL** | Low–Med | Revert per-area. |

Parallelize: **A1 ‖ A2 ‖ A3 ‖ A4 ‖ A5 ‖ A6** after −1. Then A7–A9. Then A10–A12. A13 after A4/A5. A14 last.

**Rough calendar (one engineer, no parallel):** Phase 0 ≈ 1 week · Phase 1 ≈ 3 days · Phase 2–3 ≈ 1 week · Phase 4–6 ≈ 1–1.5 weeks. With parallel A1–A6, Phase 0 compresses to ~3–4 days.

---

## 5. Phase 0 — Launch blockers (detail)

### A1 — POS durable resume + gates `[x]`
| CR | Fix direction | Test |
|----|---------------|------|
| **001** | Persist one sale gesture key (reuse create/complete/receipt/alloc); on receipt/alloc failure do **not** remint; skip to unpaid recover if already COMPLETED | `pos_online_cash_retry_after_receipt_failure_does_not_double_complete` |
| **003** | Gate menu/route: `canCreateSales && canCreatePayments` | `pos_hidden_without_can_create_payments` |
| **004** | `updateDraft({ customerId })` (or idempotent customer key) before invoice create on flush | `flushPosDraft_pending_customer_retry_does_not_duplicate_customer` |

### A2 — `PostingService` atomicity `[x]`
| CR | Fix direction | Test |
|----|---------------|------|
| **078** | Create JE + `bulk_create` lines inside **one** `atomic`; idempotent fast-path must reject/repair zero-line POSTED | `posting_crash_between_header_and_lines_does_not_leave_empty_posted` |
| **088** | Quantize line amounts to 2 dp **before** balance check | `post_rejects_subpaisa_unbalanced_after_quantize` |

### A3 — Concurrent returns `[x]`
| CR | Fix direction | Test |
|----|---------------|------|
| **014** | `SalesInvoice.objects.select_for_update().get(...)` before remaining-qty check | Concurrent `complete_return` — one 200, one 400 |
| **036** | Same for `PurchaseInvoice` in `complete_return` | Twin concurrency test |

### A4 — Register + GSTR honesty `[x]`
| CR | Fix direction | Test |
|----|---------------|------|
| **063** | Default registers exclude `CANCELLED` (keep optional status filter) | Cancelled invoice absent from default totals |
| **069** | `net_payable_hint` uses same heads as `recommended_claimable` | 2B&gt;books → net uses min |
| **065** | Single opening predicate: `is_opening_balance` everywhere (drop `notes="TALLY_OPENING"`-only) | Opening flag alone excludes from dashboard |

### A5 — Dual AR + stock summary `[x]`
| CR | Fix direction | Test |
|----|---------------|------|
| **060** | One definition: KPI and aging share document bulk **or** both age GL; assert `sum(aging)==receivables` | Books on + off fixtures |
| **062** | Inventory summary on-hand from movements (or fail-closed if balance≠Σ movements) | Corrupt balance → report does not silently trust |

### A6 — Manual serial return `[x]`
| CR | Fix direction | Test |
|----|---------------|------|
| **048** | Stop reading nonexistent `StockMovement.serial_numbers`; cost via valuation/linked SALE | `serial_transition_sold_to_returned_succeeds` |
| **049** | Match document return: status `AVAILABLE` + `restore_fifo_peels` (or disable manual path) | Re-sale + layer sum == balance |

---

## 6. Phase 1 — Twins, notes, AR display

### A7 — Purchase notes + subscription `[x]`
| CR | Fix | Test |
|----|-----|------|
| **030** | `wrap_idempotent` + add `purchase_credit_note_complete` / `purchase_debit_note_complete` to `MONEY_IDEMPOTENCY_SCOPES` | Double-complete same key → one JE |
| **031** | Delete view-side second `post_note` (sales B2-010) | Exactly one JE after HTTP complete |
| **037** | Add `SubscriptionWritesAllowed` on CN/DN/PO writes (**closes R-012** for these viewsets) | Suspended tenant → 402/403 |
| **039** | FE Idempotency-Key on note complete | E2E double-submit |

### A8 — List/KPI parity `[x]`
| CR | Fix | Test |
|----|-----|------|
| **016** | List balance via `bulk_sales_invoice_outstanding` (CN/DN-aware); twin purchase list | List == detail after return |
| **061** | Align aging allocation filters with R2-020 | Mis-typed alloc ignored |
| **064** | Dashboard MTD purchases net completed PCN/PDN | Mirror sales KPI |

### A9 — Cancel guards + TDS on notes `[x]`
| CR | Fix | Test |
|----|-----|------|
| **034** | Block cancel if completed CN/DN exist (sales twin too) | Cancel with CN → 400 |
| **035** | Block cancel if draft purchase return exists (copy R2-005) | Draft PR → cancel PI → 400 |
| **083** | `post_note` PURCHASE_* reverses 2265 TDS; no silent dump to 1250 | PI+TDS+full PCN → 2265/2100/1250 |

---

## 7. Phase 2 — Settlement + period centralization

### A10 `[x]` — CR-002 optional endpoint **skipped** (A1 durable resume remains pilot path)
| CR | Fix | Test |
|----|-----|------|
| **002** | Optional: `POST /pos/checkout/` (complete+receipt+alloc one atomic + one scope). Flagged. Client uses when present. | Half-success matrix impossible under endpoint |
| **015** | Do **not** advance `next_run_at` on locked period; retry after unlock | Lock→process→unlock→draft for same `period_key` |
| **019** | `assert_period_allows_money_amend` on challan complete when stock posts | Soft-closed → 400 |
| **023** | Move period gate **before** number/status/stock on invoice complete (purchase twin) | Closed period → no SALE movement |
| **052** | Same gate on stock count post + transfer complete/cancel | Soft-closed → 400 |
| **079** | `reverse()` + status flip in one `atomic`; viewset `@transaction.atomic` | Induced failure → not both POSTED |
| **080** | Call GST+accounting period assert inside `PostingService.post` (or require callers — prefer inside) | Soft-close GST only → backfill refuses |
| **081** | `select_for_update` on period row in soft_close/close; posters lock same row | Parallel close+complete |
| **087** | Harden backfills: `--dry-run`, require `--company` on mass command; inherit A2/A10 gates | Dry-run docs |

---

## 8. Phase 3 — Stock policy + landed cost

### A11 `[x]` (requires §0 policy)
| CR | Fix | Test |
|----|-----|------|
| **032** | Stop capitalizing `additional_charges` into `unit_cost` (default decision) **or** capitalize into 1400 — pick one | Layer cost == GL inventory basis |
| **033** | Same for BoE BCD vs layers; honesty in model docstring | BoE+import complete fixture |
| **043** | Document DN AP-only; no 1400 restamp | DN after PI → layers unchanged |
| **050** | WARN path: FEFO/batch/transfer/adjust/reserve return warning string, allow same as unbatched | WARN matrix pytest |
| **051** | Running cost must track negative under WARN **or** forbid WARN when valuation on | Balance vs running-cost agree |

### A12 `[x]`
| CR | Fix | Test |
|----|-----|------|
| **053** | Import void: compensating movement only; stop mutating `reference_type` via `.update` | Void leaves original type; reverse ADJUSTMENT exists |
| **057** | Scrap AVAILABLE requires `on_hand >= 1` | Scrap at 0 → 400 |
| **059** | Document ops runbook for `verify_fifo_layers`; optional health warn | — |

---

## 9. Phase 4 — Reporting remainder

### A13 `[x]`
| CR | Fix | Test |
|----|-----|------|
| **066** | Net CN/DN in product/customer sales | Ranking after CN |
| **067** | Warehouse filter applies to note rows | WH-scoped register |
| **068** | `_int_or_none` on inventory warehouse param | `?warehouse=abc` |
| **070** | Prefer stored RCM tax; no silent rebuild | Legacy RCM fixture |
| **071** | HSN keys use `applied_rate` (fallback `gst_rate`) | Rate mismatch fixture |
| **072** | SQL-bound BoE ITC period | GSTR-9 FY perf smoke |
| **073** | Fix GSTR-9 table 8 note text | Snapshot |
| **074** | Max date span + stream CSV | Oversized range → 400 |
| **075** | Prefetch cancel reasons; FY in SQL | Query count |
| **076** | Label cash book vs GL cash-flow; no silent mix on dashboard | Copy/honesty |
| **077** | Aggregate cash_flow in SQL | — |
| **082** | Books health: compare docs↔GL party totals; block or warn on period close | Drift fixture |

---

## 10. Phase 5 — Medium polish (A14 batch) `[x]`

Group by area; can split sub-PRs if review size demands.

**POS:** CR-005 thermal warning + reprint · CR-006 flush→print · CR-007 server preview tender · CR-008 docs only (§0) · CR-009 inclusive line helper · CR-010 keep cart on unknown complete  

**Sales:** CR-017 paid-CN confirm/unallocate · CR-018 DN qty cap · CR-020 keep reservation until invoice complete · CR-021 quotation header discounts · CR-022 help limitation · CR-024 raise in `set_items` if completed qty changes · CR-026 CN price override confirm  

**Purchase:** CR-038 note `additional_charges` fields · CR-040 rewrite FAQ to BoE flow · CR-041 import NON_GST confirm · CR-044 block BoE cancel if linked completed PI · CR-045 return unit snapshot  

**Stock:** CR-054 drift health/API · CR-055 document DRAFT non-binding or reserve · CR-056 KEEP_SERVER copy  

**Accounting:** CR-084 TDS override audit like TCS · CR-085 purchase tax drift hard-fail (sales parity) · CR-086 manual JE respects `books_start_date`

---

## 11. Phase 6 — Low / Deferred

| CR | Action |
|----|--------|
| **011** | **Deferred** — till sessions |
| **012, 013** | Qty UX + stock cache invalidate — Low |
| **025** | IRN FAILED amend/cancel matrix — Low |
| **027** | Recurring multi-period catch-up loop (cap N) — after CR-015 |
| **028** | Optional `full_clean` before `bulk_create` — Low |
| **029** | Residual alloc tests only — Low |
| **042** | Document bill import all-or-nothing — Low |
| **046, 047** | Query param validation / `CompanyPrimaryKeyRelatedField` — Low |
| **058** | Default warehouse — monitor only |
| **089** | Honesty note on books-on backfill — Low |

---

## 12. Per-CR checklist (tracker)

### Critical
- [x] CR-001 A1
- [x] CR-048 A6
- [x] CR-060 A5
- [x] CR-062 A5
- [x] CR-063 A4
- [x] CR-069 A4
- [x] CR-078 A2

### High
- [ ] CR-002 A10 (optional endpoint) — **accepted skipped**; A1 durable resume is pilot path
- [x] CR-003 A1
- [x] CR-004 A1
- [x] CR-014 A3
- [x] CR-015 A10
- [x] CR-016 A8
- [x] CR-030 A7
- [x] CR-031 A7
- [x] CR-032 A11
- [x] CR-033 A11
- [x] CR-034 A9
- [x] CR-036 A3
- [x] CR-037 A7
- [x] CR-049 A6
- [x] CR-050 A11
- [x] CR-051 A11
- [x] CR-052 A10
- [x] CR-061 A8
- [x] CR-064 A8
- [x] CR-065 A4
- [x] CR-066 A13
- [x] CR-070 A13
- [x] CR-071 A13
- [x] CR-072 A13
- [x] CR-074 A13
- [x] CR-079 A10
- [x] CR-080 A10
- [x] CR-081 A10
- [x] CR-082 A13
- [x] CR-083 A9
- [x] CR-087 A10

### Medium / Low
- [x] CR-005–010, 017–018, 020–024, 026, 038, 040–041, 044–045, 053–057, 059, 067–068, 073, 075–077, 084–086, 088 — Phases 5–6 / A14 (CR-035 is High → A9)
- [x] CR-012–013, 025, 027–029, 042, 046–047, 058, 089 — Phase 6 Low
- [x] CR-011 Deferred

---

## 13. Suggested fix order for a solo engineer (first week)

1. **A1** POS key remint (stops double stock at counter)  
2. **A2** empty JE (stops silent books corruption)  
3. **A3** return races (sales+purchase together)  
4. **A4** registers + 3B payable hint  
5. **A5** AR/stock KPI truth  
6. **A6** serial return crash  
7. **A7** purchase note idempotency + R-012  

Then A8–A9, then period/POS checkout (A10), then policy-heavy A11.

---

## 14. Out of scope for this plan (still launch risks)

### Not in A1–A14
- **GSP / honesty pytest failures** listed in Phase −1 (e-invoice backlog).
- **Prior audits, not CR-scoped:** **BUG-703** media auth, **BUG-109** invite attach, **BUG-102** OTP SMS stub, payment webhook RLS (**R-005**), refund event map (**R-002/R-003**). Keep [`FIX_PLAN_2026-09-05.md`](./FIX_PLAN_2026-09-05.md) for those.
- **Full R-001…R-088 set** (88 open) runs in parallel; only cross-closes above. Closing “both trackers” means editing [`FINDINGS_2026-09-05.md`](./FINDINGS_2026-09-05.md) when the matching CR merges.
- **BB-series open residuals** (~64 Open in the master register Totals) are a third ledger — see [`MASTER_ISSUE_REGISTER.md`](./MASTER_ISSUE_REGISTER.md) open-work rollup. A1–A14 does not close them.

### Accepted / deferred inside the CR set
- **CR-002** — High, optional until A10 (Phase 0 uses A1 resume).
- **CR-011** — Deferred (till sessions).
- **CR-008 / CR-022** — product-accepted limitations for pilot (document, don’t build).

---

## 15. Success criteria (pilot go)

Explicitly **not** “all 89 closed” and **not** “all 31 Highs closed.”

- [x] All **7 Critical** CR-IDs fixed and tested (001, 048, 060, 062, 063, 069, 078)
- [x] All **Phase 0–1 Highs in A1–A9** fixed (includes 003, 004, 014, 016, 030, 031, 034, 036, 037, 049, 061, 064, 065, 083 — **excludes CR-002** until A10)
- [ ] Concurrent return + POS retry tests green on **Postgres**
- [ ] `sum(receivables_aging) == dashboard.receivables` for both outstanding bases
- [ ] Default sales/purchase register totals exclude cancelled
- [ ] No empty POSTED journals after kill-mid-`post` chaos test
- [ ] Purchase CN/DN complete idempotent; subscription gate on note writes
- [ ] Pytest fail count ≤ **Phase −1 re-recorded** baseline (no new failures)
- [ ] Twin follow-ups from findings “Check/Partial” table either fixed in the parent PR or filed as explicit CR Invalid/Deferred notes

**Post-pilot (still required before “all Highs” claim):** A10–A13 Highs done in tree (002 optional skipped, 015, 032, 033, 050–052, 066, 070–072, 074, 079–082, 087).

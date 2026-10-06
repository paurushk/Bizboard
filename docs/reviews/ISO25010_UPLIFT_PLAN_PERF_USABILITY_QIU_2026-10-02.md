# Implementation Plan — lift Performance efficiency, Usability, Quality in use to score 3

**Date:** 2026-10-02 · **Revision:** v2 (decisions D1–D24 folded in; body and parent aligned to §0) · **Parent:** [ISO25010_QUALITY_ASSESSMENT_2026-10-02.md](ISO25010_QUALITY_ASSESSMENT_2026-10-02.md)
**Current → target:** Performance efficiency 1 → 3 · Usability 2 → 3 · Quality in use 2 → 3
**Duration:** **8 weeks of engineering (9 with buffer)**, 2 engineers + 1 QA + part-time founder/Ops. (v1 said 6; that was not credible — see D23.)

**Scope statement.** This plan is an **ISO rescore programme**. It is *not* a pilot Go decision. The pilot-entry blockers that must be true before real businesses touch the system are listed separately in §3 (PRE-5/6) and are in the plan because the pilot is internet-exposed; they do not make this a Go/No-Go.

**Founder-owned decisions** are marked **[F]**. Everything else is my recommended default; each answer says what it changes. Items marked **[F]** need a written yes/no before week 1 — they are the ones I cannot decide for you. **Verification notes** state which claims in the questions I checked against the tree on 2026-10-02.

---

## 0. Decisions (answers to the 24 questions)

### Scoring and gates

**D1 — What counts as a 3? Who may accept an SLO miss?**
Two separate outcomes, previously conflated:
- **ISO score 3** = *measured, honest, and accepted*. A miss against the tight SLOs is allowed **only if** (a) the number is committed with a root cause, (b) the **founder [F] accepts the miss in writing** with a remediation date, and (c) the Section-D2 *gate* bar is met.
- **F-PERF-01 stays open** until the tight SLOs pass. Accepting a miss **does not close F-PERF-01** and does not delete it from the backlog; it re-statuses QOS-0003 from "unmeasured P1" to "measured, accepted, remediation scheduled" (P1 → P2 by founder acceptance, recorded via the QOS-0052 governance path). The rule in §1 is reworded: "no *unaccepted* P1".
- The 2026-09-12 laptop run (list p95 = 9.33 s, per `docs/roadmap/ticket-logs/X-01.md`, verified) is **not valid evidence for either outcome**: single-Postgres laptop, and the same log says the Complete number was conflict-rejection latency. It stays as history.

**D2 — Which latency bar is the build target?** Three tiers, one table:

| Tier | Bar | Role |
|---|---|---|
| **Gate (blocks ISO 3)** | At 25 concurrent users, 30 min, **no endpoint p95 > 8 s**, error rate < 0.5 %, no worker OOM/restart | Must pass |
| **Target SLO (recorded)** | Complete < 800 ms, list < 2 s, dashboard < 500 ms (`load/README.md`, `k6_slo.js`) | Measured at **both** 10k-invoice and 50k-invoice tiers; passing at the 10k tier is a **pilot-Go** bar (pilot tenants will be nearer 10k than 50k); passing at 50k is the F-PERF-01 close bar |
| **Async rule** | Any request whose p95 > 8 s → index it or make it async. Requests 2–8 s are *flagged* in the endpoint table, not blocking | Replaces the parent's "async anywhere > 2 s", which would have forced async on most reports |

The parent's §6 table and QI-15 are amended accordingly (the GST worksheet target of 8 s p95 *is* the gate; its 8 s p95 is not a stretch goal).

**D3 — ISO rescore or pilot Go?** **ISO rescore only.** Yes, the scorecard can move to 3 while `GO_NO_GO.md` stays unsigned; the two are independent documents. Consequences:
- **[F]** Before C4, the founder records in `GO_NO_GO.md` → *Waivers* that the "UAT ≥ 5 companies" row (`UAT_CHECKLIST.md`: "Companies: ≥5", verified) is replaced for this pilot by a **3-company controlled pilot**, with the marker "Conditional". Template in §9. Without that waiver the pilot is not a Go candidate, but the ISO rescore is unaffected.
- The parent's release blockers F-SEC-01 (isolation proof), F-SEC-04 (TLS edge) and F-REL-01 (backups) are **pilot-entry** conditions, so they are added as PRE-3 (TLS, already present), **PRE-5** (isolation matrix) and **PRE-6** (encrypted offsite backup). They are not required for a 3 on the three characteristics, but the pilot must not start without them.

**D4 — Which sentence is the rescore rule when field results are bad?** One rule, outcome-independent:
> **A 3 is awarded for evidence produced and Severity-1 findings resolved, not for hitting targets.** The targets (SUS ≥ 70, ≥ 4/5 unaided, zero incidents, SLOs) decide **3 → 4** and **pilot Go**.

Exact criteria:
- *Usability 3:* study completed on the RC with the defined protocol; every Sev-1 finding is fixed **or** has a documented workaround, owner and date; axe gate in place; retest of the Sev-1 fixes with 3 new participants shows those tasks completable. SUS/unaided rate are **recorded**; SUS < 50 or < 3/5 unaided on the core loop caps the score at 2 until a re-run.
- *Quality in use 3:* ≥ 3 tenants × ≥ 2 weeks of metrics; every incident has RCA + fix + regression test. A **money-wrong or data-loss incident that reached a customer and was not reversed** caps the score at 2 until fixed and re-verified. A handled, reversed incident is evidence and does not cap.
- The v1 sentences "SUS ≥ 70" and "zero incidents" are demoted to targets; the v1 risk notes are the rule.

**D5 — Does the pilot freeze the UI?** **Yes.** The pilot runs only on the tagged RC1.
- B2 splits: **B2a** (Sev-1 fixes from the study + minimal progressive disclosure on the invoice/purchase editors) lands **before** RC1; **B2b** (the larger QOS-0095 redesign) is developed on a branch during the pilot and ships as **RC2 after the 2-week window**.
- Usability 3 evidence = study on RC0 (pre-fix) + Sev-1 fixes on RC1 + a 3-new-participant retest of the fixed tasks. The B2b retest is 3 → 4 evidence, not required for 3.
- Pilot start moves from week 3 to **week 5** (needs RC1 = after the study, B2a, B3, B4, C2, PRE-5/6).

### Prerequisites

**D6 — What is allowed into the RC commit?** Verified state: 225 modified, 132 untracked, 37 renamed, 3 deleted, 1 added. `backend/db.sqlite3` and `backend/test_media/` are **already gitignored** (verified) — not a risk. Rules:
- **Out (never committed):** `.env*` except `*.example`, `.ux-audit-credentials.local`, any `*.sqlite3`, `test_media/`, `node_modules/`, `dist/`, `test-results/`, `backups/`, `load/results/`, local pytest DBs. Add `.gitignore` entries for anything missing; run `gitleaks` on the RC diff.
- **Spreadsheets / registers:** the four untracked root files (`Bizboard_Master_Task_Register_Enhanced.*`, `Bizboard_Product_Task_Universe_Master.*`) **stay out** of the RC commit; **[F]** decide archive (`docs/archive/`) vs keep local. One root `.xlsx` is already tracked — leave it.
- **Deleted docs:** the three root review docs (`FUNCTIONAL_CODE_REVIEW_2026-09-08_CLAUDE.md`, `MVP_IMPLEMENTATION_PLAN.md`, `RELEASE_BLOCKING_CODE_REVIEW_2026-09-08.md`) are committed **only** as moves into `docs/archive/…` or with a link-fix PR, because `CLAUDE.md`/memory reference some review docs. Check inbound links first.
- **Slices (each its own commit/PR):** (1) docs archive + renames; (2) backend payments/insights/whatsapp/notifications + migrations `insights/0011–0013`; (3) backend new commands/tests (`enable_full_demo`, `provision_ux_audit` …); (4) web pages (by area); (5) qos YAML + generated backlog; (6) CI/workflow edits last.
- **Reviewer:** each slice reviewed by someone who did not write it — the second engineer or founder; I run `/code-review` on each slice as a pre-check, not as the approver. Migrations additionally pass `guard_zdt_migrations`.
- **Green on the tag = the full existing CI workflow** (backend suite on Postgres minus `slow`/`flaky_quarantine`/`llm_accuracy`, cov floor 83 %, diff-cover 80, invariant-sweep, web lint/tsc/vitest, spectacular and openapi-types drift checks, golden e2e, trivy, pip-audit, npm audit, `guard_required_checks_match`). A full local run is not required; CI is the authority.

**D7 — Which runtime is measured?** **Pin the images down to CI: Python 3.13 and Node 22 LTS.** Reasons: it matches the recorded 3.13 decision, CI is where the 2,389 tests run, and moving CI up to 3.14/Node 26 is a dependency-compatibility project of its own. **The in-image smoke is part of PRE-2**: a new CI job builds the API and web images and runs `manage.py check --deploy`, `/api/v1/health/?ready=1`, `migrate` on an empty Postgres, and `k6_smoke.js` against the container. New base-image digests are pinned (`scripts/pin_image_digests.sh`); `guard_config_consistency.py` asserts Dockerfile and CI versions match. All performance numbers are taken **from the image**, never from the venv.

**D8 — Is Postgres-as-default in scope?** **No.** PRE-4 is *"a documented, one-command Postgres path"* (compose service + `README` + script to run `pytest -m postgres`). SQLite stays the default for fast local runs. Every number in this plan is taken on Postgres regardless. Flipping the default is a separate follow-up (QI-13) and is removed from this programme's critical path.

**D9 — What is the staging host? [F]** I cannot pick this; the plan needs a named answer by day 2. Recommendation:
- **One provider/region close to users**, a single VM per environment: **4 vCPU / 8 GB RAM / 100 GB SSD**, Docker + the compose stack, domain with TLS at a managed edge (Cloudflare or the provider's LB, per QOS-0020). *Staging and the pilot should be the same spec but different machines*, so the load test cannot disturb pilot tenants and pilot data never enters the load fixture.
- **Cost owner:** founder. For the performance work only, an *ephemeral* VM of the same spec for ~2 weeks is acceptable if budget is tight; it must be recreated from the same compose files, so it counts as staging evidence.
- **Secrets:** host `.env` (mode 600) plus GitHub Environment secrets for CI; k6 credentials, `SENTRY_DSN`, SMTP creds live there, never in a git tag or `load/` files. Test accounts for load are created by command on the host, not committed.
- **Blocks:** A2, A3, B1 hosting, C5, C6, PRE-3. Until it exists, no run counts as E-P1 evidence.

### Performance design

**D10 — Which 50k fixture counts?** **The existing `seed_synthetic_bulk` is not the SLO fixture.** Verified: it refuses `DJANGO_ENV=staging`/production and requires DEBUG/development, builds on `seed_demo`, attaches invoices to **one customer and one product**, and bulk-inserts rows rather than calling `SalesService.complete`. Keep it for dev/dashboard-budget use. Build a **new** command `seed_load_tenant` with this contract:
- **Gate:** runs only when `DJANGO_ENV in {staging, test}`; refuses production explicitly (inverse of today's gate).
- **Path:** `SalesService.set_items` + `complete` for each invoice with an idempotency key (re-runnable, resumable, `--shard i/n` for parallel workers).
- **Mix:** ~1k products (5 % batch/serial), ~500 customers, 70 % B2C small / 25 % B2B 5–15 lines / 5 % returns+credit notes; ~60 % paid by receipts (part/full); 12 months of back-dating.
- **Side-effect suppression is part of the contract**, enforced by a `SEED_LOAD=1` guard that no-ops: PDF enqueue (leave `pdf_status` NONE — `SEED_50K.md` already requires this), GSP/e-invoice/e-way, WhatsApp/Telegram/email/notification tasks, outbound webhooks, LLM calls. The implementer first lists every `safe_delay`/`.delay(` reachable from `complete` and proves each is suppressed with a test that asserts **zero** queued tasks after a seed batch.
- **Wall-clock budget:** ≤ 4 h at 4 shards. If the service path measures slower, **fallback (documented, not silent):** service path for the first 2,000 invoices (proves correctness) and ORM bulk path for the remainder, then `check_invariants` must be clean and a 200-invoice sample is recomputed through the service and compared.
- **Tiers:** produce a snapshot at **10k** and at **50k** (the 10k tier is the pilot-Go comparison, D2).
- **Done when:** counts verified, `check_invariants` clean, snapshot stored on the host (not git), seed duration recorded.

**D11 — Why A5 before A6?** It was a sequencing error. **A6 (long-request audit) now precedes the timeout reduction.** A5 splits:
- **A5a (after A2/A3):** worker/thread sizing (`gthread`, `--workers`, `--threads`) with the **timeout kept at 120 s** and re-run.
- **A6:** audit; each endpoint gets *index / async / accept* decisions.
- **A5b (after A6):** lower the timeout to the p99 of the slowest accepted synchronous endpoint + margin (expected ~60 s), set `--max-requests`, re-run the gate scenario.

**D12 — Same k6 scenario for dashboard and GSTR?** **No — separate scenarios with their own thresholds, run sequentially for attribution, then together in the soak for capacity.** `k6_slo.js` gets named scenarios: `list_complete` (existing; thresholds already tagged), `dashboard` (<500 ms), `reports` (GSTR/sales/GL, 1–2 VUs, 8 s gate), plus new `load/k6_mixed.js` for the soak. Verified facts and fixes:
- The script **already logs in once in `setup()`** (verified), so the 10/min login throttle only matters for multi-tenant setups: for 20 tenants, issue the 20 tokens sequentially with ≥ 7 s spacing (≈ 2.5 min) or raise the login throttle by env on staging only.
- **New catch:** access tokens last **15 min** (`JWT_ACCESS_MINUTES`), so a 30-min soak will 401 halfway. Set `JWT_ACCESS_MINUTES=60` on staging only, or have the script refresh. Verify in the first dry run.
- **Draft pool size:** `seed_draft_pool --count` ≥ `target_completes_per_second × duration × 1.2`. For the soak at ~3 completes/s × 1,800 s ≈ 5,400 → **6,500 drafts**. Re-seed the pool between runs.
- **`seed_draft_pool` cannot be used as it stands.** It refuses any non-DEBUG process (so it refuses `DJANGO_ENV=staging`) and only attaches drafts to the `seed_demo` company "Demo Traders". Extend it, or have `seed_load_tenant` emit the pool, so drafts are created on the load tenant under `DJANGO_ENV=staging`. Clear that tenant's `monthly_complete_limit` first — the command's own docstring says a quota will turn the run into rejection latency. Stock top-up stays part of the command.

**D13 — What does the bundle budget include?** **Initial-load chunks only, as a ratchet, not an aspirational cap.** Measured: entry ≈ 250 KB gz; `mui-vendor` 414 KB raw (`vite.config.ts` `manualChunks`).
- Budget = **sum of chunks referenced by the built `index.html` (entry + modulepreload'd vendor chunks), gz**, set at *measured + 10 %*, ratcheted down when it shrinks. `mui-vendor` is **in** this sum only if it is preloaded; lazy-route chunks get a separate per-chunk cap (150 KB gz) with an allow-list for known-large ones. **A vendor split is explicitly not part of this plan**; if the first measurement fails the per-chunk cap on a legitimate chunk, it goes on the allow-list with a ticket.
- **Dashboard e2e:** allowed to call staging (read-only, seeded 50k tenant, dedicated test user). Gate on the **median of 5 runs**, unthrottled: API ≤ 500 ms and first-KPI paint ≤ 3 s; one retry; **flake budget < 5 %** over 20 runs, else the test is quarantined and the number is recorded manually. The Fast-3G / 4× CPU profile is **informational (recorded, not gating)**.

**D14 — What memory limit is real?** **None is set before the soak.** Run the soak with no container limit (host ceiling = 8 GB minus DB/Redis/OS headroom), record peak RSS/CPU per container, then set `mem_limit = ceil(1.5 × peak)` and `cpus` from the host, **below the host ceiling**, and re-run the gate scenario to prove no OOM. The parent's "512 MB / 70 % CPU" are *evaluation targets*, not pre-set limits; if measured peak is higher, the target is revised with a note, not silently dropped. Depends on D9.

### Usability design

**D15 — What does "unaided" mean, and in which language?**
- **Unaided** = the participant completes the task with **no facilitator hint on how to proceed**. After **2 minutes of no progress** the facilitator may give a hint; the task is then logged **"assisted"** (not unaided) and the participant continues. Clarifying the *task wording* is not an assist.
- **Core loop for the 4/5 measure = tasks 1–3** (onboard/login to a usable company; create a GST invoice; record a part-payment and state the amount still owed). **Task 4** becomes "find which customers owe the most" (view-only); *sending* the reminder is deferred until SMTP/WhatsApp are live (they are still unchecked final gates). **Task 6** ("do the numbers match the dashboard?") runs only after C2 lands — C2 is moved to week 1 so it precedes the study. **Task 5 (POS, phone width)** is a **separate 30-min mini-session** with counter-staff participants only; it is reported but **not** in the 4/5 core measure.
- **Environment failures** (a dead integration, a staging outage, a seeding bug) are *excluded from the denominator and logged separately* as "environment failure", never scored against usability, never silently dropped.
- **SUS:** the standard 10-item form, in the participant's preferred language (Hindi or English). Hindi version: forward-translate then back-translate by a bilingual reviewer; if a participant prefers, the facilitator reads items aloud and records answers. The version used is recorded.

**D16 — Facilitator, participants, retest.**
- **Facilitator is not the founder.** A QA engineer or an external UX researcher facilitates; the founder may observe silently (muted, off-camera). This is required for the unaided rate to be unbiased.
- **Participants are not pilot tenants** and are not in the pilot cohort during the window — pilot users would be pre-trained and the pilot metrics contaminated. They may be warm leads from the same segment.
- **Consent:** one plain-language page, English + Hindi (drafted by QA, founder approves): purpose, recording, that only demo data appears on screen, storage on an encrypted drive, deletion after 90 days, right to stop. **No real business data on screen** — demo tenant only; a participant's own data is not entered. First 3 sessions in person (see the hands, the phone), remaining remote is acceptable. **[F]** Set compensation (proposal: ₹1,000–1,500 per 45-min session; mini-session ₹500).
- **Retest = 3 new participants** (not the originals): different people measure the fix; originals would show learning effect. Originals may be used for a regression-only check.

**D17 — How hard is the Hindi rule?** Scope: **customer-visible strings only**, not logs/codes. Two checks: (1) **missing key** in `hi` vs `en` = hard fail; (2) **identical-to-English value** = hard fail only for strings of ≥ 3 words or containing none of the allow-listed tokens; otherwise a warning. Allow-list file (`web/src/i18n/hi-allowlist.ts`, *new*): GST, GSTIN, PAN, HSN, SAC, POS, UPI, IFSC, OK, PDF, QR, email, SMS and similar. **Owner:** the web engineer maintains it; additions need review by a Hindi reader (founder or a native-speaker reviewer). Lands **after PRE-1**, because `hi.ts` is in the uncommitted tree.

**D18 — Is axe-on-everything a day-one merge gate?** **No — three stages with a ratchet.**
1. **Week 1:** generator (same route source as `route-smoke.spec.ts`/`protectedRoutes.ts`).
2. **Week 2:** **report-only** CI job on all routes, sharded 4-way, OWNER only. Output = baseline file. Not a merge blocker.
3. **Weeks 3–4:** **blocking for the core tier** (~25 routes: auth, dashboard, invoice, purchase, POS, payments, customers, items, top reports, core settings) × **4 roles** (OWNER, ACCOUNTANT, SALES_STAFF, VIEWER); roles matter only where rendered actions/nav differ, so non-core routes run OWNER only.
4. **Weeks 5–6, on the branch, not on RC1:** blocking on all routes against a **baseline file that can only shrink** — a new violation fails; an existing one does not. This ratchet does not have to be green before the pilot tag.
- **Skip rules:** routes behind flags off in the frozen profile, dark modules (manufacturing/payroll/CRM), and routes a role is forbidden from (403/redirect) are **skipped with the reason logged** in the report.
- **Allow-list:** a row requires a PR approved by the web owner **and** QA, with reason, ticket and **expiry ≤ 30 days**; **an expired row fails the build.**
- **QOS-0007 is not reopened** (it is `fixed`, scoped to the POS/invoice keyboard journey, verified). Create **a new QOS item** (next free id) "Axe gate across all routes × roles".

### Quality in use

**D19 — How much of QOS-0053 is left?** Verified: `test_cr100_purchase_invoice_outstanding_ignores_receipt_allocations` and `test_cr101_dashboard_payables_equals_aging_sum` exist in `backend/tests/test_a15_cr090_plus.py`; the item is `lifecycle: verified`, `closed: null`; CR-101 covers a single completed purchase. So C2 is **"extend, then decide"**: first write the matrix as **characterization tests** (part-payment, full payment, purchase return, debit note, advance, books on, books off) — ~1–2 days. If they pass, C2 is just the matrix plus closing the item; **only if they expose divergence** does the truth model change. The pilot profile's books-on/off is read from FREEZE_SCOPE Table B (`guard_freeze_table_b_defaults` exists); the matrix covers **both** so the answer does not gate the work. C2 runs **week 1**, before the study (D15).

**D20 — Which backup outcome is in scope?** Two tiers, so nothing is ambiguous:
- **Pilot-entry (PRE-6, by end of week 4):** `backup.sh` **fails closed** with no encryption recipient; daily **encrypted offsite** upload to object storage in a different failure domain; backup-age alert (> 26 h); **written RPO: 24 h, accepted by the founder [F] for the controlled pilot** (PITR deferred and listed as a follow-up).
- **ISO Quality-in-use 3 (C6):** the 50k restore **from the offsite copy** is timed and `check_invariants` is run. The number is the artefact. A restore slower than 60 min is recorded with a cause; it does not block the score. It does leave the parent's F-REL-01 acceptance unmet (that acceptance is still "≤ 60 min").
- **Not in this plan:** PITR/WAL archiving, multi-region.

**D21 — Where do the field metrics come from?**
- **Correction:** H-01…H-05 are the validation hypotheses in `docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md` §11 (ledger accuracy, counter speed, offline outbox, FEFO/expiry, CA filing). `docs/ux/heart_metrics.md` has no such ids. They are **not** the eight pilot counters. C1 defines those eight counters itself. The hypotheses are recorded beside them where the pilot can actually observe them: H-01 via the AR/AP matrix and `NUMBER_MISMATCH` tickets, H-05 via CA Ask 1. H-02, H-03 and H-04 are out of this score unless a recruited tenant exercises that path.
- **"Unaided" invoice** = invoice completed by a user with **no support contact in the prior 24 h**. Support contacts are recorded in **one place**: the in-app `support` tickets (the Tickets page exists), with CS logging WhatsApp/phone contacts there manually. Until that is set up (C5), the metric is **not collected** rather than guessed.
- **Mismatch reports:** add a ticket category `NUMBER_MISMATCH` plus a "Report a number issue" link on the dashboard cards and reports (small web change, week 3).
- **Nightly invariants:** `core-nightly-invariants` is already scheduled at 02:20 (verified); **no new schedule entry**. C5 instead verifies (a) the `beat` service is deployed on the staging/pilot host, (b) a failing run produces an alert someone receives (Sentry/Telegram), by injecting one violation in staging.

**D22 — What is the CA asked to do?** **Ask 1 (goes out week 0): worksheet review.** The CA independently computes GSTR-1 and 3B figures from the same source invoices of one pilot-month and records every variance against Bizboard's worksheets. It needs no GSTIN or legal filing. **Ask 2 (filing)** is opportunistic: only if a consenting pilot tenant's CA agrees, and **not required** for any score. QOS-0004/H-05 as written wants *filing* with no recalculation, so Ask 1 moves it from "unproven" to "reviewed", leaves it `P1-investigate`, and does not close it.

### Staffing and calendar

**D23 — Is the 6-week date real?** **No.** Re-estimated with PRE-5/6, the in-image smoke, a fixture rewrite, and the split of B2: **≈ 75–90 engineer-days**. With 2 engineers that is **8 weeks, 9 with buffer**, assuming the staging host exists by end of week 1. Assignment:
- **Engineer 1 (backend/ops):** PRE-1/2/4/5/6, A1–A6, C2, backend part of C3, C5/C6 with Ops.
- **Engineer 2 (web):** B2a, B3, B4, B5, A7, web part of C3, "report a number issue"; B2b on a branch during the pilot.
- **QA:** B1 protocol/facilitation, B5 manual pass, B6 goldens, retest.
- Web work before RC1 ≈ 20 days (B2a 5, B3 5, B4 5, B5 report-only 3, C3 web 2) — fits weeks 1–4; **B2b (≈ 10 d) is the part that moves after the pilot.**

**D24 — Can week 0 happen in 2–3 days?** **No.** Re-planned:
- **Week 0 (≈ 2 days, no engineering):** sign off D1–D24 **[F]** items (D3 waiver intent, D9 host/budget, D6 spreadsheet disposition, D16 compensation, D20 RPO, D22 ask); **start** study, pilot and CA recruitment (they have the longest lead time and need nothing from engineering).
- **Week 1:** PRE-1 slicing/review/tag candidate, PRE-2, PRE-4, host provisioning, `seed_load_tenant` build, C2 characterization.
- **Measurement starts week 2**, only once the host exists *and* the RC0 image exists. If the host slips, every dependent row slips one-for-one; the timeline in §8 states this explicitly.

---

## 1. What "3" means (rescoring rule, v2)

Score 3 = "partially adequate, supported by evidence". A characteristic reaches 3 when **all** its exit criteria hold; targets decide 3 → 4 (D4).

| Characteristic | Exit criteria (all required) |
|---|---|
| **Performance efficiency** | E-P1 dated k6 results on the **10k and 50k** tenants, per-scenario (list+complete, dashboard, reports), committed with numbers; E-P2 30-min mixed soak with CPU/RSS/DB-connection/queue readings; **E-P3 Gate bar met** (no endpoint p95 > 8 s, error < 0.5 %, no OOM) — a founder acceptance does **not** waive this gate; E-P4 gunicorn/limits sized from E-P1/2 and re-run; E-P5 top-20 query plans reviewed; E-P6 frontend initial-load budget enforced in CI; E-P7 each target-SLO miss has a root cause, a remediation date and a **founder acceptance** — F-PERF-01 remains open until the target SLOs pass |
| **Usability** | E-U1 study done per D15/D16 on RC0, report committed, SUS and unaided rate **recorded**; E-U2 every Sev-1 fixed or has a documented workaround (owner/date); **E-U3 retest of the fixed tasks with 3 new participants**; E-U4 axe: core tier blocking, all-routes report + ratchet baseline in CI; E-U5 keyboard-only + 44 px touch-target checks on POS and both editors; E-U6 states + Hindi checks green (D17); E-U7 one manual screen-reader pass recorded. *Cap:* SUS < 50 or < 3/5 unaided on core loop → score stays 2 until re-run |
| **Quality in use** | E-Q1 ≥ 3 tenants × ≥ 2 weeks of metrics (C1 set) on **RC1**; E-Q2 AR/AP matrix green (D19); E-Q3 every Go/No-Go and DPDP row is signed, waived, or blocked-with-owner-and-date; E-Q4 every incident has RCA + fix + regression test (cap rule in D4); E-Q5 alert path proven by drill; E-Q6 restore at 50k measured (D20) |

---

## 2. Critical decisions summary (what must be signed before week 1)

| # | Decision | Owner | Default if no answer |
|---|---|---|---|
| D1 | Accept a target-SLO miss in writing (the 8 s gate still has to pass) | Founder **[F]** | No miss can be accepted, so Performance does not reach 3 |
| D3 | Waiver of the 5-company UAT row for a 3-company controlled pilot | Founder **[F]** | Pilot cannot be called a Go candidate; ISO plan unaffected |
| D6 | Disposition of untracked spreadsheets/registers | Founder **[F]** | Left out of the RC; stay local |
| D9 | Staging host: provider, spec, domain, budget, secrets store | Founder **[F]** + Ops | Ephemeral 4 vCPU / 8 GB VM for perf runs; pilot blocked until a host is named |
| D16 | Participant compensation | Founder **[F]** | ₹1,000–1,500 per session; QA facilitates |
| D20 | Written acceptance of a 24-hour RPO for the controlled pilot | Founder **[F]** | PRE-6 does not complete; pilot does not start |
| D22 | CA ask sent in week 0 | Founder **[F]** | Worksheet review only (Ask 1). Filing is not required |

---

## 3. Prerequisites

| ID | Task | How | Artefact / acceptance |
|---|---|---|---|
| **PRE-1** (3–5 d) | Freeze **RC0** per D6 | Slice, review, tag; `gitleaks` on the diff; confirm no `.env`/credential files staged | Tag `rc0-2026-10-xx`; CI green on the tag; `git status` clean |
| **PRE-2** (2 d) | Pin images to Py 3.13/Node 22 + **in-image smoke job** (D7) | Dockerfile base images + digests; new CI job; extend `guard_config_consistency.py` | Guard passes; smoke job green on RC0 |
| **PRE-3** (2–3 d, Ops, needs D9) | Staging host + **TLS edge** | `docker-compose.staging.yml`; `scripts/edge_tls_smoke.sh` against the real host | PASS output pasted in `docs/pilot/ENV_CHECKLIST.md` row 1 |
| **PRE-4** (1 d) | Documented Postgres path (D8) | compose service + README + one-command script | A dev can run `pytest -m postgres` |
| **PRE-5** (4–5 d) | **Cross-tenant isolation matrix** (parent F-SEC-01; pilot-entry) | Generate route × method from the URL conf; tenant-A client hits tenant-B ids; fail CI on unclassified routes; allow-list with reasons | 100 % of routes classified; zero leaks; CI gate |
| **PRE-6** (3 d) | **Encrypted offsite backup, fail-closed** (D20) | `backup.sh` exits non-zero without recipient; offsite upload; backup-age alert | Offsite file present and decryptable; alert test fires |

---

## 4. Workstream A — Performance efficiency (1 → 3)

Reused assets (verified to exist): `load/k6_slo.js` (login in `setup()`, `DRAFT_INVOICE_IDS` pool), `load/k6_smoke.js`, `load/locust_smoke.py`, `load/SEED_50K.md`, `seed_draft_pool`, `seed_synthetic_bulk`, `seed_staging`, `tests/test_qos0016_dashboard_budget.py`, `web/e2e-golden/v95-dashboard-budget.spec.ts`, `deploy/pgbouncer.ini`, ticket log `docs/roadmap/ticket-logs/X-01.md`.

**A1 — `seed_load_tenant` + snapshots (5–6 d, BE).** Per D10 (gate, service path, mix, side-effect suppression with a zero-queued-tasks test, ≤ 4 h at 4 shards, 10k and 50k snapshots, `check_invariants` clean). *Replaces v1's "wrap `seed_synthetic_bulk`".*

**A2 — Gate/SLO runs (2 d, BE + Ops).** Per D12: sequential scenarios (`list_complete`, `dashboard`, `reports`) on **10k then 50k**; `EXPLAIN (ANALYZE, BUFFERS)` for list and Complete before the run; JSON to `load/results/` (gitignored) **and** a numbers-only summary table committed to `X-01.md`; resources sampled every 5 s (`docker stats`, `pg_stat_activity`, Redis queue length). Cell format: PASS/FAIL + number + SHA. The draft pool comes from the extended `seed_draft_pool` (D12), not from the current Demo-Traders-only command.

**A3 — Mixed soak + tenant fan-out (2 d).** `load/k6_mixed.js` (*new*): 70/30 read/write, 25 VUs ramped, 30 min; plus 20 tenants × 5 users (tokens per D12; `JWT_ACCESS_MINUTES=60` on staging only; draft pool 6,500). Record p95 drift between minute 5 and 30, DB connections, restarts. No container limits (D14).

**A4 — Query review (2–3 d).** `pg_stat_statements` top-20 by total and mean time; `EXPLAIN`; N+1 guards modelled on `test_qos0016_dashboard_budget.py` for list, receipts, stock summary; indexes via zero-downtime migrations (`guard_zdt_migrations`), re-checked with `migration-rehearsal.yml`.

**A5a — Sizing (1 d).** `gthread`, workers/threads from A2/A3, **timeout unchanged (120 s)**; DB connections ≤ 60 % of the pgbouncer pool; re-run.

**A6 — Long-request audit (2 d).** Table of endpoints × measured p95 on the 50k tenant, covering reports/GSTR, CSV/Excel exports, imports (`imports/views.py`), tenant backup/export (`accounts/tenant_backup.py`), bank-statement import, recurring invoices. PDF (`pdf_status` + 409 retry) and bill extraction (`extract_purchase_bill_task`) are already async (verified). Decision per row: index / async (PDF pattern) / accept. Rows > 8 s p95 are mandatory fixes (D2).

**A5b — Limits and timeout (1 d).** Per D11 and D14: timeout from A6, `--max-requests`, `mem_limit = 1.5 × peak`, `cpus`; re-run the gate scenario.

**A7 — Frontend budgets (2 d, Web).** `web/scripts/check-bundle-budget.mjs` (*new*) enforcing D13 (initial-load ratchet + per-chunk cap with allow-list); dashboard e2e to the median-of-5 rule against staging; throttled-profile LCP recorded, informational.

**A8 — Governance (0.5 d, QA).** Update `QOS-0003`, `QOS-0016` with `strength: measured`; **record founder acceptance of misses (D1)**; run `qos/tools/build_backlog.py`; qos-lint green. **F-PERF-01 is not closed unless the target SLOs pass.**

**Exit:** E-P1…E-P7 → **3**. **Risks:** host not ready (D9); service-path seed slower than budget (documented fallback); gate failing at 10k (then the finding is a real defect, scheduled before the pilot).

---

## 5. Workstream B — Usability (2 → 3)

Reused assets: `docs/UX_AUDIT_2026-09-30.md`, `docs/UX_ACTION_ITEMS.md`, `docs/ux/*` (personas_jtbd, cognitive_load_audit, heart_metrics, `L1_surface_ledger.csv`), `web/e2e/a11y.spec.ts` (≈ 13 routes today), `ux-axe-detail.spec.ts`, `ux-surface-crawl.spec.ts`, `route-smoke.spec.ts`, `pos-keyboard-checkout.spec.ts`, `pos-friction.spec.ts`, `mobile-layout.spec.ts`, `src/i18n/hi.ts`, QOS-0029/0095/0096/0097/0098. Crawl re-run steps: memory note "UX programme" (installed Chrome, port 34521).

**B1 — Study (QA, 1 d prep + 4 d run + 1 d synthesis).** Protocol per D15/D16: 5 participants (non-pilot), QA/UX facilitator, founder muted observer. **Core loop = tasks 1–3.** Task 4 is view-only and is reported separately, not in the 4/5 measure. Task 6 runs only after C2. POS is a separate mini-session. SUS in the participant's language. Assists and environment failures are logged separately. Report: `docs/ux/usability_study_2026-10.md` (*new*), findings Sev-1…4 linked to QOS items. **Run on RC0 once PRE-3 is green (target: week 2).**

**B2a — Minimal progressive disclosure, then Sev-1 fixes (5 d, Web).** Both land on RC1; they do not start on the same day. **Week 3, before synthesis:** progressive disclosure on the invoice and purchase editors — essentials first (customer, items, qty/price, total, Save/Complete); discounts, charges, shipping, TCS, transport and custom fields behind "More options" that auto-opens when a value or error lives there; keep Tab order and Enter-to-add-line. Target ≤ 12 controls at first paint. **Week 4, after the week-3 synthesis:** the Sev-1 fixes from B1, and only those. Anything else is ticketed for B2b. **B2b (full QOS-0095 redesign, ~10 d)** is built on a branch **during the pilot** and ships as RC2 after the window (D5). The pilot does not wait for the week-7 retest; Usability 3 is scored after that retest.

**B3 — Keyboard, touch, headings — QOS-0096 (5 d, Web).** Visible focus, no keyboard traps, focus return, one `h1` per page, ordered headings, ≥ 44×44 px touch targets on mobile layouts (375×812). Playwright: target-size assertion on tagged primary controls in `/pos`, `/sales/new`, `/purchases/new`; extend `pos-keyboard-checkout.spec.ts` to both editors.

**B4 — States and Hindi — QOS-0098 (5 d, Web).** Page × state inventory from `App.tsx` (139 lazy routes) and `L1_surface_ledger.csv`; shared `PageState` (skeleton, error with retry + `HelpCode`, empty with next-action); Hindi test per D17 (after PRE-1); "Report a number issue" link + `NUMBER_MISMATCH` ticket category (D21).

**B5 — Accessibility (3 d report-only in week 2 + 3 d to block + 1 d manual, Web/QA).** Staged per D18 (report-only → core tier blocking × 4 roles → all routes with a shrink-only baseline); skip rules and expiry-enforced allow-list; 200 % zoom and 320 px reflow checks on 6 core screens; manual NVDA+Chrome pass on login → invoice → payment in `docs/ux/a11y_manual_2026-10.md` (*new*). **New QOS item** for the axe gate; QOS-0007 untouched.

**B6 — Real-backend verification — QOS-0097 (3 d, QA).** Golden suite (`playwright.golden.config.ts`) against the **RC image** on staging; add goldens for the claimed 2026-09-30/10-01 fixes (dashboard, POS, editors, unsaved-changes guard).

**B7 — Retest + governance (QA, 3 d).** Retest the Sev-1-fixed tasks with **3 new participants** on RC1; update QOS-0029/0095/0096/0097/0098; regenerate backlog.

**Exit:** E-U1…E-U7 → **3** (D4 caps apply). **Risks:** recruitment lead time (starts week 0); study findings exceeding B2a (Sev-1 only before RC1; the rest ticketed); host dependency for B1/B6.

---

## 6. Workstream C — Quality in use (2 → 3)

Reused assets: `docs/pilot/*` (GO_NO_GO, UAT_CHECKLIST, ONBOARDING, CSAT, DPDP_POSTURE, ENV_CHECKLIST, FINAL_GATES_10, ARCH03_PILOT_RUNBOOK), `docs/ca/*`, `docs/ux/heart_metrics.md`, **H-01…H-05 in `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §11**, `docs/ops/` (exists, untracked files), QOS-0004/0021/0029/0030/0031/0049/0053/0082, `check_invariants`, `core.tasks.nightly_invariants_task` (02:20), Telegram/Sentry hooks, Django-admin ops page.

**C1 — Metric definitions + `pilot_metrics` (2 d, BE).** Eight counters defined here (D21), each with event, denominator and source: time-to-first-completed-invoice, weekly active days, invoices with no support contact in the prior 24 h, tickets per tenant-week, user-visible 4xx/5xx per 1k requests, `NUMBER_MISMATCH` reports, invariant failures per night, CSAT after week 2. H-01 and H-05 are recorded next to this table; they are not renamed into these counters. Management command in `ops/` emitting a weekly per-tenant table; shown in Django admin (staff tooling stays out of the customer SPA).

**C2 — AR/AP matrix (2–4 d, BE) — week 1.** Per D19: characterization tests extending `test_a15_cr090_plus.py`; fix only if they diverge; close QOS-0053 with evidence and note it in `docs/CROSS_FLOW_IMPACT_MAP.md`.

**C3 — Risk-behaviour hardening (4 d, BE+Web).** Confirmation with consequence text on destructive actions (inventory first); generated double-click e2e on POS, invoice Complete, receipt (single record asserted, `Idempotency-Key` present); `UnsavedChangesGuard` coverage per editor type.

**C4 — Sign / waive (2–3 d spread, Founder).** Every `GO_NO_GO.md` row becomes Done (evidence link), Blocked (owner, date) or Waived (reason, approver) — **including the D3 waiver**; DPDP checklist; ratify Q-OS rubric (QOS-0052). Go SHA = RC1.

**C5 — Operational readiness (3–4 d, Ops+BE).** Sentry live with a real DSN and `manage.py sentry_test_event`; 6 alerts (5xx rate, p95, queue depth/age, failed webhooks, backup age > 26 h, **nightly-invariant failure**); verify `beat` runs on the host and a seeded violation reaches the on-call phone ≤ 5 min; support process (named responder, hours, targets, shared inbox, ticket logging for D21); record in `docs/ops/`.

**C6 — Restore at volume (2 d, Ops).** Restore the 50k snapshot **from the offsite copy** (PRE-6) to a clean host, run `check_invariants`, record wall-clock (replaces the 4m6s demo-size RTO in `GO_NO_GO.md`).

**C7 — Pilot + CA (weeks 5–6 window; Founder + CS).** ≥ 3 businesses × ≥ 2 weeks on **RC1 only** (UI frozen, D5); founder on call; frozen scope profile; nightly `check_invariants` + verified backup; weekly 20-min check-ins; `docs/pilot/PILOT_LOG_2026-10.md` (*new*) with `pilot_metrics` output, incidents and support themes. **CA Ask 1** (worksheet review, D22) on a real pilot month.

**C8 — Governance (1 d).** Update QOS-0004/0021/0029/0030/0031/0049/0053 with `strength: measured`; regenerate backlog; qos-lint green.

**Exit:** E-Q1…E-Q6 → **3** (D4 caps apply). **Risks:** pilot recruitment; CA availability (Ask 1 suffices); an incident (evidence, unless it hits the cap rule).

---

## 7. Dependencies

- Host (D9) → PRE-3 → A1 snapshots → A2/A3, B1/B6 staging, C5, C6.
- PRE-2 → every number (measure the image).
- C2 → B1 task 6 → RC1.
- PRE-3 green → B1. Synthesis is the following week. Sev-1 fixes are the week after synthesis, and they are the last commit on RC1.
- B2a (disclosure + Sev-1) / B3 / B4 / C2 / PRE-5 / PRE-6 → **RC1 → pilot**.
- A2/A3 → A5a (timeout stays 120 s) → A6 → A5b. A5a does not follow A6.
- B2b ships only after the pilot window, so it cannot contaminate C1 metrics.
- The two-week pilot clock starts the day RC1 is deployed to the pilot host. It is calendar days, not the week numbers in the table. If that deploy slips, E-Q1 and the week-8 rescore slip by the same number of days.

## 8. Timeline (assumes the host exists by end of week 1; every host slip moves dependent rows one-for-one)

| Week | Backend/Ops (Eng 1) | Web (Eng 2) | QA / Founder |
|---|---|---|---|
| **0** (2 d) | — | — | Sign **[F]** decisions; start study, pilot and CA recruitment |
| **1** | PRE-1 slices → RC0, PRE-2, PRE-4, host build, A1 build, **C2 matrix** | PRE-1 web slices, B5 generator only | B1 protocol/consent/recruiting |
| **2** | PRE-3 TLS, A1 seed (10k/50k), **A2** | B3 start, B4 start, B5 report-only baseline | **B1 study on RC0**, starting the day PRE-3 is green; POS mini-session |
| **3** | A3 soak, **A5a** (timeout stays 120 s, re-run), A4 queries, PRE-5 | **B2a disclosure only** (no study fixes yet), B4, number-issue link, B5 → core blocking | B1 synthesis; C4 pass; C5 start |
| **4** | **A6 then A5b** (timeout + limits), PRE-6, C3 backend | **B2a Sev-1 fixes**, B3/B4 finish, C3 web, A7 | B6 goldens on RC image, B5 manual, C6 restore after PRE-6 → **tag RC1; pilot-entry checklist** |
| **5–6** | A8, C5 drills, support the pilot | **B2b on branch (not shipped)**, B5 all-routes ratchet | **Pilot window on RC1**, C7 weekly logs; CA Ask 1 |
| **7** | Fix pilot findings (no UI changes until window closes) | **RC2 = B2b**, after window | **B7 retest (3 new participants)** |
| **8** | Re-score from the **RC1** artefacts. An A2 re-run on RC2 is informational and does not gate the score | — | **Re-score all three**; update parent scorecard |
| **9** | buffer | buffer | buffer / CA follow-up |

## 9. Waiver template for D3 (founder to complete; I have not signed or filled it)

> *Waiver — `GO_NO_GO.md`, row "UAT matrix ≥5 companies".* For the controlled pilot beginning ____, the requirement is replaced by: **≥ 3 businesses, ≥ 2 weeks each, on RC1**, with founder on call, frozen scope profile, nightly invariants and verified backups. Reason: ____. Risk accepted: ____. Re-instated for: general release. Approver: ____ Date: ____.

## 10. Definition of done and effort

- Every exit criterion in §1 has a committed artefact linked from its QOS item; `docs/PRODUCT_QUALITY_BACKLOG.md` regenerated; parent scorecard updated (Performance 3, Usability 3, Quality in use 3, confidence Low → Medium).
- **Not in scope for 3:** meeting every SLO, WCAG AAA, app-store distribution, HA/multi-region, PITR, external pen-test, SQLite→Postgres default flip.

| Stream | Eng-days | Non-eng |
|---|---|---|
| Prerequisites incl. PRE-5/6 | 17–21 | Ops 3 |
| A Performance | 18–22 | Ops 4 |
| B Usability (B2b counted post-pilot) | 24–28 | QA 10, Founder 3 |
| C Quality in use | 16–20 | Founder 8, Ops 4, CS 10 |
| **Total** | **≈ 75–90** | ≈ 45 |

Two engineers ≈ 8 weeks if the host and decisions land on time; 9 with buffer.

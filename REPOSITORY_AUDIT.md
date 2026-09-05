# Repository Audit — Bizboard

**Date:** 2026-09-05
**Branch:** `main` (clean working tree; 212 commits; `.git` ≈ 61 MB)
**Scope:** Phase 1 audit only — no application code changed.
**Method:** Repository-wide file/dependency/documentation inspection. Behavior derived from code, not documentation.

---

## 1. Repository overview

Bizboard is a cloud-first GST billing / business-management platform for Indian SMBs. Three deployables plus docs:

| Area | Tracked files | Stack | Notes |
|---|---|---|---|
| `backend/` | ~700 | Django 5 + DRF + Celery + Postgres/SQLite | ~19 Django apps; 121 test modules in `backend/tests/` |
| `web/` | ~383 | React 18 + MUI 6 + Vite 6 + TanStack Query + Playwright | 172 page components |
| `mobile/` | ~56 | Capacitor 6 WebView shell (Android focus) | Thin shell over `web/` build |
| `docs/` | ~358 | Markdown + PNG + helper scripts | **Largest single source of debt** (see §4) |
| root | ~40 | stray `.md`, `.docx`, tmp files | Mostly historical/superseded artifacts |

**Total tracked:** 1559 files. Breakdown: 726 `.py`, 193 `.png`, 193 `.tsx`, 163 `.md`, 134 `.ts`, 30 `.cjs`.

### Architecture (from code)

- **Documents are the source of truth.** No customer/supplier ledger tables — balances derived from completed documents, returns, and payment allocations (`backend/ledgers/services.py`, `LedgerService.bulk_*_outstanding`).
- **Append-only typed stock movements**; document completion + inventory effects are atomic.
- Every business query scoped to `company_id` (shared-DB multi-tenant). Optional Postgres RLS, flag-gated **off** (`POSTGRES_RLS_ENABLED=0`).
- Public API versioned under `/api/v1/`; OpenAPI via drf-spectacular; snapshot at `docs/openapi-snapshot.json` drives generated TS types.
- **Advanced surfaces feature-flagged dark in production:** GSTR filing, e-invoice submit, accounting books, AI insights, Tally sync, Manufacturing, Payroll, CRM, POS. These modules have real code and are intentionally gated — **not dead code**.

### Entry points

- Backend: `backend/manage.py`, `backend/config/` (settings/urls/wsgi/asgi/celery), `backend/core/urls.py`.
- Web: `web/src/main.tsx` → `web/src/App.tsx`.
- Mobile: `mobile/` Capacitor config wrapping the web build.
- CI: `.github/workflows/{ci,cd,codeql,mobile-android}.yml`.

---

## 2. Architecture map (backend domains)

| App | Role | Largest file (LOC) |
|---|---|---|
| `core` | Cross-cutting: auth, permissions, RLS, idempotency, feature flags, notifications, LLM, PDF/file assets, help system | `core/services/*` (many) |
| `imports` | CSV/bill import pipelines | **`services.py` 3014** |
| `reporting` | GST returns + financial reports | **`gst_returns.py` 2421**, `views.py` 1267 |
| `accounting` | Optional dual-ledger books, GL, FIFO | **`services.py` 2008** |
| `inventory` | Stock movements, valuation, godown/expiry | `services.py` 1904 |
| `payments` | Receipts, supplier payments, allocations, gateway | `services.py` 1791, `gateway.py` 960 |
| `sales` / `purchases` | Invoices, quotes, orders, returns, CN/DN | `services.py` 1436 / 1367 |
| `accounts` | Tenant/company/user, backup/DR | `views.py` 1385, `tenant_backup.py` 1315 |
| `ledgers` | Derived party ledgers | `services.py` 1006 |
| `masters`, `banking`, `billing` (SaaS), `crm`, `manufacturing`, `payroll`, `insights`, `integrations`, `search` | Domain / flag-gated modules | — |

Dependency direction is generally `views → services → models` with `core` as the shared base. No circular-import problems surfaced in the audit (one historical circular-import fix noted in `MASTER_ISSUE_REGISTER.md`, since resolved via middleware).

---

## 3. Prioritized findings

### P0 — Dangerous
**None found in the audit.** No committed secrets in tracked files (`.env` is git-ignored + guarded by `.githooks/pre-commit`; `.env.example` / `.env.production.example` are templates). No obvious data-corruption or auth-bypass patterns spotted at audit depth. Business-logic correctness (GST/tax/FIFO) was **not** line-audited here and is explicitly out of scope for cleanup — it is covered by the existing `docs/reviews/` register and requires CA sign-off.

### P1 — High value

| # | Finding | Evidence | Recommendation |
|---|---|---|---|
| P1-1 | **Review/audit scaffolding sprawl.** Two+ overlapping, stale-dated review systems: `docs/reviews/` (Waves 0–22, ~46 md + ~55 `_wave*.py`/`_ux*.js` helper scripts + ~200 screenshots in `screenshots_uxaudit/` + `screenshots_wave2/`), **plus** root `DEEP_CODE_REVIEW_2026-09-02.md`, `DEEP_CODE_REVIEW_2026-09-03.md` (492 KB), `FIX_PLAN_2026-09-03.md` (260 KB), `COMPREHENSIVE_CODE_REVIEW_FINDINGS.md` (44 KB), **plus** `docs/roadmap/ticket-logs/` (36 files). `MASTER_ISSUE_REGISTER.md` alone is **69,839 lines / 1.9 MB**. | `git ls-files docs/reviews` | **CONSOLIDATE + DELETE.** Keep one authoritative issue register + one changelog. Archive the rest under `docs/archive/` or delete the helper scripts outright (they are one-shot wave automation). Delete committed screenshot sets (regenerable; ~28 MB of PNGs). |
| P1-2 | **`web/audit_scripts/` — 35 throwaway `.cjs` runners** (`test_purchase_save.cjs`, `…save2.cjs`, `…save3.cjs`, `run_phase2.cjs`, `run_phase2_fixed.cjs`, `run_phase2_full.cjs`, …) + committed JSON result blobs. Not wired into `package.json`, lint, or CI. | `git ls-files web/audit_scripts` | **DELETE** the directory. Genuine E2E lives in `web/e2e/` + `web/e2e-golden/` (Playwright, wired to scripts). |
| P1-3 | **Root-level stray/temp files committed or lingering.** `backend;C/` (empty dir from a botched `cd backend;C:\…` — untracked), `~$reenShot.docx` (Word lock file, untracked), `.tmp_lan_out.txt`, `web_build_out.txt` (git-ignored but present), `.vite/vitest/results.json` (**tracked** test cache), `backend/_tmp_sprint0_check.py`, `backend/_tmp_run_sprint0_tests.py`, `backend/_pytest_fail_extract.txt` (**tracked** scratch). | `ls -la`, `git ls-files` | **DELETE.** Add `.vite/` and `backend/_tmp_*` / `_pytest_fail_extract.txt` to `.gitignore`. |
| P1-4 | **`docs/reviews/` contains executable helper scripts, not docs.** ~40 `_wave{6..22}_*.py`, `_annotate_sprint6.py`, `_generate_audit.py`, `_ux_wave2_*.js`, `_stats.json` (240 KB), `_open_ids_wave15.txt`, runner `_out.txt` files. | `git ls-files docs/reviews \| grep -v '\.md$'` | **DELETE.** One-shot automation for closed waves; no ongoing use. |
| P1-5 | **Derived artifacts committed alongside their source.** `extracted_prd.txt` (21 KB) is a text dump of `Product Requirements Document.docx`; not referenced anywhere. `ScreenShot.docx` (407 KB) is a screenshot dump. `docs/openapi-snapshot.json` (672 KB) is generated but *is* referenced by `web` type-gen and a CI check — **keep that one**. | `git grep extracted_prd` (0 hits) | **DELETE** `extracted_prd.txt`, `ScreenShot.docx`. Keep the `.docx` PRD or move to `docs/requirements/`. |

### P2 — Medium

| # | Finding | Recommendation |
|---|---|---|
| P2-1 | **~25 root-level `.md` files**, most already self-labelled "Historical / Superseded / Archived / pointer stub" (`SECURITY_REPORT.md`, `TEST_REPORT.md`, `BUG_REPORT.md`, `PERFORMANCE_REPORT.md`, `PRODUCTION_READINESS.md`, `ACCOUNTING_VALIDATION.md`, `CALCULATION_VALIDATION.md`, `UX_*`, `IMPORT_FLOW_ISSUES.md`, `BILL_IMPORT_REDESIGN_PLAN.md`, `MVP_IMPLEMENTATION_PLAN.md`). | **DELETE** the ones marked superseded; **MOVE** any still-authoritative content (MVP scope, calculation formulas) into `docs/`. Target: only `README.md` at root. |
| P2-2 | **7× `PHASE{1..7}_IMPLEMENTATION_PLAN.md` at root** are 16–24-line pointer stubs to `docs/phase{N}/`. `docs/archive/PHASE1_IMPLEMENTATION_PLAN.md` duplicates the old plan. | **DELETE** all 7 root stubs; link `docs/` phase docs from `README.md` instead. Keep `docs/phase{N}/`. |
| P2-3 | **`bugs/` (8 files) vs `docs/reviews/` vs `docs/roadmap/ticket-logs/` (36)** — three parallel issue-tracking conventions. | Pick one. Fold `bugs/` into the register or delete if closed. |
| P2-4 | **`docs/` has 11 sibling top-level folders** (`phase1..7`, `pilot`, `roadmap`, `reviews`, `help`, `ca`, `requirements`, `onboarding`, `archive`) with no `docs/README.md` index and no `architecture.md` / `setup.md` / `testing.md`. | Introduce `docs/README.md` + the canonical set (`architecture.md` can be distilled from `README.md` "Architecture invariants" + `docs/reviews/02_ARCHITECTURE_REVIEW.md`). |
| P2-5 | **Backend test modules named by delivery wave** — 53 of 121 files are `test_wave_*`, `test_sprint_*`, `test_phase_*`, `test_ws*`, `test_w0_*`. Tests are organized by *when added*, not *what they cover*. | Low-risk rename only where a file maps cleanly to one domain; otherwise **leave** — do not merge/delete (regression coverage). P3 effort at best. |
| P2-6 | **`constraints.txt` partially duplicates `requirements.txt`** version ranges. Intentional (documented CI pin file) but a second place to keep in sync. | KEEP — verify it is actually used in CI; if not, delete. |

### P3 — Cosmetic
- `.tmp_invoice_preview/`, `.scratch/`, `.vscode/` present locally, correctly git-ignored — no action.
- README "Wave 17 / 18 / 19 honesty" sections are accreting; fold into `docs/reviews/CHANGELOG.md` and keep README lean.
- Very few `TODO`/`FIXME` markers in `backend/` + `web/src` (≈5, excluding tests) — code-comment hygiene is **good**.

---

## 4. Documentation inventory & classification

163 tracked `.md`. By location: `docs/reviews` 46, `docs/roadmap/ticket-logs` 36, `docs/pilot` 13, `docs/help` 8, `bugs` 8, `docs/roadmap/charters` 5, root ≈25, `docs/phase*` 9, other ≈13.

| Category | Files (representative) | Action |
|---|---|---|
| **A. Current / authoritative** | `README.md`, `docs/pilot/*` (DoD, GO_NO_GO, runbooks), `docs/help/*`, `docs/requirements/*`, `docs/roadmap/charters/*`, `docs/reviews/KNOWN_LIMITATIONS_AND_TECH_DEBT.md`, `docs/reviews/CHANGELOG.md` | Keep. Index from `docs/README.md`. |
| **B. Outdated** | Root `SECURITY_REPORT.md`, `TEST_REPORT.md`, `BUG_REPORT.md`, `PERFORMANCE_REPORT.md` (all self-marked "Historical … do not treat as current") | Delete (content superseded by `docs/reviews/`). |
| **C. Duplicate** | Root `PHASE{1..7}_IMPLEMENTATION_PLAN.md` (stubs) vs `docs/phase*/`; `PRODUCTION_READINESS.md` vs `docs/reviews/21_PRODUCTION_READINESS.md`; `docs/archive/PHASE1_*` | Delete root copies; keep `docs/` version. |
| **D. Planning** | `MVP_IMPLEMENTATION_PLAN.md`, `BILL_IMPORT_REDESIGN_PLAN.md`, `docs/roadmap/WAVES_*_CURSOR_IMPLEMENTATION_PLAN.md`, `docs/onboarding/NEW_USER_ONBOARDING_PLAN.md` | Move to `docs/roadmap/` or `docs/archive/`; MVP plan is still referenced by README — move + fix link. |
| **E. Implementation record** | `docs/reviews/ARCHITECTURAL_DECISIONS.md`, `CHANGELOG.md`, `MASTER_ISSUE_REGISTER.md`, `docs/reviews/19_TECHNICAL_DEBT.md`, `20_REFACTORING_PLAN.md` | Keep, but **compress/split** `MASTER_ISSUE_REGISTER.md` (1.9 MB → archive closed waves). |
| **F. Temporary LLM artifact** | `docs/reviews/_wave*.py` / `_ux*.js` / `_stats.json` / `*_out.txt`, `web/audit_scripts/*`, `docs/reviews/*_MASTER_PROMPT.md`, root `COMPREHENSIVE_CODE_REVIEW_FINDINGS.md` / `DEEP_CODE_REVIEW_2026-09-0{2,3}.md` / `FIX_PLAN_2026-09-03.md`, `docs/reviews/DEEP_*` / `QUALITY_AUDIT_LIVE_*` / `WORLDCLASS_*` | **Delete** scripts. **Archive or delete** the point-in-time review dumps once their open items are migrated to the single register. |
| **G. Unknown** | `docs/reviews/CODE_REVIEW_wip_phase0_diff_2026-08-25.md`, `docs/ca/CA_SIGN_OFF_CHECKLIST.md`, `docs/reviews/E2E_UI_PLAYWRIGHT_VALIDATION_*` | Verify with maintainer before acting. |

**Target documentation hierarchy:**
```
README.md
docs/
  README.md            (index — new)
  architecture.md      (distilled — new)
  setup.md             (from README "Local development")
  testing.md
  deployment.md        (from docker-compose.prod + nginx + scripts)
  features/            (phase1..7 canonical docs, renamed)
  decisions/           (ARCHITECTURAL_DECISIONS.md)
  pilot/               (keep as-is — active)
  reviews/
    ISSUE_REGISTER.md  (single, current-wave only)
    CHANGELOG.md
    archive/           (closed-wave registers, screenshots removed)
```

---

## 5. Dead code candidates

Backend/web are comparatively lean; **no large dead-code seams found.** Checked and **cleared** (NOT dead):
- `web/src/api/legacy/*` — re-exported via `web/src/api/resources.ts` "legacy barrel", still widely imported. **Keep.**
- `manufacturing` / `payroll` / `crm` / `insights` backend apps — real, intentionally flag-gated dark. **Keep.**
- `openai` **and** `anthropic` deps — both used in `backend/core/services/llm.py`. **Keep both.**

Genuine dead/removable weight is almost entirely **non-code**: the audit scripts, wave helpers, screenshots, and superseded markdown in §3/§4.

Minor code-level items to verify before removing:
- `backend/_tmp_sprint0_check.py`, `backend/_tmp_run_sprint0_tests.py` — scratch runners, not referenced by `pytest.ini` or CI. **DELETE (high confidence).**
- `scripts/split_phase_pages.py` — one-shot doc splitter; safe to archive once phase-doc consolidation is done.

---

## 6. Dependency assessment

**Backend (`requirements.txt` 21 pkgs, `requirements-dev.txt` +3):** lean and appropriate. `requirements-dev.txt` already correctly separates test/lint tooling out of the prod image (BUG-711). No obvious unused packages at manifest level — `reportlab`, `qrcode`, `pypdf`, `pypdfium2`, `openpyxl` all map to PDF/Excel features; `sentry-sdk`, `celery`, `redis` are wired. **Recommend a runtime import check** (`pip-check`/`deptry`) to confirm, but nothing jumps out.

**Web (`web/package.json`):** 17 deps / 27 devDeps, all recognizable and in use (MUI, TanStack Query + Virtual, RHF + zod + resolvers, axios, dayjs, Sentry, react-router 7, vite-plugin-pwa, Playwright + axe, vitest + testing-library). No duplication (single date lib `dayjs`, single form lib RHF). **No action.**

**Mobile:** 8 Capacitor plugins, all plausible for a WebView shell. **No action.**

**Dependabot** has ~40 open branches (`remotes/origin/dependabot/*`) including a **Python 3.14** bump that conflicts with the CI-pinned 3.12 target. Triage separately from cleanup — do **not** fold dependency upgrades into this work.

---

## 7. Architectural over-engineering

Low overall. The backend follows a consistent `views → services → models` shape without facade/manager/adapter tower proliferation. Observations:

- **Large service modules** (`imports/services.py` 3014, `reporting/gst_returns.py` 2421, `accounting/services.py` 2008, `inventory/services.py` 1904). Mostly *inherent* domain complexity (GST return formats, FIFO, import mapping). **Split by responsibility only where a clear seam exists** — Phase 3 work, behavior-preserving, not urgent.
- **`web` NewInvoicePage ≈1680 LOC** (flagged in `docs/reviews/19_TECHNICAL_DEBT.md` as BB-000751) — genuine component-decomposition candidate.
- **Dual API client generations** (`web/src/api/legacy/*` barrel vs typed `typedClient.ts` / `openapi-types.ts` / per-domain `*.ts`). Intentional migration in progress (Wave 19F). Track completion; don't add a third.

No unnecessary generic `Abstract*<T>` / `GenericFactory<T>` scaffolding found.

---

## 8. Highest-risk areas (handle with care / do NOT casually change)

1. **`backend/core/migrations/` (22) + every app's migrations** — 22 RLS-related migrations; never edit/delete.
2. **GST / tax / FIFO / GL calculation code** (`core/services/billing.py`, `reporting/gst_returns.py`, `accounting/services.py`, `inventory/services.py`, `web/src/utils/{tax,money}.ts`) — CA-approval gated; cleanup must not touch numbers.
3. **`core/rls.py` + RLS migrations** — multi-tenant isolation; flag currently off, code must stay correct.
4. **`accounts/tenant_backup.py`** — DR/backup path; PII/financial.
5. **Idempotency / webhook / gateway** (`core/idempotency.py`, `payments/gateway.py`, `core/services/gsp_*`) — money movement.
6. **`docs/openapi-snapshot.json`** — generated but consumed by web type-gen + CI check; regenerate, don't hand-edit, don't delete.
7. **`backend/tests/` wave-named modules** — ugly names, real coverage. Do not delete.

---

## 9. Recommended execution order

**Phase 2 — Safe cleanup (no approval needed; test after each batch):**
1. Delete untracked junk: `backend;C/`, `~$reenShot.docx`, `.tmp_lan_out.txt`.
2. Untrack + gitignore build/scratch: `.vite/vitest/results.json`, `backend/_tmp_*.py`, `backend/_pytest_fail_extract.txt`.
3. Delete `web/audit_scripts/` (35 files + JSON).
4. Delete `docs/reviews/_*.py`, `docs/reviews/_*.js`, `docs/reviews/_*.txt`, `docs/reviews/_*.json` (wave helpers).
5. Delete `docs/reviews/screenshots_uxaudit/` + `screenshots_wave2/` (regenerable PNGs).
6. Delete `extracted_prd.txt`, `ScreenShot.docx`.
7. Delete root superseded reports (§4 category B) and the 7 `PHASE*_IMPLEMENTATION_PLAN.md` stubs + `docs/archive/PHASE1_*` after confirming no inbound links, fixing README.
8. `cd backend && pytest` · `cd web && npm run lint && npm test -- --run && npm run build` · `docker compose config`.

**Phase 3 — Structural (needs approval):**
9. Consolidate `docs/` into the §4 target hierarchy; add `docs/README.md`, `architecture.md`, `setup.md`.
10. Collapse the multiple review dumps into one `ISSUE_REGISTER.md` + archive; split/compress `MASTER_ISSUE_REGISTER.md`.
11. Merge `bugs/` into the single register.
12. (Optional, separate PRs) NewInvoicePage decomposition; large `services.py` splits — behavior-preserving, one module per PR.

**Phase 4 — Validation:** full backend + web test/lint/build/type-check; `docker compose config`; diff API snapshot.

---

## 10. What to explicitly NOT change

- Business logic: GST/tax/TCS/TDS calculations, pricing, FIFO/COGS, GL postings, document status machines, allocation math.
- Any migration file.
- API contracts under `/api/v1/` and `docs/openapi-snapshot.json` semantics.
- Feature-flag gating of manufacturing/payroll/CRM/accounting/GSTR/e-invoice/POS.
- RLS code paths (`core/rls.py`, RLS migrations) even though the flag is off.
- `backend/tests/` — no deletions; renames only where unambiguous.
- Dependency versions — no upgrades as part of cleanup; leave Dependabot triage separate.
- `README.md` architecture invariants and honesty sections' *substance* (may relocate, not reword).
- `constraints.txt`, `.githooks/pre-commit`, CI workflows — keep unless proven unused.

---

## Appendix — quick stats

- Tracked files: 1559 · `.git`: ~61 MB · commits: 212
- Markdown: 163 files; ~55 non-md "helper" files under `docs/reviews/`; ~400 PNG screenshots across `docs/reviews/screenshots_*`
- Largest tracked file: `docs/reviews/MASTER_ISSUE_REGISTER.md` (1.9 MB / 69,839 lines)
- Largest code file: `backend/imports/services.py` (3014 LOC)
- Root `.md` files: ~25 (target: 1)
- Backend apps: ~19 · backend tests: 121 modules (53 wave/sprint/phase-named)
- Open Dependabot branches: ~40

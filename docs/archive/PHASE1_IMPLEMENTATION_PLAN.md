# BizBoard — Phase 1 Implementation Plan (ARCHIVED)

> **Archived.** Pilot hardening is **Phase 0** — see [`docs/pilot/`](../pilot/).  
> Post-pilot document completeness is **Phase 1** — see [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](../phase1/PHASE_1_DOCUMENT_COMPLETENESS.md).  
> Root stub: [`PHASE1_IMPLEMENTATION_PLAN.md`](../../PHASE1_IMPLEMENTATION_PLAN.md).

**Status:** Archived (historical)  
**Goal:** Make BizBoard safe for a **paid pilot (20–50 businesses)** with CA-credible GST math, hardened ops/security, and clear UX.  
**Out of scope:** Product Phase 2 backlog (credit/debit notes, GSTR filing, e-Invoice, POS, offline, multi-warehouse, full RBAC roles beyond light flags, httpOnly cookie auth migration).  
**Source:** `TEST_REPORT.md`, `BUG_REPORT.md`, `PRODUCTION_READINESS.md`, `MVP_IMPLEMENTATION_PLAN.md` §21  

**Target duration:** ~4–5 weeks (1 senior full-stack + 0.5 QA + CA review week 3–4)  
**Exit criteria:** All Phase 1 P0 items Done; CA sign-off letter; staging UAT golden path green; zero open Critical bugs for 7 days.

---

## 1. Phase 1 scope map

| Wave | Theme | Bug / gap IDs | Priority |
|------|--------|---------------|----------|
| **W1** | Money correctness | BUG-001, BUG-003, BUG-014, BUG-015, BUG-016 | P0 |
| **W2** | API contract & GST guards | BUG-002, BUG-010, BUG-017, BUG-018, BUG-020 | P0/P1 |
| **W3** | Security & production config | BUG-004, BUG-005, BUG-007, BUG-008, BUG-021, BUG-022, BUG-019 | P0 |
| **W4** | Permissions, UX, performance | BUG-009*, BUG-012, BUG-013, BUG-024–027, aging | P1 |
| **W5** | CA pack, E2E, pilot ops | CA sign-off, E2E golden path, runbooks | P0 gate |

\*Phase 1 delivers **permission flags + cancel/export gates**, not full Accountant/Viewer roles (those stay Phase 2 / GA).

**Explicitly deferred to Phase 2 / GA (do not implement in Phase 1):**

- BUG-011 Credit/Debit notes  
- GSTR-1 / GSTR-3B, e-Invoice / e-Way  
- Reverse charge, tax-inclusive pricing, full ITC registers  
- BUG-006 httpOnly cookie session rewrite (mitigate via CSP + XSS hygiene in W3)  
- Broader roles (Accountant, Manager, Viewer) beyond new boolean flags  
- Android / thermal / offline / Tally  

---

## 2. Architecture decisions (locked for Phase 1)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Backend remains source of truth** for tax; FE must mirror `billing.compute_document_totals` residual split exactly | Avoid dual-math drift |
| D2 | Add optional **`POST /sales/invoices/preview-totals/`** (and purchase twin) for authoritative live preview | Guarantees parity; FE local calc kept for snappy UX but must match |
| D3 | Document discount: introduce **`invoice_discount_mode`**: `AFTER_TAX` (current) \| `BEFORE_TAX` (reduces taxable / GST) | CA-safe; no silent behavior change for existing drafts |
| D4 | Missing party state: **warn + block Complete** when company is GST-registered and party state/GSTIN state code missing | Stops silent IGST misclassification |
| D5 | Prod profile: `DJANGO_DEBUG=0`, refuse default `SECRET_KEY`, `OTP_DEBUG_ECHO=false` | Fail-fast misconfig |
| D6 | Phase 1 session: keep JWT in localStorage; add **CSP + upload hardening + rate limits** | Cookie migration is larger; pilot-acceptable with mitigations |
| D7 | WhatsApp remains share-link; Email requires real SMTP in staging/prod | Honest product copy |

---

## 3. Delivery waves (calendar)

```text
Week 1 ████████  W1 Money correctness
Week 2 ████████  W2 API/GST guards + start W3 security
Week 3 ████████  W3 finish + W4 UX/perf/permissions
Week 4 ████████  W5 CA pack + E2E + staging UAT
Week 5 ░░░░░░░░  Buffer / pilot onboarding dry-run
```

Parallelism: FE tax parity (W1) can run alongside BE discount mode migration; security (W3) parallel with W2 after D-decisions locked.

---

## 4. Epic details

---

### EPIC A — Tax & totals parity (W1)

**Objective:** Screen, API, DB, and PDF always show the same money for the same inputs.

#### A1. Align frontend line tax with backend residual split
**Bugs:** BUG-001, BUG-014  

| Step | Work |
|------|------|
| 1 | Change `web/src/utils/tax.ts` `calculateLineTax` intra-state branch to: `taxRaw = taxable * rate/100`; `cgst = roundMoney(taxRaw/2)` using **same order as BE** (half of unrounded tax, then `sgst = roundMoney(taxRaw) - cgst`). Prefer implementing via Decimal-like helpers or shared golden vectors. |
| 2 | Update comment to match BE (`sgst = q2(tax) - half`). |
| 3 | Add FE unit cases for ₹10.05 @ 18%, ₹11.11 @ 18%, multi-line odd paise. |
| 4 | Add BE fixture export or shared JSON golden file `testdata/tax_parity_cases.json` consumed by pytest + Vitest. |

**Files:**  
`web/src/utils/tax.ts`, `web/src/utils/tax.test.ts`, `backend/tests/test_tax_calc.py`, `backend/tests/test_billing_totals.py`, new `shared/tax_parity_cases.json` (or `backend/tests/fixtures/` + copied to web)

**Acceptance:**  
- For every golden case, FE line CGST/SGST/IGST/lineTotal == BE within ₹0.00.  
- New Invoice UI preview matches `POST` response totals for odd-paise SKU.

#### A2. Harden FE rounding helpers
**Bugs:** BUG-015  

| Step | Work |
|------|------|
| 1 | Replace EPSILON float rounding with string/Decimal-style half-up (e.g. scale to integer paise via `Math.round(Number((value * 100).toFixed(8)))` **or** `decimal.js` if already acceptable). |
| 2 | Expand `money.test.ts` with HALF_UP edge cases (x.xx5). |

**Acceptance:** FE `roundMoney` matches Python `q2` for 200 random samples in a generator test.

#### A3. Align `isIntraState` FE ↔ BE
**Bugs:** BUG-016  

| Step | Work |
|------|------|
| 1 | Document single rule: prefer GSTIN first 2 digits if either side looks like GSTIN; else case-insensitive state name; empty party → **unknown** (not silently intra). |
| 2 | Update `billing.is_intra_state` and `tax.isIntraState` to same helper semantics. |
| 3 | Tests: KA company + blank party; KA + MH; GSTIN `29…` vs `27…`; name “Karnataka” vs GSTIN 29. |

**Acceptance:** FE and BE agree on intra/inter for all matrix rows; blank party is `unknown` (see A4/B2 for Complete block).

#### A4. Authoritative preview endpoint (recommended)
**Optional but strongly recommended**

| Step | Work |
|------|------|
| 1 | `POST /api/v1/sales/invoices/preview-totals/` body = draft serializer fields (unsaved). Returns totals + per-line tax. |
| 2 | Same for purchases. |
| 3 | FE: debounce 300ms; use preview when online; fall back to local calc offline/error with banner “Showing local estimate”. |

**Acceptance:** With network on, displayed totals always equal last preview response.

**Estimate:** A1–A3 = 3–4d · A4 = 2d  

---

### EPIC B — Discount semantics & GST guards (W1–W2)

**Objective:** Discounts and place-of-supply cannot silently create GST mistakes.

#### B1. Invoice / purchase discount modes
**Bugs:** BUG-003, BUG-024  

| Step | Work |
|------|------|
| 1 | Add field `invoice_discount_mode` on sales & purchase invoices: `AFTER_TAX` (default, current) \| `BEFORE_TAX`. Migration + serializer + PDF. |
| 2 | In `compute_document_totals`: if `BEFORE_TAX`, allocate invoice discount across taxable lines (proportional to taxable) **before** GST, or apply as document-level taxable reduction then recompute tax (CA-confirm method — **default: proportional to line taxable**). |
| 3 | FE: replace “+ Discount” with select + amount: “Discount (reduces GST)” vs “Cash discount (after tax)”. i18n keys in `en.ts`. |
| 4 | Mirror on `NewPurchasePage`. |
| 5 | PDF labels must state mode. |
| 6 | Tests: ₹100 @ 18% − ₹10 BEFORE_TAX → taxable 90, tax 16.20, etc.; AFTER_TAX unchanged from today. |

**Files:**  
`backend/sales/models.py`, `purchases/models.py`, migrations, `billing.py`, serializers, PDF helpers, `NewInvoicePage.tsx`, `NewPurchasePage.tsx`, `i18n/en.ts`

**Acceptance:**  
- CA-approved examples in `CALCULATION_VALIDATION` appendix.  
- UI never shows ambiguous “+ Discount”.  
- Existing completed invoices remain AFTER_TAX historically.

#### B2. Block Complete when place-of-supply unknown (GST docs)
**Bugs:** BUG-010  

| Step | Work |
|------|------|
| 1 | On Complete (sales/purchase GST types): if company has GSTIN and party has empty state **and** no GSTIN state code → `BusinessRuleError`. |
| 2 | FE: warning banner on party select; disable Complete/Save-complete CTA with helper text “Add customer state or GSTIN”. |
| 3 | Walk-in: require company default “assume local state” setting **or** force state on walk-in master. |

**Company setting (Phase 1 light):** `assume_local_state_for_blank_party: bool` default **false** for new companies; demo seed may set true with warning.

**Acceptance:** Cannot complete GST invoice with blank party state unless explicit company opt-in.

#### B3. Purchase outstanding status parity
**Bugs:** BUG-017  

| Step | Work |
|------|------|
| 1 | Align `purchase_invoice_outstanding` / supplier aggregations with sales open statuses (include `RETURNED` if that status exists on purchases; else document and add status). |
| 2 | Tests in `test_ledger.py`. |

#### B4. Label advances on ledger / receipts
**Bugs:** BUG-018  

| Step | Work |
|------|------|
| 1 | Ledger API: flag receipt entries with `is_advance` when unallocated amount &gt; 0. |
| 2 | UI: chip “Advance” on Customer Ledger & Receipts. |

#### B5. Invoice number UX
**Bugs:** BUG-020  

| Step | Work |
|------|------|
| 1 | Make prefix/number read-only on create UI; show “Next number: INV-00007 (assigned on Complete)”. |
| 2 | Keep `number-series` settings under OWNER Settings only. |

**Estimate:** B1 = 4–5d · B2 = 2d · B3–B5 = 2d  

---

### EPIC C — API envelope correctness (W2)

**Bugs:** BUG-002  

#### C1. Renderer + call-site fix

| Step | Work |
|------|------|
| 1 | Update `EnvelopeJSONRenderer`: if `response.status_code >= 400` and body is not already `{success: false}`, wrap as error envelope. |
| 2 | Audit views that return `Response(..., status=4xx)` without exceptions (`accounts/views.py` OTP, others via ripgrep). Prefer `raise ValidationError`. |
| 3 | Tests: OTP missing phone → `success: false`; weak register already OK; add renderer unit tests. |
| 4 | FE client: treat `success === false` **or** HTTP ≥400 as error (defense in depth). |

**Files:** `backend/core/renderers.py`, `backend/core/exceptions.py`, `accounts/views.py`, `web/src/api/client.ts`, tests  

**Acceptance:** No 4xx response with `success: true` in full API smoke.  

**Estimate:** 1–2d  

---

### EPIC D — Production security & notifications (W3)

#### D1. Fail-fast production settings
**Bugs:** BUG-004  

| Step | Work |
|------|------|
| 1 | If `DJANGO_ENV=production` (or `DEBUG=0`): raise ImproperlyConfigured when secret is default / short; force `OTP_DEBUG_ECHO=False`. |
| 2 | Split `.env.example` vs `.env.production.example`. |
| 3 | `docker-compose.prod.yml` (or compose profile `prod`) with DEBUG=0, no echo. |
| 4 | CI check: grep rejects default secret in prod compose. |

#### D2. File upload hardening
**Bugs:** BUG-005  

| Step | Work |
|------|------|
| 1 | `FileService.store_upload`: max size (e.g. 10MB images/PDF, 5MB CSV), allowlist by `kind` (logo/pdf/csv/bill/attachment). |
| 2 | Sniff content (filetype/imghdr/pdf magic); reject mismatch. |
| 3 | Store with sanitized filename; never execute. |
| 4 | Ensure download requires auth + company scope (already likely — verify). |
| 5 | Tests: exe upload rejected; oversized rejected; bill types still work. |

#### D3. Auth rate limiting
**Bugs:** BUG-021  

| Step | Work |
|------|------|
| 1 | DRF throttles: `anon` + scoped `login`, `otp`, `register` (e.g. 5/min login, 3/min OTP). |
| 2 | Optional django-ratelimit / Redis cache backend (Redis already in stack). |
| 3 | Tests with APIClient burst. |

#### D4. OTP & email for pilot
**Bugs:** BUG-007, BUG-008  

| Step | Work |
|------|------|
| 1 | Abstract `SmsProvider` (Twilio/MSG91 stub interface); wire one provider behind env; if unset in prod → disable OTP login with clear error. |
| 2 | Never return `debug_code` unless `OTP_DEBUG_ECHO` explicitly true **and** DEBUG. |
| 3 | Require `EMAIL_HOST` in prod profile; document SendGrid/SES setup. |
| 4 | UI copy on Share: “Opens WhatsApp with link (Business API later)”. |
| 5 | Verify invoice email path uses Notification Service + attachment when SMTP set. |

#### D5. TLS & security headers
**Bugs:** BUG-022  

| Step | Work |
|------|------|
| 1 | Nginx: add `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, baseline `Content-Security-Policy` for SPA. |
| 2 | Document TLS via reverse proxy / Lightsail cert (compose comment + README). Staging may use Caddy/Traefik. |
| 3 | Django `SECURE_*` settings when `USE_TLS=1`. |

#### D6. OpenAPI docs
**Bugs:** BUG-019  

| Step | Work |
|------|------|
| 1 | Fix Spectacular 500 (debug root cause). |
| 2 | In production: docs/schema **OWNER-only** or disabled via `ENABLE_API_DOCS=0`. |

#### D7. XSS mitigation (partial BUG-006)
| Step | Work |
|------|------|
| 1 | Confirm no `dangerouslySetInnerHTML` without sanitization. |
| 2 | CSP as in D5. |
| 3 | Shorten refresh token lifetime for pilot optional (7d → 2d) via env. |

**Estimate:** D1–D3 = 3d · D4 = 2–3d · D5–D7 = 2d  

---

### EPIC E — Permissions & access UX (W4)

**Bugs:** BUG-009 (partial), BUG-012  

Phase 1 does **not** add Accountant/Viewer enums. It adds **capability flags** and enforces them FE+BE.

#### E1. New capability flags on `CompanyUser`

| Flag | Default OWNER | Default STAFF | Meaning |
|------|---------------|---------------|---------|
| `can_cancel_documents` | true | **false** | Complete reverse / cancel |
| `can_view_financial_reports` | true | true (pilot) or false — **PM pick**: recommend **true** for staff in tiny shops, **false** when inviting cashiers | Ledgers + reports + dashboard receivables |
| `can_export` | true | false | CSV exports |
| (existing) `can_manage_inventory` | true | flag | |
| (existing) `can_import` | true | flag | |

| Step | Work |
|------|------|
| 1 | Migration + admin/settings Users UI checkboxes. |
| 2 | Backend: permission classes on cancel actions, report/export views, audit already Owner. |
| 3 | FE: hide/disable actions; `RoleRoute` for reports if flag false. |

#### E2. Access denied UX
| Step | Work |
|------|------|
| 1 | Replace silent `<Navigate to="/" />` with `/forbidden` page: title, reason, link home. |
| 2 | Toast if API returns 403. |

**Acceptance:** Staff without cancel cannot cancel via UI or API; denied route shows explanation.  

**Estimate:** 3d  

---

### EPIC F — Performance & reporting polish (W4)

**Bugs:** BUG-013 + P1 aging  

#### F1. Dashboard receivables SQL aggregation
| Step | Work |
|------|------|
| 1 | Replace Python loop with SQL: sum completed/returned sales − returns − allocations (company-scoped). |
| 2 | Same pattern for payables. |
| 3 | Benchmark with seed of 2k customers (management command). |

#### F2. Receivables aging (light)
| Step | Work |
|------|------|
| 1 | Report endpoint or dashboard widget: buckets 0–30 / 31–60 / 61–90 / 90+ using `due_date` or `invoice_date + terms`. |
| 2 | Customer ledger filter “Overdue”. |

**Estimate:** F1 = 1–2d · F2 = 2d  

---

### EPIC G — UX cleanup (W4, small)

**Bugs:** BUG-024–027  

| ID | Work |
|----|------|
| G1 | Discount labels (covered in B1) |
| G2 | Audit icon buttons for `aria-label` + Tooltip |
| G3 | Customer Autocomplete placeholder “Type to search customers” |
| G4 | Terms default from `Company.default_terms` (settings), not hard-coded Bengaluru |

**Estimate:** 1d  

---

### EPIC H — CA pack, E2E, pilot ops (W5) — release gate

#### H1. CA validation pack
| Step | Work |
|------|------|
| 1 | Generate PDF samples: intra, inter, NON_GST, discount BEFORE/AFTER, round-off on/off, multi-rate. |
| 2 | Spreadsheet of inputs → expected CGST/SGST/IGST/grand. |
| 3 | CA signs checklist; store under `docs/ca/` (PDF + sign-off note). |

#### H2. Playwright golden path
Extend `web/e2e/`:

1. Login  
2. Create purchase → complete → stock up  
3. Create sales invoice odd-paise product → assert UI totals == API  
4. Partial receipt + allocation  
5. Sales return  
6. Cancel draft  
7. Staff user without cancel → 403  
8. Ledger shows advance chip if applicable  

Run in CI (existing workflow).

#### H3. Staging UAT script
Document in `docs/pilot/UAT_CHECKLIST.md` mirroring MVP §21.

#### H4. Runbooks
- PDF worker down  
- OTP/SMS failure  
- SMTP failure  
- Discount mode explanation for support  

**Estimate:** H1 = 2d + CA calendar · H2 = 3d · H3–H4 = 1d  

---

## 5. Dependency graph

```text
A1/A2 ──┬──► A4 (optional)
A3 ─────┤
        ▼
B2 (needs A3 unknown-state)
B1 ──────────► H1 CA pack
C1 ── parallel
D1 ──► D4 OTP/email prod
D2/D3/D5 parallel after D1
E1/E2 after C1 (403 handling)
F1/F2 parallel W4
H2 after A1+B1+E1
H1 after A1+B1+PDF labels
```

---

## 6. Test plan (Phase 1 DoD)

| Layer | Requirement |
|-------|-------------|
| Unit BE | New/updated tax, discount modes, envelope, upload reject, throttle, ledger parity, dashboard SQL |
| Unit FE | tax parity golden file, money HALF_UP, permissions flags, forbidden page |
| API | Contract tests: no `success:true` on 4xx; preview totals; complete blocked without state |
| E2E | Golden path H2 in CI |
| Manual | CA matrix; mobile smoke on New Invoice; staff permission matrix |
| Perf | Dashboard &lt; 200ms p95 with 2k customers on staging |

Regression: full `pytest` + `vitest --run` + `npm run build` must stay green.

---

## 7. Rollout plan

| Stage | Action |
|-------|--------|
| 1 | Merge W1–W2 to `main`; deploy staging |
| 2 | W3 prod-profile dry-run on staging |
| 3 | CA sign-off |
| 4 | W4–W5; UAT with 2 internal + 1 friendly merchant |
| 5 | Pilot cohort 5 → 20; feature flag `discount_before_tax` if needed |
| 6 | Monitor: PDF fail rate, 4xx envelope, login throttle hits |

**Feature flags (optional):** `PREVIEW_TOTALS_API`, `DISCOUNT_BEFORE_TAX`, `BLOCK_BLANK_PARTY_STATE`.

---

## 8. Effort summary

| Epic | Days (eng) |
|------|----------:|
| A Tax parity | 5–6 |
| B Discount & GST guards | 8–9 |
| C Envelope | 1–2 |
| D Security & notifications | 7–8 |
| E Permissions & forbidden UX | 3 |
| F Perf & aging | 3–4 |
| G UX polish | 1 |
| H CA / E2E / ops | 6 + CA lag |
| **Total** | **~34–39 eng-days** ≈ **4–5 weeks** with 1 FTE |

---

## 9. Phase 1 Definition of Done

A Phase 1 release is **Done** when:

1. All P0 items in §1 Wave W1–W3 and H1 are complete.  
2. Golden tax file: FE == BE for all cases (including ₹10.05 @ 18%).  
3. Zero responses with HTTP ≥400 and `success: true`.  
4. Prod compose refuses insecure defaults; OTP never echoed in staging/prod.  
5. Uploads reject non-allowlisted types; auth endpoints throttled.  
6. GST Complete blocked on unknown place-of-supply (unless explicit company opt-in).  
7. Discount UI/PDF states BEFORE_TAX vs AFTER_TAX clearly.  
8. Cancel/export gated by flags; forbidden page exists.  
9. Dashboard outstanding not O(n) Python loop.  
10. Playwright golden path green in CI.  
11. **CA written sign-off** on invoice PDF + tax matrix.  
12. Support runbook published.  
13. `PRODUCTION_READINESS.md` score re-evaluated (target ≥ **7.5/10** for pilot).

---

## 10. Tracking board (suggested tickets)

1. `P1-A1` FE residual CGST/SGST + golden tests  
2. `P1-A2` roundMoney HALF_UP parity  
3. `P1-A3` isIntraState shared rules  
4. `P1-A4` preview-totals API + FE wire-up  
5. `P1-B1` discount mode BE+FE+PDF  
6. `P1-B2` block complete unknown POS  
7. `P1-B3` purchase outstanding parity  
8. `P1-B4` advance labeling  
9. `P1-B5` read-only document numbers on create  
10. `P1-C1` error envelope fix  
11. `P1-D1` prod settings fail-fast  
12. `P1-D2` upload allowlist  
13. `P1-D3` auth throttles  
14. `P1-D4` SMS provider + SMTP pilot  
15. `P1-D5` nginx headers + TLS docs  
16. `P1-D6` docs auth/disable  
17. `P1-E1` capability flags  
18. `P1-E2` forbidden page  
19. `P1-F1` dashboard SQL  
20. `P1-F2` aging buckets  
21. `P1-G` UX polish batch  
22. `P1-H1` CA pack  
23. `P1-H2` E2E golden path  
24. `P1-H3` UAT + runbooks  

---

## 11. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| CA rejects BEFORE_TAX allocation method | Agree formula in week 1 workshop before coding B1 |
| SMS provider delay | Pilot can launch email+password only; disable OTP in prod until provider live |
| Preview API latency on slow networks | Debounce + local calc fallback with banner |
| Scope creep into CN/GSTR | PM gate; link requesters to Phase 2 backlog |
| Float edge cases remain | Golden file + random parity harness |

---

## 12. Immediate next actions (this week)

1. PM confirms D1–D7 decisions (especially discount default and staff report visibility).  
2. Book CA for week 3 sample review.  
3. Open tickets `P1-A1` … `P1-A3` and start implementation.  
4. Create `shared/tax_parity_cases.json` with the known failing ₹10.05 case first (RED → GREEN).  

---

*This plan implements audit Phase 1 (pilot hardening). Product “Phase 2” features in `MVP_IMPLEMENTATION_PLAN.md` §19 remain deferred.*

# Bizboard — Deep Code Review of Onboarding (`ONBOARDING_CODE_REVIEW.md`)

**Audit Date:** 2026-10-21  
**Scope:** Frontend correctness, Backend correctness, Database & Data Integrity, and Architecture/Maintainability across all 25 onboarding screens and backend services.

---

## 1. Executive Summary of Code Review Findings

| Finding ID | Severity | Category | Title | Affected Screen / Route |
|---|---|---|---|---|
| `ONB-CR-001` | **P1 (High)** | Functional / State Machine | Setup Wizard Step 5 ("Create First Bill") creates a `DRAFT` invoice without completing it or dismissing onboarding, trapping the Owner in an infinite redirect loop when clicking "Go to Dashboard" | `SCR-14` (`/setup?step=first_bill` -> `/`) |
| `ONB-CR-002` | **P1 (High)** | Validation / API Contract | Composition GSTIN validation mismatch: Setup Wizard UI marks GSTIN as optional for `COMPOSITION`, but `CompanySerializer.validate` rejects blank GSTIN with HTTP 400 | `SCR-09` (`/setup?step=tax`) |
| `ONB-CR-003` | **P1 (High)** | Functional / UI | Forced 2FA enrolment on `/login` fails to render QR code (`setup.qrPng`) and leaves the user on a blank dead-end screen after clicking "I have saved them" | `SCR-05` (`/login` enrolment state) |
| `ONB-CR-004` | **P1 (High)** | Functional / Cache Coherency | `SetupWizardPage` does not invalidate `['company']` query after Step 1 (`saveTax`), causing Step 5 (`createFirstBill`) to issue a `GST` tax invoice for `UNREGISTERED`/`COMPOSITION` businesses | `SCR-09`, `SCR-12`, `SCR-14` (`/setup`) |
| `ONB-CR-005` | **P1 (High)** | Functional / Business Logic | Sample products and zero-opening-stock catalog items created in Step 4 cannot be completed in Step 5's draft invoice because `Company.negative_stock_policy` defaults to `BLOCK` | `SCR-12`, `SCR-14` (`/setup?step=catalog`, `/sales/history/{id}/edit`) |
| `ONB-CR-006` | **P2 (Medium)** | Functional / Validation | Registration with a new email + valid OTP but an already-registered mobile number silently returns HTTP 200 OK without creating the account, causing immediate 401 on login | `SCR-01` (`/register` -> `/login?registered=1`) |
| `ONB-CR-007` | **P2 (Medium)** | Validation / Data Integrity | Setup Wizard Step 1 (`tax`) and `CompanySerializer` do not check or sync `company.state` against the 2-digit state prefix of a newly entered GSTIN | `SCR-09` (`/setup?step=tax`), `SCR-20` (`/settings/gst`) |
| `ONB-CR-008` | **P2 (Medium)** | Functional / Payments | Setup Wizard Step 3 (`payments`) collects `bankAccount` and `upiId` but omits `bankName` and `bankIfsc`, syncing an incomplete `BankAccount` record (`name="Company bank"`, `ifsc=""`) | `SCR-11` (`/setup?step=payments`) |
| `ONB-CR-009` | **P2 (Medium)** | Functional / State Machine | Setup Wizard Step 5 (`pack` step) displays raw pack keys (`retail`/`trade`), lacks the 4-group preview breakdown, and does not reset `proposedPack` when answers change | `SCR-13` (`/setup?step=pack`) |
| `ONB-CR-010` | **P2 (Medium)** | Authorization / UI | `OnboardingChecklist` renders owner-only `Dismiss guide` action and owner-only settings links for `MANAGER`, `ACCOUNTANT`, and `AUDITOR` users, resulting in HTTP 403 errors | `SCR-15` (`/` — `DashboardPage` / `OnboardingChecklist`) |
| `ONB-CR-011` | **P2 (Medium)** | Architecture / Feature Flags | Frontend `isSetupWizardEnabled()` only checks build-time `import.meta.env.VITE_ENABLE_SETUP_WIZARD`, ignoring the backend runtime `/api/v1/feature-flags/` `ENABLE_SETUP_WIZARD` flag | `SCR-09`–`SCR-15` (`web/src/config/features.ts`) |
| `ONB-CR-012` | **P3 (Low)** | Functional / Settings Health | `settings_health(company)` always reports `gstin: "todo"` for `UNREGISTERED` companies even after they confirm their unregistered tax profile | `SCR-18` (`/settings`) |

---

## 2. Detailed Confirmed Defects (Mandatory 17-Field Format)

### `ONB-CR-001` — Infinite Redirect Loop at End of Setup Wizard After Creating First Bill Draft
- **Finding ID:** `ONB-CR-001`
- **Title:** Setup Wizard Step 5 ("Create First Bill") creates a `DRAFT` invoice without completing it or dismissing onboarding, trapping the Owner in an infinite redirect loop when clicking "Go to Dashboard"
- **Severity:** **P1 (High)**
- **Category:** Functional / State Machine
- **Affected screen / route:** `SCR-14` (`/setup?step=first_bill` -> `/`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 295–327, 495–520)
  - `backend/accounts/onboarding.py` (`derive_onboarding`, lines 18–57; `should_force_setup`, lines 60–68)
  - `web/src/onboarding/shouldForceSetup.ts` (lines 16–22)
  - `web/src/pages/HomePage.tsx` (line 33) & `web/src/pages/DashboardPage.tsx` (line 97)
- **Preconditions:**
  - `VITE_ENABLE_SETUP_WIZARD=true`
  - Newly registered `OWNER` has completed Steps 1–4 (`tax`, `shop`, `payments`, `catalog`) and is on Step 5 (`first_bill`) with zero completed invoices and `onboarding_dismissed_at = None`.
- **Reproduction steps:**
  1. On `/setup?step=first_bill`, click **Create first bill** (`createFirstBill`).
  2. Observe the success alert: *"Your First Invoice Draft is Ready"* with two buttons: **Review & Finalize Bill** (`/sales/history/{id}/edit`) and **Go to Dashboard** (`/`).
  3. Click **Go to Dashboard** (`/`).
- **Expected behavior:**
  - Clicking **Go to Dashboard** navigates the Owner to the main dashboard (`/`) without bouncing them back to `/setup`.
- **Actual behavior:**
  - `HomePage` and `DashboardPage` evaluate `shouldForceSetup(user, company)`. Because `createSalesInvoice` created a `DRAFT` invoice (not `COMPLETED`) and `dismissOnboarding` was not set, `derive_onboarding(company)` returns `status: "IN_PROGRESS", step: "first_bill"`. `shouldForceSetup` returns `true` and immediately executes `<Navigate to="/setup" replace />`, sending the user right back to `/setup?step=first_bill` where `completedInvoiceId` state is reset to `null`!
- **Evidence / test status:**
  - Verified in source code: `SetupWizardPage.tsx:312-322` calls `createSalesInvoice` (changed in PR `CW-PR-3` so it no longer calls `completeSalesInvoice`), while `backend/accounts/onboarding.py:18-20` checks `SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.COMPLETED).exists()`.
- **Root cause:**
  - `CW-PR-3` changed Step 5 of `SetupWizardPage.tsx` from creating + completing an invoice to only creating a `DRAFT` invoice, but neither updated `derive_onboarding` nor called `updateCompany({ dismissOnboarding: true })` when the user clicks "Go to Dashboard" (or upon draft creation).
- **Impact:**
  - Any Owner who clicks "Go to Dashboard" at the end of the Setup Wizard is trapped in a redirect loop back to `/setup?step=first_bill` and thinks the button is broken, potentially creating multiple duplicate `DRAFT` invoices each time they click "Create first bill" again.
- **Recommended correction:**
  - Either mark `onboarding_dismissed_at` (or `onboarding_completed_at`) when the user clicks "Go to Dashboard" from the draft-created card, or have `createFirstBill` mark onboarding completed/dismissed once the first draft bill is created so `shouldForceSetup` returns `false`.
- **Regression tests required:**
  - Frontend integration test in `SetupWizardPage.test.tsx` verifying that clicking "Go to Dashboard" after creating the first bill draft transitions the company out of forced-setup mode.
- **Acceptance criteria:**
  - Clicking "Go to Dashboard" after creating the first bill in `/setup` lands on `/` (`DashboardPage`) without redirecting back to `/setup`.
- **Verification status:** Confirmed in code review; awaiting Phase 9 fix implementation.

---

### `ONB-CR-002` — Composition GSTIN Validation Mismatch Between Setup Wizard UI and Backend Serializer
- **Finding ID:** `ONB-CR-002`
- **Title:** Composition GSTIN validation mismatch: Setup Wizard UI marks GSTIN as optional for `COMPOSITION`, but `CompanySerializer.validate` rejects blank GSTIN with HTTP 400
- **Severity:** **P1 (High)**
- **Category:** Validation / API Contract
- **Affected screen / route:** `SCR-09` (`/setup?step=tax`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 184–203, 405–413)
  - `web/src/i18n/en.ts` (line 2222: `gstinOptional: 'Optional for composition businesses'`)
  - `backend/accounts/serializers.py` (`CompanySerializer.validate`, lines 356–370)
- **Preconditions:**
  - New company (`gstin=""`) opens `/setup?step=tax`.
- **Reproduction steps:**
  1. Select **Composition scheme** (`COMPOSITION`) in the `GST registration type` dropdown.
  2. Notice the `GSTIN` field is NOT marked required and displays helper text: *"Optional for composition businesses"*.
  3. Leave `GSTIN` blank and click **Save & continue**.
- **Expected behavior:**
  - Frontend validation rules and helper copy must match backend validation rules (either both require a 15-character GSTIN for Composition dealers—since Indian GST Composition dealers under Section 10 of the CGST Act hold a 15-char GSTIN—or backend allows blank GSTIN when `COMPOSITION` is selected).
- **Actual behavior:**
  - Frontend `saveTax()` passes validation (`if (registrationType === 'REGULAR' && !gstin.trim())`) and sends `PATCH /api/v1/company/ {registrationType: "COMPOSITION", gstin: "", confirmTaxProfile: true}`.
  - Backend `CompanySerializer.validate()` (lines 364–370) checks:
    `elif registration_type in (Company.RegistrationType.REGULAR, Company.RegistrationType.COMPOSITION) ... if len(gstin) != 15: raise serializers.ValidationError({"gstin": "A valid 15-character GSTIN is required for REGULAR or COMPOSITION registration."})`
  - The request fails with HTTP 400!
- **Evidence / test status:**
  - Confirmed by comparing `SetupWizardPage.tsx:186,408,412` against `backend/accounts/serializers.py:364-370`. Note also that `backend/tests/test_onboarding.py:109` (`test_composition_cannot_complete_gst_tax_invoice`) sets `registration_type = COMPOSITION, gstin = ""` directly via ORM, bypassing `CompanySerializer`!
- **Root cause:**
  - Design drift between `docs/onboarding/NEW_USER_ONBOARDING_PLAN.md` (which originally proposed optional GSTIN for Composition in the wizard) and `backend/accounts/serializers.py` (which enforces a 15-character GSTIN for both `REGULAR` and `COMPOSITION`).
- **Impact:**
  - Composition scheme businesses following the UI helper text ("Optional for composition businesses") hit an unexpected server validation error on Step 1 of onboarding.
- **Recommended correction:**
  - Align `CompanySerializer.validate()` and `SetupWizardPage.tsx`: either allow blank `gstin` when `registration_type == COMPOSITION` (validating format only if non-empty, matching `NEW_USER_ONBOARDING_PLAN.md` and `test_onboarding.py:109`), or require GSTIN in both UI and backend and update the helper text. Allowing optional GSTIN for `COMPOSITION` (validated when provided) preserves backward compatibility with `NEW_USER_ONBOARDING_PLAN.md` and `test_onboarding.py:109`.
- **Regression tests required:**
  - Backend test in `test_onboarding.py` PATCHing `/api/v1/company/` with `{"registration_type": "COMPOSITION", "gstin": "", "confirm_tax_profile": True}` via API client.
- **Acceptance criteria:**
  - `COMPOSITION` selection in Step 1 of `/setup` behaves identically in client validation and `PATCH /api/v1/company/`.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-003` — Forced 2FA Enrolment on `/login` Omits QR Code and Dead-Ends After Recovery Codes
- **Finding ID:** `ONB-CR-003`
- **Title:** Forced 2FA enrolment on `/login` fails to render QR code (`setup.qrPng`) and leaves the user on a blank dead-end screen after clicking "I have saved them"
- **Severity:** **P1 (High)**
- **Category:** Functional / UI
- **Affected screen / route:** `SCR-05` (`/login` forced MFA enrolment state)
- **Affected file / component / API / model:**
  - `web/src/pages/LoginPage.tsx` (lines 80–84, 150–179, 293–345)
  - Compare with `web/src/pages/settings/TwoStepVerificationPanel.tsx` (lines 118–135)
- **Preconditions:**
  - Backend has `MFA_ENFORCE_FOR_MONEY_ROLES=True` (enabled by default in `BIZBOARD_PROFILE=pilot`).
  - An `OWNER` or `ACCOUNTANT` without 2FA signs in on `/login`.
- **Reproduction steps:**
  1. Enter valid email and password on `/login` and click **Sign in**.
  2. `POST /api/v1/auth/login/` returns `{"mfa_enrollment_required": true, "enrol_token": "..."}`.
  3. `LoginPage` calls `startMfaSetup(enrolToken)` which returns `{secret, otpauthUri, qrPng}`.
  4. Observe the enrolment form on `/login`: the prompt says *"Scan this QR code with an authenticator app... If you cannot scan it, type the setup key instead"*, **but no QR code image (`qrPng`) is rendered**—only the text setup key (`enrolSecret`)!
  5. Enter the 6-digit TOTP code and click **Confirm and turn on**.
  6. The 10 recovery codes are displayed with the button **I have saved them** (`recoveryDone`).
  7. Click **I have saved them**.
- **Expected behavior:**
  - Step 4 should render `<Box component="img" src={enrolQrPng} ... />` alongside the manual setup key.
  - Step 7 clicking **I have saved them** should clear `enrolDone` (or keep the info banner while re-displaying the password sign-in form) so the user can sign in with their password + new TOTP code.
- **Actual behavior:**
  - In Step 4, `startEnrolment` (`LoginPage.tsx:150-162`) only saves `setEnrolSecret(setup.secret)` and discards `setup.qrPng`!
  - In Step 7, clicking **I have saved them** (`LoginPage.tsx:338`) only calls `setRecoveryCodes(null)`. Because `enrolDone` is still `true` and line 345 renders `{mfaToken || enrolToken || enrolDone ? null : (<password & otp forms>)}`, **all forms disappear**—leaving only a static info alert (*"Two-step verification is on. Sign in again with your password and a code from the app."*) with **no sign-in form or button on the page**! The user is completely stuck unless they reload the browser.
- **Evidence / test status:**
  - Confirmed in `web/src/pages/LoginPage.tsx` lines 153–156 and 322–345.
- **Root cause:**
  - `enrolQr` state was omitted from `LoginPage.tsx`, and the `recoveryDone` button handler (`onClick={() => setRecoveryCodes(null)}`) forgot to reset `setEnrolDone(false)` (or allow the login form to render when `enrolDone && !recoveryCodes`).
- **Impact:**
  - In `pilot` mode (`MFA_ENFORCE_FOR_MONEY_ROLES=True`), every newly registered `OWNER` is forced through this screen on their very first login, cannot scan a QR code, and hits a dead-end screen with no login form after saving their recovery codes.
- **Recommended correction:**
  - Store `enrolQrPng` from `startMfaSetup` and render the QR code `<Box component="img" src={enrolQrPng} alt="" sx={{ width: 180, height: 180, ... }} />` in `LoginPage.tsx`.
  - When `enrolDone` is true and `recoveryCodes` is dismissed (`setRecoveryCodes(null)`), render the `enrolDone` info alert **above** the restored sign-in form (by changing line 345 from `mfaToken || enrolToken || enrolDone ? null : ...` to `mfaToken || enrolToken || recoveryCodes ? null : ...`).
- **Regression tests required:**
  - Unit test in `LoginPage.mfa.test.tsx` covering the full enrolment lifecycle (`startMfaSetup` -> QR rendered -> `confirmMfa` -> recovery codes shown -> click "I have saved them" -> password sign-in form is visible again).
- **Acceptance criteria:**
  - QR code image is displayed during login-time MFA enrolment, and clicking "I have saved them" reveals the sign-in form with the confirmation banner.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-004` — Stale `company` Query Cache in `SetupWizardPage` Causes Wrong Invoice Type and Missing HSN Gate
- **Finding ID:** `ONB-CR-004`
- **Title:** `SetupWizardPage` does not invalidate `['company']` query after Step 1 (`saveTax`), causing Step 4 and Step 5 to use stale `company.registrationType`
- **Severity:** **P1 (High)**
- **Category:** Functional / Cache Coherency
- **Affected screen / route:** `SCR-09`, `SCR-12`, `SCR-14` (`/setup`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 184–203, 313, 498)
- **Preconditions:**
  - New company created at `/register` without GSTIN (defaults in DB to `registration_type = 'REGULAR'`, `gstin = ''`).
  - Owner enters `/setup?step=tax` and changes `registrationType` from `REGULAR` to `UNREGISTERED` (or `COMPOSITION`).
- **Reproduction steps:**
  1. On Step 1 (`tax`), change `GST registration type` to **Unregistered** and click **Save & continue**.
  2. Proceed through Step 2 (`shop`), Step 3 (`payments`), and Step 4 (`catalog`).
  3. Reach Step 5 (`first_bill`).
  4. Observe the description text and click **Create first bill**.
- **Expected behavior:**
  - Step 5 should recognize that `company.registrationType` is now `'UNREGISTERED'`, show `t('setup.firstBill.bos')` (*"This will create a non-GST Bill of Supply..."*), and pass `invoiceType: 'NON_GST'` and `gstRate: 0` to `createSalesInvoice`.
- **Actual behavior:**
  - Neither `saveTax` (line 191), `saveShop` (line 214), nor `savePayments` (line 232) calls `qc.invalidateQueries({ queryKey: ['company'] })`!
  - Consequently, `companyQuery.data` (`company`) in `SetupWizardPage.tsx` still holds the initial cached value `company.registrationType === 'REGULAR'`!
  - On Step 5 (`first_bill`), line 498 checks `company?.registrationType === 'REGULAR'` (still `true`!) and line 313 sends `invoiceType: 'GST'` with `gstRate: 18` for an `UNREGISTERED` company!
  - When the user opens the draft invoice to complete it, `assert_may_issue_gst_tax_invoice` rejects completion with `BusinessRuleError: Unregistered companies cannot issue GST/TAX invoices with CGST/SGST/IGST`!
- **Evidence / test status:**
  - Confirmed in `web/src/pages/setup/SetupWizardPage.tsx` lines 191–198, 313, 317, 498.
- **Root cause:**
  - `saveTax`, `saveShop`, and `savePayments` mutate the company via `updateCompany(...)` without updating or invalidating the `['company']` React Query cache, and lines 313/317/498 read `company?.registrationType` instead of the local `registrationType` state (or refetched `company`).
- **Impact:**
  - Every `UNREGISTERED` or `COMPOSITION` business that changes its registration type in Step 1 gets a `GST` tax invoice draft created in Step 5 that is legally and functionally blocked from completion!
- **Recommended correction:**
  - Call `await qc.invalidateQueries({ queryKey: ['company'] })` in `saveTax`, `saveShop`, and `savePayments`, and use `registrationType === 'REGULAR'` in `createFirstBill` and Step 5 rendering.
- **Regression tests required:**
  - Test in `SetupWizardPage.test.tsx` where a company starts as `REGULAR`, selects `UNREGISTERED` in Step 1, advances to `first_bill`, and verifies `createSalesInvoice` is called with `invoiceType: 'NON_GST'` and `gstRate: 0`.
- **Acceptance criteria:**
  - Changing `registrationType` in Step 1 immediately updates `company` query state and creates a `NON_GST` Bill of Supply in Step 5 for `UNREGISTERED`/`COMPOSITION` businesses.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-005` — Sample Products & Zero-Stock Catalog Items Cannot Be Completed on First Bill Due to `negative_stock_policy='BLOCK'`
- **Finding ID:** `ONB-CR-005`
- **Title:** Sample products and zero-opening-stock catalog items created in Step 4 cannot be completed in Step 5's draft invoice because `Company.negative_stock_policy` defaults to `BLOCK`
- **Severity:** **P1 (High)**
- **Category:** Functional / Business Logic
- **Affected screen / route:** `SCR-12` (`/setup?step=catalog`), `SCR-14` (`/setup?step=first_bill` -> `/sales/history/{id}/edit`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (`addSamples`, lines 267–293; `addFirstProduct`, lines 242–265)
  - `backend/accounts/models.py` (`Company.negative_stock_policy`, line 162 — defaults to `BLOCK`)
- **Preconditions:**
  - Newly registered company has `negative_stock_policy = "BLOCK"` (the default).
- **Reproduction steps:**
  1. In Step 4 (`catalog`) of `/setup`, click **Add sample products** (and confirm the dialog), OR add a product with `Opening quantity (optional)` left blank.
  2. In Step 5 (`first_bill`), click **Create first bill** (which uses `products[0]`, e.g., `SAMPLE-ITEM` with 0 stock).
  3. Click **Review & Finalize Bill** (`/sales/history/{id}/edit`) and click **Complete**.
- **Expected behavior:**
  - If the user clicked "Add sample products" (which explicitly states: *"They are real items you can bill against"*), completing the first bill created from `SAMPLE-ITEM` should succeed without a negative stock error.
- **Actual behavior:**
  - `addSamples()` creates `SAMPLE-ITEM` (`trackInventory` defaults to `true` on `Product`) without calling `createOpeningStock`!
  - When the user tries to complete the draft invoice created in Step 5, `SalesService.complete_invoice` checks stock against `Company.negative_stock_policy == 'BLOCK'` and fails with `NegativeStockError` (`Insufficient stock for Sample Item`)!
- **Evidence / test status:**
  - Confirmed in `SetupWizardPage.tsx:273-277` (creates `SAMPLE-ITEM` with no opening stock) and `backend/tests/personas/test_pj_ftue_onboarding_and_help.py:43,175` (where the test author had to manually set `negative_stock_policy="ALLOW"` AND post `InventoryService.post_movement(... OPENING_STOCK, quantity=10)` for the first bill to complete!).
- **Root cause:**
  - `addSamples()` does not seed opening stock (or `trackInventory: false`) for `SAMPLE-ITEM`.
- **Impact:**
  - Non-technical users who click "Add sample products" to try out billing immediately hit a stock-block error on their very first bill.
- **Recommended correction:**
  - In `addSamples()`, either seed opening stock (e.g. `await createOpeningStock({ product: createdItem.id, quantity: 100, unitCost: 50 })`) for `SAMPLE-ITEM` or set `trackInventory: false` on sample items.
- **Regression tests required:**
  - Update `SetupWizardPage.test.tsx` to verify that `addSamples` provisions billable stock (or non-tracked sample items).
- **Acceptance criteria:**
  - A draft bill created from sample products in Step 5 can be finalized/completed on a default `negative_stock_policy='BLOCK'` company without stock errors.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-006` — Silent Registration Drop When Mobile Number Is Already Taken by Another User
- **Finding ID:** `ONB-CR-006`
- **Title:** Registration with a new email + valid OTP but an already-registered mobile number silently returns HTTP 200 OK without creating the account, causing immediate 401 on login
- **Severity:** **P2 (Medium)**
- **Category:** Functional / Validation
- **Affected screen / route:** `SCR-01` (`/register` -> `/login?registered=1`)
- **Affected file / component / API / model:**
  - `backend/accounts/views.py` (`RegisterView.create`, lines 435–465)
  - `web/src/pages/RegisterPage.tsx` (lines 169–188)
- **Preconditions:**
  - User A already exists in the database with phone `+919876543210` and email `usera@example.com`.
  - New User B registers with a brand-new email `userb@example.com`, verifies the 6-digit email OTP sent to `userb@example.com`, and enters `+919876543210` in the optional Mobile Number field.
- **Reproduction steps:**
  1. On `/register`, enter Company Name, `userb@example.com`, click **Send code**, and enter the valid 6-digit OTP received at `userb@example.com`.
  2. Enter `+91 98765 43210` (already used by User A) and a valid password.
  3. Click **Create account**.
  4. User B is redirected to `/login?registered=1` with the banner: *"If this email can be registered, we prepared an account..."*
  5. User B enters `userb@example.com` and their password on `/login` and clicks **Sign in**.
- **Expected behavior:**
  - Because User B has **already proven ownership of a brand-new email via the 6-digit OTP** (`otp_code`), or if `phone` is conflicted, User B should either receive a field validation error on `phone` (after OTP verification) or have the account created without the duplicate optional phone, rather than silently dropping the entire registration!
- **Actual behavior:**
  - `RegisterView.create` (`backend/accounts/views.py:451-453`) checks `if canonical_phone and phone_taken(phone=canonical_phone): return Response(_register_payload(), status=status.HTTP_200_OK)` **before** creating the user and without returning any error!
  - User B's account is **never created**, yet they are redirected to `/login?registered=1` and get HTTP 401 `Invalid credentials` when trying to sign in with the email they just verified!
- **Evidence / test status:**
  - Confirmed in `backend/accounts/views.py:446-453`.
- **Root cause:**
  - Anti-enumeration logic for `phone_taken` returns a silent 200 OK instead of either validating the email OTP first or returning a generic/field error, leaving a verified new email registrant with no account and no explanation.
- **Impact:**
  - High user confusion and support burden when an Indian merchant enters a shared family/business mobile number during registration: they receive the email OTP, complete signup, see a success redirect, and then cannot log in.
- **Recommended correction:**
  - Verify the email OTP first; once the caller has proven possession of the email OTP for a new email address, if `phone_taken(phone=canonical_phone)` is true, return a 400 validation error on `phone` (or clear `phone` / inform the user) instead of silently discarding the registration with HTTP 200.
- **Regression tests required:**
  - Backend test in `test_auth.py` testing registration with a valid email OTP + duplicate phone number.
- **Acceptance criteria:**
  - A user who verifies a valid email OTP is never silently dropped with a fake 200 OK without an account being created.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-007` — Missing State vs GSTIN Prefix Synchronization in Setup Wizard & `CompanySerializer`
- **Finding ID:** `ONB-CR-007`
- **Title:** Setup Wizard Step 1 (`tax`) and `CompanySerializer` do not check or sync `company.state` against the 2-digit state prefix of a newly entered GSTIN
- **Severity:** **P2 (Medium)**
- **Category:** Validation / Data Integrity
- **Affected screen / route:** `SCR-09` (`/setup?step=tax`), `SCR-20` (`/settings/gst`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 184–203, 405–415)
  - `backend/accounts/serializers.py` (`CompanySerializer.validate`, lines 354–384)
  - Compare with `backend/accounts/serializers.py` (`RegisterSerializer.validate`, lines 110–122) and `web/src/pages/RegisterPage.tsx` (`gstinStateMismatch`, line 79)
- **Preconditions:**
  - User registers on `/register` with `state = "Karnataka"` (`29`) and leaves `gstin` blank.
  - On `/setup?step=tax`, user enters a valid Maharashtra GSTIN (`27AABCU9603R1ZM`).
- **Reproduction steps:**
  1. On `/setup?step=tax`, enter `27AABCU9603R1ZM` (state code `27` = Maharashtra) while `company.state` is `Karnataka`.
  2. Click **Save & continue**.
- **Expected behavior:**
  - Just like `RegisterPage.tsx` (which uses `gstinStateMismatch(gstin, state)`) and `RegisterSerializer.validate` (lines 110–122, which rejects a GSTIN whose state code conflicts with `state`), `SetupWizardPage` and `CompanySerializer` should warn or reject a GSTIN whose 2-digit state code conflicts with `company.state` (or allow updating `company.state`).
- **Actual behavior:**
  - `SetupWizardPage.tsx` does not call `gstinStateMismatch(gstin, company?.state)` and `CompanySerializer.validate()` only calls `validate_gstin(gstin)` without checking `gstin_state_name(gstin)` against `company.state`.
  - The company is saved with `state = "Karnataka"` and `gstin = "27AABCU9603R1ZM"` (Maharashtra), causing intra-state vs inter-state (CGST/SGST vs IGST) calculation mismatches on subsequent invoices.
- **Evidence / test status:**
  - Confirmed by comparing `RegisterSerializer.validate` (`serializers.py:110-122`) with `CompanySerializer.validate` (`serializers.py:354-384`).
- **Root cause:**
  - `gstin_state_name` validation was implemented in `RegisterSerializer` and `RegisterPage.tsx` but omitted from `SetupWizardPage.tsx` and `CompanySerializer`.
- **Impact:**
  - Inconsistent `company.state` and `company.gstin` state prefix leads to wrong CGST/SGST vs IGST tax splits on invoices.
- **Recommended correction:**
  - Display the `gstinStateMismatch` helper/warning in `SetupWizardPage.tsx` Step 1 and validate or sync `company.state` from `gstin_state_name(gstin)` in `CompanySerializer` when the primary GSTIN is set during onboarding.
- **Regression tests required:**
  - Unit tests in `SetupWizardPage.test.tsx` and `test_onboarding.py` for GSTIN state-code consistency.
- **Acceptance criteria:**
  - Entering a GSTIN in `/setup?step=tax` validates state-code consistency with `company.state`.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-008` — Setup Wizard Step 3 (`payments`) Omits Bank Name and IFSC Code
- **Finding ID:** `ONB-CR-008`
- **Title:** Setup Wizard Step 3 (`payments`) collects `bankAccount` and `upiId` but omits `bankName` and `bankIfsc`, syncing an incomplete `BankAccount` record (`name="Company bank"`, `ifsc=""`)
- **Severity:** **P2 (Medium)**
- **Category:** Functional / Payments
- **Affected screen / route:** `SCR-11` (`/setup?step=payments`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 65–66, 226–240, 441–446)
  - `backend/payments/services.py` (`sync_company_bank_account`, lines 135–188)
- **Preconditions:**
  - Owner reaches Step 3 (`payments`) of `/setup`.
- **Reproduction steps:**
  1. On `/setup?step=payments`, observe the form fields: only `Bank account number` and `UPI ID` are shown.
  2. Enter a bank account number and click **Save & continue**.
- **Expected behavior:**
  - When a user enters a bank account number to print on customer invoices in India, they need `Bank Name` and `IFSC Code` (`bankName`, `bankIfsc`) alongside `Bank Account Number` so customers can pay via NEFT/RTGS/IMPS.
- **Actual behavior:**
  - `SetupWizardPage.tsx` only sends `{ bankAccount, upiId }`. `sync_company_bank_account` creates a `BankAccount` row with `name="Company bank"` and `ifsc=""`, printing a bank account number without an IFSC code on invoices until the owner visits `/settings/bank-accounts`.
- **Evidence / test status:**
  - Confirmed in `SetupWizardPage.tsx:443-444` and `backend/tests/personas/test_pj_ftue_onboarding_and_help.py:112-119` (where the backend FTUE test sends `bank_account`, `bank_name`, `bank_ifsc`, and `upi_id`, even though the frontend wizard UI lacks inputs for `bankName` and `bankIfsc`).
- **Root cause:**
  - `bankName` and `bankIfsc` inputs were omitted from `SetupWizardPage.tsx` Step 3.
- **Impact:**
  - Invoices printed after completing the Setup Wizard show a bank account number with no IFSC code or bank name, making NEFT/IMPS transfers impossible without manual follow-up.
- **Recommended correction:**
  - Add optional `bankName` and `bankIfsc` fields to Step 3 (`payments`) of `SetupWizardPage.tsx` and pass them in `updateCompany({ bankName, bankAccount, bankIfsc, upiId })`.
- **Regression tests required:**
  - Update `SetupWizardPage.test.tsx` to verify `bankName` and `bankIfsc` are rendered and submitted when provided.
- **Acceptance criteria:**
  - Owner can enter `Bank name`, `Bank account number`, `IFSC code`, and `UPI ID` in Step 3 of `/setup`.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-009` — Setup Wizard Step 5 (`pack` Step) Uses Raw Pack Keys and Doesn't Reset Preview When Answers Change
- **Finding ID:** `ONB-CR-009`
- **Title:** Setup Wizard Step 5 (`pack` step) displays raw pack keys (`retail`/`trade`), lacks the 4-group preview breakdown, and does not reset `proposedPack` when answers change
- **Severity:** **P2 (Medium)**
- **Category:** Functional / State Machine
- **Affected screen / route:** `SCR-13` (`/setup?step=pack`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 72–78, 338–355, 467–492)
  - Compare with `web/src/pages/settings/PackWizardPage.tsx` (lines 48–62, 170–248)
- **Preconditions:**
  - `ENABLE_ARCHETYPE_PACKS` is enabled and Owner reaches `/setup?step=pack`.
- **Reproduction steps:**
  1. On `/setup?step=pack`, click **See pack** (`runPackStep` -> `proposePack(packAnswers)`).
  2. Observe the alert: `Recommended pack: retail` (raw lowercase internal key `'retail'` instead of localized `t('osPlan.pack.retail')` = `'Retail counter'`).
  3. Change `How do you sell?` from `At a counter` (`counter`) to `On the road / on credit` (`field`).
  4. Notice the primary button STILL says **Apply pack** and the alert STILL says `Recommended pack: retail`!
  5. Click **Apply pack** — it sends `confirmPack(packAnswers)` with the mutated answers (`field` -> `trade`) without ever previewing `trade`!
- **Expected behavior:**
  - Changing any answer in `packAnswers` must clear `proposedPack` (just like `PackWizardPage.tsx:58-62` does in `updateAnswer`), and the proposed pack name should use `t('osPlan.pack.' + proposedPack)`.
- **Actual behavior:**
  - `SetupWizardPage.tsx` does not clear `proposedPack` when answers are changed and passes the raw key (`'retail'` / `'trade'`) into `t('osPlan.proposedPack', { name: proposedPack })`.
- **Evidence / test status:**
  - Confirmed by comparing `SetupWizardPage.tsx:467-492` with `PackWizardPage.tsx:58-62,193`.
- **Root cause:**
  - `SetupWizardPage.tsx` duplicated a simplified version of `PackWizardPage.tsx` without resetting `proposedPack` on answer change or translating the pack key.
- **Impact:**
  - Users see raw internal identifiers (`retail`, `trade`) and can accidentally apply a different pack than the one shown in the recommendation banner.
- **Recommended correction:**
  - Reset `setProposedPack(null)` whenever any `packAnswers` select changes in `SetupWizardPage.tsx`, and format the pack name via `t(\`osPlan.pack.\${proposedPack}\`, undefined, proposedPack)`.
- **Regression tests required:**
  - Add test case in `SetupWizardPackStep.test.tsx` verifying that changing an answer after previewing resets the primary action back to `See pack` and translates the pack name.
- **Acceptance criteria:**
  - Pack name is localized (`Retail counter` / `Wholesale & trade`) and changing any answer requires re-previewing before applying.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-010` — `OnboardingChecklist` Exposes Owner-Only Actions to Non-Owner Dashboard Roles (`MANAGER`, `ACCOUNTANT`, `AUDITOR`)
- **Finding ID:** `ONB-CR-010`
- **Title:** `OnboardingChecklist` renders owner-only `Dismiss guide` action and owner-only settings links for `MANAGER`, `ACCOUNTANT`, and `AUDITOR` users, resulting in HTTP 403 errors
- **Severity:** **P2 (Medium)**
- **Category:** Authorization / UI
- **Affected screen / route:** `SCR-15` (`/` — `DashboardPage` / `OnboardingChecklist`)
- **Affected file / component / API / model:**
  - `web/src/components/OnboardingChecklist.tsx` (lines 38–159)
  - `web/src/pages/DashboardPage.tsx` (lines 72–73, 189–213)
  - `backend/accounts/views.py` (`CompanyDetailView`, lines 776–781 — requires `IsOwner` for `PATCH /api/v1/company/`)
- **Preconditions:**
  - An invited `MANAGER`, `ACCOUNTANT`, or `AUDITOR` logs into a company whose onboarding status is still `NOT_STARTED` or `IN_PROGRESS`.
- **Reproduction steps:**
  1. Log in as `MANAGER`, `ACCOUNTANT`, or `AUDITOR` and land on `/` (`DashboardPage`).
  2. Observe `OnboardingChecklist` rendered at the top of the dashboard.
  3. Click the `X` (**Dismiss guide**) button on `OnboardingChecklist`, OR click **Shop Details** when `VITE_ENABLE_SETUP_WIZARD=true` (which links to `/setup?step=shop`, gated by `RoleRoute(['OWNER'])`).
- **Expected behavior:**
  - `OnboardingChecklist` should either only render for `OWNER`, or hide owner-only mutations (`Dismiss guide` -> `PATCH /api/v1/company/`) and `/setup` links when `user.role !== 'OWNER'`.
- **Actual behavior:**
  - Clicking `Dismiss guide` fires `PATCH /api/v1/company/ {dismissOnboarding: true}`, which fails with **HTTP 403 Forbidden** (`IsOwner` permission on `CompanyDetailView.patch`), and `onError` silently swallows it!
  - Clicking any step button when `wizardEnabled` is true navigates the `MANAGER`/`ACCOUNTANT`/`AUDITOR` to `/setup?step=...`, where `RoleRoute(['OWNER'])` renders an **Access denied** screen!
- **Evidence / test status:**
  - Confirmed in `OnboardingChecklist.tsx:53-59,90-125` and `App.tsx:251-257`.
- **Root cause:**
  - `OnboardingChecklist.tsx` does not check `useAuth().user?.role === 'OWNER'`.
- **Impact:**
  - Non-owner dashboard roles hit dead-end "Access denied" screens or silent 403 errors when interacting with the onboarding checklist card.
- **Recommended correction:**
  - Gate `OnboardingChecklist` (or its owner-only `/setup` links and `Dismiss guide` button) on `user?.role === 'OWNER'`.
- **Regression tests required:**
  - Unit test verifying `OnboardingChecklist` does not render `/setup` links or the `PATCH /api/v1/company/` dismiss button for non-owner roles.
- **Acceptance criteria:**
  - Non-owner roles never see links to `/setup` or buttons that trigger HTTP 403 on `PATCH /api/v1/company/`.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-011` — Frontend `isSetupWizardEnabled()` Ignores Backend Runtime `ENABLE_SETUP_WIZARD` Feature Flag
- **Finding ID:** `ONB-CR-011`
- **Title:** Frontend `isSetupWizardEnabled()` only checks build-time `import.meta.env.VITE_ENABLE_SETUP_WIZARD`, ignoring the backend runtime `/api/v1/feature-flags/` `ENABLE_SETUP_WIZARD` flag
- **Severity:** **P2 (Medium)**
- **Category:** Architecture / Feature Flags
- **Affected screen / route:** `SCR-09`–`SCR-15` (`web/src/config/features.ts`)
- **Affected file / component / API / model:**
  - `web/src/config/features.ts` (lines 14–16: `export function isSetupWizardEnabled(): boolean { return flag('VITE_ENABLE_SETUP_WIZARD'); }`)
  - `backend/core/services/feature_flags.py` (lines 35, 105 — exposes `ENABLE_SETUP_WIZARD` in `/api/v1/feature-flags/` and `ROLLOUT_GRANTABLE_KEYS`)
- **Preconditions:**
  - Backend enables `ENABLE_SETUP_WIZARD=True` (either via Django settings or per-company `feature_flags["ENABLE_SETUP_WIZARD"] = True`), while the static Vite bundle was built without `VITE_ENABLE_SETUP_WIZARD=true`.
- **Reproduction steps:**
  1. Enable `ENABLE_SETUP_WIZARD=True` on the backend or in `company.feature_flags`.
  2. Log in as a newly registered `OWNER`.
- **Expected behavior:**
  - `isSetupWizardEnabled()` should check `isRuntimeFlagEnabled('ENABLE_SETUP_WIZARD') || flag('VITE_ENABLE_SETUP_WIZARD')` so staged per-company rollouts (configured in `ROLLOUT_GRANTABLE_KEYS` and tested in `backend/tests/test_onboarding.py:143`) actually work in the SPA.
- **Actual behavior:**
  - `web/src/config/features.ts:14` only reads `import.meta.env.VITE_ENABLE_SETUP_WIZARD === 'true'`, completely ignoring the runtime `/api/v1/feature-flags/` `ENABLE_SETUP_WIZARD` boolean!
- **Evidence / test status:**
  - Confirmed in `web/src/config/features.ts:14-16` vs `backend/tests/test_onboarding.py:143-147`.
- **Root cause:**
  - `isSetupWizardEnabled()` was written before runtime feature flags were unified in `web/src/config/featureFlags.ts`.
- **Impact:**
  - Per-tenant or backend-controlled rollout of `ENABLE_SETUP_WIZARD` has no effect on the frontend unless the static bundle is rebuilt with `VITE_ENABLE_SETUP_WIZARD=true`.
- **Recommended correction:**
  - Update `isSetupWizardEnabled()` in `web/src/config/features.ts` to return `flag('VITE_ENABLE_SETUP_WIZARD') || isRuntimeFlagEnabled('ENABLE_SETUP_WIZARD')`.
- **Regression tests required:**
  - Unit test verifying `isSetupWizardEnabled()` returns `true` when runtime flag `ENABLE_SETUP_WIZARD` is enabled.
- **Acceptance criteria:**
  - Enabling `ENABLE_SETUP_WIZARD` via backend `/api/v1/feature-flags/` activates `/setup` and `shouldForceSetup` on the frontend.
- **Verification status:** Confirmed in code review.

---

### `ONB-CR-012` — `settings_health` Marks `gstin` as `todo` for Confirmed `UNREGISTERED` Companies
- **Finding ID:** `ONB-CR-012`
- **Title:** `settings_health(company)` always reports `gstin: "todo"` for `UNREGISTERED` companies even after they confirm their unregistered tax profile
- **Severity:** **P3 (Low)**
- **Category:** Functional / Settings Health
- **Affected screen / route:** `SCR-18` (`/settings`)
- **Affected file / component / API / model:**
  - `backend/accounts/settings_health.py` (lines 33–34)
- **Preconditions:**
  - Company completes Step 1 of `/setup` as `UNREGISTERED` (`registration_type='UNREGISTERED'`, `tax_profile_confirmed_at` is set, `gstin=""`).
- **Reproduction steps:**
  1. Navigate to `/settings` (`SettingsHubPage`).
  2. Observe the GST settings card health chip.
- **Expected behavior:**
  - An `UNREGISTERED` business by definition does not have a GSTIN; once `registration_type == 'UNREGISTERED'` and `tax_profile_confirmed_at` is set (or always for `UNREGISTERED`), `settings_health` should report `ok` for `gstin` instead of nagging the owner with `todo` (`Needs attention`).
- **Actual behavior:**
  - `settings_health.py:33-34` checks `has_gstin = bool(company.gstin) or ...` and appends `_item("gstin", OK if has_gstin else TODO, "/settings/gst")` unconditionally, so `UNREGISTERED` companies permanently have `needs_attention >= 1` for a missing GSTIN.
- **Evidence / test status:**
  - Confirmed in `backend/accounts/settings_health.py:33-34`.
- **Root cause:**
  - `settings_health` did not check `company.registration_type == Company.RegistrationType.UNREGISTERED`.
- **Impact:**
  - Unregistered small merchants see a permanent "To do" badge on `/settings` telling them to add a GSTIN they do not possess.
- **Recommended correction:**
  - Treat `gstin` health item as `OK` when `company.registration_type == Company.RegistrationType.UNREGISTERED`.
- **Regression tests required:**
  - Backend unit test in `test_onboarding.py` checking `settings_health(company)` for an `UNREGISTERED` company.
- **Acceptance criteria:**
  - `settings_health` returns `status="ok"` for `gstin` when `company.registration_type == "UNREGISTERED"`.
- **Verification status:** Confirmed in code review.

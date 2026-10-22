# Bizboard — Onboarding Defect Log & Prioritized Remediation Plan (`ONBOARDING_REMEDIATION_PLAN.md`)

**Audit Date:** 2026-10-21  
**Status:** Phase 8 Complete — Ready for Phase 9 Controlled Implementation & Verification.

---

## 1. Consolidated Prioritized Defect Log (23 Confirmed Findings)

### P0 — Blocker
*None (core registration, login, and database creation succeed without data corruption or tenant leakage).*

### P1 — High Severity (Must Fix Before Production Onboarding Sign-Off)

| ID | Category | Screen / Route | Summary | Target Files for Fix |
|---|---|---|---|---|
| `ONB-CR-001` | Functional / State Machine | `SCR-14` (`/setup?step=first_bill` -> `/`) | Step 5 creates a `DRAFT` invoice without completing it or dismissing onboarding; clicking "Go to Dashboard" triggers `shouldForceSetup` and redirects Owner back to `/setup` in an infinite loop. | `web/src/pages/setup/SetupWizardPage.tsx`, `backend/accounts/onboarding.py` |
| `ONB-CR-002` | Validation / API Contract | `SCR-09` (`/setup?step=tax`) | UI marks GSTIN as optional for `COMPOSITION`, but `CompanySerializer.validate` rejects blank GSTIN with HTTP 400. | `backend/accounts/serializers.py`, `web/src/pages/setup/SetupWizardPage.tsx` |
| `ONB-CR-003` | Functional / UI | `SCR-05` (`/login` forced 2FA enrolment) | Forced 2FA enrolment on `/login` fails to render QR code (`setup.qrPng`) and hides all login forms after clicking "I have saved them" (`enrolDone` remains `true`). | `web/src/pages/LoginPage.tsx` |
| `ONB-CR-004` | Functional / Cache Coherency | `SCR-09`, `SCR-12`, `SCR-14` (`/setup`) | `saveTax`, `saveShop`, and `savePayments` do not invalidate `['company']` React Query cache; changing `registrationType` to `UNREGISTERED` or `COMPOSITION` still creates a `GST` tax invoice in Step 5. | `web/src/pages/setup/SetupWizardPage.tsx` |
| `ONB-CR-005` | Functional / Business Logic | `SCR-12`, `SCR-14` (`/setup?step=catalog`) | Sample products (`SAMPLE-ITEM`) are created with `0` stock while `Company.negative_stock_policy` defaults to `BLOCK`, causing invoice completion to fail with `NegativeStockError`. | `web/src/pages/setup/SetupWizardPage.tsx` |

### P2 — Medium Severity (Should Fix in Current Remediation Pass)

| ID | Category | Screen / Route | Summary | Target Files for Fix |
|---|---|---|---|---|
| `ONB-CR-006` | Functional / Validation | `SCR-01` (`/register`) | Registering with a new email + valid email OTP + an already-used phone number silently returns HTTP 200 OK without creating the user, causing immediate 401 on login. | `backend/accounts/views.py` (`RegisterView.create`) |
| `ONB-CR-007` | Validation / Data Integrity | `SCR-09` (`/setup?step=tax`) | Setup Wizard Step 1 and `CompanySerializer` do not check or sync `company.state` against the 2-digit state prefix of a newly entered GSTIN. | `web/src/pages/setup/SetupWizardPage.tsx`, `backend/accounts/serializers.py` |
| `ONB-CR-008` | Functional / Payments | `SCR-11` (`/setup?step=payments`) | Step 3 (`payments`) collects `bankAccount` and `upiId` but omits `bankName` and `bankIfsc`, creating an incomplete invoice bank record. | `web/src/pages/setup/SetupWizardPage.tsx`, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts` |
| `ONB-CR-009` | Functional / State Machine | `SCR-13` (`/setup?step=pack`) | Step 5 (`pack`) displays raw pack keys (`retail`/`trade`) instead of localized names and does not reset `proposedPack` when answers change. | `web/src/pages/setup/SetupWizardPage.tsx` |
| `ONB-CR-010` | Authorization / UI | `SCR-15` (`/` — `OnboardingChecklist`) | `OnboardingChecklist` exposes owner-only `Dismiss guide` (`PATCH /api/v1/company/`) and `/setup` links to non-owner roles (`MANAGER`, `ACCOUNTANT`, `AUDITOR`). | `web/src/components/OnboardingChecklist.tsx` |
| `ONB-CR-011` | Architecture / Feature Flags | `SCR-09`–`SCR-15` (`web/src/config/features.ts`) | `isSetupWizardEnabled()` only checks build-time `VITE_ENABLE_SETUP_WIZARD`, ignoring runtime `ENABLE_SETUP_WIZARD` from `/api/v1/feature-flags/`. | `web/src/config/features.ts` |
| `ONB-SEC-001` | Security / Authentication | `SCR-08` (`/invite`) | `AcceptInviteView` switches `user.active_company` for an existing 2FA-enabled user before MFA verification when called unauthenticated. | `backend/accounts/views.py` (`AcceptInviteView.post`) |
| `ONB-UX-001` | UX / Localization | `SCR-02`, `SCR-03` (`/login` in Hindi) | Hindi `auth.demoHint` says `"सीड किया हुआ मालिक खाता उपयोग करें..."` ("Use the seeded owner account..."). | `web/src/i18n/hi.ts` |
| `ONB-UX-002` | UX / Cognitive Load | `SCR-01` (`/register`) | `RegisterPage` has no resend cooldown timer on `Send code` / `Resend code` and keeps stale `codeSentTo` alert when `email` is edited. | `web/src/pages/RegisterPage.tsx` |
| `ONB-UX-003` | UX / Copy Accuracy | `SCR-09`–`SCR-14` (`/setup`) | Setup Wizard subtitle hardcodes "Five focused steps to your first completed bill" even when 6 steps are shown and Step 5 creates a draft bill. | `web/src/i18n/en.ts`, `web/src/i18n/hi.ts` |
| `ONB-UX-004` | UX / Invite Flow | `SCR-08` (`/invite`) | `AcceptInvitePage` prompts existing multi-company users for a "New password" when the backend requires their current password. | `web/src/pages/AcceptInvitePage.tsx`, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts` |
| `ONB-UX-005` | UX / Localization | `SCR-12` (`/setup?step=catalog` in Hindi) | Hindi sample warning (`setup.addSamplesWarning` / `addSamplesConfirm`) leaves `"Products"` untranslated. | `web/src/i18n/hi.ts` |
| `ONB-UX-006` | Accessibility / Responsive | `SCR-09`–`SCR-14` (`/setup`) | `<Stepper>` overflows horizontally on 360px mobile screens when 5–6 steps are shown and lacks `aria-live="polite"` on step progress. | `web/src/pages/setup/SetupWizardPage.tsx` |

### P3 — Low Severity (Polish & Hygiene)

| ID | Category | Screen / Route | Summary | Target Files for Fix |
|---|---|---|---|---|
| `ONB-CR-012` | Functional / Settings Health | `SCR-18` (`/settings`) | `settings_health(company)` marks `gstin` as `todo` even when `company.registration_type == 'UNREGISTERED'`. | `backend/accounts/settings_health.py` |
| `ONB-UX-007` | UX / Indian SMB Guidance | `SCR-09`, `SCR-10` (`/setup`) | `company.state` is static read-only text in `/setup`; auto-syncing or warning on GSTIN prefix (`ONB-CR-007`) resolves this cleanly. | `web/src/pages/setup/SetupWizardPage.tsx`, `backend/accounts/serializers.py` |
| `ONB-UX-008` | Accessibility / Form Semantics | `SCR-08` (`/invite`) | `AcceptInvitePage` uses plain `<TextField type="password">` instead of `<PasswordField>` with show/hide toggle. | `web/src/pages/AcceptInvitePage.tsx` |
| `ONB-SEC-002` | Security / Operational | `SCR-01`, `SCR-03` | `OTP_DEBUG_ECHO=True` echoes `debug_code` only for new emails / registered phones (already blocked when `DEBUG=False`). | Operational control (no code change needed) |
| `ONB-SEC-003` | Security / Session Hygiene | `SCR-02`, `SCR-03`, `SCR-08` | `AuthContext.login` / `AcceptInvitePage` do not overwrite stale `localStorage['bizboard:active-company-id']` from a prior session on the same browser. | `web/src/auth/AuthContext.tsx`, `web/src/pages/AcceptInvitePage.tsx` |

---

## 2. Safe Remediation Architecture (Phase 9 Plan)

All fixes are surgical, backward-compatible, and require **zero destructive database migrations**:

### Batch 1 — Backend Onboarding, Serializer, Invite & Settings-Health Fixes
1. **`backend/accounts/serializers.py` (`ONB-CR-002`, `ONB-CR-007`):**
   - In `CompanySerializer.validate()`:
     - Require a 15-character GSTIN strictly when `registration_type == Company.RegistrationType.REGULAR` (for `COMPOSITION`, validate the 15-char GSTIN if provided, or allow blank when confirming tax profile, matching `SetupWizardPage.tsx` and `test_onboarding.py:109`).
     - When a valid 15-character `gstin` is saved on `Company` and `state` is not explicitly being changed to something else, if `gstin_state_name(gstin)` resolves to a valid state name and `company.state` was set at registration without a GSTIN, either sync `attrs["state"] = gstin_state_name(gstin)` (when `confirm_tax_profile` is true) or raise a clear validation error if an explicit `state` in `attrs` conflicts with `gstin[:2]`.
2. **`backend/accounts/views.py` (`ONB-CR-006`, `ONB-SEC-001`):**
   - In `RegisterView.create()`:
     - Verify the email OTP (`otp_code`) for the new email address first (or check `phone_taken` after confirming the caller owns the new email via OTP); if `email` does not exist and the caller has provided a valid `otp_code` for that new email, if `canonical_phone and phone_taken(phone=canonical_phone)`, return HTTP 400 `{"phone": ["This mobile number is already registered with another account."]}` without consuming the email OTP so the user can immediately correct or clear the optional phone field and click "Create account" again! (If `email` already exists, keep the existing non-enumerating 200 OK return).
   - In `AcceptInviteView.post()`:
     - If `not caller_already_authenticated` and `(enrolment_required(user) or mfa_is_enabled(user))`, only set `user.active_company = membership.company` if `user.active_company_id is None`, preserving the user's existing active company until they complete MFA login.
3. **`backend/accounts/settings_health.py` (`ONB-CR-012`):**
   - In `settings_health(company)`: treat `gstin` status as `OK` when `company.registration_type == Company.RegistrationType.UNREGISTERED`.

### Batch 2 — Frontend Setup Wizard (`SetupWizardPage.tsx`) & Feature Flag Fixes
1. **`web/src/pages/setup/SetupWizardPage.tsx` (`ONB-CR-001`, `ONB-CR-004`, `ONB-CR-005`, `ONB-CR-007`, `ONB-CR-008`, `ONB-CR-009`, `ONB-UX-006`):**
   - **Fix `ONB-CR-001` (Infinite loop after creating draft bill):** In `createFirstBill()`, after creating the draft invoice (`inv`), call `await updateCompany({ dismissOnboarding: true })` and `await qc.invalidateQueries({ queryKey: ['company'] })` so onboarding is marked finished and clicking "Go to Dashboard" (`/`) lands cleanly on `DashboardPage` without redirecting back to `/setup`!
   - **Fix `ONB-CR-004` (Stale `company` cache across steps):** Call `await qc.invalidateQueries({ queryKey: ['company'] })` in `saveTax`, `saveShop`, and `savePayments`, and use `registrationType === 'REGULAR'` (instead of stale `company?.registrationType === 'REGULAR'`) in `createFirstBill` and Step 5 rendering.
   - **Fix `ONB-CR-005` (Sample product 0 stock block):** In `addSamples()`, set `trackInventory: false` on the 3 sample items (or post opening stock for `SAMPLE-ITEM`) so a draft bill created from sample items can be completed without `NegativeStockError`.
   - **Fix `ONB-CR-007` (GSTIN state mismatch warning):** Compute `gstinMismatch = gstinStateMismatch(gstin, company?.state)` in `SetupWizardPage.tsx` and display `t('tax.gstinStateMismatch', { gstinState: gstinMismatch, selectedState: company?.state || '' })` as a warning helper on the GSTIN field in Step 1.
   - **Fix `ONB-CR-008` (Bank Name & IFSC in Step 3):** Add `bankName` and `bankIfsc` fields to Step 3 (`payments`) and pass them to `updateCompany({ bankName, bankAccount, bankIfsc, upiId })`.
   - **Fix `ONB-CR-009` (Pack step preview reset & localized name):** Reset `setProposedPack(null)` whenever any `packAnswers` dropdown changes, and display `t(\`osPlan.pack.\${proposedPack}\`, undefined, proposedPack)` instead of the raw key.
   - **Fix `ONB-UX-006` (Mobile Stepper overflow & a11y):** Add `sx={{ mb: 3, overflowX: 'auto', pb: 1 }}` to `<Stepper>` and `aria-live="polite"` to the step progress chip/header.
2. **`web/src/config/features.ts` (`ONB-CR-011`):**
   - Update `isSetupWizardEnabled()` to check `flag('VITE_ENABLE_SETUP_WIZARD') || isRuntimeFlagEnabled('ENABLE_SETUP_WIZARD')`.
3. **`web/src/components/OnboardingChecklist.tsx` (`ONB-CR-010`):**
   - Check `const isOwner = user?.role === 'OWNER';` — only render the `Dismiss guide` (`PATCH /api/v1/company/`) button and `/setup` links when `isOwner` is true (or only show `OnboardingChecklist` to `OWNER`).

### Batch 3 — Frontend Auth, MFA Enrolment, Invite & Localization Fixes
1. **`web/src/pages/LoginPage.tsx` (`ONB-CR-003`):**
   - Store `enrolQrPng` (`setup.qrPng`) in `startEnrolment()` and render `<Box component="img" src={enrolQrPng} alt={t('auth.mfa.qrAlt')} sx={{ width: 180, height: 180, alignSelf: 'center', border: '1px solid', borderColor: 'divider', borderRadius: 1 }} />` when present.
   - Change line 345 from `{mfaToken || enrolToken || enrolDone ? null : (` to `{mfaToken || enrolToken || recoveryCodes ? null : (` so that once the user clicks **I have saved them** (`setRecoveryCodes(null)`), the `enrolDone` success banner stays visible at the top and the password sign-in form reappears immediately below it!
2. **`web/src/pages/RegisterPage.tsx` (`ONB-UX-002`):**
   - Clear `codeSentTo` when `email` changes to a different address, and add a 30-second resend cooldown (`resendCooldown`) on the `Send code` / `Resend code` button.
3. **`web/src/pages/AcceptInvitePage.tsx` & `web/src/auth/AuthContext.tsx` (`ONB-UX-004`, `ONB-UX-008`, `ONB-SEC-003`):**
   - Replace `<TextField type="password">` with `<PasswordField>` in `AcceptInvitePage.tsx`.
   - Sync `ACTIVE_COMPANY_STORAGE_KEY` (`bizboard:active-company-id`) in `localStorage` with `user.companyId` upon `login`, `loginWithOtp`, `completeMfaLogin`, and `AcceptInvitePage` activation.
4. **`web/src/i18n/en.ts` & `web/src/i18n/hi.ts` (`ONB-UX-001`, `ONB-UX-003`, `ONB-UX-004`, `ONB-UX-005`):**
   - Fix `hi.ts` `auth.demoHint` to remove `"सीड किया हुआ मालिक खाता"`.
   - Update `setup.subtitle`, `setup.descriptions.first_bill`, `setup.bankName`, `setup.bankIfsc`, `invite.description`, and `hi.ts` `setup.addSamplesWarning` / `addSamplesConfirm`.

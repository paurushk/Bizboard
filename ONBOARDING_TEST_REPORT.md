# Bizboard — Onboarding Automated & Runtime Test Execution Report (`ONBOARDING_TEST_REPORT.md`)

**Audit Date:** 2026-10-21  
**Environment:** Windows 11 (`win32`), Python 3.13.x (`pytest`), Node.js / Vite / Vitest 2.1.9 (`web/`).

---

## 1. Summary of Executed Automated Test Suites

| Suite / Layer | Command Executed | Test Files | Tests Run | Passed | Failed | Skipped | Duration |
|---|---|---|---|---|---|---|---|
| **Backend — Onboarding, Auth, MFA, Packs & FTUE Personas** | `.\.venv\Scripts\python.exe -m pytest tests/test_onboarding.py tests/test_auth.py tests/test_mfa.py tests/test_mfa_edge_cases.py tests/test_settings_ai_and_packs.py tests/personas/test_pj_ftue_onboarding_and_help.py -q` | 6 | 154 | **154** | 0 | 0 | 128.47s |
| **Backend — User Invites & Company Settings Matrix** | `.\.venv\Scripts\python.exe -m pytest tests/test_settings_users.py tests/matrices/test_company_settings_matrix.py -q` | 2 | 22 | **22** | 0 | 0 | 23.62s |
| **Frontend — Registration, Login MFA, OTP, Setup Wizard & Tax Hints** | `npx vitest run src/pages/RegisterPage.test.tsx src/pages/LoginPage.mfa.test.tsx src/pages/loginOtp.test.ts src/pages/setup/SetupWizardPage.test.tsx src/pages/setup/SetupWizardPackStep.test.tsx src/onboarding/taxHints.test.ts` | 6 | 29 | **29** | 0 | 0 | 95.77s |
| **Frontend — Accept Invite, Users/Invites Settings, Pack Wizard & PasswordField** | `npx vitest run src/pages/settings/UsersInvites.test.tsx src/pages/AcceptInvitePage.test.tsx src/components/PasswordField.test.tsx src/pages/settings/PackWizardPage.test.tsx` | 4 | 18 | **18** | 0 | 0 | 65.33s |
| **TOTAL EXECUTED** | — | **18 files** | **223 tests** | **223** | **0** | **0** | **313.19s** |

---

## 2. Detailed Breakdown by Test File

### 2.1 Backend Test Suites (`backend/tests/`)
1. **`tests/test_onboarding.py` (10 passed):**
   - `test_derive_completed_when_completed_invoice_exists` — PASS
   - `test_dismissed_company_with_address_is_not_forced_into_setup` — PASS
   - `test_owner_can_dismiss_onboarding` — PASS
   - `test_regular_tax_confirmation_requires_valid_gstin` — PASS
   - `test_composition_cannot_complete_gst_tax_invoice` — PASS
   - `test_setup_wizard_feature_flag_is_exposed` — PASS
   - `test_j_onboard_p1_steps_blocking_path_is_four` — PASS
   - `test_payments_optional_does_not_block_catalog_step` — PASS
   - `test_backfill_dismisses_existing_progress_companies` — PASS
   - `test_archetype_pack_follows_how_you_sell_and_skips_a_denied_flag` — PASS
   - `test_trade_pack_does_not_turn_on_crm_when_the_plan_omits_it` — PASS
   - `test_trial_modules_list_grantable_flags_and_keep_dark_off` — PASS
   - `test_migrated_trial_plan_row_holds_back_growth_os_flags` — PASS
   - `test_pack_adds_four_flags_and_does_not_rewrite_a_hand_edit` — PASS
2. **`tests/personas/test_pj_ftue_onboarding_and_help.py` (3 passed):**
   - `test_pj_ftue_founder_onboarding_stepper_and_error_recovery` — PASS
   - `test_pj_ftue_team_invite_landing_and_role_access` — PASS
   - `test_pj_ftue_help_error_code_to_intent_resolution` — PASS
3. **`tests/test_auth.py`, `tests/test_mfa.py`, `tests/test_mfa_edge_cases.py`, `tests/test_settings_ai_and_packs.py` (141 passed):**
   - Covers signup email OTP verification, login password & mobile OTP, JWT cookie issuance & refresh rotation, CSRF cookie/body verification, TOTP MFA setup/confirm/verify/disable/recovery codes, forced money-role MFA enrolment (`enrol_token` presentation caps & JTI burn), password reset token consumption & `token_version` bump, and pack wizard API.
4. **`tests/test_settings_users.py` & `tests/matrices/test_company_settings_matrix.py` (22 passed):**
   - Covers staff invitation creation, resend, cancel, expiry, existing-user vs new-user invite acceptance, and company settings validation matrix.

### 2.2 Frontend Unit & Component Test Suites (`web/src/`)
1. **`src/pages/RegisterPage.test.tsx` (4 passed):**
   - Hindi validation messages for company, email, state, and emailed OTP code.
   - Indian mobile number E.164 normalization (`098765 43210` -> `+919876543210`).
   - Client-side short phone rejection and server-side `phone` error mapping under the field.
2. **`src/pages/LoginPage.mfa.test.tsx` (10 passed) & `src/pages/loginOtp.test.ts` (2 passed):**
   - Standard password sign-in redirect, MFA challenge transition (`MfaRequiredError`), TOTP & recovery code submission, 401 invalid code handling, back-to-sign-in reset, forced enrolment transition (`MfaEnrollmentRequiredError`), and Hindi validation on email & mobile OTP tabs.
3. **`src/pages/setup/SetupWizardPage.test.tsx` (9 passed) & `src/pages/setup/SetupWizardPackStep.test.tsx` (1 passed):**
   - Regular GSTIN required validation + telemetry emission (`signup`).
   - Draft first bill creation (`CW-PR-3`).
   - Resuming at saved `uiStep`, URL `?step=` override, fallback for unknown `?step=`, Hindi sample product creation & walk-in customer reuse, single `markOnboardingStarted` call, and skipping pack step.
4. **`src/pages/settings/PackWizardPage.test.tsx` (7 passed), `src/pages/settings/UsersInvites.test.tsx` (6 passed), `src/pages/AcceptInvitePage.test.tsx` (1 passed), `src/components/PasswordField.test.tsx` (4 passed), `src/onboarding/taxHints.test.ts` (3 passed):**
   - All passed with zero failures.

---

## 3. Why Existing Tests Missed the Newly Discovered Defects

Despite 223 passing onboarding/auth tests, our end-to-end trace across frontend state, API contracts, and backend derivation uncovered **5 P1 (High)** and **14 P2/P3** defects because of specific test boundary gaps:

1. **Mocked Boundary in `SetupWizardPage.test.tsx` (`ONB-CR-001`, `ONB-CR-004`, `ONB-CR-005`):**
   - `SetupWizardPage.test.tsx` mocks `updateCompany`, `createSalesInvoice`, and `getCompany`, and never navigates from Step 5's `"Go to Dashboard"` link to `<HomePage />` with a live `derive_onboarding(company)` payload. As a result, the test suite verified that Step 5 creates a `DRAFT` invoice (`CW-PR-3`), while `test_onboarding.py` verified that `derive_onboarding` requires a `COMPLETED` invoice (`SalesInvoice.Status.COMPLETED`), leaving the integration gap (infinite redirect loop back to `/setup`) undetected!
2. **Direct ORM Mutation in `test_onboarding.py:109` (`ONB-CR-002`):**
   - `test_composition_cannot_complete_gst_tax_invoice` set `company.registration_type = COMPOSITION` and `company.gstin = ""` directly via `company.save()`, bypassing `CompanySerializer.validate()`, which rejects blank GSTIN for `COMPOSITION` even though `SetupWizardPage.tsx` marks it optional!
3. **Incomplete Enrolment Flow in `LoginPage.mfa.test.tsx:110` (`ONB-CR-003`):**
   - The test `opens enrolment when the server requires it and does not show an error` stopped as soon as the heading `"Set up two-step verification"` rendered—it never checked for the QR code image (`setup.qrPng`) and never clicked `"Confirm and turn on"` -> `"I have saved them"`, where the login form completely disappears.
4. **Backend FTUE Test Used `negative_stock_policy="ALLOW"` (`ONB-CR-005`):**
   - `test_pj_ftue_founder_onboarding_stepper_and_error_recovery` explicitly passed `negative_stock_policy="ALLOW"` when creating the test company (`test_pj_ftue_onboarding_and_help.py:43`) AND manually posted `OPENING_STOCK` before completing the invoice, masking the fact that real companies default to `negative_stock_policy="BLOCK"` and sample products created in `SetupWizardPage.tsx` have `0` stock.

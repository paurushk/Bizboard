# Bizboard — End-to-End Onboarding Journey Test Matrix (`ONBOARDING_E2E_TEST_MATRIX.md`)

**Audit Date:** 2026-10-21  
**Scope:** Complete scenario matrix covering Happy Paths, Business Archetypes, Validation & Negative Cases, OTP/Verification, Session/Navigation/Resilience, Multi-User/Role/Tenant Isolation, Responsive/Accessibility, and Backward Compatibility.

---

## Category A — Happy Path Onboarding Journeys

| Test ID | Scenario | Persona / Role | Preconditions | Steps | Expected Result | Automated / Manual Status |
|---|---|---|---|---|---|---|
| `E2E-A01` | Brand-new Regular GST Owner full signup -> OTP -> Login -> 5-step Setup Wizard -> First Bill | `OWNER` (Regular GST) | Fresh email & phone; `ENABLE_SETUP_WIZARD=true` | 1. Request signup OTP on `/register`<br>2. Submit company, email, OTP, password, state (`Karnataka`), GSTIN (`29AABCU9603R1ZJ`)<br>3. Sign in on `/login`<br>4. Confirm `REGULAR` tax profile on `/setup?step=tax`<br>5. Save shop address on `shop`<br>6. Save bank & UPI on `payments`<br>7. Add first product + opening stock on `catalog`<br>8. Create first bill on `first_bill` and go to Dashboard | Account, Company, Default Warehouse, COA, and 14-day Trial created. Wizard progresses `tax -> shop -> payments -> catalog -> first_bill`. **Note:** Currently fails on "Go to Dashboard" due to `ONB-CR-001` (draft invoice leaves status `IN_PROGRESS`). | Backend covered (`test_pj_ftue_founder_onboarding_stepper_and_error_recovery`); UI defect `ONB-CR-001` confirmed |
| `E2E-A02` | Unregistered small shopkeeper signup -> Setup Wizard (skip payments, use sample products) -> Bill of Supply | `OWNER` (Unregistered Kirana) | Fresh email; no GSTIN | 1. Register without GSTIN<br>2. Sign in -> redirected to `/setup`<br>3. Select `UNREGISTERED` on `tax`<br>4. Enter shop address on `shop`<br>5. Click `Skip this optional step` on `payments`<br>6. Click `Add sample products` on `catalog`<br>7. Click `Create first bill` on `first_bill` | Tax step saves `UNREGISTERED` without GSTIN. Payments skipped cleanly. **Note:** Currently hits `ONB-CR-004` (stale `company.registrationType` creates `GST` invoice instead of `NON_GST`) and `ONB-CR-005` (sample product has 0 stock). | Unit tests partial; defects `ONB-CR-004` & `ONB-CR-005` confirmed |
| `E2E-A03` | Composition scheme dealer signup -> Setup Wizard | `OWNER` (Composition Dealer) | Fresh email | 1. Register and sign in<br>2. Select `COMPOSITION` on `/setup?step=tax`<br>3. Save tax profile with valid GSTIN (or blank GSTIN per UI helper) | **Defect `ONB-CR-002`:** UI says GSTIN is optional for Composition, but backend `CompanySerializer` returns 400 if GSTIN is blank. With valid 15-char GSTIN, saves `COMPOSITION` and blocks regular GST tax invoices (`assert_may_issue_gst_tax_invoice`). | Backend gate covered (`test_composition_cannot_complete_gst_tax_invoice`); UI/API mismatch `ONB-CR-002` confirmed |
| `E2E-A04` | Owner skips Setup Wizard (`Skip for now`) and completes onboarding via Dashboard `OnboardingChecklist` | `OWNER` | New company on `/setup` | 1. Click `Skip for now` on `/setup`<br>2. Land on `/` (`DashboardPage`)<br>3. Verify `onboarding.status === 'DISMISSED'` and `shouldForceSetup === false` | `PATCH /api/v1/company/ {dismiss_onboarding: true}` sets `onboarding_dismissed_at`, emits `wizard_completed`, and unlocks `/` permanently. | Automated (`test_owner_can_dismiss_onboarding`) — **PASS** |
| `E2E-A05` | Catalog setup via Bulk CSV Import and return to Setup Wizard | `OWNER` | On `/setup?step=catalog` | 1. Click `Import products by CSV`<br>2. Land on `/settings/import?kind=PRODUCTS&return=/setup?step=catalog`<br>3. Upload valid products CSV, preview, and commit<br>4. Click `Continue setup` | Products are imported into tenant catalog; clicking `Continue setup` navigates back to `/setup?step=catalog` showing `{count} product(s) ready for billing`. | Code verified (`ImportPage.tsx:100,455` + `SetupWizardPage.tsx:460`) — **PASS** |

---

## Category B — Business Archetype & Configuration Variations

| Test ID | Scenario | Archetype | Steps | Expected Result | Automated / Manual Status |
|---|---|---|---|---|---|
| `E2E-B01` | Retail Counter Pack (`how_you_sell: 'counter'`) | Retail Shop / Kirana | Preview & confirm pack in `/setup?step=pack` or `/settings/pack-wizard` | Proposes `retail` pack; enables `ENABLE_POS`, `ENABLE_GST_GUARD`, `ENABLE_GSTR`; skips unentitled dark modules. | Automated (`test_archetype_pack_follows_how_you_sell_and_skips_a_denied_flag`, `PackWizardPage.test.tsx`) — **PASS** (UI defect `ONB-CR-009` in `/setup?step=pack`) |
| `E2E-B02` | Wholesale & Trade Pack (`how_you_sell: 'field'`) | Wholesaler / Trader | Preview & confirm pack with `how_you_sell: 'field'` | Proposes `trade` pack; enables `ENABLE_CREDIT_CONTROL`, `ENABLE_ORDER_GATES`, `ENABLE_GST_GUARD`, `ENABLE_TDS`, `ENABLE_GSTR`; holds back `ENABLE_CRM`, `ENABLE_TALLY`, `ENABLE_ROUTE_OPTIMIZATION` on trial plan. | Automated (`test_trade_pack_does_not_turn_on_crm_when_the_plan_omits_it`, `test_pack_adds_four_flags_and_does_not_rewrite_a_hand_edit`) — **PASS** |
| `E2E-B03` | Sidebar Navigation Scope (`NAV_PACK_DEFAULT`) | New Signup Tenant | Register new company -> inspect `company.feature_flags` and `/api/v1/company/nav-scope/` | New signup sets `NAV_PACK_DEFAULT: True` so sidebar defaults to the focused archetype pack view; owner can toggle `Show all modules` via `NavScopeView`. | Automated (`test_settings_ai_and_packs.py`) — **PASS** |

---

## Category C — Validation and Negative Testing

| Test ID | Scenario | Target Field / Endpoint | Input Tested | Expected Result | Status |
|---|---|---|---|---|---|
| `E2E-C01` | Blank required fields on `/register` | `companyName`, `email`, `otpCode`, `password`, `state` | Empty strings | Client-side validation blocks submit and displays localized field errors (`en` & `hi`). | Automated (`RegisterPage.test.tsx`) — **PASS** |
| `E2E-C02` | Invalid Indian mobile numbers on `/register` & `/login` | `phone` (`PhoneNumberField`) | `98765` (too short), `1234567890` (starts with 1), `+91 098765 43210` (trunk 0) | Short/invalid prefixes rejected with `phoneField.invalidIndia`; trunk `0` normalized cleanly to `+919876543210`. | Automated (`RegisterPage.test.tsx`, `loginOtp.test.ts`, `test_auth.py`) — **PASS** |
| `E2E-C03` | Invalid GSTIN format & checksum | `gstin` (`/register`, `/setup`, `/settings/gst`) | `29INVALID`, wrong 15th check character | Client `isValidGstinFormat` blocks invalid pattern; backend `validate_gstin` & `CompanyVerifyGstinView` validate structure and checksum. | Automated (`taxHints.test.ts`, `test_onboarding.py`, `test_pj_ftue_onboarding_and_help.py`) — **PASS** |
| `E2E-C04` | GSTIN state code mismatch with selected `State` | `gstin` + `state` | `gstin="27AABCU9603R1ZM"` (Maharashtra) + `state="Karnataka"` | On `/register`: client shows warning (`gstinStateMismatch`) and `RegisterSerializer` returns 400. On `/setup`: **Defect `ONB-CR-007`** (no client warning or server check). | `/register` **PASS**; `/setup` defect `ONB-CR-007` confirmed |
| `E2E-C05` | Regular GST product without HSN/SAC code in Setup Wizard | `hsnCode` (`/setup?step=catalog`) | `registrationType='REGULAR'`, `gstRate=18`, `hsnCode=""` | Blocked client-side with `setup.errors.hsnRequired` (*"HSN / SAC is required for this Regular GST product"*). | Code verified (`SetupWizardPage.tsx:247`) — **PASS** |
| `E2E-C06` | Invalid IFSC, Pincode, and UPI ID on `PATCH /api/v1/company/` | `bank_ifsc`, `pincode`, `upi_id` | `ifsc="INVALID"`, `pincode="123"`, `upi_id="not-a-vpa"` | Rejected with HTTP 400 by `core.validators` (`validate_ifsc`, `validate_pincode`, `validate_upi_id`). | Automated (`test_company_settings_matrix.py`) — **PASS** |
| `E2E-C07` | Duplicate email vs duplicate phone on `/register` | `POST /api/v1/auth/register/` | 1. Existing email<br>2. New email + valid OTP + existing phone | 1. Existing email returns non-enumerating 200 OK.<br>2. **Defect `ONB-CR-006`:** New email + valid OTP + existing phone silently returns 200 OK without creating account! | Defect `ONB-CR-006` confirmed |

---

## Category D — OTP, Verification, and Password Flows

| Test ID | Scenario | Endpoint / Screen | Expected Result | Status |
|---|---|---|---|---|
| `E2E-D01` | Signup email OTP lifecycle (request, wrong code, expired code, 5-attempt lockout, replay) | `POST /auth/register/otp/request/` & `POST /auth/register/` | Wrong code increments `attempts` and returns 400; 5th failed attempt locks challenge (`MAX_OTP_ATTEMPTS = 5`); consumed OTP cannot be replayed. | Automated (`test_auth.py`) — **PASS** |
| `E2E-D02` | Login mobile OTP lifecycle (request, verify, unregistered phone anti-enumeration) | `POST /auth/otp/request/` & `POST /auth/otp/verify/` | Unregistered phone returns identical 200 `{detail: "If that number is registered..."}`; valid OTP issues session cookies (or MFA challenge if 2FA enabled). | Automated (`test_auth.py`) — **PASS** |
| `E2E-D03` | TOTP 2FA login & recovery code consumption | `POST /auth/mfa/verify/` (`SCR-04`) | Valid 6-digit TOTP or recovery code completes login; replayed TOTP step (`last_used_step`) or consumed recovery code is rejected with 401. | Automated (`test_mfa.py`, `test_mfa_edge_cases.py`, `LoginPage.mfa.test.tsx`) — **PASS** |
| `E2E-D04` | Forced 2FA enrolment on login for Money Roles (`OWNER`, `ACCOUNTANT`) | `SCR-05` (`/login` + `/auth/mfa/setup/` + `/auth/mfa/confirm/`) | Backend issues `enrol_token` (max 8 presentations, 10-min TTL) without session cookies. **Defect `ONB-CR-003`:** Frontend `LoginPage.tsx` omits QR code image and hides login form after recovery codes are saved. | Backend automated (`test_mfa.py`); Frontend defect `ONB-CR-003` confirmed |
| `E2E-D05` | Password reset request & confirmation invalidates prior sessions | `/forgot-password` -> `/reset-password` | Consumes `PasswordResetJti`, updates password, increments `User.token_version` so existing JWTs are immediately invalidated. | Automated (`test_auth.py`, `auth-recovery.spec.ts`) — **PASS** |

---

## Category E — Session, Navigation, and State Resilience

| Test ID | Scenario | Steps | Expected Result | Status |
|---|---|---|---|---|
| `E2E-E01` | Browser refresh mid-Setup Wizard (`/setup`) | Complete Step 1 (`tax`) and Step 2 (`shop`), then refresh browser on `/setup` | `SetupWizardPage` fetches `getCompany()`, reads `company.onboarding.uiStep` (`payments`), and resumes at Step 3 (`payments`) with saved fields populated. | Automated (`SetupWizardPage.test.tsx:129`) — **PASS** |
| `E2E-E02` | Direct URL step override (`/setup?step=payments`) vs unknown step (`/setup?step=nonsense`) | Navigate to `/setup?step=payments` and `/setup?step=nonsense` | Known `?step=` opens that step; unknown `?step=` falls back safely to `company.onboarding.uiStep` or `tax`. | Automated (`SetupWizardPage.test.tsx:135,147`) — **PASS** |
| `E2E-E03` | Logged-out deep link to protected routes (`/setup`, `/sales/new`, etc.) | Open protected route in unauthenticated browser context | Redirects cleanly to `/login` with `state.from` preserved; never triggers generic error boundary. | Automated (`route-smoke-unauthenticated.spec.ts`) — **PASS** |
| `E2E-E04` | Duplicate `markOnboardingStarted` prevention on `/setup` mount | Mount `SetupWizardPage` when `onboarding.started === false` | `startedRef` ensures `updateCompany({ markOnboardingStarted: true })` is called at most once. | Automated (`SetupWizardPage.test.tsx:206`) — **PASS** |

---

## Category F — Multi-User, Role, and Tenant Scenarios

| Test ID | Scenario | Role | Expected Result | Status |
|---|---|---|---|---|
| `E2E-F01` | Owner invites Sales Clerk, Godown Custodian, and Accountant; staff accept invite and land on workspace | `OWNER` -> `SALES`, `INVENTORY`, `ACCOUNTANT` | Invite email/link generated (`/invite?token=...`); accepting invite activates membership and lands `SALES`/`INVENTORY` on `LimitedAccessLanding` (`SCR-16`) with role welcome banner and `ACCOUNTANT` on `DashboardPage`. | Automated (`test_pj_ftue_team_invite_landing_and_role_access`, `UsersInvites.test.tsx`) — **PASS** |
| `E2E-F02` | Non-owner roles (`MANAGER`, `ACCOUNTANT`, `SALES`) are never redirected into `/setup` | `MANAGER`, `ACCOUNTANT`, `SALES` | `shouldForceSetup` returns `false` for all non-`OWNER` roles; direct navigation to `/setup` is blocked by `RoleRoute(['OWNER'])`. **Note:** `OnboardingChecklist` on `/` has defect `ONB-CR-010` for `MANAGER`/`ACCOUNTANT`/`AUDITOR`. | Guard verified; checklist defect `ONB-CR-010` confirmed |
| `E2E-F03` | Multi-company user switches active tenant via `CompanySwitcher` | Multi-company `OWNER` / `ACCOUNTANT` | `POST /api/v1/auth/switch-company/` updates `user.active_company` and `localStorage['bizboard:active-company-id']`, invalidating React Query caches. | Automated (`test_auth.py`, `test_audit_company_scope.py`) — **PASS** |
| `E2E-F04` | Existing user invited to a second company accepts invite while logged out | Multi-company user | Backend requires existing password (`AcceptInviteView`). **Defect `ONB-UX-004`:** Frontend prompts for "New password". | Backend automated (`test_settings_users.py`); UI defect `ONB-UX-004` confirmed |

---

## Category G — Accessibility & Bilingual (English / Hindi) Scenarios

| Test ID | Scenario | Viewport / Locale | Expected Result | Status |
|---|---|---|---|---|
| `E2E-G01` | Full Hindi (`hi`) validation & onboarding copy across `/register`, `/login`, `/setup` | Locale `hi` | All validation messages, step labels, and sample product names render in Hindi. **Defects found:** `ONB-UX-001` (`auth.demoHint` seed jargon) & `ONB-UX-005` (untranslated `Products` in sample warning). | Automated (`RegisterPage.test.tsx`, `LoginPage.mfa.test.tsx`, `SetupWizardPage.test.tsx`) + 2 copy defects confirmed |
| `E2E-G02` | Mobile 360×800 viewport layout across `/register`, `/login`, `/setup`, `/invite` | `360x800` | Auth cards fit cleanly; **Defect `ONB-UX-006`:** `<Stepper>` in `/setup` overflows horizontally when 5–6 steps are rendered without `overflowX: 'auto'`. | Defect `ONB-UX-006` confirmed |

---

## Category H — Existing User & Legacy Tenant Backward Compatibility

| Test ID | Scenario | Target | Expected Result | Status |
|---|---|---|---|---|
| `E2E-H01` | Migration `0028_onboarding_fields` backfill for existing tenants | Existing companies with address, products, or invoices | `backfill_onboarding` sets `onboarding_dismissed_at` or `onboarding_completed_at` so existing active tenants are **never** forced into `/setup`. | Automated (`test_backfill_dismisses_existing_progress_companies`) — **PASS** |
| `E2E-H02` | Existing company with completed invoice has `onboarding.status === 'COMPLETED'` | Existing tenant | `derive_onboarding` returns `status: "COMPLETED", activation_done: True, step: None`. | Automated (`test_derive_completed_when_completed_invoice_exists`) — **PASS** |

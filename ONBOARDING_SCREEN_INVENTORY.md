# Bizboard — Complete Onboarding Screen Inventory (`ONBOARDING_SCREEN_INVENTORY.md`)

**Audit Date:** 2026-10-21  
**Scope:** Every discovered page, wizard step, tab, modal, conditional surface, and role-based landing state in Bizboard's end-to-end onboarding journey.

---

## 1. Master Inventory Summary Table

| Screen ID | Screen Name | Route / Trigger | Component Path | Target Persona | Access Control |
|---|---|---|---|---|---|
| `SCR-01` | New Account & Company Registration | `/register` | `web/src/pages/RegisterPage.tsx` | Business Owner / Founder | Public (redirects to `/` if authenticated) |
| `SCR-02` | Sign In — Email & Password Tab | `/login` (`tab="password"`) | `web/src/pages/LoginPage.tsx` | All Users | Public |
| `SCR-03` | Sign In — Mobile OTP Tab | `/login` (`tab="otp"`) | `web/src/pages/LoginPage.tsx` | Users with registered mobile | Public |
| `SCR-04` | Sign In — Two-Step Verification (MFA Challenge) | `/login` (when `mfaToken` is active) | `web/src/pages/LoginPage.tsx` | Users with 2FA enabled | Public (requires signed `mfa_token`) |
| `SCR-05` | Sign In — Forced 2FA Enrolment & Recovery Codes | `/login` (when `enrolToken` or `enrolDone` is active) | `web/src/pages/LoginPage.tsx` | Money roles (`OWNER`, `ACCOUNTANT`, `can_post_journals`) when `MFA_ENFORCE_FOR_MONEY_ROLES=True` | Public (requires signed `enrol_token`) |
| `SCR-06` | Forgot Password Request | `/forgot-password` | `web/src/pages/ForgotPasswordPage.tsx` | All Users | Public |
| `SCR-07` | Reset Password Confirmation | `/reset-password?token=...` | `web/src/pages/ResetPasswordPage.tsx` | Users with reset link | Public (requires valid `token`) |
| `SCR-08` | Accept Team Invitation | `/invite?token=...` | `web/src/pages/AcceptInvitePage.tsx` | Invited Staff (`SALES`, `INVENTORY`, `ACCOUNTANT`, `MANAGER`, `AUDITOR`, `VIEWER`, `POLICY_DESK`) | Public (requires valid `InviteJti` token) |
| `SCR-09` | Setup Wizard — Step 1: Tax Profile | `/setup` (`?step=tax`) | `web/src/pages/setup/SetupWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-10` | Setup Wizard — Step 2: Shop Details | `/setup?step=shop` | `web/src/pages/setup/SetupWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-11` | Setup Wizard — Step 3: Payments (Bank & UPI) | `/setup?step=payments` | `web/src/pages/setup/SetupWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-12` | Setup Wizard — Step 4: Catalog (Product / Samples / CSV) | `/setup?step=catalog` | `web/src/pages/setup/SetupWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-13` | Setup Wizard — Step 5 (Conditional): Business Pack | `/setup?step=pack` (when `ENABLE_ARCHETYPE_PACKS` is on) | `web/src/pages/setup/SetupWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-14` | Setup Wizard — Final Step: First Bill & Completion Card | `/setup?step=first_bill` | `web/src/pages/setup/SetupWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-15` | Dashboard Onboarding Checklist & Post-Activation Invite Banner | `/` (`DashboardPage`) | `web/src/components/OnboardingChecklist.tsx` & `web/src/pages/DashboardPage.tsx` | `OWNER`, `MANAGER`, `ACCOUNTANT`, `AUDITOR` | `ProtectedRoute` |
| `SCR-16` | Limited Access Staff Welcome Landing | `/` (`LimitedAccessLanding`) | `web/src/pages/LimitedAccessLanding.tsx` | `SALES`, `INVENTORY`, `VIEWER`, `POLICY_DESK` | `ProtectedRoute` |
| `SCR-17` | Standalone Business Archetype Pack Wizard | `/settings/pack-wizard` | `web/src/pages/settings/PackWizardPage.tsx` | Owner | `ProtectedRoute` + `RoleRoute(['OWNER'])` |
| `SCR-18` | Settings Hub & Health Checklist | `/settings` | `web/src/pages/settings/SettingsHubPage.tsx` | Owner / Staff with Settings access | `ProtectedRoute` + `settingsRoute` |
| `SCR-19` | Company Profile Settings | `/settings/company` | `web/src/pages/settings/CompanySettingsPage.tsx` | Owner (write), Staff (read) | `ProtectedRoute` + `settingsRoute` |
| `SCR-20` | GST & Statutory Licences Settings | `/settings/gst` | `web/src/pages/settings/GstSettingsPage.tsx` | Owner | `ProtectedRoute` + `settingsRoute` |
| `SCR-21` | Bank Accounts & UPI Settings | `/settings/bank-accounts` | `web/src/pages/settings/BankAccountsPage.tsx` | Owner / Accountant | `ProtectedRoute` + `settingsRoute` |
| `SCR-22` | Users, Invites Modal & 2FA Settings Panel | `/settings/users` | `web/src/pages/settings/UsersSettingsPage.tsx` & `TwoStepVerificationPanel.tsx` | Owner (user management), All authenticated users (own 2FA panel) | `ProtectedRoute` + `settingsRoute` |
| `SCR-23` | Bulk CSV Import Wizard (Onboarding Return Flow) | `/settings/import?kind=PRODUCTS&return=/setup?step=catalog` | `web/src/pages/settings/ImportPage.tsx` | Owner / Manager / Inventory | `ProtectedRoute` + `settingsRoute` |
| `SCR-24` | Multi-Company Switcher & Staff Company Required Dialog | Global (`AppShell`) | `web/src/components/CompanySwitcher.tsx` & `CompanyRequiredDialog.tsx` | Multi-company users & staff users without `active_company` | `ProtectedRoute` |
| `SCR-25` | B2B Customer Onboarding Tracker (CRM Module) | `/crm/onboarding` | `web/src/pages/crm/CrmOnboardingPage.tsx` | CRM / Sales / Owner (`ENABLE_CRM`) | `ProtectedRoute` |

---

## 2. Detailed Screen-by-Screen Specifications

### `SCR-01` — New Account & Company Registration
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-01` |
| **Screen name** | Create your Bizboard account (`RegisterPage`) |
| **Route** | `/register` |
| **Entry condition** | Unauthenticated visitor clicks "Create account" on `/login` or navigates directly to `/register`. |
| **User objective** | Verify email ownership via 6-digit OTP and create a new company tenant + `OWNER` user account. |
| **Required fields** | `companyName` (non-empty), `email` (valid email format), `otpCode` (6 digits emailed to `email`), `password` (min 8 chars + Django password validators), `state` (Indian state/UT dropdown from `INDIAN_STATES`). |
| **Optional fields** | `fullName`, `phone` (validated via `PhoneNumberField`, normalized to `+91XXXXXXXXXX`), `gstin` (15-char GSTIN; validated client-side via `isValidGstinFormat` + state-prefix match warning via `gstinStateMismatch`). |
| **Actions** | `Send code` / `Resend code` (inline button inside Email field), `Create account` (submit), language toggle (`EN`/`हिं`), `Sign in` link to `/login`. |
| **Backend dependencies** | `POST /api/v1/auth/register/otp/request/`, `POST /api/v1/auth/register/`. |
| **Data affected** | Reads/updates `OtpChallenge(purpose='REGISTER')`; creates `Company`, `User`, `CompanyUser(role='OWNER')`, `CompanyGstin` (if GSTIN provided), `Warehouse(code='MAIN')`, default `Account` rows (Chart of Accounts), and 14-day `Subscription(status='TRIAL')`. |
| **Next states** | **Success:** Navigates to `/login?registered=1` (shows info alert on `LoginPage`). **Failure:** Inline field errors (`fieldErrors`) or top-level error `Alert`. |
| **Access control** | Public (`AllowAny`); rate-limited by `AuthBurstThrottle`, `OtpRequestEmailRateThrottle` (5/min/IP, 3/10min/email), and `RegisterRateThrottle` (10/hr/IP). |
| **Test coverage** | Covered by `web/src/pages/RegisterPage.test.tsx` and `backend/tests/test_auth.py`. **Missing:** Test for new email + valid OTP combined with an already-taken `phone` (silent 200 without creating account). |

---

### `SCR-02` — Sign In: Email & Password Tab
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-02` |
| **Screen name** | Sign in to Bizboard — Email & password (`LoginPage`) |
| **Route** | `/login` (with optional query params `?registered=1`, `?invited=1`, `?reset=1`) |
| **Entry condition** | User navigates to `/login`, is redirected from `ProtectedRoute`, or finishes `/register`, `/invite`, or `/reset-password`. |
| **User objective** | Authenticate with email and password to enter the workspace. |
| **Required fields** | `email` (valid email format), `password` (non-empty). |
| **Optional fields** | None. |
| **Actions** | `Sign in`, `Forgot password?` link (`/forgot-password`), `Create account` link (`/register`), switch to `Mobile OTP` tab, language toggle (`EN`/`हिं`). |
| **Backend dependencies** | `POST /api/v1/auth/login/`, followed by `GET /api/v1/auth/me/` and `GET /api/v1/feature-flags/`. |
| **Data affected** | Sets `bb_access` and `bb_refresh` `httpOnly` cookies; updates `User.last_login`; repairs `User.active_company` if null. |
| **Next states** | **Standard Success:** Redirects to `location.state.from` or `/` (`HomePage` -> `/setup` for un-onboarded `OWNER`). **2FA Enabled:** Transitions inline to `SCR-04` (`mfaToken`). **Enrolment Required:** Transitions inline to `SCR-05` (`enrolToken`). **Failure:** Error `Alert` (401 invalid credentials / 429 rate limit). |
| **Access control** | Public (`AllowAny`); rate-limited by `AuthBurstThrottle` and `LoginRateThrottle` (10/min/IP + 5 failed attempts per 15 min per email+IP). |
| **Test coverage** | Covered by `web/src/pages/LoginPage.mfa.test.tsx` and `backend/tests/test_auth.py`. |

---

### `SCR-03` — Sign In: Mobile OTP Tab
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-03` |
| **Screen name** | Sign in to Bizboard — Mobile OTP (`LoginPage`) |
| **Route** | `/login` (`tab="otp"`) |
| **Entry condition** | User clicks the `Mobile OTP` tab on `/login`. |
| **User objective** | Sign in passwordlessly using a 6-digit OTP sent to their registered mobile number. |
| **Required fields** | `phone` (validated via `PhoneNumberField`), `otp` (6 digits). |
| **Optional fields** | None. |
| **Actions** | `Send OTP` (`handleRequestOtp`), `Verify & sign in` (`handleOtpSubmit`). |
| **Backend dependencies** | `POST /api/v1/auth/otp/request/`, `POST /api/v1/auth/otp/verify/`. |
| **Data affected** | Creates/consumes `OtpChallenge(purpose='LOGIN')`; issues JWT cookies on verification. |
| **Next states** | Same as `SCR-02` (workspace redirect, `SCR-04` MFA challenge, or `SCR-05` forced MFA enrolment). |
| **Access control** | Public (`AllowAny`); rate-limited by `OtpRequestPhoneRateThrottle` and `OtpVerifyPhoneRateThrottle`. |
| **Test coverage** | Covered by `web/src/pages/loginOtp.test.ts`, `LoginPage.mfa.test.tsx`, and `backend/tests/test_auth.py`. |

---

### `SCR-04` — Sign In: Two-Step Verification (MFA Challenge)
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-04` |
| **Screen name** | Two-step verification (`LoginPage` when `mfaToken !== null`) |
| **Route** | `/login` (inline state transition) |
| **Entry condition** | `login()` or `verifyOtp()` throws `MfaRequiredError(mfaToken)`. |
| **User objective** | Provide a 6-digit TOTP authenticator code or a one-time recovery code to complete login. |
| **Required fields** | Either `mfaCode` (6-digit TOTP) OR `recoveryCode` (when `useRecovery` toggle is active). |
| **Optional fields** | None. |
| **Actions** | `Verify and sign in`, `Use a recovery code instead` / `Use the authenticator code instead`, `Back to sign in`. |
| **Backend dependencies** | `POST /api/v1/auth/mfa/verify/`. |
| **Data affected** | Updates `UserMfa.last_used_step` or consumes one recovery code hash from `UserMfa.recovery_hashes`; issues `bb_access` and `bb_refresh` cookies. |
| **Next states** | **Success:** Redirects to `from` or `/`. **Failure:** Shows `t('auth.mfa.invalid')` on 401. |
| **Access control** | Requires valid signed `mfa_token` (5-minute TTL). |
| **Test coverage** | Covered by `web/src/pages/LoginPage.mfa.test.tsx` and `backend/tests/test_mfa.py`. |

---

### `SCR-05` — Sign In: Forced 2FA Enrolment & Recovery Codes
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-05` |
| **Screen name** | Set up two-step verification (`LoginPage` when `enrolToken !== null` or `enrolDone === true`) |
| **Route** | `/login` (inline state transition or via `consumeEnrolToken()` after 401 refresh redirect) |
| **Entry condition** | `MFA_ENFORCE_FOR_MONEY_ROLES=True` and user has an active `OWNER`, `ACCOUNTANT`, or `can_post_journals=True` membership without confirmed `UserMfa`. |
| **User objective** | Scan/enter TOTP setup key into authenticator app, confirm with a 6-digit code, save 10 recovery codes, and sign in. |
| **Required fields** | `enrolCode` (6-digit TOTP code). |
| **Optional fields** | None. |
| **Actions** | `Confirm and turn on`, `Back to sign in`, `I have saved them` (after recovery codes are shown). |
| **Backend dependencies** | `POST /api/v1/auth/mfa/setup/` (with `enrol_token`), `POST /api/v1/auth/mfa/confirm/` (with `enrol_token` and `code`). |
| **Data affected** | Creates/updates `UserMfa(confirmed_at=now(), recovery_hashes=[...])`; burns `enrol_token` JTI in cache. |
| **Next states** | Intended to return user to sign-in form after clicking `I have saved them`. **Defect found:** Does not render `setup.qrPng` QR image, and after clicking `I have saved them`, `enrolDone` remains `true` while `enrolToken` is `null`, hiding the login form completely! |
| **Access control** | Requires valid signed `enrol_token` (10-minute TTL, max 8 presentations). |
| **Test coverage** | Partially covered in `LoginPage.mfa.test.tsx` (only tests initial render, not completion). |

---

### `SCR-06` & `SCR-07` — Password Recovery (`ForgotPasswordPage` & `ResetPasswordPage`)
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-06` (`/forgot-password`) & `SCR-07` (`/reset-password?token=...`) |
| **Entry condition** | User clicks `Forgot password?` on `/login` (`SCR-06`), then opens emailed link `/reset-password?token=...` (`SCR-07`). |
| **User objective** | Request a password reset link by email or mobile (`SCR-06`) and set a new password (`SCR-07`). |
| **Required fields** | `SCR-06`: `identifier` (email or mobile). `SCR-07`: `password` (min 8 chars), `confirmPassword` (must match). |
| **Actions** | `SCR-06`: `Send Reset Link`, `Back to Sign In`. `SCR-07`: `Update password`, `Request a new link` (if token missing/invalid). |
| **Backend dependencies** | `POST /api/v1/auth/password/reset/`, `POST /api/v1/auth/password/reset/confirm/`. |
| **Data affected** | Creates/consumes `PasswordResetJti`; updates `User.password` and increments `User.token_version` (invalidating all prior sessions). |
| **Next states** | Redirects to `/login?reset=1` after 800ms on success. |
| **Access control** | Public (`AllowAny`); rate-limited by `PasswordResetRequestThrottle` and `PasswordResetConfirmThrottle`. |
| **Test coverage** | Covered by `web/e2e/auth-recovery.spec.ts` and `backend/tests/test_auth.py`. |

---

### `SCR-08` — Accept Team Invitation (`AcceptInvitePage`)
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-08` |
| **Screen name** | Join your Bizboard team (`AcceptInvitePage`) |
| **Route** | `/invite` (`?token=...`) |
| **Entry condition** | Invited staff member opens `/invite?token=...` from invite email or WhatsApp/copied link shared by Owner. |
| **User objective** | Activate their `CompanyUser` membership and set (or confirm) their password. |
| **Required fields** | `token` (auto-filled from `?token=` or pasted manually if missing), `password` (min 8 chars). |
| **Optional fields** | None. |
| **Actions** | `Activate account`, `Sign in` link (`/login`). |
| **Backend dependencies** | `POST /api/v1/auth/invite/accept/`, followed by `GET /api/v1/auth/me/`. |
| **Data affected** | Marks `InviteJti.consumed_at = now()`, sets `CompanyUser.is_active = True`, sets `User.password` (if unusable) or verifies existing password, sets `User.active_company = membership.company`, and issues JWT cookies (unless `mfa_required` or `mfa_enrollment_required`). |
| **Next states** | **Standard:** Navigates to `/` (which renders `LimitedAccessLanding` with role welcome banner or `DashboardPage`). **If 2FA required/enrolment required:** Navigates to `/login?invited=1`. |
| **Access control** | Public (`AllowAny`), requires valid unconsumed `InviteJti` (7-day TTL). |
| **Test coverage** | Covered by `web/src/pages/AcceptInvitePage.test.tsx`, `backend/tests/test_settings_users.py`, and `backend/tests/personas/test_pj_ftue_onboarding_and_help.py`. |

---

### `SCR-09` to `SCR-14` — Owner Setup Wizard (`SetupWizardPage`)
| Step / Screen ID | Step Key | Required Inputs | Optional Inputs | Primary & Secondary Actions | Backend APIs Called | Data Modified |
|---|---|---|---|---|---|---|
| `SCR-09` (Step 1) | `tax` (Tax profile) | `registrationType` (`REGULAR` \| `COMPOSITION` \| `UNREGISTERED`); `gstin` (required in UI only when `REGULAR`, **but required by backend for both `REGULAR` and `COMPOSITION`!**) | `gstin` (hidden when `UNREGISTERED`) | `Save & continue`, `Skip for now` (header button) | `PATCH /api/v1/company/` (`registrationType`, `gstin`, `confirmTaxProfile: true`) | Updates `Company.registration_type`, `Company.gstin`, `Company.tax_profile_confirmed_at`; emits `wizard_tax_confirmed` |
| `SCR-10` (Step 2) | `shop` (Shop details) | `address` (Shop address) | `city`, `pincode` (6-digit PIN) | `Save & continue`, `Back`, `Skip for now` | `PATCH /api/v1/company/` (`address`, `city`, `pincode`) | Updates `Company.address`, `city`, `pincode`; emits `wizard_shop_saved` |
| `SCR-11` (Step 3) | `payments` (Payments) | None (entire step is optional) | `bankAccount`, `upiId` (**missing `bankName` and `bankIfsc` fields**) | `Save & continue`, `Skip this optional step`, `Back`, `Skip for now` | `PATCH /api/v1/company/` (`bankAccount`, `upiId`) | Encrypts `Company.bank_account`, updates `upi_id`, syncs `payments.BankAccount`; emits `wizard_payments_saved` or `wizard_payments_skipped` |
| `SCR-12` (Step 4) | `catalog` (Catalog) | At least 1 product in catalog (`productName`, `sellingPrice > 0`, `gstRate`, plus `hsnCode` if `REGULAR` and `gstRate > 0`) | `openingQty`, `Add sample products` button (creates 3 `SAMPLE-*` products), `Import products by CSV` link (`/settings/import?kind=PRODUCTS&return=/setup?step=catalog`), `Continue` (if products already exist) | `Add product & continue`, `Add sample products`, `Import products by CSV`, `Continue`, `Back` | `POST /api/v1/products/`, optional `POST /api/v1/inventory/opening-stock/` | Creates `Product` row(s) and optional `StockMovement(OPENING_STOCK)` |
| `SCR-13` (Step 5, if `ENABLE_ARCHETYPE_PACKS`) | `pack` (Business pack) | None (can skip) | `what_you_sell`, `how_you_sell`, `deliver`, `gst_registered` | `See pack` (`proposePack`) -> `Apply pack` (`confirmPack`), `Continue without a pack`, `Back` | `POST /api/v1/company/pack-wizard/` (`action: 'propose'` / `'confirm'`), `GET /api/v1/feature-flags/` | Creates/updates `CompanyPackState` and `Company.feature_flags` |
| `SCR-14` (Final Step) | `first_bill` (First bill) | Requires `products.length >= 1` | None | `Create first bill`, `Back`, `Skip for now`; after creation: `Review & Finalize Bill` (`/sales/history/{id}/edit`) and `Go to Dashboard` (`/`) | `GET /api/v1/customers/`, optional `POST /api/v1/customers/` (Walk-in Customer), `POST /api/v1/sales/invoices/` (creates **DRAFT** invoice) | Creates `Customer` (if absent) and `SalesInvoice(status='DRAFT')` (**Defect:** does not complete invoice or dismiss onboarding, causing redirect loop on `/`) |

---

### `SCR-15` — Dashboard Onboarding Checklist & Post-Activation Invite Banner
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-15` |
| **Screen name** | Getting Started with Bizboard (`OnboardingChecklist` inside `DashboardPage`) |
| **Route** | `/` (when `shouldForceSetup` is `false`, e.g., when `VITE_ENABLE_SETUP_WIZARD=false` or user is `MANAGER`/`ACCOUNTANT`/`AUDITOR`) |
| **Entry condition** | User lands on `DashboardPage` while `onboarding.status !== 'COMPLETED' && onboarding.status !== 'DISMISSED'`. Once `onboarding.status === 'COMPLETED'`, `DashboardPage` shows the post-activation `Invite staff` alert (`bb_invite_nudge_dismissed`). |
| **User objective** | Track completion of the 4 core setup milestones (`Shop Details & GSTIN`, `Bank Account & UPI QR`, `Add Products & Stock`, `Create Your First Bill`) or dismiss the guide. |
| **Actions** | Step CTA buttons (`/setup?step=...` when wizard enabled, or `/settings/company`, `/settings/bank-accounts`, `/products`, `/sales/pos`), `Dismiss guide` (`X` button -> `PATCH /api/v1/company/ {dismissOnboarding: true}`), and post-completion `Invite staff` button (`/settings/users`). |
| **Backend dependencies** | `GET /api/v1/company/`, `GET /api/v1/products/`, `GET /api/v1/sales/invoices/`, `PATCH /api/v1/company/`. |
| **Access control** | Visible to dashboard roles (`OWNER`, `MANAGER`, `ACCOUNTANT`, `AUDITOR`). **Defect found:** Non-owner dashboard roles (`MANAGER`, `ACCOUNTANT`, `AUDITOR`) see the `Dismiss guide` button and owner-only settings links, which fail with HTTP 403 when clicked! |

---

### `SCR-16` — Limited Access Staff Welcome Landing (`LimitedAccessLanding`)
| Field | Specification |
|---|---|
| **Screen ID** | `SCR-16` |
| **Screen name** | Welcome to Bizboard (`LimitedAccessLanding`) |
| **Route** | `/` (for `SALES`, `INVENTORY`, `VIEWER`, `POLICY_DESK`, or when a module route is disabled) |
| **Entry condition** | Non-dashboard staff logs in or accepts an invite and lands on `/`. |
| **User objective** | Understand their assigned role and navigate to their primary allowed workspace (e.g., `/sales/pos`, `/inventory`, `/insurance/policies`). |
| **Actions** | `Go to your workspace` primary CTA, module cards for all allowed routes, dismissible first-visit welcome alert (`localStorage['bb_role_welcome']`). |
| **Backend dependencies** | Uses `useAuth().user` and runtime feature flags (no extra API call). |
| **Access control** | Authenticated users (`ProtectedRoute`). |

---

### `SCR-17` to `SCR-25` — Secondary & Post-Signup Onboarding Surfaces
- **`SCR-17` (`/settings/pack-wizard` — `PackWizardPage`):** Full-featured archetype pack selector with 4 questions (`what_you_sell`, `how_you_sell`, `deliver`, `gst_registered`), explicit preview gate (`POST /api/v1/company/pack-wizard/ {action: 'propose'}`), 4-group module breakdown (`turnsOn`, `alreadyOn`, `staysOff`, `notInPlan`), and confirmation (`{action: 'confirm'}`).
- **`SCR-18` (`/settings` — `SettingsHubPage`):** Displays server-computed `GET /api/v1/company/settings-health/` chips (`TODO` / `WARN` / `OK`) for GSTIN, Tax Profile confirmation, Bank Account, Statutory Licences, Payment Gateway, and Pending/Expired Staff Invites.
- **`SCR-19` (`/settings/company` — `CompanySettingsPage`) & `SCR-20` (`/settings/gst` — `GstSettingsPage`):** Full post-wizard configuration for legal name, shop address, state, negative stock policy, GST registration type, GSTIN checksum verification (`POST /api/v1/company/verify-gstin/`), additional branch GSTINs (`CompanyGstin`), and statutory licences (`CompanyStatutoryLicence`: Drug licence, FSSAI, Shop & Establishment, Trade licence).
- **`SCR-21` (`/settings/bank-accounts` — `BankAccountsPage`):** Full bank account & UPI QR management (`payments.BankAccount`), supporting IFSC validation, account masking/encryption, and `print_on_invoices` selection.
- **`SCR-22` (`/settings/users` — `UsersSettingsPage` + `TwoStepVerificationPanel`):** Allows Owner to invite team members by email + role + granular permissions (`canViewReports`, `canPostJournals`, `canManageInventory`, `canApproveCredit`), copy/resend/cancel pending invite links, and allows any user to set up TOTP 2FA with QR code (`setup.qrPng`) and recovery codes.
- **`SCR-23` (`/settings/import` — `ImportPage`):** 3-step CSV import (`Download template` -> `Validate & Preview` -> `Commit import`). When entered from Setup Wizard (`/settings/import?kind=PRODUCTS&return=/setup?step=catalog`), displays a `Continue setup` button after commit to return to `/setup?step=catalog`.
- **`SCR-24` (`CompanySwitcher` & `CompanyRequiredDialog`):** Header company selector (`GET /api/v1/auth/memberships/`, `POST /api/v1/auth/switch-company/`) and blocking modal for staff users who have not yet selected an active tenant.
- **`SCR-25` (`/crm/onboarding` — `CrmOnboardingPage`):** Internal B2B customer onboarding checklist tracker (`GET /api/v1/crm/onboarding/`, `POST /api/v1/crm/onboarding/{id}/complete-step/`) for won CRM opportunities.

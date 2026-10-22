# Bizboard — Screen-by-Screen UI/UX, Indian Business Usability & Accessibility Audit (`ONBOARDING_UI_UX_AUDIT.md`)

**Audit Date:** 2026-10-21  
**Evaluation Frameworks:** Nielsen's 10 Usability Heuristics, Cognitive Load Theory, WCAG 2.1 AA Accessibility Standards, Mobile/Desktop Responsive Ergonomics, and Indian SMB Domain Suitability (Kirana, Retail, Wholesale, Trader, Distributor, Workshop, Manufacturer).

---

## 1. Executive Summary of UI/UX & Accessibility Findings

| Finding ID | Severity | Category | Title | Affected Screen / Route |
|---|---|---|---|---|
| `ONB-UX-001` | **P2 (Medium)** | UX / Indian SMB Copy | Hindi login page (`auth.demoHint`) leaks developer jargon ("सीड किया हुआ मालिक खाता उपयोग करें" / "Use the seeded owner account") to end users | `SCR-02`, `SCR-03` (`/login` in Hindi) |
| `ONB-UX-002` | **P2 (Medium)** | UX / Cognitive Load | `RegisterPage` requires users to request and enter a 6-digit email OTP inside a single crowded 8-field form without resend cooldown feedback or step separation | `SCR-01` (`/register`) |
| `ONB-UX-003` | **P2 (Medium)** | UX / Copy & Expectation Mismatch | `SetupWizardPage` header & Step 5 copy promise "Five focused steps to your first completed bill" even when 6 steps are shown (`ENABLE_ARCHETYPE_PACKS`) and even though Step 5 only creates a **draft** bill | `SCR-09`–`SCR-14` (`/setup`) |
| `ONB-UX-004` | **P2 (Medium)** | UX / Existing User Invite Flow | `AcceptInvitePage` always labels the password input "New password" and says "Choose a password to activate...", misleading existing Bizboard users invited to a second company who must enter their **existing** password | `SCR-08` (`/invite`) |
| `ONB-UX-005` | **P2 (Medium)** | UX / Dialog Ergonomics | `SetupWizardPage` Step 4 (`Add sample products`) uses a blocking browser `window.confirm(...)` dialog instead of an accessible MUI `Dialog` and leaves untranslated `"Products"` in Hindi copy | `SCR-12` (`/setup?step=catalog`) |
| `ONB-UX-006` | **P2 (Medium)** | Accessibility (WCAG 2.1 AA) | `SetupWizardPage` Stepper fails to announce step changes to screen readers (missing focus management / `aria-current="step"` live region announcement on step transition) and uses horizontal `Stepper` that overflows on 360px mobile screens when 6 steps are active | `SCR-09`–`SCR-14` (`/setup` at 360px mobile viewport) |
| `ONB-UX-007` | **P3 (Low)** | UX / Indian SMB Guidance | `SetupWizardPage` Step 1 (`tax`) does not allow correcting the `State` selected during registration (`State: {state} (set during registration)` is static text with no edit link) | `SCR-09` (`/setup?step=tax`) |
| `ONB-UX-008` | **P3 (Low)** | Accessibility / Form Semantics | `AcceptInvitePage` password input uses a plain `<TextField type="password">` instead of the shared `<PasswordField>` component, depriving invited staff of the show/hide password toggle | `SCR-08` (`/invite`) |

---

## 2. Screen-by-Screen Heuristic & Responsive Evaluation

### 2.1 `SCR-01` — Registration Screen (`/register` — `RegisterPage.tsx`)
- **Strengths:**
  - Clean centered card (`maxWidth: 460`) with immediate `EN`/`हिं` language switcher in the header.
  - `State` dropdown includes all 36 Indian States and Union Territories (`INDIAN_STATES`) with clear helper text explaining **why** state is needed (*"Required to calculate CGST/SGST vs IGST automatically on your bills"*).
  - Real-time client-side GSTIN format check (`isValidGstinFormat`) and state-prefix mismatch warning (`gstinStateMismatch`) prevent common Indian GST entry mistakes before form submission.
  - `PhoneNumberField` automatically normalizes Indian 10-digit mobile numbers, strips trunk `0` (`098765 43210` -> `+919876543210`), and displays `+91` country code clearly.
- **Usability & Accessibility Gaps:**
  - **Cognitive load (`ONB-UX-002`):** All 8 inputs (`Company name`, `Full name`, `Email` + inline `Send code` button, `Verification code`, `Mobile number`, `Password`, `State`, `GSTIN`) are presented simultaneously. Non-technical users often fill the entire form and click `Create account` without noticing the small inline `Send code` button inside the `Email` field, triggering the validation error *"Enter the 6-digit code we emailed you"*.
  - **No resend timer:** After clicking `Send code`, the button switches immediately to `Resend code` with no 30-second countdown timer, making it easy for users on slow connections to click `Resend code` repeatedly and hit the 3-per-10-minute email rate limit (`OtpRequestEmailRateThrottle`).

### 2.2 `SCR-02` to `SCR-05` — Login, Mobile OTP & 2FA Screens (`/login` — `LoginPage.tsx`)
- **Strengths:**
  - Clear `Tabs` switching between **Email & password** and **Mobile OTP**.
  - Contextual arrival banners (`?registered=1`, `?invited=1`, `?reset=1`) provide positive feedback after registration, invitation acceptance, or password reset.
  - `PasswordField` provides an accessible show/hide password toggle (`aria-label`) that does not accidentally submit the form.
- **Usability & Accessibility Gaps:**
  - **Developer copy leak in Hindi (`ONB-UX-001`):** `hi.ts:540` renders *"सीड किया हुआ मालिक खाता उपयोग करें, या नई कंपनी पंजीकृत करें।"* ("Use the seeded owner account...").
  - **Broken Forced 2FA Enrolment (`ONB-CR-003`):** Missing QR code image (`setup.qrPng`) and dead-end blank state after acknowledging recovery codes.

### 2.3 `SCR-06` & `SCR-07` — Password Recovery (`/forgot-password`, `/reset-password`)
- **Strengths:**
  - Accepts either Email or Mobile number (`identifier`), with helpful staff guidance (`forgotPasswordStaffHint`: *"Staff: ask your company owner to send a new invite if you do not have a reset link"*).
  - Non-enumerating confirmation state with clear `Return to Login` CTA.
  - Missing or expired reset token displays a clear recovery state with a `Request a new link` button leading back to `/forgot-password`.

### 2.4 `SCR-08` — Accept Team Invitation (`/invite` — `AcceptInvitePage.tsx`)
- **Strengths:**
  - Automatically reads `?token=` from URL and hides the raw token field unless the token is missing from the URL.
  - Automatically logs in new staff upon acceptance and lands them on their role-appropriate workspace (`LimitedAccessLanding` or `DashboardPage`).
- **Usability & Accessibility Gaps:**
  - **Misleading copy for existing users (`ONB-UX-004`):** When an accountant or staff member who already belongs to Company A is invited to Company B, backend `AcceptInviteView` requires their **existing** account password (`views.py:1254-1261`). However, `AcceptInvitePage` labels the field `New password` and instructs *"Choose a password to activate the account your company invited"*. If the user types a new password, `user.check_password(password)` fails with HTTP 400 *"Incorrect password for this existing account. Sign in first or use Forgot password."*
  - **Missing show/hide toggle (`ONB-UX-008`):** Uses `<TextField type="password">` instead of `<PasswordField>`.

### 2.5 `SCR-09` to `SCR-14` — Owner Setup Wizard (`/setup` — `SetupWizardPage.tsx`)
- **Strengths:**
  - Contextual `PreventionNote` help cards (`intent="add-gstin"`, `"complete-invoice"`, `"fix-stock-block"`) educate Indian business owners on why each setting matters.
  - Supports 3 distinct catalog onboarding paths in Step 4: manual 1-item entry, 1-click sample products (`SAMPLE-*`), or full CSV import (`/settings/import?kind=PRODUCTS&return=/setup?step=catalog`) with seamless return navigation.
  - Always offers a visible `Skip for now` escape hatch in the header so an urgent counter sale is never blocked.
- **Usability & Accessibility Gaps:**
  - **Mobile horizontal overflow on Stepper (`ONB-UX-006`):** `<Stepper activeStep={stepIndex} sx={{ mb: 3 }}>` renders 5 or 6 horizontal labels (`Tax profile`, `Shop details`, `Payments`, `Catalog`, `Business pack`, `First bill`) without `alternativeLabel` or responsive scroll/collapse, causing horizontal overflow on 360px–390px mobile viewports.
  - **Inaccurate subtitle and Step 5 copy (`ONB-UX-003`):** Subtitle hardcodes *"Five focused steps to your first completed bill"* even when 6 steps are active (`Step 1 of 6`), and Step 5 description says *"Create a completed bill..."* when it actually creates a **draft** bill.
  - **Static uneditable State on Step 1 (`ONB-UX-007`):** Displays `State: Karnataka (set during registration)` as plain text with no way to change it if the user picked the wrong state during sign-up.
  - **Missing Bank Name & IFSC on Step 3 (`ONB-CR-008`):** Indian merchants expect `Bank Name` and `IFSC Code` alongside `Bank Account Number`.

### 2.6 `SCR-15` & `SCR-16` — First-Login Landing (`DashboardPage`, `OnboardingChecklist`, `LimitedAccessLanding`)
- **Strengths:**
  - `OnboardingChecklist` provides a clear `LinearProgress` bar (`0%`–`100%`) and 4 actionable cards with green completion checkmarks (`CheckCircleIcon`).
  - Once `onboarding.status === 'COMPLETED'`, `DashboardPage` transitions smoothly from the setup checklist to a dismissible `Invite staff` nudge banner.
  - `LimitedAccessLanding` prevents invited cashiers (`SALES`) and godown staff (`INVENTORY`) from seeing 403 errors on owner KPIs, greeting them with a role welcome banner (`bb_role_welcome`) and direct cards to their allowed modules.

---

## 3. Detailed UI/UX & Accessibility Findings (Mandatory 17-Field Format)

### `ONB-UX-001` — Hindi Login Screen Leaks Developer "Seeded Owner Account" Terminology
- **Finding ID:** `ONB-UX-001`
- **Title:** Hindi login page (`auth.demoHint`) leaks developer jargon ("सीड किया हुआ मालिक खाता उपयोग करें" / "Use the seeded owner account") to end users
- **Severity:** **P2 (Medium)**
- **Category:** UX / Indian SMB Copy
- **Affected screen / route:** `SCR-02`, `SCR-03` (`/login` when locale is `hi`)
- **Affected file / component / API / model:**
  - `web/src/i18n/hi.ts` (line 540: `demoHint: 'सीड किया हुआ मालिक खाता उपयोग करें, या नई कंपनी पंजीकृत करें।'`)
  - `web/src/pages/LoginPage.tsx` (line 205: `<Typography variant="body2" color="text.secondary">{t('auth.demoHint')}</Typography>`)
- **Preconditions:**
  - User switches language to Hindi (`हिं`) on `/login`.
- **Reproduction steps:**
  1. Open `/login` and click **हिं** in the top-right corner.
  2. Read the subtitle directly below the "बिज़बोर्ड में साइन इन करें" heading.
- **Expected behavior:**
  - Hindi subtitle should match the production English copy (`en.ts:543`: *"Sign in with your company email, or create a new company."*, e.g., *"अपनी कंपनी के ईमेल से साइन इन करें, या नई कंपनी बनाएँ।"*).
- **Actual behavior:**
  - Displays *"सीड किया हुआ मालिक खाता उपयोग करें, या नई कंपनी पंजीकृत करें।"* ("Use the seeded owner account, or register a new company"), which is incomprehensible developer jargon ("सीड किया हुआ" = database-seeded) for Indian shopkeepers.
- **Evidence / test status:**
  - Confirmed in `web/src/i18n/hi.ts:540` vs `web/src/i18n/en.ts:543`.
- **Root cause:**
  - When `en.ts:543` (`auth.demoHint`) was cleaned up for production to remove the "seeded owner account" text, `hi.ts:540` was not updated.
- **Impact:**
  - Confuses Hindi-speaking business users at their very first touchpoint with the product and undermines trust.
- **Recommended correction:**
  - Update `auth.demoHint` in `web/src/i18n/hi.ts` to `'अपनी कंपनी के ईमेल से साइन इन करें, या नई कंपनी बनाएँ।'`.
- **Regression tests required:**
  - Add assertion in `LoginPage.mfa.test.tsx` (Hindi suite) that `auth.demoHint` does not contain `'सीड'`.
- **Acceptance criteria:**
  - Hindi login subtitle uses natural business Hindi matching the English prompt.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-002` — Crowded Single-Step Registration Form Without OTP Resend Cooldown Timer
- **Finding ID:** `ONB-UX-002`
- **Title:** `RegisterPage` requires users to request and enter a 6-digit email OTP inside a single crowded 8-field form without resend cooldown feedback
- **Severity:** **P2 (Medium)**
- **Category:** UX / Cognitive Load
- **Affected screen / route:** `SCR-01` (`/register`)
- **Affected file / component / API / model:**
  - `web/src/pages/RegisterPage.tsx` (lines 110–131, 224–266)
- **Preconditions:**
  - New user opens `/register`.
- **Reproduction steps:**
  1. Open `/register`.
  2. Enter `Email` and click `Send code`.
  3. Observe that the button immediately changes to `Resend code` with no countdown timer, while the user must also fill 7 other fields on the same screen.
- **Expected behavior:**
  - After sending the verification code, a cooldown timer (e.g., 30s) or clear helper state prevents accidental double-clicks that exhaust the strict 3-emails-per-10-minutes throttle (`OtpRequestEmailRateThrottle`).
- **Actual behavior:**
  - No cooldown timer is shown on `Resend code`, and if the user changes the `email` input after requesting a code, `codeSentTo` still shows the old email in the success alert until they click `Resend code`.
- **Evidence / test status:**
  - Confirmed in `web/src/pages/RegisterPage.tsx:110-131,224-266`.
- **Root cause:**
  - `RegisterPage.tsx` only tracks `sendingCode` (in-flight request) and `codeSentTo`, without a resend cooldown or clearing `codeSentTo` when `email` is edited.
- **Impact:**
  - Users on slower email providers click `Resend code` 3 times within a minute, hit HTTP 429 rate limiting, and get locked out of registration for 10 minutes.
- **Recommended correction:**
  - Add a 30-second resend cooldown timer on the `Resend code` button and reset `codeSentTo` if the user edits `email` to a different address.
- **Regression tests required:**
  - Unit test in `RegisterPage.test.tsx` verifying `Send code` / `Resend code` state behavior.
- **Acceptance criteria:**
  - `Resend code` shows a cooldown or prevents rapid duplicate clicks, and editing `email` clears stale `codeSentTo` messaging.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-003` — Setup Wizard Subtitle & Step 5 Description Contradict Actual Step Count and Draft Bill Behavior
- **Finding ID:** `ONB-UX-003`
- **Title:** `SetupWizardPage` header & Step 5 copy promise "Five focused steps to your first completed bill" even when 6 steps are shown (`ENABLE_ARCHETYPE_PACKS`) and even though Step 5 only creates a **draft** bill
- **Severity:** **P2 (Medium)**
- **Category:** UX / Copy & Expectation Mismatch
- **Affected screen / route:** `SCR-09`–`SCR-14` (`/setup`)
- **Affected file / component / API / model:**
  - `web/src/i18n/en.ts` (lines 2208, 2263) & `web/src/i18n/hi.ts` (lines 1815, 1870)
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 382–384, 495–520)
- **Preconditions:**
  - Owner opens `/setup`.
- **Reproduction steps:**
  1. Open `/setup` when `ENABLE_ARCHETYPE_PACKS` is enabled: the chip says `Step 1 of 6`, while the subtitle immediately next to it says `"Five focused steps to your first completed bill."`
  2. Advance to the final step (`first_bill`): the description says `"Create a completed bill with your first product and a walk-in customer."`
  3. Click **Create first bill**: the alert says `"Your First Invoice Draft is Ready"` (`setup.draftCreatedTitle`).
- **Expected behavior:**
  - Subtitle should not hardcode "Five" when 5 or 6 steps are possible (or should interpolate `{total}` / say *"Quick guided steps to set up your business and create your first bill"*), and Step 5's description should accurately state that it prepares your first bill draft for review.
- **Actual behavior:**
  - Hardcoded "Five focused steps" contradicts `Step 1 of 6`, and "Create a completed bill" contradicts "Your First Invoice Draft is Ready".
- **Evidence / test status:**
  - Confirmed in `web/src/i18n/en.ts:2208,2244,2263` and `web/src/i18n/hi.ts:1815,1851,1870`.
- **Root cause:**
  - Copy in `en.ts` and `hi.ts` was not updated when the 6th step (`pack`) was added and when `CW-PR-3` changed Step 5 from completing an invoice to creating a draft.
- **Impact:**
  - Confuses users about how many steps remain and whether their first bill has actually been finalized or is only a draft.
- **Recommended correction:**
  - Update `setup.subtitle` and `setup.descriptions.first_bill` in `en.ts` and `hi.ts` to accurately reflect the guided setup and draft bill creation.
- **Regression tests required:**
  - Verify `SetupWizardPage.test.tsx` and `SetupWizardPackStep.test.tsx` pass with updated copy.
- **Acceptance criteria:**
  - Setup Wizard subtitle and `first_bill` description are consistent across 5-step and 6-step modes and match the draft-creation behavior.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-004` — `AcceptInvitePage` Misleads Existing Multi-Company Users Into Entering a New Password
- **Finding ID:** `ONB-UX-004`
- **Title:** `AcceptInvitePage` always labels the password input "New password" and says "Choose a password to activate...", misleading existing Bizboard users invited to a second company who must enter their **existing** password
- **Severity:** **P2 (Medium)**
- **Category:** UX / Existing User Invite Flow
- **Affected screen / route:** `SCR-08` (`/invite`)
- **Affected file / component / API / model:**
  - `web/src/pages/AcceptInvitePage.tsx` (lines 58–94)
  - `web/src/i18n/en.ts` (lines 2331–2339) & `web/src/i18n/hi.ts` (lines 1938–1946)
  - `backend/accounts/views.py` (`AcceptInviteView.post`, lines 1252–1264)
- **Preconditions:**
  - An accountant or manager who already has a Bizboard account in Company A is invited to Company B (`user.has_usable_password()` is `True`).
- **Reproduction steps:**
  1. Open `/invite?token=...` while logged out.
  2. Read the prompt: *"Choose a password to activate the account your company invited"* and the field label *"New password"*.
  3. Type a new password and click **Activate account**.
- **Expected behavior:**
  - Either the UI should clarify that new users choose a password while existing Bizboard users should enter their current password (or sign in first), and use `<PasswordField>` so they can verify what they typed.
- **Actual behavior:**
  - The user invents a new password as instructed by *"New password"*, and the server rejects it with HTTP 400: `"Incorrect password for this existing account. Sign in first or use Forgot password."`
- **Evidence / test status:**
  - Confirmed in `AcceptInvitePage.tsx:61,86` and `backend/accounts/views.py:1254-1261`.
- **Root cause:**
  - `AcceptInvitePage` copy assumes every invited user is a brand-new user without an existing password.
- **Impact:**
  - External CAs/Accountants (Persona P5, who commonly serve multiple Bizboard companies) fail invite activation on their second client company.
- **Recommended correction:**
  - Update `invite.description` and `invite.passwordHint` in `en.ts`/`hi.ts` to note that existing Bizboard users should enter their current password, and replace `<TextField type="password">` with `<PasswordField>`.
- **Regression tests required:**
  - Unit test in `AcceptInvitePage.test.tsx` verifying `<PasswordField>` and updated helper copy.
- **Acceptance criteria:**
  - Invited users can toggle password visibility and understand whether to enter a new or existing password.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-005` — Native `window.confirm` and Untranslated `"Products"` in Hindi Sample Catalog Flow
- **Finding ID:** `ONB-UX-005`
- **Title:** `SetupWizardPage` Step 4 (`Add sample products`) uses a blocking browser `window.confirm(...)` dialog and leaves untranslated `"Products"` in Hindi copy
- **Severity:** **P2 (Medium)**
- **Category:** UX / Dialog Ergonomics & Localization
- **Affected screen / route:** `SCR-12` (`/setup?step=catalog`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (line 268: `if (!window.confirm(t('setup.addSamplesConfirm'))) return;`)
  - `web/src/i18n/hi.ts` (lines 1843, 1845)
- **Preconditions:**
  - Owner is on `/setup?step=catalog` in Hindi (`hi`) or mobile webview.
- **Reproduction steps:**
  1. Switch locale to Hindi (`हिं`) and navigate to `/setup?step=catalog`.
  2. Read the warning alert and click **नमूना उत्पाद जोड़ें** (`Add sample products`).
- **Expected behavior:**
  - Hindi text should refer to `उत्पाद (Products)` consistently with the Hindi sidebar navigation, and confirmation should be clear.
- **Actual behavior:**
  - Lines 1843 & 1845 in `hi.ts` use the raw English word `Products` (*"अपने उत्पाद जोड़ने के बाद इन्हें Products से हटा दें"*), even though the Hindi navigation menu calls that page `उत्पाद`.
- **Evidence / test status:**
  - Confirmed in `web/src/i18n/hi.ts:1843,1845`.
- **Root cause:**
  - Partial translation in `hi.ts`.
- **Impact:**
  - Hindi users looking for "Products" in the sidebar only see "उत्पाद" (`nav.products`).
- **Recommended correction:**
  - Update `hi.ts:1843,1845` to reference `उत्पाद (Products)`.
- **Regression tests required:**
  - Verify `SetupWizardPage.test.tsx` Hindi sample test passes.
- **Acceptance criteria:**
  - Hindi sample warning and confirmation strings match the Hindi navigation label.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-006` — Setup Wizard Stepper Overflows Horizontally on 360px Mobile Screens and Lacks Screen-Reader Step Announcements
- **Finding ID:** `ONB-UX-006`
- **Title:** `SetupWizardPage` Stepper overflows horizontally on 360px mobile viewports when 5–6 steps are rendered and does not manage focus or `aria-live` on step transitions
- **Severity:** **P2 (Medium)**
- **Category:** Accessibility (WCAG 2.1 AA) & Mobile Responsiveness
- **Affected screen / route:** `SCR-09`–`SCR-14` (`/setup` at 360px mobile viewport)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 386–393)
- **Preconditions:**
  - Open `/setup` on a 360×800 mobile viewport (or with a screen reader).
- **Reproduction steps:**
  1. Set viewport to 360×800 and open `/setup`.
  2. Inspect the horizontal `<Stepper activeStep={stepIndex}>` with 5 or 6 `<StepLabel>` elements.
  3. Click **Save & continue** to move from Step 1 to Step 2.
- **Expected behavior:**
  - On narrow mobile viewports (`xs`), the Stepper should wrap, scroll horizontally (`overflowX: 'auto'`), or use `alternativeLabel` so it never causes horizontal page overflow.
  - When `activeStep` changes, screen readers should be informed of the new step heading via `aria-live="polite"` or heading focus.
- **Actual behavior:**
  - `<Stepper activeStep={stepIndex} sx={{ mb: 3 }}>` has no `overflowX: 'auto'` or responsive layout, overflowing a 360px container when 5–6 steps are rendered side by side.
  - Step title (`Step {current} of {total}`) has no `aria-live="polite"` attribute.
- **Evidence / test status:**
  - Confirmed in `web/src/pages/setup/SetupWizardPage.tsx:375-393`.
- **Root cause:**
  - Missing `overflowX: 'auto'` on `<Stepper>` and missing `aria-live="polite"` on the step progress indicator.
- **Impact:**
  - Horizontal clipping/scrolling on budget Android phones (360px width) commonly used by Indian shopkeepers, and silent step transitions for screen-reader users.
- **Recommended correction:**
  - Add `sx={{ mb: 3, overflowX: 'auto', pb: 1 }}` to `<Stepper>` and `aria-live="polite"` on the step progress header in `SetupWizardPage.tsx`.
- **Regression tests required:**
  - Verify `SetupWizardPage.test.tsx` renders without layout regression.
- **Acceptance criteria:**
  - Stepper scrolls cleanly within its container on 360px screens and announces step changes via `aria-live="polite"`.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-007` — No Way to Change Company `State` in Setup Wizard Step 1 (`tax`) or Step 2 (`shop`)
- **Finding ID:** `ONB-UX-007`
- **Title:** `SetupWizardPage` displays `State: {state} (set during registration)` as read-only text with no way to edit it if the user selected the wrong state at sign-up or entered a GSTIN from another state
- **Severity:** **P3 (Low)**
- **Category:** UX / Indian SMB Guidance
- **Affected screen / route:** `SCR-09` (`/setup?step=tax`), `SCR-10` (`/setup?step=shop`)
- **Affected file / component / API / model:**
  - `web/src/pages/setup/SetupWizardPage.tsx` (lines 437–439)
- **Preconditions:**
  - User accidentally picked the wrong state on `/register` and notices `State: ... (set during registration)` in Step 2 (`shop`).
- **Reproduction steps:**
  1. Navigate to `/setup?step=shop`.
  2. Observe `State: Karnataka (set during registration)` rendered as plain static text.
- **Expected behavior:**
  - Either allow selecting/updating `state` in the Setup Wizard or automatically sync `state` from the verified GSTIN state code in Step 1 (`ONB-CR-007`).
- **Actual behavior:**
  - `state` is read-only throughout `/setup`; the user has to leave `/setup` and visit `/settings/company` to fix their state.
- **Evidence / test status:**
  - Confirmed in `web/src/pages/setup/SetupWizardPage.tsx:437-439`.
- **Root cause:**
  - `SetupWizardPage` displays `company.state` as a static `<Typography>` instead of an editable select or auto-synced GSTIN state.
- **Impact:**
  - Minor friction if a user selected the wrong state during sign-up.
- **Recommended correction:**
  - Auto-sync `company.state` from `gstin_state_name(gstin)` when a valid GSTIN is saved in Step 1 (and warn via `gstinStateMismatch` if it differs from the registration state).
- **Regression tests required:**
  - Covered by `ONB-CR-007` regression tests.
- **Acceptance criteria:**
  - GSTIN state prefix and `company.state` remain synchronized during onboarding.
- **Verification status:** Confirmed in code review.

---

### `ONB-UX-008` — `AcceptInvitePage` Uses Plain Password Input Without Show/Hide Toggle
- **Finding ID:** `ONB-UX-008`
- **Title:** `AcceptInvitePage` password input uses a plain `<TextField type="password">` instead of `<PasswordField>`, depriving invited staff of the show/hide password toggle
- **Severity:** **P3 (Low)**
- **Category:** Accessibility / Form Semantics
- **Affected screen / route:** `SCR-08` (`/invite`)
- **Affected file / component / API / model:**
  - `web/src/pages/AcceptInvitePage.tsx` (lines 83–94)
- **Preconditions:**
  - Invited staff member opens `/invite?token=...` on mobile or desktop.
- **Reproduction steps:**
  1. Open `/invite?token=abc`.
  2. Inspect the `New password` field.
- **Expected behavior:**
  - Should use `<PasswordField>` (like `LoginPage` and `RegisterPage`) so users on mobile keyboards can reveal the password they are typing (since there is no "Confirm password" field on `AcceptInvitePage`!).
- **Actual behavior:**
  - Uses `<TextField type="password">` with no visibility toggle and no confirmation field; a single typo locks the user out of the password they think they set.
- **Evidence / test status:**
  - Confirmed in `web/src/pages/AcceptInvitePage.tsx:83-94`.
- **Root cause:**
  - `AcceptInvitePage` was not updated to use `<PasswordField>` when `<PasswordField>` was introduced on `LoginPage` and `RegisterPage`.
- **Impact:**
  - Invited staff typing a password on mobile with no confirm field and no show/hide toggle can easily mistype their password and get locked out immediately after activating their invite.
- **Recommended correction:**
  - Replace `<TextField type="password" ... />` with `<PasswordField ... />` in `AcceptInvitePage.tsx`.
- **Regression tests required:**
  - Verify `AcceptInvitePage.test.tsx` passes with `<PasswordField>`.
- **Acceptance criteria:**
  - `AcceptInvitePage` renders `<PasswordField>` with a working show/hide password toggle button.
- **Verification status:** Confirmed in code review.

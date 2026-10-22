# Bizboard — Onboarding Security, Privacy, Tenant Isolation & Compliance Review (`ONBOARDING_SECURITY_REVIEW.md`)

**Audit Date:** 2026-10-21  
**Scope:** Authentication, Session Cookies, CSRF, OTP/MFA Cryptography, Brute-Force Throttling, Anti-Enumeration, Tenant Isolation (`X-Company-Id`), PII Encryption, Audit Logging, and Indian Statutory/DPDP Privacy Controls.

---

## 1. Security Architecture Strengths Verified

1. **Cryptographic OTP & Recovery Code Storage (`backend/accounts/otp_utils.py`, `backend/accounts/mfa.py`):**
   - Signup and login OTPs (`OtpChallenge.code`) are **never** stored in plaintext; they are hashed with `HMAC-SHA256` using `OTP_PEPPER` (or `SECRET_KEY`) and verified via constant-time `hmac.compare_digest`.
   - TOTP secrets (`UserMfa.secret_enc`) are encrypted at rest with Fernet (`planwave.crypto`), and MFA recovery codes are stored as salted SHA-256 digests (`UserMfa.recovery_hashes`).
2. **Production Guardrails Against Debug Bypass (`backend/planwave/settings.py:591-614`, `web/src/api/client.ts:8-14`):**
   - `settings.py` raises `ImproperlyConfigured` at startup if `DEBUG=False` and `OTP_DEBUG_ECHO=True`.
   - `web/src/api/client.ts` throws a fatal error at bundle boot if `import.meta.env.PROD` is true and `VITE_USE_MOCKS === 'true'` or `VITE_PILOT_ADVANCED === 'true'`.
3. **HttpOnly Cookie JWTs + Double-Submit CSRF (`backend/accounts/jwt_cookies.py`, `web/src/api/client.ts`):**
   - Access (`bb_access`) and refresh (`bb_refresh`) tokens are set as `httpOnly` cookies (`SameSite=Lax`, `Secure` in production), preventing XSS token theft.
   - Enrolment tokens (`memoryEnrolToken`) are kept strictly in module memory (`client.ts:20`), never in `localStorage` or `sessionStorage` (`BUG-SEC-015`).
4. **Rate Limiting & Brute-Force Protection (`backend/core/throttles.py`, `backend/accounts/views.py`):**
   - Dedicated throttles guard every public onboarding endpoint: `AuthBurstThrottle`, `RegisterRateThrottle` (10/hr/IP), `LoginRateThrottle` (10/min/IP + 5 failed attempts/15min per email+IP), `OtpRequestEmailRateThrottle` (5/min/IP + 3/10min/email), `OtpRequestPhoneRateThrottle`, `OtpVerifyPhoneRateThrottle`, `InviteAcceptRateThrottle`, `PasswordResetRequestThrottle`, and `PasswordResetConfirmThrottle`.
5. **Sensitive Financial PII Encryption at Rest (`backend/planwave/crypto.py`, `backend/accounts/models.py`):**
   - `Company.bank_account` and `payments.BankAccount.account_number` are encrypted at rest (`seal_bank_account` / `reveal_bank_account`), and staff serializers (`CompanySerializerStaff`) strip bank account and gateway fields.

---

## 2. Executive Summary of Security Findings

| Finding ID | Severity | Category | Title | Affected Component / Endpoint |
|---|---|---|---|---|
| `ONB-SEC-001` | **P2 (Medium)** | Security / Authentication | `AcceptInviteView` marks `InviteJti` consumed and activates `CompanyUser` membership **before** verifying MFA when an existing user with 2FA enabled accepts an invite | `POST /api/v1/auth/invite/accept/` (`backend/accounts/views.py:1236-1318`) |
| `ONB-SEC-002` | **P3 (Low)** | Security / Anti-Enumeration | `RequestRegisterOtpView` and `RequestOtpView` omit `debug_code` when email already exists or phone is unregistered in `OTP_DEBUG_ECHO=True` mode, creating a dev/staging enumeration oracle | `POST /api/v1/auth/register/otp/request/`, `POST /api/v1/auth/otp/request/` (`backend/accounts/views.py:397-409, 646-662`) |
| `ONB-SEC-003` | **P3 (Low)** | Security / Session Hygiene | `AcceptInvitePage` and `LoginPage` do not clear cached active company ID (`localStorage['bizboard:active-company-id']`) from a prior user's session on the same browser before establishing a new user's session | `web/src/pages/AcceptInvitePage.tsx`, `web/src/auth/AuthContext.tsx` |

---

## 3. Detailed Security Findings (Mandatory 17-Field Format)

### `ONB-SEC-001` — `AcceptInviteView` Activates Membership & Consumes Invite Token Before MFA Verification
- **Finding ID:** `ONB-SEC-001`
- **Title:** `AcceptInviteView` marks `InviteJti` consumed and activates `CompanyUser` membership **before** verifying MFA when an existing user with 2FA enabled accepts an invite
- **Severity:** **P2 (Medium)**
- **Category:** Security / Authentication
- **Affected screen / route:** `SCR-08` (`/invite` -> `POST /api/v1/auth/invite/accept/`)
- **Affected file / component / API / model:**
  - `backend/accounts/views.py` (`AcceptInviteView.post`, lines 1236–1318)
  - `web/src/pages/AcceptInvitePage.tsx` (lines 38–48)
- **Preconditions:**
  - Existing User U has 2FA (`UserMfa`) enabled on their account (or `enrolment_required(user)` is True).
  - User U is invited to Company B and receives an invite link (`/invite?token=...`).
- **Reproduction steps:**
  1. Call `POST /api/v1/auth/invite/accept/` with `{ "token": "<valid_invite_token>", "password": "<user_password>" }`.
  2. Inside the `with transaction.atomic():` block (`views.py:1236-1269`), `invite_jti.consumed_at = timezone.now()`, `membership.is_active = True`, and `user.active_company = membership.company` are committed to the database.
  3. After the atomic block, lines 1311–1315 check `if not caller_ already_authenticated:` and return `mfa_challenge_response(user)` (`{"mfa_required": True, "mfa_token": "..."}`).
  4. On the frontend, `AcceptInvitePage.tsx:42-46` sees `body?.mfaRequired` and simply redirects the user to `/login?invited=1` (discarding `mfa_token`), while in the database the membership is already activated and `user.active_company` has already been mutated!
- **Expected behavior:**
  - Either `AcceptInvitePage.tsx` should complete the MFA challenge (or redirect to `/login` cleanly), and more importantly, if an unauthenticated caller supplies only the first factor (password) for a 2FA-protected user, `user.active_company` should not be mutated across their existing active sessions until the second factor is verified (or they sign in).
- **Actual behavior:**
  - Knowing only the invite token and first-factor password mutates `user.active_company` and activates `membership` before MFA is verified.
- **Evidence / test status:**
  - Confirmed in `backend/accounts/views.py:1236-1318` and `web/src/pages/AcceptInvitePage.tsx:42-46`.
- **Root cause:**
  - MFA check was placed after the `transaction.atomic()` block in `AcceptInviteView.post`.
- **Impact:**
  - Partial state mutation (`user.active_company` switched for an existing 2FA user) prior to second-factor verification.
- **Recommended correction:**
  - When `not caller_already_authenticated` and `(enrolment_required(user) or mfa_is_enabled(user))`, only switch `user.active_company` if `user.active_company_id is None`, or require MFA verification before switching an existing user's active company.
- **Regression tests required:**
  - Backend test in `test_settings_users.py` verifying invite acceptance for an MFA-enabled existing user.
- **Acceptance criteria:**
  - Accepting an invite unauthenticated for an existing 2FA-enabled user does not disrupt their existing `active_company` before 2FA is verified.
- **Verification status:** Confirmed in code review.

---

### `ONB-SEC-002` — Dev/Staging Enumeration Side-Channel When `OTP_DEBUG_ECHO=True`
- **Finding ID:** `ONB-SEC-002`
- **Title:** `RequestRegisterOtpView` and `RequestOtpView` omit `debug_code` when email already exists or phone is unregistered in `OTP_DEBUG_ECHO=True` mode
- **Severity:** **P3 (Low)**
- **Category:** Security / Anti-Enumeration
- **Affected screen / route:** `SCR-01` (`/register`), `SCR-03` (`/login` Mobile OTP tab)
- **Affected file / component / API / model:**
  - `backend/accounts/views.py` (`RequestRegisterOtpView`, lines 397–409; `RequestOtpView`, lines 646–662)
- **Preconditions:**
  - Non-production environment with `DEBUG=True` and `OTP_DEBUG_ECHO=True`.
- **Reproduction steps:**
  1. Call `POST /api/v1/auth/register/otp/request/` with a new email -> response includes `debug_code`.
  2. Call `POST /api/v1/auth/register/otp/request/` with an already-registered email -> response omits `debug_code`.
- **Expected behavior:**
  - In production (`DEBUG=False`), `OTP_DEBUG_ECHO` is hard-blocked at startup (`settings.py:591-614`), so production is safe. In dev/demo environments where `OTP_DEBUG_ECHO=True`, developers should be aware that `debug_code` presence reveals whether the email/phone exists.
- **Actual behavior:**
  - `debug_code` is only echoed when a challenge is newly sent.
- **Evidence / test status:**
  - Confirmed in `backend/accounts/views.py:397-409` and `settings.py:591-614`.
- **Root cause:**
  - By design for local/dev convenience (`OTP_DEBUG_ECHO`), mitigated in production by the startup check in `settings.py`.
- **Impact:**
  - Low / Informational (cannot occur in production because `settings.py` refuses to boot if `DEBUG=False` and `OTP_DEBUG_ECHO=True`).
- **Recommended correction:**
  - Keep `OTP_DEBUG_ECHO=False` in any shared staging environment; no production code change needed, documented as an operational control.
- **Regression tests required:**
  - Already covered in `backend/tests/test_auth.py`.
- **Acceptance criteria:**
  - `OTP_DEBUG_ECHO` remains strictly disabled outside local/CI test runs.
- **Verification status:** Verified safe in production configuration.

---

### `ONB-SEC-003` — Stale `bizboard:active-company-id` in `localStorage` Across User Logins on Shared Browser
- **Finding ID:** `ONB-SEC-003`
- **Title:** `AcceptInvitePage` and `AuthContext.login` do not clear a prior user's `localStorage['bizboard:active-company-id']` before fetching `/auth/me/` or `/company/`
- **Severity:** **P3 (Low)**
- **Category:** Security / Session Hygiene
- **Affected screen / route:** `SCR-02`, `SCR-03`, `SCR-08` (`/login`, `/invite`)
- **Affected file / component / API / model:**
  - `web/src/auth/AuthContext.tsx` (lines 71–116)
  - `web/src/pages/AcceptInvitePage.tsx` (lines 38–54)
  - `web/src/api/client.ts` (`ACTIVE_COMPANY_STORAGE_KEY`, lines 29–36, 126–139)
- **Preconditions:**
  - User A was logged in on a shared shop PC with `localStorage['bizboard:active-company-id'] = "10"`.
  - User B logs in (or accepts an invite for Company 25) in the same browser without User A having clicked "Sign out" (e.g., session expired or direct `/login` / `/invite` visit).
- **Reproduction steps:**
  1. Set `localStorage.setItem('bizboard:active-company-id', '10')`.
  2. Sign in as User B (whose active company is `25`) on `/login` or accept an invite on `/invite`.
  3. Inspect the `X-Company-Id` header attached by `apiClient` (`client.ts:126-139`) on the subsequent `GET /api/v1/auth/me/` and `GET /api/v1/company/` calls.
- **Expected behavior:**
  - Backend `get_company_user(request)` safely ignores an `X-Company-Id` that User B is not a member of (falling back to `user.active_company`), **unless** User B happens to be a member of BOTH Company 10 and Company 25 (e.g., an external Accountant)! If User B is a member of both, the stale `localStorage['bizboard:active-company-id'] = '10'` overrides `user.active_company` (`25`) on every API request!
- **Actual behavior:**
  - `AuthContext.login` / `loginWithOtp` / `completeMfaLogin` and `AcceptInvitePage` do not synchronize `localStorage['bizboard:active-company-id']` to `loggedIn.companyId` upon login/invite acceptance!
- **Evidence / test status:**
  - Confirmed in `web/src/auth/AuthContext.tsx:71-96`, `web/src/pages/AcceptInvitePage.tsx:38-54`, and `web/src/api/client.ts:29-36,126-139`.
- **Root cause:**
  - `localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY)` is called in `logout()`, but not updated/cleared at the start of `login()`, `loginWithOtp()`, `completeMfaLogin()`, or `AcceptInvitePage` submit.
- **Impact:**
  - If a multi-company user (or two users on a shared device who share a company membership) signs in or accepts an invite without a prior explicit `logout()`, `X-Company-Id` sends the stale company ID from `localStorage` instead of the newly authenticated user's `companyId`.
- **Recommended correction:**
  - In `AuthContext.tsx` (`login`, `loginWithOtp`, `completeMfaLogin`) and `AcceptInvitePage.tsx`, set `localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, String(user.companyId))` (or remove it if `companyId` is null) whenever a new session is established.
- **Regression tests required:**
  - Unit test verifying that `login()` overwrites a stale `bizboard:active-company-id` in `localStorage` with the newly logged-in user's `companyId`.
- **Acceptance criteria:**
  - Signing in or accepting an invite always aligns `bizboard:active-company-id` with the authenticated user's `companyId`.
- **Verification status:** Confirmed in code review.

# Area 01 — Backend Core, Auth, Tenancy, Config

**Scope:** `backend/accounts/*`, `backend/config/*`, `backend/core/*` (models, permissions, viewsets, views, urls, pagination, renderers, serializers, validators, exceptions, handlers, events, tasks), `backend/core/services/{audit,files,notifications,sms,llm}.py`.

---

### BUG-100 — BUG-002 (manual 400 rendered as success:true) — claim verification
- **Severity:** N/A
- **Location:** `backend/core/renderers.py:11-43`; `backend/accounts/views.py:113-166`
- **Description:** Already fixed. `EnvelopeJSONRenderer` now has an explicit `status_code >= 400` branch wrapping any error response as `{"success": false, "error": {...}}` regardless of `response.exception`. Reproduced live: `otp/request {}` → 400 with a proper `success:false` envelope; `RequestOtpView.post` now raises `ValidationError` instead of returning a raw `Response`.
- **Suggested test:** `test_otp_request_missing_phone_returns_error_envelope` asserting `resp.json()["success"] is False` at the wire level (current tests only check status code, not the actual envelope).
- **Status vs prior report:** ALREADY-FIXED.

### BUG-101 — DEBUG/SECRET_KEY defaults still fail open, not closed
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/config/settings.py:17-28`
- **Description:** `DEBUG` still defaults `True` and an insecure `SECRET_KEY` fallback is still hardcoded. A fail-fast guard exists but only fires when `DJANGO_ENV` is explicitly `"production"`. Since `DJANGO_ENV` itself defaults to `"production" if not DEBUG else "development"`, and `DEBUG` defaults `True`, an operator who simply forgets `DJANGO_DEBUG=0` gets `DJANGO_ENV="development"` automatically — the fail-fast never triggers.
- **Impact:** A misconfigured/forgotten env var deploys with debug stack traces (leaking SECRET_KEY, settings, SQL) and a publicly-known secret key (JWT/session forgery risk) to real users.
- **Remediation:** Make `DJANGO_ENV` default to `"production"` unconditionally (not derived from DEBUG), or fail closed whenever `DJANGO_SECRET_KEY`/`DJANGO_DEBUG` are unset with no explicit `DJANGO_ENV=development`.
- **Suggested test:** Settings-level test asserting `ImproperlyConfigured` when `DJANGO_DEBUG` is unset and no `DJANGO_ENV` override is given.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (mitigated, not closed) (BUG_REPORT.md BUG-004).

### BUG-102 — OTP SMS provider never sends a real SMS in any configuration, but reports success
- **Severity:** Critical
- **Category:** Broken-Flow
- **Location:** `backend/core/services/sms.py:6-16`; `backend/config/settings.py:203`; `backend/accounts/views.py:107-132`
- **Description:** `SmsProvider.send_otp` prints the code to stdout for every branch, including the "real provider" branch — no actual SMS integration exists at all. With `SMS_PROVIDER` defaulting to `"console"` (not blocked by the view's `("", "off", "disabled")` check) and production `OTP_DEBUG_ECHO` off, default production behavior is: user requests OTP → API returns "OTP sent." (200) → no SMS is ever delivered → code exists only in server logs.
- **Impact:** OTP login is completely non-functional out of the box while reporting success. Also: plaintext OTP codes land in production logs for any non-blocked `SMS_PROVIDER` value — a log-access-based OTP bypass.
- **Remediation:** Raise a business-rule error from `SmsProvider.send_otp` when no real provider integration exists, instead of silently printing; wire an actual MSG91/Twilio client before shipping OTP login.
- **Suggested test:** `test_otp_request_with_unconfigured_real_provider_fails_loudly`.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (worse than described — even a "configured" provider silently no-ops) (BUG_REPORT.md BUG-007).

### BUG-103 — RBAC still binary at the role level; Owner unconditionally bypasses all capability flags
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/models.py:96-117`; `backend/core/permissions.py:28-85`
- **Description:** Granular capability flags were added since the prior report (real progress), but `role` remains only `OWNER | SALES_STAFF`, and every permission class special-cases `role == "OWNER"` to bypass its flag entirely — there's no way to create a "bookkeeper"/limited-owner account, and multi-owner companies can't restrict any owner's access.
- **Remediation:** Introduce an ACCOUNTANT/VIEWER role, or decouple "Owner" (account admin) from "full business permissions" so flags can restrict owners too.
- **Status vs prior report:** PARTIALLY-FIXED (BUG_REPORT.md BUG-009).

### BUG-104 — `/api/v1/docs/` 500s due to a namespace mismatch in the reverse lookup
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/config/urls.py:16-44`
- **Description:** `GatedSwaggerView(url_name="schema")` tries `reverse("schema", ...)`, but the URL is registered under the `"v1"` namespace — the real name is `"v1:schema"`. Reproduced live: `NoReverseMatch` → 500. `/api/v1/schema/` itself works fine.
- **Remediation:** `GatedSwaggerView(url_name="v1:schema")`.
- **Suggested test:** `test_docs_view_renders_for_owner` — would have caught this immediately.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT, root cause pinpointed (BUG_REPORT.md BUG-019).

### BUG-105 — VerifyOtpView missing its own throttle scope
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/config/settings.py:139-150`; `backend/accounts/views.py:39,68,111,135`
- **Description:** Throttling (login/otp/register scopes) is now largely implemented — real progress. But `VerifyOtpView` has no `throttle_scope` set, unlike its sibling `RequestOtpView`, so only the blanket `anon` (120/min) rate applies to OTP-code guessing (the per-challenge `OTP_MAX_ATTEMPTS=5` lockout is the real backstop).
- **Remediation:** Add `throttle_scope = "otp"` to `VerifyOtpView`.
- **Status vs prior report:** ALREADY-FIXED (mostly) (BUG_REPORT.md BUG-021), minor gap remains.

### BUG-106 — CSRF with Bearer JWT — claim verification
- **Severity:** N/A
- **Location:** `backend/config/settings.py:64-73`; `backend/accounts/views.py:150`
- **Description:** Verified non-issue. Auth is JWT-only (no `SessionAuthentication`), DRF's `APIView.as_view()` unconditionally wraps views in `csrf_exempt`, and `Authorization: Bearer` headers are never auto-attached by browsers — no CSRF attack surface.
- **Status vs prior report:** INACCURATE (non-issue) (SECURITY_REPORT.md S-12).

### BUG-107 — Refresh tokens never rotate; a stolen token stays valid for the full 7-day lifetime
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/config/settings.py:157-162,213-214`
- **Description:** `ROTATE_REFRESH_TOKENS: False` means refresh tokens are reused verbatim for 7 days; `BLACKLIST_AFTER_ROTATION: True` is inert since rotation never happens. The only mitigation for a stolen refresh token is the victim explicitly calling `/auth/logout/` with that same token.
- **Impact:** Refresh-token exfiltration (XSS, device theft, log leakage — compounded by area 04's BUG-402 localStorage finding) gives an attacker up to 7 days of persistent, undetectable access.
- **Remediation:** Set `ROTATE_REFRESH_TOKENS: True` so each refresh invalidates the prior token, making reuse-by-both-parties detectable.
- **Status vs prior report:** CONFIRMED (SECURITY_REPORT.md, accurately described; not fixed).

### BUG-108 — Duplicate phone numbers crash OTP verification with a 500
- **Severity:** Critical
- **Category:** Bug
- **Location:** `backend/accounts/views.py:155`; `backend/accounts/models.py:28`
- **Description:** `User.phone` is not unique (index only), and nothing enforces phone uniqueness at registration/invite. `VerifyOtpView.post` uses `User.objects.get(phone=phone, is_active=True)` — if two active users share a phone (common for families/small shops), this raises `MultipleObjectsReturned`, unhandled, → 500. **Reproduced live.**
- **Impact:** Any two legitimately registered accounts sharing a phone permanently 500 on OTP login for that number — a real production outage waiting to happen.
- **Remediation:** Add `unique=True` to `User.phone` (migration + data audit), or defensively change to `.filter(...).order_by(...).first()`, and reject duplicate phones at registration/invite time.
- **Suggested test:** `test_otp_verify_with_duplicate_phone_across_users_does_not_500` (currently fails/500s).
- **Status vs prior report:** NEW.

### BUG-109 — CompanyUserViewSet allows attaching an existing, unconsenting user to your company
- **Severity:** Critical
- **Category:** Bug
- **Location:** `backend/accounts/views.py:209-232`
- **Description:** `CompanyUserViewSet.create` looks up `User.objects.filter(email__iexact=...)` across **all** users system-wide. If the email belongs to an existing user unrelated to the inviting company, a `CompanyUser` row is created attaching them — at any role the inviter chooses, including OWNER — with zero consent, invite token, or confirmation. **Reproduced live**: attacker POSTs an existing victim's email with `role:"OWNER"` → 201, victim now has an OWNER membership in a company they never agreed to join.
- **Impact:** A genuine cross-tenant boundary violation in a multi-tenant billing product — any company owner can forcibly enroll any registered user (discoverable via BUG-114) into their own company at any role.
- **Remediation:** Require the target to not already exist as a `User` for direct attach (create-account-and-email-activation flow), or require an out-of-band consent step before the `CompanyUser` row goes active.
- **Suggested test:** `test_cannot_attach_existing_user_to_company_without_consent` (currently the opposite happens).
- **Status vs prior report:** NEW.

### BUG-110 — Non-deterministic "first active membership" resolution for multi-company users
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/core/permissions.py:4-16`; `backend/accounts/models.py:96-117`
- **Description:** `get_company_user()` (used by `HasCompany`, `MeView`, `LoginView`, `VerifyOtpView` — everywhere) resolves the active company via an unordered `.filter(is_active=True).first()`. `CompanyUser` has no `Meta.ordering`, and nothing prevents a user from having multiple active memberships (only unique *within* a company). Combined with BUG-109, a user can end up in an arbitrary company context on login with no way to choose.
- **Impact:** For any user with 2+ memberships, which company they see/act in per request is undefined — they could unknowingly view or write data into the wrong tenant.
- **Remediation:** Enforce one active membership per user at the DB level (partial unique index on `user` where `is_active=True`), or build explicit "select active company" UX.
- **Status vs prior report:** NEW.

### BUG-111 — Company bank/UPI details exposed to SALES_STAFF (read)
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/views.py:176-188`; `backend/accounts/serializers.py:21-32`
- **Description:** `CompanyDetailView` only gates `PUT`/`PATCH` behind `IsOwner`; `GET` only requires `IsAuthenticated, HasCompany`. `CompanySerializer` includes `bank_name`/`bank_account`/`bank_ifsc`/`upi_id`, fully readable by any SALES_STAFF regardless of the capability flags (BUG-103), since no capability covers "view banking details."
- **Impact:** Any invited (potentially low-trust, high-turnover) staff member can read the company's bank account number and IFSC code.
- **Remediation:** Split `CompanySerializer` into a staff-visible subset (no banking fields) and an owner-only full serializer.
- **Status vs prior report:** NEW (extension of BUG-009/S-10).

### BUG-112 — No safeguard against removing the last OWNER of a company
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/views.py:198-238`
- **Description:** An Owner can PATCH their own row's role down or DELETE it (soft-deactivate), with no check for whether they're the company's only active owner — a company can end up with zero active owners, permanently losing access to Owner-gated functionality short of a Django-admin intervention.
- **Remediation:** Before demoting/deactivating an OWNER, verify another active OWNER exists; reject with 400 otherwise.
- **Status vs prior report:** NEW.

### BUG-113 — Phone-number enumeration oracle in RequestOtpView
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/views.py:113-118`
- **Description:** Returns a distinct "No user with this phone number." error before even checking whether OTP is configured — an unauthenticated, throttled-only-5/min caller can enumerate which phone numbers have accounts.
- **Impact:** PII leak usable for targeted phishing/social engineering against small retailers.
- **Remediation:** Return a generic "If this phone number is registered, an OTP has been sent." regardless of existence.
- **Status vs prior report:** NEW.

### BUG-114 — Email enumeration oracle in registration
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/accounts/serializers.py:15-18`
- **Description:** Distinct "A user with this email already exists." error enables email enumeration — this is what makes BUG-109 practical to target.
- **Status vs prior report:** NEW.

### BUG-115 — Concurrent duplicate-email registration can 500
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/accounts/views.py:41-62`; `backend/accounts/serializers.py:15-18`
- **Description:** Email uniqueness is checked via a pre-`SELECT` before `create_user`; under concurrent requests for the same email (double-submit, retry on flaky mobile network), both can pass the check before either commits, and the second `INSERT` raises an uncaught `IntegrityError` → 500 instead of a clean 400.
- **Remediation:** Wrap creation in `try/except IntegrityError`, translate to the same validation message.
- **Status vs prior report:** NEW.

### BUG-116 — Custom User model registered in Django admin without UserAdmin
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/accounts/admin.py:1-7`
- **Description:** `admin.site.register(User)` uses the default `ModelAdmin`, not `UserAdmin` — the raw hashed `password` field is shown as a plain editable text field. Typing a new value directly into it stores it unhashed, silently breaking that user's login.
- **Remediation:** Register `User` with a `UserAdmin`-derived class using `ReadOnlyPasswordHashField`.
- **Status vs prior report:** NEW.

### BUG-117 — CompanyUserViewSet.perform_destroy doesn't create an audit event
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/accounts/views.py:198-238`
- **Description:** Doesn't extend `CompanyScopedViewSet` (which auto-audits); its custom `perform_destroy` deactivates a user's company access with no `AuditService.log` call, unlike `create`.
- **Impact:** Removing a user's company access (security-sensitive, e.g. offboarding) leaves no audit trail.
- **Status vs prior report:** NEW.

### BUG-118 — Inconsistent error `code` field between exception path and manual-400 path
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/core/exceptions.py:29`; `backend/core/renderers.py:36`
- **Description:** The exception-handler path returns specific `code`s (`invalid`, `authentication_failed`, etc.); `VerifyOtpView`'s three manual `Response(..., status=400)` calls all hardcode `"code": "error"` — frontend clients can't distinguish "Invalid OTP" from "Too many attempts" from "OTP expired" programmatically.
- **Remediation:** Have `VerifyOtpView` raise typed exceptions instead of manual Responses.
- **Status vs prior report:** NEW.

### BUG-119 — Redundant dead condition in RequestOtpView
- **Severity:** Cosmetic
- **Location:** `backend/accounts/views.py:130`; `backend/config/settings.py:201`
- **Description:** `OTP_DEBUG_ECHO` is already `DEBUG and env==1`, so the view's `if settings.OTP_DEBUG_ECHO and settings.DEBUG:` redundantly re-checks DEBUG.
- **Status vs prior report:** NEW.

### BUG-120 — No per-account brute-force lockout on login, only per-IP throttling
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/views.py:65-86`; `backend/config/settings.py:144-150`
- **Description:** `LoginView` relies solely on IP-keyed `ScopedRateThrottle`; no per-account failed-attempt counter/lockout. Distributed credential-stuffing across many IPs isn't meaningfully rate-limited against a specific target account.
- **Remediation:** Add a per-email failed-attempt counter (cache-based) with backoff/temporary lock, independent of source IP.
- **Status vs prior report:** NEW (extension of S-04/BUG-021).

### BUG-121 — OtpChallenge table has no purge mechanism / composite index
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/accounts/models.py:120-129`
- **Description:** Every OTP request creates a row; nothing ever deletes expired/consumed ones. Only a single-column index exists despite queries filtering on `phone`+`consumed`+ordering by `-created_at`. Unbounded retention of security-sensitive OTP history.
- **Remediation:** Add a composite index; add a periodic purge task for challenges older than ~24h.
- **Status vs prior report:** NEW.

### BUG-122 — FileAssetViewSet.download can 500 if the underlying file is missing
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/core/views.py:47-50`
- **Description:** `asset.file.open("rb")` has no existence/error handling — a missing storage file (ops cleanup, migration, disk issue) raises `FileNotFoundError` → 500 instead of a clean 404.
- **Status vs prior report:** NEW.

### BUG-123 — No logout / refresh-blacklist-reuse test
- **Severity:** Medium
- **Category:** Test-Coverage
- **Description:** No test for `/auth/logout/` at all, nor that a blacklisted refresh token is subsequently rejected.
- **Suggested test:** `test_logout_blacklists_refresh_token_and_prevents_reuse`.
- **Status vs prior report:** NEW.

### BUG-124 — No OTP max-attempts lockout or blocked-provider test
- **Severity:** Medium
- **Category:** Test-Coverage
- **Description:** `OTP_MAX_ATTEMPTS` lockout and the blocked-`SMS_PROVIDER` path are entirely untested.
- **Suggested test:** `test_otp_verify_locks_out_after_max_attempts`, `test_otp_request_blocked_when_sms_provider_disabled`.
- **Status vs prior report:** NEW.

### BUG-125 — No throttle-enforcement tests
- **Severity:** Medium
- **Category:** Test-Coverage
- **Description:** Throttle rates exist but nothing verifies enforcement end-to-end (e.g. 11th login attempt in a minute returns 429) — this was the exact prior claim (BUG-021) and warrants a regression guard.
- **Suggested test:** `test_login_throttled_after_rate_exceeded`.
- **Status vs prior report:** NEW.

### BUG-126 — No smoke test for /schema/ or /docs/
- **Severity:** Medium
- **Category:** Test-Coverage
- **Description:** Nothing hits either endpoint — a single test would have caught BUG-104 immediately, the cheapest possible guard against this regression class.
- **Suggested test:** `test_owner_can_view_api_docs`, `test_schema_endpoint_returns_200`.
- **Status vs prior report:** NEW.

### BUG-127 — No regression tests for the two most severe findings in this area
- **Severity:** High
- **Category:** Test-Coverage
- **Description:** Neither BUG-108 (duplicate-phone 500) nor BUG-109 (unconsented cross-tenant invite) has any covering test — both currently misbehave and would go undetected in CI.
- **Suggested test:** `test_otp_verify_with_duplicate_phone_across_users_does_not_500`, `test_cannot_attach_existing_user_to_company_without_consent`.
- **Status vs prior report:** NEW.

---

## Summary of most severe systemic issues

1. **The multi-tenancy/identity model has no real boundary around who can join which company.** `CompanyUserViewSet.create` will silently attach any existing registered user (found via the register-email-enumeration oracle) to an attacker's company at any role, and `get_company_user()`'s undefined `.first()`-based resolution means a user with multiple memberships gets an arbitrary tenant context on every login (BUG-108/109/110) — a genuine cross-tenant boundary violation in a multi-tenant billing product, the highest-priority fix in this whole review.
2. **OTP login is functionally broken by default in production.** `SmsProvider` never actually sends SMS for any provider while the API reports "OTP sent" success, and a duplicate phone number crashes verification outright with a 500 (BUG-102/108) — this login path needs both a real SMS integration and defensive data-integrity fixes before it's pilot-safe.
3. **Config-hardening added since the last review (throttling, envelope-wrapping, capability flags, fail-fast secret checks) is real progress, but opt-in rather than secure-by-default.** DEBUG/SECRET_KEY/DJANGO_ENV all fail open if an operator simply forgets to set env vars (BUG-101), and the reproduced `/api/v1/docs/` 500 (BUG-104) shows this class of easily-tested regression is currently invisible to CI because no test hits these endpoints at all.

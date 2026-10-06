# LLM implementation plan — ISO 25010 closeable items

**Date:** 2026-10-04. **Revised** the same day after review.
**Status:** execution plan. Not a scope change. Not a Go/No-Go signature.
**Source:** the 2026-10-04 ISO/IEC 25010 assessment and the follow-up list of items an agent can finish inside the repo.
**Tree this plan was written against:** commit `5deafb2` plus a large uncommitted working tree. Cite symbols (`AcceptInviteView`, `HttpIdentityProvider._get`), not line numbers. P0 records the dirty-tree fingerprint so G1 can be reproduced.

## What this plan closes

An agent can meet the acceptance line of every work package below without a public host, a CA, a paying customer, or a signed waiver.

## What this plan does not close

Leave these untouched. Coding them does not meet their acceptance criteria, or they are outside the freeze.

- TLS on a real hostname (`F-SEC-04`, QOS-0020). Do not invent a certificate.
- Offsite object storage and a restore from that copy (`F-REL-01`).
- Paging a human (`F-OBS-01`).
- The five-user study and any editor redesign driven by it (QOS-0029, QOS-0095).
- CA letter, DPDP signature, Go/No-Go names (QOS-0004, QOS-0049, QOS-0021).
- Live GSP, WhatsApp Cloud, payroll, manufacturing, CRM, milestone billing.

## Traceability

| Package | Closes | ISO 25010 | Risk |
|---|---|---|---|
| P0 | F-TEST-02 baseline | Functional correctness | Low |
| D1 | Doc drift found in the architecture audit | Maintainability › Analysability | Low |
| D2 | Backup comment vs `check_backup_age.sh` | Reliability › Recoverability | Low |
| D3 | Identity SSRF (partial in the security findings) | Security › Confidentiality | Medium. Rollback: revert `_get` |
| D4 | Freeze §C not visible in the product | Usability › User assistance | Low |
| S4 | Stale test module name | Maintainability › Testability | Low |
| S1 | Authenticated invite skips a fresh TOTP | Security › Authenticity | High. Rollback: restore the previous `AcceptInviteView` branch |
| S2 | F-SEC-02, QOS-0103 | Security › Authenticity | High. Rollback: `MFA_ENFORCE_FOR_MONEY_ROLES=0` and `MFA_ENFORCE_WAIVER=1` |
| S3 | F-SEC-03 tail truncation | Security › Integrity | Medium. Rollback: stop passing `--tip`; plain `verify` is unchanged |
| R1 | F-DATA-01 | Reliability › Maturity | Low |
| U1 | Deferred dirty-guard editors (MT-003) | Usability › User error protection | Low |
| U2 | F-A11Y-01, QOS-0096 (keyboard and touch) | Usability › Accessibility | Medium |
| U3 | QOS-0098 | Usability › Learnability | Medium |
| M1 | QOS-0016 query growth, not the field budget | Performance › Time behaviour | Low |
| M2 | QOS-0014 | Reliability › Maturity | Medium. Throwaway database only |
| M3 | QOS-0015 | Functional correctness | Low. A missing key is a written “not run” |
| M4 | F-PERF-01 evidence, not a passed SLO | Performance › Time behaviour | Low. A co-located run is labelled smoke |
| G1 | F-TEST-02, F-PORT-01 image smoke | Functional correctness | Medium |

## Rules for the executing agent

1. Implement one work package at a time and run its tests before the next. The commit-slice table is not an instruction to code several packages in one edit. It applies only when the operator asks for commits, and it bundles packages that were already finished separately. Slice 4 is the one exception that is also an implementation exception: S1 and S2 both edit `AcceptInviteView` and login, so they are written together. See that slice.
2. Do not weaken an existing test to go green. If a login helper breaks because MFA enforcement is on, the helper stays on the test default (enforcement off) and the new tests turn enforcement on.
3. **S2 stop rule.** After `settings_test.py` forces enforcement off, the number of newly failing tests outside `test_mfa.py` and `test_mfa_edge_cases.py` must be zero. If any pre-existing test fails, stop and report the node ids. Do not xfail them inside S2. Do not “fix” them by turning enforcement on in the suite.
4. Do not commit unless the operator asked for commits in that session.
5. Money, stock, and tax behaviour stay as they are. This plan does not retune GST, costing, or document totals.
6. Pilot flag defaults stay the frozen profile. S2 adds two settings, `MFA_ENFORCE_FOR_MONEY_ROLES` and `MFA_ENFORCE_WAIVER`. Classify both in `docs/FREEZE_SCOPE.md` in that same change.
7. P0 does not fix baseline failures. G1 triages them. A failure with no owner is not a green gate.

## Order

| Wave | Packages | Why this order |
|---|---|---|
| 0 | P0 | Fingerprint the tree and record the suite before new code |
| 1 | D1, D2, D3, D4, S4 | Docs, the static limitations page, the workflow rename, and the identity-client fix. No login behaviour change |
| 2 | S1+S2 together, then S3 | Auth, then the audit tip. S3 does not depend on S2 |
| 3 | R1, U1, U2, U3 | UX and accessibility. U2’s pilot-limits axe row waits until D4 exists |
| 4 | M1, M2, M3, M4 | Measurement. Does not block waves 1–3 |
| 5 | G1 | Full Postgres suite, image smoke, triage of anything P0 recorded |

Packages inside a wave are independent except S1+S2, and except U2’s `/help/pilot-limits` row, which follows D4. Waves are not.

---

## Wave 0 — Baseline

### P0. Record the suite before new edits

**Goal.** A before-picture a later run can be compared to.

**Do.**

1. Record `git rev-parse HEAD`, `git status --porcelain`, and a hash of the uncommitted diff (`git diff | git hash-object --stdin`, plus the same for untracked files that are source: `git ls-files --others --exclude-standard`). Write all three into `docs/reviews/ISO25010_REMEDIATION_LOG_2026-10-02.md` §3a under **baseline fingerprint**. G1 cites this fingerprint. A later “dirty tree” without it is not reproducible.
2. From `backend/`, with Docker Postgres up:

```text
PYTEST_KEEP_DATABASE_URL=1 DATABASE_URL=postgresql://... pytest --create-db -q --tb=no
```

Write the totals and the failing node ids into the same section, marked **baseline, not a fix**. If Postgres is unavailable, write that sentence and continue. Do not fix anything in this package.

**Done when.** §3a contains the fingerprint and either the suite totals or the explicit “Postgres unavailable” line.

---

## Wave 1 — Docs, limitations page, identity client

### D1. Architecture doc matches the code

**Current.** `docs/architecture.md` says Python 3.12 and “~19 Django apps”. `INSTALLED_APPS` installs 26 project apps: `core`, `accounts`, `masters`, `inventory`, `purchases`, `sales`, `payments`, `imports`, `ledgers`, `reporting`, `accounting`, `search`, `insights`, `integrations`, `manufacturing`, `payroll`, `crm`, `complaints`, `support`, `contracts`, `workshop`, `projects`, `insurance`, `banking`, `billing`, `ops`. Images are Python 3.13 (`backend/Dockerfile`).

**Dark modules.** `DARK_MODULE_KEYS` in `core/services/feature_flags.py` is only `ENABLE_MANUFACTURING`, `ENABLE_PAYROLL`, and `ENABLE_CRM`. `contracts`, `workshop`, `projects`, `insurance`, and `banking` are installed apps. They are not dark modules. Do not put them in that group.

**Change.** Replace the version and the app sentence. Group the 26 names as domain, platform, and dark modules (those three only). List the other five as installed apps, not as dark modules.

**Drift test.** Add a test that reads `docs/architecture.md` and asserts every project app label from `INSTALLED_APPS` (apps that are not `django.*` and not third-party) appears as a backtick token in that file, and that the string `DARK_MODULE_KEYS` is not required in the doc but the three dark app names appear under a heading that says dark modules. Fail if a new app is installed and the doc is not updated.

**Done when.** The drift test passes and the first screen of the doc says Python 3.13.

### D2. Backup scripts describe the same check

**Current.** The header of `scripts/backup.sh` says `scripts/check_backup_age.sh` reads `LAST_SUCCESS`. The age script does not. It uses the mtime of the newest `bizboard-*.gpg` or `*.age` file, and of `*.sql.gz` only when `BACKUP_ALLOW_UNENCRYPTED=1`. It exits 1 when that age is greater than 93600 seconds, which is 26 × 3600.

**Change.** Rewrite the `backup.sh` header so it describes the mtime check and the 93600-second threshold. Leave `LAST_SUCCESS` in place; `backup.sh` still writes it after a successful dump. Do not change retention or encryption.

**Tests.** Extend `backend/tests/test_backup_scripts.py` (or `test_backup_scripts_extra.py` if that is where the script stubs live). Assert `check_backup_age.sh` exits 0 for a fresh `.gpg` file and exits 1 when that file’s mtime is older than 93600 seconds. Follow the existing stub style.

**Done when.** Those two cases pass, and the header no longer says the age check reads `LAST_SUCCESS`.

### D3. Identity lookup refuses private addresses

**Current.** `HttpIdentityProvider._get` builds `IDENTITY_SANDBOX_BASE_URL + path` and calls `urllib.request.urlopen`. That follows redirects. It does not check the address. Resolving the name and then calling `urlopen` again would also re-resolve it (DNS rebinding).

**Design.**

- Allow `https` only. Allow `http` only when the host is `localhost` or `127.0.0.1` **and** `DJANGO_ENV` is not `production` or `staging`. In those two environments, localhost is an SSRF target, not a sandbox.
- Resolve the host. Reject the URL if any answer is loopback (except the localhost exception above), link-local, private, reserved, multicast, or unspecified. Unwrap IPv4-mapped IPv6 (`::ffff:10.0.0.1` and `::ffff:169.254.169.254`) and apply the same rules to the inner IPv4 address. Reject a literal IP in those ranges before DNS.
- Do not follow redirects. Install a handler that raises on 3xx. A public host that returns 302 to a link-local address must not be fetched. Re-validate is not enough unless every hop is checked; refusing redirects is the requirement.
- Connect to the pinned address, with the original hostname as the TLS `server_hostname` and as the `Host` header. Do not call `urlopen` on the original URL after the check. That re-resolves and re-opens the rebinding window. If pinning the IP breaks certificate verification in a way you cannot fix with `server_hostname`, stop and report. Do not ship the check-then-`urlopen` version.
- On rejection, return the existing `UNVERIFIED` / `lookup_failed` result. Do not raise into the PAN lookup caller.
- No new dependency. `ipaddress` and `urllib` are enough.

**Files.** `backend/core/services/identity_verify.py`. Cases in the existing identity test module.

**Tests.** Patch the opener and assert it was not called, or was called only with the pinned IP.

- `http://169.254.169.254/...` is not fetched.
- `https://10.1.2.3/...` is not fetched.
- `https://[::ffff:10.0.0.1]/...` is not fetched.
- `http://127.0.0.1/...` is attempted only when `DJANGO_ENV` is `test` or `development`. The same URL is not attempted when `DJANGO_ENV` is `production`.
- A 302 from a public host to `http://169.254.169.254/` is not followed.
- A public https URL is fetched once, at the pinned IP, with the original hostname as `Host`.

**Done when.** Those tests pass. No production setting defaults `IDENTITY_SANDBOX_BASE_URL`.

### S4. Rename the workflow module that is no longer stubs

**Current.** `backend/tests/workflows/test_wf_extended_stubs.py` contains real tests and no active skip.

**Change.** Rename to `test_wf_extended.py`. Update any import or doc link that names the old file (`rg test_wf_extended_stubs`).

**Done when.** `pytest backend/tests/workflows/test_wf_extended.py -q --collect-only` collects the same tests, and the old path is gone.

### D4. Known-limitations screen

**Current.** Limitations live in `docs/FREEZE_SCOPE.md` §C. The product does not show them as one page.

**Design.** A read-only route `/help/pilot-limits`, linked from the dashboard checklist and from the help drawer. English and Hindi strings in `web/src/i18n/en.ts` and `hi.ts`. Content, and no more than this:

- GSTR-1 and GSTR-3B worksheets are not filing. The CA files on the portal.
- e-invoice preview is not an IRN. Live NIC generation is off.
- Stock cost is a running weighted cost, not FIFO layers.
- Offline drafts are plaintext on the device and are wiped on sign-out.
- Books are opt-in per company.
- Online collection is sandbox until a live gateway is configured.
- Payroll, manufacturing, and CRM are not part of this pilot.

No new API. The page is static copy.

**Files.** New `web/src/pages/help/PilotLimitsPage.tsx`, a route in `web/src/App.tsx`, one link in the existing dashboard checklist (search before adding a second checklist), i18n keys, a Vitest render test that all seven statements above are visible as headings or paragraphs, and an axe entry for this route in `web/e2e/a11y.spec.ts` (serious and critical empty). The axe entry is allowed to land in U2 if Playwright is not run in this package; the Vitest test is not.

**Done when.** The Vitest test sees all seven statements. `fullParity.test.ts` still passes.

---

## Wave 2 — Auth and audit

### S1. Step-up when an already-signed-in user accepts an invite

**Current.** `AcceptInviteView`: if `mfa_is_enabled(user)` and the caller is not already that user, no session is issued. If the caller is already that user, `_tokens_for_user` runs with no fresh TOTP.

**Status code.** Do not return 401. `web/src/api/client.ts` treats 401 as “refresh the session and retry”, and `isAuthCredentialUrl` does not include `/auth/invite/accept/`. A 401 here would refresh or log the user out after a successful invite. Match `mfa_challenge_response`: **HTTP 200**, body `mfa_required: true`, no `Set-Cookie` for `bb_access` or `bb_refresh`. Add `/auth/invite/accept/` to `isAuthCredentialUrl` anyway, so a future 401 on that path cannot start a refresh loop.

**Design.** When `mfa_is_enabled(user)`, require a current TOTP or a recovery code on this request before any call that mints a session. Reuse `_check_second_factor`. Do not copy the crypto.

- Missing or wrong code: 200, `mfa_required: true`, membership still activated, no auth cookies. Include the same `mfa_token` shape as `mfa_challenge_response` so the existing second step can finish login.
- Right code: today’s success payload and cookies.
- User without MFA: unchanged.
- Replay of the TOTP on a second accept: rejected by the existing replay protection.

**Tests.** In `backend/tests/test_mfa.py`:

- Authenticated invite accept with MFA and no code → 200, `mfa_required`, no auth cookies, membership active.
- Same request with a valid TOTP → 200 and a refresh cookie.
- Replay of that TOTP → rejected, still no new session.
- User without MFA, already authenticated → session still issued.

**Web.** A unit test that a 200 body `{mfa_required: true}` from the invite URL does not call the refresh helper. Do not assert on a 401.

**Done when.** Those tests pass and `backend/tests/test_mfa.py` stays green. S2 lands in the same implementation pass (rule 1 exception).

### S2. Mandatory MFA for Owner and Accountant

**Current.** TOTP is opt-in. `MFA_ENCRYPTION_KEY` defaults to empty. `accounts.mfa._fernet` derives a key from `SECRET_KEY` when the setting is empty. `test_secret_key_rotation_keeps_old_secrets_readable` shows the setting is a comma-separated MultiFernet list, newest first. Replacing that with a new key alone makes every existing `UserMfa` secret undecryptable.

**Who is in scope.** Enforcement is on the user, not the active company. If any active membership has role `OWNER` or `ACCOUNTANT`, the user must enrol, including when they are only a viewer in a second company. Sales staff and viewers with no money-role membership are unchanged. `SwitchCompanyView` does not bypass this: it already requires a session, and it is not a login.

**Settings.** Two environment variables. Classify both in `docs/FREEZE_SCOPE.md`.

- `MFA_ENFORCE_FOR_MONEY_ROLES`. Default `0` when unset, and `settings_test.py` forces `0`. Default `1` when `DJANGO_ENV` is `production` or `staging` and the variable is unset.
- `MFA_ENFORCE_WAIVER`. Production or staging may set the enforce flag to `0` only when this is `1`. Otherwise startup raises `ImproperlyConfigured`. That check is env-only and stays in `settings.py`. It does not read the database.

`backend/.env.pilot.example` sets `MFA_ENFORCE_FOR_MONEY_ROLES=1` and comments that `MFA_ENCRYPTION_KEY` is required before the first enrolled user.

**Do not query `UserMfa` from `settings.py`.** A “any row exists” check at import time runs before the database is ready and breaks migrate. Put the ciphertext check in a Django system check tagged for `manage.py check --deploy`:

- Skip the query on `OperationalError` / `ProgrammingError` (migrations not applied).
- If enforcement is on and `MFA_ENCRYPTION_KEY` is empty, the check errors.
- If the key is set, decrypt one existing `UserMfa.secret` with the **first** key only. If that fails, the check errors and tells the operator to keep the old derived key in the comma list or to run `reencrypt_mfa_secrets`.

Dev and test keep the `SECRET_KEY` derivation so local enrolment works with an empty setting.

**Key migration, required before a production key is set.**

`accounts.mfa._fernet` already decrypts with every key in the comma list and encrypts with the first. The operator sets:

```text
MFA_ENCRYPTION_KEY=<new Fernet key>,<derived key from the current SECRET_KEY>
```

The derived key is what `_fernet` builds today: `urlsafe_b64encode(sha256("bizboard-mfa|" + SECRET_KEY))`. Document the exact expression next to the command. Do not invent a second derivation.

Add `manage.py reencrypt_mfa_secrets`. It decrypts every `UserMfa` secret with the full MultiFernet and writes it back with the first key. It refuses to run when the first key cannot decrypt a row. After it succeeds, the operator may drop the derived key from the list.

**Test.** Encrypt a secret with the derived `SECRET_KEY` key. Set `MFA_ENCRYPTION_KEY` to `new,derived`. Decrypt succeeds. Run the command. Set the setting to `new` only. Decrypt still succeeds. Set the setting to `new` only *before* the command and assert decrypt raises `ValueError`. This is the lock-out the command exists to prevent.

**Enrolment token. One design, not a choice.** Do not reuse the login `mfa_token` (`salt` `bizboard.mfa.login`). That token means “password already accepted, send a TOTP”. Issue a different signed token from `mfa_service`, salt `bizboard.mfa.enrol`, TTL 10 minutes, payload `{uid, jti}`. No cookie. Bearer auth stays disabled in production, so the token travels in the JSON body, same as `mfa_token`.

- Response when enrolment is required: **HTTP 200**, `mfa_enrollment_required: true`, `enrol_token`, `expires_in`. No auth cookies. 200 keeps the axios 401 interceptor from refreshing. 403 would also avoid that interceptor; 200 matches `mfa_challenge_response` and is what the login page should branch on.
- Allowlist, not a denylist. The token is accepted only by `POST /api/v1/auth/mfa/setup/` and `POST /api/v1/auth/mfa/confirm/`. Every other route, including `GET` and `POST /api/v1/sales/invoices/`, ignores it and returns 401 or 403 as that route already does for an anonymous caller.
- Rate limit those two posts with the existing `login` throttle.
- The token may be presented until confirm succeeds or the TTL ends. Cap presentations at 8 via the cache, keyed by `jti`. Confirm deletes the `jti`. Setup may be called more than once before confirm; `test_restarting_setup_replaces_the_secret` already depends on that.
- After confirm, the client signs in again with password + TOTP. The enrol token does not become a session.

**Where the gate runs.** These are the session issuers. A test must list them by reading the source of `accounts/views.py` and `accounts/mfa_views.py` and failing if a new call to `_tokens_for_user` or `_complete_login` appears without being in this table.

| Issuer | Gate |
|---|---|
| `LoginView` | Enrolment response instead of `_complete_login` when the user is a money role without MFA. Existing MFA challenge stays when MFA is already on |
| `MfaLoginVerifyView` | Unchanged. It only runs after enrolment |
| `VerifyOtpView` | Same enrolment response. OTP alone must not call `_tokens_for_user` for a money role without MFA |
| `AcceptInviteView` | S1 step-up when MFA is on. Enrolment response when the flag is on and MFA is off |
| `CookieTokenRefreshView` | If the flag is on and the user is a money role without MFA: do not mint new tokens, blacklist the presented refresh token, return 200 with `mfa_enrollment_required` and an `enrol_token`. Do not return 401 |
| `SwitchCompanyView` | No extra gate. The caller already has a session |
| `RegisterView` | No session today. Leave it that way |
| `ConfirmPasswordResetView` | No session today. Leave it that way |

**Already-issued sessions.** Do not mass-revoke on deploy. An access cookie remains valid until its 15-minute lifetime. The next refresh hits the gate above. Do not add a membership query to every authenticated request in this package. State that 15-minute window in `backend/.env.pilot.example`.

**Lost device.** In-product recovery already exists: codes issued at confirm, and `MfaRecoveryCodesView` regenerates them when the user still has password plus TOTP or a remaining code. That does not help a sole owner who has lost both the phone and the codes. Add `manage.py reset_user_mfa --email`. It deletes that user’s `UserMfa` row, blacklists their `OutstandingToken` rows, and writes an audit event. It is a host command, not an API. There is no second owner who can click “reset MFA” in the UI. Document the command in the pilot env example. After it runs, enforcement sends the user through enrolment again on the next login.

**Do not** enrol MFA inside `seed_demo`. Add one README sentence: the pilot profile demands TOTP for the owner; `seed_demo` does not.

**Tests.**

- Flag off: owner password login still sets cookies.
- Flag on, owner, no MFA: 200, `mfa_enrollment_required`, no cookies.
- Flag on, accountant: same.
- Flag on, user who is owner in company A and viewer in company B: same.
- Flag on, sales staff with no money-role membership: cookies issued.
- Flag on, owner, MFA confirmed: password alone does not set cookies; password + TOTP does.
- Production with the flag forced off and no waiver: `ImproperlyConfigured` from settings, no database.
- `check --deploy` errors when enforcement is on and `MFA_ENCRYPTION_KEY` is empty.
- Enrol token rejected on `GET` and `POST /api/v1/sales/invoices/`.
- Enrol token accepted on setup and confirm, rejected on the 9th presentation, rejected after confirm.
- `CookieTokenRefreshView` for a money role without MFA returns 200 `mfa_enrollment_required` and that refresh token cannot be used again.
- The source enumeration test fails if a new `_tokens_for_user` or `_complete_login` call is added outside the table.
- The re-encrypt test in the key-migration section.

**Web.** Login page: an `mfa_enrollment_required` body opens the existing enrolment panel. Refresh helper: a refresh response with that code clears the session state and shows the panel, and does not retry the refresh. Vitest both with mocked responses. Do not restyle.

**Stop.** Rule 3. If any pre-existing test fails, stop.

**Done when.** The tests above pass, `pytest backend/tests/test_auth.py backend/tests/test_mfa.py backend/tests/test_mfa_edge_cases.py -q` passes, and `python scripts/ci_gates/run_guards.py` passes.

### S3. Audit tip file

**Current.** `audit_chain.verify` walks sealed rows in `chain_seq` order. It reports a bad content hash, a gap, or a bad `chain_prev`. It starts `expected_seq` at 1. Deleting the last sealed row leaves a shorter chain that is still contiguous, so `verify` returns ok. That is the tail-truncation hole. Confirmed in `_verify_one`. Do not change that function’s meaning; add a tip comparison beside it.

**Threat model.** The tip file detects “the row we exported is no longer the row at that seq” and “the chain got shorter than the file”. If the file sits on the same host as the database, someone who can delete audit rows can rewrite the file too. This package does not copy the file offsite (`F-REL-01` is out of scope). Say that in the command’s help text. The control is weak until the file is stored elsewhere. Still build it; a later offsite job has something to copy.

**Check, not an equality of current tips.** Events sealed after export move the tip. A new company appears after export. Neither is tampering.

For each company in the file:

- The database has a sealed row with `chain_seq == file.max_seq` and `chain_hash == file.tip_hash`.
- The company’s current max `chain_seq` is greater than or equal to `file.max_seq`.

A company present in the file and missing from the database is a failure. A company present in the database and absent from the file is a warning on stdout. `--strict` turns that warning into a failure. Default is warning, so onboarding a tenant does not fail the nightly check.

**Commands.**

- `manage.py export_audit_tip --out PATH` writes `{ "companies": [ {"id", "max_seq", "tip_hash"} ] }`, sorted by id, mode `0600` on POSIX. Refuse to write if `audit_chain.verify` is not ok.
- `manage.py verify_audit_chain --tip PATH` runs the existing verify, then the comparison above. `--strict` as described. A mismatch names the company id, the file seq, and both hashes.

**Tests.** In `backend/tests/test_audit_chain_edge_cases.py`:

- Seal two events, export, seal a third, `verify --tip` succeeds (the file’s row is still there, max seq moved forward).
- Delete the later of the two exported rows under `audit_maintenance`. Plain `verify` succeeds. `verify --tip` fails.
- A tip file whose hash does not match that seq fails.
- A new company with a sealed row, absent from the file: default command exits 0 and prints a warning; `--strict` exits non-zero.

**Done when.** Those four tests pass on SQLite. If Postgres is up, also run the existing trigger tests in that module.

---

## Wave 3 — Usability of the money screens

### R1. Postgres for the race tests, without breaking laptop SQLite

**Current.** `backend/config/settings_test.py` deletes `DATABASE_URL` unless `CI=1` or `PYTEST_KEEP_DATABASE_URL=1`, on purpose, because a leftover Postgres client deadlocks pytest. Concurrency tests are `pytest.mark.postgres` and skip on SQLite.

**Do not** make Postgres the default local database. That fights the deadlock guard and makes every unit test need Docker.

**Change.**

- The primary script is `scripts/test_postgres.ps1`. This machine is Windows. The script sets `PYTEST_KEEP_DATABASE_URL=1` and `DATABASE_URL` (parameter, else `postgresql://bizboard:bizboard@127.0.0.1:5432/bizboard_test`) and runs pytest with the remaining arguments.
- `scripts/test_postgres.sh` is the same contract for Linux CI and for a developer who has a POSIX shell. It is not the script this workstation runs. Do not require Git Bash.
- README “Verification”: on Windows, money and stock changes use the PowerShell script. SQLite remains the default for a fast local run.
- Add `backend/tests/test_postgres_marker_collected.py`, marked `postgres`, which asserts `connection.vendor == "postgresql"`. On SQLite the existing skip is enough. In CI the backend job already uses Postgres; this test fails the job if someone later skips the marker globally.
- Confirm `.github/workflows/ci.yml` does not pass `--ignore` on `test_concurrency_races.py`. If it does, remove that ignore. Do not add a new job.

**Done when.** `powershell -File scripts/test_postgres.ps1 -q --collect-only backend/tests/test_postgres_marker_collected.py` collects the test when Postgres is configured, or prints the script’s own “database unreachable” error without claiming the marker ran. A local `pytest` with no `DATABASE_URL` still skips postgres tests. The README names the `.ps1` first.

### U1. Unsaved-changes guard on the remaining money editors

**Current.** `UnsavedChangesGuard` is already on `NewInvoicePage`, `NewPurchasePage`, `SalesOrderEditorPage`, `PurchaseOrderEditorPage`, `PurchaseNoteEditorPage`, `SalesInvoiceNoteEditor`, plus several settings pages. It is absent from:

- `web/src/pages/sales/DeliveryChallanEditorPage.tsx`
- `web/src/pages/sales/ReceiptsPage.tsx`
- `web/src/pages/purchases/SupplierPaymentsPage.tsx`
- `web/src/pages/sales/SalesReturnsPage.tsx`
- `web/src/pages/purchases/PurchaseReturnsPage.tsx`

**Design.** Same component, same `when` rule as the sales order editor: dirty when the form has a party or a line or a non-zero amount the user typed, and not dirty after a successful save or when the dialog is closed. Copy the `skipLeaveGuard` pattern from `SalesOrderEditorPage` so a successful navigate does not prompt.

Receipts and payments are dialogs on list pages. Guard route changes while the dialog is open and dirty. Closing the dialog with dirty state uses the same confirm the guard already shows; do not invent a second modal.

**Tests.** A Vitest per page, following `UnsavedChangesGuard.test.tsx` and `NewPurchasePage` tests: dirty form sets `when` true; saved or empty form sets `when` false. Do not start Playwright for this package.

**Done when.** Those five pages render the guard, the new unit tests pass, and `npm run test:run -- src/components/UnsavedChangesGuard.test.tsx` still passes.

### U2. Axe on the freeze-scope money routes

**Current.** `web/e2e/a11y.spec.ts` already covers login, dashboard, `/sales/new`, `/pos`, `/reports/profit-loss`, `/settings/company`, `/purchases/new`, `/sales/history`, `/inventory/stock`, `/settings/items`, `/settings/users`, `/settings/billing`, `/inventory/stock-counts`.

**Add** to that same loop, no new harness:

| Name | Path |
|---|---|
| Receipts | `/sales/receipts` |
| Supplier payments | `/purchases/payments` |
| Sales returns | `/sales/returns` |
| Purchase returns | `/purchases/returns` |
| Customer ledger | `/reports/customer-ledger` |
| Supplier ledger | `/reports/supplier-ledger` |
| Pilot limits | `/help/pilot-limits` (after D4) |

**Fix loop.** When a route reports a serious or critical violation, fix that screen (label, name, heading, contrast). Do not add `disableRules` and do not drop `wcag2aa`. A violation that is a pre-existing MUI false positive gets a one-line comment and an `exclude` scoped to that node, with the rule id in the comment. Cap excludes at the node that failed. If a route needs more than three excludes, stop and report it; do not blanket-disable.

**Keyboard.** Add one test to `web/e2e/pos-keyboard-checkout.spec.ts`: from a fresh POS screen, using only the keyboard, add one item, choose cash, confirm, and assert the success state the spec’s existing backend (mock or golden) already shows for a paid sale. Do not add a live gateway. If that backend cannot complete a cash sale, stop and report the missing fixture. Do not skip the test in silence and do not mark the package done.

**Touch targets.** For the primary button on `/sales/new`, `/purchases/new`, and `/pos`, assert the bounding box is at least 44 by 44 CSS pixels. That is an internal Bizboard bar for counter use. It is stricter than WCAG 2.2 AA success criterion 2.5.8 (24 by 24 CSS pixels). Do not describe the assertion as a WCAG conformance claim. Fix the button sizing if it fails. Do not restyle the whole page.

**Done when.** `npm run test:e2e -- e2e/a11y.spec.ts` passes on Chromium. WebKit is already selected for this file by `playwright.config.ts`; run that project too if it is cheap, and record a skip reason if the machine has no WebKit.

### U3. Hindi and empty/error/loading on the money screens

**Current.** `web/src/i18n/fullParity.test.ts` requires every English leaf in Hindi. `web/src/i18n/jsxLiteralRatchet.test.ts` scans 22 files for hard-coded English between JSX tags.

**Change.**

- Add the five pages from U1, plus `ReceiptsPage`’s dialog component if the strings live in a child, to the `SWEPT` array.
- Move each new hit onto `en.ts` and `hi.ts`. Brand names stay in the `ALLOWED` set.
- For each of those pages, if the list fetch has no loading indicator, no error message, or an empty state that is a blank table, use the existing `EmptyState` component and the existing query `isLoading` / `isError` pattern from `CustomersPage`. Do not add a new empty-state component.
- Hindi strings: a fluent equivalent, not a transliteration of the English key. If a GST term has a standard Hindi form already in `hi.ts`, reuse it.

**Done when.** `npx vitest run src/i18n/jsxLiteralRatchet.test.ts src/i18n/fullParity.test.ts` passes, and each swept money page has a unit test or an existing test that shows the empty title when the list is `[]`.

---

## Wave 4 — Measurement

These produce evidence files. They do not change product behaviour except where a bug is found, and that bug becomes its own fix with a test.

### M1. Dashboard budget on a non-trivial fixture

**Current.** `backend/tests/test_qos0016_dashboard_budget.py` exists. QOS-0016 is still open, which means the test is not yet a budget against a year of data.

**Change.** Read the test. Seed completed invoices through the service layer, call the dashboard, and assert:

- response 200 at 100 invoices and at 300 invoices
- the query count at 300 is less than twice the query count at 100 (an N+1 would roughly triple). Record both counts in comments
- a sanity ceiling of the 300-invoice count plus 10 percent, so a later absolute blow-up still fails
- the payload’s receivables total equals the sum of open invoice outstanding

Do not assert wall-clock milliseconds. Timing belongs to M4.

**Done when.** The test passes on SQLite and, via `scripts/test_postgres.ps1`, on Postgres. Update `qos/backlog/QOS-0016.yaml` only to point at the test name. Do not mark the QOS item `fixed`; a co-located timing run is M4 and is not an SLO.

### M2. Migration rehearsal on `seed_load_tenant`

**Current.** `seed_load_tenant` refuses to run unless `DJANGO_ENV` is `staging` or `test`, and it refuses production. `load/SEED_50K.md` already names it.

**Change.** Do not migrate to N−1 and then seed with current models. If the latest migration alters a column the seeder writes, that seed fails or writes the wrong shape. Seed with the old code, then migrate with the new code.

`scripts/migration_rehearsal.ps1` (PowerShell first; a `.sh` twin is optional):

1. Create a throwaway Postgres database. Refuse to run if the URL’s database name does not contain `rehearsal`.
2. Resolve the old tree. Prefer the latest git tag. If there is no tag, use commit `5deafb2` (the commit this plan was written against). Add a git worktree at that revision. Do not seed from the dirty working tree.
3. In that worktree, with `DJANGO_ENV=test` and the throwaway `DATABASE_URL`, run `migrate`, then `seed_load_tenant --invoices 2000`. 2000, not 50000.
4. In the new tree (the tree under test), point at the same database, run `migrate`, then `check_invariants`.
5. Drop the database and remove the worktree.

The script exits non-zero on any step. If the old revision cannot import because the working tree’s dependencies moved, stop and report. Do not point the old code at the new tree’s `models.py`.

**Done when.** One successful run is pasted into `docs/roadmap/ticket-logs/X-01.md` under a dated “migration rehearsal” heading: old revision, new revision or “dirty tree” plus the P0 fingerprint, invoice count, and the invariant line. Do not commit a SQL dump.

### M3. Bill-extraction accuracy figure

**Current.** `backend/tests/accuracy/test_bill_accuracy_scoring.py` pins the scorer and runs in the default suite. `test_llm_bill_extraction_accuracy.py` is marker `llm_accuracy`, floor `0.70`, and skips without a key and a corpus. Corpus notes are in `backend/tests/fixtures/bill_accuracy_corpus/README.md`.

**Change.**

- If the corpus has no real bill images, do not call an API and do not fake a score. Add a checked-in `backend/tests/fixtures/bill_accuracy_corpus/SCORE.md` that says **not run** and why (missing images or missing key). That is an honest result, and the package is still done.
- If images and `OPENAI_API_KEY` (or the configured `LLM_PROVIDER` key) are present, run:

```text
pytest backend/tests/accuracy/test_llm_bill_extraction_accuracy.py -m llm_accuracy -q
```

Write the accuracy, the case count, the model name, and the date into `SCORE.md`. Do not lower `ACCURACY_FLOOR` to make it pass. A miss stays a miss, with the number.

**Done when.** `SCORE.md` exists and either contains a measured fraction or the explicit not-run reason. The scorer tests still pass.

### M4. k6 SLO run, recorded whether it passes or not

**Current.** `load/k6_slo.js` thresholds: complete p95 &lt; 800 ms, list p95 &lt; 2 s, dashboard p95 &lt; 500 ms. `load/results/` is gitignored. `load/SEED_50K.md` says a laptop failure is not a pass and is not a reason to hide the file. `seed_draft_pool` must supply fresh drafts or Complete measures a 400.

**Change.**

1. Start compose Postgres and the API against it. `DJANGO_ENV=test` is acceptable for this evidence run. Do not point at a database that has real GSTINs.
2. `python manage.py seed_load_tenant --invoices 10000` if the machine can finish it in a reasonable time. If it cannot, seed 1000 and write the actual count in the log. Never label a 1000-invoice run as a 50k run.
3. `python manage.py seed_draft_pool --count 700` and pass `DRAFT_INVOICE_IDS` into k6.
4. `k6 run --out json=load/results/slo-YYYYMMDD.json load/k6_slo.js` with `BASE_URL`, `EMAIL`, `PASSWORD`.
5. Append a table to `docs/roadmap/ticket-logs/X-01.md`: date, SHA plus the P0 fingerprint if the tree is dirty, invoice count, VU and duration, p50/p95/p99 for complete, list, and dashboard, error rate, and pass or fail per threshold.
6. On the same row record machine CPU and RAM, `GUNICORN_WORKERS`, and whether k6 ran on the same host as Postgres and the API. A run where all three share one machine is labelled **functional smoke, not an SLO result**. Do not quote it against the 800 ms / 2 s / 500 ms targets. Those targets stay in `k6_slo.js` so the script still fails closed; the ticket log is what says the failure is not evidence of production latency.

**Done when.** That table is in `X-01.md`, the co-location label is present, and the JSON is under `load/results/`. A failed threshold is a successful package. Do not change gunicorn workers or indexes inside this package.

---

## Wave 5 — Final gate

### G1. Prove the tree

Run, in order, and stop on the first failure:

1. `python scripts/ci_gates/run_guards.py` and `--selftest`.
2. `powershell -File scripts/test_postgres.ps1` for the full suite from a clean database (`--create-db`). This is `F-TEST-02`. On a Linux CI runner the `.sh` twin is acceptable; on this workstation use the `.ps1`.
3. `cd web && npm run test:run`.
4. `scripts/image_smoke.sh` against a locally built API image and a throwaway Postgres, through gunicorn health. The script already implements that sequence. The 2026-10-02 log stopped early because Postgres was busy. Run it when the suite is finished, not during it.
5. Write the pytest totals, the image-smoke `IMAGE SMOKE OK` line, `git rev-parse HEAD`, and a fresh dirty-tree fingerprint in the same form as P0 into `docs/reviews/ISO25010_REMEDIATION_LOG_2026-10-02.md` §3a as the **final** run. Keep the baseline subsection.

**Triage, because P0 does not fix failures and this gate wants a clean suite.** For each node id that failed in the baseline and still fails:

- Fix it if a package in this plan caused it, with a regression test.
- Or `xfail` it with a reason that names an existing QOS id or finding id, and a one-line cause. Do not xfail without that id.
- Or list it under **G1 blockers** with an owner (package id or “pre-existing, not in this plan”).

A failure in none of those three states means G1 is not done. Do not delete the test.

**Done when.** Guards are green, every remaining failure is either absent or on the G1 blocker list with an id, web unit tests are green, and image smoke prints `IMAGE SMOKE OK`. “0 failed” is the target. A non-empty blocker list is an honest finish only when each row has an id. An empty unexplained failure list is not.

---

## Commit slices

Use these only when the operator asks for commits. Implement each package on its own first (rule 1). The bundles below are commit groupings of finished work, except slice 4, which is also implemented as one change because S1 and S2 share `AcceptInviteView`.

| Slice | Packages | Message focus |
|---|---|---|
| 1 | D1, D2, S4 | Docs and backup comment match the code |
| 2 | D3 | Identity client pins the address and refuses redirects |
| 3 | S3 | Audit tip detects a deleted tail and allows a later seal |
| 4 | S1, S2 | Exception to rule 1. Money roles must enrol; invite accept steps up; key re-encrypt command |
| 5 | D4 | In-app pilot limitations page, seven statements |
| 6 | R1 | Windows Postgres test script; SQLite remains the local default |
| 7 | U1 | Unsaved-changes guard on challan, receipts, payments, returns |
| 8 | U2, U3 | Axe, internal 44px target, keyboard checkout, Hindi |
| 9 | M1, M2, M3 | N+1 dashboard guard, old-code migration rehearsal, accuracy score file |
| 10 | M4, G1 | Smoke-labelled k6 numbers and the triaged suite log |

## Risks the agent must not “solve” by skipping

| Risk | What to do |
|---|---|
| S2 turns a pre-existing test red | Stop. Rule 3. Rollback is `MFA_ENFORCE_FOR_MONEY_ROLES=0` plus `MFA_ENFORCE_WAIVER=1`. Do not xfail the old test inside S2 |
| S2 production key cannot decrypt old secrets | Keep `new,derived_old` until `reencrypt_mfa_secrets` has run. Do not drop the derived key first |
| Sole owner loses phone and recovery codes | `reset_user_mfa --email` on the host. Do not add an in-app reset that skips the second factor |
| U2 axe fails on a third-party widget | One scoped exclude with the rule id, or stop and report. No global disable |
| M4 misses 800 ms on a shared laptop | Label it functional smoke. Do not drop the threshold in `k6_slo.js` and do not add indexes |
| M3 has no API key | Write “not run” in `SCORE.md`. Do not stub the model |
| `seed_load_tenant` refuses the env | Set `DJANGO_ENV=test`. Do not weaken the production refusal |
| M2 old revision cannot import | Stop and report. Do not seed with the new models against an old schema |
| Image smoke and pytest fight over Postgres | Sequence them. Do not point image smoke at the pytest database |
| Either new MFA setting missing from `FREEZE_SCOPE.md` | `run_guards.py` fails. Classify both in the S2 change |
| Baseline failures and G1’s clean-suite line | Triage in G1: fix, `xfail` with an id, or a named blocker. P0 does not fix them |

## Exit

This plan is finished when G1’s done line is true and slices 1–8 are in the tree (committed or not). Slices 9–10 may record a measured miss, a smoke label, or a “not run” and still count as finished. The pilot is still not generally releasable: TLS, an offsite copy of the audit tip, the user study, and the CA letter remain outside this plan. The tip file on the same disk as the database is not that offsite copy.

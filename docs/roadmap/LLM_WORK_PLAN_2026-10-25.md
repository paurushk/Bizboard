# Readiness items an LLM can close or move forward: implementation plan (2026-10-25, rev 2)

**Scope.** Of the 105 open rows in `docs/Bizboard_SaaS_Readiness_Checklist.xlsx` (85 In Progress,
18 Blocked, 2 Not Started), these are the ones where the remaining work is writing, building or
testing that can be done without a host, a CA, counsel, a provider account or real users. Each work
package (WP) says what already exists, so nothing is built twice, and exactly what stays for a
person afterwards.

**Rev 2** takes in the plan review of the same day. All points were checked against the repo; see
§ "Review changes" at the end for what changed and the two points that were adjusted.

**Ground rules (from earlier decisions).**
- Nothing is committed until the founder says so (D-06, D-12). WP-8 is the commit itself.
- Test credentials are used only against local staging (`http://127.0.0.1:8081`).
- `.env.staging`, `.env.glitchtip`, phone numbers and the ntfy topic stay out of git.
- Every WP ends by updating the sheet row's note, the decision log if a decision was taken, and
  the memory file.

## 0. Decisions needed before starting

| # | Question | Needed for | Default if not answered |
|---|---|---|---|
| Q-A | May I download the OWASP ZAP scanner image (`ghcr.io/zaproxy/zaproxy:stable`, the image CI already uses; roughly 1.5–2 GB)? | WP-1 | WP-1 runs only the scanners already installed (pip-audit, npm audit) and the tenant probe |
| Q-B | Which hosting provider should the setup guide target (e.g. AWS Mumbai, DigitalOcean Bangalore, Azure Central India, E2E Networks)? | WP-4 | Write only the provider-neutral parts (VM bootstrap, preflight check) |
| Q-C | Lift the "referral after launch" deferral (G-03) so BB-139 can be built now? | WP-7 | WP-7 is skipped |
| Q-C2 | If yes: what is the reward? (a) free days added to the referrer's next renewal, (b) a money credit against the next renewal, which needs a GST credit note, (c) recorded only, and the founder settles it by hand | WP-7 | (c): record only, no reward mechanism built |
| Q-D | Commit go-ahead? | WP-8 | WP-8 waits (as D-12) |
| Q-E | May I download Prometheus and Alertmanager images (roughly 300 MB together) to test the alert rules on local staging? | WP-6 | WP-6 tests only the alert paths already running locally (GlitchTip uptime monitor, in-app watchers); the Prometheus rules wait for the host |

## 1. Summary

| WP | Rows | Result for the row | Size | Needs |
|---|---|---|---|---|
| WP-0 Sheet corrections | BB-004, BB-090, BB-093 | Notes made accurate; no status change | 15 min | — |
| WP-1 Local security scan and pentest brief | BB-045, BB-144, BB-029, BB-143 | Moved forward | 1–1.5 days | Q-A (partly) |
| WP-2 DPIA draft | BB-123, BB-047 | Moved forward | 0.5 day | — |
| WP-3 Vendor contract checklist | BB-129 | Moved forward | 0.5 day | — |
| WP-4 Hosting setup kit | BB-080, BB-081, BB-082, BB-085, BB-087, BB-089 | Moved forward | 1–1.5 days | Q-B (partly) |
| WP-5 PgBouncer wiring | BB-068 | Moved forward | 1 day | — |
| WP-6 Local incident drill kit | BB-099, BB-149, BB-051, BB-093 | Moved forward | 1–1.5 days | Q-E (partly) |
| WP-7 Bizboard referral programme | BB-139 | **Closable** (behind a flag) | 2–2.5 days | Q-C, Q-C2 |
| WP-8 Commit and CI | BB-017 (closable); BB-141 (CI half) | BB-017 **closable** once CI is green | 1 day plus CI fixes | Q-D |

**Correction to the earlier list:** BB-004 is not an LLM item. The consolidated requirements
document already exists (`docs/requirements/REQUIREMENTS_BASELINE.md`, sign-off pack §B-14). It
needs only the founder's signature.

**Order:** WP-0 → WP-5 → WP-1 → WP-6 → WP-7 (if Q-C) → WP-2 → WP-3 → WP-4 → WP-8 (if Q-D).
- WP-5 comes early, so WP-1 and WP-6 run on the stack that will be deployed.
- WP-7 comes before WP-2, so the DPIA already covers the new referral data. If WP-7 is skipped,
  or done later, WP-2's data list must be updated when it lands.

---

## WP-0 Sheet corrections (15 min)

| Row | Current note says | Correct to |
|---|---|---|
| BB-004 | "Spread across freeze scope, plans and tests" | Baseline consolidated in `docs/requirements/REQUIREMENTS_BASELINE.md` (sign-off pack B-14); awaiting founder signature |
| BB-090 | "No Sentry project/DSN" | Self-hosted GlitchTip integrated and tested on local staging (`docs/ops/GLITCHTIP.md`); left: run it on the host and set the DSNs |
| BB-093 | "No receiver/on-call phone" | Receiver chosen (D-02: founder email + ntfy phone push); left: a backup on-call person and a live alert test on the host |

Keep the earlier notes; add these as dated entries. No status change.

**Done when:** the three notes are added and the counts are unchanged.

---

## WP-1 Local security scan and pentest brief (1–1.5 days)

**Rows:** BB-045 (SQLi/XSS/CSRF/authorization), BB-144 (critical vulnerabilities), BB-029 and
BB-143 (cross-tenant). None of these can be closed without an independent pentest on the hosted
server. This WP finds and fixes what an automated scan can find first.

**Already in place:**
- A CI `zap` job, skipped while `STAGING_BASE_URL` is unset.
- `pip-audit` and `npm audit` in CI, plus the supply-chain job.
- Cross-tenant endpoint tests (`backend/tests/tenancy/test_endpoint_isolation.py`).
- `docs/ops/STRIDE.md`.

**Things the scan must work around on local staging:**
- **Reaching the app from the container.** Inside the ZAP container, `127.0.0.1` is the container
  itself. Target `http://host.docker.internal:8081`, and add `host.docker.internal` to
  `DJANGO_ALLOWED_HOSTS` in the local `.env.staging` for the run only. That file is not committed;
  put it back afterwards.
- **Sign-in is cookie-only on staging (BB-000547).** A Bearer token is refused. Every request
  needs the `bb_access` cookie, and every POST, PUT, PATCH and DELETE needs the `csrftoken` cookie
  and a matching `X-CSRFToken` header. The active company comes from the session or `X-Company-Id`.
  - Use ZAP's script-based authentication: sign in through the real login endpoints, keep the
    cookies, and send the CSRF header on unsafe methods.
  - Re-authenticate when a response comes back 401.
  - Check before scanning: a sample PATCH must return something other than "403 CSRF Failed".
    Otherwise the scan would only test the CSRF check.
- **The active scan writes data.** Run it against a dedicated throwaway tenant. Take a `pg_dump`
  of the local staging database before the scan, and restore it afterwards.

**Steps**
1. **Passive baseline scan** (Q-A): `zap-baseline.py -t http://host.docker.internal:8081`. It finds
   missing headers, cookie flags, information leaks and mixed content.
2. **API scan with a signed-in user** (Q-A):
   - run `zap-api-scan.py` with `docs/openapi-snapshot.json` as the definition, using the
     authentication above;
   - limit it to `/api/v1/`;
   - exclude logout, erasure, ownership transfer, billing, and other destructive or external-call
     endpoints, using a context file at `scripts/security/zap/`. The file holds paths only, no
     credentials.
3. **Cross-tenant probe** (`scripts/security/tenant_probe.py`; needs no download). It signs in as
   the tenant A and tenant B test owners, through nginx and gunicorn, with the real app database
   role and RLS on, then checks:
   - **Detail reads:** for every GET path with `{id}` or `{pk}`, request B's object IDs as A.
     Expected: 404.
   - **List filters:** list endpoints with B's IDs in query filters (`?customer=`, `?invoice=`,
     `?product=`, `?company=` …). Expected: an empty list or 400/404, never B's rows.
   - **IDs injected into writes:** POST or PATCH, on A's own draft objects, a body that refers to
     B's customer, product, godown or invoice IDs. Expected: 400/403/404, with nothing saved.
     Non-destructive actions only (drafts, then deleting the draft); destructive endpoints are skipped.
   - Any 200 that returns B's data, or any write that is accepted, is a Sev-1 finding.
4. **Dependency check:** run `pip-audit` and `npm audit --omit=dev` locally.
5. **Triage:** each finding is fixed with a test, accepted with a reason (for example "local HTTP;
   TLS is at the edge"), or left to the pentest. Regenerate the OpenAPI snapshot if the API changes.
6. **Pentest brief** (`docs/security/PENTEST_SCOPE.md`):
   - targets, one test login per role, and the two test companies;
   - the sign-in model (cookies plus CSRF);
   - what is out of bounds: real payment and SMS calls, and load;
   - focus areas: tenant isolation, the RLS role, authorization by role, file upload and download,
     public share links, webhooks, the browser error relay, rate limits behind the proxy, two-step sign-in;
   - accepted risks, the reporting format (CVSS score, steps to reproduce) and retest terms.

**Files:**
- New: `scripts/security/zap/` (context and authentication script), `scripts/security/tenant_probe.py`,
  `docs/security/LOCAL_SCAN_2026-10-xx.md`, `docs/security/PENTEST_SCOPE.md`.
- Changed: code touched by the fixes.

**Done when:**
- with Q-A, the baseline and API scans have run with authentication confirmed working;
- every High and Medium finding is fixed or accepted with a reason;
- the tenant probe shows 0 cross-tenant reads and 0 accepted writes with B's IDs;
- the database is restored after the scan;
- the brief is written and the notes for BB-045, BB-144, BB-029 and BB-143 are updated.

**Still for people:** the pentest on hosted staging, and fixing what it finds.

---

## WP-2 DPIA draft (half a day)

**Rows:** BB-123 (Indian data-protection duties), BB-047 (protect financial and personal data).

**Already in place:**
- `docs/pilot/DPDP_POSTURE.md`, which says it is not a DPIA.
- `docs/ops/PRODUCT_BEHAVIORS_FOR_COUNSEL.md`, `DATA_CATEGORIES.md`, `SUBPROCESSORS.md`,
  `STRIDE.md`, `DATA_RETENTION.md`, `ERASURE_PLAYBOOK.md`, `DPDP_REQUESTS.md`.
- The legal drafts in `docs/legal/drafts/`.

**Steps:** write `docs/legal/drafts/DPIA_DRAFT.md`:
1. **Whether a DPIA is legally required.** Under the DPDP Act it is a duty of a *Significant Data
   Fiduciary*; whether Bizboard is one is for counsel. Bizboard has two roles: fiduciary for its own
   users' data, and processor for its customers' customer and supplier records.
2. **Processing description:** data categories and where they are stored (from
   `DATA_CATEGORIES.md`, including the referral data if WP-7 has landed), purposes, lawful basis,
   in-tenant access by role, and Bizboard staff access through the support-access grant.
3. **Data flows:** browser and mobile app → API → Postgres, Redis, object storage and backups,
   then each subprocessor and what it receives.
4. **Risks:** likelihood, impact, existing controls (with file references) and remaining risk. The
   list covers:
   - cross-tenant leak;
   - account takeover;
   - insider access;
   - backup theft;
   - over-retention (D-13);
   - error-report leakage;
   - AI features (consent toggle, off by default);
   - children's data (not expected; B2B);
   - transfer outside India (depends on the host region; Q-B);
   - referral attribution, if WP-7 is built.
5. **Rights handling** (`DPDP_REQUESTS.md`) and **breach response** (CERT-In 6-hour report,
   notice to affected people, `INCIDENT_RESPONSE.md`).
6. **Open points for counsel**, and a sign-off block.

**Done when:** the draft is complete, every control it cites exists in the repo (checked by grep),
the data categories match `DATA_CATEGORIES.md`, and the BB-123 and BB-047 notes are updated.

**Still for people:** counsel decides whether a DPIA is mandatory and approves the text.

---

## WP-3 Vendor contract checklist (half a day)

**Row:** BB-129.

**Already in place:** `docs/ops/SUBPROCESSORS.md`, `docs/ops/VENDOR_SLA.md`,
`docs/legal/drafts/DATA_PROCESSING_AGREEMENT_DRAFT.md`.

**Steps:** write `docs/legal/drafts/VENDOR_CONTRACT_CHECKLIST.md`.
1. One row per vendor that is live at launch; the rest are marked "dark, not needed at launch".
   - Razorpay (subscriptions).
   - The email (SMTP) provider.
   - The SMS provider.
   - The host (Q-B).
   - The backup storage account.
   - Cloudflare, if used.
   - GlitchTip: self-hosted, so not a subprocessor. Record that.
2. Columns:
   - whether a standard DPA is offered, and where to find it (no guessed URLs);
   - data sent;
   - data location;
   - breach-notice timeline, which must allow the 6-hour CERT-In report;
   - notice of sub-processor changes;
   - deletion at contract end;
   - audit and certification (ISO 27001, SOC 2, PCI DSS for payments);
   - uptime SLA and credits;
   - liability cap;
   - termination and data return;
   - jurisdiction;
   - status.

   Each column has a "what good looks like" line for the first pass.
3. A section mapping the customer DPA draft's promises (breach notice, sub-processor list,
   deletion) to the vendor terms that must support them.

**Done when:** the checklist is complete for the launch vendors and the BB-129 note is updated.

**Still for people:** collect the vendors' actual terms, and counsel's review.

---

## WP-4 Hosting setup kit (1–1.5 days)

**Rows:** BB-080, BB-081, BB-082, BB-085, BB-087, BB-089. All stay open until the host exists. This
WP turns setting up the host into copy-and-run steps, with a check at the end.

**Already in place:**
- `docs/ops/HOSTED_STAGING.md`, the provider-neutral steps.
- `docker-compose.prod.yml`, `docker-compose.cloudflared.yml`, `docker-compose.rollback.yml`.
- `.github/workflows/cd.yml`, plus `deploy-staging.yml`, which is bound to the `staging`
  environment and already reads `STAGING_SSH_HOST`, `STAGING_SSH_USER`, `STAGING_SSH_KEY` and
  `STAGING_DIR` from its secrets.
- `scripts/staging-db-role.sh`, `db-app-role.sh`, the backup scripts, `deploy/prometheus/`.

**Steps (provider-neutral):**
1. `scripts/host/bootstrap_vm.sh` (Ubuntu LTS). It sets up:
   - a non-root deploy user and SSH keys only;
   - `ufw` allowing only 22 and 443 (or nothing public with a Cloudflare tunnel);
   - unattended security updates;
   - Docker Engine and the compose plugin from Docker's apt repository;
   - time sync, swap, and a log rotation limit.

   It is safe to re-run, and read-only with `--check`. **Docker bypasses ufw:** a container that
   publishes `0.0.0.0:<port>` is reachable whatever ufw says. The script therefore sets
   `APP_BIND=127.0.0.1` for every published port and documents why. It does not edit Docker's
   iptables chains.
2. `scripts/host/render_env.sh`: builds `.env` from the provider's secret store at deploy time.
   One adapter per provider, plus a plain-file fallback for the first staging.
3. `scripts/host/preflight.py` prints PASS or FAIL for each item.

   *Configuration and database:*
   - the required variables from `HOSTED_STAGING.md` §2 are set, and `DJANGO_ENV` is right;
   - the app connects as the NOSUPERUSER NOBYPASSRLS role, with `POSTGRES_RLS_ENABLED=1`;
   - migrations are at head;
   - `SHOW statement_timeout` is `30s` on the app connection (see WP-5).

   *Network and edge:*
   - TLS certificate valid for 21 days or more, HSTS present, HTTP redirects to HTTPS;
   - `NUM_TRUSTED_PROXIES` matches the real hop count (a test request with a fake `X-Forwarded-For`);
   - `/admin/` restricted, if so configured;
   - **no service is open to the internet except the edge.** `ss -tlnp` and `docker ps` show
     `api`, `db`, `redis`, `pgbouncer` and `glitchtip` bound only to `127.0.0.1` or internal Docker
     networks. The check runs on the host itself, because ufw cannot be trusted for this.

   *Backups and services:*
   - newest encrypted backup under 26 hours old, and the off-host copy exists;
   - GlitchTip DSN accepts a test event;
   - ntfy and email alert test sent;
   - beat is alive, and the worker answers a ping.
4. **Deploy target:** no new workflow inputs. `deploy-staging.yml` already takes the host, user and
   directory from the `staging` environment's secrets, so no-one types a host on each deploy and a
   trigger cannot point SSH at an arbitrary host. Document which environment secrets to create, and
   whether to move the non-secret ones (host, user, directory) to environment variables.
5. `docs/ops/HOSTED_STAGING.md` gets a "first boot in 60 minutes" checklist: the scripts in
   order, then preflight.

**Steps (only with Q-B):** a provider annex (`docs/ops/hosting/<PROVIDER>.md`). It covers:
- services and sizes for staging and production;
- the India region;
- managed Postgres 17 with point-in-time recovery;
- managed Redis;
- two storage buckets, with the backup bucket in a separate account;
- private network;
- the console or CLI steps;
- the monthly cost as a range, to be checked on the day.

**Testing:**
- `bootstrap_vm.sh --check` is run in a throwaway Ubuntu container.
- `preflight.py` is unit-tested with mocked HTTP, DB and `ss` output, then run on local staging.
  The expected results there: TLS and backup age FAIL, and the bind check passes because local
  ports are on 127.0.0.1.

**Done when:** the scripts exist and are tested, preflight gives the expected results on local
staging, and the rows' notes say "kit ready; run on host".

**Still for people:** pick the provider, create the accounts, pay, run the kit, and register the domain.

---

## WP-5 PgBouncer wiring (1 day)

**Row:** BB-068.

**Already in place:**
- `deploy/pgbouncer.ini`: session mode for SR0-06, `auth_type = scram-sha-256`, and
  `ignore_startup_parameters = extra_float_digits,options`.
- The "Before enabling" list in `docs/ops/POSTGRES.md`.
- The ADR says not to enable it until `CONN_MAX_AGE=0`. Settings read `DB_CONN_MAX_AGE`, default 600.

**Two traps found in review:**
- **Timeouts would be lost silently.** `config/settings.py` sets `statement_timeout=30000` and
  `idle_in_transaction_session_timeout=60000` through the libpq startup `options`. PgBouncer
  accepts `options` because it is in `ignore_startup_parameters`, but drops it without passing it
  on. Through the pool, both timeouts would be off.
- **The user list needs a method decided.** With SCRAM authentication, PgBouncer needs either the
  role's SCRAM verifier in `userlist.txt`, or an `auth_query` that looks it up in Postgres. A plain
  password must not be kept on disk.

**Steps**
1. **Timeouts on the role:**
   - add `ALTER ROLE <app role> SET statement_timeout = '30s'` and
     `SET idle_in_transaction_session_timeout = '60s'` to `scripts/db-app-role.sh` and
     `scripts/staging-db-role.sh`. That way they apply with or without the pool, and the `options`
     string stays for direct connections;
   - the worker's long tasks keep their per-transaction `SET LOCAL` overrides, if any; check by
     grepping for `statement_timeout`;
   - a Postgres test asserts `SHOW statement_timeout` = `30s` and
     `SHOW idle_in_transaction_session_timeout` = `1min` **through the pool**.
2. **User list:** prefer `auth_query` against a `SECURITY DEFINER` lookup function owned by a
   dedicated `pgbouncer_auth` role, which can read only that function. That way nothing derived from
   the password is written to disk. Fallback: an entrypoint that reads the verifier from
   `pg_authid.rolpassword` once at start and writes `userlist.txt` with mode 600.
   - Both are tested against the `postgres:17-alpine` image the stack uses: sign in through the
     pool as the app role, and get refused with a wrong password.
3. `docker-compose.pgbouncer.yml` overlay:
   - a pinned, maintained PgBouncer image (checked at the time);
   - `pool_mode = session`, `server_reset_query = DISCARD ALL`, a health check;
   - api, worker and beat use `DATABASE_URL` pointed at `pgbouncer:6432`, with `DB_CONN_MAX_AGE=0`
     and `DB_VIA_PGBOUNCER=1`;
   - `migrate` stays direct to Postgres, because migrations and advisory locks should not pass
     through the pool.
4. **Boot guard:** with `DB_VIA_PGBOUNCER=1` and `CONN_MAX_AGE` not 0, refuse to boot. A test covers it.
5. **CI:** add the overlay to the `docker` job's `docker compose ... config` render checks, beside
   the glitchtip overlay.
6. **Local soak:**
   - the Postgres-only RLS and concurrency suites through the pool;
   - a `k6_slo.js` run with 25 logins;
   - a p95 comparison with and without the pool;
   - an alternating two-company request test that asserts no rows cross over.
7. Update `docs/ops/POSTGRES.md` and `ADR_TOPOLOGY.md`. Transaction mode still waits on WP-C4.

**Done when:**
- the overlay boots on local staging;
- the timeouts show through the pool;
- the RLS and race suites pass through it;
- the k6 numbers are recorded;
- the config render runs in CI;
- the BB-068 note is updated.

**Still for people:** decide whether production starts with the pool, and confirm on the host.

---

## WP-6 Local incident drill kit (1–1.5 days)

**Rows:** BB-099 (the half that is not failover), BB-149, BB-051, BB-093.

**Already in place:**
- `docs/ops/TABLETOP_EXERCISES.md`, `INCIDENT_RESPONSE.md`, `ALERTS.md`, `STATUS_COMMS.md`,
  `POSTMORTEM.md`, `docker-compose.rollback.yml`.
- GlitchTip plus ntfy.

**What actually raises alerts on local staging:** only GlitchTip's uptime monitor (it calls
`/api/v1/health/?ready=1` every 60 s), GlitchTip error issues, and the app's own watcher tasks.
The Prometheus rules (`BizBoardWorkerDown`, `BizBoardBeatSilent` in `deploy/prometheus/alerts.yml`)
need Prometheus and Alertmanager, which are not in `docker-compose.staging.yml`. Each drill case
below names the path it tests.

**Steps**
1. `scripts/drills/game_day.sh`, one subcommand per failure. Each one injects the failure, waits,
   checks the named alert path, restores, and records detection and recovery times. The cases:

   | Case | How it's injected | Alert path checked |
   |---|---|---|
   | Database down | stop `db` | Uptime monitor: `?ready=1` returns 503 → GlitchTip notice + ntfy |
   | Beat stopped | stop `beat`, **and** back-date the `bizboard:celery_beat_heartbeat` key in Redis by more than 600 s. The health check allows 10 minutes, so this avoids a 10-minute wait | Uptime monitor (`?ready=1` returns 503) |
   | Worker stopped | stop `worker`, enqueue a ping task | The ready probe, if it covers the worker; otherwise recorded as "Prometheus only" (Q-E) |
   | Stale backup | make the newest dump look 27 hours old | `check_backup_age.sh` exits 1 → ops alert endpoint → ntfy |
   | App error | raise a test exception | GlitchTip issue + notice |
   | Redis full | fill to `maxmemory` | Degraded but up; record how it behaves |
   | Rollback | tag the running api and web images locally as `bizboard-api:drill-prev` / `bizboard-web:drill-prev`, set `BIZBOARD_API_PREVIOUS_IMAGE` / `BIZBOARD_WEB_PREVIOUS_IMAGE`, then run `up -d --no-build` with `docker-compose.rollback.yml`. `--no-build` is needed because the base file keeps `build: ./backend` | The app stays healthy on the old image; roll forward afterwards |

   Real phone pushes go to the topic chosen in D-02. The script asks before sending, and
   `--dry-run` skips them.
2. **With Q-E:** a local-only `docker-compose.monitoring.yml` that runs Prometheus and Alertmanager
   with `deploy/prometheus/`. The worker and beat cases are then also checked against
   `BizBoardWorkerDown` and `BizBoardBeatSilent`, with the receiver set to ntfy. Without Q-E, those
   two rules are marked "verified on host only".
3. A missing or slow alert becomes a fix (an alert rule, a probe, runbook text) or a recorded gap.
4. **Tabletop pack:** printable inject cards and a 1-page scoring sheet for each scenario in
   `TABLETOP_EXERCISES.md`, plus a pre-filled solo-run record, as an appendix.
5. Results go in `docs/ops/DRILLS/2026-10-xx_LOCAL_GAME_DAY.md`.

**Done when:** every case has run, with its alert path and times recorded; gaps are fixed or
listed; the tabletop pack is ready; and the notes for BB-099, BB-149, BB-051 and BB-093 are updated.

**Still for people:**
- the founder runs the tabletop;
- a backup on-call person is named;
- failover waits on hosted Postgres.

---

## WP-7 Bizboard referral programme (2–2.5 days, only with Q-C)

**Row:** BB-139. The feedback half is done (BB-136).

**Not the same as CRM referrals.** `crm.ReferralCode` and the `/api/v1/crm/referrals/*`
endpoints track a tenant's *own* customers' referrals. They are gated by `ENABLE_REFERRALS`, which
is already in `ROLLOUT_GRANTABLE_KEYS`, `ENV_FLAG_KEYS` and `TRIAL_HELD_FALSE`. This WP is one
Bizboard customer referring another business to Bizboard. It uses its own flag,
**`ENABLE_SAAS_REFERRALS`**, added to `COMPANY_ROLLOUT_KEYS` and off by default. `ENABLE_REFERRALS`
is not touched.

**Design**
1. `billing.ReferralLink`: one per company (the referrer), with a short random code; it can be
   turned off.
2. Sign-up accepts `?ref=<code>`. The code is kept through the sign-up and Google flows and stored
   on the new company as `Company.referred_by`, an FK to `ReferralLink` with
   `on_delete=models.SET_NULL`, plus a timestamp.
   - No self-referral, and only the first code counts.
   - The code check is a pre-company, public endpoint. It is rate-limited, and returns only
     "valid or not" (never the referrer's name).
3. `billing.ReferralEvent(kind=SIGNED_UP|QUALIFIED)`, belonging to the **referrer** company:
   - `referred_company` is an FK with `on_delete=SET_NULL`, so erasing either company never fails
     and never keeps a link to an erased company's identity;
   - a referral qualifies when the referred company first becomes ACTIVE on a paid plan.
4. **Reward, per Q-C2:**
   - (a) **Free days:** add N days to the referrer's next renewal. This needs care with Razorpay.
     Extending `current_period_end` locally does not move Razorpay's charge date, so it is built
     only together with the Razorpay schedule change, or held until Razorpay is live (D-03).
   - (b) **Money credit:** a dedicated `ReferralCredit` balance, consumed at renewal capture. It
     issues a GST credit note (`PlatformGstInvoice.Kind.CREDIT_NOTE`) when applied. This is a
     discount, so its GST treatment needs the CA. There is **no existing plan-change credit to
     reuse**: `billing/plan_change.py` only prorates upgrades through a payment link, and the
     `SaasTdsClaim` credit is for statutory TDS refunds, so it must not be borrowed.
   - (c) **Recorded only (default):** Django admin lists qualified referrals. The founder settles
     them by hand and marks each one "settled", with a note. Nothing touches money.
5. **Owner screen:** Settings → "Refer a business" shows the link, copy and share (the `wa.me`
   share link, already allowed), and counts of signed up and qualified. English and Hindi.
6. **Abuse limits:**
   - sign-ups per code per day are capped;
   - the same email domain or GSTIN as the referrer does not qualify;
   - the admin can void an event.
7. **Privacy:** the referrer sees counts only, never the referred company's name.

**Tenancy and data rules (all must pass CI)**
- **RLS:** both new tables have a `company` FK, so they go in a new `core/migrations/00xx_rls_*.py`
  policy migration, and are granted to the app role in `scripts/staging-db-role.sh` /
  `db-app-role.sh`. Otherwise `test_every_tenant_table_is_in_the_rls_migration` fails.
- **Writing for another company.** The sign-up request and the activation webhook run as the
  *referred* company (B). The `ReferralEvent` belongs to the *referrer* (A), and B's context cannot
  write it under forced RLS.
  - One small service function, `record_referral_event(...)`, writes it inside
    `company_scope(referrer_id)`, never a broad `rls_bypass()`.
  - It is the only place this happens, with a test on Postgres with RLS on: the B context succeeds
    through the service; a direct write fails.
- **Endpoint isolation:** the public code-check endpoint is added to the allow-list in
  `test_every_api_view_is_tenant_scoped_or_allowlisted`, with a reason. The owner endpoints are
  tenant-scoped as usual.
- **Erasure:** `erase_company` is tested with a referrer and with a referred company. Both work,
  and the links are nulled.
- **Data list:** add the referral fields to `docs/ops/DATA_CATEGORIES.md` (and so to WP-2's DPIA).

**Tests:**
- Backend: attribution; no self-referral; first code wins; qualification on paid activation; flag
  off hides everything; staff can't see the link; the RLS cases above; erasure.
- Web: the panel, copy and share.
- Regenerate the OpenAPI snapshot and TypeScript types.

**Done when:** it is built, all tests and CI gates pass, and BB-139 can be marked Passed (feature
built, off until pilots).

**Still for people:** the reward amount and terms (Q-C2), the CA on GST if (b), and a
privacy-policy line from counsel.

---

## WP-8 Commit and CI (1 day plus fixes, only with Q-D)

**Rows:** BB-017 (closable), BB-141 (its CI half).

**Steps**
1. Inventory `git status`, and split this programme's files from other sessions' files. The known
   other-session files are:
   - `.github/workflows/lead-pilot-journeys.yml`
   - `scripts/ci_gates/mutation_*`
   - `qos/backlog/QOS-0154..0156`
   - `qos/tools/verify_fixed.py`
   - `docs/STABILIZATION_PLAN.md`
   - `web/e2e-golden/lead-pilot-gaps.spec.ts`
   - `web/src/pages/sales/VoidReceiptDialog.test.tsx`
   - `playwright.*.local` configs
   - `backend/tests/broker/`
   - `backend/setup.cfg`
   - other sessions' lines in `AppShell.tsx`

   Commit only this programme's files. Mixed files are committed by hunk.
2. Secret scan before committing: `.env.staging`, `.env.glitchtip`, phone numbers, the ntfy topic, tokens.
3. Commits by area, in an order that builds: models and migrations, services and tests, OpenAPI
   and types, web, docs, the sheet.
4. **Run every blocking CI gate locally first** (`.github/workflows/ci.yml`):

   | Gate | Command |
   |---|---|
   | Register claims | `python scripts/check_register_claims.py` |
   | Lint | ruff; web lint; `tsc -b` |
   | Migrations | `python manage.py makemigrations --check --dry-run` |
   | Help codes | `python manage.py dump_help_codes && git diff --exit-code ../web/src/pages/help/helpCodes.json` |
   | Backend tests | SQLite suite, and the Postgres-only suites |
   | Postgres skips | `python ../scripts/ci_gates/check_postgres_skips.py pg_skips.json` (and `pg_skips_rls.json`) |
   | Diff coverage | `diff-cover coverage.xml --compare-branch origin/main --fail-under=80`, on every changed line; add tests where it falls short |
   | Web | vitest; `npm run build`; `node scripts/check-sw-navigate.mjs`; `node scripts/check-bundle-budget.mjs` |
   | Drift | the OpenAPI snapshot and the generated types |
   | Compose | `docker compose ... config` renders for every overlay, including the new `docker-compose.pgbouncer.yml` (WP-5) |
   | Supply chain | `gitleaks` with `.gitleaks.toml`; `python scripts/ci_gates/guards/guard_trivy_allowlist.py`; pip-audit; npm audit |
   | Q-OS and freeze | qos-lint; the freeze guards |
5. Push the branch, open a PR, read CI, and fix failures until it's green. No auto-merge.

**Done when:** CI is green on the PR, BB-017 is moved to Passed, and the BB-141 note records the
CI half done (the hosted half stays open).

**Still for people:** reviewing and merging the PR.

---

## After this plan

**Rows that can move to Passed (2):**
- BB-017, with Q-D;
- BB-139, with Q-C.

**Rows whose LLM-side work is finished, which stay open for people (19):**
- **Security:** BB-029, BB-045, BB-143, BB-144
- **Data protection:** BB-047, BB-123
- **Contracts:** BB-129
- **Hosting:** BB-080, BB-081, BB-082, BB-085, BB-087, BB-089
- **Pooling:** BB-068
- **Incidents:** BB-051, BB-093, BB-099, BB-149
- **CI:** BB-141 (CI half)

**Note-only corrections (WP-0):** BB-004 and BB-090. BB-093 also gets a WP-0 note, and is counted above.

Every other open row is unchanged, because it needs a person, a host or a provider.

---

## Review changes (rev 2, 2026-10-25)

| Review point | Checked in the repo | Change |
|---|---|---|
| WP-7 flag clash with `ENABLE_REFERRALS` | Confirmed (`feature_flags.py`, `billing/services.py`, `crm/growth_views.py`) | New flag `ENABLE_SAAS_REFERRALS` |
| WP-7 "plan-change credit" does not exist | Confirmed (`plan_change.py` prorates upgrades only; `SaasTdsClaim` credit is for TDS) | Reward options set out, with a new Q-C2; default is record-only |
| WP-5 timeouts dropped through PgBouncer | Confirmed (`settings.py` `options`; `pgbouncer.ini` `ignore_startup_parameters`) | Timeouts set on the role, plus a through-the-pool test, plus a preflight check |
| WP-1 ZAP container can't reach `127.0.0.1`; staging is cookie + CSRF only | Confirmed (`authentication.py`, BB-000547) | `host.docker.internal`, script-based authentication with CSRF, a pre-scan check, throwaway tenant with a database restore |
| WP-7 RLS migration, cross-company write, isolation allow-list, erasure, data list | Confirmed (the tests named exist) | "Tenancy and data rules" section; WP-7 moved before WP-2 |
| WP-6 no Prometheus locally; 600 s beat window; rollback overlay needs image variables | Confirmed (`views.py` `age < 600`; `docker-compose.rollback.yml`) | Alert path named for each case; heartbeat back-dated; images tagged locally with `--no-build`; Prometheus optional (Q-E) |
| WP-8 missing CI gates | Confirmed (`ci.yml`) | Full gate table |
| WP-5 SCRAM user list | Partly: whether a plain password works depends on the PgBouncer version, but it shouldn't be on disk anyway | `auth_query` preferred, verifier fallback, both tested against `postgres:17-alpine` |
| WP-4 use environment variables, not workflow inputs | Partly: `deploy-staging.yml` already reads the host, user and directory from `staging` environment secrets | Proposed workflow inputs dropped; documents which secrets to create |
| WP-1 tenant probe beyond GET details | Accepted | List filters and IDs injected into writes added |
| WP-4 Docker bypasses ufw | Accepted | `APP_BIND=127.0.0.1`, plus a host bind check in preflight |
| Footer count | Accepted | Exact row IDs listed |

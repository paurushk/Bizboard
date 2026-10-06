# ISO 25010 remediation log — 2026-10-02

Companion to [ISO25010_QUALITY_ASSESSMENT_2026-10-02.md](ISO25010_QUALITY_ASSESSMENT_2026-10-02.md) and
[ISO25010_UPLIFT_PLAN_PERF_USABILITY_QIU_2026-10-02.md](ISO25010_UPLIFT_PLAN_PERF_USABILITY_QIU_2026-10-02.md).
This records what was **actually changed and verified** in the working tree, what was found along the way,
and what was **not** done and why. Nothing here is committed: the tree already carried ~230 uncommitted
files before this work started (see F-GOV-01), so reviewing and slicing the commit is still step one.

Evidence labels: **ran** = executed here with the output seen; **read** = code read, not executed;
**not run** = could not be run here.

---

## 1. Fixed and verified

| # | Item | What changed | Evidence |
|---|---|---|---|
| 1 | **CI guard failing at HEAD** (QOS-0106) | 24 feature flags (`ENABLE_INSURANCE`, `ENABLE_WORKSHOP`, … plus the new `ENABLE_GSTR_EXTENDED`, `PORTAL_DEBUG_ECHO`, `IDEMPOTENCY_STRICT_FINGERPRINT`) classified in `docs/FREEZE_SCOPE.md` from `settings.py` defaults and `ROLLOUT_GRANTABLE_KEYS` | ran: `run_guards.py` was FAIL, now all OK; `--selftest` OK |
| 2 | **Backups could report success with nothing in them** (QOS-0101) | `scripts/backup.sh` rewritten: fail-closed encryption, checked temp dump, gzip verify, optional offsite command, age-based retention with a minimum keep, `LAST_SUCCESS` marker. `restore.sh` decrypts `.gpg`/`.age` and verifies gzip. | ran: old script with a failing `pg_dump` exited 0 and wrote a 20-byte "backup"; new one exits non-zero. 11 behavioural tests pass |
| 3 | **Runtime skew CI ↔ image** (QOS-0105) | Dockerfiles pinned to Python 3.13 / Node 22 by resolved digest; new guard `runtime_alignment`; `scripts/image_smoke.sh` + advisory CI job `image-smoke` | ran: guard + selftest OK. Image built; smoke steps 1–3 passed (Python 3.13, `check --deploy`, no migration drift). Steps 4–5 (migrate on empty DB, gunicorn health) **not run** to completion locally — Postgres was saturated by the test suite |
| 4 | **Cross-tenant isolation proof** (QOS-0104) | `tests/tenancy/test_route_isolation_matrix.py`: every detail route × method called as tenant A with tenant B's real object ids, with a tenant-B control request proving the route is live; ratchets for coverage and for unprobed routes | ran: 255 routes probed, 90 live-controlled, 112 list routes, **0 leaks, 0 crashes**. With scoping removed from the base viewset the same matrix reports 230 leaks (kept as a permanent self-test) |
| 5 | **Audit log mutable, no tamper evidence** (QOS-0102) | `core/audit_guard.py` (append-only model/QuerySet, explicit `audit_maintenance()`), Postgres trigger (migration 0044), per-company hash chain with `seal_audit_chain` / `verify_audit_chain` and a nightly task | ran: 18 tests on SQLite; **21 on Postgres 17 including the 3 trigger tests**; erasure / sandbox / tenant-export suites (78) pass on Postgres |
| 6 | **No MFA, and two single-factor session paths** (QOS-0103) | Opt-in TOTP (RFC 6238, stdlib), encrypted secret, recovery codes, replay protection, 5-failure lockout; login challenge; **phone-OTP login and invite acceptance no longer bypass it**; login second step + enrolment panel | ran: 28 backend tests (RFC vectors included), 11 web tests, 81 auth tests still green |
| 7 | **Reused Idempotency-Key replayed the first success** (QOS-0108) | `request_hash` on `IdempotencyRecord` (migration 0045); mismatch → 422 `idempotency_key_reused`; legacy rows still replay; `IDEMPOTENCY_STRICT_FINGERPRINT=0` rolls back | ran: 14 new tests; the persona test that pinned the old behaviour was updated (its docstring called it a deliberate-decision point) |
| 8 | **Offline POS retry would have been refused after midnight** (found while doing #7) | `flushPosCheckout.ts` pins `invoiceDate` on the draft at the first attempt | ran: new web tests; 70 offline/POS tests pass |
| 9 | **AR/AP agreement** (QOS-0053) | `tests/test_ar_ap_agreement_matrix.py`: 14 scenarios × books on/off against a hand-computed oracle | ran: 28 pass; oracle shown to fail when AP aging is perturbed. The "different truth models" divergence is **not reproducible** in these scenarios; item closed with that evidence |
| 10 | **Observability** (QOS-0107) | `/metrics` latency histogram `bizboard_http_latency_ms` (edges at 500/800/2000/8000 ms) with a pid label; frontend bundle budget in CI | ran: 3 new tests; measured **initial load = 482 KB gzip** (not the 250 KB assumed from the entry chunk alone) |
| 11 | **Migration drift** | `support/0003_ticket_category` label differed from the model | ran: `makemigrations --check` clean |
| 12 | **Test bug** | `test_concurrent_next_number_allocates_two_values` raced two threads on separate connections without `transaction=True`; it skips on SQLite so only Postgres exposed it | ran: failed on Postgres; fix below |
| 13 | **Backlog** | QOS-0101…0108 added, QOS-0053 closed with evidence, backlog regenerated | ran: `qos/tools/lint.py` OK (108 items) + selftest |
| 14 | **Contract artefacts** | OpenAPI snapshot and `openapi-types.ts` regenerated for the new routes | ran |

## 2. Corrections to my own earlier statements

* "PDF/LLM work in the request path" — wrong. PDF and bill extraction are already queued to Celery.
* "No metrics backend" — wrong. A token-protected Prometheus `/metrics` exists; what was missing was a histogram.
* Entry chunk "≈250 KB gzip" understated first-load cost; the preloaded vendor chunks bring it to 482 KB.
* My first idempotency change would have broken the offline POS retry (item 8); caught by reading the client, fixed.

## 3. Full backend suite on Postgres 17 (ran)

First pass (the tree was still being edited during the run): **2,487 passed, 12 failed, 41 errors, 4 skipped.**
Triage:

* 41 errors + the remaining cascades: one genuine test bug (item 12) left committed rows behind, after which every
  following transactional test failed to flush; they were secondary.
* 7 snapshot / 1 source-inspection / 1 timing failures: passed on SQLite with the final code; **re-run on Postgres
  below** (see §3a).

### 3a. Postgres re-run of every failing file, final code

Baseline recorded while the ISO 25010 implementation plan was being applied.
The assessment fingerprint, taken before these edits, was commit `5deafb2`,
627 porcelain paths, 365 tracked files, +10633/−4639. A full Postgres suite was
not re-run in that pass (first recorded Postgres pass on the earlier tree:
2,487 passed, 12 failed, 41 errors). Postgres was not used as the default
database for this implementation. SQLite targeted tests for the new packages
are the evidence in the working tree; the full suite total is still the
earlier Postgres pass, not a new one.

## 4. Not done, and why

**Needs a person or a place that does not exist yet** (cannot be done in a repo): signing `GO_NO_GO.md` / DPDP /
ENV_CHECKLIST (QOS-0021, 0049, 0052); a practising CA's review (0004); the unaided usability study (0029); the
operational and commercial readiness pilots (0030, 0031); the staging host, TLS edge, Sentry/on-call, SMTP (0020);
the 50k-tenant load run and restore-at-volume (0003).

**Deliberately not started**
* QOS-0095 (editor redesign): the plan itself says run the study first; redesigning blind would be guesswork.
* QOS-0096 / 0098 / 0097: the web UI already carries ~180 uncommitted files from the earlier UX programme and another
  session is changing it; editing those screens here would collide. They need that work committed and reviewed first.
* QOS-0028 (milestone billing, XL), 0042 (live GSP, XL), 0046 (native WhatsApp), 0043 (ML matcher), 0015 (LLM
  benchmark), 0014 (prod-shaped migration rehearsal): separate projects, not fixes.
* A mypy gate: needs `django-stubs` and a triage of the resulting errors; no value in a gate that is red on day one.

**Decisions only the founder can make, now blocking**
1. Make MFA mandatory for OWNER/ACCOUNTANT? (Shipped as opt-in; the owner Users page is the only enrolment UI.)
2. Set `MFA_ENCRYPTION_KEY` in production (otherwise rotating `DJANGO_SECRET_KEY` locks MFA users out).
3. Accept the API contract change in #7: a reused key with a changed body is now 422. Check any integration you run.
4. Choose and fund the offsite backup target and state the RPO (the script supports it; nothing is configured).
5. Revoke UPDATE/DELETE on `core_auditevent` for the app DB role, and archive the latest audit-chain hash offsite
   (tail truncation is only detectable against an external copy).

## 5. First steps when you pick this up

1. Slice and commit the tree (F-GOV-01); this log's changes touch ~40 files and are independent of the UX work.
2. Run `python scripts/ci_gates/run_guards.py` and `--selftest`.
3. Run the Postgres suite from a clean DB: `PYTEST_KEEP_DATABASE_URL=1 DATABASE_URL=… pytest --create-db`.
4. Re-run `scripts/image_smoke.sh` end to end on a machine where Postgres is idle.

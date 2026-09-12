# Phase 0 Go / No-Go record

> **Wave 16:** Engineering may mark code-complete. **Human signatures below remain
> Final Gates** — do not claim Production Readiness 10/10 until every checkbox is
> signed and live GSP credentials (if filing) are configured.

**UAT build SHA:** `ae3202d88821141220b56d7764d199921d5e04d2`  
**Go build SHA:** ________  
<!-- CI may inject: BUILD_SHA={{github.sha}} -->
<!-- A-05: UAT SHA filled from `git rev-parse HEAD` on 2026-08-31. Not a signature. Do not tick SHAs-match until a human re-smokes or signs. -->
- [ ] SHAs match **or** 12-row smoke re-signed on Go SHA — *blocked: no Go SHA cut yet; needs a human
  to re-smoke once one is.*

## Checklist

- [ ] Wave 0 Critical+High mapping complete (`WAVE0_AUDIT.md`) — *the mapping table itself is fully
  populated (62/62 BUG rows dispositioned, verified 2026-09-12), but its own last row explicitly defers
  "Remaining Highs" to a PM go-meeting note — blocked on that meeting, not on more mapping work.*
- [ ] Must DoD items Done or PM-waived (`PHASE_0_DOD.md`) — *blocked: needs a PM to review and
  sign/waive; a prior issue-register sweep (2026-09-10) found the open P0/P1 items are all
  ops/governance/roadmap, zero code-level defects — see `docs/reviews/MASTER_ISSUE_REGISTER.md`.*
- [ ] H9-A signed (`H9_CORRECTION_PATH.md`) — *blocked: needs a named human signature; the
  implementation itself (BE, tests) is done per `WAVE0_AUDIT.md` Wave 2.*
- [ ] CA letter stored (F9) + F12 additional-charges scope — send `../ca/F9_CA_REVIEW_COVER.md` +
  `../ca/CA_SIGN_OFF_CHECKLIST.md` (all 9 rows' PDF/DB/FE evidence pre-filled 2026-09-12; only the
  CA's sign-off and the F12 business decision are still open) — *blocked: needs a real practising CA.*
- [ ] UAT matrix ≥5 companies (`UAT_CHECKLIST.md`) — *blocked: needs ≥5 real pilot businesses, not
  something to simulate.*
- [ ] TLS on pilot host (E1) — **Final Gate** — *blocked: no pilot host/domain exists yet to terminate
  TLS on. `scripts/edge_tls_smoke.sh` (the verification script named in `ENV_CHECKLIST.md` row 1) was
  validated against a real HTTPS+HSTS host (github.com) on 2026-09-12 and works correctly — run it
  against the real pilot host the moment one exists.*  
- [x] Backup + restore drill dated — **Final Gate** (scripts: `backup` / `restore` compose profiles)
  **2026-09-12** — ran `scripts/restore_drill.sh` locally (Docker, two throwaway `postgres:17-alpine`
  containers, real `pg_dump | gzip` → `psql` restore into a scratch DB, same pipeline as
  `scripts/backup.sh`/`scripts/restore.sh`), then `manage.py check_invariants` against the restored
  data. Result: **PASS** — "All 1 company(ies) clean." **RTO measured: 4m6s** wall-clock for
  migrate+seed+dump+restore+invariant-sweep on the single-company demo dataset (re-measure at
  pilot data volume before relying on this number for a real incident). **RPO commitment: ≤ backup
  cron interval** (daily `pg_dump`, per `ENV_CHECKLIST.md` row 14) — the drill proves a *fresh* dump
  restores cleanly, it does not by itself bound RPO. Two pre-existing, unrelated warnings surfaced
  (`core.W001`/`W002` — local dev Postgres role is superuser/BYPASSRLS, so RLS is bypassed in this
  throwaway container); not a drill regression, tracked separately under the RLS test-strictness
  work (D16).
- [ ] ENV_CHECKLIST signed (incl. JWT localStorage accept-risk) — *blocked: needs Eng/Ops/PM
  signatures; the checklist's evidence steps are now concrete commands (TLS/SMTP/Sentry rows all
  name an exact script/command to run and paste output from, as of 2026-09-12) rather than bare
  claims, so signing it should now be fast once someone has a real host.*
- [ ] Support SLA live (`SUPPORT_SLA.md`) — *blocked: needs a staffed, real support process, not code.*
- [x] Zero open Criticals; no new Critical since UAT sign-off — **verified 2026-09-12**:
  `docs/PRODUCT_QUALITY_BACKLOG.md` dashboard shows 0 Critical bugs (0 tracked); the 2026-09-10
  issue-register sweep found 0 open code-level P0/P1 defects. This session's own changes (CI
  digest-pin fix, k6 login-throttle fix, new tests) fixed 2 pre-existing test/CI-tooling bugs and
  introduced none. *Caveat: this confirms the current state, not a re-run of the original UAT
  reviewer's own historical diff against the exact UAT SHA above.*
- [ ] Image digests verified on deploy host (`scripts/pin_image_digests.sh`) — **Final Gate** —
  *blocked: no real deploy host exists yet. The script itself was proven end-to-end on 2026-09-12
  (built local images, ran the script, validated the resulting overlay with `docker compose config`)
  and the CI check that was supposed to enforce this was found to be a no-op and fixed (see git log)
  — run the same script against the real deploy host once one exists.*
- [ ] Sentry DSN + on-call routing live — **Final Gate** — *blocked: needs a real Sentry/PagerDuty
  account. `manage.py sentry_test_event` (added 2026-09-12) makes verification a single command once
  `SENTRY_DSN` is set — see `ENV_CHECKLIST.md` row 18.*
- [ ] SMTP spot-send verified — **Final Gate** — *blocked: needs real SMTP credentials. Django's
  built-in `manage.py sendtestemail <addr>` is now named explicitly in `ENV_CHECKLIST.md` row 11 —
  run it once credentials exist.*
- [ ] Live GSP credentials (if e-invoice/e-way in prod) — **Final Gate** — *blocked: needs GSP vendor
  registration with GSTN under the business's legal identity — not something to simulate.*
- [ ] Q-OS dashboard reviewed ([`docs/PRODUCT_QUALITY_BACKLOG.md`](../PRODUCT_QUALITY_BACKLOG.md)): **Critical bugs = 0**, open-item trend non-increasing, and the sequenced frontier's top items for this pilot stage are addressed or explicitly waived — *Critical bugs = 0 confirmed (see above). The sequenced frontier's current top items are QOS-0021 (this checklist itself), QOS-0020 (TLS), QOS-0003 (load/soak — progressed 2026-09-12, see `qos/backlog/QOS-0003.yaml`), QOS-0049 (DPDP sign-off), QOS-0052 (governance ratification) — all either founder/ops-owned or, for QOS-0003, partially closed this session. Leaving unchecked: "reviewed" and "addressed or explicitly waived" is a founder judgment call on the remaining items, not a fact to assert on their behalf.*  

## Decision

| Role | Name | Date | Go / No-Go / Conditional |
|------|------|------|--------------------------|
| PM | | | |
| Eng | | | |
| QA | | | |
| CA | | | |
| Ops | | | |

Waivers (Should only): ________

## Wave 16 Final Gates (non-negotiable for score 10/10)

See [`docs/pilot/FINAL_GATES_10.md`](FINAL_GATES_10.md).

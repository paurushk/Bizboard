# Phase 0 Go / No-Go record

> **Wave 16:** Engineering may mark code-complete. **Human signatures below remain
> Final Gates** — do not claim Production Readiness 10/10 until every checkbox is
> signed and live GSP credentials (if filing) are configured.

**UAT build SHA:** `ae3202d88821141220b56d7764d199921d5e04d2`  
**Go build SHA:** ________  
<!-- CI may inject: BUILD_SHA={{github.sha}} -->
<!-- A-05: UAT SHA filled from `git rev-parse HEAD` on 2026-08-31. Not a signature. Do not tick SHAs-match until a human re-smokes or signs. -->
- [ ] SHAs match **or** 12-row smoke re-signed on Go SHA  

## Checklist

- [ ] Wave 0 Critical+High mapping complete (`WAVE0_AUDIT.md`)  
- [ ] Must DoD items Done or PM-waived (`PHASE_0_DOD.md`)  
- [ ] H9-A signed (`H9_CORRECTION_PATH.md`)  
- [ ] CA letter stored (F9) + F12 additional-charges scope  
- [ ] UAT matrix ≥5 companies (`UAT_CHECKLIST.md`)  
- [ ] TLS on pilot host (E1) — **Final Gate**  
- [ ] Backup + restore drill dated — **Final Gate** (scripts: `backup` / `restore` compose profiles)  
- [ ] ENV_CHECKLIST signed (incl. JWT localStorage accept-risk)  
- [ ] Support SLA live (`SUPPORT_SLA.md`)  
- [ ] Zero open Criticals; no new Critical since UAT sign-off  
- [ ] Image digests verified on deploy host (`scripts/pin_image_digests.sh`) — **Final Gate**  
- [ ] Sentry DSN + on-call routing live — **Final Gate**  
- [ ] SMTP spot-send verified — **Final Gate**  
- [ ] Live GSP credentials (if e-invoice/e-way in prod) — **Final Gate**  

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

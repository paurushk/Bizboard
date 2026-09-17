# Open Q-OS items — freeze classification (1.3)

Priorities already live on each `qos/backlog/QOS-*.yaml` (`qos/tools/lint.py` L3).
This file is the freeze-lane overlay: **do not implement Table B / ARCH-07 /
WhatsApp / live GSP filing** even if a yaml is still `lifecycle: open`.

Founder still owns residuals and any P0/P1 that is governance, not code.

## Open items (as of 2026-09-16)

| ID | Priority | Freeze action |
|---|---|---|
| QOS-0004 | P1-investigate | **Human** — H-05 CA filing. Not code. |
| QOS-0016 | P1-investigate | Observation pytest + Playwright first-paint spec landed. Signed 12-month p95 SLO stays Human. |
| QOS-0021 | P1 | **Human** — unsigned Go/No-Go. |
| QOS-0028 | P2 | **Deferred** — ARCH-07 milestone/job-work. Table B / out of freeze. Do not build. |
| QOS-0029 | P1-investigate | **Human** — unaided UX with real staff. |
| QOS-0030 | P1-investigate | **Human** — daily operational readiness in pilot. |
| QOS-0031 | P1-investigate | **Human** — paid conversion / renewal. |
| QOS-0042 | P3 | **Deferred** — live GSTR filing / GSP. Table B. Do not enable `VITE_ENABLE_GSTR`. |
| QOS-0046 | P3 | **Deferred** — WhatsApp Cloud. Table B. Keep `ENABLE_WHATSAPP_CLOUD=0`. |
| QOS-0052 | P2 | **Human** — ratify Q-OS rubric / ADR-0001. |

No open item is P0. None of the deferred rows may be raised to P0 without
measured evidence (rubric cap).

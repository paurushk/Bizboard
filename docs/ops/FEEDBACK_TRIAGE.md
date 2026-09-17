# Feedback triage (15.8)

Cluster incoming beta tickets before they become freeze exceptions.

| Bucket | Examples | Action |
|---|---|---|
| P0 money/tax/stock | totals, allocation, GST split, oversell | Patch this freeze; HelpCode if missing |
| Freeze exception | payroll, CRM, GSTR screens, Tally live, BoE | `docs/ops/FREEZE_EXCEPTION.md` — founder only |
| Known limitation | FA, landed cost, composition, RCM | Point at `FREEZE_SCOPE.md` KNOWN LIMITATIONS |
| Cutover / Excel | import mapping | `docs/ops/CUTOVER.md` |
| Later (post-beta) | WhatsApp Cloud, ARCH-07, multi-GSTIN | Backlog; do not expand freeze |
| Legal / DPDP | erasure, ToS | Counsel; `docs/ops/ERASURE_PLAYBOOK.md` |

Do not invent a GST filing claim to close a ticket. Macros:
`docs/ops/SUPPORT_MACROS.md`. Taxonomy: `docs/ops/TICKET_TAXONOMY.md`.

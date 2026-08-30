# Help event schema

Sink of record: first-party `HelpEvent` via batched `POST /api/v1/help-events/`.

Raw query text **never leaves the box**. `window.bizboardAnalytics` (if wired) receives `{intentId, state, source, result_count, queryLenBucket}` only — never `query`.

| Name | When | Props (first-party) |
|---|---|---|
| `help_open` | Nav, field `?`, error Why?, empty-state link, Universal Search, Assistant hint | `source`, `intentId?`, `code?`, `slot?` |
| `help_search` | Once per `/help` search | `query`, `result_count`, `state`, `intentId?` |
| `faq_resolved` | Three-way: Solved it | `intentId`, `query?` |
| `faq_understood_pending` | Three-way: Understood, not done | `intentId`, `query?` |
| `faq_unresolved` | Three-way: Still stuck | `intentId`, `query?` |
| `diagnosis_branch` | Diagnosis option tap | `id`, `leaf` |
| `prevention_view` | Prevention note first paint | `slot`, `intent` |

`HelpFeedback` (still-stuck capture) is a separate table: `{query, screen, role, intentId, note}`. Confirmation must not promise a human reply.

Rollups on `GET /api/v1/help-health/` (last 30 days): resolution rate, **time to resolution** (median seconds from last `help_open` to `faq_resolved` for the same user+intent), escalation rate, zero-result rate, opens, top zero-result queries, per-intent stats (including per-intent TTR), **repeat query rate** (distinct queries seen ≥2 times / distinct queries), repeat queries list (n ≥ 3).

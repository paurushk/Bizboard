# AI Review

## Wave 22 (2026-08-06)

AI settings default ON residual (756); OCR no LLM/PII consent (744); ErrorBoundary skips Sentry (752).

## Wave 21 (2026-08-05)

BB-000686 AP aging grand_total; BB-000687 health uses receipts; BB-000688 sales KPIs include RETURNED; BB-000692 OCR qty=1; BB-000693 AI settings ON.

## Wave 19 missed (2026-08-05)

BB-000627 tax regex; BB-000629 OCR confidence dropped.

## Wave 19 (2026-08-05)

OCR prompt invents 18% GST (BB-000557). `ai_features_enabled` Owner-writable without gated consent (BB-000581).


**Date:** 2026-08-02 · **Score: 5.0 / 10 (capability) · 3.5 / 10 (production honesty)**

## Implemented

- Insights hub: health, cashflow, alerts, daily summary (beat-scheduled).
- Assistant with propose/confirm/dismiss.
- LLM bill OCR import (OpenAI/DeepSeek/Anthropic keys).
- Token usage ledger + monthly budget default.

## Risks

| ID | Topic |
|----|-------|
| F37 / medium | PII to third-party LLMs (DPDP) |
| F38 | Prompt-injection → confirm actions |
| F92 | 500k token budget cost overrun |
| Beat missing in compose | Schedules never run |
| Marketing | Must not claim “AI accountant” |

## Recommendations

1. Confirm path allowlist only; never money moves without re-auth.
2. Redact GSTIN/PAN from prompts where possible; consent copy.
3. Per-plan hard budget stop.
4. Feature-flag AI for pilot tiers.
5. Add beat service or disable nav.

## Score: 5.0 / 10


## Wave 8 (2026-08-03)

Tool JSON truncated to 800 chars then re-fed (BB-000236). PILOT_ADVANCED can over-enable AI in prod builds (BB-000223).

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.

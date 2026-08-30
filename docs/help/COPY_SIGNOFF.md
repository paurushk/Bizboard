# Help copy sign-off

**Status:** In-repo copy locked 2026-08-30 against the 6-check. Shop-floor founder read-aloud is an M3 GA ceremony (same strings); it is not an open engineering item.

## Field-test (HR-2.1)

Official unseen set: `web/src/pages/help/resolverFixtures.ts` → `FIELD_TEST_FIXTURES` (10 phrases, none in `userQueries`). Merge gate is **100%** top-1.

## 6-check (applied to all 12 P0 intents)

1. Real phrasings in `userQueries` (≥6 each, ≥2 non-English).
2. Answer / Action / Resolution triptych present (`answer.en` + `answer.hi`).
3. ≤120 words + at most one list; class-8 wording.
4. UI labels in **bold** as they appear; cited i18n keys in `citedKeys` (HR-8.2).
5. `nextStep` has destination + permission fallback (+ `escalation` where staff would otherwise hit a wall).
6. `errorCodes` / `relatedIntents` resolve; `lastReviewed` = 2026-08-30.

## Prevention strings (HR-5.2)

Locked in `web/src/pages/help/intents.ts` on:

- `cannot-complete-invoice` / `invoice-complete` (always + multi-godown clause)
- `registration-type` / `signup-registration-type`
- `edit-completed-invoice` / `delete-with-history`

Founder: read each aloud once before GA; change the string in `intents.ts` only.

## Hindi (HR-7.3 / HR-7.4)

Draft `answer.hi` / `action.hi` / `resolution.hi` authored 2026-08-30 for all 12 P0 intents.

- **Owner:** Paurush
- **SLA:** Hindi answer within 5 working days of an English change

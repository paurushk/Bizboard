# Adding a Help intent

Help answers live in `docs/help/INTENTS.md` first, then in `web/src/pages/help/intents.ts`. Error codes live in `backend/core/help_codes.py` and are copied to `web/src/pages/help/helpCodes.json` by `python manage.py dump_help_codes`.

See [CODEOWNERS](../../.github/CODEOWNERS) — PRs that touch those paths request **@paurushk**.

## 6-check (every new answer)

1. Matches the user's actual words (≥3 real phrasings in `userQueries`).
2. Triptych present: **Answer** / **Action** / **Resolution**.
3. ≤120 words + ≤1 list; class-8 readability. Read it aloud to someone with no books background; if they restate it right, it passes.
4. Zero banned *explanation* words. UI buttons named **exactly as they appear**, in **bold**, then glossed once. In `intents.ts` write those labels as `**t:nav.gst**` (HR-8.2) so the renderer prints the live catalog string.
5. `nextStep` has a real destination **and** a permission-fallback sentence. Permissions are existing caps (`owner`, `can_create_sales`, …) — do not invent a new permission system.
6. `errorCodes[]` / `appliesWhen` / `relatedIntents` all resolve; `lastReviewed` set to today (ISO date).

## Content format

Plain strings + optional one bullet list. No ReactNode, no tables, no full markdown.

The renderer supports only `**bold**` (UI labels, including `**t:dot.key**`) and `` `code` `` (values the user types).

Locale: one content module. `answer: { en, hi?: string }`. Hindi **answers** are drafted for all P0 intents (see [COPY_SIGNOFF.md](COPY_SIGNOFF.md)); Hinglish/Devanagari **queries** are required.

## Hindi owner + SLA (HR-7.3)

**Owner:** Paurush. **SLA:** Hindi answer within **5 working days** of an English change.

## Weekly triage

See [TRIAGE.md](TRIAGE.md). Fold into the onboarding funnel review. Latest run: [TRIAGE_2026-08-30.md](TRIAGE_2026-08-30.md).

## Error codes

Do **not** add `code=` to a `BusinessRuleError` unless the site is listed in `docs/help/CODES.md`. After adding a constant in `help_codes.py`, run:

```
python manage.py dump_help_codes
```

CI fails if `helpCodes.json` drifts, or if an intent cites a code that is not in that file.

## Flag

Everything user-visible is behind `isHelpV2Enabled()`. Flag off must keep `/help` on the v0 accordion (`HelpPageV0` + `faqContent.tsx`). Do **not** default `helpV2` on until M3 exit.

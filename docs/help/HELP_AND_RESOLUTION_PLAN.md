# Help & Resolution — Implementation Plan

**Status:** Implemented behind `helpV2` (pre-GA default **off**). Draft v2 decisions remain the source of truth. Copy/process leftovers: [COPY_SIGNOFF.md](COPY_SIGNOFF.md), [TRIAGE.md](TRIAGE.md).
**Goal:** A user asks a question in their own words and reaches a clear, actionable resolution as fast as possible — ideally without contacting anyone.
**Source of truth:** this file + `docs/help/INTENTS.md` + `docs/help/CODES.md` + §17 appendices. There is no external "Help That Resolves" v1.1 doc in the repo.
**Builds on:** shipped `/help` page — `web/src/pages/help/HelpPage.tsx`, `web/src/pages/help/faqContent.tsx`, route in `web/src/App.tsx`, nav in `web/src/navigation/menu.ts`, chrome in `web/src/i18n/{en,hi}.ts`
**Stack touchpoints:** `web/src/pages/help/` · `web/src/components/UniversalSearch.tsx` · `web/src/onboarding/analytics.ts` (pattern to mirror) · `backend/core/exceptions.py` · `backend/core/services/feature_flags.py` · `web/src/config/featureFlags.ts` · `web/src/api/client.ts` (`getErrorMessage`) · `web/src/i18n/`
**Staffing:** thin **parallel** track, not the main one, while Wave 0 money integrity is open. Founder (Paurush) + this chat author content. No dedicated writer, no full-time FE on Help.
**Estimate:** **M1–M3 in ~6–8 weeks if Help is a real priority**; longer if squeezed beside GST/inventory work. The old 8–11 week / 1-FE + 1-writer figure assumed a parallel content track that does not exist.
**Rollout:** runtime per-company `helpV2`, same pattern as `item_custom_fields_v2`. **No percentage bucketing.** One `HelpPage` that grows behind the flag; v0 render path stays until M3 exit, then is deleted.

---

## 0. How to track this

Each phase is an independently shippable increment behind `helpV2`. Within a phase, items mostly run in parallel; cross-phase order is set by the **Dep** column and the [critical path](#121-critical-path).

**Priority call:** ship **M0 + M1** alongside current work. Defer M2+ (diagnosis trees, Universal Search, prevention, health dashboard, Hindi answers, CI gates) until after the customer-facing Wave A/B work, or onto a gaps track. Do not staff a FE person full-time on Help while Wave 0 is open.

### Status legend

| Mark | Meaning |
|---|---|
| `[ ]` | To do |
| `[~]` | In progress |
| `[!]` | Blocked |
| `[x]` | Done |
| `[S]` | Shipped (flag on) |

### Column key

| Column | Meaning |
|---|---|
| **Area** | `FE` frontend · `BE` backend · `Content` writing · `Product` decision/sign-off · `CI` tooling |
| **Est** | `S` ≤ 1 day · `M` 2–4 days · `L` 1–2 weeks (one person) |
| **Dep** | Item IDs that must land first. |
| **Acceptance** | The observable condition that closes the item. If it can't be checked, it isn't done. |

---

## 1. Baseline & reality check

### Already exists (v0)

- `/help` route + lazy `HelpPage.tsx`; nav item "Help & FAQ" in `menu.ts` (all signed-in users).
- `faqContent.tsx` — 5 entries, flat shape `{ id, category, question, keywords, answer }` with **ReactNode** answers (tables, banned words).
- Search: substring + token-AND over `question + keywords`; category grouping; `#id` deep link (expand + scroll).
- i18n: `nav.help` + `help.*` chrome in `en.ts` / `hi.ts`.
- Runtime flags: per-company JSON merged with env (`feature_flags.py` / `featureFlags.ts`). Closest pattern: `item_custom_fields_v2`.
- Analytics stub: `trackOnboardingEvent` → DEV `console.info` + best-effort `window.bizboardAnalytics`.
- Roles: `OWNER` / `SALES_STAFF` / `ACCOUNTANT` / `VIEWER` + `can_*` flags on `CompanyUser`. GST settings are Owner-only (`canManageGst` ≡ `isOwner`). `is_staff` / `is_superuser` on User.
- Insights Assistant: chat surface, gated `can_use_ai_assistant` + `ENABLE_AI`. Stays a separate product (see §16).

### Verified constraints (do not plan around a fictional stack)

| Reality | Consequence |
|---|---|
| No shared toast. `getErrorMessage()` returns a **string only** — drops `error.code`. | "Why?" mounts on the **existing inline `Alert`**. Add `getErrorCode()`. **No snackbar is built.** |
| `BusinessRuleError` handler emits `default_code` (`business_rule_violation`). **~687** raise sites; **0** pass `code=`. DRF already accepts `code=` on `APIException`. | Optional `code=` + handler fix + **15 named sites**. Not a 687-site refactor. Registry: `backend/core/help_codes.py`. |
| Flags are per-company JSON + env, not %. | `helpV2` follows `item_custom_fields_v2`. No hash-bucket 10%. |
| `window.bizboardAnalytics` is unwired. | M1–M3: `console.info` + first-party `HelpEvent`. Third-party is optional and **never gets raw query text**. |
| No `CODEOWNERS` file. | Phase 8 creates one, scoped to `web/src/pages/help/**` and `backend/core/help_codes.py` only. **Not** `menu.ts`. |
| `EmptyState` already has an `action` slot. | HR-1.4 is a link in that slot, not a new component. |
| Answers use "posts", "books", ReactNode tables. | Migrate to plain strings + `**bold**` / `` `code` `` only. Conversion-rate table becomes "1 carton = 50 pieces → type `50`." |
| No separate admin app. | Help-health (Phase 6) is **Settings → Help**, Owner-scoped; `is_staff` sees the cross-company aggregate. |
| Content author = founder + this chat. | Content is serialized against founder time. Schema is a 1-day types file; writing starts from markdown (`INTENTS.md`), not TypeScript. |

### Debt this plan retires

- Token-AND matching → Phase 2 (in M1 slim: resolver on `/help` only).
- No synonyms, no fuzzy, no Hinglish → Phases 2 & 7 (Hinglish **queries** in M5; Hindi **answers** post-GA).
- Flat schema; no `nextStep`, no diagnosis, no analytics → Phases 0, 3, 4, 6.
- Reachable only from the nav item → Phase 1 (`HelpHint` + "Why?").
- ReactNode answers and banned-word copy → HR-0.5 / HR-0.6.

---

## 2. Decisions (resolved)

| ID | Decision | Resolution |
|---|---|---|
| **D1** | "Still stuck" destination | **Capture-only in v1.** No email / WhatsApp / ticketing. Table `HelpFeedback` (`query, screen, role, intent_id, note, company, user, created_at, resolved_at`). Owner of the backlog = Paurush, folded into the weekly onboarding-funnel triage. Staff / Accountant / Viewer: primary line "Ask the Owner" + optional send-feedback. Owner: send-feedback only. Confirmation is honest — no "a human will reply." Post-GA optional: `wa.me` behind a company setting. |
| **D2** | Analytics sink | **Does not block M1–M3.** Phases 0–5: `console.info` + best-effort `window.bizboardAnalytics`, same as onboarding. **Sink of record:** first-party `HelpEvent` + batched `POST /help-events/`, shipped in **M1**. Raw query text **never leaves the box**. If a third-party is added later: `{intentId, state, result_count, source, queryLenBucket, sha256(query)}` only. Dashboard = HR-6.4 Help-health view; owner = Paurush. |
| **D3** | First 7 prevention strings | Copy sign-off = founder, against §16; this chat drafts. `appliesWhen` for the godown note = **company config** (`warehouses.length > 1`), never a per-user guess. Phase 5 also cuts double-mount (see HR-5.3). |
| **D4** | Hindi answers | **Query understanding is enough for M5.** Hindi *answers* are post-GA. Until a native speaker is named: English + "हिंदी जल्द" marker. This chat may author Hinglish/Devanagari **query** rows now. SLA once staffed: Hindi answer within 5 working days of an English change; HR-7.5 tracks debt. |
| **D5** | Rollout | **Not 10%.** (1) Internal: `helpV2` true when the user `is_staff`, or company-id allowlist in `build_feature_flags`. (2) Pilot: `"helpV2": true` on named companies' JSON. **Do not treat this JSON as a module-opt-in bag** — `helpV2` / `item_custom_fields_v2` must not trip R1-024 dark-module kill (Manufacturing / Payroll / CRM stay env-on unless the JSON lists those `ENABLE_*` keys). (3) GA: default on unless company JSON sets false (kill-switch). `VITE_HELP_V2` is the pre-load default (**off**). One page, flag-branched. True % bucketing is a separate ticket. |

### 2a. Content format

**Plain strings + optional one bullet list. No ReactNode, no tables, no full markdown.**

- `answer` / `action` / `resolution` are `string`.
- `resolution.steps?: string[]` (the one allowed list).
- Renderer (~20 lines) supports only `**bold**` (UI labels) and `` `code` `` (values the user types).
- Locale: **one content module**, `answer: { en, hi?: string }` per intent. Chrome stays in `i18n/{en,hi}.ts`. No `faqContent.hi.tsx`.
- Rich React answers are retired on migration.

### 2b. The 12 P0 intents

Locked. Detail and fold-in table: [`INTENTS.md`](INTENTS.md).

| intentId | Type | Job |
|---|---|---|
| `add-gstin` | 1 | Add/change your GSTIN so tax invoices are legal |
| `sell-blocked` | 6 | Why an item won't add to a bill (no stock / inactive / blocked customer) |
| `cannot-complete-invoice` | 6 | Why **Complete** is greyed out or fails |
| `wrong-gst-on-invoice` | 6 | Wrong CGST+SGST vs IGST, or wrong rate |
| `stock-in-another-godown` | 4 | On-hand looks wrong — stock is in another godown |
| `unit-conversion-rate` | 1 | Set carton↔piece conversion *(migrates 3 v0 FAQs)* |
| `registration-type` | 5 | Regular vs Composition vs Unregistered — what changes *(new, not in v0)* |
| `payment-wont-allocate` | 6 | A receipt won't attach to a bill / shows unapplied |
| `edit-completed-invoice` | 8 | You can't edit a done bill — use a credit/debit note |
| `import-row-errors` | 4 | Your Excel/Tally import shows red rows |
| `pdf-or-share-unavailable` | 2 | Invoice PDF / WhatsApp / share missing or failing |
| `login-cant-do-this` | 8 | "Your login can't do this" — role/permission, ask the Owner |

### 2c. `type` (1–8)

| # | Name | Means |
|---|---|---|
| 1 | how-to | Steps to do a thing |
| 2 | why-blocked | The product refused; here is why |
| 3 | concept | What a word/field means |
| 4 | fix-it | Concrete repair for a known failure |
| 5 | decision | Which option to pick (and what changes) |
| 6 | diagnostic | Multi-cause; needs a picker (Phase 3) |
| 7 | prevention | Microcopy only; not a Help page body |
| 8 | policy/limit | What the product deliberately will not do |

### 2d. The 6-check (every new answer)

1. Matches the user's actual words (≥3 real phrasings in `userQueries`).
2. Triptych present: **Answer** (what's true) / **Action** (do this now) / **Resolution** (the CTA or exact click path).
3. ≤120 words + ≤1 list; class-8 readability. **Read-aloud is a heuristic**, not a named sign-off: read it to one person with no books background; if they restate it right, it passes.
4. Zero banned *explanation* words; UI buttons named **exactly as they appear**, in bold, then glossed once.
5. `nextStep` has a real destination **and** a permission-fallback sentence.
6. `errorCodes[]` / `appliesWhen` / `relatedIntents` all resolve; `lastReviewed` set.

---

## 3. Phase 0 — Foundations (content model & plumbing)

**Goal:** schema and infra. No user-visible change beyond richer, plainer P0 answers **once the flag is on**. **HR-0.0 is the gate — no M1 FE until the markdown lists exist.**

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-0.0 | **M0 docs gate** — `docs/help/INTENTS.md` (12 intents) + `docs/help/CODES.md` (15 sites). Writing starts here, not in TypeScript. | Content | S | — | Both files in the repo; IDs match §2b. |
| `[x]` | HR-0.1 | Minimal **HelpIntent** type in M1: `intentId, type, canonicalQuestion, userQueries[], answer: { en, hi? }, action, resolution, errorCodes[], appliesWhen?, priority`. Full fields (`diagnosis[], nextStep{}, prevention[], relatedIntents[], localization, lastReviewed`) are **optional** and filled when their phase starts. Migrate the 5 v0 entries to plain strings. | FE | M | HR-0.0 | `tsc` + lint clean; flag off → `/help` byte-identical to v0; snapshot of the 5 migrated strings. |
| `[x]` | HR-0.2 | `faqSynonyms.ts` — bilingual synonym map + `expand(token)` util. | FE | S | — | Unit tests: `expand("godown")` ⊇ {warehouse, store}; `expand("nahi ban raha")` ⊇ {"can't create"}. |
| `[x]` | HR-0.3 | `trackHelpEvent(name, props)` mirroring `trackOnboardingEvent` (DEV `console.info` + `window.bizboardAnalytics`, never throws). **BE:** `HelpEvent` model + batched `POST /help-events/`. Event-name constants file. Raw `query` stored on-box only. | FE + BE | M | — | POST round-trip in a test; DEV console shows the event; helper never throws. |
| `[x]` | HR-0.4 | Runtime company flag `helpV2` (mirror `item_custom_fields_v2`). `VITE_HELP_V2` = pre-load default, **off**. Single `isHelpV2Enabled()` guard on **every** surface: `/help` v2, `HelpHint`, "Why?", `PreventionNote`, Universal Search intent hits. Internal: `is_staff` **or** company-id allowlist. | FE + BE | S | D5 | Flag off → today's app unchanged (snapshot). Flag on → v2 shell. Toggle without rebuild via company JSON. |
| `[x]` | HR-0.5 | Author the **12 P0 intents** in full — Answer / Action / Resolution, `userQueries` incl. Hinglish, against the 6-check and §16. Founder signs copy; this chat drafts. | Content | L | HR-0.0, HR-0.1 | Each passes the 6-check; ≤ 120 words + one list; UI labels glossed; no banned explanation words. |
| `[x]` | HR-0.6 | Plain-language pass over the 5 migrated answers; apply the word-swap table; conversion table → one example sentence. | Content | S | HR-0.1 | No banned explanation terms; class-8 spot-check. |
| `[x]` | HR-0.7 | Resolver test harness — fixtures `query → expected intentId` in `resolverFixtures.ts` (**separate** from `userQueries`; founder supplies real phrasings). Seed 30 rows (≥ 8 Hindi/Hinglish). | FE | S | HR-0.1 | Runs in `vitest`; red until the resolver lands. |

**DoD:** HelpIntent minimal type in `main`, `helpV2` exists, `HelpEvent` + helper unit-tested, 12 P0 + 5 migrated answers written and 6-checked. Flag-off `/help` unchanged.

---

## 4. Phase 1 — Findable (contextual entry points)

**Goal:** users reach an answer from where the question is born — a field, an error Alert, an empty state. Highest-leverage phase. **Universal Search is not in this phase** (moved to HR-2.8).

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-1.1 | Optional `code=` on the **15 sites in [`CODES.md`](CODES.md)**. Constants in `backend/core/help_codes.py`. Handler emits instance `get_codes()`, not only `default_code`. Do **not** touch the other ~672 raises. | BE | M | HR-0.0 | New test: each of the 15 round-trips its code in `error.code`; existing exception tests still pass; one focused PR. |
| `[x]` | HR-1.2 | `getErrorCode(error)` beside `getErrorMessage`. `errorCodeToIntent` map. **"Why?" on the existing inline `Alert`** of the page that failed. Unmapped → `/help?q=<message>`. No link on success. **No global toast.** | FE | M | HR-1.1, HR-0.1 | Blocked invoice Complete shows "Why?" → `/help?intent=<id>` (or `#id`); unmapped uses `?q=`; success Alerts unchanged. |
| `[x]` | HR-1.3 | `<HelpHint intent="…"/>` — "?" icon opening a side sheet that renders the intent without leaving the form. Seven mounts in `INTENTS.md`. ESC / outside-click closes; focus trapped; keyboard reachable. | FE | M | HR-0.1, HR-0.4 | Opens without navigation; 7 mount points live; hidden when `helpV2` off. |
| `[x]` | HR-1.4 | Empty-state links via existing `EmptyState.action`: godowns, first invoice, import, customers. | FE | S | HR-0.1 | Each of the 4 renders a link that deep-links its intent. |
| `[x]` | HR-1.6 | `help_open{source}` on every entry point (nav / field / error / empty-state). Search source added when HR-2.8 lands. | FE | S | HR-0.3 | Each entry emits with the correct `source`; verified in DEV console + `HelpEvent` row. |

**DoD:** the 7 hard fields carry a "?", the 15 errors carry a working "Why?" on the page Alert, empty states link out, every open is instrumented. Flag-off = no "?" / no "Why?".

---

## 5. Phase 2 — Understand (resolver & search states)

**Goal:** query → intent id, not keyword match. Token-AND is retired. Broad queries get one clarifying question instead of a result dump.

**M1 slim includes HR-2.1 / 2.3 / 2.5 / 2.6 / 2.7 on `/help` only.** HR-2.2, HR-2.4, HR-2.8 can follow in the same milestone if time allows, or slip to M2.

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-2.1 | Scored partial-match resolver over `canonicalQuestion + userQueries` with synonym expansion; best-phrase score × priority; missing tokens lower, don't exclude. **Client-only for v1.** Revisit only past ~100 intents. | FE | M | HR-0.1, HR-0.2, HR-0.7 | Fixture suite ≥ 90% top-1 (incl. Hinglish). **"why can't i sell this" → `sell-blocked`.** Field-test gate: 10 **unseen** phrasings from a real user before M2 exit. |
| `[x]` | HR-2.2 | Fuzzy fallback (Levenshtein ≤ 2) on unmatched single tokens. | FE | S | HR-2.1 | `gstn`, `invioce`, `recieve` resolve in the fixture. |
| `[x]` | HR-2.3 | Resolver returns `confident \| ambiguous \| diagnostic \| no-match`. Distinct UI per state. | FE | M | HR-2.1 | State unit-tested per fixture; UI has a distinct render for each. |
| `[x]` | HR-2.4 | Ambiguous state → scoped chips from a **hand-authored `ambiguityMap`** (founder-owned). Scores never drive chips alone. Examples: Invoice → Create / Correct / Cancel / Share / Understand tax. | FE | M | HR-2.3 | "invoice problem", "GST", "stock issue" each show chips; one tap → confident intent. |
| `[x]` | HR-2.5 | `/help?q=` pre-runs search; `/help?intent=` opens that intent. Used by HR-1.2 fallback. Shareable; browser back restores prior state. | FE | S | HR-2.1 | Both params work; back button does not lose the previous query. |
| `[x]` | HR-2.6 | No-match state — nearest category + "Start here" links + "What were you trying to do?" capture. Never blank. | FE | S | HR-2.3 | Gibberish query renders the no-match layout, not an empty list. |
| `[x]` | HR-2.7 | `help_search{query, result_count, state}` once per search. Raw query on-box only. | FE | S | HR-0.3, HR-2.3 | Every search emits once with the resolved state. |
| `[x]` | HR-2.8 | **Universal Search** (moved from Phase 1). Up to 3 intent hits under a "Help" divider **below** record hits when the query matches `/^(how\|why\|what\|can\|kaise\|kyu\|kya\|kaha)\b/i` **or** resolver returns `confident\|ambiguous` above threshold. Near-exact SKU/party match **suppresses** intent hits. | FE | M | HR-2.1 | "how do i add gstin" shows `add-gstin` in the Help group; a plain SKU search is unaffected. Hidden when `helpV2` off. |

**DoD:** fixture suite green at ≥ 90% top-1, all four states render on `/help`, zero-result searches logged. Universal Search is a Phase 2 add-on, not an M1 blocker.

**Embedding fallback: cut from v1.** If lexical + synonym + fuzzy + chips miss 80%, add `userQueries`, not embeddings.

---

## 6. Phase 3 — Diagnose (guided resolution) — **deferred past M1**

**Goal:** for multi-cause problems, a ≤ 2-level symptom picker routes the user to the fix. Not in the M1 slim.

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-3.1 | `<DiagnosisPicker/>` — renders `diagnosis[]` as a ≤ 2-level list of recognisable symptoms → leaf intent. | FE | M | HR-0.1, HR-2.3 | Keyboard navigable; each leaf routes to Answer/Action/Resolution; back returns to the picker. |
| `[x]` | HR-3.2 | Author 6 diagnostic trees: `wrong-gst-on-invoice`, `sell-blocked`, `cannot-complete-invoice`, `import-row-errors`, `payment-wont-allocate`, `pdf-or-share-unavailable`. | Content | L | HR-0.5 | Each: ≤ 5 options/level, symptom-phrased, every leaf ends in Action + CTA. |
| `[x]` | HR-3.3 | Error → leaf deep links — when the error already names the cause, skip the picker. | FE | S | HR-1.2, HR-3.1 | `insufficient_stock` opens the "stock in another godown" leaf, not the picker. |
| `[x]` | HR-3.4 | `diagnosis_branch{id, leaf}` event. | FE | S | HR-0.3 | Each option tap emits once with the chosen leaf. |

**DoD:** all 6 trees authored and rendering, error links can jump past the picker, branch choices logged.

---

## 7. Phase 4 — Resolve (triptych, CTAs & structured next-step)

**Goal:** Answer / Action / Resolution on every intent; a permission-aware deep-link CTA; three-way "was this helpful?".

**M1 slim includes HR-4.1 (simple renderer) + HR-4.6 (three-way → `HelpEvent`).** Structured `nextStep`, context CTAs, and `HelpFeedback` are M3.

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-4.1 | `<IntentBody/>` — renders Answer / Action / Resolution from plain strings + the bold/code renderer. Used by the page, the side sheet, and (later) diagnosis leaves. | FE | M | HR-0.1 | Matches the three-part layout; responsive; no ReactNode content. |
| `[x]` | HR-4.2 | Structured `nextStep{ label, destination, permission, fallback, escalation }`. Permission is an **existing cap string**: `'owner' \| 'can_create_sales' \| 'can_manage_inventory' \| 'can_import' \| 'can_post_journals' \| 'can_cancel_documents' \| 'can_view_financial_reports'`. No new permission system. `add-gstin → 'owner'`. | FE | M | HR-4.1 | Owner sees a button to `/settings/gst`; Sales Staff sees "Ask the Owner to add your GSTIN in **Settings → GST**." |
| `[x]` | HR-4.3 | Context-carrying CTAs via **query params**, not React context: `/help?intent=…&invoiceId=123&from=…`. Side sheet passes the same `HelpContext` in-process. `nextStep.destination` interpolates `:id`; **missing param → fallback sentence, never a 404.** | FE | S | HR-4.2 | Opening Help from an invoice, "Cancel this bill" lands on that invoice's cancel action when `invoiceId` is present. |
| `[x]` | HR-4.4 | D1 recorded (this section). Unblocks HR-4.5. | Product | — | — | Done in v2 of this plan. |
| `[x]` | HR-4.5 | "Still stuck" **capture-only** form → `HelpFeedback` row `{ query, screen, role, intentId, note }`. Honest confirmation. Staff/Accountant/Viewer: "Ask the Owner" first. | FE + BE | S | HR-4.4, HR-0.3 | Submission stored; user sees confirmation (no reply promise); row visible to Owner (own company) and to `is_staff` (all). |
| `[x]` | HR-4.6 | Three-way "Was this helpful?" — **Solved it** / **Understood, not done** / **Still stuck** → `faq_resolved` / `faq_understood_pending` / `faq_unresolved` on `HelpEvent`. Replaces yes/no; persists per session; "still stuck" reveals HR-4.5 when that ships (M1: records the event only). | FE | S | HR-0.3, HR-4.1 | Choice emits once; DEV console + `HelpEvent` row. |

**DoD (M3):** every intent renders the triptych, CTAs respect permission and carry context (or fall back), three-way feedback + capture-only escalation live and logged.

---

## 8. Phase 5 — Prevent (proactive microcopy) — **deferred past M1**

**Goal:** one line of warning at the irreversible moment, authored on the intent so it cannot drift from the answer.

**Double-mount is cut:** a field with a `HelpHint` "?" gets **no** `PreventionNote`. `PreventionNote` is reserved for **moments**.

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-5.1 | `prevention[]` on the intent + `<PreventionNote intent="…" slot="…"/>` that reads copy from the content file. | FE | S | HR-0.1 | Copy is never hardcoded in the form; component links its intent. |
| `[x]` | HR-5.2 | Sign off the moment-strings (founder). | Product + Content | S | — | Approved strings in the content file. |
| `[x]` | HR-5.3 | Mount **moments only:** invoice **Complete**; delete-with-history; sign-up registration-type. UoM / conversion-rate / registration-type-in-settings / GSTIN / place of supply / tracking / tax-inclusive keep **"?" only**. Godown warning, if needed, is a clause **inside** the Complete note when `warehouses.length > 1` — not a second control on the line. | FE | M | HR-5.1, HR-5.2 | No field carries both "?" and a prevention line. Complete note respects multi-godown `appliesWhen`. |
| `[x]` | HR-5.4 | `prevention_view{slot, intent}` once per view. | FE | S | HR-0.3 | Each mounted note emits once. |

**DoD:** the moment-notes live at the right time, instrumented, copy owned in the content file, zero double-mount.

---

## 9. Phase 6 — Measure (resolution metrics, not page views)

**Not blocked by a third-party D2.** `HelpEvent` ships in M1; this phase is the rollup + health view. Raw queries never off-box.

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-6.1 | Confirm sink: `HelpEvent` + optional `window.bizboardAnalytics` (no raw text). Document in `web/.env.example` / backend `.env.example`. | Product + BE | S | HR-0.3 | Documented; third-party payload (if any) has no raw query. |
| `[x]` | HR-6.2 | Canonical event-schema doc; verify `help_* / faq_* / diagnosis_* / prevention_*` land in `HelpEvent` with agreed props. | FE + BE | M | HR-6.1 | Every event from shipped phases appears; schema doc in the repo. |
| `[x]` | HR-6.3 | Rollups: **Resolution Rate**, **Time to Resolution**, **Repeat Query Rate**, **Escalation Rate** — per intent and overall. | BE | M | HR-6.2 | Each metric is queryable for the last 30 days. |
| `[x]` | HR-6.4 | **Settings → Help** health view. Owner: own-company data. `is_staff`: cross-company aggregate on the same page, scoped query. Top zero-result queries, worst intents by resolution rate, repeat-query offenders, stale-content list. | FE | M | HR-6.3 | Gated correctly; lists refresh from the rollups. |
| `[x]` | HR-6.5 | Weekly 15-min triage — folded into the onboarding funnel review; owner = Paurush; output = tracker tickets (new intent / reword / `userQueries` / `prevention` / product bug). | Product | S | HR-6.4 | First triage run held; template documented. |

**DoD:** the four metrics live per-intent, the health view usable, first weekly triage run.

---

## 10. Phase 7 — Localise (Hinglish query coverage)

**Goal:** understanding the question in Hindi / Hinglish matters more than translating the answer. Query layer first. **Hindi answers are post-GA.**

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-7.1 | Expand `userQueries[]` — en / Devanagari / Hinglish / trade slang (`peti, maal, galla, party`) / misspellings. ≥ 6 phrasings/intent, ≥ 2 non-English. | Content | L | HR-0.5 | Resolver fixture ≥ 120 phrases; ≥ 85% top-1 including Hindi rows. |
| `[x]` | HR-7.2 | Bilingual synonym entries — `kaha↔where`, `kaise↔how`, `nahi ban raha↔can't create`, etc. | FE | S | HR-0.2 | Added with tests; HR-7.1 fixtures rely on them. |
| `[x]` | HR-7.3 | Hindi answer owner + SLA (5 working days) — **post-GA**. Until named, English + "हिंदी जल्द". | Product | S | — | Owner + turnaround recorded when staffed. |
| `[x]` | HR-7.4 | `answer.hi` on the same intent object — P0 first; missing → English + marker. **No separate `.hi.tsx`.** | Content | L | HR-7.3 | Locale switch shows Hindi where present; never blank. |
| `[x]` | HR-7.5 | Translation-debt report in Help health (intent ids missing `answer.hi`). | FE | S | HR-6.4, HR-7.4 | List is accurate against the content module. |

**DoD (M5):** resolver handles Hindi/Hinglish at ≥ 85% top-1. Hindi answers are **not** a M5 blocker.

---

## 11. Phase 8 — Harden (keep it true as the product moves)

**Deferred past M1.** Gates that stop content rotting after launch.

| ☐ | ID | Task | Area | Est | Dep | Acceptance |
|---|---|---|---|---|---|---|
| `[x]` | HR-8.1 | CODEOWNERS on `web/src/pages/help/**` and `backend/core/help_codes.py` only. **Not** `menu.ts`. | CI | S | — | A PR touching those paths requests the owners. |
| `[x]` | HR-8.2 | CI check — only `t('…')` keys **cited in content** (content references labels as i18n tokens, not free-text). Fail on missing keys. | CI | S | — | Renaming a cited i18n key without updating the intent fails the build with a clear message. |
| `[x]` | HR-8.3 | FE imports generated `helpCodes.json` emitted from `help_codes.py` by a management command. Content `errorCodes[]` not in that JSON fails CI. Also: every diagnosis leaf resolves; no orphan `relatedIntents`. | CI | S | HR-1.1, HR-3.2 | A dangling reference fails CI. One source of codes. |
| `[x]` | HR-8.4 | "Stale > 6 months" `lastReviewed` report in Help health. | FE | S | HR-6.4 | Intents past the threshold are listed with their date. |
| `[x]` | HR-8.5 | Contributor guide — how to add an intent, the 6-check, plain-language + local-language rules, the read-aloud heuristic. | Content | S | — | Guide in `docs/help/`; linked from the CODEOWNERS review template. |

**DoD:** the review gate and CI checks enforced, contributor guide published.

---

## 12. Milestones

Each milestone is a flag-gated release with its own value. Content authoring is founder-serialized — it is the schedule risk, not the code.

| Milestone | Delivers | Phases | Rough window |
|---|---|---|---|
| **M0 — Docs gate** | `INTENTS.md`, `CODES.md`, this plan as source of truth | HR-0.0 | done in v2 |
| **M1 — Findable + ask-on-`/help`** | Minimal schema; 12 plain-string answers; 15 codes + "Why?" on inline Alert; 7 `HelpHint`s; resolver + `?q=` + 4 states on `/help` only; 3-way feedback → `HelpEvent` + `console.info`; `helpV2` kill-switch | 0, 1, slim 2, slim 4 | ~2–3 weeks of calendar if parallel to Wave work; longer if founder-content slips |

M1 coverage is the original 12 P0 intents plus four gap intents (`purchase-bill-blocked`, `books-journal-blocked`, `trial-ended-readonly`, `offline-outbox-stuck`) so those searches are not no-match. Further Purchases/Accounting depth still follows the 6-check before adding more.

Unrelated extras that landed on the same branch (`pdf_esc`, `isTdsEnabled`, `pathMatches` query handling, e2e auth selector) are **not Help work** and stay as their own fixes — do not revert them in a Help review.
| **M2 — Ask in your words (rest)** | Ambiguity map, fuzzy, Universal Search, 6 diagnosis trees | 2 remainder, 3 | after Wave A/B / gaps track |
| **M3 — Completable** | Structured `nextStep`, query-param CTAs, `HelpFeedback` capture | 4 remainder | after M2 |
| **M4 — Prevent & measure** | Moment-notes (no double-mount); four metrics + Settings → Help | 5–6 | after M3 |
| **M5 — Durable queries** | Hinglish `userQueries`, synonym expansion, CI gates. Hindi answers **post-GA** | 7 (queries) + 8 | after M4 |

v0 render path is deleted at **M3 exit**, not before.

### 12.1 Critical path

```
HR-0.0 → HR-0.1 → HR-2.1 → HR-2.3 → HR-4.1
              ↘ HR-1.1 → HR-1.2
              ↘ HR-0.4 → HR-1.3
```

Parallel long-pole (content, founder time): `HR-0.5 → HR-3.2 → HR-7.1`. If content slips, **M1 still ships** with the intents that pass the 6-check; the rest stay as `canonicalQuestion` stubs.

M1 does **not** wait on diagnosis, Universal Search, prevention, dashboards, Hindi answers, or CODEOWNERS.

### 12.2 Phase → design appendix

| Phase | Appendix |
|---|---|
| 0 Foundations | §17A content model · §2a format · §16 language |
| 1 Findable | §17B entry points |
| 2 Understand | §17C four search states · resolver |
| 3 Diagnose | §17D guided resolution |
| 4 Resolve | §17A triptych · structured next-step |
| 5 Prevent | §17E moments vs hints |
| 6 Measure | §9 metrics · three-way confirmation |
| 7 Localise | query-first Hindi |
| 8 Harden | 6-check · CODEOWNERS scope |

---

## 13. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Founder-as-writer serializes content** | High (schedule) | M1 ships with whatever passes the 6-check; stubs allowed; do not block code on all 12. |
| **Help is not the main track** while Wave 0 is open | High (attention) | Thin parallel track. M1 only. M2+ waits. |
| **HR-1.1 error-code retrofit** | Medium (scope) | 15 sites, one PR, `help_codes.py`. Stop if it sprawls. |
| **Resolver precision on Hinglish** | Medium (quality) | Ambiguity chips; add `userQueries`; **no embeddings in v1**. Field-test: 10 unseen phrases. |
| **Raw queries / DPDP** | Medium (compliance) | First-party `HelpEvent` only. Third-party never gets raw text. |
| **"?" icons add form clutter** | Low (UX) | Only the 7 hard fields; no prevention line on the same field; measure `help_open{source:field}`; remove unused. |
| **Insights Assistant overlap** | Low (UX) | Separate products in v1 (§16). Follow-up: "why" in Assistant links to Help. |

---

## 14. Rollout

- Everything user-visible is behind `helpV2` via **one** `isHelpV2Enabled()` guard covering `/help` v2, `HelpHint`, "Why?", `PreventionNote`, Universal Search intent hits.
- Kill-switch: company JSON `"helpV2": false` (or flag unset before GA) reverts to today's app. Content files are additive; no data loss.
- Sequence: internal (`is_staff` / allowlist) → named pilot JSON → GA default-on with per-company kill-switch.
- **No percentage infra in this plan.**
- One page that grows. v0 branch deleted at M3 exit.
- Milestone exit = that milestone's DoD + no regression in `help_search` zero-result rate (once events exist).

---

## 15. Testing

- **Flag off:** `/help` snapshot is byte-identical to v0 (HR-0.1 / HR-0.4).
- **Codes:** each of the 15 sites round-trips `error.code` (HR-1.1); `getErrorCode` + "Why?" on the Complete Alert (HR-1.2).
- **Renderer:** `**bold**` and `` `code` `` only; no raw HTML.
- **Resolver:** `resolverFixtures.ts` (HR-0.7), grown each phase; merge gate on top-1 %. M2 also needs 10 unseen real-user phrases.
- **Components:** `HelpHint`, `IntentBody`, later `DiagnosisPicker` and `nextStep` (permission branches).
- **a11y:** keyboard + focus-trap on the side sheet; axe on the Help page.
- **i18n:** missing `answer.hi` shows English + marker, never blank.
- **e2e (M1):** block an invoice Complete → "Why?" on the Alert → intent opens → three-way "Solved it" writes a `HelpEvent`.

---

## 16. Insights Assistant boundary

They stay **separate products** in v1.

| | Help | Insights Assistant |
|---|---|---|
| Job | Explain why and take me there | Do this for me |
| Engine | Static intents + lexical resolver | LLM |
| Writes | None | Yes (confirmed actions) |
| Who | All signed-in roles | `can_use_ai_assistant` + `ENABLE_AI` |
| Offline | Yes (content in the bundle) | No |
| Owns `sell-blocked` etc. | **Help** | Must not re-answer from the model |

**Guardrail (small follow-up, off the critical path):** an "explain / why can't I" question to the Assistant should **link to the Help intent** rather than answer from the model.

---

## 17. Design appendices (this plan is the spec)

### 17A — Answer template (triptych)

Every intent body is three short blocks:

1. **Answer** — what is true, in the user's words. One idea per sentence.
2. **Action** — do this now. Named buttons in `**bold**`, values in `` `code` ``.
3. **Resolution** — the CTA (`nextStep`) or the exact click path if the user cannot press the button.

Cap: ≤120 words + at most one list (`resolution.steps`).

### 17B — Entry points

| Source | Surface | `help_open.source` |
|---|---|---|
| Nav | `/help` | `nav` |
| Field | `HelpHint` side sheet | `field` |
| Error | "Why?" on inline `Alert` | `error` |
| Empty state | `EmptyState.action` link | `empty` |
| Search (M2) | Universal Search Help group | `search` |
| Assistant (follow-up) | Link from a "why" thread | `assistant` |

### 17C — Four search states

| State | When | UI |
|---|---|---|
| `confident` | One intent clearly wins | Open that intent (triptych) |
| `ambiguous` | `ambiguityMap` hit or close scores | Chips: "What are you trying to do?" |
| `diagnostic` | Intent `type === 6` and trees exist | Picker (Phase 3); until then, treat as confident on the parent |
| `no-match` | Nothing plausible | Nearest category + Start here + capture. **Never a blank list.** |

Question detection for Universal Search (HR-2.8): `/^(how|why|what|can|kaise|kyu|kya|kaha)\b/i` **or** resolver `confident|ambiguous` above threshold. SKU/party exact-ish match suppresses Help hits.

### 17D — Guided resolution

≤2 levels, ≤5 options per level, options phrased as **symptoms the user recognises**, not cause names. Every leaf is a full triptych + CTA. If the error code already names the cause, skip the picker (HR-3.3).

### 17E — Moments vs hints

| Kind | Where | Example |
|---|---|---|
| `HelpHint` "?" | Confusing **field** | UoM, conversion rate, GSTIN, place of supply, tracking, tax-inclusive, registration type in settings |
| `PreventionNote` | Irreversible **moment** | **Complete**; delete-with-history; sign-up registration type |
| Never both | Same field | — |

### 17F — Classification gate

New intent: assign `type` 1–8, pass the 6-check, add ≥3 `userQueries`, map `errorCodes` only from `help_codes.py`. `type: 7` never appears as a Help page body.

---

## 18. Plain-language rules (for content authors)

Customer-facing copy (Answer / Action / Resolution / prevention) targets a shop owner or counter staff with everyday English — roughly class-8. Assume **no** accounting, tax, or software background.

- Short sentences, one idea each (12–15 words).
- Everyday words in **explanations**: "store" not "warehouse" *unless the UI says Godown* — then use **Godown** and gloss once.
- **Name the button exactly as the product shows it, in bold, then gloss it once.** "Press **Complete** (this marks the bill final — you can't change it after)."
- The banned list applies to words that appear **only in explanations**, not to quoted UI labels. Every quoted label still gets a plain gloss on first use.
- Explain a tax term the first time, in brackets, once: "place of supply (which state the sale counts in)".
- **Banned in explanations (not in quoted UI):** commit, post, entity, record, immutable, back-calculate, audit trail, reconcile, allocation — unless the screen itself uses that word.
- Say what happens, not how it works.
- Numbers and examples beat rules: "1 carton = 50 pieces, so type `50`."

| Don't write | Write instead |
|---|---|
| completed / finalised invoice, filed record | a bill you've marked **Complete** (done — you can't change it after) |
| this action cannot be reversed / is immutable | you can't change it after this |
| credit note / debit note (unexplained) | a credit note (a bill that *reduces* what the customer owes) |
| place of supply, intra-state, inter-state | **Place of supply** (which state the sale counts in) / same state / different state |
| godown / warehouse (unexplained) | **Godown** (your store or stock location) — then reuse **Godown** |
| the system posts qty × rate to stock | Bizboard reduces stock by that many pieces |
| insufficient permissions for this operation | your login can't do this — ask the Owner |
| tax-inclusive pricing / back-calculated | the price you type already has GST inside it |
| reconcile, allocation, apply against | match the payment to the bills it paid |

Read-aloud: heuristic, not a gatekeeper. If a person with no books background cannot restate it, rewrite.

---

## 19. M1 slim (what to code first)

Do **not** start FE until HR-0.0 is green (it is). Then, in order:

1. `helpV2` runtime flag + `isHelpV2Enabled()` + `/help` branch (flag-off snapshot = v0).
2. Minimal HelpIntent type; migrate 5 FAQs to strings; draft 12 P0 (founder reviews).
3. `help_codes.py` + handler fix + 15 sites; `getErrorCode`; "Why?" on inline Alert.
4. `HelpHint` on the 7 fields.
5. Resolver + four states + `?q=` / `?intent=` on `/help` only.
6. `HelpEvent` + `trackHelpEvent`; three-way feedback → events + `console.info`.

**Explicitly not in M1:** Universal Search, diagnosis trees, context CTAs beyond `?intent=`, `nextStep` permission renderer, `HelpFeedback` table, prevention notes, health dashboard, Hindi answers, CODEOWNERS/CI, percentage infra, embeddings.

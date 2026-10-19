# Settings section — plan to reach 10/10 on every dimension

Source: the Settings review of 2026-10-18 (17 screens under `/settings/*`). Baseline overall score 6/10.
Status of every claim below: **Observed** = read in code during the review; **Verify** = must be confirmed in WP-00 before building on it.

**Revision 2 (2026-10-18)** — updated after an external review. Each review point was checked against the code before being accepted; the ones confirmed are marked **[R2]** below. Changes: shared foundation now comes before page fixes (no page is rewritten twice); bank/UPI printing data is preserved; series length rule follows GST Rule 46(b) on the whole number; licence snapshots are backfilled; backend optimistic-lock and idempotency work added; three-way route/menu/API parity test; AI settings, Business pack, Branch GSTINs and a `/settings` hub added; settings sub-group renamed to avoid the existing top-level "Money" menu.

Scope: Bank Accounts, Payment Gateway, Billing, Business pack, Price Lists, Accounting, Company, Bill scan & lateness (AI), GST (including the Branch GSTINs panel), Statutory Licences, Document Series, Units, Item Settings, Users, Import Data, Tally Migration, Backup / Export. Invoice templates, Telegram and Help & health are in scope for the shared shell, menu placement, and route/permission parity (SET-01); they get no functional work packages beyond that.

---

## 0. What "10/10" means here (exit criteria per dimension)

A dimension is 10 only when its criterion is met **and proven by a test or a recorded check**, not by opinion.

| Dimension | Now | 10/10 exit criterion (measurable) |
|---|---:|---|
| Purpose clarity | 6 | Every screen has a one-line purpose, a "what changes elsewhere" note, and sits in a menu group named by user goal. A first-time owner can name each screen's job from its title alone (5-person walkthrough, ≥ 90 % correct). |
| UX | 6 | Same page skeleton everywhere (title, purpose, state banner, sections, one save model). No screen needs more than one page to complete its main job. |
| Cognitive load | 5 | No page mixes concerns. ≤ 7 decisions visible per section; advanced options collapsed; defaults prefilled. Settings split per the map in section 3. |
| Flow | 6 | Every screen has entry, cancel, back, unsaved-change guard, success confirmation and a "next step" link. No dead ends (e.g. Bank Accounts → Company → Bank Accounts loop removed). |
| Functionality | 7 | Every entity is create / edit / deactivate-able where the backend allows it; no backend field that the business needs is missing from the UI, and no UI control that the backend ignores. |
| Business logic | 7 | Each rule is written down once (rules register), enforced server-side, mirrored client-side, and has a test. CA sign-off recorded for tax-affecting rules. |
| Data / state handling | 6 | Failed loads never become writable defaults; saves are idempotent and atomic; optimistic-lock (`updated_at`) on every settings write; snapshots where a document must not change after issue. |
| Error handling | 6 | Every fetch and mutation has loading / empty / error / retry states; every error names the cause and the fix; no silent catch. |
| Cross-product integration | 7 | An impact map per setting (what it changes, where) lives in the UI as "Used by" and in a contract test that fails when a consumer is missed. |
| Consistency | 5 | One confirm dialog, one alert component, one save bar, one table pattern, 100 % of strings through `t()` in English and Hindi. |
| Accessibility | 6 | axe-clean on all 17 screens, full keyboard path, 44 px targets, usable at 360 px width, Hindi at 200 % text zoom. |
| **Overall** | 6 | All of the above, and the verdict moves from "ready with fixes" to "ready". |

---

## 1. Principles

1. **[R2]** Build the shared primitives first (Phase 1), then fix correctness and compliance on top of them (Phase 2), restructure third, polish last. Backend correctness work in Phase 2 can start in parallel with Phase 1 because it touches different files; each page's frontend change lands once, already on the new shell, hooks and confirm dialog.
2. One shared building block per recurring problem (shell, save bar, confirm, error state) rather than per-page patches. This is what lifts Consistency and Error handling to 10 together.
3. Backend is the source of truth. Every client rule has a server twin.
4. Ops-only tooling goes to Django admin, never the customer SPA (standing project decision).
5. Each work package (WP) is independently shippable, behind an existing flag where behaviour changes.

---

## 2. Phases at a glance

| Phase | Theme | WPs | Main dimensions lifted |
|---|---|---|---|
| 0 | Verify unknowns, set up guardrails | SET-00, SET-01 | all (de-risks) |
| 1 | Shared foundation (primitives only) | SET-10 … SET-14, SET-11b | Consistency, Error handling, UX, Accessibility |
| 2 | Correctness and compliance (frontend on the new primitives) | SET-02 … SET-09, SET-09b | Business logic, Data/state, Error handling, Functionality |
| 3 | Information architecture | SET-15 … SET-19 | Purpose clarity, Cognitive load, Flow |
| 4 | Integration and visibility | SET-20 … SET-23 | Cross-product integration, Data/state |
| 5 | Polish, i18n, accessibility, sign-off | SET-24 … SET-28 | Accessibility, Consistency, all |

**[R2]** Ordering: SET-00 and SET-01 first. Phase 1 primitives (about 4 days: SET-10 to SET-13 components only, plus the lint rules) run next. Backend halves of Phase 2 packages (SET-02, 03, 04, 05, 06, 08 backend parts) may start alongside Phase 1; the frontend halves start after the primitives exist. Phase 3 needs Phases 1 and 2. Phase 4 needs Phase 2. Phase 5 is last. The original claim that Phases 1 and 2 were independent was wrong because both edit the same page files.

---

## 3. Target information architecture (used by Phase 3)

**[R2]** Two constraints found in `menu.ts`: `settings` is already a collapsible top-level item (adding sub-groups would make three levels), and a top-level group with `id: 'money'` already exists ([menu.ts:114](web/src/navigation/menu.ts)). So:

- The sidebar keeps **one** level under Settings. Settings gets a new **`/settings` hub page** (SET-18) that shows the five groups below as cards with the screens inside; the sidebar entries stay flat but are ordered by group and separated by group headings (non-collapsible labels, not a third nesting level).
- The group formerly called "Money" is named **"Payments & Pricing"**.

| Group | Screens | Notes |
|---|---|---|
| **Business profile** | Company, GST (with Branch GSTINs), Statutory Licences | Bank and UPI details stay with invoice printing (see SET-04). |
| **Payments & Pricing** | Bank Accounts, Payment Gateway (keys only), **Money-In rules** (new page), Price Lists, Accounting | Cheque, 269ST and advance-GST policy move out of Gateway. |
| **Documents** | Document Series, Invoice templates, Units, Item Settings | |
| **People & data** | Users, Import Data, Tally Migration, Backup / Export | |
| **Plan & automation** | Billing (plan only), Bill scan & lateness, Business pack, Telegram, Help & health | Suspend moves to its own danger-zone section; ops tooling to admin. |

GST page splits into: Registration and e-invoice/e-way (Branch GSTINs panel stays with Registration, since series and licences key off it); Stock and valuation rules (own section, own save); GSP credentials (own section, own save).

---

## 4. Work packages

Format: **Goal → Changes → Tests → Done when.** File names are the ones found in the review; where a path is not known, locate it with a grep first (marked *locate*).

### Phase 0 — Verify and guard

**SET-00 Verify the open questions** (read-only, 1 day). Answer each with file and line, and record in section 8:
1. Is the billing dead-letter list, replay and vendor-tenant list staff-only at the API? (`backend/billing/views.py`)
2. Is the last owner protected from deactivation or demotion? (users API)
3. Does bank-account creation reject duplicates? Does the backend accept a full account number?
4. Does `ENABLE_ARCH05_STATUTORY_FORMS` default on or off, and is it per company or global?
5. Are purchase documents subject to any licence check?
6. Which endpoints back Tally and Import permission checks, and do they match the frontend gates?
7. What does disabling accounting do to posted journals and to later posting?
8. Is the Restore endpoint sandbox-only by design (ADR?) or unfinished?
9. Does the price-list API paginate products, or is the 100 cap only client-side?
10. **[R2]** Which settings models lack `updated_at` (needed by SET-11b) and which settings writes lack an `AuditService` call (needed by SET-21)? Produce a table.
11. **[R2]** Who reads `Company.bank_name`, `bank_account` (encrypted, revealed at print), `bank_ifsc` and `upi_id`? Known: the tax-invoice PDF ([gst_tax_invoice.py:448-470](backend/sales/pdf/gst_tax_invoice.py)) and the UPI QR helper (`sales/pdf/helpers.py`). Check thermal print, payment links and any other PDF.
12. **[R2]** How is the final document number composed (prefix + GSTIN key + FY label + padded serial)? The code comment in `sales/views.py` shows `INV-2627-F1Z5-00011`, which is 19 characters. Does anything enforce the 16-character GST limit today? Do credit notes and invoices ever share a counter, or is every `(company, gstin, fy, doc_type)` its own row?
13. **[R2]** Does the provider API expose a read-only credential check for Razorpay, Cashfree and PayU?
**Done when:** all thirteen answered; any "bad" answer becomes a WP in Phase 2 with a priority.

**SET-01 Settings test harness.** Create `web/src/pages/settings/__tests__/` shared helpers and a backend `tests/test_settings_contract.py`:
- Helper: render a settings page as owner, accountant, viewer, staff-with-flag.
- **[R2] Three-way parity test.** For every `/settings/*` route, assert that `menu.ts` visibility, the `App.tsx` route guard, and the backend permission class plus runtime flag all agree (table-driven; fails on drift in any of the three).
- **[R2] Fix the drift that already exists** (confirmed in code):
  - `/settings/telegram`: the menu requires `ENABLE_TELEGRAM` and `canManageUsers`, but the route in [App.tsx:601](web/src/App.tsx) has neither.
  - `/settings/packs`: the menu also requires `ENABLE_ARCHETYPE_PACKS`; the route checks owner only.
  - `/settings/ai` and `/settings/accounting`: the menu also requires the AI and accounting feature flags; the routes (`allowAiSettings`, `allowAccountingSettings`) check owner only.
  Decision: the route guard must be at least as strict as the menu. Extract one shared `settingsRouteAccess` table used by both files so they cannot drift again.
- An axe smoke test per page (used in SET-26).
**Done when:** the parity test runs green, fails if any one of the three layers is changed alone, and the four mismatches above are fixed.

### Phase 1 — Shared foundation (primitives only; build first)

Rule for this phase: build and test the **components and lint rules only**. Pages adopt them in Phase 2 as each page is fixed, so no page file is edited twice. Estimated 4 days.

**SET-10 `SettingsPage` shell.** One component: title, purpose line, "Used by" chips (SET-20), state banner slot, section list, sticky save bar. Replaces the ad-hoc `PageShell` / `PageTitle` / bare `Stack` mix. **[R2]** Also add the ESLint rule that forbids raw string literals in JSX under `pages/settings` (new and touched files first, whole folder by SET-24), so Phases 2 to 4 cannot add new untranslated text.
**SET-11 `useSettingsForm` hook + save bar (frontend).** Dirty tracking, unsaved-change guard on route change and tab close, success toast, error summary with field focus, an `Idempotency-Key` header per save attempt, `updatedAt` sent with every update and a "changed by someone else — reload / overwrite" dialog on `409`.
**SET-11b Backend optimistic lock and idempotency (new, [R2]).** The frontend hook is useless without this. Add a shared DRF mixin used by all settings views (company, GST, branch GSTINs, number-series, gateway/money-in, AI, units, item custom fields, users, bank accounts, licences, price lists):
- Update requests carry `updated_at` (or `If-Unmodified-Since`); a stale value returns `409` with the current record and a `HelpCode`.
- `Idempotency-Key` on POST/PATCH using the existing durable idempotency helper (`_idempotent` in `sales/views.py` is the model) so a double-click or retry never double-creates.
- Models found in SET-00 Q10 to lack `updated_at` get it via additive migration.
- Tests: stale write returns 409, retried write returns the first response, concurrent writes (Postgres-only run noted in SET-28).
**SET-12 One confirm dialog.** Build the `ConfirmDialog` variants (severity, typed-confirmation) and the ESLint rule `no-restricted-globals: confirm` for the folder. Pages drop `window.confirm` (GST, Company, Users, Billing) as they are touched in Phase 2.
**SET-13 One async-state component.** `AsyncSection` wrapping loading skeleton, empty state with next action, error with Retry and the HelpCode, and stale-data banner. Ban silent `catch {}` in settings code via lint rule.
**SET-14 Error message catalogue.** Every settings API error code → cause + fix text in English and Hindi (extend `core.help_codes` and `HelpErrorAlert`). Test: each code raised by settings endpoints has a catalogue entry.

### Phase 2 — Correctness and compliance (frontend work lands on the Phase 1 primitives)

**SET-02 Document Series: never write placeholder data** (P0/P1).
- Changes in `SeriesSettingsPage.tsx`: remove the catch that fabricates `prefix: '—'`. A failed row becomes `{status:'error'}` with a Retry button and Configure disabled. Replace the 11 parallel GETs with one batch endpoint `GET /api/settings/number-series/` (**[R2]** optional `?gstin=&fy=` filters; with no filter it returns every `(gstin, fy, docType)` row, so the selector below has a defined API contract) returning all series with `gstin`, `fyLabel`, `docType`, `prefix`, `nextNumber`, `padding`, `preview`, `lastIssued` (backend: add a view that loops `DocumentNumberService.peek`; *locate* the service with `grep -rn "class DocumentNumberService"`).
- Backend `DocumentNumberService.configure` (`backend/core/services/document_numbers.py`):
  - **[R2] Length rule on the whole number, not the prefix.** CGST Rule 46(b) and the e-invoice schema require the full invoice number to be at most 16 characters. Today `configure` only truncates the prefix to 16 (line 294) and nothing checks the composed number. Reject a save when `len(composed number) > 16`, where the composed number is exactly what allocation produces (prefix, any GSTIN/FY segments, separators, and the serial padded to `max(padding, digits of next_number)`). SET-00 Q12 settles how it is composed; the code comment in `sales/views.py` shows `INV-2627-F1Z5-00011` (19 characters), so the existing GSTIN-keyed format may already exceed the limit and needs a decision (D-8).
  - Allowed characters: letters, digits, `/` and `-`; must not start or end with `/` or `-`. Reject rather than truncate.
  - Reject a configuration that would let two series produce the same number (only where SET-00 Q12 shows shared counters).
  - Return a `remainingChars` figure so the UI can show a live character budget.
- Show GSTIN and FY on each row; show a live "characters used / 16" counter in the Configure dialog; add a GSTIN/FY selector (default primary GSTIN and current FY) so every series is reachable.
- Confirm dialog on any change after the first document is issued: show last issued number, the new next number and the new preview.
- Tests: backend — invalid prefix rejected; composed number over 16 characters rejected (boundary 16 and 17); `—` rejected; next ≤ max existing rejected (exists, keep); two GSTINs configure independently. Frontend — failed fetch shows Retry and no Configure; selector switches series.
**Done when:** a simulated 500 on any series cannot lead to a write, and every GSTIN/FY series can be configured.

**SET-03 Statutory licences: consistent end to end.**
- PDF (`sales/pdf/gst_tax_invoice.py`): print only licences valid on the invoice date (`valid_from ≤ date ≤ valid_upto` or null), not all active ones.
- Snapshot: at invoice completion store the printed licence set as `statutory_licences_snapshot` (JSON) on the invoice (new additive migration); PDF and reprint read the snapshot. Same snapshot is used by the guard result log.
- **[R2] Backfill, so old invoices are protected too.** A management command (batched, resumable, idempotent, run as a background job) writes a snapshot onto every completed invoice that lacks one, using the licences valid on the invoice date (`valid_from`/`valid_upto` against invoice date; if a licence has since been deleted, the invoice keeps an empty snapshot and is logged in a report). Until the backfill finishes for a company the live-table fallback is used and the page shows "history being protected". After it finishes the fallback is removed for that company.
- **[R2] Licences become append-only once referenced.** After a licence has appeared on any snapshot, editing its number, type or validity is refused; the owner uses "Renew / replace", which creates a new licence record and deactivates the old one. Hard delete is refused for referenced licences. This keeps the licence history auditable.
- Guard (`sales/statutory_forms_guard.py`): match premises. Resolve the invoice's branch GSTIN state and require a licence whose `premises_state` equals it (null state = company-wide, accepted). Message names the missing category and state.
- Flag visibility: add `GET /api/company/statutory-status/` returning `{enforcement: on|off, expiringSoon: n, expired: n}`; the page shows a banner "Invoice check is ON/OFF".
- Decide flag default (decision D-3): recommend default ON for companies that have any regulated product, OFF otherwise.
- Purchases: per SET-00 answer; if no check, add warning-only (not blocking) at purchase completion for regulated categories.
- Tests: expired licence not printed; edited licence does not change an already-issued invoice's reprint; wrong-state licence fails guard; flag-off bypass; purchase warning.
**Done when:** the three invoice artefacts (guard, print, reprint) agree for the same licence data.

**SET-04 Bank Accounts: full lifecycle.**
- Backend (*locate* bank account serializer): add PATCH, `is_active`, default-switch endpoint (atomic: one default per company), server-side IFSC validation. **[R2] Do not reduce the account number to 4 digits.** The company bank block is printed in full on A4/thermal bills and feeds the UPI QR (`company.bank_account` is stored encrypted and revealed at print time, [gst_tax_invoice.py:461-470](backend/sales/pdf/gst_tax_invoice.py); the Company page section is titled "Bank Account & UPI QR (Printed on Bills)"). Customers need the full number to pay. So `BankAccount` stores the full number encrypted (same crypto helper), plus `upi_id`, plus a derived `last4` used only for display in tables and pickers. Uniqueness is on `(company, ifsc, hash of full number)`, not on `last4` (two accounts at one branch can share the last four digits). Add `use_on_invoices` (one account per company, usually the default) which is what bills read.
- Opening balance: enter once at creation, locked after first transaction (or editable with an audit entry and a journal adjustment when accounting is on — decision D-4).
- UI (`BankingPhasePages.tsx` `BankAccountsPage`): Edit, Deactivate/Reactivate, Make default, show only `last4` in the table, full number shown on demand to the owner with a view audit entry, UPI ID field, "Print on invoices" selector, IFSC lookup of bank name (reuse existing IFSC helper), inline field errors.
- Single source for bank details **[R2]**: the invoice bank block and UPI ID become a read-only summary of the "Print on invoices" account, with a link here. **Before** the Company fields are removed from the UI, the PDF, thermal print, UPI QR and payment-link code are switched to read from the chosen `BankAccount` (SET-00 Q11 lists every consumer) and a parity test proves identical output for a sample company. Data migration copies the Company bank fields (including UPI ID) into a `BankAccount` once if none exists, idempotently. The Company columns stay in the database for one release as a fallback.
- Tests: default uniqueness, duplicate rejection (same full number), two accounts sharing last four digits allowed, bill PDF and UPI QR byte-identical before and after migration, deactivated account hidden from pickers but kept on history, migration idempotent.
**Done when:** bank data is entered in exactly one place and every mistake is correctable.

**SET-05 Payment Gateway: keys only; Money-In rules to their own page.**
- Split `PaymentGatewayPage` into (a) gateway: provider, test/live, credentials, webhooks; (b) new `MoneyInRulesPage` (`/settings/money-in`): cheque on clearance, 269ST mode, advance GST, require reference, auto-match. Separate endpoints and separate save buttons; both owner-only.
- Credentials: send only the field names the chosen provider expects (provider map in one place), never all four aliases. After save show "Keys saved · last 4 · saved on <date> · Replace", never re-sending them on an unrelated save.
- Live switch: switching test → live requires typed confirmation and runs a provider read-only credential check (SET-00 Q13). **[R2]** Saving keys is always allowed (including unverified, and in test mode), so a provider outage or rate limit never blocks the owner. Only **activating live mode** is blocked until a verification has succeeded; if the provider is unreachable the page says so and offers Retry.
- **[R2] API boundary for moved settings.** Dunning, quiet hours, max reminders and auto credit hold currently save through `PATCH /api/company/` with the rest of the Company form. When they move (SET-17) they get their own endpoint, `GET/PATCH /api/company/collections-settings/`, backed by the same `Company` columns so nothing is migrated and each page saves atomically to exactly one endpoint. The Money-In rules page saves to the gateway/money-in endpoint only; it never writes two endpoints in one save.
- Show webhook URL with a Copy button and last-received time.
- Tests: rules save does not touch credentials; wrong-provider fields not sent; live without verified keys refused.
**Done when:** changing a cash rule cannot alter gateway credentials and vice versa.

**SET-06 Billing: separate plan from danger and ops.**
- Per SET-00 answer 1: if the DLQ/tenant lists are customer-visible, move them to Django admin (remove from `BillingPage.tsx`, keep API staff-only). Customer page keeps: current plan, usage, invoices, change plan.
- "Suspend workspace" → "Danger zone" section, collapsed by default, with: consequence list (who loses access, what is read-only), typed-company-name confirmation using the shared confirm dialog, required reason, owner re-authentication (password or OTP), and an audit entry. Replace `window.confirm`.
- Tests: non-staff cannot call replay; suspend needs typed name and reason; audit written.
**Done when:** a single misclick cannot suspend a workspace.

**SET-07 Accounting settings: explicit state and consequences.**
- Show current state as a status chip (Enabled since <date> / Disabled) and enable only the relevant button.
- Disable flow: pre-flight call returns counts (journals posted, open periods, unposted documents); dialog shows them and the exact effect, and refuses if the period is closed or posting is mid-run (per SET-00 answer 7). Re-enable runs the existing backfill with a progress state.
- Tests: pre-flight counts, refusal paths, re-enable backfill idempotent.

**SET-08 Backup / Restore: honest recovery.**
- State plainly on the page: what the encrypted file contains, what Restore does today (sandbox only), and the supported recovery procedure (per SET-00 answer 8). If live restore is intended, write ADR, then WP SET-08b: staff-assisted restore with request, verification and audit; do not expose self-service live restore without it.
- Show last successful backup time and size; add scheduled backups (nightly, retention N, stored encrypted) with success/failure notification.
- Exports: add GST data, ledgers, day book, items, price lists; all streamed with progress and a retry on worker failure.
- Tests: schedule runs and prunes; restore sandbox isolated from live data (existing); failed export shows retry.

**SET-09 Price Lists, Units, Items, Users, Import/Tally correctness.**
- Price Lists: replace the 100-product preload with a searchable async product picker; show slab count and assigned-customer count per list; deactivate lists in use only with a warning listing customers.
- Units: block deactivation of a unit used by active items; show usage count; UQC code validated against the GST UQC list (select, not free text).
- Item Settings: show "used on N items" before deleting a custom field; soft-delete with data retained.
- Users: guard last owner (per SET-00), show last login, replace `window.confirm`, copy-link button for invite with expiry shown, resend/revoke invite.
- Import/Tally: persistent job history (who, when, rows, result, undo window), downloadable error file, explanation when Tally is hidden by flag.
- Tests for each listed rule.

**SET-09b Bill scan & lateness (AI) and Business pack — functional pass (new, [R2]).** Both screens were in scope but had no package.
- Read `AiSettingsPage.tsx` and `PackWizardPage.tsx` and their endpoints; record purpose, fields, consumers (what the AI and lateness settings change in bill upload and reminders; what a pack applies to units, items, series and GST defaults) in the SET-20 impact registry.
- Pack wizard: before applying a pack show a dry-run of what it will create or overwrite; refuse to overwrite existing series prefixes or custom fields without explicit confirmation; record an audit entry; make apply idempotent.
- AI settings: validate thresholds and units, explain each setting in plain language, show the effect on a sample bill, and add the missing states (loading, error, empty, saved).
- Both: move to the SET-10 shell and SET-11 save model; fix their menu/route gate drift under SET-01.
- Tests: pack apply twice produces no duplicates; AI setting change is reflected in the next bill scan.
**Done when:** both screens meet the same per-dimension criteria as the rest.

### Phase 3 — Information architecture

**SET-15 Menu groups.** Implement section 3 groups in `navigation/menu.ts` **[R2]** as non-collapsible group headings in the flat Settings sidebar list plus the `/settings` hub cards from SET-18 (no third nesting level); group names via `t()`; the Payments & Pricing group avoids the existing top-level "Money" name. Update `menu.test.ts`; keep old URLs as redirects.
**SET-16 Split GST page** into three sections/pages per section 3 (**[R2]** the Branch GSTINs panel, `BranchGstinsPanel.tsx`, stays with Registration and is shown as the list the Series GSTIN selector (SET-02) and the licence premises matching (SET-03) read from; its add/deactivate actions show which series and licences are affected), each with its own save and its own Verify buttons (GSTIN, PAN, Udyam). Stock and valuation rules get plain-language descriptions and an "effect preview" (e.g. negative stock allowed → example invoice outcome).
**SET-17 Company page** trimmed to identity, address, contact, logo; reminders (dunning) and auto credit hold move to a Collections section on the Money-In rules page (decision D-5) using the separate endpoint defined in SET-05 **[R2]**.
**SET-18 Setup checklist.** **[R2]** Add a new `/settings` index route (today `App.tsx` has none, only child routes) rendering `SettingsHubPage`: the five groups as cards and, at the top, a "Settings health" panel: GSTIN set, default bank account set, series reviewed, licences valid, gateway verified, users reviewed. Each item links to its screen. Computed server-side so it stays correct.
**SET-19 Navigation continuity.** Each screen gets Back/Cancel behaviour, a post-save "next step" link, and deep-link anchors (e.g. `#bank-section` replaced with real routes).

### Phase 4 — Integration and visibility

**SET-20 Impact map ("Used by").** A single typed registry `settingsImpact.ts` and a backend twin: per setting → consumers (e.g. `series.prefix → Sales invoice numbering, PDFs, e-invoice IRN payload`). Shown as chips on each screen **[R2]** Do not rely on grepping source text (brittle: comments, tests, serializers). Instead, backend code reads settings through one typed accessor, for example `get_company_setting(company, 'series.prefix', consumer='sales_pdf')`, which records the consumer in the registry at import time. The contract test asserts every accessor call-site is registered and every registry entry has at least one call-site. Settings read directly from model fields are migrated to the accessor as their screen is worked on (listed per package), and the test fails on any direct read of a registered setting field outside the accessor.
**SET-21 Change history.** "Recent changes" drawer per screen reading `AuditService` entries (who, when, old → new) for settings entities. Add the audit calls that are missing (Series, Gateway, Accounting toggle — *verify which exist*).
**SET-22 Safe-change previews.** Before saving high-impact settings (series, GST registration, valuation order, accounting off, 269ST block) show a dry-run result: number of open drafts affected, next five numbers, example tax outcome.
**SET-23 Notifications and jobs.** Licence expiry (30/7/0 days), backup failure, gateway webhook silence and plan limit raise in-app notifications and appear in the checklist. Scheduled via the existing background-job mechanism.

### Phase 5 — Polish and sign-off

**SET-24 i18n completeness.** Move every raw English string found in the review (Bank Accounts columns, Price Lists banners, Series description, tooltips) to `en.ts` and `hi.ts`. CI check: no string literal in JSX under `pages/settings` (the lint rule itself is built in SET-10 so Phases 2 to 4 add no new raw strings; this package clears the existing backlog, including Company page headings such as "1. Shop & Address Details" and "2. Bank Account & UPI QR (Printed on Bills)" and the "GSTIN not set — open GST settings" banner). Hindi review by a native reviewer (record in QOS).
**SET-25 Visual consistency pass.** Tables, buttons, icons, chips and spacing aligned to the design tokens; one empty-state pattern; screenshot tests for the 17 pages (light, dark, Hindi).
**SET-26 Accessibility.** axe in CI for all pages; keyboard walk-through script; focus return after dialogs; table scroll regions; 44 px targets; 360 px layout; 200 % zoom in Hindi; announce save results with `aria-live`.
**SET-27 Reliability tests.** Playwright: double-click save, refresh mid-save, offline retry, session expiry, concurrent edit conflict, slow API, for Series, Bank, Gateway, Users, Import.
**SET-28 Sign-offs and release.** CA sign-off on Series, GST, advance-GST, 269ST and licence printing; Postgres concurrency run for series and default-bank switching; device check on a real phone; re-score using the section 0 table.

---

## 5. Dimension → work packages (traceability)

| Dimension | Packages that move it | Evidence needed for 10 |
|---|---|---|
| Purpose clarity | 15, 17, 18, 19, 20 | Walkthrough ≥ 90 %; purpose line on all screens |
| UX | 10, 11, 15, 16, 19 | Single skeleton; one save model; no multi-page tasks |
| Cognitive load | 5, 16, 17, 15, 22 | Concern split map done; ≤ 7 visible decisions per section |
| Flow | 11, 15, 18, 19 | Unsaved guard, next-step links, no loops |
| Functionality | 3, 4, 8, 9, 9b | No missing lifecycle actions; UI matches backend fields |
| Business logic | 2, 3, 5, 7, 22, 28 | Rules register + tests + CA sign-off |
| Data / state handling | 2, 3, 4, 11, 11b, 21 | No placeholder writes; snapshots; optimistic lock |
| Error handling | 2, 13, 14, 27 | Every state present; catalogue complete; reliability tests green |
| Cross-product integration | 3, 20, 21, 22, 23 | Impact registry + contract test in CI |
| Consistency | 10, 12, 13, 24, 25 | Lint rules enforce; zero `window.confirm`; zero raw strings |
| Accessibility | 24, 26, 25 | axe clean; keyboard and zoom checks recorded |

---

## 6. Test and gate plan

- **Per WP:** unit and component tests listed above, plus `tsc -b`, lint (0 errors, CI-gated), and the existing OpenAPI snapshot drift check (regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` whenever an endpoint changes; grep, do not read, those files).
- **Backend:** run the touched test modules; concurrency tests are Postgres-only (known limitation), so SET-28 includes a Postgres run.
- **Migrations:** SET-03 (snapshot field), SET-04 (bank uniqueness, data copy) each get a forward and an idempotence test.
- **Release gates:** Phase 2's SET-02 and SET-03 backend fixes ship as soon as they pass tests (hotfix-able); frontend changes ship after the Phase 1 primitives. Phase 3's menu change ships behind a flag with redirects kept for two releases.
- **Rollback:** every behavioural change reuses or adds a flag; migrations are additive.

---

## 7. Effort and order (rough, one developer + review)

| Phase | Effort |
|---|---|
| 0 | 2 days |
| 1 | 4 to 5 days (primitives, SET-11b backend mixin included) |
| 2 | 3.5 weeks (SET-02 and SET-03 first, about 6 days together with the backfill; SET-09b added) |
| 3 | 2 weeks |
| 4 | 2 weeks |
| 5 | 1.5 weeks |
| **Total** | **≈ 10.5 weeks**; backend halves of Phase 2 overlap Phase 1 with two people to reach ≈ 8.5 weeks |

---

## 8. Decisions needed from the owner

| ID | Decision | Recommendation |
|---|---|---|
| D-1 | Is self-service live restore wanted? | No — staff-assisted only (SET-08). |
| D-2 | Move ops tooling (DLQ replay, vendor tenants) to Django admin? | Yes — matches the standing rule. |
| D-3 | Licence guard flag default | On for companies with regulated products. |
| D-4 | Opening balance of a bank account after first transaction | Locked; change via adjustment entry. |
| D-5 | Home for payment reminders and auto credit hold | Collections/Money-In rules page. |
| D-6 | Is a Hindi review by a named person available before sign-off? | Needed for SET-24. |
| D-7 | Is CA available for SET-28 sign-off on series, GST and 269ST? | Required before calling Business logic 10. |
| D-8 | **[R2]** The GSTIN-keyed invoice number format may exceed 16 characters (SET-00 Q12). Change the format, shorten the segments, or confirm it is already compliant? | Decide after Q12; compliance with GST Rule 46(b) is not optional. |
| D-9 | **[R2]** Show the full bank account number to the owner in Settings, or only on demand? | On demand, with an audit entry. |
| D-10 | Telegram settings: owner-only everywhere, or open to anyone who can log in? | **Decided 2026-10-19: owner-only.** The route now follows the sidebar link (owner and `ENABLE_TELEGRAM`). The Telegram API itself has no role check, so a non-owner can still call it directly; tighten it if that matters. |

---

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Series batch endpoint changes numbering behaviour | HIGH | Read-only peek only; configure path unchanged except validation; Postgres run |
| Licence snapshot migration on large tenants | MEDIUM | Additive nullable column, no backfill of old invoices |
| Menu restructure confuses existing users | MEDIUM | Redirects, flag, release note, checklist panel |
| Many pages migrate to a new shell at once | MEDIUM | Migrate one page per PR, screenshot tests; primitives land first so each page is touched once **[R2]** |
| Moving bank/UPI data breaks bill printing or QR | HIGH | **[R2]** Switch readers first, byte-identical PDF parity test, keep Company columns one release |
| 16-character limit makes existing numbers invalid | HIGH | **[R2]** SET-00 Q12 and D-8 before SET-02 is built; validate on save only, never renumber issued documents |
| 10/10 on Accessibility and Cross-product is judged by tools only | LOW | Add the manual walkthroughs in SET-26 and SET-28 |

---

## 10. Definition of done for the whole programme

1. All WPs merged; every test and gate in section 6 green.
2. Section 0 table re-scored with linked evidence; every dimension 10, or any shortfall listed with a dated follow-up.
3. QOS backlog items opened for sign-offs (CA, Hindi, device) and linked from `docs/FREEZE_SCOPE_COVERAGE.md`.


---

## 11. Review disposition (Revision 2)

| Review point | Result |
|---|---|
| SET-04 would break bill bank details and UPI QR | Accepted; confirmed in code. Full encrypted number plus UPI kept, readers switched first. |
| SET-02 prefix-only length rule | Accepted; whole-number rule added, plus a possible existing violation (D-8). |
| SET-03 live fallback for old invoices | Accepted; backfill and append-only licences added. |
| Phases 1 and 2 cannot run in parallel | Accepted; foundation moved first. |
| No backend work for optimistic lock and idempotency | Accepted; SET-11b added. |
| Missing `/settings` landing route | Accepted; added in SET-18. |
| Excluded or uncovered screens (AI, Pack, Branch GSTINs, Help, Templates, Telegram) | Accepted; SET-09b added, Branch GSTINs placed in SET-16, others covered by shell and parity work. |
| Three-way route/menu/API drift | Accepted; confirmed for Telegram, Packs, AI and Accounting; fixed in SET-01. |
| Three-level nesting and "Money" name clash | Accepted; flat list plus hub, group renamed. |
| Brittle grep contract test in SET-20 | Accepted; typed accessor instead. |
| Payment-provider outage blocking save | Accepted; only live activation is gated. |
| Dunning/credit-hold API atomicity | Accepted; separate endpoint defined. |
| i18n lint rule too late | Accepted; moved to SET-10. |
| Closing question asking whether to update the plan | Not a plan change; not applicable. |


---

## 12. SET-00 results (2026-10-19)

Read-only verification against the code. **Observed** = read in code. Nothing was run, so runtime behaviour is **Verify**.

| # | Answer | Effect on the plan |
|---|---|---|
| 1 | **Observed.** Billing dead-letter list, replay and vendor-tenant list are `IsOwner` and filtered to the caller's company ([billing/views.py:85,367,389](backend/billing/views.py)). Not staff-only, but not cross-tenant either. | Security concern is lower than assumed. Placement (ops tooling in the customer SPA) is still a product decision, D-2. SET-06 keeps the suspend work. |
| 2 | **Observed.** Last active owner is protected on role change, deactivation and delete ([accounts/views.py:1537-1565](backend/accounts/views.py)); deactivation also revokes sessions and consumes invites. | Remove "last owner" from SET-09. Keep the other Users items. |
| 3 | **Observed.** `BankAccountViewSet` already has PATCH and DELETE; the UI just does not call them. Writes are allowed to `CanCreatePayments` **or** owner, wider than the owner-only route. The only uniqueness rule is one default per company; duplicates are not blocked. `account_number_masked` is free text with no validation. DELETE is a hard delete and `CustomerReceipt.bank_account` is `SET_NULL`, so deleting an account silently detaches its receipts. `opening_balance` and `opening_as_of` are already writable in the API. | SET-04 changes: add validation, replace hard delete with deactivate (refuse delete when referenced), align permission with the route, expose opening balance in the UI. |
| 3b | **Observed, new and important.** `BankAccountViewSet.get_queryset` calls `sync_company_bank_account` on every list ([payments/views.py:113](backend/payments/views.py), [payments/services.py:109](backend/payments/services.py)). That copies the Company bank name, masked number and IFSC onto the first (default) `BankAccount`, **overwriting edits** made in Bank Accounts, and it writes during a GET. | Must be fixed in SET-04 before any bank edit UI ships: make sync create-only (first time) or remove it after the one-time migration. Add a test that a PATCH survives a later list call. |
| 4 | **Observed.** `ENABLE_ARCH05_STATUTORY_FORMS` is an environment setting, default off ([config/settings.py:1251](backend/config/settings.py)), global rather than per company. | SET-03: the page cannot show "ON for this company"; show the global state, and decide D-3 as an environment or company-flag question. |
| 5 | **Observed.** No licence check exists in `purchases/` (only statutory event logging). | SET-03 purchase warning stays as a new, warning-only item. |
| 6 | **Observed.** Tally and Import endpoints use `CanImport`, matching the frontend `canImport`. Whether the backend also checks `ENABLE_TALLY` was **not confirmed**. | Add to the SET-01 parity test: backend flag check for Tally. |
| 7 | **Observed.** Enabling accounting is guarded (books stay off until back-fill ties). **Disabling has no check at all**: no period, journal or draft check, and no audit entry ([accounting/views.py:1363-1385](backend/accounting/views.py)). | SET-07 confirmed and raised: add pre-flight, refusal rules and an audit entry. |
| 8 | **Observed.** The SPA only posts `restore=sandbox`; `TenantRestoreView` also supports destroy-in-place and is `IsOwner`, described as "API-only for ops"; sandbox restore is rate-limited to once per 10 minutes ([accounts/export_views.py](backend/accounts/export_views.py)). | SET-08: confirm destroy-in-place cannot be reached by an owner without extra guards (**Verify** the code path); document as ops-only; D-1 unchanged. |
| 9 | **Observed.** The 100 is a client choice: the page asks for page 1 with size 100; the API allows up to 200 per page. | SET-09: async picker as planned. |
| 10 | **Observed.** `DocumentSeries` is a plain model with **no `created_at` or `updated_at`**, so the series screen cannot use the optimistic lock without a migration; no audit call on series configure. The gateway update **is** audited. The accounting toggle has no audit. `TimeStampedModel` gives `updated_at` to most other models. The full table for the remaining settings models was **not** built. | SET-11b: add `updated_at` to `DocumentSeries`; SET-21: add audit to series configure and the accounting toggle. Complete the table when SET-11b starts. |
| 11 | **Observed.** Company bank and UPI fields are read by: tax-invoice PDF (full account, IFSC, UPI, QR), thermal receipt (UPI), UPI QR and payment link ([payments/serializers.py:630](backend/payments/serializers.py), [payments/webhook_views.py:88](backend/payments/webhook_views.py)), dunning gating on `upi_id` ([payments/services.py:2731-2769](backend/payments/services.py)), a default-account bootstrap ([payments/services.py:1653-1660](backend/payments/services.py)), the setup checklist ([accounts/onboarding.py:14](backend/accounts/onboarding.py)), and the sync in 3b. | The SET-04 consumer list is now complete; the PDF parity test must cover all of these. |
| 12 | **Observed.** A number is `{prefix}-{next_number zero-padded to padding}` with default padding 5 ([document_numbers.py:274](backend/core/services/document_numbers.py)). When the company has a GSTIN, the default prefix is `{base}-{FY compact}-{last 4 of GSTIN}` ([document_numbers.py:129-140](backend/core/services/document_numbers.py)). **Result: the default sales invoice number is `INV-2627-F1Z5-00001`, 19 characters; every GSTIN-keyed document type comes out at 18 to 20.** Each `(company, doc_type, gstin, fy)` is its own counter, so invoices and credit notes do not share one. I found no length check anywhere (the document `number` column allows 32; the e-invoice payload is built in [sales/einvoice_payload.py:382](backend/sales/einvoice_payload.py), length validation not confirmed). | **Verify with the CA and the IRP schema: the 16-character limit (Rule 46(b)) comes from the review comment and my recollection, not from anything checked here.** If it holds, default numbers for every tenant with a GSTIN exceed it. D-8 becomes a blocking decision for SET-02 (options below). The "shared counter" check in SET-02 can be dropped. |
| 13 | **Observed.** The gateway adapter interface has no credential-check method (`create_payment_link`, `verify_webhook`, `parse_webhook`, `refund` only, [payments/gateway.py:217-237](backend/payments/gateway.py)). Whether each provider offers a safe read-only call was not checked. Credential save already ignores blank values and supports `clear_credentials` ([payments/views.py:2425-2433](backend/payments/views.py)); the UI does not expose clear. | SET-05: add a `verify_credentials` adapter method per provider (needs provider documentation), a "Remove keys" button, and keep the rule that only live activation is gated. |

### D-8 options (decision needed)

| Option | Example number | Length | Trade-off |
|---|---|---:|---|
| A. Keep a GSTIN code in the prefix, shorten the rest | `INV/A/2627/00001` style with a branch letter | about 16 | Needs a mapping from GSTIN to a short code; changes the default only (issued numbers untouched). |
| B. Drop GSTIN text, keep it in the series key | `INV-2627-00001` | 14 | Simple; two GSTINs would show the same visible number, so only valid if the CA accepts it. |
| C. Reduce padding and base | `I-2627-F1Z5-001` | 15 | Fits, but 3-digit padding rolls over at 999 documents. |
| D. Leave as is | `INV-2627-F1Z5-00001` | 19 | Only if the CA confirms the limit does not apply to this business. |

**Recommendation:** B for single-GSTIN companies (most tenants), A for multi-GSTIN, applied to new series only, with the length rule from SET-02 enforced on save. Needs CA confirmation first.

### Changes to apply to the plan from these results

- SET-04: add 3b (sync overwrite), the delete and `SET_NULL` problem, and the permission mismatch as first items.
- SET-07: raise to P1 (disable has no checks and no audit).
- SET-09: drop the last-owner item.
- SET-11b: `DocumentSeries.updated_at` migration.
- SET-02: remove the shared-counter check; make D-8 a prerequisite.
- SET-05: add `verify_credentials` and "Remove keys".
- SET-01: add the backend `ENABLE_TALLY` check to the parity test.


---

## 13. Build status (2026-10-19)

**Decision D-8 recorded (owner, 2026-10-19):** option B (drop GSTIN text from the visible number, keep GSTIN in the series key) for single-GSTIN companies and option A (short branch code) for multi-GSTIN companies, applied to **new series only**, **pending CA confirmation** of the 16-character rule. SET-02 stays blocked on that confirmation; nothing about numbering has been changed yet.

| Package | State | What was done |
|---|---|---|
| SET-00 | Done | Section 12. |
| SET-04 first item (sync overwrite) | **Built** | `sync_company_bank_account` gained `create_only`; the bank-accounts list now only bootstraps the first account and never rewrites an existing one ([payments/services.py](backend/payments/services.py), [payments/views.py](backend/payments/views.py)). Regression test `test_bank_account_edit_survives_later_list`. The rest of SET-04 (validation, deactivate instead of delete, permission alignment, full number plus UPI, UI) is **not built**. The Company page save still syncs Company bank fields onto the default account by design until SET-04 moves invoice printing to `BankAccount`. |
| SET-10 `SettingsPage` | **Built** | [components/settings/SettingsPage.tsx](web/src/components/settings/SettingsPage.tsx). Not yet used by any page. |
| SET-11 `useSettingsForm` + save bar | **Built** | [hooks/useSettingsForm.ts](web/src/hooks/useSettingsForm.ts), [components/settings/SettingsSaveBar.tsx](web/src/components/settings/SettingsSaveBar.tsx); 6 unit tests. Reuses the existing `UnsavedChangesGuard`. |
| SET-11b backend lock and idempotency | **Built, one endpoint** | [core/settings_writes.py](backend/core/settings_writes.py) (`SettingsWriteMixin`: 409 on stale `expected_updated_at` or `X-Expected-Updated-At`; idempotent create via the existing `wrap_idempotent`). Adopted by `BankAccountViewSet` only; `updated_at` added to its serializer; OpenAPI snapshot and TypeScript types regenerated. 6 tests. **Not yet adopted** by series, gateway, GST, company, units, items, users, licences, price lists. `DocumentSeries` still needs an `updated_at` column (migration). |
| SET-12 confirm dialog | **Already existed** | `ConfirmDialog` already has typed-confirmation and reason variants, and `confirmAction()` exists. Added a lint rule for Settings (warn level) instead of a new component. The 8 `window.confirm` calls in Settings pages remain and are converted in Phase 2 as each page is touched. |
| SET-13 `AsyncSection` | **Built** | [components/settings/AsyncSection.tsx](web/src/components/settings/AsyncSection.tsx); 3 tests. |
| SET-10 lint rules | **Built (warn)** | `eslint.config.js`: Settings folders warn on `window.confirm` and on raw JSX text. Becomes an error when the folder is clean (SET-24). |
| i18n | Added | `settingsShell` block in `en.ts` and `hi.ts`. The Hindi wording needs a native review (D-6). |
| SET-14 error catalogue | Not started | |
| SET-01 parity test | Not started | |

**Checks run:** `tsc -b` clean; ESLint clean on the new files; 9 new web tests and 6 new backend tests pass; the 24 existing payments tests pass. The full web and backend suites were **not** run, and nothing was checked in a browser because no page uses the new components yet.

**Known limits of what was built:** the idempotent create replays a stored response; I tested it with a repeated key but not under concurrent requests (Postgres run still open). The lock compares timestamps to the millisecond.


### SET-02 failure-path fix (2026-10-19)

Scope agreed with the owner: the failure-path fix only; the number-format change (D-8) waits for the CA.

| Item | State |
|---|---|
| Failed load no longer becomes editable placeholder data | **Built.** [SeriesSettingsPage.tsx](web/src/pages/settings/SeriesSettingsPage.tsx): a series that errors, or answers without a usable prefix and next number, is shown as an error row with Retry and no Configure button; `handleEdit` also refuses such a row. Two new tests (failed row, empty response). |
| Prefix refused instead of silently cut or accepted | **Built.** `DocumentNumberService.validate_prefix` ([document_numbers.py](backend/core/services/document_numbers.py)): letters, digits, `/` and `-`; at most 16; not starting or ending with `/` or `-`. The old `[:16]` truncation on save is gone. 20 backend tests ([test_series_prefix_validation.py](backend/tests/test_series_prefix_validation.py)); 49 tests across the related series suites pass. |
| Whole-number 16-character rule | **Not built** (D-8, pending CA). |
| Batch endpoint, GSTIN/FY on each row and selector, confirm after first issue, `DocumentSeries.updated_at` | **Not built** (outside the agreed scope). |

**Behaviour change to know about:** a company whose existing prefix contains a space, underscore or other character, or starts or ends with `-` or `/`, will now get an error when it saves that series with its prefix field (the page always sends the prefix). Nothing already issued is touched. I did not scan real data for such prefixes.

**Checks run:** `tsc -b` clean, ESLint on the two Series files reports no errors, and 3 Series page tests plus 49 backend tests pass. Not checked in a browser.


### SET-03 licence snapshot (2026-10-19)

Scope agreed with the owner: licence validity on the PDF, the snapshot, and the backfill.

| Item | State |
|---|---|
| Validity on the PDF | **Built.** The invoice PDF no longer prints a licence that had expired (or not yet started) on the invoice date. |
| Snapshot at completion | **Built.** New field `SalesInvoice.statutory_licences_snapshot` (migration `0079`, additive). `complete()` captures the licences valid on the invoice date ([sales/statutory_snapshot.py](backend/sales/statutory_snapshot.py), [sales/services.py](backend/sales/services.py)). `None` means never captured, `[]` means captured with none. |
| PDF reads the snapshot | **Built.** [gst_tax_invoice.py](backend/sales/pdf/gst_tax_invoice.py) prints the stored set; an invoice with no snapshot falls back to the licences valid on its own date. Editing, deactivating or letting a licence expire no longer changes a reprint of an issued invoice. |
| Backfill | **Built.** `python manage.py backfill_statutory_licence_snapshots [--company ID] [--batch-size N] [--dry-run]`. Touches only invoices whose snapshot is NULL, skips drafts, resumable and safe to re-run, writes with `update()` so `updated_at` is unchanged, and reports how many got licences versus none. For an old invoice it uses licences valid on the invoice date; a licence switched off since then counts only if it has an end date covering that date. |
| Append-only licences ("Renew / replace"), premises-state matching in the guard, enforcement-status banner, purchase warning | **Not built** (outside the agreed scope). |

**Run the backfill after deploying the migration** (dry run first). Until it has run for a company, its old invoices use the date-valid fallback, which can still shift if someone edits a licence's dates; the backfill is what freezes them.

**Limits.** The backfill cannot know what was actually printed on an old invoice, only what the licence records say was valid then. Licences that were deleted before this change leave no trace, so affected old invoices will correctly show none. The snapshot holds the licence type, number, premises state and dates; the PDF still prints only type and number. The API serializer is unchanged, so the OpenAPI snapshot did not change. I did not run the full backend suite.

**Checks run:** 9 new tests in [test_statutory_licence_snapshot.py](backend/tests/test_statutory_licence_snapshot.py) (including PDF text before and after a licence edit and deactivation, the dry run, and the second-run guard); 49 related existing tests in the PDF, sales, roadmap and async suites pass; `ruff` clean; `makemigrations --check` clean. The test database was rebuilt because of the migration.


### SET-03 second half (2026-10-19)

SET-03 is now complete apart from the purchase-side warning (needs a decision, below).

| Item | State |
|---|---|
| Locked licences | **Built.** New fields `locked_at` and `renewal_history` on `CompanyStatutoryLicence` (migration `accounts/0064`). A licence is locked the first time it is frozen onto an invoice snapshot (completion and the backfill both do it). Once locked: number, type, start date and premises state cannot be edited, the end date can only move later, and it cannot be deleted. Deactivating is still allowed. Unlocked licences stay freely editable and deletable. |
| Renew | **Built**, as an end-date extension. Each change is appended to `renewal_history` (when, previous date, new date, who). |
| Replace | **Built.** `POST /company/statutory-licences/{id}/replace/` creates the new licence (type and premises copied unless overridden), switches the old one off and keeps it, in one transaction, with audit entries. Refuses an unchanged number, an invalid number, and an inactive licence. |
| Premises-state matching | **Built.** The completion guard and the invoice snapshot only count licences with no state or the same state as the invoice's branch GSTIN. If the branch state or the licence's state cannot be recognised, nothing is filtered out. The block message names the state. |
| Enforcement status | **Built.** `GET /company/statutory-licences/status/` returns the invoice-check flag, number of medicine or food products, active, expired and expiring-in-30-days licences. The page shows these as banners (check on, check off, check off with regulated products present, expired, expiring), and still lists licences if the status call fails. |
| UI | Licences screen now uses the new `SettingsPage` shell; locked rows show an "On invoices" chip and a Renew button with the identity fields disabled; Replace button with its own dialog. English and Hindi text added (Hindi needs a native review, D-6). |

**Decision made on my own, please confirm:** the original plan said a locked licence should be replaced, never extended. Real renewals usually keep the same licence number with a later date, and the database does not allow two records with the same type and number, so I allowed the end date to move later (recorded in `renewal_history`) and kept Replace for a new number or a correction.

**Not built:** the warning-only check on purchase documents (needs the decision of whether a purchase of a regulated product should warn at all); POSP and Agency types and the address, city, pincode and valid-from fields in the UI.

**Limits.** Licences already snapshotted before this change have snapshot rows without an id, so they are not locked until a snapshot is rebuilt; nothing was deployed, so this only matters if you ran the first version against real data. The flag `ENABLE_ARCH05_STATUTORY_FORMS` is still an environment setting, so the banner shows the server-wide state. The state comparison uses GST state codes; a free-text premises state that is not a recognised state is treated as covering every branch.

**Checks run:** 20 tests in [test_statutory_licence_snapshot.py](backend/tests/test_statutory_licence_snapshot.py) (11 added for this half); 76 related existing backend tests; 6 new page tests in [StatutoryLicencesPage.test.tsx](web/src/pages/settings/StatutoryLicencesPage.test.tsx); `ruff`, `tsc -b` clean; ESLint 0 errors; `makemigrations --check` clean; OpenAPI snapshot and TypeScript types regenerated. Not checked in a browser, and the full suites were not run.


### Correction to SET-03 and SET-01 build (2026-10-19)

**SET-03 change, as decided by the owner: renewals are replace-only.** The earlier "extend the end date in place" path is removed (and so is `renewal_history`; the unreleased `accounts/0064` migration was regenerated). A licence that has been printed on an issued invoice is locked completely: type, number, start date, end date and state cannot change, it cannot be deleted, it can only be deactivated. A renewal or correction is a new record made with **Renew / replace**, which switches the old one off and keeps it. Because a renewal usually keeps the licence number, the database rule changed from "one record per number" to **one *active* record per number** (conditional unique constraint), and Renew / replace accepts the same number when the dates change. 22 backend tests and 7 page tests cover it.

### SET-01 route, menu and API parity (2026-10-19)

| Item | State |
|---|---|
| One shared list of Settings screens | **Built.** [navigation/settingsAccess.ts](web/src/navigation/settingsAccess.ts): id, label, path, who sees the sidebar link, who may open the route. `menu.ts` builds the Settings children from it and `App.tsx` registers every `settings/*` route through `settingsRoute(id, …)`, so link and route cannot be written differently by accident. |
| Packs drift | **Fixed.** The route was owner-only while the sidebar also needed `ENABLE_ARCHETYPE_PACKS`, and the API answers 404 without it; the route now follows the sidebar. |
| Accounting and AI settings drift | **Not a bug; kept and documented.** These routes are deliberately wider than their sidebar links: the "Enable accounting" and "Enable AI" links on the limited-access pages, and the golden end-to-end tests, open them while the feature is off, and they are the screens that turn the feature on. The earlier review (and my own first reading) called this drift; making the route follow the sidebar would have broken that flow. Each exception carries a written reason in the list. |
| Help & health | Route is wider than the sidebar only because the page checks the Help v2 flag itself; recorded as an exception. |
| Telegram | **Open decision D-10.** The sidebar link is owner-only (and needs `ENABLE_TELEGRAM`), but the route opens for anyone who can open Settings. Linking Telegram is per person and the API has no role check, only the flag. Behaviour left unchanged; recorded as an exception. Choose: (a) owner-only everywhere, (b) anyone with a login may link their own Telegram and the sidebar link should show for them too. |
| Front-end parity tests | **Built** ([settingsAccess.test.ts](web/src/navigation/settingsAccess.test.ts), 13 tests): the sidebar and the Settings list match in id, path and order; for 9 personas × 5 flag sets × Help v2 on/off, a link the router would refuse never appears, and the route is wider than the sidebar only where an exception is written down; `App.tsx` contains no hand-written `settings/*` route and registers each screen once. A deliberate change to the packs rule was caught by these tests. |
| API side | **Built** ([test_settings_api_access.py](backend/tests/test_settings_api_access.py), 26 tests): a plain staff user is refused the writes on the 12 owner-only screens' endpoints and the reads on 6 of them; the company profile read stays open to staff and is listed as such; the owner can read all of them. |

**What the API test does not cover:** Import, Tally, Backup/Export for staff granted those flags, Bank Accounts for staff with the payments flag (the API lets them write, which is wider than the owner-only screen; noted in SET-04), Units/Price Lists reads, and whether the backend also checks `ENABLE_TALLY`. Only the staff-without-flags and owner cases were checked.

**Checks run:** `tsc -b` clean; ESLint 0 errors (50 warnings, all the new Settings-folder rules on existing code); 72 web tests across navigation and Settings pass; 26 new backend tests pass; `ruff` clean. The e2e specs were not run.


### D-10 applied (2026-10-19)

Telegram settings are owner-only: the route now needs the owner and the `ENABLE_TELEGRAM` flag, the same as the sidebar link, and the shared list no longer has a Telegram exception (exceptions are now only accounting settings, AI settings and Help & health). Test updated; 57 navigation tests pass, `tsc -b` and ESLint clean. **Not changed:** the Telegram API endpoints have no role check, so a non-owner can still link their own account by calling the API directly; and a staff member who had already linked Telegram can no longer open the page to unlink (the API still allows it).


### SET-04 bank accounts (2026-10-19)

Built, following the SET-00 findings (the bill's full account number and UPI ID must keep printing, and the list used to overwrite edits).

**Backend**

| Item | State |
|---|---|
| Full number, UPI, invoice account | **Built.** `BankAccount` gained `account_number_sealed` (sealed with the existing bank-account sealing), `account_number_hash` (keyed hash for duplicate detection), `upi_id`, and `print_on_invoices` (migration `payments/0045`; one invoice account and one default per company, enforced by the database). The list API never returns the full number; `account_number_masked` is now derived from it and read-only, so a typed-in "masked" value is ignored. |
| Validation | **Built.** IFSC format (upper-cased), account number 9 to 18 digits, UPI ID format, name required, duplicate full number refused within a company (the same last four digits are allowed). |
| Owner-only fields | **Built.** Changing the account number, UPI ID or invoice account needs the owner; a staff member with payments access can still add or edit a plain account (name, type, IFSC, balance). |
| Show full number | **Built.** `GET /payments/bank-accounts/{id}/reveal-number/`, owner only, each look written to the audit trail (`bank_account.reveal_number`). Decision D-9 as recommended: on demand. |
| Deactivate, not delete | **Built.** `DELETE` switches the account off and keeps it (repeatable). The default account, and the invoice account, cannot be switched off. Pickers list live accounts only; the Bank Accounts screen asks for all with `?include_inactive=1`. |
| Default and invoice account switching | **Built.** Switching one on switches the other off in one transaction. An invoice account needs a full number, must be active and cannot be a cash box. |
| Opening balance | **Built.** Locked once money has moved through the account (receipts, payments and similar); the error tells the owner to record an adjustment. |
| What bills print | **Built.** One function, `invoice_bank_details(company)`, returns the chosen invoice account's name, full number, IFSC and UPI ID, or the company's own fields until one is chosen. The A4 invoice PDF, thermal receipt, UPI QR and payment link, dunning check and the onboarding checklist all read it. A test proves the invoice PDF text is identical before and after the details move to a bank account. |
| Company sync | **Built.** Saving the Company form now touches the bank account only when its bank or UPI fields actually changed, and then copies name, full number, IFSC and UPI onto the invoice account (or the default one, which becomes the invoice account). The list only creates the first account, never rewrites one. |
| Backfill | **Built.** `python manage.py backfill_bank_account_details [--company ID] [--dry-run]` copies each company's saved bank details onto a bank account marked for invoices; skips companies that already chose one. **Run once after deploying, before owners start editing accounts** (it overwrites the name, IFSC and UPI ID of the account it picks). Until it runs, bills use the company fields as before. |

**Frontend**

- New Bank Accounts screen ([BankAccountsPage.tsx](web/src/pages/settings/BankAccountsPage.tsx)) on the Settings shell: list with masked number, "full number saved" hint, IFSC, UPI, opening balance and chips (Default, On invoices, Switched off); Add and Edit dialog with account number (blank keeps the saved one), IFSC, UPI, opening balance (disabled with the reason once locked), default and print-on-invoices switches, owner-only "Show full number"; Make default, Use on invoices, Switch off (confirmation) and Switch on; server reasons are shown.
- The Company screen's bank block is replaced by a read-only summary of the invoice account with a link to Bank Accounts ([InvoiceBankSummary.tsx](web/src/pages/settings/InvoiceBankSummary.tsx)). Its other fields and the reminder settings are unchanged.
- The old Bank Accounts page in `BankingPhasePages.tsx` is removed.
- English and Hindi added (Hindi needs a native review, D-6).

**Checks run:** 25 new backend tests ([test_bank_account_settings.py](backend/tests/test_bank_account_settings.py)) and about 590 related existing backend tests (payments, receipts, dunning, onboarding, PDFs, settings) pass; `ruff` and `makemigrations --check` clean; OpenAPI snapshot and types regenerated; 10 new page tests; 210 web tests across phase, settings, accounting, navigation and i18n pass; `tsc -b` clean; ESLint 0 errors. The full backend and web suites, Postgres and the browser were not run.

**Known gaps and risks**

- **PDF caching not checked.** I did not verify whether already-generated invoice PDFs are cached; changing the invoice account may not alter a PDF generated earlier.
- Bank Accounts writes are still open to staff with payments access for the non-sensitive fields; the screen itself stays owner-only (SET-01).
- The Company API still carries the old bank fields (kept as the fallback and for old clients); the screen no longer edits them. They go stale once an invoice account is chosen.
- Bank-account data in `settings_test` is SQLite; the unique constraints and sealing were not exercised on Postgres.
- Existing masked-only accounts keep their old masked text until the full number is entered.
- Counterparty bank fields on customers and suppliers are untouched.


### SET-05 payment gateway and Money-In rules (2026-10-19)

**Two things in the plan did not fit the code, and I changed the design instead of building them as written.**

1. **"Block going live until keys are verified" is not built.** `test_mode` on the company is a development and CI shortcut (it maps empty keys to the sandbox), and the server refuses to turn it on outside development, test or local. In production it is always off, so there is no "test to live" switch to gate. Whether Razorpay keys are test or live comes from the key itself (`rzp_test_` or `rzp_live_`). Instead the page now shows the key mode, shows whether the provider has accepted the keys, warns when a server that is not in test mode holds test keys, and shows the "test mode" switch only where the server allows it. Nothing blocks saving keys. If you still want a hard gate, the natural place is payment-link creation (refuse a link when the keys were never accepted); that was not asked for and would change the money path, so I left it.
2. **Provider checks.** Razorpay: `GET /v1/payments?count=1` with Basic auth, which Razorpay documents for its APIs (401 means keys not accepted). Cashfree: a Get Order lookup of an id that cannot exist, with the client id and secret headers; treating 404 as "keys accepted" and 401 as "refused" is my assumption, not something Cashfree's documentation states, so it is marked as such in the code. PayU: no documented call that separates a wrong key from an unknown transaction, so PayU keys are reported as "cannot be checked automatically". None of this was run against a real provider.

**Backend**

| Item | State |
|---|---|
| Money-In rules endpoint | **Built.** `GET/PATCH /payments/money-in-rules/` (owner only, audited with the fields changed). The gateway endpoint still accepts and returns the same rule fields for older clients (marked deprecated), through one shared function, so there is no second set of rules. |
| Check keys | **Built.** `POST /payments/gateway-settings/verify/` (owner only, one call per 5 seconds per company, audited). A provider acceptance is remembered, with the provider name, inside the sealed credentials until the keys change; a refusal clears an older mark; an unanswered check changes nothing. Each adapter got `verify_credentials()`; checks run outside the money-path circuit breaker. |
| Key hint, mode, status | **Built.** The gateway GET returns last four characters of the key id, test, live or unknown, whether verified, and when. Never the secret. |
| Remove keys | **Built (API existed).** `clear_credentials` now clears the verified mark and writes an audit entry that says "Payment keys removed". |
| Blank fields | Unchanged and tested: a blank key field never wipes a saved key. |

**Frontend**

- **Payment Gateway** ([PaymentGatewayPage.tsx](web/src/pages/settings/PaymentGatewayPage.tsx)): provider, only the key fields that provider uses (one table), "Keys saved, ending ####, test/live keys", verified or not checked, Check keys, Remove keys (confirmation), copyable webhook addresses, and no Money-In rules. Switching provider clears typed keys; saving sends only typed fields.
- **Money In rules** ([MoneyInRulesPage.tsx](web/src/pages/settings/MoneyInRulesPage.tsx)): new screen at `/settings/money-in`, in the Settings list and menu, using the new save bar (unsaved-change guard, "saved" status, server errors shown, changes kept on refusal). First real user of `useSettingsForm`.
- The old combined page is removed from `BankingPhasePages.tsx`. English and Hindi added (Hindi needs a native review, D-6).

**Checks run:** 20 new backend tests ([test_gateway_settings.py](backend/tests/test_gateway_settings.py)) and 214 related existing ones pass (money-in, payments, dunning, webhooks, public links, bank accounts, settings access); the API access matrix now covers the verify and rules endpoints; 16 new page tests; 195 web tests across navigation, settings, phase and i18n; `tsc -b` clean; ESLint 0 errors; `ruff` clean; OpenAPI snapshot and types regenerated. The full suites, the browser and the end-to-end specs (one path added to the settings spec) were not run.

**Not done:** dunning and auto credit hold stay on the Company page (SET-17); "last webhook received" time; per-provider extra fields such as the Cashfree or PayU base address; and a real call to any provider.


### Payment-link key gate and SET-07 accounting (2026-10-19)

**Payment-link gate (SET-05 follow-up), built with one deliberate softening.**
`PaymentService.create_payment_link` now first calls `assert_gateway_keys_accepted`. Keys the provider has accepted pass at once. Keys never checked (every company that saved keys before this change, or just entered) are **checked on first use, once, and remembered**; only an explicit refusal by the provider blocks the link ("The Razorpay account did not accept the saved payment keys…"). A check that could not finish (provider down, timeout), a provider with no automatic check (PayU) and the sandbox never block. I did it this way rather than "refuse until verified" because every existing tenant already has keys with no verified mark, and a hard rule would have stopped all of them creating payment links the moment this shipped. The check runs before the link's database transaction, so the provider call never holds locks. Applies to all three callers (staff create, public invoice pay, customer portal). 6 tests; one existing test that mocked the provider adapter needed the gate to honour its mock, which it now does. Cost: the first link after saving new keys makes one extra provider call (up to 10 seconds).

**SET-07 accounting on and off**

| Item | State |
|---|---|
| Pre-flight | **Built.** `GET /accounting/settings/disable-preflight/` (owner only): posted entries with first and last date, closed and soft-closed periods, latest closed period end, back-fill running, blockers, and whether switching off is allowed. |
| Refusals | **Built, server-side.** Switching off is refused while any accounting period is **closed** (bills dated in it could never be posted later; the back-fill refuses closed periods too) and while a **back-fill is running**. Soft-closed periods do not block. |
| Reason and acknowledgement | **Built.** Switching off needs a written reason; if the books hold posted entries it also needs an explicit acknowledgement that bills completed while off will not be posted until a back-fill. |
| Audit | **Built.** `accounting.enable` and `accounting.disable` events (reason in the description, counts and last entry date in the metadata). Repeating a change already in place records nothing. |
| Screen | **Built.** [Accounting settings](web/src/pages/phase/AccountingExtraPages.tsx) shows "Books are on/off" and only the button that applies; "Switch off…" opens a dialog ([DisableAccountingDialog.tsx](web/src/components/accounting/DisableAccountingDialog.tsx)) with the consequences and counts, error banners for the two blockers (no way to proceed), a required reason, the acknowledgement checkbox, and the server's reason if it still refuses. If the pre-flight cannot load, the dialog shows Retry and cannot be confirmed. English and Hindi added (Hindi needs a native review, D-6). |

**Checks run:** 11 new backend tests ([test_accounting_disable.py](backend/tests/test_accounting_disable.py)), 6 new gate tests, 8 new page tests, and about 90 related existing backend tests (settings, accounting, payments) pass; 174 web tests across phase, settings, navigation and accounting components; `tsc -b` clean; ESLint 0 errors; `ruff` clean; OpenAPI snapshot and types regenerated. I checked that the golden end-to-end helpers that click "Enable accounting" still work (they use fresh companies with the books off) but did not run them.

**Not done or open**

- **Re-enabling** is unchanged (it keeps its existing "books must tie" guard); there is no pre-flight for turning on beyond that.
- **A company with a closed period can now never switch accounting off from the screen.** That is the intended rule, but if an owner needs it, someone has to reopen the period first; the dialog says so.
- Documents completed while the books are off are not listed anywhere; the dialog only warns. A count of them would need a new query.
- The gate and the key check have only been run against mocks, never a real provider.


### SET-06 Billing (2026-10-19)

**What changed**

| Item | State |
|---|---|
| Suspend is guarded (server) | **Built.** `POST /billing/subscription/ {action: suspend}` now needs: a reason; the **company name typed out** (case and spacing ignored); the owner's **password**, and a **two-step code** when that owner has one set up; and it is refused if the workspace is **already suspended**. Wrong password or code is counted: 5 failures in 15 minutes lock the action (even a right password is refused for that time); a right one clears the count. An owner with no usable password is told to set one. Every suspension writes a `billing.suspend` audit entry with the reason. New helper [billing/reauth.py](backend/billing/reauth.py). |
| Danger zone (screen) | **Built.** On the Billing screen, suspend is no longer next to the plan. It is in a collapsed "Danger zone" that is hidden once the workspace is suspended. "Suspend workspace…" opens a dialog ([SuspendWorkspaceDialog.tsx](web/src/components/billing/SuspendWorkspaceDialog.tsx)) with an accurate consequence line (read from the code: while a paid period is still running you can keep working until it ends, then the workspace is read-only; with no paid period, e.g. a trial, it is read-only straight away; renewal charges stop), the reason, the typed company name, the password and an optional two-step code. Server errors appear in the dialog. The browser `window.confirm` is gone. |
| Plan page | **Built.** Billing now uses the Settings shell: current plan and notices, available plans and checkout, an error with Retry if the plan cannot load. |
| Operator tooling | **Moved.** The parked billing events list and Replay button are removed from the customer screen. Replay is now an action on the Django admin's Dead letter events page ("Replay selected parked events", pending only, superuser only). Decision D-2 as recommended. |
| Vendor tenants | **Kept, relocated.** The list of a vendor company's own tenants (redacted snapshots) is a feature for vendor companies, not operator tooling, so it stays, as its own "Your tenants" section shown only when there are rows. |

**Checks run:** 11 new backend tests ([test_billing_suspend.py](backend/tests/test_billing_suspend.py)) including password, lockout, two-step code (with the second-factor check stubbed), already-suspended, staff refused, admin action; the existing suspend test was updated to send the new fields; 90 related backend tests pass; the staff-refusal matrix covers the endpoint; 12 page tests rewritten and added; 171 web tests in settings, navigation and phase; `tsc -b`, `ruff` clean; ESLint 0 errors. OpenAPI snapshot and types regenerated (no schema change). Not browser-checked.

**Not done or to know**

- The parked-events and vendor-tenant **API endpoints still exist** (owner only, company-scoped); nothing in the app calls them any more except vendor tenants. Remove them if you want the API surface gone too.
- The two-step path was tested with the second-factor check stubbed, not with a real authenticator code.
- Any other client that calls the suspend endpoint without a password and the company name (scripts, support tools) will now be refused.
- The consequence text describes the code's behaviour (read-only after the paid period); I did not check what each module does while read-only, and did not claim anything about data retention.
- Un-suspending is not changed; the dialog says a plan can be chosen again later, which I did not re-test end to end.


### SET-08 Backup, restore and exports (2026-10-19)

**What I found while reading the code, and what the page now says**

- The encrypted backup can only be opened by the Bizboard server (it is locked with a key the server keeps). The old page said the owner should "keep that key with your ops backups", which an owner does not hold and cannot read. The page now says in plain words that the file is for restoring into Bizboard, not for reading or moving elsewhere, and points to the spreadsheet exports for that.
- Large attached files (over 256 KB) are listed in the backup but their contents are not inside it. The page now says so, with the real counts from the last backup.
- **Restoring over live data was reachable by any owner through the API** (the screen never offered it). It needed a real backup of the same company, the company name typed, and an "unbacked rows" confirmation, but no switch, no password and no audit before the destructive step.

**Built**

| Item | State |
|---|---|
| Last backup | **Built.** `GET /company/export/last/` (owner only) reads the audit trail: when, by whom, size, and a summary counted from the export itself (sections, records, customers, suppliers, items, sales and purchase invoices, receipts, journals, files inside, large files listed only, files that could not be read). Only backups taken after this change carry the summary; an older one shows when, who and size. |
| Live restore is not self-service | **Built.** New setting `TENANT_RESTORE_DESTROY_ENABLED`, **off by default**: a restore over live data is refused with "done by support, not from this screen", and nothing changes. Support can switch it on for a case; the typed-name and unbacked-rows checks still apply, and a `tenant.restore_destroy_started` audit entry is now written before the destructive step. The test settings turn it on so the existing restore tests keep exercising that path. Sandbox restore is unchanged. Decision D-1 as recommended. |
| Page | **Built.** [BackupExportPage.tsx](web/src/pages/settings/BackupExportPage.tsx) on the Settings shell: plain explanation, last backup and its contents (or a warning that none has been taken), download with progress text and retry, "Check a backup" (restores a separate sandbox copy; says it expires, does not change the live company, how many copies are allowed, and that restoring over live data is a support matter), and after a check says the copy's name, its expiry date and where to open it. Staff who may export see only the spreadsheet exports. English and Hindi added (Hindi needs a native review, D-6). |
| More exports | **Built.** Spreadsheet exports now include **items and prices** (item master) and **price lists** (one row per slab); **suppliers** is now offered. The purchase price column is left out for anyone who may not see margins. Soft-deleted items and other companies' data are excluded. |
| A bug found and fixed | The suppliers export, which existed but had no button, **failed with a server error** (it read columns suppliers do not have). Fixed, with a test. |
| Removed | The "background workers look unhealthy, exports may stall" warning. Backups and exports are built inside the request, not by workers, so the warning did not apply to them. |

**Not built**

- **Scheduled nightly backups, retention and failure notices**: not asked for in this step and a bigger piece (scheduler, storage, pruning, notifications).
- **Ledgers, day book and GST exports**: those reports already have their own export on their own screens; I did not add a second route to them. A per-customer or per-supplier outstanding export needs new logic and was left out.
- **Progress bars and background building** for very large companies: the backup and CSV exports are still built in one request and can time out on a very large tenant; the page shows "Preparing…" and a retry, nothing more.
- **A way for owners to see or manage their sandbox copies** from this screen.

**Checks run:** 17 new backend tests ([test_backup_page_honesty.py](backend/tests/test_backup_page_honesty.py)) and about 250 related existing backend tests (restore drills, tenant export, exports, imports, tenant isolation, settings access) pass; 13 new page tests; web settings, navigation and i18n tests pass; `tsc -b`, `ruff` clean; ESLint 0 errors; OpenAPI snapshot and types regenerated. No real restore against production data, no browser check, and the full suites were not run.


### SET-09 and SET-09b (2026-10-19)

Several plan assumptions did not match the code; each is noted where it changed what I built.

**Units**

- The unit code was already a pick-list on the screen (the plan said free text). The **server** still accepted any typed code it could not match; it now refuses a code that is not a real GSTN unit code.
- Units had no "inactive" state, but the API let anyone with owner rights **delete a unit that items use, silently blanking those items' unit**. Delete is now refused with the item count; the screen shows "Items using it" per unit (counted by a new uncached `usage` endpoint) and offers Delete only for unused units, with a confirmation.

**Price lists**

- **Real bug fixed:** "Active" did nothing for invoicing. A switched-off or deleted list **still priced every customer assigned to it** (only the POS list filtered it). Invoice and POS pricing now ignore a list that is off or deleted. **This changes prices for any customer still on a list that was switched off**: they now pay the normal selling price.
- New screen ([PriceListsPage.tsx](web/src/pages/settings/PriceListsPage.tsx)): slab and customer counts per list; switching off a list customers use names them and needs confirmation (server-enforced with `confirm_customers`; deleting a list in use likewise); item picker is a **search**, not the first 100 items; slabs show the item name; every slab problem is listed at once. The old editor **dropped each slab's discount percentage on every save** (it did not send it); the new one keeps it and lets you edit it.

**Item custom fields**

- Removal already kept the values (soft-remove with a "Removed fields" restore list). Added: "Used on N items" next to each saved field, and the same count in the remove dialog, with a warning when the count cannot be loaded.

**Users**

- **Real bug fixed:** nothing ever recorded when someone signed in (Django's `last_login` was never set), so "last signed in" would have been empty for everyone, and the vendor tenant snapshot that reads it too. It is now stamped on password and two-step sign-in.
- Users list now shows last sign-in (or "Never") and invite state: **pending** (with expiry), **expired**, **deactivated**, accepted. Pending or expired invites get **Resend** (new link, old links stop; shown with Copy) and **Cancel invite** (confirmation); the misleading "Reactivate" button is hidden for an unaccepted invite. Last-owner protection was already there (SET-00).
- All four browser `confirm` popups on the screen now use the in-app confirmation. Limitation: an account deactivated **before** sign-ins were recorded shows as "Invite expired" until that person next signs in.

**Import and Tally**

- Import page: new **Past imports** list (who, file, when, rows, result, problems download, Undo). The server now reports who uploaded and whether an import can be undone. There is **no time window**: product and opening-stock imports can be undone while their stock is unused, bills while still a draft; **customer and supplier imports cannot be undone** and say so.
- Tally: new `GET /integrations/tally/runs/` and a **Past Tally imports** list with a problems download. When Tally is not switched on, the page now opens and says so (the sidebar link stays hidden) instead of a bare "forbidden"; recorded as a documented exception in the shared access list.

**SET-09b: Business pack and "Bill scan & lateness"**

- **A business pack only turns feature flags on**; it never touches units, items, series or GST defaults as the plan assumed. Built: a **preview** (will be switched on / already on / left as you set them / not on your plan) shown before applying, "Apply" disabled until the pack has been previewed for the current answers, an audit entry (`pack.apply`) naming what was enabled. It was already safe to apply twice and never turns anything off; tests now prove it.
- **Real defect found on the AI screen:** the "Enable bill scan" switch and the monthly token limit **did nothing**. The server deliberately ignores both from an owner (they are controlled per company by Bizboard), yet the screen said "saved". They are now shown as status only, with plain wording about who controls them, and are no longer sent. The Insights "turn it on in settings" prompt used to point owners at that switch; its wording is corrected. **Decision for you:** whether owners should be able to switch AI on themselves, or whether it stays a support action (it costs money per bill read).
- Opening cash (used by the cash-flow forecast and as the first cash account's starting amount): the server and screen now require **both a balance and its date or neither** (one without the other was accepted and silently ignored). Added help text on what it feeds.

**Checks run:** about 60 new backend tests across eight new test files and 192 related backend tests pass; about 90 new page and component tests; 315 web tests across settings, navigation, i18n, phase and hooks pass; `tsc -b`, `ruff` clean; ESLint 0 errors; OpenAPI snapshot and types regenerated; no new migrations. Not browser-checked; the full suites were not run.

**Not done**

- Hindi review for all new text (D-6).
- Import history is a recent-20 list only (no filters or paging).
- Tally has no "undo" (the code has none).
- Item custom field usage counts scan every item that has custom values on each request.
- The "Business pack" screen still has raw navigation wording unrelated to this change.


### SET-15 and SET-18 (2026-10-19)

**Built**

- **Groups (SET-15):** every Settings screen in the shared list ([settingsAccess.ts](web/src/navigation/settingsAccess.ts)) now has a group, and the list is ordered by group: Business profile, Payments & pricing, Documents, People & data, Plan & automation. The sidebar shows the group name as a plain label above each group (still one level, no new nesting). Old URLs are unchanged, so no redirects were needed. A test fails if a screen has no group or the groups are not kept together.
- **Hub (SET-18):** new `/settings` page ([SettingsHubPage.tsx](web/src/pages/settings/SettingsHubPage.tsx)) with an "Overview" link at the top of the Settings menu. It shows the groups as cards (only the screens that person may open), one line each on what the screen is for.
- **Health checklist:** owner-only `GET /api/v1/company/settings-health/` ([settings_health.py](backend/accounts/settings_health.py)), read-only, computed on the server: GST number set, default active bank account, licences (warns on expired or expiring in 30 days), payment keys accepted by the provider, invites that ran out. Each row links to its screen. If the checklist cannot load it shows an error with Retry and the groups still show. Non-owners do not see it.

**Not built**

- "Series reviewed" and "users reviewed" checklist items: there is no record of a review, so they would be invented. Replaced by "invites that ran out".
- Dunning and credit hold have not moved to Money-In rules (SET-17), the GST page is not split (SET-16), and post-save "next step" links and Back behaviour (SET-19) are not done.
- Hindi for the new text needs review (D-6). Not checked in a browser.

**Checks:** 5 new backend tests plus 37 settings API tests pass; 109 web tests across navigation, i18n and the hub pass; `tsc -b`, `ruff` clean; ESLint 0 errors; OpenAPI snapshot and types regenerated.


### SET-16 and SET-17 (2026-10-19)

**Built**

- **GST page in sections (SET-16):** [GstSettingsPage.tsx](web/src/pages/settings/GstSettingsPage.tsx) is now four sections, each with its **own Save** that sends only its own fields: Registration (GSTIN, PAN, Udyam, state, registration type, verify buttons), Stock and tax rules, e-Invoice and e-way bill, and Portal (GSP) keys. Branch GSTINs sit directly under Registration. Before, one Save at the bottom sent all of it, so a change to the e-invoice switch also sent a half-edited GSTIN.
  - A changed GSTIN still needs the "I have checked it" tick (shown only when the GSTIN has changed; before, it was always shown at the bottom and tied to the portal keys).
  - Changing registration type or the negative-stock policy still asks first, now with the in-app confirmation instead of the browser popup.
  - Verify buttons are enabled only for the saved value (before, they could verify a number you had typed but not saved).
  - After saving portal keys the secret box is emptied. A **new "Remove the saved portal keys" option** (with confirmation) uses the existing clear flag, which had no button.
  - Fixed on the way: the old page sent every field, including the e-invoice switches, on every save.
- **Company page trimmed (SET-17):** [CompanySettingsPage.tsx](web/src/pages/settings/CompanySettingsPage.tsx) now has only name, legal name, address, city, state, pincode, phone, email, the GSTIN chip, and the invoice-bank pointer. Its save no longer resends the older bank and UPI text fields. Reminders and credit hold are gone from it.
- **Reminders and credit hold moved (SET-17):** now a second section on Money-In rules with its own Save, saved through the same `payments/money-in-rules/` endpoint. The server checks them: reminder days whole numbers 1 to 365, 1 to 10 reminders, quiet hours 0 to 23, each refused with a reason. Turning reminders on still asks first and shows the schedule. The company API still accepts these fields, so older clients keep working.

**Not built**

- **Logo:** the plan listed the logo on the Company page, but the page never had one (the logo is not in the company API either), so nothing was moved. Needs a decision whether to build upload.
- The "I have confirmed" tick is a local tick, not recorded on the server.
- Hindi for the new text needs review (D-6). Not browser-checked.

**Checks:** 5 new backend tests (collections) plus the settings access, health and Money-In suites; 21 new web tests (GST sections 8, Company 5, Money-In reminders 4 added); `tsc -b`, `ruff`, ESLint 0 errors; OpenAPI snapshot and types regenerated.


### SET-19 (2026-10-19)

**Built** (web only; no backend change)

- **Back on every Settings screen:** [SettingsContinuity.tsx](web/src/components/settings/SettingsContinuity.tsx) is mounted once in the app shell and shows "← All settings" above any `/settings/<screen>` page. It is in the shell rather than in each page because 11 of the 21 Settings screens do not use the shared page frame. Leaving with unsaved changes is still stopped by each screen's own leave guard, so Back does not lose edits silently.
- **Next step after a save:** after a successful write on a Settings screen, a banner says "Saved. Next in set-up: X" with a button to go there, and a Close button. The order is Company, GST, Licences, Bank Accounts, Payment Gateway, Money-In rules, Series, Templates, Units, Items, Price Lists, Users (`SETUP_ORDER` in [settingsAccess.ts](web/src/navigation/settingsAccess.ts)). Screens the person cannot open are skipped; screens outside the order (Backup, Billing, Tally and so on) just say "Saved" with a link to the overview.
- **How a save is detected:** the API client announces every successful write made while the page is under `/settings/` ([settingsSaveSignal.ts](web/src/utils/settingsSaveSignal.ts)), except calls whose URL says preview, verify, reveal, check, usage, search, validate or propose. This is deliberately screen-independent but approximate: it also fires for a write that is not a form save (an export, an invite resend, a delete), and a write whose URL contains one of those words is not announced.
- **Cancel:** each screen already has Discard (shared save bar) or its own Cancel in dialogs; nothing new was added, and screens without a save bar keep their own buttons.
- **Deep links:** `#bank-section` was already replaced by the Bank Accounts route in SET-04 (nothing links to it any more).

**Not built**

- Per-screen Cancel for the 11 screens that do not use the shared frame or save bar (Users, Series, Units and similar save row by row; they have no whole-page edit to cancel).
- The banner does not appear for a save made in a dialog opened from another screen.
- Hindi for the new text needs review (D-6). Not browser-checked.

**Checks:** 8 new web tests (frame 5, set-up order 2, plus sidebar); `tsc -b`, ESLint 0 errors; 248 web tests across settings, navigation, i18n pass.


### Close-out of every open item (2026-10-19)

**Built in this round**

- **SET-02:** one `GET/PATCH /company/number-series/` for all 11 series, with GSTIN and financial-year choice, all-or-nothing save, per-row lock (`DocumentSeries.updated_at`, not bumped by allocating a number), and a non-blocking warning when an invoice number is over 16 characters. The screen is one table with one Save and a dry-run of the next five numbers.
- **SET-11b:** the lock now covers company, Money-In rules, gateway, units, price lists and users, and the screens send it. Creates (bank account, unit, price list, user invite) carry an `Idempotency-Key`, and a second click while one is running is ignored. Found and fixed: the UI never sent keys, so a double-click on Bank accounts created two POSTs.
- **GST page (found in this round):** e-invoice, e-way switch, turnover and portal keys are **read-only for owners in the company API** (Bizboard controls them), so the old switches said "saved" and did nothing. They are status only now; the e-way threshold is the one editable value. "Remove portal keys" was dropped for the same reason.
- **Payment gateway (found):** there was **no field for the webhook secret**, and Razorpay and Cashfree reject any notification without one. Added, with "saved/missing" status, last notification time, an allow-list for the provider address (live or test only), and the key check is kept when only the webhook secret changes.
- **Others closed:** logo upload/replace/remove; "GST details confirmed" now recorded on the server and shown in the checklist; weekly automatic backup (opt-in, last 4 kept, failures audited and alerted, one failure never stops other companies); import history filter and paging; custom-field usage counted in the database; invite state tells "deactivated" from "expired" by invite history.
- **SET-14:** 21 stable error codes (`core/settings_codes.py`) plus a status-based fallback, each with a cause and a fix in English and Hindi; every Settings error text now ends with what to do. Tests fail if a code is listed but not raised or has no text.
- **SET-20:** impact registry (screen and field level) in the web and a backend twin; "Used by" chips come from it, shown by the shared frame on every screen; tests keep both in step and check every field exists on its model.
- **SET-21:** "Recent changes" drawer on 13 screens (who, when, old to new, secrets never shown). Audit entries with old and new values now written for company, Money-In rules, gateway, series, units, price lists, bank accounts, users and licences.
- **SET-22:** dry-run previews before saving series, GST registration, stock and tax rules, and the cash limit (next five numbers, open drafts touched, past days that would have been refused). Accounting off keeps its own preflight from SET-07.
- **SET-23:** daily job raises in-app alerts for licence expiry (30, 7, 0 days), failed backup, a quiet gateway and plan limits, once each, and the checklist shows them.
- **SET-24:** raw text cleared; ESLint rule on the Settings folders is now an **error** and also covers label, placeholder, helper text, title, alt and aria-label.
- **SET-25:** all 18 screens captured in English and Hindi and compared with stored images (`E2E_VISUAL=1`; images are for Chrome on Windows). **The app has no dark theme, so the plan's dark variant does not apply.**
- **SET-26:** axe (WCAG 2 A/AA) on 18 screens, a 360 px no-sideways-scroll check on each, keyboard save, and focus return after a dialog: all pass on the live backend.
- **SET-27:** live-backend specs for double-click, refresh mid-save, offline retry, slow API, signed-out save and a concurrent edit (Company, Series, Bank, Gateway, Users, Import): all pass. Signed-out save now says "Your session has ended" instead of "Authentication credentials were not provided".

**Not done, and why**

- **Tally undo:** the importer keeps no list of what it created, so a truthful undo cannot be built without changing the importer. Use a sandbox check instead.
- **Per-call "typed accessor" for impact (SET-20 in the plan):** replaced by the registry and contract tests above; an accessor around every settings read would touch hundreds of call sites for little gain.
- **"Series reviewed" and "users reviewed" checklist items:** nothing records a review, so they would be invented.
- **Older per-document `number-series` endpoints** are still unaudited and unlocked; the screen no longer uses them.
- **Needs people, not code:** CA sign-off (16-character invoice number, D-8 format, advance-GST, 269ST, licence printing), native Hindi review (D-6) of all new text, a real-phone check, a Postgres concurrency run, and a real call to a payment provider with live keys.
- **Nothing is committed.**

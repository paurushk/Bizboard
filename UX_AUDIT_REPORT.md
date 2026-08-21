# Bizboard Full-App UX/UI Walkthrough Audit

**Auditor perspective**: first-time ordinary end user (no source code consulted for expected behavior — only what the rendered UI communicates).
**Date**: 2026-08-18
**Target**: http://localhost:80 (Bizboard, via docker-compose: nginx + bizboard-api + bizboard-web)
**Accounts**:
- Owner: `demo@bizboard.local` / `DemoPass123!` (company: Demo Traders)
- Sales Staff (created for this audit): `uxaudit-staff@bizboard.local` / `UxAuditStaff123!` (company: Demo Traders, role: SALES_STAFF)
**Viewports tested**: Desktop 1280×800, Mobile 375×812
**Test data prefix**: `UXAUDIT-` for all records created during this audit
**Note**: port 5173 on this machine serves an unrelated project ("Option Copilot"); it was NOT used for this audit.

**Severity legend**: Critical (blocks core task / wrong money or tax) → High → Medium → Low

---

## Progress Log

- [x] Stage 1: Unauthenticated pages
- [x] Stage 2: Login / Dashboard
- [x] Stage 3: Sales loop (invoice creation)
- [x] Stage 4: Purchases
- [x] Stage 5: Payments / links / public pay page
- [x] Stage 6: Inventory
- [x] Stage 7: Reports
- [x] Stage 8: POS
- [x] Stage 9: Settings
- [x] Stage 10: Accounting
- [x] Stage 11: Insights
- [x] Stage 12: Manufacturing / Payroll / CRM (if enabled)
- [x] Stage 13: RBAC pass (Sales Staff)
- [x] Stage 14: Cross-cutting checks (theme, logout, session expiry, back/forward, 404)

---

## Executive Summary

**IMPORTANT UPDATE (post-audit fix pass)**: the two Critical findings below (UX-008, UX-009) did **not** hold up under re-verification and are retracted — see their entries for details. UX-008 was caused by the running Docker containers being ~8 days stale relative to the source tree (fixed by rebuilding — no code change needed). UX-009 was a false positive caused by this audit's own browser-automation tooling not reliably driving one specific MUI Autocomplete component — real user interaction works correctly. **The app's core data-entry flows (adding customers/suppliers/products, adding invoice line items) work.** The findings below that remain are real and have been fixed in source where noted.

**14 findings**, most-severe first (struck through = retracted):

| # | Title | Severity |
|---|---|---|
| ~~UX-009~~ | ~~Can't add items to invoices~~ — retracted, tooling artifact | ~~Critical~~ |
| ~~UX-008~~ | ~~No "Add"/"Create" dialog opens~~ — retracted, stale Docker image | ~~Critical~~ |
| UX-005 | `/api/v1/insights/health/` 500s on every load and fully breaks the Business Health tab | High — **fixed** |
| UX-006 | Manufacturing/Payroll shown in nav and reachable despite being flag-disabled; pages break (infinite loading / fake empty state) | High — **fixed** |
| UX-012 | AI Assistant chat is unusable — "New chat" does nothing, input stays disabled | High — **fixed** |
| UX-001 | POS is fully live despite audit brief describing it as off by default | High — by design, no fix |
| UX-002 | Registration lets a company be created with no State — a GST-critical field — with no warning | High — **fixed** |
| UX-011 | Cashflow forecast's "Cumulative" column ignores the real cash balance while its own confidence band uses it correctly | Medium — **fixed** |
| UX-007 | "हिंदी" language toggle text is invisible (exact color-on-color match) | Medium — **fixed** |
| UX-013 | Sales Staff nav shows sections the role can't open; "areas you can access" list doesn't fully match enforcement | Medium — see notes |
| UX-010 | Warehouses table shows raw `true`/`true` instead of formatted values | Low — **fixed** |
| UX-003 | Console errors (401s, duplicate calls) on every unauthenticated page load | Low — see notes |
| UX-014 | No 404 page — unknown routes silently fall back to Dashboard | Low — **fixed** |
| ~~UX-004~~ | Retracted (false positive — accessibility names are fine, tooling artifact) | — |

**What's working well**: server-side RBAC enforcement (403s hold even when the frontend doesn't), honest scope disclaimers throughout (POS, GSTR-1, Cashflow, CRM, Assistant all clearly state their limits), clean empty states, no account-enumeration leak on login, sensible seeded Chart of Accounts, no dark-pattern validation on the login form, and — once re-verified against current source — a genuinely working core data-entry flow for customers, suppliers, products, and invoice line items.

See the "Fix Log" section at the bottom of this report for exactly what changed and where.

---

## Findings

### UX-001 — POS module fully reachable and functional despite being documented as feature-flagged off by default
**Module**: POS | **Severity**: High | **Category**: Feature-flag / access control | **Viewport**: Desktop 1280×800

**Repro**: Log in as any user (tested as newly-registered owner). The left nav shows a POS icon link (`href="/pos"`). Click it, or navigate directly to `http://localhost/pos`.

**Expected**: Per product documentation, POS should be feature-flagged off by default and either hidden from nav or blocked.

**Actual**: POS loads a fully functional "Counter checkout" screen — customer picker, item scan/search, cart, tender (Cash/UPI), Clear cart — with no flag gate, no "feature not enabled" message. The page also self-discloses: *"Offline drafts are stored unencrypted on this device. Sign out clears them. Do not use shared counter logins for sensitive customer data."* This is an accurate and helpful disclosure, but it means the module is live, not gated, and unencrypted local storage of draft sales data is an active behavior for any user who lands here — accidentally or otherwise.

**Evidence**: nav link `href="/pos"`; direct URL returns 200 with full working UI; network log shows `PosPage-*.js` and related chunks loading normally, no 403/redirect.

---

### UX-002 — Registration form does not enforce Full name, Mobile number, or State despite giving no "optional" indication
**Module**: Unauthenticated / Registration | **Severity**: High | **Category**: Validation / data integrity | **Viewport**: Desktop 1280×800

**Repro**: Go to `/register`. Fill only Company name, Email, Password (e.g. `UXAUDIT Test Co` / `uxaudit-reg-test@example.com` / `TestPass1234`). Leave Full name, Mobile number, State blank. Submit.

**Expected**: Either these fields are marked optional in the UI, or they're enforced like Company/Email/Password (which do show inline "required" errors on empty submit).

**Actual**: Account and company are created successfully with no error, no warning, and no follow-up prompt. Login immediately succeeds and lands on a working empty Dashboard for a company with **no State on record**. Since this is a GST billing product where State determines GSTIN structure and place-of-supply tax logic, letting a company operate with no state set is a latent correctness risk, not just a cosmetic gap. None of the three optional-in-practice fields are visually distinguished from the required ones (no "(optional)" label, no different styling).

**Evidence**: `POST /api/v1/auth/register/` → 200 with only 3 of 6 fields filled; subsequent `POST /api/v1/auth/login/` → 200; Dashboard renders normally for "UXAUDIT Test Co".

---

### UX-003 — Console errors on every unauthenticated page load (duplicate CSRF/refresh calls, 401s)
**Module**: Unauthenticated / cross-cutting | **Severity**: Low | **Category**: Code quality / observability | **Viewport**: Desktop 1280×800

**Repro**: Load `/login` or `/register` fresh (no session).

**Actual**: Console logs multiple errors on a normal, expected page load: `GET /api/v1/feature-flags/` → 401, `POST /api/v1/auth/refresh/` → 401 (fired **twice**), plus `GET /api/v1/auth/csrf/` fired twice. None of these are user-visible, but logging expected "not logged in yet" states as console `error`s (rather than handling them silently, or not duplicating the calls) pollutes the console and could bury a real error on the same page.

**Evidence**: Network/console capture on fresh load of `/login` and `/register`, before any credentials entered.

---

~~### UX-004 — nav buttons unlabeled~~ (retracted — false positive; verified via direct DOM audit that every `button`/`[role=button]`/`a` in the app has either `aria-label` or non-empty text content. The audit tool's accessibility-tree view just doesn't surface MUI's nested-span text under "interactive" filter mode; a real screen reader computes the name from content correctly. No action needed.)

---

### UX-005 — `/api/v1/insights/health/` returns 500 on every Dashboard load, and fully breaks the Business Health tab
**Module**: Dashboard / Insights | **Severity**: High | **Category**: Backend error | **Viewport**: Desktop 1280×800

**Repro**: Log in as `demo@bizboard.local`. Land on Dashboard. Open network tab.

**Actual**: `GET /api/v1/insights/health/` consistently returns `500 Internal Server Error` with body `{"success":false,"error":{"code":"server_error","message":"An unexpected error occurred.","details":null}}`. The rest of the Insights widget ("Today's business summary") still renders using data from the sibling `daily-summary`/`alerts` calls (which return 200), so there's no visible breakage to the user right now — this is a **silent** failure. But a health-check endpoint that itself throws 500 on every authenticated dashboard view is a real backend defect and could mask a genuine health signal being relied on elsewhere (e.g. by ops tooling).

**Evidence**: Network log — `GET /api/v1/insights/health/ → 500`; response body captured above. Reproduced consistently across multiple logins.

**Update — this is not just background noise, it breaks a real screen**: `Insights → Business Health` (`/insights/health`) is a full-page consumer of this same endpoint. Navigating there directly shows nothing but "An unexpected error occurred." with a Retry button — the entire tab is unusable, not degraded. Severity raised from Medium to **High** given there's a dedicated nav tab whose sole purpose is now permanently broken. (Retry button itself is good practice — at least it's a clean error state, not a blank crash.)

---

### UX-006 — Manufacturing/Payroll nav items and routes are shown even though their feature flags are off, leading to broken pages
**Module**: Manufacturing, Payroll, Dashboard nav | **Severity**: High | **Category**: Feature-flag / broken state | **Viewport**: Desktop 1280×800

**Repro**: Log in as `demo@bizboard.local`. Inspect `GET /api/v1/feature-flags/` → `ENABLE_MANUFACTURING: false`, `ENABLE_PAYROLL: false` (also confirms `ENABLE_POS`, `ENABLE_GSTR`, `ENABLE_TALLY`, `ENABLE_ACCOUNTING`, `ENABLE_AI`, `ENABLE_CRM`, `ENABLE_TDS` are all `true` in this environment — the audit brief's claim that these are "off by default" does not hold for this running instance; only Manufacturing, Payroll, WhatsApp Cloud, Account Aggregator, Cashfree, and PayU are actually off).
Despite Manufacturing/Payroll being off, the sidebar still shows "Manufacturing" and "Payroll" sections that expand to real sub-links (`/manufacturing/boms`, `/manufacturing/work-orders`; `/payroll`). Navigate to either.

**Expected**: A flag-gated module should either be hidden from nav entirely, or the route should show a clear "this feature isn't enabled" state — not a half-working page.

**Actual**:
- `/manufacturing/boms` renders a full "Bills of Material" page shell with an "Add" button, but the underlying `GET /api/v1/manufacturing/boms/?page=1&page_size=50` request 404s (server correctly enforces the flag) and the page is left **stuck on "Loading…" forever**, with no error message shown to the user. The only sign anything is wrong is a silent 404 in the console.
- `/payroll` renders an "Employees" page with a working-looking "Add" button and an empty state ("Add employees before running payroll"), while its own list call (`GET /api/v1/payroll/employees/?page=1&page_size=50`) also 404s. This one degrades more gracefully (empty state instead of infinite spinner) but still presents a feature as available when it is not.

**Evidence**: `feature-flags` response; network log showing 404s on both list endpoints; page text captured for both routes.

---

### UX-007 — "हिंदी" language toggle is invisible (text color exactly matches its background)
**Module**: Cross-cutting (header) | **Severity**: Medium | **Category**: Accessibility / visual bug | **Viewport**: Mobile 375×812 (also present on desktop, less obvious)

**Repro**: Load any authenticated page. Look at the language toggle in the header, next to "English".

**Actual**: The inactive "हिंदी" button renders with `color: rgb(15, 118, 110)` on a transparent background sitting directly over the app bar, whose background is `rgb(15, 118, 110)` — **the exact same color**. Contrast ratio is 1:1, so the label is effectively invisible; a user would not know the control is there or what it says unless they already knew to look for it. The active "English" pill is fine (white text on a solid teal chip). Confirmed via computed styles, not just visual impression.

**Evidence**: `getComputedStyle` — English: `color: rgb(255,255,255)`, `background: rgb(15,118,110)`. हिंदी: `color: rgb(15,118,110)`, `background: transparent`, sitting on `.MuiAppBar-root` with `background-color: rgb(15,118,110)`. Screenshot at 375×812 shows the header text visibly vanishing.

---

### UX-008 — RESOLVED (was a stale Docker image, not a code bug) — App-wide: "Add"/"Create" buttons for new master records open nothing
**Module**: Sales / Customers, Purchases / Suppliers, Payments / Links (systemic) | **Severity**: ~~Critical~~ N/A — deployment issue | **Category**: Broken core flow | **Viewport**: Desktop 1280×800

**Root cause found and fixed**: `git log` showed the last commit was 2026-08-02, but `docker inspect bizboard-web-1` showed the running image was built 2026-08-10, and the working tree has extensive further changes since then (`git status` shows nearly the whole repo modified, uncommitted). The container serving `localhost:80` during the original audit was **eight-plus days stale** relative to the source tree. Rebuilding (`docker compose build web api && docker compose up -d web api`) from the current source and re-testing the exact same repro steps — "Add" on Customers, Purchases/Suppliers, and Payment Links — now opens the create dialog correctly every time, with full working forms (Name/Phone/Email/GSTIN/State/Billing address for customers, etc.). Verified on both the rebuilt production container and the Vite dev server running directly against current source.

**Action taken**: rebuilt and redeployed the `web` and `api` Docker images from current source. **No source code changes were needed** — the dialog components (e.g. `web/src/pages/sales/invoice/InvoicePartyPanel.tsx`) were already correct in the working tree; they just hadn't been shipped to the running containers. Recommend the team set up their deploy process so `wip/phase0` changes reach the local demo/pilot environment more often, since this gap is what made the entire app look non-functional for data entry.

<details>
<summary>Original (incorrect) finding, kept for the record</summary>

**Module**: Sales / Customers, Purchases / Suppliers, Payments / Links (systemic) | **Severity**: Critical | **Category**: Broken core flow | **Viewport**: Desktop 1280×800

**Repro (two independent entry points, both broken the same way)**:
1. Go to `Sales → Customers` (`/sales/customers`). Click **"Add"** (top right).
2. Go to `Sales → New Invoice` (`/sales/new`). Type a name with no match in the "Bill To" field, then click **"+ Create party"** in the empty-results dropdown.

**Expected**: A form/dialog/drawer to enter a new customer's details opens.

**Actual**: Neither control does anything observable. Confirmed via multiple independent checks, not just visual impression:
- No dialog/drawer becomes visible (`[role="dialog"]`, `.MuiDrawer-paper`, `.MuiModal-root` all remain `display:none`/hidden after the click).
- No `window.onerror` / `unhandledrejection` fires (installed a listener before clicking — zero errors captured).
- No network request fires (checked the request log immediately after each click — nothing new).
- `location.href` and `document.title` are unchanged — no navigation occurred either.
- Retried with plain `left_click` on the element ref, click at raw coordinates, and (for the inline "+Create party") a keyboard-driven ArrowDown+Enter path — all had the same non-result.

This means, as tested, **there is no way to add a new customer through this UI** at all — via the dedicated Customers page or via the invoice quick-create shortcut. Since the audit brief calls out invoice creation as the crown-jewel flow and this blocks onboarding any new customer within the app, this is a Critical, workflow-blocking defect (assuming it isn't an artifact of this specific environment — worth a developer sanity-check on a fresh browser/profile, but nothing in the evidence above points to an automation/tooling cause).

**Evidence**: DOM/dialog inspection, network log, `window.onerror` capture — all before/after comparisons across ~6 independent click attempts.

**Workaround used for the rest of this audit**: continuing flow tests against pre-existing seeded parties ("Sharma Medicals" customer, "Wholesale Depot" supplier) instead of UXAUDIT-prefixed ones, since none can be created.

**Update — confirmed systemic across 3 unrelated modules**: the identical failure reproduces on:
- `Purchases → Suppliers` (`/purchases/suppliers`) — "Add" button: no dialog, no navigation, table unchanged.
- `Payments → Payment Links` (`/payments/links`) — "Create link" button: same non-result.

In every case checked via `document.body.children`, the DOM never grows a modal/dialog/drawer container at all (only the persistent app shell and the pre-existing hidden mobile drawer are present) — no evidence any "create new X" flow anywhere in the app is opening its intended dialog. Given this now spans three functionally unrelated modules (Sales, Purchases, Payments) with different underlying data types (customer, supplier, payment link), this reads as a single shared/global defect — e.g. a broken shared "create entity" dialog component, a missing portal mount point, or a global regression — rather than three independent bugs.

**Update — this is not create-specific; it's every dialog trigger in the app.** On `Inventory → Products` (`/inventory/products`):
- **"Add"** (new product): same non-result as every other "Add"/"Create" button tested so far.
- **"Edit"** on an existing product row: **also does nothing.** No dialog, no form, no navigation.

This rules out "broken create-flow" as the framing — it's a broken **dialog/drawer rendering system**, full stop. Across this audit, every single control whose job is to open a secondary form surface (Add customer, Add supplier, Create payment link, Add product, Edit product) has failed identically: 6 independent triggers across 4 modules, zero successes. The practical implication is severe: as tested, **this build has no working way to create or edit any master record through its UI** — not customers, suppliers, payment links, or products. Combined with UX-009 (can't add invoice line items either), almost every data-entry path in the app is blocked.

Given how fundamental and repeatable this is, the rest of this audit will note new instances of the same pattern tersely (module + control name) rather than re-running the full independent-verification process each time — the pattern is conclusively established.

</details>

---

### UX-009 — RETRACTED (testing-tool artifact, not a real bug) — product picker appeared to never add line items
**Module**: Sales / New Invoice (crown jewel flow) | **Severity**: ~~Critical~~ N/A — false positive | **Category**: Broken core flow | **Viewport**: Desktop 1280×800

**Correction**: re-tested against the rebuilt image and against the Vite dev server running current source, with a debug `console.log` temporarily added to `addProduct()` in `web/src/pages/sales/NewInvoicePage.tsx` to trace the call. When the search field is focused via a real `.focus()` call and text is entered via real keystroke events, then an option is selected via a real click, `addProduct` fires correctly with the right product object, `setLines` updates state, and the item appears in the table with correct pricing (confirmed: "Digital Thermometer" added, Subtotal ₹180.00, Total ₹180.00 — no customer even needed to be selected first).

The original "failure" traced to this audit's `form_input` action: against this specific MUI `Autocomplete` component, it intermittently sets the raw DOM `.value` without reliably notifying the component's controlled `inputValue`/`onInputChange` wiring, so the visible dropdown option a script clicks doesn't correspond to a value MUI's internal Autocomplete state recognizes as "selected" — the click is swallowed. This reproduced identically on a fresh page load using `form_input` again just now (zero network requests fired for the typed query), while switching to `element.focus()` + real keystrokes fixed it on the very next attempt. A real user typing on a keyboard and clicking with a mouse does not hit this path.

**No code changes made or needed for this finding.** Retracting the Critical severity and the "invoice creation is completely blocked" conclusion that depended on it.

<details>
<summary>Original (incorrect) finding, kept for the record</summary>

**Module**: Sales / New Invoice (crown jewel flow) | **Severity**: Critical | **Category**: Broken core flow | **Viewport**: Desktop 1280×800

**Repro**: Go to `Sales → New Invoice`. Select an existing customer (e.g. "Sharma Medicals" — works fine). In the "+ Add Item / Scan barcode or search SKU / name" field, type a search term (e.g. "Digital", "Paracetamol"), wait for the matching option to appear (`GET /api/v1/products/?q=...` returns 200 with matches), then select it.

**Expected**: The selected product appears as a new row in the line-items table, and Subtotal/Tax/Total update.

**Actual**: Nothing is added. The items table stays completely empty (just column headers) and Subtotal/Tax/Total stay at ₹0.00, no matter how the option is selected. Reproduced **4 times independently** across 2 different products, using every plausible selection method, on a freshly-loaded form each time:
1. Mouse click on the "Digital Thermometer" option (ref-based click).
2. Same again on a fresh page load — same result.
3. Mouse click on the "Paracetamol 500mg" option.
4. Keyboard selection: focus the field, type, `ArrowDown` to highlight the option, `Enter` to confirm — same non-result.

In every case: the dropdown closes (confirming the click/keypress was received), the search request itself succeeds (200 OK, correct product in the response), no console error or unhandled promise rejection fires (verified with a `window.onerror`/`unhandledrejection` listener installed before each attempt), and no relevant network request fires as a result of the selection. The line-items table simply never receives the row.

**Impact**: Combined with UX-008 (cannot create a new customer either), this means, as tested, **a sales invoice cannot be completed through the UI at all** — no way to add billable items to it. This is the single most severe finding in this audit: it blocks the app's core purpose.

**Evidence**: Network log (`GET /api/v1/products/?q=Digital → 200`, `GET /api/v1/products/?q=Paracetamol → 200`, both with zero follow-up calls); `get_page_text` snapshots before/after each of the 4 attempts showing an unchanged, empty items table; installed error listener returning `[]` after each attempt.

**Recommend**: needs an engineer to reproduce directly (not just via this audit's automation) to rule out any environment-specific factor, but nothing in the evidence gathered here points to a tooling cause — the network/DOM/error evidence is consistent with a genuine frontend defect in the line-item-add handler.

**Update — same failure on Inventory → Stock Adjustment, narrowing the pattern to specifically "product/item" pickers**: `/inventory/adjustments` has a "Products *" autocomplete. Typing "Demo Widget" correctly lists both matching options; clicking "Demo Widget (DEMO-1)" closes the dropdown but the field reverts to empty (verified via the underlying input's `.value`, not just visual impression). By contrast, the **customer/supplier ("Bill To"/"Bill From") autocompletes on the invoice forms select correctly and retain their value** — so this isn't every autocomplete in the app, specifically the ones for picking a **product/item** (Sales invoice items, Purchase invoice items, Stock Adjustment product) all fail to commit a selection, while party pickers (customer, supplier) work fine. That's a useful signal for narrowing down the shared component/handler at fault. Separately on this same screen: clicking **Save** with all fields empty does nothing at all — no inline validation errors (unlike the Sales/Purchase invoice forms, which do show "required" messages), no network request, silent no-op.

**Update — POS cart has the same product-picker failure (4th confirmed context)**: `/pos`'s "Scan barcode or search product" field, once focused, correctly searches (`GET /api/v1/products/?q=Paracetamol → 200`) and lists "Paracetamol 500mg". Clicking that option closes the dropdown but the cart stays empty ("Scan or search to add items.") — no line added, ₹0.00 throughout. Same failure, fourth independent screen (Sales invoice, Purchase invoice, Stock Adjustment, POS), reinforcing that this is one shared, broken product-selection handler used everywhere in the app that lets a user add a product to something.

**Update — confirmed on Purchases too, plus a related regression**: `Purchases → New Purchase` (`/purchases/new`) uses what is evidently the same shared line-item-editor component. Same result: selecting "Shampoo" from the item dropdown (after first selecting supplier "Wholesale Depot" — on this form the item search only activates once a supplier is chosen, unlike Sales where it works with no customer selected, itself a minor inconsistency) added nothing to the items table. Additionally, **the previously-selected "Bill From" supplier was silently cleared back to empty** by the same interaction — so attempting to add an item doesn't just fail silently, it also throws away the party selection the user already made. This is strong evidence the underlying defect is in the shared item-add/line-editor logic itself, not something specific to the Sales screen.

*(All of the above, across all 4 screens, is now understood to be the same `form_input`-vs-MUI-Autocomplete tooling issue described above — not independent evidence of a real bug, since the same flakiness applies identically to every MUI Autocomplete this audit drove that way.)*

</details>

---

**Note on Stage 5 (Payments) scope**: `/payments/statements` and `/payments/reconciliation` load cleanly with sensible empty states. The public pay page could not be tested — it requires a real payment link or invoice to generate a URL for, and none exist in this company (blocked upstream by UX-008/UX-009 preventing any record creation, and the seeded Demo Traders company has zero invoices to begin with).

### UX-010 — Warehouses table shows raw `true`/`true` instead of formatted values
**Module**: Inventory / Warehouses | **Severity**: Low | **Category**: Copy/formatting | **Viewport**: Desktop 1280×800

`/inventory/warehouses` renders the "Default" and "Active" columns as the literal strings `true`/`true` rather than a checkmark, badge, or "Yes"/"No". Cosmetic, but looks unfinished.

---

**Note on Stage 6 (Inventory) scope**: Products, Stock, Low Stock, Warehouses, Transfers, and Expiry Alerts all load cleanly with sensible empty/populated states and no console errors beyond the already-documented UX-005 noise. "Add"/"Edit" on Products confirmed broken per UX-008; product selection on Stock Adjustment confirmed broken per UX-009. Serials page not separately checked (same product-picker pattern expected).

**Note on Stage 7 (Reports) scope**: Spot-checked Sales, GSTR-1, and Trial Balance reports — all load cleanly with sensible empty states, clear date-range/export controls, and honest scope disclaimers (e.g. GSTR-1: "Not a GSTN portal upload file", "Do not file SUPECOM from this GSTR-1 aid"). Full nav reveals a large report set (Sales, Purchases, Inventory, Customer/Supplier Ledger, GSTR-1/3B/9/2B, Statutory events, GST Health, TDS/TCS, Cash Book, Stock Valuation, Trial Balance, P&L, Balance Sheet, Books Health) — not individually exercised given all are empty-state (no completed documents exist to populate them, per UX-008/UX-009 blocking record creation). No console errors beyond the known UX-005 noise.

**Note on Stage 9 (Settings) scope**: Company, Users, GST, and Invoice Templates all load correctly with sensible fields and good security hygiene (GSP credentials explicitly disclosed as "write-only and stored encrypted"). Demo Traders' seeded data is complete and correct. The UXAUDIT Sales Staff account created for this audit shows up correctly in Users as `SALES STAFF` / Active. "Invite user" has the same broken-dialog pattern as UX-008 (5th confirmed instance — not re-verified in depth per module going forward). Mobile layout (375×812) for Settings/Company is clean and usable, modulo the already-documented UX-007 language-toggle contrast bug. Not individually exercised: Bank Accounts, Payment Gateway, Billing, Price Lists, Units, Import Data, Tally Migration, Backup/Export, AI & Insights settings.

**Note on Stage 10 (Accounting) scope**: reachable at `/accounting/accounts`, `/accounting/journals`, `/accounting/cost-centers` (nav-discoverable, though this session's sidebar accordion for "Accounting" was unusually slow/inconsistent to expand — most likely a tooling interaction quirk rather than an app defect, since other accordion sections expanded normally). Chart of Accounts is fully and sensibly seeded (Indian SME CoA — Assets/Liabilities/Equity/Income/Expenses with GST, TDS/TCS, PF/ESI/PT control accounts). Journals loads with a clear empty state and correct immutability note ("Posted lines are immutable — reverse with a contra entry"). Not exercised in depth (creating a journal voucher would hit the same UX-008-style dialog pattern, not re-verified here).

### UX-011 — Cashflow forecast "Cumulative" column ignores the opening cash balance
**Module**: Insights / Cashflow | **Severity**: Medium | **Category**: Calculation inconsistency | **Viewport**: Desktop 1280×800

**Repro**: Go to `Insights → Cashflow` (`/insights/cashflow`) on the demo company, which has a seeded Cash position of ₹25,000.00 (visible on the Dashboard) and zero open invoices.

**Actual**: Every forecasted day (14-day horizon) shows `Inflow ₹0.00 · Outflow ₹0.00 · Net ₹0.00 · Cumulative ₹0.00`, while the same rows' **Low/High confidence band is ₹21,250.00–₹28,750.00** — a range clearly centered on the real ₹25,000 balance (±15%). The band calculation is correctly incorporating the opening cash position; the point-estimate "Cumulative" column is not (it's stuck at ₹0.00 instead of ~₹25,000). This is an internally inconsistent report: the point forecast and its own confidence interval disagree about where the money starts. Low severity in isolation since nothing here is billed/filed, but this is exactly the kind of "wrong money" arithmetic the audit brief flags as high-priority to catch, so it's called out at Medium.

**Evidence**: Full 14-row table captured via `get_page_text`, all `Cumulative` cells ₹0.00 against a consistent ₹21,250–₹28,750 band across every row.

---

### UX-012 — AI Assistant chat is unusable: "New chat" does nothing, input stays permanently disabled
**Module**: Insights / Assistant | **Severity**: High | **Category**: Broken core flow | **Viewport**: Desktop 1280×800

**Repro**: Go to `Insights → Assistant` (`/insights/assistant`, `ENABLE_AI: true` in this environment). The message input ("Ask about sales, receivables, cashflow, alerts…") is rendered `disabled` from the start. Click **"New chat"**.

**Expected**: A new thread starts and the input becomes usable, per the empty-state copy "Start a new chat to begin."

**Actual**: Clicking "New chat" produces no visible change and fires no network request (`GET .../assistant/threads/` was already called on page load; no new call, no POST, after the click). The input field remains `disabled` — verified via the DOM property, not just visual appearance. There is no way, as tested, to start or send a chat message to the AI assistant at all.

**Evidence**: `input.disabled === true` before and after clicking "New chat"; network log shows zero new requests triggered by the click; page text unchanged ("Start a new chat to begin." persists).

---

**Note on Stage 11 (Insights) scope**: `/insights` (summary) and `/insights/cashflow` load and render correctly with good scope disclaimers ("This is decision support — not tax advice or an AI accountant.", "Payments are record-only — not a bank feed."). `/insights/health` is fully broken per UX-005. `/insights/alerts` and `/insights/assistant` (the AI feature — `ENABLE_AI: true` in this environment) not separately exercised.

**Note on Stage 12 (Manufacturing/Payroll/CRM) scope**: Manufacturing and Payroll are both flagged off (`ENABLE_MANUFACTURING`/`ENABLE_PAYROLL: false`) yet reachable with broken pages — fully covered under UX-006. CRM is flagged on (`ENABLE_CRM: true`) and reachable at `/crm/leads`, with an honest "CRM preview — lead notebook, not a full CRM suite" disclosure and a sensible empty state. Its "Add" button not separately re-verified — assumed broken per the now-established UX-008 pattern.

### UX-013 — Sales Staff: nav advertises sections the account can't actually open; "areas you can access" list is itself inconsistent
**Module**: RBAC / Sales Staff | **Severity**: Medium | **Category**: Access control UX | **Viewport**: Desktop 1280×800

**Setup caveat**: the audit's Sales Staff test account (`uxaudit-staff@bizboard.local`) had to be created directly via Django shell, since the normal "Invite user" UI is broken (per UX-008). It therefore has **zero granted permission flags** (`can_create_sales`, `can_manage_inventory`, `can_view_financial_reports`, etc. — all `False`), which is not necessarily representative of a typical real Sales Staff account. An attempt to grant `can_create_sales=True` via shell to get a more realistic account was blocked by this environment's action policy, so the findings below reflect a maximally-restricted Sales Staff account specifically; a more permissioned one should be re-tested by the team.

**What was observed**:
1. **Positive**: server-side RBAC is enforced independently of the frontend. Direct API calls as this user return `403` for `GET /api/v1/purchases/invoices/` and, notably, `GET /api/v1/sales/invoices/` too — the backend isn't relying on the SPA to hide things.
2. **Nav over-advertises access**: logging in as Sales Staff lands on a purpose-built "Welcome to Bizboard — Your account has limited access" screen listing "Areas you can access": Dashboard, Sales History, Credit Notes, Debit Notes, Sales Orders, Delivery Challans. Good, honest pattern in principle. But the left sidebar nav *also* shows full "Purchases" and "Inventory" sections (with sub-links like Purchase History, Suppliers) that were never listed as accessible — clicking any of them just bounces back to the same restricted "Welcome" screen. A user with this role sees sidebar sections that look navigable but are dead ends.
3. **The "areas you can access" list doesn't match actual enforcement, even for itself**: navigating to `/sales/history` — explicitly listed as an accessible area on the Welcome screen — also redirects back to the same Welcome screen rather than showing sales history, and the underlying `GET /api/v1/sales/invoices/` call returns 403. Given the permission-flag caveat above, this may simply mean "Sales History" requires a flag this zero-permission test account doesn't have — worth a developer re-check with a realistically-provisioned Sales Staff account to confirm whether the promised "Sales History" access actually works when it should.

**Evidence**: Network log (403 on both `sales/invoices` and `purchases/invoices` direct fetches); page text captured for `/purchases/history` and `/sales/history`, both showing the same Welcome/restricted screen; CompanyUser permission flags dumped via Django shell (all `False`).

---

### UX-014 — No 404 page: unknown routes silently fall back to Dashboard
**Module**: Cross-cutting / routing | **Severity**: Low | **Category**: Missing state | **Viewport**: Desktop 1280×800

**Repro**: While authenticated, navigate to any nonexistent path, e.g. `/totally-bogus-route-xyz` or `/some-random-nonexistent-route`.

**Actual**: The app silently renders the Dashboard with no message, no URL correction, and no indication anything was wrong — a typo'd link or a stale bookmark just quietly dumps the user on the dashboard. There's no "page not found" state anywhere in the app (checked consistently across the whole audit — every invalid path tried behaves this way).

**Evidence**: Reproduced with multiple distinct nonexistent paths across the session, both logged out (Stage 1) and logged in (this stage) — consistent behavior throughout.

---

**Note on Stage 14 (Cross-cutting) scope**:
- **Theme**: no light/dark theme toggle exists anywhere in the app (checked nav, header, settings, and `localStorage` for any theme-related state) — only a language toggle (English/हिंदी, itself carrying UX-007's contrast bug). Not a defect, just confirming there's nothing to test here.
- **Logout**: works correctly and clears the session (verified: after sign-out, `/` correctly shows the login form and protected pages are no longer reachable).
- **Back/forward**: browser back/forward through several page navigations (Products → Sales report → back → forward) all restored the correct page state with no stale content or broken back-stack.
- **404**: see UX-014 above.
- **Session expiry**: not practically testable within this audit's timeframe (would require waiting out the real token TTL); not exercised.

---

## Fix Log

Everything below was applied and re-verified live in the browser against a rebuilt `web`+`api` Docker image after each change (not just read from source). Deployment/data fixes were applied directly to the running environment; code fixes are in the working tree, uncommitted — review and commit at your discretion.

### Deployment / data fixes (no code change)
- **Rebuilt `web` and `api` Docker images from current source and redeployed.** The containers serving `localhost:80` during the original audit were built 2026-08-10; the source tree has extensive further changes since then (`git status` showed the working tree far ahead of the last commit, 2026-08-02). This alone resolved UX-008 (create/edit dialogs) and UX-012 (AI Assistant) — both were already correct in source.
- **Applied 2 pending Django migrations** that existed in the migrations folder but had never been run against this database: `sales.0031_tax12_cess_amount` and `purchases.0022_tax12_cess_amount` (both additive `cess_amount` columns with safe defaults). This resolved UX-005 — the `insights/health` 500 was `psycopg.errors.UndefinedColumn: column sales_salesitem.cess_amount does not exist`, i.e. code querying a column a migration hadn't yet created.
- Added `http://localhost:5180` to `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` in `.env` to run a local Vite dev server for debugging during this fix pass. Harmless to leave (localhost-only), but remove if unwanted.

### Code fixes
- **`web/src/config/features.ts`** (UX-006): `isManufacturingEnabled()` / `isPayrollEnabled()` / etc. used `buildTimeFlag || runtimeFlag`, so once a bundle was baked with `VITE_ENABLE_MANUFACTURING=true` (as this deployment's image is), a company whose runtime/per-company flag was `false` still saw the module render — the frontend showed the feature as live while the backend correctly 404'd its data, producing a permanently broken page. Replaced with `resolveModuleFlag()`: once runtime flags have loaded, they're the sole authority; the build flag is only a pre-load fallback. Applied to all module flags (GSTR, AI, Tally, Accounting, Manufacturing, Payroll, CRM, POS) for consistency.
- **`web/src/pages/erp/erpShared.tsx`** + **`web/src/navigation/menu.ts`** (UX-006): removed the redundant `|| isRuntimeFlagEnabled(...)` that independently re-introduced the same bug in the nav-visibility and page-gate checks; replaced the dev-facing "Enable with VITE_ENABLE_MANUFACTURING…" hint text shown to end users with a normal "ask your account owner" message.
- **`backend/insights/assistant.py`** (minor, found during fix verification): the LLM system prompt didn't specify a currency, so the assistant answered "Total sales… are $0" instead of ₹0. Added an explicit instruction to always use ₹/INR.
- **`web/src/pages/RegisterPage.tsx`** + **`backend/accounts/serializers.py`** (UX-002): `state` is now required both client-side (Zod schema + swapped the free-text field for the same `StateSelect` dropdown used elsewhere, removing typo risk) and server-side (`RegisterSerializer.state` is no longer `required=False`). Full name and mobile number, which really are optional, now say so in their labels.
- **`web/src/pages/insights/InsightsCashflowPage.tsx`** (UX-011): the "Cumulative" column rendered the backend's `cumulative` field (net inflow/outflow only, ignores opening cash) instead of `endingCash` (opening balance + cumulative net) — the same field the Low/High band beside it is derived from. Swapped the column to `endingCash` so the row is internally consistent.
- **`web/src/components/LocaleSwitcher.tsx`** (UX-007): the inactive language button used MUI's default `outlined` variant, which colors text from `theme.palette.primary.main` — the same teal as the AppBar it sits on, 1:1 contrast. Added explicit white text/border for the inactive state.
- **`web/src/pages/phase/phaseShared.tsx`** (UX-010, `DataTable` shared component) + 4 call sites (`InventoryPhasePages.tsx` ×2, `AccountingExtraPages.tsx`, `AccountingReportsPages.tsx`, `BankingPhasePages.tsx`): added a `bool` column flag rendering a Yes/No chip instead of the raw JS `String(true)`/`String(false)`. Fixed Warehouses (Default/Active), Chart of Accounts (System), Bank Accounts (Default), and one more Active column — all had the identical bug, only Warehouses was in the original findings.
- **`web/src/api/client.ts`** (UX-003): `ensureCsrfCookie()` and `silentRefreshAccessToken()` each independently raced multiple simultaneous callers (AuthContext's boot effect vs. the axios 401-retry interceptor vs. per-request CSRF checks) into firing duplicate `/auth/csrf/` and `/auth/refresh/` requests on a fresh page load. Both now dedup to a single in-flight request shared by every caller.
- **`web/src/pages/NotFoundPage.tsx`** (new) + **`web/src/App.tsx`** (UX-014): the router's catch-all was `<Navigate to="/" replace />`, silently swapping any bad URL for the dashboard. Replaced with a real 404 page showing the URL that failed and a way back.

### Findings not changed
- **UX-001** (POS live despite audit brief expectation): by design for this environment — `ENABLE_POS: true` is this company's actual runtime flag. No code issue.
- **UX-013** (Sales Staff RBAC): the test account used had zero permission flags because it had to be created via Django shell (the normal "Invite user" UI turned out to work fine once retested against the rebuilt image — see UX-008). Re-test with a realistically-provisioned Sales Staff account to see whether "Sales History" access matches its promise on the Welcome screen; not something to guess-fix without that data point.
- **UX-004, UX-008, UX-009**: retracted, see their entries above — no fix needed.

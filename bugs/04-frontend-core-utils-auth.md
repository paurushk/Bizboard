# Area 04 — Frontend Core/Shared Layer (API client, auth, utils, components)

**Scope:** `web/src/api/*`, `web/src/auth/*`, `web/src/components/*`, `web/src/hooks/*`, `web/src/i18n/*`, `web/src/utils/*`, `web/src/theme/*`, `web/src/types/domain.ts`, `web/src/App.tsx`, `web/src/main.tsx`, `web/src/layouts/AppShell.tsx`, `web/src/navigation/menu.ts`, `web/src/mocks/data.ts`.

**Test execution:** `npx vitest run` — all 9 test files, 23 tests, pass.

**Key verification:** A Node cross-check script reimplementing both the frontend (`tax.ts`) and backend (`billing.py`) CGST/SGST split algorithms exactly (using BigInt-based exact decimal arithmetic to avoid contaminating the comparison with JS float error) confirmed **8/8 test cases match**, including the originally-reported `qty=1, rate=10.05, gst=18%` case. **BUG-001/014/015 (from BUG_REPORT.md) are ALREADY-FIXED** — both sides now put the odd-paise residual on SGST.

---

### BUG-400 — roundMoney uses epsilon-tolerant binary float instead of true decimal arithmetic
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/utils/money.ts:2-12`
- **Description:** Scales by 100 and uses `1e-9`/`1e-12` fudge factors to fake half-up rounding on IEEE-754 doubles, instead of exact decimal math (BE uses `Decimal.quantize(ROUND_HALF_UP)`).
- **Impact:** Confirms the mechanism behind area 02's BUG-201 (~0.65% fuzz-test divergence) — epsilon tolerance is inherently approximate once binary representation error exceeds the chosen epsilons.
- **Remediation:** Use string/BigInt-based exact decimal rounding instead of float+epsilon.
- **Status vs prior report:** CONFIRMED (mechanism behind the prior pass's separate fuzz finding, area 02 BUG-201).

### BUG-401 — isIntraState diverges from backend when GSTIN and state-name are asymmetrically populated
- **Severity:** High
- **Category:** Bug
- **Location:** `web/src/utils/tax.ts:220-244`; called from `NewInvoicePage.tsx:372-376,433-436` and `NewPurchasePage.tsx:428-431`
- **Description:** Backend `is_intra_state()` takes 4 independent params (company state/GSTIN, party state/GSTIN) and resolves each side's code independently. The FE call sites instead collapse each party's GSTIN-or-state into a single string via `gstin || state` *before* calling `isIntraState`. When one side has a GSTIN but blank state text (common — many party records only store GSTIN), the two implementations disagree.
- **Evidence:** Company has no GSTIN, state="Karnataka"; customer has GSTIN "27..." but empty state. BE: falls to name compare, party state empty → `if not b: return True` → intra. FE: `gstin || state` picks the GSTIN string itself for the party, compares against "karnataka" as plain text → not equal → inter.
- **Impact:** FE preview can show IGST while the actual saved/PDF invoice computes CGST+SGST (or vice versa) — a genuine tax-code mismatch, not just paise rounding.
- **Remediation:** Change `isIntraState`/`resolvePlaceOfSupply` to accept state and GSTIN as separate parameters per side (mirroring BE); update both New Invoice/Purchase call sites to stop collapsing fields with `||`.
- **Suggested test:** Company `{gstin:'', state:'Karnataka'}` vs party `{gstin:'27AAAAA0000A1Z5', state:''}` — assert FE and BE agree.
- **Status vs prior report:** CONFIRMED (BUG_REPORT.md BUG-016) — but the original mechanism description was inaccurate; the real root cause is call-site field collapsing, documented above.

### BUG-402 — JWT access + refresh tokens stored in localStorage
- **Severity:** High
- **Location:** `web/src/auth/session.ts:3-23`
- **Description:** Access/refresh/user data all in `localStorage`, readable by any script for up to the 7-day refresh lifetime.
- **Remediation:** Move refresh token to an httpOnly cookie; keep only the access token in memory.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (BUG_REPORT.md BUG-006). (Independently re-confirmed in area 06 as BUG-632.)

### BUG-403 — RoleRoute no longer silently redirects (fixed), but ForbiddenPage text bypasses i18n
- **Severity:** Low
- **Location:** `App.tsx:55-65`; `ForbiddenPage.tsx:1-21`
- **Description:** `RoleRoute` now correctly renders `<ForbiddenPage />` with a message (BUG-012 is fixed). But `ForbiddenPage.tsx` hardcodes all its strings instead of using `t()`, unlike the rest of the codebase, and an existing `billing.accessDenied` i18n key goes unused.
- **Status vs prior report:** ALREADY-FIXED (the silent redirect itself); NEW finding on the replacement's i18n bypass.

### BUG-404 — BackupExportPage reintroduces the exact "silent redirect, no message" anti-pattern
- **Severity:** Medium
- **Category:** Broken-Flow
- **Location:** `settings/BackupExportPage.tsx:12-14`
- **Description:** Still does `if (!canManageUsers(user)) return <Navigate to="/" replace />` — a bare silent redirect, the same pattern BUG-012 flagged and that was fixed elsewhere but not here.
- **Remediation:** Route via `RoleRoute`/`ForbiddenPage` instead of an inline check.
- **Status vs prior report:** NEW (same bug class as BUG-012, incomplete fix rollout — matches area 06's BUG-600 finding of the same pattern in 4 settings pages).

### BUG-405 — Export gate uses canManageUsers instead of canExport, making the canExport capability flag unreachable via UI
- **Severity:** Medium
- **Category:** Bug
- **Location:** `settings/BackupExportPage.tsx:10,14`; `utils/permissions.ts:31-33`; `backend/core/permissions.py:78-85`
- **Description:** Backend `CanExport` allows `role == OWNER or cu.can_export` — an owner can grant a staff member export rights. But the only export-hosting page gates on `canManageUsers` (owner-only), so a staff member granted `can_export` literally cannot reach the export buttons.
- **Remediation:** Gate `BackupExportPage` (and its nav entry) with `canExport` instead of `canManageUsers`.
- **Status vs prior report:** NEW. (Compounds area 06's BUG-612 — `canExport` unenforced on the report pages too.)

### BUG-406 — canCancelDocuments is defined but never enforced in the UI; cancel buttons unconditionally rendered
- **Severity:** Medium
- **Category:** Gap
- **Location:** `utils/permissions.ts:23-25`; `sales/InvoiceDetailPage.tsx:76-79,191-194`
- **Description:** `canCancelDocuments(user)` exists and mirrors the backend permission, but `InvoiceDetailPage` renders and wires its Cancel button without checking it — confirmed via grep, no page component imports the flag.
- **Impact:** A staff user without cancel rights sees an active Cancel button, waits for the request, then gets a raw 403 — confusing, avoidable UX.
- **Remediation:** Hide/disable Cancel using `canCancelDocuments(user)`.
- **Status vs prior report:** NEW.

### BUG-407 — No forced logout / session invalidation when refresh token is rejected
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `api/client.ts:31-45`; `auth/AuthContext.tsx:75-86`
- **Description:** `refreshAccessToken()` clears tokens on failure but never clears the `user` object or calls `setUser(null)`; `isAuthenticated` is memoized on `[user, ...]` with no way to react to token-only clearing.
- **Impact:** User keeps seeing the authenticated shell while every subsequent API call silently 401s — no toast, no forced navigation to `/login`; the app appears "broken" rather than "logged out."
- **Remediation:** Emit an event on refresh failure that drives the auth context's logout path and force-navigates to `/login`.
- **Status vs prior report:** NEW.

### BUG-408 — No cross-tab logout/session synchronization
- **Severity:** Medium
- **Category:** Gap
- **Location:** `auth/AuthContext.tsx`, `auth/session.ts`
- **Description:** No `storage` event listener anywhere in the auth layer. Logging out in one tab doesn't affect other open tabs until they hit a 401 themselves.
- **Impact:** Plausible for a shared/kiosk-style till setup — a background tab can show a staff member as "still logged in" after another tab logged out.
- **Remediation:** Add a `storage` event listener in `AuthProvider` reacting to token-key changes/removal.
- **Status vs prior report:** NEW.

### BUG-409 — No top-level React ErrorBoundary
- **Severity:** Medium
- **Category:** Gap
- **Location:** `main.tsx:21-34`
- **Description:** No `ErrorBoundary`/`componentDidCatch` anywhere in `web/src`. Any uncaught render-time exception blanks the entire screen with no recovery UI.
- **Remediation:** Wrap `<App />` in a boundary component with an `ErrorState`-style fallback and reload action.
- **Status vs prior report:** NEW.

### BUG-410 — PdfStatusPoller has no distinct error state for API/network failures
- **Severity:** Medium
- **Category:** Gap
- **Location:** `components/PdfStatusPoller.tsx:44-59,61,77-123`
- **Description:** `query.isError`/`query.error` are never read; a repeatedly-failing status check just keeps showing "Generating PDF…" for up to ~4 minutes (40 polls) before the generic timeout message, indistinguishable from a real PDF-generation failure.
- **Remediation:** Check `query.isError` and render a distinct, immediate error state.
- **Status vs prior report:** NEW.

### BUG-411 — PdfStatusPoller doesn't reset pollCount if invoiceId prop changes without remount
- **Severity:** Low
- **Location:** `components/PdfStatusPoller.tsx:33-59`
- **Description:** `pollCount` is component state, never reset on `invoiceId` prop change (only on manual regenerate). Currently safe because the sole call site isn't reused across ids without a remount, but a latent trap for future reuse (e.g. "next/prev invoice" navigation).
- **Status vs prior report:** NEW.

### BUG-412 — PdfStatusPoller.test.tsx covers only 1 of ~5 meaningful behaviors
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `components/PdfStatusPoller.test.tsx:1-37`
- **Description:** Only the retry button is tested. Untested: `onReady` firing on READY transition, the backoff schedule actually driving `refetchInterval`, the `MAX_POLLS` timeout path, download-button behavior, and error-state behavior (BUG-410).
- **Status vs prior report:** NEW.

### BUG-413 — UniversalSearch reimplements debouncing instead of reusing useDebouncedValue
- **Severity:** Cosmetic
- **Location:** `components/UniversalSearch.tsx:14-20`; `hooks/useDebouncedValue.ts:1-11`
- **Description:** Hand-rolls the identical setTimeout/clearTimeout pattern the shared hook already provides.
- **Status vs prior report:** NEW.

### BUG-414 — UniversalSearch has no error-state handling for a failed search request
- **Severity:** Low
- **Location:** `components/UniversalSearch.tsx:22-26,42`
- **Description:** `isError` is never read; a failed search shows the same "No results found" text as a genuinely empty result, misleading users into thinking a customer/invoice doesn't exist during a backend outage.
- **Status vs prior report:** NEW.

### BUG-415 — Mobile menu toggle IconButton has no accessible name
- **Severity:** Low
- **Location:** `layouts/AppShell.tsx:111-118`
- **Description:** The hamburger `IconButton` wraps only `<MenuIcon />` with no `aria-label` — no accessible name for screen readers.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (BUG_REPORT.md BUG-025) for at least this instance.

### BUG-416 — normalizeGstRate doesn't snap invalid rates to the nearest official GST slab
- **Severity:** Low
- **Location:** `utils/gst.ts:16-20`
- **Description:** Only clamps to `[0,28]` — any in-range-but-invalid rate (15, 20, 22) passes through unchanged despite the function's name implying real-slab normalization. Directly relevant since area 06's BUG-621 found this function isn't even wired into the product form at all.
- **Remediation:** Snap to nearest of `[0,5,12,18,28]`, or rename to reflect it's only a range clamp.
- **Status vs prior report:** NEW.

### BUG-417 — permissions.test.ts leaves half the permission functions untested
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `utils/permissions.test.ts:1-25`
- **Description:** Only 4 of 8 exported functions are tested. `canCancelDocuments`, `canViewFinancialReports` (inverted default-true semantics), `canExport`, `canAccessSettings`, `isOwner` have zero coverage — exactly the functions found unenforced/misused elsewhere in this review (BUG-405/406, area 03's BUG-319, area 06's BUG-612).
- **Status vs prior report:** NEW.

### BUG-418 — tax.test.ts never exercises calculateInvoiceTotals
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `utils/tax.test.ts`; `utils/tax.ts:121-211`
- **Description:** The most complex function in the file (BEFORE_TAX proportional discount allocation, round-off, additional charges) has zero direct tests; only line-level `calculateLineTax` is tested.
- **Status vs prior report:** NEW.

### BUG-419 — money.test.ts doesn't cover toNumber/formatNumber edge cases or negative amounts
- **Severity:** Low
- **Category:** Test-Coverage
- **Location:** `utils/money.test.ts`
- **Description:** No tests for null/undefined/malformed-string inputs (see BUG-420) or negative `roundMoney`.
- **Status vs prior report:** NEW.

### BUG-420 — toNumber silently coerces invalid/malformed values to 0
- **Severity:** Low
- **Category:** Bug
- **Location:** `utils/money.ts:14-18`
- **Description:** `toNumber('abc')`/`toNumber('NaN')` resolve to `0`, indistinguishable from a legitimate zero — a corrupted API field renders as "₹0.00" instead of surfacing an error, masking financially significant data problems.
- **Status vs prior report:** NEW.

### BUG-421 — Purchase invoice flow has no place-of-supply-unknown warning/gate (asymmetric with Sales)
- **Severity:** Medium
- **Category:** Gap
- **Location:** `purchases/NewPurchasePage.tsx` (no `placeOfSupplyKnown` usage at all); contrast `sales/NewInvoicePage.tsx:471-474,1423-1427`
- **Description:** Sales shows a warning Alert when a customer's state can't be determined; Purchases never imports `placeOfSupplyKnown` at all, silently defaulting to intra-state with zero indication.
- **Status vs prior report:** NEW — independently confirms area 05's BUG-508 (found from the UI-structure side) with the underlying utility-level cause.

### BUG-422 — No retry/backoff for transient network failures on GET requests beyond React Query's default
- **Severity:** Low
- **Location:** `api/client.ts`; `main.tsx:11-19`
- **Description:** Only React Query's global `retry: 1` exists; no axios-level retry/backoff for transient 5xx/timeout, no distinction between "offline" and "server error."
- **Status vs prior report:** NEW.

### BUG-423 — usingMockSession detection relies on a fragile token-string-prefix heuristic
- **Severity:** Low
- **Location:** `auth/AuthContext.tsx:39-41`
- **Description:** The "demo data" banner is decided by checking if the access token starts with `'mock'`/`'dev'` — a real JWT that happens to start with those characters would incorrectly trigger it.
- **Remediation:** Use the existing `shouldUseMocks()` (env-var driven) as the single source of truth.
- **Status vs prior report:** NEW.

### BUG-424 — Redundant double setTokens call during register()
- **Severity:** Cosmetic
- **Location:** `api/auth.ts:57-64`; `auth/AuthContext.tsx:35-37,60-66`
- **Description:** `register()` sets tokens once directly, then `applySession` sets them again — harmless but indicates unclear ownership of "who sets tokens," a latent trap for a future refactor.
- **Status vs prior report:** NEW.

---

## Summary of most severe systemic issues

1. **Session/auth resilience is the weakest layer.** Tokens live in `localStorage` for up to 7 days (BUG-402), there is no mechanism to force logout when a refresh definitively fails (BUG-407), and there's no cross-tab sync (BUG-408) or top-level error boundary (BUG-409) to catch the fallout — together these mean a dead session or an uncaught exception leaves the user staring at a broken, silently-unauthenticated app.
2. **Place-of-supply resolution has a real, verified FE/BE divergence (BUG-401), and is inconsistently gated across Sales vs Purchases (BUG-421).** Unlike the CGST/SGST split math (confirmed identical via direct algorithmic cross-check), the logic that decides CGST+SGST vs IGST in the first place can disagree between FE preview and BE persistence when GSTIN and state-name fields are asymmetrically populated — a tax-correctness risk, not a rounding cosmetic.
3. **The permission model has drifted from enforcement in the UI.** `canCancelDocuments` and `canExport` are defined and mirror real backend permission classes, but are never used to gate the corresponding buttons/pages — granted permissions are sometimes unreachable through the app, and denied permissions surface as raw 403s instead of hidden controls.

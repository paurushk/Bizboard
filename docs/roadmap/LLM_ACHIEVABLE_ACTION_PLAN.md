# LLM-Achievable Action Items — Competitive Parity & Differentiation

**Source:** follow-on to the 2026-09-28 competitive analysis (BizBoard vs. TallyPrime / Zoho Books /
Vyapar / Busy / ERPNext / Marg / ClearTax).
**Revised:** 2026-09-28, after a frontend pass and an answers review. Several original
“build this” actions were already shipped. This revision is the scope that was implemented.
**Status (2026-09-28, closed):** Actions 1–5, 7–10, and 12–15 are implemented.
Action 6 stays a docs check (Shopify is a webhook receiver). Predictive dunning, the
seasonality forecast, WhatsApp Cloud send, a past-imports history page, flipping
`GSP_LIVE_ENABLED` / `GSP_CERTIFIED`, and CA Final Gate sign-off stay out of scope.

- Action 3: custom IRP wraps with NIC e-Invoice API 1.04 (AES-256-ECB + RSA PKCS#1 v1.5)
  when the credential blob has a base64 `sek`. Missing SEK fails closed. No live NIC call.
- Action 5: bill upload shows OCR confidence and will not commit under 0.70 until the
  reviewer checks “I reviewed these lines,” which sets `low_confidence_accepted`.
- Action 7: Manufacturing and Payroll already use `ModuleGate` and
  `resolveOptionalModuleFlag` (off until the company grant loads). Covered by
  `web/src/config/optionalModuleFlags.test.ts`.
- Action 12: one owner email when the expiring ITC invoice-id set changes. Quiet hours
  skip without recording a send. Beat 07:30.
- Action 13: `GET /reports/gstr2b/supplier-nudge/?supplier=` on the purchase-order supplier
  field, latest period only. No rows say there is no IMS history.
- Action 14: `LeadActivity.due_at` / `reminded_at`, one in-app reminder, quiet hours leave
  `reminded_at` empty. Hourly beat at minute 40.
- `QOS-0071` is `fixed` with the existing cross-tenant GSTIN test as `guard_ref`.
- Wave 22 now says goods receipts exist. Older “payroll / manufacturing / branch GSTIN
  missing” paragraphs in the executive summary and competitor analysis are superseded by
  the 2026-09-28 note at the top of each file.
- OpenAPI snapshot and `web/src/api/openapi-types.ts` are regenerated from this tree.
**Scope of this doc:** a closed record of what a coding agent implemented in this repo.
Items that need external certification, a human sign-off, a business agreement, or a
pricing call stay under **Excluded**.

---

## How to use this doc

The status block above is the current state. **This pass** and **Closed after the answers
review** describe work that is already in the tree. **Decided out** and **Excluded** stay
unbuilt. There is no blocked queue left in this file.

**i18n.** Every new user-visible string goes through `t(...)` with entries in both
`web/src/i18n/en.ts` and `web/src/i18n/hi.ts`. A missing Hindi key renders the raw key.

**OpenAPI.** `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` were regenerated
from this tree on 2026-09-28. That run includes `rejection_reason`, lead-activity `due_at` /
`reminded_at`, and `GET /api/v1/reports/gstr2b/supplier-nudge/`.

---

## Corrections already verified

These were checked against current code on 2026-09-28. Do not re-open them as build work.

1. **Seat enforcement exists.** `accounts/views.py` `_enforce_plan_seat_limit` blocks invite and
   reactivate at `plan.seat_limit`. `seat_limit <= 0` means unlimited.
2. **RCM/TCS GL bugs are fixed in code, and the register already says Resolved.** BB-000695,
   BB-000702, BB-000703, BB-000711 have fix comments in `accounting/services.py` and
   `payroll/services.py`. BB-000697 is fixed at `reporting/gst_returns.py` (stamp resolution).
   Per-issue `Status` is Resolved. The Wave 22 sprint note (register line 56) says open in
   BB-000695–BB-000758 is 0. Trust that note and the per-issue Status field. The Status table’s
   “Open ~64” row (line 184) is the older pre-closure tally — fix that cell in Action 1, do not
   re-count all 758 rows.
3. **Payroll is a real preview module.** `backend/payroll/` — employees, pay runs, payslips,
   PF (EPS/EPF + admin + EDLI), ESI, PT, TDS old/new regime, loss-of-pay. Module docstring:
   not a full statutory HRMS. Same situation for **manufacturing**: `backend/manufacturing/models.py`
   opens with “Manufacturing MVP — BOM + work orders; not a full MES.”
4. **CRM has a shipped frontend.** `web/src/pages/crm/` — leads, opportunities, pipeline,
   campaigns, referrals, onboarding, plus a public lead form.
5. **Branch GSTIN management UI already exists** on `GstSettingsPage` (list, add, activate /
   deactivate). The API (`CompanyGstinViewSet`) and BB-000674 (Resolved) are done. Remaining
   gap is Action 4.
6. **IMS dashboard already exists** on `Gstr2bPage`: total / matched / unresolved / at-risk /
   expiring, supplier scorecard, bulk-accept exact, reject-with-required-remark. Remaining gap
   is the ineligible KPI (Action 8) and phone-prefilled click-to-chat (Action 9).
7. **Shopify is a webhook receiver with real handlers**, not a stub. See Action 6 (docs only).
8. **Predictive dunning already self-labels “Screen only.”** No “AI-powered” copy. No labeling
   change. No model in this pass.
9. **Lead CSV import already stores per-row errors.** `import_lead_rows` returns
   `{created, pending_review, errors: [{row, detail}]}`. `process_lead_ingest` writes that dict
   to `LeadIngestJob.result` and marks the job `DONE`. `importLeadsCsv` already polls and
   returns that object. `LeadsPage` only toasts `created` or “still running.” Remaining gap is
   Action 15, UI only. There is no list endpoint — only `GET .../ingest-jobs/{id}/`.

---

## This pass — approved

### Action 1: Correct the two docs that are still wrong

**Why:** The issue register statuses for the IDs below are already Resolved. Rewriting them
would change nothing. Two surfaces still mislead a reader, plus one backlog item that now
contradicts the code.

**Do:**

1. `docs/reviews/18_COMPETITOR_ANALYSIS.md` Wave 22 paragraph (line 5). It still says seats are
   not enforced and the multi-GSTIN GSTR-3B bug (BB-000697) is open. Both are false. Correct
   those two clauses. Leave the GRN clause on that line alone unless a separate check shows GRN
   is also misstated. Leave older dated sections (Wave 21, Sprint 2, Sprint 6) as history.
2. `docs/reviews/MASTER_ISSUE_REGISTER.md` Status table, the Open ~64 row (line 184). Point it
   at the Wave 22 closure note (open in 695–758: 0) and the preamble tally (no open code
   defect). Do not hand-recount 758 issues.
3. Backlog YAML check, already done for the four files that mention seats or 3B:
   - `QOS-0041` — GSTR-1/3B portal-mapping help. Not the stamp bug. No edit.
   - `QOS-0042` — one-click live GSP filing. Still a real excluded/certification gap. No edit.
   - `QOS-0004` — CA filing from worksheets. Not the stamp bug. No edit.
   - `QOS-0071` — title “Multi-company / multi-branch GSTIN is not built,” lifecycle
     `accepted_wontfix`, rationale “one primary GSTIN per tenant.” That claim is now false:
     `CompanyGstin` CRUD and the settings UI exist. Closed 2026-09-28: lifecycle is `fixed`,
     the title no longer says the feature is unbuilt, and `guard_ref` points at
     `test_company_gstins_list_excludes_other_tenant`. The backlog markdown was regenerated.

No seat-enforcement claim turned up in those four YAML files.

**Test:** none. Every sentence you write needs a file:line citation.
**Size:** S.

### Action 2: Payroll and manufacturing capability notes

**Why:** `docs/reviews/01_EXECUTIVE_SUMMARY.md` “Reality vs claimed modules” (around line 54)
still says CRM, Payroll, Manufacturing, and Multi Company / Multi Branch are **Not implemented**.
CRM and branch GSTIN are shipped. Payroll and manufacturing are real preview modules. The
“don’t chase payroll / don’t chase manufacturing” line was written from the stale label.

**Scope:** backend only. Enough for a founder to choose “market” versus “keep gated as preview.”
Frontend scoping is a later follow-up if they invest. Writing the note does not commit either way.

**Do:**

1. Payroll: enumerate what `backend/payroll/` calculates (PF EPS/EPF split, admin, EDLI, ESI, PT,
   TDS old/new, loss-of-pay, payslips, employer GL posting) versus what code comments already
   put out of scope (Form 16, PF/ESI challan e-filing/ECR, leave and attendance, arrears,
   reimbursements, HRA / Chapter VI-A declarations). Note `ENABLE_PAYROLL` is a dark module.
2. Manufacturing: same treatment for `backend/manufacturing/` (BOM + work orders, not a full MES).
   Record the documented limitation on multiple ACTIVE BOMs (`manufacturing/models.py` Bom
   docstring). Note `ENABLE_MANUFACTURING` is a dark module.
3. Put a dated correction on the executive-summary reality table for those four rows, and add a
   short standalone note under `docs/roadmap/` for pricing/GTM. That file is a stacked historical
   review — update the table and add a dated section at the top. Do not rewrite every later
   “do not commercially launch” paragraph; those are wave history.
4. CRM row on that table: MVP implemented (leads, opportunities, pipeline, campaigns, referrals).
   Multi-branch row: `CompanyGstin` model + CRUD API + settings UI (add / activate / deactivate);
   set-primary and edit land in Action 4.

**Test:** n/a — audit, not a behavior change.
**Size:** S. Separate docs PR from the UI branch.

### Action 4: Finish branch GSTIN editing on the existing settings page

**Why:** `web/src/pages/settings/GstSettingsPage.tsx` (the Additional Branch GSTINs block) already
lists rows, creates them, and toggles `is_active`. Create hardcodes `is_primary: false`. There is
no edit of legal name / state, no set-primary, and the create `.then()` has no `.catch` — a
failed create fails silently.

**Do, on that same `Paper` and the same `company-gstins` query key. Do not add a new screen.**

1. Per row: “Set primary” → `updateCompanyGstin(id, { is_primary: true })`. The single-primary
   rule is already enforced in `accounts/models.py`.
2. Edit dialog reusing the same three fields as create (GSTIN, business name, state).
3. `.catch` on create, update, activate/deactivate, and set-primary, writing the same error
   state the rest of that page already uses.
4. Show which row is primary.
5. New strings via `t()` in `en` and `hi`. The surrounding block is still hardcoded English;
   do not i18n the whole page in this change.

**Test:** component or page test for set-primary, edit, and a failed create that surfaces the
error. One e2e only if the GST settings flow is already covered nearby; do not stand up a new
GSTR-1/3B fixture just to prove a button.
**Size:** S.

### Action 8: Show ineligible ITC on the existing IMS page

**Why:** `Gstr2bPage` already renders total, matched, unresolved, at-risk, and expiring from
`credit_at_risk`. The API also returns `ineligible_itc` (rejected or past the Section 16(4)
deadline). That number is “how much ITC was actually lost.”

**Do:** one `KpiStat` on the existing row, same money helper, label in `en` and `hi`. No second
dashboard. No backend change.

**Test:** extend the existing GSTR-2B page test if one asserts the KPI set; otherwise a render
test that a summary payload with `ineligible_itc` shows it.
**Size:** S.

### Action 9: Prefill the supplier phone on click-to-chat

**Why:** `Gstr2bPage` already opens `https://wa.me/?text=...` with the defect message and a copy
button. The URL has no phone. `supplier_defect_message` already returns `phone`.

**Do:** when `phone` is present, open `https://wa.me/<digits>?text=...`. When it is empty, keep
today’s text-only `wa.me` link and the copy button. Do not call the WhatsApp Cloud API. Template
approval, opt-in, and the 24-hour window stay on the excluded list until Meta approval exists.

**Test:** unit/component test that a phone becomes a `wa.me/<phone>` href and a missing phone
stays text-only.
**Size:** S.

### Action 10: Show why a referral reward was auto-rejected

**Why:** `ReferralsPage` shows code, leaderboard (`approvedTotal`), and reward status with
approve / reject / mark-paid. It never shows a reason. The leaderboard is enough conversion
signal — do not add an analytics panel.

**What the code actually stores:** `ReferralReward` has no reason column.
`ReferralRewardSerializer` fields are id, code, lead, opportunity, amount, status, `paid_at`,
`created_at`. A self-referral is `reward_status=REJECTED` plus an audit row
`referral_self_referral_blocked` (`crm/referrals.py`). A manual reject in
`ReferralRewardViewSet` also sets `REJECTED` and stores no reason. The UI cannot tell those
apart from today’s payload.

**Do:**

1. Add a nullable reason on `ReferralReward`, set only by the self-referral path to a stable
   code or short sentence (the audit description already has the sentence). Leave manual reject
   as status-only with an empty reason. Do not add a remark box to the decide endpoint in this
   pass.
2. Expose it on `ReferralRewardSerializer` (read-only). Regenerate the OpenAPI snapshot and
   `openapi-types.ts` in the same PR.
3. On the rewards list, when the reason is present, show it next to `REJECTED`.

**Test:** API test that a self-referral reward is REJECTED and the reason is in the list
payload; UI test that the reason renders. A normal pending reward has an empty reason.
**Size:** S.

### Action 15: Show the CSV import result the client already fetched

**Why:** `importLeadsCsv` polls `LeadIngestJob` and, on `DONE`, returns
`{created, pendingReview, errors}`. `LeadsPage` toasts only `created`, or “still running” when
the poll times out (`accepted: true`). Per-row `errors` are dropped. Partial success is already
the backend behavior: bad rows land in `result.errors`, other rows are created, job stays `DONE`.
A whole-job `FAILED` is only the worker-level exception path (`job.error`).

**Do, UI only. No model change. No new endpoint** (a past-jobs list would need one; out of scope).

1. Replace the success toast with created count, pending-review count, and the per-row error
   list (`row` + `detail`).
2. Keep the “still running” notice when the poll gives up. Do not pretend those rows failed.
3. Strings in `en` and `hi`.

**Test:** page test with a mocked import result that has one error row, asserting the bad row
is visible and the created count is too.
**Size:** S.

---

## Decided out of this pass

### Action 6: Shopify — documentation check only, not a build

`integrations/shopify.py` is “Shopify v1 webhook receiver. One store per company, HMAC before
any write.” `_apply_shopify_event` imports `orders/create` and `orders/updated` into a
`SalesOrder` and applies `inventory_levels/update`. If marketing or docs call this a full
catalog/order sync, correct that sentence where it lives. Do not extend the integration in
this pass. Dropped from the coding list.

### Action 11: Predictive dunning — no code change

Labeling is already honest (“Screen only,” “predicted days late” on the collections worklist).
Do not add a model. `requirements.txt` has no scikit-learn, xgboost, lightgbm, torch, or
tensorflow. A global model on all tenants’ payment history would cross the tenant boundary the
rest of the app isolates with RLS. The current score is a per-company median of the last five
paid invoices. A real model is a founder investment decision; default is no.

### Action 16: Seasonality-aware forecast — do not build

`inventory/forecast.py` `trailing_mean` stays the method. No second method, no flag, no backtest
in this pass.

---

## Closed after the answers review

These were recorded as blocked or unscoped, then implemented on 2026-09-28 with the
recommendations from that review. `GSP_LIVE_ENABLED` and `GSP_CERTIFIED` were not flipped.

### Action 3: NIC crypto for the custom-provider path

`core/services/nic_irp_crypto.py` implements NIC e-Invoice API 1.04. Invoice `Data` is
AES-256-ECB PKCS7. App key and password use RSA PKCS#1 v1.5. The SEK is the base64 `sek`
value already stored in the encrypted GSP credential blob. `wrap_irp_payload` uses that wrap
only when the provider is `custom`. A missing SEK raises `BusinessRuleError`. ClearTax and
MasterGST envelopes are unchanged. There is no sandbox call and no HMAC placeholder.
Round-trip coverage is `backend/tests/test_nic_irp_crypto.py`.

### Action 5: OCR review on the bill-upload screen

The screen is `web/src/pages/imports/BillUploadPage.tsx`. Per-line include (accept or leave
out) and field edit (correct) were already there. The missing piece was commit: confidence
under 0.70 now shows `billUpload.lowConfidence`, and commit stays disabled until
“I reviewed these lines” is checked. That checkbox is sent as `low_confidence_accepted`,
which `imports/services.py` already required before commit.

### Action 7: Manufacturing and payroll use the same gate as CRM

`BomsPage` and `EmployeesPage` wrap their body in `ModuleGate`. Nav visibility uses
`isManufacturingEnabled` and `isPayrollEnabled`. `resolveOptionalModuleFlag` stays false
until runtime flags have loaded, then follows the company grant. A Vite-on build without
that grant does not show the module. `web/src/config/optionalModuleFlags.test.ts` covers
that. `ROLLOUT_GRANTABLE_KEYS` were not linted.

### Action 12: Section 16(4) ITC-expiry digest

`reporting/ims.py` `send_itc_expiry_digest_for_company` emails the owner once when the set
of expiring invoice ids changes. It scans every period that still has unresolved rows.
Quiet hours (`in_quiet_hours` on the company dunning window) return `quiet` and do not
write a notification. Dedup compares the subject `ITC expiring — Section 16(4)` and the
first body line `ids:...`. The body says the date is from the books, not a filing opinion.
Celery beat `reporting-itc-expiry-digest` runs at 07:30. Covered by
`backend/tests/test_itc_digest_and_lead_reminders.py`.

### Action 13: Supplier score on the purchase-order picker

`GET /api/v1/reports/gstr2b/supplier-nudge/?supplier=` calls `supplier_po_nudge` for the
latest IMS period only, when a supplier is selected. A supplier with no rows in that period
returns `no_ims_history`. The purchase-order supplier field shows that sentence, or the
mismatch and rejection counts. It does not block the order.

### Action 14: Lead activity due dates

`LeadActivity.due_at` and `reminded_at` are on the existing model (`crm` migration 0014).
The lead activity form has a due field, and the timeline marks due and overdue.
`remind_due_lead_activities` sends one `Notification.Channel.IN_APP` when `due_at` is due
and `reminded_at` is empty, then stamps `reminded_at`. Quiet hours leave `reminded_at`
empty. Beat `crm-lead-activity-reminders` runs at minute 40. Opportunities were not given
the same fields.

---

## Excluded — not achievable by code alone

- **GSP live certification** (`GSP_CERTIFIED`) and WhatsApp Business API commercial approval.
  Action 3 wraps a custom payload when a SEK is already stored. It does not certify the
  adapter or call NIC. Action 9 stays click-to-chat.
- **CA Final Gate sign-off.** The underlying RCM/TCS/3B code fixes are already in. Engineering
  does not sign the gate. The ITC digest states a books date. It is not a filing opinion
  and it is not that sign-off.
- **Razorpay / Cashfree / PayU production KYC.**
- **Pricing, positioning, and GTM.** Includes whether to market payroll or manufacturing
  after Action 2’s notes. `QOS-0071` is `fixed`; the multi-GSTIN CRUD gap is closed.
- **External security review** of the NIC crypto path before any production flag flip.

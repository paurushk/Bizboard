# E2E UI Playwright Validation — Bizboard

Run date: 2026-08-26 · Tester: Cursor agent (Playwright MCP) · URL: `http://localhost` (Docker/nginx, title **Bizboard**) · git: `c613d46`  
Roles: New Owner `e2e3-owner-20260826@bizboard.test` (E2E3 Test Shop, Maharashtra, UNREGISTERED)  
Demo Owner / Staff: **not reached this session** (password entry into Playwright was gated; new-Owner session continued instead)  
Viewport: 1280×800 then 375×812  
Test data prefix: E2E3-  
Wizard flag observed: **off** (`/setup` bounced incomplete Owner to `/`; dashboard checklist used)

Screenshots (Playwright output dir): `C:\Users\Dell\.playwright-mcp\` (named `E2E3_S5_*` … `E2E3_S16_*`) plus earlier `e2e3\` folder from Stage 0–2.

## Summary

- Stages completed: **0–17** plus leftover new-doc / Insights / accounting / CSV-template smoke (demo Owner + staff RBAC + `/pay/:token` + CSV **commit** still skipped)  
- Findings: **9 high**, remaining medium/low (**39 logged**, E2E3-001 … 039)  
- Hindi toggle: nav translates; dashboard KPIs stay English (E2E3-034)  
- Global search: INV-00001 → `/sales/history/60`  
- Stage 17: **done** — see table below; UX-018 404 is fixed; login still has no link (E2E3-001); register empty submit still silent vs WC-010

## Fix status (2026-08-27)

All **E2E3-001 … E2E3-039** are **closed** in this workspace. Original “Actual” notes below are the audit snapshot from 2026-08-26, not current product behavior.

| IDs | Status | What shipped |
|---|---|---|
| 001, 003–006 | Fixed | Login `/forgot-password` link; register `noValidate` + helpers; password show/hide; “Account created” banner; register phone → company |
| 002 | Fixed | System font stack; Google Fonts request removed |
| 007–008 | Fixed | GSP `autocomplete` off/new-password; GST type bound to Unregistered |
| 009, 016, 021, 024–025 | Fixed | Godown labels; “Create item”; hide purchase MRP savings; “Add supplier”; Non-GST tax column 0% |
| 010, 011–013, 020, 026, 036 | Fixed | Non-GST default for UNREGISTERED on invoice/PO/SO/POS; catalog on open; cost-centers gated; single complete-error; POS voids failed drafts |
| 014, 017, 022–023 | Fixed | History spacers only when height > 0; adjustment “Select a product”; TRF number on draft; To-godown excludes From |
| 015, 018–019 | Fixed | Healthy-stock empty copy; godown filter string ids; company-wide low-stock unless per-godown reorder |
| 027–028, 032 | Fixed | Inventory report labels/names/2dp; transfer carries WAVG cost; valuation product + godown |
| 029, 031, 033–035, 037–039 | Fixed | Sales bill-upload copy; Paid when balance 0; company bank sync; dashboard i18n; `/new` → `?create=1`; split CSV/XLSX; blank template; Back to setup |
| 030 | Fixed | Owner-facing enablement on accounting/Insights; alias redirects; settings not gated as staff |

Do **not** recreate E2E3 data. Do **not** click GST Save or live Pay/SMS.

**Test data created this run (not cleaned up):**

| Record | Value |
|---|---|
| Owner | `e2e3-owner-20260826@bizboard.test` / company **E2E3 Test Shop** |
| Address | 12 MG Road, Camp, Pune 411001 · UPI `e2e3shop@oksbi` · HDFC `123456789012` |
| Product | **E2E3-Widget** SKU `E2E3-WGT-001` barcode `BB002150923456` · opening 100 PCS @ default godown |
| Godown 2 | **E2E3-Godown-2** code `E2E3-G2` |
| Transfer | **TRF-00001** COMPLETED · 10 PCS Default → E2E3-Godown-2 |
| Stock count | Session **#1** Default Warehouse **POSTED** counted 94 (zero variance) |
| Supplier | **E2E3-Test Supplier** Maharashtra · `e2e3-supplier@bizboard.test` · 9876543210 |
| Purchase | **PUR-00001** (id 32) Completed Non-GST ₹600.00 · qty 10 @ ₹60 |
| Customer | Walk-in Customer (Cash Customer shortcut) |
| Invoice | **INV-00001** (id 60) Completed Non-GST ₹100.00 · **Balance ₹0.00** after receipt |
| Receipt | **RCT-00001** CASH ₹100 allocated to INV-00001 (`POST /payments/receipts/` + `allocations/` 201) |
| POS leftover | Draft **sales invoice id 61** created then Complete **400** (GST on UNREGISTERED) |
| Stock now | All godowns **114** · Default **104** · E2E3-Godown-2 **10** (unchanged this session) |

Port `5173` served **Option Copilot**, not Bizboard — correctly unused.

## Coverage ledger

| Route | Result | Notes |
|---|---|---|
| `/login` | Partial | Validation OK; no Forgot-password link; 401 refresh in console |
| `/register` | Partial | Real signup worked → `?registered=1`; empty submit showed no errors |
| `/forgot-password` | Pass | Empty submit alert; **not linked from login** |
| `/reset-password` | Partial | Missing-token error only after submit |
| `/invite` | Pass | Missing-token UX; Activate disabled |
| `/pay/:token` | Blocked | Playwright policy blocked garbage-token URL |
| `/sales/new` (logged out) | Pass | `/login?next=%2Fsales%2Fnew` |
| `/some-nonexistent-route` | Pass | 404 + Back to Dashboard |
| `/` | Pass | Checklist 0/4 → after first bill, invite CTA; KPIs ₹100 |
| `/setup` | Pass (flag off) | Incomplete Owner redirected to `/` |
| `/settings/company` | Pass | Save toast; GSTIN banner |
| `/settings/gst` | Fail (UX/security) | GSP fields autofilled with login secrets; type empty |
| `/inventory/products` | Pass | Create Goods + opening stock 100 |
| `/inventory/stock` | Pass | 100 then 99 after sale |
| `/inventory/adjustments` | Pass with defect | Empty Save: E2E3-017; +5 saved; stock 99→104 |
| `/inventory/warehouses` | Pass | E2E3-Godown-2 created; mixed Godown/Warehouse copy (E2E3-009) |
| `/inventory/transfers` | Pass | TRF-00001 COMPLETED; draft number “—” until complete |
| `/inventory/stock` (filter) | Fail | Godown filter Default Warehouse → empty (E2E3-018); Show lots 94/10 then 104/10 |
| `/inventory/low-stock` | Fail | Available **10** / Below reorder while company on-hand 104 then 114 (E2E3-019) |
| `/inventory/expiry-alerts` | Pass | Empty 30-day horizon; APIs 200 |
| `/inventory/serials` | Pass | Empty (item not serial-tracked) |
| `/inventory/stock-counts` | Pass | Counted 94, POSTED, zero variance |
| `/purchases/suppliers` | Pass | E2E3-Test Supplier 201; empty CTA “Add Suppliers” |
| `/purchases/new` | Partial | GST default; Non-GST Complete PUR-00001 ₹600; cost-centers 400 |
| `/purchases/history` | Pass | PUR-00001 Completed; toast “10 items added to stock” |
| `/pos` | Fail | GST ₹118; Cash Complete **400**; no Non-GST control (E2E3-026) |
| `/reports/sales` | Pass | INV-00001 ₹100 |
| `/reports/purchases` | Pass | PUR-00001 ₹600 |
| `/reports/inventory` | Partial | Per-godown 104+10; raw camelCase headers; stockValue noise (E2E3-027/028) |
| `/sales/receipts` | Pass | RCT-00001 ₹100 allocated; list + toast |
| `/sales/history/60` | Pass | Balance ₹0.00; status still **Completed** not Paid |
| `/` after receipt | Partial | Outstanding ₹0, cash ₹100, payables ₹600; Low stock **1** / available **10** (E2E3-019); alerts now low-stock not empty-stock |
| `/sales/quotations` `/sales/orders` `/sales/delivery-challans` `/sales/credit-notes` `/sales/debit-notes` `/sales/recurring` | Pass | Empty states; APIs 200 |
| `/sales/quotations/new` | Fail | SPA **404** (E2E3-035); list **New quotation** opens a dialog instead |
| `/sales/orders/new` | Partial | Full form; **Invoice type GST** default on UNREGISTERED (E2E3-020) |
| `/sales/delivery-challans/new` | Pass | Full form; no GST type control; Save disabled until customer/lines |
| `/sales/credit-notes/new` `/sales/debit-notes/new` | Pass | Full forms; Source invoice + reason; Save disabled until filled |
| `/sales/returns` | Pass | Empty; **New sales return** opens dialog (original invoice + reason) |
| `/sales/returns/new` | Fail | SPA **404** (E2E3-035); create is dialog-only |
| `/sales/customers` | Partial | Heading + Add; still Loading… at 1.2s |
| `/sales/bill-upload` | Partial | Upload UI; copy says **supplier** invoice (E2E3-029) |
| `/sales/upload` | Pass | Redirects to `/sales/bill-upload` |
| `/reports/cash-book` | Pass | RCT-00001 ₹100 in; closing ₹100 |
| `/reports/customer-ledger` | Pass | Walk-in: INV-00001 + RCT-00001; outstanding ₹0.00 |
| `/reports/supplier-ledger` | Pass | E2E3-Test Supplier PUR-00001 outstanding ₹600 |
| `/reports/gstr1` | Pass | Loads; B2B/B2CS 0; outward ₹0 (Non-GST sale excluded) |
| `/reports/profit-and-loss` `/reports/trial-balance` `/reports/profit-loss` | Fail | Owner **limited access** gate (E2E3-030); alias `/profit-loss` does **not** rewrite URL |
| `/accounting/accounts` `/insights` | Fail | Same Owner gate (E2E3-030) |
| `/settings/users` | Pass | E2E3 Owner row; Invite **not** submitted |
| `/settings/units` | Pass | PCS present |
| `/settings/import` | Partial | Template **downloaded** (CSV+XLSX, E2E3-037/038); **not** uploaded/committed |
| `/settings/import?kind=PRODUCTS&return=/setup?step=catalog` | Partial | Kind=Products honored; **no** back-to-setup control (E2E3-039); wizard flag off |
| `/settings/billing` | Pass | Plan page; **did not** click Pay |
| `/settings/templates` | Pass | GST Tax Invoice (A4) template |
| `/settings/items` | Pass | Item Settings heading |
| `/settings/backup` | Pass | Export buttons; **did not** download |
| `/settings/bank-accounts` | Fail | Empty despite HDFC on company (E2E3-033) |
| `/settings/payment-gateway` | Pass | Razorpay UI; **did not** save secrets |
| `/settings/price-lists` | Pass | Empty |
| `/settings/accounting` `/settings/ai` | Fail | Owner limited-access gate (E2E3-030) |
| `/settings/tally` | Pass | Migration aid; **did not** upload |
| `/reports/gstr3b` `/reports/gstr2b` `/reports/gstr9` `/reports/gst-health` | Pass | ₹0 GST (Non-GST books); 2B empty; health info 1 |
| `/reports/stock-valuation` | Partial | 104 @ ₹57.39 = ₹5,968.85; 10 @ ₹0; Product **—** (E2E3-032, 028) |
| `/reports/tds-tcs` | Pass | Page loads; ENABLE_TDS copy; **did not** download |
| `/reports/statutory-events` | Pass | Empty table |
| `/reports/books-health` `/reports/balance-sheet` | Fail | Owner gate (E2E3-030) |
| `/payments/statements` | Pass | Empty |
| `/payments/reconciliation` | Pass | Counters 0; empty |
| `/payments/recon` | Pass | Redirects to reconciliation |
| `/purchases/bill-upload` `/purchases/upload` | Pass | Supplier copy OK; upload alias redirects |
| `/inventory/expiry` `/inventory/count` | Pass | Redirect to expiry-alerts / stock-counts |
| `/manufacturing/work-orders` `/payroll/pay-runs` `/crm/opportunities` | Pass | Empty |
| `/insights/alerts` `/insights/cashflow` `/insights/assistant` `/accounting/chart-of-accounts` | Fail | Owner gate (E2E3-030); alias URL **not** rewritten |
| `/accounting/periods` `/accounting/fixed-assets` `/accounting/bank-reconciliation` `/accounting/bank-recon` | Fail | Same Owner gate; `/bank-recon` **does not** rewrite URL |
| `/purchases/payments` | Pass | Empty Payment Out |
| `/payments/links` | Pass | Empty |
| `/manufacturing` `/crm` `/payroll` | Pass | Redirect to boms / leads / employees |
| `/crm/leads` `/manufacturing/boms` `/payroll/employees` | Pass | Empty states |
| `/purchases/orders` `/purchases/returns` `/purchases/credit-notes` `/purchases/debit-notes` | Pass | Empty lists |
| `/purchases/orders/new` | Partial | Full form; **Purchase type GST** default (E2E3-036) |
| `/purchases/credit-notes/new` `/purchases/debit-notes/new` | Pass | Full forms load; Save disabled until filled |
| `/purchases/returns/new` | Fail | SPA **404** (E2E3-035); list has New purchase return |
| `/sales/history/60/edit` `/purchases/history/32/edit` | Pass | Completed-doc amend banner; Non-GST preserved; **did not Save**; cost-centers 400 (E2E3-012) |
| `/accounting/journals` `/accounting/cost-centers` `/insights/health` | Fail | Owner gate (E2E3-030); UX-005 500 **not** reproduced |
| Header search | Pass | `INV-00001` → `/sales/history/60` |
| Hindi toggle | Partial | Nav Hindi; main KPIs English (E2E3-034) |
| Stage 17 | Pass | Cross-check table written |
| demo Owner / staff / `/pay/:token` / CSV execute | Not reached | Password entry gated; pay URL policy-blocked earlier |

## Golden chain evidence

### Chain A — Onboarding

| Step | Result | Evidence |
|---|---|---|
| A0 Register | Pass | Unique email; **not** auto-login; landed `/login?registered=1&email=…` |
| A1 Login banner | Pass | “Your account request was received. Sign in to continue.” (copy issue E2E3-005) |
| A2 Landing | Pass | Wizard **off**; checklist 0/4; `/setup` bounce |
| A3 Tax | Partial | Unregistered default; GST page empty type + autofill (did **not** Save GST) |
| A4 Shop | Pass | Address/city/PIN saved |
| A5 Payments | Pass | UPI + bank saved on same company form |
| A6 Catalog + opening | Pass | E2E3-Widget; `POST /products/` 201 + `POST /opening-stock/` 201; stock 100 |
| A7 First bill | Partial | GST Complete **400** then Non-GST Complete **200** INV-00001 ₹100; stock 99 |
| A8 Checklist residual | Pass | Checklist gone; “Invite staff” banner |

### Chain B — Product / opening stock / stock

| Item/godown | Opening qty | After ops | Downstream proof |
|---|---|---|---|
| E2E3-Widget / Default Warehouse | 100 | 104 after +5 adj then 94 after TRF then **104** after PUR +10 | Current Stock lots; stock count System 94.000 |
| E2E3-Widget / E2E3-Godown-2 | 0 | **10** after TRF-00001 | Show lots; inventory report warehouse id 19 |
| All godowns | 100 | 99 → 104 → 114 | Current Stock On Hand |
| Adjustments | — | +5 Physical Count Discrepancy | Toast “Stock adjustment recorded successfully” |
| Transfers | — | TRF-00001 COMPLETED 10 PCS | `POST …/transfers/2/complete/` 200 |
| Stock count | — | #1 POSTED counted 94 | Zero variance; stock unchanged |
| Import CSV | — | Template downloaded only (CSV+XLSX). **Not** uploaded (sample rows include opening_stock) | E2E3-037, 038 |

### Chain C — Purchase / sale / cash

| Step | Doc/ID | Amount / qty | Downstream proof |
|---|---|---|---|
| Sale | INV-00001 | ₹100 / qty 1 | Sales register; after receipt dashboard outstanding ₹0 |
| Receipt | RCT-00001 | ₹100 CASH | Allocated 100; invoice balance ₹0; cash book in ₹100; customer ledger ₹0 |
| Purchase | PUR-00001 | ₹600 / qty 10 @ ₹60 | Stock 104→114; supplier ledger outstanding ₹600 |
| POS cash | invoice 61 draft | ₹118 GST attempted | Complete **400**; leftover draft |
| P&L / TB / COA / Insights | — | Gated | Owner sees staff “limited access” (E2E3-030) |

## Findings

### E2E3-001 — Login has no Forgot-password link

- **Class:** Defect
- **Module/Page:** `/login`
- **Severity:** High
- **Category:** Broken flow / Usability
- **Steps to reproduce:**
  1. Open `/login`.
  2. Read footer copy: “Forgot password? Ask your company owner to send a new invite.”
  3. Open `/forgot-password` directly — a working Reset Password form exists.
- **Expected:** Login offers a control that opens `/forgot-password`. Reset-password error copy says “Request a new link from the login page.”
- **Actual:** No link. Owner-only invite copy. `/forgot-password` is orphaned from the login journey.
- **Impact:** Shopkeepers cannot self-serve password reset from the obvious place.
- **Suggested fix:** Link “Forgot password?” to `/forgot-password`. Keep invite copy as secondary for staff.
- **Evidence:** `E2E3_S1_login_blank_submit.png`, `E2E3_S1_forgot_password.png`
- **Viewport / role:** desktop, anonymous
- **Cross-check:** **partial duplicate of WC-009** (no forgot-password). **UX-018** claimed `/forgot-password` 404 **fixed** — page now loads (not a 404 regression). Remaining gap is the missing login **link**.

### E2E3-002 — Google Fonts fail with ERR_INSUFFICIENT_RESOURCES

- **Class:** Defect
- **Module/Page:** `/login` (and later pages)
- **Severity:** Low
- **Category:** Performance / API/console
- **Steps to reproduce:** Load `/login`. Read console.
- **Expected:** Fonts load or fail silently with a local fallback and no error noise.
- **Actual:** Console ERROR loading `fonts.googleapis.com` (`DM Sans` / `IBM Plex Sans`).
- **Impact:** Possible FOUT; console pollution. App still usable.
- **Suggested fix:** Self-host fonts or treat as optional; don’t block render.
- **Evidence:** console error on first login load
- **Viewport / role:** desktop, anonymous

### E2E3-003 — Empty register submit shows no validation

- **Class:** Defect
- **Module/Page:** `/register`
- **Severity:** High
- **Category:** Validation
- **Steps to reproduce:**
  1. Open `/register`.
  2. Click **Create account** with all required fields empty.
- **Expected:** Inline errors on Company name, Email, Password, State (same pattern as login).
- **Actual:** No `[invalid]` helpers, no alert. Form stays silent. Company name merely focused.
- **Impact:** First-time Owner thinks the button is dead.
- **Suggested fix:** Same required-field helpers as login; disable or explain Save until valid.
- **Evidence:** `E2E3_S1_register_blank_submit.png`
- **Viewport / role:** desktop, anonymous
- **Cross-check:** **duplicate of WC-010** (still open). This run High vs WC Medium. Not a claimed-fixed regression.

### E2E3-004 — No show/hide password on login or register

- **Class:** Improvement
- **Module/Page:** `/login`, `/register`
- **Severity:** Low
- **Category:** Usability / Accessibility
- **Expected:** Visibility toggle on password fields (common on billing apps).
- **Actual:** Password textboxes only.
- **Suggested fix:** Add toggle with accessible name.
- **Evidence:** snapshots of login/register
- **Viewport / role:** desktop

### E2E3-005 — Register success copy sounds like a pending request

- **Class:** Improvement
- **Module/Page:** `/login?registered=1`
- **Severity:** Medium
- **Category:** Copy
- **Expected:** “Account created. Sign in to continue.”
- **Actual:** “Your account request was received. Sign in to continue.”
- **Impact:** Sounds like approval is required; Owner may wait instead of signing in.
- **Suggested fix:** Say the account is ready. Keep anti-enumeration (no “email already exists”).
- **Evidence:** `E2E3_S2_login_registered_banner.png`

### E2E3-006 — Register mobile number is not copied to company Phone

- **Class:** Improvement
- **Module/Page:** `/register` → `/settings/company`
- **Severity:** Low
- **Category:** Usability
- **Steps to reproduce:** Register with mobile `9876543210`. Open Company settings. Phone is blank.
- **Expected:** Company phone prefilled from register mobile.
- **Actual:** Must re-type.
- **Suggested fix:** Map register phone → company.phone on create.
- **Evidence:** company form snapshot after register

### E2E3-007 — GSP Client Secret / Portal Username autofilled from login

- **Class:** Bug / Defect
- **Module/Page:** `/settings/gst`
- **Severity:** High
- **Category:** Validation / Usability (credential mix-up)
- **Steps to reproduce:**
  1. Sign in as new Owner.
  2. Open GST settings.
  3. Scroll to GSP Portal Credentials.
- **Expected:** Empty write-only secret fields (`autocomplete=new-password` / `off`).
- **Actual:** **Client Secret** filled with the **login password**; **Portal Username** filled with the Owner email. One Save click would persist the login password as a GSP secret.
- **Impact:** Accidental credential overwrite; password visible in a government-integration field.
- **Suggested fix:** `autocomplete="off"` / `new-password` on Client Secret, Client ID, Portal Username. Do not use `type=password` that browsers bind to the site login.
- **Evidence:** `E2E3_S2_gst_settings_autofill.png` (contains live password — treat as sensitive)
- **Viewport / role:** desktop, New Owner
- **Note:** GST **Save was not clicked** in this run.

### E2E3-008 — GST Registration Type combobox looks empty

- **Class:** Defect
- **Module/Page:** `/settings/gst`
- **Severity:** Medium
- **Category:** Usability
- **Expected:** Shows Unregistered (register default) as selected label.
- **Actual:** Combobox has no visible selected text while State shows Maharashtra.
- **Impact:** Owner cannot tell GST type without opening the list.
- **Suggested fix:** Bind display value to `registration_type`.
- **Evidence:** GST settings snapshot

### E2E3-009 — Godown vs Warehouse mixed labels

- **Class:** Improvement
- **Module/Page:** Inventory nav vs item/invoice/adjustment forms
- **Severity:** Medium
- **Category:** Copy
- **Expected:** One shopkeeper word. Nav already says **Godowns**.
- **Actual:** Item Stock tab: Godown + “Default **Warehouse**”. Invoice and Stock Adjustment: **Warehouse**.
- **Impact:** Confusion for Indian traders who say godown.
- **Suggested fix:** Label all location pickers Godown; keep API name Warehouse.
- **Evidence:** `E2E3_S2_item_stock_tab.png`, invoice form, `/inventory/adjustments`

### E2E3-010 — Unregistered Owner’s new invoice defaults to GST and Complete fails

- **Class:** Defect
- **Module/Page:** `/sales/new`
- **Severity:** High
- **Category:** Broken flow / Data
- **Steps to reproduce:**
  1. New UNREGISTERED company (checklist step 4: “Create a non-GST Bill of Supply”).
  2. New Invoice → Cash Customer → add E2E3-Widget.
  3. Invoice type is **GST Invoice**; tax ₹18 CGST+SGST; total ₹118.
  4. Save & Complete.
- **Expected:** Default **Non-GST / Bill of Supply**; or block GST type before fill; Complete succeeds first try.
- **Actual:** Complete `POST …/invoices/60/complete/` **400**: “Unregistered companies cannot issue GST/TAX invoices…”. Draft saved. Duplicate alerts on history. User must Edit → **Non-GST Invoice** → Complete again (then ₹100, 200 OK, INV-00001).
- **Impact:** First-bill onboarding fails on the default path. Checklist copy does not match the form.
- **Suggested fix:** Default invoice type from `registration_type`; hide or disable GST/TAX for UNREGISTERED/COMPOSITION; surface the gate **before** Complete.
- **Evidence:** `E2E3_S2_invoice_with_line.png`, `E2E3_S2_complete_gst_blocked.png`, `E2E3_S2_inv00001_completed.png`
- **Viewport / role:** desktop, New Owner

### E2E3-011 — Invoice item dropdown says “No options” until the user types

- **Class:** Defect
- **Module/Page:** `/sales/new` item combobox
- **Severity:** Medium
- **Category:** Usability
- **Steps to reproduce:** Open **Open** on “+ Add Item” with one product in catalog. Listbox: **No options**. Type `E2E3` → option appears with avail 100.
- **Expected:** Show recent/all products on open, or placeholder “Type to search” instead of “No options”.
- **Actual:** Looks like an empty catalog.
- **Suggested fix:** Initial fetch of products on open; don’t use empty-state “No options” when the catalog is non-empty.
- **Evidence:** snapshot after Open click

### E2E3-012 — cost-centers API 400 on sales invoice (no user message)

- **Class:** Bug
- **Module/Page:** `/sales/new`, `/sales/history/60/edit`
- **Severity:** Medium
- **Category:** API/console
- **Expected:** Don’t call accounting cost-centers when accounting is off; or 204/empty list.
- **Actual:** Repeated `GET /api/v1/accounting/cost-centers/` **400**. No on-screen error. Also `ERR_INSUFFICIENT_RESOURCES` on that URL during edit.
- **Impact:** Console noise; possible extra latency. Invoice still usable.
- **Suggested fix:** Gate the request on `accountingEnabled`.
- **Evidence:** network list on `/sales/new`

### E2E3-013 — Duplicate Complete-failure alerts on Sales History

- **Class:** Defect
- **Module/Page:** `/sales/history`
- **Severity:** Medium
- **Category:** Usability
- **Expected:** One error toast.
- **Actual:** Two stacked alerts with the same unregistered-GST message (one prefixed “Draft Draft #60 saved — complete failed:”).
- **Suggested fix:** Single error channel; fix “Draft Draft” double word.
- **Evidence:** `E2E3_S2_complete_gst_blocked.png`

### E2E3-014 — Empty extra rows in Sales History table

- **Class:** Improvement
- **Module/Page:** `/sales/history`
- **Severity:** Low
- **Category:** Usability
- **Actual:** Header row + empty `row` + data row + empty `row` in the accessibility tree.
- **Suggested fix:** Don’t render spacer rows as table rows.
- **Evidence:** history snapshots

### E2E3-015 — Dashboard “stock empty” copy after opening stock and a sale

- **Class:** Bug
- **Module/Page:** `/` Business alerts
- **Severity:** High
- **Category:** Data / Copy
- **Steps to reproduce:** Create product with opening 100, complete a sale (stock 99). Open dashboard.
- **Expected:** Alerts reflect real stock / invoices, or hide the empty-stock card.
- **Actual:** KPIs show ₹100 sales and INV-00001, but Business alerts: **“Nothing here yet” / “Stock balances will appear after opening stock or purchases.”**
- **Impact:** Owner thinks stock was not posted.
- **Suggested fix:** Drive that card from inventory balances / movements, not a stale empty flag.
- **Evidence:** `E2E3_S2_dashboard_after_first_bill.png`
- **Viewport / role:** desktop and mobile, New Owner

### E2E3-016 — Create item dialog title is “Create Products”

- **Class:** Improvement
- **Module/Page:** `/inventory/products` dialog
- **Severity:** Low
- **Category:** Copy
- **Expected:** “Create item” / “Create product”.
- **Actual:** “Create Products”.
- **Evidence:** item dialog snapshot

### E2E3-017 — Stock adjustment Save with no product: no error text

- **Class:** Defect
- **Module/Page:** `/inventory/adjustments`
- **Severity:** Medium
- **Category:** Validation
- **Steps to reproduce:** Leave Products empty, click Save.
- **Expected:** “Select a product” helper.
- **Actual:** Combobox focused; no alert/helper. Easy to think Save is broken.
- **Evidence:** adjustment snapshot after Save
- **Viewport / role:** desktop, New Owner

### E2E3-018 — Current Stock godown filter shows empty table

- **Class:** Defect
- **Module/Page:** `/inventory/stock`
- **Severity:** High
- **Category:** Data / Broken filter
- **Steps to reproduce:**
  1. With E2E3-Widget on Default Warehouse (94 then 104) and E2E3-Godown-2 (10), open Current Stock — All godowns shows 104 then 114.
  2. Open Godowns filter and choose **Default Warehouse**.
- **Expected:** Row for E2E3-Widget with that godown’s on-hand (94 / 104).
- **Actual:** Table gone; **“No items found.”** Show lots on All godowns still lists Default Warehouse 94/104. Network still only showed `GET /inventory/balances/` without a warehouse query change that the UI reflected.
- **Impact:** Owner cannot view stock by godown; looks like transfer/purchase vanished.
- **Suggested fix:** Filter balances by warehouse id; keep All-godowns total; never replace a non-empty lot list with an empty state when lots exist.
- **Evidence:** `E2E3_S5_stock_default_filter.png`, `E2E3_S5_stock_show_lots.png`
- **Viewport / role:** desktop, New Owner
- **Cross-check:** new

### E2E3-019 — Low Stock uses one godown qty (10) not company on-hand (104+)

- **Class:** Defect
- **Module/Page:** `/inventory/low-stock`
- **Severity:** High
- **Category:** Data
- **Steps to reproduce:**
  1. After transfer, Current Stock All godowns = 104 (Default 94 + G2 10); reorder level 10.
  2. Open Low Stock.
- **Expected:** Available ≈ 104 (or clearly labeled per-godown with godown name). Status at reorder should be “At reorder” not necessarily “Below”.
- **Actual:** Available **10**, Reorder **10**, Status **Below reorder**. Matches E2E3-Godown-2 qty only. After purchase, company 114 — not rechecked.
- **Impact:** False “order now” while default godown still has ~94–104 PCS.
- **Suggested fix:** Sum available across godowns unless a per-godown reorder rule exists; label godown if row is per-location.
- **Evidence:** `E2E3_S5_low_stock.png`
- **Viewport / role:** desktop, New Owner

### E2E3-020 — Unregistered purchase bill defaults to GST

- **Class:** Defect
- **Module/Page:** `/purchases/new`
- **Severity:** Medium
- **Category:** Broken flow / GST
- **Steps to reproduce:** New Owner UNREGISTERED. Open New Purchase. Purchase type is **GST**.
- **Expected:** Default Non-GST / Bill of Supply (same as sales E2E3-010).
- **Actual:** GST selected. Complete was not attempted on GST (sales already 400). Switching to Non-GST then Complete **200** PUR-00001.
- **Impact:** Same foot-gun as first sales invoice.
- **Suggested fix:** Default purchase type from company GST registration.
- **Evidence:** purchase form snapshot Purchase type GST
- **Viewport / role:** desktop, New Owner

### E2E3-021 — Purchase line shows “50% vs MRP” savings copy

- **Class:** Improvement
- **Module/Page:** `/purchases/new` line table
- **Severity:** Low
- **Category:** Copy
- **Expected:** Purchase lines show cost vs last purchase / MRP without “savings” sales language.
- **Actual:** MRP ₹120.00 with **“50% vs MRP”** while PRICE/ITEM is ₹60.
- **Impact:** Confusing on a payable bill.
- **Suggested fix:** Hide savings chip on purchase; show last-cost if needed.
- **Evidence:** purchase line snapshot
- **Viewport / role:** desktop, New Owner

### E2E3-022 — Draft stock transfer has no document number

- **Class:** Improvement
- **Module/Page:** `/inventory/transfers`
- **Severity:** Low
- **Category:** UX
- **Expected:** Draft shows a reserved number or “Draft”.
- **Actual:** Number column **—** until Complete assigns **TRF-00001**.
- **Impact:** Hard to talk about the draft in a shop with several pending transfers.
- **Suggested fix:** Assign TRF number on create, or label “Draft”.
- **Evidence:** transfers table after Create draft
- **Viewport / role:** desktop, New Owner

### E2E3-023 — To-godown list includes the From godown

- **Class:** Improvement
- **Module/Page:** `/inventory/transfers` New transfer dialog
- **Severity:** Low
- **Category:** Validation
- **Expected:** Destination excludes source, or Save errors “same godown”.
- **Actual:** Both Default Warehouse and E2E3-Godown-2 listed under To after From was Default. Same-godown Complete **not** attempted.
- **Impact:** Easy to post a no-op / invalid transfer.
- **Suggested fix:** Filter options; block complete when from === to.
- **Evidence:** To godown listbox snapshot
- **Viewport / role:** desktop, New Owner

### E2E3-024 — Empty suppliers CTA says “Add Suppliers”

- **Class:** Improvement
- **Module/Page:** `/purchases/suppliers`
- **Severity:** Low
- **Category:** Copy
- **Expected:** “Add supplier”.
- **Actual:** Header **Add** plus empty-state **Add Suppliers**.
- **Evidence:** suppliers empty snapshot
- **Viewport / role:** desktop, New Owner

### E2E3-025 — Non-GST purchase still shows 18% tax column

- **Class:** Improvement
- **Module/Page:** `/purchases/new`
- **Severity:** Low
- **Category:** Copy / GST
- **Expected:** Non-GST lines hide GST rate or show “Non-GST / 0%”.
- **Actual:** TAX column **18% (₹0.00)** on a Non-GST bill; total tax ₹0.00.
- **Impact:** Looks like GST was applied then zeroed.
- **Evidence:** purchase form after Non-GST + line
- **Viewport / role:** desktop, New Owner

### E2E3-026 — POS charges GST and Cash Complete 400 for unregistered company

- **Class:** Defect
- **Module/Page:** `/pos`
- **Severity:** High
- **Category:** Broken flow / GST
- **Steps to reproduce:**
  1. UNREGISTERED company. Open POS (Walk-in customer).
  2. Add E2E3-Widget. Tender shows Tax ₹18.00, Total **₹118.00**. No bill-type control.
  3. Click **Cash — ₹118.00**.
- **Expected:** POS uses Non-GST (₹100) for unregistered, or a visible Non-GST toggle before tender.
- **Actual:** `POST /sales/invoices/` **201** (draft **id 61**), `POST …/61/complete/` **400**. Toast: “Unregistered companies cannot issue GST/TAX invoices… Use a non-GST bill type.” POS has **no** Non-GST control. Cart remains; leftover draft.
- **Impact:** Counter billing is unusable for this new shop; draft invoices accumulate.
- **Suggested fix:** Default POS `invoice_type` from GST registration; add type toggle; don’t create a draft until Complete can succeed; delete/void failed drafts.
- **Evidence:** `E2E3_S8_pos_gst_unregistered.png`; console 400 on `/sales/invoices/61/complete/`
- **Viewport / role:** desktop, New Owner

### E2E3-027 — Inventory report uses raw field names and warehouse ids

- **Class:** Defect
- **Module/Page:** `/reports/inventory`
- **Severity:** Medium
- **Category:** UX / Copy
- **Expected:** Headers like Godown, On hand, Reserved, Reorder, Stock value; godown **names**.
- **Actual:** Columns `reserved`, `reorderLevel`, `stockValue`. Godown shown as **18** / **19**. Stock value `5968.846153846154`.
- **Impact:** Unshippable as an owner-facing report.
- **Suggested fix:** Human labels, godown name, money rounded to 2 dp.
- **Evidence:** inventory report snapshot after PUR-00001
- **Viewport / role:** desktop, New Owner

### E2E3-028 — Transferred qty shows stock value 0 on inventory report

- **Class:** Defect
- **Module/Page:** `/reports/inventory`
- **Severity:** Medium
- **Category:** Data / Valuation
- **Steps to reproduce:** Transfer 10 PCS to E2E3-Godown-2. Open Inventory report.
- **Expected:** Those 10 units keep cost (FIFO/weighted) so value > 0.
- **Actual:** Warehouse 19 row: on hand **10**, stockValue **0**. Default warehouse 18: 104 with ~₹5968.85.
- **Impact:** Valuation understated after transfers; godown P&L/stock value wrong.
- **Suggested fix:** Carry cost on TRANSFER_IN lots; include in report.
- **Evidence:** inventory report two E2E3-Widget rows
- **Viewport / role:** desktop, New Owner

### E2E3-029 — Sales bill-upload copy talks about supplier invoices

- **Class:** Defect
- **Module/Page:** `/sales/bill-upload`
- **Severity:** Medium
- **Category:** Copy
- **Expected:** Sales upload copy refers to **customer/sales** bills or generic “document”.
- **Actual:** “Automatic Bill Scanner: Upload a photo or PDF of your **supplier invoice**.”
- **Impact:** Owner thinks they are on purchase upload.
- **Suggested fix:** Sales vs purchase specific copy.
- **Evidence:** bill-upload snapshot; `/sales/upload` correctly redirects here
- **Viewport / role:** desktop, New Owner

### E2E3-030 — Owner is shown a staff “limited access” gate on accounting and Insights

- **Class:** Defect
- **Module/Page:** `/reports/profit-and-loss`, `/reports/trial-balance`, `/reports/profit-loss`, `/reports/balance-sheet`, `/reports/books-health`, `/accounting/accounts`, `/accounting/chart-of-accounts`, `/accounting/journals`, `/accounting/cost-centers`, `/accounting/periods`, `/accounting/fixed-assets`, `/accounting/bank-reconciliation`, `/accounting/bank-recon`, `/settings/accounting`, `/settings/ai`, `/insights`, `/insights/alerts`, `/insights/health`, `/insights/cashflow`, `/insights/assistant`
- **Severity:** High
- **Category:** Broken flow / RBAC copy
- **Steps to reproduce:** Logged in as **OWNER** (badge OWNER, email e2e3-owner-…). Open P&L, trial balance, chart of accounts, or Insights.
- **Expected:** Owner sees the report, or a clear “enable accounting / Insights for this company” CTA addressed to **you**.
- **Actual:** “Welcome to Bizboard” / “Your account has **limited access**. … **ask them** to update your permissions.” Sidebar still shows Reports. GSTR-1, cash book, sales/purchase registers **do** load. No P&L API call (only memberships + billing). Aliases `/reports/profit-loss` and `/accounting/chart-of-accounts` **do not** rewrite. **`/settings/accounting` is also gated**, so the Owner cannot turn books on from Settings.
- **Impact:** New Owner cannot see P&L after first sale/purchase; copy tells them they are not the owner.
- **Suggested fix:** Grant Owner accounting/insights by default, or gate with Owner-facing enablement. Fix alias redirect. Never tell an Owner to “ask your owner”.
- **Evidence:** `E2E3_S11_pnl_gate.png`
- **Viewport / role:** desktop, New Owner

### E2E3-031 — Paid invoice stays “Completed” with no Paid status

- **Class:** Improvement
- **Module/Page:** `/sales/history/60`, dashboard Recent invoices
- **Severity:** Low
- **Category:** Copy / Data
- **Expected:** After RCT-00001 full allocation, status **Paid** (or Completed + Paid chip).
- **Actual:** Status **Completed**; payment summary Balance **₹0.00**. Dashboard outstanding correctly ₹0.
- **Impact:** Hard to see which bills are collected from the list.
- **Suggested fix:** Derive Paid when balance is 0.
- **Evidence:** invoice 60 snapshot; `E2E3_S9_dashboard_after_receipt.png`
- **Viewport / role:** desktop, New Owner

### E2E3-032 — Stock valuation hides product name

- **Class:** Defect
- **Module/Page:** `/reports/stock-valuation`
- **Severity:** Medium
- **Category:** Data / UX
- **Expected:** Rows show E2E3-Widget (and godown name).
- **Actual:** Product column **—**. Qty 104 @ ₹57.39 = ₹5,968.85 and qty **10 @ ₹0.00** (same valuation hole as E2E3-028, but this report is owner-facing with money rounded).
- **Impact:** Cannot tell which item/godown the rows belong to.
- **Suggested fix:** Product + godown labels; carry cost on transferred lots.
- **Evidence:** `E2E3_S11_stock_valuation.png`
- **Viewport / role:** desktop, New Owner

### E2E3-033 — Company bank details do not appear on Bank accounts settings

- **Class:** Defect
- **Module/Page:** `/settings/bank-accounts` vs `/settings/company`
- **Severity:** Medium
- **Category:** Data / Broken flow
- **Steps to reproduce:** During onboarding, save HDFC `123456789012` on company. Open `/settings/bank-accounts`.
- **Expected:** That account listed (or a note that company bank lives on Company settings).
- **Actual:** **“Nothing here yet.”** Payments/receipts still work (cash).
- **Impact:** Owner thinks bank was not saved; Payment Out / statements have no account to pick.
- **Suggested fix:** Sync company bank into `payments/bank-accounts`, or deep-link Company settings from empty state.
- **Evidence:** bank-accounts empty snapshot; company form save earlier in run
- **Viewport / role:** desktop, New Owner

### E2E3-034 — Hindi toggle translates nav but not dashboard KPIs

- **Class:** Improvement
- **Module/Page:** `/` language toggle
- **Severity:** Low
- **Category:** i18n
- **Steps to reproduce:** Click **हिंदी**.
- **Expected:** Visible Hindi on nav **and** KPI labels (or honest “partial translation” note).
- **Actual:** Nav becomes डैशबोर्ड / बिक्री. Main heading stays **Dashboard**; **Today's sales**, **Customer outstanding**, etc. stay English. Toggle itself is clickable (UX-007 contrast **not** reproduced).
- **Impact:** Hindi mode looks unfinished.
- **Suggested fix:** Translate dashboard strings or hide the toggle until coverage is complete.
- **Evidence:** `E2E3_S15_hindi_partial.png`
- **Viewport / role:** desktop, New Owner
- **Cross-check:** UX-007 claimed Hindi toggle **invisible** — **fixed** (button worked). Remaining gap is incomplete strings.

### E2E3-035 — Quotations and returns `/new` URLs 404 (create is dialog-only)

- **Class:** Defect
- **Module/Page:** `/sales/quotations/new`, `/sales/returns/new`, `/purchases/returns/new`
- **Severity:** Medium
- **Category:** Broken flow / Routing
- **Steps to reproduce:**
  1. Open `/sales/quotations` — **New quotation** opens an in-page dialog (Customer, Valid until, Notes; Save disabled until customer).
  2. Open `/sales/quotations/new` directly.
  3. Repeat for `/sales/returns/new` and `/purchases/returns/new` (list **New** buttons exist).
- **Expected:** Deep-link `/new` either opens the same create UI or redirects to the list with the dialog open. Same pattern as `/sales/orders/new` and `/sales/delivery-challans/new`, which **do** load full pages.
- **Actual:** Bare **404 / Page not found** (no app chrome). Bookmark, email, or checklist links to those paths are dead.
- **Impact:** Inconsistent create UX; any documented `/new` URL for quotes/returns is wrong.
- **Suggested fix:** Register the `/new` routes **or** redirect `/…/new` → list `?create=1`. Prefer one pattern across docs.
- **Evidence:** `E2E3_S16_quotation_new_404.png`, `E2E3_S16_quotation_dialog.png`, `E2E3_S16_returns_new.png`, `E2E3_S16_sales_return_dialog.png`, `E2E3_S16_purchase_returns_new.png`
- **Viewport / role:** desktop, New Owner

### E2E3-036 — New purchase order defaults to GST for UNREGISTERED company

- **Class:** Bug
- **Module/Page:** `/purchases/orders/new`
- **Severity:** Medium
- **Category:** Tax / Defaults
- **Steps to reproduce:** As UNREGISTERED Owner, open New purchase order. Read **Purchase type**.
- **Expected:** **Non-GST** (same as the completed PUR-00001 bill after the user learned to switch).
- **Actual:** Combobox **Purchase type GST**. Save stays disabled until supplier/lines, so this is not a silent Complete-400, but it is the same wrong default as sales invoice / sales order / POS (E2E3-010, 020, 026).
- **Impact:** Easy to raise a GST PO against an unregistered shop; first-time users already hit Complete 400 on invoices.
- **Suggested fix:** Default Non-GST when company registration type is UNREGISTERED, on every buy/sell document that has a GST toggle.
- **Evidence:** `E2E3_S16_po_new_gst.png`
- **Viewport / role:** desktop, New Owner
- **Cross-check:** Related to E2E3-010 / 020 / 026 — additional surface, not a duplicate of POS 400.

### E2E3-037 — One Download template click saves both CSV and XLSX

- **Class:** Improvement
- **Module/Page:** `/settings/import`
- **Severity:** Low
- **Category:** Usability
- **Expected:** One format, or an explicit choice (CSV vs Excel).
- **Actual:** Click **Download template** → `products_import_template.csv` **and** `products_import_template.xlsx` both download. `GET /api/v1/imports/template/?kind=PRODUCTS` 200.
- **Impact:** Surprise double download; easy to upload the wrong file next.
- **Suggested fix:** Split into two buttons or a format menu.
- **Evidence:** Playwright download events; `E2E3_S16_import_ui.png`
- **Viewport / role:** desktop, New Owner

### E2E3-038 — Products template copy vs sample rows with opening stock

- **Class:** Defect
- **Module/Page:** `/settings/import` Download template
- **Severity:** Medium
- **Category:** Data / Copy
- **Expected:** Template is headers + a blank example row (page copy: “The template includes a second row with optional fields left blank.”).
- **Actual:** CSV contains populated sample SKUs including **Soap** `opening_stock` **25**, **Milk** `opening_stock` **6000** with batch/expiry, plus a Service row. Uploading the unmodified template would create catalog + stock (this run **did not** upload).
- **Impact:** Shopkeeper who “just uploads the template” poisons products and on-hand qty.
- **Suggested fix:** Ship a blank optional row only; put samples in a separate “example” download, or strip `opening_stock` from the starter file.
- **Evidence:** Downloaded `products_import_template.csv` (Playwright: `.playwright-mcp/products-import-template.csv`)
- **Viewport / role:** desktop, New Owner
- **Note:** CSV **commit was not executed** this run.

### E2E3-039 — Import `return=` query does not offer a back-to-setup path

- **Class:** Improvement
- **Module/Page:** `/settings/import?kind=PRODUCTS&return=/setup?step=catalog`
- **Severity:** Low
- **Category:** Onboarding / Usability
- **Expected:** When `return` is present, a **Back to catalog / setup** control (or auto-return after commit).
- **Actual:** Same Import data page; Products kind is selected. No return CTA. Wizard flag is **off**, so `/setup` would bounce to `/` anyway.
- **Impact:** Wizard import round-trip is incomplete even if the flag is later turned on.
- **Suggested fix:** Honor `return` with a visible back link; after successful commit, navigate there.
- **Evidence:** import snapshot with query in URL; `E2E3_S16_import_ui.png`
- **Viewport / role:** desktop, New Owner

## Improvements backlog (also listed above)

- Login → forgot-password link (E2E3-001)
- Register empty-state validation (E2E3-003)
- Password visibility; register success copy (E2E3-004, 005)
- Autocomplete hygiene on GST GSP fields (E2E3-007)
- Unify Godown wording (E2E3-009)
- Default Non-GST invoice **and purchase, PO, sales order, and POS** for UNREGISTERED (E2E3-010, 020, 026, 036)
- Item combobox initial list (E2E3-011)
- Stop cost-centers 400 (E2E3-012)
- Dashboard stock empty card (E2E3-015) — after receipt this became false **low stock 10** (E2E3-019)
- Current Stock godown filter (E2E3-018)
- Low Stock company vs godown qty (E2E3-019)
- Inventory report labels + transfer cost (E2E3-027, 028)
- Owner accounting/Insights/AI/settings-accounting gate copy (E2E3-030)
- Sales bill-upload supplier copy (E2E3-029)
- Paid vs Completed (E2E3-031)
- Stock valuation product name (E2E3-032)
- Company bank vs Bank accounts page (E2E3-033)
- Hindi dashboard strings (E2E3-034)
- Register `/new` routes or redirect for quotes/returns (E2E3-035)
- Split CSV vs XLSX template download (E2E3-037)
- Blank import template vs sample opening_stock (E2E3-038)
- Honor import `return=` back-to-setup (E2E3-039)

## Top 10 fix-first

1. **E2E3-026** — POS GST + no Non-GST toggle; Cash 400; leftover drafts.
2. **E2E3-030** — Owner blocked from P&L / TB / COA / Insights with “ask your owner”.
3. **E2E3-010** — Unregistered first invoice must not default to GST Complete-fail.
4. **E2E3-018** — Current Stock godown filter empty vs real lots.
5. **E2E3-019** — Low Stock Available 10 vs company 114.
6. **E2E3-007** — Stop password autofill into GSP Client Secret.
7. **E2E3-001** — Wire Forgot password on login.
8. **E2E3-003** — Register empty submit validation.
9. **E2E3-027 / 028 / 032** — Inventory/valuation labels and transferred stock value 0.
10. **E2E3-033** — Company bank not on Bank accounts settings.

## Stage 17 — Cross-check vs prior audits

Sources opened: `UX_AUDIT_REPORT.md`, `docs/reviews/UX_AUDIT_WAVE2_FINDINGS.md`, `docs/reviews/WORLDCLASS_QUALITY_AUDIT_FINDINGS.md`, `docs/reviews/FR_AUDIT_FINDINGS.md`, `docs/reviews/MASTER_ISSUE_REGISTER.md` (spot-search).

| This run | Prior ID | Verdict |
|---|---|---|
| E2E3-001 | WC-009, UX-018 | UX-018 **404 fixed** (page exists). **Not** a full duplicate: login still has **no link**. WC-009 leftover. |
| E2E3-002 fonts / 401 refresh | WC-008, UX-017 | UX-017 claimed **fixed**. Login still logged **401 refresh** earlier this run → treat as **possible regression** of silent-refresh noise. Fonts ERR is new/env. |
| E2E3-003 | WC-010 | **Duplicate**, still open. |
| E2E3-007 GSP autofill | — | **New** (security/UX). GST page “write-only” note from UX Stage 9 did not prevent browser password fill. |
| E2E3-010 / 020 / 026 / 036 | UXW2-003 | **Related** (GST complete blocked) but different: UNREGISTERED company + GST **default**, including POS **and PO**. Keep as new. |
| E2E3-035 quotes/returns `/new` 404 | UX-014 | 404 **page** holds; these paths should not 404. **New** routing gap. |
| E2E3-012 cost-centers 400 | FR-AC-03 **Met** | **Conflict**: FR says cost-center API works; this tenant gets **400** while accounting capability is off. |
| E2E3-015 / 019 | UXW2-001, UXW2-006 | **Related** dashboard/stock alerts vs real stock. Not exact duplicates. |
| E2E3-018 filter empty | — | **New**. |
| E2E3-027 / 028 / 032 | WC-005 | Related duplicate-SKU/valuation; **new** transferred-lot value 0 + blank product name. |
| E2E3-030 Owner gate | UX-013, WC-021, UX-005 | **New copy bug** (Owner told to ask owner). UX-005 **500 not reproduced** — Insights health is **gated**, API not called. UX-006 mfg/payroll broken-flag pages **not reproduced** (empty states load). |
| E2E3-033 bank accounts | — | **New**. |
| E2E3-034 Hindi KPIs | UX-007 | UX-007 contrast **fixed**. Incomplete i18n **new**. |
| GSTR-3B | UX-015 500 **fixed** | **Holds** — GSTR-3B loaded 200 this run. |
| `/forgot-password` | UX-018 **fixed** | **Holds** — route works. |
| 404 page | UX-014 **fixed** | **Holds** — 404 tested Stage 1. |

**Regressions to triage:** UX-017 401-on-login (if still claimed fixed); FR-AC-03 vs cost-centers 400 for capability-off tenants.

## Session limits (honest)

- **Did** this continue: leftover `/new` forms (DC, sales/purchase CN/DN, PO, sales order), quotation/return dialogs, Insights cashflow/assistant (gated), accounting periods/fixed-assets/bank-recon (gated), completed invoice/purchase **edit** (no Save), CSV **template download only**, import `return=` query, Stage 17 already written.
- **Did not** execute CSV **upload/commit**, send an invite, click billing Pay, demo Owner, staff RBAC, `/pay/:token`, or GST Save.
- Invite user dialog was **not** opened (policy blocked the click).
- Remaining if another pass: demo Owner `demo@bizboard.local`; staff RBAC; CSV commit with a **blank** (not sample) file. Do **not** Save GST settings (E2E3-007). Do **not** recreate E2E3 data. Do **not** upload the stocked sample template (E2E3-038).

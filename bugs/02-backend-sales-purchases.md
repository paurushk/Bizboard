# Area 02 — Backend Sales & Purchases (GST money engine)

**Scope:** `backend/core/services/billing.py`, `place_of_supply.py`, `document_numbers.py`; `backend/sales/*` (models, serializers, services, views, handlers, tasks, pdf/*); `backend/purchases/*`; `backend/core/models.py`, `events.py`, `handlers.py`, `viewsets.py`, `permissions.py`, `validators.py`, `exceptions.py`, `tasks.py`; `backend/ledgers/services.py`; `backend/inventory/services.py`; related migrations and tests; `web/src/utils/tax.ts`/`money.ts`; `web/src/pages/sales/NewInvoicePage.tsx` and `web/src/pages/purchases/NewPurchasePage.tsx`.

**Method:** Line-by-line read of every file above, plus two executed reproduction scripts (Python/Decimal and Node/JS) verifying the FE/BE tax-split arithmetic claims, and cross-checks against `BUG_REPORT.md`, `CALCULATION_VALIDATION.md`, `ACCOUNTING_VALIDATION.md`.

This is the highest-stakes area in the app: incorrect output here means wrong GST filed with the government or wrong money charged to customers.

---

### BUG-200 — BUG-001 claim does not reproduce: FE/BE CGST-SGST split now match
- **Severity:** Low (confirmed fixed)
- **Category:** Bug
- **Location:** `backend/core/services/billing.py:62-74`, `web/src/utils/tax.ts:33-82`
- **Description:** The prior report's exact repro (qty 1 × ₹10.05 @ 18%, intra-state) was recomputed by hand and by running both engines. Both now split via "unrounded tax, half rounded, residual to SGST".
- **Evidence:** Python (`ROUND_HALF_UP` Decimal): `tax raw 1.809 → cgst 0.90 sgst 0.91 sum 1.81`. Node (replicating `tax.ts`): `{ taxRaw: 1.809, cgst: 0.9, sgst: 0.91, sum: 1.81 }`. Both agree exactly.
- **Impact:** None currently for this case.
- **Remediation:** N/A — keep the parity fixture (`tests/fixtures/tax_parity_cases.json`) as a regression guard (see BUG-216).
- **Suggested test:** N/A, already covered by `test_cgst_sgst_halves_sum_to_tax` and `tax.test.ts`.
- **Status vs prior report:** ALREADY-FIXED (BUG_REPORT.md BUG-001, BUG-014/015 partially).

### BUG-201 — Genuine FE/BE floating-point divergence exists (rare, ~0.65% of cases)
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/utils/money.ts:2-12` (`roundMoney`, float+epsilon) vs `backend/core/services/billing.py:15-16` (`q2`, exact Decimal)
- **Description:** Although the algorithm now matches, the FE's float-based `roundMoney` and the BE's exact-Decimal `q2` disagree near `x.xx5` boundaries due to binary floating-point representation error. A 2000-case randomized fuzz found 13 mismatches (0.65%), all off by exactly ₹0.01 — in one case the CGST/SGST split literally swaps which side gets the extra paisa.
- **Evidence:** e.g. `qty=6, price=853.65, discount=5%, rate=0` → backend taxable `4865.80`, frontend `4865.81`; `qty=5, price=1030.10, rate=18%` → backend `cgst=463.55, sgst=463.54`, frontend `cgst=463.54, sgst=463.55`.
- **Impact:** Backend is authoritative on save, so the filed invoice is always correct, but the on-screen preview can show a ₹0.01-different total/split than what gets recorded — reintroducing the "preview disagrees with saved/PDF" trust problem via a rarer path.
- **Remediation:** Route preview math through the existing but unused `POST /sales/invoices/preview-totals/` endpoint (`backend/sales/views.py:85-156`), or reimplement `roundMoney` with exact string/BigInt decimal rounding instead of float+epsilon.
- **Suggested test:** Cross-language fuzz test over thousands of random qty/price/rate/discount combos asserting FE/BE equality.
- **Status vs prior report:** NEW (refines BUG-001/BUG-015 with concrete new evidence).

### BUG-202 — Document discount-after-tax: fixed on backend + Sales UI, default unchanged
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/core/services/billing.py:126-130, 171-174`; `web/src/pages/sales/NewInvoicePage.tsx:1397-1410`
- **Description:** A `BEFORE_TAX` discount mode was added (migrations `sales/0005`, `purchases/0003`) that proportionally reduces line taxables before GST. Sales UI now exposes an explicit AFTER_TAX/BEFORE_TAX selector. Default remains AFTER_TAX.
- **Evidence:** `test_billing_totals.py::test_before_tax_invoice_discount_reduces_gst` passes with correct math.
- **Impact:** Sales invoices can now correctly reduce GST via discount when opted in; default unchanged but now a clearly-labeled choice, not a hidden bug.
- **Remediation:** Consider defaulting to BEFORE_TAX per stated commercial policy, or add a first-run tooltip.
- **Suggested test:** N/A — covered.
- **Status vs prior report:** ALREADY-FIXED for Sales (BUG_REPORT.md BUG-003) — see BUG-203/204 for residual gaps.

### BUG-203 — Purchases page still has the confusing "+ Discount / -₹" UI and no BEFORE_TAX option
- **Severity:** High
- **Category:** UI-Optimization / Bug
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:1386-1399`
- **Description:** Unlike Sales, Purchases never renders an `invoiceDiscountMode` selector even though state and backend both support `BEFORE_TAX`. Label is `"+ Invoice discount"` while the input's adornment is `"- ₹"`.
- **Evidence:** `label={`+ ${t('billing.invoiceDiscount')}`}` next to `startAdornment: "- ₹"`; no discount-mode `MenuItem` anywhere in the file.
- **Impact:** Purchase-side discounts can never be entered as GST-reducing via UI; sign-confused label. Since ITC correctness for the buyer's own books depends on the purchase-side taxable value, arguably more consequential than the sales-side version.
- **Remediation:** Port the `invoiceDiscountMode` selector from `NewInvoicePage.tsx:1397-1410`; drop the stray "+".
- **Suggested test:** RTL test asserting the purchase form renders a discount-mode selector and BEFORE_TAX reduces taxable/CGST preview.
- **Status vs prior report:** CONFIRMED (BUG_REPORT.md BUG-003/024) — present in Purchases only. Same root issue as BUG-504.

### BUG-204 — PDF invoice ignores invoice_discount_mode, printing self-contradictory math for BEFORE_TAX
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/sales/pdf/gst_tax_invoice.py:345-385`
- **Description:** The printed GST Tax Invoice always prints a "Discount" line after TAXABLE AMOUNT/CGST/SGST rows, unconditionally, with zero reference to `invoice_discount_mode` anywhere in the PDF module. In BEFORE_TAX mode the discount is already netted into TAXABLE AMOUNT, so printing it again again makes the visible arithmetic under-count the total by the discount amount.
- **Evidence:** `right_rows.append(["Discount", format_money(invoice_discount)])` fires unconditionally; no read of `invoice.invoice_discount_mode` anywhere in the file.
- **Impact:** The legal tax document shown to the customer/auditor can visually misrepresent its own math whenever BEFORE_TAX mode is used — undermines CA/audit confidence.
- **Remediation:** When mode is BEFORE_TAX, omit the "Discount" row or add "(already reflected in taxable value)" sub-label.
- **Suggested test:** Extend `test_pdf_and_share.py` with a BEFORE_TAX-mode invoice asserting the printed rows sum to the printed TOTAL.
- **Status vs prior report:** NEW.

### BUG-205 — Additional charges are never subject to GST anywhere in the stack
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/core/services/billing.py:112-118, 172-174`; `backend/sales/pdf/gst_tax_invoice.py:346-352`
- **Description:** `charges` (additional_charges) is added to `raw_total` after all GST computation with no tax ever applied, in both discount modes. Under GST law (Section 15, CGST Act), incidental charges that are part of the value of supply are generally taxable at the same rate as the principal supply.
- **Evidence:** `raw_total = taxable_total + cgst_total + sgst_total + igst_total + charges [- inv_discount]` — `charges` never multiplied by any rate anywhere in the file.
- **Impact:** If a retailer bills packing/delivery charges through this field, output GST liability is understated by the tax that should have applied — a real GSTR-1/3B understatement risk.
- **Remediation:** Either explicitly document/scope the field as "non-taxable charges only" or apply the invoice's blended GST rate to `charges` by default with opt-out.
- **Suggested test:** `test_additional_charges_are_taxed_at_line_rate` (current test uses `gst_rate=0`, masking this gap).
- **Status vs prior report:** NEW.

### BUG-206 — Blank-party-state-defaults-to-intra gate has a real bypass for non-GST-registered companies
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/core/services/place_of_supply.py:7-20`; `backend/sales/services.py:81-82, 197-202`
- **Description:** `assert_place_of_supply_for_gst` returns immediately with no check when `not company.is_gst_registered`. But `_tax_enabled(invoice_type)` computes tax for any invoice type except `NON_GST`, regardless of `is_gst_registered`. So an unregistered company issuing a TAX/RETAIL invoice (tax enabled) to a customer with blank state can Complete an actual inter-state sale and silently get CGST+SGST instead of IGST.
- **Evidence:** `if not company.is_gst_registered: return` precedes the `place_of_supply_known` check entirely.
- **Impact:** Wrong tax type recorded/filed for real interstate transactions by unregistered/borderline businesses using invoice types that still compute tax.
- **Remediation:** Gate on `tax_enabled` rather than (or in addition to) `is_gst_registered`.
- **Suggested test:** `is_gst_registered=False`, `invoice_type="TAX"`, blank customer state implying inter-state — assert Complete blocks or computes IGST correctly.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT, narrower scope than BUG_REPORT.md BUG-010.

### BUG-207 — Free-text state fields + exact-string fallback risk intra/inter misclassification
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/models.py:61`, `backend/masters/models.py:63,83`; `backend/core/services/billing.py:53-59`; `web/src/pages/sales/NewInvoicePage.tsx:1602-1606`
- **Description:** When a party lacks a GSTIN, `is_intra_state()` falls back to exact lowercase string comparison of free-text `state` fields with no canonical state list/autocomplete anywhere. Spelling variance ("Orissa" vs "Odisha", "TN" vs "Tamil Nadu") causes misclassification with no GSTIN cross-check to catch it.
- **Evidence:** `state = models.CharField(max_length=64, blank=True)` with no choices/validators on Company/Customer/Supplier.
- **Impact:** Wrong CGST+SGST vs IGST split for real transactions whenever a party has no GSTIN and typed state differently — a factual filing error.
- **Remediation:** Constrain `state` to the official Indian state/UT list (with GST state code) everywhere it's captured.
- **Suggested test:** `test_intra_state_state_name_variance_still_matches` (e.g. "Orissa" vs "Odisha").
- **Status vs prior report:** NEW (adjacent to BUG-010/016).

### BUG-208 — Invoice/purchase numbers are burned at DRAFT creation, not at Complete
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/sales/serializers.py:123-136`; `backend/purchases/serializers.py:128-143`; `backend/sales/services.py:218-220`; `backend/sales/views.py:63-66`
- **Description:** `"number"` is `read_only`, so `DocumentNumberService.next_number(...)` is called unconditionally on every draft creation (`POST /sales/invoices/`), not deferred to Complete — contradicting both the code's own `complete()` logic (`invoice.number = invoice.number or next_number(...)`) and explicit claims in `CALCULATION_VALIDATION.md`/`ACCOUNTING_VALIDATION.md` ("assigned on Complete"). Drafts are freely deletable, so every abandoned draft permanently burns a number with no audit trail. The quotation→invoice conversion path does this correctly (defers to Complete), so the two creation paths are internally inconsistent.
- **Evidence:** `SalesInvoiceSerializer.create()`: `if not validated_data.get("number"): validated_data["number"] = DocumentNumberService.next_number(...)` — always true since the field is read-only.
- **Impact:** Real, unexplained gaps in a supposedly GST-sequential invoice series — draws scrutiny in a GST audit, and contradicts the docs a CA may be relying on.
- **Remediation:** Defer number allocation to `complete()` for both serializers, matching the quotation-conversion path.
- **Suggested test:** Create a draft, delete it, create+complete another — assert whether a gap results (currently untested either way).
- **Status vs prior report:** NEW — directly contradicts a "Pass" claim in the validation docs.

### BUG-209 — Invoice number field is NOT editable in the UI (prior claim inaccurate for current code)
- **Severity:** N/A
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:916-929`
- **Description:** The number field is `disabled` with a no-op `onValueChange`, showing a read-only preview with helper text "Invoice number is fixed when editing". Backend also enforces `read_only` (BUG-208).
- **Impact:** None — cannot reproduce the claimed editability.
- **Status vs prior report:** ALREADY-FIXED (BUG_REPORT.md BUG-020).

### BUG-210 — Invoice-line GST rate has zero validation (unlike the product master)
- **Severity:** High
- **Category:** Gap
- **Location:** `backend/core/models.py:65`; `backend/sales/serializers.py:38-54`; `backend/purchases/serializers.py:26-45`
- **Description:** `Product.gst_rate` is validated against `ALLOWED_GST_RATES` via `validate_gst_rate`, but `DocumentLineModel.gst_rate` (used by `SalesItem`/`PurchaseItem`/etc — the fields that actually drive charged/filed tax) has no validators at all, at model or serializer level.
- **Evidence:** `core/models.py:65`: `gst_rate = models.DecimalField(...)` — no `validators=`.
- **Impact:** A client can submit `gst_rate: "17"` or `"99"` or negative directly on an invoice line; used verbatim in `compute_document_totals`.
- **Remediation:** Add `validators=[validate_gst_rate]` to `DocumentLineModel.gst_rate`, or validate in `_validate_lines`.
- **Suggested test:** `test_invalid_line_gst_rate_rejected` — POST an invoice with a line `gst_rate: "17"`, assert 400.
- **Status vs prior report:** NEW.

### BUG-211 — No bounds validation on unit_price, discount_percent, or additional_charges
- **Severity:** High
- **Category:** Gap
- **Location:** `backend/core/models.py:63-64`; `backend/sales/services.py:29-39`; `backend/core/services/billing.py:100-110`
- **Description:** `_validate_lines` only checks `quantity > 0`. Nothing validates `unit_price >= 0` or `0 <= discount_percent <= 100`. `discount_percent > 100` silently produces negative `taxable_amount`/`cgst`/`sgst`/`igst`/`line_total` with no error (contrast with the carefully-clamped BEFORE_TAX document-discount allocation).
- **Evidence:** Neither model fields nor serializers add `MinValueValidator`/`MaxValueValidator` anywhere in `sales/serializers.py` or `purchases/serializers.py`.
- **Impact:** Malformed/negative money values can enter a completed, filed GST invoice with no server-side rejection.
- **Remediation:** Add `MinValueValidator(0)` to `unit_price`/`additional_charges`; `MinValueValidator(0)`+`MaxValueValidator(100)` to `discount_percent`.
- **Suggested test:** `test_negative_unit_price_rejected`, `test_discount_percent_over_100_rejected`.
- **Status vs prior report:** NEW.

### BUG-212 — PurchaseInvoice has no RETURNED status; sales/purchase status machines diverge
- **Severity:** Medium
- **Category:** Broken-Flow
- **Location:** `backend/purchases/models.py:10-13`; `backend/sales/models.py:10-14`; `backend/purchases/services.py:283-332`
- **Description:** `SalesService.complete_return` flips a fully-returned invoice to `RETURNED`; `PurchaseInvoice.Status` has no such value, and `PurchaseReturn.complete_return` never updates the source invoice's status. A fully-returned purchase stays `COMPLETED` forever, indistinguishable in listings/filters from a normal purchase.
- **Impact:** No tax/ledger miscalculation (see BUG-223), but a real reporting/filtering gap when reconciling with suppliers.
- **Remediation:** Add a `RETURNED` status to `PurchaseInvoice` mirroring `SalesInvoice`, or document the asymmetry as intentional.
- **Suggested test:** `test_fully_returned_purchase_marked_returned`.
- **Status vs prior report:** NEW (root cause behind BUG_REPORT.md BUG-017 — see BUG-223).

### BUG-213 — No detailed audit trail (diff) for post-completion line-item edits; dead domain events
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/core/viewsets.py:36-38,48-55`; `backend/sales/services.py:176-177`; `backend/purchases/services.py:171`
- **Description:** `perform_update` logs a generic `AuditEvent(action="UPDATE")` with no before/after metadata, unlike the completed/cancelled handler which does record metadata. Completed invoices can have line items edited post-Complete (re-triggering tax/stock), with no way to reconstruct prior totals from the audit log. Separately, `sales_invoice.edited`/`purchase_invoice.edited` events have zero subscribers anywhere — dead events.
- **Impact:** Weak forensic trail for a money-critical, post-completion mutation path the app deliberately allows.
- **Remediation:** Emit before/after metadata on post-completion edits, or wire a subscriber that logs a diff.
- **Suggested test:** `test_completed_invoice_edit_audit_captures_diff`.
- **Status vs prior report:** NEW.

### BUG-214 — Email notification task re-raises after failure, propagating a 500 through NotificationService.send()
- **Severity:** Medium
- **Category:** Broken-Flow
- **Location:** `backend/core/tasks.py:6-25`; `backend/core/services/notifications.py:24-29`
- **Description:** `send_email_notification` marks the notification FAILED then `raise`s again. Under `CELERY_TASK_ALWAYS_EAGER=True` (test/local default), `.delay()` executes synchronously, so the exception propagates into the `share` API view as an unhandled 500 — inconsistent with the PDF task's explicit "must survive failure" design.
- **Impact:** "Share invoice by email" can 500 the whole request instead of degrading gracefully when SMTP is down.
- **Remediation:** Drop the `raise` (mirror the PDF task's swallow-and-mark-FAILED pattern).
- **Suggested test:** `test_share_email_smtp_failure_returns_graceful_error`.
- **Status vs prior report:** NEW.

### BUG-215 — No automatic retry for PDF generation Celery task
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/sales/tasks.py:10-48`
- **Description:** No `autoretry_for`/`max_retries`/backoff configured; a transient failure permanently marks `pdf_status=FAILED` requiring manual "Regenerate PDF".
- **Remediation:** `@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)`.
- **Status vs prior report:** NEW.

### BUG-216 — FE/BE tax-parity test coverage is far too thin to catch real divergence
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `backend/tests/fixtures/tax_parity_cases.json`; `web/src/utils/tax.test.ts:4-32`
- **Description:** The shared parity fixture has exactly 3 cases and isn't actually loaded by `tax.test.ts` (values hand-copied instead of imported); no Python test loads the same JSON. Far too small a sample to have caught BUG-201's 0.65% divergence.
- **Remediation:** Load the fixture from both a Python test and `tax.test.ts` as single source of truth; add a fuzzed case set to both.
- **Suggested test:** `test_tax_parity_fixture_matches_backend` + updated `tax.test.ts` importing the JSON, plus property-based fuzzing.
- **Status vs prior report:** NEW.

### BUG-217 — No test for invalid GST rate submitted directly on an invoice line
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_business_rules.py:116-120`
- **Description:** `test_invalid_gst_rate_rejected` only covers product master data, not invoice/purchase lines (see BUG-210).
- **Suggested test:** `test_invalid_line_gst_rate_rejected` on `POST /api/v1/sales/invoices/`.
- **Status vs prior report:** NEW.

### BUG-218 — No test for negative unit_price or out-of-range discount_percent
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_business_rules.py`
- **Description:** Only `test_zero_quantity_rejected` exists; nothing exercises negative `unit_price` or `discount_percent > 100` (see BUG-211).
- **Suggested test:** `test_negative_unit_price_rejected`, `test_discount_over_100_percent_rejected`.
- **Status vs prior report:** NEW.

### BUG-219 — No test proving/disproving whether deleting a draft leaves a numbering gap
- **Severity:** Low
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_document_numbers.py`
- **Description:** Nothing tests: create draft → number assigned → delete draft → create another → is there a gap? (directly relevant to BUG-208).
- **Suggested test:** `test_deleting_draft_invoice_leaves_number_gap`.
- **Status vs prior report:** NEW.

### BUG-220 — No credit/debit note feature
- **Severity:** High
- **Category:** Gap
- **Location:** N/A (repo-wide)
- **Description:** No `CreditNote`/`DebitNote` model/serializer/view/UI anywhere. Only quantity-based `SalesReturn`/`PurchaseReturn` exist — no way to issue a pure value/price correction without a matching physical return.
- **Impact:** GST law (Section 34, CGST Act) explicitly provides for credit/debit notes for exactly this correction class; traders needing one are forced into a fictitious "return" or an unaudited direct edit of a completed invoice — likely to be rejected by a CA during filing review.
- **Remediation:** Add `SalesCreditNote`/`SalesDebitNote` (and purchase equivalents) linked to an invoice but independent of stock quantities, feeding `LedgerService` and GST reporting.
- **Status vs prior report:** CONFIRMED (BUG_REPORT.md BUG-011).

### BUG-221 — Dead/unreachable "cancel a RETURNED invoice restores stock" branch
- **Severity:** Cosmetic
- **Category:** Bug
- **Location:** `backend/sales/services.py:243-262`
- **Description:** The "cannot cancel an invoice with completed returns" guard always fires before the `status in (COMPLETED, RETURNED)` stock-restore check can hit the RETURNED case, making that half dead code today. Harmless now; would misbehave if the guard is ever relaxed.
- **Remediation:** Add a comment noting this, or simplify to `if invoice.status == COMPLETED`.
- **Status vs prior report:** NEW (minor).

### BUG-222 — Race condition: negative-stock BLOCK policy can be bypassed by concurrent completions
- **Severity:** Critical
- **Category:** Bug
- **Location:** `backend/inventory/services.py:55-65` (`check_negative_stock`, unlocked read); `backend/sales/services.py:186-216`; `backend/inventory/services.py:32-47` (locked write happens later)
- **Description:** `SalesService.complete()` locks only the invoice row, not the product/stock row. `check_negative_stock` reads `available_quantity` via a plain unlocked SELECT and raises only if that stale snapshot already shows insufficient stock; the actual row lock happens later, inside `post_movement`, for the write only. Two invoices completing concurrently for the same product can both read the same "available" quantity, both pass the BLOCK check, and both post SALE movements — driving `on_hand` negative even under the strictest policy.
- **Impact:** Under real concurrent load (two staff completing sales for the same fast-moving SKU at once), the app can oversell past zero stock — a genuine business-integrity failure.
- **Remediation:** Take `select_for_update()` on the relevant `StockBalance` row(s) at the start of `complete()`, before `check_negative_stock`, holding it through the check-and-post sequence.
- **Suggested test:** Two threads/DB connections completing two invoices for the same product with `available=5`, each requesting qty 3, under BLOCK policy — assert exactly one succeeds and `on_hand` never goes negative (verify against Postgres, not SQLite).
- **Status vs prior report:** NEW. (Same underlying race independently found by the inventory/payments review as BUG-309 — see area 03.)

### BUG-224 — An unreachable Celery broker blocks the entire sales-invoice Complete request for 30+ seconds (FIXED)
- **Severity:** High
- **Category:** Broken-Flow / Reliability
- **Location:** `backend/sales/handlers.py:9-19` (`enqueue_invoice_pdf`); `backend/sales/views.py:170-179` (`regenerate_pdf`); `backend/config/settings.py:178-183` (Celery config, prior to fix)
- **Description:** `enqueue_invoice_pdf` (subscribed to `sales_invoice.completed`, itself emitted from inside `SalesService.complete()`'s `@transaction.atomic` block) calls `transaction.on_commit(lambda: generate_invoice_pdf.delay(invoice_id))` whenever `CELERY_TASK_ALWAYS_EAGER` is False — the production/non-eager default (`settings.py` had no broker timeout configured, so kombu/redis fell back to OS-level TCP timeouts). `transaction.on_commit` callbacks run synchronously, in the same request thread, before the HTTP response is sent. If the Celery broker (Redis) is unreachable, `.delay()`'s connection attempt blocked for 30+ seconds before failing — stalling the `POST .../complete/` response even though the invoice row had already committed as COMPLETED. Found via a real end-to-end Playwright test against the live backend (not mocks), where the frontend axios client timed out on `complete()` while the invoice was already COMPLETED in the database. The regenerate-pdf endpoint (`views.py:177`, prior code) called `.delay()` directly with the same lack of protection.
- **Why the test suite never caught it:** `backend/config/settings_test.py` sets `CELERY_TASK_ALWAYS_EAGER = True` unconditionally, so `.delay()` always short-circuits to run in-process, bypassing the broker (and the `transaction.on_commit` branch entirely) in every test.
- **Impact:** Any Redis restart, network blip, or broker misconfiguration in production turns every sales-invoice Complete (and PDF regenerate) request into a 30+ second hang, tying up a request-handling worker/thread per stalled request — under load this can cascade into full worker-pool exhaustion, a de facto outage, even though the underlying business operation (Complete) already succeeded and committed.
- **Symmetry check — purchases:** `PurchaseService.complete()`/`purchases/services.py` only emits `document.completed`, whose only subscriber is `core/handlers.py::audit_document_event` (a synchronous DB write, no Celery/broker involved). Purchases has no PDF-generation-on-complete flow at all, so this specific pattern does **not** reproduce there — confirmed by reading the code, not just inference. (A structurally similar unprotected `.delay()` does exist at `backend/imports/services.py:220` (`extract_purchase_bill_task.delay`) for purchase-bill-import extraction, which is a related but separate document flow, not the sales/purchase invoice Complete path — flagged here for awareness but out of scope for this fix.)
- **Remediation (applied):** (1) `backend/config/settings.py` now sets `CELERY_BROKER_CONNECTION_TIMEOUT=2`, `CELERY_BROKER_CONNECTION_MAX_RETRIES=1`, `CELERY_BROKER_TRANSPORT_OPTIONS={"socket_connect_timeout": 2, "socket_timeout": 2}`, and `CELERY_TASK_PUBLISH_RETRY_POLICY={"max_retries": 1, ...}` so a broker-connect attempt fails within a few seconds instead of the OS TCP default. (2) Added `core/celery_utils.safe_delay()`, which wraps `task.delay(...)` in a try/except that logs and swallows any dispatch failure; `sales/handlers.py::enqueue_invoice_pdf` and `sales/views.py::regenerate_pdf` now both dispatch through it as defense-in-depth, so even a slow/failing broker can never propagate into the request path — `pdf_status` stays `QUEUED` and can be retried later via the existing regenerate-pdf endpoint.
- **Suggested test (added):** `backend/tests/test_pdf_and_share.py::test_complete_survives_broker_connection_failure` — forces `CELERY_TASK_ALWAYS_EAGER=False`, uses `django_capture_on_commit_callbacks` to actually exercise the `on_commit` dispatch path, mocks `generate_invoice_pdf.delay` to raise `kombu.exceptions.OperationalError`, and asserts `complete()` still returns 200 with the invoice COMPLETED. `test_regenerate_pdf_survives_broker_connection_failure` covers the same for the regenerate-pdf endpoint.
- **Status vs prior report:** NEW (not previously catalogued in this review or `BUG_REPORT.md`) — found live via Playwright E2E testing against the real backend, not a static-read finding. Fixed same day as found.

### BUG-223 — BUG-017 re-examined: not a computation bug, root cause is the status-machine asymmetry (BUG-212)
- **Severity:** N/A
- **Category:** Bug
- **Location:** `backend/ledgers/services.py:27-50`
- **Description:** Traced both `sales_invoice_outstanding` and `purchase_invoice_outstanding`: both compute the same formula (`grand_total − completed_returns − allocated`); the only difference is which statuses short-circuit to zero, and purchase's short-circuit set is correct given it has no RETURNED status (BUG-212). No incorrect outstanding balances were found in any traced case.
- **Impact:** None — the "inconsistency" is real but lives in the status model, not the ledger arithmetic.
- **Status vs prior report:** INACCURATE (BUG_REPORT.md BUG-017 as literally stated) — see BUG-212 for the real gap.

---

## Summary of most severe systemic issues

1. **The negative-stock BLOCK policy is not race-safe (BUG-222).** `check_negative_stock` reads stock unlocked before the atomic write in `post_movement` takes its lock, so concurrent completions of two different invoices against the same product can both pass validation and both post, overselling past zero even under the strictest configured policy.
2. **The printed tax document and the tax engine have drifted apart on discount semantics (BUG-202/203/204/205).** The backend gained a `BEFORE_TAX` discount mode, but the Purchases UI never got the matching control, and the PDF generator was never taught about the mode at all — so the one document a CA or tax officer looks at can visually misstate its own arithmetic. `additional_charges` is also unconditionally GST-exempt everywhere, a plausible real understatement of output tax.
3. **Document numbering and post-completion mutation lack the integrity the app claims to have (BUG-208, 213, 220).** Invoice numbers are burned at draft creation (not Complete, contrary to in-code comments and the prior validation reports), and drafts are freely deletable — producing silent, unexplained gaps in a supposedly GST-sequential series. Completed invoices can be edited with only a bare "UPDATE" audit row, and there is still no credit/debit-note feature.

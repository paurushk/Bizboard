# Purchase module — provisional release review

Verdict: **Purchase invoice Complete is largely sales-parity atomic (stock + AP in one `@transaction.atomic`)**, but **CN/DN complete, landed-cost vs GL, cancel guards, and subscription gating** are release-risk before first paying users.

---

### PUR-001
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Idempotency |
| **Location** | `backend/purchases/phase1_views.py` (`PurchaseCreditNoteViewSet.complete`, `PurchaseDebitNoteViewSet.complete`); `backend/core/idempotency.py` `MONEY_IDEMPOTENCY_SCOPES` |
| **Type** | Missing money idempotency |
| **Severity** | **High** |
| **What's wrong** | Purchase CN/DN `complete` has **no** `wrap_idempotent`. Scopes `purchase_credit_note_complete` / `purchase_debit_note_complete` are **absent** from `MONEY_IDEMPOTENCY_SCOPES`. Invoice/return/BoE completes are wrapped; notes are not. |
| **Trigger** | Double-click / retry on `/purchases/credit-notes/{id}/complete/` or debit-note complete; SPA `completePurchaseCreditNote` sends **no** Idempotency-Key. |
| **Consequence** | No durable replay of success; after a timed-out success, retry returns 400 “already completed” instead of cached body. Future stale in-flight reclaim would not be money-protected if wrap is added without updating the set. |
| **Code evidence** | Sales: `sales/phase1_views.py` uses `scope="sales_credit_note_complete"` / `sales_debit_note_complete` in `MONEY_IDEMPOTENCY_SCOPES`. Purchase phase1 complete has neither. |
| **Suggested fix** | Mirror sales: `wrap_idempotent` + add both scopes to `MONEY_IDEMPOTENCY_SCOPES`; send Idempotency-Key from note UI. |
| **Test to add** | Double-complete same key → identical 200 + single JE; without key, concurrent completes → one success. |
| **Twin check** | **N** (Sales fixed; Purchase not) |

---

### PUR-002
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Accounting |
| **Location** | `backend/purchases/phase1_views.py` L61–70, L117–125 vs `notes_services.complete_*_note` |
| **Type** | Latent double-post |
| **Severity** | **High** (currently masked by dedup) |
| **What's wrong** | View calls `PostingService.post_note` **after** service already posts. Sales removed this (B2-010) as “dead code kept alive only by dedup.” |
| **Trigger** | Complete any purchase CN/DN with `accounting_enabled`. |
| **Consequence** | Today second call returns existing JE (`PostingService.post` fast-path). Any uniqueness/purpose change → **double AP/inventory JE**. |
| **Code evidence** | `complete_credit_note` posts; view posts again. Sales comment: *“second post_note … would double-post.”* |
| **Suggested fix** | Delete view-side `post_note` (sales pattern). |
| **Test to add** | Assert exactly one `JournalEntry` `(PURCHASE_CREDIT_NOTE, id, COMPLETE)` after HTTP complete. |
| **Twin check** | **N** (Sales fixed B2-010; Purchase still double-calls) |

---

### PUR-003
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Inventory cost vs GL |
| **Location** | `PurchaseService.complete` (~L785–804); `PostingService.post_purchase` (~L1133–1139, charges → 5110) |
| **Type** | Landed-cost / perpetual mismatch |
| **Severity** | **High** |
| **What's wrong** | Complete **capitalizes `additional_charges` into stock `unit_cost` / FIFO layers**, while GL books freight to **5110** and Inventory **1400 = line taxables only** (`capitalize_purchase_charges` noted as not enabled). |
| **Trigger** | Complete purchase with freight/packing > 0, then sell stock (FIFO/WAVG). |
| **Consequence** | Layer COGS ≠ GL inventory cost; inventory GL drifts vs quantity × layer cost; P&L/COGS wrong for paying users with freight. |
| **Code evidence** | Stock: `effective_unit_cost = base_cost + charge_alloc/qty`. GL docstring: charges → 5110 “not capitalized into 1400”. |
| **Suggested fix** | One policy: either capitalize charges in both GL+layers, or keep layers at taxable-only and expense freight only in GL. |
| **Test to add** | Purchase + freight → assert layer `unit_cost` and JE 1400/5110 agree under chosen policy; sell → COGS matches. |
| **Twin check** | **N** (Sales issues; purchase receives — purchase-specific) |

---

### PUR-004
| Field | Detail |
|--------|--------|
| **Module** | Purchase / BoE landed cost |
| **Location** | `boe_services.py` / `PostingService.post_bill_of_entry`; `PurchaseService.complete` (no BoE amounts in `unit_cost`) |
| **Type** | Incomplete landed cost |
| **Severity** | **High** |
| **What's wrong** | Model says BCD is for “GL / landed-cost picture”; GL puts BCD (+ ineligible IGST/cess) on **5110**, never into purchase stock layers. Import NON_GST complete uses invoice line prices only. |
| **Trigger** | Import purchase + completed BoE with BCD; stock moves at commercial price only. |
| **Consequence** | Import inventory undervalued; margin/COGS wrong vs customs cash cost. |
| **Code evidence** | `post_bill_of_entry`: Dr 5110 BCD; complete loop never reads `invoice.bill_of_entry.bcd_amount`. |
| **Suggested fix** | Allocate BoE cost (BCD ± ineligible duty) into linked purchase layers on Complete, or document “expense-only” and stop claiming landed-cost. |
| **Test to add** | BoE+import complete → layer cost includes BCD; GL 1400/5110 consistent. |
| **Twin check** | **N** |

---

### PUR-005
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Cancel |
| **Location** | `PurchaseService.cancel` (~L830–845) |
| **Type** | Missing cancel guard |
| **Severity** | **High** |
| **What's wrong** | Cancel blocks completed returns and open allocations, **not** completed credit/debit notes. Restores stock + reverses purchase JE while CN/DN JEs remain. |
| **Trigger** | Complete purchase → standalone CN → cancel purchase. |
| **Consequence** | Stock restored; AP still relieved by CN → free inventory / distorted payables/GSTR. |
| **Code evidence** | Guards: returns, allocations only. No `credit_notes` / `debit_notes` filter. |
| **Suggested fix** | Block cancel if completed CN/DN exist (or auto-cancel notes first, like return→CN). |
| **Test to add** | Cancel with open CN → 400; after cancel CN → cancel OK. |
| **Twin check** | **Y** (Sales cancel also omits CN/DN check) |

---

### PUR-006
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Cancel |
| **Location** | `PurchaseService.cancel` vs `SalesService.cancel` R2-005 |
| **Type** | Missing draft-return guard |
| **Severity** | **Medium** |
| **What's wrong** | Sales refuses cancel when draft/in-progress returns exist. Purchase does not. |
| **Trigger** | Draft purchase return on invoice → cancel purchase. |
| **Consequence** | Orphan draft return pointing at cancelled bill; complete later fails or confuses AP/stock. |
| **Code evidence** | Sales `returns.exclude(COMPLETED|CANCELLED)`; purchase has no equivalent. |
| **Suggested fix** | Copy R2-005 for purchase returns. |
| **Test to add** | Draft return → cancel purchase → 400. |
| **Twin check** | **N** (Sales has guard; Purchase missing) |

---

### PUR-007
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Return |
| **Location** | `PurchaseService.complete_return` (~L961–1012) |
| **Type** | Race / over-return |
| **Severity** | **High** |
| **What's wrong** | Locks return row, **not** source invoice. Qty headroom from unlocked aggregates of completed returns. |
| **Trigger** | Two concurrent completes returning the last remaining qty. |
| **Consequence** | Both can pass headroom → return more than received; stock/AP over-relieved (auto CN). |
| **Code evidence** | `PurchaseReturn.objects.select_for_update`; invoice only read. Sales return same pattern. |
| **Suggested fix** | `PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)` before headroom; or unique constraint / advisory lock. |
| **Test to add** | Concurrent completes on last unit → one 200, one 400. |
| **Twin check** | **Y** |

---

### PUR-008
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Billing permissions |
| **Location** | `phase1_views.py` CN/DN/PO `get_permissions`; contrast invoice/return/BoE views |
| **Type** | Subscription gate bypass |
| **Severity** | **High** |
| **What's wrong** | Overridden `get_permissions` **omit** `SubscriptionWritesAllowed`. Invoice/return/BoE add it explicitly. |
| **Trigger** | Suspended / unpaid tenant completes CN/DN or converts PO. |
| **Consequence** | Money documents after subscription should block writes. |
| **Code evidence** | CN create/complete: `CanCreatePurchases` only. Invoice complete includes `SubscriptionWritesAllowed()`. |
| **Suggested fix** | Add `SubscriptionWritesAllowed()` on all write actions (incl. convert). |
| **Test to add** | Suspended company → CN complete → 402/403. |
| **Twin check** | Check Sales phase1 — if Sales includes it, **N**; if also missing, **Y**. (Purchase invoice path is gated; note path is not.) |

---

### PUR-009
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Notes API |
| **Location** | `phase1_serializers.py` CN/DN Meta.fields |
| **Type** | Functional gap vs Sales |
| **Severity** | **Medium** |
| **What's wrong** | Purchase CN/DN serializers omit `additional_charges` (and related). Sales note serializers expose them. Auto-return CN sets charges in service only. |
| **Trigger** | Manual CN for freight credit via API/UI. |
| **Consequence** | Cannot record charge legs on notes; AP headroom wrong vs supplier CN. |
| **Code evidence** | Purchase CN fields lack `additional_charges`; sales phase1 includes it. |
| **Suggested fix** | Add fields + wire editor; keep company scoping. |
| **Test to add** | Create CN with additional_charges → totals/GL include 5110/AP. |
| **Twin check** | **N** |

---

### PUR-010
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Frontend |
| **Location** | `web/src/api/legacy/purchases.ts` `completePurchaseCreditNote` / debit; `PurchaseNoteEditorPage.tsx` |
| **Type** | Client abuse / retry |
| **Severity** | **Medium** |
| **What's wrong** | Note complete POSTs without Idempotency-Key. Invoice/return/payments use `userGestureIdempotencyKey()`. |
| **Trigger** | Slow network + double submit on note editor / list complete. |
| **Consequence** | Amplifies PUR-001; poor recovery vs purchase bill complete. |
| **Code evidence** | `apiClient.post(.../complete/)` — no key option. |
| **Suggested fix** | Pass gesture key like returns. |
| **Test to add** | E2E double-complete note → single document/JE. |
| **Twin check** | **N** if Sales note UI sends keys |

---

### PUR-011
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Docs vs product |
| **Location** | `web/src/pages/help/faqContent.tsx` (~L691, L706–711); vs `PurchaseService._assert_import_bill_of_entry`, BoE UI |
| **Type** | Stale guidance / operator error |
| **Severity** | **Medium** |
| **What's wrong** | FAQ: foreign/import “not supported yet” / “hard block.” Code: NON_GST + completed BoE path + `/purchases/bills-of-entry`. |
| **Trigger** | First import customers follow help → avoid real flow or invent workarounds. |
| **Consequence** | Support load; incorrect GSTIN hacks; missed BoE ITC. |
| **Code evidence** | FAQ vs `test_r024_import_complete_requires_this_invoice_boe`. |
| **Suggested fix** | Rewrite FAQ to BoE → NON_GST link → Complete. |
| **Test to add** | Doc/help snapshot or content test for import keywords. |
| **Twin check** | **N** |

---

### PUR-012
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Bill import |
| **Location** | `imports/services.py` `BillImportService._commit_purchase` (~L2894–2918) |
| **Type** | Inference / classification |
| **Severity** | **Medium** |
| **What's wrong** | All lines 0% GST → `purchase_type=NON_GST`. Exempt GST bills (still GST docs) and composition can be mis-typed. RCM inference for unregistered is set on draft (good) but type flip is aggressive. |
| **Trigger** | OCR/import of nil-rated GST tax invoice or composition bill of supply. |
| **Consequence** | Wrong register/GSTR class; Complete composition checks may not run as GST. |
| **Code evidence** | `all_zero → NON_GST` + note string; not user-confirmed. |
| **Suggested fix** | Default GST + preview confirm for “all zero → NON_GST”; or supplier taxpayer_type–driven. |
| **Test to add** | 0-rate REGULAR supplier → stays GST unless confirmed. |
| **Twin check** | Check sales bill import — likely similar (**Y** if same helper) |

---

### PUR-013
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Bill import commit semantics |
| **Location** | `BillImportService.commit` / `_commit_purchase` |
| **Type** | Partial commit / re-commit (checklist) |
| **Severity** | **Low** (behavior note; not a defect if intentional) |
| **What's wrong** | Bill commit is **all-or-nothing** in one atomic (any line error aborts). Re-commit of same job blocked by `PREVIEWED`→`COMMITTED`. Creates **draft** only (Complete separate) — good. No row-level partial draft. |
| **Trigger** | Mixed good/bad lines; retry committed job. |
| **Consequence** | Operators must fix all lines; cannot partial-post a bill. Masters CSV partial differs. |
| **Code evidence** | Raises on missing qty/rate; `job.status = COMMITTED` after success. |
| **Suggested fix** | Document; optional “commit valid lines only” if product wants it. |
| **Test to add** | Already partly covered by purchase bill import tests — assert no draft on mid-commit failure. |
| **Twin check** | **Y** (sales bill same service) |

---

### PUR-014
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Debit note vs inventory |
| **Location** | `PurchaseNotesService.complete_debit_note` |
| **Type** | Incomplete exact reversal / cost amend |
| **Severity** | **Medium** |
| **What's wrong** | DN posts AP/inventory GL only. No stock qty/layer restamp for price uplift (unlike H9 purchase amend `restamp_fifo_layers_for_price_amend`). |
| **Trigger** | Supplier additional debit for rate difference after goods received. |
| **Consequence** | Layers stay cheap; GL inventory up → valuation split. |
| **Code evidence** | DN complete → `post_note` only. |
| **Suggested fix** | Policy: restamp layers or keep DN as AP-only and never touch 1400 for pure price DNs. |
| **Test to add** | DN after purchase → layer vs 1400 policy assertion. |
| **Twin check** | **Y** if sales DN also GL-only for price |

---

### PUR-015
| Field | Detail |
|--------|--------|
| **Module** | Purchase / BoE cancel |
| **Location** | `BillOfEntryService.cancel` |
| **Type** | Orphan linkage |
| **Severity** | **Medium** |
| **What's wrong** | Cancel reverses BoE JE even if completed purchases still link `bill_of_entry`. No check for linked completed imports. |
| **Trigger** | Complete BoE → complete import → cancel BoE. |
| **Consequence** | Import ITC/customs AP reversed while goods/AP from purchase remain; GSTR-3B 4(A)(5) vs books diverge. |
| **Code evidence** | Cancel only checks BoE status + period; no `purchase_invoices` filter. |
| **Suggested fix** | Block cancel if linked non-cancelled purchases; or require unlink. |
| **Test to add** | Linked completed purchase → BoE cancel → 400. |
| **Twin check** | **N** |

---

### PUR-016
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Return UX & qty |
| **Location** | `PurchaseReturnItem` (no `unit_name`); `complete_return` `_item_stock_qty` uses invoice unit map; `_returned_quantities` compares raw qty |
| **Type** | Unit / exact reversal risk |
| **Severity** | **Medium** |
| **What's wrong** | Return lines lack unit snapshot; stock converts via invoice unit, headroom compares document qty. Alternate-unit products are ambiguous if UI/API send base qty. |
| **Trigger** | Invoice in cartons; return qty entered as pieces (or reverse). |
| **Consequence** | Over/under stock return vs billed qty; auto CN amounts wrong. |
| **Code evidence** | `PurchaseItem.unit_name` exists; `PurchaseReturnItem` has no unit fields; `_invoice_unit_name_by_product`. |
| **Suggested fix** | Snapshot unit on return lines; headroom in base units. |
| **Test to add** | Alternate-unit purchase → return in base → reject or convert correctly. |
| **Twin check** | Check sales return line units — **?** |

---

### PUR-017
| Field | Detail |
|--------|--------|
| **Module** | Purchase / List filters |
| **Location** | `PurchaseReturnViewSet.get_queryset`; `BillOfEntryViewSet.get_queryset` |
| **Type** | Input validation / abuse |
| **Severity** | **Low** |
| **What's wrong** | Status/supplier query params passed raw; invoice list validates status enum and int supplier (R-038). |
| **Trigger** | `?status=nope` or non-numeric supplier. |
| **Consequence** | Empty/odd results or DB errors vs clean 400 on invoices. |
| **Code evidence** | Invoice view validates; return/BoE do not. |
| **Suggested fix** | Same R-038 pattern. |
| **Test to add** | Bad status → 400. |
| **Twin check** | **N** vs purchase invoices; sales returns may share gap (**Y** if so) |

---

### PUR-018
| Field | Detail |
|--------|--------|
| **Module** | Payments / Supplier payment (purchase checklist) |
| **Location** | `PaymentService.allocate_supplier_payment`; `PaymentAllocationSerializer.__init__`; `create_supplier_payment` |
| **Type** | Wrong-supplier / tenancy (mitigated) |
| **Severity** | **Low** (service-hardened) |
| **What's wrong** | Allocation serializer scopes FKs by company; service requires `payment.supplier_id == purchase_invoice.supplier_id` + `select_for_update`. SupplierPayment ModelSerializer supplier FK is default (unscoped) but create checks `supplier.company_id`. |
| **Trigger** | Cross-tenant / cross-supplier IDs without RLS. |
| **Consequence** | With RLS+service checks, wrong-supplier alloc rejected. Residual: unscoped serializer resolve before service on non-RLS. |
| **Code evidence** | `allocate_supplier_payment` L452–455; serializer company filter L173–180. |
| **Suggested fix** | `CompanyPrimaryKeyRelatedField` on SupplierPayment.supplier / bank_account for defense in depth. |
| **Test to add** | Cross-company supplier id on payment create → 400; alloc mismatched supplier → 400 (likely exists). |
| **Twin check** | **Y** (receipt/customer same pattern) |

---

### PUR-019
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Feature flags |
| **Location** | `core/services/feature_flags.py`; purchase views |
| **Type** | Architecture invariant check |
| **Severity** | **Info** |
| **What's wrong** | Core Purchase is not a dark module; gated by roles + `SubscriptionWritesAllowed` (except PUR-008). `ENABLE_TDS` gates UI TDS fields. ITC/2B gates are code-level, not flags. |
| **Trigger** | N/A |
| **Consequence** | No silent “purchases module off” — OK if intentional; ensure plan modules don’t need a purchase key. |
| **Code evidence** | `DARK_MODULE_KEYS` = manufacturing/payroll/CRM only. |
| **Suggested fix** | Confirm billing plans; fix PUR-008. |
| **Test to add** | Plan without purchases write → blocked via subscription permission. |
| **Twin check** | **Y** (Sales same model) |

---

### PUR-020
| Field | Detail |
|--------|--------|
| **Module** | Purchase / Complete atomicity (audit) |
| **Location** | `PurchaseService.complete` |
| **Type** | Positive control / residual ordering |
| **Severity** | **Info** (mostly OK) |
| **What's wrong** | Path: `select_for_update` → gates → number → status COMPLETED → period assert → serials/batches → `post_movement` → `PostingService.post_purchase` → emit — all one atomic. Matches sales “stock+money together.” Period after number is fine (series row locked in same tx). Opening skips stock+normal post. |
| **Trigger** | Normal complete / mid-loop stock failure. |
| **Consequence** | Failure rolls back number+stock+JE. Residual: confirms collected before period (same as sales). |
| **Code evidence** | `@transaction.atomic` + order above. |
| **Suggested fix** | None for atomicity; keep CN/DN and freight policies aligned (PUR-001–004). |
| **Test to add** | Inject stock failure mid-complete → draft unchanged, no JE (if not already). |
| **Twin check** | **Y** (Sales same structure) |

---

## Purchase coverage notes

**Traced Complete path:** `PurchaseInvoiceViewSet.complete` → `wrap_idempotent(purchase_invoice_complete)` → `PurchaseService.complete` → stock PURCHASE movements (+ serial/batch) → `PostingService.post_purchase` → events. No separate GRN. Company scoping on invoice FKs via validators + `CompanyPrimaryKeyRelatedField` for BoE/products.

**Traced Return path:** `PurchaseReturnViewSet.complete` → `purchase_return_complete` → `complete_return` → qty headroom → PURCHASE_RETURN / damaged ADJUSTMENT + layer retire → auto `PurchaseCreditNote` → `complete_credit_note` (AP). Cancel restores stock and cancels linked CN.

**Idempotency vs `MONEY_IDEMPOTENCY_SCOPES`:** Covered: `purchase_invoice_create/complete`, `purchase_return_create/complete`, `bill_of_entry_create/complete`, `import_job_commit`, `supplier_payment_create`, `allocation_create`. **Gaps:** purchase CN/DN complete (PUR-001/002).

**Bill / BoE import:** validate→preview→commit present; bill commit → draft + RCM inference; ITC: invoice `assert_claimable_itc_allowed` (2B MATCHED); BoE `_assert_boe_import_itc_reconciled` (ICEGATE / 2B). Re-commit blocked; no partial bill lines.

**Supplier payment:** Party match + locks + outstanding caps look sound (PUR-018 residual serializer hardening).

**Highest release blockers:** PUR-001, PUR-002, PUR-003, PUR-004, PUR-005, PUR-007, PUR-008.
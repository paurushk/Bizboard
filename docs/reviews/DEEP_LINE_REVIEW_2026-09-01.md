# Bizboard — Exhaustive Line-by-Line Code Review (2026-09-01)

Reviewer: Cursor Grok 4.6 · Method: read current source (including uncommitted
working tree). No assumptions. Goal: log every verified bug, defect, gap,
broken flow, partial feature, UI/UX issue, and improvement so the quality
picture is visible.

**Severity:** `P0` data/money loss, security, or hard crash on a real path ·
`P1` wrong output / broken flow · `P2` correctness-edge / missing validation /
race · `P3` maintainability · `UX` user-facing friction · `SUGG` improvement.

**Coverage:** `core`, `accounts`, `sales`, `purchases`, `payments`, `reporting`,
`inventory`, `accounting`, `manufacturing`, `payroll`, `banking`, `masters`,
`imports`, `insights`, `billing`, `crm`, `integrations/tally`, `ledgers`,
`config`, `web/src` (pages, components, offline, i18n, permissions), `mobile`
(Capacitor stub only). Migrations and generated OpenAPI types were scanned
for constraints, not restated line-by-line.

**Counts (this pass):** 16 P0 · 92 P1 · 118 P2 · 41 P3 · 48 UX · 22 SUGG
≈ **337 logged findings**. Highest-risk clusters are called out first.

---

## 0. Fix-first cluster (do these before more features)

| # | Sev | Loc | Finding |
|---|---|---|---|
| 0.1 | P0 | `accounts/views.py:377-381` | Cookie refresh catches `TokenError` from `old.blacklist()` and **still mints new access+refresh**. A replayed/stolen already-blacklisted refresh gets a fresh session. Rotation is fail-open. |
| 0.2 | P0 | `payments/tasks.py:28-29,71-74` | `execute_gateway_refund` no-ops on `IN_PROGRESS`. The retry job re-queues stale `IN_PROGRESS` rows, which immediately return. Crash after books unwind + status flip → **gateway refund stuck forever**; customer remains charged. |
| 0.3 | P0 | `manufacturing/services.py:303-320` + `inventory/services.py:477-484` | WO cancel restores components via `ADJUSTMENT`/`work_order_cancel`. That reference is in `cancel_restore`, so `_apply_cost_layers` **skips layer create** and `restore_fifo_peels` is never called. FIFO tenants lose cost layers while on-hand recovers → later COGS/valuation wrong. |
| 0.4 | P0 | `manufacturing/services.py:211-221` | `BatchLot.objects.get_or_create(..., defaults={"mrp": ...})` — `BatchLot` has **no `mrp` field**. Completing a batch-tracked FG work order **TypeError**s. |
| 0.5 | P0 | `accounting/views.py:206-210` | Recon session: `aggregate(d=Sum("debit"), c=Sum("credit"))` then reads `gl["debit"]`/`gl["credit"]`. Keys are `d`/`c` → **KeyError 500** on create. UI cannot open a bank-recon session. |
| 0.6 | P0 | `integrations/tally/adapter.py:406-526` | `commit_tally_preview` has **no `transaction.atomic`**. Mid-run failure can leave partial masters/stock/AR/AP then still mark `COMMITTED`. |
| 0.7 | P0 | `web/.../useInvoiceOffline.ts:26-36` vs `OfflineOutboxPage.tsx:78-95` | Auto-flush of invoice drafts only `create`/`update` — **never Completes**. Manual Sync Now honors `completeIntent`. Same draft, two behaviors: offline Complete becomes a durable draft and the outbox entry is removed. |
| 0.8 | P0 | `core/idempotency.py:271` | `wrap_idempotent` **stores 5xx** as the idempotency result. Retry with the same key replays the cached 500 forever. Pre-commit transient 500 bricks the operator until they mint a new key. |
| 0.9 | P0 | `core/events.py:24-26` | `emit()` has **no try/except** and runs inside Complete's DB transaction. A failing handler rolls back the **entire invoice/purchase Complete**. |
| 0.10 | P0 | `core/services/files.py:97-98` | Any file starting with `PK` is sniffed as XLSX. ZIP-bomb / `.docx` reach `openpyxl` with no decompression-ratio guard via import. |
| 0.11 | P0 | `core/services/bill_images.py:43-51` | `Image.open(); image.load()` with **no `MAX_IMAGE_PIXELS`**. Pillow decompression-bomb is a Warning, not Exception — crafted PNG OOMs the OCR/import worker. |
| 0.12 | P0 | `core/services/document_numbers.py:248-279` | `configure()` allows `next_number` ≥ 1 **including already-used** values → duplicate GST invoice numbers (filing violation). |
| 0.13 | P0 | `core/exceptions.py:131-145` | Catching `IntegrityError` returns 400 **without `transaction.set_rollback(True)`**. Next query on an aborted Postgres connection → confusing later 500. |
| 0.14 | P0 | `core/services/sms.py:41-83` | MSG91 HTTP 200 treated as success even when body is `{"type":"error"}`. User sees "OTP sent" when nothing was delivered. |
| 0.15 | P0 | `purchases/services.py:1172-1187` | Purchase-return cancel always transitions serials `SCRAPPED→AVAILABLE`. Complete path sets sellable returns to `RETURNED`. Cancelling a non-damaged serial return fails or corrupts serial state. |
| 0.16 | P0 | `accounts/models.py:241-264` | `CompanyGstin` has **no unique/partial constraint** for a single `is_primary=True`. Numbering and GSTR stamp can flip between two "primary" branches. |

---

## 1. `backend/core/`

### 1.1 Tax / billing engine

| # | Sev | Loc | Finding |
|---|---|---|---|
| 1.1.1 | P3 | `billing.py:160-180` | `is_intra_state` docstring says blank party → True; code returns **False**. |
| 1.1.2 | P2 | `billing.py:128-130` | `extract_state_code` trusts any 15-char string whose first 2 chars are digits. |
| 1.1.3 | P2 | `billing.py:405-412` | `apply_effective_gst_rate` silently overwrites user-entered `gst_rate` from HSN catalog with no warning. |
| 1.1.4 | P3 | `billing.py:389-396` | Rate-override audit uses `entity_id=""` on unsaved lines. |
| 1.1.5 | P2 | `billing.py:258` | Inclusive price `0` treated as "not set" → falls back to exclusive `unit_price`. |
| 1.1.6 | P3 | `billing.py:717-720` | `recompute_totals_for_stamped_gstin` bulk-updates even when totals unchanged. |
| 1.1.7 | SUGG | `billing.py:186-193` | CGST/SGST split can differ by ₹0.01 on odd-paise tax. |
| 1.1.8 | P3 | `billing.py:276,281` | Inclusive amounts stashed as private attrs on ORM instances — fragile. |
| 1.1.9 | P2 | `billing.py:749-762` | Totals preview has no `status` → treated as live doc; HSN rate swap can differ from typed rate. |
| 1.1.10 | P2 | `billing.py:800-811` | Preview TCS always from `tcs_rate`, ignores explicit `tcs_amount` (Complete path: amount wins). |

### 1.2 Permissions / middleware / RLS

| # | Sev | Loc | Finding |
|---|---|---|---|
| 1.2.1 | P1 | `permissions.py:34,43,68` | `get_company_user()` raises from inside `has_permission()`; middleware swallows → RLS GUC `None`. |
| 1.2.2 | P2 | `permissions.py:221-226` | `DenyViewerWrite` allows all GET before company check. |
| 1.2.3 | P2 | `permissions.py:278-286` | `CanManageFileAssets` GET: any sales/purchase creator can download **all** company files. |
| 1.2.4 | P3 | `permissions.py` | Role checks are string literals (`"OWNER"`), not an enum. |
| 1.2.5 | P3 | `permissions.py:46-68` | `CompanyRequired` does not cache → membership queried 3× per request. |
| 1.3.1 | P2 | `middleware.py:24-27` | Access-log IDs are unsalted `sha256(pk)[:12]` — reversible for small ints. |
| 1.3.2 | P3 | `middleware.py:41-50` | No try around `get_response` → `NameError` can mask original error. |
| 1.3.3 | P2 | `middleware.py:110-120` | RLS on + `get_company_user` raise → `set_rls_company(None)`. Fail-mode undefined. |
| 1.3.4 | P2 | `middleware.py:127-131` | Clearing RLS GUCs swallows exceptions — pooled connection can retain prior tenant. |
| 1.3.5 | P3 | `middleware.py:101-109` | Cookie JWT decoded twice per request when RLS is on. |

### 1.3 Idempotency / exceptions / models

| # | Sev | Loc | Finding |
|---|---|---|---|
| 1.4.2 | P2 | `idempotency.py:120-133` | Stale in-flight takeover has no heartbeat — slow original + retry → double-create. |
| 1.4.3 | P2 | `idempotency.py:131-155` | No prune job; `IdempotencyRecord` grows forever. |
| 1.4.4 | P3 | `idempotency.py:199-208` | 403 classified as transient 4xx → key released. |
| 1.4.5 | P2 | `idempotency.py:177-186` | `store_record` race can raise uncaught `IntegrityError`. |
| 1.5.2 | P2/UX | `exceptions.py:173-190` | Nested serializer errors render as raw Python repr in `message`. |
| 1.5.3 | P3 | `exceptions.py:160-170` | Unhandled 500 always `details: None` even in DEBUG. |
| 1.5.4 | P3 | `exceptions.py:108-124` | Field `ValidationError` code collapses to `"invalid"`. |
| 1.6.1 | P2 | `models.py:75-92` | Line validators not enforced by `bulk_create` (sales `_build_items`). |
| 1.6.2 | P2 | `models.py:144-173` | `AuditEvent.action` choices vs free-form dotted strings. |
| 1.6.4 | P2 | `models.py:185-206` | `FileAsset` no soft-delete; Django does not delete storage blobs. |
| 1.6.5 | P2 | `models.py:208-234` | `Notification.recipient` plaintext PII, no retention. |
| 1.6.6 | P2 | `models.py:236+` | "Append-only" audit tables have no DB trigger blocking UPDATE/DELETE. |
| 1.7.2 | P2 | `document_numbers.py:331-344` | `SELECT FOR UPDATE` held for entire Complete — POS throughput ceiling. |
| 1.7.3 | P2 | `document_numbers.py:184-206` | `_max_existing_seq` is O(n) regex per row. |
| 1.7.4 | P2 | `document_numbers.py:77-82` | Company with no GSTIN later adding one silently starts a new series. |
| 1.7.5 | P3 | `document_numbers.py:33-34` | Internal vouchers (JE, stock transfer) get FY/GSTIN scoping. |

### 1.4 Auth, files, flags, notifications, GSP

| # | Sev | Loc | Finding |
|---|---|---|---|
| 1.8.1 | P3 | `authentication.py:24-30` | CSRF-skip Bearer path keyed on env label; `prod`/`uat` silently skip CSRF. |
| 1.9.5 | P2 | `csv_utils.py:14-16` | Negative `Decimal` amounts get anti-formula `'` prefix → CSV numeric parse breaks. |
| 1.9.6 | P2 | `charges.py:24-63` | Synthetic freight line has no `product` — GSTR/e-invoice builders that touch `item.product.name` crash. |
| 1.9.7 | P2 | `viewsets.py:17-21` | `SubscriptionWritesAllowed` appended to list/retrieve too. |
| 1.9.8 | P2 | `viewsets.py:44-47` | `perform_destroy` audits after delete with pk only — no snapshot. |
| 1.9.11 | P3 | `validators.py:70-76` | `validate_gst_rate` `Decimal(value)` can raise `InvalidOperation` → 500. |
| 1.10.2 | P2 | `files.py:129-165` | ClamAV reads entire file before cheap MIME/size reject; also run twice from `FileAssetViewSet`. |
| 1.10.3 | P2 | `files.py:214,231` | `original_name` stored unsanitised. |
| 1.11.1 | P1 | `feature_flags.py:104-109` | `plan_modules_for_company` exceptions → plan gates **fail open**. |
| 1.11.3 | P3 | `feature_flags.py:63-64` | `user.is_staff` forces Help v2 in customer tenants. |
| 1.12.1 | P2/UX | `place_of_supply.py:70-89` | Unknown POS + assume-local off → draft preview shows **IGST** for local walk-in. |
| 1.13.1 | P1 | `h9_amend.py:99-120` | Header-only amend omits serials / supply_nature / rate_override. |
| 1.13.2 | P2 | `h9_amend.py:8-96` | Two-line same-product pairing disagrees between allowlist and price-unchanged. |
| 1.13.3 | P2 | `h9_amend.py:55-62` | Amend allowlist does not re-check cess. |
| 1.14.1 | P2 | `notifications.py:37-39` | Post-`.delay()` refresh still `QUEUED` in prod. |
| 1.14.2 | P2 | `notifications.py:60-64` | `wa.me` fallback embeds payment-link token in `?text=`. |
| 1.16.2 | P1 | `sms.py:41-68` | MSG91 v5 OTP may generate its own OTP ≠ hashed code we stored → login broken with a real MSG91 account. |
| 1.16.3 | P2 | `sms.py:85-109` | Twilio India path has no DLT template; carriers drop, UI says sent. |
| 1.17.1 | P2 | `whatsapp.py:137-142` | Sync Graph POST up to 30s on request path. |
| 1.17.2 | P2 | `whatsapp.py:132` | Language hardcoded `"en"` — Hindi-approved templates rejected. |
| 1.19.1 | P2 | `gstin_verify.py:133-140` | Non-VALID lookup **wipes** `gstin_verified_at`. |
| 1.20.1 | P2 | `views.py:110-176` | `HealthView ?ready=1` is AllowAny, unthrottled, Celery inspect broadcast. |
| 1.20.3 | P2 | `views.py:302-315` | Metrics open if env not exactly production/staging and token empty. |
| 1.21.2 | P2 | `core/models.py` | Only `HelpEvent` is pruned; Notification/Idempotency/Audit grow unbounded. |
| 1.23.1 | P2 | `gsp_secrets.py:38-49` | Fernet `InvalidToken` → `{}` silently; e-invoice/WhatsApp die with no alert. |
| 1.28 | P2 | `help_views.py:69-79` | `_latest_ratings` materializes all ratings; no row cap. |
| 1.29 | P2 | `help_views.py:139-193` | Help events accept arbitrary `name` (length only). |
| 1.41 | UX | `help_views.py:221-232` | Non-owner GET `/help-feedback/` returns empty results instead of 403. |

---

## 2. `backend/accounts/` + `config/`

| # | Sev | Loc | Finding |
|---|---|---|---|
| A02 | P1 | `otp_utils.py:28-41` + `views.py:508` | Phone unique is raw string; `+91…` and `98…` can both exist. OTP verify `.order_by("id").first()` can log in the **wrong user**. |
| A03 | P1 | `views.py:825-827` vs `915-929` | Seat limit checked on invite create, **not** on accept. Flood pending invites then accept → exceed plan seats. |
| A04 | P1 | `views.py:951-952` | Soft-deleted members cannot be re-invited (existing `CompanyUser` treated as member). |
| A05 | P1 | `views.py:354-390` | Refresh only checks `user.is_active`, not active membership. Deactivated staff keep rotating cookies. |
| A06 | P1 | `views.py:448-453` | New OTP does not invalidate prior challenges — stacked brute-force windows. |
| A07 | P1 | `views.py:1134-1140` | SMTP failure on **found** user → 500; unknown identifier → 200. Password-reset existence oracle. |
| A08 | P1 | `views.py:811-824` | Outside prod/staging, invite accept can proceed without password if omitted. |
| A09 | P1 | `config/celery.py:122-132` | Tasks without `company_id` resolve company while RLS GUC empty → silent no-op under RLS. |
| A10 | P1 | `tenant_backup.py:444-502` vs export | Wipe deletes quotations/orders/notes/returns; **export does not include them**. Destroy-in-place restore drops those docs. |
| A11 | P1 | `tenant_backup.py:32-44,830-847` | Export skips logo/signature FKs; restore recreates FileAssets with new PKs — branding broken. |
| A12 | P1 | `tenant_backup.py:174-176` | Sales/purchase items drop `batch_id` on export/import. |
| A13 | P2 | `models.py:81-82` | `registration_type` defaults REGULAR with blank GSTIN allowed. |
| A14 | P2 | `serializers.py:127` | Owners can PATCH `ai_features_enabled` with no billing gate. |
| A15 | P2 | `serializers.py:115-145` | `books_start_date` / `doc_number_scope` on model, **absent from CompanySerializer**. Partial feature. |
| A16 | P2 | `views.py:471-516` | OTP-only users (`has_usable_password` false) mapped to `OtpExpiredError` — passwordless path dead. |
| A17 | P1 | `views.py:300-309` | Correct password + inactive membership returns a **distinct** message vs wrong password (login enumeration). |
| A18 | P2 | `views.py:206-216` | Login/OTP counters `incr` without refreshing TTL. |
| A19 | P2 | `views.py:1111-1129` | Password-reset JTI created before `FRONTEND_URL` check. |
| A20 | P2 | `serializers.py:450-482` | Primary GSTIN clear+create not atomic. |
| A21 | P2 | `views.py:915-929` | Seat check TOCTOU. |
| A22 | P2 | `export_views.py:86-104` | Failed restore still rate-limits the company 10 minutes. |
| A23 | P2 | `tenant_backup.py:501` | Wipe never deletes `Warehouse` rows. |
| A24 | P2 | `tenant_backup.py:161-164` | Product export strips category/brand/unit FKs. |
| A25 | P2 | `serializers.py:135` | `payroll_pt_slabs` free-form JSON, no shape validation. |
| A26 | P2 | `serializers.py:137-138` | Dunning quiet hours have no 0–23 validation. |
| A27 | P2 | `serializers.py:382-400` | Invite omits AI capability flags. |
| A33 | P2 | `config/settings.py:601-613` | `REQUIRE_SUBSCRIPTION` defaults True only in `DJANGO_ENV==production`. Staging writes ungated. |
| A36 | P3 | `views.py:393-411` | Logout requires auth; expired access cannot blacklist refresh. |
| A38 | P3 | `password_validation.py:11-18` | "Breached password" is a tiny local frozenset, not HIBP. |
| A40 | P3 | `core/celery_utils.py:8-18` | `safe_delay` swallows broker failures — PDFs/emails silently never enqueue. |
| A42 | UX | `onboarding.py:53-55` | Blocking step can be `catalog` while `ui_step` is `payments`. |
| A43 | UX | `views.py:439-467` | OTP request returns success payload even when SMS failed and challenge deleted. |
| A46 | SUGG | `tenant_backup.py:145-273` | Full export built in memory then Fernet-encrypted — OOM risk. |
| A50 | P2 | `views.py:287-342` | Login sets auth cookies with no CSRF (SameSite=Lax only). |

---

## 3. `backend/sales/` + `purchases/`

| # | Sev | Loc | Finding |
|---|---|---|---|
| S02 | P1 | `sales/serializers.py:113-134,266-282` | `filing_party_gstin` / `filing_place_of_supply` writable on COMPLETED and **not** in H9 `money_fields`. Bypasses Owner-only `amend-filing-identity`. |
| S03 | P1 | `sales/serializers.py:266-270,332-340` | `tcs_rate` / `tcs_amount` / `is_reverse_charge` / `supply_type` / `company_gstin` changeable on COMPLETED without `confirm_amend` or GL re-post. |
| S04 | P1 | `einvoice_payload.py:424-427` | Note status guard is dead: `getattr(note.status, "COMPLETED", note.status)` on a string always equals `note.status`. Draft CN/DN can prepare/submit IRN. |
| S05 | P1 | `return_service.py:324-326` | Cancel one sales return always sets invoice `RETURNED→COMPLETED` even if other returns still cover qty. |
| S06 | P1 | `purchases/services.py:1243-1245` | Same bug on purchase-return cancel. |
| S07 | P1 | `pdf/gst_tax_invoice.py:99-536` | GST tax invoice PDF never prints **TCS** or **place of supply** (Rule 46). |
| S08 | P1 | `pdf/gst_tax_invoice.py:107-161` | Seller GSTIN uses stamp; address always HO `_company_address`. Multi-GSTIN branch invoice shows wrong address vs IRN. |
| S09 | P1 | `purchases/pdf.py:235-239` | Looks for `supplier_invoice_number` / `reference`; model field is `supplier_bill_number`. Supplier bill never appears. |
| S10 | P1 | `return_service.py:230-231` | `getattr(sales_return, "is_damaged", False)` — field does not exist; damage is per-line. Scrap GL never runs. |
| S11 | P1 | `notes_services.py:540-571` | SO→challan marks order CONVERTED without releasing reservations; draft challan leaves stock reserved; `cancel_sales_order` rejects CONVERTED. |
| S12 | P1 | `sales/services.py:616-618` + serializers | H9 amend: `set_items` reverses all POSTED incl. COGS then serializer reverses COMPLETE again. Double reverse; COGS lost if `set_items` used alone. |
| S13 | P1 | `purchases/services.py:404-407` | Same double reverse/repost on purchase H9. |
| S14 | P1 | `purchases/serializers.py:194-197` | `tds_rate`/`tds_amount` writable on COMPLETED, not in `money_fields`. |
| S15 | P1 | `sales/services.py:803-809` vs notes | Invoice Complete only **warns** on missing HSN even when e-invoice on; CN Complete **hard-blocks**. |
| S16 | P1 | `einvoice_eway_actions.py:365-397` | `submit-eway` has no atomic claim — concurrent double GSP call. |
| S17 | P1 | `einvoice_eway_actions.py:640-692` | Note IRN submit has no QUEUED claim. |
| S18 | P2 | `einvoice_eway_actions.py:594-607` | Challan `cancel-eway` skips sandbox GSP assert. |
| S19 | P2 | `sales/views.py:100-110` | `submit_einvoice_async` / `amend_filing_identity` not in Owner permission list. |
| S20 | P2 | `sales/tasks.py:75-78` | CN/DN PDF tasks accept `company_id` but never filter by it. |
| S21 | P2 | `notes_services.py:648-653` | Challan Complete numbers via primary GSTIN only — `DeliveryChallan` has no `company_gstin`. |
| S22 | P2 | `notes_services.py:493-507` | SO→invoice drops cess, supply_nature, HSN; SO items have no batch/serial. |
| S23 | P2 | `purchases/notes_services.py:437-447` | PO→purchase drops cess, HSN, batch, serials, inclusive price. |
| S24 | P2 | `sales/services.py:1196-1223` | Quotation→invoice drops warehouse, charges, discounts, supply_type, company_gstin, payment terms. |
| S25 | P2 | `purchases/services.py:1091-1151` | Auto purchase CN never carries `additional_charges` — freight bills leave AP residue. |
| S26 | P2 | `return_service.py:196-212` | Auto sales CN copies `cess_rate` not `cess_amount`. |
| S27 | P2 | `einvoice_payload.py:439-523` | Note e-invoice keeps invoice BuyerDtls/TranDtls; note `filing_*` overlays ignored. |
| S28 | P2 | `eway_payload.py:301,307` | Invalid state codes become `0` instead of failing. |
| S29 | P2 | `irn_guard.py:5-15` | `LIVE_IRN` only GENERATED/MANUAL_IRN — IRN present with other status does not block books cancel. |
| S30 | P2 | `sales/serializers.py:79-81` | Line `hsn_code` is read_only — cannot set HSN on create. |
| S31 | P2 | `purchases/pdf.py:243-269` | Uses nonexistent `place_of_supply`; billed-to GSTIN always `company.gstin`. |
| S32 | P2 | `purchases/views.py:190-204` | Purchase PDF has no COMPLETED gate — drafts downloadable. |
| S33 | P2 | `sales/views.py:533-547` | Return number-series peek omits GSTIN vs Complete's GSTIN-scoped series. |
| S35 | P2 | `phase1_views.py:84-89` | View complete re-calls `PostingService.post_note` after service already posted. |
| S37 | P2 | `sales/services.py:70-127` | TCS base excludes additional charges / round-off. |
| S39 | P2 | `cogs_service.py:102-128` | Challan-stocked invoice COGS can fall back to current WAVG when challan `unit_cost` is 0. |
| S40 | P2 | `einvoice_eway_actions.py:304-309` | Manual IRN `ack_date` via `parse_datetime` only — date-only portal strings → `None`. |
| S41 | P1 | `notes_services.py:779-833` | Cancel draft challan not supported — orphan reservations from SO convert. |
| S42 | UX | PDF TOTAL | Grand total with no TCS line — operators cannot see TCS on the statutory PDF. |

---

## 4. `backend/payments/`

| # | Sev | Loc | Finding |
|---|---|---|---|
| PAY-02 | P0 | `tasks.py:43-48` | Provider `adapter.refund()` outside row lock; no Razorpay idempotency key. Death after provider success + before SUCCEEDED → retry would double-refund if IN_PROGRESS is ever reset. |
| PAY-03 | P1 | `services.py:1173-1190` | Full refund of one capture on a multi-capture link always reopens the link, ignoring remaining CAPTURED payments. |
| PAY-04 | P1 | `services.py:892-909` | `prior_captured` ignores `CAPTURED_PENDING_BOOKS` → over-capture vs `link.amount`. |
| PAY-05 | P1 | `services.py:1129-1149` | Provider partial refunds logged on payload only; allocations/GL stay posted. |
| PAY-06 | P1 | `webhook_views.py:165-184` | Refund webhook on parked `CAPTURED_PENDING_BOOKS` returns 400; Razorpay retries forever. |
| PAY-07 | P1 | `services.py:614-630` | Open-link reserve check has no `select_for_update` — concurrent links oversubscribe outstanding. |
| PAY-08 | P1 | `views.py:290-292` | `ValidationError` **never imported** → NameError/500 on bad allocation payloads. |
| PAY-09 | P1 | `serializers.py:124-125` | `get_unallocated` uses `amount - allocated`; service headroom is `amount + tds_amount`. UI understates allocatable when TDS present. |
| PAY-10 | P1 | `views.py:794-820` | `create_receipt_from_line` then `_confirm_match`; already MATCHED → early return, **orphaned receipt**. |
| PAY-11 | P1 | `dunning.py:58-70` | Any CAPTURED / CAPTURED_PENDING_BOOKS skips dunning even when outstanding remains. |
| PAY-12 | P1 | `recon.py:179-188` | Bank debit scoring matches `payment.amount` not net-of-TDS outflow. |
| PAY-13 | P1 | `services.py:1192-1221` | Books unwind **before** provider confirms; failed outbox = customer charged, books refunded. |
| PAY-14 | P2 | `models.py:357-387` | ReconMatch unique on receipt/payment but no XOR that exactly one is set. |
| PAY-15 | P2 | `views.py:641-661` | Confirm-match TOCTOU → uncaught IntegrityError. |
| PAY-16 | P2 | `services.py:371-378` | Duplicate active allocation unique → 500 instead of BusinessRuleError. |
| PAY-17 | P2 | `gateway.py:261-293` | Razorpay parser ignores event type; partial `refund.*` often ignored. |
| PAY-18 | P2 | `gateway.py:349-351` | Cashfree uses `float(Decimal)` — paise drift. |
| PAY-19 | P2 | `services.py:636-666` | Provider link created before DB row — DB failure orphans live Razorpay link. |
| PAY-20 | P2 | `holding.py:113-122` | Any CAPTURED with remaining outstanding reports `PAID_PENDING_BOOKS` even when books posted and only allocation failed. |
| PAY-21 | P2 | `webhook_views.py:117-121` | Ambiguous `provider_link_id` → 409 forever, provider retries. |
| PAY-22 | P2 | `views.py:574-586` | Duplicate `line_hash` on bank upload → 500. |
| PAY-23 | P2 | `services.py:948-960` | Gateway finalize never bypasses period gate; closed period parks forever. |
| PAY-24 | P3 | `serializers.py:194-229` | PaymentLink list returns raw `token`. |
| PAY-25 | UX | `services.py:1265-1277` | Payment health cached 60s — stuck-refund alerts lag. |
| PAY-27 | P2 | `models.py:198-213` | Unique active alloc per receipt×invoice forces reverse+recreate to top up. |

---

## 5. `backend/reporting/` (GSTR / IMS / 2B)

| # | Sev | Loc | Finding |
|---|---|---|---|
| RPT-01 | P1 | `gst_returns.py:1391-1407` | 3.1(a) taxable uses `_non_rcm_sum` and **drops rchrg=Y** — understates outward taxable vs comment. |
| RPT-02 | P1 | `gst_returns.py:1041-1075` | ATADJ includes every allocation with `receipt_date <= invoice_date`, including same-day collections that are not advances. |
| RPT-03 | P1 | `gstr2b.py:106-107` | `claimable_itc_from_2b` strict-filters `company_gstin_id`; primary GSTIN under-claims 2B ITC vs NULL-stamp purchases. |
| RPT-04 | P1 | `ims.py:217-231` | Soft-close deems **all** `NO_ACTION` 2B rows ACCEPT, including MISSING_IN_BOOKS / mismatches. |
| RPT-05 | P1 | `views.py:758-774` | 2B upload has no unique `(company, period, supplier_gstin, invoice_number)` — re-upload **double ITC**. |
| RPT-06 | P1 | `gst_returns.py:1282-1286` | `itc.claimable = has_2b` if **any** 2B row exists, even zero MATCHED. |
| RPT-07 | P2 | `gst_returns_sections.py:267-279` | B2C small notes net into B2CS; CDNUR table omits them — CA packs look incomplete. |
| RPT-08 | P2 | `gst_returns.py:700-751` | Header outward totals exclude sales-RCM; section footing includes B2B rchrg=Y → `OUTWARD_FOOTING_MISMATCH`. |
| RPT-09 | P2 | `gst_returns.py:671-673` | Cancelled CN/DN filtered by note stamp; completed notes by invoice stamp. |
| RPT-10 | P2 | `gst_returns_sections.py:161` | B2CL vs B2CS uses `grand_total` (may include TCS) vs GSTN invoice-value semantics. |
| RPT-11 | P2 | `gstr2b.py:33` | 2B match is case-sensitive on invoice number. |
| RPT-12 | P2 | `gst_returns.py:983-1038` | Unallocated posted receipts treated as advances (incl. failed gateway allocation). |
| RPT-13 | P2 | `services.py:111-128` | Receivables aging recomputes outstanding instead of `LedgerService.sales_invoice_outstanding`. |
| RPT-14 | P2 | `ims.py:186-208` | `deemed_accept` not period-atomic — partial ACCEPT on mid-loop failure. |
| RPT-15 | P2 | `gst_periods.py:57-98` | Document Complete is warn-only on soft-closed periods; money allocate hard-blocks. |
| RPT-16 | P2 | `gstr2b.py:226-273` | GSTR-7/8/6 are honesty stubs (`supported: False`). Partial product. |
| RPT-17 | P3 | `gst_rate_scan.py:20` | Default `date_from=date(2025, 9, 1)` hardcoded. |
| RPT-19 | UX | `gst_returns.py:837-848` | SUPECOM Table 15 also in B2/3.1(a) — easy double-file. |

---

## 6. Inventory / accounting / manufacturing / payroll / banking / Tally

| # | Sev | Loc | Finding |
|---|---|---|---|
| MFG-01 | P1 | `manufacturing/services.py:100-181` | `release_work_order` no `select_for_update` — concurrent double-issue + double WIP GL. |
| MFG-02 | P1 | `manufacturing/services.py:184-256` | Same TOCTOU on complete → double FG receipt. |
| INV-04 | P1 | `inventory/services.py:1012-1014` | Transfer complete checks negative stock **without** `line.batch` then posts against the batch. |
| INV-05 | P1 | `inventory/services.py:111-119` | Negative-stock gate uses `available` (`on_hand - reserved`) but outbound does not always release reservations. |
| INV-06 | P1 | `inventory/views.py:335-351` | Serial `transition` sets `warehouse_id` from raw request with **no company ownership check** (IDOR). |
| INV-07 | P1 | `inventory/services.py:493-504` | Manual ADJUSTMENT inbound with `unit_cost=None` creates FIFO layers at **0**. |
| INV-08 | P1 | `inventory/services.py:748-768` | FEFO WARN shortfall parks remainder on **unbatched** balance. |
| ACC-02 | P1 | `accounting/views.py:212-231` | Bank recon `match`: no amount equality, statement not scoped to session, no unique on bank line, `reconciled_at` is `localdate()` into DateTimeField. |
| ACC-03 | P1 | `accounting/reports.py:335-348` | FY-close WIP check is **all-time company-wide**, not FY-bounded. |
| ACC-05 | P1 | `accounting/services.py:617-618` | Opening-stock JE date ignores `movement.movement_date`. |
| PR-01 | P1 | `payroll/services.py:220-233` | LOP prorates `base_gross`, then statutory prorates basic+DA again → **double-prorated PF**. |
| PR-02 | P1 | `payroll/services.py:106-120` | Dict `payroll_pt_slabs` missing state key → `DEFAULT_PT_SLABS`, skips `_STATE_PT_SLABS` (wrong MH/WB/TN PT). |
| PR-03 | P1 | `payroll/services.py:170-174` | ESI ceiling tested on already-prorated gross — LOP can incorrectly pull high earners into ESI. |
| TLY-01 | P1 | `tally/adapter.py:498-507` | Tally opening stock never calls `post_opening_stock` GL. |
| TLY-02 | P1 | `tally/adapter.py:275-284` | Opening AR/AP invents ±1 stock on `__TALLY_OPENING__` with `skip_negative_check`. |
| TLY-03 | P1 | `tally/adapter.py:512-525` | Marked COMMITTED even when recon checks fail (warnings only). |
| FF-02 | P1 | `billing/permissions.py:30-35` | Non-`APIException` from `get_company_user` → write gate **fail-open**. |
| BNK-01 | P1 | `banking/services.py:11-57` | AA↔receipt match has no row lock; concurrent ingest can double-attach. |
| CRM-01 | P1 | `crm/services.py:31-83` | Convert with `customer_id` set but status ≠ QUALIFIED always creates a **new** Opportunity. |
| LED-01 | P1 | `ledgers/services.py:309-327` | GL bulk outstanding does not floor per party; UI floors at 0 — Tally recon can disagree. |
| INV-09 | P2 | `inventory/services.py:84-109` | Opening uniqueness race surfaces as 500 IntegrityError. |
| INV-10 | P2 | `inventory/services.py:893-935` | FIFO seed skips zero/missing unit cost → silent qty gaps after WAVG→FIFO. |
| INV-12 | P2 | `inventory/views.py:392-402` | Expiry write-off checks `on_hand` not `reserved`. |
| ACC-06 | P2 | `accounting/services.py:1345-1349` | AR/AP control health tolerates ₹1 mismatch. |
| ACC-08 | P2 | `accounting/reports.py:288-311` | Idempotent FY-close replay still closes periods/GST returns. |
| PR-04 | P2 | `payroll/services.py:63-88` | PT slab validation is warnings only — never enforced. |
| PR-05 | P2 | `payroll/views.py:85-91` | LOP `paid_days` has no upper bound vs calendar days. |
| PR-07 | P2 | `payroll/services.py:253-284` | Employer PF/ESI mixed into salary expense 5800. |
| MFG-03 | P2 | `manufacturing/services.py:197-204` | Zero issue cost → FG cost from **purchase_price** × BOM, not layers. |
| MFG-04 | P2 | `manufacturing/services.py:64-70` | Lot allocation does not verify BatchLot belongs to the **component** product. |
| TLY-04 | P2 | `tally/adapter.py:84-91` | Any `PK` treated as xlsx; parse failure falls through to CSV. |
| TLY-05 | P2 | `tally/adapter.py:566` | Export silently truncates at 5000 invoices. |
| TLY-06 | P2 | `tally/adapter.py:447-456` | Customer `get_or_create` by **name only**. |
| TLY-08 | P2 | `tally/adapter.py:124` | Blank product gst_rate defaults to **18**. |
| HSN-01 | P2 | `masters/hsn_catalog.py:108-119` | Starter rates only seed 1905 and 2402; almost all HSN → `None`. |
| HSN-02 | P2 | `masters/hsn_catalog.py:86-102` | `search_hsn` is a static COMMON list, not GSTN. |
| IMP-01 | P1 | `imports/services.py:877-994` | XLSX fully materialized; no row/cell caps (zip-bomb within size limit). |
| IMP-02 | P2 | `imports/services.py` | Master CSV loops all rows with no hard max-row guard. |
| INS-01 | P2 | `insights/services.py:55-99` | Alert upsert has no uniqueness — duplicate open alerts. |
| INS-02 | P2 | `insights/services.py:298-316` | Margin uses master `purchase_price`, not FIFO/WAVG movement cost. |
| INS-04 | P2 | `insights/services.py:481` | Cashflow spreads collections evenly — ignores due-date spikes. |
| SUB-02 | P2 | `billing/services.py:56-74` | PENDING subscription can **block writes** before payment succeeds. |
| BIL-01 | P3 | `billing/models.py:49-65` | `ACTIVE` never checks `current_period_end` — relies on webhook. |
| CRM-02 | P2 | `crm/services.py:35-40` | Convert attaches to existing customer by phone/email without name confirm. |
| MST-01 | P3 | `masters/serializers.py:134-141` | Product validate auto-creates Unit/Category/Brand from free text — typos proliferate. |
| UX-05 | UX | recon UI | GL vs statement with GL always crashing/zero (0.5) → users chase phantom diffs. |

---

## 7. Frontend (`web/src`) — bugs, broken flows, ACL, i18n, UX

| # | Sev | Loc | Finding |
|---|---|---|---|
| F-002 | P0 | `OfflineOutboxPage.tsx:78-95` | Manual sync Completes; auto-flush on New Invoice does not (see 0.7). |
| F-003 | P1 | `NewPurchasePage.tsx:750-761` | Purchase offline queue never sets `completeIntent`; flush is draft-only. |
| F-004 | P1 | `permissions.ts:96-99` | FE `canViewPaymentSurfaces` = payments **or sales view**. BE is Owner / `can_create_payments` / financial reports. Sales staff hit 403 on receipts. |
| F-005 | P1 | `permissions.ts:118-126` | FE inventory view includes sales/purchase creators; BE stock APIs need inventory/financial flags. |
| F-006 | P1 | `permissions.ts:19-22` | FE manufacturing allows ACCOUNTANT / inventory managers; BE **IsOwner only**. |
| F-007 | P1 | `permissions.ts:24-27` | FE payroll allows ACCOUNTANT / financial-report; BE **IsOwner only**. |
| F-008 | P1 | `NewInvoicePage.tsx:1024-1039` | Preview **error zeros** subtotal/tax/grandTotal instead of last-good / client totals. |
| F-009 | P1 | `NewInvoicePage.tsx:1024-1035` | Preview `tcsAmount` / `amountDue` never bound; payable **understated** vs Complete. |
| F-010 | P1 | `NewInvoicePage.tsx:628-651` | "Mark fully paid" uses client `totals.grandTotal`, not preview/`amountDue`. |
| F-011 | P1 | `PosPage.tsx:662-788` | `checkout()` creates walk-in customers **before** `setBusy(true)`. Cash/UPI buttons disable on `busy` only — double-click → two customers / two invoices. |
| F-012 | P1 | `flushPosCheckout.ts:71-74` | Flush `paymentMode === 'UPI'` returns after Complete **with no receipt**. Offline UPI is blocked in UI, but any queued UPI draft completes unpaid. |
| F-013 | P1 | `invoiceDraftCache.ts:323-341` | `removeDraft` swallows IDB delete failure; merge then **resurrects** the draft. |
| F-014 | P1 | `NewInvoicePage.tsx:1153` | Unsaved-changes guard `when={lines.length > 0}` still true after successful save navigate. |
| F-015 | P1 | `OfflineOutboxPage.tsx:93-94` | Invoice complete on sync omits `confirmBlankPos` / `confirmGstinTotalChange`. |
| F-016 | P1 | `useInvoiceOffline.ts:28-35` | Auto-flush posts raw payload including `_completeIntent` / `status`. |
| F-017 | P2 | `invoiceDraftCache.ts:385-412` | `saveInvoiceDraft` `void enqueueDraft` — persistence failures silent. |
| F-018 | P2 | `flushPosCheckout.ts:47-56` | Flush maps lines without cess, discountAmount, serials, supplyType. |
| F-019 | P2 | `NewInvoicePage.tsx:1055-1058` | Ctrl+S drafts without `canSave` (no customer / empty lines). |
| F-021 | P2 | `usePreviewTotals.ts:24-54` | No abort of in-flight preview; rapid edits can apply stale totals. |
| F-022 | P2 | `NewInvoicePage.tsx:807-820` | Complete failure after create lands on history with "Draft saved — complete failed…" easy to miss. |
| F-023 | P2 | `PosPage.tsx:254-284` | Offline recovery loads **only latest** POS draft into cart. |
| F-024 | P2 | `PartySelectPanel.tsx:88-124` | Warns only if **both** state and GSTIN missing; invalid GSTIN checksum looks fine. |
| F-025 | P2 | `types/domain.ts:321-349` | `LineItem` missing `rateOverride` / `appliedRate` / `cessAmount` / `uqcCode`. |
| F-026 | P2 | `NewInvoicePage.tsx:708-710` | TCS fields only sent when `ENABLE_TDS` flag on. |
| F-027 | P2 | `EinvoiceEwayPanel.tsx:124-189` | Success toasts hardcoded English. |
| F-028 | P2 | `DocumentTaxSummary.tsx:155` | Cess row label hardcoded `"Cess"`. |
| F-029 | P2 | `DraftLineTable.tsx:89` | Column header `"Serials"` not i18n. |
| F-030 | UX | `NewInvoicePage.tsx:1802-1806` | Payment mode MenuItems hardcoded English. |
| F-031 | UX | `NewInvoicePage.tsx:1680-1684` | TCS block labels hardcoded English. |
| F-032 | UX | `InvoiceTemplatesPage.tsx:21-100` | **Partial:** static layout legend + terms textarea only. No template picker, preview, or variant. Success toast `'Invoice terms saved'` not i18n. |
| F-033 | UX | `erpShared.tsx` + mfg/payroll/crm | Modules openly MVP (`MvpModuleBanner`) — thin CRUD, not full ERP. |
| F-034 | UX | `PosPage.tsx` | **No cash-drawer open** — only receipt/thermal print. |
| F-035 | UX | `NewInvoicePage.tsx:1005-1014` | Dirty = `lines.length > 0` only — header/party/TCS edits with no lines leave without warning. |
| F-036 | UX | `DraftLineTable.tsx:79-81` | HSN column `display:{xs:'none'}` — mobile never sees HSN. |
| F-037 | UX | `DraftLineTable.tsx:252` | Cess % input hidden on xs — uneditable on phone. |
| F-038 | UX | `LoginPage.tsx:38-44` | Validation strings hardcoded English. |
| F-040 | UX | `HelpPageV0.tsx:53-59` | Search lacks results-count live region. |
| F-043 | P3 | `i18n/hi.ts` vs `en.ts` | Hindi missing `billUpload.*` cluster and `auth.gstinHelper` (raw keys / English fallback). Extra `help.feedbackBacklog` in hi only. |
| F-045 | P3 | `invoiceDraftCache.ts:27-30` | Documented plaintext outbox on shared POS devices — PII at rest. |
| F-047 | P3 | `App.tsx` | No `/dashboard` route; deep link → NotFound. |
| F-051 | P2 | `EinvoiceEwayPanel.tsx:198-199` | E-way submit gated by `isEinvoiceSubmitEnabled()` — wrong flag. |
| F-052 | UX | `DashboardPage.tsx:87-88` | Dual camel/snake fallbacks paper over API contract drift. |
| F-053 | P2 | `PosPage.tsx:515-540` | Cash always allocates **full** `grandTotal`; no partial-pay path. |
| F-054 | P2 | `SalesReturnsPage.tsx:49-53` | Viewers-with-finance can open `?create=1` then fail on mutate. |

### Additional UI/UX (verified)

| # | Sev | Loc | Finding |
|---|---|---|---|
| UX-10 | UX | Invoice / purchase editors | Keyboard shortcut docs mention Wave 18; operators have no in-app shortcut cheat-sheet. |
| UX-11 | UX | POS | Status chip is visual-only; no `aria-live` for offline/sync/error. |
| UX-12 | UX | `PartySelectPanel` | Selected-party block is not a named region; Autocomplete a11y is field-label only. |
| UX-13 | UX | Offline outbox | Sync disabled when `!navigator.onLine` with weak empty-state when drafts exist. |
| UX-14 | UX | Share invoice | Phone placeholder `9198XXXXXXXX` not i18n; weak vs `isValidIndianPhone`. |
| UX-15 | UX | Unit labels | `unitLabels.ts` incomplete vs GSTN UQC (QTL, TON, SQM, KME…) — raw codes shown. |
| UX-16 | UX | Reports | Aging can disagree with invoice balance (RPT-13) with no "source of truth" note. |
| UX-17 | UX | GST returns UI | Honesty flags / SUPECOM double-count notes are easy to miss; CA can double-file. |
| UX-18 | UX | Help v0 vs v2 | `helpV2` flag-off → FAQ-only v0; staff see v2, customers may not (`feature_flags` staff override). |
| UX-19 | UX | Settings | `books_start_date` / `doc_number_scope` not on company API → no UI to configure FY numbering scope. |
| UX-20 | UX | File download | Content-Type guessed from filename, not `asset.content_type`. |
| UX-21 | UX | Error envelope | Nested field errors shown as Python dict repr (`exceptions.py`) — unreadable in toasts. |
| UX-22 | UX | Onboarding | Progress can show Payments while catalog is still blocking. |
| UX-23 | UX | Manufacturing UI | Cancel confirm mentions WIP reverse; FIFO layers are **not** restored (0.3) — copy over-promises. |
| UX-24 | UX | Payroll | PT/ESI/PF numbers can be silently wrong (double proration) with no warning chip. |
| UX-25 | UX | Tally | Commit success UI can look like full parity; export truncated at 5k with no banner. |
| UX-26 | UX | Insights | Daily narrative presents AR/AP as facts; margin uses list price not true cost. |
| UX-27 | UX | Public pay | Payment-link token in list API + WhatsApp `wa.me` text — leakage surface. |
| UX-28 | UX | Register | Defaults UNREGISTERED even when GSTIN supplied (accounts RegisterView) — cannot issue tax invoices until settings fix. |
| UX-29 | UX | Hindi | Large billing/e-invoice/login/TCS/payment-mode surfaces still English. |
| UX-30 | UX | Mobile web | HSN + cess hidden on xs; POS is usable but invoice editor is not a first-class phone flow. |
| UX-31 | UX | `mobile/` | Only `capacitor.config.ts` — **no native screens**. "Mobile app" is a PWA wrapper at best. |
| UX-32 | UX | Confirm dialogs | Several destructive actions (WO cancel, restore wipe) need typed confirm; wipe's `confirm_destroy_unbacked` is easy to tick. |

---

## 8. Partially implemented / stubbed product surfaces

| Area | What exists | What is missing |
|---|---|---|
| Invoice templates | Company `invoiceTerms` + static layout legend | Multiple templates, per-GSTIN header, preview, logo/sign placement, original/duplicate copies as real variants |
| Manufacturing | BOM + WO release/complete/cancel + optional WIP GL | Shop-floor, routing, by-products, true WIP account vs 1450, FIFO restore on cancel, Owner-only API vs wider FE |
| Payroll | Pay runs, LOP, PF/ESI/PT | State PT completeness, employer expense split, Form 24Q/16, attendance import |
| CRM | Leads → opportunity convert | Pipeline stages, activities, quotes linkage, duplicate-party confirm |
| Banking AA | Match receipts by UTR `icontains` | Atomic match, ambiguous-UTR reject, full AA product |
| GSTR-7/8/6 | Stubs `supported: False` | Actual worksheets / JSON |
| Tenant backup | Invoices/payments/stock subset | Orders, notes, challans, returns, batch FKs, logo FKs — wipe deletes more than export |
| Company API | Many flags | `books_start_date`, `doc_number_scope` |
| Help | v0 FAQ + v2 flag | Most `BusinessRuleError`s still generic `business_rule_violation`; sparse deep-links |
| Cash drawer | — | No ESC/POS drawer pulse |
| Offline Complete | Outbox page | Auto-flush on invoice/purchase editors |
| HSN catalog | Static COMMON + 2 starter rates | GSTN-backed search; rate table coverage |
| WhatsApp | Template send + wa.me fallback | Locale, async send, token-safe share |
| OTP login | MSG91/Twilio adapters | Body-parsed MSG91 success; DLT; passwordless users |
| Subscription | Razorpay checkout + write gate | Fail-closed on billing errors; period-end without webhook |
| Mobile | Capacitor config | No app screens |

---

## 9. Improvement suggestions (not defects)

| # | Area | Suggestion |
|---|---|---|
| SUG-1 | Feature flags | Fail **closed** on `plan_modules_for_company` errors for dark modules. |
| SUG-2 | Idempotency | Store 2xx only; treat 5xx as in-flight with TTL heartbeat; prune table. |
| SUG-3 | Events | Emit domain events **after** commit (`transaction.on_commit`). |
| SUG-4 | FIFO | WO cancel should call `restore_fifo_peels` like stock-transfer cancel. |
| SUG-5 | Bank recon | Fix aggregate aliases; require amount equality + unique bank-line. |
| SUG-6 | H9 | Put TCS, RCM, filing GSTIN, POS in money/statutory allowlist. |
| SUG-7 | PDF | Print TCS, POS, stamped branch address, supplier bill number. |
| SUG-8 | FE ACL | Mirror backend permission classes 1:1; hide routes that 403. |
| SUG-9 | Preview | Bind `amountDue` + TCS; never zero totals on preview error. |
| SUG-10 | Offline | One flush path (shared with Outbox); always honor completeIntent + POS confirms. |
| SUG-11 | GST 2B | Unique ingest key; case-insensitive invoice match; stamp NULL as primary. |
| SUG-12 | IMS | Do not deemed-ACCEPT MISSING_IN_BOOKS. |
| SUG-13 | Seats | Check seat limit on accept; lock on invite create. |
| SUG-14 | Refresh | Fail closed if `blacklist()` raises; require active membership. |
| SUG-15 | Phone | Normalize E.164 at register/invite; unique on normalized value. |
| SUG-16 | Payroll | Single proration; dict-miss → state table → default; enforce slab schema. |
| SUG-17 | Tally | `transaction.atomic`; require recon pass; warn on 5k truncate. |
| SUG-18 | Import | Max rows, shared-string size, real XLSX sniff (not `PK`). |
| SUG-19 | i18n | Generate a CI check: every `en.ts` key exists in `hi.ts`; no hardcoded billing strings. |
| SUG-20 | Observability | Alert on GSP decrypt fail, MSG91 type=error, refund IN_PROGRESS > 10 min. |
| SUG-21 | POS | Set busy **before** walk-in create; cash-drawer; UPI flush must not Complete unpaid. |
| SUG-22 | Docs | Operator-facing "what Complete does" vs draft, and "why preview ≠ PDF" when TCS hidden. |

---

## 10. What looks solid (so this is not only a complaint list)

- Gateway payment unique `(company, provider, provider_payment_id)`.
- Receipt/supplier UTR partial uniques; allocation XOR at serializer.
- Webhook requires `payment_link_id` + signature (unsigned only in `DJANGO_ENV=test`).
- Refund outbox unique (migration 0018) and recon match unique (0019) close duplicate-row races — they do **not** fix stuck IN_PROGRESS.
- B2CL ₹1L threshold from 2024-08-01; 3B RCM notes netted into 3.1(d); 2B claimable excludes RCM/opening/ineligible (when stamp matches).
- `post_movement` balance locking is generally sound; FEFO ordering itself is coherent.
- Many historical BB-###### comments show prior P0s were actually fixed (e.g. POS offline now clears cart after enqueue; IRN cancel guard exists for GENERATED/MANUAL).

---

## 11. Method notes

Line numbers are against the tree as of 2026-09-01 (including uncommitted sales/payments/inventory/frontend edits). A parallel session was touching unit-labels / Help-v0 (~32 files); those findings are against the files as read, not an older commit.

This is a quality log, not a fix list ordered by effort. Section 0 is the only recommended sequence if the goal is "stop losing money / breaking GST / leaking sessions" before the next feature wave.

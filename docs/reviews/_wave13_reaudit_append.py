#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 13 independent re-audit (2026-08-04): append BB-000379+ after Wave 12 Open==0.

Never regenerates prior IDs. Append-only. IDs permanent.
Invalidates Wave 12 “Open == 0” as a commercial launch gate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-04"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
START_ID = 379

ISSUES: list[dict] = []


def add(**kwargs):
    ISSUES.append(kwargs)


# ─── CRITICAL ───────────────────────────────────────────────────────────────
add(
    title="Payment-link create accepts provider=sandbox in production (settings PATCH-only ban)",
    category="Security",
    subcategory="Payments",
    severity="Critical",
    priority="P0",
    module="Payments",
    feature="Payment links",
    files="backend/payments/services.py; backend/payments/views.py payment_webhook",
    problem="BB-000318 banned sandbox on GatewaySettingsView PATCH for production/staging, but PaymentService.create_payment_link still accepts explicit provider=sandbox (and remaps empty-cred+test_mode to sandbox when DJANGO_ENV!=production). payment_webhook settles sandbox HMAC captures into receipts/GL with no env ban.",
    evidence="create_payment_link ~305-319: no sandbox+prod reject; webhook ~540-574: get_adapter('sandbox') then finalize_gateway_payment; only settings PATCH ~850-853 bans sandbox",
    root_cause="Wave 12A gated settings surface only; create + webhook settlement paths untouched.",
    business="Fake captures mark invoices paid and post cash/GL without money in production.",
    technical="Settlement trusts sandbox adapter whenever a sandbox PaymentLink exists.",
    customer="AR fraud / false paid state; GST cash basis distortion.",
    security="Critical payment forgery residual after claimed BB-000318 Resolved.",
    performance="N/A",
    scalability="Any tenant API client can mint sandbox links if create allowed.",
    compliance="Financial controls failure; SoD broken.",
    risk="Silent production AR corruption if staff/API uses provider=sandbox.",
    fix_immediate="Reject provider=sandbox (and remap) when DJANGO_ENV in (production,staging) in create_payment_link AND payment_webhook; refuse settle if company.provider!=sandbox or env forbids.",
    fix_short="Boot-scan existing sandbox links in prod; quarantine; per-company secrets.",
    fix_long="Sandbox only in isolated non-prod tenants; never settle into live books.",
    effort="0.5-1d",
    tests="Prod env POST payment-link provider=sandbox → 400; sandbox webhook → 403 in prod.",
    acceptance="Production/staging cannot create or settle sandbox payment links.",
    status="Open",
    refs="BB-000318 residual; BB-000196/258/265; Wave13 NEW",
)
add(
    title="Sales return restores stock + CN but never reverses COGS/Inventory GL",
    category="Accounting",
    subcategory="Perpetual inventory",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="Sales returns",
    files="backend/sales/services.py complete_return; backend/accounting/services.py post_note post_sales_cogs",
    problem="Complete sale posts Dr COGS / Cr Inventory via post_sales_cogs. complete_return posts SALES_RETURN stock and auto CN (Dr Sales/Output GST, Cr AR) but never reverses the COGS journal.",
    evidence="complete_return ~679-825: stock + SalesNotesService.complete_credit_note only; no PostingService.post_sales_cogs reverse or return COGS purpose",
    root_cause="Wave 12C perpetual model added sale COGS without return lifecycle GL parity.",
    business="Inventory asset understated; COGS permanently overstated after returns; P&L/BS wrong vs stock.",
    technical="Dual truth: physical stock restored, perpetual GL not.",
    customer="CA rejects books; tax P&L misstated.",
    security="N/A",
    performance="N/A",
    scalability="Every return widens GL vs stock divergence.",
    compliance="Books not true and fair; audit failure.",
    risk="Accounting_enabled pilots produce wrong trading accounts.",
    fix_immediate="On return complete, Dr Inventory / Cr COGS for returned qty × original SALE movement cost; reverse on cancel.",
    fix_short="Purpose SALES_RETURN_COGS with source_id=return; health check stock vs 1400.",
    fix_long="Unified inventory event → GL projector.",
    effort="2-3d",
    tests="Sale+COGS+return → COGS and 1400 net correct; cancel restores.",
    acceptance="Return leaves Inventory/COGS aligned with stock valuation.",
    status="Open",
    refs="BB-000322 residual; Wave13 NEW",
)
add(
    title="Tally/opening invoices skip GL but remain in AR/AP outstanding and BooksHealth",
    category="Accounting",
    subcategory="Dual ledger",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="Opening balances",
    files="backend/sales/services.py complete; backend/purchases/services.py; backend/ledgers/services.py; backend/accounting/services.py BooksHealthService",
    problem="is_tally_opening / opening invoices skip post_sales_invoice/post_purchase but remain in ledger outstanding formulas and AR/AP control balance checks.",
    evidence="complete skips GL when is_tally_opening; ledgers include openings; BooksHealth control_balances compares GL 1200/2100 to outstanding",
    root_cause="Migration magnet openings treated as document-truth without opening equity JEs.",
    business="Permanent AR_CONTROL_MISMATCH / AP_CONTROL_MISMATCH after Tally import; books unusable.",
    technical="Dual-ledger invariant broken by design for openings.",
    customer="Post-migration trust collapse.",
    security="N/A",
    performance="N/A",
    scalability="Every migrated tenant hits health red.",
    compliance="Opening balances not GAAP/Ind AS coherent.",
    risk="accounting_enabled cannot be turned on after Tally import.",
    fix_immediate="Post opening JEs AR/AP vs Opening Equity (no P&L/COGS), OR exclude is_opening_balance from outstanding and BooksHealth consistently.",
    fix_short="Opening balance wizard with explicit equity posting.",
    fix_long="Single opening subledger with GL bridge.",
    effort="3-5d",
    tests="Opening invoice → no control mismatch; outstanding matches GL.",
    acceptance="Openings never permanently trip AR/AP control alerts.",
    status="Open",
    refs="BB-000264/346 residual; Wave13 NEW",
)
add(
    title="Unallocated receipts/payments credit AR/AP control GL but not party outstanding",
    category="Accounting",
    subcategory="Advances",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="Receipts/payments",
    files="backend/accounting/services.py post_receipt post_supplier_payment; backend/ledgers/services.py",
    problem="Full receipt amount credits AR control (1200) in GL; party outstanding only subtracts allocations. Unallocated advances always diverge statement vs outstanding vs BooksHealth.",
    evidence="post_receipt credits 1200 for full amount; customer_outstanding uses allocations only",
    root_cause="No Advances/Unearned liability account; control account used as catch-all.",
    business="False control alerts; overstated customer outstanding vs cash books.",
    technical="BooksHealth unusable whenever advances exist.",
    customer="Collections staff see wrong due; CA sees mismatch.",
    security="N/A",
    performance="N/A",
    scalability="Any advance breaks health.",
    compliance="Incorrect AR presentation.",
    risk="Operators disable health checks instead of fixing books.",
    fix_immediate="Unallocated → Cr Customer Advances (liability); allocate moves Advances→AR; mirror AP.",
    fix_short="Include unallocated in control reconciliation report.",
    fix_long="Subledger engine with control rollup.",
    effort="2-4d",
    tests="Unallocated receipt → BooksHealth OK; outstanding excludes advance correctly.",
    acceptance="Advances never trip AR/AP control mismatch.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Purchase return of batch-tracked goods cannot complete (no batch on return lines)",
    category="Inventory",
    subcategory="Batch/FEFO",
    severity="Critical",
    priority="P0",
    module="Purchases",
    feature="Purchase returns",
    files="backend/purchases/services.py complete_return; backend/inventory/services.py post_movement; purchases models PurchaseReturnItem",
    problem="post_movement requires batch when product.track_batch. Purchase return completion posts movement without batch; PurchaseReturnItem has no batch/serial fields. Batched SKUs hard-fail on return.",
    evidence="complete_return movement without batch=; model lacks batch FK; InventoryService enforces track_batch",
    root_cause="Wave 12D fixed sales return lot replay (BB-000341) but not purchase returns.",
    business="Cannot return purchased batched goods — core MSME ops blocked.",
    technical="Asymmetric sales vs purchase return inventory model.",
    customer="Forced to disable track_batch or manual stock hacks.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Inventory register incomplete for returns.",
    risk="Pilot pharmacies/FMCG abandon batch tracking.",
    fix_immediate="Persist batch/serial on purchase return lines; post_movement with batch; FEFO/original lot selection.",
    fix_short="Mirror sales return movement-replay.",
    fix_long="Unified return lot allocator.",
    effort="2-3d",
    tests="track_batch purchase→return complete succeeds; lot qty correct.",
    acceptance="Batched purchase returns complete without disabling tracking.",
    status="Open",
    refs="BB-000341 asymmetry; Wave13 NEW",
)
add(
    title="Production live e-Invoice/e-Way adapters always raise not-enabled (dead end)",
    category="GST",
    subcategory="GSP",
    severity="Critical",
    priority="P0",
    module="Integrations",
    feature="e-Invoice/e-Way",
    files="backend/core/services/gsp_adapters.py; backend/sales/einvoice_eway_actions.py",
    problem="Production + live GSTIN blocks sandbox GSP; LiveIrpAdapter/LiveEwayAdapter always BusinessRuleError('…not enabled yet'). Flags einvoice_enabled/eway_enabled are enableable but non-functional in prod.",
    evidence="Live adapters stub raise; _assert_sandbox_gsp_allowed blocks sandbox in prod",
    root_cause="Sandbox path shipped; live GSP HTTP never implemented; Wave 12 closed honesty IDs without shipping integration.",
    business="Cannot generate real IRN/EWB in production despite UI/settings.",
    technical="Feature flags lie; compliance workflow dead-ends.",
    customer="B2B invoices > threshold cannot legally move goods with product IRN.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical — statutory e-invoice mandate unmet.",
    risk="Commercial claim of GST Portal Integration is false for live.",
    fix_immediate="Fail-closed: disable einvoice_enabled/eway_enabled in prod until live adapter ships; UI honesty banner.",
    fix_short="Integrate certified GSP HTTP with sandbox+prod credentials.",
    fix_long="Multi-GSP adapter with circuit breaker + audit.",
    effort="20-40d (vendor)",
    tests="Prod enable flag without live adapter → rejected; sandbox only non-prod.",
    acceptance="No prod path claims IRN/EWB without working live adapter.",
    status="Open",
    refs="BB-000005/012 Deferred residual surfaced as Critical honesty; Wave13 NEW",
)
add(
    title="Prod Celery beat healthcheck always succeeds (assert … or True)",
    category="DevOps",
    subcategory="Healthchecks",
    severity="Critical",
    priority="P0",
    module="DevOps",
    feature="docker-compose.prod",
    files="docker-compose.prod.yml",
    problem="Beat healthcheck: assert r.get('bizboard:celery_beat_heartbeat') or True — never fails even when heartbeat missing.",
    evidence="docker-compose.prod.yml L25-31 or True",
    root_cause="Placeholder left in place after BB-000359 claimed readiness/beat attention.",
    business="Silent beat death → missed depreciation, insights, scheduled GST jobs.",
    technical="Orchestrator reports healthy forever.",
    customer="Stale automations without alert.",
    security="N/A",
    performance="N/A",
    scalability="Fleet-wide silent failure.",
    compliance="Ops control failure.",
    risk="Production schedules stop with green health.",
    fix_immediate="Remove `or True`; assert heartbeat exists and is fresh.",
    fix_short="Alert on missing heartbeat in monitoring.",
    fix_long="Liveness + readiness split with SLO.",
    effort="0.25d",
    tests="Compose config test / script asserts no `or True` in beat health.",
    acceptance="Missing beat heartbeat → unhealthy.",
    status="Open",
    refs="BB-000359 residual; Wave13 NEW",
)
add(
    title="Wave 12 Open==0 invalidated — residual Criticals after claimed closure (meta)",
    category="Process",
    subcategory="Audit integrity",
    severity="Critical",
    priority="P0",
    module="Docs",
    feature="Issue register",
    files="docs/reviews/MASTER_ISSUE_REGISTER.md; docs/reviews/CHANGELOG.md; docs/reviews/_wave12_assert_gates.py",
    problem="Wave 12 open-closure claimed Open==0 and PR score 6.5, but independent Wave 13 re-verification found residual Criticals (sandbox create/settle, return COGS, openings dual-ledger, purchase batch returns, live GSP dead-end, beat or True).",
    evidence="This Wave 13 register append; code evidence on BB-000379+",
    root_cause="Checklist/gate scripts verify selected patches, not adversarial residual hunt across create paths and GL lifecycle.",
    business="False launch confidence.",
    technical="Process debt; gates insufficient.",
    customer="Risk of shipping known-broken payments/books.",
    security="Process failure enables shipping Criticals.",
    performance="N/A",
    scalability="N/A",
    compliance="Audit trail of false closure.",
    risk="Repeated Open==0 theater without residual tests.",
    fix_immediate="Treat Open==0 as non-gate until Wave 13 P0 closed; require residual adversarial suites.",
    fix_short="Gate scripts must include create_payment_link sandbox+prod, return COGS, beat health AST.",
    fix_long="Independent audit cadence with fail-on-residual.",
    effort="1-2d process",
    tests="New assert script fails until P0 residuals green.",
    acceptance="No Open==0 claim without residual suite pass.",
    status="Open",
    refs="BB-000325 pattern; Wave13 NEW",
)

# ─── HIGH ───────────────────────────────────────────────────────────────────
add(
    title="prepare_einvoice/prepare_eway fall through to HasCompany (VIEWER mutates compliance state)",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P0",
    module="Sales",
    feature="e-Invoice prepare",
    files="backend/sales/views.py get_permissions; backend/sales/einvoice_eway_actions.py",
    problem="submit/mark/cancel einvoice/eway gated IsOwner; prepare_* actions not listed → super() HasCompany only. Mutates einvoice_status/eway_status to READY and returns compliance payload.",
    evidence="get_permissions L81-90 lists mark/submit/cancel only; prepare_einvoice action exists; fallthrough L90",
    root_cause="Wave 12B gated listed actions; prepare omitted.",
    business="VIEWER tampers GST compliance workflow state.",
    technical="API RBAC ≠ FE assumption.",
    customer="Unauthorized access to IRN payload drafts.",
    security="Privilege escalation within tenant.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD failure for statutory docs.",
    risk="Internal fraud / accidental READY spam.",
    fix_immediate="Gate prepare_* with IsOwner (or CanCreateSales+Owner).",
    fix_short="Deny VIEWER all compliance actions; audit log.",
    fix_long="Capability can_manage_gst_compliance.",
    effort="0.5d",
    tests="VIEWER prepare-einvoice → 403.",
    acceptance="No HasCompany-only mutate on einvoice/eway.",
    status="Open",
    refs="BB-000319 residual; Wave13 NEW",
)
add(
    title="WarehouseViewSet CRUD is HasCompany-only — VIEWER mutates warehouses",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P0",
    module="Inventory",
    feature="Warehouses",
    files="backend/inventory/views.py WarehouseViewSet",
    problem="WarehouseViewSet has no permission_classes override; inherits CompanyScopedViewSet HasCompany. Transfers/adjustments require CanManageInventory; warehouses do not.",
    evidence="WarehouseViewSet L134-142 no CanManageInventory; StockTransferViewSet L148 has it",
    root_cause="Wave 12B inventory RBAC incomplete.",
    business="VIEWER deletes/renames default warehouse; stock ops break.",
    technical="Inconsistent inventory ACL.",
    customer="Ops outage from unauthorized warehouse edits.",
    security="Privilege escalation.",
    performance="N/A",
    scalability="N/A",
    compliance="Inventory control failure.",
    risk="Pilot with VIEWER role unsafe.",
    fix_immediate="Mutate → CanManageInventory or Owner; list may stay broader.",
    fix_short="Hard-block VIEWER on warehouse write.",
    fix_long="Full inventory ACL matrix.",
    effort="0.5d",
    tests="VIEWER POST/PATCH/DELETE warehouse → 403.",
    acceptance="Warehouse mutate requires inventory capability.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Register success sets JWT cookies — email enumeration oracle (body-isomorphic incomplete)",
    category="Security",
    subcategory="Auth",
    severity="High",
    priority="P0",
    module="Accounts",
    feature="Register",
    files="backend/accounts/views.py RegisterView",
    problem="BB-000349 made response body isomorphic, but successful new-email register sets access/refresh cookies; duplicate email returns 200 without cookies.",
    evidence="RegisterView ~144-176 _set_access_cookie on success path",
    root_cause="Body-only fix; cookie side channel ignored.",
    business="Account existence enumeration.",
    technical="Auth oracle.",
    customer="Privacy / targeted phishing.",
    security="High — user enumeration.",
    performance="N/A",
    scalability="N/A",
    compliance="Privacy expectation failure.",
    risk="Credential stuffing recon.",
    fix_immediate="Never set auth cookies on register; require login/verify after register.",
    fix_short="Identical Set-Cookie absence both paths; timing harden.",
    fix_long="Email verification before session.",
    effort="0.5-1d",
    tests="New vs duplicate register → identical headers re cookies.",
    acceptance="No cookie oracle on register.",
    status="Open",
    refs="BB-000349 residual; Wave13 NEW",
)
add(
    title="FE placeOfSupplyKnown treats any non-empty state text as known (BE rejects unmapped)",
    category="GST",
    subcategory="Tax preview",
    severity="High",
    priority="P0",
    module="Web",
    feature="Invoice tax preview",
    files="web/src/utils/tax.ts placeOfSupplyKnown; backend/core/services/billing.py",
    problem="FE: any trimmed partyState → known=true. BE place_of_supply_known('Nowhereland') is false. FE then string-compares → inter tax preview while Complete may fail or differ.",
    evidence="tax.ts L402-404; BE test_phase2_gst Nowhereland",
    root_cause="BB-000365 fixed BE; FE not ported. BB-000320 mapped names but known-gate still loose.",
    business="UI enables Complete then API rejects; or wrong IGST preview.",
    technical="FE/BE POS contract drift.",
    customer="Billing friction; wrong tax collected if staff trusts UI.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Preview ≠ books GST split risk.",
    risk="Pilot CA demo failure on typoed states.",
    fix_immediate="Mirror BE: known only if extractStateCode(state|gstin) succeeds.",
    fix_short="Shared golden fixture FE↔BE including unknown states.",
    fix_long="Server tax preview API as SoT.",
    effort="0.5d",
    tests="vitest Nowhereland → placeOfSupplyKnown false; parity with BE.",
    acceptance="FE known-gate ≡ BE for mapped/unmapped/blank.",
    status="Open",
    refs="BB-000365 residual; BB-000320; Wave13 NEW",
)
add(
    title="allow_partial still accepts over-capture above link amount",
    category="Security",
    subcategory="Payments",
    severity="High",
    priority="P1",
    module="Payments",
    feature="Webhooks",
    files="backend/payments/services.py finalize_gateway_payment",
    problem="BB-000351 rejects over-capture only when not allow_partial. With allow_partial=True, capture_amount > link.amount creates oversize receipt.",
    evidence="finalize_gateway_payment L434-438: `if capture_amount > link.amount and not link.allow_partial`",
    root_cause="Overpay guard tied to partial flag incorrectly.",
    business="Overstated cash/receipts; customer overpay booked.",
    technical="Books record excess without policy.",
    customer="Disputes; refund ops missing.",
    security="Integrity — webhook can inflate cash.",
    performance="N/A",
    scalability="N/A",
    compliance="Cash controls.",
    risk="Malicious/buggy provider payload overpays books.",
    fix_immediate="Always reject capture > link.amount (refund policy separate).",
    fix_short="Store provider_amount vs applied_amount.",
    fix_long="Explicit overpay+refund workflow.",
    effort="0.5d",
    tests="allow_partial + capture>amount → 400.",
    acceptance="No receipt amount > link.amount.",
    status="Open",
    refs="BB-000351 residual; Wave13 NEW",
)
add(
    title="Partial under-capture marks PaymentLink PAID and closes collection",
    category="Business Logic",
    subcategory="Payments",
    severity="High",
    priority="P1",
    module="Payments",
    feature="Partial payments",
    files="backend/payments/services.py finalize_gateway_payment",
    problem="Underpay allowed when allow_partial; link status always set PAID after one capture.",
    evidence="L430-433 underpay check only if not allow_partial; L468 link.status=PAID always",
    root_cause="No PARTIALLY_PAID state.",
    business="Remaining balance uncollectable via link; AR wrong.",
    technical="Link lifecycle incomplete.",
    customer="Cannot collect remainder; manual receipt workarounds.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="AR aging wrong.",
    risk="Revenue leakage on partial UPI.",
    fix_immediate="PARTIALLY_PAID until sum(captures)>=amount; keep link open.",
    fix_short="Multi-capture allocation ledger on link.",
    fix_long="Payment plan objects.",
    effort="1-2d",
    tests="Partial capture → not PAID; second capture completes.",
    acceptance="Link PAID iff fully collected.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Multiple open payment links can oversubscribe invoice outstanding",
    category="Business Logic",
    subcategory="Payments",
    severity="High",
    priority="P1",
    module="Payments",
    feature="Payment links",
    files="backend/payments/services.py create_payment_link finalize_gateway_payment",
    problem="Each link checks current outstanding independently; no reservation against other CREATED/SENT links. Parallel captures can over-collect or leave unallocated cash.",
    evidence="create checks amount<=outstanding only; no sum(open links)",
    root_cause="No link reservation model.",
    business="Double payment / stuck unapplied cash; disputes.",
    technical="Race between links.",
    customer="Overpay pain.",
    security="Integrity under concurrency.",
    performance="N/A",
    scalability="Worse with many cashiers.",
    compliance="Cash application ambiguity.",
    risk="High in retail multi-counter.",
    fix_immediate="Single active link per invoice OR reserve open-link amounts.",
    fix_short="Fail create when reserved+amount>outstanding.",
    fix_long="Payment intent with exclusive lock.",
    effort="1-2d",
    tests="Second full link while first open → 400.",
    acceptance="Open links cannot exceed outstanding.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Sales/purchase return cancel restores unbatched stock (lot corruption)",
    category="Inventory",
    subcategory="FEFO",
    severity="High",
    priority="P0",
    module="Inventory",
    feature="Return cancel",
    files="backend/sales/services.py cancel_return; backend/purchases/services.py cancel_return",
    problem="complete_return restores specific SALE lots; cancel_return posts ADJUSTMENT without batch=, undoing into unbatched balance.",
    evidence="cancel_return L834-845 movement without batch=",
    root_cause="Wave 12D fixed invoice FEFO cancel and return complete lots; cancel path incomplete.",
    business="Lot balances corrupt; FEFO expiry wrong after cancel.",
    technical="Asymmetric complete/cancel.",
    customer="Wrong batch stock after ops mistake undo.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Batch traceability break.",
    risk="Pharma/FMCG pilots unsafe.",
    fix_immediate="Replay return movements' batches/serials on cancel.",
    fix_short="Movement-linked reverse helper.",
    fix_long="Event-sourced inventory.",
    effort="1-2d",
    tests="Return complete+cancel → lot qty identical to pre-return.",
    acceptance="Cancel never creates unbatched qty from batched return.",
    status="Open",
    refs="BB-000321/341 residual; Wave13 NEW",
)
add(
    title="H9 money-amend re-posts stale COGS after qty/cost change",
    category="Accounting",
    subcategory="Amend",
    severity="High",
    priority="P0",
    module="Accounting",
    feature="H9 amend",
    files="backend/sales/serializers.py amend path; accounting post_sales_cogs",
    problem="Amend reverses prior COGS journal then re-posts same cogs_amount after set_items may change sold qty/cost.",
    evidence="serializers amend ~219-248 reads prior COGS debit and reuses",
    root_cause="COGS not recomputed from post-amend SALE movements.",
    business="Inventory GL ≠ valuation after amend.",
    technical="Silent books error.",
    customer="Wrong GP after corrections.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Books inaccurate.",
    risk="Any H9 qty amend corrupts perpetual inventory.",
    fix_immediate="Recompute COGS from post-amend movements/valuation.",
    fix_short="Refuse money amend when stock already posted without reverse+reissue.",
    fix_long="Immutable stock events + compensating entries only.",
    effort="1-2d",
    tests="Amend qty down → COGS and 1400 match new qty.",
    acceptance="Post-amend COGS equals valuation of remaining SALE.",
    status="Open",
    refs="BB-000011/199 residual; Wave13 NEW",
)
add(
    title="SOFT_CLOSED periods behave as hard CLOSED (soft path dead)",
    category="GST",
    subcategory="Periods",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="GST/accounting periods",
    files="backend/reporting/gst_periods.py; backend/accounting/services.py PostingService.post",
    problem="SOFT_CLOSED treated like CLOSED for money posts; period_complete_warning unused. Operators soft-close expecting warn-only; Completes hard-fail.",
    evidence="assert_period_allows_money_amend blocks SOFT_CLOSED; warning helper never called",
    root_cause="Incomplete soft-close productization (BB-000271).",
    business="Ops confusion; blocked billing after soft close.",
    technical="Enum value without semantics.",
    customer="Support load.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Period control UX lies.",
    risk="Owners avoid period close entirely.",
    fix_immediate="Soft=warn on Complete (Owner override); CLOSED=block. Wire warning into responses.",
    fix_short="UI distinguishes soft vs hard.",
    fix_long="Period workflow with approvals.",
    effort="1-2d",
    tests="SOFT_CLOSED Complete → 200+warning; CLOSED → 400.",
    acceptance="Soft close is warn-only for Complete.",
    status="Open",
    refs="BB-000271/337 residual; Wave13 NEW",
)
add(
    title="assume_local_state_for_blank_party does not stamp POS on Sales Complete",
    category="GST",
    subcategory="Place of supply",
    severity="High",
    priority="P1",
    module="Sales",
    feature="B2C POS",
    files="backend/core/services/place_of_supply.py; backend/sales/services.py complete",
    problem="Assert early-returns on assume_local; Complete still requires mappable resolved_code and never stamps company state as filing POS.",
    evidence="assert_place_of_supply_for_gst assume_local return; complete ~424-437 still needs resolved_code",
    root_cause="Setting half-wired.",
    business="Documented setting is a trap; blank-party B2C GST invoices cannot complete.",
    technical="Config lie.",
    customer="Retail B2C blocked.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="POS missing on filed docs.",
    risk="Retail pilots fail.",
    fix_immediate="When assume_local, set filing_place_of_supply from company GSTIN/state.",
    fix_short="E2E test blank party + flag.",
    fix_long="POS resolver service single path.",
    effort="0.5-1d",
    tests="Blank party + assume_local → Complete OK with company POS.",
    acceptance="Setting works end-to-end.",
    status="Open",
    refs="BB-000278 residual; Wave13 NEW",
)
add(
    title="GSTR-1 CDNR includes notes against opening-balance invoices",
    category="GST",
    subcategory="GSTR-1",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="CDNR",
    files="backend/reporting/gst_returns.py _gst_credit_notes _gst_debit_notes",
    problem="Invoice builders exclude is_opening_balance; note builders do not. CDNR reduces outward liability without original B2B/B2C row.",
    evidence="notes filter invoice_type only; openings excluded only on invoice query",
    root_cause="BB-000335 fixed invoices not notes.",
    business="Under-reported tax / portal mismatch if used as filing aid.",
    technical="GSTR section inconsistency.",
    customer="CA filing error risk.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="High — CDNR integrity.",
    risk="Wrong GSTR-1 from product JSON.",
    fix_immediate="Exclude notes where sales_invoice.is_opening_balance (purchase mirror).",
    fix_short="Shared _gst_note_base queryset.",
    fix_long="Filing package with cross-section asserts.",
    effort="0.5d",
    tests="CN on opening invoice absent from CDNR.",
    acceptance="CDNR never references opening invoices.",
    status="Open",
    refs="BB-000335 residual; Wave13 NEW",
)
add(
    title="Composition challan convert creates GST invoice that cannot Complete",
    category="GST",
    subcategory="Registration gates",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Delivery challan",
    files="backend/sales/notes_services.py convert_delivery_challan; registration_gates.py",
    problem="Convert uses is_gst_registered → COMPOSITION+GSTIN gets InvoiceType.GST; assert_may_issue_gst_tax_invoice blocks Complete.",
    evidence="convert_delivery_challan type selection; registration gate on Complete",
    root_cause="is_gst_registered conflates composition with regular.",
    business="Dead draft invoices after challan convert.",
    technical="Type vs gate mismatch.",
    customer="Composition dealers stuck.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Wrong document type vs CMP BoS.",
    risk="Composition segment unusable for challan flow.",
    fix_immediate="Branch on registration_type (REGULAR→GST; COMPOSITION/UNREG→NON_GST/BoS).",
    fix_short="Gate at convert time.",
    fix_long="Document-type policy engine.",
    effort="0.5-1d",
    tests="Composition convert → NON_GST; Complete OK.",
    acceptance="No uncompletable GST draft from composition convert.",
    status="Open",
    refs="BB-000007/342 residual; Wave13 NEW",
)
add(
    title="Purchase additional charges capitalized into Inventory 1400",
    category="Accounting",
    subcategory="Inventory valuation",
    severity="High",
    priority="P1",
    module="Accounting",
    feature="Purchase posting",
    files="backend/accounting/services.py post_purchase",
    problem="Inventory debit uses grand_total-tax (includes charges / after-tax discount effects) not pure item taxables.",
    evidence="post_purchase taxable = grand_total - tax",
    root_cause="Shortcut inventory base.",
    business="Inflated stock asset; wrong COGS later.",
    technical="Valuation ≠ item cost.",
    customer="GP distortion.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Inventory valuation policy unclear.",
    risk="Books diverge from CA expectations.",
    fix_immediate="Debit 1400 = sum(line taxables); charges→expense; discounts separate.",
    fix_short="Configurable landed-cost allocator.",
    fix_long="Landed cost module.",
    effort="1-2d",
    tests="Purchase with freight → 1400 excludes freight.",
    acceptance="Inventory = item taxables unless explicit landed-cost rule.",
    status="Open",
    refs="BB-000322 related; Wave13 NEW",
)
add(
    title="Sales invoice cancel does not restore serials to AVAILABLE",
    category="Inventory",
    subcategory="Serials",
    severity="High",
    priority="P1",
    module="Inventory",
    feature="Serial numbers",
    files="backend/sales/services.py cancel; SerialNumberService",
    problem="Complete transitions serials SOLD; cancel adjusts stock qty only — no SOLD→AVAILABLE.",
    evidence="cancel stock adjust; no SerialNumberService.transition on cancel",
    root_cause="Serial lifecycle incomplete.",
    business="Serials stuck SOLD; cannot resell.",
    technical="Register ≠ stock.",
    customer="Blocked resale of cancelled invoice goods.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Serial traceability break.",
    risk="Electronics retailers blocked.",
    fix_immediate="Reverse serial transitions from invoice line serial lists on cancel.",
    fix_short="Movement-linked serial reverse.",
    fix_long="Unified stock+serial event.",
    effort="1d",
    tests="Sell serial→cancel→serial AVAILABLE.",
    acceptance="Cancel restores serial status.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Delivery challan stock path ignores serial-tracked products",
    category="Inventory",
    subcategory="Serials",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Delivery challan",
    files="backend/sales/notes_services.py complete_challan; DeliveryChallanItem",
    problem="Challan FEFO batch movements only; no SerialNumberService when stock_on_delivery_challan; model may lack serial field.",
    evidence="complete_challan stock without serial transition",
    root_cause="Challan stock feature incomplete for serials.",
    business="Serial stock leaves warehouse without register update.",
    technical="Convert→invoice may skip serials (stock_from_challan).",
    customer="Serial inventory lies.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Traceability.",
    risk="Serial SKUs unsafe with challan stock mode.",
    fix_immediate="Require/transition serials on challan complete when track_serial.",
    fix_short="Skip serial on invoice only if challan already transitioned.",
    fix_long="Unified issue document stock service.",
    effort="1-2d",
    tests="Serial product challan complete updates serial status.",
    acceptance="No qty leave warehouse without serial transition when tracked.",
    status="Open",
    refs="BB-000343 residual; Wave13 NEW",
)
add(
    title="SO reserve FEFO vs rebuild_balance reserved dump mismatch",
    category="Inventory",
    subcategory="Reservations",
    severity="High",
    priority="P1",
    module="Inventory",
    feature="SO reserve",
    files="backend/inventory/services.py reserve_stock rebuild_balance",
    problem="Reserve spreads across FEFO lots; rebuild dumps all CONFIRMED SO qty onto unbatched default-warehouse row.",
    evidence="reserve_stock FEFO; rebuild_balance reserved aggregation unbatched",
    root_cause="Wave 12D SO batch claim incomplete at rebuild.",
    business="After rebuild, available qty lies; oversell risk.",
    technical="Reserved invariant broken by maintenance command.",
    customer="Stock promises fail.",
    security="N/A",
    performance="N/A",
    scalability="Rebuild becomes footgun.",
    compliance="N/A",
    risk="Nightly rebuild corrupts reserved.",
    fix_immediate="Rebuild reserved from same FEFO rules or persist reservation lots.",
    fix_short="Reservation allocation table.",
    fix_long="ATP service.",
    effort="2-3d",
    tests="Reserve FEFO→rebuild→lot reserved unchanged.",
    acceptance="rebuild_balance preserves lot reserved.",
    status="Open",
    refs="BB-000343 residual; Wave13 NEW",
)
add(
    title="FIFO valuation setting does not drive outbound COGS (blended cost used)",
    category="Accounting",
    subcategory="Valuation",
    severity="High",
    priority="P1",
    module="Inventory",
    feature="Valuation method",
    files="backend/inventory/services.py InventoryValuationService; sales complete unit_cost",
    problem="Company FIFO setting documented for reports; COGS uses blended remaining cost.",
    evidence="ValuationService docstring; unit_cost blended path",
    root_cause="FIFO layers not consumed on SALE.",
    business="Misstated COGS if company selects FIFO.",
    technical="Setting lie.",
    customer="Books ≠ claimed method.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Accounting policy misrepresentation.",
    risk="CA rejects FIFO companies.",
    fix_immediate="Layer-consume on SALE for COGS OR remove FIFO from company setting until implemented.",
    fix_short="Honesty: only weighted-average supported.",
    fix_long="True FIFO/FEFO cost layers.",
    effort="3-5d or 0.5d honesty",
    tests="FIFO company either layer-COGS or setting rejected.",
    acceptance="No FIFO claim without FIFO COGS.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Invoice cancel after challan-stocked sale does not reverse challan stock",
    category="Inventory",
    subcategory="Challan",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Challan convert",
    files="backend/sales/services.py cancel complete",
    problem="Challan-converted invoices skip SALE on invoice; cancel looks for invoice SALE → no stock restore; challan stock_posted remains.",
    evidence="cancel posted_sale only reference_type=sales_invoice",
    root_cause="Stock ownership split across challan/invoice without cancel bridge.",
    business="Stock stays issued after invoice cancel; goods physically out, AR may reverse.",
    technical="Orphan issued stock.",
    customer="Inventory shortage after cancel.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Stock register wrong.",
    risk="Challan stock mode unsafe.",
    fix_immediate="On cancel, reverse linked challan SALE lots or block cancel until challan handled.",
    fix_short="Unified stock document graph.",
    fix_long="Single goods-issue entity.",
    effort="1-2d",
    tests="Challan stock→invoice→cancel restores stock.",
    acceptance="Cancel never leaves issued stock without goods.",
    status="Open",
    refs="BB-000270 related; Wave13 NEW",
)
add(
    title="No GSTR-2B import/match — ITC always provisional (compliance gap)",
    category="GST",
    subcategory="ITC",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="GSTR-3B ITC",
    files="backend/reporting/gst_returns.py; accounting post_purchase RCM ITC",
    problem="No 2B models/services; ITC claimable:false; yet GL may show Input ITC (incl RCM) immediately. Product cannot safely drive 3B ITC filing.",
    evidence="ITC disclaimer in gst_returns; no 2B ingest",
    root_cause="Known Deferred; still a launch-blocking compliance gap if ITC UI shown.",
    business="Cannot claim ITC from product safely.",
    technical="Books ITC ≠ filing ITC.",
    customer="CA must ignore product ITC.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical for GST GA — logged High as residual honesty.",
    risk="Users file from GL ITC balances.",
    fix_immediate="UI/API: ITC not claimable banners; park RCM ITC in pending account.",
    fix_short="2B CSV import + match.",
    fix_long="Live GSTN 2B pull.",
    effort="15-30d",
    tests="No claimable ITC without 2B match flag.",
    acceptance="No filing-ready ITC without 2B.",
    status="Open",
    refs="BB-000009 residual honesty; Wave13 NEW",
)
add(
    title="Access JWT still returned in login/OTP/refresh JSON bodies",
    category="Security",
    subcategory="Auth",
    severity="High",
    priority="P0",
    module="Accounts",
    feature="JWT",
    files="backend/accounts/views.py LoginView CookieTokenRefreshView VerifyOtpView; web/src/api/auth.ts",
    problem="httpOnly access cookie set AND access token still in JSON for SPA bootstrap — XSS exfiltrates 15m access despite BB-000375 cookie work.",
    evidence="LoginView L207-216 keep access in body; refresh returns access",
    root_cause="Dual-channel bootstrap left for SPA convenience.",
    business="XSS → account takeover window.",
    technical="Cookie-only story incomplete.",
    customer="Session theft risk.",
    security="High — token theft via XSS.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth hardening incomplete.",
    risk="Undermines httpOnly investment.",
    fix_immediate="Cookie-only access outside DEBUG; SPA boot via /me + refresh cookie.",
    fix_short="Remove access from all JSON responses in prod.",
    fix_long="BFF pattern.",
    effort="1-2d",
    tests="Prod login body has no access; cookie present.",
    acceptance="No access JWT in JSON when DJANGO_ENV production/staging.",
    status="Open",
    refs="BB-000375/266 residual; Wave13 NEW",
)
add(
    title="Users settings checkbox treats canViewFinancialReports !== false as on",
    category="Security",
    subcategory="RBAC UI",
    severity="High",
    priority="P0",
    module="Web",
    feature="Users settings",
    files="web/src/pages/settings/UsersSettingsPage.tsx",
    problem="checked={u.canViewFinancialReports !== false} while BE default False and other flags use !!. Undefined/missing renders as checked.",
    evidence="UsersSettingsPage ~L146",
    root_cause="BB-000350 partial — create helpers fixed === true; settings checkbox missed.",
    business="Owner may save financial ACL open unintentionally.",
    technical="UI/BE default mismatch.",
    customer="Over-permissioned staff.",
    security="Privilege creep.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD UI failure.",
    risk="VIEWER-like users get financials.",
    fix_immediate="checked={u.canViewFinancialReports === true}.",
    fix_short="Audit all !== false capability checkboxes.",
    fix_long="Typed capability form components.",
    effort="0.25d",
    tests="Undefined field renders unchecked.",
    acceptance="All capability checkboxes === true semantics.",
    status="Open",
    refs="BB-000350 residual; Wave13 NEW",
)
add(
    title="AI tax-refusal regex bypassable; LLM can emit tax advice",
    category="Security",
    subcategory="AI safety",
    severity="High",
    priority="P0",
    module="Insights",
    feature="Assistant",
    files="backend/insights/assistant.py TAX_PATTERNS run_assistant_turn",
    problem="Refusal only if regex hits user text. Phrases without GST keywords skip refusal; no output scrubber. Tests cover explicit GSTR only.",
    evidence="TAX_PATTERNS L55-64; run_assistant_turn L510-521",
    root_cause="BB-000369 partial regex list.",
    business="Product emits tax advice despite disclaimer — liability.",
    technical="Safety net incomplete.",
    customer="Reliance on unsafe advice.",
    security="Compliance/legal exposure.",
    performance="N/A",
    scalability="N/A",
    compliance="High — tax advice regulation risk.",
    risk="Pilot CA refuses AI feature.",
    fix_immediate="Broader classifier + output scan; refuse tax+advice intents; footer always.",
    fix_short="Tool-only answers for money topics.",
    fix_long="Separate compliance LLM with allowlist.",
    effort="2-3d",
    tests="Paraphrase tax questions all refuse; output filter test.",
    acceptance="No tax-filing advice leaves assistant.",
    status="Open",
    refs="BB-000369 residual; Wave13 NEW",
)
add(
    title="Root PRODUCTION_READINESS.md stale — contradicts shipped notes/RBAC/JWT",
    category="Documentation",
    subcategory="Honesty",
    severity="High",
    priority="P0",
    module="Docs",
    feature="Production readiness",
    files="PRODUCTION_READINESS.md; docs/reviews/21_PRODUCTION_READINESS.md",
    problem="Root doc still lists unchecked Credit/Debit notes, localStorage JWT, binary RBAC, old score — contradicts shipped Phase1 notes, cookie JWT, Accountant/Viewer.",
    evidence="PRODUCTION_READINESS.md body vs README and Wave 12 code",
    root_cause="Historical doc never archived after waves.",
    business="Operators mis-prioritize; false absences.",
    technical="Docs drift.",
    customer="Trust damage if shared externally.",
    security="Misconfigured ops from wrong checklist.",
    performance="N/A",
    scalability="N/A",
    compliance="Readiness sign-off invalid.",
    risk="Signed Go based on wrong doc.",
    fix_immediate="Banner archive OR rewrite against docs/reviews; remove false absences.",
    fix_short="Single readiness SoT in docs/reviews.",
    fix_long="Generated readiness from register Open P0.",
    effort="0.5-1d",
    tests="Doc lint: no 'notes not implemented' claims.",
    acceptance="Root readiness matches register.",
    status="Open",
    refs="BB-000014 related; Wave13 NEW",
)
add(
    title="settings.py fail-open DEBUG/SECRET defaults outside explicit prod/staging",
    category="Security",
    subcategory="Configuration",
    severity="High",
    priority="P0",
    module="Config",
    feature="Django settings",
    files="backend/config/settings.py",
    problem="DEBUG default 1; insecure SECRET_KEY default; OTP_PEPPER falls back to SECRET_KEY; fail-fast only when DJANGO_ENV in (production,staging) or flag. Mis-set env → DEBUG in reachable deploy.",
    evidence="settings.py DEBUG/SECRET_KEY defaults; env gate",
    root_cause="Developer convenience; BB-000001 partially gated.",
    business="Catastrophic if DJANGO_ENV unset on public host.",
    technical="Fail-open posture.",
    customer="Data breach risk.",
    security="Critical-class if exposed — High given gate exists but footgun remains.",
    performance="N/A",
    scalability="N/A",
    compliance="Secret hygiene.",
    risk="Compose without prod overlay.",
    fix_immediate="Containers require DJANGO_ENV; no SECRET_KEY default when not local; DEBUG=0 without secrets fails.",
    fix_short="entrypoint validates.",
    fix_long="12-factor sealed config.",
    effort="1d",
    tests="Unset DJANGO_ENV in prod-like boot → exit nonzero.",
    acceptance="No insecure defaults on non-local boots.",
    status="Open",
    refs="BB-000001/347 residual; Wave13 NEW",
)

# ─── MEDIUM ─────────────────────────────────────────────────────────────────
add(
    title="Shared global SANDBOX_WEBHOOK_SECRET across all tenants",
    category="Security",
    subcategory="Payments",
    severity="Medium",
    priority="P1",
    module="Payments",
    feature="Sandbox webhooks",
    files="backend/payments/gateway.py _sandbox_webhook_secret",
    problem="One env secret verifies every tenant's sandbox webhooks.",
    evidence="_sandbox_webhook_secret global",
    root_cause="BB-000354 deferred residual still Open-worthy after sandbox-in-prod residual.",
    business="Secret leak forges all sandbox settlements.",
    technical="No tenant isolation on webhook auth.",
    customer="Cross-tenant payment forgery in non-prod (and prod if sandbox slips).",
    security="Medium-High isolation failure.",
    performance="N/A",
    scalability="N/A",
    compliance="Tenant isolation.",
    risk="Shared secret ops practice.",
    fix_immediate="Per-company webhook secret; bind HMAC to company_id.",
    fix_short="Rotate API.",
    fix_long="Disable sandbox settle entirely outside local.",
    effort="1d",
    tests="Company A secret cannot verify company B link.",
    acceptance="No global sandbox webhook secret.",
    status="Open",
    refs="BB-000354 residual; Wave13 NEW",
)
add(
    title="Razorpay webhook amount parse divides by 100 only for int type",
    category="Business Logic",
    subcategory="Payments",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Razorpay adapter",
    files="backend/payments/gateway.py RazorpayAdapter.parse_webhook",
    problem="if amount >= 100 and isinstance(amount_paise, int) — string/float paise stay as rupees → 100× overstatement.",
    evidence="gateway.py ~205-209",
    root_cause="Type-fragile paise conversion.",
    business="Inflated receipts / failed integrity.",
    technical="Parse bug.",
    customer="Wrong charged amount booked.",
    security="Integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="Cash accuracy.",
    risk="Provider payload variance breaks books.",
    fix_immediate="Always treat Razorpay amount as paise; normalize type first.",
    fix_short="Contract tests with string amounts.",
    fix_long="Typed money parser.",
    effort="0.5d",
    tests="String '10000' paise → 100.00 INR.",
    acceptance="All Razorpay amount shapes → correct Decimal rupees.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Staging still remaps empty-cred Razorpay to sandbox via test_mode",
    category="Security",
    subcategory="Payments",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Gateway remap",
    files="backend/payments/services.py create_payment_link",
    problem="test_mode remap allowed when django_env != production; staging can mint sandbox links.",
    evidence="L312-314 django_env != production",
    root_cause="BB-000318 staging ban on settings; create remap uses production-only.",
    business="Staging settles fake money into near-prod data.",
    technical="Env asymmetry.",
    customer="Staging UAT false paid.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="UAT integrity.",
    risk="Staging≈prod data with sandbox.",
    fix_immediate="Treat staging like production for sandbox/test_mode remap.",
    fix_short="Explicit allowlist development|test only.",
    fix_long="Separate sandbox tenant.",
    effort="0.25d",
    tests="Staging test_mode empty creds → 400 not sandbox.",
    acceptance="Staging cannot create sandbox links.",
    status="Open",
    refs="BB-000318 residual; Wave13 NEW",
)
add(
    title="Manual bank recon confirm ignores amount equality",
    category="Accounting",
    subcategory="Bank recon",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Recon",
    files="backend/payments/views.py BankStatementViewSet._confirm_match ReconViewSet.confirm",
    problem="Match created with arbitrary receipt/payment id; no |line.amount|==target.amount check.",
    evidence="_confirm_match no amount assert",
    root_cause="Trust operator fully.",
    business="Wrong cash application; misstatement.",
    technical="No invariant.",
    customer="Recon lies.",
    security="Fraud assist if malicious staff.",
    performance="N/A",
    scalability="N/A",
    compliance="Bank recon controls.",
    risk="Month-end chaos.",
    fix_immediate="Require amount match or Owner override+reason audit.",
    fix_short="Tolerance config.",
    fix_long="Auto-suggest only equal amounts.",
    effort="0.5-1d",
    tests="Mismatched amounts → 400 without override.",
    acceptance="Confirm enforces amount policy.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="PaymentHealthView is HasCompany-only (VIEWER sees AR health)",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Payment health",
    files="backend/payments/views.py PaymentHealthView",
    problem="permission_classes HasCompany only — no CanViewPaymentSurfaces/financial gate.",
    evidence="PaymentHealthView ~429-434",
    root_cause="Wave 12B missed health endpoint.",
    business="VIEWER sees receivables intel.",
    technical="ACL hole.",
    customer="Least-privilege failure.",
    security="Information disclosure.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD.",
    risk="Multi-role pilots leak AR.",
    fix_immediate="Require CanViewPaymentSurfaces or financial; hard-block VIEWER.",
    fix_short="Align all health endpoints.",
    fix_long="Capability matrix codegen.",
    effort="0.25d",
    tests="VIEWER payment health → 403.",
    acceptance="Health requires payment/financial cap.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Cookie JWT auth without CSRF enforcement",
    category="Security",
    subcategory="CSRF",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="CookieJWTAuthentication",
    files="backend/core/authentication.py; backend/config/settings.py",
    problem="Cookie bearer auth without DRF CSRF; dangerous if SameSite=None allowed.",
    evidence="CookieJWTAuthentication; DEFAULT_AUTHENTICATION_CLASSES",
    root_cause="JWT-in-cookie without session CSRF pair.",
    business="Cross-site state-changing requests as victim.",
    technical="CSRF gap.",
    customer="Account abuse.",
    security="Medium CSRF.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth hardening.",
    risk="SameSite misconfig → CSRF.",
    fix_immediate="CSRF for cookie-auth mutations or forbid SameSite=None; prefer header-only access.",
    fix_short="Double-submit CSRF token.",
    fix_long="BFF.",
    effort="1-2d",
    tests="Cross-site POST without CSRF rejected when cookie auth.",
    acceptance="Cookie-auth mutations CSRF-safe.",
    status="Open",
    refs="BB-000353 residual; Wave13 NEW",
)
add(
    title="Invite without password is a dead end (no invite-token flow)",
    category="Security",
    subcategory="Auth",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="Invites",
    files="backend/accounts/views.py CompanyUserViewSet.create",
    problem="Prod/staging forbid invite password; sets unusable password; promises login token / password-change — no invite-token/email flow exists.",
    evidence="CompanyUserViewSet ~490-506",
    root_cause="BB-000366 partial — removed password without replacement.",
    business="Staff accounts locked out.",
    technical="Incomplete invite UX.",
    customer="Cannot onboard staff in prod.",
    security="Owners may re-enable password invites in non-prod habits.",
    performance="N/A",
    scalability="N/A",
    compliance="Access provisioning.",
    risk="Pilot multi-user blocked.",
    fix_immediate="Signed invite email + set-password endpoint.",
    fix_short="Remove password field entirely; document.",
    fix_long="SCIM/IdP.",
    effort="2-3d",
    tests="Invite → email token → set password → login.",
    acceptance="Prod invite onboarding works without shared passwords.",
    status="Open",
    refs="BB-000366 residual; Wave13 NEW",
)
add(
    title="OTP claims sent while SMS providers are stubs",
    category="Security",
    subcategory="OTP",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="OTP",
    files="backend/accounts/views.py RequestOtpView; backend/core/services/sms.py",
    problem="Console/stub SMS no-op but API returns success and creates challenge. Real MSG91/Twilio not implemented.",
    evidence="SmsProvider.send_otp stubs",
    root_cause="BB-000006 honesty incomplete for OTP_ENABLED path.",
    business="False sense of OTP auth; users locked out.",
    technical="Delivery lie.",
    customer="Cannot login via OTP in real deploy.",
    security="Auth availability failure.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth.",
    risk="OTP_ENABLED=1 in prod without SMS.",
    fix_immediate="Fail closed unless real provider wired; never claim sent on stub outside dev.",
    fix_short="Implement MSG91/Twilio.",
    fix_long="Multi-provider SMS.",
    effort="0.5d honesty / 3-5d real SMS",
    tests="Stub+OTP_ENABLED non-dev → 503.",
    acceptance="Success response iff SMS accepted by real provider.",
    status="Open",
    refs="BB-000006/332 residual; Wave13 NEW",
)
add(
    title="Stock valuation/balances readable by VIEWER (cost leakage)",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Inventory",
    feature="Valuation reports",
    files="backend/inventory/views.py StockValuationReportView StockBalanceViewSet StockMovementViewSet",
    problem="Valuation/balances/movements HasCompany — VIEWER sees costed inventory.",
    evidence="permission_classes HasCompany on valuation/balance views",
    root_cause="Wave 12B tightened sales/purchases; inventory cost left open.",
    business="Cost/GP leakage to read-only users.",
    technical="ACL gap.",
    customer="Competitive/internal privacy.",
    security="Information disclosure.",
    performance="N/A",
    scalability="N/A",
    compliance="Financial data ACL.",
    risk="VIEWER role unsafe for cost.",
    fix_immediate="Valuation → CanViewFinancialReports; balances → inventory/sales cap; block VIEWER.",
    fix_short="Field-level cost strip.",
    fix_long="ACL matrix.",
    effort="0.5d",
    tests="VIEWER valuation → 403.",
    acceptance="Costed inventory not HasCompany-only.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="FileAssetViewSet lists company files to any member (PDF bypass)",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Core",
    feature="File assets",
    files="backend/core/views.py FileAssetViewSet",
    problem="Any active member lists/downloads FileAssets including invoice PDFs, bypassing CanViewSalesSurfaces.",
    evidence="FileAssetViewSet HasCompany",
    root_cause="Shared file API without kind ACL.",
    business="VIEWER downloads invoices.",
    technical="ACL bypass via files.",
    customer="Document confidentiality failure.",
    security="Authorization bypass.",
    performance="N/A",
    scalability="N/A",
    compliance="Data access.",
    risk="Multi-role unsafe.",
    fix_immediate="Scope by document permission/kind; Owner-only sensitive kinds.",
    fix_short="Signed short-lived download URLs tied to cap.",
    fix_long="Object-level ACL.",
    effort="1-2d",
    tests="VIEWER cannot download sales invoice PDF asset.",
    acceptance="File access mirrors document ACL.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Masters list/retrieve still HasCompany (VIEWER sees parties & prices)",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Masters",
    feature="Customers/products",
    files="backend/masters/views.py",
    problem="Mutate Owner-only; read HasCompany — product prices, customer phone/GSTIN to VIEWER despite search PII strip.",
    evidence="masters views read HasCompany",
    root_cause="BB-000297 intentional half-measure.",
    business="Inconsistent least privilege.",
    technical="Search vs masters ACL drift.",
    customer="PII/price leak to viewers.",
    security="Information disclosure.",
    performance="N/A",
    scalability="N/A",
    compliance="PII.",
    risk="VIEWER role oversharing.",
    fix_immediate="Align read gates with sales/purchase caps; strip fields for VIEWER.",
    fix_short="Serializer role-aware.",
    fix_long="Policy engine.",
    effort="1d",
    tests="VIEWER masters prices/PII stripped or 403.",
    acceptance="VIEWER cannot read full party/price via masters.",
    status="Open",
    refs="BB-000297 residual; Wave13 NEW",
)
add(
    title="Dual FE/BE IN_STATE_NAME_TO_CODE with no CI key-parity test",
    category="GST",
    subcategory="Tax math",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="State maps",
    files="web/src/utils/tax.ts; backend/core/services/billing.py",
    problem="Maps duplicated; no test asserting FE↔BE key equality after BB-000320.",
    evidence="Two maps; no parity test in CI",
    root_cause="Port without contract test.",
    business="Silent preview/posting drift on UT rename.",
    technical="Dual maintenance.",
    customer="Tax mismatch regressions.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Tax engine drift.",
    risk="Next GST state update breaks one side.",
    fix_immediate="pytest/vitest sorted key diff OR generate one map.",
    fix_short="Shared JSON fixture.",
    fix_long="Server preview SoT.",
    effort="0.5d",
    tests="CI fails if keys diverge.",
    acceptance="Automated FE↔BE map parity.",
    status="Open",
    refs="BB-000320 residual; Wave13 NEW",
)
add(
    title="POS string-equality fallback classifies unmapped text as inter/intra",
    category="GST",
    subcategory="Tax math",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="resolvePlaceOfSupply",
    files="web/src/utils/tax.ts; backend/core/services/billing.py is_intra_state",
    problem="When codes missing, FE returns a===b ? intra : inter; invents tax type from free text.",
    evidence="tax.ts resolvePlaceOfSupply fallback; BE similar",
    root_cause="Fallback instead of unknown.",
    business="Wrong tax type for typoed states.",
    technical="Unsafe default.",
    customer="Wrong GST collected.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="POS correctness.",
    risk="Paired with placeOfSupplyKnown FE bug.",
    fix_immediate="Unknown when either side unmapped; never invent from free text.",
    fix_short="Block Complete until mapped.",
    fix_long="Server SoT.",
    effort="0.5d",
    tests="Typos → unknown not inter.",
    acceptance="Unmapped never yields intra/inter.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="ai_features_enabled defaults True; FE treats missing as enabled",
    category="Configuration",
    subcategory="AI",
    severity="Medium",
    priority="P1",
    module="Insights",
    feature="AI settings",
    files="backend/accounts/models.py; web/src/pages/settings/AiSettingsPage.tsx",
    problem="Model default True; FE !== false / form default true — new companies get AI on.",
    evidence="ai_features_enabled default=True; AiSettingsPage",
    root_cause="Growth default without consent/cost control.",
    business="Unexpected LLM cost/liability.",
    technical="Fail-open AI.",
    customer="Surprise AI on.",
    security="Data to LLM without explicit opt-in.",
    performance="Cost.",
    scalability="Cost at fleet.",
    compliance="Data processing consent.",
    risk="Pilot AI bills / advice risk.",
    fix_immediate="Default False + migration; UI === true.",
    fix_short="Explicit opt-in wizard.",
    fix_long="Per-capability AI flags.",
    effort="0.5d",
    tests="New company ai_features_enabled False.",
    acceptance="AI off until Owner enables.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Dashboard route bypasses RoleRoute financial gate",
    category="Security",
    subcategory="RBAC UI",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="Dashboard",
    files="web/src/App.tsx",
    problem="Index Dashboard under ProtectedRoute only — no canViewFinancialReports/viewer gate.",
    evidence="App.tsx Route index DashboardPage",
    root_cause="Dashboard assumed universal.",
    business="Low-ACL users see KPI/AR if API allows.",
    technical="FE ACL hole.",
    customer="Oversharing.",
    security="UI disclosure.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD UI.",
    risk="VIEWER dashboard leak.",
    fix_immediate="Wrap with financial/dashboard allow RoleRoute.",
    fix_short="API dashboard ACL match.",
    fix_long="Widget-level ACL.",
    effort="0.5d",
    tests="VIEWER redirected from dashboard KPIs.",
    acceptance="Dashboard respects financial ACL.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="fetchAllPages still hard-fails at 50 pages on many list screens",
    category="Performance",
    subcategory="Frontend",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="Pagination",
    files="web/src/api/resources.ts; invoice/customer/journal pages",
    problem="Throws Too many pages — many screens still fetch-all instead of server list UX.",
    evidence="resources.ts L180-203",
    root_cause="BB-000348 partial picker migration incomplete.",
    business="Large pilots hard-error on history.",
    technical="Client scalability limit.",
    customer="App breaks at ~5k rows.",
    security="N/A",
    performance="High client load.",
    scalability="Hard cap.",
    compliance="N/A",
    risk="Growing tenants hit wall.",
    fix_immediate="Server-driven lists + search for history screens.",
    fix_short="Keep cap only for tiny pickers.",
    fix_long="Virtualized infinite query.",
    effort="3-5d",
    tests="10k invoices list page works without fetchAllPages.",
    acceptance="No production screen depends on fetchAllPages beyond pickers.",
    status="Open",
    refs="BB-000348 residual; Wave13 NEW",
)
add(
    title="GST Health ignores opening filter (false alerts on migration stubs)",
    category="GST",
    subcategory="Health",
    severity="Medium",
    priority="P2",
    module="Reporting",
    feature="GST health",
    files="backend/reporting/gst_health.py",
    problem="No is_opening_balance=False while GSTR builders exclude openings.",
    evidence="build_gst_health invoice query ~76-86",
    root_cause="BB-000335 incomplete across health.",
    business="False HSN/POS/e-invoice alerts.",
    technical="Noise.",
    customer="Alert fatigue.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Health signal quality.",
    risk="Real issues ignored.",
    fix_immediate="Same opening exclusion as _gst_sales_invoices.",
    fix_short="Shared queryset.",
    fix_long="Health rules engine.",
    effort="0.25d",
    tests="Opening invoice not in GST health issues.",
    acceptance="Health aligns with GSTR invoice set.",
    status="Open",
    refs="BB-000335 residual; Wave13 NEW",
)
add(
    title="EINVOICE_PENDING alert treats MANUAL_IRN as not generated",
    category="GST",
    subcategory="Health",
    severity="Medium",
    priority="P2",
    module="Reporting",
    feature="GST health",
    files="backend/reporting/gst_health.py",
    problem="Alerts unless einvoice_status==GENERATED; ignores MANUAL_IRN.",
    evidence="gst_health ~160-170",
    root_cause="BB-000214 status not wired into health.",
    business="Permanent false criticals for attested IRNs.",
    technical="Alert bug.",
    customer="Noise.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Ops signal.",
    risk="Ignore all e-invoice alerts.",
    fix_immediate="Accept GENERATED or MANUAL_IRN (warn for manual).",
    fix_short="Severity tiers.",
    fix_long="Compliance state machine.",
    effort="0.25d",
    tests="MANUAL_IRN no critical pending.",
    acceptance="Manual IRN not critical-pending.",
    status="Open",
    refs="BB-000214 residual; Wave13 NEW",
)
add(
    title="e-Way validation requires buyer GSTIN (blocks B2C/URP)",
    category="GST",
    subcategory="e-Way",
    severity="Medium",
    priority="P1",
    module="Sales",
    feature="e-Way",
    files="backend/sales/eway_payload.py _validate_customer_party",
    problem="Unconditional require customer.gstin — interstate B2C URP cannot prepare.",
    evidence="eway_payload validation",
    root_cause="B2B-only assumption.",
    business="Cannot prepare e-way for unregistered buyers.",
    technical="NIC URP path missing.",
    customer="Compliance gap.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="e-Way B2C.",
    risk="Wrong refusal of legal e-way.",
    fix_immediate="Allow URP when unregistered; GSTIN mandatory only B2B.",
    fix_short="SupTyp-aware validation.",
    fix_long="Full NIC schema matrix.",
    effort="0.5d",
    tests="B2C without GSTIN prepare OK with URP.",
    acceptance="URP e-way prepare succeeds.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Purchase CN/DN skip place-of-supply hard gate",
    category="GST",
    subcategory="POS",
    severity="Medium",
    priority="P2",
    module="Purchases",
    feature="Notes",
    files="backend/purchases/notes_services.py",
    problem="Sales notes call assert_place_of_supply_for_gst; purchase notes do not.",
    evidence="purchase notes complete without POS assert",
    root_cause="Asymmetric gates.",
    business="Wrong CGST/SGST vs IGST on notes.",
    technical="ITC distortion risk.",
    customer="GSTR ITC wrong.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Note tax split.",
    risk="Purchase returns tax wrong.",
    fix_immediate="Same POS assert as sales notes / purchase Complete.",
    fix_short="Shared note complete guard.",
    fix_long="Tax policy service.",
    effort="0.5d",
    tests="Blank supplier state purchase CN blocked.",
    acceptance="Purchase notes POS-gated.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="JournalEntry.number has no uniqueness constraint",
    category="Accounting",
    subcategory="Vouchers",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="Journals",
    files="backend/accounting/models.py JournalEntry; PostingService.post",
    problem="Unique on (source_type,source_id,purpose) for POSTED; number unconstrained; pattern JV-{type}-{purpose}-{id} truncates.",
    evidence="models JournalEntry Meta",
    root_cause="BB-000363 partial.",
    business="Audit trail / Tally export ambiguity.",
    technical="Collision risk.",
    customer="Hard to cite vouchers.",
    security="N/A",
    performance="N/A",
    scalability="Collision grows.",
    compliance="Voucher identity.",
    risk="Duplicate numbers in exports.",
    fix_immediate="UniqueConstraint(company, number) + sequential series.",
    fix_short="Human voucher series per FY.",
    fix_long="DocumentNumberService for journals.",
    effort="1d",
    tests="Duplicate number rejected.",
    acceptance="(company,number) unique.",
    status="Open",
    refs="BB-000363 residual; Wave13 NEW",
)
add(
    title="Balance sheet folds all-time P&L without year close to RE",
    category="Accounting",
    subcategory="Reports",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="Balance sheet",
    files="backend/accounting/reports.py balance_sheet profit_and_loss",
    problem="P&L from dawn of books into BS; no period close → 3100 Retained Earnings.",
    evidence="balance_sheet calls profit_and_loss(date_to=as_of) without FY open",
    root_cause="No year-end close.",
    business="Multi-year BS current earnings balloon.",
    technical="Report ≠ Tally FY model.",
    customer="FY comparison wrong.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Presentation.",
    risk="CA rejects BS.",
    fix_immediate="Year-end close JE to RE; P&L scoped to FY.",
    fix_short="FY parameter required.",
    fix_long="Full period close workflow.",
    effort="2-4d",
    tests="After FY close, prior P&L in RE not current earnings.",
    acceptance="BS respects FY close.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="RCM purchase notes Inventory leg uses grand_total not taxable base",
    category="Accounting",
    subcategory="RCM",
    severity="Medium",
    priority="P1",
    module="Accounting",
    feature="Purchase notes",
    files="backend/accounting/services.py post_note RCM branches",
    problem="RCM CN inventory leg grand_total-round_off while reversing tax; charges distort vs original inventory_amount.",
    evidence="post_note PURCHASE_CREDIT/DEBIT RCM ~324-364",
    root_cause="BB-000336 incomplete inventory base.",
    business="Unbalanced inventory vs purchase RCM under charges.",
    technical="GL drift.",
    customer="Books wrong on RCM returns.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="RCM accounting.",
    risk="RCM-heavy traders broken books.",
    fix_immediate="Inventory leg = rcm_taxable/taxable_total; AP = payable grand_total.",
    fix_short="Shared amount resolver with purchase post.",
    fix_long="Event-sourced posting.",
    effort="1d",
    tests="RCM purchase+CN with freight → 1400 nets.",
    acceptance="RCM note inventory matches taxable inventory base.",
    status="Open",
    refs="BB-000336 residual; Wave13 NEW",
)
add(
    title="Nil-rated GSTR section conflates 0% with nil/exempt/non-GST",
    category="GST",
    subcategory="GSTR-1",
    severity="Medium",
    priority="P2",
    module="Reporting",
    feature="Nil bucket",
    files="backend/reporting/gst_returns.py build_gstr1",
    problem="rate==0 → nil_taxable with best-effort note — exempt vs nil vs non-GST conflated.",
    evidence="build_gstr1 nil bucket",
    root_cause="No supply-type flags.",
    business="Table 8 wrong if used for filing.",
    technical="Classification missing.",
    customer="Filing risk.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR-1 Table 8.",
    risk="Wrong nil reporting.",
    fix_immediate="Keep nil empty until classified; or explicit supply-type.",
    fix_short="Line supply_type enum.",
    fix_long="Full GSTR schema types.",
    effort="2-3d",
    tests="0% GST line not auto-nil without flag.",
    acceptance="Nil only when explicitly classified.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Registration gate only on Complete — TAX drafts still compute illegal GST",
    category="GST",
    subcategory="Registration",
    severity="Medium",
    priority="P2",
    module="Sales",
    feature="Draft invoices",
    files="backend/core/services/registration_gates.py; sales set_items",
    problem="Gate blocks Complete for UNREGISTERED/COMPOSITION tax_enabled; drafts of TAX type still created and tax-computed.",
    evidence="Gate on Complete; create/set_items ungated",
    root_cause="Late gate.",
    business="Misleading tax on drafts/PDF preview.",
    technical="Illegal GST preview.",
    customer="Confusion; wrong quotes.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Document type honesty.",
    risk="Staff prints draft as tax invoice.",
    fix_immediate="Gate on create/set_items too.",
    fix_short="Force NON_GST type at create for composition.",
    fix_long="Policy on document factory.",
    effort="0.5-1d",
    tests="Composition create TAX → 400.",
    acceptance="No taxable draft for composition/unregistered.",
    status="Open",
    refs="BB-000007 residual; Wave13 NEW",
)
add(
    title="Release reservation order ≠ FEFO reserve order",
    category="Inventory",
    subcategory="SO reserve",
    severity="Medium",
    priority="P2",
    module="Inventory",
    feature="Reservations",
    files="backend/inventory/services.py release_reservation",
    problem="Reserve FEFO by expiry; release order_by('-id') newest first.",
    evidence="release_reservation order_by -id",
    root_cause="No stored allocation.",
    business="Reserved qty sticks on early-expiry lots after partial release.",
    technical="Asymmetric allocate/release.",
    customer="Wrong available on FEFO lots.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Oversell near-expiry.",
    fix_immediate="Release same FEFO order or store allocation rows.",
    fix_short="Reservation line table.",
    fix_long="ATP.",
    effort="1d",
    tests="Partial release frees earliest expiry first.",
    acceptance="Release mirrors reserve order.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Duplicate CAPTURED webhook IDs mark second GatewayPayment CAPTURED without receipt",
    category="Business Logic",
    subcategory="Payments",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Webhooks",
    files="backend/payments/services.py finalize_gateway_payment",
    problem="If link already PAID, new provider_payment_id row forced CAPTURED with no receipt/allocation.",
    evidence="finalize ~418-422",
    root_cause="Idempotency incomplete for second payment id.",
    business="Provider paid twice; books one receipt.",
    technical="Silent money loss / recon break.",
    customer="Lost funds hard to spot.",
    security="Integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="Cash recon.",
    risk="Double capture unnoticed.",
    fix_immediate="Second → FAILED/IGNORED + alert; never CAPTURED without receipt.",
    fix_short="Ops notification.",
    fix_long="Payment recon workspace.",
    effort="0.5d",
    tests="Second payment id on paid link → not CAPTURED silently.",
    acceptance="CAPTURED iff receipt exists.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Light e2e mock-only; seeds obsolete JWT keys; ACL unproven",
    category="Testing",
    subcategory="E2E",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="Playwright",
    files="web/e2e/smoke.spec.ts; playwright.config.ts",
    problem="Mock auth; seeds bizboard.access/refresh; does not prove RoleRoute/API ACL. CI green without RBAC/GST regressions.",
    evidence="smoke.spec.ts; --mode e2e mocks",
    root_cause="BB-000370/378 partial.",
    business="False CI confidence.",
    technical="Test theater.",
    customer="Regressions ship.",
    security="ACL untested at e2e.",
    performance="N/A",
    scalability="N/A",
    compliance="QA gate weak.",
    risk="Critical RBAC holes merge green.",
    fix_immediate="Role matrix e2e against golden API; deny VIEWER routes.",
    fix_short="Stop seeding obsolete JWT keys.",
    fix_long="Remove mocks from critical paths.",
    effort="3-5d",
    tests="VIEWER denied sales create in e2e.",
    acceptance="Critical ACL paths in required golden e2e.",
    status="Open",
    refs="BB-000370/378 residual; Wave13 NEW",
)
add(
    title="Prod compose overlay thin — no TLS, weak health, latest tags",
    category="DevOps",
    subcategory="Production",
    severity="Medium",
    priority="P1",
    module="DevOps",
    feature="compose.prod",
    files="docker-compose.prod.yml; nginx/default.conf",
    problem="Overlay mostly forces DJANGO_ENV/DEBUG + env_file; nginx HTTP; beat health bogus; digest pin incomplete story.",
    evidence="compose.prod thin; nginx listen 80",
    root_cause="BB-000015/368 partial.",
    business="Easy to believe prod compose = hardened.",
    technical="Ops false confidence.",
    customer="MITM / downtime.",
    security="No TLS at edge in stock compose.",
    performance="N/A",
    scalability="N/A",
    compliance="Prod baseline.",
    risk="Teams deploy compose.prod as-is to internet.",
    fix_immediate="Document TLS mandatory; fix beat health; pin digests.",
    fix_short="TLS termination example + HSTS.",
    fix_long="K8s/Helm hardened chart.",
    effort="2-4d",
    tests="CI validates compose.prod healthchecks have no or True.",
    acceptance="Prod overlay checklist signed for TLS/backups/health.",
    status="Open",
    refs="BB-000015/368 residual; Wave13 NEW",
)
add(
    title="Nginx CSP allows unsafe-inline styles; Host IP remapped to localhost",
    category="Security",
    subcategory="CSP",
    severity="Medium",
    priority="P2",
    module="DevOps",
    feature="nginx",
    files="nginx/default.conf",
    problem="style-src 'unsafe-inline'; bare IPs remapped to localhost for Django Host.",
    evidence="default.conf CSP and $django_host map",
    root_cause="SPA convenience.",
    business="Weaker XSS containment; Host rewrite masks LAN misconfig.",
    technical="CSP debt.",
    customer="XSS impact higher.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Browser security.",
    risk="XSS more powerful.",
    fix_immediate="Nonces/hashes for styles; require explicit ALLOWED_HOSTS for LAN IPs.",
    fix_short="Report-Only CSP tighten.",
    fix_long="Strict CSP.",
    effort="1-2d",
    tests="CSP without unsafe-inline in prod profile.",
    acceptance="No unsafe-inline in production CSP.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="CD publishes without provenance attestation / compose.prod validation",
    category="DevOps",
    subcategory="CD",
    severity="Medium",
    priority="P1",
    module="CI",
    feature="cd.yml",
    files=".github/workflows/cd.yml",
    problem="workflow_run on CI success; no artifact attestation; no compose.prod validation job.",
    evidence="cd.yml triggers",
    root_cause="BB-000368 partial.",
    business="Ambiguous which SHA is releasable.",
    technical="Supply chain weak.",
    customer="Wrong image deploy risk.",
    security="Supply chain.",
    performance="N/A",
    scalability="N/A",
    compliance="Change control.",
    risk="Latest confusion.",
    fix_immediate="Require checks API for SHA; sign images; validate compose.prod.",
    fix_short="Separate deploy approval job.",
    fix_long="SLSA provenance.",
    effort="2-3d",
    tests="CD fails without attestation.",
    acceptance="Only attested digests deployable.",
    status="Open",
    refs="BB-000368 residual; Wave13 NEW",
)
add(
    title="Structured observability thin — no request-id/JSON logs/metrics SLOs",
    category="DevOps",
    subcategory="Observability",
    severity="Medium",
    priority="P2",
    module="DevOps",
    feature="Logging/metrics",
    files="backend/config/settings.py; core middleware",
    problem="Limited structured logging; no ubiquitous request-id; metrics/SLO dashboards absent for payments/GST jobs.",
    evidence="BB-000372 prior; residual still true for SRE readiness",
    root_cause="Feature velocity over SRE.",
    business="MTTR high in prod incidents.",
    technical="Blind ops.",
    customer="Longer outages.",
    security="Forensics weak.",
    performance="Cannot capacity plan.",
    scalability="Unmeasured.",
    compliance="Ops evidence.",
    risk="Pilot incidents un-debuggable.",
    fix_immediate="Request-id middleware + JSON logs; basic RED metrics.",
    fix_short="Sentry+metrics dashboards for webhooks/celery.",
    fix_long="SLO/error budgets.",
    effort="3-5d",
    tests="Request-id present on API responses/logs.",
    acceptance="Payment webhook traceable end-to-end.",
    status="Open",
    refs="BB-000372 residual; Wave13 NEW",
)
add(
    title="Tally commit force=True API can bypass validation errors",
    category="Integration",
    subcategory="Tally",
    severity="Medium",
    priority="P2",
    module="Integrations",
    feature="Tally import",
    files="backend/integrations/tally/adapter.py commit_tally_preview",
    problem="Client amount rewrite largely fixed via reparse; force=True can still commit with errors if exposed.",
    evidence="commit_tally_preview force path",
    root_cause="Escape hatch without Owner/audit gate.",
    business="Bad masters/openings committed.",
    technical="Validation bypass.",
    customer="Corrupt migration.",
    security="Integrity if force exposed broadly.",
    performance="N/A",
    scalability="N/A",
    compliance="Migration quality.",
    risk="Support uses force casually.",
    fix_immediate="Owner-only force + audit log; default deny.",
    fix_short="Remove force from public API.",
    fix_long="Quarantine error rows workflow.",
    effort="0.5d",
    tests="Non-owner force → 403; force audited.",
    acceptance="Force cannot be silent.",
    status="Open",
    refs="BB-000346 residual; Wave13 NEW",
)
add(
    title="WhatsApp remains link-only — delivery expectations residual",
    category="Integration",
    subcategory="WhatsApp",
    severity="Medium",
    priority="P2",
    module="Core",
    feature="Notifications",
    files="backend/core/services/notifications.py; web i18n",
    problem="LINK_READY wa.me only; button label WhatsApp may still imply delivery despite helper text improvements.",
    evidence="notifications LINK_READY; i18n Opens WhatsApp link",
    root_cause="Product scope; residual UX expectation.",
    business="Users expect sent messages.",
    technical="Not Business API.",
    customer="Support tickets 'message not sent'.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Comms honesty.",
    risk="Trust hit.",
    fix_immediate="Inline 'opens wa.me — not delivered by BizBoard' on every CTA.",
    fix_short="Rename button Open in WhatsApp.",
    fix_long="WhatsApp Business API optional.",
    effort="0.25d copy / large for API",
    tests="UI copy assertion in e2e.",
    acceptance="No CTA implies BizBoard delivered WhatsApp.",
    status="Open",
    refs="BB-000036 residual; Wave13 NEW",
)
add(
    title="Accessibility residual — no skip link; sparse live regions on billing",
    category="UX",
    subcategory="a11y",
    severity="Medium",
    priority="P2",
    module="Web",
    feature="App shell",
    files="web/src/layouts/AppShell.tsx; billing pages",
    problem="No skip-to-content; sparse aria-live for save/errors; icon buttons inconsistently labeled.",
    evidence="grep a11y patterns thin",
    root_cause="BB-000371 partial.",
    business="Keyboard/AT users blocked.",
    technical="a11y debt.",
    customer="Exclusion.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="WCAG aspirational miss.",
    risk="Enterprise accessibility RFPs fail.",
    fix_immediate="Skip link, main landmark, live regions on mutations.",
    fix_short="axe in CI smoke.",
    fix_long="WCAG 2.2 AA program.",
    effort="2-4d",
    tests="axe critical pages clean.",
    acceptance="Skip link + live regions on invoice save.",
    status="Open",
    refs="BB-000371 residual; Wave13 NEW",
)
add(
    title="Capability helpers inconsistent — inventory/import still truthy ||",
    category="Security",
    subcategory="RBAC UI",
    severity="Medium",
    priority="P2",
    module="Web",
    feature="permissions.ts",
    files="web/src/utils/permissions.ts",
    problem="canCreate* use === true; canImport/inventory/cancel/export use user.flag || isOwner truthy.",
    evidence="permissions.ts L23-32, L61-62",
    root_cause="BB-000350 incomplete sweep.",
    business="Inconsistent least-privilege.",
    technical="Helper drift.",
    customer="Wrong button enablement.",
    security="Fail-open risk if fields odd.",
    performance="N/A",
    scalability="N/A",
    compliance="ACL UI.",
    risk="Regression to !== false patterns.",
    fix_immediate="All gates === true + owner override.",
    fix_short="Unit tests per helper.",
    fix_long="Generated from BE capability list.",
    effort="0.5d",
    tests="undefined flag → deny for non-owner.",
    acceptance="No truthy capability checks.",
    status="Open",
    refs="BB-000350 residual; Wave13 NEW",
)
add(
    title="post_sales_invoice trusts header tax totals without line/POS assert",
    category="Accounting",
    subcategory="Tax GL",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="Sales posting",
    files="backend/accounting/services.py post_sales_invoice",
    problem="Credits 2210/2220/2230 from headers; no assert header==sum(lines) or intra/inter consistency.",
    evidence="post_sales_invoice header taxes",
    root_cause="Trust document headers.",
    business="Output GST GL wrong if header drift.",
    technical="No posting invariant.",
    customer="GSTR vs books mismatch.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Tax GL.",
    risk="Amend races corrupt Output GST.",
    fix_immediate="Assert Σ line taxes == headers before post; refuse unbalanced split.",
    fix_short="Recompute from lines at post.",
    fix_long="Tax engine single writer.",
    effort="0.5-1d",
    tests="Header≠lines → post refuses.",
    acceptance="Unbalanced tax cannot post.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Auto purchase CN uses SalesReturn reason enum",
    category="GST",
    subcategory="Notes",
    severity="Low",
    priority="P3",
    module="Purchases",
    feature="Purchase return CN",
    files="backend/purchases/services.py complete_return",
    problem="Purchase return auto-CN uses PurchaseNoteReason.SALES_RETURN.",
    evidence="complete_return reason=SALES_RETURN",
    root_cause="Enum reuse.",
    business="GSTR reason/CDNR semantics wrong.",
    technical="Dirty data.",
    customer="Confusing reason labels.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Low — reason code.",
    risk="Filters mis-bucket notes.",
    fix_immediate="Dedicated PURCHASE_RETURN reason.",
    fix_short="Migrate existing rows.",
    fix_long="Reason taxonomy per doc type.",
    effort="0.25d",
    tests="Auto CN reason purchase_return.",
    acceptance="No SALES_RETURN on purchase notes.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="GSTR cancelled-doc count includes openings inconsistently",
    category="GST",
    subcategory="GSTR-1",
    severity="Low",
    priority="P3",
    module="Reporting",
    feature="Docs table",
    files="backend/reporting/gst_returns.py docs.invoices_cancelled",
    problem="Cancelled count filters GST types/dates but not is_opening_balance.",
    evidence="docs.invoices_cancelled query",
    root_cause="Filter drift vs _gst_sales_invoices.",
    business="Docs table mismatch.",
    technical="Cosmetic/section inconsistency.",
    customer="Confusion in GSTR aid.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Low.",
    risk="Minor filing aid noise.",
    fix_immediate="Align filters with _gst_sales_invoices.",
    fix_short="Shared cancelled queryset.",
    fix_long="Single docs builder.",
    effort="0.25d",
    tests="Opening cancelled excluded from docs count.",
    acceptance="Docs counts match section invoice universe.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Universal search still returns product catalog to VIEWER",
    category="Security",
    subcategory="RBAC",
    severity="Low",
    priority="P3",
    module="Search",
    feature="Universal search",
    files="backend/search/views.py",
    problem="Products always queried; pricing stripped but SKU/barcode/name remain for VIEWER.",
    evidence="UniversalSearchView products always",
    root_cause="Catalog treated as public within tenant.",
    business="Catalog enumeration by read-only users.",
    technical="Minor ACL.",
    customer="Internal catalog leak.",
    security="Low disclosure.",
    performance="N/A",
    scalability="N/A",
    compliance="Least privilege.",
    risk="Low.",
    fix_immediate="Gate products behind sales/purchase/inventory capability.",
    fix_short="Role-aware search facets.",
    fix_long="Search ACL policy.",
    effort="0.25d",
    tests="VIEWER search no products without cap.",
    acceptance="Product hits capability-gated.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Migrations run in compose api command — multi-replica race",
    category="DevOps",
    subcategory="Migrations",
    severity="Low",
    priority="P2",
    module="DevOps",
    feature="compose",
    files="docker-compose.yml api command; backend/Dockerfile",
    problem="migrate in api startup; scaled replicas race migrations.",
    evidence="compose api command migrate && gunicorn",
    root_cause="Convenience.",
    business="Partial boots / lock contention.",
    technical="Migrate not one-shot job.",
    customer="Deploy flakes.",
    security="N/A",
    performance="Startup delay.",
    scalability="Breaks horizontal scale.",
    compliance="Change control.",
    risk="Scale-out footgun.",
    fix_immediate="One-shot migrate job before scale-out.",
    fix_short="Migration lock documented.",
    fix_long="Init container / Job.",
    effort="0.5d",
    tests="Docs/CI assert migrate job pattern for prod.",
    acceptance="Only one migrate runner in prod pattern.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="Accounting period CLOSE allowed with CanPostJournals (Accountant default)",
    category="Security",
    subcategory="RBAC",
    severity="Low",
    priority="P3",
    module="Accounting",
    feature="Periods",
    files="backend/accounting/views.py PeriodViewSet; CompanyUser capability defaults",
    problem="CLOSE/destroy non-system accounts = CanPostJournals; ACCOUNTANT defaults can_post_journals=True.",
    evidence="PeriodViewSet permissions; capability_defaults_for_role",
    root_cause="SoD not Owner-only for period close.",
    business="Non-owner closes books.",
    technical="High blast radius invite default.",
    customer="Locked periods unexpectedly.",
    security="SoD weak.",
    performance="N/A",
    scalability="N/A",
    compliance="Period control.",
    risk="Accountant mistake locks company.",
    fix_immediate="Period CLOSE + system CoA → Owner-only.",
    fix_short="Dual control.",
    fix_long="Close approval workflow.",
    effort="0.5d",
    tests="Accountant CLOSE → 403.",
    acceptance="Only Owner closes periods.",
    status="Open",
    refs="Wave13 NEW",
)
add(
    title="e-Invoice/e-Way PIN fallback can emit 0",
    category="GST",
    subcategory="Payload",
    severity="Low",
    priority="P3",
    module="Sales",
    feature="e-Invoice payload",
    files="backend/sales/einvoice_payload.py; eway_payload.py",
    problem="Pin fallbacks or '0' / isdigit else 0 can still slip to IRP.",
    evidence="pin or '0' patterns",
    root_cause="Defensive default wrong for NIC.",
    business="IRP reject or wrong geography.",
    technical="Validation gap.",
    customer="Submit failures.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Payload quality.",
    risk="Support noise.",
    fix_immediate="Never emit Pin=0; fail validation.",
    fix_short="Strict 6-digit PIN assert.",
    fix_long="Address master validation.",
    effort="0.25d",
    tests="Missing PIN → prepare errors not Pin 0.",
    acceptance="No zero PIN in payloads.",
    status="Open",
    refs="BB-000272 residual; Wave13 NEW",
)
add(
    title="Claimed ERP modules Manufacturing/Payroll/CRM/multi-company absent (honesty residual)",
    category="Product",
    subcategory="Scope",
    severity="High",
    priority="P0",
    module="Product",
    feature="Module claims",
    files="README.md; docs/reviews/KNOWN_LIMITATIONS; no backend apps",
    problem="Audit brief / commercial narratives may list Manufacturing, Payroll, CRM, Multi Company, Multi Branch, Mobile App, WhatsApp Business, live GST Portal as implemented. Repo: absent apps; README excludes many; warehouses≠branches; wa.me only; responsive web only; live GSP stub.",
    evidence="No manufacturing/payroll/crm apps; uniq_active_membership_per_user; LiveIrpAdapter stub",
    root_cause="Product aspiration vs shipped scope; audit input list over-claims vs README.",
    business="Selling unbuilt modules is fraud risk; GA blocked.",
    technical="Scope honesty.",
    customer="Expectation breach.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Commercial representation.",
    risk="If marketing uses audit brief list → Critical commercial failure.",
    fix_immediate="All external claims match README exclusions; scrub decks.",
    fix_short="Public capability matrix generated from flags.",
    fix_long="Build modules or never claim.",
    effort="0.5d honesty / multi-quarter build",
    tests="Doc lint against forbidden claim phrases.",
    acceptance="No commercial surface claims unbuilt modules.",
    status="Open",
    refs="BB-000035 Deferred related; Wave13 NEW honesty",
)


def fmt_issue(n: int, d: dict) -> str:
    iid = f"BB-{n:06d}"
    return f"""
## {iid} — {d['title']}

| Field | Value |
|-------|-------|
| **Issue ID** | {iid} |
| **Title** | {d['title']} |
| **Category** | {d['category']} |
| **Subcategory** | {d['subcategory']} |
| **Severity** | {d['severity']} |
| **Priority** | {d['priority']} |
| **Module** | {d['module']} |
| **Feature** | {d['feature']} |
| **Affected Files** | {d['files']} |
| **Affected Classes** | See files |
| **Affected Functions** | See files |
| **Affected APIs** | See files / related endpoints |
| **Affected Database Tables** | See models in files |
| **Status** | {d['status']} |
| **Owner** | Unassigned |
| **Review Date** | {TODAY} |
| **Estimated Effort** | {d['effort']} |
| **Breaking Change** | Possibly — assess per fix |
| **Regression Risk** | Medium unless tests added |
| **Dependencies** | See Cross References |
| **Cross References** | {d['refs']} |
| **References** | Wave 13 re-audit {TODAY}; code evidence |

### Problem Description
{d['problem']}

### Evidence
{d['evidence']}

### Code Snippet
See affected files at `{TODAY}` tree.

### Root Cause
{d['root_cause']}

### Business Impact
{d['business']}

### Technical Impact
{d['technical']}

### Customer Impact
{d['customer']}

### Security Impact
{d['security']}

### Performance Impact
{d['performance']}

### Scalability Impact
{d['scalability']}

### Compliance Impact
{d['compliance']}

### Risk if Ignored
{d['risk']}

### Steps to Reproduce
1. Follow Evidence paths in current tree.
2. Exercise affected API/UI as described in Problem.
3. Observe incorrect behavior vs Acceptance Criteria.

### Recommended Fix
**Immediate:** {d['fix_immediate']}
**Short-term:** {d['fix_short']}
**Long-term:** {d['fix_long']}

### Alternative Solutions
Defer only with signed risk waiver listing this Issue ID.

### Required Tests
{d['tests']}

### Acceptance Criteria
{d['acceptance']}

"""


def patch_register_totals(text: str, stats: dict) -> str:
    sev = stats["severity"]
    pri = stats["priority"]
    total = stats["total"]
    new_totals = f"""## Totals (this register)

| Metric | Count |
|--------|------:|
| **Total issues** | {total} |
| Critical | {sev.get('Critical', 0)} |
| High | {sev.get('High', 0)} |
| Medium | {sev.get('Medium', 0)} |
| Low | {sev.get('Low', 0)} |

### By Priority

| Priority | Count |
|----------|------:|
| P0 | {pri.get('P0', 0)} |
| P1 | {pri.get('P1', 0)} |
| P2 | {pri.get('P2', 0)} |
| P3 | {pri.get('P3', 0)} |
"""
    cat_rows = "".join(
        f"| {c} | {n} |\n" for c, n in sorted(stats["category"].items(), key=lambda x: -x[1])
    )
    mod_rows = "".join(
        f"| {m} | {n} |\n" for m, n in sorted(stats["module"].items(), key=lambda x: -x[1])
    )
    status_rows = "".join(
        f"| {s} | {n} |\n" for s, n in sorted(stats["status"].items(), key=lambda x: -x[1])
    )
    new_block = (
        new_totals
        + "\n### By Category\n\n| Category | Count |\n|----------|------:|\n"
        + cat_rows
        + "\n### By Module\n\n| Module | Count |\n|--------|------:|\n"
        + mod_rows
        + "\n### By Status\n\n| Status | Count |\n|--------|------:|\n"
        + status_rows
    )
    pattern = r"## Totals \(this register\)[\s\S]*?(?=\n## BB-000001)"
    text2, n = re.subn(pattern, new_block + "\n", text, count=1)
    if n != 1:
        raise SystemExit(f"Failed to patch totals header (replacements={n})")
    return text2


def rebuild_stats(existing_issues: list, new_issues: list, start_id: int) -> dict:
    all_issues = list(existing_issues)
    for i, d in enumerate(new_issues):
        all_issues.append(
            {
                "id": f"BB-{start_id + i:06d}",
                "title": d["title"],
                "severity": d["severity"],
                "priority": d["priority"],
                "category": d["category"],
                "module": d["module"],
                "effort": d["effort"],
                "status": d["status"],
            }
        )

    sev, pri, cat, mod, status = {}, {}, {}, {}, {}
    for item in all_issues:
        sev[item["severity"]] = sev.get(item["severity"], 0) + 1
        pri[item["priority"]] = pri.get(item["priority"], 0) + 1
        cat[item["category"]] = cat.get(item["category"], 0) + 1
        mod[item["module"]] = mod.get(item["module"], 0) + 1
        status[item["status"]] = status.get(item["status"], 0) + 1

    prior = {}
    if STATS.exists():
        prior = json.loads(STATS.read_text(encoding="utf-8"))

    result = {
        "total": len(all_issues),
        "severity": sev,
        "priority": pri,
        "category": cat,
        "module": mod,
        "status": status,
        "wave13_new": len(new_issues),
        "wave13_start": f"BB-{start_id:06d}",
        "wave13_end": f"BB-{start_id + len(new_issues) - 1:06d}",
        "audit_date": TODAY,
        "open_count": status.get("Open", 0),
        "issues": all_issues,
    }
    for k in (
        "wave9_new",
        "wave9_start",
        "wave9_end",
        "wave9_reopened",
        "wave10_closure",
        "wave11_closure",
        "wave12_new",
        "wave12_start",
        "wave12_end",
        "wave12_closure",
    ):
        if k in prior:
            result[k] = prior[k]
    return result


def update_changelog(stats: dict) -> None:
    block = f"""# docs/reviews — CHANGELOG

## {TODAY} — Wave 13 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Wave 12 claimed Open==0.

### Outcomes

- Appended **{stats['wave13_new']}** issues `{stats['wave13_start']}` … `{stats['wave13_end']}` (
  Critical {sum(1 for d in ISSUES if d['severity']=='Critical')} ·
  High {sum(1 for d in ISSUES if d['severity']=='High')} ·
  Medium {sum(1 for d in ISSUES if d['severity']=='Medium')} ·
  Low {sum(1 for d in ISSUES if d['severity']=='Low')}).
- Register total: **{stats['total']}**.
- Status: Open **{stats['status'].get('Open', 0)}** · prior Resolved/Deferred retained.
- Invalidated Wave 12 “Open == 0” as a launch gate (see BB-000386).
- Production Readiness Score revised **6.5 → 3.2**.

### Highest new Criticals

- BB-000379 Sandbox payment-link create/settle still allowed in production
- BB-000380 Sales return never reverses COGS/Inventory GL
- BB-000381 Opening invoices dual-ledger permanent mismatch
- BB-000382 Unallocated receipts break AR control
- BB-000383 Purchase return batch-tracked hard-fail
- BB-000384 Production live e-Invoice/e-Way dead end
- BB-000385 Prod Celery beat healthcheck `or True`
- BB-000386 Wave 12 Open==0 meta invalidation

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 13).

Script: `_wave13_reaudit_append.py` (append-only; IDs permanent).

---

"""
    if not CHANGELOG.exists():
        CHANGELOG.write_text(block, encoding="utf-8")
        return
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"Wave 13 independent re-audit" in text and TODAY in text[:800]:
        return
    # Prepend after title line
    if text.startswith("# docs/reviews"):
        parts = text.split("\n", 2)
        if len(parts) >= 2:
            rest = parts[2] if len(parts) > 2 else ""
            CHANGELOG.write_text(parts[0] + "\n\n" + block.split("\n", 2)[2] + rest, encoding="utf-8")
            return
    CHANGELOG.write_text(block + text, encoding="utf-8")


def append_exec_summary(stats: dict) -> None:
    if not EXEC.exists():
        return
    text = EXEC.read_text(encoding="utf-8")
    text = re.sub(
        r"\*\*Latest:\*\*[^\n]*",
        f"**Latest:** Wave 13 independent re-audit {TODAY} — register **{stats['total']}** issues. "
        f"**Open: {stats['status'].get('Open', 0)}.** "
        f"Resolved {stats['status'].get('Resolved', 0)}. "
        f"Deferred — roadmap {stats['status'].get('Deferred — roadmap', 0)}. "
        f"Production Readiness Score **3.2 / 10**.",
        text,
        count=1,
    )
    if f"## Wave 13 re-audit ({TODAY})" in text:
        EXEC.write_text(text, encoding="utf-8")
        return
    block = f"""

---

## Wave 13 re-audit ({TODAY}) — SUPERSEDES Wave 12 “Open == 0”

Independent code re-verification **invalidated Wave 12 open-closure**. W12A–E fixed many named IDs, but **sandbox create/settle bypass, sales-return COGS gap, openings/advances dual-ledger, purchase batch returns, live GSP dead-end, beat `or True`, prepare_* RBAC, FE POS known-gate, and access-in-body** remain. **{stats['wave13_new']} new issues** logged as `{stats['wave13_start']}` … `{stats['wave13_end']}`.

### Updated verdict

| Audience | Deploy? |
|----------|---------|
| Internal dogfood (sandbox payments off, accounting off, Owner-only API) | **Conditional** |
| Paid pilot with multi-role staff / payments / books / e-invoice | **No — until Wave 13 P0 Criticals closed** |
| GA / full ERP claims | **No** |

### Scores (0–10) — Wave 13

| Dimension | Score | Notes |
|-----------|------:|-------|
| Production Readiness | **3.2** | Sandbox create bypass + beat health lie + books return COGS |
| Architecture | **4.5** | Perpetual incomplete on returns; dual ledger openings/advances |
| Security | **3.0** | Sandbox settle residual; prepare RBAC; access JWT in body; warehouse ACL |
| Performance | **4.0** | fetchAllPages residual |
| Accounting Correctness | **2.5** | Return COGS missing; openings/advances control mismatch |
| GST Compliance | **3.0** | Live GSP dead; CDNR openings; FE POS known-gate; no 2B |
| Maintainability | **5.0** | God modules still Deferred |
| Scalability | **4.0** | Client fetch-all; no load proof |
| Testing Coverage | **4.5** | Mock e2e; residual suites missing |

### Register totals (cumulative)

| Metric | Count |
|--------|------:|
| **Total issues** | **{stats['total']}** |
| Critical | {stats['severity'].get('Critical', 0)} |
| High | {stats['severity'].get('High', 0)} |
| Medium | {stats['severity'].get('Medium', 0)} |
| Low | {stats['severity'].get('Low', 0)} |
| **Open** | **{stats['status'].get('Open', 0)}** |

### Wave 13 P0 blockers

1. **BB-000379** — Sandbox payment-link create/settle in production
2. **BB-000380** — Sales return never reverses COGS
3. **BB-000381 / 382** — Openings + advances dual-ledger mismatch
4. **BB-000383** — Purchase return batch hard-fail
5. **BB-000384** — Live e-Invoice/e-Way production dead end
6. **BB-000385** — Beat healthcheck `or True`
7. **BB-000386** — Open==0 process invalidation
8. **BB-000387–389 / 391 / 403–407** — prepare RBAC, warehouses, register cookies, FE POS, JWT body, AI tax, docs, settings

### Final CTO Verdict (Wave 13)

**Do not treat Wave 12 Open==0 as a quality gate.** Require adversarial residual tests covering create paths, GL lifecycle (returns), and compose health AST.

**Do not enable public payment webhooks or sandbox provider** until BB-000379 closed and adversarially tested.

**Do not enable accounting_enabled** until return COGS + openings/advances control (BB-000380–382) close.

**Do not claim live GST Portal / IRN in production** until BB-000384 ships or flags fail closed.

**Do not commercially launch** as Cloud ERP with Manufacturing/Payroll/CRM/WhatsApp Business/native mobile/multi-branch claims (BB-000447).

"""
    EXEC.write_text(text.rstrip() + block + "\n", encoding="utf-8")


def update_roadmap(stats: dict) -> None:
    if not ROADMAP.exists():
        return
    text = ROADMAP.read_text(encoding="utf-8")
    if "Wave 13 hotfix" in text:
        return
    block = f"""

---

## Wave 13 hotfix track ({TODAY}) — P0 before any paid multi-role pilot

> Wave 12 Open==0 is **not** a launch gate. Open count now **{stats['status'].get('Open', 0)}** (`{stats['wave13_start']}`–`{stats['wave13_end']}`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Sandbox create/settle | BB-000379, BB-000392–394, BB-000408 | No sandbox in prod/staging create or webhook |
| Books perpetual lifecycle | BB-000380–382, BB-000395, BB-000401, BB-000426 | Return COGS; openings/advances coherent |
| Inventory returns/lots | BB-000383, BB-000395, BB-000402–404, BB-000431 | Batch purchase returns; cancel lots; serials |
| GSP / GST honesty | BB-000384, BB-000398–400, BB-000405, BB-000447 | Fail-closed live GSP; CDNR/POS/gates |
| Auth/RBAC residuals | BB-000387–389, BB-000403–404, BB-000413–418 | prepare/warehouse/register/JWT/FE ACL |
| DevOps truth | BB-000385–386, BB-000407, BB-000434–437 | Beat health; readiness docs; TLS/CD |
| Process | BB-000386 | Stop checklist-only closure |

**Exit:** Conditional billing dogfood with Owner-only staff, sandbox banned on all paths, accounting off, e-invoice flags fail-closed in prod.

"""
    if "## Scope C completed" in text:
        text = text.replace("## Scope C completed", block + "\n## Scope C completed", 1)
    else:
        text = text.rstrip() + block
    ROADMAP.write_text(text, encoding="utf-8")


def update_review_docs(stats: dict) -> None:
    banner = (
        f"\n\n---\n\n## Wave 13 re-audit ({TODAY})\n\n"
        f"Independent re-verification appended `{stats['wave13_start']}`…`{stats['wave13_end']}` "
        f"({stats['wave13_new']} issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. "
        f"Open count: **{stats['status'].get('Open', 0)}**. "
        f"Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.\n"
    )
    for name in [
        "02_ARCHITECTURE_REVIEW.md",
        "03_BACKEND_REVIEW.md",
        "04_FRONTEND_REVIEW.md",
        "05_DATABASE_REVIEW.md",
        "06_SECURITY_REVIEW.md",
        "07_PERFORMANCE_REVIEW.md",
        "08_GST_REVIEW.md",
        "09_ACCOUNTING_REVIEW.md",
        "10_BUSINESS_LOGIC_REVIEW.md",
        "11_API_REVIEW.md",
        "12_DEVOPS_REVIEW.md",
        "13_TESTING_REVIEW.md",
        "14_UI_UX_REVIEW.md",
        "15_AI_REVIEW.md",
        "16_MOBILE_REVIEW.md",
        "17_INTEGRATION_REVIEW.md",
        "18_COMPETITOR_ANALYSIS.md",
        "19_TECHNICAL_DEBT.md",
        "20_REFACTORING_PLAN.md",
        "21_PRODUCTION_READINESS.md",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md",
        "ARCHITECTURAL_DECISIONS.md",
    ]:
        path = OUT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if f"Wave 13 re-audit ({TODAY})" in text:
            continue
        path.write_text(text.rstrip() + banner, encoding="utf-8")


def main():
    if not REGISTER.exists():
        raise SystemExit(f"Missing {REGISTER}")
    text = REGISTER.read_text(encoding="utf-8")
    if f"## BB-{START_ID:06d}" in text:
        raise SystemExit(f"BB-{START_ID:06d} already present — refuse double-append")

    if not ISSUES:
        raise SystemExit("No issues defined")

    existing = []
    if STATS.exists():
        existing = json.loads(STATS.read_text(encoding="utf-8")).get("issues", [])
    if len(existing) < 378:
        raise SystemExit(f"Expected ≥378 issues in _stats.json, got {len(existing)}")

    banner = (
        f"\n## Wave 13 re-audit ({TODAY})\n\n"
        f"Appended **{len(ISSUES)}** new issues "
        f"`BB-{START_ID:06d}` … `BB-{START_ID + len(ISSUES) - 1:06d}` "
        f"from independent code re-verification after Wave 12 open-closure. "
        f"Prior IDs unchanged. "
        f"**Invalidates Wave 12 Open==0 as a launch gate.**\n"
    )
    if f"Wave 13 re-audit ({TODAY})" not in text:
        text = text.replace("## How to use\n", "## How to use\n" + banner + "\n", 1)

    body = "".join(fmt_issue(START_ID + i, d) for i, d in enumerate(ISSUES))
    if not text.endswith("\n"):
        text += "\n"
    text = text + "\n# Wave 13 appended issues\n" + body
    stats = rebuild_stats(existing, ISSUES, START_ID)
    text = patch_register_totals(text, stats)
    text = re.sub(
        r"\*\*Audit date:\*\*[^\n]*",
        f"**Audit date:** 2026-08-02 (Wave 13 re-audit {TODAY})",
        text,
        count=1,
    )
    REGISTER.write_text(text, encoding="utf-8")
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    update_changelog(stats)
    append_exec_summary(stats)
    update_roadmap(stats)
    update_review_docs(stats)
    print(f"Appended {len(ISSUES)} issues BB-{START_ID:06d}..BB-{START_ID+len(ISSUES)-1:06d}")
    print(
        "New by severity:",
        {k: sum(1 for d in ISSUES if d["severity"] == k) for k in ("Critical", "High", "Medium", "Low")},
    )
    print("Totals now:", stats["total"], stats["severity"])
    print("Status:", stats.get("status"))
    print("Open:", stats.get("open_count"))


if __name__ == "__main__":
    main()

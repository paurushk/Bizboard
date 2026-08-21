#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 12 independent re-audit (2026-08-03): append BB-000318+ after Wave 11 Open==0.

Never regenerates prior IDs. Append-only. IDs permanent.
Invalidates Waves 10–11 “Open == 0” as a commercial launch gate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-03"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
START_ID = 318

ISSUES: list[dict] = []


def add(**kwargs):
    ISSUES.append(kwargs)


# ─── CRITICAL ───────────────────────────────────────────────────────────────
add(
    title="Sandbox payment provider allowed in production (test_mode blocked asymmetrically)",
    category="Security",
    subcategory="Payments",
    severity="Critical",
    priority="P0",
    module="Payments",
    feature="Gateway settings",
    files="backend/payments/views.py; backend/payments/services.py; backend/config/settings.py",
    problem="GatewaySettingsView blocks test_mode in production but still accepts provider=sandbox. enabled_providers includes sandbox. Webhooks with shared SANDBOX_WEBHOOK_SECRET finalize real receipts/GL.",
    evidence="views.py ~814-820 sets payment_gateway_provider without sandbox ban; enabled_providers=['razorpay','sandbox']; test_mode blocked separately ~824",
    root_cause="Wave 10 hardened test_mode and HMAC but left explicit sandbox provider as first-class prod option.",
    business="Fake captures become paid invoices and bank/GL receipts in production.",
    technical="Settlement path trusts sandbox adapter with env-wide HMAC.",
    customer="Invoices marked paid without money; GST/books distorted.",
    security="Critical payment forgery / integrity failure.",
    performance="N/A",
    scalability="Any tenant can enable sandbox.",
    compliance="Financial controls failure.",
    risk="Silent AR fraud in any prod deploy that selects sandbox.",
    fix_immediate="Reject provider=sandbox when DJANGO_ENV in (production,staging); boot-fail if sandbox company exists in prod.",
    fix_short="Sandbox only when DJANGO_ENV=test/development; per-company secrets.",
    fix_long="Isolated sandbox tenants; no settlement into live books.",
    effort="0.5-1d",
    tests="Prod env PATCH provider=sandbox → 400; sandbox webhook cannot settle in prod.",
    acceptance="Production cannot select or settle via sandbox provider.",
    status="Open",
    refs="BB-000196/258/265 residual; Wave12 NEW",
)
add(
    title="Credit/debit notes, returns, orders, challans mutate under HasCompany only (VIEWER can post GL/stock)",
    category="Security",
    subcategory="RBAC",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Phase1 documents",
    files="backend/sales/phase1_views.py; backend/sales/views.py SalesReturnViewSet; backend/purchases/phase1_views.py; backend/purchases/views.py",
    problem="CN/DN/SO/Challan get_permissions only elevates cancel. complete posts journals. SalesReturnViewSet has no capability gate. Purchase notes/returns same pattern. FE RoleRoute not mirrored on API.",
    evidence="phase1_views.py L32-35 return super() for non-cancel; complete calls PostingService.post_note",
    root_cause="BB-000018 gated invoice create/complete only; Phase1 surfaces never got CanCreateSales/Purchases.",
    business="Any company member including VIEWER can invent returns/notes and move AR/AP/stock/GL via API.",
    technical="API authoritative RBAC hole; FE false safety.",
    customer="Unauthorized books and inventory changes.",
    security="Critical privilege escalation within tenant.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD failure for books/GST docs.",
    risk="Internal fraud / accidental mass corruption.",
    fix_immediate="Gate create/update/complete on CanCreateSales/CanCreatePurchases; cancel stays CanCancelDocuments.",
    fix_short="Deny VIEWER list/retrieve of money docs; align FE canView* helpers.",
    fix_long="Capability matrix per document type with tests.",
    effort="2-3d",
    tests="VIEWER POST complete CN/return → 403; staff without can_create_sales same.",
    acceptance="No note/return/order/challan mutate without create caps.",
    status="Open",
    refs="BB-000018 incomplete; BB-000210 FE-only; Wave12 NEW",
)
add(
    title="FE tax preview lacks state-name→code map (BE has it) — IGST vs CGST/SGST mismatch",
    category="GST",
    subcategory="Tax math",
    severity="Critical",
    priority="P0",
    module="Web",
    feature="Invoice tax preview",
    files="web/src/utils/tax.ts; backend/core/services/billing.py; backend/core/services/place_of_supply.py",
    problem="BE extract_state_code maps Karnataka→29; FE extractStateCode only accepts digit prefixes then string-compares raw values. Same-state B2C with state name + company GSTIN often shows IGST on UI while BE posts CGST/SGST.",
    evidence="tax.ts L264-285 returns null for non-digit; falls through to string compare; billing.py maps IN_STATE_NAME_TO_CODE",
    root_cause="Incomplete FE port of BB-000063 POS normalize.",
    business="User/PDF preview ≠ filed tax; wrong liability presentation at bill time.",
    technical="Dual tax engines diverge on common Indian state names.",
    customer="Trust loss; disputes; wrong cash collected if staff trusts UI.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Preview vs books GST split conflict.",
    risk="Pilot CAs reject product on first demo with named states.",
    fix_immediate="Port IN_STATE_NAME_TO_CODE into FE extractStateCode/isIntraState.",
    fix_short="Shared golden fixture FE↔BE for state names.",
    fix_long="Single tax preview API as source of truth.",
    effort="0.5-1d",
    tests="Karnataka vs 29GSTIN → FE intra matches BE.",
    acceptance="FE preview tax split equals BE complete for name and code POS.",
    status="Open",
    refs="BB-000063 residual; BB-000032/278; Wave12 NEW",
)
add(
    title="FEFO multi-batch sale cancel restores full qty to first batch only",
    category="Inventory",
    subcategory="Batch/FEFO",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Invoice cancel",
    files="backend/sales/services.py",
    problem="Complete posts SALE movements per FEFO lot; only allocations[0] saved on line. Cancel restores full qty to item.batch only — other lots stay depleted.",
    evidence="services.py _sale_batches + cancel path ~533-547 restores to single batch",
    root_cause="Allocation persisted incompletely; cancel not movement-replay based.",
    business="Batch balances corrupt; expiry/FEFO wrong; traceability broken.",
    technical="StockMovement history vs StockBalance diverge on cancel.",
    customer="Wrong available stock; failed picks; audit failure.",
    security="N/A",
    performance="N/A",
    scalability="Worse with many lots.",
    compliance="Batch recall / pharma-style traceability failure.",
    risk="Silent inventory fraud appearance after cancel.",
    fix_immediate="Persist per-lot allocations; reverse exact movements on cancel.",
    fix_short="Child allocation table; cancel = reverse StockMovement set.",
    fix_long="Event-sourced stock ledger.",
    effort="2-3d",
    tests="Two-lot FEFO sale cancel restores each lot qty.",
    acceptance="Cancel restores exact FEFO lot quantities.",
    status="Open",
    refs="Wave12 NEW; inventory FEFO",
)
add(
    title="Purchase posts Dr 5100 expense while sales COGS credits Inventory 1400 — hybrid double-count",
    category="Accounting",
    subcategory="Inventory GL",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="PostingService",
    files="backend/accounting/services.py",
    problem="post_purchase debits Purchases 5100; post_sales_cogs debits COGS 5400 / credits Inventory 1400. Inventory never debited on purchase. Hybrid perpetual/periodic overstates cost and drifts Inventory GL.",
    evidence="post_purchase lines Dr 5100; post_sales_cogs Cr 1400",
    root_cause="BB-000042 partial — inventory account seeded but purchase still expense model.",
    business="P&L overstates cost; BS inventory diverges from stock valuation.",
    technical="Trial balance may balance while economic inventory wrong.",
    customer="CA rejects books; wrong margins.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Books not fit for statutory MIS.",
    risk="accounting_enabled pilots publish false P&L.",
    fix_immediate="Pick one model: perpetual Dr 1400 on purchase and keep COGS; or periodic drop COGS/1400 sale posts.",
    fix_short="Company flag inventory_accounting_mode with migration.",
    fix_long="Full perpetual with valuation method.",
    effort="3-5d",
    tests="Purchase+sale: Inventory GL equals stock valuation under chosen mode.",
    acceptance="No simultaneous 5100 expense and 1400 credit without matching Dr 1400.",
    status="Open",
    refs="BB-000042 residual; Wave12 NEW",
)
add(
    title="supplier_outstanding double-counts purchase return + auto CN (invoice-level fix incomplete)",
    category="Accounting",
    subcategory="AP ledger",
    severity="Critical",
    priority="P0",
    module="Ledgers",
    feature="Supplier outstanding",
    files="backend/ledgers/services.py",
    problem="BB-000281 fixed purchase_invoice_outstanding to exclude returns linked to auto CNs. supplier_outstanding / bulk_supplier_outstanding / statements still subtract both returns and CNs.",
    evidence="L100-117 auto_cn_return_ids on invoice path; L281-315 still invoices-returns-credit_notes",
    root_cause="Fix applied only to per-invoice helper.",
    business="Understated payables; overpayment risk; control health false mismatches.",
    technical="AP control account vs supplier subledger diverge.",
    customer="Wrong supplier balances on statements.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Books/AP unreliable.",
    risk="Cash leakage via overpay.",
    fix_immediate="Mirror invoice auto-CN exclusion in supplier_outstanding, bulk, and statement builders.",
    fix_short="Single AP computation service.",
    fix_long="Derived outstanding from allocations + notes only.",
    effort="1d",
    tests="Complete return+auto CN → supplier outstanding decreases once.",
    acceptance="Supplier AP never double-relieves return+CN.",
    status="Open",
    refs="BB-000281 incomplete; BB-000043; Wave12 NEW",
)
add(
    title="E-invoice marks unregistered buyers as SupTyp B2B",
    category="GST",
    subcategory="E-Invoice",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="einvoice_payload",
    files="backend/sales/einvoice_payload.py",
    problem="Empty buyer GSTIN still sets SupTyp B2B. Sandbox may accept; live IRP will reject or misclassify.",
    evidence="einvoice_payload.py ~166-183 SupTyp hard B2B without GSTIN guard",
    root_cause="BB-000287 partially addressed RegRev/SupTyp; B2C path still absent.",
    business="Invalid IRN payloads; false sandbox success.",
    technical="Payload schema violates IRP B2B requirement.",
    customer="Cannot generate valid IRN for B2C / unregistered.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="E-invoice compliance failure.",
    risk="Pilot believes e-invoice works until live GSP.",
    fix_immediate="Require buyer GSTIN for B2B; refuse generate otherwise with clear error.",
    fix_short="Explicit B2C/B2CL supply types when in scope.",
    fix_long="Full SupTyp matrix incl SEZ/export.",
    effort="0.5d",
    tests="Empty GSTIN → generate blocked; B2B with GSTIN ok.",
    acceptance="No B2B payload without valid buyer GSTIN.",
    status="Open",
    refs="BB-000287 residual; Wave12 NEW",
)
add(
    title="Wave 10–11 Open==0 invalidated — residual Criticals remain after re-audit (meta)",
    category="Process",
    subcategory="Audit governance",
    severity="Critical",
    priority="P0",
    module="Product",
    feature="Register closure",
    files="docs/reviews/01_EXECUTIVE_SUMMARY.md; docs/reviews/CHANGELOG.md; docs/reviews/MASTER_ISSUE_REGISTER.md",
    problem="Waves 10–11 asserted Open==0 and PR score ~6.7 while adversarial Wave 12 found sandbox-in-prod, API RBAC holes, FE/BE tax split, FEFO cancel, hybrid GL, AP double-count, e-invoice B2B.",
    evidence="CHANGELOG Wave 11 Open:0; Wave12 verified residuals in payments/views, phase1_views, tax.ts, ledgers/services, accounting/services",
    root_cause="Checklist closure without independent residual pass (same failure as BB-000254/317).",
    business="Launch decisions based on false quality gate.",
    technical="Register status ≠ code risk.",
    customer="Overconfidence in pilot readiness.",
    security="Process failure hides Criticals.",
    performance="N/A",
    scalability="N/A",
    compliance="Governance failure.",
    risk="Repeat false GA.",
    fix_immediate="Append Wave12 Open issues; stop treating Open==0 as launch gate.",
    fix_short="Require adversarial re-audit after every open-closure wave.",
    fix_long="Issue Resolve requires failing-then-passing tests + second reviewer.",
    effort="1d process",
    tests="Wave12 assert script: known Criticals must be Open until fixed.",
    acceptance="Open count reflects verified residuals.",
    status="Open",
    refs="BB-000254; BB-000317; Wave12 META",
)

# ─── HIGH ───────────────────────────────────────────────────────────────────
add(
    title="Sales/purchase invoice update/destroy/list ungated beyond HasCompany",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P0",
    module="Sales",
    feature="Invoice CRUD",
    files="backend/sales/views.py; backend/purchases/views.py",
    problem="Only create/complete require CanCreate*; update/partial_update/destroy/list/retrieve fall through to HasCompany. VIEWER and capped staff can list money docs and PATCH/delete drafts.",
    evidence="get_permissions create/complete branch only ~60-74 sales views",
    root_cause="Partial Wave4 capability wiring.",
    business="Revenue/party data leak; draft tampering.",
    technical="FE RoleRoute bypass via API.",
    customer="Confidential invoices visible to all members.",
    security="High confidentiality + integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="Access control failure.",
    risk="Competitor/staff data exfil.",
    fix_immediate="Gate update/destroy with create caps; list/retrieve with financial or create caps matching FE.",
    fix_short="Central document permission policy.",
    fix_long="ABAC per action.",
    effort="1-2d",
    tests="VIEWER list invoices → 403; staff can_create_sales=False cannot PATCH draft.",
    acceptance="Invoice mutate/list match FE canViewSalesSurfaces.",
    status="Open",
    refs="BB-000018; Wave12 NEW",
)
add(
    title="Invoice number-series PATCH open to any company member",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P0",
    module="Sales",
    feature="DocumentNumberService",
    files="backend/sales/views.py; backend/purchases/views.py",
    problem="number_series action not in create/complete permission branch → HasCompany; PATCH calls DocumentNumberService.configure.",
    evidence="views.py number_series ~110-125",
    root_cause="Action omitted from get_permissions matrix.",
    business="Prefix/sequence sabotage; compliance gaps; collisions.",
    technical="Uncontrolled document numbering.",
    customer="Broken invoice sequences.",
    security="Integrity of statutory numbering.",
    performance="N/A",
    scalability="N/A",
    compliance="GST invoice number rules.",
    risk="Filing/DOC series chaos.",
    fix_immediate="IsOwner (or Owner+create) for PATCH; GET may stay broader.",
    fix_short="Audit log number series changes.",
    fix_long="Locked series after first document.",
    effort="0.5d",
    tests="Non-owner PATCH number_series → 403.",
    acceptance="Only Owner configures series.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Quotation convert and masters CRUD open to VIEWER",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P0",
    module="Sales",
    feature="Quotation convert / masters",
    files="backend/sales/views.py; backend/masters/views.py; backend/core/viewsets.py",
    problem="Quotation only gates cancel; convert creates invoices under HasCompany. All masters use bare CompanyScopedViewSet.",
    evidence="convert action HasCompany; masters views CompanyScopedViewSet only",
    root_cause="Convert treated as read-side action; masters never got caps.",
    business="VIEWER invents invoices; mutates customers/products/pricing.",
    technical="Privilege escalation path.",
    customer="Unauthorized master data changes.",
    security="High integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="Master data SoD.",
    risk="Price list sabotage.",
    fix_immediate="CanCreateSales on convert; masters mutate Owner or explicit caps; VIEWER read-only.",
    fix_short="can_manage_masters flag.",
    fix_long="Fine-grained master RBAC.",
    effort="2d",
    tests="VIEWER convert quotation → 403; VIEWER POST product → 403.",
    acceptance="Convert and master writes require caps.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Accounting CoA/journals readable without CanViewFinancialReports",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P1",
    module="Accounting",
    feature="Account/Journal list",
    files="backend/accounting/views.py; web/src/App.tsx",
    problem="Account/Journal list permissions return HasCompany for non-mutate; FE allowAccounting requires canViewFinancialReports. BE/FE split-brain.",
    evidence="accounting/views.py ~48-51, 101-107",
    root_cause="Mutate gated (CanPostJournals) but reads left open.",
    business="Sales staff/VIEWER pull CoA and journal lines via API.",
    technical="Confidential books leakage.",
    customer="Financial privacy breach within tenant.",
    security="High confidentiality.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD.",
    risk="Insider P&L leak.",
    fix_immediate="Read → CanViewFinancialReports.",
    fix_short="Align all accounting endpoints.",
    fix_long="Report vs ledger capability split.",
    effort="0.5-1d",
    tests="Staff without financial reports → 403 on journals list.",
    acceptance="Books reads match FE gate.",
    status="Open",
    refs="BB-000200/267 residual; Wave12 NEW",
)
add(
    title="FixedAsset create lacks CanPostJournals",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P1",
    module="Accounting",
    feature="Fixed assets",
    files="backend/accounting/views.py",
    problem="get_permissions only elevates dispose; perform_create seeds CoA and creates assets under HasCompany.",
    evidence="views.py ~196-217",
    root_cause="Incomplete accounting RBAC matrix.",
    business="Any member creates fixed assets / triggers CoA seed.",
    technical="Side-effect CoA seed without books privilege.",
    customer="Unauthorized asset register changes.",
    security="Integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="Fixed asset register control.",
    risk="BS misstatement.",
    fix_immediate="Gate create/update/destroy with CanPostJournals.",
    fix_short="Dedicated can_manage_assets.",
    fix_long="Asset workflow approvals.",
    effort="0.5d",
    tests="Non-poster POST fixed asset → 403.",
    acceptance="Asset CRUD requires journals/asset cap.",
    status="Open",
    refs="BB-000267 residual; Wave12 NEW",
)
add(
    title="AI insights API grants via can_view_financial_reports (VIEWER default True)",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P1",
    module="Insights",
    feature="AI insights",
    files="backend/insights/views.py; backend/accounts/models.py; web/src/utils/permissions.ts",
    problem="Insights allow OWNER or can_view_ai_insights or can_view_financial_reports. VIEWER defaults can_view_financial_reports True; FE blocks VIEWER from AI.",
    evidence="insights/views.py ~39-50; models.py VIEWER defaults ~179-191",
    root_cause="OR of financial reports into AI permission; VIEWER default too broad.",
    business="VIEWER pulls summaries/forecasts via API despite UI forbid.",
    technical="BE/FE permission divergence.",
    customer="Sensitive cashflow insights leak to viewers.",
    security="Confidentiality.",
    performance="N/A",
    scalability="N/A",
    compliance="Data minimization.",
    risk="Insider intelligence leak.",
    fix_immediate="Require can_view_ai_insights (or Owner); drop financial OR; align VIEWER defaults.",
    fix_short="Separate AI capability default False.",
    fix_long="Per-insight RBAC.",
    effort="0.5d",
    tests="VIEWER GET insights → 403.",
    acceptance="AI API matches FE VIEWER deny.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="OTP login impossible in production — enablement conflated with OTP_DEBUG_ECHO",
    category="Security",
    subcategory="Auth",
    severity="High",
    priority="P1",
    module="Accounts",
    feature="OTP",
    files="backend/accounts/views.py; backend/config/settings.py",
    problem="Request OTP requires OTP_DEBUG_ECHO; production boot forbids OTP_DEBUG_ECHO. Real SMS provider cannot enable OTP safely.",
    evidence="views.py ~262-265; settings.py ~394-397 forbids echo in prod",
    root_cause="Debug echo flag reused as feature flag.",
    business="Mobile OTP auth dead in prod or pressure to enable echo.",
    technical="Misconfig footgun.",
    customer="Cannot use claimed OTP login.",
    security="Echo path temptation; or missing 2FA.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth channel gap.",
    risk="Operators enable DEBUG_ECHO in prod.",
    fix_immediate="Gate on OTP_ENABLED or SMS_PROVIDER not in (off,console); echo remains debug-only.",
    fix_short="Document SMS provider setup.",
    fix_long="Multi-channel OTP (SMS/email).",
    effort="0.5-1d",
    tests="Prod OTP_ENABLED=1 without echo works with mock SMS; echo still forbidden.",
    acceptance="OTP works without OTP_DEBUG_ECHO.",
    status="Open",
    refs="BB-000003/006 residual; Wave12 NEW",
)
add(
    title="filing_place_of_supply / e-Invoice Stcd can remain free-text state names",
    category="GST",
    subcategory="Place of supply",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Filing overlays",
    files="backend/sales/services.py; backend/sales/einvoice_payload.py; backend/reporting/gst_returns.py",
    problem="Complete can fall back to raw customer.state; GSTR _party_pos may emit Maharashtra not 27; e-Invoice Stcd may be free-text.",
    evidence="services.py filing_place_of_supply ~414-422; gst_returns _party_pos",
    root_cause="Normalization incomplete at persist time.",
    business="NIC/GSTR exports fail or mis-bucket by POS.",
    technical="Inconsistent POS encoding.",
    customer="Filing errors.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR/e-Invoice schema.",
    risk="Portal reject.",
    fix_immediate="Always persist 2-digit POS; reject unmapped text at complete.",
    fix_short="Backfill normalize command.",
    fix_long="POS enum constrained column.",
    effort="1d",
    tests="Complete with Karnataka → filing_place_of_supply=29.",
    acceptance="No free-text POS on completed GST docs.",
    status="Open",
    refs="BB-000063 residual; Wave12 NEW",
)
add(
    title="Filing-identity amend can desync POS vs tax components",
    category="GST",
    subcategory="H9 / filing",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Filing amend",
    files="backend/sales/einvoice_eway_actions.py",
    problem="Owner can change filing_place_of_supply/GSTIN without recomputing CGST/SGST/IGST.",
    evidence="einvoice_eway_actions.py ~273-322",
    root_cause="Filing overlay treated as metadata-only.",
    business="GSTR-1/e-Invoice POS contradicts tax split.",
    technical="Identity vs money amend split incomplete.",
    customer="Wrong returns.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GST filing integrity.",
    risk="Mismatch notices.",
    fix_immediate="Block POS changes that flip intra/inter or force H9 money amend.",
    fix_short="Validate tax vs POS consistency on amend.",
    fix_long="Single amend service with invariants.",
    effort="1-2d",
    tests="POS flip without tax recompute → rejected.",
    acceptance="POS and tax components always consistent.",
    status="Open",
    refs="BB-000011 residual; Wave12 NEW",
)
add(
    title="Opening-balance invoices included in GSTR-1/3B builders",
    category="GST",
    subcategory="GSTR",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="gst_returns",
    files="backend/reporting/gst_returns.py",
    problem="Builders do not exclude is_opening_balance=True Tally openings.",
    evidence="gst_returns.py invoice querysets ~153-202 lack is_opening_balance filter",
    root_cause="Opening flag added for credit-limit/GL skip but not GSTR filters.",
    business="Opening AR/AP inflate outward/inward returns.",
    technical="Migration openings pollute statutory aids.",
    customer="Wrong GSTR worksheets.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR accuracy.",
    risk="Over-reported turnover.",
    fix_immediate="Filter is_opening_balance=False in all GST document querysets.",
    fix_short="Shared GST document queryset helper.",
    fix_long="Separate opening ledger docs from GST docs.",
    effort="0.5d",
    tests="Opening invoice excluded from GSTR-1 B2B and 3B.",
    acceptance="Openings never appear in GSTR aids.",
    status="Open",
    refs="BB-000264 related; Wave12 NEW",
)
add(
    title="RCM purchase credit/debit notes — wrong GL + missing 3.1(d) netting",
    category="GST",
    subcategory="RCM",
    severity="High",
    priority="P1",
    module="Purchases",
    feature="RCM notes",
    files="backend/purchases/notes_services.py; backend/accounting/services.py; backend/reporting/gst_returns.py",
    problem="Notes use normal tax math. post_note hits Input GST/AP not RCM payable/ITC. GSTR-3B excludes RCM-linked PCN/PDN from inward/RCM sections.",
    evidence="notes_services tax path; post_note; gst_returns RCM exclusion",
    root_cause="RCM invoice path fixed (BB-000010) but notes never specialized.",
    business="RCM liability/ITC uncleared after returns; 3B RCM stale.",
    technical="GL + GSTR incomplete for RCM lifecycle.",
    customer="Wrong RCM books.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="RCM statutory.",
    risk="Interest/penalty exposure narrative.",
    fix_immediate="RCM-aware note totals + GL reverse 2240–2260/1310–1330; include notes in 3.1(d) netting.",
    fix_short="Tests for RCM CN complete/cancel.",
    fix_long="RCM document state machine.",
    effort="2-3d",
    tests="RCM purchase + CN clears RCM payable and adjusts 3B.",
    acceptance="RCM notes reverse RCM GL and appear in 3.1(d).",
    status="Open",
    refs="BB-000010 residual; Wave12 NEW",
)
add(
    title="Purchase complete soft-warns on closed GST period while sales hard-blocks",
    category="GST",
    subcategory="Period control",
    severity="High",
    priority="P1",
    module="Purchases",
    feature="Period close",
    files="backend/purchases/services.py; backend/sales/services.py",
    problem="Purchases soft-warn only; sales assert_period_allows_money_amend hard-blocks.",
    evidence="purchases/services.py ~253-260 warn; sales ~477-482 assert",
    root_cause="Asymmetric period gates.",
    business="Purchases/ITC enter closed GST months.",
    technical="Period integrity hole.",
    customer="Amended closed periods silently.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Period lock failure.",
    risk="Filing reopen chaos.",
    fix_immediate="Same hard assert on purchase (and notes) complete.",
    fix_short="Central period guard for all money docs.",
    fix_long="Period status machine.",
    effort="0.5d",
    tests="Soft-closed period purchase complete → blocked.",
    acceptance="Sales and purchase period gates identical.",
    status="Open",
    refs="BB-000271 residual; Wave12 NEW",
)
add(
    title="Credit/debit note complete ignores GST/accounting period soft-close",
    category="GST",
    subcategory="Period control",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Notes complete",
    files="backend/sales/notes_services.py; backend/purchases/notes_services.py",
    problem="No assert_period_allows_money_amend on note complete.",
    evidence="notes_services complete paths lack period assert",
    root_cause="Period guard only on invoice complete/H9.",
    business="CDNR/ITC changes after soft-close.",
    technical="Period bypass via notes.",
    customer="Closed-period mutations.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Period lock.",
    risk="GSTR period drift.",
    fix_immediate="Call period assert before note complete.",
    fix_short="Cancel/reverse also respect period.",
    fix_long="Unified DocumentCompleteService.",
    effort="0.5-1d",
    tests="Soft-closed period CN complete → blocked.",
    acceptance="Notes respect period locks.",
    status="Open",
    refs="BB-000271; Wave12 NEW",
)
add(
    title="Purchase CN/DN lacks outstanding / over-credit cap (sales CN has it)",
    category="Business Logic",
    subcategory="AP notes",
    severity="High",
    priority="P1",
    module="Purchases",
    feature="Purchase notes",
    files="backend/purchases/notes_services.py; backend/sales/notes_services.py",
    problem="Sales CN capped to invoice outstanding; purchase notes are not.",
    evidence="sales notes_services outstanding cap; purchases notes_services no cap",
    root_cause="Asymmetric note validation.",
    business="AP over-credited; floored to 0 hides over-relief.",
    technical="Ledger floor masks bug.",
    customer="Wrong supplier balances.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="AP integrity.",
    risk="Overpayment.",
    fix_immediate="Cap to LedgerService.purchase_invoice_outstanding.",
    fix_short="Cumulative note caps.",
    fix_long="Allocation-based note application.",
    effort="0.5d",
    tests="PCN > outstanding → rejected.",
    acceptance="Purchase notes cannot exceed invoice outstanding.",
    status="Open",
    refs="BB-000303 sales-side; Wave12 NEW",
)
add(
    title="Sales return serial_numbers never saved (_build_items dead branch)",
    category="Inventory",
    subcategory="Serials",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Sales returns",
    files="backend/sales/services.py",
    problem="serial_numbers only set inside model_cls in (SalesItem, CN, DN); SalesReturnItem elif unreachable for serial assignment.",
    evidence="services.py _build_items ~86-133",
    root_cause="Branch ordering bug.",
    business="Serial-tracked returns fail or skip serial transition.",
    technical="Dead code path.",
    customer="Cannot return serial products correctly.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Serial traceability.",
    risk="Ghost serial ownership.",
    fix_immediate="Handle SalesReturnItem (and challan) serials correctly.",
    fix_short="Unit tests for serial return.",
    fix_long="Shared line builder.",
    effort="0.5d",
    tests="Return with serials persists and restores serial status.",
    acceptance="SalesReturnItem.serial_numbers saved.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Sales return stock restore ignores original batch",
    category="Inventory",
    subcategory="Batch",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Sales returns",
    files="backend/sales/services.py",
    problem="SALES_RETURN movement posts with batch=None even when invoice issued from lots.",
    evidence="services.py return stock ~692-708 batch=None",
    root_cause="Return path not batch-aware.",
    business="Unbatched stock appears; batch on-hand stays depleted.",
    technical="Batch imbalance.",
    customer="Wrong batch availability.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Batch recall.",
    risk="Expiry mismanagement.",
    fix_immediate="Return to source batch(es).",
    fix_short="Multi-lot return allocations.",
    fix_long="Movement reverse API.",
    effort="1-2d",
    tests="Batched sale return restores same batch qty.",
    acceptance="Return movements carry source batches.",
    status="Open",
    refs="Wave12 FEFO related; Wave12 NEW",
)
add(
    title="Delivery challan convert always creates NON_GST invoice",
    category="GST",
    subcategory="Challan",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Challan convert",
    files="backend/sales/notes_services.py",
    problem="Convert hardcodes InvoiceType.NON_GST despite GST products/rates on challan.",
    evidence="notes_services.py ~491-494 NON_GST",
    root_cause="Conservative hardcode without user choice.",
    business="GST sales via challan never tax; stock-skip path still used.",
    technical="Wrong invoice type.",
    customer="Missing GST invoices.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GST billing gap.",
    risk="Under-reported outward supplies if used as primary flow.",
    fix_immediate="Carry appropriate invoice type or require explicit choice.",
    fix_short="UI type selector on convert.",
    fix_long="Challan as stock-only doc with mandatory tax invoice step.",
    effort="0.5-1d",
    tests="GST challan convert → GST invoice with tax.",
    acceptance="Convert does not force NON_GST for GST companies.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Challan stock issue and SO reservation ignore batch tracking",
    category="Inventory",
    subcategory="Batch/reservation",
    severity="High",
    priority="P1",
    module="Inventory",
    feature="Challan / SO",
    files="backend/sales/notes_services.py; backend/inventory/services.py",
    problem="Challan posts SALE without batch; reserve_stock forces batch=None while availability for batched products is per-batch.",
    evidence="notes_services challan ~452-468; inventory reserve_stock ~147-173",
    root_cause="Batch FEFO only wired on invoice complete.",
    business="Over-reserve unbatched / under-protect lots; challan+batch blocked or wrong.",
    technical="Reservation vs balance inconsistency.",
    customer="Oversell / blocked challans.",
    security="N/A",
    performance="N/A",
    scalability="Concurrent oversell risk.",
    compliance="Batch control.",
    risk="Negative available on real lots.",
    fix_immediate="FEFO/batch allocation for challan; reserve against batch policy.",
    fix_short="Unified allocation service for invoice/challan/SO.",
    fix_long="ATP engine.",
    effort="2d",
    tests="Batched product challan issues lot; SO reserve respects batches.",
    acceptance="No unbatched movements for track_batch products.",
    status="Open",
    refs="BB-000060 residual; Wave12 NEW",
)
add(
    title="Accounting UI flag defaults ON — README claims off by default",
    category="Configuration",
    subcategory="Feature flags",
    severity="High",
    priority="P1",
    module="Web",
    feature="features.ts",
    files="web/src/config/features.ts; web/Dockerfile; README.md; .github/workflows/cd.yml",
    problem="accounting: VITE_ENABLE_ACCOUNTING !== 'false' → on unless disabled. Docker build has no VITE_* ARGs so GHCR images ship accounting UI on. README says flagged off by default.",
    evidence="features.ts L19; Dockerfile no ARG; README honesty",
    root_cause="Opt-out flag + missing Docker build-args.",
    business="Pilot builds expose books UI contrary to honesty gates.",
    technical="Deployed SPA ≠ documented gating.",
    customer="Over-claimed books surface.",
    security="Expands attack surface of accounting APIs usage.",
    performance="N/A",
    scalability="N/A",
    compliance="Honesty / Go-No-Go.",
    risk="accounting_enabled companies use unfinished hybrid GL (#GL).",
    fix_immediate="Default accounting === 'true' only; Docker ARG/ENV; CD pass flags.",
    fix_short="Fail CI if prod image has accounting on without waiver.",
    fix_long="Server-driven feature flags.",
    effort="1d",
    tests="Default build features.accounting false; docker ARG respected.",
    acceptance="Accounting UI off by default in prod images.",
    status="Open",
    refs="BB-000132 residual; Wave12 NEW",
)
add(
    title="CI pins constraints.txt but Docker/CD installs requirements without constraints",
    category="DevOps",
    subcategory="Supply chain",
    severity="High",
    priority="P1",
    module="DevOps",
    feature="Dockerfile / CD",
    files="backend/Dockerfile; backend/constraints.txt; .github/workflows/ci.yml; .github/workflows/cd.yml",
    problem="CI uses constraints; image pip install -r requirements.txt only. constraints incomplete vs openai/reportlab/openpyxl.",
    evidence="Dockerfile L10-11; ci.yml -c constraints.txt",
    root_cause="Constraints added for CI only.",
    business="CI-green / prod-CVE drift.",
    technical="Unreproducible releases.",
    customer="Unexpected runtime behavior.",
    security="Supply-chain risk.",
    performance="N/A",
    scalability="N/A",
    compliance="Change control.",
    risk="Silent dependency shift on rebuild.",
    fix_immediate="Bake -c constraints.txt into Dockerfile; expand pins.",
    fix_short="Full lockfile (pip-tools/uv).",
    fix_long="Signed SBOMs.",
    effort="1-2d",
    tests="Image pip freeze matches CI constrained set for pinned pkgs.",
    acceptance="Docker and CI use same constraints.",
    status="Open",
    refs="BB-000125 residual; Wave12 NEW",
)
add(
    title="Tally preview commit trusts client-rewritten opening amounts",
    category="Integration",
    subcategory="Tally",
    severity="High",
    priority="P1",
    module="Integrations",
    feature="Tally migration",
    files="backend/integrations/views.py; backend/integrations/tally/adapter.py",
    problem="update_tally_preview accepts arbitrary preview JSON (opening AR/AP/qty); commit posts openings from that JSON.",
    evidence="integrations/views.py ~53-57; adapter commit openings",
    root_cause="Preview treated as editable source of truth.",
    business="Import user invents books openings without file evidence.",
    technical="Integrity of migration aid broken.",
    customer="Wrong opening balances.",
    security="Books fraud via import path.",
    performance="N/A",
    scalability="N/A",
    compliance="Opening balance integrity.",
    risk="Silent BS corruption at go-live.",
    fix_immediate="Server re-parse upload as truth; allow only name/SKU map edits.",
    fix_short="Sign preview server-side.",
    fix_long="Two-person review on openings.",
    effort="2d",
    tests="Tampered opening amount in preview → ignored/rejected on commit.",
    acceptance="Commit amounts match re-parsed file.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title=".env.example cannot boot as documented (DJANGO_ENV / Fernet / DEBUG mismatch)",
    category="Configuration",
    subcategory="Env examples",
    severity="High",
    priority="P1",
    module="Docs",
    feature="Onboarding",
    files=".env.example; backend/config/settings.py; README.md",
    problem="README says copy .env.example; example may omit DJANGO_ENV while ALLOWED_HOSTS includes trycloudflare requiring explicit env; DJANGO_DEBUG=false triggers dedicated secret requirements with empty GSP_FERNET_KEY; ADMIN_ENABLED=1.",
    evidence=".env.example vs settings ImproperlyConfigured gates",
    root_cause="Env example drift after Wave security hardening.",
    business="Broken onboarding; operators weaken DEBUG/hosts.",
    technical="Footgun config.",
    customer="Cannot start local stack.",
    security="Pressure to disable fail-closed gates.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Insecure local patterns leak to staging.",
    fix_immediate="Ship DJANGO_ENV=development + valid Fernet placeholders; ADMIN_ENABLED=0 when DEBUG false.",
    fix_short="Boot doctor script.",
    fix_long="Generated .env from wizard.",
    effort="0.5-1d",
    tests="cp .env.example .env && compose up boots.",
    acceptance="Documented first-run works without ImproperlyConfigured.",
    status="Open",
    refs="BB-000247/308 residual; Wave12 NEW",
)
add(
    title="fetchAllPages still powers returns/notes/quotations/journals pickers (throw at 50 pages)",
    category="Performance",
    subcategory="Frontend lists",
    severity="High",
    priority="P1",
    module="Web",
    feature="resources.ts",
    files="web/src/api/resources.ts; SalesReturnsPage; SalesInvoiceNoteEditor; QuotationsPage; PurchaseReturnsPage; SupplierPaymentsPage; accounting listJournals",
    problem="BB-000245 throw after 50 pages replaces silent truncate but editors still crawl or hard-fail. ReceiptsPage uses single page 50 silently.",
    evidence="resources.ts fetchAllPages; ReceiptsPage listSalesInvoicesPage pageSize 50",
    root_cause="Wave fixes on some pickers only.",
    business="Mid-size tenants broken CN/DN/returns/pickers.",
    technical="N-page storms; incomplete pickers.",
    customer="Cannot find invoices beyond page 1 on receipts.",
    security="N/A",
    performance="High latency / memory.",
    scalability="Fails at ~5k rows.",
    compliance="N/A",
    risk="Pilot at 1k invoices fails.",
    fix_immediate="Server search Autocomplete; fix Receipts silent truncate.",
    fix_short="Ban fetchAllPages for money docs in lint.",
    fix_long="Virtualized infinite query everywhere.",
    effort="3-5d",
    tests="Receipts can find invoice #51 via search.",
    acceptance="No fetchAllPages on editor pickers; no silent page-1 truncate.",
    status="Open",
    refs="BB-000033/245/246/298 residual; Wave12 NEW",
)

# ─── MEDIUM ─────────────────────────────────────────────────────────────────
add(
    title="Register still enumerates emails via access/user_id/company_id body shape",
    category="Security",
    subcategory="Auth",
    severity="Medium",
    priority="P1",
    module="Accounts",
    feature="Register",
    files="backend/accounts/views.py; backend/tests/test_auth.py",
    problem="Duplicate → access null; new → JWT + ids. Tests encode as fixed. Residual of BB-000251/290.",
    evidence="views.py register ~97-151",
    root_cause="Partial anti-enum (status code) without body isomorphism.",
    business="Email existence oracle.",
    technical="Auth privacy gap.",
    customer="Account harvesting.",
    security="Enumeration.",
    performance="N/A",
    scalability="N/A",
    compliance="Privacy.",
    risk="Targeted phishing list.",
    fix_immediate="Identical null token fields always; session only via cookie after verify.",
    fix_short="Constant-time responses.",
    fix_long="Invite-only registration.",
    effort="1d",
    tests="Duplicate vs new response JSON keys/types identical.",
    acceptance="No distinguishing register body fields.",
    status="Open",
    refs="BB-000251/290 residual; Wave12 NEW",
)
add(
    title="FE create-capability helpers treat undefined as allow (!== false)",
    category="Security",
    subcategory="Frontend RBAC",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="permissions.ts",
    files="web/src/utils/permissions.ts",
    problem="canCreateSales/purchases/payments use !== false while BE defaults False and canViewFinancialReports uses === true.",
    evidence="permissions.ts L65-78",
    root_cause="Permissive FE default opposite of least privilege.",
    business="Stale/partial user objects show create UI.",
    technical="Defense-in-depth failure.",
    customer="Confusing 403s after UI allows.",
    security="UI over-grant.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD UX.",
    risk="Staff click paths that should be hidden.",
    fix_immediate="Require === true.",
    fix_short="Type canCreate* as required boolean from /me.",
    fix_long="Generated permission helpers from OpenAPI.",
    effort="0.5d",
    tests="undefined canCreateSales → UI deny.",
    acceptance="FE create helpers least-privilege.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Webhook over-capture silently clamps amount and marks link PAID",
    category="Security",
    subcategory="Payments",
    severity="Medium",
    priority="P1",
    module="Payments",
    feature="finalize_gateway_payment",
    files="backend/payments/services.py",
    problem="If capture_amount > link.amount and not allow_partial, clamp to link.amount; GatewayPayment may store webhook amount; link marked PAID.",
    evidence="services.py ~429-435",
    root_cause="Convenience clamp vs reject policy.",
    business="Customer overpays; books under-record.",
    technical="Provider amount ≠ receipt amount.",
    customer="Dispute / recon nightmare.",
    security="Integrity of settlement amounts.",
    performance="N/A",
    scalability="N/A",
    compliance="Payment recon.",
    risk="Hidden overpay.",
    fix_immediate="Reject over-amount unless explicit overpay policy; alert.",
    fix_short="Store both provider and applied amounts.",
    fix_long="Automatic refund of overpay.",
    effort="1d",
    tests="Overpay webhook → 4xx not PAID underpay.",
    acceptance="No silent clamp to PAID.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="SANDBOX_WEBHOOK_SECRET production boot check is pass no-op",
    category="Security",
    subcategory="Secrets",
    severity="Medium",
    priority="P1",
    module="Config",
    feature="settings.py",
    files="backend/config/settings.py; backend/payments/gateway.py",
    problem="Comment says required; code pass when empty in prod/staging. Failure only at verify-time.",
    evidence="settings.py ~241-245 pass",
    root_cause="Incomplete fail-closed boot.",
    business="Deploy looks healthy; first webhook fails opaquely.",
    technical="Misconfig latency.",
    customer="Payment outage at first capture.",
    security="Encourages late weak fixes.",
    performance="N/A",
    scalability="N/A",
    compliance="Config control.",
    risk="Sandbox enabled without secret.",
    fix_immediate="ImproperlyConfigured when prod/staging and sandbox enabled or secret empty if used.",
    fix_short="Health ready checks secret present.",
    fix_long="Secrets manager integration.",
    effort="0.5d",
    tests="Prod boot without secret + sandbox → fail.",
    acceptance="Boot fails closed for missing sandbox secret when applicable.",
    status="Open",
    refs="BB-000258 related; Wave12 NEW",
)
add(
    title="Refresh cookie endpoint CSRF-exempt with configurable SameSite (access JWT in body)",
    category="Security",
    subcategory="Session",
    severity="Medium",
    priority="P1",
    module="Accounts",
    feature="CookieTokenRefreshView",
    files="backend/accounts/views.py; backend/config/settings.py",
    problem="DRF APIView csrf_exempt; returns access JWT in body; JWT_REFRESH_COOKIE_SAMESITE env-default Lax — ops may set None for split hosts.",
    evidence="CookieTokenRefreshView ~192-224; settings SameSite",
    root_cause="SPA refresh design without CSRF binding for cross-site.",
    business="Cross-site POST can mint access if SameSite=None.",
    technical="Session fixation/CSRF class risk.",
    customer="Account takeover if misconfigured.",
    security="Session integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth hardening.",
    risk="Split-domain deploy footgun.",
    fix_immediate="Refuse SameSite=None without CSRF token; document same-site only.",
    fix_short="Double-submit CSRF on refresh.",
    fix_long="BFF httpOnly access.",
    effort="1-2d",
    tests="SameSite=None without CSRF → ImproperlyConfigured or 403.",
    acceptance="Cross-site refresh cannot mint access without CSRF.",
    status="Open",
    refs="BB-000266 residual; Wave12 NEW",
)
add(
    title="Shared global SANDBOX_WEBHOOK_SECRET across all tenants",
    category="Security",
    subcategory="Payments tenancy",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="SandboxAdapter",
    files="backend/payments/gateway.py",
    problem="One env secret verifies all tenants' sandbox webhooks.",
    evidence="gateway.py ~71-83",
    root_cause="Env-global secret design.",
    business="Env leak forges any sandbox link.",
    technical="Cross-tenant forge surface.",
    customer="Multi-tenant payment integrity risk.",
    security="Tenancy boundary weak for sandbox.",
    performance="N/A",
    scalability="N/A",
    compliance="Multi-tenant isolation.",
    risk="Pairs with sandbox-in-prod Critical.",
    fix_immediate="Disable sandbox outside test; or per-company encrypted secret.",
    fix_short="Rotate per tenant.",
    fix_long="Remove sandbox settlement from shared cloud.",
    effort="1d",
    tests="Company A secret cannot verify company B sandbox webhook.",
    acceptance="No global sandbox HMAC in multi-tenant prod.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="VIEWER default can_view_financial_reports=True expands blast radius",
    category="Security",
    subcategory="RBAC design",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="CompanyUser defaults",
    files="backend/accounts/models.py",
    problem="VIEWER defaults financial reports True; combined with ungated list APIs grants money reads.",
    evidence="models.py ~179-191",
    root_cause="Viewer meant read-all originally.",
    business="Viewer is financial reader by default.",
    technical="Role naming mismatch.",
    customer="Unexpected data access.",
    security="Over-broad default.",
    performance="N/A",
    scalability="N/A",
    compliance="Least privilege.",
    risk="Amplifies API RBAC holes.",
    fix_immediate="Default False; grant explicitly.",
    fix_short="Migration to tighten existing VIEWER rows with opt-in.",
    fix_long="Rename roles ACCOUNTANT/VIEWER clearly.",
    effort="0.5d + migration",
    tests="New VIEWER cannot list journals/invoices without grant.",
    acceptance="VIEWER least privilege by default.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Company-wide notification list leaks recipient/body to any member",
    category="Security",
    subcategory="Privacy",
    severity="Medium",
    priority="P2",
    module="Core",
    feature="Notifications",
    files="backend/core/views.py; backend/core/serializers.py",
    problem="Filter by company only; serializer includes recipient, subject, body.",
    evidence="views.py ~143-150",
    root_cause="No per-user scope.",
    business="Any member reads others' share/email/SMS content.",
    technical="PII leak within tenant.",
    customer="Privacy breach.",
    security="Confidentiality.",
    performance="N/A",
    scalability="N/A",
    compliance="DPDP minimization.",
    risk="Phone/email harvest.",
    fix_immediate="Scope to created_by=request.user or Owner; redact bodies for staff.",
    fix_short="Notification ACL.",
    fix_long="Per-recipient inbox.",
    effort="0.5-1d",
    tests="User B cannot see User A notification body.",
    acceptance="Notifications private per user unless Owner.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Payment receipts/bank statements/search party PII readable without payment/financial caps",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="List APIs / search",
    files="backend/payments/views.py; backend/search/views.py",
    problem="Receipts/statements list HasCompany; search returns customers/suppliers/products with phone/GSTIN/prices to VIEWER; invoices gated but parties not.",
    evidence="payments views list super(); search/views.py ~16-66",
    root_cause="Partial search gating (BB-000083 invoices only).",
    business="VIEWER harvests CRM and cash/UPI/UTR via API.",
    technical="PII overshare.",
    customer="Privacy failure.",
    security="Confidentiality.",
    performance="Search also unscoped throttle.",
    scalability="DoS via search.",
    compliance="DPDP.",
    risk="Staff scrapes full customer book.",
    fix_immediate="List receipts → financial/payment caps; search deny VIEWER or require sales caps; strip prices.",
    fix_short="CompanyRateThrottle on search.",
    fix_long="Field-level RBAC.",
    effort="1d",
    tests="VIEWER search customers → empty/403; VIEWER receipts → 403.",
    acceptance="Party/cash data gated.",
    status="Open",
    refs="BB-000083 residual; Wave12 NEW",
)
add(
    title="Anonymous health readiness discloses infra topology (db/cache/celery/queue)",
    category="Security",
    subcategory="Info disclosure",
    severity="Medium",
    priority="P2",
    module="Core",
    feature="Health",
    files="backend/core/views.py; backend/Dockerfile; docker-compose.yml",
    problem="AllowAny returns db, cache, celery, celery_workers, pdf_queue_depth. Image HEALTHCHECK uses /health/ without ready while compose uses ?ready=1.",
    evidence="views.py ~59-104",
    root_cause="Combined liveness+readiness public.",
    business="Attackers map outages for timing DoS.",
    technical="Probe asymmetry Docker vs compose.",
    customer="N/A direct.",
    security="Recon aid.",
    performance="N/A",
    scalability="Targeted Celery DoS.",
    compliance="Ops hardening.",
    risk="Public topology leak.",
    fix_immediate="Public liveness {status} only; detailed ready internal/auth.",
    fix_short="Align Dockerfile HEALTHCHECK with ready policy.",
    fix_long="Separate /livez /readyz.",
    effort="0.5d",
    tests="Unauth /health/ no celery keys.",
    acceptance="Public health minimal.",
    status="Open",
    refs="BB-000218/294 residual; Wave12 NEW",
)
add(
    title="Readiness ignores Celery beat; beat service has no healthcheck",
    category="DevOps",
    subcategory="Observability",
    severity="Medium",
    priority="P2",
    module="Ops",
    feature="Celery beat",
    files="backend/core/views.py; docker-compose.yml",
    problem="Worker ping only; beat dead → API still ready; insights/depreciation never run.",
    evidence="compose beat no healthcheck; health worker-only",
    root_cause="Beat treated optional.",
    business="Silent staleness of AI/accounting schedules.",
    technical="False ready.",
    customer="Stale insights.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Ops reliability.",
    risk="Undetected schedule outage.",
    fix_immediate="Beat heartbeat key in Redis; include in ready.",
    fix_short="Compose healthcheck for beat.",
    fix_long="Unified scheduler monitoring.",
    effort="1d",
    tests="Kill beat → ready fails.",
    acceptance="Ready requires beat heartbeat.",
    status="Open",
    refs="BB-000046 residual; Wave12 NEW",
)
add(
    title="Backend Sentry dead without package; FE Sentry blocked by CSP connect-src self",
    category="DevOps",
    subcategory="Observability",
    severity="Medium",
    priority="P2",
    module="Ops",
    feature="Sentry",
    files="backend/config/settings.py; backend/requirements.txt; nginx/default.conf; web/src/main.tsx",
    problem="settings import sentry_sdk except ImportError pass; requirements has no sentry-sdk. FE init with VITE_SENTRY_DSN blocked by CSP connect-src 'self'.",
    evidence="settings.py ~412-427; nginx CSP; main.tsx Sentry init",
    root_cause="Optional observability never completed.",
    business="Believed error tracking does not exist.",
    technical="Silent no-op.",
    customer="Incidents invisible.",
    security="Reduced detection.",
    performance="N/A",
    scalability="N/A",
    compliance="Ops.",
    risk="Prod blind.",
    fix_immediate="Pin sentry-sdk; fail boot if DSN set and import fails; CSP allowlist or tunnel.",
    fix_short="Traces sample >0 in staging.",
    fix_long="OpenTelemetry.",
    effort="1d",
    tests="DSN set without package → boot fail; FE CSP allows ingest or tunnel.",
    acceptance="Sentry actually receives events when configured.",
    status="Open",
    refs="BB-000047/121 residual; Wave12 NEW",
)
add(
    title="GSTR-1 CDNR skips invoice-value mismatch gate; AFTER_TAX still allowed on TAX/RETAIL",
    category="GST",
    subcategory="GSTR",
    severity="Medium",
    priority="P2",
    module="Reporting",
    feature="gst_returns / discounts",
    files="backend/reporting/gst_returns.py; backend/sales/services.py",
    problem="Mismatched invoices excluded from B2B/B2C; notes always included. AFTER_TAX blocked only for InvoiceType.GST not TAX/RETAIL with party GSTIN.",
    evidence="gst_returns CDNR path; sales services AFTER_TAX check type GST only",
    root_cause="Incomplete mismatch/discount policy.",
    business="Section totals disagree; under-reported GSTR if issues ignored.",
    technical="Aid inconsistency.",
    customer="CA worksheet confusion.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR identity.",
    risk="Silent section drop.",
    fix_immediate="Apply mismatch gate to notes; extend AFTER_TAX block to all GST_INVOICE_TYPES with GSTIN.",
    fix_short="Health alert on mismatch notes.",
    fix_long="Forbid AFTER_TAX on any GST doc.",
    effort="0.5d",
    tests="AFTER_TAX on TAX+GSTIN blocked; mismatched CN excluded or flagged.",
    acceptance="Notes and invoices share mismatch policy.",
    status="Open",
    refs="BB-000038/093 residual; Wave12 NEW",
)
add(
    title="Inclusive invoices under-report discount_total; RCM flag clear leaves stale rcm_* memos",
    category="GST",
    subcategory="Billing",
    severity="Medium",
    priority="P2",
    module="Core",
    feature="billing.py / purchases",
    files="backend/core/services/billing.py; backend/purchases/services.py",
    problem="Inclusive path zeroes line discounts for tax pass; discount_total uses zeroed sum. H9 toggle off RCM never zeroes rcm_taxable/cgst/sgst/igst.",
    evidence="billing.py inclusive path; purchases services RCM clear",
    root_cause="Stash not accumulated into discount_total; memo fields not cleared.",
    business="Wrong discount analytics/PDF; phantom RCM in API.",
    technical="Data quality.",
    customer="Confusing totals.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Audit trail noise.",
    risk="Support burden.",
    fix_immediate="Accumulate stashed inclusive discounts; clear rcm_* when not RCM.",
    fix_short="Serializer hide stale memos.",
    fix_long="Single billing DTO.",
    effort="0.5d",
    tests="Inclusive 10% discount → discount_total>0; RCM off → rcm_*=0.",
    acceptance="discount_total and rcm memos accurate.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Journal number collisions across source types (JV-SALES_-id)",
    category="Accounting",
    subcategory="Journal identity",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="PostingService",
    files="backend/accounting/services.py",
    problem="JV-{source_type[:6]}-{source_id} → SALES_INVOICE and SALES_CREDIT_NOTE both JV-SALES_-42. No unique on number.",
    evidence="services.py ~129-130",
    root_cause="Truncated source_type in number.",
    business="Ambiguous audit/UI references.",
    technical="Non-unique human keys.",
    customer="Support confusion.",
    security="N/A",
    performance="N/A",
    scalability="Collision likelihood grows.",
    compliance="Audit trail clarity.",
    risk="Wrong journal cited.",
    fix_immediate="Include full source_type + purpose or sequence.",
    fix_short="Unique constraint (company, number).",
    fix_long="DocumentNumberService for journals.",
    effort="0.5d",
    tests="SI and SCN same id → distinct journal numbers.",
    acceptance="No JV number collisions.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Auto return CNs omit source_item / invoice HSN snapshot; BooksHealth ignores accounting_enabled",
    category="Accounting",
    subcategory="Notes / health",
    severity="Medium",
    priority="P2",
    module="Sales",
    feature="Auto CN / books health",
    files="backend/sales/services.py; backend/purchases/services.py; backend/accounting/services.py",
    problem="Auto CN lines from return lines without source_item_id; HSN from product not invoice snapshot. Books health alerts missing journals even when accounting off.",
    evidence="auto CN builders; books health ~314-325",
    root_cause="Shortcut line copy; health ungated.",
    business="Table 12/CDNR HSN drift; false health alerts.",
    technical="Noise + compliance drift.",
    customer="Wrong HSN on notes; alert fatigue.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="HSN continuity.",
    risk="GSTR HSN mismatch.",
    fix_immediate="Map return→invoice lines with source_item; gate health on accounting_enabled.",
    fix_short="HSN snapshot fields on return lines.",
    fix_long="Lineage graph.",
    effort="1d",
    tests="Auto CN HSN equals invoice line; accounting off → no missing posting alert.",
    acceptance="HSN lineage + quiet health when books off.",
    status="Open",
    refs="BB-000105 residual; Wave12 NEW",
)
add(
    title="GSTR B2CL inter-check uses tax-time party state not filing POS; place_of_supply_known accepts any text",
    category="GST",
    subcategory="GSTR / POS",
    severity="Medium",
    priority="P2",
    module="Reporting",
    feature="B2CL / billing gates",
    files="backend/reporting/gst_returns.py; backend/core/services/billing.py",
    problem="B2CL bucket uses customer.state for inter while row POS uses filing POS. place_of_supply_known true for any non-empty string.",
    evidence="gst_returns B2CL; billing place_of_supply_known",
    root_cause="Dual POS sources; weak known check.",
    business="Wrong B2CL vs B2CS after filing amend; typos pass Complete.",
    technical="Classification drift.",
    customer="Wrong GSTR buckets.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR B2CL.",
    risk="Misfiled B2C large.",
    fix_immediate="Classify inter using filing POS/GSTIN; require mappable POS when tax_enabled.",
    fix_short="Reject unmapped states.",
    fix_long="POS code FK.",
    effort="0.5d",
    tests="Filing POS amend reclassifies B2CL; 'xyz' state blocked.",
    acceptance="B2CL uses filing POS; unmapped POS rejected.",
    status="Open",
    refs="BB-000274 related; Wave12 NEW",
)
add(
    title="Invite can still set invitee password; no password-change / logout-all API",
    category="Security",
    subcategory="Auth lifecycle",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="Invite / password",
    files="backend/accounts/views.py; backend/accounts/serializers.py; backend/accounts/urls_auth.py",
    problem="Invite optional password remains; no change-password or revoke-all-refresh endpoints. Compromised password keeps refresh cookie up to JWT_REFRESH_DAYS.",
    evidence="invite views ~412-422; urls_auth no change-password",
    root_cause="Partial invite hardening (BB-000306).",
    business="Shared/weak invite secrets; no recovery rotation.",
    technical="Session lifetime after compromise.",
    customer="Account recovery weak.",
    security="Credential lifecycle.",
    performance="N/A",
    scalability="N/A",
    compliance="Access control.",
    risk="Stolen password window.",
    fix_immediate="Prod forbid invite password; add change-password + blacklist refreshes.",
    fix_short="Logout all devices.",
    fix_long="Invite token email only.",
    effort="2d",
    tests="Prod invite with password rejected; change password revokes old refresh.",
    acceptance="No owner-set passwords; rotation revokes sessions.",
    status="Open",
    refs="BB-000306 residual; Wave12 NEW",
)
add(
    title="Gateway credential PATCH merges empty strings wiping secrets",
    category="Security",
    subcategory="Secrets",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="GatewaySettingsView",
    files="backend/payments/views.py",
    problem="existing.update({k:v if v is not None}) — empty string overwrites webhook_secret/key_secret. GSP merge strips empties.",
    evidence="views.py ~833-837",
    root_cause="Inconsistent empty handling.",
    business="Accidental wipe breaks verify.",
    technical="Secret destruction.",
    customer="Payment outage.",
    security="Availability + integrity.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Ops footgun.",
    fix_immediate="Ignore empty strings like GSP merge.",
    fix_short="Explicit clear_secret flag.",
    fix_long="Secrets vault.",
    effort="0.25d",
    tests="PATCH webhook_secret='' leaves previous.",
    acceptance="Empty string does not wipe secrets.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="docker-compose env_file.required false; no prod overlay; CD pushes latest without provenance",
    category="DevOps",
    subcategory="Deploy",
    severity="Medium",
    priority="P2",
    module="DevOps",
    feature="compose / CD",
    files="docker-compose.yml; .github/workflows/cd.yml; web/nginx.conf",
    problem="env_file required false; no docker-compose.prod.yml; CD tags :latest without SBOM/sign/manual approve.",
    evidence="compose L36-39; cd.yml latest push",
    root_cause="BB-000314 accepted residual; CD convenience.",
    business="Easy half-configured deploys; accidental prod pull.",
    technical="Weak supply chain.",
    customer="Unstable deploys.",
    security="Missing secrets / mutable latest.",
    performance="N/A",
    scalability="N/A",
    compliance="Change management.",
    risk="Prod on broken main.",
    fix_immediate="prod overlay required true; digest-only promote; gate latest.",
    fix_short="Cosign attestations.",
    fix_long="GitOps environments.",
    effort="2d",
    tests="Prod compose without .env fails; CD docs forbid unpinned latest.",
    acceptance="Prod requires secrets file; latest gated.",
    status="Open",
    refs="BB-000314 residual; Wave12 NEW",
)
add(
    title="AI tax-refusal regex bypassable; LLM path weakly tested for injection",
    category="AI",
    subcategory="Honesty / injection",
    severity="Medium",
    priority="P2",
    module="Insights",
    feature="assistant",
    files="backend/insights/assistant.py; backend/tests/test_phase6_insights.py",
    problem="TAX_PATTERNS narrow; with LLM key user text goes raw. Injection tests only under rules fallback.",
    evidence="assistant.py ~55-58, 396-520; tests rules-only",
    root_cause="Heuristic refusal + incomplete adversarial suite.",
    business="Tax/filing advice leakage; injection when LLM on.",
    technical="Policy bypass.",
    customer="Unsafe AI advice.",
    security="Prompt injection residual.",
    performance="N/A",
    scalability="N/A",
    compliance="AI honesty gates.",
    risk="Regulatory advice liability.",
    fix_immediate="Broader classifier; tool-only answers; fake-provider injection tests.",
    fix_short="Allowlist tools only.",
    fix_long="Separate compliance model.",
    effort="2-4d",
    tests="Paraphrased tax questions refused; injection cannot cross tenant with LLM mock.",
    acceptance="Tax advice blocked; injection tests cover LLM path.",
    status="Open",
    refs="BB-000070/309 residual; Wave12 NEW",
)
add(
    title="Light e2e mock-only; seeds obsolete localStorage JWTs; golden path narrow",
    category="Testing",
    subcategory="E2E",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="Playwright",
    files="web/.env.e2e; web/e2e/smoke.spec.ts; web/playwright.config.ts",
    problem="VITE_USE_MOCKS=true; Desktop Chrome only; smoke seeds localStorage JWTs while prod is memory+httpOnly cookie.",
    evidence="smoke.spec.ts L16-17; .env.e2e mocks",
    root_cause="E2E not updated after auth cookie migration.",
    business="False confidence on auth/RBAC/GST.",
    technical="Tests document wrong session model.",
    customer="Regressions slip.",
    security="Auth regressions undetected.",
    performance="N/A",
    scalability="N/A",
    compliance="QA gate weak.",
    risk="Ship broken cookie auth.",
    fix_immediate="Drop obsolete token seeding; add Pixel viewport; expand golden against real API in CI job.",
    fix_short="Contract money tests FE↔BE.",
    fix_long="Full critical-path e2e matrix.",
    effort="5-8d",
    tests="Golden auth uses cookie refresh; mobile viewport smoke.",
    acceptance="CI e2e exercises real auth model.",
    status="Open",
    refs="BB-000221/310 residual; Wave12 NEW",
)
add(
    title="Accessibility residual on billing tables; mobile dense editors oversell responsive",
    category="UX",
    subcategory="a11y / mobile",
    severity="Medium",
    priority="P2",
    module="Web",
    feature="NewInvoicePage / AppShell",
    files="web/src/pages/sales/NewInvoicePage.tsx; web/src/components/AppShell.tsx; docs/reviews/16_MOBILE_REVIEW.md",
    problem="Skip link exists; dense billing tables lack systematic column/header a11y; phone pilots get horizontal-scroll editors only.",
    evidence="Sparse aria beyond icon buttons; multi-column invoice editor",
    root_cause="Shell a11y fixed; core flows not.",
    business="AT users and phone pilots cannot realistically bill.",
    technical="a11y debt on highest-value page.",
    customer="Exclusion / failed mobile pilots.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Accessibility expectations.",
    risk="Responsive claim oversell.",
    fix_immediate="Label associations; table scopes; desktop-recommended banner on phone.",
    fix_short="axe CI; narrow mobile invoice layout.",
    fix_long="Dedicated mobile billing mode.",
    effort="3-5d",
    tests="axe critical pages clean; mobile banner shown <md.",
    acceptance="Invoice flow usable with SR; honesty on mobile limits.",
    status="Open",
    refs="BB-000110/179 residual; Wave12 NEW",
)
add(
    title="Structured observability thin (no request-id/JSON logs/metrics); OpenAPI DESCRIPTION overclaims",
    category="DevOps",
    subcategory="Observability / honesty",
    severity="Medium",
    priority="P2",
    module="Config",
    feature="Logging / Spectacular",
    files="backend/config/settings.py",
    problem="Console verbose text only; Sentry traces default 0.0; SPECTACULAR DESCRIPTION 'One-stop GST billing & business management platform' vs README pilot honesty.",
    evidence="settings logging ~429-449; SPECTACULAR DESCRIPTION ~224-227",
    root_cause="MVP logging left; marketing blurb in schema.",
    business="Incident response hard; integrators reuse inflated blurb.",
    technical="No correlation IDs.",
    customer="Slow support.",
    security="Weak detection.",
    performance="Hard to diagnose latency.",
    scalability="No RED metrics.",
    compliance="Honesty.",
    risk="Ops blindness + marketing drift.",
    fix_immediate="JSON logs + X-Request-ID; align DESCRIPTION with README.",
    fix_short="Basic metrics for throttles/PDF queue.",
    fix_long="Full APM.",
    effort="2d",
    tests="Request returns X-Request-ID; OpenAPI description matches pilot scope.",
    acceptance="Correlated logs; honest schema blurb.",
    status="Open",
    refs="BB-000047 residual; Wave12 NEW",
)
add(
    title="Universal search unscoped throttle + expensive icontains; edge nginx no limit_req",
    category="Performance",
    subcategory="Search / edge",
    severity="Medium",
    priority="P2",
    module="Search",
    feature="Universal search",
    files="backend/search/views.py; nginx/default.conf; backend/core/throttles.py",
    problem="5× icontains without throttle_scope; nginx no limit_req on auth/search.",
    evidence="search/views.py; nginx default.conf",
    root_cause="Search added without rate/index plan.",
    business="Tenant DoS / worker exhaustion.",
    technical="Full table scans.",
    customer="Slow app under abuse.",
    security="DoS vector.",
    performance="High.",
    scalability="Poor.",
    compliance="N/A",
    risk="Shared-DB noisy neighbor.",
    fix_immediate="CompanyRateThrottle; nginx limit_req on auth/search.",
    fix_short="Trigram indexes.",
    fix_long="Search service.",
    effort="1-2d",
    tests="Search exceeds throttle → 429; nginx limit documented.",
    acceptance="Search and auth edge-limited.",
    status="Open",
    refs="BB-000187 residual; Wave12 NEW",
)

# ─── LOW ────────────────────────────────────────────────────────────────────
add(
    title="OTP generation uses random.randint not secrets",
    category="Security",
    subcategory="Crypto hygiene",
    severity="Low",
    priority="P3",
    module="Accounts",
    feature="OTP",
    files="backend/accounts/views.py",
    problem="OTP uses random.randint not secrets.randbelow.",
    evidence="views.py ~272",
    root_cause="Non-CSPRNG habit.",
    business="Low practical risk with rate limits.",
    technical="Crypto hygiene.",
    customer="N/A",
    security="Low.",
    performance="N/A",
    scalability="N/A",
    compliance="Best practice.",
    risk="Theoretical predictability.",
    fix_immediate="secrets.randbelow(10**6).",
    fix_short="N/A",
    fix_long="N/A",
    effort="0.1d",
    tests="OTP still 6 digits.",
    acceptance="OTP from secrets module.",
    status="Open",
    refs="Wave12 NEW",
)
add(
    title="Access JWT still XSS-exfiltratable in memory (15m); Redis TLS not documented",
    category="Security",
    subcategory="Session / transport",
    severity="Low",
    priority="P3",
    module="Web",
    feature="session.ts / Redis",
    files="web/src/auth/session.ts; .env.production.example; backend/config/settings.py",
    problem="Memory access token XSS-exfiltratable for 15m. Production Redis may use redis:// not rediss://.",
    evidence="session.ts; env production example REDIS_URL",
    root_cause="BFF not done; Redis TLS optional.",
    business="Residual XSS window; broker eavesdrop on shared clouds.",
    technical="Defense in depth residual.",
    customer="Session abuse if XSS.",
    security="Low-Medium residual.",
    performance="N/A",
    scalability="N/A",
    compliance="Transport.",
    risk="Accept or BFF.",
    fix_immediate="Document XSS residual; document rediss://.",
    fix_short="BFF httpOnly access.",
    fix_long="mTLS Redis.",
    effort="0.5d docs / 3-5d BFF",
    tests="Docs mention residual; prod example rediss.",
    acceptance="Risk accepted or BFF landed.",
    status="Open",
    refs="BB-000266 residual; Wave12 NEW",
)
add(
    title="Dependabot omits Docker base images; CodeQL shallow without build",
    category="DevOps",
    subcategory="CI security",
    severity="Low",
    priority="P3",
    module="CI",
    feature="dependabot / codeql",
    files=".github/dependabot.yml; .github/workflows/codeql.yml",
    problem="No docker ecosystem; CodeQL init+analyze only without autobuild/security-extended.",
    evidence="dependabot.yml; codeql.yml",
    root_cause="Minimal enablement.",
    business="False confidence; stale base CVEs.",
    technical="Shallow SAST.",
    customer="N/A",
    security="Detection gap.",
    performance="N/A",
    scalability="N/A",
    compliance="SSDCL lite.",
    risk="Missed vulns.",
    fix_immediate="Add docker dependabot; CodeQL autobuild + security-extended.",
    fix_short="Trivy image scan in CD.",
    fix_long="Full AppSec pipeline.",
    effort="1d",
    tests="Dependabot opens docker PRs; CodeQL uses build.",
    acceptance="Bases monitored; CodeQL deeper.",
    status="Open",
    refs="BB-000220 residual; Wave12 NEW",
)
add(
    title="CELERY_TIMEZONE defaults UTC while Django TIME_ZONE Asia/Kolkata; round-off absorbed into Sales/Purchases",
    category="Configuration",
    subcategory="Timezone / GL purity",
    severity="Low",
    priority="P3",
    module="Config",
    feature="Celery / PostingService",
    files="backend/config/settings.py; backend/accounting/services.py; backend/accounting/reports.py",
    problem="CELERY_TIMEZONE default UTC vs Django IST; round-off folded into Sales/Purchases not round-off account; BS P&L plug all-time without FY close; e-invoice SEZ getattr dead; nil-rated additive noise.",
    evidence="settings CELERY_TIMEZONE; post_purchase/sales round-off; reports.py P&L plug",
    root_cause="Defaults and accounting simplifications.",
    business="Wrong wall-clock jobs if ops change TZ; noisy revenue; weak multi-year equity.",
    technical="Footguns + purity.",
    customer="Confusing reports.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Books presentation.",
    risk="Mis-scheduled insights.",
    fix_immediate="Default CELERY_TIMEZONE to Asia/Kolkata or document; separate round-off lines; document BS plug/nil.",
    fix_short="FY close process.",
    fix_long="Full statutory CoA.",
    effort="1-2d",
    tests="Beat TZ documented; round-off account used when accounting_enabled.",
    acceptance="TZ single source; round-off explicit.",
    status="Open",
    refs="BB-000234 residual; Wave12 NEW",
)
add(
    title="E2E smoke seeds obsolete localStorage JWTs (test honesty)",
    category="Testing",
    subcategory="E2E honesty",
    severity="Low",
    priority="P3",
    module="Web",
    feature="e2e/smoke",
    files="web/e2e/smoke.spec.ts",
    problem="Tests seed bizboard.access/refresh while production auth uses memory access + httpOnly refresh cookie.",
    evidence="smoke.spec.ts L16-17",
    root_cause="Mocks key off user blob; tokens leftover.",
    business="False confidence.",
    technical="Docs wrong session.",
    customer="N/A",
    security="Test debt.",
    performance="N/A",
    scalability="N/A",
    compliance="QA.",
    risk="Misleads future auth changes.",
    fix_immediate="Seed display user only; assert mock banner.",
    fix_short="Golden cookie path.",
    fix_long="Remove mocks from critical e2e.",
    effort="0.5d",
    tests="Smoke does not write access/refresh keys.",
    acceptance="E2E session model matches prod.",
    status="Open",
    refs="Wave12 NEW",
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
| **References** | Wave 12 re-audit {TODAY}; code evidence |

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

    # Preserve prior wave metadata
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
        "wave12_new": len(new_issues),
        "wave12_start": f"BB-{start_id:06d}",
        "wave12_end": f"BB-{start_id + len(new_issues) - 1:06d}",
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
    ):
        if k in prior:
            result[k] = prior[k]
    return result


def update_changelog(stats: dict) -> None:
    sev = {k: sum(1 for d in ISSUES if d["severity"] == k) for k in ("Critical", "High", "Medium", "Low")}
    entry = f"""# docs/reviews — CHANGELOG

## {TODAY} — Wave 12 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Waves 10–11 claimed Open==0.

### Outcomes

- Appended **{len(ISSUES)}** issues `{stats['wave12_start']}` … `{stats['wave12_end']}` (Critical {sev['Critical']} · High {sev['High']} · Medium {sev['Medium']} · Low {sev['Low']}).
- Register total: **{stats['total']}**.
- Status: Open **{stats['status'].get('Open', 0)}** · Resolved/Deferred retained for untouched IDs.
- Invalidated Waves 10–11 “Open == 0” as a launch gate (see BB-000325).
- Production Readiness Score revised **6.7 → 3.5**.

### Highest new Criticals

- BB-000318 Sandbox provider allowed in production
- BB-000319 Notes/returns/orders mutate under HasCompany (VIEWER posts GL/stock)
- BB-000320 FE tax preview missing state-name→code map
- BB-000321 FEFO cancel restores wrong batch
- BB-000322 Purchase expense + COGS/Inventory hybrid double-count
- BB-000323 supplier_outstanding double-counts return+auto CN
- BB-000324 E-invoice SupTyp B2B without buyer GSTIN
- BB-000325 Wave 10–11 Open==0 meta invalidation

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 12).

Script: `_wave12_reaudit_append.py` (append-only; IDs permanent).

---

"""
    if CHANGELOG.exists():
        old = CHANGELOG.read_text(encoding="utf-8")
        if old.startswith("# docs/reviews — CHANGELOG"):
            idx = old.find("\n## ")
            if idx >= 0:
                old = old[idx + 1 :]
        if "Wave 12 independent re-audit" in old:
            print("CHANGELOG already has Wave 12 — skip prepend body duplicate")
            return
        CHANGELOG.write_text(entry + old, encoding="utf-8")
    else:
        CHANGELOG.write_text(entry, encoding="utf-8")


def append_exec_summary(stats: dict) -> None:
    if not EXEC.exists():
        return
    text = EXEC.read_text(encoding="utf-8")
    # Update latest banner line
    text = re.sub(
        r"\*\*Latest:\*\*[^\n]*",
        f"**Latest:** Wave 12 independent re-audit {TODAY} — register **{stats['total']}** issues. "
        f"**Open: {stats['status'].get('Open', 0)}.** "
        f"Resolved {stats['status'].get('Resolved', 0)}. "
        f"Deferred — roadmap {stats['status'].get('Deferred — roadmap', 0)}. "
        f"Production Readiness Score **3.5 / 10**.",
        text,
        count=1,
    )
    if "Wave 12 independent re-audit" in text and "Wave 12 re-audit" in text:
        # still append block if missing detailed section
        pass
    if f"## Wave 12 re-audit ({TODAY})" in text:
        EXEC.write_text(text, encoding="utf-8")
        return
    block = f"""

---

## Wave 12 re-audit ({TODAY}) — SUPERSEDES Waves 10–11 “Open == 0”

Independent code re-verification **invalidated Waves 10–11 open-closure**. Prior remediations (HMAC sandbox signature, cookie refresh, note GL posts, B2CL ₹1L, etc.) landed, but **sandbox-in-prod, API RBAC holes on notes/returns/masters, FE/BE tax POS divergence, FEFO cancel corruption, hybrid purchase/COGS GL, supplier AP double-count, and e-invoice B2B-without-GSTIN** remain Critical. **{stats['wave12_new']} new issues** logged as `{stats['wave12_start']}` … `{stats['wave12_end']}`.

### Updated verdict

| Audience | Deploy? |
|----------|---------|
| Internal dogfood (sandbox payments off, accounting off, Owner-only API use) | **Conditional** |
| Paid pilot with multi-role staff / payments / books | **No — until Wave 12 P0 Criticals closed** |
| GA / full ERP claims | **No** |

### Scores (0–10) — Wave 12

| Dimension | Score | Notes |
|-----------|------:|-------|
| Production Readiness | **3.5** | Sandbox-in-prod + RBAC API holes + books/GL model |
| Architecture | **5.0** | Hybrid inventory GL; dual tax engines FE/BE |
| Security | **3.0** | VIEWER can mutate notes/returns via API; sandbox provider |
| Performance | **4.0** | fetchAllPages residual; search unthrottled |
| Accounting Correctness | **3.0** | Expense+COGS hybrid; AP double-count; RCM notes |
| GST Compliance | **3.5** | FE POS mismatch; openings in GSTR; e-invoice B2B |
| Maintainability | **5.0** | God modules still Deferred |
| Scalability | **4.0** | Client fetch-all; no load proof |
| Testing Coverage | **4.5** | Mock e2e; LLM injection gap |

### Register totals (cumulative)

| Metric | Count |
|--------|------:|
| **Total issues** | **{stats['total']}** |
| Critical | {stats['severity'].get('Critical', 0)} |
| High | {stats['severity'].get('High', 0)} |
| Medium | {stats['severity'].get('Medium', 0)} |
| Low | {stats['severity'].get('Low', 0)} |
| **Open** | **{stats['status'].get('Open', 0)}** |

### Wave 12 P0 blockers

1. **BB-000318** — Sandbox provider in production
2. **BB-000319** — Notes/returns HasCompany-only mutate
3. **BB-000320** — FE/BE state-name tax split
4. **BB-000321** — FEFO cancel batch corruption
5. **BB-000322** — Purchase 5100 + COGS 1400 hybrid
6. **BB-000323** — supplier_outstanding double-count
7. **BB-000324** — E-invoice B2B without GSTIN
8. **BB-000325** — Open==0 process invalidation

### Final CTO Verdict (Wave 12)

**Do not treat Waves 10–11 Open==0 as a quality gate.** Require adversarial residual tests before any Critical Resolve.

**Do not enable sandbox payment provider or public webhooks in production.**

**Do not enable multi-role staff access** until API RBAC matches FE for notes/returns/masters/invoices.

**Do not enable accounting_enabled** until inventory GL model is single-method and AP outstanding is consistent.

**Do not commercially launch** as Cloud ERP with Manufacturing/Payroll/CRM/live GSP/WhatsApp Business claims.

"""
    EXEC.write_text(text.rstrip() + block + "\n", encoding="utf-8")


def update_roadmap(stats: dict) -> None:
    if not ROADMAP.exists():
        return
    text = ROADMAP.read_text(encoding="utf-8")
    if "Wave 12 hotfix" in text:
        return
    block = f"""

---

## Wave 12 hotfix track ({TODAY}) — P0 before any paid multi-role pilot

> Waves 10–11 Open==0 is **not** a launch gate. Open count now **{stats['status'].get('Open', 0)}** (`{stats['wave12_start']}`–`{stats['wave12_end']}`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Sandbox-in-prod | BB-000318, BB-000348, BB-000351 | No sandbox settlement in prod |
| API RBAC parity | BB-000319, BB-000326–329, BB-000330–332 | VIEWER cannot mutate/read money |
| FE/BE tax POS | BB-000320, BB-000333, BB-000361 | Preview == Complete tax split |
| Inventory integrity | BB-000321, BB-000338–341 | FEFO cancel/return/challan/SO batch-safe |
| Books/AP/GL model | BB-000322, BB-000323, BB-000335–337, BB-000359 | Single inventory model; AP once |
| E-invoice/GSTR | BB-000324, BB-000334, BB-000357 | Honest payloads; openings excluded |
| Config/DevOps honesty | BB-000342–345, BB-000353–354 | Flags/constraints/Sentry truth |
| Process | BB-000325 | Stop checklist-only closure |

**Exit:** Conditional billing pilot with Owner-only staff, sandbox banned in prod, accounting off, FE tax map fixed.

"""
    if "## Scope C completed" in text:
        text = text.replace("## Scope C completed", block + "\n## Scope C completed", 1)
    else:
        text = text.rstrip() + block
    ROADMAP.write_text(text, encoding="utf-8")


def update_review_docs(stats: dict) -> None:
    banner = (
        f"\n\n---\n\n## Wave 12 re-audit ({TODAY})\n\n"
        f"Independent re-verification appended `{stats['wave12_start']}`…`{stats['wave12_end']}` "
        f"({stats['wave12_new']} issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. "
        f"Open count: **{stats['status'].get('Open', 0)}**. "
        f"Waves 10–11 Open==0 invalidated.\n"
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
        if f"Wave 12 re-audit ({TODAY})" in text:
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
    if len(existing) < 317:
        raise SystemExit(f"Expected ≥317 issues in _stats.json, got {len(existing)}")

    banner = (
        f"\n## Wave 12 re-audit ({TODAY})\n\n"
        f"Appended **{len(ISSUES)}** new issues "
        f"`BB-{START_ID:06d}` … `BB-{START_ID + len(ISSUES) - 1:06d}` "
        f"from independent code re-verification after Waves 10–11 open-closure. "
        f"Prior IDs unchanged. "
        f"**Invalidates Waves 10–11 Open==0 as a launch gate.**\n"
    )
    if f"Wave 12 re-audit ({TODAY})" not in text:
        text = text.replace("## How to use\n", "## How to use\n" + banner + "\n", 1)

    body = "".join(fmt_issue(START_ID + i, d) for i, d in enumerate(ISSUES))
    if not text.endswith("\n"):
        text += "\n"
    text = text + "\n# Wave 12 appended issues\n" + body
    stats = rebuild_stats(existing, ISSUES, START_ID)
    text = patch_register_totals(text, stats)
    text = re.sub(
        r"\*\*Audit date:\*\*[^\n]*",
        f"**Audit date:** 2026-08-02 (Wave 12 re-audit {TODAY})",
        text,
        count=1,
    )
    REGISTER.write_text(text, encoding="utf-8")
    STATS.write_text(json.dumps(stats, indent=2), encoding="utf-8")
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

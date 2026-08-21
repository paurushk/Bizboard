#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 9 independent re-audit (2026-08-03): append BB-000258+; reopen false Resolves.

Never regenerates prior IDs. Append-only. IDs permanent.
Invalidates Waves 1–6 “Open == 0” as a commercial launch gate.
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
START_ID = 258

ISSUES: list[dict] = []


def add(**kwargs):
    ISSUES.append(kwargs)


# ─── CRITICAL ───────────────────────────────────────────────────────────────
add(
    title="Sandbox webhook signature is static forgeable string X-Sandbox-Signature: ok",
    category="Security",
    subcategory="Payments",
    severity="Critical",
    priority="P0",
    module="Payments",
    feature="Sandbox webhooks",
    files="backend/payments/gateway.py; backend/payments/views.py",
    problem="SandboxAdapter.verify_webhook accepts header value 'ok'. Explicit provider=sandbox (and non-prod test-mode remap) still settles CAPTURED receipts after this check.",
    evidence="gateway.py L95-96: return headers.get('X-Sandbox-Signature','')=='ok'",
    root_cause="Dev convenience left on settlement path; Wave 6 closed BB-000196 for empty→sandbox in prod only.",
    business="Forged paid status without money.",
    technical="Webhook auth trivially bypassed for sandbox/test remaps.",
    customer="Invoices marked paid fraudulently.",
    security="Critical payment forgery.",
    performance="N/A",
    scalability="Attack scales with known provider_link_id.",
    compliance="Payment integrity failure.",
    risk="Silent AR fraud in staging/pilot and any sandbox-enabled deploy.",
    fix_immediate="Disable sandbox webhooks outside DJANGO_ENV=test; HMAC with per-company secret.",
    fix_short="Never remap named providers to sandbox; require explicit provider=sandbox + HMAC.",
    fix_long="Provider→company binding; signed event ledger.",
    effort="1-2d",
    tests="X-Sandbox-Signature:ok must 401 outside test; HMAC valid settles only.",
    acceptance="No settlement via static sandbox signature outside CI.",
    status="Open",
    refs="BB-000196 residual; BB-000004; Wave9",
)
add(
    title="Company PATCH bypasses GatewaySettingsView guards (test_mode/provider)",
    category="Security",
    subcategory="Payments",
    severity="Critical",
    priority="P0",
    module="Accounts",
    feature="Company settings",
    files="backend/accounts/serializers.py CompanySerializer",
    problem="payment_gateway_provider and payment_gateway_test_mode remain writable on CompanySerializer while GatewaySettingsView alone blocks cashfree/payu and prod test_mode.",
    evidence="serializers.py fields L81; read_only_fields L85-90 omit gateway fields",
    root_cause="Dual write paths; only one hardened in Wave 6.",
    business="Owner can re-enable forgeable settlement paths via /api/v1/company/.",
    technical="Bypasses Wave 6 payment gates.",
    customer="Unexpected test-mode settlements.",
    security="Critical config bypass → payment forgery.",
    performance="N/A",
    scalability="N/A",
    compliance="Control bypass.",
    risk="Hardening undone by alternate API.",
    fix_immediate="Make gateway fields read-only on CompanySerializer; mutate only via GatewaySettingsView.",
    fix_short="Centralize company money-config mutations.",
    fix_long="Settings domain service with audit log.",
    effort="0.5d",
    tests="PATCH company test_mode=true in prod → rejected; only GatewaySettingsView succeeds with guards.",
    acceptance="Company PATCH cannot change gateway provider/test_mode.",
    status="Open",
    refs="BB-000196/204 bypass; Wave9 NEW",
)
add(
    title="Cancel sales return leaves auto credit note (AR+CDNR+GL orphan)",
    category="Accounting",
    subcategory="Returns",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Sales returns",
    files="backend/sales/services.py cancel_return; complete_return",
    problem="complete_return auto-creates and completes SalesCreditNote; cancel_return reverses stock only — never cancels the CN or reverses GL.",
    evidence="services.py L692-725 auto CN; L732-758 cancel without SalesNotesService.cancel_credit_note",
    root_cause="Cancel path not paired with Wave 3 auto-CN lifecycle.",
    business="Books/GST wrong after return cancel.",
    technical="Stock restored; AR still relieved; CDNR still shows CN; GL credit remains.",
    customer="Wrong customer balance; filing mismatches.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR CDNR + books diverge from inventory.",
    risk="CA rejects books; customer disputes.",
    fix_immediate="On cancel, cancel linked auto CN and reverse GL.",
    fix_short="Link return↔CN FK; transactional cancel cascade.",
    fix_long="Document lifecycle state machine for return/CN pairs.",
    effort="1-2d",
    tests="Complete return→cancel→CN cancelled, GL reversed, outstanding restored.",
    acceptance="Cancel return restores stock, AR, CDNR, and GL consistently.",
    status="Open",
    refs="BB-000043 incomplete; BB-000008; Wave9",
)
add(
    title="Sales debit notes never post GL on complete",
    category="Accounting",
    subcategory="Notes",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Sales debit notes",
    files="backend/sales/notes_services.py complete_debit_note",
    problem="complete_credit_note calls PostingService.post_note; complete_debit_note only emits events. cancel_debit_note tries to reverse a journal that was never created.",
    evidence="notes_services.py L138-143 post CN; L242-243 DN complete emit only; L252-258 reverse on cancel",
    root_cause="CN posting added; DN path omitted.",
    business="AR ledger increases; GL AR control does not → BooksHealth mismatch; understated output tax in GL.",
    technical="Dual-ledger divergence.",
    customer="Statements vs books disagree.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GST output tax not in GL for DNs.",
    risk="Audit failure.",
    fix_immediate="PostingService.post_note(..., direction=SALES_DEBIT) on complete.",
    fix_short="Shared note complete helper for CN/DN.",
    fix_long="Event-driven posting bus.",
    effort="0.5d",
    tests="DN complete creates POSTED journal; cancel reverses.",
    acceptance="DN complete always posts when accounting_enabled.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Purchase credit/debit notes never post GL on complete",
    category="Accounting",
    subcategory="Notes",
    severity="Critical",
    priority="P0",
    module="Purchases",
    feature="Purchase notes",
    files="backend/purchases/notes_services.py",
    problem="Purchase CN/DN complete saves+emit only; cancel reverses journals that were never posted.",
    evidence="complete_credit_note L127-135 emit only; cancel uses PostingService.reverse",
    root_cause="Purchase notes GL never wired (sales CN was).",
    business="AP/ITC books diverge from documents and GSTR inward netting.",
    technical="BooksHealth AP mismatch.",
    customer="Supplier balances wrong vs books.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="ITC/AP GL incorrect.",
    risk="Wrong purchase books.",
    fix_immediate="PostingService.post_note PURCHASE_CREDIT/DEBIT; mark GST period dirty.",
    fix_short="Parity with sales notes posting.",
    fix_long="Unified notes posting service.",
    effort="1d",
    tests="Purchase CN/DN complete→POSTED journals; cancel reverses.",
    acceptance="Purchase notes post GL when accounting_enabled.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Purchase returns relieve AP in ledger with no GL and no auto CN",
    category="Accounting",
    subcategory="Returns",
    severity="Critical",
    priority="P0",
    module="Purchases",
    feature="Purchase returns",
    files="backend/purchases/services.py complete_return; ledgers/services.py",
    problem="Purchase return posts stock only; outstanding subtracts returns; no auto purchase CN; no PostingService.",
    evidence="purchases/services.py L433-464 stock only; ledgers subtracts returns+CNs",
    root_cause="Sales-return auto-CN not mirrored for purchases.",
    business="AP ledger ↓ without journals; ITC/3B may miss return as CDNR equivalent.",
    technical="Dual ledger divergence.",
    customer="Supplier statements wrong.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Purchase return GST/books incomplete.",
    risk="CA-unusable purchase books.",
    fix_immediate="Sales-parity auto purchase CN + GL, or post return GL and stop double-counting.",
    fix_short="Unified return→note pipeline.",
    fix_long="Stock+AP+GST saga.",
    effort="2-3d",
    tests="Complete purchase return adjusts AP, GL, and GSTR consistently.",
    acceptance="Purchase return leaves stock, AP, GL, GST aligned.",
    status="Open",
    refs="BB-000008 purchase gap; Wave9",
)
add(
    title="Credit-limit and GL skip via spoofable notes=TALLY_OPENING",
    category="Security",
    subcategory="Integrity",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Invoice complete",
    files="backend/sales/services.py complete",
    problem="Any draft with notes exactly TALLY_OPENING skips credit limit, PDF queue, GST period dirty, and accounting postings. notes is a normal writable serializer field.",
    evidence="services.py L332-344 is_tally_opening = (invoice.notes or '').strip() == 'TALLY_OPENING'",
    root_cause="Tally adapter magic string on user-writable field.",
    business="Credit limits and books bypassed by typing a note.",
    technical="Integrity control bypass.",
    customer="Over-limit sales without controls.",
    security="Critical business-rule bypass.",
    performance="N/A",
    scalability="N/A",
    compliance="GST period dirty skipped.",
    risk="Fraudulent over-limit credit + silent unposted invoices.",
    fix_immediate="Use non-user source flag set only by Tally adapter; reject client magic notes.",
    fix_short="source enum on SalesInvoice.",
    fix_long="Import session marks openings immutably.",
    effort="1-2d",
    tests="Client notes=TALLY_OPENING still enforces credit limit + GL.",
    acceptance="Only internal import can mark openings.",
    status="Open",
    refs="BB-000077 related; Wave9 NEW",
)

# ─── HIGH ───────────────────────────────────────────────────────────────────
add(
    title="Non-prod remaps Razorpay webhook to SandboxAdapter when test_mode + empty creds",
    category="Security",
    subcategory="Payments",
    severity="High",
    priority="P0",
    module="Payments",
    feature="Webhooks",
    files="backend/payments/views.py payment_webhook",
    problem="Staging/pilot (DJANGO_ENV!=production) still remaps named provider to sandbox when test_mode and empty creds — enabling trivial signature settlement.",
    evidence="views.py L490-501 use_provider='sandbox' when not production",
    root_cause="Prod-only fail-closed left staging forgeable.",
    business="Misconfigured staging = forgeable settlements.",
    technical="Named provider path uses sandbox verify.",
    customer="False paid in pilot environments.",
    security="High forgery risk.",
    performance="N/A",
    scalability="N/A",
    compliance="Payment integrity.",
    risk="Pilot fraud / UAT false greens.",
    fix_immediate="Never remap named providers to sandbox.",
    fix_short="Require explicit sandbox URL + HMAC.",
    fix_long="Environment matrix with signed policies.",
    effort="0.5-1d",
    tests="razorpay + empty creds + test_mode → 403 in staging too.",
    acceptance="No provider remap to sandbox outside explicit sandbox provider.",
    status="Open",
    refs="BB-000196 residual; Wave9",
)
add(
    title="Access JWT remains in localStorage; refresh still in auth JSON body",
    category="Security",
    subcategory="Auth",
    severity="High",
    priority="P0",
    module="Web",
    feature="Session",
    files="web/src/auth/session.ts; backend/accounts/views.py",
    problem="Wave 6 claimed cookie auth (BB-000257 Resolved) but access token still localStorage; login/register/OTP/refresh responses still include refresh in JSON; CookieTokenRefreshView accepts body refresh.",
    evidence="session.ts getAccessToken localStorage; views _tokens_for_user returns refresh; CookieTokenRefreshView raw=data.get('refresh') or cookie",
    root_cause="Partial cookie migration marketed as complete.",
    business="XSS steals session; body refresh undoes httpOnly.",
    technical="Incomplete auth hardening.",
    customer="Account takeover via XSS.",
    security="High session theft.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth hygiene.",
    risk="Any XSS = full API access for token TTL.",
    fix_immediate="Omit refresh from JSON; cookie-only refresh; memory-only or httpOnly access.",
    fix_short="BFF cookie pattern + CSRF on refresh.",
    fix_long="Full cookie session with rotation.",
    effort="3-5d",
    tests="No refresh in JSON; body refresh rejected in non-DEBUG; access not in localStorage.",
    acceptance="XSS cannot exfiltrate refresh; access not durable in localStorage.",
    status="Open",
    refs="BB-000257 falsely Resolved; BB-000030; Wave9",
)
add(
    title="Accounting CoA/periods/fixed-asset dispose/bank recon still HasCompany-only",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P0",
    module="Accounting",
    feature="RBAC",
    files="backend/accounting/views.py",
    problem="Journal mutate/post/reverse gated IsOwner, but AccountViewSet, PeriodViewSet, FixedAssetViewSet.dispose (posts GL), BankReconSessionViewSet remain HasCompany. Period status writable → any member can CLOSE periods.",
    evidence="JournalViewSet IsOwner; sibling ViewSets inherit CompanyScopedViewSet HasCompany only",
    root_cause="BB-000200 fixed journals only.",
    business="Staff can alter chart, close periods, dispose assets, recon-match banks.",
    technical="Incomplete RBAC.",
    customer="Books integrity breached by non-owners.",
    security="High privilege escalation within tenant.",
    performance="N/A",
    scalability="N/A",
    compliance="Period close without authority.",
    risk="Fraudulent books mutation.",
    fix_immediate="Owner/CanPostJournals on all mutate; period close Owner-only; reports CanViewFinancialReports.",
    fix_short="Add CanPostJournals capability for ACCOUNTANT.",
    fix_long="Capability matrix per accounting action.",
    effort="2-3d",
    tests="VIEWER/staff cannot PATCH accounts/periods or dispose assets.",
    acceptance="Only Owner/accountant-capability mutates books structure.",
    status="Open",
    refs="BB-000200 incomplete; BB-000018; Wave9",
)
add(
    title="Payment links/allocations/bank recon/UPI create lack CanCreatePayments",
    category="Security",
    subcategory="RBAC",
    severity="High",
    priority="P1",
    module="Payments",
    feature="RBAC",
    files="backend/payments/views.py",
    problem="Receipts correctly use CanCreatePayments; PaymentLinkViewSet, PaymentAllocation create, BankStatement, Recon, UpiQr inherit HasCompany only.",
    evidence="PaymentLinkViewSet no get_permissions; Allocation create permission_classes=[IsAuthenticated,HasCompany]",
    root_cause="Capability flags applied unevenly.",
    business="VIEWER/staff without payment flag can create collect links and allocations.",
    technical="RBAC hole.",
    customer="Unauthorized money movement UI/API.",
    security="High authorization gap.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD failure.",
    risk="Unauthorized collections.",
    fix_immediate="Mirror CanCreatePayments / CanCancelDocuments on link+allocation+recon+UPI.",
    fix_short="Audit all payments ViewSets for flags.",
    fix_long="Policy engine.",
    effort="1d",
    tests="Staff without can_create_payments → 403 on link create.",
    acceptance="Payment money paths require can_create_payments.",
    status="Open",
    refs="BB-000018 residual; Wave9 NEW",
)
add(
    title="provider_link_id not unique; webhook uses global .first()",
    category="Security",
    subcategory="Multi-tenant",
    severity="High",
    priority="P1",
    module="Payments",
    feature="Webhooks",
    files="backend/payments/models.py; backend/payments/views.py",
    problem="provider_link_id CharField blank without UniqueConstraint; payment_webhook resolves with .filter(...).first().",
    evidence="models.py L190; views.py L471 .first()",
    root_cause="Missing uniqueness after amount-match removal.",
    business="Cross-tenant mis-settlement on ID collision.",
    technical="Ambiguous webhook routing.",
    customer="Wrong company invoice settled.",
    security="High tenancy integrity risk.",
    performance="N/A",
    scalability="Collision risk grows with volume.",
    compliance="Payment attribution failure.",
    risk="Cross-tenant settlement.",
    fix_immediate="UniqueConstraint(provider, provider_link_id); reject ambiguity.",
    fix_short="Include company in resolve via signed metadata.",
    fix_long="Immutable webhook receipt table.",
    effort="1d",
    tests="Duplicate provider_link_id rejected; ambiguous webhook 409.",
    acceptance="Webhook always resolves unique link or fails closed.",
    status="Open",
    refs="BB-000004 related; Wave9 NEW",
)
add(
    title="Challan-origin invoices skip COGS GL entirely",
    category="Accounting",
    subcategory="COGS",
    severity="High",
    priority="P1",
    module="Sales",
    feature="Delivery challan",
    files="backend/sales/services.py complete",
    problem="When stock_from_challan, SALE movements and cogs_total accumulation skipped; post_sales_cogs called with 0.",
    evidence="services.py L385-466 stock_from_challan branch",
    root_cause="Stock already moved on challan; COGS not computed from challan layers.",
    business="Inventory GL never credited; GP overstated.",
    technical="Incomplete accounting for challan path.",
    customer="Wrong margins.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Books incomplete.",
    risk="Material P&L error for challan workflows.",
    fix_immediate="Compute COGS from challan movements/valuation; always post COGS when accounting_enabled.",
    fix_short="Shared COGS calculator.",
    fix_long="Stock event → valuation → GL pipeline.",
    effort="1-2d",
    tests="Invoice from stocked challan posts COGS matching valuation.",
    acceptance="Challan path COGS equals non-challan for same qty/cost.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Soft-closed periods still accept new docs and GL posts",
    category="Accounting",
    subcategory="Periods",
    severity="High",
    priority="P1",
    module="Accounting",
    feature="Period close",
    files="backend/accounting/services.py PostingService.post",
    problem="H9 blocks SOFT_CLOSED; PostingService.post only blocks CLOSED; document complete uses warn-only period_complete_warning.",
    evidence="accounting/services.py L117-121 CLOSED only",
    root_cause="Soft-close not enforced on post path.",
    business="Filed/soft-closed periods keep changing.",
    technical="Period integrity cosmetic.",
    customer="CA cannot rely on soft close.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Period lock failure.",
    risk="Post-filing amendments via new docs.",
    fix_immediate="Block SOFT_CLOSED in PostingService.post and document complete (Owner override optional).",
    fix_short="Unified period gate helper.",
    fix_long="Hard/soft/reopen workflow with audit.",
    effort="1d",
    tests="SOFT_CLOSED rejects invoice complete and journal post.",
    acceptance="Soft-closed periods immutable without explicit reopen.",
    status="Open",
    refs="BB-000096 incomplete; Wave9",
)
add(
    title="E-Way payload uses float, non-UQC units, toPincode=0",
    category="GST",
    subcategory="e-Way",
    severity="High",
    priority="P1",
    module="Sales",
    feature="e-Way",
    files="backend/sales/eway_payload.py",
    problem="_num returns float; qtyUnit from unit_name not UQC; toPincode hardcoded 0.",
    evidence="eway_payload.py L30-31 float; L75-76 unit_name; L157-158 toPincode=0",
    root_cause="e-Invoice ValDtls fixed; e-Way parity never done.",
    business="NIC rejects / wrong PIN validation.",
    technical="Float drift; schema invalid.",
    customer="Cannot generate valid e-Way.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="e-Way Bill schema non-compliant.",
    risk="Live e-Way impossible even after GSP.",
    fix_immediate="Decimal strings, UQC snapshot, require buyer PIN.",
    fix_short="Share serializers with einvoice_payload.",
    fix_long="Schema-validated payload builder.",
    effort="1-2d",
    tests="Payload golden has string amounts, UQC, real PIN.",
    acceptance="e-Way payload NIC-valid for sample invoices.",
    status="Open",
    refs="BB-000012/056 e-Way parity; Wave9 NEW",
)
add(
    title="Manual e-Way mark sets GENERATED without Owner/enabled; no MANUAL status",
    category="GST",
    subcategory="Honesty",
    severity="High",
    priority="P1",
    module="Sales",
    feature="e-Way",
    files="backend/sales/einvoice_eway_actions.py mark_eway_generated",
    problem="mark_eway_generated sets EwayStatus.GENERATED without _require_owner / _require_eway_enabled; no MANUAL_EWB enum unlike e-invoice MANUAL_IRN.",
    evidence="einvoice_eway_actions.py L242-257",
    root_cause="e-Invoice honesty not mirrored to e-Way.",
    business="Health treats GENERATED as satisfied → false compliance green.",
    technical="Honesty gap.",
    customer="Ops believe e-Way done without portal.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="False e-Way attestation.",
    risk="Audit/GST officer challenge.",
    fix_immediate="Add MANUAL_EWB; Owner + enabled gates.",
    fix_short="Parity with mark-einvoice-generated.",
    fix_long="Portal-verified statuses only for GENERATED.",
    effort="1d",
    tests="Staff cannot mark; MANUAL_EWB not counted as portal GENERATED.",
    acceptance="Manual path distinct from portal GENERATED.",
    status="Open",
    refs="BB-000214 e-Way; Wave9",
)
add(
    title="GSTR-1 B2CL threshold still ₹2.5 lakh (law is ₹1 lakh from Aug 2024)",
    category="GST",
    subcategory="GSTR-1",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="GSTR-1",
    files="backend/reporting/gst_returns.py",
    problem="B2CL_THRESHOLD=250000; Notification 12/2024-CT reduced interstate B2C large threshold to ₹1,00,000 effective 1 Aug 2024.",
    evidence="gst_returns.py L32 B2CL_THRESHOLD = Decimal('250000')",
    root_cause="Threshold not updated after legal change.",
    business="Invoices ₹1L–₹2.5L misfiled as B2CS.",
    technical="Wrong GSTR-1 classification.",
    customer="Incorrect return aids → filing errors.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical GSTR-1 misclassification risk.",
    risk="Portal mismatch / notices.",
    fix_immediate="Set threshold 100000; update fixtures/tests.",
    fix_short="Configurable effective-dated thresholds.",
    fix_long="Rule engine for GST notifications.",
    effort="0.5d",
    tests="Interstate B2C 1.5L → B2CL.",
    acceptance="B2CL uses ₹1L threshold post-Aug-2024.",
    status="Open",
    refs="Wave9 NEW; Notif 12/2024-CT",
)
add(
    title="H9 money amend does not mark GST period dirty",
    category="GST",
    subcategory="Periods",
    severity="High",
    priority="P1",
    module="Sales",
    feature="H9 amend",
    files="backend/sales/serializers.py; backend/purchases/serializers.py; reporting/gst_periods.py",
    problem="Complete/filing amend call mark_period_dirty_if_snapshotted; H9 update after money amend does not.",
    evidence="H9 paths lack mark_period_dirty after successful amend",
    root_cause="Dirty marker wired to complete only.",
    business="Snapshotted periods stay clean after money rewrite → filing drift undetected.",
    technical="GST health false green.",
    customer="CA files stale snapshot.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Period integrity failure.",
    risk="Silent GSTR drift.",
    fix_immediate="Call dirty marker after successful H9 amend.",
    fix_short="Centralize post-money-mutation hooks.",
    fix_long="Event bus marks periods.",
    effort="0.5d",
    tests="H9 amend on snapshotted period → dirty=true.",
    acceptance="Any money amend dirties snapshotted period.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Manual journal lines accept cross-tenant Account PKs",
    category="Security",
    subcategory="Tenancy",
    severity="High",
    priority="P1",
    module="Accounting",
    feature="Journals",
    files="backend/accounting/serializers.py JournalLineSerializer; views.py",
    problem="JournalLineSerializer unconstrained Account FK; create bulk-creates lines without account.company_id == journal.company_id check.",
    evidence="No company scoping on account FK validation",
    root_cause="Serializer FK not queryset-scoped.",
    business="Cross-company GL pollution / IDOR.",
    technical="Tenant isolation hole.",
    customer="Books contaminated across tenants.",
    security="High IDOR.",
    performance="N/A",
    scalability="N/A",
    compliance="Data residency / tenancy.",
    risk="Cross-tenant journal lines.",
    fix_immediate="Scope account/cost_center querysets to company; validate on create.",
    fix_short="CompanyScopedPrimaryKeyRelatedField helper.",
    fix_long="DB CHECK or composite FK.",
    effort="0.5-1d",
    tests="Foreign account PK → 400; tenant isolation test.",
    acceptance="Journal lines cannot reference other companies' accounts.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="ValDtls Discount can double-count BEFORE_TAX invoice discount",
    category="GST",
    subcategory="e-Invoice",
    severity="High",
    priority="P1",
    module="Sales",
    feature="e-Invoice payload",
    files="backend/sales/einvoice_payload.py",
    problem="AssVal is net of BEFORE_TAX discount; ValDtls.Discount still set to full invoice_discount — breaks NIC TotInvVal identity.",
    evidence="einvoice_payload.py L200-210 Discount=_num(invoice.invoice_discount)",
    root_cause="ValDtls added without discount-timing semantics.",
    business="IRP rejection or wrong invoice values.",
    technical="Payload math inconsistency.",
    customer="Cannot generate IRN.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="e-Invoice schema value identity.",
    risk="Live IRP failures.",
    fix_immediate="Only AFTER_TAX residual in Discount; or NIC-prescribed components.",
    fix_short="Golden fixtures for BEFORE/AFTER tax.",
    fix_long="Formal invoice value decomposition model.",
    effort="1d",
    tests="BEFORE_TAX discount: AssVal+tax+RndOff=TotInvVal; Discount residual only.",
    acceptance="NIC value identity holds for both discount timings.",
    status="Open",
    refs="BB-000012 residual; Wave9",
)
add(
    title="FE tax preview understates GST when assumeLocalStateForBlankParty is on",
    category="GST",
    subcategory="Tax preview",
    severity="High",
    priority="P0",
    module="Web",
    feature="Invoice editor",
    files="web/src/pages/sales/NewInvoicePage.tsx; web/src/utils/tax.ts; backend/core/services/billing.py",
    problem="Complete unlocked via assumeLocalStateForBlankParty, but isIntraState still null for blank party → client tax=0. Backend is_intra_state returns True when party state blank → CGST/SGST on complete.",
    evidence="NewInvoicePage posKnown uses assumeLocal; tax.ts null→taxTotal 0; billing.py blank party → True",
    root_cause="FE/BE POS semantics diverge for blank party.",
    business="Counter shows understated total; complete suddenly adds GST.",
    technical="Preview≠server tax.",
    customer="Trust damage; billing disputes.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="User may think NON-GST when tax applied.",
    risk="Wrong cash collection at counter.",
    fix_immediate="When assume-local on, FE treat blank party as intra (match BE).",
    fix_short="Server tax-preview endpoint as source of truth.",
    fix_long="Remove client tax math.",
    effort="0.5-1d",
    tests="assumeLocal + blank party → FE CGST/SGST matches BE.",
    acceptance="Preview tax equals complete tax for blank party.",
    status="Open",
    refs="BB-000232 incomplete; Wave9 NEW",
)
add(
    title="GSTR-3B omits RCM ITC from available_from_purchases",
    category="GST",
    subcategory="GSTR-3B",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="GSTR-3B",
    files="backend/reporting/gst_returns.py",
    problem="RCM liability shown under reverse_charge; ITC block only sums non-RCM purchase taxes while books post Dr Input ITC for RCM.",
    evidence="gst_returns.py L526-558 non-RCM only for available_from_purchases",
    root_cause="3B aid not updated after RCM GL fix.",
    business="CA understates provisional ITC vs books.",
    technical="3B/GL disagreement.",
    customer="Wrong 3B worksheet.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Provisional ITC incomplete.",
    risk="Wrong self-assessment aids.",
    fix_immediate="Add RCM ITC section (still provisional until 2B).",
    fix_short="Align 3B blocks with PostingService RCM.",
    fix_long="Full 3B table mapping.",
    effort="1d",
    tests="RCM purchase appears in liability and provisional ITC.",
    acceptance="3B RCM ITC matches books provisional.",
    status="Open",
    refs="BB-000010 residual; Wave9",
)
add(
    title="FIFO company setting does not drive sale COGS (unit_cost avg remaining)",
    category="Inventory",
    subcategory="Valuation",
    severity="High",
    priority="P1",
    module="Inventory",
    feature="COGS",
    files="backend/inventory/services.py; sales/services.py",
    problem="inventory_valuation_method=FIFO advertised; sale COGS uses unit_cost()=remaining value/qty not issue-layer FIFO.",
    evidence="InventoryValuationService docstring admits partial; sales complete uses unit_cost",
    root_cause="FIFO layers not consumed on issue.",
    business="Wrong COGS/GP when FIFO selected.",
    technical="Setting lied.",
    customer="Margin reports wrong.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Inventory valuation misstatement.",
    risk="Material P&L error.",
    fix_immediate="Hide FIFO until done OR implement issue-cost from layers.",
    fix_short="FIFO issue API.",
    fix_long="Full layer ledger.",
    effort="3-5d",
    tests="FIFO purchase layers → sale COGS matches oldest layer.",
    acceptance="FIFO setting changes COGS vs weighted avg.",
    status="Open",
    refs="BB-000062 residual; Wave9",
)
add(
    title="Purchase return + purchase CN can double-count AP relief",
    category="Accounting",
    subcategory="Ledgers",
    severity="High",
    priority="P1",
    module="Purchases",
    feature="Outstanding",
    files="backend/ledgers/services.py",
    problem="Both returns and credit_notes subtract from purchase outstanding; no mutual exclusion like sales return↔CN.",
    evidence="ledgers/services.py purchase_invoice_outstanding returns - CNs + DNs",
    root_cause="Sales BB-000043 not mirrored.",
    business="Negative supplier outstanding; overstated AP relief.",
    technical="Double relief.",
    customer="Wrong supplier balance.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="AP understated.",
    risk="Payment overpay risk.",
    fix_immediate="Auto-CN path + exclude returns OR block CN when return exists.",
    fix_short="Sales-parity model.",
    fix_long="Single relief document type.",
    effort="1-2d",
    tests="Return+CN same invoice cannot both relieve full amount.",
    acceptance="No double AP relief.",
    status="Open",
    refs="BB-000043 purchase; Wave9",
)
add(
    title="WhatsApp notifications marked SENT for wa.me links (no delivery)",
    category="Integration",
    subcategory="WhatsApp",
    severity="High",
    priority="P1",
    module="Core",
    feature="Notifications",
    files="backend/core/services/notifications.py",
    problem="WHATSAPP channel builds wa.me link and sets status=SENT; IntegrationConnection.WHATSAPP unused.",
    evidence="notifications.py L40-44 status SENT",
    root_cause="Link share mislabeled as delivery.",
    business="Ops believe WhatsApp delivered.",
    technical="False status.",
    customer="Missed messages.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Honesty / audit trail.",
    risk="Support and compliance false greens.",
    fix_immediate="Status LINK_READY; never SENT without API ack.",
    fix_short="Wire WA Business API or remove claim.",
    fix_long="Full WA Cloud API.",
    effort="1d honesty / 10d+ API",
    tests="WhatsApp notify → LINK_READY not SENT.",
    acceptance="SENT only after provider delivery receipt.",
    status="Open",
    refs="BB-000026 residual honesty; Wave9",
)
add(
    title="Idempotency-Key BE sales-only; FE never sends header",
    category="API",
    subcategory="Idempotency",
    severity="High",
    priority="P1",
    module="Web",
    feature="Creates",
    files="web/src/api/resources.ts; backend/sales/views.py",
    problem="BE implements Idempotency-Key only on sales invoice create; FE createSalesInvoice posts without header; purchases/payments have none.",
    evidence="No Idempotency-Key in FE client posts",
    root_cause="Partial BB-000189 implementation.",
    business="Double-submit duplicates money docs.",
    technical="Idempotency unused.",
    customer="Duplicate invoices/payments.",
    security="N/A",
    performance="N/A",
    scalability="Retry storms amplify duplicates.",
    compliance="Financial integrity.",
    risk="Duplicate AR/cash.",
    fix_immediate="FE UUID header on creates; extend BE to purchases/payments.",
    fix_short="Client interceptor for mutating POSTs.",
    fix_long="Idempotency middleware for all money APIs.",
    effort="2-3d",
    tests="Same key twice → one invoice; FE sends header.",
    acceptance="Double-click create cannot duplicate.",
    status="Open",
    refs="BB-000189 residual; Wave9",
)
add(
    title="CD pushes GHCR :latest with no CI/CodeQL/e2e gate",
    category="DevOps",
    subcategory="CD",
    severity="High",
    priority="P1",
    module="CI",
    feature="cd.yml",
    files=".github/workflows/cd.yml",
    problem="CD on main builds/pushes API+Web :latest without workflow_run/needs on CI, CodeQL, or e2e-golden; no digest pinning.",
    evidence="cd.yml independent of ci.yml success",
    root_cause="CD added without promotion gates.",
    business="Broken main can ship.",
    technical="Unsafe continuous deploy.",
    customer="Prod regressions.",
    security="Vulnerable images may push.",
    performance="N/A",
    scalability="N/A",
    compliance="Change control.",
    risk="Ship failing tests.",
    fix_immediate="Gate CD on green CI+golden; pin digests.",
    fix_short="Environment promotion workflow.",
    fix_long="GitOps with signed artifacts.",
    effort="1d",
    tests="CI fail → CD skipped (workflow_run).",
    acceptance="CD never runs without CI green.",
    status="Open",
    refs="BB-000219 residual; Wave9 NEW",
)
add(
    title="GSTIN verify provider always Null — never live VALID (Resolved claim false)",
    category="GST",
    subcategory="GSTIN",
    severity="High",
    priority="P1",
    module="Core",
    feature="GSTIN verify",
    files="backend/core/services/gstin_verify.py",
    problem="get_gstin_provider always returns NullGstinProvider regardless of config name.",
    evidence="gstin_verify.py L53-60 always NullGstinProvider()",
    root_cause="BB-000225 marked Resolved without live provider.",
    business="gstin.verified audit misleading.",
    technical="Dead feature.",
    customer="False verification confidence.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTIN KYC theater.",
    risk="Onboarding with invalid GSTINs.",
    fix_immediate="Real provider branch OR never set gstin_verified_at / rename action.",
    fix_short="GSP GSTIN search adapter.",
    fix_long="Cached portal verification.",
    effort="3-5d",
    tests="Configured provider returns VALID/INVALID; null never stamps verified.",
    acceptance="VALID only from live provider response.",
    status="Open",
    refs="BB-000225 falsely Resolved; Wave9",
)

# ─── MEDIUM ─────────────────────────────────────────────────────────────────
add(
    title="eway_enabled and gsp_provider still client-writable on CompanySerializer",
    category="GST",
    subcategory="Config",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="Company settings",
    files="backend/accounts/serializers.py",
    problem="read_only locked einvoice/aato/accounting but not eway_enabled or gsp_provider.",
    evidence="read_only_fields L85-90 omit eway_enabled/gsp_provider; fields L75-76 include them",
    root_cause="BB-000215 incomplete.",
    business="Staff can enable e-Way / change GSP without controls.",
    technical="Config bypass.",
    customer="Unexpected statutory features.",
    security="Medium privilege.",
    performance="N/A",
    scalability="N/A",
    compliance="Enablement without Owner.",
    risk="Sandbox e-Way in wrong env.",
    fix_immediate="read_only or Owner-only write API.",
    fix_short="Staff settings service.",
    fix_long="Feature flag service.",
    effort="0.5d",
    tests="PATCH eway_enabled as staff → rejected.",
    acceptance="eway_enabled/gsp_provider not mass-assignable.",
    status="Open",
    refs="BB-000215 residual; Wave9",
)
add(
    title="E-invoice RegRev/SupTyp still hard-coded B2B/N",
    category="GST",
    subcategory="e-Invoice",
    severity="Medium",
    priority="P2",
    module="Sales",
    feature="e-Invoice",
    files="backend/sales/einvoice_payload.py",
    problem="TranDtls SupTyp=B2B and RegRev=N hard-coded.",
    evidence="einvoice_payload.py L166-174",
    root_cause="BB-000056 partial (UQC fixed only).",
    business="SEZ/export/RCM supplies mis-typed.",
    technical="Wrong IRP classification.",
    customer="IRP rejection.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Supply type incorrect.",
    risk="Wrong e-invoice taxonomy.",
    fix_immediate="Derive from invoice/company flags.",
    fix_short="SupplyType enum on invoice.",
    fix_long="Full export/SEZ model.",
    effort="1-2d",
    tests="RCM/SEZ fixtures set RegRev/SupTyp correctly.",
    acceptance="No hard-coded B2B/N for all invoices.",
    status="Open",
    refs="BB-000056 residual; Wave9",
)
add(
    title="Outstanding can still go negative — no floor (BB-000097 falsely Resolved)",
    category="Accounting",
    subcategory="Ledgers",
    severity="Medium",
    priority="P2",
    module="Ledgers",
    feature="Outstanding",
    files="backend/ledgers/services.py",
    problem="customer_outstanding / sales_invoice_outstanding return raw arithmetic without max(0,…).",
    evidence="ledgers/services.py raw subtraction",
    root_cause="Fix claimed without floor.",
    business="Negative AR/AP after over-allocation/double relief.",
    technical="Display/API nonsense balances.",
    customer="Confusion; over-collection risk.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="AR aging wrong.",
    risk="Payment allocation bugs compound.",
    fix_immediate="Floor display + harden allocation/CN caps.",
    fix_short="Invariant tests.",
    fix_long="Ledger event sourcing.",
    effort="1d",
    tests="Over-allocate → outstanding 0 not negative.",
    acceptance="Outstanding never negative.",
    status="Open",
    refs="BB-000097 falsely Resolved; Wave9",
)
add(
    title="Statement date filter drops opening balance (BB-000098 falsely Resolved)",
    category="Accounting",
    subcategory="Statements",
    severity="Medium",
    priority="P2",
    module="Ledgers",
    feature="Statements",
    files="backend/ledgers/services.py",
    problem="date_from filters entries then balance starts at 0 — no brought-forward.",
    evidence="ledgers/services.py L224-232",
    root_cause="Fix claimed without opening calc.",
    business="Period statements start at 0.",
    technical="Wrong statement math.",
    customer="Unusable statements for CAs.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Statement incorrect.",
    risk="Customer disputes.",
    fix_immediate="Compute opening from pre-date_from docs.",
    fix_short="Opening row in API.",
    fix_long="Running balance table.",
    effort="1d",
    tests="date_from mid-year → opening = prior activity.",
    acceptance="Statements include brought-forward.",
    status="Open",
    refs="BB-000098 falsely Resolved; Wave9",
)
add(
    title="Register email enumeration via 200 vs 201 body shape",
    category="Security",
    subcategory="Auth",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="Register",
    files="backend/accounts/views.py RegisterView",
    problem="Existing email → 200 + detail no tokens; new → 201 + tokens. FE branches on access.",
    evidence="RegisterView status/body diverge",
    root_cause="BB-000251 incomplete anti-enum.",
    business="Account existence oracle.",
    technical="Privacy leak.",
    customer="Email harvesting.",
    security="Medium enumeration.",
    performance="N/A",
    scalability="N/A",
    compliance="Privacy.",
    risk="Targeted phishing lists.",
    fix_immediate="Always 200/202 identical body; async magic link.",
    fix_short="Uniform response timing.",
    fix_long="Invite-only registration.",
    effort="1d",
    tests="Existing/new email indistinguishable responses.",
    acceptance="No status/body oracle.",
    status="Open",
    refs="BB-000251 residual; Wave9",
)
add(
    title="Login lockout counter non-atomic cache get/set race",
    category="Security",
    subcategory="Brute force",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="Login",
    files="backend/accounts/views.py LoginView",
    problem="cache.get then cache.set(fail_key, get+1) race under parallel workers bypasses LOGIN_FAIL_LIMIT.",
    evidence="LoginView L137-143 non-atomic increment",
    root_cause="Redis present but INCR not used.",
    business="Distributed brute force exceeds lockout.",
    technical="Race.",
    customer="Account compromise risk.",
    security="Medium.",
    performance="N/A",
    scalability="Worse under multi-worker.",
    compliance="Auth controls.",
    risk="Credential stuffing success.",
    fix_immediate="Redis INCR + TTL.",
    fix_short="django-axes or equivalent.",
    fix_long="WAF + anomaly detection.",
    effort="0.5d",
    tests="Parallel 20 fails → locked.",
    acceptance="Atomic lockout under concurrency.",
    status="Open",
    refs="BB-000250 related; Wave9 NEW",
)
add(
    title="_public_frontend_base_url trusts Origin/Referer when FRONTEND_URL unset",
    category="Security",
    subcategory="Open redirect",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Payment links",
    files="backend/payments/views.py",
    problem="When FRONTEND_URL unset, Origin/Referer used as callback/share base.",
    evidence="views.py L62-77",
    root_cause="Dev convenience.",
    business="Phishing via poisoned callback_url.",
    technical="Open redirect / host injection.",
    customer="Pay redirects to attacker.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Payment redirect integrity.",
    risk="Credential/payment phishing.",
    fix_immediate="Require FRONTEND_URL in staging/prod; never trust Origin.",
    fix_short="Allowlist hosts.",
    fix_long="Signed callback tokens.",
    effort="0.5d",
    tests="Unset FRONTEND_URL in staging → fail; Origin ignored.",
    acceptance="Callbacks only to configured FRONTEND_URL.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Accounting XLSX export lacks CanExport",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="Exports",
    files="backend/accounting/views.py AccountingReportView",
    problem="format=xlsx export does not require CanExport — viewers with reports flag can bulk-export books.",
    evidence="_report_response xlsx path",
    root_cause="Export capability not applied.",
    business="Unauthorized bulk books export.",
    technical="RBAC gap.",
    customer="Data exfil by viewers.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Export control.",
    risk="PII/financial dump.",
    fix_immediate="Require CanExport for xlsx.",
    fix_short="Audit all export endpoints.",
    fix_long="Export audit log.",
    effort="0.5d",
    tests="can_export=false → 403 on xlsx.",
    acceptance="XLSX requires can_export.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Health liveness 200 when Celery workers down (compose uses /health/)",
    category="DevOps",
    subcategory="Health",
    severity="Medium",
    priority="P2",
    module="Core",
    feature="Health",
    files="backend/core/views.py HealthView; docker-compose.yml",
    problem="celery_ok via inspect.ping but HTTP 503 only when ?ready=1; compose healthcheck hits /health/ without ready.",
    evidence="HealthView default 200 if DB up; compose healthcheck path",
    root_cause="BB-000218 partial.",
    business="Orchestrators route to apps with dead async (PDF/insights).",
    technical="False healthy.",
    customer="Silent PDF/share failures.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Ops SLA.",
    risk="Degraded mode undetected.",
    fix_immediate="Separate /live and /ready; compose uses ready.",
    fix_short="Worker heartbeat required for ready.",
    fix_long="Full dependency mesh health.",
    effort="0.5d",
    tests="No workers → ready 503; live 200.",
    acceptance="Compose fails unhealthy without workers.",
    status="Open",
    refs="BB-000218 residual; Wave9",
)
add(
    title="Public pay link still exposes company/invoice/amount/UPI metadata",
    category="Security",
    subcategory="Privacy",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Public pay",
    files="backend/payments/views.py public_payment_link",
    problem="Customer name removed but company_name, invoice_number, amount, upi still returned unauthenticated.",
    evidence="public_payment_link response fields",
    root_cause="BB-000238 partial.",
    business="Token leak discloses commercial metadata.",
    technical="Over-sharing.",
    customer="Privacy concern.",
    security="Medium info disclosure.",
    performance="N/A",
    scalability="N/A",
    compliance="Minimization.",
    risk="Invoice phishing targeting.",
    fix_immediate="Minimal fields until pay initiated.",
    fix_short="Tokenized display.",
    fix_long="Short-lived pay session.",
    effort="1d",
    tests="Unauth GET returns minimal fields only.",
    acceptance="No invoice number until authenticated pay step.",
    status="Open",
    refs="BB-000238 residual; Wave9",
)
add(
    title="Staging secure cookies omitted unless USE_TLS=1 (BB-000235 residual)",
    category="Security",
    subcategory="Cookies",
    severity="Medium",
    priority="P2",
    module="Config",
    feature="Cookies",
    files="backend/config/settings.py",
    problem="Secure cookies when USE_TLS==1 or DJANGO_ENV==production — staging omitted.",
    evidence="settings.py L333-340",
    root_cause="Staging not in secure branch.",
    business="Refresh cookie over HTTP on staging.",
    technical="Cookie theft risk.",
    customer="Session hijack on staging hosts.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Transport security.",
    risk="Staging compromise → prod patterns.",
    fix_immediate="Include staging in secure-cookie branch.",
    fix_short="Force HTTPS middleware on staging.",
    fix_long="HSTS everywhere non-local.",
    effort="0.5d",
    tests="DJANGO_ENV=staging → SECURE_COOKIE true.",
    acceptance="Staging refresh cookie Secure.",
    status="Open",
    refs="BB-000235 residual; Wave9",
)
add(
    title="RoleRoute gaps on list/detail sales/purchase/inventory read surfaces",
    category="Security",
    subcategory="Frontend RBAC",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="Routes",
    files="web/src/App.tsx",
    problem="Mutate paths gated; list/detail for history, customers, notes lists, purchase history, inventory stock still ungated — VIEWER opens full UIs.",
    evidence="App.tsx ungated authenticated routes for list/detail",
    root_cause="BB-000210 mutate-only fix.",
    business="VIEWER sees full document UIs; BE HasCompany often only backstop.",
    technical="UI RBAC incomplete.",
    customer="Over-exposure of commercial data.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Least privilege UX.",
    risk="Data browsing by low-privilege users.",
    fix_immediate="Capability gates on read surfaces.",
    fix_short="Explicit can_view_sales flags.",
    fix_long="Route policy table.",
    effort="1-2d",
    tests="VIEWER cannot open sales/history.",
    acceptance="List/detail respect capabilities.",
    status="Open",
    refs="BB-000210 residual; Wave9",
)
add(
    title="fetchAllPages still used on Receipts/Quotations/Returns/Orders/ledgers",
    category="Performance",
    subcategory="Pagination",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="Data loading",
    files="web/src/api/resources.ts; multiple pages",
    problem="Invoice customer picker fixed; many editors still listCustomers/listProducts/listSalesInvoices via fetchAllPages (50-page cap throws).",
    evidence="resources.ts fetchAllPages callers outside NewInvoicePage",
    root_cause="BB-000246 partial.",
    business="Large tenants fail or OOM in editors.",
    technical="Client fan-out.",
    customer="Broken UX at scale.",
    security="N/A",
    performance="High memory/network.",
    scalability="Fails beyond ~few thousand rows.",
    compliance="N/A",
    risk="Pilot scale failure.",
    fix_immediate="Server search + paginated pickers everywhere.",
    fix_short="Ban fetchAllPages in pages.",
    fix_long="Virtualized infinite queries.",
    effort="3-5d",
    tests="No fetchAllPages in money editors.",
    acceptance="Editors work with >5k masters.",
    status="Open",
    refs="BB-000245/246 residual; Wave9",
)
add(
    title="Cross-tab auth restores stale localStorage user without /auth/me",
    category="Security",
    subcategory="Auth",
    severity="Medium",
    priority="P2",
    module="Web",
    feature="AuthContext",
    files="web/src/auth/AuthContext.tsx",
    problem="Boot waits for /auth/me; storage event path setUser(getStoredUser()) without revalidation.",
    evidence="AuthContext.tsx L128-137",
    root_cause="BB-000228 boot-only fix.",
    business="Stale capabilities after role change.",
    technical="Auth drift.",
    customer="Wrong permissions UI.",
    security="Medium privilege stale.",
    performance="N/A",
    scalability="N/A",
    compliance="RBAC freshness.",
    risk="Acting on revoked privileges in UI.",
    fix_immediate="Re-run fetchCurrentUser on storage restore.",
    fix_short="BroadcastChannel auth sync.",
    fix_long="Short-lived capability tokens.",
    effort="0.5d",
    tests="Role change other tab → this tab refreshes me.",
    acceptance="Storage restore always hits /auth/me.",
    status="Open",
    refs="BB-000228 residual; Wave9",
)
add(
    title="Customer Autocomplete capped at 50 with no load-more",
    category="UX",
    subcategory="Pickers",
    severity="Medium",
    priority="P2",
    module="Web",
    feature="Invoice editor",
    files="web/src/pages/sales/NewInvoicePage.tsx",
    problem="listCustomersPage pageSize 50; empty q returns first 50 ACTIVE only.",
    evidence="NewInvoicePage.tsx L179-181",
    root_cause="Pagination without search UX.",
    business="Customers beyond first 50 invisible without search.",
    technical="Silent truncation.",
    customer="Cannot find customers.",
    security="N/A",
    performance="N/A",
    scalability="Wrong at >50 customers.",
    compliance="N/A",
    risk="Wrong party invoiced / missed sales.",
    fix_immediate="Require search ≥2 chars or infinite scroll.",
    fix_short="Shared AsyncAutocomplete.",
    fix_long="Global party search.",
    effort="0.5-1d",
    tests="51st customer reachable via search.",
    acceptance="No silent 50-cap without affordance.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="reserve_stock first-row race lacks IntegrityError handler",
    category="Concurrency",
    subcategory="Inventory",
    severity="Medium",
    priority="P2",
    module="Inventory",
    feature="Reservations",
    files="backend/inventory/services.py reserve_stock",
    problem="post_movement handles concurrent get_or_create IntegrityError; reserve_stock does not.",
    evidence="inventory/services.py reserve_stock L156-158 vs post_movement handler",
    root_cause="Pattern not copied.",
    business="Concurrent SO confirms can 500 / lose reservation.",
    technical="Race.",
    customer="Order confirm failures.",
    security="N/A",
    performance="N/A",
    scalability="Worse under concurrency.",
    compliance="N/A",
    risk="Lost reservations.",
    fix_immediate="Same IntegrityError retry as movements.",
    fix_short="Shared balance ensure helper.",
    fix_long="Single stock mutex service.",
    effort="0.5d",
    tests="Parallel reserve on new SKU succeeds.",
    acceptance="No 500 on first concurrent reserve.",
    status="Open",
    refs="BB-000236 pattern; Wave9",
)
add(
    title="rebuild_balance resets on_hand but not reserved",
    category="Inventory",
    subcategory="Balances",
    severity="Medium",
    priority="P2",
    module="Inventory",
    feature="Rebuild",
    files="backend/inventory/services.py rebuild_balance",
    problem="balance.on_hand=total saved; reserved untouched.",
    evidence="inventory/services.py L198-204",
    root_cause="Incomplete rebuild.",
    business="Reserved can exceed on_hand after rebuild.",
    technical="Invariant break.",
    customer="Phantom stock blocks.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Wrong available qty.",
    fix_immediate="Recompute reserved from open SO or zero with warning.",
    fix_short="Rebuild reports drift.",
    fix_long="Derived reserved view.",
    effort="1d",
    tests="Rebuild → reserved consistent with open reservations.",
    acceptance="After rebuild available=on_hand-reserved ≥0.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Sales debit notes capped vs invoice total not outstanding (stackable)",
    category="Business Logic",
    subcategory="Notes",
    severity="Medium",
    priority="P2",
    module="Sales",
    feature="Debit notes",
    files="backend/sales/notes_services.py",
    problem="DN grand_total > inv.grand_total check only; multiple DNs each ≤ total can stack AR inflation. CN uses outstanding.",
    evidence="notes_services.py L217-220",
    root_cause="Asymmetric caps.",
    business="Stacked DNs inflate AR beyond invoice.",
    technical="Missing cumulative cap.",
    customer="Wrong AR.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Invoice value identity.",
    risk="Fraudulent AR inflation.",
    fix_immediate="Cap DN by remaining headroom policy.",
    fix_short="Shared note cap helper.",
    fix_long="Invoice balance sheet.",
    effort="0.5-1d",
    tests="Second DN exceeding headroom rejected.",
    acceptance="Cumulative DNs cannot exceed policy cap.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="mark-einvoice-generated lacks Owner + einvoice_enabled gates",
    category="GST",
    subcategory="Honesty",
    severity="Medium",
    priority="P2",
    module="Sales",
    feature="e-Invoice",
    files="backend/sales/einvoice_eway_actions.py",
    problem="Submit requires Owner+enabled; mark does not.",
    evidence="einvoice_eway_actions.py mark path L133-171",
    root_cause="Honesty partial.",
    business="Any member can attest IRN.",
    technical="Authz gap.",
    customer="False IRN attestations.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="False statutory attestation.",
    risk="Audit failure.",
    fix_immediate="Same gates as submit.",
    fix_short="Shared require_einvoice_action.",
    fix_long="Attestation audit trail.",
    effort="0.5d",
    tests="Staff mark → 403; disabled → 403.",
    acceptance="Mark requires Owner + einvoice_enabled.",
    status="Open",
    refs="BB-000214 residual; Wave9",
)
add(
    title="web/nginx.conf static location drops inherited security headers",
    category="Security",
    subcategory="Headers",
    severity="Medium",
    priority="P2",
    module="Web",
    feature="nginx",
    files="web/nginx.conf",
    problem="location for static assets add_header Cache-Control only — nginx clears inherited CSP/XFO/nosniff on that location.",
    evidence="web/nginx.conf L16-19",
    root_cause="BB-000252 incomplete for asset location.",
    business="Assets without CSP/XFO.",
    technical="Header inheritance footgun.",
    customer="Weaker XSS mitigation on assets.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Security headers baseline.",
    risk="XSS via mis-served asset context.",
    fix_immediate="Repeat security headers in every location.",
    fix_short="Shared nginx snippet include.",
    fix_long="Edge-only headers.",
    effort="0.5d",
    tests="curl asset has CSP/XFO.",
    acceptance="All locations emit security headers.",
    status="Open",
    refs="BB-000252 residual; Wave9",
)
add(
    title="Invite creates users with password in API body (no invite token)",
    category="Security",
    subcategory="Auth",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="Company users",
    files="backend/accounts/views.py CompanyUserViewSet.create",
    problem="Invite creates users with password in request body; no email verify / invite token.",
    evidence="CompanyUserViewSet.create password in payload",
    root_cause="MVP invite shortcut.",
    business="Passwords in logs/proxies; no verify.",
    technical="Weak onboarding.",
    customer="Account security risk.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Auth hygiene.",
    risk="Credential leakage.",
    fix_immediate="Invite token + set-password flow.",
    fix_short="Email invite only.",
    fix_long="SSO/OIDC.",
    effort="2-3d",
    tests="Create user without password; set via token.",
    acceptance="No password in invite API body.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Razorpay webhook_secret silently falls back to key_secret",
    category="Security",
    subcategory="Payments",
    severity="Medium",
    priority="P2",
    module="Payments",
    feature="Razorpay",
    files="backend/payments/gateway.py RazorpayAdapter",
    problem="webhook_secret falls back to key_secret if missing.",
    evidence="RazorpayAdapter.__init__ webhook_secret or key_secret",
    root_cause="Convenience default.",
    business="Wrong secret type; rotation confusion.",
    technical="Weaker ops hygiene.",
    customer="Misconfigured webhooks.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="Secret separation.",
    risk="Using API secret as webhook secret.",
    fix_immediate="Require dedicated webhook_secret; fail closed if missing.",
    fix_short="Settings UI validation.",
    fix_long="Secret manager.",
    effort="0.5d",
    tests="Missing webhook_secret → adapter init error.",
    acceptance="No key_secret fallback for webhooks.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Env example drift: root .env.example missing SMS/JWT/OTP/ADMIN/AI/GSP keys",
    category="Configuration",
    subcategory="Env",
    severity="Medium",
    priority="P2",
    module="Docs",
    feature="Env templates",
    files=".env.example; .env.production.example; web/.env.example",
    problem="Root .env.example lacks SMS_PROVIDER, JWT_*, OTP_DEBUG_ECHO, ADMIN_ENABLED, AI_*, GSP live flags present in production template; VITE flags only in web/.env.example.",
    evidence="Diff across env templates",
    root_cause="Templates diverge after Wave 6.",
    business="Easy misconfigure of pilot/prod.",
    technical="Config drift.",
    customer="Broken/auth-open deploys.",
    security="Medium misconfig.",
    performance="N/A",
    scalability="N/A",
    compliance="Deploy checklist.",
    risk="Insecure defaults in 'dev' on public hosts.",
    fix_immediate="Single matrix doc + mirrored keys with comments.",
    fix_short="CI check env parity.",
    fix_long="Generated env from schema.",
    effort="0.5-1d",
    tests="Script asserts key sets.",
    acceptance="All runtime keys documented in examples.",
    status="Open",
    refs="BB-000247 residual; Wave9",
)
add(
    title="AI assistant: prompt injection + 800-char tool truncation + budget race",
    category="AI",
    subcategory="Assistant",
    severity="Medium",
    priority="P2",
    module="Insights",
    feature="Assistant",
    files="backend/insights/assistant.py",
    problem="Raw user content to LLM; tool JSON truncated to 800 chars; budget assert before turn / usage after → concurrent overshoot.",
    evidence="assistant.py truncation and budget timing",
    root_cause="BB-000070/237 partial.",
    business="Wrong money figures; budget overrun; injection.",
    technical="Unsafe LLM loop.",
    customer="Bad advice from truncated tools.",
    security="Medium injection.",
    performance="N/A",
    scalability="Budget race under concurrency.",
    compliance="AI honesty.",
    risk="Incorrect financial guidance.",
    fix_immediate="Higher structured envelopes; atomic budget reserve; stronger isolation.",
    fix_short="Allowlisted tools only with schemas.",
    fix_long="Separate retrieval vs generation.",
    effort="2-4d",
    tests="Concurrent turns cannot exceed budget; tools not truncated mid-number.",
    acceptance="Budget atomic; no money truncation.",
    status="Open",
    refs="BB-000070/237 residual; Wave9",
)
add(
    title="Light e2e still mock-only continue-on-error; FE unit coverage thin; no money contract tests",
    category="Testing",
    subcategory="Coverage",
    severity="Medium",
    priority="P1",
    module="Web",
    feature="CI",
    files="web/e2e; .github/workflows/ci.yml",
    problem="playwright --mode e2e mocks; e2e job continue-on-error; ~13 FE unit files vs ~178 sources; no FE↔BE money contract tests.",
    evidence="ci.yml e2e continue-on-error; test file counts",
    root_cause="BB-000221/191 partial (golden exists).",
    business="Regressions ship.",
    technical="False CI confidence.",
    customer="Broken UI in prod.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Quality gate.",
    risk="Money UI regressions.",
    fix_immediate="Fail CI on e2e; expand golden; contract smoke.",
    fix_short="RoleRoute/auth unit tests.",
    fix_long="Schemathesis + Playwright money pack.",
    effort="5-8d",
    tests="e2e failure fails merge.",
    acceptance="Mock e2e not continue-on-error; contract tests for money DTOs.",
    status="Open",
    refs="BB-000221/191 residual; Wave9",
)
add(
    title="GSTR-9 aid outward-only (no inward/ITC/tax paid)",
    category="GST",
    subcategory="GSTR-9",
    severity="Medium",
    priority="P2",
    module="Reporting",
    feature="GSTR-9",
    files="backend/reporting/gst_returns.py build_gstr9",
    problem="build_gstr9 sums monthly outward taxable/tax only.",
    evidence="gst_returns.py L645-713",
    root_cause="Aid scoped narrowly; BB-000049 Deferred but aid over-claims completeness in UI.",
    business="Insufficient annual CA pack.",
    technical="Incomplete aid.",
    customer="Cannot use for annual return prep.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="GSTR-9 tables missing.",
    risk="Misuse as annual return.",
    fix_immediate="Add inward/ITC/tax-paid summaries + disclaimers.",
    fix_short="Rename UI to 'outward FY aid'.",
    fix_long="Full GSTR-9 engine.",
    effort="2-3d",
    tests="GSTR-9 includes inward section or explicit outward-only flag.",
    acceptance="UI cannot be read as full GSTR-9.",
    status="Open",
    refs="BB-000049 related; Wave9",
)
add(
    title="PostingService has no service-layer RBAC (trusted-internal only undocumented)",
    category="Security",
    subcategory="RBAC",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="Posting",
    files="backend/accounting/services.py",
    problem="Any code path calling PostingService.post/reverse bypasses view Owner checks.",
    evidence="PostingService.post no actor role assert",
    root_cause="View-layer-only RBAC.",
    business="Future endpoints/scripts can post without authz.",
    technical="Defense in depth missing.",
    customer="Indirect books mutation risk.",
    security="Medium.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD.",
    risk="Internal API footguns.",
    fix_immediate="Document trusted-internal + audit; optional actor assert.",
    fix_short="require_can_post(actor) helper.",
    fix_long="Capability-aware domain services.",
    effort="1d",
    tests="Unauthorized actor helper raises.",
    acceptance="Service documents and optionally enforces actor.",
    status="Open",
    refs="BB-000200 related; Wave9",
)

# ─── LOW ────────────────────────────────────────────────────────────────────
add(
    title="OTP_PEPPER/Fernet still SECRET_KEY-derived outside prod/staging",
    category="Security",
    subcategory="Secrets",
    severity="Low",
    priority="P3",
    module="Core",
    feature="Secrets",
    files="backend/accounts/otp_utils.py; core/services/gsp_secrets.py",
    problem="Prod/staging fail-fast; development still derives from SECRET_KEY — accidental DJANGO_ENV=development on shared host reopens coupling.",
    evidence="otp_utils._pepper; gsp_secrets._fernet fallbacks",
    root_cause="Dev convenience.",
    business="Shared-host secret coupling.",
    technical="Key reuse.",
    customer="Indirect.",
    security="Low outside mis-env.",
    performance="N/A",
    scalability="N/A",
    compliance="Key hygiene.",
    risk="Mis-env production-like hosts.",
    fix_immediate="Warn loudly; ImproperlyConfigured when not DEBUG.",
    fix_short="Always require dedicated peppers.",
    fix_long="KMS.",
    effort="0.5d",
    tests="Non-DEBUG without OTP_PEPPER fails boot.",
    acceptance="No SECRET_KEY derivation when DEBUG false.",
    status="Open",
    refs="BB-000226/248 residual; Wave9",
)
add(
    title="Nginx CSP style-src unsafe-inline; compose env_file.required false",
    category="Security",
    subcategory="Deploy",
    severity="Low",
    priority="P3",
    module="DevOps",
    feature="nginx/compose",
    files="nginx/default.conf; docker-compose.yml",
    problem="CSP allows style-src 'unsafe-inline'; compose env_file required:false for api/worker/beat.",
    evidence="nginx CSP; compose env_file",
    root_cause="MUI inline styles + flexible compose.",
    business="Weaker XSS; services may start without .env inconsistently.",
    technical="Config softness.",
    customer="Indirect.",
    security="Low-Medium XSS surface.",
    performance="N/A",
    scalability="N/A",
    compliance="Hardening.",
    risk="XSS + misconfig.",
    fix_immediate="Tighten CSP; prod overlay required:true.",
    fix_short="Nonces for styles.",
    fix_long="Strict CSP + sealed secrets.",
    effort="1d",
    tests="Prod compose refuses missing env.",
    acceptance="Prod overlay requires env_file.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="Accounting settings route omits company.accountingEnabled gate nuance",
    category="UX",
    subcategory="RBAC",
    severity="Low",
    priority="P3",
    module="Web",
    feature="Routes",
    files="web/src/App.tsx",
    problem="allowAccounting requires accountingEnabled; allowAccountingSettings only feature flag + owner — intentional for enable but inconsistent mental model.",
    evidence="App.tsx allowAccountingSettings",
    root_cause="Enable-before-flag design.",
    business="Mild UX confusion.",
    technical="Inconsistent gates.",
    customer="Settings visible before books on.",
    security="Low.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Low.",
    fix_immediate="Document intent in UI copy.",
    fix_short="Wizard to enable accounting.",
    fix_long="Unified settings capability.",
    effort="0.25d",
    tests="Owner sees settings; non-owner does not.",
    acceptance="UI explains enable-before-use.",
    status="Open",
    refs="Wave9 NEW",
)
add(
    title="No CanPostJournals capability — Owner-or-nothing vs ACCOUNTANT role mismatch",
    category="Security",
    subcategory="RBAC design",
    severity="Medium",
    priority="P2",
    module="Accounting",
    feature="Capabilities",
    files="backend/core/permissions.py; accounting/views.py",
    problem="CanPostJournals does not exist; ACCOUNTANT may get can_create_payments/can_view_financial_reports but cannot post journals (Owner-only) while still mutating CoA via HasCompany.",
    evidence="No CanPostJournals in permissions.py",
    root_cause="Incomplete capability model after BB-000200.",
    business="Cannot grant accountant posting without Owner.",
    technical="Role/capability inconsistency.",
    customer="Ops friction.",
    security="Medium design flaw.",
    performance="N/A",
    scalability="N/A",
    compliance="SoD awkward.",
    risk="Over-grant Owner or under-grant accountants.",
    fix_immediate="Add CanPostJournals; grant ACCOUNTANT; remove HasCompany writes.",
    fix_short="Role preset matrix.",
    fix_long="Fine-grained accounting abilities.",
    effort="2d",
    tests="ACCOUNTANT with flag posts; without cannot; CoA locked.",
    acceptance="Accountant posting without full Owner.",
    status="Open",
    refs="BB-000200 design; Wave9",
)
add(
    title="Wave 6 Open==0 closure invalidated — residual Criticals remain (meta)",
    category="Process",
    subcategory="Audit integrity",
    severity="High",
    priority="P1",
    module="Product",
    feature="Register hygiene",
    files="docs/reviews/MASTER_ISSUE_REGISTER.md; CHANGELOG.md",
    problem="Waves 1–6 marked BB-000196–257 Resolved and Open=0; Wave 9 code re-verification found Critical payment/GL/return defects still present. Closure without failing adversarial tests for residual paths.",
    evidence="CHANGELOG Open-closure Waves 1–6 vs live gateway.py sandbox ok; notes_services DN no post; cancel_return orphan CN",
    root_cause="Resolved claimed on partial mitigations; tests missed residual paths.",
    business="False launch readiness signal.",
    technical="Process failure.",
    customer="Risk of shipping unsafe payments/books.",
    security="High process risk.",
    performance="N/A",
    scalability="N/A",
    compliance="Quality gate integrity.",
    risk="Repeat of BB-000254.",
    fix_immediate="Require failing-then-passing tests for every Critical Resolve; reopen false Resolves.",
    fix_short="Definition of Done includes adversarial residual checklist.",
    fix_long="Independent audit gate before status Open→0.",
    effort="1d process",
    tests="Wave9 script asserts Critical Opens exist until fixed.",
    acceptance="Open==0 only after re-audit pass with zero Critical/High residual.",
    status="Open",
    refs="BB-000254 related; Wave9 meta",
)

# Reopen falsely Resolved parents
RESIDUAL_REOPENS = {
    "BB-000196": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** Empty→sandbox blocked in production for named providers, but SandboxAdapter still accepts `X-Sandbox-Signature: ok`, non-prod remaps remain, and Company PATCH can re-enable test_mode. See **BB-000258**, **BB-000259**, **BB-000265**.
""",
    "BB-000200": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** Journals gated IsOwner, but CoA/periods/fixed-asset dispose/bank recon remain HasCompany. See **BB-000267**, **BB-000316**.
""",
    "BB-000225": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** `get_gstin_provider` still always returns `NullGstinProvider`. See **BB-000286**.
""",
    "BB-000257": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** Refresh cookie exists, but access JWT remains in localStorage and refresh is still returned/accepted in JSON body. See **BB-000266**.
""",
    "BB-000097": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** Outstanding still raw arithmetic without floor. See **BB-000289**.
""",
    "BB-000098": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** Statement date filter still drops opening balance. See **BB-000290**.
""",
    "BB-000043": """
### Re-audit (2026-08-03 Wave 9)
**Status → Reopened (Open).** Sales create blocks double CN, but cancel_return orphans auto CN; purchase return+CN double relief remains. See **BB-000260**, **BB-000282**.
""",
    "BB-000214": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** Manual IRN uses MANUAL_IRN, but e-Way mark still GENERATED without Owner/enabled; mark-einvoice lacks Owner gate. See **BB-000273**, **BB-000304**.
""",
    "BB-000215": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** einvoice/aato locked; eway_enabled and gsp_provider still writable. See **BB-000287**.
""",
    "BB-000218": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** inspect.ping exists but compose healthcheck uses /health/ without ready. See **BB-000295**.
""",
    "BB-000189": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** BE sales-only Idempotency-Key; FE never sends header. See **BB-000284**.
""",
    "BB-000210": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** Mutate RoleRoutes fixed; list/detail gaps remain. See **BB-000298**.
""",
    "BB-000251": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** Register still enumerable via 200 vs 201. See **BB-000291**.
""",
    "BB-000238": """
### Re-audit (2026-08-03 Wave 9)
**Residual Open.** Customer name removed; invoice/company/amount/UPI still public. See **BB-000296**.
""",
    "BB-000254": """
### Re-audit (2026-08-03 Wave 9)
**Reconfirmed.** Wave 6 Open==0 again process-failed. See **BB-000317**.
""",
}


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
| **References** | Wave 9 re-audit {TODAY}; code evidence |

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

### Risk if ignored
{d['risk']}

### Steps to reproduce
1. Inspect affected files listed above.
2. Exercise the related API/UI path with a pilot company fixture.
3. Observe the failure mode described in Problem Description.

### Recommended Fix
{d['fix_short']}

### Immediate Fix
{d['fix_immediate']}

### Short-term Fix
{d['fix_short']}

### Long-term Refactor
{d['fix_long']}

### Alternative Solutions
Defer behind feature flag; or remove UI claim until fixed.

### Required Tests
{d['tests']}

### Acceptance Criteria
{d['acceptance']}

---
"""


def reopen_parents(text: str) -> str:
    for iid, note in RESIDUAL_REOPENS.items():
        # Flip Resolved → Open in status table row (first occurrence in issue block)
        pattern = rf"(## {iid} —[\s\S]*?\|\s*\*\*Status\*\*\s*\|\s*)(?:Resolved|Open)(\s*\|)"
        text, _ = re.subn(pattern, r"\1Open\2", text, count=1)
        try:
            after_title = text.split(f"## {iid} —", 1)[1]
            block_only = after_title.split("## BB-", 1)[0]
        except IndexError:
            continue
        if f"Re-audit ({TODAY} Wave 9)" in block_only:
            continue
        parts = re.split(rf"(## {re.escape(iid)} —[^\n]*\n)", text, maxsplit=1)
        if len(parts) < 3:
            continue
        head, title, rest = parts[0], parts[1], parts[2]
        nxt = re.search(r"\n## BB-\d+", rest)
        if nxt:
            block, after = rest[: nxt.start()], rest[nxt.start() :]
        else:
            block, after = rest, ""
        if not block.endswith("\n"):
            block += "\n"
        text = head + title + block + note + after
    return text


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
    reopen_ids = set(RESIDUAL_REOPENS.keys())
    for item in all_issues:
        if item["id"] in reopen_ids:
            item["status"] = "Open"

    sev, pri, cat, mod, status = {}, {}, {}, {}, {}
    for item in all_issues:
        sev[item["severity"]] = sev.get(item["severity"], 0) + 1
        pri[item["priority"]] = pri.get(item["priority"], 0) + 1
        cat[item["category"]] = cat.get(item["category"], 0) + 1
        mod[item["module"]] = mod.get(item["module"], 0) + 1
        status[item["status"]] = status.get(item["status"], 0) + 1
    return {
        "total": len(all_issues),
        "severity": sev,
        "priority": pri,
        "category": cat,
        "module": mod,
        "status": status,
        "wave9_new": len(new_issues),
        "wave9_start": f"BB-{start_id:06d}",
        "wave9_end": f"BB-{start_id + len(new_issues) - 1:06d}",
        "audit_date": TODAY,
        "open_count": status.get("Open", 0),
        "issues": all_issues,
        "wave9_reopened": sorted(reopen_ids),
    }


def update_changelog(stats: dict) -> None:
    sev = {k: sum(1 for d in ISSUES if d["severity"] == k) for k in ("Critical", "High", "Medium", "Low")}
    entry = f"""# docs/reviews — CHANGELOG

## {TODAY} — Wave 9 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Waves 1–6 claimed Open==0.

### Outcomes

- Appended **{len(ISSUES)}** issues `{stats['wave9_start']}` … `{stats['wave9_end']}` (Critical {sev['Critical']} · High {sev['High']} · Medium {sev['Medium']} · Low {sev['Low']}).
- Reopened residual parents: {', '.join(f'`{x}`' for x in stats.get('wave9_reopened', []))}.
- Register total: **{stats['total']}**.
- Status: Open **{stats['status'].get('Open', 0)}** · other statuses retained for untouched IDs.
- Invalidated Wave 6 “Open == 0 / open-closure complete” as a launch gate (see BB-000317).
- Production Readiness Score revised **6.2 → 3.8**.

### Highest new Criticals

- BB-000258 Sandbox `X-Sandbox-Signature: ok` forgery
- BB-000259 Company PATCH bypasses gateway settings guards
- BB-000260 Cancel sales return orphans auto credit note
- BB-000261 Sales debit notes never post GL
- BB-000262 Purchase notes never post GL
- BB-000263 Purchase returns AP without GL/auto CN
- BB-000264 Spoofable `notes=TALLY_OPENING` credit-limit/GL bypass

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 9).

Script: `_wave9_reaudit_append.py` (append-only; IDs permanent).

---

"""
    if CHANGELOG.exists():
        old = CHANGELOG.read_text(encoding="utf-8")
        # strip leading title if present to avoid duplicate H1
        if old.startswith("# docs/reviews"):
            old = old.split("\n", 2)[-1] if old.count("\n") >= 2 else old
            # keep from first ## 
            idx = old.find("\n## ")
            if idx >= 0:
                old = old[idx + 1 :]
            elif old.startswith("## "):
                pass
            else:
                old = old.lstrip("\n")
        if f"Wave 9 independent re-audit" in old:
            print("CHANGELOG already has Wave 9 — skip prepend body duplicate")
            return
        CHANGELOG.write_text(entry + old, encoding="utf-8")
    else:
        CHANGELOG.write_text(entry, encoding="utf-8")


def append_exec_summary(stats: dict) -> None:
    if not EXEC.exists():
        return
    text = EXEC.read_text(encoding="utf-8")
    if "Wave 9 independent re-audit" in text:
        return
    block = f"""

---

## Wave 9 re-audit ({TODAY}) — SUPERSEDES Wave 6 “Open == 0”

Independent code re-verification **invalidated Waves 1–6 open-closure**. Partial payment/auth/RBAC remediations landed, but **sandbox webhook forgery, Company PATCH gateway bypass, orphan return CNs, missing note/return GL, and spoofable TALLY_OPENING** remain Critical. **{stats['wave9_new']} new issues** logged as `{stats['wave9_start']}` … `{stats['wave9_end']}`. Reopened: {', '.join(f'`{x}`' for x in stats.get('wave9_reopened', []))}.

### Updated verdict

| Audience | Deploy? |
|----------|---------|
| Internal dogfood (no public pay webhooks, accounting off) | **Conditional** |
| Paid pilot with live payment links / books | **No — until Wave 9 P0 Criticals closed** |
| GA / full ERP claims | **No** |

### Scores (0–10) — Wave 9

| Dimension | Score | Notes |
|-----------|------:|-------|
| Production Readiness | **3.8** | Payment forgery residuals + books GL holes |
| Architecture | **5.5** | Dual ledger + incomplete note/return lifecycle |
| Security | **3.0** | Sandbox ok signature; JWT access localStorage; RBAC holes |
| Performance | **4.5** | fetchAllPages residual across editors |
| Accounting Correctness | **3.5** | DN/purchase notes/returns missing GL; challan COGS skip |
| GST Compliance | **3.5** | B2CL ₹2.5L stale; e-Way float; live GSP Deferred |
| Maintainability | **5.0** | God modules unchanged |
| Scalability | **4.0** | Client fetch-all; no load proof |
| Testing Coverage | **5.0** | Adversarial gaps; FE thin; e2e continue-on-error |

### Register totals (cumulative)

| Metric | Count |
|--------|------:|
| **Total issues** | **{stats['total']}** |
| Critical | {stats['severity'].get('Critical', 0)} |
| High | {stats['severity'].get('High', 0)} |
| Medium | {stats['severity'].get('Medium', 0)} |
| Low | {stats['severity'].get('Low', 0)} |
| **Open** | **{stats['status'].get('Open', 0)}** |

### Wave 9 P0 blockers

1. **BB-000258** — Sandbox `X-Sandbox-Signature: ok`
2. **BB-000259** — Company PATCH bypasses gateway guards
3. **BB-000260** — Cancel return orphans auto CN
4. **BB-000261 / 262 / 263** — DN / purchase notes / purchase returns missing GL
5. **BB-000264** — Spoofable `TALLY_OPENING` notes
6. **BB-000266** — Access JWT still localStorage
7. **BB-000267** — Accounting RBAC incomplete beyond journals
8. **BB-000277** — FE tax preview vs assume-local mismatch

### Final CTO Verdict (Wave 9)

**Do not treat Wave 6 Open==0 as a quality gate.** Require adversarial residual tests before any Critical Resolve.

**Do not enable public payment webhooks** until BB-000258/259/265 closed.

**Do not enable accounting_enabled for pilot** until note/return GL parity (BB-000260–263, 270) closes.

**Do not commercially launch** as Cloud ERP with Manufacturing/Payroll/CRM/live GSP/WhatsApp Business claims.

"""
    EXEC.write_text(text.rstrip() + block + "\n", encoding="utf-8")


def update_roadmap(stats: dict) -> None:
    if not ROADMAP.exists():
        return
    text = ROADMAP.read_text(encoding="utf-8")
    if "Wave 9 hotfix" in text:
        return
    block = f"""

---

## Wave 9 hotfix track ({TODAY}) — P0 before any paid pilot

> Wave 6 Open==0 is **not** a launch gate. Open count now **{stats['status'].get('Open', 0)}** (`{stats['wave9_start']}`–`{stats['wave9_end']}` + reopened parents).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Sandbox/webhook forgery | BB-000258, BB-000259, BB-000265, BB-000269 | No forgeable settlement |
| Return/note GL parity | BB-000260–263, BB-000270, BB-000282 | Books consistent |
| TALLY_OPENING spoof | BB-000264 | Credit/GL integrity |
| Auth cookie completion | BB-000266 | No access in localStorage; no body refresh |
| Accounting RBAC | BB-000267–268, BB-000271, BB-000275, BB-000316 | Least privilege books |
| GST P1 | BB-000272–274, BB-000277–278, BB-000286 | Honest aids / B2CL ₹1L |
| FE/API | BB-000284, BB-000298–299 | Idempotency + RoleRoutes + pagination |

**Exit:** Conditional billing pilot **without** public sandbox webhooks and **without** accounting_enabled until GL parity green.

"""
    # Insert after title block
    if "## Scope C completed" in text:
        text = text.replace("## Scope C completed", block + "\n## Scope C completed", 1)
    else:
        text = text.rstrip() + block
    ROADMAP.write_text(text, encoding="utf-8")


def update_review_docs(stats: dict) -> None:
    """Append Wave 9 banner to each review doc (do not overwrite)."""
    banner = (
        f"\n\n---\n\n## Wave 9 re-audit ({TODAY})\n\n"
        f"Independent re-verification appended `{stats['wave9_start']}`…`{stats['wave9_end']}` "
        f"({stats['wave9_new']} issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. "
        f"Open count: **{stats['status'].get('Open', 0)}**. "
        f"Wave 6 Open==0 invalidated.\n"
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
        if f"Wave 9 re-audit ({TODAY})" in text:
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
    if len(existing) < 257:
        raise SystemExit(f"Expected ≥257 issues in _stats.json, got {len(existing)}")

    # Keep prior statuses from stats except reopen set
    text = reopen_parents(text)
    banner = (
        f"\n## Wave 9 re-audit ({TODAY})\n\n"
        f"Appended **{len(ISSUES)}** new issues "
        f"`BB-{START_ID:06d}` … `BB-{START_ID + len(ISSUES) - 1:06d}` "
        f"from independent code re-verification after Waves 1–6 open-closure. "
        f"Prior IDs unchanged. Reopened residuals listed under each parent. "
        f"**Invalidates Wave 6 Open==0 as a launch gate.**\n"
    )
    if f"Wave 9 re-audit ({TODAY})" not in text:
        text = text.replace("## How to use\n", "## How to use\n" + banner + "\n", 1)

    body = "".join(fmt_issue(START_ID + i, d) for i, d in enumerate(ISSUES))
    if not text.endswith("\n"):
        text += "\n"
    text = text + "\n# Wave 9 appended issues\n" + body
    stats = rebuild_stats(existing, ISSUES, START_ID)
    text = patch_register_totals(text, stats)
    # Update audit date line
    text = re.sub(
        r"\*\*Audit date:\*\*[^\n]*",
        f"**Audit date:** 2026-08-02 (Wave 9 re-audit {TODAY})",
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
    print("Reopened:", stats.get("wave9_reopened"))


if __name__ == "__main__":
    main()

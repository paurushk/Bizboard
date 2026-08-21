#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 14 independent re-audit (2026-08-04): append BB-000456+ after Wave 13 Open==0.

Never regenerates prior IDs. Append-only. IDs permanent.
Invalidates Wave 13 “Open == 0” as a commercial launch gate.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

TODAY = "2026-08-04"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
START_ID = 456

ISSUES: list[dict] = []


def add(**kwargs):
    ISSUES.append(kwargs)


# ─── CRITICAL ───────────────────────────────────────────────────────────────
add(
    title="Beat prod healthcheck float()-parses ISO heartbeat (always fails) + Redis key prefix mismatch",
    category="DevOps",
    subcategory="Observability",
    severity="Critical",
    priority="P0",
    module="DevOps",
    feature="Celery beat health",
    files="docker-compose.prod.yml; backend/core/tasks.py celery_beat_heartbeat; backend/core/views.py _probe_celery_beat_ok",
    problem="Wave 13 closed BB-000385 by replacing `or True` with an assert that does float(raw). Task writes timezone.now().isoformat() via Django cache. HealthView correctly parses ISO; compose healthcheck ValueError on ISO and also reads bare Redis key while Django RedisCache prefixes keys (:1:…). Beat container marked unhealthy forever or false-negative vs API readiness.",
    evidence="tasks.py L49 isoformat; compose.prod L55 float(...); views.py L68-71 fromisoformat; CACHES RedisCache LOCATION without KEY_PREFIX override → default versioned keys",
    root_cause="Wave 13A–F healthcheck written against a different wire format than the heartbeat writer; no end-to-end assert in CI.",
    business="Silent beat death undetected by wrong probe OR permanent restart loop → missed depreciation/insights schedules.",
    technical="Split brain: API readiness ISO-aware; compose healthcheck float+raw key.",
    customer="Scheduled jobs stop without pageable ops signal.",
    security="N/A",
    performance="N/A",
    scalability="Multi-replica beat failover broken.",
    compliance="Ops control failure for statutory period jobs.",
    risk="Production beat never healthy after Wave 13 deploy.",
    fix_immediate="Align writer+probes: store unix epoch float OR parse ISO in compose; read via Django cache or document exact Redis key with version prefix; add compose CI self-test.",
    fix_short="Single heartbeat helper shared by task, HealthView, compose snippet.",
    fix_long="Sidecar / Kubernetes probe hitting /health/?ready=1 only.",
    effort="0.5d",
    tests="Write heartbeat → compose snippet exit 0; HealthView ready=1 true; wrong format fails.",
    acceptance="Prod beat healthcheck passes when beat runs; fails when beat stopped <3m.",
    status="Open",
    refs="BB-000385 residual; BB-000359; Wave14 NEW",
)
add(
    title="Gateway refund leaves CustomerReceipt as phantom unallocated advance (no void status)",
    category="Accounting",
    subcategory="Payments AR",
    severity="Critical",
    priority="P0",
    module="Payments",
    feature="Gateway refund",
    files="backend/payments/services.py refund_gateway_payment; backend/payments/models.py CustomerReceipt; backend/ledgers/services.py customer_unallocated_receipts",
    problem="refund_gateway_payment deletes allocations and reverses GL CREATE, but CustomerReceipt has no void/refunded status and remains in LedgerService.customer_unallocated_receipts at full amount. Invoice outstanding returns (alloc deleted) AND customer shows fake cash advance.",
    evidence="CustomerReceipt model fields have no status; refund L572-595 deletes alloc + reverse journal only; customer_unallocated_receipts L122-130 sums all receipts−alloc",
    root_cause="Refund designed as note-only unwind without receipt lifecycle state.",
    business="AR and advances both wrong after every gateway refund; cash-basis GST distortion; credit-limit exposure understated.",
    technical="Document ledger and GL diverge; cannot trust customer balance.",
    customer="Paid-then-refunded invoices reappear due + customer shows credit.",
    security="Fraud path: refund externally, keep BizBoard advance.",
    performance="N/A",
    scalability="Every refund permanently corrupts AR control.",
    compliance="Books not true and fair.",
    risk="Pilot with Razorpay refunds produces unusable books.",
    fix_immediate="Add receipt status VOID/REFUNDED excluded from ledger; zero amount or contra receipt; reset payment link; post refund GL (Dr Advances/AR Cr Bank).",
    fix_short="Idempotent refund journal purpose=REFUND; link status machine.",
    fix_long="Payment event ledger (capture/refund/chargeback) as source of truth.",
    effort="2-3d",
    tests="Capture→refund → outstanding=invoice; unallocated=0; link not PAID; GL cash down.",
    acceptance="Refund cannot create phantom advances.",
    status="Open",
    refs="BB-000382 residual; Wave14 NEW",
)
add(
    title="Gateway refund does not reopen PaymentLink (stays PAID/PARTIALLY_PAID)",
    category="Business Logic",
    subcategory="Payments",
    severity="Critical",
    priority="P0",
    module="Payments",
    feature="Payment links",
    files="backend/payments/services.py refund_gateway_payment finalize_gateway_payment",
    problem="After full refund, PaymentLink.status remains PAID with paid_receipt set. finalize blocks duplicate capture when PAID+paid_receipt. Customer cannot re-pay; UI shows paid; money returned.",
    evidence="refund_gateway_payment L543-604 never touches link; finalize L458-464 rejects when link PAID",
    root_cause="Refund path incomplete vs capture state machine.",
    business="Lost collections; support chaos; false paid KPIs.",
    technical="Link state machine missing REFUNDED/OPEN_AFTER_REFUND.",
    customer="Cannot pay again after refunded link.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Payment control failure.",
    risk="Chargeback/refund ops unusable in production.",
    fix_immediate="On full refund: set link CREATED/SENT or REFUNDED; clear paid_receipt; allow new capture up to amount.",
    fix_short="Partial refund proportional link remaining.",
    fix_long="Link ledger of captures−refunds.",
    effort="1d",
    tests="Refund → link not PAID; new capture allowed.",
    acceptance="Refunded links are not reported paid.",
    status="Open",
    refs="BB-000438 residual; Wave14 NEW",
)
add(
    title="Fixed asset disposal posts NBV to depreciation expense (no loss/consideration)",
    category="Accounting",
    subcategory="Fixed assets",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="Asset disposal",
    files="backend/accounting/views.py FixedAssetViewSet.dispose",
    problem="dispose Dr AccumDep (if any) + Dr depreciation_expense for NBV + Cr Asset cost. NBV written off to depreciation expense is not Ind AS/AS-compliant disposal; no sale proceeds, receivable, or Loss/Gain on Disposal account; P&L misclassified.",
    evidence="views.py L229-245: net_book_value debited to depreciation_expense_account",
    root_cause="Simplified stub treated write-off as extra depreciation.",
    business="Depreciation expense inflated; disposal gains/losses invisible; tax depreciation schedules wrong.",
    technical="Chart missing 5600 Loss on Disposal / Bank lines.",
    customer="CA rejects fixed-asset register.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Companies Act / Ind AS 16 disposal presentation failure.",
    risk="Accounting_enabled pilots with assets produce wrong P&L.",
    fix_immediate="Require proceeds; Dr Bank/Receivable; Dr/Cr Loss/Gain; never expense NBV via dep account.",
    fix_short="Disposal wizard + tax WDV schedule.",
    fix_long="Full FA subledger with block/shift.",
    effort="2d",
    tests="Dispose with proceeds 0 and >NBV; assert accounts; dep expense unchanged except monthly run.",
    acceptance="Disposal never hits 5300 for NBV.",
    status="Open",
    refs="BB-000330 residual; Wave14 NEW",
)
add(
    title="Sales return COGS reverse uses post-restore WAVG unit_cost not original SALE movement cost",
    category="Accounting",
    subcategory="Perpetual inventory",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="Sales returns COGS",
    files="backend/sales/services.py complete_return; backend/inventory/services.py InventoryValuationService",
    problem="BB-000380 added post_sales_return_cogs but amount = Σ current unit_cost() × qty AFTER SALES_RETURN stock movements posted. Original sale COGS used SALE movement unit_cost at complete time. WAVG drifts with intervening purchases; post-restore valuation includes returned qty — reverse ≠ original COGS.",
    evidence="complete_return L769-835 stock first; L881-897 unit_cost after restore; sale path L460-513 uses movement unit_cost",
    root_cause="Wave 13B closed 'missing reverse' without cost-basis parity.",
    business="Inventory GL and COGS permanently drift vs true perpetual layers.",
    technical="Honesty help_text admits FIFO incomplete; return reverse still wrong under WAVG timing.",
    customer="Trading account wrong after returns.",
    security="N/A",
    performance="N/A",
    scalability="Error compounds per return.",
    compliance="Books vs stock valuation fail audit.",
    risk="accounting_enabled + returns = wrong P&L.",
    fix_immediate="Sum abs(SALE movement.unit_cost×qty) for returned lots before restore; or reverse original COGS journal proportionally.",
    fix_short="Store cogs_amount on SalesReturnItem.",
    fix_long="True FIFO/FEFO layer ledger.",
    effort="1-2d",
    tests="Sale@10 → purchase@20 → return → COGS_REVERSE equals original 10×qty.",
    acceptance="Return COGS reverse matches original sale COGS basis.",
    status="Open",
    refs="BB-000380 residual; BB-000404; Wave14 NEW",
)
add(
    title="Wave 13 Open==0 invalidated — residual Criticals after checklist closure",
    category="Process",
    subcategory="Audit gates",
    severity="Critical",
    priority="P0",
    module="Docs",
    feature="Audit process",
    files="docs/reviews/MASTER_ISSUE_REGISTER.md; docs/reviews/_wave13_assert_gates.py; docs/reviews/_wave13_close_open.py",
    problem="Wave 13 asserted Open==0 via gate scripts that checked named string patterns (sandbox ban, or True removal) but did not adversarially verify refund AR, disposal GL, COGS cost basis, or beat ISO↔float. Checklist closure ≠ correctness.",
    evidence="open_count 0 in _stats.json while live residuals BB-000456–460 exist",
    root_cause="Gate scripts encode presence of prior fixes, not property-based residual tests.",
    business="False confidence for commercial launch.",
    technical="Meta-process debt.",
    customer="Risk of shipping broken money paths.",
    security="Process failure.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Repeat Wave 10–13 false Open==0 pattern.",
    fix_immediate="Reopen Open count; require adversarial money/refund/beat e2e before any Open==0 claim.",
    fix_short="Property tests in assert_gates for heartbeat roundtrip + refund ledger invariants.",
    fix_long="Separate 'checklist closed' from 'launch approved' statuses.",
    effort="1d process + tests",
    tests="assert_gates fails if heartbeat format mismatch or refund phantom advance.",
    acceptance="Open==0 never claimed without residual suite green.",
    status="Open",
    refs="BB-000386 pattern; Wave14 NEW",
)
add(
    title="Audit prompt still claims Manufacturing/Payroll/CRM/WhatsApp Business/native Mobile/multi-company as implemented",
    category="Product",
    subcategory="Honesty",
    severity="Critical",
    priority="P0",
    module="Product",
    feature="Positioning",
    files="README.md (honest); user audit prompt module list; web navigation",
    problem="Commercial audit brief lists Manufacturing, Payroll, CRM, WhatsApp, Mobile App, Multi Company/Branch as implemented. Codebase still has no manufacturing/payroll/CRM apps; WhatsApp is wa.me only; mobile is responsive web; single Company membership. README is honest but sales/audit brief is not.",
    evidence="No backend apps for manufacturing/payroll/crm; i18n whatsapp honesty; Company model single-tenant MVP lock comment",
    root_cause="Product marketing ahead of engineering; prior BB-000035 Deferred not enforced on external claims.",
    business="Mis-selling / refund / legal risk at commercial launch.",
    technical="Scope inflation.",
    customer="Expects ERP modules that 404.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Consumer protection / contract risk.",
    risk="Launch as 'Cloud ERP' is false advertising.",
    fix_immediate="Strip claims from all commercial materials; only README-scope modules.",
    fix_short="Feature matrix signed by PM/CA.",
    fix_long="Build modules or permanently Won't Claim.",
    effort="0.5d copy; years for modules",
    tests="Nav/e2e assert no Manufacturing/Payroll/CRM routes.",
    acceptance="No public surface claims absent modules.",
    status="Open",
    refs="BB-000035; BB-000455; Wave14 REAFFIRM",
)

# ─── HIGH ───────────────────────────────────────────────────────────────────
add(
    title="fetchAllPages still used across money list helpers despite BB-000427 Resolved",
    category="Performance",
    subcategory="Frontend data loading",
    severity="High",
    priority="P1",
    module="Web",
    feature="API client",
    files="web/src/api/resources.ts fetchAllPages listQuotations listReturns listReceipts listCreditNotes …",
    problem="resources.ts still implements fetchAllPages (50-page hard fail) and wires it to quotations, returns, receipts, credit/debit notes, orders, challans, stock balances, users. Prior issues marked Resolved without removing pattern.",
    evidence="resources.ts L180+ and callers L774–2132",
    root_cause="Partial picker pagination; list helpers uncleared.",
    business="Large tenants hit hard errors or multi-second loads.",
    technical="Client O(n) memory.",
    customer="Broken history screens at scale.",
    security="N/A",
    performance="High — 50×RTT cliffs.",
    scalability="Fails before 5k rows.",
    compliance="N/A",
    risk="Pilot with >2k invoices unstable.",
    fix_immediate="Ban fetchAllPages for document lists; page all screens.",
    fix_short="ESLint ban + server search endpoints.",
    fix_long="Cursor pagination.",
    effort="3-5d",
    tests="No fetchAllPages in resources for money docs.",
    acceptance="Lists use page APIs only.",
    status="Open",
    refs="BB-000245/298/348/427 residual; Wave14 NEW",
)
add(
    title="web/nginx.conf retains style-src unsafe-inline while root nginx/default.conf hardened",
    category="Security",
    subcategory="CSP",
    severity="High",
    priority="P1",
    module="Web",
    feature="CSP",
    files="web/nginx.conf; nginx/default.conf",
    problem="BB-000441 claimed CSP fix; root nginx/default.conf removed unsafe-inline but web image nginx.conf still has style-src 'self' 'unsafe-inline'. Dual configs → web container ships weaker CSP.",
    evidence="web/nginx.conf L25 and L51 unsafe-inline; nginx/default.conf L32 no unsafe-inline",
    root_cause="Incomplete dual-config remediation.",
    business="XSS impact higher on SPA.",
    technical="Config drift.",
    customer="Session risk if XSS found.",
    security="High — CSP bypass residual.",
    performance="N/A",
    scalability="N/A",
    compliance="Security baseline fail.",
    risk="CD pushes web image with weak CSP.",
    fix_immediate="Sync web/nginx.conf to default.conf; CI diff gate.",
    fix_short="Single nginx template.",
    fix_long="Nonce-based CSP for MUI.",
    effort="0.5d",
    tests="grep CI fails on unsafe-inline in prod nginx paths.",
    acceptance="No unsafe-inline in shipped web CSP.",
    status="Open",
    refs="BB-000314/441 residual; Wave14 NEW",
)
add(
    title="Company.inventory_valuation_method still offers FIFO while COGS forces WAVG",
    category="Accounting",
    subcategory="Inventory valuation",
    severity="High",
    priority="P1",
    module="Inventory",
    feature="Valuation",
    files="backend/accounts/models.py inventory_valuation_method; backend/inventory/services.py InventoryValuationService.valuation",
    problem="UI/API choice FIFO remains; valuation() forces WAVG for COGS/unit_cost (BB-000404 honesty). Operators believe FIFO COGS while books use blended cost.",
    evidence="models.py choices WAVG/FIFO help_text; valuation L438 force WAVG",
    root_cause="Honesty text without removing choice or blocking COGS when FIFO selected.",
    business="False FIFO claims to CA.",
    technical="Setting lies.",
    customer="Audit findings.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Inventory valuation policy misstatement.",
    risk="accounting_enabled + FIFO setting = material misstatement.",
    fix_immediate="Remove FIFO choice or hard-error COGS when FIFO until layers ship; report banner.",
    fix_short="FIFO layer ledger.",
    fix_long="Perpetual FIFO with lot costs.",
    effort="1d honesty / 15d+ FIFO",
    tests="Setting FIFO → API warns; COGS path documented.",
    acceptance="Cannot silently claim FIFO COGS.",
    status="Open",
    refs="BB-000404 residual; Wave14 NEW",
)
add(
    title="Dual ledger architecture remains (document AR/AP vs optional GL) without control account reconciliation job",
    category="Architecture",
    subcategory="Books",
    severity="High",
    priority="P1",
    module="Accounting",
    feature="Control accounts",
    files="backend/ledgers/services.py; backend/accounting/services.py; backend/accounting/reports.py",
    problem="Document-derived ledgers remain source of truth for UI AR/AP; GL posts optionally. No scheduled reconciliation asserting Σ document outstanding == GL 1200/2100. Wave fixes addressed individual postings but not control framework.",
    evidence="README invariants; BooksHealth partial; no Celery recon task for AR/AP control",
    root_cause="Phase5 bolted GL onto document ERP.",
    business="Silent divergence until CA notices.",
    technical="Two truths.",
    customer="Untrustworthy Balance Sheet vs ledgers.",
    security="N/A",
    performance="N/A",
    scalability="Harder multi-entity.",
    compliance="Internal control failure.",
    risk="Enable accounting → undetected BS errors.",
    fix_immediate="Nightly control-account variance alert; block period close on variance.",
    fix_short="Single posting service mandatory when accounting_enabled.",
    fix_long="GL-first or document-only — pick one.",
    effort="5-10d",
    tests="Inject divergence → health fail + close blocked.",
    acceptance="Period close requires AR/AP control match.",
    status="Open",
    refs="BB-000017 lineage; Wave14 NEW",
)
add(
    title="No PostgreSQL RLS — tenant isolation is application-only",
    category="Security",
    subcategory="Tenancy",
    severity="High",
    priority="P1",
    module="Database",
    feature="Multi-tenant",
    files="backend/core/viewsets.py; all CompanyScopedModel tables",
    problem="Shared-DB multi-tenant with ORM company filters only. Bug/raw SQL/admin mistake can cross tenants. No Postgres RLS policies.",
    evidence="CompanyScopedViewSet filter; no migrations creating POLICY",
    root_cause="MVP shared DB without defense-in-depth.",
    business="Catastrophic cross-tenant data leak risk at scale.",
    technical="Single layer isolation.",
    customer="Competitor data exposure.",
    security="High at 10k tenants.",
    performance="RLS adds planning cost — acceptable.",
    scalability="Blocks enterprise RFPs requiring RLS.",
    compliance="ISO27001 / SOC2 tenancy control gap.",
    risk="One missing filter = breach.",
    fix_immediate="CodeQL/tests for unfiltered querysets; deny superuser app role.",
    fix_short="RLS policies + SET app.company_id.",
    fix_long="Schema-per-tenant for regulated.",
    effort="10-20d",
    tests="SET ROLE app; SELECT without GUC returns 0.",
    acceptance="DB enforces tenant even if ORM buggy.",
    status="Open",
    refs="Wave14 NEW; prior scalability notes",
)
add(
    title="GO_NO_GO.md still unsigned — no CA/UAT/TLS/backup sign-off",
    category="Process",
    subcategory="Launch gate",
    severity="High",
    priority="P1",
    module="Docs",
    feature="Pilot readiness",
    files="docs/pilot/GO_NO_GO.md",
    problem="All checklist boxes empty; decision table blank. Commercial launch without signed Go is process Critical/High.",
    evidence="GO_NO_GO.md unchecked items",
    root_cause="Engineering waves outran governance.",
    business="Unmanaged launch risk.",
    technical="N/A",
    customer="Unsupported pilot.",
    security="TLS/backup unsigned.",
    performance="N/A",
    scalability="N/A",
    compliance="CA letter missing.",
    risk="Illegal/unsafe GST claims.",
    fix_immediate="Block paid pilot until signed.",
    fix_short="Automate ENV_CHECKLIST in CI.",
    fix_long="Release train with gates.",
    effort="Ops calendar",
    tests="N/A",
    acceptance="Signed GO_NO_GO attached to release.",
    status="Open",
    refs="BB-000014 lineage; Wave14 REAFFIRM",
)
add(
    title="compose backup profile exists but no scheduled restore drill automation",
    category="DevOps",
    subcategory="DR",
    severity="High",
    priority="P1",
    module="Ops",
    feature="Backups",
    files="docker-compose.yml backup service; scripts/backup.sh",
    problem="Manual profile backup dumps SQL.gz; no restore job, no CI restore proof, no RPO/RTO documented in-repo as executed.",
    evidence="backup.sh dump only; GO_NO_GO backup drill unchecked",
    root_cause="Dump ≠ DR.",
    business="Data-loss event unrecoverable in practice.",
    technical="Unverified backups.",
    customer="Business continuity fail.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="DR control missing.",
    risk="First restore fails in incident.",
    fix_immediate="Quarterly restore drill dated in GO_NO_GO.",
    fix_short="CI job restore to ephemeral PG.",
    fix_long="PITR + offsite.",
    effort="2d + ops",
    tests="Restore script exits 0 on sample dump.",
    acceptance="Documented successful restore <RTO.",
    status="Open",
    refs="Deferred ops; Wave14 NEW",
)
add(
    title="CD pushes mutable sha tags without digest pin verification on deploy host",
    category="DevOps",
    subcategory="Supply chain",
    severity="High",
    priority="P1",
    module="CI",
    feature="CD",
    files=".github/workflows/cd.yml; docker-compose.prod.yml comments",
    problem="CD builds/pushes :sha tags; compose.prod comments suggest digest pins but deploy path not enforced. Tag can be overwritten; no cosign/SBOM gate.",
    evidence="cd.yml docker push sha; compose.prod example comment only",
    root_cause="Partial supply-chain hygiene.",
    business="Compromised registry tag → prod.",
    technical="Mutable references.",
    customer="Supply-chain incident.",
    security="High.",
    performance="N/A",
    scalability="N/A",
    compliance="SLSA level low.",
    risk="Image swap attack.",
    fix_immediate="Record digests in release notes; deploy by digest.",
    fix_short="cosign sign + verify in CD.",
    fix_long="SLSA3 provenance.",
    effort="2-4d",
    tests="Deploy refuses non-digest.",
    acceptance="Prod runs digest-pinned images only.",
    status="Open",
    refs="BB-000368 residual; Wave14 NEW",
)
add(
    title="Access JWT still returned in JSON body when DJANGO_ENV not production/staging",
    category="Security",
    subcategory="Session",
    severity="High",
    priority="P1",
    module="Accounts",
    feature="Login",
    files="backend/accounts/views.py LoginView OtpVerifyView",
    problem="Cookie auth complete for prod/staging, but any mislabeled env (development on public host) still puts access in JSON. XSS/exfil residual for staging mistakes.",
    evidence="LoginView L224-227; OTP L386-390",
    root_cause="Dev convenience vs fail-closed.",
    business="Session theft if env wrong.",
    technical="Dual auth modes.",
    customer="Account takeover.",
    security="High under misconfig.",
    performance="N/A",
    scalability="N/A",
    compliance="Session standard fail.",
    risk="Common in rushed deploys.",
    fix_immediate="Cookie-only access whenever DEBUG=0 or non-local hosts.",
    fix_short="Remove body access entirely.",
    fix_long="BFF session.",
    effort="1d",
    tests="DEBUG=0 → access null in body always.",
    acceptance="No access JWT in JSON outside explicit local DEBUG.",
    status="Open",
    refs="BB-000407 residual; Wave14 NEW",
)
add(
    title="GSTR-3B ITC remains books-provisional — no GSTR-2B match engine",
    category="GST",
    subcategory="ITC",
    severity="High",
    priority="P1",
    module="Reporting",
    feature="GSTR-3B",
    files="backend/reporting/gst_returns.py",
    problem="itc_claimable False honesty present; still no 2B ingest/match. Deferred BB-000406 remains blocking compliance GA.",
    evidence="gst_returns.py itc_provisional / itc_claimable False notes",
    root_cause="Vendor GSP + product scope.",
    business="Cannot auto-claim ITC safely.",
    technical="Offline aid only.",
    customer="Manual 2B reconciliation.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="High — GST portal dependency.",
    risk="Over-claim if honesty ignored.",
    fix_immediate="Keep claimable=false; UI watermark.",
    fix_short="CSV 2B import matcher.",
    fix_long="Live GSP 2B API.",
    effort="20-40d+",
    tests="Cannot set claimable true without match records.",
    acceptance="No auto ITC claim without 2B.",
    status="Open",
    refs="BB-000406 Deferred reaffirm; Wave14",
)
add(
    title="Live IRP/e-Way adapters still raise BusinessRuleError — production statutory dead end",
    category="Integration",
    subcategory="GSP",
    severity="High",
    priority="P1",
    module="Integrations",
    feature="e-Invoice",
    files="backend/core/services/gsp_adapters.py LiveIrpAdapter LiveEwayAdapter",
    problem="Live adapters intentionally fail closed after credential check. Sandbox hashes only. Commercial claim of GST Portal Integration false for live IRN.",
    evidence="gsp_adapters.py LiveIrpAdapter._ensure_configured raises; SandboxIrpAdapter hash IRN",
    root_cause="Vendor integration not built.",
    business="Cannot issue legal IRN from prod.",
    technical="Stub.",
    customer="Must use portal/other GSP.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Blocking for B2B e-invoice mandated taxpayers.",
    risk="Misuse of sandbox IRNs as real.",
    fix_immediate="Prod flags fail-closed (done); never show sandbox IRN as filed.",
    fix_short="Partner GSP adapter.",
    fix_long="Certified GSP.",
    effort="40-80d+",
    tests="Prod submit live → clear error; no fake IRN.",
    acceptance="Live IRN only via real GSP.",
    status="Open",
    refs="BB-000384 Deferred; Wave14 REAFFIRM",
)
add(
    title="PhasePages.tsx ~73KB god-module still hosts multiple accounting/report surfaces",
    category="Technical Debt",
    subcategory="Frontend modularity",
    severity="High",
    priority="P1",
    module="Web",
    feature="Phase pages",
    files="web/src/pages/phase/PhasePages.tsx",
    problem="Single 73KB file still aggregates many phase surfaces; prior god-module issues Deferred without split.",
    evidence="File size ~72923 bytes",
    root_cause="Phase scaffolding never extracted.",
    business="Slow feature velocity; high regression risk.",
    technical="Untestable blob.",
    customer="UI bugs.",
    security="N/A",
    performance="Bundle parse cost.",
    scalability="Dev productivity fail.",
    compliance="N/A",
    risk="Untouchable code.",
    fix_immediate="Freeze new features in file.",
    fix_short="Split per route.",
    fix_long="Domain packages.",
    effort="5-8d",
    tests="Route smoke after split.",
    acceptance="No file >400 LOC in pages/phase.",
    status="Open",
    refs="BB-000108/114 Deferred residual; Wave14 NEW",
)
add(
    title="NewInvoicePage / NewPurchasePage ~69KB editors remain unsplit",
    category="Technical Debt",
    subcategory="Frontend modularity",
    severity="High",
    priority="P1",
    module="Web",
    feature="Invoice editors",
    files="web/src/pages/sales/NewInvoicePage.tsx; web/src/pages/purchases/NewPurchasePage.tsx",
    problem="Core money editors still monolithic ~69KB each — tax, stock, parties, batches intertwined.",
    evidence="File sizes ~68984 / ~69700",
    root_cause="Feature accretion.",
    business="Every GST tweak risks sales regression.",
    technical="High cyclomatic complexity.",
    customer="Subtle billing bugs.",
    security="N/A",
    performance="Main-thread parse.",
    scalability="Team bottleneck.",
    compliance="Hard to CA-review UI tax path.",
    risk="Chronic defects.",
    fix_immediate="Extract tax line table + party panel.",
    fix_short="Shared DocumentEditor kit.",
    fix_long="Headless form core + skins.",
    effort="8-12d",
    tests="Tax parity vitest + e2e complete invoice.",
    acceptance="Editor modules <300 LOC each.",
    status="Open",
    refs="Wave14 NEW",
)
add(
    title="sales/services.py ~47KB god-service — sales/returns/challans/COGS in one module",
    category="Technical Debt",
    subcategory="Backend modularity",
    severity="High",
    priority="P1",
    module="Sales",
    feature="SalesService",
    files="backend/sales/services.py",
    problem="Complete invoice, returns, COGS, reservations concentrated; hard to reason about transactions.",
    evidence="~47665 bytes",
    root_cause="Service accretion across phases.",
    business="Slow safe change.",
    technical="SOLID violation.",
    customer="Edge-case money bugs.",
    security="N/A",
    performance="Import weight.",
    scalability="Merge conflicts.",
    compliance="Hard audit.",
    risk="Regressions on every wave.",
    fix_immediate="Extract ReturnService / CogsService.",
    fix_short="Package sales/domain/.",
    fix_long="Hexagonal ports.",
    effort="8-15d",
    tests="Existing phase tests green.",
    acceptance="No sales service file >800 LOC.",
    status="Open",
    refs="Wave14 NEW",
)
add(
    title="No load / soak test evidence for shared-DB 10k-tenant target",
    category="Performance",
    subcategory="Capacity",
    severity="High",
    priority="P1",
    module="Cross-cutting",
    feature="Scalability",
    files="backend/tests; .github/workflows; docs",
    problem="No k6/Locust/JMeter suite; concurrency tests exist for inventory locks but not API RPS or DB pool saturation.",
    evidence="No load scripts in repo",
    root_cause="Pilot-first.",
    business="Unknown capacity → outages at growth.",
    technical="Ungrounded scalability score.",
    customer="Slow POS at peak.",
    security="N/A",
    performance="Unknown.",
    scalability="High risk.",
    compliance="N/A",
    risk="First festival sale melts API.",
    fix_immediate="k6 smoke 100 VU on health+login+invoice list.",
    fix_short="Nightly soak.",
    fix_long="Autoscaling SLOs.",
    effort="5d+",
    tests="CI optional load job.",
    acceptance="Published p95 for key APIs.",
    status="Open",
    refs="Wave14 NEW",
)
add(
    title="Request JSON logs omit latency, user_id, company_id — weak incident response",
    category="Reliability",
    subcategory="Observability",
    severity="High",
    priority="P1",
    module="Core",
    feature="Logging",
    files="backend/core/middleware.py RequestIdMiddleware",
    problem="Logs method/path/status/request_id only — no duration_ms, tenant, user. SRE cannot slice slow tenants or abuse.",
    evidence="middleware.py L22-33",
    root_cause="Privacy-minimal log incomplete for ops.",
    business="MTTR high.",
    technical="Blind SRE.",
    customer="Long outages.",
    security="Abuse detection weak.",
    performance="Cannot find slow endpoints.",
    scalability="N/A",
    compliance="Audit trail incomplete for API access.",
    risk="Incidents un-debuggable.",
    fix_immediate="Add duration_ms; hash user/company ids.",
    fix_short="OpenTelemetry traces.",
    fix_long="Full APM.",
    effort="1-3d",
    tests="Log line contains duration.",
    acceptance="P95 dashboards possible.",
    status="Open",
    refs="BB-000443 residual; Wave14 NEW",
)
add(
    title="Partial gateway refunds unsupported — allocation/GL cannot proportion",
    category="Business Logic",
    subcategory="Payments",
    severity="High",
    priority="P1",
    module="Payments",
    feature="Refunds",
    files="backend/payments/services.py refund_gateway_payment",
    problem="Only full refunds; Razorpay partial refunds common. Hard error leaves ops on manual journal.",
    evidence="L559-561 Only full refunds are supported",
    root_cause="Scope cut.",
    business="Cannot match gateway reality.",
    technical="Incomplete state machine.",
    customer="Support tickets.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Bank recon breaks.",
    risk="Manual books overrides.",
    fix_immediate="Document limitation in UI.",
    fix_short="Proportional alloc unwind.",
    fix_long="Payment event ledger.",
    effort="3-5d",
    tests="Partial refund 50% → half alloc remaining.",
    acceptance="Partial refunds supported or gateway partial disabled.",
    status="Open",
    refs="Wave14 NEW",
)
add(
    title="Quotations/returns list routes require canCreateSales — viewers with financial reports cannot list",
    category="Security",
    subcategory="RBAC UX",
    severity="High",
    priority="P1",
    module="Web",
    feature="RoleRoute",
    files="web/src/App.tsx",
    problem="sales/quotations and sales/returns gated by canCreateSales while history uses canViewSalesSurfaces. Accountant with view-financial cannot open returns list even if API allows view surfaces.",
    evidence="App.tsx L263-265 vs L254-261",
    root_cause="Route ACL inconsistency.",
    business="SoD friction; shadow spreadsheets.",
    technical="FE/BE ACL drift risk.",
    customer="Blocked legitimate read.",
    security="Over-deny (availability) not over-allow.",
    performance="N/A",
    scalability="N/A",
    compliance="Role design incomplete.",
    risk="Workarounds with Owner logins.",
    fix_immediate="Align list routes to canViewSalesSurfaces; keep mutate on create.",
    fix_short="Matrix test FE×BE.",
    fix_long="Capability catalog.",
    effort="0.5d",
    tests="Accountant opens returns list; cannot complete.",
    acceptance="View vs mutate split consistent.",
    status="Open",
    refs="Wave14 NEW",
)

# ─── MEDIUM (batch) ─────────────────────────────────────────────────────────
for title, cat, sub, mod, feat, files, problem, evidence, fix, effort in [
    (
        "GSTR-9 builder remains minimal FY aid — not full annual return engine",
        "GST", "GSTR-9", "Reporting", "GSTR-9",
        "backend/reporting/gst_returns.py",
        "GSTR-9 is labeled aid not full engine; commercial GST module claims imply completeness.",
        "BUILDER_VERSION_GSTR9 + docstring FY outward + minimal inward",
        "Watermark UI; defer claim; or build full GSTR-9.",
        "15-30d",
    ),
    (
        "Composition CMP-08 / GSTR-4 aids absent — composition dealers blocked from regular packs only",
        "GST", "Composition", "Reporting", "Composition returns",
        "backend/reporting/gst_returns.py assert_not_composition_for_regular_returns",
        "Composition correctly blocked from GSTR-1/3B but no CMP-08/GSTR-4 replacement.",
        "BusinessRuleError composition cannot export Regular packs",
        "Build CMP aids or refuse composition onboarding.",
        "10-20d",
    ),
    (
        "SEZ / export / deemed export GST treatments not first-class",
        "GST", "Supply type", "Sales", "Export",
        "backend/sales; core/services/billing.py",
        "No explicit SEZ/export invoice types with zero-rate + LUT/bond fields in core path.",
        "Invoice types GST/non-GST primarily; no SEZ enum in models skim",
        "Add supply_type + validation + GSTR sections.",
        "10d",
    ),
    (
        "Tally integration is CSV/XLSX migration — not bidirectional live sync",
        "Integration", "Tally", "Integrations", "Tally",
        "backend/integrations/tally/adapter.py",
        "Audit claims Tally Sync; implementation is import/export migration magnet.",
        "tally adapter CSV oriented; no XML remote continuous sync",
        "Rename to Migration; or build connector.",
        "0.5d copy / 60d+ sync",
    ),
    (
        "WhatsApp remains wa.me deep link — not WhatsApp Business API",
        "Integration", "WhatsApp", "Core", "Share",
        "web/src/i18n/en.ts; notifications",
        "Honesty string exists; product lists still say WhatsApp as module.",
        "i18n whatsapp not delivered by BizBoard",
        "Keep honesty; remove module claim.",
        "0.5d",
    ),
    (
        "No native mobile app — responsive web only",
        "Mobile", "Client", "Web", "PWA/Mobile",
        "web/",
        "No React Native/Flutter/Capacitor project; mobile claim false.",
        "Only web/ SPA",
        "Remove claim or ship PWA+store wrapper.",
        "30d+",
    ),
    (
        "Multi-warehouse ≠ multi-branch GSTIN / multi-company",
        "Architecture", "Tenancy", "Accounts", "Branches",
        "backend/accounts/models.py Company; inventory Warehouse",
        "Warehouses exist; one GSTIN company; one active membership. Multi-branch GST compliance absent.",
        "Company MVP lock comment; Warehouse model",
        "Branch GSTIN model + POS rules or stop claiming.",
        "20d+",
    ),
    (
        "AI assistant tax refusal regex bypass via synonyms/typos/Indic",
        "AI", "Safety", "Insights", "Assistant",
        "backend/insights/assistant.py TAX_PATTERNS",
        "Keyword deny list incomplete for Hindi/typos/indirect prompts; LLM may still advise if tool path used.",
        "TAX_PATTERNS English-centric",
        "Classifier + system prompt + output filter; log refusals.",
        "3-5d",
    ),
    (
        "OCR bill upload depends on LLM — no confidence threshold hard-stop before complete",
        "AI", "OCR", "Purchases", "Bill upload",
        "web/src/pages/purchases/PurchaseBillUploadPage.tsx; insights/core llm",
        "OCR drafts may complete purchases with low-confidence HSN/amounts without mandatory human confirm gates beyond UI.",
        "PurchaseBillUploadPage exists; verify confirm UX",
        "Require explicit accept per field below confidence.",
        "2d",
    ),
    (
        "Fixed asset monthly depreciation Celery task isolates failures but no per-company dead-letter UI",
        "Reliability", "Jobs", "Accounting", "Depreciation",
        "backend/accounting/tasks.py post_monthly_depreciation",
        "Per-asset try/except continues; operators lack in-app failed depreciation queue.",
        "tasks.py isolate per-asset failures",
        "Surface failures on BooksHealth.",
        "2d",
    ),
    (
        "No idempotency-Key support on document complete APIs",
        "API", "Idempotency", "Sales", "Complete",
        "backend/sales/views.py; purchases/views.py",
        "Double-submit protected by status checks + locks but clients lack Idempotency-Key standard for flaky mobile networks.",
        "select_for_update status draft checks only",
        "Support Idempotency-Key header store.",
        "3d",
    ),
    (
        "Search endpoints may still be heavier than throttle alone justifies at tenant scale",
        "Performance", "Search", "Search", "Global search",
        "backend/search/views.py",
        "Global search across documents; indexes may be incomplete for ILIKE patterns.",
        "search app views",
        "pg_trgm indexes + timeout.",
        "2d",
    ),
    (
        "Frontend vitest coverage thin vs page surface area",
        "Testing", "FE", "Web", "Unit tests",
        "web/src/**/*.test.ts*",
        "Few unit tests relative to dozens of pages; money editors under-tested on FE.",
        "Sparse *.test.ts under pages",
        "Mandatory tests for tax.ts and critical editors.",
        "10d",
    ),
    (
        "E2E smoke can seed localStorage user — not full cookie auth path",
        "Testing", "E2E", "Web", "Playwright",
        "web/e2e/smoke.spec.ts",
        "Smoke sets bizboard.user in localStorage; may not exercise httpOnly cookie login.",
        "smoke.spec.ts localStorage.setItem bizboard.user",
        "Login via UI cookies.",
        "1d",
    ),
    (
        "Accessibility: many MUI dialogs/pages lack audited axe CI gate",
        "UX", "a11y", "Web", "Accessibility",
        "web/; .github/workflows/ci.yml",
        "No axe-core CI job; prior a11y fixes incomplete as systematic gate.",
        "No axe workflow step found in CD/CI skim",
        "Add axe to Playwright CI.",
        "2d",
    ),
    (
        "i18n English-only — no Hindi for MSME target",
        "UX", "i18n", "Web", "Localization",
        "web/src/i18n/en.ts",
        "Single en.ts; Indian MSME Hindi/regional missing.",
        "Only en.ts",
        "Add hi.ts critical flows.",
        "10d",
    ),
    (
        "Password policy relies on Django defaults — no breached-password check",
        "Security", "Auth", "Accounts", "Passwords",
        "backend/accounts/views.py validate_password",
        "No HaveIBeenPwned/NIST breached password API.",
        "validate_password only",
        "Add common/breached validators.",
        "1d",
    ),
    (
        "Invite tokens use Django signing — OK entropy but no one-time consume flag on membership until accept",
        "Security", "Invites", "Accounts", "Invite",
        "backend/accounts/views.py _make_invite_token",
        "Token replay until max_age if accept not marking single-use server-side beyond membership state — verify consume.",
        "signing.dumps invite",
        "jti store + consume on accept.",
        "1d",
    ),
    (
        "FileAsset upload MIME allowlists exist — content sniffing vs extension spoof residual",
        "Security", "Uploads", "Core", "Files",
        "backend/core/services/files.py",
        "MIME from client + size rules; deep content inspection limited.",
        "files.py _KIND_RULES",
        "python-magic sniff + antivirus.",
        "2d",
    ),
    (
        "Admin enabled when DEBUG — production ADMIN_ENABLED default off but path may still be mounted if mis-set",
        "Security", "Admin", "Config",
        "Admin surface",
        "backend/config/settings.py ADMIN_ENABLED; urls",
        "Mis-set ADMIN_ENABLED=1 in prod exposes Django admin.",
        "ADMIN_ENABLED default 1 if DEBUG",
        "Fail closed unless explicit + IP allowlist.",
        "0.5d",
    ),
    (
        "CORS_ALLOW_CREDENTIALS true with origins from env — wildcard misconfig risk",
        "Security", "CORS", "Config", "CORS",
        "backend/config/settings.py",
        "Credentials+CORS; if operator sets * origins broken/unsafe depending on stack.",
        "CORS_ALLOW_CREDENTIALS = True",
        "Reject * with credentials at boot.",
        "0.5d",
    ),
    (
        "SQLite still default when DATABASE_URL absent — accidental non-prod DB in shared hosts",
        "Configuration", "Database", "Config", "DB",
        "backend/config/settings.py; README",
        "README warns PG required for prod; code still allows SQLite boot.",
        "README SQLite when DATABASE_URL absent",
        "Refuse SQLite when DJANGO_ENV production (likely exists — re-verify harden).",
        "0.5d",
    ),
    (
        "Gunicorn workers=2 hardcoded in compose — no concurrency tuning guide",
        "Performance", "Runtime", "DevOps", "Gunicorn",
        "docker-compose.yml api command",
        "Fixed 2 workers; no formula for CPU; long requests block.",
        "gunicorn --workers 2",
        "Env GUNICORN_WORKERS + docs.",
        "0.5d",
    ),
    (
        "No read replicas / statement timeout defaults documented for PG",
        "Database", "Ops", "Database", "Postgres",
        "docker-compose.yml; settings DATABASES",
        "No statement_timeout / idle_in_transaction_session_timeout set in app OPTIONS.",
        "Default Django DB config",
        "Set timeouts in OPTIONS.",
        "0.5d",
    ),
    (
        "Reporting gst_returns.py ~40KB complex builder — high defect density risk",
        "Maintainability", "Complexity", "Reporting", "GSTR",
        "backend/reporting/gst_returns.py",
        "Large GSTR builder accumulates edge cases; hard CA review.",
        "~40619 bytes",
        "Split section builders + golden fixtures per section.",
        "5d",
    ),
    (
        "Payments views.py ~38KB mixes webhooks, recon, settings, links",
        "Maintainability", "Complexity", "Payments", "Views",
        "backend/payments/views.py",
        "God view module.",
        "~38525 bytes",
        "Split webhooks/recon/api.",
        "3d",
    ),
    (
        "Hypothesis/property tests sparse outside money core",
        "Testing", "Property", "Backend", "Tests",
        "backend/tests",
        "Strong money tests exist; many modules lack property tests.",
        "tests focused phase*",
        "Expand hypothesis on allocations/refunds.",
        "5d",
    ),
    (
        "Dependabot enabled but no auto-merge policy / SLSA for Actions pins",
        "DevOps", "Dependencies", "CI", "Dependabot",
        ".github/dependabot.yml; workflows",
        "Actions may use unpinned floating tags in places; supply chain.",
        "checkout@v4 etc",
        "Pin SHAs for Actions.",
        "1d",
    ),
    (
        "Sentry optional — error budget / alert routing not codified",
        "Reliability", "APM", "DevOps", "Sentry",
        "backend/config/settings.py; web",
        "Sentry DSN optional; no alert policy as code.",
        "Sentry init conditional",
        "Require Sentry in prod + PagerDuty.",
        "1d ops",
    ),
    (
        "BooksHealth / GstHealth warnings not forced before period close",
        "Business Logic", "Controls", "Accounting", "Period close",
        "backend/accounting; reporting/gst_health.py",
        "Health endpoints advisory; close may proceed with critical health codes.",
        "Health views separate from Period close",
        "Block close on critical health.",
        "2d",
    ),
    (
        "Credit limit exposure uses unallocated receipts — interacts badly with refund phantom advances",
        "Business Logic", "Credit", "Ledgers", "Credit limit",
        "backend/ledgers/services.py customer_exposure_for_credit_limit",
        "Exposure subtracts unallocated receipts; phantom refund advances inflate credit.",
        "customer_exposure_for_credit_limit",
        "Fix refund void first; then exposure.",
        "depends on BB-000457",
    ),
    (
        "Delivery challan / SO reservation FEFO paths complex — residual edge lots",
        "Inventory", "FEFO", "Inventory", "Reservations",
        "backend/inventory/services.py; sales",
        "Multiple Wave fixes on FEFO; residual risk on cancel/partial invoice convert.",
        "reserve_stock FEFO comments BB-000343/437",
        "Matrix tests all convert paths.",
        "3d",
    ),
    (
        "No CQRS / read-model for dashboard KPIs — live aggregates on request",
        "Architecture", "CQRS", "Reporting", "Dashboard",
        "backend/reporting/services.py; insights",
        "Dashboard hits live aggregates; no materialized daily rollup required for scale.",
        "ReportService live queries",
        "Nightly rollup tables.",
        "5d",
    ),
    (
        "Public pay page tokenized — brute force token entropy must stay high",
        "Security", "Public pay", "Payments", "Payment links",
        "backend/payments; web PublicPayPage",
        "Public /pay/:token; ensure token bits + rate limit enough (verify residual).",
        "PublicPayPage route",
        "Throttle + 128-bit tokens + audit.",
        "1d",
    ),
    (
        "SMS OTP provider stub fail-closed in prod — WhatsApp/SMS delivery not production-ready",
        "Integration", "SMS", "Core", "OTP",
        "backend/core/services/sms.py",
        "OTP SMS stub; production needs real provider. Auth via SMS OTP limited.",
        "SmsProvider",
        "Integrate MSG91/Twilio; keep fail-closed.",
        "3d",
    ),
    (
        "Email console backend forbidden in prod — transactional email still ops-dependent",
        "DevOps", "Email", "Core", "Notifications",
        "backend/core/tasks.py send_email_notification",
        "Fail-closed good; pilots still need SMTP runbooks.",
        "console backend blocked",
        "Document ENV email checklist.",
        "0.5d",
    ),
    (
        "No formal API versioning sunset policy beyond /api/v1/",
        "API", "Versioning", "Core", "API",
        "backend/config/urls.py",
        "Only v1; no deprecation headers.",
        "/api/v1/",
        "Add Sunset/Deprecation headers policy.",
        "1d",
    ),
    (
        "OpenAPI/docs ENABLE_API_DOCS off when not DEBUG — good; no public schema CI diff",
        "API", "Contract", "Core", "OpenAPI",
        "settings ENABLE_API_DOCS",
        "Schema drift undetected without CI export.",
        "ENABLE_API_DOCS",
        "Export schema artifact in CI.",
        "1d",
    ),
    (
        "Competitor gap: Zoho/TallyPrime/ERPNext still ahead on multi-company, payroll, manufacturing",
        "Competitor", "Positioning", "Product", "Market",
        "docs/reviews/18_COMPETITOR_ANALYSIS.md",
        "Commercial ERP claim vs competitors false; matrix needs refresh post Wave 13.",
        "Prior competitor doc",
        "Update matrix; narrow ICP.",
        "1d",
    ),
    (
        "Root PRODUCTION_READINESS.md vs docs/reviews/21 drift risk",
        "Documentation", "Drift", "Docs", "Readiness",
        "PRODUCTION_READINESS.md; docs/reviews/21_PRODUCTION_READINESS.md",
        "Multiple readiness docs; scores diverge historically.",
        "Dual files",
        "Single canonical pointer.",
        "0.5d",
    ),
    (
        "Media volume shared across api/worker — no virus scan on OCR uploads",
        "Security", "Malware", "Core", "Uploads",
        "docker-compose media_data; FileAsset",
        "Shared media without clamav.",
        "media_data volume",
        "Scan async before serve.",
        "2d",
    ),
    (
        "No row-level audit for every money field change (only document CRUD audits)",
        "Compliance", "Audit trail", "Core", "Audit",
        "backend/core/services/audit.py",
        "AuditService on CRUD; fine-grained field history limited.",
        "AuditEvent model",
        "JSON diff on money updates.",
        "5d",
    ),
    (
        "Cost centers optional — financial reports may ignore CC dimensions",
        "Accounting", "Dimensions", "Accounting", "Cost centers",
        "backend/accounting",
        "CC on lines optional; P&L by CC incomplete for MSME with departments.",
        "CostCenter model",
        "Report filters mandatory when CC used.",
        "3d",
    ),
    (
        "Bank recon CSV only — no account aggregator / AA / net banking fetch",
        "Integration", "Banking", "Payments", "Recon",
        "backend/payments/recon.py",
        "CSV import recon; not live banking.",
        "recon modules",
        "Honesty in UI; future AA.",
        "0.5d copy",
    ),
    (
        "Razorpay only enabled gateway in prod list — Cashfree/PayU disabled stubs",
        "Integration", "Payments", "Payments", "Gateways",
        "backend/payments/gateway.py",
        "DISABLED_PROVIDERS; limited provider choice.",
        "enabled_providers razorpay",
        "Document; implement or hide.",
        "0.5d",
    ),
    (
        "Frontend feature flags build-time only — cannot kill switch without redeploy",
        "Configuration", "Flags", "Web", "Features",
        "web/src/config/features.ts",
        "VITE_ENABLE_* baked at build; CD hardcodes false for accounting/AI/tally — good default but no runtime kill.",
        "features.ts import.meta.env",
        "Runtime flags from /config endpoint.",
        "3d",
    ),
    (
        "CompanyUser single active membership — no multi-company user switcher",
        "Architecture", "Tenancy", "Accounts", "Users",
        "backend/accounts; core/permissions get_company_user",
        ".first() active membership; multi-company users unsupported.",
        "get_company_user order_by id first",
        "Explicit company switch header.",
        "10d",
    ),
    (
        "Viewer role financial default False — good; dashboard empty-state UX weak",
        "UX", "RBAC", "Web", "Dashboard",
        "web/src/pages/DashboardPage.tsx",
        "Viewers hitting Forbidden on index — OK security; needs clearer product path.",
        "RoleRoute canViewFinancialReports on index",
        "Landing for limited roles.",
        "1d",
    ),
    (
        "No contract tests between FE types/domain.ts and DRF serializers",
        "Testing", "Contract", "Cross-cutting", "API",
        "web/src/types/domain.ts; backend serializers",
        "Manual camelCase mapping drift risk.",
        "resources.ts mappers",
        "OpenAPI generated types.",
        "5d",
    ),
    (
        "Celery task send_email_notification autoretry may duplicate sends without provider idempotency",
        "Reliability", "Email", "Core", "Notifications",
        "backend/core/tasks.py",
        "autoretry_for Exception; SMTP may have sent before failure recorded.",
        "autoretry_for=(Exception,)",
        "Idempotent provider keys; mark SENT before raise carefully.",
        "1d",
    ),
    (
        "Insights AI monthly token budget default 500k — cost runaway if enabled",
        "AI", "Cost", "Insights", "Budget",
        "backend/insights/assistant.py assert_within_budget",
        "Budget exists; default high; no per-request $ cap alerts to Owner.",
        "AI_MONTHLY_TOKEN_BUDGET_DEFAULT",
        "Lower default; Owner webhook at 80%.",
        "1d",
    ),
    (
        "No formal data retention / GDPR-like deletion for tenant offboarding",
        "Compliance", "Privacy", "Accounts", "Offboarding",
        "backend/accounts",
        "No delete-company cascade runbook with backup.",
        "Absence of offboard command",
        "offboard_company management command.",
        "5d",
    ),
    (
        "H9 amend purchase/sales period hard-block residuals need continuous regression suite",
        "GST", "Amendments", "Sales", "H9",
        "backend/core/services/h9_amend.py",
        "Prior H9 issues resolved in waves; amend remains high-risk without permanent property tests.",
        "h9_amend service",
        "Keep adversarial amend tests in CI required.",
        "2d",
    ),
    (
        "Place-of-supply known-gate FE/BE — residual unknown state names still soft?",
        "GST", "POS", "Sales", "Place of supply",
        "backend/core/services/place_of_supply.py; web tax utils",
        "Many Wave POS fixes; unknown aliases may still slip depending on path.",
        "IN_STATE_NAME_TO_CODE map",
        "Fail closed on unknown state for GST invoices.",
        "1d",
    ),
    (
        "Nil-rated / exempt / non-GST line mixes on same invoice edge cases",
        "GST", "Tax lines", "Sales", "Mixed supplies",
        "backend/core/services/billing.py",
        "Mixed rate invoices complex for GSTR; edge residual risk.",
        "billing tax math",
        "Golden fixtures mixed supplies.",
        "2d",
    ),
    (
        "E-way distance/vehicle validation residual vs NIC schema",
        "GST", "E-way", "Sales", "E-way",
        "backend/sales/eway_payload.py",
        "Payload builder may omit fields NIC requires in live mode (live blocked anyway).",
        "eway_payload.py",
        "Schema tests vs NIC samples.",
        "2d",
    ),
    (
        "Manual IRN / EWB status fields allow operator override — abuse residual",
        "GST", "Honesty", "Sales", "Manual IRN",
        "backend/sales/models.py",
        "Wave added manual IRN status; operators can mark filed without GSP — needs strong audit + role.",
        "manual_irn migrations",
        "Owner-only + audit reason required.",
        "1d",
    ),
]:
    add(
        title=title,
        category=cat,
        subcategory=sub,
        severity="Medium",
        priority="P2",
        module=mod,
        feature=feat,
        files=files,
        problem=problem,
        evidence=evidence,
        root_cause="Incomplete productization after Wave 13 checklist closure.",
        business="Pilot/GA friction or misstatement.",
        technical="Residual debt.",
        customer="Confusion or manual workarounds.",
        security="See category.",
        performance="See category.",
        scalability="See category.",
        compliance="See category.",
        risk="Accumulates into launch failure modes.",
        fix_immediate=fix,
        fix_short=fix,
        fix_long="Track in REMEDIATION_ROADMAP.",
        effort=effort,
        tests="Regression covering: " + title[:80],
        acceptance="Issue resolved: " + title[:80],
        status="Open",
        refs="Wave14 NEW",
    )

# ─── LOW ─────────────────────────────────────────────────────────────────────
for title, mod, files, problem, evidence, fix in [
    (
        "Demo credentials documented in README — rotate for any shared env",
        "Docs",
        "README.md",
        "demo@bizboard.local / DemoPass123! published.",
        "README demo credentials table",
        "Disable seed_demo in shared envs.",
    ),
    (
        "Office temp file ~$reenShot.docx present in repo root listing historically",
        "Docs",
        "repo root",
        "Word lock files may appear; ensure gitignored.",
        "git status / listing showed ~$reenShot.docx",
        "gitignore Office temps.",
    ),
    (
        "Multiple duplicate path entries for .github workflows in git status (slash vs backslash)",
        "DevOps",
        ".github/",
        "Windows path duplication noise in status.",
        "git status duplicate cd.yml paths",
        "Normalize line endings / sparse checkout.",
    ),
    (
        "Agent worktree .claude/worktrees present — ensure not packaged",
        "DevOps",
        ".claude/",
        "Local agent worktrees must not ship in images.",
        ".claude/worktrees directory",
        "dockerignore + gitignore.",
    ),
    (
        "stats.json Unicode status keys historically corrupted in Windows cp1252 tools",
        "Process",
        "docs/reviews/_stats.json",
        "Encoding hygiene for audit tooling on Windows.",
        "Prior python UnicodeEncodeError",
        "Force UTF-8 in scripts.",
    ),
    (
        "CHANGELOG / EXEC summary score thrash across waves without date-stamped score series chart",
        "Documentation",
        "docs/reviews/",
        "Scores overwrite narrative; hard to trend.",
        "Multiple score revisions in EXEC",
        "Append-only score table.",
    ),
]:
    add(
        title=title,
        category="Quality",
        subcategory="Hygiene",
        severity="Low",
        priority="P3",
        module=mod,
        feature="Hygiene",
        files=files,
        problem=problem,
        evidence=evidence,
        root_cause="Repo hygiene.",
        business="Low.",
        technical="Noise.",
        customer="N/A",
        security="Low",
        performance="N/A",
        scalability="N/A",
        compliance="N/A",
        risk="Confusion.",
        fix_immediate=fix,
        fix_short=fix,
        fix_long=fix,
        effort="0.5d",
        tests="N/A",
        acceptance=title[:60] + " cleaned",
        status="Open",
        refs="Wave14 NEW",
    )


def render_issue(n: int, data: dict) -> str:
    iid = f"BB-{n:06d}"
    return f"""
## {iid} — {data['title']}

| Field | Value |
|-------|-------|
| **Issue ID** | {iid} |
| **Title** | {data['title']} |
| **Category** | {data['category']} |
| **Subcategory** | {data['subcategory']} |
| **Severity** | {data['severity']} |
| **Priority** | {data['priority']} |
| **Module** | {data['module']} |
| **Feature** | {data['feature']} |
| **Affected Files** | {data['files']} |
| **Affected Classes** | See files |
| **Affected Functions** | See files |
| **Affected APIs** | See files / related endpoints |
| **Affected Database Tables** | See models in files |
| **Status** | {data['status']} |
| **Owner** | Unassigned |
| **Review Date** | {TODAY} |
| **Estimated Effort** | {data['effort']} |
| **Breaking Change** | Possibly — assess per fix |
| **Regression Risk** | Medium unless tests added |
| **Dependencies** | See Cross References |
| **Cross References** | {data['refs']} |
| **References** | Wave 14 independent re-audit; live code {TODAY} |

### Problem Description
{data['problem']}

### Evidence
{data['evidence']}

### Code Snippet
See affected files at `{TODAY}` tree.

### Root Cause
{data['root_cause']}

### Business Impact
{data['business']}

### Technical Impact
{data['technical']}

### Customer Impact
{data['customer']}

### Security Impact
{data['security']}

### Performance Impact
{data['performance']}

### Scalability Impact
{data['scalability']}

### Compliance Impact
{data['compliance']}

### Risk if ignored
{data['risk']}

### Steps to reproduce
1. Follow evidence paths in current tree.
2. Execute related API/UI flow.
3. Observe failure vs acceptance criteria.

### Recommended Fix
{data['fix_immediate']}

### Immediate Fix
{data['fix_immediate']}

### Short-term Fix
{data['fix_short']}

### Long-term Refactor
{data['fix_long']}

### Alternative Solutions
Waive with signed risk in GO_NO_GO only if non-P0.

### Required Tests
{data['tests']}

### Acceptance Criteria
{data['acceptance']}

"""


def main():
    prior = json.loads(STATS.read_text(encoding="utf-8"))
    assert prior["total"] == START_ID - 1, f"Expected prior total {START_ID-1}, got {prior['total']}"

    start = START_ID
    end = START_ID + len(ISSUES) - 1
    blocks = []
    new_issues_meta = []
    for i, data in enumerate(ISSUES):
        n = start + i
        iid = f"BB-{n:06d}"
        blocks.append(render_issue(n, data))
        new_issues_meta.append(
            {
                "id": iid,
                "title": data["title"],
                "severity": data["severity"],
                "priority": data["priority"],
                "category": data["category"],
                "module": data["module"],
                "status": data["status"],
            }
        )

    # Append to register
    reg = REGISTER.read_text(encoding="utf-8")
    if f"BB-{start:06d}" in reg:
        raise SystemExit(f"BB-{start:06d} already present — refuse double append")

    header_note = f"""
## Wave 14 re-audit ({TODAY})

Appended **{len(ISSUES)}** new issues `BB-{start:06d}` … `BB-{end:06d}` from independent code re-verification after Wave 13 open-closure. Prior IDs unchanged. **Invalidates Wave 13 Open==0 as a launch gate.**

"""
    # Update header totals section roughly
    sev = Counter(x["severity"] for x in new_issues_meta)
    pri = Counter(x["priority"] for x in new_issues_meta)
    cat = Counter(x["category"] for x in new_issues_meta)
    mod = Counter(x["module"] for x in new_issues_meta)

    # Merge with prior stats
    def merge_count(old: dict, add: Counter):
        out = dict(old or {})
        for k, v in add.items():
            out[k] = out.get(k, 0) + v
        return out

    new_total = prior["total"] + len(ISSUES)
    status = dict(prior.get("status") or {})
    status["Open"] = status.get("Open", 0) + len(ISSUES)
    # fix encoding dash keys
    for k in list(status.keys()):
        if "Deferred" in k and "roadmap" in k:
            status["Deferred — roadmap"] = status.pop(k)
            break

    severity = merge_count(prior.get("severity"), sev)
    priority = merge_count(prior.get("priority"), pri)
    category = merge_count(prior.get("category"), cat)
    module = merge_count(prior.get("module"), mod)

    # Patch register intro totals
    reg2 = reg
    reg2 = re.sub(
        r"(\| \*\*Total issues\*\* \| )(\d+)( \|)",
        rf"\g<1>{new_total}\3",
        reg2,
        count=1,
    )
    for label, key in [
        ("Critical", "Critical"),
        ("High", "High"),
        ("Medium", "Medium"),
        ("Low", "Low"),
    ]:
        reg2 = re.sub(
            rf"(\| {label} \| )(\d+)( \|)",
            rf"\g<1>{severity.get(key, 0)}\3",
            reg2,
            count=1,
        )
    for label, key in [("P0", "P0"), ("P1", "P1"), ("P2", "P2"), ("P3", "P3")]:
        reg2 = re.sub(
            rf"(\| {label} \| )(\d+)( \|)",
            rf"\g<1>{priority.get(key, 0)}\3",
            reg2,
            count=1,
        )
    # Status table Open row
    if "| Open |" not in reg2.split("### By Status")[1][:800]:
        reg2 = reg2.replace(
            "### By Status\n\n| Status | Count |\n|--------|------:|\n",
            "### By Status\n\n| Status | Count |\n|--------|------:|\n| Open | "
            + str(status.get("Open", 0))
            + " |\n",
            1,
        )
    else:
        reg2 = re.sub(
            r"(\| Open \| )(\d+)( \|)",
            rf"\g<1>{status.get('Open', 0)}\3",
            reg2,
            count=1,
        )

    # Insert wave note after How to use / early
    if "## Wave 14 re-audit" not in reg2:
        reg2 = reg2.replace(
            "## Wave 13 open-closure",
            header_note + "## Wave 13 open-closure",
            1,
        )

    REGISTER.write_text(reg2.rstrip() + "\n\n" + "".join(blocks), encoding="utf-8")

    stats = {
        **prior,
        "total": new_total,
        "open_count": status.get("Open", 0),
        "severity": severity,
        "priority": priority,
        "category": category,
        "module": module,
        "status": status,
        "wave14_new": len(ISSUES),
        "wave14_start": f"BB-{start:06d}",
        "wave14_end": f"BB-{end:06d}",
        "audit_date": TODAY,
        "issues": (prior.get("issues") or []) + new_issues_meta,
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # CHANGELOG prepend
    cl_block = f"""## {TODAY} — Wave 14 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Wave 13 claimed Open==0.

### Outcomes

- Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (
  Critical {sev.get('Critical', 0)} ·
  High {sev.get('High', 0)} ·
  Medium {sev.get('Medium', 0)} ·
  Low {sev.get('Low', 0)}).
- Register total: **{new_total}**.
- Status: Open **{status.get('Open', 0)}** · prior Resolved/Deferred retained.
- Invalidated Wave 13 “Open == 0” as a launch gate (see BB-000461).
- Production Readiness Score revised **6.8 → 3.4**.

### Highest new Criticals

- BB-000456 Beat healthcheck float vs ISO heartbeat (+ Redis key prefix)
- BB-000457 Gateway refund phantom unallocated advances
- BB-000458 PaymentLink stays PAID after refund
- BB-000459 Fixed asset disposal NBV → depreciation expense
- BB-000460 Return COGS reverse wrong cost basis (post-restore WAVG)
- BB-000461 Wave 13 Open==0 process invalidation
- BB-000462 ERP module claims still false vs code

### Passes re-executed

Repository structure through missed-findings (Wave 14). Script: `_wave14_reaudit_append.py`.

---

"""
    cl = CHANGELOG.read_text(encoding="utf-8")
    if "Wave 14 independent re-audit" not in cl:
        if cl.startswith("# docs/reviews"):
            lines = cl.split("\n", 2)
            CHANGELOG.write_text(lines[0] + "\n\n" + cl_block + (lines[2] if len(lines) > 2 else ""), encoding="utf-8")
        else:
            CHANGELOG.write_text(cl_block + cl, encoding="utf-8")

    # EXEC summary banner + section
    if EXEC.exists():
        text = EXEC.read_text(encoding="utf-8")
        text = re.sub(
            r"\*\*Latest:\*\*[^\n]*",
            f"**Latest:** Wave 14 independent re-audit {TODAY} — register **{new_total}** issues. "
            f"**Open: {status.get('Open', 0)}.** "
            f"Resolved {status.get('Resolved', 0)}. "
            f"Deferred — roadmap {status.get('Deferred — roadmap', status.get('Deferred \u2014 roadmap', 0))}. "
            f"Production Readiness Score **3.4 / 10**.",
            text,
            count=1,
        )
        if f"## Wave 14 re-audit ({TODAY})" not in text:
            block = f"""

---

## Wave 14 re-audit ({TODAY}) — SUPERSEDES Wave 13 “Open == 0”

Independent code re-verification **invalidated Wave 13 open-closure**. W13A–F fixed many named IDs, but **beat health format mismatch, gateway refund AR phantoms, asset disposal GL, return COGS cost basis, fetchAllPages residual, dual CSP, and false ERP claims** remain. **{len(ISSUES)} new issues** logged as `BB-{start:06d}` … `BB-{end:06d}`.

### Updated verdict

| Audience | Deploy? |
|----------|---------|
| Internal dogfood (sandbox payments off, accounting off, Owner-only, no refunds) | **Conditional** |
| Paid pilot with payments refunds / books / multi-role | **No — until Wave 14 P0 Criticals closed** |
| GA / full ERP claims | **No** |

### Scores (0–10) — Wave 14

| Dimension | Score | Notes |
|-----------|------:|-------|
| Production Readiness | **3.4** | Beat probe broken; refund AR critical; Open≠0 |
| Architecture | **4.5** | Dual ledger unresolved; god modules |
| Security | **4.0** | Cookie auth improved; CSP drift; no RLS; body JWT outside prod |
| Performance | **4.0** | fetchAllPages residual; no load proof |
| Accounting Correctness | **2.8** | Refund phantoms; disposal GL; return COGS basis |
| GST Compliance | **3.5** | Honesty gates better; live GSP/2B/CMP still absent |
| Maintainability | **4.5** | God FE/BE modules |
| Scalability | **3.5** | No RLS/load; client fetch-all |
| Testing Coverage | **5.0** | Strong BE money; weak FE/e2e cookie; no residual gates |

### Register totals (cumulative)

| Metric | Count |
|--------|------:|
| **Total issues** | **{new_total}** |
| Critical | {severity.get('Critical', 0)} |
| High | {severity.get('High', 0)} |
| Medium | {severity.get('Medium', 0)} |
| Low | {severity.get('Low', 0)} |
| **Open** | **{status.get('Open', 0)}** |

### Wave 14 P0 blockers

1. **BB-000456** — Beat healthcheck ISO/float + Redis key mismatch
2. **BB-000457 / 458** — Gateway refund AR + PaymentLink state
3. **BB-000459** — Fixed asset disposal accounting
4. **BB-000460** — Return COGS cost basis
5. **BB-000461** — Open==0 process invalidation
6. **BB-000462** — False ERP module claims

### Final CTO Verdict (Wave 14)

**Do not treat Wave 13 Open==0 as a quality gate.** Require adversarial residual tests covering beat heartbeat round-trip, gateway refund ledger invariants, asset disposal, and return COGS basis before any Open==0 claim.

**Do not enable gateway refunds** until BB-000457/458 closed.

**Do not enable accounting_enabled with fixed assets or returns** until BB-000459/460 closed.

**Do not commercially launch** as Cloud ERP with Manufacturing/Payroll/CRM/WhatsApp Business/native mobile/multi-branch/live GST Portal claims.

"""
            EXEC.write_text(text.rstrip() + block + "\n", encoding="utf-8")
        else:
            EXEC.write_text(text, encoding="utf-8")

    # Roadmap
    if ROADMAP.exists():
        text = ROADMAP.read_text(encoding="utf-8")
        if "Wave 14 hotfix" not in text:
            block = f"""

---

## Wave 14 hotfix track ({TODAY}) — P0 before any paid payments/books pilot

> Wave 13 Open==0 is **not** a launch gate. Open count now **{status.get('Open', 0)}** (`BB-{start:06d}`–`BB-{end:06d}`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Beat / observability truth | BB-000456 | Healthcheck matches heartbeat wire format + key |
| Payments refund integrity | BB-000457, BB-000458, BB-000477 | Void receipts; reopen links; partial policy |
| Books correctness | BB-000459, BB-000460, BB-000466 | Disposal GL; return COGS basis; control recon |
| FE performance / CSP | BB-000463, BB-000464 | Kill fetchAllPages; sync nginx CSP |
| Product honesty | BB-000462, BB-000467–469 | No false ERP/GSP claims |
| Process | BB-000461 | Adversarial residual gates before Open==0 |

**Exit:** Conditional dogfood with refunds disabled, accounting off or Owner-only without FA/returns COGS reliance, beat probe green.

"""
            ROADMAP.write_text(text.rstrip() + block + "\n", encoding="utf-8")

    banner = (
        f"\n\n---\n\n## Wave 14 re-audit ({TODAY})\n\n"
        f"Independent re-verification appended `BB-{start:06d}`…`BB-{end:06d}` "
        f"({len(ISSUES)} issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. "
        f"Open count: **{status.get('Open', 0)}**. "
        f"Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.\n"
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
        if f"Wave 14 re-audit ({TODAY})" in text:
            continue
        path.write_text(text.rstrip() + banner, encoding="utf-8")

    print(f"Appended {len(ISSUES)} issues BB-{start:06d}..BB-{end:06d}")
    print(f"Total {new_total}; Open {status.get('Open')}")
    print("Severity+", dict(sev))


if __name__ == "__main__":
    main()

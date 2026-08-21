#!/usr/bin/env python3
"""Generate MASTER_ISSUE_REGISTER.md and score cards for BizBoard engineering audit 2026-08-02."""
from __future__ import annotations

from datetime import date
from pathlib import Path

TODAY = "2026-08-02"
OUT = Path(__file__).resolve().parent

# Each issue: (title, category, subcategory, severity, priority, module, feature,
#   files, problem, evidence, root_cause, business, technical, customer, security,
#   performance, scalability, compliance, risk, fix_immediate, fix_short, fix_long,
#   effort, tests, acceptance, status, refs)

ISSUES: list[dict] = []


def add(**kwargs):
    ISSUES.append(kwargs)


# ─── CRITICAL ───────────────────────────────────────────────────────────────
add(
    title="DEBUG/SECRET_KEY fail-open without explicit DJANGO_ENV=production",
    category="Security",
    subcategory="Configuration",
    severity="Critical",
    priority="P0",
    module="Core",
    feature="Boot / secrets",
    files="backend/config/settings.py",
    problem="DJANGO_DEBUG defaults to 1; fail-fast secret checks only run when DJANGO_ENV=production or DJANGO_FAIL_FAST_SECRETS=1. Misconfigured deploy boots with insecure SECRET_KEY and DEBUG.",
    evidence="settings.py L17-55: default SECRET_KEY 'dev-insecure-…'; DEBUG from env default '1'; residual BUG-101 documented in comments.",
    root_cause="Zero-config local-dev preference overrides production safety by default.",
    business="Compromised JWT/session signing and Fernet-derived GSP/gateway secrets; stack traces leak.",
    technical="All crypto derived from SECRET_KEY becomes attacker-controlled.",
    customer="Tenant data exfiltration risk.",
    security="Critical configuration vulnerability.",
    performance="N/A",
    scalability="N/A",
    compliance="Fails basic SaaS hardening expectations.",
    risk="Silent production compromise.",
    fix_immediate="Require DJANGO_ENV in compose/prod; refuse boot if host is non-local and DJANGO_ENV unset.",
    fix_short="Separate settings_prod.py with no defaults; vault for secrets.",
    fix_long="KMS-backed secret rotation; image without DEBUG code paths.",
    effort="2d",
    tests="Boot tests for missing SECRET_KEY / DEBUG=1 in production env.",
    acceptance="Production image cannot start with DEBUG=1 or placeholder secret.",
    status="Open",
    refs="BUG-101; SECURITY S-01; Wave0 residual",
)
add(
    title="OTP codes stored and compared in plaintext",
    category="Security",
    subcategory="Authentication",
    severity="Critical",
    priority="P0",
    module="Accounts",
    feature="OTP login",
    files="backend/accounts/models.py; backend/accounts/views.py",
    problem="OtpChallenge.code stored plaintext; verification is direct string compare.",
    evidence="OtpChallenge model; RequestOtpView creates with code=code; verify filters by phone.",
    root_cause="MVP OTP design without hashing.",
    business="DB dump enables account takeover.",
    technical="No HMAC/hash at rest.",
    customer="Phone-based accounts fully compromised on DB leak.",
    security="Credential storage failure.",
    performance="N/A",
    scalability="N/A",
    compliance="Fails OTP storage best practice.",
    risk="Mass account takeover.",
    fix_immediate="Hash OTP with HMAC-SHA256 + pepper; constant-time compare; consume atomically.",
    fix_short="Short TTL, attempt lockout in Redis, single-use tokens.",
    fix_long="Hardware-backed OTP or provider-managed verification.",
    effort="1d",
    tests="Unit: hash stored; wrong code fails; race consume once.",
    acceptance="DB never contains recoverable OTP plaintext.",
    status="Open",
    refs="F2",
)
add(
    title="OTP debug_code can be returned in API response body",
    category="Security",
    subcategory="Authentication",
    severity="Critical",
    priority="P0",
    module="Accounts",
    feature="OTP login",
    files="backend/accounts/views.py",
    problem="When OTP_DEBUG_ECHO is on, response includes debug_code, leaking OTP via HTTP logs/proxies.",
    evidence="RequestOtpView payload['debug_code']=code when OTP_DEBUG_ECHO.",
    root_cause="Debug convenience left as HTTP field.",
    business="OTP interception via access logs.",
    technical="OTP in response body.",
    customer="Account takeover.",
    security="Critical if enabled in shared env.",
    performance="N/A",
    scalability="N/A",
    compliance="Forbidden in production.",
    risk="Staging/prod misconfig.",
    fix_immediate="Never put OTP in HTTP; console-only; CI assert OTP_DEBUG_ECHO=0 outside DEBUG.",
    fix_short="Fail boot if OTP_DEBUG_ECHO and DJANGO_ENV=production.",
    fix_long="Remove echo path entirely.",
    effort="0.5d",
    tests="API contract test: no debug_code key in any env matrix used for deploy.",
    acceptance="Response schema never includes OTP.",
    status="Open",
    refs="F3; S-01",
)
add(
    title="Payment webhook company resolution via query param + amount fallback",
    category="Security",
    subcategory="Payments",
    severity="Critical",
    priority="P0",
    module="Payments",
    feature="Gateway webhooks",
    files="backend/payments/views.py",
    problem="Webhook resolves company from ?company_id=; if missing, may auto-pick open payment link by matching amount only when unique.",
    evidence="payment_webhook L447-508: company_id query; amount-based link matching.",
    root_cause="Multi-tenant webhook routing without provider account binding first.",
    business="Mis-attributed settlements; forged capture if signature weak/sandbox.",
    technical="Settlement integrity broken.",
    customer="Wrong invoices marked paid; cash disputes.",
    security="Payment integrity / possible fraud.",
    performance="N/A",
    scalability="Ambiguous amounts increase with scale.",
    compliance="PCI/payment hygiene failure.",
    risk="Financial loss and trust collapse.",
    fix_immediate="Require verified signature tied to company credentials; reject amount-only matching; require payment_link_id in signed payload.",
    fix_short="Per-company webhook secrets; idempotency ledger.",
    fix_long="Provider account → company mapping table; mTLS.",
    effort="3d",
    tests="Adversarial webhook tests: wrong company_id, duplicate amount links, invalid signature.",
    acceptance="No settlement without cryptographically verified link identity.",
    status="Open",
    refs="F4",
)
add(
    title="E-Invoice / e-Way adapters are sandbox-only (fake IRN/EWB)",
    category="GST",
    subcategory="E-Invoice",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="E-Invoice / E-Way",
    files="backend/core/services/gsp_adapters.py",
    problem="SandboxIrpAdapter/SandboxEwayAdapter hash payloads to invent IRN/e-way numbers; no NIC/GSP HTTP.",
    evidence="gsp_adapters.py docstring 'no real NIC HTTP'; hash-based irn/bill_no.",
    root_cause="Phase 2 sandbox stub shipped with UI Submit actions.",
    business="Illegal transport/filing if treated as real; CA/legal exposure.",
    technical="No real GSP integration.",
    customer="Fake compliance documents.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical GST compliance false positive.",
    risk="Regulatory penalties if marketed as live.",
    fix_immediate="Hard-block production GSTIN; watermark PDFs 'SANDBOX'; disable Submit unless GSP_MODE=sandbox and company flag.",
    fix_short="Integrate licensed GSP; feature-flag live mode.",
    fix_long="Multi-GSP failover; cancel/amend flows per NIC rules.",
    effort="15d+ (GSP contract)",
    tests="Assert sandbox watermark; refuse live without credentials.",
    acceptance="No fake IRN visible as production success.",
    status="Open",
    refs="F5; G43",
)
add(
    title="SMS provider is console stub; production OTP channel missing",
    category="Security",
    subcategory="Authentication",
    severity="Critical",
    priority="P0",
    module="Accounts",
    feature="OTP / SMS",
    files="backend/core/services/sms.py; backend/accounts/views.py",
    problem="SMS is console-only; RequestOtp gated on OTP_DEBUG_ECHO for send path.",
    evidence="sms.py stub; RequestOtpView L157-160.",
    root_cause="MVP communications stubs.",
    business="Phone login unusable in production.",
    technical="Auth channel incomplete.",
    customer="Cannot use OTP login.",
    security="False sense of SMS auth.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Broken mobile onboarding.",
    fix_immediate="Keep OTP UI disabled (VITE_ENABLE_OTP unset) until provider wired.",
    fix_short="MSG91/Twilio with DLT templates.",
    fix_long="Multi-provider failover + delivery receipts.",
    effort="5d",
    tests="Integration mock provider; no success without send ACK.",
    acceptance="OTP request fails closed without real SMS provider in prod.",
    status="Open",
    refs="F6; S-05",
)
add(
    title="Composition/unregistered companies can issue full GST tax invoices",
    category="GST",
    subcategory="Registration type",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Invoice complete",
    files="backend/core/services/billing.py; backend/core/services/place_of_supply.py; backend/accounts/models.py",
    problem="Tax engine gates on tax_enabled, not registration_type. Composition only blocked at GSTR export.",
    evidence="place_of_supply.py intentionally gates on tax_enabled; gst_returns composition block at export only.",
    root_cause="Incomplete registration-type enforcement.",
    business="Illegal tax invoices; assessment risk.",
    technical="Wrong document type for composition.",
    customer="Invalid GST invoices issued to buyers.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical GST rule violation.",
    risk="Penalties + buyer ITC disputes.",
    fix_immediate="Hard-block GST/TAX invoice types for COMPOSITION/UNREGISTERED on Complete.",
    fix_short="Bill of Supply + CMP rate engine.",
    fix_long="CMP-08 / GSTR-4 worksheets.",
    effort="5d",
    tests="Composition cannot complete GST invoice; unregistered cannot charge GST.",
    acceptance="Only REGULAR/SEZ-appropriate types produce CGST/SGST/IGST invoices.",
    status="Open",
    refs="G10; G41; F75; F76",
)
add(
    title="Sales returns invisible to GSTR-1 CDNR and missing GL postings",
    category="GST",
    subcategory="Returns",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="Sales returns",
    files="backend/reporting/gst_returns.py; backend/sales/services.py; backend/accounting/services.py",
    problem="GSTR builders import CN/DN only; SalesReturn reduces AR ledger but never appears in CDNR and never posts GL → BooksHealth control drift.",
    evidence="gst_returns.py CN/DN queries; no SalesReturn; complete_return has no PostingService.",
    root_cause="Returns treated as stock/AR only, not statutory credit documents.",
    business="Understated credit notes in returns; wrong GSTR; books ≠ party ledger.",
    technical="Dual-ledger divergence.",
    customer="Wrong outstanding + wrong returns filing.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical GSTR incompleteness.",
    risk="Failed CA filing season.",
    fix_immediate="Auto-generate SalesCreditNote on return complete OR include returns in CDNR; post GL.",
    fix_short="Single economic document linking return↔CN.",
    fix_long="Full CDNR with stock and value paths.",
    effort="8d",
    tests="Return complete → CDNR row + GL reverse sales/tax + AR match.",
    acceptance="Return cycle appears in GSTR aid and balances BooksHealth.",
    status="Open",
    refs="G12; G26; G30",
)
add(
    title="GSTR-3B ITC = all purchase tax with no eligibility / 2B matching",
    category="GST",
    subcategory="ITC",
    severity="Critical",
    priority="P0",
    module="Reporting",
    feature="GSTR-3B",
    files="backend/reporting/gst_returns.py",
    problem="ITC computed as sum of non-RCM purchase taxes; no Sec 17 / Rule 36/37 / GSTR-2B match.",
    evidence="gst_returns.py L528-557, 609-612; manual_review placeholders only.",
    root_cause="Books-only ITC approximation.",
    business="Overclaimed ITC → notices.",
    technical="No ITC register.",
    customer="Wrong 3B if auto-filed.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical if product claims filing readiness.",
    risk="Assessment + interest.",
    fix_immediate="Label ITC as 'provisional / manual review'; never auto-claim language.",
    fix_short="ITC register with eligibility flags.",
    fix_long="GSP GSTR-2B import + match engine.",
    effort="20d+",
    tests="Fixture where ineligible purchase tax excluded from suggested ITC.",
    acceptance="UI shows provisional; 2B match before claim suggestion.",
    status="Open",
    refs="G17; G19; G48",
)
add(
    title="RCM purchases post GL with tax=0 — no RCM liability or ITC",
    category="Accounting",
    subcategory="RCM posting",
    severity="Critical",
    priority="P0",
    module="Accounting",
    feature="Purchase posting",
    files="backend/core/services/billing.py; backend/accounting/services.py",
    problem="RCM memo zeroes charged tax; PostingService uses zeroed totals → no Cr RCM payable / Dr ITC.",
    evidence="apply_rcm_memo_after_tax; post_purchase uses cgst/sgst/igst totals.",
    root_cause="RCM implemented for 3B memo only, not dual-entry.",
    business="Books understate GST liability.",
    technical="Incomplete posting matrix.",
    customer="Wrong books for CA.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical accounting + GST books failure.",
    risk="Failed audit.",
    fix_immediate="When accounting_enabled, post from rcm_* fields.",
    fix_short="Split CGST/SGST/IGST RCM payable accounts.",
    fix_long="RCM reason codes + eligibility.",
    effort="5d",
    tests="RCM purchase → balanced JV with liability = rcm tax.",
    acceptance="BooksHealth and 3B RCM agree.",
    status="Open",
    refs="G24",
)
add(
    title="H9 amend rewrites completed GST invoices without period close block or GL repost",
    category="GST",
    subcategory="Amendments",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="H9 amend",
    files="backend/core/services/h9_amend.py; backend/sales/serializers.py; backend/reporting/gst_periods.py; backend/accounting/services.py",
    problem="Price amend on completed docs allowed; soft-closed GST period only warns; GL journals not reversed/reposted.",
    evidence="gst_periods warn-only; amend path set_items without PostingService.reverse.",
    root_cause="Pilot correction path without statutory hard gates.",
    business="Post-filing books/GSTR drift.",
    technical="Stale journals + dirty snapshots.",
    customer="Wrong outstanding and tax history.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical period integrity failure.",
    risk="Filed returns become irreconcilable.",
    fix_immediate="Block H9 money changes when period SOFT_CLOSED/CLOSED; require CN instead.",
    fix_short="On allowed amend: reverse+repost GL; regenerate snapshot version.",
    fix_long="Amendment register with portal amendment flow.",
    effort="6d",
    tests="Closed period reject; open period amend reposts GL.",
    acceptance="No silent rewrite of filed-period taxable values.",
    status="Open",
    refs="G22; G27; G46; F20; F53",
)
add(
    title="E-invoice payload missing ValDtls and uses float amounts",
    category="GST",
    subcategory="E-Invoice schema",
    severity="Critical",
    priority="P0",
    module="Sales",
    feature="E-Invoice payload",
    files="backend/sales/einvoice_payload.py",
    problem="Payload builds ItemList without mandatory ValDtls (AssVal, tax vals, TotInvVal, RndOffAmt); _num casts to float; Pin hardcoded 0.",
    evidence="einvoice_payload.py L70-150.",
    root_cause="Incomplete NIC schema mapping in sandbox path.",
    business="Would be rejected by real IRP; sandbox hides defect.",
    technical="Schema non-compliance.",
    customer="Cannot go live on e-invoice.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Critical for e-invoice mandate.",
    risk="Launch blocker for AATO taxpayers.",
    fix_immediate="Implement full ValDtls; Decimal string serialization; validate 6-digit PIN.",
    fix_short="Schema validator against NIC 1.1 JSON Schema.",
    fix_long="Certified GSP payload builder.",
    effort="5d",
    tests="Golden payload fixtures vs NIC samples.",
    acceptance="Payload validates against NIC schema offline.",
    status="Open",
    refs="G43; G44; G45",
)
add(
    title="VITE_USE_MOCKS can ship fake auth and fake books UI",
    category="Security",
    subcategory="Frontend config",
    severity="Critical",
    priority="P0",
    module="Web",
    feature="Mock mode",
    files="web/src/api/client.ts; web/src/api/auth.ts; web/.env.e2e",
    problem="Mock mode bypasses API auth and invents money writes; production misconfig presents fake ERP.",
    evidence="VITE_USE_MOCKS branches; mock tokens accepted as logged in.",
    root_cause="Dev/e2e convenience without prod build strip.",
    business="Catastrophic if deployed.",
    technical="Dual code paths.",
    customer="Fake data believed real.",
    security="Auth bypass in UI.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Deploy with mocks enabled.",
    fix_immediate="CI/build fail if VITE_USE_MOCKS in production build; tree-shake mocks.",
    fix_short="Separate mock entrypoint never in Docker web image.",
    fix_long="MSW only in test projects.",
    effort="2d",
    tests="Production vite build assert no mock strings.",
    acceptance="Prod image cannot enable mocks.",
    status="Open",
    refs="FE-46",
)
add(
    title="Pilot Go/No-Go gates unsigned while UI exposes full GST/books/AI suite",
    category="Process",
    subcategory="Go-live",
    severity="Critical",
    priority="P0",
    module="Product",
    feature="Commercial launch",
    files="docs/pilot/GO_NO_GO.md; web/src/navigation/menu.ts; docs/pilot/ONBOARDING.md",
    problem="GO_NO_GO signature tables blank; nav exposes GSTR/e-invoice/TB/AI/Tally while ONBOARDING says those are not claimed.",
    evidence="Empty GO_NO_GO.md; menu.ts full suite; ONBOARDING contradictions.",
    root_cause="Phase 1–7 engineering proceeded before Phase 0 human Go.",
    business="Customers treat sandbox as production-ready.",
    technical="Feature surface ≫ validated surface.",
    customer="Expectation and compliance mismatch.",
    security="Ops gates (TLS, backups) unsigned.",
    performance="N/A",
    scalability="N/A",
    compliance="Process + honesty failure.",
    risk="Paid pilot without CA/TLS/backup.",
    fix_immediate="Feature-flag non-pilot modules; complete GO_NO_GO signatures; refresh ONBOARDING.",
    fix_short="Pilot tier config per company.",
    fix_long="Release train with signed gates.",
    effort="3d + human gates",
    tests="N/A (process); smoke that flagged modules hidden.",
    acceptance="Paid traffic only after GO_NO_GO green.",
    status="Open",
    refs="DevOps-1; DevOps-2",
)
add(
    title="No TLS termination at application edge",
    category="Security",
    subcategory="Transport",
    severity="Critical",
    priority="P0",
    module="DevOps",
    feature="Deploy",
    files="nginx/default.conf; docker-compose.yml",
    problem="nginx listens on :80 only; compose maps HTTP port; GSTIN/PII/JWT can travel cleartext.",
    evidence="listen 80; APP_PORT:-80.",
    root_cause="Local-dev compose reused as deploy baseline.",
    business="PII interception.",
    technical="No HSTS at app edge.",
    customer="Credential theft risk on LAN/public IP.",
    security="Critical for any internet-facing pilot.",
    performance="N/A",
    scalability="N/A",
    compliance="DPDP/data in transit.",
    risk="Mandatory for paid pilot with real GSTIN.",
    fix_immediate="Terminate TLS at LB/Caddy; force HTTPS redirects.",
    fix_short="Cert automation; HSTS.",
    fix_long="mTLS for webhooks.",
    effort="2d ops",
    tests="TLS probe in deploy checklist.",
    acceptance="HTTP redirects; valid cert on pilot host.",
    status="Open",
    refs="S-08; DevOps-3; GO E1",
)

# ─── HIGH (batch) ───────────────────────────────────────────────────────────
HIGH = [
    ("Dual AR/AP ledger vs optional GL can diverge", "Accounting", "Dual truth", "Accounting", "BooksHealth", "backend/accounting/services.py; backend/ledgers/services.py", "Document-derived AR/AP and optional GL postings can diverge when posts skipped/returns missing.", "BooksHealthService; accounting_enabled default False.", "Optional GL + incomplete posting coverage.", "Wrong P&L vs party statements.", "Make posting mandatory when accounting on; nightly reconcile; block complete if post fails.", "5d", "F7; F8"),
    ("Child rows lack company_id (JournalLine, DocumentLine, PriceListItem)", "Security", "Tenancy", "Accounting", "Models", "backend/accounting/models.py; backend/core/models.py; backend/masters/models.py", "Child lines rely on parent FK only; harder RLS/IDOR defense.", "JournalLine without company; DocumentLineModel abstract without company.", "Normalization without denormalized tenant key.", "Cross-tenant risk if any pk-only filter.", "Denormalize company_id + DB constraints; assert match in serializers.", "4d", "F9; F62"),
    ("Coarse RBAC: staff can create/complete invoices/payments without fine-grained write flags", "Security", "Authorization", "Accounts", "RBAC", "backend/core/viewsets.py; backend/accounts/models.py; web/src/App.tsx", "Only cancel/reports/export/AI gated; sales/purchase/payment writes open to any staff.", "CompanyScopedViewSet IsAuthenticated+HasCompany; App routes ungated for money flows.", "MVP two-role model.", "Cashiers get accountant powers.", "Add can_create_sales|purchases|payments; enforce BE+FE.", "5d", "F10; FE-27"),
    ("Credit-limit check has accepted concurrent race", "Business Logic", "Credit control", "Sales", "Complete invoice", "backend/sales/services.py", "Concurrent completes for same customer can exceed credit limit.", "Comment L324-338 accepted race.", "No select_for_update on customer.", "Over-limit AR.", "Advisory lock or select_for_update on customer row.", "2d", "F11"),
    ("Purchase return purchase_invoice nullable", "GST", "Purchases", "Purchases", "Purchase returns", "backend/purchases/models.py", "Orphan returns distort AP/GSTR.", "PurchaseReturn.purchase_invoice null=True.", "Flexible MVP model.", "Wrong supplier outstanding.", "Require link for GST returns; qty ≤ invoice.", "2d", "F12; G35"),
    ("Quotation/CN/DN/Order/Challan lack unique document numbers", "Business Logic", "Document numbers", "Sales", "Numbering", "backend/sales/models.py; backend/purchases/models.py", "Only invoices have UniqueConstraint on number; other docs blankable without uniqueness.", "Model Meta constraints inventory.", "Incomplete uniqueness migration.", "GST filing chaos / duplicates.", "Conditional unique like invoices for all numbered docs.", "3d", "F13"),
    ("PaymentAllocation missing XOR/uniqueness CheckConstraints", "Business Logic", "Allocations", "Payments", "Allocations", "backend/payments/models.py", "No DB constraint that exactly one receipt/supplier_payment and one invoice side set.", "PaymentAllocation model.", "Validation only in service.", "Corrupt allocations via API edge cases.", "CheckConstraints + unique (receipt, sales_invoice).", "2d", "F14"),
    ("GSP/gateway Fernet keys derived from SECRET_KEY", "Security", "Secrets", "Core", "GSP secrets", "backend/core/services/gsp_secrets.py; backend/config/settings.py", "Optional GSP_FERNET_KEY; else derived from SECRET_KEY.", "settings GSP_FERNET_KEY comment.", "Convenience default.", "Secret rotation invalidates/exposes credentials.", "Dedicated KMS/Fernet key with versioning.", "3d", "F15"),
    ("IntegrityError details leaked to API clients", "Security", "Error handling", "Core", "Exceptions", "backend/core/exceptions.py", "details: str(exc) exposes schema/constraint info.", "exceptions.py L40-54.", "Debug-friendly handler.", "Information disclosure.", "Generic client message; log server-side.", "0.5d", "F16"),
    ("Media served when DEBUG=True", "Security", "Files", "Core", "Media", "backend/config/urls.py", "static/media served in DEBUG; unauthenticated if DEBUG left on.", "urls.py L52-53.", "Django default pattern.", "File leak.", "Always auth'd FileAsset + object storage.", "2d", "F17"),
    ("WhatsApp is wa.me link only; IntegrationConnection.WHATSAPP unused", "Integration", "WhatsApp", "Integrations", "Notifications", "backend/core/services/notifications.py; backend/integrations/", "No WhatsApp Business API; marketing may imply delivery.", "notifications wa.me; Phase 7.1 not done.", "Stub channel.", "Broken share promises.", "Label honestly or implement Cloud API.", "10d+", "F18; FE-50"),
    ("E-invoice AATO / enablement client-controlled", "GST", "E-Invoice", "Accounts", "Company settings", "backend/accounts/models.py", "einvoice_enabled and aato_turnover editable without verification.", "Company fields.", "Trust-client settings.", "Incorrect compliance posture.", "Server-side AATO rules; verify GSTIN.", "3d", "F19"),
    ("Seed commands ship known passwords", "Security", "Ops", "Accounts", "seed_demo", "backend/accounts/management/commands/seed_demo.py; seed_pilot_fixtures.py", "DemoPass123! / PilotPass123! known.", "Seed command code.", "Demo convenience.", "Trivial takeover if run on shared env.", "Refuse in production; random passwords.", "0.5d", "F21"),
    ("Login lockout may use LocMem cache (ineffective multi-worker)", "Security", "Auth", "Accounts", "Login", "backend/accounts/views.py; backend/config/settings.py", "Fail counter in Django cache without forced Redis backend.", "cache-based lockout.", "Default cache config.", "Brute force across workers.", "Redis cache backend in production.", "1d", "F22"),
    ("JWT access/refresh tokens stored in localStorage", "Security", "Session", "Web", "Auth", "web/src/auth/session.ts", "XSS can exfiltrate session up to refresh TTL.", "session.ts storage keys.", "SPA JWT pattern.", "Full account takeover via XSS.", "httpOnly cookies+CSRF or strict CSP + accept-risk signed.", "5d", "S-02; FE-1; GO A11"),
    ("Accounting routes lack RoleRoute; staff can open journals via URL", "Security", "Frontend RBAC", "Web", "Accounting", "web/src/App.tsx", "Accounting pages only nav-hidden by accountingEnabled.", "App.tsx accounting routes.", "Incomplete FE gates.", "Unauthorized books viewing.", "Wrap with canViewFinancialReports/owner.", "1d", "FE-28"),
    ("Client POS-unknown treated as intra for tax preview", "GST", "Frontend tax", "Web", "Invoice editor", "web/src/utils/tax.ts", "isIntraState treats unknown as intra → wrong CGST/SGST preview.", "tax.ts isIntraState.", "Preview convenience.", "User completes with wrong expectation.", "Show POS unknown; zero tax until known.", "1d", "FE-15; G3"),
    ("fetchAllPages loads up to 200 pages into memory", "Performance", "API client", "Web", "Lists", "web/src/api/resources.ts", "Large tenants risk OOM/slow UI.", "resources.ts fetchAllPages.", "MVP list convenience.", "Browser hang.", "Paginated tables / infinite scroll.", "4d", "FE-11; FE-37"),
    ("Share links opened without URL allowlist", "Security", "XSS/Open redirect", "Web", "Share", "web/src/pages/sales/InvoiceDetailPage.tsx; PhasePages", "window.open(shareLink)/href without allowlist.", "InvoiceDetail share handlers.", "Trust API URL.", "javascript: / open redirect if poisoned.", "Allowlist https://wa.me and known domains.", "1d", "FE-43"),
    ("Missing Manufacturing / Payroll / CRM / Multi-company / Multi-branch claimed modules", "Product", "Scope honesty", "Product", "Roadmap", "docs/; README.md; PHASE*_IMPLEMENTATION_PLAN.md", "Audit prompt claims modules; codebase lacks Manufacturing BOM, Payroll, CRM pipeline, multi-GSTIN branch, native mobile.", "No apps for manufacturing/payroll/CRM; one CompanyUser active; warehouses≠branches.", "Roadmap vs marketing confusion.", "Expectation mismatch; failed demos.", "Honest feature matrix; remove claims until built.", "1d docs + roadmap", "F77-F82"),
    ("No GSTR-2A/2B reconciliation module", "GST", "ITC matching", "Reporting", "GSTR", "backend/reporting/", "No portal pull or match UI.", "Absence of 2A/2B code.", "Phase incompleteness.", "ITC mismatch risk.", "GSP 2B import + match.", "25d+", "G19; F94"),
    ("Additional charges never taxed", "GST", "Valuation", "Sales", "Billing", "backend/core/services/billing.py", "Freight/packing added post-tax; often part of taxable value under Sec 15.", "billing.py L284-291 comment Phase 0.", "Scoped Phase 0 exclusion.", "Understated outward tax.", "Configurable charge GST / BEFORE_TAX allocation.", "4d", "G1"),
    ("AFTER_TAX discount breaks GSTR invoice-value identity", "GST", "Discounts", "Sales", "Billing", "backend/core/services/billing.py; backend/reporting/gst_returns.py", "Cash discount after GST excluded from B2B sections but still issued.", "INVOICE_VALUE_MISMATCH flag.", "Commercial discount vs GSTN model tension.", "Filing gaps.", "Prefer BEFORE_TAX for B2B; or force CN.", "3d", "G2; G16"),
    ("No Cess / Compensation Cess support", "GST", "Tax types", "Core", "Billing", "backend/core/models.py", "Only CGST/SGST/IGST fields.", "DocumentTotalsModel.", "MSME rate set without cess.", "Cannot bill cess goods correctly.", "Add cess fields + GSTR/e-invoice.", "5d", "G8"),
    ("No SEZ / export / deemed-export supply types", "GST", "Supply type", "Sales", "E-Invoice", "backend/sales/einvoice_payload.py", "SupTyp hard-coded B2B; binary intra/inter only.", "einvoice_payload.py.", "Domestic B2B focus.", "Exporters unsupported.", "Supply-type enum + tax rules.", "10d", "G9"),
    ("Single Output GST / Input GST accounts — no CGST/SGST/IGST split", "Accounting", "Chart of accounts", "Accounting", "Posting", "backend/accounting/services.py", "Lumped tax control accounts.", "Chart 1300/2200.", "Simplified CoA.", "Cannot reconcile cash ledger by head.", "Split tax accounts.", "3d", "G23"),
    ("Purchases always expense 5100 never inventory 1400", "Accounting", "Inventory accounting", "Accounting", "Posting", "backend/accounting/services.py", "Dr Purchases expense; COGS on sale from unit_cost → perpetual inventory mismatch risk.", "post_purchase Debit 5100.", "Simplified trading books.", "Wrong stock vs P&L.", "Dr Inventory on purchase.", "4d", "G29"),
    ("Double relief if both SalesReturn and SalesCreditNote for same return", "Accounting", "AR", "Ledgers", "Outstanding", "backend/ledgers/services.py", "Both subtract from outstanding.", "customer_outstanding formula.", "Independent document types.", "Over-credit customer.", "Mutual exclusion or linked documents.", "3d", "G32"),
    ("pip-audit non-blocking in CI", "DevOps", "CI", "CI", "Dependencies", ".github/workflows/ci.yml", "pip-audit ... || true never fails job.", "ci.yml backend step.", "Avoid flaky CI.", "CVEs ship unnoticed.", "Fail on high/critical; pin upgrades.", "1d", "DevOps-12"),
    ("No automated backups / restore drill in compose", "DevOps", "Reliability", "Ops", "Backups", "docs/; docker-compose.yml", "Manual pg_dump only; ENV checklist blank.", "RUNBOOKS; GO_NO_GO.", "Pilot ops gap.", "Total data loss.", "Cron encrypted off-host dumps; dated restore drill.", "3d", "DevOps-10"),
    ("Celery beat missing from docker-compose", "DevOps", "Scheduling", "Ops", "Celery", "docker-compose.yml; backend/config/settings.py", "CELERY_BEAT_SCHEDULE defined but no beat service.", "compose api/worker only.", "Incomplete compose.", "Insights/depreciation never schedule.", "Add beat service.", "0.5d", "DevOps-16"),
    ("Observability insufficient (shallow health, no APM)", "DevOps", "SRE", "Ops", "Monitoring", "backend/core/views.py; docs/", "Health returns ok only; no DB/Redis/Celery; no Sentry/OTel.", "HealthView; RUNBOOKS.", "MVP ops.", "Silent PDF/worker failures.", "Deep health; uptime; queue metrics; Sentry.", "5d", "DevOps-11"),
    ("SMTP/email console stub; share invoice unreliable", "Integration", "Email", "Core", "Notifications", "backend/core/services/notifications.py; settings", "Console email unless SMTP configured.", "SMS/email stubs.", "MVP.", "Broken share for customers.", "Require SMTP in prod or disable share.", "2d", "DevOps-9"),
    ("GSTR-9 is FY outward summary aid only — not annual return", "GST", "GSTR-9", "Reporting", "GSTR-9", "backend/reporting/gst_returns.py", "build_gstr9 sums monthly outward only.", "gst_returns.py L634-702.", "Aid scope.", "Misuse as GSTR-9.", "Rename UI; expand or hide.", "2d docs / 15d full", "G20"),
    ("Missing CMP-08 / GSTR-4 for composition", "GST", "Composition", "Reporting", "Composition returns", "backend/reporting/gst_returns.py", "Composition blocked from regular packs; no alternative.", "Error text admits absence.", "Regular dealer focus.", "Composition customers unsupported.", "CMP engine + worksheets.", "12d", "G21"),
    ("Stale root reports contradict Wave0/code reality", "Documentation", "Truthfulness", "Docs", "Reports", "PRODUCTION_READINESS.md; SECURITY_REPORT.md; BUG_REPORT.md; phase plans", "July 24 reports claim open Criticals that are fixed; phase §0 tables say ❌ while status Implemented.", "Date stamps 2026-07-24 vs WAVE0 2026-08-02.", "Docs not archived.", "Wrong prioritization.", "Mark Historical; point to docs/reviews + bugs/INDEX.", "1d", "DevOps-13"),
    ("Phase 1–7 shipped before Phase 0 Go (process breach)", "Process", "Governance", "Product", "Phases", "docs/pilot/PHASE1_ENGINEERING_PROCEED.md; PHASE*_IMPLEMENTATION_PLAN.md", "Plans forbid coding Phase 1+ before Go; code delivered anyway.", "PHASE1_ENGINEERING_PROCEED.", "Engineering velocity vs gate.", "Unvalidated money/GST surface area.", "Hard feature flags until Go.", "2d", "DevOps-2"),
    ("User object trusted from localStorage without /auth/me revalidation", "Security", "Auth", "Web", "Session", "web/src/auth/AuthContext.tsx", "Stale roles/capabilities after server revoke.", "getStoredUser on boot.", "Offline-first session.", "Privilege persistence.", "Call /auth/me on load.", "1d", "FE-2"),
    ("zod / hookform resolvers unused — weak form validation", "Frontend", "Validation", "Web", "Forms", "web/package.json", "Deps declared never imported.", "grep empty for zod imports.", "Incomplete adoption.", "Weak GSTIN/IFSC validation.", "Wire schemas or remove deps.", "3d", "FE-20"),
    ("No company/tenant header for future multi-company", "Architecture", "Multi-tenancy", "Web", "API client", "web/src/api/client.ts", "Only Authorization; no X-Company-Id.", "client.ts interceptors.", "Single membership assumption.", "Blocks Phase 7.2.", "Add header when multi-company lands.", "2d", "FE-7"),
    ("E-invoice Unit uses unit_name not UQC; IsServc/RegRev hard-coded", "GST", "E-Invoice", "Sales", "Payload", "backend/sales/einvoice_payload.py", "Unit not GSTN UQC; IsServc N; RegRev N always.", "einvoice_payload.py L102-121.", "Incomplete mapping.", "IRP reject.", "Map UQC; derive service/RCM flags.", "2d", "G44"),
]
for t, cat, sub, mod, feat, files, problem, evidence, root, business, fix, effort, refs in HIGH:
    add(
        title=t,
        category=cat,
        subcategory=sub,
        severity="High",
        priority="P1",
        module=mod,
        feature=feat,
        files=files,
        problem=problem,
        evidence=evidence,
        root_cause=root,
        business=business,
        technical=problem,
        customer=business,
        security="See category" if cat == "Security" else "N/A",
        performance="See category" if cat == "Performance" else "N/A",
        scalability="See category" if "scale" in problem.lower() else "N/A",
        compliance="See category" if cat == "GST" else "N/A",
        risk="Material if ignored in commercial launch.",
        fix_immediate=fix.split(";")[0] if ";" in fix else fix,
        fix_short=fix,
        fix_long="Architectural follow-through per remediation roadmap.",
        effort=effort,
        tests=f"Regression covering: {t}",
        acceptance=f"Issue resolved: {t}",
        status="Open",
        refs=refs,
    )

# ─── MEDIUM ─────────────────────────────────────────────────────────────────
MEDIUM = [
    ("No soft-delete for customers/suppliers; hard destroy", "Data", "Masters", "masters/", "Accidental data loss; PROTECT 500s", "Soft-delete mixin; forbid delete if referenced", "2d", "F23"),
    ("StockMovement not CompanyScopedModel", "Architecture", "Inventory", "inventory/models.py", "Inconsistent tenancy helpers", "Align mixin", "1d", "F24"),
    ("WARN negative stock still posts", "Inventory", "Policy", "inventory/services.py", "Silent negative inventory", "Mandatory UI ack; negative report", "2d", "F25"),
    ("Reserved stock always 0; SO does not reserve", "Inventory", "Reservations", "inventory/", "Over-selling against open orders", "Reserve on confirm", "5d", "F26"),
    ("Delivery challan does not move stock", "Inventory", "Challan", "sales/", "Goods out without stock if challan-only", "Optional stock-on-challan mode", "3d", "F27"),
    ("FIFO valuation setting may not fully drive costing", "Inventory", "Valuation", "inventory/", "Wrong COGS", "FIFO layer table + tests", "8d", "F28"),
    ("Place of supply free-text state equality fragile", "GST", "POS", "billing.py", "KA vs Karnataka misclassification", "Mandate state codes", "3d", "G4; G5"),
    ("GstReturnSnapshot lacks unique constraint", "Database", "GSTR", "reporting/models.py", "Duplicate snapshots", "UniqueConstraint", "1d", "F31"),
    ("Bank statement line_hash not unique", "Database", "Banking", "payments/models.py", "Duplicate imports", "Unique (company, bank, hash)", "1d", "F32"),
    ("Public payment link privacy if token leaks", "Security", "Payments", "payments/views.py", "Invoice number & UPI exposure", "High-entropy tokens; expiry; rate limit", "2d", "F33"),
    ("Celery email task swallows errors / no retry", "Reliability", "Celery", "core/tasks.py", "Lost emails", "autoretry_for; FAILED status", "1d", "F34"),
    ("Insights beat iterates companies sequentially", "Performance", "AI", "insights/tasks.py", "Long beat tasks", "Fan-out per company", "2d", "F35"),
    ("OCR/LLM sends bill PII to third parties", "Security", "Privacy", "core/services/llm.py", "DPDP risk", "Redact; consent; budget; retention", "4d", "F37"),
    ("Assistant confirm path prompt-injection risk", "Security", "AI", "insights/assistant.py", "Unintended writes", "Allowlist actions; re-auth money moves", "5d", "F38"),
    ("File upload allows application/octet-stream", "Security", "Uploads", "core/services/files.py", "Malware staging", "Stricter sniff; scan", "2d", "F39"),
    ("Django admin exposed at /admin/", "Security", "Admin", "config/urls.py", "Attack surface", "IP allowlist / MFA / disable", "1d", "F40"),
    ("ENABLE_API_DOCS defaults to 1", "Security", "API", "config/settings.py", "Schema leakage", "Default 0 in prod", "0.5d", "F43"),
    ("SQLite default encourages wrong production DB", "Database", "Config", "config/settings.py", "Lost locking guarantees", "Fail prod without Postgres", "1d", "F44; F45"),
    ("N+1 risk residual in ledger statement building", "Performance", "Ledgers", "ledgers/services.py", "Slow party ledgers", "Bulk annotate allocations", "2d", "F46"),
    ("float in einvoice payload and insights scores", "Correctness", "Money", "einvoice_payload.py; insights/", "Paise / JSON rounding risk", "Decimal until serialize", "2d", "F48"),
    ("Tally opening invoices skip credit limit & PDF magic string", "Integration", "Tally", "sales/services.py", "Fragile convention", "Explicit source=TALLY flag", "2d", "F50"),
    ("Company docstring single warehouse vs multi-warehouse", "Documentation", "Inventory", "accounts/models.py", "Product confusion", "Update docs; Branch≠Warehouse", "0.5d", "F51"),
    ("BankAccount.is_default race (no unique partial constraint)", "Database", "Banking", "payments/models.py", "Two defaults", "Partial UniqueConstraint", "1d", "F52"),
    ("Purchase CN/DN optional invoice link", "GST", "Purchases", "purchases/models.py", "Weak GSTR-2 linkage", "Require for GST-registered", "2d", "F54"),
    ("SerialNumber receive loop partial creates", "Concurrency", "Inventory", "inventory/", "Partial serial creates", "Wrap receive in atomic", "1d", "F55"),
    ("Register creates company with empty GSTIN", "Business Logic", "Onboarding", "accounts/views.py", "Incomplete GST setup", "Onboarding checklist gate", "2d", "F57"),
    ("Search may leak invoice numbers without financial capability", "Security", "Search", "search/views.py", "Staff sees financials via search", "Filter by capabilities", "2d", "F59"),
    ("Mass assignment residual if company writable on serializers", "Security", "API", "serializers", "Tenant spoof attempts", "Read-only company everywhere; audit Meta.fields", "2d", "F88"),
    ("Non-CompanyScopedViewSet IDOR residual risk", "Security", "API", "accounting/; payments/", "Must not skip company filter", "Audit every custom ViewSet", "3d", "F89"),
    ("Migration HSN/UQC backfills scan all products", "Database", "Migrations", "sales/; purchases/ migrations", "Long locks", "Batched RunPython", "2d", "F90"),
    ("CELERY_TASK_ALWAYS_EAGER possible in prod", "DevOps", "Celery", "settings", "PDF/email blocks requests", "Forbid eager in production", "0.5d", "F91"),
    ("Inclusive taxable stash lost on re-save drift", "GST", "Inclusive pricing", "billing.py", "AssAmt drift on re-open", "Persist extracted taxable", "2d", "G7"),
    ("Filing overlays can diverge from tax at Complete", "GST", "Filing", "gst_returns.py; einvoice_payload.py", "Wrong tax vs filing POS", "Force recompute or CN on POS change", "3d", "G11"),
    ("Missing GSTR-1 EXP/SEZ/AT/SUPECOM/DOC detail tables", "GST", "GSTR-1", "gst_returns.py", "Cannot full-file GSTR-1", "Implement or label aid-only", "15d", "G13"),
    ("Nil-rated section is 0% lines only", "GST", "GSTR-1", "gst_returns.py", "Nil/exempt/non-GST conflated", "Supply-type flags", "3d", "G14"),
    ("B2CL threshold uses grand_total including tax", "GST", "GSTR-1", "gst_returns.py", "Classification skew", "Document GSTN definition; align", "1d", "G15"),
    ("Mismatch invoices excluded from B2B but inflate 3B", "GST", "GSTR-3B", "gst_returns.py", "CA pack inconsistency", "Same exclusion set", "2d", "G16"),
    ("RCM not shown as explicit 3.1(d) block", "GST", "GSTR-3B", "gst_returns.py", "CA confusion", "Explicit 3.1(d) section", "2d", "G18"),
    ("Sales/purchase GL ignore round_off / AFTER_TAX structure", "Accounting", "Posting", "accounting/services.py", "Revenue distortion", "Explicit round_off/discount lines", "3d", "G25"),
    ("Soft-closed accounting period not enforced on post", "Accounting", "Periods", "accounting/services.py", "Posts after soft-close", "Block or Owner override", "1d", "G28"),
    ("Outstanding can go negative (no floor)", "Accounting", "Ledgers", "ledgers/services.py", "Confusing statements", "Clamp display; block over-CN", "2d", "G31"),
    ("Customer statement date filter drops opening balance", "Accounting", "Ledgers", "ledgers/services.py", "Wrong period statements", "Compute brought-forward", "2d", "G33"),
    ("Statement balance vs outstanding naming confusion", "Accounting", "Ledgers", "ledgers/services.py", "CA confusion on advances", "Show balance due vs ledger balance", "2d", "G34"),
    ("DN cumulative cap missing (vs invoice grand_total only)", "Business Logic", "Debit notes", "sales/notes_services.py", "Multiple DNs exceed uplift", "Cap cumulative DN−CN", "2d", "G36"),
    ("Notes use current party POS not invoice snapshot", "GST", "Credit notes", "notes_services.py", "CDNR tax split mismatch", "Inherit invoice filing POS", "2d", "G37"),
    ("Note complete posts GL only in view not service", "Accounting", "Notes", "phase1_views.py; notes_services.py", "Import path skips GL", "Post inside service", "1d", "G38"),
    ("RCM boolean only — no 9(3)/9(4) categories", "GST", "RCM", "purchases/models.py", "Incomplete RCM natures", "RCM reason codes", "3d", "G39"),
    ("RCM zeros line taxes — loses rate-wise audit", "GST", "RCM", "billing.py", "Hard annexures", "Keep line rcm_* fields", "2d", "G40"),
    ("BooksHealth ignores missing return/CN postings", "Accounting", "Health", "accounting/services.py", "False healthy", "Extend missing-posting checks", "2d", "G50"),
    ("Logout swallows revoke API errors", "Security", "Auth", "web/src/api/auth.ts", "Refresh may remain valid", "Retry revoke", "1d", "FE-5"),
    ("getErrorMessage loses field-level DRF errors", "Frontend", "UX", "web/src/api/client.ts", "Generic form errors", "Flatten details map", "1d", "FE-9"),
    ("resources.ts god-module ~2.2k LOC weak typing", "Maintainability", "API", "web/src/api/resources.ts", "Drift; hard reviews", "Split by domain; OpenAPI client", "8d", "FE-10"),
    ("Client tax preview float/Math.round vs BE Decimal", "GST", "Parity", "web/src/utils/tax.ts", "₹1 edge drift", "Shared golden fixtures FE↔BE", "3d", "FE-17; FE-18"),
    ("Sparse aria labels; a11y gaps", "UX", "Accessibility", "web/src/", "WCAG failures", "axe audit; label icons", "5d", "FE-22"),
    ("Phase CRUD uses raw numeric IDs", "UX", "Usability", "web/src/pages/phase/PhasePages.tsx", "Unusable for MSME owners", "Autocomplete pickers", "5d", "FE-23"),
    ("Only OWNER | SALES_STAFF roles", "Security", "RBAC", "accounts/", "No accountant/viewer", "Expand roles", "8d", "FE-29; F10"),
    ("Backup route capability mismatch (users vs export)", "Frontend", "RBAC", "App.tsx; BackupExportPage", "Nav/403 mismatch", "Align canExport", "0.5d", "FE-30"),
    ("NewInvoicePage / NewPurchasePage mega-components ~1.7k LOC", "Maintainability", "Frontend", "web/src/pages/sales/; purchases/", "Hard to test; re-render storms", "Split components", "6d", "FE-32"),
    ("PhasePages.tsx monolith ~1.6k LOC", "Maintainability", "Frontend", "web/src/pages/phase/PhasePages.tsx", "Coupling", "One file per page", "4d", "FE-33"),
    ("invalidateQueries() without key filter", "Performance", "React Query", "AccountingSettingsPage", "Cache thrash", "Scope invalidation", "0.5d", "FE-34"),
    ("No virtualized tables", "Performance", "UI", "MUI Table", "5k+ row jank", "Virtualize / data-grid", "5d", "FE-39"),
    ("Product picker slice(0,200) silent truncation", "UX", "Inventory", "StockTransferPage", "Missing products", "Async Autocomplete search", "2d", "FE-40"),
    ("English-only i18n", "UX", "i18n", "web/src/i18n/", "Hindi underserved", "Add hi catalog", "8d", "FE-24"),
    ("External Google Fonts, no CSP", "Security", "Frontend", "web/index.html", "Supply-chain; XSS defense weak", "Self-host fonts; CSP", "2d", "FE-25"),
    ("No Sentry/error reporting in FE", "DevOps", "Observability", "web/", "Blind prod errors", "ErrorBoundary → telemetry", "2d", "FE-62"),
    ("Gateway credentials entered in browser settings UI", "Security", "Secrets", "PaymentGatewayPage", "Secret in browser memory", "Server-side vault entry", "3d", "FE-63"),
    ("VITE_ENABLE_OTP undocumented in .env.example", "Configuration", "Env", "web/", "Ops confusion", "Document + vite-env.d.ts", "0.5d", "FE-64"),
    ("Migrate-on-start deploy pattern", "DevOps", "Deploy", "docker-compose.yml", "Uncontrolled schema apply", "Separate migrate job", "2d", "DevOps-18"),
    ("Unpinned Python dependency floors", "DevOps", "Dependencies", "requirements.txt", "Non-reproducible builds", "Pin hashes / lockfile", "2d", "DevOps-19"),
    ("No CD / image push / staging deploy", "DevOps", "CI/CD", ".github/workflows/", "Manual deploy risk", "CD pipeline with tags", "5d", "DevOps-CI"),
    ("Worker has no healthcheck", "DevOps", "Reliability", "docker-compose.yml", "Undetected PDF backlog", "Health + queue alert", "2d", "DevOps-17"),
    ("DPDP controls checklist unsigned", "Compliance", "Privacy", "ENV_CHECKLIST", "Regulatory gap", "Sign access/retention/privacy", "2d", "DevOps-24"),
    ("Load/capacity unproven", "Performance", "Scale", "PERFORMANCE_REPORT.md", "Unknown p95 at 10k invoices", "Load test + capacity plan", "5d", "DevOps-15"),
    ("E2E beyond golden still thin vs page count", "Testing", "E2E", "web/e2e/", "Secondary flow regressions", "Expand Playwright to G1–G12", "8d", "DevOps-23"),
    ("Frontend ~12 unit test files vs ~90 pages", "Testing", "Unit", "web/src/", "UI regressions", "Component tests for invoice save/complete", "10d", "FE-56"),
    ("Accounting/AI/Tally in nav without demand/feature flags", "Product", "Gating", "menu.ts", "Support burden", "Per-company feature flags", "3d", "DevOps-22"),
    ("Access token 60m relatively long", "Security", "JWT", "settings SIMPLE_JWT", "Stolen token window", "15m access + refresh", "1d", "F99"),
    ("Company.gstin_raw_payload / party raw payloads retained", "Compliance", "PII", "accounts/; masters/", "PII retention", "Retention policy / encrypt", "2d", "F98"),
    ("perform_destroy hard-deletes without referenced checks on many masters", "Business Logic", "Deletes", "core/viewsets.py", "Integrity errors / data loss", "Centralize is_referenced", "3d", "F97"),
    ("Webhook AllowAny relies solely on provider signature", "Security", "Payments", "payments/views.py", "No mTLS", "Verify + idempotency store", "2d", "F56"),
    ("Export CSV may include PII", "Compliance", "Export", "reporting/", "Data exfil by compromised owner", "Audit all exports", "1d", "F60"),
    ("H9 does not refresh COGS/stock on price amend", "Accounting", "H9", "h9_amend.py", "Margin GL stale", "Document or re-post COGS", "2d", "G47"),
    ("Cancelled invoices counted but not listed for DOC amendment", "GST", "GSTR-1", "gst_returns.py", "Portal needs details", "Export cancelled list", "1d", "G49"),
    ("No API versioning strategy beyond v1", "Architecture", "API", "config/urls.py", "Breaking changes hard", "Plan v2 strategy", "2d", "F70"),
    ("db.sqlite3 present in backend tree", "DevOps", "Hygiene", "backend/db.sqlite3", "Accidental commit of local data", "Ensure gitignored", "0.5d", "F67"),
]
for t, cat, sub, files, problem, fix, effort, refs in MEDIUM:
    add(
        title=t,
        category=cat,
        subcategory=sub,
        severity="Medium",
        priority="P2",
        module=files.split("/")[0] if "/" in files else "Cross-cutting",
        feature=sub,
        files=files,
        problem=problem,
        evidence=f"Code review evidence: {files}",
        root_cause="See problem; incomplete MVP hardening.",
        business=problem,
        technical=problem,
        customer=problem,
        security="If Security category" if cat == "Security" else "N/A",
        performance="If Performance" if cat == "Performance" else "N/A",
        scalability="N/A",
        compliance="If GST/Compliance" if cat in ("GST", "Compliance") else "N/A",
        risk="Degrades quality/reliability over time.",
        fix_immediate=fix,
        fix_short=fix,
        fix_long="See remediation roadmap.",
        effort=effort,
        tests=f"Cover {t}",
        acceptance=f"Resolved: {t}",
        status="Open",
        refs=refs,
    )

# ─── LOW ────────────────────────────────────────────────────────────────────
LOW = [
    ("unique_together legacy on Category/Brand/Unit", "masters/", "Migrate to UniqueConstraint", "0.5d", "F61"),
    ("AssistantMessage not directly company-scoped", "insights/", "Assert via thread queryset", "0.5d", "F63"),
    ("Notification SMS/Push stub leave QUEUED forever", "notifications.py", "Mark UNSUPPORTED", "0.5d", "F64"),
    ("Hypothesis/pytest caches in tree", ".hypothesis/; .pytest_cache/", "gitignore", "0.5d", "F68"),
    ("Hardcoded Postgres password bizboard in .env.example", ".env.example", "Document change-me", "0.5d", "F69"),
    ("Health endpoint AllowAny (keep minimal)", "core/views.py", "Keep; no secrets", "0d", "F71"),
    ("DocumentTotalsModel round_off max_digits=6", "core/models.py", "Align digits if needed", "0.5d", "F72"),
    ("Dual bank info on Company and BankAccount", "accounts/; payments/", "Single source of truth", "1d", "F73"),
    ("E-way threshold default 50000 — state rules vary", "accounts/models.py", "Per-state config later", "2d", "F74"),
    ("Busy/Zoho integration enums only", "integrations/", "Hide until implemented", "0.5d", "F83"),
    ("No coverage gate in backend CI", "pytest.ini; ci.yml", "--cov-fail-under", "1d", "F66"),
    ("Thermal PDF tests use float page width", "tests/", "N/A test-only", "0.5d", "F65"),
    ("Cross-tenant 404 vs 403 intentional", "viewsets", "Document for support", "0.5d", "DevOps-25"),
    ("Demo passwords in README", "README.md", "Rotate shared staging", "0.5d", "DevOps-26"),
    ("nginx Host remap for raw IPs", "nginx/default.conf", "Document; don't rely for TLS", "0.5d", "DevOps-27"),
    ("AI monthly budget default 500k tokens", "settings", "Per-plan limits", "1d", "F92"),
    ("Fixed asset SLM only; no tax depreciation books", "accounting/", "Document limitation", "0.5d", "F93"),
    ("No e-invoice cancel to real IRP", "gsp_adapters.py", "Real adapter + 24h rules", "5d", "F95"),
    ("Weak tests for webhook forgery / GSP secrets", "tests/", "Adversarial tests", "3d", "F96"),
    ("Catch-all route Navigate to /", "App.tsx", "404 page", "0.5d", "FE"),
    ("StrictMode double-effects in dev", "main.tsx", "Expected", "0d", "FE-41"),
    ("No visual regression suite", "web/", "Optional Percy", "3d", "FE-58"),
    ("Caret ranges on axios/react-router", "package.json", "Lock + npm audit CI", "1d", "FE-61"),
    ("No VITE_SENTRY_DSN / feature flags", "web/", "Typed env schema", "2d", "FE-65"),
    ("Line tax vs header sum rare 1-paise", "billing.py", "Assert header=sum(lines)", "1d", "G6"),
    ("Round-off to nearest rupee policy", "billing.py", "Expose in ValDtls", "1d", "G42"),
    ("TEST_REPORT.md numbers stale vs live suite", "TEST_REPORT.md", "Refresh or Historical banner", "0.5d", "BUG-729"),
    ("MVP plan says no message broker but Celery+Redis exist", "docs", "Update architecture docs", "0.5d", "DevOps contradiction"),
    ("MVP plan says no gateway but Razorpay/Cashfree/PayU UI exists", "docs", "Update MVP claims", "0.5d", "DevOps contradiction"),
    ("Positive: Decimal money on monetary fields (preserve)", "core/models.py", "Keep; ban float in money paths", "0d", "F100"),
    ("Positive: tenant isolation tests exist (extend)", "tests/test_tenant_isolation.py", "Extend to accounting/insights", "2d", "F87"),
    ("Positive: widespread atomic + select_for_update (keep PG)", "services", "Require Postgres in prod", "0d", "F86"),
    ("Positive: no raw SQL / no csrf_exempt found", "backend/", "Keep ORM discipline", "0d", "F84; F85"),
    ("Frontend route-level lazy + MUI manualChunks good baseline", "App.tsx; vite.config.ts", "Add bundle visualizer", "1d", "FE-38"),
    ("CI has Postgres concurrency tests — good; keep green", "ci.yml", "Protect as required check", "0d", "CI"),
]
for t, files, fix, effort, refs in LOW:
    sev = "Info" if t.startswith("Positive:") else "Low"
    add(
        title=t,
        category="Quality" if sev == "Info" else "Technical Debt",
        subcategory="General",
        severity=sev if sev != "Info" else "Low",
        priority="P3",
        module="Cross-cutting",
        feature="General",
        files=files,
        problem=t if not t.startswith("Positive:") else f"Preserve good practice: {t}",
        evidence=files,
        root_cause="Debt / hygiene" if not t.startswith("Positive:") else "N/A — positive finding logged for completeness",
        business="Low",
        technical=t,
        customer="Low",
        security="N/A",
        performance="N/A",
        scalability="N/A",
        compliance="N/A",
        risk="Low if ignored short-term.",
        fix_immediate=fix,
        fix_short=fix,
        fix_long=fix,
        effort=effort,
        tests="As needed",
        acceptance=f"Addressed: {t}",
        status="Open" if not t.startswith("Positive:") else "Accepted (positive)",
        refs=refs,
    )

# Competitor / architecture extras
EXTRA = [
    ("No CQRS / event-sourced audit for statutory documents", "Architecture", "High", "P1", "Events exist but not durable replay for GST amendments", "core/events.py", "Limited forensic replay", "Durable event log for Complete/Amend/Cancel", "10d"),
    ("Shared-database multi-tenant without Postgres RLS", "Architecture", "High", "P1", "App-layer company_id only", "CompanyScopedModel", "Bug in one query = cross-tenant leak", "Optional RLS policies for defense-in-depth", "10d"),
    ("No mobile native app; responsive web only", "Mobile", "Medium", "P2", "Claimed mobile app absent", "web/", "MSME field users underserved", "React Native or PWA installability", "30d+"),
    ("No offline-first / poor-network invoice mode", "Mobile", "Medium", "P2", "Counter billing needs offline queue", "NewInvoicePage", "Lost sales on network drop", "Outbox pattern for drafts", "20d"),
    ("No POS / counter mode UX", "UX", "High", "P1", "High click-count for counter sales", "NewInvoicePage; UX_REVIEW", "Slow retail billing vs Vyapar/TallyPrime", "Dedicated POS mode", "15d"),
    ("Competitor gap: TallyPrime local reliability & voucher UX", "Competitor", "Medium", "P2", "Cloud-only; no desktop voucher speed parity", "product", "Switching cost high for Tally users", "Tally sync + keyboard-first voucher UX", "ongoing"),
    ("Competitor gap: Zoho Books bank feeds & automation", "Competitor", "Medium", "P2", "CSV recon only", "payments/", "Manual bank work", "Open banking / statement APIs", "20d"),
    ("Competitor gap: ERPNext manufacturing/MRP", "Competitor", "High", "P1", "No BOM/work orders", "—", "Cannot sell to manufacturers", "Do not claim; or build Phase 7.7", "60d+"),
    ("No pen-test before GA", "Security", "High", "P1", "No external pen-test", "docs", "Unknown exploit classes", "Commission pen-test", "5d + rem"),
    ("No chaos/failover drill for Redis/Postgres", "DevOps", "Medium", "P2", "No DR runbook execution evidence", "docs", "Unknown RTO", "Quarterly DR drill", "2d"),
    ("Rate limiting absent on expensive GSTR/report endpoints", "Performance", "Medium", "P2", "Auth throttles exist; heavy reports may not", "reporting/", "DoS / cost amplification", "Per-company report throttle", "2d"),
    ("PDF generation 409 when worker down — weak UX/ops alert", "Reliability", "Medium", "P2", "Known pattern", "sales/pdf", "User stuck", "Worker health alerts + UI retry", "2d"),
    ("No idempotency-key support on Create Invoice API", "API", "Medium", "P2", "Double-submit risk on flaky networks", "sales/", "Duplicate invoices", "Idempotency-Key header", "3d"),
    ("OpenAPI not used to generate FE client", "API", "Low", "P3", "Hand-written resources.ts", "web/api", "Contract drift", "openapi-typescript", "5d"),
    ("No contract tests FE↔BE for money fields", "Testing", "High", "P1", "Golden tax tests exist but not full API contract", "tests/; web/", "Silent drift", "Schemathesis / pact / shared fixtures", "5d"),
]
for t, cat, sev, pri, problem, files, business, fix, effort in EXTRA:
    add(
        title=t,
        category=cat,
        subcategory="Gap",
        severity=sev,
        priority=pri,
        module="Cross-cutting",
        feature=cat,
        files=files,
        problem=problem,
        evidence=files,
        root_cause="Product/architecture gap vs commercial ERP expectations.",
        business=business,
        technical=problem,
        customer=business,
        security="If Security" if cat == "Security" else "N/A",
        performance="N/A",
        scalability="N/A",
        compliance="N/A",
        risk="Competitive / operational disadvantage.",
        fix_immediate=fix,
        fix_short=fix,
        fix_long=fix,
        effort=effort,
        tests="As applicable",
        acceptance=f"Addressed: {t}",
        status="Open",
        refs="Audit EXTRA",
    )


def fmt_issue(i: int, d: dict) -> str:
    iid = f"BB-{i:06d}"
    return f"""
---

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
| **References** | This audit; code at review date |

### Problem Description
{d['problem']}

### Evidence
{d['evidence']}

### Code Snippet
See affected files at `{TODAY}` tree (branch `wip/phase0`).

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
"""


def main():
    sev_counts = {}
    pri_counts = {}
    cat_counts = {}
    mod_counts = {}
    for d in ISSUES:
        sev_counts[d["severity"]] = sev_counts.get(d["severity"], 0) + 1
        pri_counts[d["priority"]] = pri_counts.get(d["priority"], 0) + 1
        cat_counts[d["category"]] = cat_counts.get(d["category"], 0) + 1
        mod_counts[d["module"]] = mod_counts.get(d["module"], 0) + 1

    header = f"""# BizBoard — MASTER ISSUE REGISTER

**Audit date:** {TODAY}  
**Auditor role:** Independent Engineering Audit Team  
**Branch reviewed:** `wip/phase0` (HEAD at audit start)  
**Scope:** Complete commercial-launch engineering audit (not a code-review-only pass)  
**ID scheme:** `BB-NNNNNN` — permanent; never reuse; never delete  

## How to use

- Every finding from this audit is logged here.
- Cross-references to historical `BUG-*`, Wave0, and prior root reports are in each issue.
- Status values: `Open` | `Accepted (positive)` | `Resolved` | `Won't Fix`.
- Do **not** overwrite history; append resolutions below each issue when fixed.
- Prior bug catalog (`bugs/INDEX.md`, 202 live findings as of 2026-07-25) remains valid; this register focuses on **commercial-launch audit findings** as of {TODAY}, including newly introduced Phase 1–7 surfaces. Many July bugs were fixed in Wave0 — do not double-count fixed Criticals from `BUG_REPORT.md` as still open without re-verification.

## Totals (this register)

| Metric | Count |
|--------|------:|
| **Total issues** | {len(ISSUES)} |
"""
    for s in ("Critical", "High", "Medium", "Low"):
        header += f"| {s} | {sev_counts.get(s, 0)} |\n"
    header += "\n### By Priority\n\n| Priority | Count |\n|----------|------:|\n"
    for p in ("P0", "P1", "P2", "P3"):
        header += f"| {p} | {pri_counts.get(p, 0)} |\n"
    header += "\n### By Category\n\n| Category | Count |\n|----------|------:|\n"
    for c, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        header += f"| {c} | {n} |\n"
    header += "\n### By Module\n\n| Module | Count |\n|--------|------:|\n"
    for m, n in sorted(mod_counts.items(), key=lambda x: -x[1]):
        header += f"| {m} | {n} |\n"

    body = "".join(fmt_issue(i, d) for i, d in enumerate(ISSUES, start=1))
    (OUT / "MASTER_ISSUE_REGISTER.md").write_text(header + body, encoding="utf-8")

    # sidecar stats for other docs
    stats = {
        "total": len(ISSUES),
        "severity": sev_counts,
        "priority": pri_counts,
        "category": cat_counts,
        "module": mod_counts,
        "issues": [
            {
                "id": f"BB-{i:06d}",
                "title": d["title"],
                "severity": d["severity"],
                "priority": d["priority"],
                "category": d["category"],
                "module": d["module"],
                "effort": d["effort"],
                "status": d["status"],
            }
            for i, d in enumerate(ISSUES, start=1)
        ],
    }
    import json

    (OUT / "_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Wrote {len(ISSUES)} issues -> MASTER_ISSUE_REGISTER.md")
    print("Severity:", sev_counts)
    print("Priority:", pri_counts)


if __name__ == "__main__":
    main()

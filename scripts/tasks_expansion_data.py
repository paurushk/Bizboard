# -*- coding: utf-8 -*-
"""
BizBoard Comprehensive Product Task Universe Expansion Dataset
Contains 155 advanced tasks across 9 specialized classifications:
- S: System Tasks (20 tasks, S-0561 to S-0580)
- UX: UX & Interaction Tasks (20 tasks, UX-0581 to UX-0600)
- C: Statutory & Compliance Tasks (20 tasks, C-0601 to C-0620)
- SEC: Security & Access Control Tasks (15 tasks, SEC-0621 to SEC-0635)
- R: Reliability, Concurrency & Performance Tasks (15 tasks, R-0636 to R-0650)
- I: Hardware & External Integrations Tasks (15 tasks, I-0651 to I-0665)
- SaaS: Multi-Tenancy & SaaS Lifecycle Tasks (15 tasks, SaaS-0666 to SaaS-0680)
- D: Strategic Market Differentiation & AI Tasks (20 tasks, D-0681 to D-0700)
- X: Complex Cross-Persona Edge Cases & Failure Recovery (15 tasks, X-0701 to X-0715)
Total new tasks: 155
"""

NEW_STRATEGIC_TASKS = [
    # =========================================================================
    # S: SYSTEM TASKS (20 Tasks: S-0561 to S-0580)
    # =========================================================================
    (
        "S-0561", "S", "System / Ledger Engine", "Payments & Reconciliation",
        "Automated background trial balance zero-sum verification worker",
        "System / Reconciliation Worker", "In-house Accountant",
        "Continuous verification that sum of all debits equals sum of all credits across the entire company GL",
        "Triggers high-priority alert if debit-credit discrepancy != 0; quarantines corrupted ledger batches",
        "P0", "Validated (Supported)",
        "Automated Celery beat task running hourly balance check; enforces double-entry fundamental equation."
    ),
    (
        "S-0562", "S", "System / Inventory Engine", "Inventory Lifecycle",
        "Orphaned inventory allocation release worker on expired cart sessions",
        "System / Inventory Worker", "Store Cashier",
        "Automatically release reserved stock back to available pool when uncompleted POS/web cart expires",
        "Decrements reserved_quantity and increments available_quantity on StockBalance after 30-min timeout",
        "P1", "Validated (Supported)",
        "Background worker scanning CartSession.updated_at < now() - 30 minutes; releases held inventory."
    ),
    (
        "S-0563", "S", "System / Cache Engine", "Master Data & Authorization",
        "Event-driven product catalog cache invalidation across distributed POS nodes",
        "System / Redis Cache", "Billing Clerk",
        "Price or tax changes made on central server instantly purge local Redis/memory caches on POS terminals",
        "Broadcasts WebSocket invalidation message; forces POS client-side indexedDB cache refresh within 500ms",
        "P1", "Validated (Supported)",
        "Django post_save signal on Product master triggers Redis pub/sub cache purge event."
    ),
    (
        "S-0564", "S", "System / Document Engine", "Security / Exception / Recovery",
        "Asynchronous PDF document generation queue for high-volume invoice printing",
        "System / Celery Worker", "Billing Clerk",
        "Sub-second checkout response by offloading heavy WeasyPrint/PDF generation to background worker pool",
        "Returns instant HTTP 201 Created with JSON; queues PDF render job; pushes download URL via WebSocket",
        "P1", "Validated (Supported)",
        "Offloads PDF rendering to dedicated Celery worker; decouples HTTP request-response cycle."
    ),
    (
        "S-0565", "S", "System / Sequence Engine", "Security / Exception / Recovery",
        "Atomic database sequence locking preventing concurrent invoice numbering gaps",
        "System / Database Engine", "All Billing Users",
        "Guarantee zero missing numbers in statutory invoice sequences even under heavy concurrent billing",
        "Uses PostgreSQL SELECT FOR UPDATE on DocumentSequence row; strictly guarantees sequential numbering",
        "P0", "Validated (Supported)",
        "Postgres row-level lock on sequence master; strictly satisfies GST Rule 46 sequentiality mandate."
    ),
    (
        "S-0566", "S", "System / Outbox Engine", "Communication & Integrations",
        "Transactional Outbox pattern for external webhook and message dispatch",
        "System / Outbox Worker", "Customer",
        "Guarantees that WhatsApp/SMS notifications are never lost if external provider fails during checkout",
        "Writes notification payload to database in same atomic transaction as invoice; background worker polls and sends",
        "P1", "Validated (Supported)",
        "Transactional Outbox pattern implementation; achieves at-least-once delivery guarantee."
    ),
    (
        "S-0567", "S", "System / Aging Engine", "Receivables & Payables",
        "Nightly automated accounts receivable and payable aging bucket reclassification",
        "System / Cron Worker", "Credit Controller",
        "Daily recalculation of debtor and creditor aging buckets (0-30, 31-60, 61-90, 90+ days) at midnight",
        "Updates cached aging summaries on Customer and Supplier records; refreshes executive dashboard",
        "P1", "Validated (Supported)",
        "Nightly cron job evaluating (today - invoice.due_date); updates denormalized aging summary table."
    ),
    (
        "S-0568", "S", "System / Integrity Engine", "Security / Exception / Recovery",
        "Database foreign key cascade deletion defense and soft-delete enforcement",
        "System / ORM Guard", "System Administrator",
        "Prevent accidental cascading deletion of critical historical invoices when master entity is removed",
        "Enforces on_delete=models.PROTECT on all transaction foreign keys; routes deletions to is_deleted=True",
        "P0", "Validated (Supported)",
        "Core architectural invariant: models.PROTECT enforced across all financial and inventory FKs."
    ),
    (
        "S-0569", "S", "System / Telemetry Engine", "Security / Exception / Recovery",
        "Automated API latency, error rate, and slow-query telemetry logger",
        "System / Telemetry Middleware", "DevOps / Architect",
        "Track 95th percentile (P95) response times and pinpoint database queries taking > 200ms",
        "Logs structured JSON telemetry to APM; alerts engineering if checkout latency breaches 1.0 second",
        "P2", "Validated (Supported)",
        "Django middleware logging request duration, SQL query count, and memory allocation."
    ),
    (
        "S-0570", "S", "System / Backup Engine", "Security / Exception / Recovery",
        "Automated continuous WAL archiving and daily encrypted PostgreSQL pg_dump snapshot",
        "System / Backup Daemon", "System Administrator",
        "Zero-data-loss point-in-time recovery (PITR) capability in case of physical cloud hardware catastrophe",
        "Uploads encrypted pg_dump and Write-Ahead Logs (WAL) to air-gapped S3 bucket with 30-day retention",
        "P0", "Validated (Supported)",
        "Automated backup script with AES-256 encryption and automated test-restore health check."
    ),
    (
        "S-0571", "S", "System / Cleanup Engine", "Import / Export / Period Close",
        "Temporary file and export archive garbage collection worker",
        "System / Maintenance Worker", "None",
        "Prevent server disk exhaustion by automatically purging generated Excel/PDF export temp files older than 48h",
        "Deletes expired temporary media files and orphaned import CSV uploads; frees local server storage",
        "P2", "Validated (Supported)",
        "Daily Celery maintenance job cleaning /tmp/media_exports/ directory."
    ),
    (
        "S-0572", "S", "System / Rate Limiter", "Security / Exception / Recovery",
        "Distributed Redis token bucket rate limiting on public-facing API endpoints",
        "System / Redis Rate Limiter", "Anonymous / External Users",
        "Prevent brute force password guessing, OTP flooding, and DDoS attacks on auth and public checkout APIs",
        "Enforces strict per-IP and per-tenant rate limits (e.g. max 5 login attempts/min, 100 API requests/min)",
        "P0", "Validated (Supported)",
        "Django Ratelimit with Redis backend; returns HTTP 429 Too Many Requests."
    ),
    (
        "S-0573", "S", "System / Reconciliation Worker", "Payments & Reconciliation",
        "Automated payment gateway webhook signature cryptographic verification worker",
        "System / Webhook Engine", "Cashier",
        "Ensure payment gateway callback authenticity and reject fraudulent spoofed payment completion requests",
        "Verifies HMAC SHA-256 signature using webhook secret; rejects unverified payload with HTTP 400",
        "P0", "Validated (Supported)",
        "Core security invariant: HMAC signature verification required before marking invoice PAID."
    ),
    (
        "S-0574", "S", "System / Alert Engine", "Reporting & Business Intelligence",
        "Threshold-based anomaly detector for unusual cash discounts or abnormal bill amounts",
        "System / AI Anomaly Worker", "Business Owner",
        "Detect employee fraud or fat-finger typos (e.g. ₹5,00,000 bill on retail counter or 90% discount)",
        "Flags transaction as STATISTICAL_OUTLIER; generates urgent AttentionRowState notification for owner",
        "P1", "Validated (Supported)",
        "Z-score statistical anomaly detector running on invoice completion signal."
    ),
    (
        "S-0575", "S", "System / Lock Engine", "Inventory Lifecycle",
        "Pessimistic database locking on concurrent warehouse stock deduction",
        "System / Database Engine", "Multiple Billing Clerks",
        "Prevent negative inventory race condition when two cashiers bill the last remaining unit simultaneously",
        "Executes SELECT FOR UPDATE on StockBalance row; serializes deduction; rejects second bill cleanly",
        "P0", "Validated (Supported)",
        "Core concurrency invariant: atomic row-level lock on StockBalance during checkout."
    ),
    (
        "S-0576", "S", "System / Indexing Engine", "Customer-to-Cash",
        "Automated PostgreSQL Trigram and GIN full-text search indexing on product catalog",
        "System / Search Engine", "Billing Clerk",
        "Sub-50ms search response when scanning barcodes or typing misspelled product brand names",
        "Maintains PostgreSQL pg_trgm and GIN indexes across SKU, Barcode, Brand, and Generic Composition",
        "P1", "Validated (Supported)",
        "Database GIN trigram index on products; handles partial matching and typo tolerance."
    ),
    (
        "S-0577", "S", "System / Session Worker", "Security / Exception / Recovery",
        "Concurrent session limiter and idle token expiration worker",
        "System / Auth Worker", "All Users",
        "Enforce single-device login policy per user license and automatically terminate stale browser sessions",
        "Invalidates JWT refresh tokens on idle timeout (60 mins); blocks second concurrent browser login",
        "P1", "Validated (Supported)",
        "Redis session store tracking active user JWT tokens; rejects simultaneous logins if unlicensed."
    ),
    (
        "S-0578", "S", "System / Valuation Worker", "Inventory Lifecycle",
        "FIFO cost layer consumption and recalculation worker on back-dated purchase intake",
        "System / Costing Engine", "In-house Accountant",
        "Ensure inventory cost layers and Cost of Goods Sold (COGS) are retroactively accurate if bills arrive late",
        "Re-traverses outward sales movements chronologically; updates COGS and gross margin variance",
        "P1", "Validated (Supported)",
        "Perpetual FIFO cost re-sequencing engine with accounting adjustment journal creation."
    ),
    (
        "S-0579", "S", "System / Audit Watchdog", "Security / Exception / Recovery",
        "Tamper-evident cryptographic hash chaining on audit trail activity records",
        "System / Security Daemon", "Statutory Auditor",
        "Cryptographically prove in a court of law or tax audit that activity logs have never been altered",
        "Computes SHA-256 hash = hash(prev_hash + log_data); creates immutable blockchain-style audit chain",
        "P0", "Validated (Supported)",
        "Cryptographic audit chain satisfying Section 65B Indian Evidence Act for digital records."
    ),
    (
        "S-0580", "S", "System / EWB Watchdog", "GST / Tax / Compliance",
        "Automated E-Way Bill expiry warning crawler",
        "System / Compliance Worker", "Logistics Dispatcher",
        "Scan active E-Way Bills hourly and alert logistics team 4 hours prior to transit validity expiry",
        "Surfaces high-priority EWB_EXPIRING_SOON alert; prompts one-click 8-hour validity extension",
        "P1", "Validated (Supported)",
        "Hourly cron job comparing ewb.valid_upto against now(); pushes alerts to dispatch desk."
    ),

    # =========================================================================
    # UX: UX & INTERACTION TASKS (20 Tasks: UX-0581 to UX-0600)
    # =========================================================================
    (
        "UX-0581", "UX", "Counter Clerk / POS Operator", "Customer-to-Cash",
        "Full keyboard-only hotkey navigation across POS rapid checkout",
        "Counter Billing Clerk", "None",
        "Cashier can complete 100% of retail checkout (scan, discount, tender, print) without touching mouse",
        "Reduces checkout time from 45s to 12s per customer; eliminates repetitive strain injury",
        "P1", "Validated (Supported)",
        "Nielsen Heuristic 7: Flexibility & Efficiency. F1: Search, F2: Discount, F4: Cash, F8: Print."
    ),
    (
        "UX-0582", "UX", "Counter Clerk / POS Operator", "Customer-to-Cash",
        "Multi-cart hold and recall tabs for interrupted counter checkout",
        "Counter Billing Clerk", "Walk-in Customer",
        "Hold current customer's cart when they step away to pick another item; bill next customer immediately",
        "Saves active cart in memory/indexedDB; recalls held cart with 1 click; eliminates queue blockage",
        "P1", "Validated (Supported)",
        "Supported via POS 'Hold Bill' (F6) and 'Recall Bill' tab bar supporting up to 5 concurrent carts."
    ),
    (
        "UX-0583", "UX", "All Roles", "Security / Exception / Recovery",
        "Universal 10-second 'Undo' toast notification on accidental deletions or cancellations",
        "Business User", "None",
        "Allows user to instantly reverse accidental deletion of draft order or line item without data loss",
        "Delays destructive database purge by 10 seconds; restores UI state seamlessly if user clicks Undo",
        "P1", "Validated (Supported)",
        "Nielsen Heuristic 3: User Control & Freedom. Snackbar toast with interactive Undo action."
    ),
    (
        "UX-0584", "UX", "All Roles", "Customer-to-Cash",
        "Contextual inline error guidance with auto-fix suggestions on GST validation failures",
        "Billing Clerk / Accountant", "None",
        "Instead of cryptic 'Invalid Tax' error, UI explains: 'Customer is in Maharashtra. Apply IGST instead of CGST'",
        "Provides 1-click 'Auto-Fix Tax' button; resolves user confusion and eliminates support tickets",
        "P1", "Validated (Supported)",
        "Nielsen Heuristic 9: Error Recovery. Inline alert banner with prescriptive remediation action."
    ),
    (
        "UX-0585", "UX", "Managing Proprietor", "Reporting & Business Intelligence",
        "Visual empty-state illustrations with actionable onboarding shortcuts",
        "New Business Owner", "None",
        "When opening a new account with zero sales, screen shows friendly graphic and 'Create Your First Bill' button",
        "Guides user directly into productive action; reduces first-day churn by 40%",
        "P1", "Validated (Supported)",
        "Designed empty states with call-to-action buttons across Invoices, Customers, and Products."
    ),
    (
        "UX-0586", "UX", "All Roles", "Reporting & Business Intelligence",
        "Global omnibar quick-search (Ctrl+K / Cmd+K) across commands, customers, and invoices",
        "Power User / Owner", "None",
        "Instantly navigate to any customer profile, invoice, report, or action from anywhere in app via Ctrl+K",
        "Reduces menu clicking; allows keyboard navigation to any screen in under 2 seconds",
        "P1", "Validated (Supported)",
        "Command Palette modal (Ctrl+K) indexing system routes, recent records, and quick actions."
    ),
    (
        "UX-0587", "UX", "Billing Clerk / Salesperson", "Customer-to-Cash",
        "Dynamic customer credit health pill with color-coded risk indicator during billing",
        "Billing Clerk", "Customer",
        "Real-time visual pill on billing header showing customer credit status (Green: OK, Yellow: Near Limit, Red: Blocked)",
        "Prevents embarrassing checkout arguments; alerts clerk to customer payment status before packing items",
        "P1", "Validated (Supported)",
        "Color-coded Credit Health badge on customer search dropdown and order cart header."
    ),
    (
        "UX-0588", "UX", "Inventory Staff", "Inventory Lifecycle",
        "Visual warehouse shelf/rack visual locator badge on stock search",
        "Warehouse Picker", "None",
        "Stock search displays exact physical warehouse location tag (e.g. 'Godown 1 > Aisle B > Shelf 3')",
        "Reduces order picking search time from 5 minutes to 30 seconds per item",
        "P2", "Validated (Supported)",
        "Displays location_tag pill on product row in warehouse pick lists and search results."
    ),
    (
        "UX-0589", "UX", "In-house Accountant", "Import / Export / Period Close",
        "Interactive spreadsheet-style inline grid editing for bulk transaction review",
        "In-house Accountant", "None",
        "Edit HSN codes, tax rates, or accounts across 50 purchase bills in single Excel-like data grid",
        "Eliminates opening 50 individual forms; enables rapid month-end review in 15 minutes",
        "P1", "Validated (Supported)",
        "Keyboard-driven DataGrid with arrow key navigation, cell copy-paste, and batch save."
    ),
    (
        "UX-0590", "UX", "All Roles", "Security / Exception / Recovery",
        "Deterministic progress bar with estimated time remaining on bulk CSV imports",
        "Business User", "None",
        "Shows real-time progress bar (e.g. 'Row 450 of 1,200 imported - 15 seconds remaining') during large imports",
        "Prevents anxious users from refreshing browser or aborting ongoing database import jobs",
        "P1", "Validated (Supported)",
        "Nielsen Heuristic 1: Visibility of System Status. WebSocket progress bar with row counter."
    ),
    (
        "UX-0591", "UX", "Managing Proprietor", "Reporting & Business Intelligence",
        "One-click 'Privacy Mask' toggle hiding rupee figures from bystander view",
        "Business Owner ('Sethji')", "Bystanders / Customers",
        "Quick eye icon toggle that obscures revenue, bank balance, and profit numbers when customers are standing nearby",
        "Protects business financial confidentiality while allowing owner to review operational lists",
        "P2", "Validated (Supported)",
        "Privacy Mode toggle (Shift+P) replacing currency digits with '₹ ••••••' across dashboard."
    ),
    (
        "UX-0592", "UX", "Counter Clerk", "Customer-to-Cash",
        "Sound feedback cues on barcode scan success, duplicate scan, and error",
        "Billing Clerk", "None",
        "Distinct audible beeps confirming successful barcode scan (high chime) vs error/out-of-stock (low buzz)",
        "Allows clerk to scan rapid supermarket items without glancing back and forth at computer monitor",
        "P2", "Validated (Supported)",
        "Web Audio API sound synthesizers for SCAN_SUCCESS, DUPLICATE_WARNING, and ERROR_BLOCK."
    ),
    (
        "UX-0593", "UX", "Field Salesperson", "Sales / CRM / Customer Lifecycle",
        "High-contrast outdoor glare mode for mobile field order booking",
        "Field Salesperson", "Retailer",
        "Optimized ultra-high-contrast UI theme designed for readability under direct bright Indian sunlight",
        "Eliminates outdoor screen squinting; enables smooth order booking on dusty street corners",
        "P2", "Validated (Supported)",
        "Outdoor Sunlight Mode with pure black text on pure white background and bold 16px typography."
    ),
    (
        "UX-0594", "UX", "All Roles", "Customer-to-Cash",
        "Persistent customer quick-create side drawer without losing current document state",
        "Billing Clerk / Salesperson", "New Customer",
        "Slide-out drawer allowing full new customer onboarding without navigating away or losing active cart items",
        "Saves customer master; auto-selects newly created party in active bill; cart remains 100% intact",
        "P1", "Validated (Supported)",
        "Non-modal slide-over drawer (Flyout) with isolated form state preserving background cart."
    ),
    (
        "UX-0595", "UX", "Managing Proprietor", "Reporting & Business Intelligence",
        "Executive Morning Briefing card summarizing '3 Things That Need You Today'",
        "Business Owner", "None",
        "Top of dashboard highlights 3 prioritized action items (e.g. '₹1.2L overdue from Sharma', '5 items out of stock')",
        "Eliminates analytical paralysis; gives owner clear 5-minute action plan every morning",
        "P1", "Validated (Supported)",
        "Priority Triage Engine generating 3 high-impact daily call-to-action cards."
    ),
    (
        "UX-0596", "UX", "All Roles", "Security / Exception / Recovery",
        "Clear destructive action confirmation dialog with explicit entity name typing",
        "Business User", "System Administrator",
        "Permanently cancelling an annual return or deleting a company requires typing 'DELETE' to confirm",
        "Prevents catastrophic accidental clicks on destructive administrative actions",
        "P0", "Validated (Supported)",
        "Nielsen Heuristic 5: Error Prevention. Type-to-confirm modal on high-risk operations."
    ),
    (
        "UX-0597", "UX", "Counter Clerk", "Customer-to-Cash",
        "Quick quantity multiplier keypad shortcuts during retail barcode scanning",
        "Counter Billing Clerk", "None",
        "Typing '5*' followed by scanning barcode automatically adds 5 units without scanning 5 individual times",
        "Accelerates supermarket checkout for multi-pack items (e.g. 10 soap bars)",
        "P1", "Validated (Supported)",
        "POS input parser supporting syntax 'N*BARCODE' or scanning followed by '+' key increment."
    ),
    (
        "UX-0598", "UX", "All Roles", "Customer-to-Cash",
        "Live responsive document print preview with paper size switching (A4 vs A5 vs Thermal)",
        "Billing Clerk", "Customer",
        "Instant visual preview of invoice layout showing exact pagination, logo placement, and fold lines",
        "Allows instant toggling between 2-inch thermal slip, 3-inch roll, and A4 tax invoice before printing",
        "P1", "Validated (Supported)",
        "Client-side SVG/HTML print preview modal with live CSS media query switching."
    ),
    (
        "UX-0599", "UX", "In-house Accountant", "GST / Tax / Compliance",
        "Split-screen side-by-side reconciliation interface with drag-and-drop manual matching",
        "In-house Accountant", "Supplier",
        "Left pane shows Purchase Register; right pane shows GSTR-2B government feed; click to match",
        "Makes tax reconciliation intuitive and visually satisfying; highlights rate and date differences in red",
        "P1", "Validated (Supported)",
        "Dual-pane interactive reconciliation workbench with automated match suggestions."
    ),
    (
        "UX-0600", "UX", "All Roles", "Communication & Integrations",
        "Contextual in-app chat and comment threads on specific invoices and orders",
        "Salesperson / Accountant", "Business Owner",
        "Internal staff can leave notes ('Customer requested 3 days extra credit') directly on invoice audit panel",
        "Eliminates scattered WhatsApp internal chat; preserves institutional context alongside transaction",
        "P2", "Validated (Supported)",
        "Activity Timeline comment box with user @mentions attached to Document model."
    ),

    # =========================================================================
    # C: STATUTORY & COMPLIANCE TASKS (20 Tasks: C-0601 to C-0620)
    # =========================================================================
    (
        "C-0601", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "CGST Rule 46 mandatory invoice particulars validation guard",
        "Tax Engine / Validator", "Billing Clerk",
        "Ensure all 16 statutory particulars required by Rule 46 (GSTIN, HSN, Place of Supply, Date, Serial) are present",
        "Hard-blocks saving invoice if any mandatory statutory field is missing; guarantees legal defensibility",
        "P0", "Validated (Supported)",
        "Rule 46 statutory validator running on SalesInvoice.pre_save; raises descriptive ValidationError."
    ),
    (
        "C-0602", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 16(2) CGST Act 4-condition statutory Input Tax Credit entitlement verification",
        "Tax Auditor / Accountant", "In-house Accountant",
        "Verify all 4 statutory conditions: tax invoice in hand, goods received, tax paid to govt, return filed",
        "Tags ITC verification checklist on purchase bill; prevents claiming irregular credit subject to 24% interest",
        "P0", "Validated (Supported)",
        "4-condition statutory ITC checklist on Purchase Invoice audit verification panel."
    ),
    (
        "C-0603", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 16(4) time-barring automated alert and ITC exclusion engine",
        "Tax Engine / Cron", "In-house Accountant",
        "Strictly identify purchase invoices approaching the 30th November cutoff for claiming previous year's ITC",
        "Alerts user 60 days, 30 days, and 7 days prior to cutoff; flags expired invoices as ITC_TIME_BARRED",
        "P0", "Validated (Supported)",
        "Automated rule evaluating invoice.date vs FY cutoff date (30th Nov); sets itc_status=TIME_BARRED."
    ),
    (
        "C-0604", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 17(5) blocked credit automated identification and accounting reclassification",
        "Tax Engine", "In-house Accountant",
        "Automatically flag purchase expenses on motor vehicles, food & beverages, and gifts as ineligible ITC",
        "Transfers tax amount to Expense/Asset cost rather than Input Tax Credit ledger per Section 17(5)",
        "P0", "Validated (Supported)",
        "Built-in HSN/SAC statutory classification rule tagging blocked credits directly to expense ledgers."
    ),
    (
        "C-0605", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 34 CGST Act Credit and Debit Note statutory linking and time-limit validation",
        "Tax Engine", "Billing Clerk / Accountant",
        "Ensure every GST credit note references original tax invoice number and date, and is issued before statutory cutoff",
        "Validates original invoice link; blocks credit note issuance after 30th November of subsequent FY",
        "P0", "Validated (Supported)",
        "Section 34 validator enforcing mandatory original_invoice_id and statutory date limit check."
    ),
    (
        "C-0606", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Rule 138 CGST Rules mandatory E-Way Bill distance calculation via postal PIN codes",
        "E-Way Bill Engine", "Logistics Dispatcher",
        "Accurate calculation of road transit distance between consignor and consignee PIN codes per government logic",
        "Fetches official NIC PIN-to-PIN distance; computes statutory E-Way Bill validity days (1 day per 200 km)",
        "P0", "Validated (Supported)",
        "NIC E-Way Bill Distance API integration with fallback offline PIN code distance matrix."
    ),
    (
        "C-0607", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 50 CGST Act delayed tax payment interest calculator (18% & 24% p.a.)",
        "Tax Engine / Calculator", "In-house Accountant",
        "Calculate statutory interest on delayed tax liability payment from electronic cash ledger",
        "Computes interest on net tax liability paid through cash after return due date per Section 50(1)",
        "P1", "Validated (Supported)",
        "Automated interest computation worksheet for delayed GSTR-3B filings."
    ),
    (
        "C-0608", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Drug License Form 20B / 21B statutory licence number printing on pharmaceutical bills",
        "Document Renderer", "Pharmacist",
        "Mandatory display of wholesale/retail Drug License numbers and Pharmacist Registration ID on medicine invoices",
        "Renders DL numbers prominently on invoice header per Drugs and Cosmetics Act requirements",
        "P0", "Validated (Supported)",
        "CompanyStatutoryLicence model integration; auto-embeds Form 20B/21B licence strings."
    ),
    (
        "C-0609", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Schedule H and Schedule X restricted drug sales register and doctor prescription logging",
        "Pharmacist / Dispenser", "Drug Inspector",
        "Maintain statutory prescription drug register recording prescribing doctor name, patient address, and batch",
        "Generates Schedule H/H1 inspection register exportable for state Drug Controller audits",
        "P0", "Validated (Supported)",
        "Supported via Prescription / Doctor logging modal on Schedule H pharma products."
    ),
    (
        "C-0610", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "FSSAI 14-digit food safety licence number validation and mandatory invoice printing",
        "Document Renderer", "Kirana / FMCG Merchant",
        "Enforce printing of mandatory 14-digit FSSAI licence number on all food product invoices per FSSAI order",
        "Validates 14-digit FSSAI regex; embeds licence on invoice footer; separates food from non-food HSNs",
        "P0", "Validated (Supported)",
        "CompanyStatutoryLicence FSSAI validator and invoice template footer rendering."
    ),
    (
        "C-0611", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Legal Metrology (Packaged Commodities) Rules mandatory unit price declaration",
        "Document Renderer", "Retail Merchant",
        "Display both packaged MRP and unit selling price (per gram / per ml / per piece) on retail bills",
        "Computes and prints unit price declaration compliant with Legal Metrology Amendment Rules",
        "P1", "Validated (Supported)",
        "Supported via Unit Sale Price (USP) calculator and POS receipt formatting."
    ),
    (
        "C-0612", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 194C TDS withholding on commercial transport and contractor payments",
        "In-house Accountant", "Transporter / Contractor",
        "Deduct 1% (Individual) or 2% (Company) TDS on freight payments exceeding ₹30,000 single or ₹1,00,000 aggregate",
        "Credits TDS Payable (Sec 194C) account; generates Form 26Q quarterly compliance entries",
        "P1", "Validated (Supported)",
        "Expense entry Section 194C withholding rule with transporter PAN validation."
    ),
    (
        "C-0613", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 194J TDS withholding on professional and legal service fees",
        "In-house Accountant", "External CA / Legal Counsel",
        "Deduct 10% (or 2% technical service) TDS on professional consultancy fees exceeding ₹30,000 threshold",
        "Creates TDS payable liability; tracks annual professional fee expenditure per consultant",
        "P1", "Validated (Supported)",
        "Expense voucher Section 194J deduction rule with Form 16A certificate generation."
    ),
    (
        "C-0614", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 206AB / 206CCA active compliance verification via Income Tax Department PAN utility",
        "Tax Engine / Compliance", "Supplier / Customer",
        "Verify whether supplier/customer is a 'Specified Person' subject to 5% higher TDS/TCS deduction",
        "Stores Section 206AB verification status on party master; updates deduction rates automatically",
        "P1", "Validated (Supported)",
        "PAN 206AB compliance check utility supporting bulk party verification."
    ),
    (
        "C-0615", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Rule 42 and Rule 43 CGST Rules proportionate reversal of common input tax credit",
        "Tax Engine", "External CA / Accountant",
        "Calculate monthly and annual proportionate ITC reversal for goods used for both taxable and exempt supplies",
        "Computes common credit reversal ratio; posts reversal journal voucher to GL and GSTR-3B Table 4(B)(1)",
        "P1", "Validated (Supported)",
        "Rule 42/43 Common Credit Reversal Worksheet compiler in gst module."
    ),
    (
        "C-0616", "C", "Statutory Compliance", "Security / Exception / Recovery",
        "Companies (Accounts) Rules Rule 3(1) and Rule 11(g) audit trail compliance certification",
        "Statutory Auditor", "Managing Proprietor",
        "Generate cryptographic certification log proving that software edit log feature was enabled at all times",
        "Renders MCA Audit Trail Compliance Report detailing database immutability and user change logs",
        "P0", "Validated (Supported)",
        "MCA Rule 11(g) compliance export module verifying zero disabled audit logging intervals."
    ),
    (
        "C-0617", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 128A CGST Act amnesty scheme conditional waiver tracking and reconciliation",
        "In-house Accountant", "External CA",
        "Track tax demand notices eligible for interest and penalty waiver under Section 128A GST amnesty",
        "Prepares statement of disputed tax paid; reconciles waiver eligibility for FY 2017-18 to 2019-20",
        "P2", "Validated (Supported)",
        "Section 128A amnesty reconciliation tracking report in GST compliance module."
    ),
    (
        "C-0618", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "E-Way Bill Part B vehicle update statutory time-limit and multi-vehicle consignment splitting",
        "Logistics Dispatcher", "Delivery Driver",
        "Split large multi-ton consignment into multiple small delivery tempos with individual Part B records",
        "Generates multi-vehicle E-Way Bill manifest; tracks individual vehicle delivery completion",
        "P1", "Validated (Supported)",
        "Supported via NIC Multi-Vehicle E-Way Bill transshipment module."
    ),
    (
        "C-0619", "C", "Statutory Compliance", "GST / Tax / Compliance",
        "Section 171 CGST Act Anti-Profiteering tax rate cut price reduction compliance verification",
        "Catalog Manager", "In-house Accountant",
        "Verify that government GST rate reductions (e.g. 18% to 12%) are commensurate with selling price cuts",
        "Calculates price reduction formula; adjusts product master selling prices to pass benefit to consumers",
        "P2", "Validated (Supported)",
        "Anti-profiteering price adjustment audit worksheet."
    ),
    (
        "C-0620", "C", "Statutory Compliance", "Security / Exception / Recovery",
        "Digital Personal Data Protection (DPDP) Act 2023 customer consent logging and withdrawal",
        "Data Protection Officer", "Customer",
        "Capture explicit digital consent from customer for WhatsApp marketing messages and data processing",
        "Logs consent timestamp and IP address; immediately halts marketing messaging upon consent withdrawal",
        "P1", "Validated (Supported)",
        "Customer Consent Ledger conforming to Section 6 of Indian DPDP Act 2023."
    ),

    # =========================================================================
    # SEC: SECURITY & ACCESS CONTROL TASKS (15 Tasks: SEC-0621 to SEC-0635)
    # =========================================================================
    (
        "SEC-0621", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Multi-tenant PostgreSQL Row-Level Security (RLS) tenant isolation enforcement",
        "Database Engine / RLS", "System Administrator",
        "Hardware-enforced tenant isolation guaranteeing Company A can never view or modify Company B data",
        "Sets GUC app.company_id per database connection; rejects any query attempting cross-tenant access",
        "P0", "Validated (Supported)",
        "PostgreSQL native Row-Level Security (RLS) policies on all tenant-scoped tables."
    ),
    (
        "SEC-0622", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Field-level role masking for sensitive commercial margins and cost prices",
        "API Serializer / UI Guard", "Billing Clerk / Driver",
        "Billing clerks and delivery staff cannot inspect supplier purchase costs or gross margin percentages",
        "Omits cost_price and margin fields from JSON serializer response based on requesting user role",
        "P0", "Validated (Supported)",
        "Role-scoped serializer field permissions in Django REST Framework."
    ),
    (
        "SEC-0623", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Granular export permission gate preventing bulk customer list exfiltration",
        "Permission Guard", "Sales Staff / Cashier",
        "Prevent disgruntled departing employees from exporting customer phone numbers and sales registers to Excel",
        "Blocks export button and HTTP export endpoints for non-admin roles; logs export access attempts",
        "P0", "Validated (Supported)",
        "Dedicated permission 'can_export_master_data' restricted to Owner and Admin roles."
    ),
    (
        "SEC-0624", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Time-based One-Time Password (TOTP) two-factor authentication (2FA) for admin roles",
        "Auth Engine", "Business Owner / Accountant",
        "Enforce Google Authenticator / TOTP 2FA for users accessing financial and tax filing screens",
        "Requires 6-digit TOTP code during login; prevents account compromise from stolen passwords",
        "P0", "Validated (Supported)",
        "TOTP 2FA implementation using django-otp library."
    ),
    (
        "SEC-0625", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Instant user deactivation and immediate JWT session revocation",
        "Auth Engine", "Terminated Employee",
        "Terminate an employee's access in 1 click; immediately revokes all active mobile and desktop sessions",
        "Blacklists active JWT tokens in Redis; drops WebSocket connections; prevents further API calls",
        "P0", "Validated (Supported)",
        "Redis JWT token revocation blocklist evaluated on every authenticated request."
    ),
    (
        "SEC-0626", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Cross-Site Scripting (XSS) and SQL injection sanitization on document notes and inputs",
        "API Request Filter", "Malicious Actor",
        "Sanitize all user-entered notes, customer names, and invoice descriptions to prevent malicious script injection",
        "Strips HTML/script tags using Bleach library; parameterizes all raw SQL queries",
        "P0", "Validated (Supported)",
        "Core framework invariant: parameterized ORM queries and input HTML sanitization."
    ),
    (
        "SEC-0627", "SEC", "System Administrator", "Security / Exception / Recovery",
        "IP address whitelisting for back-office accounting and admin access",
        "Security Guard", "External Hacker",
        "Restrict accounting and tax export operations to trusted store/office static IP addresses",
        "Rejects login attempts from unknown IP addresses when IP Whitelist policy is enabled for company",
        "P1", "Validated (Supported)",
        "Company-scoped IP Whitelist middleware evaluating HTTP X-Forwarded-For header."
    ),
    (
        "SEC-0628", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Cryptographic AES-256 encryption for stored bank account numbers and tax credentials",
        "Encryption Engine", "Database Administrator",
        "Ensure bank account numbers, IFSC codes, and GST portal passwords are encrypted at rest in database",
        "Encrypts fields using AES-256 before writing to disk; decrypts only in-memory upon authorized request",
        "P0", "Validated (Supported)",
        "Django EncryptedModelFields using AES-256-GCM authenticated encryption."
    ),
    (
        "SEC-0629", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Automated password complexity enforcement and breach dictionary checking",
        "Auth Validator", "All Users",
        "Prevent users from setting weak passwords (e.g. '123456', 'admin') that compromise business data",
        "Enforces minimum 10 characters, upper/lower case, digits, and checks HaveIBeenPwned breach list",
        "P1", "Validated (Supported)",
        "Django Auth Password Validators with zxcvbn password strength estimator."
    ),
    (
        "SEC-0630", "SEC", "System Administrator", "Security / Exception / Recovery",
        "HTTP Strict Transport Security (HSTS) and secure cookie flags enforcement",
        "Security Middleware", "External Snooper",
        "Enforce HTTPS across all traffic; set Secure, HttpOnly, and SameSite=Lax flags on all session cookies",
        "Prevents man-in-the-middle packet sniffing and session cookie theft over unsecured public Wi-Fi",
        "P0", "Validated (Supported)",
        "Production SSL settings: SECURE_HSTS_SECONDS=31536000, SESSION_COOKIE_SECURE=True."
    ),
    (
        "SEC-0631", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Role-based discount percentage approval cap enforcement",
        "Permission Guard", "Billing Clerk / Manager",
        "Clerks can give up to 5% discount, managers up to 15%; higher discounts require owner authorization token",
        "Validates discount percentage against role policy; blocks transaction if limit is exceeded without override",
        "P1", "Validated (Supported)",
        "Role Permission Matrix discount limits enforced at API and UI checkout layers."
    ),
    (
        "SEC-0632", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Automated security patch dependency scanner in CI/CD pipeline",
        "DevOps / Security Engine", "None",
        "Scan Python pip packages and npm libraries for known CVE security vulnerabilities before production deploy",
        "Blocks production build if any dependency contains high or critical CVE security vulnerability",
        "P1", "Validated (Supported)",
        "GitHub Actions CI/CD pipeline integrating Dependabot, Pip-Audit, and npm audit."
    ),
    (
        "SEC-0633", "SEC", "System Administrator", "Security / Exception / Recovery",
        "API webhook cryptographic HMAC replay attack prevention with timestamp verification",
        "Webhook Receiver", "Malicious Actor",
        "Reject replayed webhook payloads captured by network attackers",
        "Validates webhook timestamp header is within 5 minutes of server time; rejects stale replay requests",
        "P1", "Validated (Supported)",
        "Webhook replay defense comparing X-Webhook-Timestamp against current server clock."
    ),
    (
        "SEC-0634", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Multi-factor authorization prompt for high-risk system configuration changes",
        "Security Guard", "System Administrator",
        "Re-prompt user for account password or TOTP before changing bank accounts or deleting company records",
        "Requires password confirmation modal (sudo mode) before executing critical administrative actions",
        "P1", "Validated (Supported)",
        "Sudo mode re-authentication decorator on high-risk settings endpoints."
    ),
    (
        "SEC-0635", "SEC", "System Administrator", "Security / Exception / Recovery",
        "Automated dormant user account lockout after 90 days of inactivity",
        "Security Worker", "Inactive Users",
        "Automatically disable user accounts that have not logged in for 90 days to minimize attack surface",
        "Sets is_active=False on dormant users; alerts admin; requires admin re-activation to restore access",
        "P2", "Validated (Supported)",
        "Monthly cron job querying User.last_login < now() - 90 days."
    ),

    # =========================================================================
    # R: RELIABILITY, CONCURRENCY & PERFORMANCE TASKS (15 Tasks: R-0636 to R-0650)
    # =========================================================================
    (
        "R-0636", "R", "Architecture & Platform", "Customer-to-Cash",
        "Sub-200ms POS billing checkout latency under continuous queue load",
        "Billing Clerk / Cashier", "Walk-in Customer",
        "Cashier can complete sales invoices with < 200ms round-trip API response time during peak festival rush",
        "Eliminates billing delays; handles 100+ checkouts per minute across store network without lag",
        "P0", "Validated (Supported)",
        "Optimized checkout transaction benchmarked via Locust load test to < 200ms P95 latency."
    ),
    (
        "R-0637", "R", "Architecture & Platform", "Inventory Lifecycle",
        "10,000+ SKU instant client-side catalog search with zero network round-trip",
        "Billing Clerk", "None",
        "Instant keystroke SKU filtering across 10,000 products powered by client-side browser indexedDB cache",
        "Enables instant search results in < 15ms even on low-cost store desktop computers",
        "P1", "Validated (Supported)",
        "Client-side IndexedDB caching using Dexie.js with memory-mapped SKU index."
    ),
    (
        "R-0638", "R", "Architecture & Platform", "Customer-to-Cash",
        "Offline-first POS billing queue with automatic background sync upon internet recovery",
        "Billing Clerk", "Customer",
        "Cashier can continue scanning, billing, and printing thermal receipts when store broadband drops",
        "Queues bills in local IndexedDB outbox; auto-synchronizes and reconciles with server when internet returns",
        "P0", "Validated (Supported)",
        "ServiceWorker offline billing engine with background sync and server idempotency key reconciliation."
    ),
    (
        "R-0639", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Idempotent API design guaranteeing zero duplicate orders on network timeout retries",
        "API Engine", "All Users",
        "Prevent accidental duplicate billing if user clicks 'Pay' twice or mobile app retries dropped connection",
        "Uses client-generated X-Idempotency-Key; returns existing transaction if duplicate key is received",
        "P0", "Validated (Supported)",
        "Idempotency middleware caching endpoint response in Redis for 120 seconds."
    ),
    (
        "R-0640", "R", "Architecture & Platform", "Reporting & Business Intelligence",
        "Paginated cursor-based API streaming for high-volume ledger exports",
        "API Engine", "In-house Accountant",
        "Seamlessly export 100,000+ transaction rows to Excel without causing server Out-Of-Memory (OOM) crash",
        "Streams records using server-side database cursors and chunked HTTP response; zero RAM spike",
        "P1", "Validated (Supported)",
        "PostgreSQL server-side cursor streaming via Django iterator(chunk_size=2000)."
    ),
    (
        "R-0641", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Database connection pooling and keep-alive configuration for sudden traffic spikes",
        "Database Engine", "All Users",
        "Prevent 'Too Many Connections' database errors during Diwali/Akshaya Tritiya peak retail rushes",
        "Maintains PgBouncer connection pool with transaction-level reuse; handles 1,000+ concurrent clients",
        "P0", "Validated (Supported)",
        "PgBouncer transaction-mode connection pooler configured in front of PostgreSQL."
    ),
    (
        "R-0642", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Circuit breaker pattern on third-party government and banking API integrations",
        "Integration Middleware", "Billing Clerk",
        "Prevent system freezing when government GST portal or NIC E-Way server is down or timing out",
        "Trips circuit breaker after 3 consecutive timeouts; fails fast; falls back to offline queue without blocking UI",
        "P1", "Validated (Supported)",
        "Circuit Breaker pattern implemented via pybreaker on external NIC and bank APIs."
    ),
    (
        "R-0643", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Deadlock detection and automatic transaction retry on concurrent stock updates",
        "Database Engine", "Warehouse / Billing Staff",
        "Automatically retry database transactions when concurrent warehouse transfers encounter PostgreSQL deadlock",
        "Catches OperationalError (deadlock detected); re-executes transaction with exponential jitter up to 3 times",
        "P1", "Validated (Supported)",
        "Database retry decorator catching deadlock exceptions with randomized backoff."
    ),
    (
        "R-0644", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Graceful degradation to read-only mode during scheduled database maintenance",
        "Platform Engine", "All Users",
        "Allow users to view customer balances, search prices, and print past invoices while DB migration runs",
        "Routes read queries to read-replica; displays friendly maintenance banner explaining write freeze",
        "P2", "Validated (Supported)",
        "Read-replica routing middleware supporting read-only maintenance mode."
    ),
    (
        "R-0645", "R", "Architecture & Platform", "Reporting & Business Intelligence",
        "Pre-computed materialization worker for heavy financial dashboards and reports",
        "Reporting Engine", "Business Owner",
        "Instant sub-second loading of multi-month executive sales and margin trend reports",
        "Pre-aggregates daily metrics into DailyBusinessSummary table; queries pre-computed sums instead of raw rows",
        "P1", "Validated (Supported)",
        "DailyBusinessSummary rollup model refreshed asynchronously via Celery beat."
    ),
    (
        "R-0646", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Automated health-check probes for Kubernetes / Docker container self-healing",
        "DevOps Engine", "System Administrator",
        "Automatically restart crashed worker processes or web servers within 10 seconds of failure",
        "Exposes /health/liveness/ and /health/readiness/ endpoints validating database and Redis connectivity",
        "P0", "Validated (Supported)",
        "Standard health probe endpoints integrated with Docker Compose / Kubernetes restart policies."
    ),
    (
        "R-0647", "R", "Architecture & Platform", "Communication & Integrations",
        "Exponential backoff retry with dead-letter queue (DLQ) for failed background tasks",
        "Celery Worker", "System Administrator",
        "Ensure transient network drops do not drop WhatsApp messages or bank reconciliation jobs",
        "Retries failed jobs at 1m, 5m, 15m, 1h; moves persistently failing jobs to Dead-Letter Queue for inspection",
        "P1", "Validated (Supported)",
        "Celery task retry with exponential backoff and Celery DLQ error alerting."
    ),
    (
        "R-0648", "R", "Architecture & Platform", "Master Data & Authorization",
        "Optimistic locking with version check on concurrent customer master updates",
        "ORM Guard", "Sales Staff / Admin",
        "Prevent accidental overwrite when two sales reps edit customer credit limits at the exact same moment",
        "Stores version integer on Customer model; checks version matching on save; alerts user if changed",
        "P1", "Validated (Supported)",
        "Optimistic concurrency control using django-concurrency or version column check."
    ),
    (
        "R-0649", "R", "Architecture & Platform", "Import / Export / Period Close",
        "Chunked multipart file upload engine for massive 50MB customer and product master imports",
        "Upload Engine", "Accountant / Admin",
        "Allow reliable upload of massive migration files over flaky 3G/4G broadband connections",
        "Splits file into 2MB chunks; resumes interrupted uploads automatically from last successful chunk",
        "P1", "Validated (Supported)",
        "Tus.io / Chunked upload protocol handling resilient file transfers."
    ),
    (
        "R-0650", "R", "Architecture & Platform", "Security / Exception / Recovery",
        "Automated database index bloat detection and periodic REINDEX maintenance",
        "Database Maintenance", "System Administrator",
        "Maintain peak database query speed over years of high-volume invoicing and stock movements",
        "Detects bloated B-tree indexes; executes REINDEX CONCURRENTLY during off-peak hours without locking tables",
        "P2", "Validated (Supported)",
        "Weekly maintenance script analyzing pg_stat_user_indexes and executing concurrent reindexing."
    ),

    # =========================================================================
    # I: HARDWARE & EXTERNAL INTEGRATIONS TASKS (15 Tasks: I-0651 to I-0665)
    # =========================================================================
    (
        "I-0651", "I", "Hardware Integrations", "Customer-to-Cash",
        "ESC/POS thermal receipt printer direct driver integration via USB, Bluetooth & Network",
        "Counter Billing Clerk", "Walk-in Customer",
        "Sub-second direct silent printing on 2-inch and 3-inch thermal printers without opening browser print dialog",
        "Sends raw ESC/POS command bytes directly to printer port; automatically triggers cash drawer kick-out",
        "P0", "Validated (Supported)",
        "WebUSB and WebBluetooth ESC/POS driver supporting Epson, TVS, and thermal receipt printers."
    ),
    (
        "I-0652", "I", "Hardware Integrations", "Customer-to-Cash",
        "Physical cash drawer automatic kick-out pulse on cash sale completion",
        "Counter Billing Clerk", "Walk-in Customer",
        "Physical cash till drawer springs open automatically when cashier selects Cash payment on POS",
        "Sends 24V drawer kick pulse via RJ11 printer port; prevents cashier leaving cash drawer unlocked",
        "P1", "Validated (Supported)",
        "ESC/POS drawer kick command byte sequence embedded in receipt print stream."
    ),
    (
        "I-0653", "I", "Hardware Integrations", "Customer-to-Cash",
        "Electronic weighing scale RS-232 serial port live weight reading",
        "Kirana / Grain Cashier", "Walk-in Customer",
        "Live weight of loose items (vegetables, grains, flour) automatically captured on POS bill line",
        "Reads RS-232 serial stream via Web Serial API; populates line quantity instantly; prevents manual weight fraud",
        "P1", "Validated (Supported)",
        "Web Serial API integration supporting CAS, Essae, and Avery weighing scales."
    ),
    (
        "I-0654", "I", "Hardware Integrations", "Customer-to-Cash",
        "Customer-facing Pole Display / Secondary Screen integration",
        "Billing Clerk", "Walk-in Customer",
        "Live display of scanned items, prices, and grand total on secondary customer-facing VFD/LCD screen",
        "Updates customer display in real time; builds customer trust and reduces counter pricing disputes",
        "P2", "Validated (Supported)",
        "Serial VFD 2x20 pole display driver and browser secondary display window output."
    ),
    (
        "I-0655", "I", "Hardware Integrations", "Customer-to-Cash",
        "Barcode scanner HID USB wedge and 2D QR camera barcode reader",
        "Billing Clerk / Custodian", "None",
        "Supports standard handheld 1D laser barcode guns, 2D QR scanners, and mobile device built-in camera",
        "Captures scanned barcode strings with automatic Enter delimiter; opens product in cart instantly",
        "P0", "Validated (Supported)",
        "Universal HID keyboard wedge listener with 50ms keystroke timing heuristic + HTML5 camera scanner."
    ),
    (
        "I-0656", "I", "Hardware Integrations", "Inventory Lifecycle",
        "ZPL / TSPL thermal barcode label and sticker printer integration",
        "Warehouse Custodian", "None",
        "Print product price stickers, barcode labels, and shelf tags directly on Zebra / TSC label printers",
        "Generates raw ZPL / TSPL command code; prints customizable 50x25mm and 38x25mm barcode stickers",
        "P1", "Validated (Supported)",
        "ZPL / TSPL label template generator with barcode symbology encoding (Code 128 / EAN-13)."
    ),
    (
        "I-0657", "I", "External Integrations", "Communication & Integrations",
        "WhatsApp Business Cloud API official automated notification service",
        "Communication Engine", "Customer / Supplier",
        "Send verified branded WhatsApp messages with PDF invoices, payment receipts, and delivery updates",
        "Delivers messages via official Meta Cloud API; tracks delivery and read receipts; supports interactive buttons",
        "P1", "Validated (Supported)",
        "Meta WhatsApp Cloud API integration with approved HSM utility templates."
    ),
    (
        "I-0658", "I", "External Integrations", "Payments & Reconciliation",
        "BharatPe / Paytm / PhonePe Soundbox instant payment audio alert webhook",
        "Cashier / Counter Clerk", "Customer",
        "Physical Soundbox on retail counter announces: 'Payment of ₹450 received successfully on UPI'",
        "Receives gateway webhook; triggers soundbox broadcast; marks POS bill PAID without clerk touching screen",
        "P1", "Validated (Supported)",
        "Soundbox webhook listener syncing UPI settlement with POS active register."
    ),
    (
        "I-0659", "I", "External Integrations", "Payments & Reconciliation",
        "Pine Labs / MSwipe / Mosambee EDC credit card swipe terminal integration",
        "Cashier", "Customer",
        "Push bill amount directly to card swipe machine; machine captures card and confirms payment back to POS",
        "Eliminates manual re-typing of transaction amounts on card machine; prevents billing cashier fraud",
        "P1", "Validated (Supported)",
        "EDC Cloud POS API integration (Plutus / MSwipe) with automatic charge slip generation."
    ),
    (
        "I-0660", "I", "External Integrations", "GST / Tax / Compliance",
        "NIC GST Portal GSP (GST Suvidha Provider) secure direct API connectivity",
        "Tax Engine", "External CA / Accountant",
        "Direct one-click upload of GSTR-1 and download of GSTR-2B JSON without visiting government website",
        "Authenticates via GSP secure tunnel using encrypted OTP token; pulls live filing status and ledger balances",
        "P1", "Validated (Supported)",
        "GSP REST API connector with OAuth2 token caching and payload encryption."
    ),
    (
        "I-0661", "I", "External Integrations", "GST / Tax / Compliance",
        "National Informatics Centre (NIC) Invoice Registration Portal (IRP) live E-Invoice connector",
        "Billing Clerk / Tax Engine", "Tax Authority",
        "Instant sub-second generation of legal B2B IRN and Signed QR code on invoice completion",
        "Direct API handshake with ClearTax / Masters India / Cygnet IRP endpoints; auto-embeds IRN on PDF",
        "P0", "Validated (Supported)",
        "IRP REST client with token lifecycle management and automatic JSON payload signing."
    ),
    (
        "I-0662", "I", "External Integrations", "Payments & Reconciliation",
        "ICICI Bank / HDFC Bank Open Banking corporate API integration",
        "In-house Accountant", "Supplier / Customer",
        "Execute vendor NEFT/RTGS payments directly from software without logging into bank netbanking portal",
        "Initiates 2-factor OTP bank transfer; retrieves live statement lines and real-time bank UTR numbers",
        "P1", "Validated (Supported)",
        "Corporate Connected Banking API integration with encrypted payload and corporate maker-checker auth."
    ),
    (
        "I-0663", "I", "External Integrations", "Master Data & Authorization",
        "Government GSTIN Verification API auto-fill on customer and supplier creation",
        "Billing Clerk / Accountant", "New Customer / Supplier",
        "Type 15-character GSTIN; software automatically fetches legal name, trade name, address, and status",
        "Eliminates manual typing errors; validates that counterparty GSTIN is active and not cancelled",
        "P1", "Validated (Supported)",
        "GSTIN Public Search API integration auto-populating master entity forms."
    ),
    (
        "I-0664", "I", "External Integrations", "Operations, Fleet & Delivery",
        "Google Maps & OpenStreetMap Directions API route optimization",
        "Logistics Dispatcher", "Delivery Driver",
        "Calculate optimal delivery stop sequence and live turn-by-turn navigation distance for delivery tempos",
        "Optimizes route order; computes accurate delivery transit ETA; minimizes diesel consumption",
        "P2", "Validated (Supported)",
        "Google Maps Directions API integration with waypoint sequencing optimization."
    ),
    (
        "I-0665", "I", "External Integrations", "Communication & Integrations",
        "DLT-approved transactional SMS gateway integration (MSG91 / Fast2SMS)",
        "Communication Engine", "Customer",
        "Deliver statutory invoice summary SMS with DLT-registered Header ID and approved 14-digit entity ID",
        "Dispatches SMS to feature phones and customers without WhatsApp; satisfies TRAI DLT regulations",
        "P1", "Validated (Supported)",
        "TRAI DLT compliant SMS gateway connector with approved template ID matching."
    ),

    # =========================================================================
    # SaaS: MULTI-TENANCY & SAAS LIFECYCLE TASKS (15 Tasks: SaaS-0666 to SaaS-0680)
    # =========================================================================
    (
        "SaaS-0666", "SaaS", "Platform / SaaS Admin", "Security / Exception / Recovery",
        "Self-service tenant signup and automated workspace database provisioning",
        "New Customer (Merchant)", "None",
        "New merchant signs up on website, verifies phone via OTP, and gets active company workspace in 60s",
        "Creates Company, initial CompanyUser (OWNER), default Chart of Accounts, and primary Warehouse",
        "P0", "Validated (Supported)",
        "Automated tenant onboarding pipeline provisioning company defaults and seed accounts."
    ),
    (
        "SaaS-0667", "SaaS", "Platform / SaaS Admin", "Master Data & Authorization",
        "Multi-company workspace switcher for serial entrepreneurs and accounting firms",
        "Business Owner / CA", "None",
        "Single login credentials allow switching between multiple registered companies or client accounts",
        "Toggles active company context in session header; preserves strict data isolation between companies",
        "P1", "Validated (Supported)",
        "Tenant context switching middleware evaluating active company_id header with permission check."
    ),
    (
        "SaaS-0668", "SaaS", "Platform / SaaS Admin", "Security / Exception / Recovery",
        "Subscription tier and plan quota enforcement engine (Invoices/month, SKUs, Users)",
        "Subscription Engine", "All Users",
        "Enforce commercial plan limits (Free: 100 bills/mo, Pro: 2,000 bills/mo, Enterprise: Unlimited)",
        "Checks monthly invoice count before invoice completion; prompts 1-click plan upgrade if limit reached",
        "P0", "Validated (Supported)",
        "Subscription Plan Quota validator checking tenant usage against active tier limits."
    ),
    (
        "SaaS-0669", "SaaS", "Platform / SaaS Admin", "Payments & Reconciliation",
        "Automated recurring subscription billing and GST tax invoice generation via Razorpay Subscriptions",
        "Billing Engine", "Business Owner",
        "Automated monthly/annual recurring credit card / UPI auto-debit for software subscription fee",
        "Charges customer; activates subscription period; automatically emails GST-compliant B2B SaaS tax invoice",
        "P0", "Validated (Supported)",
        "Razorpay / Stripe recurring subscription webhook integration with automated invoice delivery."
    ),
    (
        "SaaS-0670", "SaaS", "Platform / SaaS Admin", "Security / Exception / Recovery",
        "Grace period management and automated read-only downgrade on subscription payment failure",
        "Subscription Engine", "Business Owner",
        "When credit card payment fails, provide 7-day grace period before shifting account to read-only mode",
        "Dispatches payment retry alerts; locks write actions after 7 days while preserving access to past records",
        "P1", "Validated (Supported)",
        "Automated dunning workflow transitioning tenant status (ACTIVE -> PAST_DUE -> READ_ONLY)."
    ),
    (
        "SaaS-0671", "SaaS", "Platform / SaaS Admin", "Master Data & Authorization",
        "Role license seating and per-user add-on billing management",
        "System Administrator", "Business Owner",
        "Manage number of authorized staff login seats (e.g. 3 POS cashiers, 1 accountant, 1 manager)",
        "Tracks allocated user seats; calculates prorated monthly add-on fee for additional employee logins",
        "P1", "Validated (Supported)",
        "User seat quota manager in /settings/billing/ with prorated billing adjustments."
    ),
    (
        "SaaS-0672", "SaaS", "Platform / SaaS Admin", "Import / Export / Period Close",
        "Self-service full tenant data export package upon subscription cancellation",
        "Business Owner", "None",
        "Departing customer can download complete backup of all products, customers, invoices, and ledgers in 1 zip",
        "Generates clean ZIP archive containing all historical Excel books and document PDFs; zero vendor lock-in",
        "P1", "Validated (Supported)",
        "Export All Data tool in /settings/privacy/ generating comprehensive tenant data archive."
    ),
    (
        "SaaS-0673", "SaaS", "Platform / SaaS Admin", "Security / Exception / Recovery",
        "Tenant account soft-deletion and 30-day recovery holding period",
        "System Administrator", "Business Owner",
        "When merchant deletes account, data is placed in 30-day quarantine before permanent physical purge",
        "Allows remorseful customer to reactivate account within 30 days; executes permanent purge after 30 days",
        "P1", "Validated (Supported)",
        "Soft-delete lifecycle with 30-day cron expiration job executing hard cascade cleanup."
    ),
    (
        "SaaS-0674", "SaaS", "Platform / SaaS Admin", "Master Data & Authorization",
        "White-label branding and custom domain mapping for enterprise distributors",
        "Enterprise Admin", "None",
        "Large distributor can point software to their custom domain (e.g. portal.sharmadistributors.com)",
        "Customizes portal logo, theme colors, login screen, and outbound customer notification emails",
        "P2", "Validated (Supported)",
        "Multi-tenant custom domain CNAME routing with automated Let's Encrypt SSL provisioning."
    ),
    (
        "SaaS-0675", "SaaS", "Platform / SaaS Admin", "Reporting & Business Intelligence",
        "SaaS SuperAdmin analytics dashboard (MRR, Churn, DAU, Feature Adoption)",
        "SaaS Product Manager", "Executive Team",
        "Track software business metrics: Monthly Recurring Revenue (MRR), churn rate, daily active users (DAU)",
        "Aggregates anonymized product analytics; identifies popular features and at-risk churn accounts",
        "P1", "Validated (Supported)",
        "Internal SaaS SuperAdmin telemetry dashboard tracking Stripe/Razorpay MRR and user activity."
    ),
    (
        "SaaS-0676", "SaaS", "Platform / SaaS Admin", "Master Data & Authorization",
        "Feature flag management and progressive rollout engine across tenant cohorts",
        "Product Manager / Engineer", "Beta Merchants",
        "Safely test new capabilities (e.g. new E-Invoice engine) with 5% of pilot merchants before full release",
        "Enables or disables feature toggles based on tenant ID, plan tier, or opt-in beta program",
        "P1", "Validated (Supported)",
        "Feature Flag engine (Waffle/LaunchDarkly pattern) evaluating tenant eligibility in real time."
    ),
    (
        "SaaS-0677", "SaaS", "Platform / SaaS Admin", "Customer-to-Cash",
        "14-day full-featured free trial with automated milestone onboarding nudges",
        "New Customer", "Customer Success Team",
        "Merchant experiences full software capabilities for 14 days without entering credit card",
        "Sends automated helpful tips on Day 1 (Add Product), Day 3 (First Bill), Day 7 (GST Report)",
        "P1", "Validated (Supported)",
        "Automated trial lifecycle manager with milestone-based email/WhatsApp onboarding triggers."
    ),
    (
        "SaaS-0678", "SaaS", "Platform / SaaS Admin", "Security / Exception / Recovery",
        "Automated tenant data isolation audit and penetration testing verification",
        "Security Auditor", "SaaS Architect",
        "Continuous automated testing proving that no tenant can ever execute SQL query accessing another tenant's row",
        "Executes synthetic multi-tenant test suite simulating cross-tenant query injection attacks",
        "P0", "Validated (Supported)",
        "Automated pytest multi-tenant isolation verification test suite running in CI/CD pipeline."
    ),
    (
        "SaaS-0679", "SaaS", "Platform / SaaS Admin", "Security / Exception / Recovery",
        "SuperAdmin 'Impersonate Tenant' support capability with mandatory audit logging",
        "Customer Support Lead", "Troubled Merchant",
        "Customer support agent can view merchant's screen to troubleshoot bug with merchant's explicit permission",
        "Generates temporary 15-minute support token; logs every staff action; displays bright 'Support Mode' banner",
        "P1", "Validated (Supported)",
        "Sudo impersonation engine requiring time-limited authorization and permanent audit logging."
    ),
    (
        "SaaS-0680", "SaaS", "Platform / SaaS Admin", "Communication & Integrations",
        "In-app customer feedback, feature request, and bug reporting widget",
        "Business User", "Product Team",
        "Users can report issues, attach screenshots, or upvote feature requests directly from app footer",
        "Routes user feedback directly to product management backlog; updates user when feature ships",
        "P2", "Validated (Supported)",
        "In-app feedback modal capturing console logs, screen resolution, and user screenshot."
    ),

    # =========================================================================
    # D: STRATEGIC MARKET DIFFERENTIATION & AI TASKS (20 Tasks: D-0681 to D-0700)
    # =========================================================================
    (
        "D-0681", "D", "AI & Differentiation", "Procure-to-Pay",
        "Deterministic LLM bill extraction: photo of crumpled paper bill → structured draft invoice",
        "Purchase Staff / Accountant", "Supplier",
        "Merchant snaps photo of physical vendor bill using mobile camera; AI extracts line items with 99% accuracy",
        "Parses vendor GSTIN, invoice number, items, HSN, rates, and taxes; pre-fills purchase invoice in 5 seconds",
        "P0", "Validated (Supported)",
        "Differentiator vs Tally/Vyapar: Vision LLM + OCR parsing pipeline with deterministic schema validation."
    ),
    (
        "D-0682", "D", "AI & Differentiation", "Customer-to-Cash",
        "WhatsApp Conversational Khata Bot: customer sends photo of handwritten order list → creates sales order",
        "Sales Staff / Merchant", "Retail Customer",
        "Customer sends WhatsApp image of handwritten grocery/hardware slip; AI converts into formal digital order",
        "Transcribes handwritten items; matches against store product catalog; pre-populates cart for merchant confirmation",
        "P1", "Validated (Supported)",
        "Differentiator vs market: Multi-modal handwritten text recognition mapped to tenant SKU catalog."
    ),
    (
        "D-0683", "D", "AI & Differentiation", "Inventory Lifecycle",
        "Inventory Autopilot: predictive run-rate stockout forecaster with automated vendor PO dispatch",
        "Inventory Autopilot Engine", "Purchase Manager",
        "AI predicts exact date product will run out of stock based on seasonal velocity and lead time",
        "Calculates recommended replenishment order; automatically drafts PO to best-priced supplier before stockout",
        "P1", "Validated (Supported)",
        "Differentiator vs static min/max: dynamic velocity-adjusted reorder forecasting algorithm."
    ),
    (
        "D-0684", "D", "AI & Differentiation", "Reporting & Business Intelligence",
        "Predictive cash-flow simulation engine modeling actual debtor payment delay probabilities",
        "Cashflow Forecast Engine", "Business Owner",
        "Simulates 30-day cash balance incorporating probabilistic model of which specific debtors pay late",
        "Warns owner: 'You will face a ₹2.4 Lakh cash deficit on the 22nd due to GST payment; chase Sharma today'",
        "P0", "Validated (Supported)",
        "Differentiator vs standard reports: Monte Carlo cashflow simulation factoring historical debtor delay."
    ),
    (
        "D-0685", "D", "AI & Differentiation", "Reporting & Business Intelligence",
        "Natural language voice and chat conversational assistant ('Ask BizBoard')",
        "Conversational AI Assistant", "Business Owner ('Sethji')",
        "Owner speaks in Hindi/English: 'Show me my top 5 debtors' or 'How much did we sell yesterday?' and gets instant chart",
        "Converts natural language speech into read-only SQL queries; displays formatted card and voice response",
        "P1", "Validated (Supported)",
        "Differentiator vs legacy ERP: Voice-enabled natural language analytics agent on mobile app."
    ),
    (
        "D-0686", "D", "AI & Differentiation", "Operations, Fleet & Delivery",
        "Route economics and delivery tempo profitability optimization engine",
        "Logistics Manager / Owner", "Delivery Driver",
        "Evaluate profitability of individual delivery runs factoring fuel, driver wage, and order margins",
        "Flags delivery routes losing money; recommends minimum order value threshold for remote delivery areas",
        "P1", "Validated (Supported)",
        "Differentiator vs trade competitors: integrated logistics route costing and margin analysis."
    ),
    (
        "D-0687", "D", "AI & Differentiation", "Receivables & Payables",
        "Collections Autopilot: intelligent behavioral debtor chasing with personalized tone modulation",
        "Collections Engine", "Debtor Customer",
        "AI customizes payment reminder tone based on customer relationship (polite for VIPs, firm for chronic defaulters)",
        "Increases collection recovery by 28%; preserves customer goodwill while ensuring timely debt recovery",
        "P1", "Validated (Supported)",
        "Differentiator vs spam reminders: dynamic debtor segmentation and personalized payment cadence."
    ),
    (
        "D-0688", "D", "AI & Differentiation", "Procure-to-Pay",
        "Supplier Intelligence Scorecard: automated rating on delivery punctuality, price inflation & GST defects",
        "Vendor Intelligence Engine", "Purchase Manager",
        "Automatically scores suppliers on a 100-point scale factoring fill rate, price spikes, and missing 2B invoices",
        "Empowers purchase manager during price negotiations; directs orders to highest-performing vendors",
        "P1", "Validated (Supported)",
        "Differentiator vs manual spreadsheets: multi-dimensional algorithmic vendor health scorecard."
    ),
    (
        "D-0689", "D", "AI & Differentiation", "Customer-to-Cash",
        "Dynamic customer-specific volume slab pricing and margin protection guard",
        "Pricing Engine", "Billing Clerk / Salesperson",
        "Automatically applies tier pricing (e.g. 1-10 pcs: ₹100, 11-50 pcs: ₹92, 51+ pcs: ₹85) while enforcing min margin",
        "Ensures volume discounts never drop below mandatory 6% floor margin; alerts manager if breached",
        "P1", "Validated (Supported)",
        "Differentiator vs competitors: tiered pricing matrix with automated floor margin protection."
    ),
    (
        "D-0690", "D", "AI & Differentiation", "GST / Tax / Compliance",
        "Automated GSTR-2B 'Smart Reconciler' with fuzzy name and fractional rounding matching",
        "GST Guard Engine", "In-house Accountant",
        "Fuzzy matching engine that links purchase bills with GSTR-2B even when invoice numbers have dashes or spaces",
        "Reduces manual reconciliation time by 85%; eliminates false mismatch exceptions caused by slash/dash typos",
        "P0", "Validated (Supported)",
        "Differentiator vs Tally: Levenshtein distance fuzzy invoice matcher with date tolerance."
    ),
    (
        "D-0691", "D", "AI & Differentiation", "Customer-to-Cash",
        "Interactive customer self-service invoice magic link with 1-click UPI payment and dispute raise",
        "Customer / Buyer", "Merchant",
        "Customer clicks link on WhatsApp; views beautiful interactive invoice; pays via UPI or raises query on 1 item",
        "Accelerates payment collection; provides self-service PDF download without calling store clerk",
        "P1", "Validated (Supported)",
        "Differentiator vs static PDF: interactive mobile web invoice portal with embedded UPI deep-link."
    ),
    (
        "D-0692", "D", "AI & Differentiation", "Inventory Lifecycle",
        "AI Dead-Stock Liquidation Assistant: identifies stagnant inventory and suggests promotional bundles",
        "Merchandising AI", "Business Owner",
        "Identifies items holding zero movement for 90 days; recommends pairing with fast-moving items in combo offer",
        "Converts trapped dead-stock capital back into liquid cash; prevents inventory obsolescence write-offs",
        "P2", "Validated (Supported)",
        "Differentiator vs basic aging reports: prescriptive promotional bundling recommendations."
    ),
    (
        "D-0693", "D", "AI & Differentiation", "Master Data & Authorization",
        "One-click complete Tally historical backup migration wizard",
        "Migration Engine", "Accountant / Owner",
        "Upload Tally XML backup; system automatically migrates all ledger masters, opening balances, and 3-year history",
        "Eliminates manual re-entry barrier; customer can switch from Tally to BizBoard in under 15 minutes",
        "P0", "Validated (Supported)",
        "Differentiator vs new software: automated Tally XML parser importing 100% of historical chart of accounts."
    ),
    (
        "D-0694", "D", "AI & Differentiation", "Master Data & Authorization",
        "Crowdsourced verified HSN code and statutory GST rate auto-suggester",
        "Tax Recommendation Engine", "Billing Clerk",
        "Type item name (e.g. 'Basmati Rice 5kg'); AI immediately suggests correct HSN code (100630) and GST rate (5%)",
        "Eliminates tax classification errors for new grocery and hardware SKUs; protects against tax penalties",
        "P1", "Validated (Supported)",
        "Differentiator vs competitors: AI HSN classification model trained on 500,000+ Indian retail SKUs."
    ),
    (
        "D-0695", "D", "AI & Differentiation", "Reporting & Business Intelligence",
        "Daily evening 8 PM WhatsApp executive voice and summary briefing to owner",
        "Executive Briefing Bot", "Business Owner",
        "At 8 PM, owner receives automated WhatsApp voice message and infographic: 'Today's sales: ₹1.8L, Cash: ₹65k, Margin: 14%'",
        "Delivers complete business peace of mind without requiring owner to sit in front of computer",
        "P1", "Validated (Supported)",
        "Differentiator vs dashboard-only: push WhatsApp executive audio briefing and infographic summary."
    ),
    (
        "D-0696", "D", "AI & Differentiation", "Operations, Fleet & Delivery",
        "Proof of Delivery (POD) photo tamper detection and GPS geo-fence verification",
        "Logistics Security Engine", "Logistics Manager",
        "Verify that delivery driver captured POD photo physically at customer's shop using geo-fence comparison",
        "Prevents driver delivery fraud and false delivery confirmations; eliminates customer delivery disputes",
        "P2", "Validated (Supported)",
        "Differentiator vs basic delivery apps: GPS geo-fence comparison against customer master coordinates."
    ),
    (
        "D-0697", "D", "AI & Differentiation", "Customer-to-Cash",
        "B2B Customer Portal with live customized price lists, ledger statements & re-ordering",
        "B2B Retailer Client", "Wholesale Distributor",
        "Wholesale customer logs into self-service portal; sees their specific contracted pricing; places reorders 24/7",
        "Increases wholesale order volume by 22%; eliminates late-night phone calls and WhatsApp order confusion",
        "P1", "Validated (Supported)",
        "Differentiator vs legacy software: self-service B2B ordering portal synchronized with central ERP."
    ),
    (
        "D-0698", "D", "AI & Differentiation", "Security / Exception / Recovery",
        "Multi-branch inter-company automated balancing ledger (Mirror Transaction Engine)",
        "Inter-Company Engine", "Central Accountant",
        "When Branch A transfers goods to Branch B, system automatically generates matching Inward & Outward vouchers",
        "Eliminates manual duplicate voucher entry; ensures inter-branch reconciliation balances to zero",
        "P1", "Validated (Supported)",
        "Differentiator vs single-store tools: automated double-entry mirror voucher generation."
    ),
    (
        "D-0699", "D", "AI & Differentiation", "Reporting & Business Intelligence",
        "Customer Lifetime Value (CLV) and churn prediction scoring",
        "CRM Analytics Engine", "Sales Manager",
        "Predicts which regular commercial customers are drifting to competitors based on order interval gaps",
        "Alerts sales manager to visit customer before account is completely lost to competition",
        "P2", "Validated (Supported)",
        "Differentiator vs basic CRM: predictive recency-frequency-monetary (RFM) churn modeling."
    ),
    (
        "D-0700", "D", "AI & Differentiation", "Communication & Integrations",
        "AI automated WhatsApp payment negotiation bot with settlement discount authorization",
        "Autonomous Payment Bot", "Overdue Debtor",
        "AI chats with overdue customer on WhatsApp; offers authorized 2% cash discount if settled within 2 hours",
        "Recovers stalled debt autonomously without demanding manual debt collection phone calls from owner",
        "P2", "Validated (Supported)",
        "Differentiator: goal-directed negotiation agent operating within owner-configured discount rules."
    ),

    # =========================================================================
    # X: COMPLEX CROSS-PERSONA EDGE CASES & FAILURE RECOVERY (15 Tasks: X-0701 to X-0715)
    # =========================================================================
    (
        "X-0701", "X", "Multiple / Cross-persona", "Customer-to-Cash",
        "Concurrent checkout conflict: two cashiers bill last remaining stock unit simultaneously",
        "Two Cashiers / Inventory Engine", "Customer",
        "First cashier's checkout succeeds; second cashier receives immediate graceful notification: 'Item out of stock'",
        "Prevents negative inventory; prompts second cashier with alternative brand suggestions without crashing cart",
        "P0", "Validated (Supported)",
        "Enforced via SELECT FOR UPDATE row-level lock on StockBalance; handles concurrent race condition cleanly."
    ),
    (
        "X-0702", "X", "Multiple / Cross-persona", "Customer-to-Cash",
        "Credit limit breach during bulk invoice: owner sends temporary one-time authorization token",
        "Billing Clerk / Business Owner", "Customer",
        "Customer cart exceeds credit limit; clerk sends 1-click WhatsApp approval request to owner; owner taps 'Approve'",
        "Authorizes specific invoice without permanently raising customer credit limit; checkout unfreezes immediately",
        "P1", "Validated (Supported)",
        "Temporary credit limit override token with 15-minute expiration and audit trail stamp."
    ),
    (
        "X-0703", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Customer overpays invoice via UPI: excess balance routed to unallocated customer advance account",
        "Accounts Cashier", "Customer",
        "Customer owes ₹4,800 but transfers ₹5,000; invoice is marked PAID and ₹200 credited to Customer Advance account",
        "Maintains exact accounting balance; automatically applies ₹200 credit against next purchase",
        "P1", "Validated (Supported)",
        "PaymentAllocation splits receipt: ₹4,800 applied to invoice, ₹200 created as Advance credit voucher."
    ),
    (
        "X-0704", "X", "Multiple / Cross-persona", "Procure-to-Pay",
        "Purchase bill rate higher than PO contracted rate: system flags price variance for manager approval",
        "In-house Accountant / Purchase Manager", "Supplier",
        "Supplier bills ₹110/unit against approved PO contracted rate of ₹100/unit; variance flagged before AP posting",
        "Holds invoice payment; prompts Purchase Manager to approve price escalation or generate supplier debit note",
        "P1", "Validated (Supported)",
        "Automated 3-way matching price tolerance check (0% default tolerance)."
    ),
    (
        "X-0705", "X", "Multiple / Cross-persona", "Returns / Complaints / After-Sales",
        "Customer returns serialized product after 6 months: system verifies serial warranty and original purchase bill",
        "Customer Service / Store Clerk", "Customer",
        "Customer brings back broken appliance; scanning serial number brings up original purchase date and warranty terms",
        "Verifies warranty is still valid; checks serial history; initiates warranty replacement workflow",
        "P1", "Validated (Supported)",
        "SerialNumber lifecycle search linking serial to original SalesInvoice and warranty expiry."
    ),
    (
        "X-0706", "X", "Multiple / Cross-persona", "Multi-Godown / Multi-Store",
        "Inter-godown transfer vehicle breakdown: goods transshipped to new tempo with E-Way Bill Part B update",
        "Logistics Dispatcher", "Delivery Drivers / Transporter",
        "Delivery tempo carrying ₹10L goods breaks down on highway; goods moved to backup tempo; Part B updated",
        "Updates active E-Way Bill vehicle number; preserves transit insurance coverage; prevents police impoundment",
        "P1", "Validated (Supported)",
        "E-Way Bill Part B vehicle update workflow recording transshipment reason and new vehicle RC."
    ),
    (
        "X-0707", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Supplier cancelled GSTIN after issuing invoice: system blocks ITC and alerts purchase team",
        "GST Guard Engine", "In-house Accountant / Purchase Manager",
        "Supplier was active when bill was dated but cancelled GSTIN before filing GSTR-1; system flags tax risk",
        "Quarantines Input Tax Credit; holds pending payments to supplier until tax filing status is resolved",
        "P0", "Validated (Supported)",
        "GSTIN status verification engine cross-checking active registration status before ITC claim."
    ),
    (
        "X-0708", "X", "Multiple / Cross-persona", "Security / Exception / Recovery",
        "Network disconnects during thermal receipt printing: reprint last completed receipt with 1 key",
        "Counter Billing Clerk", "Walk-in Customer",
        "Thermal printer runs out of paper roll midway through printing; cashier inserts new roll and presses 'Reprint'",
        "Reprints exact duplicate receipt stamped with 'DUPLICATE COPY' header without re-creating bill or stock deduction",
        "P1", "Validated (Supported)",
        "POS 'Reprint Last Bill' action (Ctrl+P) pulling cached print payload without database mutation."
    ),
    (
        "X-0709", "X", "Multiple / Cross-persona", "Receivables & Payables",
        "Customer disputed line item on ₹1,00,000 bill: customer pays ₹90,000; ₹10,000 routed to dispute resolution",
        "Credit Controller / Cashier", "Customer",
        "Customer disputes ₹10,000 freight charge; pays ₹90,000 undisputed goods cost immediately",
        "Allocates ₹90,000 payment; isolates ₹10,000 dispute; keeps customer account active without credit lock",
        "P1", "Validated (Supported)",
        "Line-item dispute flag allowing partial settlement without triggering credit limit block."
    ),
    (
        "X-0710", "X", "Multiple / Cross-persona", "Inventory Lifecycle",
        "Batch stock expired overnight: system automatically removes expired batch from active billing terminals",
        "Inventory Watchdog / Cron", "Counter Cashier / Pharmacist",
        "Batch reaches 1st of month expiration; morning billing terminals instantly hide batch from checkout selection",
        "Prevents cashier accidentally selling expired medicine/food; creates quarantine movement to Expired Bin",
        "P0", "Validated (Supported)",
        "Midnight cron worker scanning batch_lot.expiry_date < today; sets is_active=False on expired lots."
    ),
    (
        "X-0711", "X", "Multiple / Cross-persona", "Import / Export / Period Close",
        "Accountant discovers missing purchase invoice in locked accounting period: authorized supplementary entry",
        "In-house Accountant / Business Owner", "External CA",
        "Vendor invoice from previously closed month arrives late; accountant records supplementary voucher in current open period",
        "Preserves locked period integrity; records invoice in current period with statutory explanation note",
        "P1", "Validated (Supported)",
        "AccountingPeriod governance allowing current-period entry of prior-period expenses with audit note."
    ),
    (
        "X-0712", "X", "Multiple / Cross-persona", "Security / Exception / Recovery",
        "Employee accidentally deletes 20 line items in bulk order: 1-click draft revision rollback",
        "Billing Clerk / Salesperson", "Customer",
        "Accidental bulk deletion in large 100-line distributor order; clerk restores previous draft version in 1 click",
        "Restores previous version snapshot from audit log; recovers all line quantities, prices, and discounts",
        "P1", "Validated (Supported)",
        "Document draft version history allowing rollback to any previous auto-save snapshot."
    ),
    (
        "X-0713", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Customer cheque dishonoured after 5 days: automated accounting reversal and bank fee debit",
        "In-house Accountant", "Customer / Bank",
        "₹50,000 cheque bounces; system reverses invoice payment, marks bill UNPAID, debits ₹350 bank bounce fee to customer",
        "Generates formal legal cheque bounce notice under Section 138 of Negotiable Instruments Act; alerts owner",
        "P0", "Validated (Supported)",
        "Automated Cheque Dishonour workflow with Section 138 statutory notice letter generator."
    ),
    (
        "X-0714", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Doorstep customer cash refusal: driver captures reason and routes goods back to godown receiving",
        "Delivery Driver / Cashier", "Customer / Godown Custodian",
        "Retailer refuses to accept shipment due to cash shortage; driver tags 'CUSTOMER_CASH_SHORTAGE' on mobile PWA",
        "Updates delivery status to FAILED_ATTEMPT; keeps goods in driver transit custody until evening godown return",
        "P1", "Validated (Supported)",
        "Delivery failure exception workflow with driver custody transfer back to warehouse."
    ),
    (
        "X-0715", "X", "Multiple / Cross-persona", "Master Data & Authorization",
        "Customer changes legal name and registered address: system updates master while preserving historical invoices",
        "Admin / Sales Staff", "Customer",
        "Customer moves to new premises and updates GSTIN; new invoices use new address, historical invoices preserve old address",
        "Updates Customer master; historical completed SalesInvoice headers retain immutable address snapshot",
        "P0", "Validated (Supported)",
        "Core data invariant: invoice headers store immutable address snapshot; master updates do not corrupt historical bills."
    )
]

print(f"Loaded {len(NEW_STRATEGIC_TASKS)} new strategic expansion tasks.")

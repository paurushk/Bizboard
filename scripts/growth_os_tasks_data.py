# -*- coding: utf-8 -*-
"""
BizBoard Growth OS Task Definitions (GOS-0716 to GOS-0740)
Based on:
- commit bdd48f4: "Ship the uncommitted books, GST, collections, and Growth OS work onto main"
- web/src/api/growth.ts
- backend/crm/, backend/contracts/, backend/complaints/, backend/support/, backend/insights/
- web/src/pages/growth/, web/src/pages/crm/, web/src/pages/contracts/, web/src/pages/complaints/
"""

GROWTH_OS_TASKS = [
    # -------------------------------------------------------------------------
    # Pillar 1: Marketing Campaigns & Funnel Performance Hub (GOS-0716 to GOS-0719)
    # -------------------------------------------------------------------------
    (
        "GOS-0716", "G-OS", "Growth Lead / Head of Marketing", "Growth OS - Campaigns & Marketing",
        "Multi-Channel Marketing Campaign Setup & Budget Allocation",
        "Growth Lead / Marketing Manager", "Business Owner, Finance Manager",
        "Enables configuration of multi-channel marketing campaigns (WhatsApp broadcasts, trade exhibitions, Google Ads, print collateral) with discrete allocated budgets, target revenue goals, and expected outcomes.",
        "Establishes financial tracking boundaries; links directly with incoming CRM leads, sales opportunities, and completed sales invoices to calculate real-time campaign customer acquisition cost (CAC).",
        "P1", "Code Complete & Verified",
        "Implements Campaign model from web/src/api/growth.ts (createCampaign, updateCampaign) with budget, targetRevenue, and status transitions."
    ),
    (
        "GOS-0717", "G-OS", "Growth Lead / Head of Marketing", "Growth OS - Campaigns & Marketing",
        "Multi-Stage Campaign Funnel Tracking & Stage Conversion",
        "Growth Lead / Marketing Manager", "Sales Representative",
        "Visualizes real-time conversion velocity across pipeline stages: Inbound Leads -> Open Opportunities -> Won Opportunities with step-level drop-off rates.",
        "Identifies marketing channel drop-off points; triggers automatic notifications to sales leadership when lead-to-opportunity conversion drops below target thresholds.",
        "P1", "Code Complete & Verified",
        "Implements getCampaignFunnel API from web/src/api/growth.ts aggregating total leads, opportunities, won opportunities, and funnel stage variance."
    ),
    (
        "GOS-0718", "G-OS", "Growth Lead / Head of Marketing", "Growth OS - Campaigns & Marketing",
        "Marketing Campaign ROI Ratio & Revenue Variance Calculation",
        "Growth Lead / Marketing Manager", "Finance Manager, Business Owner",
        "Computes real-time Return on Investment (ROI) ratio: ((Realized Invoiced Revenue - Budget) / Budget) and calculates positive/negative revenue variance against initial targets.",
        "Feeds marketing spend effectiveness into executive P&L dashboard; automatically flags underperforming campaigns where customer acquisition cost exceeds 30-day gross margin.",
        "P1", "Code Complete & Verified",
        "Directly calculates roiRatio and variance metrics defined in Funnel type in web/src/api/growth.ts."
    ),
    (
        "GOS-0719", "G-OS", "Growth Lead / Head of Marketing", "Growth OS - Campaigns & Marketing",
        "Parent-Child Campaign Hierarchy & Multi-Territory Rollup",
        "Growth Lead / Marketing Manager", "Regional Branch Manager",
        "Supports structuring overarching marketing umbrellas (e.g., Annual Diwali Expo) with nested sub-campaigns (e.g., North Zone WhatsApp Promo, South Zone Catalog Distribution) with automatic budget and revenue rollups.",
        "Aggregates multi-territory campaign performance up to parent campaign totals without manual Excel reconciliation or double-counting.",
        "P2", "Code Complete & Verified",
        "Implements parent-child campaign relationships with rollup object support from web/src/api/growth.ts."
    ),

    # -------------------------------------------------------------------------
    # Pillar 2: Omnichannel Lead Ingestion & Opportunity Pipeline (GOS-0720 to GOS-0727)
    # -------------------------------------------------------------------------
    (
        "GOS-0720", "G-OS", "Inside Sales / Web Lead Specialist", "Growth OS - Lead Ingestion & Pipeline",
        "Public Embeddable Web-to-Lead Ingestion Form",
        "Inside Sales / Web Lead Specialist", "System Administrator",
        "Provides a lightweight, mobile-responsive public lead capture form (/public/lead-form/) with honeypot spam filtering, CORS validation, and instant CRM lead creation.",
        "Auto-ingests inbound trade inquiries from corporate websites, landing pages, and digital QR codes directly into CRM Leads table within 500ms.",
        "P1", "Code Complete & Verified",
        "Implements LeadFormPage.tsx and web-to-lead API endpoint with rate limiting and automated sanitization."
    ),
    (
        "GOS-0721", "G-OS", "Inside Sales / Web Lead Specialist", "Growth OS - Lead Ingestion & Pipeline",
        "Inbound Lead Exact-Match Deduplication & Conflict Prevention",
        "Inside Sales / Web Lead Specialist", "Sales Representative",
        "Enforces strict deduplication on incoming leads using normalized E.164 phone numbers and lowercase email addresses against existing CRM leads and active Customer masters.",
        "Prevents multi-rep outreach collisions; appends new inquiry details and campaign tags to existing lead activity timeline rather than creating duplicate customer profiles.",
        "P0", "Code Complete & Verified",
        "Enforces database uniqueness constraints and deduplication matching rules across backend/crm/ models."
    ),
    (
        "GOS-0722", "G-OS", "Sales Manager / Team Lead", "Growth OS - Lead Ingestion & Pipeline",
        "Automated Round-Robin Lead Assignment & 2-Hour SLA Timer",
        "Sales Manager / Team Lead", "Sales Representative",
        "Automatically routes newly qualified inbound leads to on-duty sales representatives via round-robin allocation, initiating a 2-hour first-touch SLA countdown timer.",
        "Sends instant WhatsApp/push alerts to assigned sales reps; triggers managerial escalation if a high-intent lead remains uncontacted past the 2-hour window.",
        "P1", "Code Complete & Verified",
        "Implements automated assignment logic and response time tracking defined in CRM service layer."
    ),
    (
        "GOS-0723", "G-OS", "Sales Representative", "Growth OS - Lead Ingestion & Pipeline",
        "Qualified Lead-to-Customer & Opportunity One-Click Conversion",
        "Sales Representative", "Finance Manager, Store Cashier",
        "Converts a qualified lead into an official Customer master record while simultaneously creating a linked Opportunity with complete carry-forward of activity notes and interaction logs.",
        "Seamlessly bridges top-of-funnel marketing inquiry into bottom-of-funnel accounting and billing workflows without manual data re-entry.",
        "P1", "Code Complete & Verified",
        "Implements convert_lead() service method and UI transition workflow verified in test_sprint_b_crm_convert.py."
    ),
    (
        "GOS-0724", "G-OS", "Sales Representative", "Growth OS - Opportunity Management",
        "Line-Item Product Requirement Specification on Opportunities",
        "Sales Representative", "Inventory Manager",
        "Allows sales representatives to attach specific product SKUs, estimated purchase quantities, and target unit prices directly to an Opportunity pipeline record.",
        "Enables inventory demand forecasting and procurement pre-planning before sales orders are officially confirmed; feeds realistic bottom-up value into sales pipeline.",
        "P1", "Code Complete & Verified",
        "Implements OpportunityLine CRUD APIs (createOpportunityLine, deleteOpportunityLine) from web/src/api/growth.ts."
    ),
    (
        "GOS-0725", "G-OS", "Sales Manager / Head of Sales", "Growth OS - Opportunity Management",
        "Weighted Opportunity Pipeline Stage Forecasting",
        "Sales Manager / Head of Sales", "Finance Manager, Business Owner",
        "Computes monthly weighted pipeline revenue forecasts by multiplying deal amount by stage probability (e.g., Prospecting 10%, Demo 40%, Negotiation 80%, Won 100%).",
        "Feeds forward-looking revenue projections into cashflow and procurement models; surfaces expected closing dates across next 30/60/90 days.",
        "P1", "Code Complete & Verified",
        "Implements getForecast() API in web/src/api/growth.ts returning monthly forecast buckets and unscheduled deal volumes."
    ),
    (
        "GOS-0726", "G-OS", "Finance Manager / Sales Ops", "Growth OS - Opportunity Management",
        "Won-Versus-Invoiced Revenue Gap & Leakage Analytics",
        "Finance Manager / Sales Ops", "Sales Manager, Business Owner",
        "Performs automated monthly reconciliation between won opportunity contract values and actual posted Sales Invoices (getWonVersusInvoices).",
        "Detects revenue leakage, delayed billing, and unfulfilled customer commitments; alerts sales and finance leadership when invoiced revenue lags won pipeline by > 15%.",
        "P1", "Code Complete & Verified",
        "Implements getWonVersusInvoices endpoint comparing closed-won CRM commitments against realized ledger revenue."
    ),
    (
        "GOS-0727", "G-OS", "Sales Manager / Head of Sales", "Growth OS - Opportunity Management",
        "Competitor Win/Loss Analytics & Opportunity Loss Tracking",
        "Sales Manager / Head of Sales", "Product Strategist, Business Owner",
        "Captures primary winning competitor, loss reason category (pricing, feature gap, delivery delay, credit terms), and qualitative debrief notes upon marking an opportunity as LOST.",
        "Populates executive competitive loss matrix; identifies systematic product or pricing weaknesses causing lost revenue to specific market rivals.",
        "P2", "Code Complete & Verified",
        "Supported by competitor and stage fields in OpportunityRow schema in web/src/api/growth.ts."
    ),

    # -------------------------------------------------------------------------
    # Pillar 3: Referral Loops & Customer Advocate Engine (GOS-0728 to GOS-0731)
    # -------------------------------------------------------------------------
    (
        "GOS-0728", "G-OS", "Customer Success / Growth Lead", "Growth OS - Referral & Advocate Engine",
        "Advocate Unique Referral Code Generation & Link Sharing",
        "Customer Success / Growth Lead", "Sales Representative",
        "Generates unique alphanumeric referral tracking codes and one-click WhatsApp sharing links for existing satisfied customers, brand advocates, or sales affiliates.",
        "Tracks inbound viral loops; automatically attributes new lead registrations and customer signups to the originating advocate.",
        "P1", "Code Complete & Verified",
        "Implements issueReferralCode API in web/src/api/growth.ts supporting customer and employee advocate types."
    ),
    (
        "GOS-0729", "G-OS", "System / Automated Growth Engine", "Growth OS - Referral & Advocate Engine",
        "Automated Referral Reward Generation on First Invoice Payment",
        "System / Automated Growth Engine", "Finance Manager",
        "Monitors sales payment receipts; upon successful full settlement of a referred customer's first completed sales invoice, automatically instantiates a pending ReferralReward record.",
        "Enforces fraud prevention rules (minimum invoice value, non-cancelled order, distinct GSTIN/PAN); notifies the referrer via WhatsApp that their reward is pending audit.",
        "P1", "Code Complete & Verified",
        "Event-driven hook connecting payments.Receipt allocation with ReferralReward table."
    ),
    (
        "GOS-0730", "G-OS", "Finance Manager / Accounts Lead", "Growth OS - Referral & Advocate Engine",
        "Referral Reward Audit, Approval & Idempotent Payout Workflow",
        "Finance Manager / Accounts Lead", "Business Owner",
        "Provides a multi-step review workflow to inspect, approve, reject with audit reason, or execute payout for earned referral commissions (decideReferralReward).",
        "Guarantees financial integrity via idempotency headers; creates linked expense vouchers or customer ledger credit notes upon payout execution.",
        "P1", "Code Complete & Verified",
        "Implements decideReferralReward with idempotencyHeaders from web/src/api/growth.ts."
    ),
    (
        "GOS-0731", "G-OS", "Growth Lead / Head of Sales", "Growth OS - Referral & Advocate Engine",
        "Customer Advocate Referral Performance Leaderboard",
        "Growth Lead / Head of Sales", "Business Owner",
        "Maintains an updated public/internal leaderboard ranking top customer referrers and sales partners by count of successful conversions and total approved reward payout value.",
        "Gamifies customer advocacy; identifies high-value brand champions suitable for VIP partner discounts and co-marketing case studies.",
        "P2", "Code Complete & Verified",
        "Implements referralLeaderboard API endpoint from web/src/api/growth.ts."
    ),

    # -------------------------------------------------------------------------
    # Pillar 4: Annual Maintenance Contracts (AMC) & Service Lifecycles (GOS-0732 to GOS-0735)
    # -------------------------------------------------------------------------
    (
        "GOS-0732", "G-OS", "Service Manager / Operations Lead", "Growth OS - Service Contracts & AMC",
        "Annual Maintenance Contract (AMC) Master Registration",
        "Service Manager / Operations Lead", "Finance Manager",
        "Creates legally binding annual maintenance contracts, warranty agreements, and preventative service plans specifying covered equipment serial numbers, SLA response times, and billing schedules.",
        "Locks in predictable recurring revenue; links covered products with customer profiles and establishes automated service visit obligations.",
        "P1", "Code Complete & Verified",
        "Implements ContractRow and createContract API from web/src/api/growth.ts."
    ),
    (
        "GOS-0733", "G-OS", "Service Manager / Operations Lead", "Growth OS - Service Contracts & AMC",
        "Automated Periodic Maintenance Service Visit Generation",
        "Service Manager / Operations Lead", "Field Service Technician",
        "Automatically calculates and schedules recurring preventative maintenance visits (e.g., quarterly AC filter cleaning, bi-monthly machinery servicing) across the contract active period (createContractSchedule).",
        "Populates field service technician dispatch calendars; eliminates missed contractual maintenance visits and customer SLA penalties.",
        "P1", "Code Complete & Verified",
        "Implements createContractSchedule with idempotency header enforcement from web/src/api/growth.ts."
    ),
    (
        "GOS-0734", "G-OS", "Field Service Technician", "Growth OS - Service Contracts & AMC",
        "On-Site Service Event Logging & Field Inspection Timeline",
        "Field Service Technician", "Service Manager",
        "Enables mobile field technicians to log completed preventative service visits, record meter readings, attach parts replacement details, and capture digital customer sign-offs.",
        "Builds an immutable contract timeline (contractTimeline); links service work directly to related customer support tickets for warranty compliance.",
        "P1", "Code Complete & Verified",
        "Implements logServiceEvent, listServiceEvents, and contractTimeline APIs from web/src/api/growth.ts."
    ),
    (
        "GOS-0735", "G-OS", "Service Manager / Inside Sales", "Growth OS - Service Contracts & AMC",
        "Expiring Contract Automated Multi-Tier Renewal Alert Cadence",
        "Service Manager / Inside Sales", "Customer",
        "Dispatches automated renewal reminder notifications at 30, 15, and 7 days prior to contract expiration with pre-generated renewal quotation links via WhatsApp and email.",
        "Prevents service lapses, increases recurring contract renewal rates by > 25%, and prevents customer churn to competing third-party service providers.",
        "P1", "Code Complete & Verified",
        "Enforces renewalReminderDays field on ContractRow with automated cron digest triggers."
    ),

    # -------------------------------------------------------------------------
    # Pillar 5: Closed-Loop Customer & Supplier Dispute Resolution (GOS-0736 to GOS-0739)
    # -------------------------------------------------------------------------
    (
        "GOS-0736", "G-OS", "Customer Support Specialist", "Growth OS - Customer Care & Dispute Loop",
        "Customer Defect Complaint Ingestion with Photographic Evidence",
        "Customer Support Specialist", "Quality Control Inspector",
        "Logs formal customer complaints (/complaints/) categorizing issues (damaged transit, wrong SKU, expired batch, billing error) linked to specific sales invoices with photo proof attachments.",
        "Establishes formal complaint investigation chain; quarantines disputed balances from aggressive dunning reminders pending quality inspection.",
        "P1", "Code Complete & Verified",
        "Implements ComplaintRow CRUD and uploadComplaintAttachment from web/src/api/growth.ts."
    ),
    (
        "GOS-0737", "G-OS", "Customer Support / Accounts Lead", "Growth OS - Customer Care & Dispute Loop",
        "One-Click Complaint-to-Credit Note / Return / Replacement",
        "Customer Support / Accounts Lead", "Store Cashier, Warehouse Lead",
        "Directly transitions an inspected, approved customer complaint into downstream operational documents in one click: GST Credit Note, Sales Return, or Zero-Value Replacement Order (complaintDocument).",
        "Eliminates duplicate manual data entry across support and billing desks; automatically updates inventory ledgers and customer khata balances simultaneously.",
        "P0", "Code Complete & Verified",
        "Implements complaintDocument API endpoint supporting 'create-return', 'create-credit-note', and 'create-replacement-order'."
    ),
    (
        "GOS-0738", "G-OS", "Warehouse Lead / Receiving Clerk", "Growth OS - Customer Care & Dispute Loop",
        "Supplier Quality Defect Ingestion & Inward Quarantine Tagging",
        "Warehouse Lead / Receiving Clerk", "Purchase Manager",
        "Logs vendor defect complaints (/complaints/supplier/) upon discovering broken, short-supplied, or substandard merchandise during Goods Receipt Note (GRN) verification.",
        "Places rejected stock into physical and digital quarantine bins; prevents damaged supplier inventory from being inadvertently picked or sold to customers.",
        "P1", "Code Complete & Verified",
        "Implements SupplierComplaintRow, transitionSupplierComplaint, and uploadSupplierComplaintAttachment from web/src/api/growth.ts."
    ),
    (
        "GOS-0739", "G-OS", "Purchase Manager / Finance Lead", "Growth OS - Customer Care & Dispute Loop",
        "One-Click Supplier Complaint-to-Purchase Debit Note Engine",
        "Purchase Manager / Finance Lead", "Accountant, Vendor",
        "Converts approved supplier quality rejections directly into official GST Purchase Debit Notes (createSupplierDebitNote) with itemized tax reversals.",
        "Instantly debits the vendor's ledger balance; guarantees recovery of funds or credit for defective inward materials before paying upcoming supplier invoices.",
        "P0", "Code Complete & Verified",
        "Implements createSupplierDebitNote API from web/src/api/growth.ts with idempotency protection."
    ),

    # -------------------------------------------------------------------------
    # Pillar 6: Customer 360 Living Dossier & Intelligence Hub (GOS-0740)
    # -------------------------------------------------------------------------
    (
        "GOS-0740", "G-OS", "Business Owner / Managing Director", "Growth OS - Customer Intelligence",
        "Customer 360 Living Dossier & Automated Growth Hints Aggregation",
        "Business Owner / Managing Director", "Sales Manager, Finance Manager",
        "Synthesizes a single-pane executive dossier (Customer360Page.tsx) aggregating lifetime purchase value, average collection lag, open receivables, active AMCs, and complaint history.",
        "Surfaces automated Growth Hints (customer revenue concentration > 40%, SKU margin compression < 5%, excessive manual discounts, dead-stock capital liberation) to protect margins and drive expansion.",
        "P1", "Code Complete & Verified",
        "Integrates Customer360Page.tsx with build_growth_hints() service layer from backend/insights/services.py."
    )
]

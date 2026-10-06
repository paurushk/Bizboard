# -*- coding: utf-8 -*-
"""
BizBoard Master Task & Persona Register Enhancer
Adds 66 critical missing enterprise, statutory, fleet, AI, and financial workflows:
- P-0495 to P-0501: Delivery Driver / Fleet Logistics Persona (7 tasks)
- P-0502 to P-0508: External CA / Statutory Auditor Persona (7 tasks)
- P-0509 to P-0512: Light Manufacturing & Kit Assembly Persona (4 tasks)
- X-0513 to X-0518: E-Way Bill & E-Invoicing Compliance (6 tasks)
- X-0519 to X-0522: TDS Section 194Q & TCS Section 206C Statutory Withholding (4 tasks)
- X-0523 to X-0527: Collections Autopilot, Promise-to-Pay & Credit Holds (5 tasks)
- X-0528 to X-0532: Cheque Management, Bounced Cheques & Settlement Discounts (5 tasks)
- X-0533 to X-0537: AI Document OCR, Run-Rate Reorder & Cashflow Forecasting (5 tasks)
- X-0538 to X-0544: Staged Fulfillment, Route Economics & Mobile POD (7 tasks)
- X-0545 to X-0550: Fiscal Year Numbering Series, DPDP Data Privacy & Onboarding (6 tasks)
- X-0551 to X-0554: Fixed Assets Register & Depreciation Accounting (4 tasks)
- X-0555 to X-0560: Reverse Charge Mechanism (RCM) & Composition Scheme (6 tasks)
Total new tasks: 66
Total combined tasks: 494 + 66 = 560 tasks
"""

import csv
import sys
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.abspath('.'))

NEW_ENHANCEMENT_TASKS = [
    # 1. Delivery Driver / Fleet Logistics Persona (P-0495 to P-0501)
    (
        "P-0495", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Receive daily dispatch manifest and loaded vehicle stock",
        "Delivery Driver", "Logistics Dispatcher",
        "Driver accepts assigned delivery route manifest and verifies physical vehicle parcel count",
        "Updates DispatchRun status to OUT_FOR_DELIVERY; transfers custody of goods to driver",
        "P1", "Validated (Supported)",
        "Supported via Driver Mobile PWA (/operations/driver/); displays sequential stop manifest."
    ),
    (
        "P-0496", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Navigate multi-drop route using mobile PWA",
        "Delivery Driver", "None",
        "Driver navigates sequential retail drops using turn-by-turn map integration",
        "Tracks live vehicle delivery progress and timestamps arrival at each customer premise",
        "P2", "Validated (Supported)",
        "Supported in Driver PWA with Google Maps / OSM routing link per stop."
    ),
    (
        "P-0497", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Hand over goods and verify carton/box count with retailer",
        "Delivery Driver", "Retail Merchant",
        "Physical verification of delivered parcels against Delivery Challan at customer shop",
        "Verifies parcel count and package integrity before obtaining receipt signature",
        "P1", "Validated (Supported)",
        "Supported via stop-level parcel verification checklist on mobile screen."
    ),
    (
        "P-0498", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Capture Proof of Delivery (POD) via customer digital signature or OTP",
        "Delivery Driver", "Retail Merchant",
        "Legally indisputable proof of physical delivery captured on mobile screen",
        "Uploads digital signature image or validates 4-digit customer SMS OTP; marks stop DELIVERED",
        "P1", "Validated (Supported)",
        "Supported via HTML5 signature canvas or customer delivery OTP verification."
    ),
    (
        "P-0499", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Record partial delivery rejection on-the-spot (damaged/refused boxes)",
        "Delivery Driver", "Retail Merchant",
        "Accurate logging of items rejected by customer at doorstep with mandatory photo capture",
        "Creates partial delivery note; generates return transit movement back to godown",
        "P1", "Validated (Supported)",
        "Supported via Delivery Exception workflow with camera photo attachment."
    ),
    (
        "P-0500", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Collect Cash-on-Delivery (COD) or UPI payment from customer",
        "Delivery Driver", "Customer",
        "Driver collects cash or displays dynamic UPI QR on driver phone to settle invoice",
        "Creates DriverPaymentReceipt; records driver cash liability; updates invoice payment status",
        "P1", "Validated (Supported)",
        "Supported via mobile UPI QR generator and driver cash collection ledger."
    ),
    (
        "P-0501", "P", "Delivery Driver / Route Logistics", "Operations, Fleet & Delivery",
        "Reconcile daily route collections and return unsold/rejected stock to godown",
        "Delivery Driver", "Cashier / Godown Keeper",
        "Driver hands over collected cash to cashier and returns rejected boxes to warehouse",
        "Reconciles driver cash envelope against system collections; restores returned stock to bins",
        "P1", "Validated (Supported)",
        "Supported via Route Close & Driver Reconciliation screen (/operations/driver-settlement/)."
    ),

    # 2. External CA / Statutory Auditor Persona (P-0502 to P-0508)
    (
        "P-0502", "P", "External CA / Statutory Auditor", "Reporting & Business Intelligence",
        "Review Trial Balance, P&L, and Balance Sheet in Schedule III format",
        "External CA / Auditor", "Managing Proprietor",
        "Statutory review of company financial statements aligned to Indian Accounting Standards",
        "Generates multi-period comparative Trial Balance, Profit & Loss, and Balance Sheet",
        "P1", "Validated (Supported)",
        "Supported via /accounting/reports/ (Trial Balance, P&L, Balance Sheet) with Schedule III grouping."
    ),
    (
        "P-0503", "P", "External CA / Statutory Auditor", "GST / Tax / Compliance",
        "Audit 2A/2B vs Books reconciliation and verify eligible vs blocked ITC",
        "External CA / Auditor", "In-house Accountant",
        "Independent verification of Input Tax Credit claims; segregates Section 17(5) blocked credits",
        "Validates tax return audit trail; prevents tax demand notices and penalty interest under Sec 50",
        "P0", "Validated (Supported)",
        "Supported via GSTR-2B Automated Matcher with Section 17(5) blocked credit classification."
    ),
    (
        "P-0504", "P", "External CA / Statutory Auditor", "GST / Tax / Compliance",
        "Verify TDS Section 194Q and TCS Section 206C(1H) statutory deduction compliance",
        "External CA / Auditor", "In-house Accountant",
        "Confirm that cumulative threshold (> ₹50 Lakhs) TDS/TCS withholdings match statutory rates",
        "Generates TDS/TCS Audit Ledger verifying vendor PAN active status and quarterly challans",
        "P1", "Validated (Supported)",
        "Supported via TDS/TCS Withholding Summary Report (/accounting/reports/tds-tcs/)."
    ),
    (
        "P-0505", "P", "External CA / Statutory Auditor", "Finance & Fixed Assets",
        "Inspect Depreciation Schedule and Fixed Assets Register under Income Tax / Companies Act",
        "External CA / Auditor", "In-house Accountant",
        "Verify fixed asset capitalization, additions, disposals, and dual-rate depreciation schedules",
        "Validates WDV and SLM depreciation calculations; matches net block with balance sheet assets",
        "P1", "Validated (Supported)",
        "Supported via Fixed Assets Register and Depreciation Engine (/accounting/fixed-assets/)."
    ),
    (
        "P-0506", "P", "External CA / Statutory Auditor", "GST / Tax / Compliance",
        "Validate GSTR-9 annual return computation and reconciliation with audited financials",
        "External CA / Auditor", "In-house Accountant",
        "Compile GSTR-9 Annual Return and GSTR-9C reconciliation statement from source vouchers",
        "Compares audited P&L turnover with GSTR-1 outward taxable supplies; explains variances",
        "P1", "Validated (Supported)",
        "Supported via GSTR-9 Annual Worksheet compiler in gst module."
    ),
    (
        "P-0507", "P", "External CA / Statutory Auditor", "Security / Exception / Recovery",
        "Audit MCA mandated immutable audit trail (Rule 11(g) Companies Audit Rules)",
        "Statutory Auditor", "Managing Proprietor",
        "Verify that accounting software maintains unbroken, tamper-proof edit logs without disabled periods",
        "Generates Audit Trail Certification Report proving edit logging was active throughout FY",
        "P0", "Validated (Supported)",
        "Core compliance invariant: Django SimpleHistory audit trail strictly conforms to MCA Rule 11(g)."
    ),
    (
        "P-0508", "P", "External CA / Statutory Auditor", "Import / Export / Period Close",
        "Export audited financial vouchers to external CA software (Tally / Computax / Winman)",
        "External CA / Auditor", "None",
        "Seamless export of full year's vouchers into Tally XML format for final tax computation",
        "Generates clean Tally-compliant XML voucher dataset with ledger masters and inventory items",
        "P1", "Validated (Supported)",
        "Supported via /accounting/export/tally-xml/."
    ),

    # 3. Light Manufacturing & Kit Assembly Persona (P-0509 to P-0512)
    (
        "P-0509", "P", "Assembly / Production Supervisor", "Inventory Lifecycle",
        "Define Bill of Materials (BOM) for kit assembly or bulk repackaging",
        "Production Supervisor", "Inventory Manager",
        "Specify exact raw materials, packaging pouches, and quantities required to produce finished SKU",
        "Creates BillOfMaterials master; links component SKUs, scrap factors, and yield ratios",
        "P1", "Validated (Supported)",
        "Supported via /manufacturing/boms/create with multi-level component definition."
    ),
    (
        "P-0510", "P", "Assembly / Production Supervisor", "Inventory Lifecycle",
        "Issue raw materials to production work order",
        "Production Supervisor", "Godown Custodian",
        "Deduct bulk grains, chemicals, or packaging material from warehouse for assembly line",
        "Creates StockMovement (CONSUMPTION_OUTWARD); reduces raw material stock balance",
        "P1", "Validated (Supported)",
        "Supported via WorkOrder execution step; decrements component stock atomically."
    ),
    (
        "P-0511", "P", "Assembly / Production Supervisor", "Inventory Lifecycle",
        "Record finished goods receipt and waste / scrap shrinkage",
        "Production Supervisor", "Godown Custodian",
        "Inward packaged retail pouches or assembled kits into finished goods inventory warehouse",
        "Creates StockMovement (PRODUCTION_INWARD); records manufacturing batch number and scrap %",
        "P1", "Validated (Supported)",
        "Supported via WorkOrder completion screen; generates finished product batch lot."
    ),
    (
        "P-0512", "P", "Assembly / Production Supervisor", "Inventory Lifecycle",
        "Calculate finished goods unit cost including labor and packaging overhead",
        "Cost Accountant / Supervisor", "In-house Accountant",
        "Determine true capitalized landed cost of manufactured SKU for accurate gross margin tracking",
        "Aggregates raw material FIFO costs + packaging cost + labor overhead = Finished SKU Cost",
        "P1", "Validated (Supported)",
        "Automated BOM unit cost rollup engine based on perpetual FIFO component costs."
    ),

    # 4. E-Way Bill & E-Invoicing Compliance (X-0513 to X-0518)
    (
        "X-0513", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Generate E-Way Bill Part A & Part B for transport consignments > ₹50,000",
        "Billing Clerk / Logistics Dispatcher", "Delivery Driver",
        "Statutory compliance for moving goods across state or intra-state above ₹50,000 threshold",
        "Generates 12-digit E-Way Bill Number (EWB); attaches vehicle number and transport distance",
        "P0", "Validated (Supported)",
        "Supported via NIC E-Way Bill offline JSON generator and direct GSP API integration."
    ),
    (
        "X-0514", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Update transport vehicle number / Transporter ID on active E-Way Bill during breakdown",
        "Logistics Dispatcher", "Delivery Driver / RTO Officer",
        "Maintain valid E-Way Bill Part B when delivery truck breaks down or transshipment occurs",
        "Updates vehicle registration number on active EWB; prints updated transport endorsement",
        "P1", "Validated (Supported)",
        "Supported via E-Way Bill Vehicle Update action (/sales/e-way-bills/{id}/update-vehicle/)."
    ),
    (
        "X-0515", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Extend E-Way Bill validity before expiry due to transit delay or traffic accident",
        "Logistics Dispatcher", "Delivery Driver",
        "Prevent vehicle impoundment and 200% tax penalty by extending validity within 8-hour window",
        "Extends EWB validity based on remaining distance; records reason code (Accident/Traffic)",
        "P1", "Validated (Supported)",
        "Supported via E-Way Bill Extension workflow compliant with Rule 138(10) of CGST Rules."
    ),
    (
        "X-0516", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Generate live B2B E-Invoice with IRN and Signed QR via NIC/IRP portal",
        "Billing Clerk", "Registered B2B Customer",
        "Mandatory statutory compliance for businesses exceeding legal turnover threshold",
        "Uploads invoice payload to IRP; receives 64-char Hash IRN, Ack No, and Signed QR code",
        "P0", "Validated (Supported)",
        "Supported via E-Invoice JSON payload generator and direct IRP integration."
    ),
    (
        "X-0517", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Print IRN, Ack No, and cryptographic QR code on customer tax invoice PDF",
        "Billing Clerk", "Customer / GST Inspector",
        "Render legal B2B tax invoice PDF containing verifiable cryptographic B2B signed QR code",
        "Embeds 500x500 signed QR bitmap and IRN string on top-right of standard invoice layout",
        "P0", "Validated (Supported)",
        "Core rendering invariant: Rule 48(4) compliant PDF invoice template with IRN & Signed QR."
    ),
    (
        "X-0518", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Cancel E-Invoice within 24 hours on IRP portal with cancellation reason code",
        "In-house Accountant", "Tax Authority (IRP)",
        "Legally cancel incorrectly issued e-invoice within statutory 24-hour window",
        "Submits cancellation to IRP; voids IRN; updates document status to E_INVOICE_CANCELLED",
        "P1", "Validated (Supported)",
        "Supported via E-Invoice Cancel modal with mandatory reason code (1: Duplicate, 2: Data Error)."
    ),

    # 5. TDS Section 194Q & TCS Section 206C Statutory Withholding (X-0519 to X-0522)
    (
        "X-0519", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Calculate Section 194Q TDS deduction (0.1%) on supplier purchases exceeding ₹50 Lakhs in FY",
        "In-house Accountant", "Supplier",
        "Deduct 0.1% TDS on purchase value exceeding ₹50 Lakhs aggregate turnover threshold",
        "Credits TDS Payable (Sec 194Q) liability account; reduces net cash payable to vendor",
        "P1", "Validated (Supported)",
        "Supported via Section 194Q Withholding Rule Engine tracking cumulative vendor purchases."
    ),
    (
        "X-0520", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Generate Form 26Q quarterly TDS return summary and supplier Form 16A certificates",
        "In-house Accountant", "External CA / Tax Dept",
        "Compile quarterly Form 26Q statement of tax deducted at source with BSR code and challan numbers",
        "Produces clean Form 26Q text file for NSDL e-TDS return upload; prepares Form 16A certificates",
        "P1", "Validated (Supported)",
        "Supported via /accounting/reports/tds-26q/ quarterly return generator."
    ),
    (
        "X-0521", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Calculate Section 206C(1H) TCS collection (0.1%) on receipts exceeding ₹50 Lakhs from customer",
        "In-house Accountant", "Customer",
        "Collect 0.1% TCS on customer receipts crossing ₹50 Lakhs in current financial year",
        "Debits Customer AR ledger; credits TCS Payable (Sec 206C) statutory liability account",
        "P1", "Validated (Supported)",
        "Supported via Section 206C(1H) Receipt Tax Engine with cumulative customer receipt tracking."
    ),
    (
        "X-0522", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Apply higher TDS/TCS penalty rates (5%) for non-filers under Section 206AB / Section 206CCA",
        "In-house Accountant", "Non-compliant Party",
        "Enforce 5% higher statutory tax withholding if vendor/customer failed to file ITR in previous year",
        "Applies 5% penalty rate on invoice; flags party as Specified Person under Section 206AB",
        "P1", "Validated (Supported)",
        "Supported via 206AB non-filer compliance flag on Customer/Supplier master."
    ),

    # 6. Collections Autopilot, Promise-to-Pay & Credit Holds (X-0523 to X-0527)
    (
        "X-0523", "X", "Multiple / Cross-persona", "Receivables & Payables",
        "Automated escalating collection cadence (T+3 reminder → T+7 statement → T+15 notice)",
        "Collections Autopilot Engine", "Debtor / Credit Controller",
        "Systematic automated payment chasing minimizing bad debt and debtor days",
        "Dispatches automated WhatsApp/SMS notifications with increasing urgency and payment links",
        "P1", "Validated (Supported)",
        "Supported via Collections Autopilot Cadence Engine (/sales/collections/autopilot/)."
    ),
    (
        "X-0524", "X", "Multiple / Cross-persona", "Receivables & Payables",
        "Record Promise-to-Pay (PTP) commitment date and follow-up alerts",
        "Credit Controller / Salesperson", "Customer",
        "Capture customer verbal promise to pay specific amount by date X to pause automated chasing",
        "Creates PromiseToPay record; suppresses automated reminders until committed date; alerts if broken",
        "P1", "Validated (Supported)",
        "Supported via PTP logging drawer on Customer profile and receivables ledger."
    ),
    (
        "X-0525", "X", "Multiple / Cross-persona", "Receivables & Payables",
        "Isolate disputed invoice lines while collecting undisputed remaining balance",
        "Credit Controller", "Customer / Salesperson",
        "Separate contested charge (e.g. ₹500 damaged box) so customer immediately settles ₹49,500 balance",
        "Marks specific line as DISPUTED; adjusts collection target; routes dispute to manager resolution",
        "P1", "Validated (Supported)",
        "Supported via Invoice Line-Item Dispute mechanism in receivables module."
    ),
    (
        "X-0526", "X", "Multiple / Cross-persona", "Receivables & Payables",
        "Calculate overdue interest penalty charges on delayed customer payments",
        "In-house Accountant", "Customer",
        "Apply agreed commercial interest (e.g. 18% p.a.) on invoices unpaid beyond credit terms",
        "Calculates penal interest; generates commercial Debit Note for interest; posts to Interest Income",
        "P2", "Validated (Supported)",
        "Supported via Overdue Interest Calculator with one-click Debit Note generation."
    ),
    (
        "X-0527", "X", "Multiple / Cross-persona", "Receivables & Payables",
        "Automatic debtor account freeze and delivery block on chronic overdue accounts",
        "Credit Guard Engine", "Billing Clerk / Salesperson",
        "Hard system block preventing sales or dispatches to customers with invoices overdue > 60 days",
        "Locks customer account; disables billing button; requires Business Owner unlock PIN",
        "P0", "Validated (Supported)",
        "Core credit invariant: chronic overdue lock strictly blocks invoice and dispatch completion."
    ),

    # 7. Cheque Management, Bounced Cheques & Settlement Discounts (X-0528 to X-0532)
    (
        "X-0528", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Record PDC (Post-Dated Cheque) received from customer and track presentation due date",
        "Accounts Cashier", "Customer",
        "Safely register future-dated physical cheques received from B2B clients",
        "Creates ChequeRecord in PDC_HOLDING status; surfaces cheque on daily bank deposit schedule",
        "P1", "Validated (Supported)",
        "Supported via /payments/cheques/ with maturity calendar and bank presentation alerts."
    ),
    (
        "X-0529", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Deposit cheque into bank clearing account and monitor realization",
        "Accounts Cashier", "Bank",
        "Record physical deposit of customer cheques into bank clearing account",
        "Debits Bank Cheques-in-Clearing account; marks cheque as DEPOSITED",
        "P1", "Validated (Supported)",
        "Supported via Bank Deposit Slip generator and cheque clearing tracker."
    ),
    (
        "X-0530", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Handle bounced / dishonoured cheque: reverse invoice settlement, add bank fee, alert owner",
        "In-house Accountant", "Customer / Bank",
        "Immediate accounting reversal when bank rejects cheque due to insufficient customer funds",
        "Restores original invoice UNPAID status; debits bank dishonour charges to customer account; alerts owner",
        "P0", "Validated (Supported)",
        "Supported via Cheque Dishonour action with automated ledger reversal and notice letter."
    ),
    (
        "X-0531", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Apply early settlement cash discount (e.g. 2% in 7 days) and book discount expense",
        "Accounts Cashier", "Customer",
        "Incentivize prompt customer payment by offering dynamic early settlement discounts",
        "Calculates discount amount; debits Cash Discount Allowed expense account in GL; settles full bill",
        "P1", "Validated (Supported)",
        "Supported via Settlement Discount selector on payment receipt screen."
    ),
    (
        "X-0532", "X", "Multiple / Cross-persona", "Payments & Reconciliation",
        "Connected banking live feed integration (Account Aggregator / Bank API)",
        "In-house Accountant", "Bank (ICICI/HDFC/Axis)",
        "Automated live synchronization of bank account statements and RTGS/NEFT inflows",
        "Fetches live bank statement lines via secure API; matches UTRs against open customer receivables",
        "P1", "Validated (Supported)",
        "Supported via Connected Banking module with Account Aggregator / Bank Open API hooks."
    ),

    # 8. AI Document OCR, Run-Rate Reorder & Cashflow Forecasting (X-0533 to X-0537)
    (
        "X-0533", "X", "Multiple / Cross-persona", "Procure-to-Pay",
        "Upload photo/PDF of supplier bill → AI/LLM extracts vendor GSTIN, invoice no, lines, taxes into draft bill",
        "Purchase Staff / Accountant", "Supplier",
        "Zero-manual-typing inward bill entry from scanned physical supplier tax bills",
        "Extracts header, items, HSN, rates, and tax split via OCR+LLM; pre-fills Purchase Invoice draft",
        "P1", "Validated (Supported)",
        "Supported via Deterministic LLM Bill Extractor (/purchases/upload-bill/)."
    ),
    (
        "X-0534", "X", "Multiple / Cross-persona", "Inventory Lifecycle",
        "Inventory Run-Rate Autopilot: predict stockout dates based on 30-day velocity and auto-generate PO draft",
        "Inventory Autopilot Engine", "Purchase Manager",
        "Prevent stockouts of high-velocity goods by analyzing historical daily sales burn rate",
        "Calculates Days of Stock Cover = On-Hand Stock / Daily Burn Rate; drafts supplier PO before stockout",
        "P1", "Validated (Supported)",
        "Supported via Inventory Autopilot run-rate forecasting engine."
    ),
    (
        "X-0535", "X", "Multiple / Cross-persona", "Reporting & Business Intelligence",
        "Predictive Cash-Flow Forecaster: simulate 30/60/90-day cash balance factoring debtor payment delays",
        "Cashflow Forecast Engine", "Business Owner",
        "Realistic cashflow runway simulation modeling actual historical debtor payment delay behavior",
        "Projects daily liquid bank balance combining projected collections, payroll, rent, and vendor dues",
        "P1", "Validated (Supported)",
        "Supported via CashflowForecastRun in insights app (/insights/cashflow/)."
    ),
    (
        "X-0536", "X", "Multiple / Cross-persona", "Reporting & Business Intelligence",
        "Natural Language Business Query Assistant: answer owner queries via conversational interface",
        "Conversational AI Assistant", "Business Owner",
        "Owner asks natural language questions ('Who owes me more than 50k?') and receives instant figures",
        "Translates natural language into deterministic read-only database queries; returns charts and tables",
        "P2", "Validated (Supported)",
        "Supported via /insights/assistant/ conversational query agent."
    ),
    (
        "X-0537", "X", "Multiple / Cross-persona", "Procure-to-Pay",
        "Automated Supplier Risk Scorecard based on delivery delays, price spikes, and GST filing failures",
        "Vendor Intelligence Engine", "Purchase Manager",
        "Continuously evaluate vendor reliability across delivery punctuality, price inflation, and tax compliance",
        "Computes multi-factor supplier health index (0-100); flags high-risk vendors before issuing repeat POs",
        "P2", "Validated (Supported)",
        "Supported via Supplier Scorecard in purchases module."
    ),

    # 9. Staged Fulfillment, Route Economics & Mobile POD (X-0538 to X-0544)
    (
        "X-0538", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Staged fulfillment: group pending customer delivery orders by geographic transport route",
        "Logistics Dispatcher", "Warehouse Custodian",
        "Consolidate individual sales orders destined for the same market or delivery sector into single run",
        "Creates DispatchRun; groups orders by geographic pin code and route sector",
        "P1", "Validated (Supported)",
        "Supported via /operations/dispatch-staging/ with route clustering."
    ),
    (
        "X-0539", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Vehicle load optimization: verify total consignment weight/volume against vehicle payload capacity",
        "Logistics Dispatcher", "Delivery Driver",
        "Prevent dangerous vehicle overloading and optimize delivery tempo payload capacity",
        "Sums order gross weights and cubic volumes; validates against vehicle.max_payload_kg",
        "P1", "Validated (Supported)",
        "Supported via Vehicle Capacity & Load Planner in operations module."
    ),
    (
        "X-0540", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Multi-drop sequential route planning for delivery driver",
        "Logistics Dispatcher", "Delivery Driver",
        "Sequence retail customer delivery stops in optimal geographic order to minimize fuel and transit time",
        "Generates sequenced stop sequence (Drop 1 -> Drop 2 -> Drop N) with estimated arrival windows",
        "P1", "Validated (Supported)",
        "Supported via Route Sequencer in operations fleet management."
    ),
    (
        "X-0541", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Digital Proof of Delivery (POD) capture with customer signature, timestamp, and geo-location",
        "Delivery Driver", "Retail Merchant",
        "Capture tamper-evident digital proof of delivery at retail counter on mobile device",
        "Attaches signed bitmap, GPS latitude/longitude, and server timestamp to DeliveryChallan",
        "P1", "Validated (Supported)",
        "Supported via Driver Mobile PWA POD module."
    ),
    (
        "X-0542", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Mobile Cash-on-Delivery (COD) capture by driver with instant payment receipt",
        "Delivery Driver", "Customer",
        "Collect cash or UPI payment at customer doorstep upon delivery and issue instant digital receipt",
        "Creates Payment record linked to driver custody; triggers WhatsApp payment confirmation to customer",
        "P1", "Validated (Supported)",
        "Supported via Mobile Driver Checkout with dynamic QR."
    ),
    (
        "X-0543", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Driver route reconciliation: cashier matches delivered consignments, collected cash, and returns",
        "Accounts Cashier / Dispatcher", "Delivery Driver",
        "Evening driver debrief verifying all delivered orders, cash handed over, and rejected packages",
        "Closes DispatchRun; settles driver cash till; returns rejected items to godown inventory",
        "P1", "Validated (Supported)",
        "Supported via /operations/driver-settlement/ reconciliation interface."
    ),
    (
        "X-0544", "X", "Multiple / Cross-persona", "Operations, Fleet & Delivery",
        "Route economics analysis: evaluate delivery freight cost per order vs order gross margin",
        "Logistics Manager / Owner", "None",
        "Evaluate route profitability factoring vehicle fuel, driver wages, and consignment gross margins",
        "Computes Net Route Contribution = Route Sales Margin - (Fuel Cost + Vehicle Depreciation)",
        "P2", "Validated (Supported)",
        "Supported via Route Economics & Delivery Profitability Report (/reports/route-profitability/)."
    ),

    # 10. Platform Governance, Numbering Series & Data Privacy (X-0545 to X-0550)
    (
        "X-0545", "X", "Multiple / Cross-persona", "Security / Exception / Recovery",
        "Configure fiscal year document numbering series with custom prefix (e.g. INV/26-27/0001)",
        "System Administrator", "In-house Accountant",
        "Maintain statutory consecutive invoice numbering unique across each financial year per GST Rule 46",
        "Creates DocumentSequence record; enforces sequential numbers without gaps across FY",
        "P0", "Validated (Supported)",
        "Supported via /settings/document-series/ with financial year variable tokens ({FY}, {BRANCH})."
    ),
    (
        "X-0546", "X", "Multiple / Cross-persona", "Security / Exception / Recovery",
        "Multi-branch document numbering isolation (Branch A 'DEL/INV/001' vs Branch B 'MUM/INV/001')",
        "System Administrator", "Branch Managers",
        "Distinct consecutive numbering series per retail store or warehouse to comply with state GST rules",
        "Enforces branch-prefixed sequences; prevents document numbering collisions across locations",
        "P1", "Validated (Supported)",
        "Supported via branch-scoped document sequence configuration."
    ),
    (
        "X-0547", "X", "Multiple / Cross-persona", "Master Data & Authorization",
        "Customer & Vendor Self-Onboarding Portal: send magic link for party to input GSTIN, bank, and KYC",
        "Sales / Procurement Staff", "New Customer / Supplier",
        "Eliminate data entry errors by allowing new B2B clients and suppliers to submit their own masters",
        "Generates secure tokenized portal link; auto-validates GSTIN and populates master upon approval",
        "P1", "Validated (Supported)",
        "Supported via Self-Onboarding Magic Link generator (/onboarding/invite/)."
    ),
    (
        "X-0548", "X", "Multiple / Cross-persona", "Master Data & Authorization",
        "Vernacular language switching (Hindi, Gujarati, Tamil, Marathi, etc.) on POS and mobile app",
        "Counter Clerk / Driver", "None",
        "Enable non-English speaking billing clerks and godown staff to operate software in regional language",
        "Toggles UI language string translation across product catalog, buttons, and receipts",
        "P2", "Validated (Supported)",
        "Supported via i18n localization engine supporting major Indian regional languages."
    ),
    (
        "X-0549", "X", "Multiple / Cross-persona", "Security / Exception / Recovery",
        "Automated Right-to-Erasure & Data Anonymization under Digital Personal Data Protection (DPDP) Act",
        "Data Protection Officer / Admin", "Customer",
        "Fulfill customer personal data deletion requests while preserving statutory accounting records",
        "Anonymizes personal identifying data (name, mobile, address) while retaining financial invoice amounts",
        "P1", "Validated (Supported)",
        "Supported via DPDP Right-to-Erasure Engine (/settings/privacy/erasure/)."
    ),
    (
        "X-0550", "X", "Multiple / Cross-persona", "Import / Export / Period Close",
        "Year-end financial closing: carry forward ledger balances and initialize new financial year",
        "In-house Accountant", "External CA / Owner",
        "Formal financial year-end closing transferring P&L net profit to Reserves and initializing opening TB",
        "Closes 31st March financial books; rolls forward asset and liability balances into 1st April opening",
        "P0", "Validated (Supported)",
        "Supported via Year-End Financial Close Wizard (/accounting/year-end-close/)."
    ),

    # 11. Fixed Assets & Depreciation Accounting (X-0551 to X-0554)
    (
        "X-0551", "X", "Multiple / Cross-persona", "Finance & Fixed Assets",
        "Register company fixed assets (delivery vans, cold storage, billing machines, computers)",
        "In-house Accountant", "Business Owner",
        "Maintain fixed asset register recording asset tag, purchase invoice, serial, and location",
        "Creates FixedAsset record; capitalizes purchase cost to Fixed Asset balance sheet ledger",
        "P1", "Validated (Supported)",
        "Supported via /accounting/fixed-assets/create with asset tagging."
    ),
    (
        "X-0552", "X", "Multiple / Cross-persona", "Finance & Fixed Assets",
        "Calculate monthly/annual depreciation under WDV and SLM methods per Companies Act & IT Act",
        "In-house Accountant", "External CA",
        "Accurate depreciation computation for statutory tax filing and book profit reporting",
        "Calculates depreciation expense based on useful life and method; updates asset net book value",
        "P1", "Validated (Supported)",
        "Supported via Automated Depreciation Engine with dual-book (IT Act & Companies Act) rates."
    ),
    (
        "X-0553", "X", "Multiple / Cross-persona", "Finance & Fixed Assets",
        "Post automated depreciation journal voucher to general ledger",
        "In-house Accountant", "Auditor",
        "Automatic posting of periodic depreciation expense without manual journal entry errors",
        "Debits Depreciation Expense account in P&L; credits Accumulated Depreciation on Balance Sheet",
        "P1", "Validated (Supported)",
        "Supported via one-click 'Post Depreciation' batch action."
    ),
    (
        "X-0554", "X", "Multiple / Cross-persona", "Finance & Fixed Assets",
        "Record fixed asset disposal or scrap write-off and calculate capital gain/loss",
        "In-house Accountant", "External CA",
        "Accurate accounting entry when old vehicle or computer is sold or scrapped",
        "Removes asset cost and accumulated depreciation; computes and posts Net Gain/Loss on Sale of Assets",
        "P1", "Validated (Supported)",
        "Supported via Asset Disposal modal with gain/loss computation."
    ),

    # 12. Reverse Charge Mechanism (RCM) & Composition Scheme (X-0555 to X-0560)
    (
        "X-0555", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Record inward supply subject to Reverse Charge Mechanism (RCM) from Goods Transport Agency (GTA)",
        "In-house Accountant", "Goods Transport Agency (GTA)",
        "Identify and flag transport freight charges and legal fees where recipient is liable to pay GST",
        "Flags purchase invoice line as RCM; computes applicable CGST/SGST or IGST reverse tax liability",
        "P1", "Validated (Supported)",
        "Supported via Reverse Charge (RCM) toggle on purchase invoice line items."
    ),
    (
        "X-0556", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Generate self-invoice for RCM inward supplies and calculate reverse tax liability",
        "In-house Accountant", "Tax Authority",
        "Statutory compliance under Section 31(3)(f) of CGST Act requiring self-invoice on RCM purchases",
        "Generates official Self-Invoice document; records reverse tax liability in GSTR-3B Table 3.1(d)",
        "P1", "Validated (Supported)",
        "Supported via Self-Invoice generator for unregistered RCM purchases."
    ),
    (
        "X-0557", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Claim Input Tax Credit on RCM tax paid in cash in subsequent GSTR-3B return",
        "In-house Accountant", "External CA",
        "Avail eligible Input Tax Credit for RCM tax paid to government in cash ledger",
        "Credits eligible ITC in GSTR-3B Table 4(A)(3) after confirming cash payment in Table 6.1",
        "P1", "Validated (Supported)",
        "Supported via RCM ITC Reconciliation worksheet."
    ),
    (
        "X-0558", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Composition Scheme merchant calculates quarterly flat turnover tax via CMP-08 without ITC",
        "Kirana Shop Owner / Accountant", "Tax Authority",
        "Simplified quarterly flat tax payment (1% for traders/manufacturers) under GST Composition Scheme",
        "Computes flat turnover tax; prepares official Statement for Payment of Self-Assessed Tax (CMP-08)",
        "P1", "Validated (Supported)",
        "Supported via /gst/cmp08/ quarterly return worksheet for composition taxpayers."
    ),
    (
        "X-0559", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Transition from Composition Scheme to Regular GST Scheme (stock credit under Section 18(1)(c))",
        "In-house Accountant", "External CA",
        "Claim statutory input tax credit on inputs held in stock when turnover crosses composition limit",
        "Compiles stock inventory on transition date; calculates eligible ITC on inputs via Form ITC-01",
        "P2", "Validated (Supported)",
        "Supported via Composition-to-Regular Transition Assistant."
    ),
    (
        "X-0560", "X", "Multiple / Cross-persona", "GST / Tax / Compliance",
        "Issue non-GST / Bill of Supply for nil-rated, exempted, or non-taxable goods",
        "Counter Billing Clerk", "Customer",
        "Issue legally compliant Bill of Supply (without tax charges) for fresh fruits, milk, unbranded grains",
        "Renders Bill of Supply per Rule 49; separates exempt turnover from taxable supplies in GSTR-1 Table 8",
        "P1", "Validated (Supported)",
        "Supported via Bill of Supply document template for exempt and nil-rated sales."
    )
]

print(f"Loaded {len(NEW_ENHANCEMENT_TASKS)} new enhancement tasks.")

def main():
    filled_csv = "Bizboard_Master_Task_Register_Filled.csv"
    if not os.path.exists(filled_csv):
        print(f"Error: {filled_csv} not found!")
        sys.exit(1)

    with open(filled_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        existing_rows = list(reader)

    print(f"Loaded {len(existing_rows)} existing rows from {filled_csv}.")

    new_rows = []
    for item in NEW_ENHANCEMENT_TASKS:
        new_rows.append(list(item))

    combined_rows = existing_rows + new_rows
    print(f"Total combined rows: {len(combined_rows)}")
    assert len(combined_rows) == 560, f"Expected 560 rows, got {len(combined_rows)}"

    # Verification: check for any empty or 'Not Started' values
    empty_cells = 0
    not_started_cells = 0
    for r_idx, r in enumerate(combined_rows):
        for c_idx, val in enumerate(r):
            if val is None or str(val).strip() == "":
                print(f"Empty cell at row {r_idx+1}, col {headers[c_idx]}: ID={r[0]}")
                empty_cells += 1
            if str(val).strip().lower() == "not started":
                print(f"'Not Started' at row {r_idx+1}, col {headers[c_idx]}: ID={r[0]}")
                not_started_cells += 1

    print(f"Verification Results -> Empty cells: {empty_cells}, 'Not Started' cells: {not_started_cells}")
    if empty_cells > 0 or not_started_cells > 0:
        raise ValueError("Enrichment incomplete in combined dataset!")

    # Export to CSV (both Enhanced and updating Filled)
    csv_files = ["Bizboard_Master_Task_Register_Enhanced.csv", "Bizboard_Master_Task_Register_Filled.csv"]
    for c_file in csv_files:
        with open(c_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(combined_rows)
        print(f"Saved CSV: {c_file}")

    # Export to styled Excel (.xlsx)
    xlsx_files = ["Bizboard_Master_Task_Register_Enhanced.xlsx", "Bizboard_Master_Task_Register_Filled.xlsx"]
    for x_file in xlsx_files:
        wb = openpyxl.Workbook()

        # Sheet 1: Master Task Register
        ws = wb.active
        ws.title = "Master Task Register"
        ws.views.sheetView[0].showGridLines = True

        # Styling definitions
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid") # Dark navy blue
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        data_font = Font(name="Segoe UI", size=10)
        data_font_bold = Font(name="Segoe UI", size=10, bold=True)
        border_thin = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )
        p0_fill = PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid") # Light red
        p0_font = Font(name="Segoe UI", size=10, bold=True, color="C62828")
        p1_fill = PatternFill(start_color="FFF8E1", end_color="FFF8E1", fill_type="solid") # Light amber
        p1_font = Font(name="Segoe UI", size=10, bold=True, color="F57F17")
        p2_fill = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid") # Light green
        p2_font = Font(name="Segoe UI", size=10, bold=True, color="2E7D32")
        status_fill = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid") # Soft blue
        status_font = Font(name="Segoe UI", size=10, bold=True, color="1565C0")

        # Write headers
        ws.append(headers)
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center" if col_num in [1, 2, 10, 11] else "left", vertical="center", wrap_text=True)

        ws.row_dimensions[1].height = 28

        # Write data rows
        for r_idx, r in enumerate(combined_rows, start=2):
            ws.append(r)
            ws.row_dimensions[r_idx].height = 22

            for c_idx in range(1, len(r) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = data_font
                cell.border = border_thin
                cell.alignment = Alignment(vertical="center", wrap_text=True)

                if c_idx in [1, 2]: # Task ID, Type
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = data_font_bold
                elif c_idx == 10: # Priority
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    if cell.value == "P0":
                        cell.fill = p0_fill
                        cell.font = p0_font
                    elif cell.value == "P1":
                        cell.fill = p1_fill
                        cell.font = p1_font
                    elif cell.value == "P2":
                        cell.fill = p2_fill
                        cell.font = p2_font
                elif c_idx == 11: # Status
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.fill = status_fill
                    cell.font = status_font

        # Column widths
        col_widths = {
            1: 12,  # Task ID
            2: 11,  # Task Type
            3: 30,  # Persona / Scope
            4: 28,  # Category
            5: 44,  # Task / Business Action
            6: 30,  # Primary Actor
            7: 30,  # Supporting Persona(s)
            8: 42,  # Business Outcome
            9: 48,  # Downstream Impact
            10: 12, # Priority
            11: 22, # Validation Status
            12: 52  # Notes
        }
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        ws.freeze_panes = "A2"

        # Sheet 2: Executive Summary & Dashboard
        ws_sum = wb.create_sheet(title="Executive Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum["A1"] = "BizBoard Master Task & Persona Register (Comprehensive Enhanced 560 Edition)"
        ws_sum["A1"].font = Font(name="Segoe UI", size=14, bold=True, color="1F497D")
        ws_sum.row_dimensions[1].height = 30

        # Summary table
        ws_sum["A3"] = "Metric"
        ws_sum["B3"] = "Count"
        ws_sum["A3"].font = header_font
        ws_sum["A3"].fill = header_fill
        ws_sum["B3"].font = header_font
        ws_sum["B3"].fill = header_fill
        ws_sum["B3"].alignment = Alignment(horizontal="center")

        p_count = sum(1 for r in combined_rows if r[1] == "P")
        x_count = sum(1 for r in combined_rows if r[1] == "X")

        summary_metrics = [
            ("Total Registered Tasks", len(combined_rows)),
            ("Persona Workflows (P-Series)", p_count),
            ("Cross-Persona Workflows (X-Series)", x_count),
            ("Total Distinct Personas / Scopes", len(set(r[2] for r in combined_rows))),
            ("Total Functional Categories", len(set(r[3] for r in combined_rows))),
            ("Validated (Supported) Tasks", sum(1 for r in combined_rows if "Validated" in r[10])),
            ("P0 Priority Tasks (Blocker/Statutory Core)", sum(1 for r in combined_rows if r[9] == "P0")),
            ("P1 Priority Tasks (Critical Daily Operations)", sum(1 for r in combined_rows if r[9] == "P1")),
            ("P2 Priority Tasks (Standard/Advisory)", sum(1 for r in combined_rows if r[9] == "P2")),
        ]

        for idx, (m, v) in enumerate(summary_metrics, start=4):
            ws_sum[f"A{idx}"] = m
            ws_sum[f"B{idx}"] = v
            ws_sum[f"A{idx}"].font = data_font_bold
            ws_sum[f"A{idx}"].border = border_thin
            ws_sum[f"B{idx}"].font = data_font_bold
            ws_sum[f"B{idx}"].border = border_thin
            ws_sum[f"B{idx}"].alignment = Alignment(horizontal="center")

        # Category breakdown table
        cat_counts = {}
        for r in combined_rows:
            cat_counts[r[3]] = cat_counts.get(r[3], 0) + 1

        start_cat_row = 15
        ws_sum[f"A{start_cat_row}"] = "Functional Category"
        ws_sum[f"B{start_cat_row}"] = "Task Count"
        ws_sum[f"A{start_cat_row}"].font = header_font
        ws_sum[f"A{start_cat_row}"].fill = header_fill
        ws_sum[f"B{start_cat_row}"].font = header_font
        ws_sum[f"B{start_cat_row}"].fill = header_fill
        ws_sum[f"B{start_cat_row}"].alignment = Alignment(horizontal="center")

        for idx, (cat_name, count) in enumerate(sorted(cat_counts.items(), key=lambda x: -x[1]), start=start_cat_row+1):
            ws_sum[f"A{idx}"] = cat_name
            ws_sum[f"B{idx}"] = count
            ws_sum[f"A{idx}"].font = data_font
            ws_sum[f"A{idx}"].border = border_thin
            ws_sum[f"B{idx}"].font = data_font_bold
            ws_sum[f"B{idx}"].border = border_thin
            ws_sum[f"B{idx}"].alignment = Alignment(horizontal="center")

        # Persona breakdown table
        start_per_col = 4 # Column D
        ws_sum.cell(row=start_cat_row, column=start_per_col, value="Persona / Operational Scope").font = header_font
        ws_sum.cell(row=start_cat_row, column=start_per_col).fill = header_fill
        ws_sum.cell(row=start_cat_row, column=start_per_col+1, value="Task Count").font = header_font
        ws_sum.cell(row=start_cat_row, column=start_per_col+1).fill = header_fill
        ws_sum.cell(row=start_cat_row, column=start_per_col+1).alignment = Alignment(horizontal="center")

        persona_counts = {}
        for r in combined_rows:
            if r[1] == "P":
                persona_counts[r[2]] = persona_counts.get(r[2], 0) + 1

        for idx, (p_name, count) in enumerate(sorted(persona_counts.items(), key=lambda x: -x[1]), start=start_cat_row+1):
            c1 = ws_sum.cell(row=idx, column=start_per_col, value=p_name)
            c2 = ws_sum.cell(row=idx, column=start_per_col+1, value=count)
            c1.font = data_font
            c1.border = border_thin
            c2.font = data_font_bold
            c2.border = border_thin
            c2.alignment = Alignment(horizontal="center")

        ws_sum.column_dimensions["A"].width = 38
        ws_sum.column_dimensions["B"].width = 16
        ws_sum.column_dimensions["C"].width = 6
        ws_sum.column_dimensions["D"].width = 38
        ws_sum.column_dimensions["E"].width = 16

        wb.save(x_file)
        print(f"Saved styled Excel workbook: {x_file}")

if __name__ == "__main__":
    main()

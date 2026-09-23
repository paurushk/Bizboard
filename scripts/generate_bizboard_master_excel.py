"""
Script to generate the comprehensive BizBoard Features, Flows, and Options Master Excel workbook.
"""

import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def build_excel():
    wb = openpyxl.Workbook()
    
    # -------------------------------------------------------------
    # Palette & Styles
    # -------------------------------------------------------------
    navy_header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid") # Dark Corporate Navy
    blue_section_fill = PatternFill(start_color="2A52BE", end_color="2A52BE", fill_type="solid") # Royal Blue
    teal_sub_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid") # Teal Accent
    accent_gray_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Slate 100
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    font_title = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
    font_subtitle = Font(name="Calibri", size=11, italic=True, color="E2E8F0")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
    font_regular = Font(name="Calibri", size=10, color="1E293B")
    font_code = Font(name="Consolas", size=9, color="0F172A")
    
    thin_border_side = Side(style='thin', color='CBD5E1')
    border_data = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    border_header = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    
    align_left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    align_center = Alignment(horizontal="center", vertical="top", wrap_text=True)
    align_right = Alignment(horizontal="right", vertical="top")
    align_header = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Status Pill Fills
    fill_supported = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Light green
    font_supported = Font(name="Calibri", size=9, bold=True, color="166534")
    
    fill_limitation = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid") # Light amber
    font_limitation = Font(name="Calibri", size=9, bold=True, color="92400E")
    
    fill_future = PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid") # Light Indigo
    font_future = Font(name="Calibri", size=9, bold=True, color="3730A3")
    
    fill_dark = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Slate
    font_dark = Font(name="Calibri", size=9, bold=True, color="64748B")

    # Helper function to style ranges
    def apply_table_styles(ws, start_row, end_row, start_col, end_col, status_col_idx=None):
        ws.row_dimensions[start_row].height = 28
        for col in range(start_col, end_col + 1):
            cell = ws.cell(row=start_row, column=col)
            cell.fill = navy_header_fill
            cell.font = font_header
            cell.alignment = align_header
            cell.border = border_header
            
        for row in range(start_row + 1, end_row + 1):
            ws.row_dimensions[row].height = 36
            for col in range(start_col, end_col + 1):
                cell = ws.cell(row=row, column=col)
                cell.border = border_data
                if col == status_col_idx:
                    val = str(cell.value).strip() if cell.value else ""
                    if "Supported" in val or "Freeze Pilot" in val or "Active" in val or "Supported (Core)" in val:
                        cell.fill = fill_supported
                        cell.font = font_supported
                        cell.alignment = align_center
                    elif "Known Limitation" in val or "Conditional" in val or "Preview" in val:
                        cell.fill = fill_limitation
                        cell.font = font_limitation
                        cell.alignment = align_center
                    elif "Strategic Horizon" in val or "Future Differentiator" in val or "Planned" in val:
                        cell.fill = fill_future
                        cell.font = font_future
                        cell.alignment = align_center
                    elif "Dark Module" in val or "Not Supported" in val or "Out of Scope" in val:
                        cell.fill = fill_dark
                        cell.font = font_dark
                        cell.alignment = align_center
                    else:
                        cell.font = font_regular
                        cell.alignment = align_left
                else:
                    cell.font = font_regular
                    cell.alignment = align_left
                    if row % 2 == 0:
                        cell.fill = accent_gray_fill
                    else:
                        cell.fill = white_fill

    def auto_fit_columns(ws, max_cols=12, max_len_cap=65):
        for col in range(1, max_cols + 1):
            col_letter = get_column_letter(col)
            max_len = 0
            for row in range(1, ws.max_row + 1):
                cell_val = ws.cell(row=row, column=col).value
                if cell_val:
                    lines = str(cell_val).split('\n')
                    for line in lines:
                        if len(line) > max_len:
                            max_len = len(line)
            adjusted_width = min(max(max_len + 3, 12), max_len_cap)
            ws.column_dimensions[col_letter].width = adjusted_width

    # =============================================================
    # SHEET 1: EXECUTIVE GUIDE & OVERVIEW
    # =============================================================
    ws1 = wb.active
    ws1.title = "Overview & System Scope"
    ws1.views.sheetView[0].showGridLines = True
    
    # Title Block
    ws1.merge_cells("A1:G1")
    title_cell = ws1["A1"]
    title_cell.value = "BIZBOARD: SMB BUSINESS OPERATING SYSTEM — MASTER SPECIFICATION"
    title_cell.fill = navy_header_fill
    title_cell.font = font_title
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws1.row_dimensions[1].height = 40
    
    ws1.merge_cells("A2:G2")
    sub_cell = ws1["A2"]
    sub_cell.value = "Complete Master Inventory of Features, Operational Flows, Configuration Options & Architectural Controls"
    sub_cell.fill = blue_section_fill
    sub_cell.font = font_subtitle
    sub_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws1.row_dimensions[2].height = 24
    
    metadata = [
        ("Platform Name", "BizBoard (SMB Business Operating System)"),
        ("Architecture Version", "v4.0 Canonical Architecture (Alignd with FREEZE_SCOPE.md Scope Revision 2026-09-09b)"),
        ("Date Generated", "September 22, 2026"),
        ("Core Architectural Invariants", "1. Atomic inward purchase intake (no mandatory separate GRN in pilot)\n2. Pure derived subledgers (zero balance drift by derivation from immutable documents)\n3. Append-only, strictly-typed inventory movements\n4. Strict double-entry GL (TB=0 invariant verified on every posting)\n5. Zero-float money arithmetic (fixed decimal strings on API boundaries)\n6. Strict multi-tenant isolation scoped to company_id"),
        ("Target Customer Archetypes", "ARCH-01: Specialty Counter Retailers\nARCH-03: B2B Semi-Wholesalers & Trade Merchants\nARCH-04: Multi-Godown Regional Stockists\nARCH-05: Batch & Expiry-Sensitive Stockists (Pharma/FMCG)\nARCH-06: High-Value Serialized Goods Dealers"),
    ]
    
    row_idx = 4
    for label, val in metadata:
        ws1.cell(row=row_idx, column=1, value=label).font = font_bold
        ws1.cell(row=row_idx, column=1).fill = accent_gray_fill
        ws1.cell(row=row_idx, column=1).alignment = align_left
        ws1.cell(row=row_idx, column=1).border = border_data
        
        ws1.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx, end_column=7)
        target = ws1.cell(row=row_idx, column=2, value=val)
        target.font = font_regular
        target.alignment = align_left
        target.border = border_data
        if "\n" in val:
            ws1.row_dimensions[row_idx].height = 18 * (val.count("\n") + 1)
        else:
            ws1.row_dimensions[row_idx].height = 24
        row_idx += 1
        
    row_idx += 1
    # Sheet index guide
    ws1.cell(row=row_idx, column=1, value="WORKBOOK NAVIGATION GUIDE").font = font_bold
    ws1.cell(row=row_idx, column=1).fill = teal_sub_fill
    ws1.cell(row=row_idx, column=1).font = font_header
    ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=7)
    ws1.row_dimensions[row_idx].height = 26
    row_idx += 1
    
    guide_headers = ["Sheet Name", "Domain / Subject", "Detailed Contents", "Key Use Cases / Target Audience"]
    ws1.cell(row=row_idx, column=1, value=guide_headers[0])
    ws1.cell(row=row_idx, column=2, value=guide_headers[1])
    ws1.merge_cells(start_row=row_idx, start_column=3, end_row=row_idx, end_column=5)
    ws1.cell(row=row_idx, column=3, value=guide_headers[2])
    ws1.merge_cells(start_row=row_idx, start_column=6, end_row=row_idx, end_column=7)
    ws1.cell(row=row_idx, column=6, value=guide_headers[3])
    
    for c in range(1, 8):
        ws1.cell(row=row_idx, column=c).fill = navy_header_fill
        ws1.cell(row=row_idx, column=c).font = font_header
        ws1.cell(row=row_idx, column=c).alignment = align_header
        ws1.cell(row=row_idx, column=c).border = border_header
    ws1.row_dimensions[row_idx].height = 24
    
    sheets_info = [
        ("1. Features Master Register", "All Product Capabilities", "Features across Sales, Purchase, Inventory, Accounting, GST, Ops, and AI, each with status, routes, business rules, and a recommended operating flow.", "Product managers, developers, QA, and onboarding staff choosing the path a shop should actually follow."),
        ("2. End-to-End Workflows", "Operational Business Flows", "Step sequences for quotation-to-cash, inward-to-pay, delivery, GST, and the recommended daily sales, purchase, cheque, and day-book flows.", "Operations leads, implementation specialists, and customer success architects."),
        ("3. Options & Config Master", "Settings, Flags & Formats", "Master list of all user-configurable options, system series rules, tax engines, invoice templates, and payment configurations.", "Admins, onboarding specialists, and solution architects setting up client companies."),
        ("4. Role Permission Matrix", "Security & Access Control", "Granular CRUD and Action permissions mapped across Owner, Admin, Sales Staff, Warehouse Clerk, CA/Auditor, and Delivery Driver.", "Security compliance, enterprise buyers, and external auditors."),
        ("5. Feature Flags & Env Profile", "Architecture & Deploy Flags", "Exhaustive documentation of backend and frontend feature flags (ENABLE_*, VITE_ENABLE_*), default values, and scope gates.", "DevOps engineers, platform developers, and release managers."),
        ("6. Strategic Differentiators", "Moats & OS White Space", "Deep architectural breakdown of the 13 Special Focus Areas (Action Center, Collections Autopilot, Delivery Profitability, etc.).", "Executive leadership, product strategists, and investors.")
    ]
    
    start_guide_row = row_idx + 1
    for s_name, s_dom, s_cont, s_aud in sheets_info:
        row_idx += 1
        ws1.cell(row=row_idx, column=1, value=s_name).font = font_bold
        ws1.cell(row=row_idx, column=2, value=s_dom)
        ws1.merge_cells(start_row=row_idx, start_column=3, end_row=row_idx, end_column=5)
        ws1.cell(row=row_idx, column=3, value=s_cont)
        ws1.merge_cells(start_row=row_idx, start_column=6, end_row=row_idx, end_column=7)
        ws1.cell(row=row_idx, column=6, value=s_aud)
        
        for c in range(1, 8):
            cell = ws1.cell(row=row_idx, column=c)
            cell.border = border_data
            cell.font = font_regular
            cell.alignment = align_left
            if (row_idx % 2 == 0):
                cell.fill = accent_gray_fill
        ws1.row_dimensions[row_idx].height = 32
        
    auto_fit_columns(ws1, max_cols=7, max_len_cap=45)

    print("Sheet 1 built.")

    # =============================================================
    # SHEET 2: ALL FEATURES MASTER REGISTER
    # =============================================================
    ws2 = wb.create_sheet(title="Features Master Register")
    ws2.views.sheetView[0].showGridLines = True
    
    headers_ws2 = [
        "Module / Domain",
        "Feature / Capability Name",
        "Workflow Stage",
        "Scope & Status",
        "Detailed Description & Technical Mechanics",
        "Configurable Options & Settings",
        "UI Screens & Endpoints",
        "Role Permissions",
        "Automation Level",
        "Business Invariants & Regulatory Rules",
        "Recommended Flow"
    ]
    
    # Freeze row 1
    ws2.freeze_panes = "A2"
    
    for col_idx, h in enumerate(headers_ws2, 1):
        cell = ws2.cell(row=1, column=col_idx, value=h)
        
    features_data = [
        # --- SALES & POS ---
        (
            "Sales & POS",
            "Counter POS Rapid Billing",
            "Checkout / Settlement",
            "Supported (Freeze Pilot)",
            "High-speed retail counter checkout interface. Supports real-time barcode/SKU scanning, keyboard hotkeys, cash drawer split, dynamic UPI QR generation, and sub-second receipt printing.",
            "Default godown selection; auto-print toggle; thermal printer format (2-inch vs 3-inch); cash vs UPI vs card toggles.",
            "/pos | POST /api/v1/pos/checkout/ | GET /api/v1/pos/products/",
            "Owner, Admin, Sales Staff",
            "Automated",
            "Completing sale reduces stock atomically, updates cash/bank account, records sales tax, and generates append-only stock movement. Offline drafts queued in indexedDB."
        ),
        (
            "Sales & POS",
            "B2B GST Tax Invoice (Intra-state)",
            "Order to Cash",
            "Supported (Freeze Pilot)",
            "Comprehensive B2B invoice generation with automated CGST + SGST computation based on Place of Supply. Supports customer GSTIN validation, HSN/SAC summary, and line-item discounts.",
            "Invoice numbering series; round-off toggle; default payment terms (net 15/30/45); bank account details on invoice footer.",
            "/sales/new, /sales/history/:id | POST /api/v1/sales/invoices/",
            "Owner, Admin, Sales Staff",
            "Rule-based",
            "Enforces statutory GST split when seller State == buyer State. Round-off matches Σ line rounding. Derived ledger balance updates instantly."
        ),
        (
            "Sales & POS",
            "B2B GST Tax Invoice (Inter-state)",
            "Order to Cash",
            "Supported (Freeze Pilot)",
            "Generates inter-state B2B tax invoice computing IGST (+ cess where configured). Automatically triggered when customer Place of Supply differs from company registered state.",
            "Cess configuration (ad-valorem percentage + per-unit cess); transport details (vehicle number, transporter ID).",
            "/sales/new, /sales/history/:id | POST /api/v1/sales/invoices/",
            "Owner, Admin, Sales Staff",
            "Rule-based",
            "Place of supply drives the IGST split. Updates GSTR-1 Table 4A/4B and Table 5 (large B2C inter-state)."
        ),
        (
            "Sales & POS",
            "Non-GST / Nil-Rated / Exempt Invoices",
            "Order to Cash",
            "Supported (Freeze Pilot)",
            "Bill of Supply generation for non-taxable, nil-rated, or exempt commodities. Complies with GST Section 31(3)(c).",
            "Tax-exemption reason tags; nil-rated indicator; export without payment of tax flag.",
            "/sales/new | POST /api/v1/sales/invoices/",
            "Owner, Admin, Sales Staff",
            "Rule-based",
            "Zero tax calculated; document completion posts to separate Exempt Sales GL account and feeds GSTR-1 Table 8."
        ),
        (
            "Sales & POS",
            "Sales Quotation / Proforma Invoice",
            "Pre-Sales / Estimation",
            "Supported (Freeze Pilot)",
            "Estimates and quotations issued to prospective customers. Includes line items, pricing tiers, validity dates, and one-click conversion to Sales Order or Tax Invoice.",
            "Quotation validity duration (days); quotation numbering series; discount approval threshold.",
            "/sales/quotations, /sales/quotations/:id | POST /api/v1/sales/quotations/",
            "Owner, Admin, Sales Staff",
            "Manual / Semi-Auto",
            "Quotation has zero inventory effect and zero GL impact until explicitly converted to a completed invoice."
        ),
        (
            "Sales & POS",
            "Sales Orders & Backorders",
            "Order Fulfillment",
            "Supported (Freeze Pilot)",
            "Formal sales order booking against agreed customer terms. Tracks fulfillment status (Pending, Partially Dispatched, Fulfilled, Cancelled) and enables inventory soft-reservations.",
            "Auto-reserve stock toggle; backorder allowance flag; expected delivery lead days.",
            "/sales/orders, /sales/orders/:id | POST /api/v1/sales/orders/",
            "Owner, Admin, Sales Staff",
            "Rule-based",
            "Blocks order completion if customer exceeds hard credit limit unless approved by Owner."
        ),
        (
            "Sales & POS",
            "Delivery Challans / Staged Fulfillment",
            "Dispatch / Logistics",
            "Supported (Freeze Pilot)",
            "Dispatches goods from warehouse prior to formal invoice generation. Complies with GST Rule 55 for transport of goods without tax invoice (job work, approval, staggered delivery).",
            "Challan numbering series; purpose of transport (Sale, Job-work, Exhibition, Others); vehicle details.",
            "/sales/delivery-challans, /sales/delivery-challans/:id",
            "Owner, Admin, Sales Staff, Warehouse",
            "Rule-based",
            "Increments dispatched stock movement, moves stock from Available to In-Transit, and converts to completed tax invoice in one click."
        ),
        (
            "Sales & POS",
            "Sales Return & Credit Notes (Auto-CN)",
            "Post-Sales / Returns",
            "Supported (Freeze Pilot)",
            "Processes returned goods against completed invoices. Automatically generates Credit Note (Section 34), restores inventory balance, reverses GST liability, and credits customer AR ledger.",
            "Reason code (Defective, Damaged, Quality Rejection, Cancellation); restocking location godown.",
            "/sales/returns, /sales/credit-notes | POST /api/v1/sales/returns/",
            "Owner, Admin",
            "Automated",
            "Credit note amount capped at invoice net total minus prior notes. Linked to original invoice number and date for GSTR-1 CDNR reporting."
        ),
        (
            "Sales & POS",
            "Residual Sales Debit Notes",
            "Price Escalation / Adjustment",
            "Supported (Freeze Pilot)",
            "Issues supplementary debit note for price escalation, post-sale tax adjustment, or extra transportation charges as per GST Section 34(3).",
            "Original invoice reference; supplementary tax rate; reason for debit note.",
            "/sales/debit-notes, /sales/debit-notes/new",
            "Owner, Admin",
            "Rule-based",
            "Increments AR ledger and output GST liability without altering physical inventory."
        ),
        (
            "Sales & POS",
            "Customer Receipts & Bill-by-Bill Allocation",
            "Receivables Settlement",
            "Supported (Freeze Pilot)",
            "Records cash, cheque, NEFT, or UPI payments received from customers. Allocates payment against specific open invoices or on-account advance.",
            "Allocation method (Oldest First FIFO vs Manual Selection); TDS deduction capture; payment reference UTR.",
            "/sales/receipts | POST /api/v1/sales/receipts/",
            "Owner, Admin, Sales Staff",
            "Semi-Auto / Auto",
            "Rejects over-allocation. Dynamically reduces invoice outstanding balance; posts debit to Bank/Cash and credit to AR Control."
        ),
        (
            "Sales & POS",
            "Customer Pricing Tiers & Volume Slabs",
            "Catalog & Pricing",
            "Supported (Freeze Pilot)",
            "Enables tiered price lists (Retail, Wholesale, Distributor, Institutional) and volume-based quantity discounts.",
            "Default customer price list tag; quantity slab thresholds; valid date range.",
            "/settings/price-lists | POST /api/v1/price-lists/",
            "Owner, Admin",
            "Rule-based",
            "Automatically overrides base selling price on invoice entry when customer price tier or volume threshold matches."
        ),
        (
            "Sales & POS",
            "Thermal & A4 Invoice PDF Engine",
            "Document Presentation",
            "Supported (Freeze Pilot)",
            "Dynamic document rendering engine supporting standard A4 corporate format and 2-inch / 3-inch thermal POS receipt slips. Generates PDF with embedded QR and digital signature space.",
            "Invoice template selection (Classic, Modern, Compact); logo upload; custom terms & conditions; bank details toggle.",
            "/settings/templates | GET /api/v1/sales/invoices/:id/pdf/",
            "Owner, Admin, Sales Staff",
            "Automated",
            "Complies with GST Rule 46 mandatory invoice fields (HSN table, Place of supply, reverse charge indicator, IRN QR code)."
        ),
        (
            "Sales & POS",
            "Quick Entry Voucher Mode",
            "High-Volume Data Entry",
            "Known Limitation",
            "Compact spreadsheet-like rapid billing grid for experienced operators entering multi-item invoices.",
            "Keyboard shortcut mapping; column tab order configuration.",
            "/sales/quick-entry",
            "Owner, Admin, Sales Staff",
            "Manual",
            "Optimized for high-speed Numpad entry; lacks detailed tax breakdown until previewed."
        ),
        (
            "Sales & POS",
            "Recurring Invoices & Subscriptions",
            "Billing Automation",
            "Known Limitation (Out of Freeze)",
            "Automates periodic billing for retainer clients, maintenance contracts, or rental services.",
            "Cadence (Weekly, Monthly, Quarterly, Annual); auto-send email toggle; auto-charge webhook.",
            "/sales/recurring",
            "Owner, Admin",
            "Automated",
            "Reachable in UI but gated in pilot profile; scheduled cron generates draft invoices on schedule."
        ),
        
        # --- PURCHASING & PAYABLES ---
        (
            "Purchasing & AP",
            "Atomic Purchase Bill Intake",
            "Procurement to Inward",
            "Supported (Freeze Pilot)",
            "Single-step inward procurement document. Simultaneously completes inward inventory addition to godown and posts liability to Accounts Payable ledger atomically.",
            "Supplier invoice number & date; destination godown; payment terms; TDS 194Q withholding toggle.",
            "/purchases/new, /purchases/history/:id | POST /api/v1/purchases/invoices/",
            "Owner, Admin",
            "Rule-based",
            "No separate GRN required in pilot path. Stock movement created with type PURCHASE_INWARD; input tax credit recorded to ITC Pending/Eligible GL."
        ),
        (
            "Purchasing & AP",
            "Purchase Orders (PO)",
            "Procurement Requisition",
            "Supported (Freeze Pilot)",
            "Generates official Purchase Orders sent to suppliers. Tracks supplier acknowledgment, expected delivery date, and order fulfillment status.",
            "PO numbering series; expected delivery date; supplier terms.",
            "/purchases/orders, /purchases/orders/new",
            "Owner, Admin",
            "Manual",
            "Zero inventory or financial liability until converted into a completed Purchase Bill."
        ),
        (
            "Purchasing & AP",
            "Purchase Returns & Debit Notes",
            "Post-Procurement Returns",
            "Supported (Freeze Pilot)",
            "Records goods returned to vendor due to defect, transit damage, or over-shipment. Generates statutory Debit Note, decrements warehouse stock, and reduces Accounts Payable balance.",
            "Debit note reason code; linked purchase invoice; tax adjustment amount.",
            "/purchases/returns, /purchases/debit-notes",
            "Owner, Admin",
            "Automated",
            "Reduces AP liability; reverses Input Tax Credit in GSTR-3B Table 4(B); decrements stock via RETURN_OUTWARD movement."
        ),
        (
            "Purchasing & AP",
            "Supplier Payments & Bill Settlement",
            "Disbursement",
            "Supported (Freeze Pilot)",
            "Disburses funds to suppliers via Cheque, Bank Transfer, or Cash. Allocates payments against open purchase bills with tracking of unallocated advances.",
            "Payment mode (Bank, Cash); cheque number / UTR reference; allocation mode (Manual vs FIFO).",
            "/purchases/payments | POST /api/v1/purchases/payments/",
            "Owner, Admin",
            "Semi-Auto",
            "Posts debit to Accounts Payable and credit to Cash/Bank GL. Updates bill payment status to Paid / Partially Paid."
        ),
        (
            "Purchasing & AP",
            "Supplier Directory & Dynamic Ledgers",
            "Master Data & Ledger",
            "Supported (Freeze Pilot)",
            "Central vendor master containing GSTIN, bank IFSC/account details, MSME registration type, payment terms, and real-time derived AP ledger balance.",
            "MSME classification (Micro, Small, Medium); credit period; default TDS rate.",
            "/purchases/suppliers, /reports/supplier-ledger",
            "Owner, Admin, CA/Auditor",
            "Derived",
            "Zero ledger balance tables exist; balances are computed dynamically from completed purchase bills, debit notes, and payment allocations."
        ),
        (
            "Purchasing & AP",
            "Standalone Goods Receipt Note (GRN)",
            "Warehouse Intake",
            "Future Parity (Horizon 1)",
            "Decoupled two-stage procurement workflow separating physical dock receipt (warehouse staff) from financial bill booking (accounts staff).",
            "Quality inspection stage toggle; tolerance percentage for over/under-receipt.",
            "/purchases/grn (Target Horizon 1)",
            "Warehouse Clerk, Admin",
            "Rule-based",
            "Posts stock increase to Inventory and liability to GR/IR Clearing Account pending receipt of final supplier tax invoice."
        ),
        (
            "Purchasing & AP",
            "3-Way Matching Engine",
            "Procurement Audit",
            "Future Differentiator (Horizon 2)",
            "Automated matching engine reconciling Purchase Order quantities/rates vs. Goods Receipt Notes vs. Vendor Tax Invoices.",
            "Price tolerance variance limit (e.g., ±1%); quantity tolerance limit.",
            "/purchases/reconcile-3way (Target)",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Locks payment voucher if invoice price exceeds PO price without explicit manager override."
        ),
        (
            "Purchasing & AP",
            "Bill of Entry & Landed Cost Capitalization",
            "Import Trade",
            "Known Limitation (Out of Freeze)",
            "Tracks customs duty, freight, clearing charges, and insurance on imported goods, capitalizing these expenses into unit inventory cost layers.",
            "Duty allocation method (By Value vs By Quantity); currency exchange rate.",
            "/purchases/bills-of-entry",
            "Owner, Admin",
            "Rule-based",
            "Reachable in code but marked as pilot limitation (FREEZE_SCOPE D10); workarounds via domestic charge lines."
        ),
        
        # --- INVENTORY MANAGEMENT ---
        (
            "Inventory",
            "Append-Only Typed Stock Movement Engine",
            "Warehouse / Stock Ledger",
            "Supported (Core Invariant)",
            "Core inventory accounting engine. Every stock change is an immutable, typed ledger row (PURCHASE_INWARD, SALE_OUTWARD, TRANSFER_IN, TRANSFER_OUT, ADJUSTMENT, RETURN).",
            "FIFO vs Moving Average valuation method toggle.",
            "/inventory/stock | GET /api/v1/inventory/movements/",
            "Owner, Admin, Warehouse",
            "Automated",
            "Current stock balance for any (item, godown, lot) equals the exact sum of all append-only movements. Negative stock blocked."
        ),
        (
            "Inventory",
            "Multi-Godown / Location Tracking",
            "Multi-Site Logistics",
            "Supported (Freeze Pilot)",
            "Manages multiple physical storage locations (Central Warehouse, Showroom Counter, Peripheral Godowns, In-Transit).",
            "Default billing godown; active godown flags; address and manager assignment.",
            "/inventory/warehouses | POST /api/v1/inventory/warehouses/",
            "Owner, Admin, Warehouse",
            "Rule-based",
            "Requires warehouse selection on every line item during billing or purchase."
        ),
        (
            "Inventory",
            "Inter-Godown Stock Transfers",
            "Internal Logistics",
            "Supported (Freeze Pilot)",
            "Transfers stock between warehouses with two-phase commit: Staged/Dispatched from Source Godown → Received at Destination Godown.",
            "In-transit tracking toggle; driver/vehicle details; transfer note printing.",
            "/inventory/transfers | POST /api/v1/inventory/transfers/",
            "Owner, Admin, Warehouse",
            "Automated",
            "Atomically posts TRANSFER_OUT at origin and TRANSFER_IN at destination; ensures total company inventory remains unchanged."
        ),
        (
            "Inventory",
            "Batch & Expiry Date Management (FEFO)",
            "Perishable / Pharma",
            "Supported (Freeze Pilot)",
            "Tracks manufactured products by batch/lot number, manufacturing date, and expiry date. Enforces First-Expiry-First-Out picking during sales.",
            "Mandatory batch toggle per product; expiry warning threshold (e.g., 30/60/90 days); block expired stock dispatch toggle.",
            "/inventory/expiry-alerts, /inventory/products",
            "Owner, Admin, Sales Staff, Warehouse",
            "Automated / Rule-based",
            "Prevents invoicing of expired stock; generates near-expiry discount alert reports."
        ),
        (
            "Inventory",
            "Serial Number & IMEI Tracking",
            "High-Value Electronics",
            "Supported (Freeze Pilot)",
            "Tracks unique serialized inventory items from inward purchase to outward counter sale. Records warranty status and customer ownership history.",
            "Mandatory serial scanning toggle; serial prefix rule.",
            "/inventory/serials | GET /api/v1/inventory/serials/",
            "Owner, Admin, Sales Staff",
            "Rule-based",
            "Validates serial availability; moves state from AVAILABLE to SOLD on invoice completion."
        ),
        (
            "Inventory",
            "Physical Inventory Cycle Counts & Variance Reconciliation",
            "Stock Audit",
            "Supported (Freeze Pilot)",
            "Conducts periodic physical stocktaking sessions. Compares system book stock with counted physical stock and generates variance quarantine report.",
            "Count session scope (Entire warehouse vs Specific category vs Random sample); auto-adjustment threshold.",
            "/inventory/stock-counts | POST /api/v1/inventory/stock-counts/",
            "Owner, Admin, CA/Auditor",
            "Semi-Auto",
            "Manager approval of count session automatically posts typed STOCK_ADJUSTMENT movements and variance write-off GL entry."
        ),
        (
            "Inventory",
            "Stock Adjustments & Shrinkage Write-offs",
            "Inventory Control",
            "Supported (Freeze Pilot)",
            "Manual inventory adjustment for stock loss, transit breakage, shrinkage, quality expiration, or found items.",
            "Adjustment reason codes (Damage, Shrinkage, Audit Finding, Donation); target expense GL account.",
            "/inventory/adjustments | POST /api/v1/inventory/adjustments/",
            "Owner, Admin",
            "Rule-based",
            "Requires mandatory reason; updates stock balance and posts offset entry to Stock Adjustment Expense / Loss account."
        ),
        (
            "Inventory",
            "Barcode & Product Label Printing",
            "Product Staging",
            "Supported (Freeze Pilot)",
            "Generates customized barcode labels (Code128, QR Code, EAN-13) for products. Supports standard thermal barcode sticker sheets (24-up, 40-up, single roll).",
            "Label dimensions (width/height in mm); fields to include (Product Name, SKU, MRP, Selling Price, Expiry Date).",
            "/inventory/labels",
            "Owner, Admin, Warehouse",
            "Automated",
            "Reads product master data and batch numbers to generate print-ready SVG/PDF sheets."
        ),
        (
            "Inventory",
            "Dynamic Low Stock Alerts & Reorder Points",
            "Stock Replenishment",
            "Supported (Freeze Pilot)",
            "Monitors stock levels against configured minimum thresholds and alerts managers when items breach safety margins.",
            "Minimum stock level per godown; reorder quantity recommendation; notification frequency.",
            "/inventory/low-stock | GET /api/v1/inventory/low-stock/",
            "Owner, Admin, Warehouse",
            "Automated",
            "Surfaces critical stockout warnings on Action Center dashboard."
        ),
        (
            "Inventory",
            "Stock Valuation Engine",
            "Financial Reporting",
            "Supported (Freeze Pilot)",
            "Calculates inventory valuation under FIFO (First-In, First-Out) or Moving Weighted Average cost rules for financial balance sheet reporting.",
            "Valuation rule toggle (FIFO vs Moving Weighted Average); include landed costs toggle.",
            "/reports/stock-valuation",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Produces statutory stock valuation report matching Trial Balance stock-in-hand control account."
        ),

        # --- FINANCE, BANKING & GENERAL LEDGER ---
        (
            "Finance & GL",
            "Derived Customer & Supplier Subledgers",
            "AR / AP Ledgers",
            "Supported (Core Invariant)",
            "Architectural invariant: zero balance tables exist. Balances are derived in real time from immutable completed documents, returns, and payment allocations.",
            "Date range filtering; include unallocated advances toggle; export to Excel/PDF.",
            "/reports/customer-ledger, /reports/supplier-ledger",
            "Owner, Admin, CA/Auditor",
            "Derived",
            "Completely eliminates reconciliation drift between subledgers and general ledger accounts."
        ),
        (
            "Finance & GL",
            "Double-Entry General Ledger Backbone",
            "Financial Control",
            "Supported (Freeze Pilot)",
            "Comprehensive double-entry general ledger. Every completed sales invoice, purchase bill, receipt, payment, and return posts balanced debit/credit journal lines.",
            "Standard Chart of Accounts; custom ledger groups; currency decimal precision (2 places).",
            "/accounting/accounts, /accounting/journals",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Trial Balance = 0 (Debits == Credits) enforced on every posting transaction. Rejects unbalanced entries."
        ),
        (
            "Finance & GL",
            "Statutory Financial Statements (P&L, Balance Sheet, TB)",
            "Financial Reporting",
            "Supported (Freeze Pilot)",
            "Real-time financial statement reporting including Trial Balance, Profit & Loss Statement (Schedule III format), and Balance Sheet.",
            "Comparative period view; cash vs accrual basis; drilldown to voucher source.",
            "/reports/profit-and-loss, /reports/balance-sheet, /reports/trial-balance",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Derived directly from immutable GL entries; verified against golden financial snapshots."
        ),
        (
            "Finance & GL",
            "Manual Journal Vouchers",
            "Adjustments & Provisions",
            "Supported (Freeze Pilot)",
            "Allows accountants to enter adjusting journal vouchers for accrued expenses, prepayments, non-cash charges, and year-end provisions.",
            "Reference document number; narration text; cost center tagging.",
            "/accounting/journals | POST /api/v1/accounting/journals/",
            "Owner, Admin, CA/Auditor",
            "Manual",
            "Strict validation: total debits must equal total credits; both lines require valid active ledger accounts."
        ),
        (
            "Finance & GL",
            "Accounting Period Close & Reversal Governance",
            "Compliance & Audit",
            "Supported (Freeze Pilot)",
            "Enforces accounting period closing (monthly/annual). Blocks back-dated document posting in closed periods; sanctions H9 reversing entries for corrections.",
            "Period close lock date; allowable correction grace days; audit trail logging.",
            "/accounting/periods | POST /api/v1/accounting/periods/close/",
            "Owner, CA/Auditor",
            "Rule-based",
            "Closed period strictly blocks mutations. Correction creates a linked reversing voucher pair netting to zero."
        ),
        (
            "Finance & GL",
            "Bank Account Master & Cash Till Management",
            "Cash & Bank",
            "Supported (Freeze Pilot)",
            "Manages multiple commercial bank accounts, petty cash drawers, and UPI collection virtual accounts.",
            "Bank IFSC, account number, branch; default cash drawer; daily till opening/closing balance.",
            "/settings/bank-accounts, /reports/cash-book",
            "Owner, Admin, CA/Auditor",
            "Rule-based",
            "Ensures cash and bank transactions reconcile to their respective parent GL control accounts."
        ),
        (
            "Finance & GL",
            "Bank Statement Auto-Reconciliation",
            "Cash Management",
            "Supported (Freeze Pilot)",
            "Imports bank statements (CSV/Excel/OFX) and matches transactions against recorded customer receipts, supplier payouts, and bank charges.",
            "Auto-match rule tolerance (exact date ± 3 days, exact amount); auto-create voucher rule for bank fees.",
            "/accounting/bank-reconciliation, /payments/reconciliation",
            "Owner, Admin, CA/Auditor",
            "Semi-Auto",
            "Produces Bank Reconciliation Statement (BRS) showing book balance vs bank balance with timing differences."
        ),
        (
            "Finance & GL",
            "Dynamic Payment Links & Hosted Checkout (/pay/:token)",
            "Receivables Collection",
            "Supported (Freeze Pilot)",
            "Generates secure public payment links sent to debtors via WhatsApp/SMS. Customers view invoice details and pay via UPI, NetBanking, or Credit Card.",
            "Payment gateway selection (Cashfree, PayU); expiry duration (hours/days); partial payment allowance flag.",
            "/payments/links, /pay/:token | POST /api/v1/payments/links/",
            "Owner, Admin, Sales Staff",
            "Automated",
            "Webhook capture from gateway automatically verifies signature, records Customer Receipt, and allocates against invoice."
        ),
        (
            "Finance & GL",
            "Connected Banking / Account Aggregator (AA)",
            "Open Banking",
            "Known Limitation (Out of Freeze)",
            "Direct API integration with commercial banks via RBI Account Aggregator framework for automated live bank statement pulls.",
            "AA consent duration; auto-sync interval (hourly/daily).",
            "/payments/account-aggregator",
            "Owner, CA/Auditor",
            "Automated",
            "Gated in pilot profile (`ENABLE_ACCOUNT_AGGREGATOR=0`); planned for post-pilot rollout."
        ),
        (
            "Finance & GL",
            "Cost Centers & Project Accounting",
            "Management Accounting",
            "Supported (Freeze Pilot)",
            "Allocates revenue and operational expenses across cost centers, business branches, sales regions, or vehicle fleets.",
            "Cost center hierarchy; mandatory tagging toggle on sales/purchase vouchers.",
            "/accounting/cost-centers",
            "Owner, Admin, CA/Auditor",
            "Rule-based",
            "Enables segmented P&L reporting by branch, salesperson, or vehicle."
        ),
        (
            "Finance & GL",
            "Fixed Assets & Depreciation Schedules",
            "Asset Accounting",
            "Known Limitation (Out of Freeze)",
            "Tracks company fixed assets, capitalization dates, salvage values, and computes monthly depreciation under WDV or SLM methods.",
            "Depreciation method (Written Down Value vs Straight Line); asset category useful life rules.",
            "/accounting/fixed-assets",
            "Owner, CA/Auditor",
            "Automated",
            "Gated in pilot (`ENABLE_FIXED_ASSETS=0`); manual journal entries used as workaround."
        ),

        # --- TAXATION & STATUTORY COMPLIANCE (GST / TDS / TCS) ---
        (
            "Tax & GST",
            "Automated GST Computation Engine",
            "Tax Engine",
            "Supported (Freeze Pilot)",
            "Determines Place of Supply rules, resolves HSN/SAC tax rates, computes intra-state (CGST+SGST) vs inter-state (IGST) split, and handles ad-valorem + unit cess.",
            "Default company GSTIN; state code; Composition scheme vs Regular scheme toggle.",
            "/settings/gst",
            "Owner, Admin",
            "Automated",
            "Strict compliance with GST Rules; prevents tax mismatches by deriving rates from product HSN master."
        ),
        (
            "Tax & GST",
            "GSTR-1 Preparation & Reconciliation Worksheet",
            "Statutory Reporting",
            "Supported (Freeze Pilot)",
            "Aggregates outward sales, debit/credit notes, export invoices, and nil-rated supplies into official GSTR-1 tables (B2B 4A, B2CL 5, B2CS 7, CDNR 9B, HSN 12, DOCS 13).",
            "Filing period (Monthly vs Quarterly QRMP); HSN 4-digit vs 6-digit formatting.",
            "/reports/gstr1, /reports/gstr-1",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Produces clean audit worksheet for CA sign-off; JSON export format matching GSTN schema."
        ),
        (
            "Tax & GST",
            "GSTR-3B Summary Calculation Engine",
            "Tax Settlement",
            "Supported (Freeze Pilot)",
            "Synthesizes net tax liability: Table 3.1 Outward Taxable Supplies minus Table 4 Eligible Input Tax Credit (ITC), factoring in credit/debit note reversals.",
            "RCM liability inclusion; ineligible ITC under Section 17(5) quarantine.",
            "/reports/gstr3b, /reports/gstr-3b",
            "Owner, CA/Auditor",
            "Automated",
            "Outputs net cash tax liability payable via electronic cash ledger."
        ),
        (
            "Tax & GST",
            "GSTR-2B Automated Inward ITC Match (GST Guard)",
            "ITC Audit",
            "Strategic Horizon 2 (Differentiator)",
            "Automated daily sync pulling supplier filings from GSTR-2B API and performing fuzzy reconciliation against internal purchase register.",
            "Matching tolerance (Invoice date ±30 days, Tax amount ± ₹2); auto-payment hold on delinquent vendors.",
            "/reports/gstr2b (Target Horizon 2)",
            "Owner, CA/Auditor",
            "Automated",
            "Flags missing supplier invoices under Section 16(2)(aa); prevents claiming ineligible ITC and incurring 18% penalty interest."
        ),
        (
            "Tax & GST",
            "NIC E-Invoice Live Integration (IRN & Signed QR)",
            "Statutory Clearance",
            "Preview / Sandbox in Pilot (Horizon 1 Live)",
            "Direct API integration with Invoice Registration Portal (IRP). Generates 64-character Invoice Reference Number (IRN) and digitally signed QR code embedded on PDF.",
            "GSP provider credentials; sandbox vs production mode toggle; auto-generate on invoice complete toggle.",
            "/settings/gst, /sales/history/:id",
            "Owner, Admin",
            "Automated",
            "Mandatory for taxpayers >₹5Cr turnover. Offline payload validation active in pilot; live GSP in Horizon 1."
        ),
        (
            "Tax & GST",
            "NIC E-Way Bill Generation & Tracking",
            "Transport Compliance",
            "Manual in Pilot (Horizon 1 Live)",
            "Generates statutory E-Way bills for consignment value >₹50,000 as required under GST Rule 138. Supports Part A and Part B vehicle updating.",
            "Transporter ID; vehicle number; transport mode (Road, Rail, Air, Ship); distance in km.",
            "/sales/delivery-challans, /sales/history/:id",
            "Owner, Admin, Warehouse",
            "Rule-based",
            "Validates consignment threshold; stores returned E-Way bill number and validity period on invoice."
        ),
        (
            "Tax & GST",
            "TDS (Section 194Q) & TCS (Section 206C(1H)) Withholding",
            "Direct Tax Withholding",
            "Supported (Freeze Pilot)",
            "Automated calculation and ledger deduction for Tax Deducted at Source on purchase >₹50L (194Q) and Tax Collected at Source on sales >₹50L (206C).",
            "Threshold tracking toggle; explicit withholding amount override; PAN availability check (higher rate if no PAN).",
            "/reports/tds-tcs | GET /api/v1/tax/tds-summary/",
            "Owner, CA/Auditor",
            "Automated",
            "Posts dedicated credit to TDS/TCS Payable liability account; logs explicit rate and overrides for audit."
        ),
        (
            "Tax & GST",
            "Statutory Licences & Compliance Tags",
            "Industry Compliance",
            "Supported (Freeze Pilot)",
            "Stores mandatory trade licenses (Drug License 20B/21B, FSSAI Food License, Seed/Pesticide License, Pollution Consent) with expiry alerts.",
            "License type, number, issuing authority, expiry date; mandatory print on invoice header toggle.",
            "/settings/statutory-licences",
            "Owner, Admin",
            "Rule-based",
            "Warns operators 30 days before statutory license expiration; prints statutory numbers on customer bills."
        ),
        (
            "Tax & GST",
            "Composition Scheme (CMP-08) Support",
            "Small Retailer Tax",
            "Known Limitation (Out of Freeze)",
            "Quarterly tax computation for small retailers registered under the GST Composition Scheme (flat 1% on turnover, zero ITC).",
            "Composition turnover tax rate; quarterly filing cycle.",
            "/reports/cmp08",
            "Owner, CA/Auditor",
            "Rule-based",
            "Gated in pilot (`ENABLE_COMPOSITION=0`); deprioritized commercially in favor of regular B2B traders."
        ),

        # --- OPERATIONS, DISPATCH & ROUTE LOGISTICS ---
        (
            "Operations & Fleet",
            "Dispatch Staging & Multi-Order Grouping",
            "Fulfillment Logistics",
            "Strategic Horizon 2 (White Space)",
            "Groups pending fulfilled orders by geographical delivery zone, town sector, or destination pincode for consolidated fleet dispatch.",
            "Delivery zone definitions; maximum staging window (hours); delivery priority flags.",
            "/operations/dispatch-staging (Target)",
            "Warehouse Clerk, Admin",
            "Semi-Auto",
            "Consolidates 20 individual invoices into a single dispatch batch with aggregate packing list."
        ),
        (
            "Operations & Fleet",
            "Vehicle Capacity Allocation & Load Planning",
            "Fleet Management",
            "Strategic Horizon 2 (White Space)",
            "Matches batched dispatch orders against available vehicle profiles (Two-wheeler, Tempo, 14ft Truck) constrained by gross weight (kg) and cubic volume.",
            "Vehicle profiles (Max payload kg, Max volume m³); driver assignment; vehicle maintenance status.",
            "/operations/fleet-planning (Target)",
            "Operations Lead, Warehouse",
            "Automated",
            "Prevents vehicle overloading and transit fines; flags excess orders for secondary trip."
        ),
        (
            "Operations & Fleet",
            "Sequential Route Planning & Stop Sequencing",
            "Delivery Logistics",
            "Strategic Horizon 2 (White Space)",
            "Sequences multi-order delivery stops using traveling-salesperson optimization algorithms to minimize total driving distance and transit time.",
            "Start/end hub coordinates; delivery time window constraints; traffic factor.",
            "/operations/route-planner (Target)",
            "Operations Lead, Driver",
            "Automated",
            "Generates sequential delivery run manifest with turn-by-turn stop order for delivery driver."
        ),
        (
            "Operations & Fleet",
            "Delivery Run Manifest & Driver Mobile PWA",
            "Field Logistics",
            "Strategic Horizon 2 (White Space)",
            "Mobile-friendly PWA view for delivery drivers showing stop-by-stop orders, customer phone numbers, collection amounts, and one-click navigation.",
            "Driver login credentials; offline stop caching; allow cash collection toggle.",
            "/mobile/driver-manifest (Target)",
            "Delivery Driver",
            "Interactive",
            "Operates offline; synchronizes delivery status when network reconnects."
        ),
        (
            "Operations & Fleet",
            "Proof of Delivery (POD) & Instant Cash Capture",
            "Settlement Logistics",
            "Strategic Horizon 2 (White Space)",
            "Captures customer signature, OTP confirmation, or photo proof of delivery upon handover. Records cash collected by driver directly into driver transit till.",
            "Mandatory OTP verification toggle; photo upload requirement.",
            "/mobile/pod-capture (Target)",
            "Delivery Driver, Customer",
            "Rule-based",
            "Real-time update: marks order DELIVERED, posts driver cash collection receipt, and updates AR ledger."
        ),
        (
            "Operations & Fleet",
            "Route Economics & Delivery Profitability Engine",
            "Cost & Margin Analytics",
            "Strategic Horizon 3 (Flagship Differentiator)",
            "Calculates the true net operating profitability of each delivery run by allocating fixed driver wages and variable vehicle fuel/depreciation costs across orders.",
            "Vehicle cost per km; driver daily wage rate; stop penalty overhead.",
            "/reports/route-profitability (Target)",
            "Owner, Operations Lead",
            "Automated",
            "Reveals true unit economics: Order Revenue - COGS - Attributed Delivery Cost = Real Operating Profit."
        ),

        # --- COLLECTIONS & DEBTOR RECOVERY ---
        (
            "Collections & AR",
            "Collections Autopilot (Escalating Cadence Engine)",
            "Receivables Recovery",
            "Strategic Horizon 2 (Differentiator)",
            "Autonomous multi-channel dunning engine executing scheduled reminder cadences (Polite reminder at Day -3, Due alert on Day 0, Urgent notice on Day +7, Account freeze on Day +15).",
            "Dunning cadence templates; delivery channel (WhatsApp vs SMS vs Email); escalation intervals; grace period.",
            "/settings/collections, /sales/dunning (Target)",
            "Owner, Admin",
            "Automated",
            "Sends personalized WhatsApp messages with embedded one-click UPI payment links. Shortens DSO by 7–14 days."
        ),
        (
            "Collections & AR",
            "Automated Debtor Account Freezes & Credit Holds",
            "Credit Governance",
            "Supported (Freeze Pilot)",
            "Automatically locks billing for customers whose overdue balances exceed their assigned credit limit or overdue grace days.",
            "Hard stop vs Soft warning toggle; Owner override password; maximum overdue days.",
            "/settings/company, /sales/customers/:id",
            "Owner, Admin",
            "Automated",
            "Prevents sales clerks from issuing new delivery challans or invoices to chronically delinquent accounts without owner authorization."
        ),
        (
            "Collections & AR",
            "Promise-to-Pay Logging & Follow-up Tracker",
            "Receivables Operations",
            "Supported (Freeze Pilot)",
            "Logs debtor commitments (e.g., 'Customer promised ₹50,000 by Thursday'). Tracks fulfillment rate and reschedules dunning until promised date.",
            "Promise date, amount, debtor contact note; alert snooze toggle.",
            "/sales/customers/:id/promises",
            "Owner, Admin, Sales Staff",
            "Semi-Auto",
            "Temporarily pauses automated WhatsApp dunning until promise date expires."
        ),

        # --- INTELLIGENCE, AUTOMATION & ACTION CENTER ---
        (
            "Intelligence",
            "Action Center ('Today' Priority Triage)",
            "Operational Orchestration",
            "Supported (Freeze Pilot / Polish)",
            "Unified morning triage screen replacing static vanity dashboards. Prioritizes critical operational tasks requiring owner attention today.",
            "Triage category filters (Receivables, Stockouts, Tax Deadlines, Approvals); priority weighting.",
            "/attention, /",
            "Owner, Admin",
            "Automated / Predictive",
            "Aggregates: Invoices overdue today, items reaching critical reorder level, suppliers missing GSTR-2B filing, and pending delivery dispatches."
        ),
        (
            "Intelligence",
            "Inventory Autopilot (Run-Rate Reorder Engine)",
            "Replenishment Automation",
            "Strategic Horizon 2 (Differentiator)",
            "Continuously analyzes historical sales velocity, seasonal spikes, and supplier delivery lead times to compute optimal reorder points and auto-generate draft POs.",
            "Safety stock buffer days (e.g., 7 days); supplier lead time default; auto-draft PO toggle.",
            "/inventory/autopilot (Target)",
            "Owner, Admin",
            "Predictive",
            "Generates ready-to-approve purchase orders for distributors before stockouts occur, eliminating manual clipboard counting."
        ),
        (
            "Intelligence",
            "Supplier Intelligence Scorecard",
            "Vendor Performance",
            "Strategic Horizon 2 (Differentiator)",
            "Ranks suppliers objectively across 4 dimensions: On-time fulfillment rate, Fill-rate accuracy, Historical price inflation creep, and GSTR-2B compliance.",
            "Scorecard weighting factors; evaluation window (30/60/90 days).",
            "/reports/supplier-intelligence (Target)",
            "Owner, Admin",
            "Automated",
            "Provides leverage during procurement price negotiations by exposing vendor delivery delays and price creep."
        ),
        (
            "Intelligence",
            "Deterministic LLM Bill Extraction (OCR + Parser)",
            "Data Ingestion",
            "Strategic Horizon 2 (Differentiator)",
            "Extracts line items, HSN codes, tax rates, batch numbers, and expiry dates from uploaded supplier paper invoices or WhatsApp PDF bills using multi-modal LLMs.",
            "Auto-match SKU fuzzy confidence threshold; require human verification toggle.",
            "/purchases/bill-upload",
            "Owner, Admin",
            "AI-Assisted",
            "Converts paper bills into structured draft purchase invoices in under 15 seconds, saving 2 hours of daily data entry."
        ),
        (
            "Intelligence",
            "Predictive Cash-Flow & Working Capital Forecaster",
            "Financial Forecasting",
            "Strategic Horizon 3 (Differentiator)",
            "Models expected cash balances over a 30-day forward window by combining bank balance, anticipated receivables (weighted by customer payment probability), and committed payables.",
            "Forecast window (15/30/60 days); include pending sales orders toggle.",
            "/insights/cashflow",
            "Owner, CA/Auditor",
            "Predictive",
            "Warns owners 10 days in advance if liquidity will fall below payroll and supplier liability thresholds."
        ),
        (
            "Intelligence",
            "Conversational Business Query Assistant (Natural Language)",
            "Decision Support",
            "Known Limitation (Out of Freeze)",
            "Allows owners to query operational data in plain English or Hindi ('Who owes me more than ₹1 lakh for over 30 days?') and receive instant, verifiable answers.",
            "Language selection (English, Hindi, Hinglish); voice input toggle.",
            "/insights/assistant",
            "Owner",
            "AI-Assisted",
            "Translates natural language to company-scoped SQL queries; strictly read-only; provides deep links to source vouchers."
        ),

        # --- PLATFORM, SECURITY & SETTINGS ---
        (
            "Platform & Admin",
            "Multi-Tenant Shared Database Architecture",
            "Architecture Backbone",
            "Supported (Core Invariant)",
            "Strict tenant data isolation where every table row, list endpoint, and database mutation is scoped to company_id. Prevents cross-tenant data leakage.",
            "Dedicated schema per tenant vs shared row-level security policy.",
            "All API endpoints | Header: X-Company-Id",
            "System / Platform",
            "Automated",
            "Rejects any query or mutation lacking verified company_id authentication context; eliminates IDOR vulnerabilities."
        ),
        (
            "Platform & Admin",
            "Role-Based Access Control (RBAC)",
            "Security & Governance",
            "Supported (Freeze Pilot)",
            "Granular permission system enforcing role boundaries: Owner (Unrestricted), Admin (Operational manager), Sales Staff (Restricted billing/pos), CA/Auditor (Read-only reports).",
            "Custom role creation; mask cost price toggle for sales staff; restrict discount limit toggle.",
            "/settings/users | POST /api/v1/users/",
            "Owner, Admin",
            "Rule-based",
            "Sales staff blocked from viewing gross profit margins, modifying past vouchers, or deleting customer ledgers."
        ),
        (
            "Platform & Admin",
            "OTP-Based Passwordless Login & Authentication",
            "User Access",
            "Supported (Freeze Pilot)",
            "Secure authentication via Mobile SMS OTP or Email Magic Link in addition to standard password login. Includes brute-force lockout and hashed OTP tokens.",
            "OTP expiry duration (minutes); maximum retry attempts (default 3); session timeout window.",
            "/login, /register | POST /api/v1/auth/otp/request/",
            "All Users",
            "Automated",
            "Hashes OTP at rest in Redis/database; rate-limits requests by IP and mobile number."
        ),
        (
            "Platform & Admin",
            "Guided Setup Wizard & First-Run Checklist",
            "User Onboarding",
            "Supported (Freeze Pilot)",
            "Interactive onboarding workflow guiding new business owners through 4 setup milestones: 1. Company & GSTIN Setup, 2. Item Catalog Import, 3. Opening Balances, 4. First Test Invoice.",
            "Setup wizard enable/disable flag (`ENABLE_SETUP_WIZARD`); skip wizard toggle.",
            "/setup",
            "Owner",
            "Interactive",
            "Reduces onboarding friction; achieves 'Time to First Invoice' in under 3 minutes."
        ),
        (
            "Platform & Admin",
            "Customer & Vendor Self-Onboarding Magic Portal",
            "Partner Network",
            "Strategic Horizon 2 (Differentiator)",
            "Generates secure one-time invite links sent to new customers or vendors, allowing them to fill their legal business name, GST certificate, PAN, and bank details directly.",
            "Require GSTIN validation toggle; auto-fetch trade name from GSTN API.",
            "/invite, /onboard/:token",
            "Owner, Admin, External Partners",
            "Automated",
            "Eliminates manual re-typing of partner information; prevents billing typos in legal names."
        ),
        (
            "Platform & Admin",
            "Document Numbering Series & Custom Prefixes",
            "Document Governance",
            "Supported (Freeze Pilot)",
            "Configures custom voucher numbering sequences for Invoices, Quotations, Orders, Challans, Receipts, and Debit/Credit Notes with fiscal year resets.",
            "Prefix (e.g., 'INV-26-'), suffix, starting sequence number, auto-reset every April 1st toggle.",
            "/settings/series",
            "Owner, Admin",
            "Rule-based",
            "Guarantees contiguous, unique document numbers per company conforming to GST Rule 46."
        ),
        (
            "Platform & Admin",
            "Idempotent Bulk Data Import & Migration Engine",
            "Data Management",
            "Supported (Freeze Pilot)",
            "High-capacity bulk import engine for Products, Customers, Suppliers, and Opening Stock from Excel/CSV templates with strict deduplication and validation.",
            "Duplicate action (Skip vs Overwrite); default warehouse for stock; batch size.",
            "/settings/import | POST /api/v1/import/process/",
            "Owner, Admin",
            "Automated",
            "Re-running the same import file is 100% idempotent; prevents double stock or duplicate customer entries."
        ),
        (
            "Platform & Admin",
            "One-Click Tally Historical Migration Engine",
            "Data Migration",
            "Known Limitation in Pilot (Horizon 1 Differentiator)",
            "Parses native Tally XML export files to import complete Chart of Accounts, Masters, Opening Stock Balances, and Historical Invoices without data loss.",
            "Fiscal year mapping; ignore inactive ledgers toggle.",
            "/settings/tally",
            "Owner, CA/Auditor",
            "Automated",
            "Overcomes the primary barrier to switching off Tally; preserves historical ledger integrity."
        ),
        (
            "Platform & Admin",
            "Vernacular & Multi-Language UI (Hindi / Regional)",
            "Localization",
            "Supported (Freeze Pilot)",
            "Complete vernacular language localization of the web and mobile UI, with priority on Hindi on money and POS billing screens.",
            "Language toggle (English, Hindi, Hinglish); thermal receipt vernacular printing.",
            "Global Navigation Bar | Header: Accept-Language",
            "All Users",
            "Rule-based",
            "Tested on core money screens with native localized terminology (पूर्ण, बकाया, वापस)."
        ),
        (
            "Platform & Admin",
            "Automated Right-to-Erasure & Data Privacy Engine",
            "Privacy Compliance",
            "Supported (Freeze Pilot)",
            "Anonymizes personal identifying data (PII) upon verified customer request while preserving immutable tax and accounting ledger integrity for statutory audit periods.",
            "Retention window (8 years under Indian Companies Act); anonymize customer name/phone toggle.",
            "/settings/company/privacy",
            "Owner",
            "Automated",
            "Complies with Digital Personal Data Protection (DPDP) Act 2023; protects financial ledger auditability."
        ),
        (
            "Sales & POS",
            "Invoice Quick Settings",
            "Order to Cash",
            "Supported (Freeze Pilot)",
            "One settings dialog on the sales invoice: industry presets that suggest header fields, party custom fields, item-table columns, purchase-price visibility, an empty signature box, and links to number series and invoice terms.",
            "Industry preset (trading / manufacturing / services); show batch columns; show purchase price; empty signature box.",
            "/sales/new Settings | /settings/templates | /settings/series | /settings/items",
            "Owner, Admin, Sales Staff",
            "Manual",
            "Presets only suggest fields. Number series and GST registration stay on their own settings screens."
        ),
        (
            "Sales & POS",
            "Record Invoice Payment with Settlement Discount",
            "Receivables Settlement",
            "Supported (Freeze Pilot)",
            "From a completed invoice with an open balance, record amount received, a settlement discount, payment date, and mode. The discount reduces receivable after tax; it does not rewrite the invoice GST.",
            "Payment date; settlement discount; mode (cash, UPI, bank, cheque); notes.",
            "/sales/history row menu Record payment | /sales/history/:id",
            "Owner, Admin, Sales Staff",
            "Semi-Auto",
            "Amount plus discount cannot exceed the open balance. Invoice tax snapshot stays unchanged."
        ),
        (
            "Sales & POS",
            "Cheque Receipts and Clearance",
            "Receivables Settlement",
            "Supported (Freeze Pilot)",
            "Cheque is a payment mode with number, bank, date, and an optional image. The invoice can show paid while the cheque is pending. Day Book and cash position count the cheque only after it is cleared. A bounce reverses the paid mark.",
            "Cheque number, bank, date, image; status Pending / Cleared / Bounced.",
            "/sales/receipts | /purchases/payments | /reports/day-book",
            "Owner, Admin",
            "Semi-Auto",
            "Pending cheques are not cash. Bounce unmarks the invoice paid; it is not a full bank-reconciliation subsystem."
        ),
        (
            "Sales & POS",
            "Share Invoice",
            "Document Presentation",
            "Supported (Freeze Pilot)",
            "Send the invoice PDF by email or open a WhatsApp share from the invoice and from the sales-history row menu.",
            "Recipient email or phone; PDF attachment.",
            "/sales/history row Share | /sales/history/:id Share",
            "Owner, Admin, Sales Staff",
            "Semi-Auto",
            "Share uses the same invoice PDF as print. It does not create a payment link by itself."
        ),
        (
            "Sales & POS",
            "HSN-wise Tax Summary on the Invoice",
            "Document Presentation",
            "Supported (Freeze Pilot)",
            "A completed GST invoice PDF prints an HSN/SAC table: taxable value, CGST or IGST rate and amount, SGST, cess, and total tax, under the line items.",
            "Shown when the invoice is a tax invoice with lines. Hidden on non-GST bills.",
            "Invoice PDF | /sales/history/:id Print",
            "Owner, Admin, Sales Staff",
            "Automated",
            "HSN totals must match the invoice tax summary. Place of supply chooses CGST+SGST versus IGST."
        ),
        (
            "Sales & POS",
            "Sales History Payment Filters",
            "Receivables Settlement",
            "Supported (Freeze Pilot)",
            "Sales history can be filtered by document status and by paid, partial, or unpaid, with date presets and a small stats strip.",
            "Status chips; payment-status chips; today / week / month / custom dates.",
            "/sales/history",
            "Owner, Admin, Sales Staff",
            "Manual",
            "Paid means open balance is zero. A fully returned invoice shows Returned, not Paid."
        ),
        (
            "Sales & POS",
            "Expected Margin on the Bill",
            "Order to Cash",
            "Supported (Freeze Pilot)",
            "While drafting a sales invoice, show expected profit from selling price versus purchase price so the clerk can see margin before complete.",
            "Show purchase price (Quick Settings). Uses the item purchase price already on the product.",
            "/sales/new",
            "Owner, Admin",
            "Automated",
            "This is an estimate at draft time. Posted profit still comes from the completed invoice and stock cost."
        ),
        (
            "Sales & POS",
            "Delivery Routes",
            "Dispatch / Logistics",
            "Supported (Freeze Pilot)",
            "Plan a route from sales orders, order the stops, and move the route from planned to in transit. A stop can be marked delivered, failed, or returned. Stops can be removed only while the route is still planned.",
            "Route date; stop sequence; stop status.",
            "/sales/delivery-routes",
            "Owner, Admin, Sales Staff",
            "Semi-Auto",
            "v1 is sales-order stops only. In transit, do not silently delete a stop — mark it failed or returned."
        ),
        (
            "Sales & POS",
            "Delivery Challan Return",
            "Dispatch / Logistics",
            "Supported (Freeze Pilot)",
            "Return part or all of a completed delivery challan. Stock comes back when the return is completed.",
            "Challan, quantities, reason.",
            "/sales/delivery-challans",
            "Owner, Admin, Warehouse",
            "Rule-based",
            "Return quantity cannot exceed what the challan still has out. Draft returns do not move stock."
        ),
        (
            "Sales & POS",
            "Saved Shipping Addresses",
            "Order Fulfillment",
            "Supported (Freeze Pilot)",
            "A customer can keep more than one ship-to address. Quotation and sales order store a copy of the address chosen on that document.",
            "Address label, lines, city, state, pincode. Per-document snapshot.",
            "/sales/customers | /sales/quotations | /sales/orders",
            "Owner, Admin, Sales Staff",
            "Manual",
            "Later edits to the customer address do not rewrite addresses already copied onto old documents."
        ),
        (
            "Sales & POS",
            "Recurring Document Stop Stage",
            "Billing Automation",
            "Supported (Freeze Pilot)",
            "A recurring template can stop at a draft invoice, a sales order, or a delivery challan. Existing templates stay on invoice. An auto-created challan stays draft until someone completes it.",
            "Stop stage: Invoice, Sales order, or Delivery challan.",
            "/sales/recurring",
            "Owner, Admin",
            "Automated",
            "Stock moves only when the challan or invoice is completed, not when the schedule merely creates a draft."
        ),
        (
            "Sales & POS",
            "Inline Customer on Quotation",
            "Pre-Sales / Estimation",
            "Supported (Freeze Pilot)",
            "If the buyer is not in the customer list, create them from the quotation screen and continue the quote without leaving the page.",
            "Name, phone, GSTIN as on the customer form.",
            "/sales/quotations",
            "Owner, Admin, Sales Staff",
            "Manual",
            "The new customer is a normal master record. The quote still has no stock or ledger effect until it is converted."
        ),
        (
            "Purchasing & AP",
            "Supplier Cheque Payments",
            "Disbursement",
            "Supported (Freeze Pilot)",
            "Pay a supplier by cheque with the same number, bank, date, and clearance states used on customer receipts.",
            "Cheque number, bank, date, image; Pending / Cleared / Bounced.",
            "/purchases/payments",
            "Owner, Admin",
            "Semi-Auto",
            "A pending supplier cheque is not cash out. Clear it before it counts on the day book."
        ),
        (
            "Finance & GL",
            "Day Book",
            "Cash & Bank",
            "Supported (Freeze Pilot)",
            "One company-wide day book of cash and bank movements, shared by Sales reports and Accounting. Cheque rows count only after clearance.",
            "Date. Cash-position totals. Link from expenses and from sales reports.",
            "/reports/day-book",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Pending cheques are listed with a clearance note and are excluded from the cash position."
        ),
        (
            "Finance & GL",
            "Operating Expenses",
            "Cash & Bank",
            "Supported (Freeze Pilot)",
            "Record shop expenses such as fuel or rent against a category, with party name, amount, notes, and an optional attachment. Edit or delete from the list.",
            "Expense categories; date range; attachment.",
            "/accounting/expenses | /reports/day-book",
            "Owner, Admin",
            "Manual",
            "An expense is a company document. It is not a substitute for a posted journal when books need a formal voucher."
        ),
        (
            "Finance & GL",
            "Customer Ledger Tabs",
            "AR / AP Ledgers",
            "Supported (Freeze Pilot)",
            "Open one customer and see ledger tabs for transactions, with payment status and an Excel download. This ledger is sales-side only.",
            "Customer; payment-status filter; Excel export.",
            "/reports/customer-ledger",
            "Owner, Admin, CA/Auditor",
            "Automated",
            "Balances are derived from invoices, receipts, and returns. There is no separate supplier ledger on this page."
        ),
    ]

    RECOMMENDED_FLOWS = {
        "Counter POS Rapid Billing": "Scan or search the item, take cash or UPI, and complete checkout. Print the thermal receipt. If the tender total does not match the server total, reconcile before handing over change.",
        "B2B GST Tax Invoice (Intra-state)": "Pick the customer, add items, confirm CGST and SGST in the tax summary, then Save draft or Complete. Record payment if they pay now. Share or print the PDF.",
        "B2B GST Tax Invoice (Inter-state)": "Set the customer's state outside your state, add items, confirm IGST, then Complete. Use this path for out-of-state GST customers, not for a local cash bill.",
        "Non-GST / Nil-Rated / Exempt Invoices": "Choose a non-GST invoice type, add items, and complete without tax. Use this for exempt or composition-style bills, not for a regular GST sale.",
        "Sales Quotation / Proforma Invoice": "Create the customer if needed, add items and a validity date, save the quote, then convert the accepted quantity to a sales order. Do not treat the quote as stock or as money owed.",
        "Sales Orders & Backorders": "Convert an accepted quote, or create the order directly. Reserve stock if you use reservations, then dispatch with a challan or invoice. Cancel only if nothing has been dispatched.",
        "Delivery Challans / Staged Fulfillment": "Create the challan from the sales order, complete it when the goods leave, then invoice what was delivered. Return leftover goods with a challan return, not by editing the completed challan.",
        "Sales Return & Credit Notes (Auto-CN)": "Open the original invoice from sales history, start a return for the qty that came back, and complete the return. The credit note follows the return. Do not delete the invoice.",
        "Residual Sales Debit Notes": "Raise a debit note against the original invoice for the extra charge, then complete it. Use this for a price increase after the bill, not for a new sale.",
        "Customer Receipts & Bill-by-Bill Allocation": "Take the receipt against the open invoice, allocate it bill by bill, and leave any extra as an advance. Prefer Record payment on the invoice when the customer is paying that one bill.",
        "Customer Pricing Tiers & Volume Slabs": "Assign the customer's price list, then bill as usual. The invoice should pick the slab from quantity. Change the list on the customer, not by retyping every line.",
        "Thermal & A4 Invoice PDF Engine": "Complete the invoice, then Print for A4 or Thermal from the invoice or from sales history. Check the HSN summary on the A4 tax invoice before you send it.",
        "Quick Entry Voucher Mode": "Choose the customer first, add items with the quantity stepper, and save. Use this for a fast repeat order, then open the full invoice if you need tax detail or e-invoice.",
        "Recurring Invoices & Subscriptions": "Set the customer, lines, schedule, and stop stage (invoice, sales order, or challan). Let the schedule create the next draft, then complete that document so stock and tax post.",
        "Atomic Purchase Bill Intake": "Enter the supplier bill with their invoice number, items, and tax, then Complete. Stock and the amount you owe update together. Do not create a separate goods receipt in the pilot.",
        "Purchase Orders (PO)": "Raise the order when stock is low, send it to the supplier, and convert it to a purchase bill when their invoice and the goods arrive.",
        "Purchase Returns & Debit Notes": "Open the purchase bill, return the qty you sent back, and complete the debit note. Stock and the supplier balance both come down.",
        "Supplier Payments & Bill Settlement": "Pay from supplier payments against open bills. Use bank or UPI with a reference, or cheque and clear it later. Allocate the payment to the bills it covers.",
        "Supplier Directory & Dynamic Ledgers": "Keep one supplier master with GSTIN and payment terms. Open their ledger from reports when you need the running balance, and pay from open bills.",
        "Standalone Goods Receipt Note (GRN)": "Use a GRN only when you receive goods before the supplier invoice. The pilot's normal path is still to complete the purchase bill, which receives stock itself.",
        "3-Way Matching Engine": "Match the purchase order, the receipt, and the supplier invoice before you complete the bill. Hold the bill if quantity or rate does not match.",
        "Bill of Entry & Landed Cost Capitalization": "Enter the bill of entry with duty and freight, attach it to the import purchase, and complete so the extra cost sits on the stock value.",
        "Append-Only Typed Stock Movement Engine": "Do not edit stock by hand. Sell, purchase, transfer, count, or adjust so each change is a movement. Check Current stock when the balance looks wrong.",
        "Multi-Godown / Location Tracking": "Pick the godown on the document before you complete it. Review Current stock by warehouse when you sell from more than one location.",
        "Inter-Godown Stock Transfers": "Create the transfer from the source godown to the destination and complete it. Do not adjust both godowns by hand.",
        "Batch & Expiry Date Management (FEFO)": "Receive the batch and expiry on the purchase bill. On sale, let the system pick the earliest expiry. Do not sell an expired batch.",
        "Serial Number & IMEI Tracking": "Capture serials on purchase for the quantity received, and select those serials on the sale. Complete is blocked until the serial count matches the quantity.",
        "Physical Inventory Cycle Counts & Variance Reconciliation": "Count the shelf, enter the count, review the variance, and post the adjustment with a reason. Do not overwrite the on-hand number directly.",
        "Stock Adjustments & Shrinkage Write-offs": "Post an adjustment with a reason after a count or a known loss. Owner approval is the path for shrinkage, not a silent edit.",
        "Barcode & Product Label Printing": "Open label print, add the product, set copies, and print. Generate the barcode on the item first if it does not have one.",
        "Dynamic Low Stock Alerts & Reorder Points": "Set the reorder level on the item. When Action Center flags it, raise a purchase order rather than waiting for a stock-out at the counter.",
        "Stock Valuation Engine": "Complete purchases and sales as usual, then open the stock valuation report. Do not revalue by editing old invoices.",
        "Derived Customer & Supplier Subledgers": "Bill, receive, and return through documents. Read the customer ledger for what they owe. Do not post a manual balance.",
        "Double-Entry General Ledger Backbone": "Turn accounting on, then let invoices, bills, receipts, and payments post the journals. Use a manual journal only for an adjustment the documents cannot express.",
        "Statutory Financial Statements (P&L, Balance Sheet, TB)": "Close the day's documents first, then open trial balance, profit and loss, and balance sheet. Investigate a non-zero trial balance before you file.",
        "Manual Journal Vouchers": "Post a balanced journal for provisions or corrections that have no invoice. Do not use a journal to fake a sale or a purchase.",
        "Accounting Period Close & Reversal Governance": "Finish invoices and bills for the month, review the day book and trial balance, then close the period. Ask the owner to reopen if a late bill must be entered.",
        "Bank Account Master & Cash Till Management": "Set up cash and bank accounts, record receipts and payments against them, and check the day book for the day's position.",
        "Bank Statement Auto-Reconciliation": "Import or enter the statement, match lines to receipts and payments, and leave unmatched items for the owner. Cheque clearance is separate from this match.",
        "Dynamic Payment Links & Hosted Checkout (/pay/:token)": "Create the link from the open invoice and send it to the customer. When the gateway confirms payment, the receipt allocates to that invoice.",
        "Connected Banking / Account Aggregator (AA)": "Connect the bank when you want statement lines pulled in, then reconcile. Do not treat a connected balance as a posted receipt until it is matched.",
        "Cost Centers & Project Accounting": "Pick the cost center on the invoice or bill when the job needs its own margin. Report by cost center after the documents are complete.",
        "Fixed Assets & Depreciation Schedules": "Capitalize the asset from the purchase, then run depreciation in the period. Do not expense the whole asset through Operating expenses if it is a fixed asset.",
        "Automated GST Computation Engine": "Set the company GSTIN and state, keep HSN rates on items, and let the invoice preview show CGST, SGST, or IGST before you complete.",
        "GSTR-1 Preparation & Reconciliation Worksheet": "Complete the month's sales and returns, open GSTR-1, and match it to the sales register before the CA files.",
        "GSTR-3B Summary Calculation Engine": "After GSTR-1 and the purchase register look right, open GSTR-3B and review tax payable versus credit. File from those numbers, not from a spreadsheet copy.",
        "GSTR-2B Automated Inward ITC Match (GST Guard)": "Download 2B for the period, match it to purchase bills, and chase suppliers who are missing before you claim that credit.",
        "NIC E-Invoice Live Integration (IRN & Signed QR)": "Complete the tax invoice, generate the IRN, and print the signed QR. Do not edit lines while an IRN is live.",
        "NIC E-Way Bill Generation & Tracking": "After the invoice or challan is complete, generate the e-way bill with vehicle and distance when the consignment needs one.",
        "TDS (Section 194Q) & TCS (Section 206C(1H)) Withholding": "Turn the section on for the party, complete the bill so tax is withheld, and pay the supplier the net amount. Check the TDS/TCS report before deposit.",
        "Statutory Licences & Compliance Tags": "Store the licence on the company and tag regulated items. Billing should show the licence when the item requires it.",
        "Composition Scheme (CMP-08) Support": "Mark the company as composition, bill without charging GST, and file CMP-08 from the composition report. Do not issue a tax invoice.",
        "Dispatch Staging & Multi-Order Grouping": "Collect today's orders, group them for one vehicle, then build the delivery route. Do not dispatch an order that is still over the credit limit.",
        "Vehicle Capacity Allocation & Load Planning": "Assign orders to a vehicle until weight or volume is full, then sequence the stops. Split the rest onto the next run.",
        "Sequential Route Planning & Stop Sequencing": "Create the route, order the stops, and leave it planned until the vehicle leaves. After it is in transit, update stop status instead of deleting stops.",
        "Delivery Run Manifest & Driver Mobile PWA": "Open the route manifest, follow the stop order, and mark each stop delivered or failed on the spot.",
        "Proof of Delivery (POD) & Instant Cash Capture": "At the shop, hand over the goods, collect cash or cheque if it is due, and mark the stop delivered. Clear cheques later from receipts.",
        "Route Economics & Delivery Profitability Engine": "After the route is done, review cost against the orders on that run. Use it to drop stops that do not pay for the trip, not to edit invoice totals.",
        "Collections Autopilot (Escalating Cadence Engine)": "Let reminders go out on the cadence, then call the accounts that are still open after the urgent step. Record a promise to pay if they commit a date.",
        "Automated Debtor Account Freezes & Credit Holds": "When a customer crosses the hold rule, stop new bills until the owner clears it or they pay. Do not override the hold at the counter without that clearance.",
        "Promise-to-Pay Logging & Follow-up Tracker": "Log the date they promised, follow up that day from the tracker, and take the receipt against the open invoices if they pay.",
        "Action Center ('Today' Priority Triage)": "Start the day on Action Center. Clear low stock, overdue collections, and failed documents before opening new bills.",
        "Inventory Autopilot (Run-Rate Reorder Engine)": "Review the suggested order, adjust quantities, and raise purchase orders for the suppliers you actually buy from.",
        "Supplier Intelligence Scorecard": "Check fill rate and price drift before you place the next order. Shift volume to the supplier who delivers, rather than only the cheapest rate.",
        "Deterministic LLM Bill Extraction (OCR + Parser)": "Upload the supplier bill, review every extracted line, and save as a draft purchase. Complete only after a person has checked rate, tax, and invoice number.",
        "Predictive Cash-Flow & Working Capital Forecaster": "Look at the forecast after receipts and dues are up to date. Chase the invoices it says will miss cash, and delay supplier payments that are not due.",
        "Conversational Business Query Assistant (Natural Language)": "Ask in plain language, open the document it cites, and decide from that document. Do not post a transaction from the answer.",
        "Multi-Tenant Shared Database Architecture": "Each user works inside one company. Do not copy records across companies. Support uses the company switch, not a shared login.",
        "Role-Based Access Control (RBAC)": "Give counter staff sales and POS, the accountant books and reports, and keep owner-only actions on the owner. Hide a screen by role instead of telling people not to click it.",
        "OTP-Based Passwordless Login & Authentication": "Sign in with email and OTP. Use password reset only when OTP is unavailable. Do not share the owner's OTP with the counter.",
        "Guided Setup Wizard & First-Run Checklist": "Finish company, GSTIN, and the first item and customer in the wizard before the first real invoice.",
        "Customer & Vendor Self-Onboarding Magic Portal": "Send the portal link, let them submit details, then review and accept the master before you bill them.",
        "Document Numbering Series & Custom Prefixes": "Set the series once per financial year and GSTIN. Backdated bills take the series for that date. Do not renumber completed documents.",
        "Idempotent Bulk Data Import & Migration Engine": "Download the template, import, fix the rows the preview rejects, and commit once. Do not commit a file that still has errors.",
        "One-Click Tally Historical Migration Engine": "Import masters first, then opening balances and documents. Tie the opening trial balance before you start live billing.",
        "Vernacular & Multi-Language UI (Hindi / Regional)": "Switch language from the header. Keep entering money and GSTIN in the same fields. Use Hindi for the counter if that is what the clerk reads.",
        "Automated Right-to-Erasure & Data Privacy Engine": "Erase the person's name and phone when they ask. Keep the tax invoices and ledger for the statutory period.",
        "Invoice Quick Settings": "On a new invoice, open Settings. Set the industry preset and signature on Invoice details, party fields on Party details, and columns plus the templates link on Item table. Then return to the bill.",
        "Record Invoice Payment with Settlement Discount": "From sales history, Record payment on the open invoice. Enter amount, any settlement discount, the payment date, and the mode. Save. The balance on that invoice should drop by amount plus discount.",
        "Cheque Receipts and Clearance": "Record the receipt or supplier payment as cheque with number, bank, and date. Leave it pending. When the bank clears it, mark Cleared on Receipts or Supplier payments. If it bounces, mark Bounced so the invoice is unpaid again.",
        "Share Invoice": "Open the invoice or its row in sales history, choose Share, and send the PDF by email or WhatsApp. Print is the fallback when they want paper.",
        "HSN-wise Tax Summary on the Invoice": "Complete a GST invoice and print or download the PDF. Read the HSN summary under the lines and confirm it matches the tax total before you send the bill.",
        "Sales History Payment Filters": "Open sales history, set the date preset, then filter Unpaid or Partial. Use that list for collection calls. Open a row to share, return, or record payment.",
        "Expected Margin on the Bill": "Turn on show purchase price in invoice settings, add the items, and read the expected profit before Complete. Change the rate if the margin is too thin.",
        "Delivery Routes": "Create a route, add sales-order stops, set the sequence, and keep it planned until the vehicle leaves. Mark each stop delivered, failed, or returned. Remove a stop only while the route is still planned.",
        "Delivery Challan Return": "Open the completed challan, start a return for the quantity that came back, and complete the return so stock is restored.",
        "Saved Shipping Addresses": "Add ship-to addresses on the customer. On the quotation or sales order, pick the address for that document. Change the master later without rewriting old documents.",
        "Recurring Document Stop Stage": "Edit the recurring template and choose where it should stop. Review the draft it creates and complete it. Do not expect stock to move on a draft challan.",
        "Inline Customer on Quotation": "On the quotation, if the buyer is missing, add them inline, then add items and save. Convert to an order only after they accept.",
        "Supplier Cheque Payments": "Pay the supplier bill by cheque, store the cheque copy, and mark it cleared only when the bank pays. A bounce puts the bill back to unpaid.",
        "Day Book": "Open Day Book for the date. Read cash position from cleared cash and bank only. Use the cheque note to see what is still pending clearance.",
        "Operating Expenses": "Add the expense with category, party, amount, and notes. Attach the bill if you have one. Open Day Book from the expenses page to see it next to other cash movements.",
        "Customer Ledger Tabs": "Open the customer ledger, pick the customer, switch tabs for the transaction view you need, filter by payment status, and download Excel for the CA.",
    }

    start_row = 2
    for r_idx, feat in enumerate(features_data, start_row):
        row = list(feat)
        if len(row) == 10:
            row.append(RECOMMENDED_FLOWS[row[1]])
        for c_idx, val in enumerate(row, 1):
            ws2.cell(row=r_idx, column=c_idx, value=val)
            
    end_row = start_row + len(features_data) - 1
    apply_table_styles(ws2, 1, end_row, 1, len(headers_ws2), status_col_idx=4)
    auto_fit_columns(ws2, max_cols=len(headers_ws2), max_len_cap=55)
    
    print("Sheet 2 built.")

    # =============================================================
    # SHEET 3: END-TO-END WORKFLOWS (MAPPING & STEPS)
    # =============================================================
    ws3 = wb.create_sheet(title="End-to-End Workflows")
    ws3.views.sheetView[0].showGridLines = True
    ws3.freeze_panes = "A2"
    
    headers_ws3 = [
        "Workflow Domain",
        "Workflow Identifier",
        "Step #",
        "Flow Step Name",
        "Primary Actor / Role",
        "Operational Action & System Behavior",
        "Inputs & Required Data",
        "Outputs & Generated Artifacts",
        "System Invariants & Error Checks",
        "Automation Level"
    ]
    
    for c_idx, h in enumerate(headers_ws3, 1):
        ws3.cell(row=1, column=c_idx, value=h)
        
    workflows_data = [
        # Workflow 1: Sales Order to Cash
        ("Sales", "WF-SALES-01", 1, "Customer Order Intake", "Sales Staff / Counter Clerk", "Receives order via walk-in, phone, or WhatsApp. Selects customer master or enters walk-in details. Scans item barcodes or searches SKUs.", "Customer ID, Items, Quantities, Agreed Rates", "Draft Sales Order / Cart Session", "Checks customer credit limit; checks real-time available stock in selected godown.", "Manual / Barcode Scan"),
        ("Sales", "WF-SALES-01", 2, "Price Tier & Discount Validation", "System (Rule Engine)", "Applies customer's assigned price list (Retail/Wholesale) and volume discount slabs. Checks if discount exceeds clerk permission limit.", "Item Base Price, Customer Tier, Quantity", "Calculated Line Subtotals & Discounts", "Rejects discounts greater than role maximum unless Owner override entered.", "Automated"),
        ("Sales", "WF-SALES-01", 3, "Tax Computation & Place of Supply", "Tax Engine", "Evaluates Place of Supply against seller state. Calculates CGST+SGST (intra) or IGST (inter) + cess per line based on item HSN.", "Seller State, Customer State/GSTIN, HSN rates", "Calculated Tax Summary & Document Total", "Ensures round-off matches line-item rounding sum. Validates GSTIN checksum.", "Automated"),
        ("Sales", "WF-SALES-01", 4, "Atomic Document Completion", "System / Ledger Engine", "User clicks 'Complete'. System creates immutable Sales Invoice, decrements warehouse stock, and increments Accounts Receivable.", "Completed Invoice State", "Tax Invoice PDF, StockMovement (SALE_OUTWARD), GL Voucher", "Atomic transaction: stock decrement and AR debit happen simultaneously. TB remains balanced.", "Automated"),
        ("Sales", "WF-SALES-01", 5, "Payment Settlement / UPI QR", "Counter Clerk / Customer", "Customer scans dynamic UPI QR printed on bill or pays cash. Clerk records settlement mode.", "Payment Mode, Amount Received, UPI UTR", "Customer Receipt Voucher, Paid Invoice Status", "Over-allocation blocked. Cash drawer balance updated instantly.", "Semi-Auto / Dynamic QR"),
        ("Sales", "WF-SALES-01", 6, "Post-Sale Returns / Auto-CN", "Owner / Store Manager", "Customer returns defective item with bill reference. System accepts return, restores stock, and generates Credit Note.", "Original Invoice #, Returned Items, Return Reason", "Sales Return Note, Credit Note (Sec 34), StockMovement (RETURN_INWARD)", "Credit note capped at original invoice amount minus prior notes. Links to original invoice for GSTR-1 CDNR.", "Automated"),

        # Workflow 2: Purchase Inward to Vendor Settlement
        ("Purchase", "WF-PURCH-01", 1, "Reorder Alert / PO Requisition", "Store Manager / Owner", "Action Center alerts low stock. Manager reviews recommended order quantities and generates Purchase Order to distributor.", "Product SKUs, Reorder Quantities, Preferred Supplier", "Authorized Purchase Order (PDF)", "Verifies supplier active status and agreed purchase rate.", "Semi-Auto"),
        ("Purchase", "WF-PURCH-01", 2, "Physical Goods Intake (Dock)", "Warehouse Clerk", "Distributor tempo arrives with goods and paper invoice. Warehouse clerk checks cartons, batch numbers, and expiry dates.", "Vendor Paper Bill, Physical Cartons", "Physical Inward Inspection Sheet", "Verifies physical items match batch and expiry dates stated on package.", "Manual"),
        ("Purchase", "WF-PURCH-01", 3, "Purchase Bill Inward Entry", "Accounts Clerk / Manager", "Enters vendor bill number, vendor GSTIN, line items, batch/expiry, and landed transport charges into BizBoard.", "Vendor Invoice # & Date, Items, Taxable Rates, Taxes", "Draft Purchase Invoice", "Validates vendor invoice number uniqueness per vendor to prevent duplicate bill entry.", "Manual / LLM OCR"),
        ("Purchase", "WF-PURCH-01", 4, "Atomic Inward Completion", "System / Ledger Engine", "User completes Purchase Bill. System adds stock to target godown, records AP liability, and computes TDS 194Q if applicable.", "Purchase Invoice State", "StockMovement (PURCHASE_INWARD), AP Ledger Credit, ITC GL Entry", "Atomic commit: inventory and accounts payable updated simultaneously without separate GRN in pilot.", "Automated"),
        ("Purchase", "WF-PURCH-01", 5, "Vendor Payment Disbursement", "Owner / Finance Manager", "Payment run executes on due date via NetBanking or Cheque. User enters UTR and allocates payment to vendor bills.", "Vendor Bank Details, Payment Amount, Cheque/UTR", "Supplier Payment Voucher, Updated Bill Outstanding", "Allocation reduces vendor balance; checks TDS deduction requirement.", "Semi-Auto"),
        ("Purchase", "WF-PURCH-01", 6, "Purchase Return & Debit Note", "Owner / Store Manager", "Damaged goods returned to distributor. System issues statutory Debit Note, reduces AP liability, and reduces stock.", "Original Purchase Bill #, Return Reason, Item Lots", "Debit Note (Sec 34), StockMovement (RETURN_OUTWARD)", "Reduces AP liability; reverses input tax credit in GSTR-3B Table 4(B).", "Automated"),

        # Workflow 3: Inventory Warehouse & Replenishment Loop
        ("Inventory", "WF-INV-01", 1, "Stock Movement Recording", "System", "Every physical receipt, sale, transfer, or adjustment creates an immutable, typed ledger entry.", "Document Type, Item ID, Godown ID, Batch, Qty", "Append-only StockMovement row", "Stock balance = exact sum of movements. Negative balance blocked.", "Automated"),
        ("Inventory", "WF-INV-01", 2, "Inter-Godown Transfer", "Warehouse Manager", "Stock transfer initiated from Central Warehouse to Retail Showroom. Items staged, vehicle assigned, and goods dispatched.", "Source Godown, Target Godown, Item SKUs, Quantities", "Stock Transfer Note, In-Transit Stock State", "Decrements source godown (TRANSFER_OUT) and increments destination (TRANSFER_IN) atomically.", "Automated"),
        ("Inventory", "WF-INV-01", 3, "Physical Cycle Count Session", "Auditor / Warehouse Staff", "Periodic stocktaking audit session. Staff counts physical shelf stock and enters counts into system.", "Godown ID, Counted Quantities per SKU/Batch", "Stock Count Audit Variance Report", "Identifies shrinkage, damage, and unauthorized removals.", "Manual / Barcode Scan"),
        ("Inventory", "WF-INV-01", 4, "Variance Reconciliation & Adjustment", "Owner / Inventory Manager", "Manager reviews count variances. Approves variance write-off to bring system book stock in sync with reality.", "Approved Stock Count Session", "StockMovement (ADJUSTMENT), Stock Loss GL Voucher", "Requires mandatory audit reason; posts offset to P&L Stock Adjustment Expense.", "Rule-based"),
        ("Inventory", "WF-INV-01", 5, "FEFO Batch Expiry Enforcement", "Sales Billing System", "During sales billing of batch-tracked goods, system automatically selects earliest expiring sellable batch.", "Item SKU, Required Quantity", "Assigned Batch Numbers on Invoice Lines", "Strictly blocks picking of expired batches. Alerts if batch expires within 30 days.", "Automated"),

        # Workflow 4: Receivables & Collections Autopilot
        ("Collections", "WF-COLL-01", 1, "Invoice Due Date Monitoring", "System (Background Cron)", "System daily scans all outstanding customer invoices against agreed credit terms (Net 15/30/45).", "Invoice Issue Date, Credit Days, Current Date", "Overdue Invoice Triage Queue", "Evaluates invoice outstanding amount minus unallocated customer receipts.", "Automated"),
        ("Collections", "WF-COLL-01", 2, "Escalating Dunning Dispatch", "Collections Autopilot", "Triggers automated WhatsApp / SMS reminders based on dunning schedule (Polite Day -3, Due Day 0, Urgent Day +7).", "Debtor Mobile, Invoice PDF Link, Dynamic UPI Link", "Dispatched WhatsApp Message with Payment Link", "Personalized message template with verified sender ID; logs dispatch event.", "Automated"),
        ("Collections", "WF-COLL-01", 3, "Customer Digital Settlement", "Debtor (Customer)", "Debtor opens payment link on smartphone, reviews invoice breakdown, and authorizes payment via UPI or NetBanking.", "Customer UPI PIN / Bank Auth", "Gateway Payment Webhook (Cashfree/PayU)", "Secured with tokenized URL; prevents double-payment if already settled.", "Automated"),
        ("Collections", "WF-COLL-01", 4, "Autonomous Receipt & Allocation", "System (Webhook Receiver)", "Gateway webhook verifies signature, creates Customer Receipt voucher, and auto-allocates to invoice.", "Webhook Signature, Transaction ID, Amount", "Customer Receipt, Updated Zero-Balance Invoice", "Idempotent processing: replaying same webhook is a safe no-op. AR subledger updated instantly.", "Automated"),
        ("Collections", "WF-COLL-01", 5, "Credit Lock Escalation", "System (Risk Engine)", "If debtor exceeds maximum overdue grace days (e.g., 30 days past due), system locks account from new billing.", "Customer Account Overdue Status", "Billing Lock Flag on Customer Master", "Blocks sales staff from creating new orders or challans until owner enters override.", "Automated"),

        # Workflow 5: Operations, Dispatch & Route Delivery
        ("Operations", "WF-OPS-01", 1, "Orders Staged for Dispatch", "Warehouse Dispatcher", "Gathers completed invoices and delivery challans scheduled for delivery today.", "Pending Dispatch Documents, Delivery Addresses", "Staged Orders Queue", "Validates payment clearance or credit approval before physical staging.", "Manual / System"),
        ("Operations", "WF-OPS-01", 2, "Geographic Clustering & Loading", "Operations Engine", "Clusters destination delivery addresses by town sector or pincode. Matches aggregate payload against vehicle capacity.", "Order Weight/Volume, Destination Pincodes, Fleet Specs", "Vehicle Assignment & Load Sheet", "Prevents vehicle gross weight overload; flags excess orders.", "Automated"),
        ("Operations", "WF-OPS-01", 3, "Route Sequencing & Stop Manifest", "Routing Engine", "Sequences delivery stops to minimize total travel time and distance. Generates Delivery Run Manifest for driver.", "Delivery Coordinates, Vehicle Speed Profile", "Sequential Route Manifest, Driver Mobile PWA", "Calculates estimated delivery time window per customer.", "Automated"),
        ("Operations", "WF-OPS-01", 4, "Field Delivery & Proof of Handover", "Delivery Driver", "Driver arrives at customer shop, hands over cartons, collects cash/cheque if COD, and captures customer signature or OTP.", "Customer OTP / Digital Signature, COD Cash", "Proof of Delivery (POD) Record", "Validates OTP before releasing COD delivery status.", "Interactive Mobile"),
        ("Operations", "WF-OPS-01", 5, "Route Economics & Margin Audit", "System (Costing Engine)", "System computes total route expense (fuel + driver wage) and attributes cost across fulfilled orders.", "Total Distance Km, Vehicle Running Rate, Order Gross Margins", "Per-Order Route Profitability Report", "Calculates: Net Order Margin = Gross Margin - Attributed Delivery Expense.", "Automated"),

        # Workflow 6: GST Compliance & Inward Reconciliation (GST Guard)
        ("Tax / GST", "WF-GST-01", 1, "Transaction Validation at Source", "Tax Engine", "Validates customer/supplier GSTIN, state code, and HSN tax rate during voucher creation.", "Voucher Header & Lines", "Valid Document Ready for Completion", "Blocks completion if HSN tax rate is invalid or Place of Supply is ambiguous.", "Automated"),
        ("Tax / GST", "WF-GST-01", 2, "E-Invoice (IRN) Generation", "GSP Adapter", "Sends invoice JSON payload to Invoice Registration Portal (IRP). Receives 64-character IRN and signed QR code.", "Invoice Tax Payload", "IRN, Signed QR Code, E-Invoice PDF", "Mandatory for businesses above statutory turnover threshold. Embeds QR on invoice.", "Automated"),
        ("Tax / GST", "WF-GST-01", 3, "E-Way Bill Generation", "GSP / NIC Adapter", "Generates E-Way Bill for consignments >₹50,000. Links vehicle number and transporter ID.", "Invoice Value, Distance Km, Vehicle Reg #", "E-Way Bill Number, Validity Timestamp", "Validates travel distance matches PIN-to-PIN statutory distance tables.", "Automated"),
        ("Tax / GST", "WF-GST-01", 4, "GSTR-2B Automated Inward Sync", "GST Guard Engine", "System connects to GSTN via GSP on 14th of the month. Fetches auto-drafted GSTR-2B inward statement.", "Company GSTIN, Filing Period, GSTN Auth Token", "Downloaded GSTR-2B Inward Register", "Secure API handshake; stores supplier filing snapshot.", "Automated"),
        ("Tax / GST", "WF-GST-01", 5, "Inward 2B vs Purchase Reconcile", "GST Guard Matcher", "Performs fuzzy matching between vendor GSTR-2B entries and recorded purchase invoices.", "Purchase Register, GSTR-2B Inward Data", "ITC Match Report (Matched, Missing in 2B, Missing in Books)", "Identifies unfiled supplier invoices under Section 16(2)(aa).", "Automated"),
        ("Tax / GST", "WF-GST-01", 6, "Supplier Payment Hold & Notice", "GST Guard Engine", "Automatically places Accounts Payable payment hold on suppliers who failed to file GSTR-1. Sends WhatsApp alert.", "Unmatched Vendor Bills", "Payment Hold Flag, Vendor WhatsApp Notice", "Prevents financial loss from claiming disallowed ITC; urges vendor to file.", "Automated"),
        ("Tax / GST", "WF-GST-01", 7, "Month-End GSTR-1 & 3B Filing", "Owner / External CA", "Review aggregated GSTR-1 and GSTR-3B tax worksheets. CA approves numbers; submits return to government portal.", "Monthly Sales & Purchase Registers, ITC Ledger", "Signed GSTR-1 & 3B Returns, Tax Payment Challan", "Reconciles electronic credit ledger with books before cash tax payment.", "Semi-Auto / CA Review"),

        # Recommended daily path for the sales and purchase desk
        ("Sales", "WF-DESK-01", 1, "Start from what is unpaid", "Owner / Sales Staff", "Open sales history, set today or this week, and filter Unpaid or Partial. This is the collection list before any new billing.", "Date preset, payment-status filter", "Short list of open invoices", "A fully returned invoice shows Returned, not Paid.", "Manual"),
        ("Sales", "WF-DESK-01", 2, "Bill the next customer", "Sales Staff", "New invoice. If they are new, add them. Open Settings only when the series, signature, or columns are wrong. Add items and read CGST/SGST or IGST and expected margin.", "Customer, items, place of supply", "Draft tax invoice", "Preview tax must match the footer before Complete.", "Manual"),
        ("Sales", "WF-DESK-01", 3, "Complete, then take money", "Sales Staff", "Complete the invoice. If they pay now, Record payment with amount, settlement discount, date, and mode. Use cheque only with number, bank, and date.", "Amount, mode, cheque details if any", "Completed invoice, receipt", "Discount does not change invoice GST. Pending cheque is not cash.", "Semi-Auto"),
        ("Sales", "WF-DESK-01", 4, "Share the bill and file the paper", "Sales Staff", "Share the PDF by email or WhatsApp, or print A4. Confirm the HSN summary is on the tax invoice.", "Invoice PDF", "Sent or printed bill", "Share uses the invoice PDF, not a separate payment link.", "Semi-Auto"),
        ("Sales", "WF-DESK-01", 5, "Dispatch what is not billed at the counter", "Warehouse", "For orders that leave later, create a challan, put the order on a delivery route, and complete the challan when goods leave. Invoice on delivery. Return leftovers with a challan return.", "Sales order, route, challan", "Challan, route stops, later invoice", "Stock moves on challan complete, not on a planned route.", "Semi-Auto"),
        ("Purchase", "WF-DESK-02", 1, "Bring the supplier bill in", "Accounts Clerk", "Enter the supplier invoice on a new purchase, match items and tax, and Complete so stock and the amount owed update together.", "Supplier bill number, lines, tax", "Completed purchase bill", "Duplicate supplier invoice numbers are rejected.", "Manual"),
        ("Purchase", "WF-DESK-02", 2, "Pay by bank or cheque", "Owner", "Pay open bills from supplier payments. Bank and UPI need a reference. Cheque stays pending until the bank pays, then mark it cleared.", "Amount, mode, cheque or UTR", "Supplier payment", "Pending cheques stay out of the cash position.", "Semi-Auto"),
        ("Purchase", "WF-DESK-02", 3, "Record shop expenses and read the day", "Owner", "Enter fuel, rent, and similar costs on Expenses. Open Day Book for the same date and read cash position from cleared movements only.", "Expense category, amount, attachment", "Expense row, day book", "Day Book is the one cash-and-bank list for sales and accounting.", "Manual"),
        ("Collections", "WF-DESK-03", 1, "Read one customer's story", "Owner / Accountant", "Open the customer ledger, pick the party, switch tabs, and filter by payment status. Download Excel when the CA asks.", "Customer", "Ledger tabs, Excel", "Sales-side ledger only. Balances come from documents.", "Automated"),
        ("Collections", "WF-DESK-03", 2, "Clear or bounce yesterday's cheques", "Owner", "On Receipts and Supplier payments, mark each pending cheque Cleared or Bounced. Then reopen Day Book so the cash position matches the bank.", "Cheque status", "Cleared or bounced receipt", "Bounce makes the invoice unpaid again.", "Manual"),
    ]
    
    start_row = 2
    for r_idx, wf in enumerate(workflows_data, start_row):
        for c_idx, val in enumerate(wf, 1):
            ws3.cell(row=r_idx, column=c_idx, value=val)
            
    end_row = start_row + len(workflows_data) - 1
    apply_table_styles(ws3, 1, end_row, 1, len(headers_ws3), status_col_idx=None)
    auto_fit_columns(ws3, max_cols=len(headers_ws3), max_len_cap=50)
    
    print("Sheet 3 built.")

    # =============================================================
    # SHEET 4: OPTIONS & CONFIGURATION MASTER
    # =============================================================
    ws4 = wb.create_sheet(title="Options & Configuration Master")
    ws4.views.sheetView[0].showGridLines = True
    ws4.freeze_panes = "A2"
    
    headers_ws4 = [
        "Configuration Domain",
        "Setting / Option Name",
        "Config Key / UI Path",
        "Allowed Values / Types",
        "Default Value",
        "Scope & Impact",
        "Detailed Behavioral Description",
        "Dependencies & Pre-requisites"
    ]
    
    for c_idx, h in enumerate(headers_ws4, 1):
        ws4.cell(row=1, column=c_idx, value=h)
        
    config_data = [
        ("General & Company", "Legal Business Name", "company.legal_name", "String (max 255)", "Mandatory on signup", "Company Profile", "Official registered entity name printed on all invoices, reports, and legal documents.", "None"),
        ("General & Company", "Trade Name", "company.trade_name", "String (max 255)", "Optional (defaults to legal name)", "Customer Branding", "Commercial brand name displayed on storefront, POS screen, and customer receipts.", "None"),
        ("General & Company", "Fiscal Year Start Month", "company.fiscal_year_start", "Integer (1 to 12)", "4 (April in India)", "Accounting & Periods", "Defines the 12-month accounting cycle for financial reporting and numbering resets.", "None"),
        ("General & Company", "Base Currency Code", "company.currency", "ISO Currency String (INR, USD, AED, GBP)", "INR", "Global Ledger", "Functional reporting currency for general ledger balance sheet and tax calculations.", "None"),
        ("General & Company", "Decimals in Currency", "company.currency_decimals", "Integer (2 or 3)", "2", "Money Formatting", "Strict decimal scale enforced on all monetary calculations and rounding rules.", "Fixed decimal representation"),

        ("Tax & GST", "Taxation Regime", "company.tax_regime", "Enum: REGULAR_GST, COMPOSITION, UNREGISTERED, OVERSEAS_VAT", "REGULAR_GST", "Tax Engine", "Determines whether tax invoices or bills of supply are issued, and tax rate rules applied.", "Valid GSTIN required for Regular"),
        ("Tax & GST", "Primary GSTIN", "company.gstin", "15-character Alphanumeric Regex", "Mandatory for Regular GST", "Tax Engine & Statutory", "15-digit Goods and Services Tax Identification Number. Validates state code checksum.", "State code matching"),
        ("Tax & GST", "Registered State Code", "company.state_code", "2-digit String ('01' to '38')", "Derived from GSTIN", "Place of Supply", "Determines whether a transaction is Intra-state (CGST+SGST) or Inter-state (IGST).", "Derived from GSTIN prefix"),
        ("Tax & GST", "E-Invoice Enabled", "company.einvoice_enabled", "Boolean (True/False)", "False (Sandbox in pilot)", "E-Invoice API", "Enables real-time generation of IRN and QR code from the invoice completion screen.", "Annual turnover >₹5Cr; GSP credentials"),
        ("Tax & GST", "Default HSN Code Length", "company.hsn_length", "Integer: 4, 6, or 8", "6", "Invoicing & GSTR-1", "Enforces minimum required HSN code digits on product catalog based on turnover threshold.", "None"),
        ("Tax & GST", "TDS 194Q Threshold Tracking", "company.tds_194q_enabled", "Boolean (True/False)", "True", "Purchase Bill AP", "Tracks cumulative supplier purchases exceeding ₹50 lakhs in fiscal year and applies 0.1% TDS.", "Active PAN on supplier master"),
        ("Tax & GST", "TCS 206C(1H) Threshold Tracking", "company.tcs_206c_enabled", "Boolean (True/False)", "True", "Sales Invoice AR", "Tracks cumulative customer sales receipts exceeding ₹50 lakhs in fiscal year and collects 0.1% TCS.", "Active PAN on customer master"),

        ("Sales & Invoicing", "Invoice Numbering Series Prefix", "series.sales_invoice.prefix", "String (e.g., 'INV/26-27/', 'RET-')", "'INV/'", "Sales Documents", "Prefix prepended to contiguous sequential invoice numbers conforming to GST Rule 46.", "None"),
        ("Sales & Invoicing", "Auto Round-Off to Nearest Rupee", "sales.auto_roundoff", "Boolean (True/False)", "True", "Billing & GL", "Rounds net invoice total to nearest whole integer, posting fraction to Round-Off GL account.", "Round-off ledger configured"),
        ("Sales & Invoicing", "Default Customer Payment Terms", "sales.default_credit_days", "Integer (0, 15, 30, 45, 60)", "30 days", "Receivables & Dunning", "Default credit period assigned to new B2B customers for due date calculation.", "None"),
        ("Sales & Invoicing", "Hard Credit Limit Enforcement", "sales.enforce_credit_limit", "Enum: BLOCK_BILLING, WARN_ONLY, DISABLED", "WARN_ONLY", "Sales Orders & Billing", "Prevents issuing invoices or orders to customers who exceed their assigned credit limit.", "Owner override authority"),
        ("Sales & Invoicing", "Invoice PDF Layout Format", "sales.pdf_template", "Enum: A4_CLASSIC, A4_MODERN, THERMAL_2INCH, THERMAL_3INCH", "A4_CLASSIC", "Printing & PDF", "Visual layout style used for downloading, emailing, or printing customer invoices.", "Thermal printer driver for POS"),

        ("Inventory & Warehousing", "Default Inventory Valuation Method", "inventory.valuation_method", "Enum: FIFO, MOVING_WEIGHTED_AVERAGE", "FIFO", "Stock Accounting", "Determines the cost layer consumption sequence when decrementing stock on sales completion.", "Append-only movement ledger"),
        ("Inventory & Warehousing", "Allow Negative Stock", "inventory.allow_negative_stock", "Boolean (True/False)", "False (Strictly Blocked)", "Warehouse Control", "Prevents issuing goods or billing items whose physical stock balance would drop below zero.", "Strict inventory invariant"),
        ("Inventory & Warehousing", "Enforce Batch Numbers", "inventory.enforce_batch", "Boolean (True/False)", "False (Configurable per item)", "Pharma & FMCG", "Makes batch number and expiry date mandatory during purchase inward and sales billing.", "Product lot tracking flag"),
        ("Inventory & Warehousing", "Enforce FEFO Picking", "inventory.enforce_fefo", "Boolean (True/False)", "True", "Stock Dispatch", "Automatically suggests and allocates the earliest expiring available batch on sales orders.", "Batch management enabled"),
        ("Inventory & Warehousing", "Default Godown for Billing", "inventory.default_godown_id", "Foreign Key (Godown)", "Primary Godown", "POS & Sales", "Default storage location debited or credited during rapid billing and counter sales.", "Active Godown master"),

        ("Payments & Gateway", "Payment Gateway Provider", "payments.gateway_provider", "Enum: CASHFREE, PAYU, RAZORPAY, NONE", "CASHFREE", "Online Collections", "Payment aggregator rails used for generating dynamic payment links and webhooks.", "Merchant API keys & secrets"),
        ("Payments & Gateway", "Enable Dynamic UPI QR on PDF", "payments.upi_qr_on_pdf", "Boolean (True/False)", "True", "Printed Invoices", "Embeds NPCI-compliant dynamic UPI QR code on printed A4 and thermal invoices for instant scan.", "Company UPI VPA configured"),
        ("Payments & Gateway", "Auto-Allocate Webhook Receipts", "payments.auto_allocate_receipts", "Boolean (True/False)", "True", "Settlement", "Automatically creates customer receipt and allocates payment to invoice upon webhook confirmation.", "Active payment gateway webhook"),

        ("Automation & AI", "Collections Autopilot Enabled", "autopilot.collections_enabled", "Boolean (True/False)", "True", "Receivables Management", "Enables scheduled background dunning sequences via WhatsApp and SMS.", "WhatsApp Cloud API integration"),
        ("Automation & AI", "WhatsApp Dunning Channel", "comms.whatsapp_channel", "Enum: CLOUD_API, SHARE_LINK_ONLY", "SHARE_LINK_ONLY (Pilot)", "Customer Comms", "Determines whether WhatsApp messages are sent via automated background API or manual tap.", "Meta Business Manager account"),
        ("Automation & AI", "GST Guard 2B Inward Matching", "autopilot.gst_guard_enabled", "Boolean (True/False)", "False (Horizon 2)", "Input Tax Credit", "Runs automated background reconciliation against GSTR-2B and flags supplier defaults.", "GSP API connectivity"),
        ("Automation & AI", "LLM Invoice Extraction", "ai.bill_ocr_enabled", "Boolean (True/False)", "False (Horizon 2)", "Purchase Intake", "Enables camera photo or PDF bill parsing into structured draft purchase invoices.", "LLM Vision API keys")
    ]
    
    start_row = 2
    for r_idx, cfg in enumerate(config_data, start_row):
        for c_idx, val in enumerate(cfg, 1):
            ws4.cell(row=r_idx, column=c_idx, value=val)
            
    end_row = start_row + len(config_data) - 1
    apply_table_styles(ws4, 1, end_row, 1, len(headers_ws4), status_col_idx=None)
    auto_fit_columns(ws4, max_cols=len(headers_ws4), max_len_cap=45)
    
    print("Sheet 4 built.")

    # =============================================================
    # SHEET 5: ROLE PERMISSION MATRIX (RBAC)
    # =============================================================
    ws5 = wb.create_sheet(title="Role Permission Matrix")
    ws5.views.sheetView[0].showGridLines = True
    ws5.freeze_panes = "A2"
    
    headers_ws5 = [
        "Module / Feature Area",
        "Granular Action / Capability",
        "Owner / SuperAdmin",
        "Business Admin / Manager",
        "Sales Staff / Billing Clerk",
        "Warehouse / Logistics Clerk",
        "External CA / Tax Auditor",
        "Delivery Driver (Mobile PWA)"
    ]
    
    for c_idx, h in enumerate(headers_ws5, 1):
        ws5.cell(row=1, column=c_idx, value=h)
        
    rbac_data = [
        ("Sales & POS", "Create & Complete Retail POS Sale", "Full Access", "Full Access", "Full Access", "No Access", "Read Only", "No Access"),
        ("Sales & POS", "Create & Complete B2B Tax Invoice", "Full Access", "Full Access", "Full Access", "No Access", "Read Only", "No Access"),
        ("Sales & POS", "Apply Custom Line-Item Discounts", "Unrestricted", "Up to 15%", "Up to 5%", "No Access", "No Access", "No Access"),
        ("Sales & POS", "View Item Purchase Cost / Gross Margin", "Full Access", "Full Access", "Hidden (Masked)", "No Access", "Full Access", "No Access"),
        ("Sales & POS", "Amend / Cancel Completed Invoice", "Full Access (Audit Trail)", "Require Owner Approval", "No Access", "No Access", "No Access", "No Access"),
        ("Sales & POS", "Issue Sales Return & Credit Note", "Full Access", "Full Access", "Create Draft Only", "No Access", "Read Only", "No Access"),
        ("Sales & POS", "Override Customer Credit Limit Lock", "Full Access", "No Access", "No Access", "No Access", "No Access", "No Access"),
        
        ("Purchases & AP", "Create & Approve Purchase Orders", "Full Access", "Full Access", "No Access", "Create Requisition", "Read Only", "No Access"),
        ("Purchases & AP", "Complete Purchase Bill (Stock + AP)", "Full Access", "Full Access", "No Access", "Goods Receipt Only", "Read Only", "No Access"),
        ("Purchases & AP", "Issue Supplier Payment Disbursement", "Full Access", "Create Draft Only", "No Access", "No Access", "Read Only", "No Access"),
        ("Purchases & AP", "View Supplier Purchase Price History", "Full Access", "Full Access", "No Access", "No Access", "Full Access", "No Access"),
        ("Purchases & AP", "Process Purchase Return & Debit Note", "Full Access", "Full Access", "No Access", "Create Draft Only", "Read Only", "No Access"),

        ("Inventory & Stock", "View Warehouse Stock Balances", "Full Access", "Full Access", "Assigned Store Only", "Full Access", "Full Access", "No Access"),
        ("Inventory & Stock", "Initiate Inter-Godown Transfer", "Full Access", "Full Access", "No Access", "Full Access", "Read Only", "No Access"),
        ("Inventory & Stock", "Approve Stock Count & Write-offs", "Full Access", "Require Owner Approval", "No Access", "Count Entry Only", "Read Only", "No Access"),
        ("Inventory & Stock", "Override Negative Stock Lock", "No (Strict Invariant)", "No (Strict Invariant)", "No (Strict Invariant)", "No (Strict Invariant)", "No Access", "No Access"),
        ("Inventory & Stock", "Print Product Barcode Labels", "Full Access", "Full Access", "Full Access", "Full Access", "No Access", "No Access"),

        ("Finance & Accounting", "View Financial Statements (P&L, BS)", "Full Access", "Summary Only", "No Access", "No Access", "Full Access", "No Access"),
        ("Finance & Accounting", "Create Manual Journal Vouchers", "Full Access", "No Access", "No Access", "No Access", "Full Access", "No Access"),
        ("Finance & Accounting", "Perform Bank Account Reconciliation", "Full Access", "Full Access", "No Access", "No Access", "Full Access", "No Access"),
        ("Finance & Accounting", "Close / Reopen Accounting Period", "Full Access", "No Access", "No Access", "No Access", "Full Access", "No Access"),
        ("Finance & Accounting", "View Customer & Supplier Ledgers", "Full Access", "Full Access", "Assigned Accounts Only", "No Access", "Full Access", "No Access"),

        ("Taxation & GST", "Generate Live E-Invoice (IRN) / E-Way", "Full Access", "Full Access", "Full Access", "E-Way Only", "Full Access", "No Access"),
        ("Taxation & GST", "Export GSTR-1, 3B Audit Worksheets", "Full Access", "Full Access", "No Access", "No Access", "Full Access", "No Access"),
        ("Taxation & GST", "Configure Company GSTIN & Tax Settings", "Full Access", "No Access", "No Access", "No Access", "Consultative", "No Access"),
        ("Taxation & GST", "Run GSTR-2B Inward ITC Reconciliation", "Full Access", "Full Access", "No Access", "No Access", "Full Access", "No Access"),

        ("Operations & Fleet", "Plan & Batch Delivery Dispatches", "Full Access", "Full Access", "No Access", "Full Access", "No Access", "No Access"),
        ("Operations & Fleet", "Access Driver Mobile Manifest & POD", "Full Access", "Full Access", "No Access", "Full Access", "No Access", "Assigned Run Only"),
        ("Operations & Fleet", "Collect Cash on Delivery (COD)", "Full Access", "Full Access", "Full Access", "No Access", "No Access", "Collect & Record"),
        ("Operations & Fleet", "View Route Economics & Order Profit", "Full Access", "Full Access", "No Access", "No Access", "No Access", "No Access"),

        ("Platform & Settings", "Invite & Manage Company Users", "Full Access", "No Access", "No Access", "No Access", "No Access", "No Access"),
        ("Platform & Settings", "Configure Payment Gateway Webhooks", "Full Access", "No Access", "No Access", "No Access", "No Access", "No Access"),
        ("Platform & Settings", "Trigger Bulk Data Imports & Exports", "Full Access", "Full Access", "No Access", "No Access", "Export Only", "No Access"),
        ("Platform & Settings", "Right-to-Erasure Privacy Execution", "Full Access", "No Access", "No Access", "No Access", "No Access", "No Access")
    ]
    
    start_row = 2
    for r_idx, rbac in enumerate(rbac_data, start_row):
        for c_idx, val in enumerate(rbac, 1):
            ws5.cell(row=r_idx, column=c_idx, value=val)
            
    end_row = start_row + len(rbac_data) - 1
    apply_table_styles(ws5, 1, end_row, 1, len(headers_ws5), status_col_idx=None)
    auto_fit_columns(ws5, max_cols=len(headers_ws5), max_len_cap=35)
    
    print("Sheet 5 built.")

    # =============================================================
    # SHEET 6: FEATURE FLAGS & ENVIRONMENT PROFILES
    # =============================================================
    ws6 = wb.create_sheet(title="Feature Flags & Profiles")
    ws6.views.sheetView[0].showGridLines = True
    ws6.freeze_panes = "A2"
    
    headers_ws6 = [
        "Flag Name (Backend / Frontend)",
        "Component",
        "Frozen Pilot Default",
        "Target Production Value",
        "Scope Disposition",
        "Purpose & Architectural Function",
        "Verification & Gate Checks"
    ]
    
    for c_idx, h in enumerate(headers_ws6, 1):
        ws6.cell(row=1, column=c_idx, value=h)
        
    flags_data = [
        ("ENABLE_SETUP_WIZARD / VITE_ENABLE_SETUP_WIZARD", "Fullstack", "1 / true", "1 / true", "Supported (Freeze Pilot)", "Enables guided 4-step first-run onboarding wizard for new user registrations.", "e2e-golden golden journey"),
        ("ENABLE_GSTR / VITE_ENABLE_GSTR", "Fullstack", "0 / false", "1 / true (Horizon 1)", "Not Supported (Out of Freeze)", "Gates on-screen GSTR report filing screens; offline worksheets remain accessible.", "Phase 2 route block test"),
        ("ENABLE_GSTN_JSON", "Backend", "0", "1 (Horizon 1)", "Not Supported (Out of Freeze)", "Gates direct GSTN-compliant JSON export for portal upload.", "API 404 assertion"),
        ("GSP_LIVE_ENABLED", "Backend", "0", "1 (Horizon 1)", "Not Supported (Out of Freeze)", "Gates direct live HTTP connection to NIC/IRP servers via certified GSP pipes.", "Fail-closed mock check"),
        ("VITE_ENABLE_EINVOICE_SUBMIT", "Frontend", "false", "true (Horizon 1)", "Not Supported (Out of Freeze)", "Disables live submit button on UI; prevents merchants assuming sandbox is live filing.", "UI element absent test"),
        ("ENABLE_AI / VITE_ENABLE_AI", "Fullstack", "0 / false", "1 / true (Horizon 2)", "Not Supported (Out of Freeze)", "Gates AI insights, conversational assistant, and experimental LLM chat surfaces.", "Route 404 / Nav hidden"),
        ("ENABLE_TALLY / VITE_ENABLE_TALLY", "Fullstack", "0 / false", "1 / true (Horizon 1)", "Not Supported (Out of Freeze)", "Gates direct live Tally ODBC/XML sync engine; manual CSV dump available.", "Nav menu hidden test"),
        ("ENABLE_MANUFACTURING", "Backend", "0", "0 (Dark Module)", "Dark Module", "Disables Bill of Materials (BOM) and Work Order manufacturing module.", "Route 404 test"),
        ("ENABLE_PAYROLL", "Backend", "0", "0 (Dark Module)", "Dark Module", "Disables statutory payroll, salary slips, and attendance management module.", "Route 404 test"),
        ("ENABLE_CRM", "Backend", "0", "0 (Dark Module)", "Dark Module", "Disables CRM lead pipelines, deal tracking, and opportunity scoring module.", "Route 404 test"),
        ("ENABLE_FIXED_ASSETS", "Backend", "0", "1 (Horizon 3)", "Known Limitation", "Gates automated fixed asset depreciation schedules; manual journals used as workaround.", "Route 404 test"),
        ("ENABLE_BOE", "Backend", "0", "1 (Horizon 3)", "Known Limitation", "Gates Bill of Entry and import landed cost duty capitalization engine.", "Route 404 test"),
        ("ENABLE_WHATSAPP_CLOUD", "Backend", "0", "1 (Horizon 1)", "Known Limitation", "Gates automated background WhatsApp Cloud API; share-link dunning used in pilot.", "API mock test"),
        ("ENABLE_TELEGRAM", "Backend", "0", "0 (Deprioritized)", "Not Supported", "Gates opt-in staff notification alerts via Telegram bot.", "Disabled in freeze"),
        ("ENABLE_ACCOUNT_AGGREGATOR", "Backend", "0", "1 (Horizon 2)", "Not Supported (Out of Freeze)", "Gates RBI Account Aggregator banking consent and automated bank statement fetch.", "API 404 assertion"),
        ("ENABLE_COMPOSITION", "Backend", "0", "0 (Deprioritized)", "Known Limitation", "Gates GST Composition scheme CMP-08 filing; regular GST prioritized commercially.", "Route 404 test"),
        ("VITE_PILOT_ADVANCED", "Frontend", "false", "false", "Safety Guard", "Development toggle to force-show experimental/preview modules in local demos.", "Refused in prod build"),
        ("VITE_USE_MOCKS", "Frontend", "false", "false", "Development Only", "Enables client-side mock API responses for isolated UI testing without backend.", "Production build fails if true")
    ]
    
    start_row = 2
    for r_idx, flg in enumerate(flags_data, start_row):
        for c_idx, val in enumerate(flg, 1):
            ws6.cell(row=r_idx, column=c_idx, value=val)
            
    end_row = start_row + len(flags_data) - 1
    apply_table_styles(ws6, 1, end_row, 1, len(headers_ws6), status_col_idx=5)
    auto_fit_columns(ws6, max_cols=len(headers_ws6), max_len_cap=45)
    
    print("Sheet 6 built.")

    # =============================================================
    # SHEET 7: STRATEGIC DIFFERENTIATORS & OPERATING SYSTEM
    # =============================================================
    ws7 = wb.create_sheet(title="Strategic Differentiators (OS)")
    ws7.views.sheetView[0].showGridLines = True
    ws7.freeze_panes = "A2"
    
    headers_ws7 = [
        "Focus Area #",
        "Strategic Capability Name",
        "Target Archetype & User Problem",
        "How Incumbents Fail / Gap",
        "BizBoard Closed-Loop Solution",
        "Copy Difficulty & Moat Source",
        "Data Asset Created",
        "Implementation Horizon & Roadmap"
    ]
    
    for c_idx, h in enumerate(headers_ws7, 1):
        ws7.cell(row=1, column=c_idx, value=h)
        
    diff_data = [
        (
            "Focus 1",
            "Action Center / Today Triage",
            "SMB Owners: Overwhelmed by administrative chaos; don't know what operational emergency to tackle first.",
            "Tally/BUSY have no task concept. Zoho shows static vanity charts (e.g. monthly sales) that provide zero operational guidance.",
            "Unified morning triage screen aggregating: overdue invoices to chase, stockouts to reorder, delinquent suppliers, and delivery dispatches.",
            "Moderate | Cross-module event architecture",
            "Owner daily action priorities, task completion velocity.",
            "Horizon 1 (Pilot Hardening & Polish)"
        ),
        (
            "Focus 2",
            "Collections Autopilot",
            "B2B Wholesalers: 30-40% of capital trapped in overdue credit; manual WhatsApp chasing takes 2-3 hours daily.",
            "Desktop tools print paper aging reports. CredFlow charges ₹20k/yr as an add-on. Vyapar requires manual tap-to-send per invoice.",
            "Autonomous multi-channel dunning engine with escalating cadences, embedded dynamic UPI payment links, and automated debtor credit locks.",
            "Difficult | Financial webhook rails & dunning state machine",
            "Proprietary debtor payment behavior graph (who pays on time, who delays).",
            "Horizon 2 (Near-Term Core Differentiator)"
        ),
        (
            "Focus 3",
            "Inventory Autopilot",
            "Stockists & Distributors: Balancing stockouts of fast movers against cash tied up in dead stock.",
            "Static reorder levels in Tally/BUSY ignore supplier replenishment lead times and seasonal sales velocity.",
            "Dynamically computes safety margins based on actual run-rate velocity and auto-generates ready-to-approve POs to distributors.",
            "Difficult | Statistical run-rate modeling",
            "SKU velocity patterns, replenishment lead-time reliability.",
            "Horizon 2 (Near-Term Differentiation)"
        ),
        (
            "Focus 4",
            "GST Guard & 2B Matching",
            "Indian B2B Traders: Loss of Input Tax Credit (ITC) and tax penalties because suppliers fail to file GSTR-1 returns.",
            "ClearTax reports errors after the fact. Accounting desktop software dumps the problem on external CAs at year-end.",
            "Continuous background GSTR-2B sync that automatically places an Accounts Payable payment hold on delinquent vendors until returns reflect.",
            "Difficult | Certified GSP infrastructure + subledger locks",
            "Vendor statutory compliance reliability rating.",
            "Horizon 2 (India Pack Defensive Moat)"
        ),
        (
            "Focus 5",
            "Automated Bank Reconciliation",
            "High-Volume Merchants: Matching hundreds of UPI and NEFT settlements against open invoices takes hours of manual work.",
            "Desktop tools require manual voucher-by-voucher ticking. High error rates and unreconciled suspense accounts.",
            "Multi-source auto-matching engine linking dynamic payment gateway tokens, bank statement UTR numbers, and partial payments.",
            "Difficult | Banking rails / Account Aggregator API",
            "Cash flow velocity, banking clearing lag benchmarks.",
            "Horizon 2 (FinTech Parity & Scale)"
        ),
        (
            "Focus 6",
            "Supplier Intelligence Scorecard",
            "Traders & Wholesalers: Distributors vary widely in fulfillment accuracy and price creep, but owners rely on gut feel.",
            "Basic purchase reports by vendor; zero comparative scoring across multiple suppliers of identical goods.",
            "Ranks suppliers objectively across 4 dimensions: On-time fulfillment rate, Fill-rate accuracy, Price inflation creep, and GSTR-2B compliance.",
            "Difficult | Multi-document historical analytics",
            "Industry supplier performance and price competitiveness benchmark.",
            "Horizon 2 (High Strategic Value)"
        ),
        (
            "Focus 7",
            "Customer / Vendor Self-Onboarding",
            "Growing B2B Traders: Onboarding new trade accounts requires chasing GST certificates, bank details, and addresses via WhatsApp images.",
            "Accountants manually re-type details into software, causing typos in legal names, bank IFSC, or GSTIN.",
            "One-click magic link sent to counterparty: partner fills profile in 60 seconds with automated company auto-fetch from GSTIN registry.",
            "Moderate | Viral loop mechanics",
            "Verified B2B partner network directory.",
            "Horizon 2 (Viral Acquisition Loop)"
        ),
        (
            "Focus 8",
            "Tally Historical Migration Engine",
            "Prospective Switchers: Fear of losing 5 years of historical accounting data and ledger history keeps merchants trapped on Tally.",
            "Clunky CSV import templates that fail on format mismatches and require days of paid CA consulting.",
            "Intelligent XML/ODBC parser that imports Tally masters, Opening Balances, and historical vouchers with automated reconciliation verification.",
            "Moderate to Difficult | Deep Tally schema mastery",
            "Chart of Accounts mapping heuristics.",
            "Horizon 1 (Sales Funnel Unblocker)"
        ),
        (
            "Focus 9",
            "Multi-Order Delivery Planning",
            "Wholesalers & Distributors: Dispatching 20 orders daily across multiple towns is managed on scrap paper with zero load coordination.",
            "Non-existent in SMB accounting tools. Handled by paper run-sheets or pure driver discretion.",
            "One-click order clustering by pincode/zone, vehicle payload matching (weight/volume), and sequential stop run manifest generation.",
            "Difficult | Spatial optimization algorithms",
            "Local delivery route density and stop-duration logs.",
            "Horizon 2 (Major White Space)"
        ),
        (
            "Focus 10",
            "Route Economics & Delivery Margin",
            "B2B Traders offering free local delivery: Absorbing delivery costs blindly erodes gross margins on small-ticket orders.",
            "Complete blind spot across all accounting competitors (Tally, Zoho Books, Vyapar, Marg).",
            "Calculates true net order profitability by attributing vehicle fuel, maintenance, and driver wage costs to each fulfilled order.",
            "Difficult | Linking fleet operational costs to sales lines",
            "True delivery cost per km and minimum profitable order size per zone.",
            "Horizon 3 (Flagship Differentiator)"
        ),
        (
            "Focus 11",
            "Cross-Module Event Workflows",
            "SMBs with 3-15 staff: Departmental silos between billing, warehouse pickers, finance, and delivery drivers cause lost orders.",
            "Desktop tools share one single login; cloud suites (Zoho) require complex custom webhook scripting between separate apps.",
            "Built-in event state machine: Order Approved -> Stock Reserved -> Pick List -> Dispatch -> Delivery -> Invoice -> Payment.",
            "Moderate | Core architectural event model",
            "Operational process cycle time benchmarks.",
            "Horizon 1 (Core Architecture)"
        ),
        (
            "Focus 12",
            "AI Business Assistant (Natural Language)",
            "Mobile Owners: Navigating 4 screens and 3 dropdowns to answer simple operational questions while away from the shop.",
            "Keyword bots (Zoho Zia) that fail on complex queries; generic ChatGPT wrappers that hallucinate financial numbers.",
            "Secure natural-language interface translating English/Hindi voice/text into validated read-only SQL queries with source document links.",
            "Difficult | Deterministic Text-to-SQL + Security",
            "Semantic business query vocabulary and intent logs.",
            "Horizon 3 (Intelligence Layer)"
        ),
        (
            "Focus 13",
            "Automated Business Recommendations",
            "SMB Owners acting as their own CFO: Lack formal business training to detect working capital traps before cash runs out.",
            "Static historical reports. Software tells you what happened, never what you should do next.",
            "Proactive recommendations: flagging customer credit concentration risks, dead-stock capital recovery discounts, and supplier price creep.",
            "Very Difficult | Proprietary business heuristics",
            "Multi-dimensional business optimization decision rules.",
            "Horizon 3 (The Ultimate Product Moat)"
        )
    ]
    
    start_row = 2
    for r_idx, d in enumerate(diff_data, start_row):
        for c_idx, val in enumerate(d, 1):
            ws7.cell(row=r_idx, column=c_idx, value=val)
            
    end_row = start_row + len(diff_data) - 1
    apply_table_styles(ws7, 1, end_row, 1, len(headers_ws7), status_col_idx=None)
    auto_fit_columns(ws7, max_cols=len(headers_ws7), max_len_cap=50)
    
    print("Sheet 7 built.")

    # -------------------------------------------------------------
    # Save Workbook
    # -------------------------------------------------------------
    output_path = r"e:\Bizboard\BizBoard_Features_Flows_Options_Master.xlsx"
    wb.save(output_path)
    print(f"Workbook successfully saved to: {output_path}")

if __name__ == "__main__":
    build_excel()

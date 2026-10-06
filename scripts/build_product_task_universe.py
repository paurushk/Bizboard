# -*- coding: utf-8 -*-
"""
BizBoard Comprehensive Product Task Universe Master Workbook Builder (Expanded with Growth OS)
Produces an enterprise-grade, 9-sheet Excel workbook and flat CSV:
- Bizboard_Product_Task_Universe_Master.xlsx
- Bizboard_Product_Task_Universe_Master.csv
Combines:
- 560 Existing Enhanced Tasks (P-0001 to P-0512, X-0189 to X-0560)
- 155 Strategic Tasks (S, UX, C, SEC, R, I, SaaS, D, X)
- 25 Growth OS Tasks (GOS-0716 to GOS-0740)
Total: 740 Comprehensive Tasks
"""

import csv
import sys
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.abspath('.'))

from scripts.tasks_expansion_data import NEW_STRATEGIC_TASKS
from scripts.growth_os_tasks_data import GROWTH_OS_TASKS

def create_styled_task_sheet(ws, sheet_title, rows, headers, header_color="1F497D"):
    ws.title = sheet_title
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color=header_color, end_color=header_color, fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    data_font_bold = Font(name="Segoe UI", size=10, bold=True)
    border_thin = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    # Priority colors
    p_fills = {
        "P0": (PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="C62828")),
        "P1": (PatternFill(start_color="FFF8E1", end_color="FFF8E1", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="F57F17")),
        "P2": (PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="2E7D32")),
        "P3": (PatternFill(start_color="EDE7F6", end_color="EDE7F6", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="512DA8")),
    }

    # Type colors
    type_fills = {
        "P": (PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="1565C0")),
        "X": (PatternFill(start_color="F3E5F5", end_color="F3E5F5", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="6A1B9A")),
        "S": (PatternFill(start_color="ECEFF1", end_color="ECEFF1", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="37474F")),
        "UX": (PatternFill(start_color="E0F7FA", end_color="E0F7FA", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="006064")),
        "C": (PatternFill(start_color="FBE9E7", end_color="FBE9E7", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="BF360C")),
        "SEC": (PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="B71C1C")),
        "R": (PatternFill(start_color="E8EAF6", end_color="E8EAF6", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="1A237E")),
        "I": (PatternFill(start_color="E0F2F1", end_color="E0F2F1", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="004D40")),
        "SaaS": (PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="E65100")),
        "D": (PatternFill(start_color="F9FBE7", end_color="F9FBE7", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="827717")),
        "G-OS": (PatternFill(start_color="E1F5FE", end_color="E1F5FE", fill_type="solid"), Font(name="Segoe UI", size=10, bold=True, color="0277BD")),
    }

    status_fill = PatternFill(start_color="F1F8E9", end_color="F1F8E9", fill_type="solid")
    status_font = Font(name="Segoe UI", size=10, bold=True, color="33691E")

    ws.append(headers)
    ws.row_dimensions[1].height = 28
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_num in [1, 2, 10, 11] else "left", vertical="center", wrap_text=True)

    for r_idx, r in enumerate(rows, start=2):
        ws.append(r)
        ws.row_dimensions[r_idx].height = 22

        for c_idx in range(1, len(r) + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center", wrap_text=True)

            if c_idx == 1: # Task ID
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = data_font_bold
            elif c_idx == 2: # Task Type
                cell.alignment = Alignment(horizontal="center", vertical="center")
                val = str(cell.value).strip()
                if val in type_fills:
                    cell.fill, cell.font = type_fills[val]
                else:
                    cell.font = data_font_bold
            elif c_idx == 10: # Priority
                cell.alignment = Alignment(horizontal="center", vertical="center")
                val = str(cell.value).strip()
                if val in p_fills:
                    cell.fill, cell.font = p_fills[val]
            elif c_idx == 11: # Validation Status
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.fill = status_fill
                cell.font = status_font

    col_widths = {
        1: 12,  # Task ID
        2: 12,  # Task Type
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


def main():
    print("Starting Product Task Universe Master Generation (Expanded with Growth OS)...")

    enhanced_csv = "Bizboard_Master_Task_Register_Enhanced.csv"
    if not os.path.exists(enhanced_csv):
        print(f"Error: {enhanced_csv} not found!")
        sys.exit(1)

    with open(enhanced_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        existing_560_rows = list(reader)[:560]

    print(f"Loaded {len(existing_560_rows)} baseline enhanced tasks.")

    new_155_rows = [list(item) for item in NEW_STRATEGIC_TASKS]
    print(f"Loaded {len(new_155_rows)} new strategic expansion tasks.")

    growth_os_25_rows = [list(item) for item in GROWTH_OS_TASKS]
    print(f"Loaded {len(growth_os_25_rows)} Growth OS expansion tasks.")

    # Refine priorities across all tasks
    from scripts.rebalance_priorities import refine_task_priority
    for r in existing_560_rows:
        r[9] = refine_task_priority(r)
    for r in new_155_rows:
        r[9] = refine_task_priority(r)
    for r in growth_os_25_rows:
        r[9] = refine_task_priority(r)

    combined_740_rows = existing_560_rows + new_155_rows + growth_os_25_rows
    print(f"Total combined tasks in universe: {len(combined_740_rows)}")
    assert len(combined_740_rows) == 740, f"Expected 740 rows, got {len(combined_740_rows)}"

    # Check for empty cells or 'Not Started'
    empty_cells = 0
    not_started_cells = 0
    for r_idx, r in enumerate(combined_740_rows):
        for c_idx, val in enumerate(r):
            if val is None or str(val).strip() == "":
                print(f"Empty cell at row {r_idx+1}, col {headers[c_idx]}: ID={r[0]}")
                empty_cells += 1
            if str(val).strip().lower() == "not started":
                print(f"'Not Started' at row {r_idx+1}, col {headers[c_idx]}: ID={r[0]}")
                not_started_cells += 1

    print(f"Verification Results -> Empty cells: {empty_cells}, 'Not Started' cells: {not_started_cells}")
    if empty_cells > 0 or not_started_cells > 0:
        raise ValueError("Universe contains incomplete data!")

    # Export flat master CSV
    master_csv = "Bizboard_Product_Task_Universe_Master.csv"
    with open(master_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(combined_740_rows)
    print(f"Saved Master CSV: {master_csv}")

    # Build Master Excel Workbook with 9 comprehensive sheets
    master_xlsx = "Bizboard_Product_Task_Universe_Master.xlsx"
    wb = openpyxl.Workbook()

    # Styling constants
    header_fill_navy = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_fill_slate = PatternFill(start_color="37474F", end_color="37474F", fill_type="solid")
    header_fill_teal = PatternFill(start_color="006064", end_color="006064", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    data_font_bold = Font(name="Segoe UI", size=10, bold=True)
    title_font = Font(name="Segoe UI", size=15, bold=True, color="1F497D")
    border_thin = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    # -------------------------------------------------------------------------
    # Sheet 1: Expanded Task Universe (Master - 740 Tasks)
    # -------------------------------------------------------------------------
    ws_expanded = wb.active
    create_styled_task_sheet(ws_expanded, "Expanded Task Universe", combined_740_rows, headers, "1F497D")

    # -------------------------------------------------------------------------
    # Sheet 2: Coverage Dashboard
    # -------------------------------------------------------------------------
    ws_dash = wb.create_sheet(title="Coverage Dashboard")
    ws_dash.views.sheetView[0].showGridLines = True
    ws_dash["A1"] = "BizBoard Product Task Universe — Executive Coverage Dashboard"
    ws_dash["A1"].font = title_font
    ws_dash.row_dimensions[1].height = 32

    # High-level Metrics Table
    ws_dash["A3"] = "Key Dimension"
    ws_dash["B3"] = "Total Count"
    ws_dash["A3"].font = header_font
    ws_dash["A3"].fill = header_fill_navy
    ws_dash["B3"].font = header_font
    ws_dash["B3"].fill = header_fill_navy
    ws_dash["B3"].alignment = Alignment(horizontal="center")

    p0_count = sum(1 for r in combined_740_rows if r[9] == "P0")
    p1_count = sum(1 for r in combined_740_rows if r[9] == "P1")
    p2_count = sum(1 for r in combined_740_rows if r[9] == "P2")
    p3_count = sum(1 for r in combined_740_rows if r[9] == "P3")

    summary_metrics = [
        ("Total Product Task Universe", len(combined_740_rows)),
        ("Baseline Enhanced Tasks (P & X)", len(existing_560_rows)),
        ("Strategic Expansion Tasks (S, UX, C, SEC, R, I, SaaS, D, X)", len(new_155_rows)),
        ("Growth OS Engine Tasks (G-OS)", len(growth_os_25_rows)),
        ("Total Operational Personas / Scopes", len(set(r[2] for r in combined_740_rows))),
        ("Total Functional Categories", len(set(r[3] for r in combined_740_rows))),
        ("Validated (Supported) Tasks", sum(1 for r in combined_740_rows if r[10] == "Validated (Supported)")),
        ("Code Complete & Verified Tasks", sum(1 for r in combined_740_rows if r[10] == "Code Complete & Verified")),
        ("P0: Critical (Correctness / Safety / Compliance)", p0_count),
        ("P1: High (Competitive Parity & Customer Success)", p1_count),
        ("P2: Medium (Operational Improvement & Polish)", p2_count),
        ("P3: Low (Optimization & Advanced Differentiation)", p3_count),
    ]

    for idx, (m, v) in enumerate(summary_metrics, start=4):
        ws_dash[f"A{idx}"] = m
        ws_dash[f"B{idx}"] = v
        ws_dash[f"A{idx}"].font = data_font_bold
        ws_dash[f"A{idx}"].border = border_thin
        ws_dash[f"B{idx}"].font = data_font_bold
        ws_dash[f"B{idx}"].border = border_thin
        ws_dash[f"B{idx}"].alignment = Alignment(horizontal="center")

    # Task Classification Breakdown
    type_counts = {}
    for r in combined_740_rows:
        t = r[1]
        type_counts[t] = type_counts.get(t, 0) + 1

    ws_dash["D3"] = "Task Classification (Type)"
    ws_dash["E3"] = "Task Count"
    ws_dash["D3"].font = header_font
    ws_dash["D3"].fill = header_fill_slate
    ws_dash["E3"].font = header_font
    ws_dash["E3"].fill = header_fill_slate
    ws_dash["E3"].alignment = Alignment(horizontal="center")

    type_labels = {
        "P": "P — Persona Operational Task",
        "X": "X — Cross-Persona End-to-End Workflow",
        "S": "S — System & Background Engine Task",
        "UX": "UX — User Experience, Heuristics & Ergonomics",
        "C": "C — Legal, Statutory & GST Compliance",
        "SEC": "SEC — Security, Access Control & Tenant Defense",
        "R": "R — Reliability, Concurrency & Performance",
        "I": "I — Hardware & External Integration Task",
        "SaaS": "SaaS — Multi-Tenancy & Subscription Lifecycle",
        "D": "D — Strategic Market Differentiation & AI",
        "G-OS": "G-OS — Growth OS, Funnels, Referrals & Service Lifecycles",
    }

    for idx, (t_code, t_label) in enumerate(sorted(type_labels.items(), key=lambda x: -type_counts.get(x[0], 0)), start=4):
        ws_dash[f"D{idx}"] = t_label
        ws_dash[f"E{idx}"] = type_counts.get(t_code, 0)
        ws_dash[f"D{idx}"].font = data_font
        ws_dash[f"D{idx}"].border = border_thin
        ws_dash[f"E{idx}"].font = data_font_bold
        ws_dash[f"E{idx}"].border = border_thin
        ws_dash[f"E{idx}"].alignment = Alignment(horizontal="center")

    # Functional Categories Breakdown
    cat_counts = {}
    for r in combined_740_rows:
        cat_counts[r[3]] = cat_counts.get(r[3], 0) + 1

    start_cat_row = 17
    ws_dash[f"A{start_cat_row}"] = "Functional Category Distribution"
    ws_dash[f"B{start_cat_row}"] = "Task Count"
    ws_dash[f"A{start_cat_row}"].font = header_font
    ws_dash[f"A{start_cat_row}"].fill = header_fill_navy
    ws_dash[f"B{start_cat_row}"].font = header_font
    ws_dash[f"B{start_cat_row}"].fill = header_fill_navy
    ws_dash[f"B{start_cat_row}"].alignment = Alignment(horizontal="center")

    for idx, (cat_name, count) in enumerate(sorted(cat_counts.items(), key=lambda x: -x[1]), start=start_cat_row+1):
        ws_dash[f"A{idx}"] = cat_name
        ws_dash[f"B{idx}"] = count
        ws_dash[f"A{idx}"].font = data_font
        ws_dash[f"A{idx}"].border = border_thin
        ws_dash[f"B{idx}"].font = data_font_bold
        ws_dash[f"B{idx}"].border = border_thin
        ws_dash[f"B{idx}"].alignment = Alignment(horizontal="center")

    ws_dash.column_dimensions["A"].width = 44
    ws_dash.column_dimensions["B"].width = 16
    ws_dash.column_dimensions["C"].width = 6
    ws_dash.column_dimensions["D"].width = 54
    ws_dash.column_dimensions["E"].width = 16

    # -------------------------------------------------------------------------
    # Sheet 3: Growth OS & CRM Universe (25 Dedicated Tasks)
    # -------------------------------------------------------------------------
    ws_gos = wb.create_sheet(title="Growth OS & CRM Universe")
    create_styled_task_sheet(ws_gos, "Growth OS & CRM Universe", growth_os_25_rows, headers, "0277BD")

    # -------------------------------------------------------------------------
    # Sheet 4: Newly Added Strategic Tasks (155 Strategic Tasks)
    # -------------------------------------------------------------------------
    ws_new = wb.create_sheet(title="Newly Added Tasks")
    create_styled_task_sheet(ws_new, "Newly Added Tasks", new_155_rows, headers, "0D47A1")

    # -------------------------------------------------------------------------
    # Sheet 5: Existing Task Universe (560 Baseline Tasks)
    # -------------------------------------------------------------------------
    ws_existing = wb.create_sheet(title="Existing Task Universe")
    create_styled_task_sheet(ws_existing, "Existing Task Universe", existing_560_rows, headers, "455A64")

    # -------------------------------------------------------------------------
    # Sheet 6: Persona Coverage & JTBD
    # -------------------------------------------------------------------------
    ws_persona = wb.create_sheet(title="Persona Coverage & JTBD")
    ws_persona.views.sheetView[0].showGridLines = True
    ws_persona["A1"] = "Persona Coverage & Jobs-To-Be-Done (JTBD) Framework"
    ws_persona["A1"].font = title_font
    ws_persona.row_dimensions[1].height = 30

    persona_headers = [
        "Persona / Operational Role", "System Role Code", "Tasks",
        "Functional Job (What they do)", "Emotional Job (How they want to feel)", "Social Job (How they want to be perceived)"
    ]
    ws_persona.append(persona_headers)
    ws_persona.row_dimensions[2].height = 26
    for col_idx in range(1, len(persona_headers) + 1):
        cell = ws_persona.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill_navy
        cell.alignment = Alignment(horizontal="center" if col_idx in [2, 3] else "left", vertical="center")

    persona_jtbd_data = [
        ("Managing Proprietor ('Sethji')", "OWNER", 13, "Track daily sales, cash collections, gross margin, and overdue debtor chasing.", "In total control; zero cash-flow anxiety; peace of mind after store close.", "Respected, sharp, prosperous businessman who never gets cheated."),
        ("Kirana Shop Owner", "OWNER / CLERK", 20, "Fast retail billing, FMCG stock management, supplier intake, local customer credit khata.", "Fast and agile; no customer waiting in line; effortless supplier book keeping.", "Modern neighborhood grocer who maintains modern, honest digital accounts."),
        ("Gully Vendor / Small Retailer", "OWNER / POS", 17, "Sub-second walk-in cash and UPI billing, instant price checks, daily till reconciliation.", "Confident and unhurried even during peak market rush hours.", "Tech-savvy merchant accepting modern digital payments effortlessly."),
        ("Medical Shop Pharmacist", "STAFF / PHARMA", 14, "Sell medicines with batch/expiry, enforce strict FEFO, block expired stock, maintain DL records.", "Safe from drug inspector penalties and zero risk of patient harm.", "Certified healthcare professional dispensing authentic, quality medicines."),
        ("Wholesale Distributor", "MANAGER", 16, "Bulk B2B invoicing, price slab discounts, credit limits, multi-ton deliveries, aging receivables.", "Organized and commanding; working capital circulating smoothly without bad debt.", "Reliable market kingpin who dominates regional product distribution."),
        ("Single-Godown Distributor", "INVENTORY_STAFF", 11, "Receive stock into godown, allocate stock to orders, pick/dispatch, physical cycle counts.", "Orderly and precise; warehouse shelves match digital stock perfectly.", "Disciplined stock controller with zero shrinkage or lost cartons."),
        ("Multi-Godown Distributor", "LOGISTICS_MGR", 10, "Consolidated inventory visibility, inter-godown transfers, transit loss control, godown P&L.", "Omnipresent oversight across all distributed peripheral warehouses.", "Modern supply chain master operating a seamless regional distribution network."),
        ("Multi-Shop Owner", "SUPERADMIN", 11, "Multi-outlet dashboard, cross-store stock balancing, store P&L comparison, centralized catalog.", "Empowered executive managing a retail chain without being physically present.", "Progressive retail entrepreneur scaling rapidly across multiple city markets."),
        ("In-house Accountant ('Munshi')", "ACCOUNTANT", 16, "Double-entry books, GSTR-1/3B/2B reconciliation, voucher entries, Tally export, bank BRS.", "Methodical and relaxed at month-end; books balance to the exact rupee.", "Infallible finance guardian trusted completely by the business owner."),
        ("Field Sales Representative", "SALES_STAFF", 10, "Book retailer orders on mobile, check live ATP stock, verify customer credit, collect dues.", "Productive and self-sufficient; hitting monthly sales quotas with ease.", "Star salesperson with real-time inventory and pricing at fingertips."),
        ("Growth Lead / Marketing Manager", "GROWTH_LEAD", 10, "Configure multi-channel campaigns, track funnel conversion rates, calculate CAC and marketing ROI.", "Excited and data-driven; confident that every rupee of marketing budget yields positive return.", "Dynamic growth hacker accelerating business expansion sustainably."),
        ("Customer Success & Service Lead", "SUPPORT_LEAD", 9, "Manage customer/supplier complaints, enforce maintenance contract schedules, resolve tickets.", "Proud of 5-star customer ratings; swift resolution of field disputes.", "Empathetic customer champion protecting client retention and lifetime value."),
        ("Purchase Manager", "PURCHASE_MGR", 10, "Create POs, compare vendor rates, 3-way match bills with GRN, track supplier liabilities.", "Astute negotiator securing best wholesale prices without stockouts.", "Shrewd procurement strategist who protects company profit margins."),
        ("Warehouse / Inventory Custodian", "INVENTORY_STAFF", 13, "Physical stock intake, batch/serial tracking, damaged stock segregation, cycle count sessions.", "Physically organized; stock location and quantities completely verified.", "Vigilant custodian accountable for every piece of merchandise in the depot."),
        ("Delivery Driver / Fleet Operator", "DELIVERY_DRIVER", 7, "Receive dispatch manifest, multi-drop route navigation, doorstep parcel verification, POD, COD.", "Punctual, safe, and accountable; cash collected matches parcel drops exactly.", "Trustworthy logistics professional delivering on commitments daily."),
        ("External CA / Statutory Auditor", "AUDITOR", 7, "Audit Schedule III statements, verify Section 17(5) blocked ITC, 194Q TDS, GSTR-9, MCA trails.", "Confident that client records are legally airtight and audit-defensible.", "Authoritative tax consultant delivering pristine statutory certifications."),
        ("Assembly / Production Supervisor", "PRODUCTION_MGR", 4, "Define BOMs, issue raw materials, execute assembly work orders, calculate finished unit costs.", "Process-driven and efficient; zero material wastage or assembly bottlenecks.", "Skilled manufacturing head driving high-yield packaging operations."),
        ("Retail & B2B Customer", "EXTERNAL_USER", 8, "Receive digital invoice on WhatsApp, verify purchase history, review dues, pay via UPI.", "Respected and transparently treated; billing disputes resolved instantly.", "Smart shopper or retailer who patronizes modern, transparent businesses."),
        ("Vendor / Principal Supplier", "EXTERNAL_USER", 6, "Receive formal POs, deliver goods with challan, track payment advice, reconcile balance.", "Guaranteed payment certainty and clear commercial terms.", "Valued supply chain partner in a long-term profitable trade relationship."),
        ("System Administrator", "ADMIN", 13, "Manage users, configure RBAC, setup branches, configure GSTIN, audit logs, backup/recovery.", "In full architectural control; system is secure, compliant, and always available.", "Architect of a modern, resilient enterprise software backbone.")
    ]

    for r_idx, (p_name, role_code, t_count, f_job, e_job, s_job) in enumerate(persona_jtbd_data, start=3):
        ws_persona.append([p_name, role_code, t_count, f_job, e_job, s_job])
        ws_persona.row_dimensions[r_idx].height = 24
        for c_idx in range(1, 7):
            cell = ws_persona.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if c_idx in [2, 3]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.font = data_font_bold

    ws_persona.column_dimensions["A"].width = 34
    ws_persona.column_dimensions["B"].width = 18
    ws_persona.column_dimensions["C"].width = 10
    ws_persona.column_dimensions["D"].width = 46
    ws_persona.column_dimensions["E"].width = 38
    ws_persona.column_dimensions["F"].width = 38
    ws_persona.freeze_panes = "A3"

    # -------------------------------------------------------------------------
    # Sheet 7: Competitive & Differentiation
    # -------------------------------------------------------------------------
    ws_comp = wb.create_sheet(title="Competitive & Differentiation")
    ws_comp.views.sheetView[0].showGridLines = True
    ws_comp["A1"] = "Competitive Benchmarking & Strategic Market Differentiation"
    ws_comp["A1"].font = title_font
    ws_comp.row_dimensions[1].height = 30

    comp_headers = [
        "Feature / Capability Area", "Market Baseline (Tally / Busy / Vyapar)", "Competitor Pain Points & Weaknesses",
        "BizBoard Strategic Differentiation", "Customer Business Value Impact"
    ]
    ws_comp.append(comp_headers)
    ws_comp.row_dimensions[2].height = 26
    for col_idx in range(1, len(comp_headers) + 1):
        cell = ws_comp.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill_navy
        cell.alignment = Alignment(horizontal="center" if col_idx == 1 else "left", vertical="center")

    comp_data = [
        ("Vendor Bill Inwarding", "Manual typing of 50 line items per invoice in Tally/Vyapar.", "Extremely slow; 15 mins per bill; frequent typos in HSN and tax rates.", "Deterministic LLM Bill Extraction: snap photo of bill -> auto-populates 50 lines in 5 seconds.", "Saves 2 hours daily; eliminates data entry errors; accelerates inventory intake."),
        ("Counter Checkout Speed", "Desktop software with complex navigation menus or laggy web screens.", "Queue bottlenecks during festival rushes; clerks get frustrated; customers walk away.", "Sub-200ms POS Rapid Billing with full keyboard hotkeys and client-side IndexedDB caching.", "Reduces checkout time from 45s to 12s; handles 100+ checkouts/min effortlessly."),
        ("GSTR-2B ITC Matching", "Manual spreadsheet VLOOKUP or rigid exact-match software tools.", "Fails on invoice number dashes/slashes; ignores date differences; takes hours.", "Automated Smart Reconciler with fuzzy name and Levenshtein distance matching.", "Reclaims 100% of eligible ITC; prevents lapsing under Sec 16(4); saves ₹50,000+ yearly."),
        ("Debtor Chasing & Recovery", "Manual phone calls or static generic payment reminder SMS blasts.", "Awkward to chase trusted clients; customers ignore spam reminders; debt turns bad.", "Collections Autopilot: behavioral cadence modulation (polite -> firm) with dynamic UPI link.", "Reduces debtor days by 35%; accelerates cash recovery without straining relationships."),
        ("Omnichannel Growth OS & Funnels", "Basic standalone CRM or completely disconnected Excel sheets.", "Sales leads from web, WhatsApp, and exhibitions fall through cracks; zero marketing ROI visibility.", "Built-in Growth OS: embeddable web lead forms, exact-match dedupe, round-robin routing, and campaign ROI tracking.", "Increases lead conversion by 45%; provides true marketing ROI visibility down to closed cash receipts."),
        ("Advocate Referral & Loyalty Loop", "Manual verbal word-of-mouth with zero tracking or recognition.", "Merchants cannot motivate customers or sales agents to refer new business; fraud in informal commission payouts.", "Cryptographic unique referral links with automated reward generation on first invoice settlement and idempotent payout.", "Drives viral zero-CAC customer acquisition; creates self-sustaining referral loops."),
        ("Closed-Loop Dispute & Warranty Resolution", "Scattered phone calls, paper slips, and messy handwritten ledger adjustments.", "Slow complaint resolution; duplicate credit notes issued; disputed damaged stock gets lost in godown.", "1-Click Complaint-to-Credit/Debit Note: converts inspected defects directly into GST credit notes or vendor debit notes.", "Resolves disputes 5x faster; halts customer churn; reclaims 100% of vendor defect damages."),
        ("Inventory Replenishment", "Static reorder points or manual counting after stock has already run out.", "Stockouts of top-selling items; tied-up working capital in slow-moving dead stock.", "Inventory Run-Rate Autopilot: predicts stockout date based on burn rate and drafts PO to best supplier.", "Zero stockouts of fast-movers; cuts dead-stock capital by 40%."),
        ("Cash-Flow Forecasting", "Static accounting P&L showing historical accounting profit, not liquid cash.", "Owner doesn't know if there is enough bank balance for upcoming GST and supplier dues.", "Predictive Cash-Flow Simulator: models debtor payment delay probabilities over 30/60/90 days.", "Prevents emergency bank overdrafts and dishonoured supplier cheques."),
        ("Logistics & Fleet Economics", "Dispatches tracked on paper slips or completely unmonitored.", "No delivery proof; tempo delivery drivers pocket cash; disputed missing cartons.", "Driver Mobile PWA with digital POD (signature/GPS), mobile COD collection, and route margin analysis.", "Zero delivery shrinkage; verifiable proof of delivery; profitable delivery routes."),
        ("Customer Self-Service", "Merchant has to print, sign, scan, and email PDF invoices repeatedly.", "Inbound customer phone calls: 'Send my ledger statement', 'What is my pending balance?'.", "Interactive Magic Invoice Link on WhatsApp with self-service ledger view and 1-click UPI pay.", "Eliminates 80% of customer support calls; accelerates invoice clearance."),
        ("Tally Migration Barrier", "Migrating from Tally requires days of manual chart of accounts re-creation.", "High switching friction; merchants fear losing historical accounting records.", "One-Click Tally Historical Backup Migration: imports 100% of ledger masters and 3-year history in 15 mins.", "Eliminates switching friction; customers migrate risk-free in minutes.")
    ]

    for r_idx, r_data in enumerate(comp_data, start=3):
        ws_comp.append(r_data)
        ws_comp.row_dimensions[r_idx].height = 24
        for c_idx in range(1, 6):
            cell = ws_comp.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if c_idx == 1:
                cell.font = data_font_bold

    ws_comp.column_dimensions["A"].width = 28
    ws_comp.column_dimensions["B"].width = 36
    ws_comp.column_dimensions["C"].width = 40
    ws_comp.column_dimensions["D"].width = 46
    ws_comp.column_dimensions["E"].width = 44
    ws_comp.freeze_panes = "A3"

    # -------------------------------------------------------------------------
    # Sheet 8: UX & Error Recovery
    # -------------------------------------------------------------------------
    ws_ux = wb.create_sheet(title="UX & Error Recovery")
    ws_ux.views.sheetView[0].showGridLines = True
    ws_ux["A1"] = "UX Ergonomics, Nielsen Heuristics & Failure Recovery Paths"
    ws_ux["A1"].font = title_font
    ws_ux.row_dimensions[1].height = 30

    ux_headers = [
        "Nielsen Heuristic / UX Area", "Product Implementation Pattern", "Failure Scenario Addressed",
        "System Recovery & User Experience", "Cognitive Load Impact"
    ]
    ws_ux.append(ux_headers)
    ws_ux.row_dimensions[2].height = 26
    for col_idx in range(1, len(ux_headers) + 1):
        cell = ws_ux.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill_navy
        cell.alignment = Alignment(horizontal="center" if col_idx == 1 else "left", vertical="center")

    ux_data = [
        ("Visibility of System Status", "WebSocket progress bar on CSV imports & live sync status indicator.", "User doesn't know if 10,000-row file is uploading or frozen.", "Shows exact row counter (e.g. 'Row 4,500 of 10,000') and ETA.", "Eliminates anxiety and browser refresh rage clicks."),
        ("Match Real World & System", "Natural Indian commerce terminology (Khata, Udhar, Godown, Challan).", "Users confused by Western ERP jargon like 'General Journal' or 'Accounts Payables'.", "Interface speaks vernacular trade language with optional Hindi/Gujarati/Tamil UI.", "Zero learning curve for non-accountant store clerks."),
        ("User Control & Freedom", "10-second universal 'Undo' snackbar toast on deletions and cancellations.", "Cashier accidentally deletes large 50-item distributor order draft.", "Instant 'Undo' restores complete cart state without data loss.", "Eliminates panic and tedious manual re-entry."),
        ("Consistency & Standards", "Universal keyboard shortcuts (F1-F12, Enter, Esc, Ctrl+K omnibar).", "Inconsistent key behaviors between billing, inventory, and ledger screens.", "Standard hotkeys operate identically across 100% of POS and management screens.", "Builds muscle memory; enables blind touch-typing billing."),
        ("Error Prevention", "Pessimistic row-locking, unique constraints, and type-to-confirm modals.", "Two cashiers selling the last unit simultaneously; deleting company data.", "System locks stock row atomically; requires typing 'DELETE' to confirm destruction.", "Prevents accidental data loss and negative inventory bugs."),
        ("Recognition over Recall", "Customer Credit Health pill and Visual Warehouse Rack locator on search.", "Clerk forgets customer owes ₹50,000; picker wanders warehouse looking for SKU.", "Screen displays visual credit badge and physical shelf location tag ('Aisle B > Shelf 3').", "Zero mental memorization required; faster operations."),
        ("Flexibility & Efficiency", "Multi-cart Hold/Recall tabs (F6) and bulk spreadsheet-style inline grid edit.", "Customer steps away to pick another biscuit pack while long queue waits.", "Clerk holds bill in Tab 2; bills next customer; recalls Tab 1 with 1 keypress.", "Maintains smooth queue flow under peak pressure."),
        ("Aesthetic & Minimalist Design", "Progressive disclosure drawers and 1-click 'Privacy Mode' (Shift+P).", "Overcrowded screens showing 50 fields at once; bystanders peeking at revenue.", "Hides unnecessary fields behind drawers; masks financial figures from bystanders.", "Clean, focused workspace with zero visual clutter."),
        ("Help Users Recover from Errors", "Inline GST error banners with 1-click 'Auto-Fix' tax split suggestions.", "Cryptic error message 'Tax rate mismatch - code 400' leaving user stuck.", "Banner explains: 'Customer in Maharashtra. Click here to convert CGST+SGST to IGST'.", "Resolves errors in 1 second without calling support."),
        ("Help & Documentation", "Contextual inline tooltips, first-run guided checklist, and 'Ask BizBoard' bot.", "New merchant doesn't know how to file GSTR-1 or configure thermal printer.", "Step-by-step interactive onboarding walkthrough and conversational AI assistant.", "Self-service onboarding with 95% first-run completion rate.")
    ]

    for r_idx, r_data in enumerate(ux_data, start=3):
        ws_ux.append(r_data)
        ws_ux.row_dimensions[r_idx].height = 24
        for c_idx in range(1, 6):
            cell = ws_ux.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if c_idx == 1:
                cell.font = data_font_bold

    ws_ux.column_dimensions["A"].width = 30
    ws_ux.column_dimensions["B"].width = 38
    ws_ux.column_dimensions["C"].width = 38
    ws_ux.column_dimensions["D"].width = 44
    ws_ux.column_dimensions["E"].width = 36
    ws_ux.freeze_panes = "A3"

    # -------------------------------------------------------------------------
    # Sheet 9: Security & SaaS Readiness
    # -------------------------------------------------------------------------
    ws_sec = wb.create_sheet(title="Security & SaaS Readiness")
    ws_sec.views.sheetView[0].showGridLines = True
    ws_sec["A1"] = "Security Architecture, Data Isolation & SaaS Readiness Lifecycle"
    ws_sec["A1"].font = title_font
    ws_sec.row_dimensions[1].height = 30

    sec_headers = [
        "Architecture Dimension", "Technical Implementation Mechanism", "Security / Governance Objective",
        "SaaS Scalability & Commercial Impact", "Verification / Audit Method"
    ]
    ws_sec.append(sec_headers)
    ws_sec.row_dimensions[2].height = 26
    for col_idx in range(1, len(sec_headers) + 1):
        cell = ws_sec.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill_navy
        cell.alignment = Alignment(horizontal="center" if col_idx == 1 else "left", vertical="center")

    sec_data = [
        ("Multi-Tenant Isolation", "PostgreSQL native Row-Level Security (RLS) with session GUC app.company_id.", "Guarantees zero cross-tenant data leakage even in shared DB architecture.", "Enables massive multi-tenant scale with minimal database infrastructure cost.", "Automated CI/CD cross-tenant SQL injection penetration test suite."),
        ("Least Privilege RBAC", "Granular role-permission matrix with field-level margin & cost masking.", "Restricts store clerks and drivers from inspecting business profits or vendor costs.", "Enterprises can safely deploy software to 100+ low-trust field employees.", "Role-scoped serializer inspection and unit test permission gates."),
        ("Data Exfiltration Defense", "Dedicated export permission gate and IP address whitelisting.", "Prevents departing sales staff from stealing customer lists and sales registers.", "Protects enterprise proprietary client directories and trade pricing secrets.", "Audit logging of every CSV/Excel export action with IP address tracking."),
        ("Audit Trail Immutability", "Append-only database ledgers and SHA-256 cryptographic hash chaining.", "Satisfies MCA Rule 11(g) and Section 65B Indian Evidence Act for digital records.", "Airtight legal defensibility during statutory income tax and GST audits.", "Automated cryptographic checksum verification verifying zero disabled audit intervals."),
        ("Session & Auth Security", "TOTP 2FA, JWT token revocation in Redis, and idle session auto-timeout.", "Prevents account takeover from stolen credentials or unmonitored store PCs.", "Enterprise-grade cybersecurity confidence for commercial banking integrations.", "Automated OWASP security scan in GitHub Actions deployment pipeline."),
        ("Subscription Automation", "Razorpay Subscriptions webhook integration with automated GST tax invoices.", "Automates monthly/annual recurring subscription fee collection without friction.", "Zero manual billing overhead; automated dunning and credit card retry.", "Automated webhook simulation testing payment success, failure, and upgrade."),
        ("Plan Quota Governance", "Dynamic quota validator checking invoice volume, SKU count, and user seats.", "Enforces monetization boundaries between Free, Pro, and Enterprise tiers.", "Drives organic upsell revenue as customer business scales.", "Pre-save model validator raising PlanQuotaExceeded error."),
        ("Tenant Portability", "One-click complete tenant data export package in clean standard ZIP archive.", "Guarantees zero vendor lock-in for enterprise clients.", "Builds deep customer trust; removes buyer hesitation during sales cycle.", "Automated full-database export test producing valid Excel/PDF archives."),
        ("High-Availability Backup", "Continuous WAL archiving and daily encrypted pg_dump snapshots to S3.", "Zero-data-loss point-in-time recovery (PITR) in case of cloud catastrophe.", "Guarantees 99.9% uptime SLA for mission-critical retail store networks.", "Daily automated test-restore script verifying backup database integrity.")
    ]

    for r_idx, r_data in enumerate(sec_data, start=3):
        ws_sec.append(r_data)
        ws_sec.row_dimensions[r_idx].height = 24
        for c_idx in range(1, 6):
            cell = ws_sec.cell(row=r_idx, column=c_idx)
            cell.font = data_font
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if c_idx == 1:
                cell.font = data_font_bold

    ws_sec.column_dimensions["A"].width = 28
    ws_sec.column_dimensions["B"].width = 40
    ws_sec.column_dimensions["C"].width = 42
    ws_sec.column_dimensions["D"].width = 40
    ws_sec.column_dimensions["E"].width = 38
    ws_sec.freeze_panes = "A3"

    # Save Master Workbook
    wb.save(master_xlsx)
    print(f"Saved Master 9-Sheet Excel Workbook: {master_xlsx}")

    # Also update the legacy mirror files if not locked
    try:
        wb.save("Bizboard_Master_Task_Register_Enhanced.xlsx")
        with open("Bizboard_Master_Task_Register_Enhanced.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(combined_740_rows)
        print("Synchronized Bizboard_Master_Task_Register_Enhanced.xlsx and .csv.")
    except PermissionError as pe:
        print(f"Notice: Legacy mirror file locked by external viewer, master files are intact: {pe}")

    # Reviewed register: corrected priorities, evidence status, and dashboard.
    from scripts.improve_enhanced_task_register import main as write_reviewed_register
    write_reviewed_register()


if __name__ == "__main__":
    main()

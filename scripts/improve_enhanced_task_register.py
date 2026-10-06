# -*- coding: utf-8 -*-
"""Build the reviewed BizBoard task register workbook.

Reads the 12-column register, restores authored priorities from the filled
baseline, and checks distinctive mechanism claims against product code.
Writes Bizboard_Master_Task_Register_Enhanced.xlsx and the universe workbook.
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.additional_flows_data import (
    ADDITIONAL_FLOW_TASKS,
    CATEGORY_FLOWS,
    FLOW_BY_TASK,
    FLOW_CATALOG,
)
from scripts.os_readiness import OS_HEADERS, build_os_sheets, os_fields
from scripts.growth_os_tasks_data import GROWTH_OS_TASKS
from scripts.rebalance_priorities import refine_task_priority
from scripts.tasks_expansion_data import NEW_STRATEGIC_TASKS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENHANCED_CSV = os.path.join(ROOT, "Bizboard_Master_Task_Register_Enhanced.csv")
FILLED_XLSX = os.path.join(ROOT, "Bizboard_Master_Task_Register_Filled.xlsx")
ENHANCED_XLSX = os.path.join(ROOT, "Bizboard_Master_Task_Register_Enhanced.xlsx")
UNIVERSE_XLSX = os.path.join(ROOT, "Bizboard_Product_Task_Universe_Master.xlsx")
UNIVERSE_CSV = os.path.join(ROOT, "Bizboard_Product_Task_Universe_Master.csv")
PREREVIEW_CSV = os.path.join(ROOT, "scripts", "task_register_prereview_priorities.csv")
EVIDENCE_CSV = os.path.join(ROOT, "scripts", "task_evidence.csv")

HEADERS = [
    "Task ID",
    "Task Type",
    "Persona / Scope",
    "Category",
    "Task / Business Action",
    "Primary Actor",
    "Supporting Persona(s)",
    "Business Outcome",
    "Downstream Impact",
    "Priority",
    "Validation Status",
    "Notes",
    "Register slice",
    "Scope class",
    "Authored priority",
    "Priority decision",
    "Review outcome",
    "Audit note",
    "Flow ID",
    "Flow name",
    "Flow step",
    "Module",
    *OS_HEADERS,
]

THEME_SCOPES = {
    "Statutory Compliance",
    "AI & Differentiation",
    "Architecture & Platform",
    "Hardware Integrations",
    "External Integrations",
    "All Roles",
    "Platform / SaaS Admin",
    "System Administrator",
}

# Notes that name a mechanism absent from product code.
HARD_ABSENT = [
    ("pg_trgm", "No pg_trgm index was found in application code."),
    ("GinIndex", "No Django GinIndex on product search was found."),
    ("Shift+P", "No Shift+P privacy mask was found in the web client."),
    ("Privacy Mode", "No privacy-mask mode was found in the web client."),
    ("Z-score", "No Z-score invoice anomaly detector was found."),
    ("django-otp", "django-otp is not used in application code."),
    ("WebSocket", "No WebSocket import-progress channel was found."),
    ("location_tag", "No location_tag shelf-locator field was found."),
    ("TIME_BARRED", "No itc_status TIME_BARRED flag was found."),
    ("206AB", "No Section 206AB PAN check was found."),
    ("Ctrl+K", "No Ctrl+K command palette was found in the web client."),
    ("Command Palette", "No command palette was found in the web client."),
    ("type-to-confirm", "No type-to-confirm destructive modal was found."),
    ("hash chaining", "No cryptographic hash chain on the audit trail was found."),
]

# Related behaviour exists, or the note names the wrong mechanism.
SOFT_ABSENT = [
    (
        "SimpleHistory",
        "django-simple-history is not a dependency. The note names the wrong audit mechanism.",
    ),
    (
        "PlanQuotaExceeded",
        "No PlanQuotaExceeded exception exists. plan_quota_exceeded is only a help code.",
    ),
    (
        "Hindi/Gujarati",
        "English and Hindi catalogs exist. Stored locales gu and ta are forced back to English in web/src/i18n/index.ts.",
    ),
    (
        "Gujarati/Tamil",
        "English and Hindi catalogs exist. Stored locales gu and ta are forced back to English in web/src/i18n/index.ts.",
    ),
]

# Hand-checked rows. These replace the note so the sheet no longer states the false claim.
PARTIAL = {
    "S-0561": {
        "category": "Reporting & Business Intelligence",
        "note": (
            "Trial-balance reporting exists in accounting.reports.trial_balance, and books health "
            "exposes trial_balance_balanced. No hourly Celery beat task that quarantines unbalanced "
            "batches was found."
        ),
        "audit": (
            "Category moved off Payments & Reconciliation. The previous note claimed an hourly "
            "Celery quarantine worker."
        ),
    },
    "S-0562": {
        "note": (
            "No CartSession model and no 30-minute cart-expiry release worker were found. "
            "Do not treat that timeout as implemented."
        ),
        "audit": "Previous note cited CartSession.updated_at. That model does not exist.",
    },
    "UX-0581": {
        "note": (
            "POS keys in web/src/pages/pos/PosPage.tsx: F2 focuses search, F1 cash, F4 card, "
            "F5 and F6 UPI, F7 credit, F8 holds the session. The previous note reversed this map."
        ),
        "audit": "Previous note said F1 search, F4 cash, and F8 print.",
    },
    "UX-0582": {
        "note": (
            "Session hold is F8 (holdAndCreateSession). F9 recalls when more than one session exists. "
            "F6 tenders UPI. A five-cart cap was not verified."
        ),
        "audit": "Previous note called F6 Hold Bill.",
    },
}

IDENT_RE = re.compile(
    r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"
    r"|[a-z]+(?:[A-Z][a-z0-9]*)+"
    r"|[a-z]+(?:_[a-z0-9]+){1,}"
)
IDENT_SKIP = {
    "updated_at",
    "created_at",
    "post_save",
    "payment_mode",
    "company_id",
}

NAVY = "1F497D"
SLATE = "37474F"
THIN = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color=NAVY)
DATA_FONT = Font(name="Calibri", size=10)
BOLD_FONT = Font(name="Calibri", size=10, bold=True)
WRAP = Alignment(vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

PRIORITY_FILL = {
    "P0": ("FDECEA", "9B1C1C"),
    "P1": ("FFF6E0", "8A5A00"),
    "P2": ("E7F6EE", "1B5E20"),
    "P3": ("F3E8FF", "4A148C"),
}
STATUS_FILL = {
    "Validated (Supported)": ("FFF6E0", "8A5A00"),
    "Code Complete & Verified": ("E7F6EE", "1B5E20"),
    "Partial": ("FFE8CC", "E65100"),
    "Mechanism not found": ("FDECEA", "9B1C1C"),
    "In product": ("E3F2FD", "0D47A1"),
    "Author assertion": ("FFF6E0", "8A5A00"),
    "Code symbol found": ("E3F2FD", "0D47A1"),
    "Note corrected": ("FFE8CC", "E65100"),
}


def load_product_blob():
    parts = []
    roots = [
        os.path.join(ROOT, "backend"),
        os.path.join(ROOT, "web", "src"),
    ]
    skip = {"node_modules", ".git", "__pycache__", "venv", ".venv"}
    for base in roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for name in filenames:
                if os.path.splitext(name)[1] not in {".py", ".ts", ".tsx"}:
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8", errors="ignore") as handle:
                        parts.append(handle.read())
                except OSError:
                    continue
    return "\n".join(parts)


def code_symbol(note, blob):
    found = []
    for token in IDENT_RE.findall(note or ""):
        if len(token) < 8 or token in IDENT_SKIP:
            continue
        if token in blob:
            found.append(token)
    found.sort(key=len, reverse=True)
    return found[0] if found else ""


def flow_for(task_id, category):
    if task_id in FLOW_BY_TASK:
        return FLOW_BY_TASK[task_id]
    mapped = CATEGORY_FLOWS.get(category)
    if mapped:
        return (mapped[0], mapped[1], "", mapped[2])
    return ("OTHER", category or "Unassigned", "", "")


def slice_for(task_id, task_type):
    if task_type == "F":
        return "Added flows"
    if task_type == "G-OS":
        return "Growth OS"
    number = int(str(task_id).rsplit("-", 1)[1])
    if number >= 561:
        return "Strategic expansion"
    return "Baseline"


def scope_class(persona, task_type, operational):
    if task_type == "G-OS":
        return "Growth role"
    if persona == "Multiple / Cross-persona":
        return "Cross-persona"
    if str(persona).startswith("System /"):
        return "System engine"
    if persona in THEME_SCOPES:
        return "Platform or theme scope"
    if persona in operational:
        return "Operational role"
    return "Named role"


def apply_evidence(row, blob):
    """Return status, category, note, review outcome, audit note."""
    task_id = row[0]
    category = row[3]
    action = row[4] or ""
    status = row[10]
    note = row[11] or ""
    text = f"{action}\n{note}"

    if task_id in PARTIAL:
        spec = PARTIAL[task_id]
        return (
            "Partial",
            spec.get("category", category),
            spec["note"],
            "Partial",
            spec["audit"],
        )

    for token, message in HARD_ABSENT:
        if token in text:
            return ("Mechanism not found", category, note, "Mechanism not found", message)

    for token, message in SOFT_ABSENT:
        if token in text:
            return ("Partial", category, note, "Partial", message)

    hit = code_symbol(note, blob)
    if hit:
        return (
            status,
            category,
            note,
            "Code symbol found",
            f"Matched {hit} in product code. This is not a functional test.",
        )
    return (status, category, note, "Author assertion", "")


def priority_decision(authored, final, previous):
    if final == previous and final == authored:
        return "Unchanged"
    if final == authored and final != previous:
        return (
            f"Restored to authored {final}. The previous workbook had {previous} "
            "after a keyword rebalance."
        )
    if final != previous:
        return (
            f"Set to {final}. The previous workbook had {previous}. "
            f"Authored priority was {authored}."
        )
    return (
        f"Kept {final}. The previous workbook had {previous}. "
        f"Authored priority was {authored}."
    )


def load_rows():
    with open(ENHANCED_CSV, encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader)
        current = list(reader)
    if headers[:12] != HEADERS[:12]:
        raise SystemExit(f"Unexpected register headers: {headers}")

    authored = {}
    operational = set()
    if os.path.exists(FILLED_XLSX):
        filled_wb = openpyxl.load_workbook(FILLED_XLSX, data_only=True)
        authored = {
            row[0]: row[9]
            for row in filled_wb["Master Task Register"].iter_rows(min_row=2, values_only=True)
        }
        operational = {
            row[2]
            for row in filled_wb["Master Task Register"].iter_rows(min_row=2, values_only=True)
            if row[2]
        }
    else:
        # The 560-task workbook is optional once its priorities are in the CSV.
        operational = {
            "Kirana Shop Owner",
            "Gully Vendor / Small Retailer",
            "Distributor",
            "Accountant / GST Operator",
            "Medical Shop",
            "Business Owner",
            "Inventory Manager",
            "Admin / System Owner",
            "Single-Godown Distributor",
            "Multi-Shop Owner",
            "Multi-Godown Distributor",
            "Salesperson",
            "Purchase Manager",
            "Customer",
            "Delivery Driver / Route Logistics",
            "External CA / Statutory Auditor",
            "Supplier",
            "Assembly / Production Supervisor",
        }
    source_priority = {item[0]: item[9] for item in list(NEW_STRATEGIC_TASKS) + list(GROWTH_OS_TASKS)}
    source_priority.update({item[0]: item[9] for item in ADDITIONAL_FLOW_TASKS})
    flow_rows = {item[0]: list(item) for item in ADDITIONAL_FLOW_TASKS}
    current = [flow_rows.get(row[0], row) for row in current]
    present = {row[0] for row in current}
    for item in ADDITIONAL_FLOW_TASKS:
        if item[0] not in present:
            current.append(list(item))

    with open(PREREVIEW_CSV, encoding="utf-8", newline="") as handle:
        prereview = {
            item["Task ID"]: item["Priority in the workbook before this review"]
            for item in csv.DictReader(handle)
        }

    blob = load_product_blob()
    evidence = load_evidence()
    reviewed = []
    for raw in current:
        row = list(raw[:12])
        # Priorities already corrected in the CSV must still be compared with the
        # pre-review workbook, or a second run hides the decision log.
        previous = prereview.get(row[0], row[9])
        if row[0] in authored:
            row[9] = authored[row[0]]
        elif row[0] in source_priority:
            row[9] = source_priority[row[0]]
        authored_priority = row[9]
        row[9] = refine_task_priority(row)
        status, category, note, outcome, audit = apply_evidence(row, blob)
        row[3] = category
        row[10] = status
        row[11] = note
        decision = priority_decision(authored_priority, row[9], previous)
        if decision != "Unchanged":
            audit = (audit + " " if audit else "") + decision
        reviewed.append(
            row
            + [
                slice_for(row[0], row[1]),
                scope_class(row[2], row[1], operational),
                authored_priority,
                decision,
                outcome,
                audit,
                *flow_for(row[0], row[3]),
                *os_fields(row, outcome, evidence.get(row[0])),
            ]
        )
    link_flow_dependencies(reviewed)
    return reviewed, operational


def load_evidence():
    """Optional hand or CI fills. A header-only file changes nothing."""
    if not os.path.exists(EVIDENCE_CSV):
        return {}
    with open(EVIDENCE_CSV, encoding="utf-8", newline="") as handle:
        return {
            item["Task ID"]: item
            for item in csv.DictReader(handle)
            if item.get("Task ID")
        }


def link_flow_dependencies(rows):
    """A numbered flow step depends on the previous step. Category groups have no step."""
    groups = defaultdict(list)
    for row in rows:
        step = row[20]
        if isinstance(step, int) or (isinstance(step, str) and str(step).isdigit()):
            groups[row[18]].append((int(step), row))
    for items in groups.values():
        items.sort(key=lambda pair: pair[0])
        for index, (_step, row) in enumerate(items):
            if index and not row[41]:
                row[41] = items[index - 1][1][0]


def fill_header(ws, headers, fill=NAVY):
    ws.append(headers)
    ws.row_dimensions[1].height = 30
    header_fill = PatternFill(start_color=fill, end_color=fill, fill_type="solid")
    for col, _header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = HEADER_FONT
        cell.alignment = CENTER


def paint_task_rows(ws, rows):
    for offset, row in enumerate(rows):
        excel_row = offset + 2
        ws.append(row)
        ws.row_dimensions[excel_row].height = 32
        for col in range(1, len(HEADERS) + 1):
            cell = ws.cell(row=excel_row, column=col)
            cell.font = DATA_FONT
            cell.border = THIN
            cell.alignment = CENTER if col in {1, 2, 10, 11, 13, 14, 15, 17, 19, 21, 22, 23, 28, 29, 35, 36, 37, 38, 47} else WRAP
            if col == 1:
                cell.font = BOLD_FONT
        priority = row[9]
        if priority in PRIORITY_FILL:
            bg, fg = PRIORITY_FILL[priority]
            cell = ws.cell(row=excel_row, column=10)
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=True, color=fg)
        status = row[10]
        if status in STATUS_FILL:
            bg, fg = STATUS_FILL[status]
            cell = ws.cell(row=excel_row, column=11)
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=True, color=fg)
        outcome = row[16]
        if outcome in STATUS_FILL:
            bg, fg = STATUS_FILL[outcome]
            cell = ws.cell(row=excel_row, column=17)
            cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
            cell.font = Font(name="Calibri", size=10, bold=True, color=fg)


def add_task_table(ws, name, nrows):
    last_col = get_column_letter(len(HEADERS))
    ref = f"A1:{last_col}{nrows + 1}"
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=False,
        showColumnStripes=False,
    )
    ws.add_table(table)
    ws.freeze_panes = "A2"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_TABLOID
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddHeader.left.text = "BizBoard task register"
    ws.oddFooter.right.text = "Page &P of &N"
    ws.print_title_rows = "1:1"
    ws.sheet_view.showGridLines = False
    widths = {
        1: 14, 2: 12, 3: 32, 4: 32, 5: 46, 6: 28, 7: 28, 8: 40, 9: 42,
        10: 12, 11: 26, 12: 55, 13: 22, 14: 26, 15: 18, 16: 42, 17: 24, 18: 55,
        19: 14, 20: 36, 21: 12, 22: 16,
        23: 14, 24: 22, 25: 18, 26: 18, 27: 16, 28: 16, 29: 16,
        30: 26, 31: 20, 32: 20, 33: 18, 34: 20, 35: 12,
        36: 22, 37: 16, 38: 12, 39: 18, 40: 16, 41: 14, 42: 16, 43: 18,
        44: 18, 45: 16, 46: 16, 47: 18,
    }
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def write_label_value(ws, row, label, value, bold=False):
    ws.cell(row=row, column=1, value=label).font = BOLD_FONT if bold else DATA_FONT
    ws.cell(row=row, column=1).alignment = WRAP
    ws.cell(row=row, column=1).border = THIN
    cell = ws.cell(row=row, column=2, value=value)
    cell.font = BOLD_FONT
    cell.alignment = CENTER
    cell.border = THIN


def build_dashboard(wb, rows):
    ws = wb["Coverage Dashboard"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "BizBoard task register - coverage dashboard"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 28
    ws["A2"] = (
        "Live counts use formulas on Task Register. The snapshot on How to read "
        "is the figure set from this review."
    )
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.merge_cells("A2:E2")

    # Write two blocks side by side with formulas so a later edit cannot
    # reprint 740 validated rows.
    left_header_row = 4
    ws.cell(row=left_header_row, column=1, value="Register size").font = HEADER_FONT
    ws.cell(row=left_header_row, column=1).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    ws.cell(row=left_header_row, column=2, value="Count").font = HEADER_FONT
    ws.cell(row=left_header_row, column=2).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    size_formulas = [
        ("Tasks", "=COUNTA(TaskRegister[Task ID])"),
        ("Baseline", '=COUNTIF(TaskRegister[Register slice],"Baseline")'),
        ("Strategic expansion", '=COUNTIF(TaskRegister[Register slice],"Strategic expansion")'),
        ("Growth OS", '=COUNTIF(TaskRegister[Register slice],"Growth OS")'),
        ("Added flows", '=COUNTIF(TaskRegister[Register slice],"Added flows")'),
    ]
    for idx, (label, formula) in enumerate(size_formulas, start=5):
        write_label_value(ws, idx, label, formula)

    ws.cell(row=10, column=1, value="Validation status").font = HEADER_FONT
    ws.cell(row=10, column=1).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    ws.cell(row=10, column=2, value="Count").font = HEADER_FONT
    ws.cell(row=10, column=2).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    statuses = [
        "Validated (Supported)",
        "Code Complete & Verified",
        "Partial",
        "Mechanism not found",
        "In product",
    ]
    for idx, status in enumerate(statuses, start=11):
        write_label_value(
            ws, idx, status, f'=COUNTIF(TaskRegister[Validation Status],"{status}")'
        )
    ws["A16"] = (
        "Validated (Supported) is the author's claim. In product means the flow step exists "
        "in a module. Neither status is a full functional test."
    )
    ws["A16"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.merge_cells("A16:E16")
    ws.row_dimensions[16].height = 32

    ws.cell(row=17, column=1, value="Priority").font = HEADER_FONT
    ws.cell(row=17, column=1).fill = PatternFill(start_color=SLATE, end_color=SLATE, fill_type="solid")
    ws.cell(row=17, column=2, value="Count").font = HEADER_FONT
    ws.cell(row=17, column=2).fill = PatternFill(start_color=SLATE, end_color=SLATE, fill_type="solid")
    for idx, priority in enumerate(["P0", "P1", "P2", "P3"], start=18):
        write_label_value(ws, idx, priority, f'=COUNTIF(TaskRegister[Priority],"{priority}")')

    ws.cell(row=4, column=4, value="Scope class").font = HEADER_FONT
    ws.cell(row=4, column=4).fill = PatternFill(start_color=SLATE, end_color=SLATE, fill_type="solid")
    ws.cell(row=4, column=5, value="Tasks").font = HEADER_FONT
    ws.cell(row=4, column=5).fill = PatternFill(start_color=SLATE, end_color=SLATE, fill_type="solid")
    classes = [
        "Operational role",
        "Named role",
        "Growth role",
        "Cross-persona",
        "Platform or theme scope",
        "System engine",
    ]
    for idx, name in enumerate(classes, start=5):
        cell_l = ws.cell(row=idx, column=4, value=name)
        cell_l.font = DATA_FONT
        cell_l.border = THIN
        cell_l.alignment = WRAP
        cell_v = ws.cell(row=idx, column=5, value=f'=COUNTIF(TaskRegister[Scope class],"{name}")')
        cell_v.font = BOLD_FONT
        cell_v.border = THIN
        cell_v.alignment = CENTER

    ws.cell(row=17, column=4, value="Task type").font = HEADER_FONT
    ws.cell(row=17, column=4).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    ws.cell(row=17, column=5, value="Tasks").font = HEADER_FONT
    ws.cell(row=17, column=5).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    type_labels = [
        ("P", "P - persona task"),
        ("X", "X - cross-persona workflow"),
        ("G-OS", "G-OS - growth and service"),
        ("S", "S - system engine"),
        ("UX", "UX - ergonomics"),
        ("C", "C - statutory control"),
        ("D", "D - differentiation"),
        ("SEC", "SEC - security"),
        ("R", "R - reliability"),
        ("I", "I - hardware and integrations"),
        ("SaaS", "SaaS - tenancy and subscription"),
    ]
    for idx, (code, label) in enumerate(type_labels, start=18):
        cell_l = ws.cell(row=idx, column=4, value=label)
        cell_l.font = DATA_FONT
        cell_l.border = THIN
        cell_v = ws.cell(row=idx, column=5, value=f'=COUNTIF(TaskRegister[Task Type],"{code}")')
        cell_v.font = BOLD_FONT
        cell_v.border = THIN
        cell_v.alignment = CENTER

    categories = [name for name, _count in Counter(row[3] for row in rows).most_common()]
    start = 24
    ws.cell(row=start, column=1, value="Category").font = HEADER_FONT
    ws.cell(row=start, column=1).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    ws.cell(row=start, column=2, value="Tasks").font = HEADER_FONT
    ws.cell(row=start, column=2).fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    for idx, name in enumerate(categories, start=start + 1):
        write_label_value(ws, idx, name, f'=COUNTIF(TaskRegister[Category],"{name}")')

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 4
    ws.column_dimensions["D"].width = 42
    ws.column_dimensions["E"].width = 14
    ws.freeze_panes = "A4"
    ws.oddHeader.left.text = "Coverage dashboard"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return categories


def build_how_to_read(wb, rows):
    ws = wb["How to read"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "How to read this register"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 28
    ws["A2"] = (
        "Feature list frozen at 770 tasks. Start at Founder view. "
        "Release gate splits MVP, Pilot, and Later. Evidence columns stay empty until a test passes. "
        "See Review disposition for comments that were not applied."
    )
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.merge_cells("A2:C2")

    intro = [
        (4, "What changed"),
        (5, "The previous file marked 715 rows Validated (Supported) and 25 rows Code Complete & Verified, then the dashboard added those together and printed 740 validated tasks."),
        (6, "A keyword pass had raised 37 ordinary workflows to P0 because the note contained words such as atomic or credit limit, and had dropped 23 owner reports from P2 to P3."),
        (7, "Persona counts on the jobs-to-be-done sheet were copied from the 560-task register and renamed. They did not match Persona / Scope on this file. System engines were included in a count of 72 operational personas."),
        (8, "Several notes name mechanisms that are not in the product code. Those rows are now Partial or Mechanism not found. The original wording is in the audit note where it was replaced."),
        (9, "Numbering shares one sequence through GOS-0740. Added flows are F-0741 onward. Filter Flow ID on Task Register, or open the Flows sheet. Category rows are grouped into a flow as well, with a blank step."),
        (10, "New flows cover payroll, workshop jobs, manufacturing execution, project milestones, and insurance. Each note cites a model or function that is in the product, and the flow catalog states the module limit."),
    ]
    for row_idx, text in intro:
        ws.cell(row=row_idx, column=1, value=text).font = BOLD_FONT if row_idx == 4 else DATA_FONT
        ws.cell(row=row_idx, column=1).alignment = WRAP
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=3)
        ws.row_dimensions[row_idx].height = 36 if row_idx > 4 else 20

    ws["A12"] = "Status meanings"
    ws["A12"].font = HEADER_FONT
    ws["A12"].fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    ws.merge_cells("A12:C12")
    meanings = [
        ("Validated (Supported)", "Author assertion", "The register author marked the row supported. A blank audit note means this review did not re-test it."),
        ("Code Complete & Verified", "Growth OS claim", "Kept where the note's API name exists in product code. Still not a full functional test."),
        ("Code symbol found", "Review outcome", "A specific identifier in the note occurs in backend or web/src. That confirms the name, not the business outcome."),
        ("Partial", "Corrected", "Related behaviour exists, or the note named the wrong mechanism. Read the audit note."),
        ("Mechanism not found", "Corrected", "The note names a mechanism that is absent from product code."),
        ("Author assertion", "Review outcome", "The note has no specific code identifier. The status was left as the author wrote it."),
        ("In product", "Added flow", "The step exists in a module. Read the Flows sheet for what that module does not do."),
    ]
    for col, header in enumerate(["Status or outcome", "Kind", "Meaning"], start=1):
        cell = ws.cell(row=13, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=SLATE, end_color=SLATE, fill_type="solid")
        cell.alignment = WRAP
        cell.border = THIN
    for offset, item in enumerate(meanings):
        for col, value in enumerate(item, start=1):
            cell = ws.cell(row=14 + offset, column=col, value=value)
            cell.font = DATA_FONT
            cell.alignment = WRAP
            cell.border = THIN
        ws.row_dimensions[14 + offset].height = 28

    ws["A22"] = "Snapshot at this review"
    ws["A22"].font = HEADER_FONT
    ws["A22"].fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    ws.merge_cells("A22:B22")
    snapshot = [
        ("Tasks", len(rows)),
        ("Baseline", sum(1 for row in rows if row[12] == "Baseline")),
        ("Strategic expansion", sum(1 for row in rows if row[12] == "Strategic expansion")),
        ("Growth OS", sum(1 for row in rows if row[12] == "Growth OS")),
        ("Added flows", sum(1 for row in rows if row[12] == "Added flows")),
    ]
    snapshot_start = 23
    for status, _count in Counter(row[10] for row in rows).most_common():
        snapshot.append((status, _count))
    for priority in ["P0", "P1", "P2", "P3"]:
        snapshot.append((priority, sum(1 for row in rows if row[9] == priority)))
    for name, _count in Counter(row[13] for row in rows).most_common():
        snapshot.append((f"Scope: {name}", _count))
    changed = sum(1 for row in rows if row[15] != "Unchanged")
    snapshot.append(("Priority decisions", changed))
    for idx, (label, value) in enumerate(snapshot, start=snapshot_start):
        write_label_value(ws, idx, label, value)

    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 88
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.right.text = "Page &P of &N"


def build_findings(wb):
    ws = wb["Review findings"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Review findings"
    ws["A1"].font = TITLE_FONT
    headers = ["#", "Finding", "What was wrong", "Correction in this file"]
    findings = [
        (
            "1",
            "Validated total",
            "The dashboard counted every status containing Validated or Verified as Validated (Supported), so 25 Code Complete rows were included and the total printed as 740.",
            "Status totals are separate. Validated (Supported) is labeled as an author assertion.",
        ),
        (
            "2",
            "Priority rebalance",
            "Scanning notes for atomic, credit limit, and similar words raised ordinary workflows to P0. A polish list dropped margin, valuation, dead stock, and store comparison from P2 to P3.",
            "Authored priorities were restored. P0 is applied only when the task action itself names a statutory or credit-limit control. P3 is limited to polish and speculative features.",
        ),
        (
            "3",
            "Persona counts",
            "Jobs-to-be-done counts were hardcoded from the 560-task register under different names. Medical Shop was titled Medical Shop Pharmacist. Business Owner's 13 tasks were titled Managing Proprietor. System engines inflated the persona total to 72.",
            "Each jobs-to-be-done row names the register persona it counts. Task counts are COUNTIF formulas. Scope class separates operational roles, named roles, growth roles, cross-persona work, platform scopes, and system engines.",
        ),
        (
            "4",
            "False mechanisms",
            "Notes asserted CartSession, an hourly trial-balance quarantine worker, pg_trgm search, Shift+P privacy mask, a Z-score detector, WebSocket import progress, Ctrl+K, type-to-confirm, TIME_BARRED ITC, Section 206AB, django-otp, and django-simple-history.",
            "Those rows are Partial or Mechanism not found. POS hold is documented as F8, not F6. F6 tenders UPI.",
        ),
        (
            "5",
            "Illustrated market claims",
            "Competitive, UX, and security sheets stated checkout throughput, conversion lifts, rupee savings, and a 99.9 percent SLA as if they were measured results.",
            "Each row now has a review column. Quantified outcomes are labeled illustrative targets.",
        ),
        (
            "6",
            "Duplicate workbook",
            "This file was identical to Bizboard_Product_Task_Universe_Master.xlsx.",
            "Both workbooks are written from this review so they do not diverge.",
        ),
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = CENTER
    for offset, item in enumerate(findings):
        for col, value in enumerate(item, start=1):
            ws.cell(row=4 + offset, column=col, value=value)
    for row_idx in range(4, 10):
        ws.row_dimensions[row_idx].height = 48
        for col in range(1, 5):
            cell = ws.cell(row=row_idx, column=col)
            cell.font = DATA_FONT
            cell.alignment = WRAP
            cell.border = THIN
    ws.row_dimensions[3].height = 22
    for col in range(1, 5):
        cell = ws.cell(row=3, column=col)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = CENTER
        cell.border = THIN
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 62
    ws.column_dimensions["D"].width = 62
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "3:3"


def build_persona(wb):
    ws = wb["Persona Coverage"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Persona coverage and jobs to be done"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Register tasks counts Persona / Scope with COUNTIF. "
        "Previously printed counts came from the 560-task register and several names did not match."
    )
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.merge_cells("A2:G2")
    ws.row_dimensions[2].height = 28
    headers = [
        "Jobs-to-be-done name",
        "Register persona",
        "Register tasks",
        "Previously printed",
        "Count check",
        "Functional job",
        "Emotional job",
        "Social job",
    ]
    # Row 3 will be the header because we append after two title rows.
    # COUNTIF must use the table. Header is row 3, data starts row 4.
    persona_rows = [
        ("Managing Proprietor ('Sethji')", "Business Owner", 13, "Track daily sales, cash, margin, and overdue debtors.", "In control of the day's cash.", "A proprietor who can see the books."),
        ("Kirana Shop Owner", "Kirana Shop Owner", 20, "Fast billing, FMCG stock, supplier intake, and customer khata.", "No queue and a clear supplier book.", "A grocer with tidy accounts."),
        ("Gully Vendor / Small Retailer", "Gully Vendor / Small Retailer", 17, "Walk-in cash and UPI billing, price checks, and till close.", "Unhurried at peak hour.", "A merchant who takes digital payment."),
        ("Medical Shop Pharmacist", "Medical Shop", 14, "Batch and expiry sales, FEFO, and drug-licence records.", "Safe from expiry and licence gaps.", "A dispenser with a defensible register."),
        ("Wholesale Distributor", "Distributor", 16, "Bulk billing, slabs, credit limits, and receivables.", "Working capital moving without silent bad debt.", "A distributor who can see exposure."),
        ("Single-Godown Distributor", "Single-Godown Distributor", 11, "Receive, allocate, pick, and count one godown.", "Shelves that match the book.", "A stock controller who can explain a variance."),
        ("Multi-Godown Distributor", "Multi-Godown Distributor", 10, "Transfers, transit loss, and godown margin.", "One view across godowns.", "An operator who can move stock on purpose."),
        ("Multi-Shop Owner", "Multi-Shop Owner", 11, "Outlet comparison, stock balancing, and a shared catalog.", "Able to run more than one counter.", "An owner who can compare shops."),
        ("In-house Accountant ('Munshi')", "Accountant / GST Operator", 16, "Books, returns, vouchers, Tally export, and bank reconciliation.", "A period close that ties.", "An accountant the owner can trust with the return."),
        ("Field Sales Representative", "Salesperson", 10, "Book orders, check stock and credit, and collect dues.", "Able to answer a retailer without calling the office.", "A salesperson with current price and stock."),
        ("Growth Lead / Marketing Manager", "", 10, "Campaigns, funnel conversion, and acquisition cost.", "Able to see which channel produced cash.", "A lead who can explain spend."),
        ("Customer Success & Service Lead", "", 9, "Complaints, contracts, and tickets.", "A dispute that has an owner.", "A service lead who can close the loop."),
        ("Purchase Manager", "Purchase Manager", 10, "Purchase orders, vendor rates, and three-way match.", "Buying without a surprise stockout.", "A buyer who can show the rate decision."),
        ("Warehouse / Inventory Custodian", "Inventory Manager", 13, "Intake, batch and serial, damage, and cycle counts.", "A location that matches the balance.", "A custodian who can account for a carton."),
        ("Delivery Driver / Fleet Operator", "Delivery Driver / Route Logistics", 7, "Manifest, drop, proof of delivery, and cash on delivery.", "Cash collected matches the drops.", "A driver with a manifest, not a loose slip."),
        ("External CA / Statutory Auditor", "External CA / Statutory Auditor", 7, "Statements, blocked credit, TDS, and annual returns.", "A file that can be explained.", "An auditor who is not reconstructing the books."),
        ("Assembly / Production Supervisor", "Assembly / Production Supervisor", 4, "Bills of material, issue, and finished cost.", "Material issued matches the order.", "A supervisor who can explain yield."),
        ("Retail & B2B Customer", "Customer", 8, "Invoice, history, dues, and payment.", "A bill that can be checked.", "A customer who can see the same number as the shop."),
        ("Vendor / Principal Supplier", "Supplier", 6, "Purchase orders, challan, and payment advice.", "A balance both sides can tie.", "A supplier with a document, not a verbal order."),
        ("System Administrator", "Admin / System Owner", 13, "Users, roles, branches, GSTIN, and recovery.", "A tenant that is configured on purpose.", "An admin who can see who changed what."),
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = CENTER
    for idx, (name, key, old, functional, emotional, social) in enumerate(persona_rows, start=4):
        ws.cell(row=idx, column=1, value=name)
        ws.cell(row=idx, column=2, value=key)
        if key:
            ws.cell(row=idx, column=3, value=f'=COUNTIF(TaskRegister[Persona / Scope],B{idx})')
            ws.cell(row=idx, column=5, value=f'=IF(C{idx}=D{idx},"Matches","Does not match")')
        else:
            ws.cell(row=idx, column=3, value="")
            ws.cell(row=idx, column=5, value="No single register persona uses this name")
        ws.cell(row=idx, column=4, value=old)
        ws.cell(row=idx, column=6, value=functional)
        ws.cell(row=idx, column=7, value=emotional)
        ws.cell(row=idx, column=8, value=social)
        ws.row_dimensions[idx].height = 30
        for col in range(1, 9):
            cell = ws.cell(row=idx, column=col)
            cell.font = BOLD_FONT if col in {3, 4, 5} else DATA_FONT
            cell.alignment = CENTER if col in {3, 4, 5} else WRAP
            cell.border = THIN
    note_row = 25
    ws.cell(
        row=note_row,
        column=1,
        value=(
            "Managing Proprietor is also its own persona, separate from Business Owner. "
            "System Administrator on the old sheet was the count for Admin / System Owner. "
            "The register also has a System Administrator scope. See Scope inventory."
        ),
    )
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=8)
    ws.cell(row=note_row, column=1).font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.cell(row=note_row, column=1).alignment = WRAP
    ws.row_dimensions[note_row].height = 32
    widths = [36, 36, 18, 20, 28, 42, 36, 40]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = "A3:H23"
    ws.print_title_rows = "3:3"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def build_scope_inventory(wb, rows):
    ws = wb["Scope inventory"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Every persona and scope on the register"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Task counts are COUNTIF formulas. Scope class is assigned by this review."
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    headers = ["Persona / Scope", "Scope class", "Tasks"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = CENTER
    ranked = Counter(row[2] for row in rows).most_common()
    class_by_persona = {}
    for row in rows:
        class_by_persona[row[2]] = row[13]
    for idx, (persona, _count) in enumerate(ranked, start=4):
        ws.cell(row=idx, column=1, value=persona)
        ws.cell(row=idx, column=2, value=class_by_persona[persona])
        ws.cell(row=idx, column=3, value=f'=COUNTIF(TaskRegister[Persona / Scope],A{idx})')
        for col in range(1, 4):
            cell = ws.cell(row=idx, column=col)
            cell.font = BOLD_FONT if col == 3 else DATA_FONT
            cell.alignment = CENTER if col == 3 else WRAP
            cell.border = THIN
        ws.row_dimensions[idx].height = 20
    last = 3 + len(ranked)
    ws.cell(row=last + 1, column=1, value="Personas and scopes")
    ws.cell(row=last + 1, column=3, value=f"=COUNTA(A4:A{last})")
    ws.cell(row=last + 1, column=1).font = BOLD_FONT
    ws.cell(row=last + 1, column=3).font = BOLD_FONT
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 12
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:C{last}"
    ws.print_title_rows = "3:3"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def write_review_sheet(ws, title, headers, data, widths):
    ws.sheet_view.showGridLines = False
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 28
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = WRAP
    for r_idx, record in enumerate(data, start=4):
        for c_idx, value in enumerate(record, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.font = BOLD_FONT if c_idx == 1 else DATA_FONT
            cell.alignment = WRAP
            cell.border = THIN
        ws.row_dimensions[r_idx].height = 48
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{get_column_letter(len(headers))}{3 + len(data)}"
    ws.print_title_rows = "3:3"
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.right.text = "Page &P of &N"


def build_narrative_sheets(wb):
    target = "Hypothesis until a pilot confirms it. Not a measured result."
    competitive = [
        ("Vendor bill inwarding", "Manual line entry in Tally or Vyapar.", "Slow entry and HSN or tax typos.", "Photo extraction that fills bill lines.", "Saves about two hours a day and removes entry error.", f"{target} Extraction quality was not measured in this review."),
        ("Counter checkout", "Desktop menus or a slow web screen.", "Queues at peak hour.", "Keyboard POS with an IndexedDB catalog cache.", "Checkout falls from 45 seconds to 12 seconds and the counter handles 100 checkouts a minute.", f"{target} IndexedDB draft cache exists. The 12-second and 100-per-minute figures were not measured. F6 is UPI, not a universal hold key."),
        ("GSTR-2B matching", "Spreadsheet lookup or exact invoice-number match.", "Fails on punctuation and date differences.", "Fuzzy party and invoice matching.", "Reclaims all eligible credit and saves Rs 50,000 a year.", f"{target} Do not treat the rupee figure as a customer result."),
        ("Debtor follow-up", "Phone calls or a generic reminder.", "Reminders get ignored.", "A cadence of reminders with a UPI link.", "Debtor days fall by 35 percent.", target),
        ("Growth funnels", "A separate CRM or a sheet.", "Leads are not tied to cash.", "Web lead form, dedupe, assignment, and campaign cost.", "Lead conversion rises by 45 percent.", f"{target} Campaign, funnel, and lead-form APIs exist in the product. The conversion figure was not measured."),
        ("Referral loop", "Verbal referrals.", "No record of who referred whom.", "Referral codes and a reward after the first paid invoice.", "Acquisition at zero cost.", f"{target} Referral code and reward APIs exist. Zero-cost acquisition is a slogan, not a result."),
        ("Complaint to note", "Phone calls and handwritten adjustments.", "Duplicate credit notes.", "Complaint actions that create a credit note, return, or supplier debit note.", "Disputes close five times faster.", f"{target} Complaint-to-document APIs exist. The speed multiple was not measured."),
        ("Replenishment", "A static reorder point.", "Stockouts and dead stock.", "A burn-rate forecast that drafts a purchase order.", "No stockouts and 40 percent less dead stock.", target),
        ("Cash forecast", "A historical profit and loss.", "The owner cannot see upcoming cash.", "A 30/60/90 cash simulator.", "Prevents overdrafts and dishonoured cheques.", target),
        ("Delivery proof", "Paper challans.", "Cash and cartons go missing.", "A driver PWA with proof of delivery and route margin.", "No delivery shrinkage.", target),
        ("Customer self-service", "Print, scan, and email.", "Customers call for a statement.", "A WhatsApp invoice link with a ledger and UPI pay.", "Removes 80 percent of support calls.", target),
        ("Tally migration", "Rebuilding the chart of accounts by hand.", "Fear of losing history.", "A backup import of masters and three years of history in 15 minutes.", "Migration without downtime.", f"{target} A 15-minute full-history import was not verified."),
    ]
    write_review_sheet(
        wb["Competitive"],
        "Competitive position",
        ["Capability", "Market baseline", "Competitor pain", "BizBoard claim", "Stated customer impact", "Review"],
        competitive,
        [24, 36, 36, 42, 40, 46],
    )

    ux_rows = [
        ("Visibility of system status", "WebSocket progress on CSV import.", "A large file looks frozen.", "A row counter and an ETA.", "Less refreshing.", "Mechanism not found. No WebSocket import-progress channel was found."),
        ("Match the real world", "Khata, udhar, godown, and challan in the interface.", "Western ledger words.", "Hindi, Gujarati, and Tamil UI.", "No learning curve.", "Partial. English and Hindi catalogs exist. Locales gu and ta are stored and then forced back to English."),
        ("User control", "A 10-second undo on delete.", "A clerk deletes a large draft.", "Undo restores the cart.", "No retyping.", "Not re-verified in this review."),
        ("Consistency", "The same F-keys and Ctrl+K on every screen.", "Keys change between screens.", "One map on every screen.", "Touch-typing billing.", "Partial. POS has its own F-key map. There is no Ctrl+K palette, and the map is not shared by every screen."),
        ("Error prevention", "Row locks and type-to-confirm.", "Two clerks sell the last unit.", "The stock row locks and delete requires typing DELETE.", "No negative stock.", "Type-to-confirm was not found. Stock locking was not re-tested here."),
        ("Recognition", "A credit pill and a rack locator.", "The clerk forgets a balance or a bin.", "A badge and a shelf tag such as Aisle B.", "Less recall.", "location_tag was not found. The credit badge was not re-tested."),
        ("Flexibility", "Hold and recall on F6, plus grid edit.", "A customer steps away.", "Hold on tab 2 and recall with one key.", "The queue keeps moving.", "Incorrect hotkey. Hold is F8. F6 tenders UPI. F9 recalls when several sessions exist."),
        ("Minimal screen", "Drawers and Shift+P privacy mode.", "Too many fields, and bystanders can see figures.", "Privacy mode masks rupees.", "A quieter screen.", "Shift+P privacy mode was not found."),
        ("Recover from errors", "A GST banner with a one-click tax split.", "A raw tax-mismatch error.", "The banner offers CGST/SGST to IGST.", "The clerk is not blocked.", "Not re-verified in this review."),
        ("Help", "Tooltips, a first-run list, and an assistant.", "A new merchant cannot file GSTR-1.", "A walkthrough and a 95 percent first-run completion rate.", "Self-serve setup.", "The 95 percent figure is a hypothesis until a pilot confirms it."),
    ]
    write_review_sheet(
        wb["UX and recovery"],
        "UX and recovery",
        ["Heuristic", "Claimed pattern", "Failure addressed", "Claimed recovery", "Claimed effect", "Review"],
        ux_rows,
        [28, 40, 36, 40, 28, 50],
    )

    security_rows = [
        ("Multi-tenant isolation", "PostgreSQL row-level security with the app.company_id setting.", "No cross-tenant reads.", "Shared-database scale.", "A cross-tenant SQL injection suite in CI.", "Confirmed in part. RLS policies and the app.company_id setting exist. This review did not confirm a SQL injection suite."),
        ("Least privilege", "Role permissions and field-level cost masking.", "Clerks cannot see margin.", "Safe rollout to field staff.", "Permission tests.", "Role permissions exist. Field-level cost masking was not re-tested."),
        ("Export control", "An export permission and IP allow list.", "A departing employee cannot export the customer list.", "Trade secrets stay in the tenant.", "An audit row for every export.", "Not re-verified in this review."),
        ("Audit immutability", "Append-only ledgers and a SHA-256 hash chain.", "Records stand up under MCA Rule 11(g) and Section 65B.", "A defensible file.", "A checksum job with no gaps.", "Partial. SHA-256 is used elsewhere. No hash chain and no django-simple-history were found. Do not cite Section 65B from this note alone."),
        ("Session and sign-in", "TOTP, Redis JWT revocation, and idle timeout.", "Stolen passwords and unattended counters.", "A control a bank integration can rely on.", "An OWASP scan in GitHub Actions.", "TOTP was not found. The OWASP scan claim was not re-verified."),
        ("Subscriptions", "Razorpay subscriptions, GST invoices, and dunning.", "Fees collect themselves.", "No manual billing.", "Webhook tests for success, failure, and upgrade.", "Razorpay code exists. The full subscription, dunning, and GST-invoice loop was not confirmed."),
        ("Plan quotas", "A validator on invoices, SKUs, and seats that raises PlanQuotaExceeded.", "Free, Pro, and Enterprise stay distinct.", "Upsell as usage grows.", "A pre-save validator.", "Partial. plan_quota_exceeded exists as a help code. There is no PlanQuotaExceeded exception."),
        ("Tenant export", "One click exports the tenant to a ZIP.", "No lock-in.", "Easier purchase decision.", "An automated export test.", "Not re-verified in this review."),
        ("Backup", "WAL archiving and a daily encrypted pg_dump to S3.", "Point-in-time recovery.", "A 99.9 percent uptime SLA.", "A daily restore test.", "The 99.9 percent SLA is an operating target, not a control found in the product. A shipped PITR job was not confirmed."),
    ]
    write_review_sheet(
        wb["Security and SaaS"],
        "Security and SaaS",
        ["Dimension", "Claimed mechanism", "Objective", "Commercial claim", "Claimed verification", "Review"],
        security_rows,
        [24, 44, 36, 32, 40, 52],
    )


def build_priority_sheet(wb, rows):
    ws = wb["Priority decisions"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Priority decisions in this review"
    ws["A1"].font = TITLE_FONT
    changed = [row for row in rows if "The previous workbook had" in row[15] and not row[15].startswith("Kept ")]
    kept = [row for row in rows if row[15].startswith("Kept ")]
    ws["A2"] = (
        f"{len(changed)} tasks changed from the previous workbook. "
        f"{len(kept)} tasks stay at a priority that differs from the authored value "
        "because the task action names a statutory control or a polish item."
    )
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.merge_cells("A2:F2")
    headers = ["Task ID", "Task", "Authored priority", "Priority now", "Previous workbook", "Decision"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = CENTER
    # Previous priority is embedded at the start of the decision sentence for restored rows.
    # Recover it from the decision text when present; otherwise leave the current value.
    for idx, row in enumerate(changed, start=4):
        previous = ""
        decision = row[15]
        marker = "The previous workbook had "
        if marker in decision:
            previous = decision.split(marker, 1)[1].split(".", 1)[0].split(" ", 1)[0]
        values = [row[0], row[4], row[14], row[9], previous, decision]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=idx, column=col, value=value)
            cell.font = DATA_FONT
            cell.alignment = WRAP
            cell.border = THIN
        ws.row_dimensions[idx].height = 30
    last = 3 + len(changed)
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:F{last}"
    ws.print_title_rows = "3:3"
    widths = [14, 55, 20, 16, 22, 70]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS[:12])
        for row in rows:
            writer.writerow(row[:12])


def build_flows(wb):
    ws = wb["Flows"]
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Flows"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        "Task counts are COUNTIF formulas on Task Register. "
        "The first flows are sequenced steps. The rest group older tasks by category."
    )
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="546E7A")
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 28
    headers = ["Flow ID", "Flow name", "Module", "Tasks", "What it covers", "Limit"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
        cell.alignment = CENTER
    records = []
    seen = set()
    for flow_id, name, module, covers, limit in FLOW_CATALOG:
        records.append((flow_id, name, module, covers, limit))
        seen.add(flow_id)
    for _category, (flow_id, name, module) in CATEGORY_FLOWS.items():
        if flow_id in seen:
            continue
        records.append((
            flow_id,
            name,
            module,
            "Tasks already filed under this category.",
            "Grouped from the category. Flow step is blank.",
        ))
        seen.add(flow_id)
    for idx, (flow_id, name, module, covers, limit) in enumerate(records, start=4):
        values = [
            flow_id,
            name,
            module,
            f'=COUNTIF(TaskRegister[Flow ID],A{idx})',
            covers,
            limit,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=idx, column=col, value=value)
            cell.font = BOLD_FONT if col in {1, 4} else DATA_FONT
            cell.alignment = CENTER if col in {1, 3, 4} else WRAP
            cell.border = THIN
        ws.row_dimensions[idx].height = 36
    last = 3 + len(records)
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:F{last}"
    ws.print_title_rows = "3:3"
    widths = [14, 40, 16, 12, 62, 62]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_properties.tabColor = "0277BD"


def build_workbook(rows):
    wb = openpyxl.Workbook()
    # Create sheets in reading order. Task Register is filled first so table
    # formulas on later sheets resolve when Excel opens the file.
    names = [
        "How to read",
        "Review findings",
        "Coverage Dashboard",
        "Task Register",
        "Flows",
        "Baseline tasks",
        "Newly Added Tasks",
        "Growth OS",
        "Added flows",
        "Persona Coverage",
        "Scope inventory",
        "Competitive",
        "UX and recovery",
        "Security and SaaS",
        "Priority decisions",
    ]
    wb.active.title = names[0]
    for name in names[1:]:
        wb.create_sheet(name)

    register = wb["Task Register"]
    fill_header(register, HEADERS)
    paint_task_rows(register, rows)
    add_task_table(register, "TaskRegister", len(rows))
    register.sheet_properties.tabColor = NAVY

    slices = {
        "Baseline tasks": [row for row in rows if row[12] == "Baseline"],
        "Newly Added Tasks": [row for row in rows if row[12] == "Strategic expansion"],
        "Growth OS": [row for row in rows if row[12] == "Growth OS"],
        "Added flows": [row for row in rows if row[12] == "Added flows"],
    }
    colors = {
        "Baseline tasks": "455A64",
        "Newly Added Tasks": "0D47A1",
        "Growth OS": "0277BD",
        "Added flows": "00695C",
    }
    for name, subset in slices.items():
        ws = wb[name]
        fill_header(ws, HEADERS, colors[name])
        paint_task_rows(ws, subset)
        add_task_table(ws, name.replace(" ", "")[:20], len(subset))
        ws.sheet_properties.tabColor = colors[name]

    build_flows(wb)
    build_os_sheets(wb, rows)
    build_how_to_read(wb, rows)
    build_findings(wb)
    build_dashboard(wb, rows)
    build_persona(wb)
    build_scope_inventory(wb, rows)
    build_narrative_sheets(wb)
    build_priority_sheet(wb, rows)

    wb.properties.title = "BizBoard reviewed task register"
    wb.properties.subject = "770-task register plus an OS control layer that is not yet proven"
    wb.properties.creator = "BizBoard task register review"
    wb.calculation.calcMode = "auto"
    wb.calculation.fullCalcOnLoad = True
    return wb


def main():
    rows, _operational = load_rows()
    expected = 740 + len(ADDITIONAL_FLOW_TASKS)
    if len(rows) != expected:
        raise SystemExit(f"Expected {expected} tasks, found {len(rows)}")
    ids = [row[0] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate task ids")

    wb = build_workbook(rows)
    wb.save(ENHANCED_XLSX)
    wb.save(UNIVERSE_XLSX)
    write_csv(ENHANCED_CSV, rows)
    write_csv(UNIVERSE_CSV, rows)

    print(f"Tasks {len(rows)}")
    print("Status", dict(Counter(row[10] for row in rows)))
    print("Review", dict(Counter(row[16] for row in rows)))
    print("Priority", dict(Counter(row[9] for row in rows)))
    print("Release gate", dict(Counter(row[28] for row in rows)))
    print("Work status", dict(Counter(row[35] for row in rows)))
    print("Scope", dict(Counter(row[13] for row in rows)))
    changed = sum(
        1 for row in rows
        if "The previous workbook had" in row[15] and not row[15].startswith("Kept ")
    )
    kept = sum(1 for row in rows if row[15].startswith("Kept "))
    print(f"Priority changes {changed}; kept above authored priority {kept}")
    print("Wrote", ENHANCED_XLSX)


if __name__ == "__main__":
    main()

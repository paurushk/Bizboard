# -*- coding: utf-8 -*-
"""OS control layer for the task register.

Feature expansion stays frozen. These sheets record what must be proved
before a task is called OS-ready. Empty measurements stay empty.
"""
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

NAVY = "1F497D"
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color=NAVY)
DATA_FONT = Font(name="Calibri", size=10)
BOLD_FONT = Font(name="Calibri", size=10, bold=True)
WRAP = Alignment(vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
THIN = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)
HEADER_FILL = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
NOTE_FONT = Font(name="Calibri", size=10, italic=True, color="546E7A")

NOT_VERIFIED = "Not verified"
NOT_MEASURED = "Not measured"
NOT_ENTERED = "Not entered"

RUN = {
    "Customer-to-Cash",
    "Inventory Lifecycle",
    "Procure-to-Pay",
    "Payments & Reconciliation",
    "Returns / Complaints / After-Sales",
    "Operations, Fleet & Delivery",
    "Workshop Job",
    "Manufacturing",
    "Multi-Godown / Multi-Store",
    "Project Billing",
}
CONTROL = {
    "GST / Tax / Compliance",
    "Receivables & Payables",
    "Reporting & Business Intelligence",
    "Import / Export / Period Close",
    "Finance & Fixed Assets",
    "Security / Exception / Recovery",
    "Payroll & Statutory Dues",
}
VERTICAL = {
    "Payroll & Statutory Dues",
    "Workshop Job",
    "Manufacturing",
    "Project Billing",
    "Insurance Distribution",
}


def os_layer(category):
    if category in RUN:
        return "RUN"
    if category in CONTROL:
        return "CONTROL"
    if str(category).startswith("Growth OS") or category in {
        "Sales / CRM / Customer Lifecycle",
        "Insurance Distribution",
    }:
        return "GROW"
    return "KERNEL"


def capability_class(row):
    priority = row[9]
    task_type = row[1]
    category = row[3]
    if priority == "P3" or task_type == "D":
        return "Future"
    if category in VERTICAL:
        return "Vertical extension"
    if task_type == "SaaS":
        return "Adjacent"
    if task_type in {"UX", "I"}:
        return "Differentiator"
    return "Core"


def canonical_role(persona):
    text = str(persona or "")
    if text.startswith("System /") or text.startswith("System"):
        return "System"
    if text == "Multiple / Cross-persona":
        return "Cross-persona"
    if text in {"Statutory Compliance", "AI & Differentiation", "Architecture & Platform",
                "Hardware Integrations", "External Integrations", "All Roles",
                "Platform / SaaS Admin"}:
        return "Platform scope"
    if "Growth" in text or text in {"Inside Sales / Web Lead Specialist", "Customer Success / Growth Lead"}:
        return "Growth"
    if text in {"Accountant / GST Operator", "In-house Accountant", "External CA / Statutory Auditor"}:
        return "Accountant"
    if text in {"Inventory Manager", "Single-Godown Distributor"} or "Warehouse" in text or "Godown" in text:
        return "Stock"
    if text in {"Salesperson", "Field Salesperson", "Sales Representative", "Sales Manager / Head of Sales",
                "Sales Manager / Team Lead"}:
        return "Sales"
    if "Purchase" in text:
        return "Buyer"
    if "Delivery" in text or "Driver" in text:
        return "Driver"
    if text in {"Customer", "Supplier"} or text.startswith("Vendor"):
        return "External party"
    if "Admin" in text or text == "System Administrator":
        return "Admin"
    if text == "Assembly / Production Supervisor":
        return "Production"
    if text == "Workshop Supervisor":
        return "Service"
    if text in {"Business Owner", "Kirana Shop Owner", "Gully Vendor / Small Retailer", "Medical Shop",
                "Multi-Shop Owner", "Managing Proprietor", "Distributor", "Multi-Godown Distributor"}:
        return "Owner"
    return "Named role"


_IMPACT = {"High": 3, "Medium": 2, "Low": 1}
_CLASS_WEIGHT = {
    "Core": 3,
    "Vertical extension": 2,
    "Differentiator": 2,
    "Adjacent": 1,
    "Future": 1,
}


def risk_score(row):
    """Failure impact × compliance impact × capability class. Not a copy of Priority."""
    return (
        _IMPACT[failure_impact(row)]
        * _IMPACT[compliance_impact(row)]
        * _CLASS_WEIGHT[capability_class(row)]
    )


def criticality(row):
    score = risk_score(row)
    if score >= 18:
        return "Critical"
    if score >= 9:
        return "High"
    if score >= 4:
        return "Medium"
    return "Low"


def release_gate(row):
    """MVP is every current P0. Pilot is core RUN/CONTROL work at P1. The rest is Later."""
    if row[9] == "P0":
        return "MVP"
    if row[9] == "P1" and capability_class(row) == "Core" and os_layer(row[3]) in {"RUN", "CONTROL"}:
        return "Pilot"
    return "Later"


def work_status(status, outcome):
    if status == "Mechanism not found" or outcome == "Mechanism not found":
        return "Gap"
    if status == "Partial" or outcome == "Partial":
        return "Built - partial"
    if outcome == "Code symbol found" or status in {"In product", "Code Complete & Verified"}:
        return "Built - unverified"
    return "Claimed - unverified"


def failure_impact(row):
    category = row[3]
    if category in {
        "GST / Tax / Compliance",
        "Payments & Reconciliation",
        "Inventory Lifecycle",
        "Finance & Fixed Assets",
        "Receivables & Payables",
        "Payroll & Statutory Dues",
    }:
        return "High"
    if row[9] == "P3":
        return "Low"
    return "Medium"


def compliance_impact(row):
    category = row[3]
    if category in {"GST / Tax / Compliance", "Payroll & Statutory Dues", "Finance & Fixed Assets"}:
        return "High"
    if category in {"Security / Exception / Recovery", "Receivables & Payables"}:
        return "Medium"
    return "Low"


def code_evidence(status, outcome):
    if status == "Mechanism not found" or outcome == "Mechanism not found":
        return "Not in code"
    if status == "Partial" or outcome == "Partial":
        return "Partial"
    if outcome == "Code symbol found" or status == "In product":
        return "Cited in code"
    if status == "Code Complete & Verified":
        return "Cited in code"
    return "Not independently checked"


def os_fields(row, outcome, evidence=None):
    """Columns added beside the existing validation status. None are a pass."""
    evidence = evidence or {}
    return (
        os_layer(row[3]),
        capability_class(row),
        canonical_role(row[2]),
        criticality(row),
        failure_impact(row),
        compliance_impact(row),
        release_gate(row),
        code_evidence(row[10], outcome),
        NOT_VERIFIED,
        NOT_VERIFIED,
        NOT_VERIFIED,
        NOT_VERIFIED,
        "No",
        work_status(row[10], outcome),
        row[9],
        risk_score(row),
        evidence.get("Owner", ""),
        evidence.get("Target date", ""),
        evidence.get("Estimate days", ""),
        evidence.get("Depends on", ""),
        evidence.get("Blocked by", ""),
        evidence.get("Test case ID", ""),
        evidence.get("Last verified", ""),
        evidence.get("Verified by", ""),
        evidence.get("Verification result") or "Not run",
    )


OS_HEADERS = [
    "OS layer",
    "Capability class",
    "Canonical role",
    "Business criticality",
    "Failure impact",
    "Compliance impact",
    "Release gate",
    "Code evidence",
    "Integrity evidence",
    "Recovery evidence",
    "Security evidence",
    "Concurrency evidence",
    "OS ready",
    "Work status",
    "Proposed priority",
    "Risk score",
    "Owner",
    "Target date",
    "Estimate days",
    "Depends on",
    "Blocked by",
    "Test case ID",
    "Last verified",
    "Verified by",
    "Verification result",
]


def _heading(ws, title, note):
    ws.sheet_view.showGridLines = False
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 28
    ws["A2"] = note
    ws["A2"].font = NOTE_FONT
    ws["A2"].alignment = WRAP
    ws.merge_cells("A2:G2")
    ws.row_dimensions[2].height = 32


def _write_table(ws, headers, records, widths, table_name):
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
    for r_idx, record in enumerate(records, start=4):
        for c_idx, value in enumerate(record, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.font = DATA_FONT
            cell.alignment = WRAP
            cell.border = THIN
        ws.row_dimensions[r_idx].height = 36
    last = 3 + len(records)
    ref = f"A3:{get_column_letter(len(headers))}{last}"
    table = Table(displayName=table_name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=False)
    ws.add_table(table)
    ws.freeze_panes = "A4"
    ws.print_title_rows = "3:3"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width


def build_disposition(wb):
    ws = wb.create_sheet("Review disposition", 2)
    _heading(
        ws,
        "Review disposition",
        "Comments from the SMB OS gap plan. Accepted items are in the sheets that follow. Rejected items were not applied.",
    )
    headers = ["Comment", "Decision", "Why"]
    rows = [
        ("Freeze feature expansion", "Accepted", "No new feature tasks were added. The register stays at 770."),
        ("OS layers RUN, CONTROL, GROW, and KERNEL", "Accepted", "Each task has an OS layer derived from its category."),
        ("Business event, state, integrity, failure, concurrency, security, integration, SLA, and customer-evidence sheets", "Accepted", "The matrices exist. Their proof columns are Not verified or Not measured."),
        ("Capability evidence register for Partial and Mechanism not found", "Accepted", "Built from the task rows. Open gaps stay open."),
        ("OS readiness gates G1 to G5", "Accepted", "Defined on OS readiness. No task is marked OS ready."),
        ("Extra priority dimensions", "Accepted", "Criticality, failure impact, compliance impact, and release gate sit beside Priority. Priority itself was not rewritten."),
        ("Canonical role", "Accepted", "A rollup column. Persona / Scope is unchanged, so kirana, distributor, and medical context remain."),
        ("Capability class for scope governance", "Accepted", "Core, vertical extension, differentiator, adjacent, or future. This is a label, not a roadmap decision."),
        ("Replace the single validation status", "Rejected", "Validation Status stays as the author and review label. Evidence columns sit beside it. Replacing it would hide the earlier correction."),
        ("Hide later work and merge cross-persona rows", "Rejected", "Later rows stay in the register. Founder view and Release gate separate them. Cross-persona rows were not merged."),
        ("Fill owners, dates, and test results", "Accepted as blanks", "Owner, target date, estimate, and test columns exist. They stay blank until a person or a passing test fills them."),
        ("Fill SLA actuals, P95, P99, and customer results", "Rejected", "Those figures were not measured. Illustrative numbers on the competitive sheet are not SLAs."),
        ("Mark capabilities OS ready", "Rejected", "OS ready is No on every row until the gates have evidence."),
        ("Implement the 10 missing mechanisms in this pass", "Rejected", "The plan also says to freeze features. The claims stay open in Capability evidence."),
        ("Delete or merge the 770 tasks as duplicates", "Rejected", "Cross-persona rows are workflow steps with their own IDs. Merging them without a case-by-case review would drop traceability."),
        ("Collapse owner personas into one role", "Rejected", "Canonical role groups them for counting. The operating context stays on the task."),
        ("Treat customer and supplier masters as document state machines", "Rejected", "They are master records. Credit control is a rule, not a DRAFT/COMPLETED status."),
    ]
    _write_table(ws, headers, rows, [42, 16, 78], "ReviewDisposition")


def build_architecture(wb):
    ws = wb.create_sheet("OS architecture", 3)
    _heading(
        ws,
        "OS architecture",
        "RUN operates the business. CONTROL keeps the books and the rules. GROW finds and keeps customers. KERNEL is identity, masters, and platform. Counts are formulas.",
    )
    headers = ["Layer", "What it covers", "Tasks"]
    layers = [
        ("RUN", "Sales, purchases, inventory, payments, workshop, manufacturing, delivery, project billing."),
        ("CONTROL", "GST, receivables and payables, payroll dues, reports, period close, fixed assets, security and recovery."),
        ("GROW", "CRM, campaigns, referrals, insurance distribution, customer intelligence."),
        ("KERNEL", "Master data, integrations, and platform scopes that are not themselves a business flow."),
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
    for idx, (layer, covers) in enumerate(layers, start=4):
        ws.cell(row=idx, column=1, value=layer).font = BOLD_FONT
        ws.cell(row=idx, column=2, value=covers).font = DATA_FONT
        ws.cell(row=idx, column=3, value=f'=COUNTIF(TaskRegister[OS layer],A{idx})').font = BOLD_FONT
        for col in range(1, 4):
            ws.cell(row=idx, column=col).alignment = WRAP
            ws.cell(row=idx, column=col).border = THIN
        ws.row_dimensions[idx].height = 32
    ws.cell(row=9, column=1, value="Kernel contents named in the plan").font = BOLD_FONT
    kernel = (
        "Identity, master data, business events, document state, ledger, rules, workflow, "
        "audit, notifications, automation, and intelligence. This sheet names them. "
        "It does not certify that they behave as one kernel."
    )
    ws.cell(row=10, column=1, value=kernel).font = DATA_FONT
    ws.cell(row=10, column=1).alignment = WRAP
    ws.merge_cells("A10:C10")
    ws.row_dimensions[10].height = 36
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 88
    ws.column_dimensions["C"].width = 14
    ws.freeze_panes = "A4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def build_events(wb):
    ws = wb.create_sheet("Business events", 4)
    _heading(
        ws,
        "Business event matrix",
        "State names below are the document enums in code. Downstream effects and reversals are not certified. Proven is No until a cross-domain check exists.",
    )
    headers = ["Event", "State change in code", "Downstream effects expected", "Reversal in code", "Audit", "Proven"]
    rows = [
        ("Sale / sales invoice", "SalesInvoice DRAFT → COMPLETED or CANCELLED", "Stock, receivable, tax, and ledger", "CANCELLED", NOT_VERIFIED, "No"),
        ("Purchase invoice", "PurchaseInvoice DRAFT → COMPLETED or CANCELLED", "Stock, payable, input tax, and ledger", "CANCELLED", NOT_VERIFIED, "No"),
        ("Goods receipt", "GoodsReceipt DRAFT → COMPLETED or CANCELLED", "Stock on hand", "CANCELLED", NOT_VERIFIED, "No"),
        ("Sales order", "SalesOrder DRAFT → CONFIRMED → CONVERTED or CANCELLED", "Reservation, then a draft invoice", "CANCELLED", NOT_VERIFIED, "No"),
        ("Purchase order", "PurchaseOrder DRAFT → CONVERTED or CANCELLED", "A draft purchase invoice", "CANCELLED", NOT_VERIFIED, "No"),
        ("Customer receipt", "Receipt POSTED, REFUNDED, or VOIDED", "Receivable and bank or cash", "VOIDED or REFUNDED", NOT_VERIFIED, "No"),
        ("Supplier payment", "Supplier payment POSTED or VOIDED", "Payable and bank or cash", "VOIDED", NOT_VERIFIED, "No"),
        ("Sales return", "SalesReturn DRAFT → COMPLETED or CANCELLED", "Stock and output tax", "CANCELLED", NOT_VERIFIED, "No"),
        ("Purchase return", "PurchaseReturn DRAFT → COMPLETED or CANCELLED", "Stock and input tax", "CANCELLED", NOT_VERIFIED, "No"),
        ("Sales credit note", "SalesCreditNote DRAFT → COMPLETED or CANCELLED", "Receivable and output tax", "CANCELLED", NOT_VERIFIED, "No"),
        ("Sales debit note", "SalesDebitNote DRAFT → COMPLETED or CANCELLED", "Receivable", "CANCELLED", NOT_VERIFIED, "No"),
        ("Purchase debit note", "PurchaseDebitNote DRAFT → COMPLETED or CANCELLED", "Payable and input tax", "CANCELLED", NOT_VERIFIED, "No"),
        ("Stock adjustment", "Stock movement, not a DRAFT/COMPLETED document", "On-hand quantity and value", "A reversing movement", NOT_VERIFIED, "No"),
        ("Stock transfer", "Transfer between warehouses", "Source and destination on-hand", "Cancel or reverse the transfer", NOT_VERIFIED, "No"),
        ("Journal", "JournalEntry exists. This matrix does not treat it as a document status machine.", "Ledger only", "A reversing journal", NOT_VERIFIED, "No"),
        ("Bank reconciliation", "BankReconSession OPEN or CLOSED", "Match of statement lines to ledger", "Session can stay open", NOT_VERIFIED, "No"),
    ]
    _write_table(ws, headers, rows, [28, 55, 42, 36, 18, 12], "BusinessEvents")


def build_states(wb):
    ws = wb.create_sheet("State machines", 5)
    _heading(
        ws,
        "State machine matrix",
        "Statuses are copied from the model enums. Allowed, forbidden, rollback, and automated transition tests are not verified in this register.",
    )
    headers = ["Entity", "Statuses in code", "Actor", "Transition tests", "Rollback", "Proven"]
    rows = [
        ("Sales invoice", "DRAFT, COMPLETED, CANCELLED", "Billing clerk", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Sales order", "DRAFT, CONFIRMED, CONVERTED, CANCELLED", "Salesperson", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Quotation", "DRAFT, CONVERTED, CANCELLED", "Salesperson", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Purchase order", "DRAFT, CONVERTED, CANCELLED", "Purchase manager", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Purchase invoice", "DRAFT, COMPLETED, CANCELLED", "Purchase manager", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Goods receipt", "DRAFT, COMPLETED, CANCELLED", "Stores", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Customer receipt", "POSTED, REFUNDED, VOIDED", "Cashier", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Supplier payment", "POSTED, VOIDED", "Accountant", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Sales return", "DRAFT, COMPLETED, CANCELLED", "Billing clerk", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Purchase return", "DRAFT, COMPLETED, CANCELLED", "Purchase manager", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Credit and debit notes", "DRAFT, COMPLETED, CANCELLED on the sales and purchase note models", "Accountant", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Delivery challan", "DRAFT, COMPLETED, CANCELLED", "Dispatcher", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Work order", "DRAFT, RELEASED, COMPLETED, CANCELLED", "Production supervisor", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Job card", "DRAFT, IN_PROGRESS, INVOICED, CANCELLED", "Service advisor", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Pay run", "DRAFT, COMPLETED", "Payroll clerk", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Stock balance", "Not a status enum. on_hand and reserved; available is on_hand minus reserved.", "Stores", NOT_VERIFIED, NOT_VERIFIED, "No"),
        ("Customer and supplier", "Master records. Not a document status machine.", "Accountant", "Not applicable", "Not applicable", "No"),
        ("GST e-invoice and e-way bill", "Product areas exist. The full portal status graph is not copied here.", "Accountant", NOT_VERIFIED, NOT_VERIFIED, "No"),
    ]
    _write_table(ws, headers, rows, [32, 62, 24, 20, 18, 12], "StateMachines")


def build_integrity(wb):
    ws = wb.create_sheet("Business integrity", 6)
    _heading(
        ws,
        "Business integrity matrix",
        "A trial-balance report exists and exposes trial_balance_balanced. That is not a gate on every transaction. No invariant below is marked proven.",
    )
    headers = ["Domain", "Invariant", "Known handle in code", "Gate on every transaction", "Proven"]
    rows = [
        ("Financial", "Debits equal credits", "accounting.reports.trial_balance", "No", "No"),
        ("Financial", "Customer balance equals invoices minus receipts minus credits", "Receipt and SalesInvoice", "No", "No"),
        ("Financial", "Supplier balance equals purchases minus payments minus debits", "Supplier payment and PurchaseInvoice", "No", "No"),
        ("Financial", "Receivable total ties to open invoices", "Not established as a gate", "No", "No"),
        ("Financial", "Payable total ties to open purchases", "Not established as a gate", "No", "No"),
        ("Inventory", "Opening plus receipts minus issues plus adjustments equals closing", "Stock movements", "No", "No"),
        ("Inventory", "On-hand does not go negative unless the tenant allows it", "Negative-stock policy is described on existing tasks", "No", "No"),
        ("Inventory", "Reserved plus available equals on-hand", "StockBalance.reserved; available is on_hand minus reserved", "No", "No"),
        ("Inventory", "Batch and serial quantities tie to the balance", "Batch and serial models exist", "No", "No"),
        ("Inventory", "Warehouse totals tie to the company total", "Not established as a gate", "No", "No"),
    ]
    _write_table(ws, headers, rows, [16, 62, 55, 28, 12], "BusinessIntegrity")


def build_failure(wb):
    ws = wb.create_sheet("Failure and recovery", 7)
    _heading(
        ws,
        "Failure and recovery matrix",
        "Refund posting uses an idempotency key on the gateway refund outbox. That single key does not prove the cases below.",
    )
    headers = ["Case", "What must remain true", "Evidence", "Proven"]
    rows = [
        ("Create, post, update, cancel, return, reverse", "Cancel and reverse put stock, tax, and ledger back", NOT_VERIFIED, "No"),
        ("Retry and duplicate submit", "A second submit does not post twice", "uniq_refund_outbox_per_idempotency_key covers one refund path only", "No"),
        ("Inventory updates and the ledger write fails", "Neither side is left posted alone", NOT_VERIFIED, "No"),
        ("Payment succeeds and the callback is late", "The receipt is not doubled when the callback arrives", NOT_VERIFIED, "No"),
        ("GST portal fails after the document is saved", "The local document shows the portal failure", NOT_VERIFIED, "No"),
        ("Webhook delivered twice", "The second delivery is a no-op", NOT_VERIFIED, "No"),
        ("Browser closes during checkout", "The draft or outbox can be recovered", "IndexedDB invoice draft cache exists. Recovery of a half-posted bill is not verified", "No"),
        ("Background job stops halfway", "The job can be retried without a second posting", NOT_VERIFIED, "No"),
    ]
    _write_table(ws, headers, rows, [55, 55, 62, 12], "FailureRecovery")


def build_concurrency(wb):
    ws = wb.create_sheet("Concurrency", 8)
    _heading(
        ws,
        "Concurrency matrix",
        "Some stock paths take a row lock. That is not a pass for these races. No scenario here is marked proven.",
    )
    headers = ["Race", "Harm if lost", "Evidence", "Proven"]
    races = [
        "Two users sell the last unit",
        "Two users edit the same invoice",
        "Two users approve the same document",
        "Two stock transfers of the same quantity",
        "Duplicate payment submit",
        "Duplicate webhook",
        "Duplicate GST import",
        "Two goods receipts for the same order",
        "Two edits of the same customer",
        "Two stock adjustments of the same item",
    ]
    rows = [(race, "Duplicate document or a balance that does not tie", NOT_VERIFIED, "No") for race in races]
    _write_table(ws, headers, rows, [48, 55, 22, 12], "ConcurrencyMatrix")


def build_security(wb):
    ws = wb.create_sheet("Security assurance", 9)
    _heading(
        ws,
        "Security assurance matrix",
        "Row-level security policies and the app.company_id setting exist. A control is not assured until the evidence column says so. TOTP remains absent.",
    )
    headers = ["Control", "What was found", "Evidence", "Assured"]
    rows = [
        ("Tenant isolation", "Postgres RLS and app.company_id", "Policies exist. A cross-tenant test suite was not confirmed here", "No"),
        ("RBAC", "Role permissions exist", NOT_VERIFIED, "No"),
        ("Object-level authorization", "Not re-tested", NOT_VERIFIED, "No"),
        ("Session and 2FA", "No TOTP implementation", "SEC-0624 remains Mechanism not found", "No"),
        ("Audit trail", "django-simple-history is not the mechanism", "P-0115, X-0432, and P-0507 remain Partial", "No"),
        ("Hash chain", "No audit hash chain", "S-0579 remains Mechanism not found", "No"),
        ("Export permission", "Not re-tested", NOT_VERIFIED, "No"),
        ("Rate limit", "Not re-tested as a release gate", NOT_VERIFIED, "No"),
        ("Injection resistance", "Not re-tested", NOT_VERIFIED, "No"),
        ("Sensitive-data masking", "Shift+P privacy mask was not found", "UX-0591 remains Mechanism not found", "No"),
        ("Backup security", "A shipped PITR control was not confirmed", NOT_VERIFIED, "No"),
    ]
    _write_table(ws, headers, rows, [32, 48, 62, 12], "SecurityAssurance")


def build_integrations(wb):
    ws = wb.create_sheet("Integration reliability", 10)
    _heading(
        ws,
        "Integration reliability matrix",
        "Each integration must survive timeout, retry, duplicate, replay, out-of-order, partial, invalid, and unavailable responses. None of those cases are marked proven.",
    )
    headers = ["Integration", "Idempotent", "Observable", "Recoverable", "Proven"]
    names = ["GST portal", "Razorpay", "WhatsApp", "SMS", "Email", "Tally", "Banking and account aggregator", "E-invoice", "E-way bill", "Inbound webhooks"]
    rows = [(name, NOT_VERIFIED, NOT_VERIFIED, NOT_VERIFIED, "No") for name in names]
    _write_table(ws, headers, rows, [36, 18, 18, 18, 12], "IntegrationReliability")


def build_sla(wb):
    ws = wb.create_sheet("Performance SLA", 11)
    _heading(
        ws,
        "Performance SLA matrix",
        "Target, actual, P95, and P99 are blank on purpose. Figures on the competitive sheet are illustrative and are not measurements.",
    )
    headers = ["Scenario", "Dataset size", "Concurrent users", "Target", "Actual", "P95", "P99", "Pass or fail"]
    scenarios = [
        "Login", "Dashboard", "Search", "Invoice creation", "POS checkout", "Stock update",
        "Purchase posting", "Payment posting", "GST import", "Report generation",
        "Bulk import or export", "API response", "Background job",
    ]
    rows = [(name, "", "", "", "", "", "", NOT_MEASURED) for name in scenarios]
    _write_table(ws, headers, rows, [28, 16, 20, 14, 14, 12, 12, 16], "PerformanceSla")


def build_customer(wb):
    ws = wb.create_sheet("Customer evidence", 12)
    _heading(
        ws,
        "Customer evidence matrix",
        "These are hypotheses. Invoice timestamps, debtor days, and ticket counts are the sources to instrument. Baseline, experiment, and result stay empty until a pilot measures them.",
    )
    headers = ["Hypothesis", "Baseline", "Experiment", "Measurement", "Result", "Evidence"]
    hypotheses = [
        "Invoice creation time falls",
        "Reconciliation time falls",
        "Collection cycle shortens",
        "Stock accuracy rises",
        "Dead stock falls",
        "GST reconciliation effort falls",
        "User error rate falls",
        "Support tickets fall",
        "Repeat usage rises",
        "Customer retention rises",
    ]
    rows = [(item, "", "", "", NOT_MEASURED, "") for item in hypotheses]
    _write_table(ws, headers, rows, [40, 16, 18, 18, 18, 18], "CustomerEvidence")


def build_capability_evidence(wb, rows):
    ws = wb.create_sheet("Capability evidence", 13)
    _heading(
        ws,
        "Capability evidence register",
        "Open claims from the task register. Action is to keep the corrected label. They are not relabeled as supported, and they are not scheduled as new features by this sheet.",
    )
    headers = ["Task ID", "Claim", "Validation status", "Code evidence", "Action"]
    open_rows = []
    for row in rows:
        if row[10] in {"Partial", "Mechanism not found"}:
            action = (
                "Keep the corrected note. Do not mark it supported."
                if row[10] == "Partial"
                else "Keep it as not found. Do not implement it under the feature freeze."
            )
            open_rows.append((row[0], row[4], row[10], row[29], action))
    open_rows.sort(key=lambda item: item[0])
    _write_table(ws, headers, open_rows, [14, 55, 24, 22, 55], "CapabilityEvidence")


def build_readiness(wb):
    ws = wb.create_sheet("OS readiness", 14)
    _heading(
        ws,
        "OS readiness gate",
        "A task is OS ready only when every applicable gate has evidence. The register does not award that status. The count below should stay at zero until it does.",
    )
    headers = ["Gate", "Question", "Tasks passed"]
    gates = [
        ("G1 Functional", "Can the intended user finish the task?"),
        ("G2 Business integrity", "Are the downstream stock, tax, and ledger effects right?"),
        ("G3 Resilience and security", "Does it survive failure, races, and a user without permission?"),
        ("G4 User validation", "Has the SMB persona completed the workflow?"),
        ("G5 Business outcome", "Is there a measured customer result?"),
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
    for idx, (gate, question) in enumerate(gates, start=4):
        ws.cell(row=idx, column=1, value=gate).font = BOLD_FONT
        ws.cell(row=idx, column=2, value=question).font = DATA_FONT
        ws.cell(row=idx, column=3, value="Not entered").font = DATA_FONT
        for col in range(1, 4):
            ws.cell(row=idx, column=col).alignment = WRAP
            ws.cell(row=idx, column=col).border = THIN
        ws.row_dimensions[idx].height = 28
    ws.cell(row=10, column=1, value="Tasks marked OS ready").font = BOLD_FONT
    ws.cell(row=10, column=2, value='=COUNTIF(TaskRegister[OS ready],"Yes")').font = BOLD_FONT
    ws.cell(row=11, column=1, value="Tasks still not OS ready").font = DATA_FONT
    ws.cell(row=11, column=2, value='=COUNTIF(TaskRegister[OS ready],"No")').font = BOLD_FONT
    for row_idx in (10, 11):
        for col in (1, 2):
            ws.cell(row=row_idx, column=col).border = THIN
            ws.cell(row=row_idx, column=col).alignment = WRAP
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 78
    ws.column_dimensions["C"].width = 18
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def build_founder(wb):
    ws = wb.create_sheet("Founder view", 0)
    _heading(
        ws,
        "Founder view",
        "Live counts from the task register. A task is verified only when Verification result is Pass. That column is Not run until a test is linked. OS ready stays at zero until all five gates have evidence.",
    )
    headers = ["Question", "Count", "How to read it"]
    rows = [
        ("Tasks", "=COUNTA(TaskRegister[Task ID])", "The frozen universe."),
        ("MVP (current P0)", '=COUNTIF(TaskRegister[Release gate],"MVP")', "Pilot scope to approve or cut. Release gate is not frozen until you sign it."),
        ("Pilot (core P1, RUN or CONTROL)", '=COUNTIF(TaskRegister[Release gate],"Pilot")', "Comes after MVP. This is a rule, not a target of 290."),
        ("Later", '=COUNTIF(TaskRegister[Release gate],"Later")', "Hidden from the pilot board. Still in the register."),
        ("MVP with a passing test", '=COUNTIFS(TaskRegister[Release gate],"MVP",TaskRegister[Verification result],"Pass")', "Go / no-go numerator. Threshold is a decision, not a formula."),
        ("MVP with a test id", '=COUNTIFS(TaskRegister[Release gate],"MVP",TaskRegister[Test case ID],"<>")', "Linked tests that have not been scored as a pass."),
        ("Open gaps", '=COUNTIF(TaskRegister[Work status],"Gap")', "Mechanism not found. Do not claim these."),
        ("Built, only partly", '=COUNTIF(TaskRegister[Work status],"Built - partial")', "The partial claims."),
        ("Tasks with no owner", '=COUNTBLANK(TaskRegister[Owner])', "Fill owners on MVP rows first."),
        ("Tasks with no test id", '=COUNTBLANK(TaskRegister[Test case ID])', "Validation status does not fill this."),
        ("Tasks marked OS ready", '=COUNTIF(TaskRegister[OS ready],"Yes")', "Stays at zero until G1 to G5 each have evidence."),
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
    for idx, (question, formula, note) in enumerate(rows, start=4):
        ws.cell(row=idx, column=1, value=question).font = BOLD_FONT
        ws.cell(row=idx, column=2, value=formula).font = BOLD_FONT
        ws.cell(row=idx, column=3, value=note).font = DATA_FONT
        for col in range(1, 4):
            ws.cell(row=idx, column=col).alignment = WRAP
            ws.cell(row=idx, column=col).border = THIN
        ws.row_dimensions[idx].height = 32
    ws.cell(row=16, column=1, value="Four-week routine").font = TITLE_FONT
    routine = [
        "Week 1. Fill Decision owner and Decision date on P0 gap decisions. Approve or edit Proposed priority, then treat Release gate as frozen.",
        "Week 2. The compliance gaps stay open until someone builds them: admin second factor, a nightly invariant check with an alert, and an audit event test per posting action. This sheet does not mark them done.",
        "Week 3. Add one Test case ID per MVP task, money and stock and tax first. Set Verification result to Pass only when that test passes. Re-run the Postgres concurrency tests; they are still Not verified.",
        "Week 4. Fill Performance SLA actuals from a large-tenant seed, and Customer evidence from one pilot. Competitive targets stay hypotheses until then.",
    ]
    for offset, line in enumerate(routine):
        cell = ws.cell(row=17 + offset, column=1, value=line)
        cell.font = DATA_FONT
        cell.alignment = WRAP
        ws.merge_cells(start_row=17 + offset, start_column=1, end_row=17 + offset, end_column=3)
        ws.row_dimensions[17 + offset].height = 32
    ws.cell(row=22, column=1, value="Day to day").font = TITLE_FONT
    uses = [
        ("Sprint planning", "Filter Task Register: Release gate = MVP, Work status = Gap or Built - unverified or Claimed - unverified, sort by Risk score."),
        ("Pilot go / no-go", "MVP with a passing test, divided by MVP. Pick the threshold in the room. The sheet does not invent 90 percent."),
        ("Due diligence", "Share P0 gap decisions, Security assurance, and Business integrity. The Not verified labels are the point."),
        ("Hiring", "Role rollup on OS architecture names the area. Owner on the register names the person."),
        ("Release notes", "Verification result = Pass. Validation status alone is an author or review label."),
    ]
    for idx, (use, how) in enumerate(uses, start=23):
        ws.cell(row=idx, column=1, value=use).font = BOLD_FONT
        ws.cell(row=idx, column=2, value=how).font = DATA_FONT
        ws.merge_cells(start_row=idx, start_column=2, end_row=idx, end_column=3)
        for col in range(1, 4):
            ws.cell(row=idx, column=col).alignment = WRAP
            ws.cell(row=idx, column=col).border = THIN
        ws.row_dimensions[idx].height = 28
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 78
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddHeader.left.text = "BizBoard founder view"
    ws.oddFooter.right.text = "Page &P of &N"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.tabColor = "C65911"


def build_pilot_readiness(wb):
    ws = wb.create_sheet("Pilot readiness", 1)
    _heading(
        ws,
        "Pilot readiness",
        "Three personas only. A gate count is tasks with evidence, and there is no evidence yet, so the passed columns stay at zero. OS ready is not awarded here.",
    )
    headers = [
        "Persona",
        "Tasks",
        "MVP tasks",
        "G1 to G5 passed",
        "With a passing test",
        "OS ready",
    ]
    personas = [
        "Kirana Shop Owner",
        "Distributor",
        "Accountant / GST Operator",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
    for idx, persona in enumerate(personas, start=4):
        ws.cell(row=idx, column=1, value=persona).font = BOLD_FONT
        ws.cell(row=idx, column=2, value=f'=COUNTIF(TaskRegister[Persona / Scope],A{idx})').font = DATA_FONT
        ws.cell(
            row=idx,
            column=3,
            value=f'=COUNTIFS(TaskRegister[Persona / Scope],A{idx},TaskRegister[Release gate],"MVP")',
        ).font = DATA_FONT
        ws.cell(row=idx, column=4, value=0).font = DATA_FONT
        ws.cell(
            row=idx,
            column=5,
            value=f'=COUNTIFS(TaskRegister[Persona / Scope],A{idx},TaskRegister[Verification result],"Pass")',
        ).font = DATA_FONT
        ws.cell(
            row=idx,
            column=6,
            value=f'=COUNTIFS(TaskRegister[Persona / Scope],A{idx},TaskRegister[OS ready],"Yes")',
        ).font = DATA_FONT
        for col in range(1, 7):
            ws.cell(row=idx, column=col).alignment = CENTER if col > 1 else WRAP
            ws.cell(row=idx, column=col).border = THIN
        ws.row_dimensions[idx].height = 22
    ws.cell(row=8, column=1, value="Why these three").font = BOLD_FONT
    ws.cell(
        row=8,
        column=2,
        value="Kirana owner, distributor, and accountant are the first pilot desks. Other personas stay in the register and are not in this go / no-go.",
    ).font = DATA_FONT
    ws.merge_cells("B8:F8")
    ws.cell(row=8, column=2).alignment = WRAP
    ws.row_dimensions[8].height = 32
    for col in range(1, 7):
        ws.column_dimensions[get_column_letter(col)].width = 28 if col > 1 else 32
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def build_gap_decisions(wb, rows):
    ws = wb.create_sheet("P0 gap decisions", 2)
    _heading(
        ws,
        "P0 gap decisions",
        "Open claims only. Fill Decision, Decision owner, and Decision date in week 1. Blank means the decision is not made.",
    )
    headers = [
        "Task ID",
        "Claim",
        "Validation status",
        "Recommended next step",
        "Decision",
        "Decision owner",
        "Decision date",
    ]
    body = []
    for row in rows:
        if row[10] not in {"Partial", "Mechanism not found"}:
            continue
        if row[10] == "Partial":
            step = "Keep the corrected limit in the pilot story. Build the missing piece only if you accept it into MVP."
        else:
            step = "Leave it out of the pilot, or accept a build. Do not describe it as present."
        if row[0] == "SEC-0624":
            step = "Admin second factor is not in the product. Decide whether MVP requires it before a bank or auditor review."
        if row[0] == "S-0561":
            step = "Trial balance exists. A nightly invariant check with an alert does not. Decide whether to build the check."
        body.append((row[0], row[4], row[10], step, "", "", ""))
    body.sort(key=lambda item: item[0])
    _write_table(ws, headers, body, [14, 55, 22, 55, 28, 22, 18], "P0GapDecisions")


def build_weekly_snapshot(wb, rows):
    ws = wb.create_sheet("Weekly snapshot", 3)
    _heading(
        ws,
        "Weekly snapshot",
        "Copy the live row down when you want a trend. This file starts with one snapshot. History is not backfilled.",
    )
    headers = [
        "Week",
        "Tasks",
        "MVP",
        "Pilot",
        "Later",
        "Open gaps",
        "Partial",
        "MVP tests passing",
        "No owner",
        "No test id",
        "OS ready",
    ]
    mvp = sum(1 for row in rows if row[28] == "MVP")
    pilot = sum(1 for row in rows if row[28] == "Pilot")
    later = sum(1 for row in rows if row[28] == "Later")
    gaps = sum(1 for row in rows if row[35] == "Gap")
    partial = sum(1 for row in rows if row[35] == "Built - partial")
    no_owner = sum(1 for row in rows if not row[38])
    no_test = sum(1 for row in rows if not row[43])
    os_ready = sum(1 for row in rows if row[34] == "Yes")
    snapshot = [(
        "2026-10-04",
        len(rows),
        mvp,
        pilot,
        later,
        gaps,
        partial,
        0,
        no_owner,
        no_test,
        os_ready,
    )]
    _write_table(ws, headers, snapshot, [16, 12, 12, 12, 12, 14, 12, 20, 14, 14, 12], "WeeklySnapshot")
    live = len(snapshot) + 4
    ws.cell(row=live, column=1, value="Live (updates when the workbook calculates)").font = BOLD_FONT
    formulas = [
        '=COUNTA(TaskRegister[Task ID])',
        '=COUNTIF(TaskRegister[Release gate],"MVP")',
        '=COUNTIF(TaskRegister[Release gate],"Pilot")',
        '=COUNTIF(TaskRegister[Release gate],"Later")',
        '=COUNTIF(TaskRegister[Work status],"Gap")',
        '=COUNTIF(TaskRegister[Work status],"Built - partial")',
        '=COUNTIFS(TaskRegister[Release gate],"MVP",TaskRegister[Verification result],"Pass")',
        '=COUNTBLANK(TaskRegister[Owner])',
        '=COUNTBLANK(TaskRegister[Test case ID])',
        '=COUNTIF(TaskRegister[OS ready],"Yes")',
    ]
    for col, formula in enumerate(formulas, start=2):
        ws.cell(row=live, column=col, value=formula).font = DATA_FONT
        ws.cell(row=live, column=col).border = THIN
    ws.cell(row=live, column=1).border = THIN
    ws.row_dimensions[live].height = 22


def build_os_sheets(wb, rows):
    build_disposition(wb)
    build_architecture(wb)
    build_events(wb)
    build_states(wb)
    build_integrity(wb)
    build_failure(wb)
    build_concurrency(wb)
    build_security(wb)
    build_integrations(wb)
    build_sla(wb)
    build_customer(wb)
    build_capability_evidence(wb, rows)
    build_readiness(wb)
    build_founder(wb)
    build_pilot_readiness(wb)
    build_gap_decisions(wb, rows)
    build_weekly_snapshot(wb, rows)

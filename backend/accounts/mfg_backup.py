"""Backup, wipe and restore for the Manufacturing tables that sit beside the core documents.

Quality, job work, planning and the shop floor each add tables that point at products, godowns,
suppliers, customers, batches and work orders. A tenant backup has to carry them, and a wipe has to
remove them first or the godowns, items and lots they point at cannot be deleted.

The tables are listed once, parents before children. Export walks the list forward, restore walks it
forward and remaps ids as it goes, and wipe walks it backward.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps

# (payload key, "app.Model", {field: map name}, fields to require, fields to leave out, map name this table fills)
SPECS: list[tuple[str, str, dict[str, str], tuple[str, ...], set[str], str | None]] = [
    ("mfg_standard_costs", "manufacturing.StandardCost", {"product_id": "product"}, ("product_id",), set(), None),
    ("mfg_work_centres", "manufacturing.WorkCentre", {}, (), set(), "work_centre"),
    (
        "mfg_routing_operations", "manufacturing.RoutingOperation",
        {"bom_id": "bom", "work_centre_id": "work_centre", "subcontract_supplier_id": "supplier"},
        ("bom_id", "work_centre_id"), set(), "routing_op",
    ),
    ("mfg_operators", "manufacturing.Operator", {}, (), set(), "operator"),
    (
        "mfg_job_cards", "manufacturing.JobCard",
        {"work_order_id": "wo", "operation_id": "routing_op", "work_centre_id": "work_centre"},
        ("work_order_id", "work_centre_id"), set(), "job_card",
    ),
    (
        "mfg_time_logs", "manufacturing.TimeLog", {"job_card_id": "job_card", "operator_id": "operator"},
        ("job_card_id",), {"user_id"}, None,
    ),
    ("mfg_downtime_reasons", "manufacturing.DowntimeReason", {}, (), set(), "downtime_reason"),
    (
        "mfg_downtime_events", "manufacturing.DowntimeEvent",
        {"work_centre_id": "work_centre", "job_card_id": "job_card", "reason_id": "downtime_reason"},
        ("work_centre_id", "reason_id"), set(), None,
    ),
    ("mfg_machines", "manufacturing.Machine", {"work_centre_id": "work_centre"}, (), set(), "machine"),
    ("mfg_maintenance_plans", "manufacturing.MaintenancePlan", {"machine_id": "machine"}, ("machine_id",), set(), "maint_plan"),
    (
        "mfg_maintenance_logs", "manufacturing.MaintenanceLog", {"machine_id": "machine", "plan_id": "maint_plan"},
        ("machine_id",), set(), None,
    ),
    ("mfg_mrp_runs", "manufacturing.MrpRun", {}, (), set(), "mrp_run"),
    (
        "mfg_mrp_lines", "manufacturing.MrpLine", {"run_id": "mrp_run", "product_id": "product", "supplier_id": "supplier"},
        ("run_id", "product_id"), set(), None,
    ),
    ("mfg_revaluations", "manufacturing.StandardRevaluation", {"product_id": "product"}, (), set(), "reval"),
    (
        "mfg_revaluation_lines", "manufacturing.StandardRevaluationLine",
        {"run_id": "reval", "product_id": "product", "warehouse_id": "warehouse", "batch_id": "batch"},
        ("run_id", "product_id"), {"last_movement_id"}, None,
    ),
    ("quality_defect_codes", "quality.DefectCode", {}, (), set(), "defect_code"),
    ("quality_templates", "quality.InspectionTemplate", {"product_id": "product"}, (), set(), "q_template"),
    ("quality_parameters", "quality.InspectionParameter", {"template_id": "q_template"}, ("template_id",), set(), None),
    (
        "quality_inspections", "quality.Inspection",
        {"template_id": "q_template", "product_id": "product", "batch_id": "batch", "supplier_id": "supplier"},
        ("product_id",), {"grn_item_id", "inspector_id"}, "inspection",
    ),
    ("quality_results", "quality.InspectionResult", {"inspection_id": "inspection"}, ("inspection_id",), set(), None),
    (
        "quality_ncrs", "quality.NonConformance",
        {
            "inspection_id": "inspection", "product_id": "product", "batch_id": "batch", "supplier_id": "supplier",
            "customer_id": "customer", "defect_code_id": "defect_code",
        },
        (), {"complaint_id", "owner_id"}, None,
    ),
    (
        "jw_orders", "jobwork.JobWorkOrder",
        {"supplier_id": "supplier", "customer_id": "customer", "job_worker_warehouse_id": "warehouse"},
        (), set(), "jw_order",
    ),
    (
        "jw_challans", "jobwork.JobWorkChallan", {"order_id": "jw_order", "warehouse_id": "warehouse"},
        ("order_id",), {"source_challan_id"}, "jw_challan",
    ),
    (
        "jw_challan_lines", "jobwork.JobWorkChallanLine",
        {"challan_id": "jw_challan", "product_id": "product", "batch_id": "batch"},
        ("challan_id", "product_id"), set(), "jw_challan_line",
    ),
    (
        "jw_receipts", "jobwork.JobWorkReceipt", {"order_id": "jw_order", "warehouse_id": "warehouse"},
        ("order_id",), {"reversed_by_id"}, "jw_receipt",
    ),
    (
        "jw_receipt_lines", "jobwork.JobWorkReceiptLine",
        {
            "receipt_id": "jw_receipt", "product_id": "product", "batch_id": "batch", "input_product_id": "product",
            "input_batch_id": "batch", "other_order_id": "jw_order",
        },
        ("receipt_id", "product_id"), set(), "jw_receipt_line",
    ),
    (
        "jw_settlements", "jobwork.JobWorkSettlement",
        {"receipt_line_id": "jw_receipt_line", "challan_line_id": "jw_challan_line"},
        ("receipt_line_id", "challan_line_id"), set(), None,
    ),
    (
        "jw_principal_movements", "jobwork.PrincipalMaterialMovement",
        {"principal_id": "customer", "order_id": "jw_order", "challan_id": "jw_challan", "product_id": "product"},
        ("principal_id", "product_id"), set(), None,
    ),
    ("jw_itc04_filings", "jobwork.Itc04Filing", {}, (), set(), None),
]

# Fields that hold ids of stock movements or lots; they would point at the wrong rows after a restore.
STALE_ID_FIELDS = {"movement_ids", "lot_allocations"}


def _model(label: str):
    app, name = label.split(".")
    return apps.get_model(app, name)


def export_rows(company, extra: dict, optional_rows) -> None:
    for key, label, *_ in SPECS:
        try:
            extra[key] = optional_rows(_model(label), company)
        except Exception:
            extra[key] = []


def wipe(company) -> None:
    """Delete these tables, children before parents."""
    for key, label, *_ in reversed(SPECS):
        try:
            model = _model(label)
            if key == "jw_challans":
                model.objects.filter(company=company).update(source_challan=None)
            model.objects.filter(company=company).delete()
        except Exception:
            continue


def restore(*, payload: dict, target_company, owner, maps: dict[str, dict[Any, int]], create_mapped) -> None:
    """Recreate the tables with new ids. ``maps`` holds old-to-new ids for what the core restore already made."""
    own: dict[str, dict[Any, int]] = {}
    lookup = {**maps}
    for key, label, remap, require, skip, fills in SPECS:
        model = _model(label)
        names = {f.name for f in model._meta.concrete_fields}
        leave = set(skip) | (STALE_ID_FIELDS & names)
        resolved = {fld: lookup.setdefault(name, {}) for fld, name in remap.items()}
        table = own.setdefault(fills, {}) if fills else None
        for row in payload.get(key) or []:
            try:
                obj = create_mapped(
                    model, row, company=target_company, owner=owner, skip=leave, remap=resolved, require=require,
                )
            except Exception:
                continue
            if obj is not None and table is not None:
                table[row.get("id")] = obj.pk
        if fills:
            lookup[fills] = own[fills]
    # A challan raised from another worker's challan points at one of this file's challans.
    JobWorkChallan = _model("jobwork.JobWorkChallan")
    challans = lookup.get("jw_challan", {})
    for row in payload.get("jw_challans") or []:
        src = row.get("source_challan_id")
        if src in challans and row.get("id") in challans:
            JobWorkChallan.objects.filter(pk=challans[row["id"]]).update(source_challan_id=challans[src])

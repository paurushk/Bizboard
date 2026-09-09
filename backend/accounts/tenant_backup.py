"""BB-000668: company-scoped tenant export / restore (encrypted zip).

Instance-level dumps (`scripts/backup.sh`, BB-000045 / BB-000469) remain the
ops runbook for Postgres. This module is a per-tenant logical backup for
owners — not a replacement for infrastructure backups.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from core.csv_utils import csv_safe
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

EXPORT_VERSION = 1
SMALL_FILE_MAX_BYTES = 256 * 1024
_TENANT_EXPORT_HKDF_SALT = b"bizboard-tenant-export-v1"
COMPANY_SKIP_FIELDS = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "logo_id",
        "signature_id",
        "gsp_credentials_encrypted",
        "payment_gateway_credentials_encrypted",
        "gstin_raw_payload",
        # B6-015: raw third-party identity-verification responses (proprietor
        # name / DOB / address / masked IDs) — exclude like gstin_raw_payload.
        "pan_raw_payload",
        "udyam_raw_payload",
        "billing_override_active",
        "is_sandbox",
        "sandbox_expires_at",
    }
)

SANDBOX_TTL_DAYS = 30
SANDBOX_NAME_PREFIX = "[sandbox] "
JSON_SECTIONS = (
    "company",
    "gstins",
    "document_series",
    "warehouses",
    "customers",
    "suppliers",
    "products",
    "batch_lots",
    "stock_balances",
    "stock_movements",
    "serial_numbers",
    "inventory_cost_layers",
    "sales_invoices",
    "sales_items",
    "quotations",
    "quotation_items",
    "sales_orders",
    "sales_order_items",
    "delivery_challans",
    "delivery_challan_items",
    "purchase_invoices",
    "purchase_items",
    "receipts",
    "supplier_payments",
    "allocations",
    "accounts",
    "journals",
    "journal_lines",
    "gstr2b",
    "file_assets",
    # R-014: every wipe target so restore/unbacked_live_counts stay honest.
    "bank_accounts",
    "leads",
    "lead_activities",
    "opportunities",
    "employees",
    "pay_runs",
    "pay_slips",
    "payment_links",
    "gateway_payments",
    "gateway_refund_outbox",
    "dunning_reminders",
    "bank_statements",
    "bank_statement_lines",
    "bank_recon_sessions",
    "recon_matches",
    "sales_credit_notes",
    "sales_credit_note_items",
    "sales_debit_notes",
    "sales_debit_note_items",
    "sales_returns",
    "sales_return_items",
    "purchase_orders",
    "purchase_order_items",
    "purchase_credit_notes",
    "purchase_debit_notes",
    "purchase_returns",
    "purchase_return_items",
    "bills_of_entry",
    "recurring_schedules",
    "recurring_runs",
    "fixed_assets",
    "boms",
    "bom_lines",
    "work_orders",
    "work_order_lines",
    "stock_transfers",
    "stock_transfer_lines",
    "stock_count_sessions",
    "warehouse_reorder_levels",
    "inventory_running_costs",
    "inventory_valuation_snapshots",
    "import_jobs",
    "ims_action_history",
)


def _instance_fernet_material() -> bytes:
    """Return instance Fernet key bytes (TENANT_EXPORT / GSP / DEBUG SECRET_KEY digest)."""
    raw = getattr(settings, "TENANT_EXPORT_FERNET_KEY", None) or ""
    if raw:
        return raw.encode("utf-8") if isinstance(raw, str) else raw
    gsp = getattr(settings, "GSP_FERNET_KEY", None) or ""
    if gsp:
        return gsp.encode("utf-8") if isinstance(gsp, str) else gsp
    env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
    if env in ("production", "staging") or not getattr(settings, "DEBUG", True):
        raise ImproperlyConfigured(
            "TENANT_EXPORT_FERNET_KEY (or GSP_FERNET_KEY) is required outside local DEBUG."
        )
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def tenant_export_fernet(company_id: int | None = None) -> Fernet:
    """Fernet for tenant export.

    company_id=None → instance key (legacy decrypt).
    company_id set → HKDF-SHA256 per-company key derived from instance material.
    """
    material = _instance_fernet_material()
    if company_id is None:
        return Fernet(material)
    try:
        ikm = base64.urlsafe_b64decode(material)
    except (ValueError, TypeError):
        ikm = material
    if len(ikm) != 32:
        # Already-raw 32-byte material, or non-Fernet encoding — use as IKM if 32 else hash.
        ikm = material if len(material) == 32 else hashlib.sha256(material).digest()
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_TENANT_EXPORT_HKDF_SALT,
        info=f"company:{company_id}".encode(),
    ).derive(ikm)
    return Fernet(base64.urlsafe_b64encode(derived))


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    raise TypeError(f"Unserializable type {type(value)!r}")


def _row_dict(instance, *, extra_exclude: set[str] | frozenset[str] = frozenset()) -> dict:
    data: dict[str, Any] = {"id": instance.pk}
    for field in instance._meta.concrete_fields:
        name = field.attname
        if name in extra_exclude:
            continue
        if name in {"created_by_id", "updated_by_id"}:
            continue
        data[name] = getattr(instance, name)
    return data


def _rows(qs, *, extra_exclude: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    return [_row_dict(obj, extra_exclude=extra_exclude) for obj in qs.iterator()]


def _optional_rows(model, company, *, extra_exclude: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    try:
        return _rows(model.objects.filter(company=company).order_by("id"), extra_exclude=extra_exclude)
    except Exception:  # noqa: BLE001 — optional apps / missing tables
        return []


def _wipe_target_sections(company) -> dict[str, list[dict]]:
    """Serialize every wipe-target table that the core payload does not already cover."""
    extra: dict[str, list[dict]] = {}
    try:
        from payments.models import (
            BankAccount,
            BankStatement,
            BankStatementLine,
            DunningReminder,
            GatewayPayment,
            GatewayRefundOutbox,
            PaymentLink,
            ReconMatch,
        )

        extra["bank_accounts"] = _optional_rows(BankAccount, company)
        extra["payment_links"] = _optional_rows(PaymentLink, company)
        extra["gateway_payments"] = _optional_rows(GatewayPayment, company)
        extra["gateway_refund_outbox"] = _optional_rows(GatewayRefundOutbox, company)
        extra["dunning_reminders"] = _optional_rows(DunningReminder, company)
        extra["bank_statements"] = _optional_rows(BankStatement, company)
        extra["bank_statement_lines"] = _optional_rows(BankStatementLine, company)
        extra["recon_matches"] = _optional_rows(ReconMatch, company)
    except Exception:
        pass
    try:
        from accounting.models import BankReconSession, FixedAsset

        extra["bank_recon_sessions"] = _optional_rows(BankReconSession, company)
        extra["fixed_assets"] = _optional_rows(FixedAsset, company)
    except Exception:
        pass
    try:
        from crm.models import Lead, LeadActivity, Opportunity

        extra["leads"] = _optional_rows(Lead, company)
        extra["lead_activities"] = _optional_rows(LeadActivity, company)
        extra["opportunities"] = _optional_rows(Opportunity, company)
    except Exception:
        pass
    try:
        from payroll.models import Employee, PayRun, PaySlip

        extra["employees"] = _optional_rows(Employee, company)
        extra["pay_runs"] = _optional_rows(PayRun, company)
        extra["pay_slips"] = _optional_rows(PaySlip, company)
    except Exception:
        pass
    try:
        from sales.models import (
            RecurringInvoiceRun,
            RecurringInvoiceSchedule,
            SalesCreditNote,
            SalesCreditNoteItem,
            SalesDebitNote,
            SalesDebitNoteItem,
            SalesReturn,
            SalesReturnItem,
        )

        extra["recurring_schedules"] = _optional_rows(RecurringInvoiceSchedule, company)
        extra["recurring_runs"] = _optional_rows(RecurringInvoiceRun, company)
        extra["sales_credit_notes"] = _optional_rows(SalesCreditNote, company)
        extra["sales_credit_note_items"] = _optional_rows(SalesCreditNoteItem, company)
        extra["sales_debit_notes"] = _optional_rows(SalesDebitNote, company)
        extra["sales_debit_note_items"] = _optional_rows(SalesDebitNoteItem, company)
        extra["sales_returns"] = _optional_rows(SalesReturn, company)
        extra["sales_return_items"] = _optional_rows(SalesReturnItem, company)
    except Exception:
        pass
    try:
        from purchases.models import (
            BillOfEntry,
            PurchaseCreditNote,
            PurchaseDebitNote,
            PurchaseOrder,
            PurchaseOrderItem,
            PurchaseReturn,
            PurchaseReturnItem,
        )

        extra["purchase_orders"] = _optional_rows(PurchaseOrder, company)
        extra["purchase_order_items"] = _optional_rows(PurchaseOrderItem, company)
        extra["purchase_credit_notes"] = _optional_rows(PurchaseCreditNote, company)
        extra["purchase_debit_notes"] = _optional_rows(PurchaseDebitNote, company)
        extra["purchase_returns"] = _optional_rows(PurchaseReturn, company)
        extra["purchase_return_items"] = _optional_rows(PurchaseReturnItem, company)
        extra["bills_of_entry"] = _optional_rows(BillOfEntry, company)
    except Exception:
        pass
    try:
        from manufacturing.models import Bom, BomLine, WorkOrder, WorkOrderLine

        extra["boms"] = _optional_rows(Bom, company)
        extra["bom_lines"] = _optional_rows(BomLine, company)
        extra["work_orders"] = _optional_rows(WorkOrder, company)
        extra["work_order_lines"] = _optional_rows(WorkOrderLine, company)
    except Exception:
        pass
    try:
        from inventory.models import (
            InventoryRunningCost,
            InventoryValuationSnapshot,
            StockCountSession,
            StockTransfer,
            StockTransferLine,
            WarehouseReorderLevel,
        )

        extra["stock_transfers"] = _optional_rows(StockTransfer, company)
        extra["stock_transfer_lines"] = _optional_rows(StockTransferLine, company)
        extra["stock_count_sessions"] = _optional_rows(StockCountSession, company)
        extra["warehouse_reorder_levels"] = _optional_rows(WarehouseReorderLevel, company)
        extra["inventory_running_costs"] = _optional_rows(InventoryRunningCost, company)
        extra["inventory_valuation_snapshots"] = _optional_rows(InventoryValuationSnapshot, company)
    except Exception:
        pass
    try:
        from imports.models import ImportJob

        extra["import_jobs"] = _optional_rows(ImportJob, company, extra_exclude={"file_id"})
    except Exception:
        pass
    try:
        from reporting.models import ImsActionHistory

        extra["ims_action_history"] = _optional_rows(ImsActionHistory, company)
    except Exception:
        pass
    return extra


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    if not rows:
        buf.write("")
        return buf.getvalue().encode("utf-8")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: csv_safe(v) for k, v in row.items()})
    return buf.getvalue().encode("utf-8")


def _file_checksum(asset) -> str:
    try:
        asset.file.open("rb")
        digest = hashlib.sha256()
        for chunk in asset.file.chunks():
            digest.update(chunk)
        return digest.hexdigest()
    except Exception:  # noqa: BLE001 — manifest must not fail export
        return ""
    finally:
        try:
            asset.file.close()
        except Exception:  # noqa: BLE001
            pass


def build_export_payload(company) -> dict[str, Any]:
    from accounting.models import Account, JournalEntry, JournalLine
    from core.models import FileAsset
    from masters.models import Customer, Product, Supplier
    from payments.models import CustomerReceipt, PaymentAllocation, SupplierPayment
    from purchases.models import PurchaseInvoice, PurchaseItem
    from reporting.models import Gstr2bIngest
    from sales.models import (
        DeliveryChallan,
        DeliveryChallanItem,
        Quotation,
        QuotationItem,
        SalesInvoice,
        SalesItem,
        SalesOrder,
        SalesOrderItem,
    )
    from accounts.models import CompanyGstin
    from core.models import DocumentSeries
    from inventory.models import Warehouse, BatchLot, StockMovement, StockBalance, SerialNumber, InventoryCostLayer

    company_profile = _row_dict(company, extra_exclude=COMPANY_SKIP_FIELDS)
    gstins = _rows(CompanyGstin.objects.filter(company=company).order_by("id"))
    document_series = _rows(DocumentSeries.objects.filter(company=company).order_by("id"))
    warehouses = _rows(Warehouse.objects.filter(company=company).order_by("id"))
    customers = _rows(Customer.objects.filter(company=company).order_by("id"), extra_exclude={"price_list_id"})
    suppliers = _rows(Supplier.objects.filter(company=company).order_by("id"))
    products = _rows(
        Product.objects.filter(company=company).order_by("id"),
        extra_exclude={"category_id", "brand_id", "unit_id"},
    )
    batch_lots = _rows(BatchLot.objects.filter(company=company).order_by("id"))
    stock_balances = _rows(StockBalance.objects.filter(company=company).order_by("id"))
    stock_movements = _rows(StockMovement.objects.filter(company=company).order_by("id"))
    serial_numbers = _rows(SerialNumber.objects.filter(company=company).order_by("id"))
    inventory_cost_layers = _rows(InventoryCostLayer.objects.filter(company=company).order_by("id"))
    sales_invoices = _rows(
        SalesInvoice.objects.filter(company=company).order_by("id"),
        extra_exclude={"warehouse_id", "cost_center_id", "signature_id", "pdf_file_id"},
    )
    sales_items = _rows(
        SalesItem.objects.filter(company=company).order_by("id"),
        extra_exclude={"batch_id"},
    )
    quotations = _rows(Quotation.objects.filter(company=company).order_by("id"))
    quotation_items = _rows(QuotationItem.objects.filter(company=company).order_by("id"))
    sales_orders = _rows(
        SalesOrder.objects.filter(company=company).order_by("id"),
        extra_exclude={"warehouse_id"},
    )
    sales_order_items = _rows(SalesOrderItem.objects.filter(company=company).order_by("id"))
    delivery_challans = _rows(
        DeliveryChallan.objects.filter(company=company).order_by("id"),
        extra_exclude={"warehouse_id", "pdf_file_id"},
    )
    delivery_challan_items = _rows(DeliveryChallanItem.objects.filter(company=company).order_by("id"))
    purchase_invoices = _rows(
        PurchaseInvoice.objects.filter(company=company).order_by("id"),
        extra_exclude={"warehouse_id", "cost_center_id", "signature_id", "attachment_id"},
    )
    purchase_items = _rows(
        PurchaseItem.objects.filter(company=company).order_by("id"),
        extra_exclude={"batch_id"},
    )
    receipts = _rows(
        CustomerReceipt.objects.filter(company=company).order_by("id"),
        extra_exclude={"bank_account_id", "gateway_payment_id"},
    )
    payments = _rows(
        SupplierPayment.objects.filter(company=company).order_by("id"),
        extra_exclude={"bank_account_id"},
    )
    allocations = _rows(PaymentAllocation.objects.filter(company=company).order_by("id"))
    accounts = _rows(Account.objects.filter(company=company).order_by("id"), extra_exclude={"bank_account_id"})
    journals = _rows(
        JournalEntry.objects.filter(company=company).order_by("id"),
        extra_exclude={"posted_by_id", "reversed_entry_id"},
    )
    journal_lines = _rows(
        JournalLine.objects.filter(company=company).order_by("id"),
        extra_exclude={"cost_center_id", "bank_statement_line_id"},
    )
    gstr2b_rows = _rows(Gstr2bIngest.objects.filter(company=company).order_by("id"))
    gstr2b_summary = {
        "row_count": len(gstr2b_rows),
        "periods": sorted({row.get("period") for row in gstr2b_rows if row.get("period")}),
        "matched": sum(1 for row in gstr2b_rows if row.get("match_status") == "MATCHED"),
        "unmatched": sum(1 for row in gstr2b_rows if row.get("match_status") == "UNMATCHED"),
    }

    file_manifest = []
    # Track assets whose bytes/checksum could not be read so the Owner is not
    # handed an export they believe is byte-complete when it is not.
    file_asset_warnings: list[dict] = []
    for asset in FileAsset.objects.filter(company=company).order_by("id"):
        checksum = _file_checksum(asset)
        if not checksum:
            file_asset_warnings.append({"id": asset.pk, "reason": "checksum_unreadable"})
        entry = {
            "id": asset.pk,
            "kind": asset.kind,
            "original_name": asset.original_name,
            "content_type": asset.content_type,
            "size": asset.size,
            "checksum_sha256": checksum,
            "bytes_b64": None,
        }
        if asset.size and asset.size <= SMALL_FILE_MAX_BYTES:
            try:
                asset.file.open("rb")
                entry["bytes_b64"] = base64.b64encode(asset.file.read()).decode("ascii")
            except Exception:  # noqa: BLE001
                entry["bytes_b64"] = None
                file_asset_warnings.append({"id": asset.pk, "reason": "bytes_unreadable"})
            finally:
                try:
                    asset.file.close()
                except Exception:  # noqa: BLE001
                    pass
        file_manifest.append(entry)

    return {
        "version": EXPORT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "source_company_id": company.pk,
        "source_company_name": company.name,
        "company": company_profile,
        "gstins": gstins,
        "document_series": document_series,
        "warehouses": warehouses,
        "customers": customers,
        "suppliers": suppliers,
        "products": products,
        "batch_lots": batch_lots,
        "stock_balances": stock_balances,
        "stock_movements": stock_movements,
        "serial_numbers": serial_numbers,
        "inventory_cost_layers": inventory_cost_layers,
        "sales_invoices": sales_invoices,
        "sales_items": sales_items,
        "quotations": quotations,
        "quotation_items": quotation_items,
        "sales_orders": sales_orders,
        "sales_order_items": sales_order_items,
        "delivery_challans": delivery_challans,
        "delivery_challan_items": delivery_challan_items,
        "purchase_invoices": purchase_invoices,
        "purchase_items": purchase_items,
        "receipts": receipts,
        "supplier_payments": payments,
        "allocations": allocations,
        "accounts": accounts,
        "journals": journals,
        "journal_lines": journal_lines,
        "gstr2b_summary": gstr2b_summary,
        "gstr2b": gstr2b_rows,
        "file_assets": file_manifest,
        "file_asset_warnings": file_asset_warnings,
        **_wipe_target_sections(company),
    }


def encrypt_export_zip(payload: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _asset_warnings = payload.get("file_asset_warnings") or []
        zf.writestr("manifest.json", json.dumps({
            "version": payload.get("version"),
            "exported_at": payload.get("exported_at"),
            "source_company_id": payload.get("source_company_id"),
            "source_company_name": payload.get("source_company_name"),
            "gstr2b_summary": payload.get("gstr2b_summary") or {},
            "file_asset_warning_count": len(_asset_warnings),
            "file_asset_warnings": _asset_warnings,
        }, default=_json_default, indent=2))
        for key in JSON_SECTIONS:
            zf.writestr(f"{key}.json", json.dumps(payload.get(key), default=_json_default, indent=2))
        for key in ("customers", "suppliers", "products", "sales_invoices", "purchase_invoices"):
            rows = payload.get(key) or []
            if isinstance(rows, list):
                zf.writestr(f"{key}.csv", _csv_bytes(rows))
    company_id = payload.get("source_company_id")
    fernet = (
        tenant_export_fernet(company_id=company_id)
        if company_id is not None
        else tenant_export_fernet()
    )
    return fernet.encrypt(buf.getvalue())


def decrypt_export_zip(blob: bytes, *, company_id: int | None = None) -> dict[str, Any]:
    from core.exceptions import BusinessRuleError

    zip_bytes = None
    last_exc: Exception | None = None
    if company_id is not None:
        try:
            zip_bytes = tenant_export_fernet(company_id=company_id).decrypt(blob)
        except (InvalidToken, ValueError) as exc:
            last_exc = exc
    if zip_bytes is None:
        try:
            zip_bytes = tenant_export_fernet().decrypt(blob)
        except (InvalidToken, ValueError) as exc:
            last_exc = exc
            raise BusinessRuleError("Invalid or tampered export file.") from last_exc
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        def _load(name: str, default=None):
            try:
                return json.loads(zf.read(name).decode("utf-8"))
            except KeyError:
                return default

        manifest = _load("manifest.json") or {}
        manifest_version = manifest.get("version", EXPORT_VERSION)
        # B6-018: refuse a payload written by a different (future/older) schema
        # rather than importing it best-effort and producing a partial tenant.
        try:
            manifest_version_int = int(manifest_version)
        except (TypeError, ValueError):
            manifest_version_int = None
        if manifest_version_int != EXPORT_VERSION:
            raise BusinessRuleError(
                f"Unsupported export version {manifest_version!r}; "
                f"this build imports version {EXPORT_VERSION} only."
            )
        payload = {
            "version": manifest_version,
            "exported_at": manifest.get("exported_at"),
            "source_company_id": manifest.get("source_company_id"),
            "source_company_name": manifest.get("source_company_name"),
            "gstr2b_summary": manifest.get("gstr2b_summary") or _load("gstr2b_summary.json") or {},
        }
        for key in JSON_SECTIONS:
            default: dict | list = {} if key == "company" else []
            payload[key] = _load(f"{key}.json") or default
    return payload


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _parse_date(value):
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    if isinstance(parsed, datetime):
        return parsed.date()
    return parsed


def _remap_stock_movement_reference_id(
    reference_type: str, old_reference_id, sales_map: dict[Any, int], purchase_map: dict[Any, int]
) -> str:
    """B6-019: rewrite a StockMovement's soft `reference_id` through the
    matching id map for restorable document types; blank it for every other
    `reference_type` (stock_transfer*, work_order*, delivery_challan*,
    sales_return*, purchase_return*, manual/serial/expiry adjustments, ...)
    since this backup format doesn't carry those source rows at all — there
    is no map to rewrite through, and leaving the old numeric id is worse
    than blank (it can resolve to an unrelated, possibly other-tenant, row).
    """
    if not old_reference_id:
        return ""
    id_map: dict[Any, int] | None = None
    if reference_type.startswith("sales_invoice"):
        id_map = sales_map
    elif reference_type.startswith("purchase_invoice"):
        id_map = purchase_map
    if id_map is None:
        return ""
    # Backup JSON round-trips ids as either int or str depending on source;
    # try both forms since map keys come from the original serialized rows.
    new_id = id_map.get(old_reference_id)
    if new_id is None:
        try:
            new_id = id_map.get(int(old_reference_id))
        except (TypeError, ValueError):
            new_id = None
    return str(new_id) if new_id is not None else ""


def _copy_model_fields(model, row: dict, *, skip: set[str], remap: dict[str, int | None]) -> dict:
    kwargs: dict[str, Any] = {}
    field_names = {f.attname: f for f in model._meta.concrete_fields}
    for attname, field in field_names.items():
        if attname in skip or attname in {"id", "pk"}:
            continue
        if attname not in row and field.name not in row:
            continue
        raw = row.get(attname, row.get(field.name))
        if attname.endswith("_id") and attname in remap:
            old_id = raw
            kwargs[attname] = remap[attname].get(old_id) if isinstance(remap[attname], dict) else remap[attname]
            continue
        if getattr(field, "is_relation", False) and field.many_to_one:
            # B6-005: a real FK column that isn't in `remap` would otherwise be
            # copied verbatim — a source PK pointing at the old tenant's row (or
            # a global id that resolves to another tenant). Null it; only an
            # explicitly-remapped FK is carried across.
            kwargs[attname] = None
            continue
        if raw is None:
            kwargs[attname] = None
            continue
        internal = field.get_internal_type()
        if internal in {"DateField"}:
            kwargs[attname] = _parse_date(raw)
        elif internal in {"DateTimeField"}:
            kwargs[attname] = _parse_dt(raw)
        elif internal in {"DecimalField"}:
            kwargs[attname] = Decimal(str(raw))
        elif internal in {"BooleanField"}:
            kwargs[attname] = bool(raw)
        elif internal in {"IntegerField", "BigIntegerField", "PositiveIntegerField", "PositiveSmallIntegerField", "SmallIntegerField"}:
            kwargs[attname] = int(raw) if raw not in ("", None) else None
        elif internal in {"JSONField"}:
            kwargs[attname] = raw if isinstance(raw, (dict, list)) else (json.loads(raw) if isinstance(raw, str) and raw else raw)
        else:
            kwargs[attname] = raw
    return kwargs


def wipe_logical_tenant_rows(company) -> None:
    """Delete business rows on a company so destroy-in-place restore can reload."""
    from accounting.models import Account, BankReconSession, FixedAsset, JournalEntry, JournalLine
    from accounts.models import CompanyGstin
    from core.models import DocumentSeries, FileAsset, IdempotencyRecord, Notification
    from imports.models import ImportJob
    from inventory.models import (
        BatchLot,
        InventoryCostLayer,
        InventoryRunningCost,
        InventoryValuationSnapshot,
        SerialNumber,
        StockBalance,
        StockCountSession,
        StockMovement,
        StockTransfer,
        Warehouse,
        WarehouseReorderLevel,
    )
    from masters.models import Customer, Product, Supplier
    from payments.models import (
        BankStatement,
        BankStatementLine,
        CustomerReceipt,
        DunningReminder,
        GatewayPayment,
        GatewayRefundOutbox,
        PaymentAllocation,
        PaymentLink,
        ReconMatch,
        SupplierPayment,
    )
    from purchases.models import (
        BillOfEntry,
        PurchaseCreditNote,
        PurchaseDebitNote,
        PurchaseInvoice,
        PurchaseOrder,
        PurchaseReturn,
    )
    from reporting.models import Gstr2bIngest, ImsActionHistory
    from sales.models import (
        DeliveryChallan,
        Quotation,
        RecurringInvoiceRun,
        RecurringInvoiceSchedule,
        SalesCreditNote,
        SalesDebitNote,
        SalesInvoice,
        SalesOrder,
        SalesReturn,
    )

    ImsActionHistory.objects.filter(company=company).delete()
    ImportJob.objects.filter(company=company).delete()
    ReconMatch.objects.filter(company=company).delete()
    DunningReminder.objects.filter(company=company).delete()
    GatewayRefundOutbox.objects.filter(company=company).delete()
    PaymentAllocation.objects.filter(company=company).delete()
    GatewayPayment.objects.filter(company=company).delete()
    PaymentLink.objects.filter(company=company).delete()
    BankReconSession.objects.filter(company=company).delete()
    BankStatementLine.objects.filter(company=company).delete()
    BankStatement.objects.filter(company=company).delete()
    from payments.models import BankAccount

    BankAccount.objects.filter(company=company).delete()
    JournalLine.objects.filter(company=company).delete()
    JournalEntry.objects.filter(company=company).update(reversed_entry=None)
    JournalEntry.objects.filter(company=company).delete()
    Gstr2bIngest.objects.filter(company=company).delete()
    CustomerReceipt.objects.filter(company=company).delete()
    SupplierPayment.objects.filter(company=company).delete()
    RecurringInvoiceRun.objects.filter(company=company).delete()
    RecurringInvoiceSchedule.objects.filter(company=company).delete()
    Quotation.objects.filter(company=company).delete()
    SalesOrder.objects.filter(company=company).delete()
    DeliveryChallan.objects.filter(company=company).delete()
    SalesCreditNote.objects.filter(company=company).delete()
    SalesDebitNote.objects.filter(company=company).delete()
    SalesReturn.objects.filter(company=company).delete()
    SalesInvoice.objects.filter(company=company).delete()
    PurchaseOrder.objects.filter(company=company).delete()
    PurchaseCreditNote.objects.filter(company=company).delete()
    PurchaseDebitNote.objects.filter(company=company).delete()
    PurchaseReturn.objects.filter(company=company).delete()
    BillOfEntry.objects.filter(company=company).delete()
    PurchaseInvoice.objects.filter(company=company).delete()
    try:
        from crm.models import Lead, LeadActivity, Opportunity

        LeadActivity.objects.filter(company=company).delete()
        Opportunity.objects.filter(company=company).delete()
        Lead.objects.filter(company=company).delete()
    except Exception:
        pass
    try:
        from manufacturing.models import Bom, BomLine, WorkOrder, WorkOrderLine

        WorkOrderLine.objects.filter(company=company).delete()
        WorkOrder.objects.filter(company=company).delete()
        BomLine.objects.filter(company=company).delete()
        Bom.objects.filter(company=company).delete()
    except Exception:
        pass
    try:
        from payroll.models import Employee, PayRun, PaySlip

        PaySlip.objects.filter(company=company).delete()
        PayRun.objects.filter(company=company).delete()
        Employee.objects.filter(company=company).delete()
    except Exception:
        pass
    StockCountSession.objects.filter(company=company).delete()
    StockTransfer.objects.filter(company=company).delete()
    InventoryCostLayer.objects.filter(company=company).delete()
    StockMovement.objects.filter(company=company).delete()
    StockBalance.objects.filter(company=company).delete()
    SerialNumber.objects.filter(company=company).delete()
    WarehouseReorderLevel.objects.filter(company=company).delete()
    InventoryRunningCost.objects.filter(company=company).delete()
    InventoryValuationSnapshot.objects.filter(company=company).delete()
    BatchLot.objects.filter(company=company).delete()
    Warehouse.objects.filter(company=company).delete()
    DocumentSeries.objects.filter(company=company).delete()
    IdempotencyRecord.objects.filter(company=company).delete()
    Notification.objects.filter(company=company).delete()
    RecurringInvoiceSchedule.objects.filter(company=company).delete()
    Customer.objects.filter(company=company).delete()
    Supplier.objects.filter(company=company).delete()
    Product.objects.filter(company=company).delete()
    FixedAsset.objects.filter(company=company).delete()
    Account.objects.filter(company=company).update(parent=None)
    Account.objects.filter(company=company).delete()
    FileAsset.objects.filter(company=company).delete()
    CompanyGstin.objects.filter(company=company).delete()


def _apply_company_profile(company, profile: dict) -> None:
    from accounts.models import Company

    skip = set(COMPANY_SKIP_FIELDS) | {"id", "company_id", "name"}
    kwargs = _copy_model_fields(Company, profile, skip=skip, remap={})
    for key, value in kwargs.items():
        if key == "company_id":
            continue
        setattr(company, key, value)
    company.save()


def _create_mapped(model, row, *, company, owner, skip: set[str], remap: dict, require: tuple[str, ...] = ()):
    kwargs = _copy_model_fields(model, row, skip=skip | {"id", "company_id", "created_by_id", "updated_by_id"}, remap=remap)
    if any(not kwargs.get(key) for key in require):
        return None
    field_names = {f.name for f in model._meta.concrete_fields}
    extras = {}
    if "created_by" in field_names:
        extras["created_by"] = owner
    if "updated_by" in field_names:
        extras["updated_by"] = owner
    return model.objects.create(company=company, **extras, **kwargs)


def _import_wipe_target_rows(
    *,
    target_company,
    payload: dict[str, Any],
    owner,
    customer_map,
    supplier_map,
    product_map,
    sales_map,
    purchase_map,
    warehouse_map,
    gstin_map,
    account_map,
    batch_map,
) -> None:
    """Restore wipe-target tables that sit outside the original core payload."""
    bank_map: dict[Any, int] = {}
    try:
        from payments.models import BankAccount

        for row in payload.get("bank_accounts") or []:
            if row.get("is_default") and BankAccount.objects.filter(company=target_company, is_default=True).exists():
                row = {**row, "is_default": False}
            obj = _create_mapped(
                BankAccount, row, company=target_company, owner=owner,
                skip=set(), remap={},
            )
            if obj:
                bank_map[row.get("id")] = obj.pk
    except Exception:
        pass

    lead_map: dict[Any, int] = {}
    try:
        from crm.models import Lead, LeadActivity, Opportunity

        for row in payload.get("leads") or []:
            obj = _create_mapped(
                Lead, row, company=target_company, owner=owner,
                skip=set(), remap={"customer_id": customer_map},
            )
            if obj:
                lead_map[row.get("id")] = obj.pk
        for row in payload.get("lead_activities") or []:
            _create_mapped(
                LeadActivity, row, company=target_company, owner=owner,
                skip=set(), remap={"lead_id": lead_map}, require=("lead_id",),
            )
        for row in payload.get("opportunities") or []:
            _create_mapped(
                Opportunity, row, company=target_company, owner=owner,
                skip=set(), remap={"lead_id": lead_map, "customer_id": customer_map},
            )
    except Exception:
        pass

    employee_map: dict[Any, int] = {}
    payrun_map: dict[Any, int] = {}
    try:
        from payroll.models import Employee, PayRun, PaySlip

        for row in payload.get("employees") or []:
            obj = _create_mapped(
                Employee, row, company=target_company, owner=owner,
                skip=set(), remap={},
            )
            if obj:
                employee_map[row.get("id")] = obj.pk
        for row in payload.get("pay_runs") or []:
            obj = _create_mapped(
                PayRun, row, company=target_company, owner=owner,
                skip=set(), remap={},
            )
            if obj:
                payrun_map[row.get("id")] = obj.pk
        for row in payload.get("pay_slips") or []:
            _create_mapped(
                PaySlip, row, company=target_company, owner=owner,
                skip=set(),
                remap={"employee_id": employee_map, "pay_run_id": payrun_map},
                require=("employee_id", "pay_run_id"),
            )
    except Exception:
        pass

    try:
        from sales.models import (
            RecurringInvoiceSchedule,
            RecurringInvoiceRun,
            SalesCreditNote,
            SalesCreditNoteItem,
            SalesDebitNote,
            SalesDebitNoteItem,
            SalesReturn,
            SalesReturnItem,
        )

        schedule_map: dict[Any, int] = {}
        for row in payload.get("recurring_schedules") or []:
            obj = _create_mapped(
                RecurringInvoiceSchedule, row, company=target_company, owner=owner,
                skip={"converted_invoice_id"},
                remap={"customer_id": customer_map, "company_gstin_id": gstin_map},
                require=("customer_id",),
            )
            if obj:
                schedule_map[row.get("id")] = obj.pk
        for row in payload.get("recurring_runs") or []:
            _create_mapped(
                RecurringInvoiceRun, row, company=target_company, owner=owner,
                skip=set(),
                remap={"schedule_id": schedule_map, "invoice_id": sales_map},
                require=("schedule_id",),
            )
        cn_map: dict[Any, int] = {}
        for row in payload.get("sales_credit_notes") or []:
            obj = _create_mapped(
                SalesCreditNote, row, company=target_company, owner=owner,
                skip={"sales_return_id"},
                remap={"customer_id": customer_map, "sales_invoice_id": sales_map},
                require=("customer_id", "sales_invoice_id"),
            )
            if obj:
                cn_map[row.get("id")] = obj.pk
        for row in payload.get("sales_credit_note_items") or []:
            _create_mapped(
                SalesCreditNoteItem, row, company=target_company, owner=owner,
                skip={"source_item_id"},
                remap={"credit_note_id": cn_map, "product_id": product_map},
                require=("credit_note_id", "product_id"),
            )
        dn_map: dict[Any, int] = {}
        for row in payload.get("sales_debit_notes") or []:
            obj = _create_mapped(
                SalesDebitNote, row, company=target_company, owner=owner,
                skip=set(),
                remap={"customer_id": customer_map, "sales_invoice_id": sales_map},
                require=("customer_id", "sales_invoice_id"),
            )
            if obj:
                dn_map[row.get("id")] = obj.pk
        for row in payload.get("sales_debit_note_items") or []:
            _create_mapped(
                SalesDebitNoteItem, row, company=target_company, owner=owner,
                skip={"source_item_id"},
                remap={"debit_note_id": dn_map, "product_id": product_map},
                require=("debit_note_id", "product_id"),
            )
        sr_map: dict[Any, int] = {}
        for row in payload.get("sales_returns") or []:
            obj = _create_mapped(
                SalesReturn, row, company=target_company, owner=owner,
                skip=set(),
                remap={"customer_id": customer_map, "sales_invoice_id": sales_map},
                require=("customer_id", "sales_invoice_id"),
            )
            if obj:
                sr_map[row.get("id")] = obj.pk
        for row in payload.get("sales_return_items") or []:
            _create_mapped(
                SalesReturnItem, row, company=target_company, owner=owner,
                skip=set(),
                remap={"sales_return_id": sr_map, "product_id": product_map},
                require=("sales_return_id", "product_id"),
            )
    except Exception:
        pass

    try:
        from purchases.models import (
            BillOfEntry,
            PurchaseCreditNote,
            PurchaseDebitNote,
            PurchaseOrder,
            PurchaseOrderItem,
            PurchaseReturn,
            PurchaseReturnItem,
        )

        po_map: dict[Any, int] = {}
        for row in payload.get("purchase_orders") or []:
            obj = _create_mapped(
                PurchaseOrder, row, company=target_company, owner=owner,
                skip={"converted_purchase_id"},
                remap={"supplier_id": supplier_map},
                require=("supplier_id",),
            )
            if obj:
                po_map[row.get("id")] = obj.pk
        for row in payload.get("purchase_order_items") or []:
            _create_mapped(
                PurchaseOrderItem, row, company=target_company, owner=owner,
                skip=set(),
                remap={"purchase_order_id": po_map, "product_id": product_map},
                require=("purchase_order_id", "product_id"),
            )
        for row in payload.get("purchase_credit_notes") or []:
            _create_mapped(
                PurchaseCreditNote, row, company=target_company, owner=owner,
                skip=set(),
                remap={"supplier_id": supplier_map, "purchase_invoice_id": purchase_map},
                require=("supplier_id",),
            )
        for row in payload.get("purchase_debit_notes") or []:
            _create_mapped(
                PurchaseDebitNote, row, company=target_company, owner=owner,
                skip=set(),
                remap={"supplier_id": supplier_map, "purchase_invoice_id": purchase_map},
                require=("supplier_id",),
            )
        pr_map: dict[Any, int] = {}
        for row in payload.get("purchase_returns") or []:
            obj = _create_mapped(
                PurchaseReturn, row, company=target_company, owner=owner,
                skip=set(),
                remap={"supplier_id": supplier_map, "purchase_invoice_id": purchase_map},
                require=("supplier_id",),
            )
            if obj:
                pr_map[row.get("id")] = obj.pk
        for row in payload.get("purchase_return_items") or []:
            _create_mapped(
                PurchaseReturnItem, row, company=target_company, owner=owner,
                skip={"batch_id"},
                remap={"purchase_return_id": pr_map, "product_id": product_map},
                require=("purchase_return_id", "product_id"),
            )
        for row in payload.get("bills_of_entry") or []:
            _create_mapped(
                BillOfEntry, row, company=target_company, owner=owner,
                skip=set(),
                remap={"supplier_id": supplier_map},
            )
    except Exception:
        pass

    try:
        from payments.models import PaymentLink
        import secrets

        for row in payload.get("payment_links") or []:
            kwargs = _copy_model_fields(
                PaymentLink, row,
                skip={"id", "company_id", "created_by_id", "updated_by_id", "token",
                      "provider_link_id", "provider_short_url", "paid_receipt_id"},
                remap={"sales_invoice_id": sales_map, "customer_id": customer_map},
            )
            PaymentLink.objects.create(
                company=target_company, created_by=owner, updated_by=owner,
                token=secrets.token_urlsafe(32), **kwargs,
            )
    except Exception:
        pass

    try:
        from manufacturing.models import Bom, BomLine, WorkOrder, WorkOrderLine

        bom_map: dict[Any, int] = {}
        for row in payload.get("boms") or []:
            obj = _create_mapped(
                Bom, row, company=target_company, owner=owner,
                skip=set(), remap={"product_id": product_map}, require=("product_id",),
            )
            if obj:
                bom_map[row.get("id")] = obj.pk
        for row in payload.get("bom_lines") or []:
            _create_mapped(
                BomLine, row, company=target_company, owner=owner,
                skip=set(),
                remap={"bom_id": bom_map, "component_id": product_map},
                require=("bom_id", "component_id"),
            )
        wo_map: dict[Any, int] = {}
        for row in payload.get("work_orders") or []:
            obj = _create_mapped(
                WorkOrder, row, company=target_company, owner=owner,
                skip=set(),
                remap={"bom_id": bom_map, "warehouse_id": warehouse_map},
                require=("bom_id",),
            )
            if obj:
                wo_map[row.get("id")] = obj.pk
        for row in payload.get("work_order_lines") or []:
            _create_mapped(
                WorkOrderLine, row, company=target_company, owner=owner,
                skip={"batch_id"},
                remap={"work_order_id": wo_map, "component_id": product_map},
                require=("work_order_id", "component_id"),
            )
    except Exception:
        pass

    try:
        from accounting.models import FixedAsset

        for row in payload.get("fixed_assets") or []:
            _create_mapped(
                FixedAsset, row, company=target_company, owner=owner,
                skip=set(),
                remap={
                    "asset_account_id": account_map,
                    "accumulated_depreciation_account_id": account_map,
                    "depreciation_expense_account_id": account_map,
                },
                require=("asset_account_id",),
            )
    except Exception:
        pass

    _ = (bank_map, batch_map)


def import_payload(*, target_company, payload: dict[str, Any], owner) -> None:
    from accounting.models import Account, JournalEntry, JournalLine
    from core.models import FileAsset
    from django.core.files.base import ContentFile
    from masters.models import Customer, Product, Supplier
    from payments.models import CustomerReceipt, PaymentAllocation, SupplierPayment
    from purchases.models import PurchaseInvoice, PurchaseItem
    from reporting.models import Gstr2bIngest
    from sales.models import (
        DeliveryChallan,
        DeliveryChallanItem,
        Quotation,
        QuotationItem,
        SalesInvoice,
        SalesItem,
        SalesOrder,
        SalesOrderItem,
    )
    from accounts.models import CompanyGstin
    from core.models import DocumentSeries
    from inventory.models import Warehouse, BatchLot, StockMovement, StockBalance, SerialNumber, InventoryCostLayer

    profile = payload.get("company") or {}
    _apply_company_profile(target_company, profile)

    gstin_map: dict[Any, int] = {}
    for row in payload.get("gstins") or []:
        kwargs = _copy_model_fields(
            CompanyGstin,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id"},
            remap={},
        )
        obj = CompanyGstin.objects.create(company=target_company, **kwargs)
        gstin_map[row.get("id")] = obj.pk

    for row in payload.get("document_series") or []:
        kwargs = _copy_model_fields(
            DocumentSeries,
            row,
            skip={"id", "company_id"},
            remap={},
        )
        doc_type = kwargs.get("doc_type")
        if not doc_type:
            continue
        gstin_key = kwargs.get("gstin_key") or ""
        fy_label = kwargs.get("fy_label") or ""
        defaults = {
            k: v
            for k, v in kwargs.items()
            if k not in {"doc_type", "gstin_key", "fy_label"}
        }
        DocumentSeries.objects.update_or_create(
            company=target_company,
            doc_type=doc_type,
            gstin_key=gstin_key,
            fy_label=fy_label,
            defaults=defaults,
        )

    warehouse_map: dict[Any, int] = {}
    default_wh = Warehouse.objects.filter(company=target_company, is_default=True).first()
    if default_wh:
        warehouse_map["default"] = default_wh.pk
    for row in payload.get("warehouses") or []:
        kwargs = _copy_model_fields(
            Warehouse,
            row,
            skip={"id", "company_id"},
            remap={},
        )
        if default_wh and kwargs.get("is_default"):
            warehouse_map[row.get("id")] = default_wh.pk
            continue
        existing = Warehouse.objects.filter(company=target_company, code=kwargs.get("code")).first()
        if existing:
            warehouse_map[row.get("id")] = existing.pk
        else:
            obj = Warehouse.objects.create(company=target_company, **kwargs)
            warehouse_map[row.get("id")] = obj.pk

    customer_map: dict[Any, int] = {}
    for row in payload.get("customers") or []:
        kwargs = _copy_model_fields(
            Customer,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "price_list_id"},
            remap={},
        )
        obj = Customer.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        customer_map[row.get("id")] = obj.pk

    supplier_map: dict[Any, int] = {}
    for row in payload.get("suppliers") or []:
        kwargs = _copy_model_fields(
            Supplier,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id"},
            remap={},
        )
        obj = Supplier.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        supplier_map[row.get("id")] = obj.pk

    product_map: dict[Any, int] = {}
    for row in payload.get("products") or []:
        kwargs = _copy_model_fields(
            Product,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "category_id", "brand_id", "unit_id"},
            remap={},
        )
        obj = Product.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        product_map[row.get("id")] = obj.pk

    batch_map: dict[Any, int] = {}
    for row in payload.get("batch_lots") or []:
        kwargs = _copy_model_fields(
            BatchLot,
            row,
            skip={"id", "company_id"},
            remap={"product_id": product_map},
        )
        if not kwargs.get("product_id"):
            continue
        obj = BatchLot.objects.create(company=target_company, **kwargs)
        batch_map[row.get("id")] = obj.pk

    sales_map: dict[Any, int] = {}
    for row in payload.get("sales_invoices") or []:
        kwargs = _copy_model_fields(
            SalesInvoice,
            row,
            skip={
                "id",
                "company_id",
                "created_by_id",
                "updated_by_id",
                "warehouse_id",
                "cost_center_id",
                "signature_id",
                "pdf_file_id",
            },
            remap={"customer_id": customer_map, "company_gstin_id": gstin_map},
        )
        obj = SalesInvoice.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        sales_map[row.get("id")] = obj.pk

    for row in payload.get("sales_items") or []:
        kwargs = _copy_model_fields(
            SalesItem,
            row,
            skip={"id", "company_id", "batch_id"},
            remap={"invoice_id": sales_map, "product_id": product_map},
        )
        if not kwargs.get("invoice_id") or not kwargs.get("product_id"):
            continue
        SalesItem.objects.create(company=target_company, **kwargs)

    quote_map: dict[Any, int] = {}
    for row in payload.get("quotations") or []:
        kwargs = _copy_model_fields(
            Quotation,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "converted_invoice_id", "converted_order_id"},
            remap={"customer_id": customer_map, "company_gstin_id": gstin_map},
        )
        obj = Quotation.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        quote_map[row.get("id")] = obj.pk
    for row in payload.get("quotation_items") or []:
        kwargs = _copy_model_fields(
            QuotationItem,
            row,
            skip={"id", "company_id"},
            remap={"quotation_id": quote_map, "product_id": product_map},
        )
        if not kwargs.get("quotation_id") or not kwargs.get("product_id"):
            continue
        QuotationItem.objects.create(company=target_company, **kwargs)

    order_map: dict[Any, int] = {}
    for row in payload.get("sales_orders") or []:
        kwargs = _copy_model_fields(
            SalesOrder,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "warehouse_id", "converted_invoice_id"},
            remap={"customer_id": customer_map, "company_gstin_id": gstin_map},
        )
        obj = SalesOrder.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        order_map[row.get("id")] = obj.pk
    for row in payload.get("sales_order_items") or []:
        kwargs = _copy_model_fields(
            SalesOrderItem,
            row,
            skip={"id", "company_id"},
            remap={"sales_order_id": order_map, "product_id": product_map},
        )
        if not kwargs.get("sales_order_id") or not kwargs.get("product_id"):
            continue
        SalesOrderItem.objects.create(company=target_company, **kwargs)

    for row in payload.get("delivery_challans") or []:
        kwargs = _copy_model_fields(
            DeliveryChallan,
            row,
            skip={
                "id",
                "company_id",
                "created_by_id",
                "updated_by_id",
                "warehouse_id",
                "pdf_file_id",
                "converted_invoice_id",
            },
            remap={"customer_id": customer_map, "sales_order_id": order_map},
        )
        challan = DeliveryChallan.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        old_id = row.get("id")
        for item_row in payload.get("delivery_challan_items") or []:
            if item_row.get("challan_id") != old_id:
                continue
            ikw = _copy_model_fields(
                DeliveryChallanItem,
                item_row,
                skip={"id", "company_id", "challan_id", "batch_id"},
                remap={"product_id": product_map},
            )
            if not ikw.get("product_id"):
                continue
            DeliveryChallanItem.objects.create(company=target_company, challan=challan, **ikw)

    purchase_map: dict[Any, int] = {}
    for row in payload.get("purchase_invoices") or []:
        kwargs = _copy_model_fields(
            PurchaseInvoice,
            row,
            skip={
                "id",
                "company_id",
                "created_by_id",
                "updated_by_id",
                "warehouse_id",
                "cost_center_id",
                "signature_id",
                "attachment_id",
            },
            remap={"supplier_id": supplier_map, "company_gstin_id": gstin_map},
        )
        obj = PurchaseInvoice.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        purchase_map[row.get("id")] = obj.pk

    for row in payload.get("purchase_items") or []:
        kwargs = _copy_model_fields(
            PurchaseItem,
            row,
            skip={"id", "company_id", "batch_id"},
            remap={"invoice_id": purchase_map, "product_id": product_map},
        )
        if not kwargs.get("invoice_id") or not kwargs.get("product_id"):
            continue
        PurchaseItem.objects.create(company=target_company, **kwargs)

    receipt_map: dict[Any, int] = {}
    for row in payload.get("receipts") or []:
        kwargs = _copy_model_fields(
            CustomerReceipt,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "bank_account_id", "gateway_payment_id"},
            remap={"customer_id": customer_map},
        )
        if not kwargs.get("customer_id"):
            continue
        obj = CustomerReceipt.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        receipt_map[row.get("id")] = obj.pk

    payment_map: dict[Any, int] = {}
    for row in payload.get("supplier_payments") or []:
        kwargs = _copy_model_fields(
            SupplierPayment,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "bank_account_id"},
            remap={"supplier_id": supplier_map},
        )
        if not kwargs.get("supplier_id"):
            continue
        obj = SupplierPayment.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        payment_map[row.get("id")] = obj.pk

    for row in payload.get("allocations") or []:
        kwargs = _copy_model_fields(
            PaymentAllocation,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id"},
            remap={
                "receipt_id": receipt_map,
                "supplier_payment_id": payment_map,
                "sales_invoice_id": sales_map,
                "purchase_invoice_id": purchase_map,
            },
        )
        if not ((kwargs.get("receipt_id") or kwargs.get("supplier_payment_id")) and (
            kwargs.get("sales_invoice_id") or kwargs.get("purchase_invoice_id")
        )):
            continue
        PaymentAllocation.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)

    account_map: dict[Any, int] = {}
    pending_parents: list[tuple[Any, Any]] = []
    for row in payload.get("accounts") or []:
        kwargs = _copy_model_fields(
            Account,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "parent_id", "bank_account_id"},
            remap={},
        )
        obj = Account.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        account_map[row.get("id")] = obj.pk
        if row.get("parent_id"):
            pending_parents.append((obj.pk, row.get("parent_id")))
    for new_id, old_parent in pending_parents:
        new_parent = account_map.get(old_parent)
        if new_parent:
            Account.objects.filter(pk=new_id).update(parent_id=new_parent)

    journal_map: dict[Any, int] = {}
    for row in payload.get("journals") or []:
        kwargs = _copy_model_fields(
            JournalEntry,
            row,
            skip={"id", "company_id", "created_by_id", "updated_by_id", "posted_by_id", "reversed_entry_id"},
            remap={},
        )
        obj = JournalEntry.objects.create(company=target_company, created_by=owner, updated_by=owner, **kwargs)
        journal_map[row.get("id")] = obj.pk

    for row in payload.get("journal_lines") or []:
        kwargs = _copy_model_fields(
            JournalLine,
            row,
            skip={"id", "company_id", "cost_center_id", "bank_statement_line_id"},
            remap={
                "entry_id": journal_map,
                "account_id": account_map,
                "customer_id": customer_map,
                "supplier_id": supplier_map,
            },
        )
        if not kwargs.get("entry_id") or not kwargs.get("account_id"):
            continue
        JournalLine.objects.create(company=target_company, **kwargs)

    for row in payload.get("stock_movements") or []:
        kwargs = _copy_model_fields(
            StockMovement,
            row,
            skip={"id", "company_id", "created_by_id", "reference_id"},
            remap={
                "warehouse_id": warehouse_map,
                "product_id": product_map,
                "batch_id": batch_map,
            },
        )
        if not kwargs.get("warehouse_id") or not kwargs.get("product_id"):
            continue
        # B6-019: `reference_id` is a plain CharField holding a stringified
        # source-document PK (e.g. the sales/purchase invoice this movement
        # came from) — `_copy_model_fields`'s generic remap only rewrites
        # real FK columns, so this was copied verbatim and dangled after
        # restore (pointing at the old tenant's row id, or an unrelated row
        # if that numeric id now belongs to someone else). Rewrite it
        # through the same id map the row's `reference_type` indicates when
        # one exists; blank it otherwise rather than leave a value that
        # looks valid but resolves to the wrong document.
        kwargs["reference_id"] = _remap_stock_movement_reference_id(
            row.get("reference_type") or "", row.get("reference_id"), sales_map, purchase_map
        )
        StockMovement.objects.create(company=target_company, created_by=owner, **kwargs)

    for row in payload.get("stock_balances") or []:
        kwargs = _copy_model_fields(
            StockBalance,
            row,
            skip={"id", "company_id"},
            remap={
                "warehouse_id": warehouse_map,
                "product_id": product_map,
                "batch_id": batch_map,
            },
        )
        if not kwargs.get("warehouse_id") or not kwargs.get("product_id"):
            continue
        StockBalance.objects.create(company=target_company, **kwargs)

    for row in payload.get("serial_numbers") or []:
        kwargs = _copy_model_fields(
            SerialNumber,
            row,
            skip={"id", "company_id"},
            remap={
                "warehouse_id": warehouse_map,
                "product_id": product_map,
                "batch_id": batch_map,
            },
        )
        if not kwargs.get("warehouse_id") or not kwargs.get("product_id"):
            continue
        SerialNumber.objects.create(company=target_company, **kwargs)

    for row in payload.get("inventory_cost_layers") or []:
        kwargs = _copy_model_fields(
            InventoryCostLayer,
            row,
            skip={"id", "company_id"},
            remap={
                "warehouse_id": warehouse_map,
                "product_id": product_map,
                "batch_id": batch_map,
            },
        )
        if not kwargs.get("warehouse_id") or not kwargs.get("product_id"):
            continue
        InventoryCostLayer.objects.create(company=target_company, **kwargs)

    for row in payload.get("gstr2b") or []:
        kwargs = _copy_model_fields(
            Gstr2bIngest,
            row,
            skip={"id", "company_id"},
            remap={"purchase_invoice_id": purchase_map},
        )
        Gstr2bIngest.objects.create(company=target_company, **kwargs)

    _import_wipe_target_rows(
        target_company=target_company,
        payload=payload,
        owner=owner,
        customer_map=customer_map,
        supplier_map=supplier_map,
        product_map=product_map,
        sales_map=sales_map,
        purchase_map=purchase_map,
        warehouse_map=warehouse_map,
        gstin_map=gstin_map,
        account_map=account_map,
        batch_map=batch_map,
    )

    for row in payload.get("file_assets") or []:
        raw_b64 = row.get("bytes_b64")
        if not raw_b64:
            continue
        try:
            content = base64.b64decode(raw_b64)
        except (ValueError, TypeError):
            continue
        asset = FileAsset(
            company=target_company,
            kind=row.get("kind") or FileAsset.Kind.ATTACHMENT,
            original_name=row.get("original_name") or "restored.bin",
            content_type=row.get("content_type") or "application/octet-stream",
            size=len(content),
            created_by=owner,
            updated_by=owner,
        )
        asset.file.save(asset.original_name, ContentFile(content), save=True)


@transaction.atomic
def restore_to_sandbox(*, source_company, payload: dict[str, Any], owner):
    from django.conf import settings

    from accounts.models import Company, CompanyUser
    from core.exceptions import BusinessRuleError

    # B6-006: a sandbox restore creates a full company copy of real tenant
    # data -- cap how many an owner can have live at once rather than
    # letting them accumulate unboundedly.
    max_sandboxes = int(getattr(settings, "MAX_CONCURRENT_SANDBOXES", 3) or 0)
    if max_sandboxes > 0:
        existing = CompanyUser.objects.filter(
            user=owner, role=CompanyUser.Role.OWNER, company__is_sandbox=True,
        ).count()
        if existing >= max_sandboxes:
            raise BusinessRuleError(
                f"You already have {existing} sandbox compan{'y' if existing == 1 else 'ies'} "
                f"(limit {max_sandboxes}). Ask an admin to remove an old one before creating another."
            )

    # B6-006: copy the requester's real AI capability flags from their
    # membership on the source company instead of hard-coding everything to
    # True -- a sandbox must not grant AI access a source membership never had.
    source_membership = CompanyUser.objects.filter(company=source_company, user=owner).first()
    ai_insights = bool(source_membership and source_membership.can_view_ai_insights)
    ai_assistant = bool(source_membership and source_membership.can_use_ai_assistant)

    source_name = (source_company.name or "company").strip() or "company"
    sandbox_name = f"{SANDBOX_NAME_PREFIX}{source_name}"[:255]
    expires = timezone.now() + timedelta(days=SANDBOX_TTL_DAYS)
    sandbox = Company.objects.create(
        name=sandbox_name,
        state=source_company.state or "",
        is_sandbox=True,
        sandbox_expires_at=expires,
    )
    CompanyUser.objects.create(
        company=sandbox,
        user=owner,
        role=CompanyUser.Role.OWNER,
        can_manage_inventory=True,
        can_import=True,
        can_cancel_documents=True,
        can_view_financial_reports=True,
        can_export=True,
        can_view_ai_insights=ai_insights,
        can_use_ai_assistant=ai_assistant,
        can_create_sales=True,
        can_create_purchases=True,
        can_create_payments=True,
        can_post_journals=True,
    )
    # R-014: inherit the source plan (modules/seat_limit) without extra seats —
    # sandbox membership is the same Owner only. Do not copy Razorpay ids.
    from billing.models import Subscription
    from billing.services import ensure_register_trial, subscription_for_company

    source_sub = subscription_for_company(source_company)
    if source_sub and source_sub.plan_id:
        Subscription.objects.create(
            company=sandbox,
            plan=source_sub.plan,
            status=source_sub.status,
            trial_ends_at=source_sub.trial_ends_at,
            current_period_end=source_sub.current_period_end,
        )
    else:
        ensure_register_trial(sandbox)
    # B6-001: PostgresRlsMiddleware has app.company_id pinned to the requester's
    # *active* company; every tenant-table INSERT for `sandbox` would fail the
    # RLS WITH CHECK. import_payload sets company= explicitly on every row, so a
    # bypass is safe here.
    from core.rls import rls_bypass

    with rls_bypass():
        import_payload(target_company=sandbox, payload=payload, owner=owner)
    sandbox.refresh_from_db()
    touch = []
    if sandbox.name != sandbox_name:
        sandbox.name = sandbox_name
        touch.append("name")
    if not sandbox.is_sandbox:
        sandbox.is_sandbox = True
        touch.append("is_sandbox")
    if sandbox.sandbox_expires_at != expires:
        sandbox.sandbox_expires_at = expires
        touch.append("sandbox_expires_at")
    if touch:
        sandbox.save(update_fields=touch)
    return sandbox


def unbacked_live_counts(company, payload: dict[str, Any]) -> dict[str, int]:
    """Rows wipe would drop that are not represented in the backup payload."""
    from accounting.models import Account, JournalEntry
    from accounts.models import CompanyGstin
    from core.models import DocumentSeries, FileAsset
    from inventory.models import BatchLot, InventoryCostLayer, SerialNumber, StockBalance, StockMovement, Warehouse
    from masters.models import Customer, Product, Supplier
    from payments.models import BankAccount, CustomerReceipt, PaymentAllocation, PaymentLink, ReconMatch, SupplierPayment
    from purchases.models import (
        BillOfEntry,
        PurchaseCreditNote,
        PurchaseDebitNote,
        PurchaseInvoice,
        PurchaseOrder,
        PurchaseReturn,
    )
    from reporting.models import Gstr2bIngest
    from sales.models import (
        DeliveryChallan,
        Quotation,
        SalesCreditNote,
        SalesDebitNote,
        SalesInvoice,
        SalesOrder,
        SalesReturn,
    )

    mapping = (
        ("gstins", CompanyGstin),
        ("document_series", DocumentSeries),
        ("customers", Customer),
        ("suppliers", Supplier),
        ("products", Product),
        ("warehouses", Warehouse),
        ("batch_lots", BatchLot),
        ("stock_balances", StockBalance),
        ("stock_movements", StockMovement),
        ("serial_numbers", SerialNumber),
        ("inventory_cost_layers", InventoryCostLayer),
        ("sales_invoices", SalesInvoice),
        ("purchase_invoices", PurchaseInvoice),
        ("receipts", CustomerReceipt),
        ("supplier_payments", SupplierPayment),
        ("allocations", PaymentAllocation),
        ("accounts", Account),
        ("journals", JournalEntry),
        ("quotations", Quotation),
        ("sales_orders", SalesOrder),
        ("delivery_challans", DeliveryChallan),
        ("sales_credit_notes", SalesCreditNote),
        ("sales_debit_notes", SalesDebitNote),
        ("sales_returns", SalesReturn),
        ("purchase_orders", PurchaseOrder),
        ("purchase_credit_notes", PurchaseCreditNote),
        ("purchase_debit_notes", PurchaseDebitNote),
        ("purchase_returns", PurchaseReturn),
        ("bills_of_entry", BillOfEntry),
        ("gstr2b", Gstr2bIngest),
        ("file_assets", FileAsset),
        ("payment_links", PaymentLink),
        ("recon_matches", ReconMatch),
        ("bank_accounts", BankAccount),
    )
    try:
        from accounting.models import FixedAsset
        from manufacturing.models import Bom
        from sales.models import RecurringInvoiceSchedule

        mapping = mapping + (
            ("fixed_assets", FixedAsset),
            ("boms", Bom),
            ("recurring_schedules", RecurringInvoiceSchedule),
        )
    except Exception:
        pass
    try:
        from crm.models import Lead

        mapping = mapping + (("leads", Lead),)
    except Exception:
        pass
    try:
        from payroll.models import Employee

        mapping = mapping + (("employees", Employee),)
    except Exception:
        pass
    extra: dict[str, int] = {}
    for key, model in mapping:
        live = model.objects.filter(company=company).count()
        backed = len(payload.get(key) or [])
        if live > backed:
            extra[key] = live - backed
    return extra


@transaction.atomic
def restore_destroy_in_place(*, company, payload: dict[str, Any], owner, confirm_destroy_unbacked: bool = False):
    extra = unbacked_live_counts(company, payload)
    if extra and not confirm_destroy_unbacked:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError(
            "Destroy-in-place would drop live rows that are not in this backup "
            f"({extra}). Pass confirm_destroy_unbacked=true to proceed.",
            code="UNBACKED_ROWS",
        )
    # B6-001: robust even when the caller's active company != the one being
    # restored (an owner restoring a different company they own).
    from core.rls import rls_bypass

    with rls_bypass():
        wipe_logical_tenant_rows(company)
        import_payload(target_company=company, payload=payload, owner=owner)
    return company


def delete_sandbox_company(company) -> None:
    """Wipe business rows, clear PROTECT audit trails, then delete the sandbox company."""
    from accounts.models import CompanyUser, User
    from core.models import AuditEvent, MoneyFieldAudit, StatutoryDocumentEvent
    from core.rls import rls_bypass

    with rls_bypass():
        wipe_logical_tenant_rows(company)
        AuditEvent.objects.filter(company=company).update(company=None)
        MoneyFieldAudit.objects.filter(company=company).delete()
        StatutoryDocumentEvent.objects.filter(company=company).delete()
        User.objects.filter(active_company=company).update(active_company=None)
        CompanyUser.objects.filter(company=company).delete()
        company.delete()


def sweep_expired_sandboxes() -> int:
    """Daily janitor: delete sandbox companies whose sandbox_expires_at has passed."""
    from accounts.models import Company
    from core.rls import rls_bypass

    now = timezone.now()
    with rls_bypass():
        expired = list(
            Company.objects.filter(is_sandbox=True, sandbox_expires_at__isnull=False, sandbox_expires_at__lte=now)
        )
    deleted = 0
    for sandbox in expired:
        try:
            delete_sandbox_company(sandbox)
            deleted += 1
        except Exception:  # noqa: BLE001 — one bad sandbox must not block the sweep
            logger.exception("Failed to delete expired sandbox company %s", sandbox.pk)
    return deleted

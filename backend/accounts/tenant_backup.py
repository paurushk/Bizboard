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
import zipfile
from datetime import date, datetime
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
        "billing_override_active",
    }
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
    from sales.models import SalesInvoice, SalesItem
    from accounts.models import CompanyGstin

    company_profile = _row_dict(company, extra_exclude=COMPANY_SKIP_FIELDS)
    gstins = _rows(CompanyGstin.objects.filter(company=company).order_by("id"))
    customers = _rows(Customer.objects.filter(company=company).order_by("id"), extra_exclude={"price_list_id"})
    suppliers = _rows(Supplier.objects.filter(company=company).order_by("id"))
    products = _rows(
        Product.objects.filter(company=company).order_by("id"),
        extra_exclude={"category_id", "brand_id", "unit_id"},
    )
    sales_invoices = _rows(
        SalesInvoice.objects.filter(company=company).order_by("id"),
        extra_exclude={"warehouse_id", "cost_center_id", "signature_id", "pdf_file_id"},
    )
    sales_items = _rows(
        SalesItem.objects.filter(company=company).order_by("id"),
        extra_exclude={"batch_id"},
    )
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
    for asset in FileAsset.objects.filter(company=company).order_by("id"):
        entry = {
            "id": asset.pk,
            "kind": asset.kind,
            "original_name": asset.original_name,
            "content_type": asset.content_type,
            "size": asset.size,
            "checksum_sha256": _file_checksum(asset),
            "bytes_b64": None,
        }
        if asset.size and asset.size <= SMALL_FILE_MAX_BYTES:
            try:
                asset.file.open("rb")
                entry["bytes_b64"] = base64.b64encode(asset.file.read()).decode("ascii")
            except Exception:  # noqa: BLE001
                entry["bytes_b64"] = None
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
        "customers": customers,
        "suppliers": suppliers,
        "products": products,
        "sales_invoices": sales_invoices,
        "sales_items": sales_items,
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
    }


def encrypt_export_zip(payload: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({
            "version": payload.get("version"),
            "exported_at": payload.get("exported_at"),
            "source_company_id": payload.get("source_company_id"),
            "source_company_name": payload.get("source_company_name"),
            "gstr2b_summary": payload.get("gstr2b_summary") or {},
        }, default=_json_default, indent=2))
        json_sections = (
            "company",
            "gstins",
            "customers",
            "suppliers",
            "products",
            "sales_invoices",
            "sales_items",
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
        )
        for key in json_sections:
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
        payload = {
            "version": manifest.get("version", EXPORT_VERSION),
            "exported_at": manifest.get("exported_at"),
            "source_company_id": manifest.get("source_company_id"),
            "source_company_name": manifest.get("source_company_name"),
            "gstr2b_summary": manifest.get("gstr2b_summary") or _load("gstr2b_summary.json") or {},
            "company": _load("company.json") or {},
            "gstins": _load("gstins.json") or [],
            "customers": _load("customers.json") or [],
            "suppliers": _load("suppliers.json") or [],
            "products": _load("products.json") or [],
            "sales_invoices": _load("sales_invoices.json") or [],
            "sales_items": _load("sales_items.json") or [],
            "purchase_invoices": _load("purchase_invoices.json") or [],
            "purchase_items": _load("purchase_items.json") or [],
            "receipts": _load("receipts.json") or [],
            "supplier_payments": _load("supplier_payments.json") or [],
            "allocations": _load("allocations.json") or [],
            "accounts": _load("accounts.json") or [],
            "journals": _load("journals.json") or [],
            "journal_lines": _load("journal_lines.json") or [],
            "gstr2b": _load("gstr2b.json") or [],
            "file_assets": _load("file_assets.json") or [],
        }
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
    from accounting.models import Account, JournalEntry, JournalLine
    from core.models import FileAsset
    from inventory.models import BatchLot, InventoryCostLayer, SerialNumber, StockBalance, StockMovement
    from masters.models import Customer, Product, Supplier
    from payments.models import CustomerReceipt, PaymentAllocation, SupplierPayment
    from purchases.models import PurchaseInvoice
    from reporting.models import Gstr2bIngest
    from sales.models import SalesInvoice
    from accounts.models import CompanyGstin

    PaymentAllocation.objects.filter(company=company).delete()
    JournalLine.objects.filter(company=company).delete()
    JournalEntry.objects.filter(company=company).update(reversed_entry=None)
    JournalEntry.objects.filter(company=company).delete()
    Gstr2bIngest.objects.filter(company=company).delete()
    CustomerReceipt.objects.filter(company=company).delete()
    SupplierPayment.objects.filter(company=company).delete()
    SalesInvoice.objects.filter(company=company).delete()
    PurchaseInvoice.objects.filter(company=company).delete()
    InventoryCostLayer.objects.filter(company=company).delete()
    StockMovement.objects.filter(company=company).delete()
    StockBalance.objects.filter(company=company).delete()
    SerialNumber.objects.filter(company=company).delete()
    BatchLot.objects.filter(company=company).delete()
    Customer.objects.filter(company=company).delete()
    Supplier.objects.filter(company=company).delete()
    Product.objects.filter(company=company).delete()
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


def import_payload(*, target_company, payload: dict[str, Any], owner) -> None:
    from accounting.models import Account, JournalEntry, JournalLine
    from core.models import FileAsset
    from django.core.files.base import ContentFile
    from masters.models import Customer, Product, Supplier
    from payments.models import CustomerReceipt, PaymentAllocation, SupplierPayment
    from purchases.models import PurchaseInvoice, PurchaseItem
    from reporting.models import Gstr2bIngest
    from sales.models import SalesInvoice, SalesItem
    from accounts.models import CompanyGstin

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

    for row in payload.get("gstr2b") or []:
        kwargs = _copy_model_fields(
            Gstr2bIngest,
            row,
            skip={"id", "company_id"},
            remap={"purchase_invoice_id": purchase_map},
        )
        Gstr2bIngest.objects.create(company=target_company, **kwargs)

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
    from accounts.models import Company, CompanyUser

    sandbox_name = f"{source_company.name} (sandbox restore)"
    sandbox = Company.objects.create(name=sandbox_name, state=source_company.state or "")
    CompanyUser.objects.create(
        company=sandbox,
        user=owner,
        role=CompanyUser.Role.OWNER,
        can_manage_inventory=True,
        can_import=True,
        can_cancel_documents=True,
        can_view_financial_reports=True,
        can_export=True,
        can_view_ai_insights=True,
        can_use_ai_assistant=True,
        can_create_sales=True,
        can_create_purchases=True,
        can_create_payments=True,
        can_post_journals=True,
    )
    import_payload(target_company=sandbox, payload=payload, owner=owner)
    sandbox.refresh_from_db()
    if sandbox.name != sandbox_name:
        sandbox.name = sandbox_name
        sandbox.save(update_fields=["name"])
    return sandbox


@transaction.atomic
def restore_destroy_in_place(*, company, payload: dict[str, Any], owner):
    wipe_logical_tenant_rows(company)
    import_payload(target_company=company, payload=payload, owner=owner)
    return company

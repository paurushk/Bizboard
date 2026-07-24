"""Import Service — CSV pipeline + purchase-bill LLM extraction."""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.validators import ALLOWED_GST_RATES, GSTIN_RE, HSN_RE
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier
from purchases.models import PurchaseInvoice
from purchases.services import PurchaseService

from .models import ImportJob

REQUIRED_COLUMNS = {
    ImportJob.Kind.CUSTOMERS: ["name"],
    ImportJob.Kind.SUPPLIERS: ["name"],
    ImportJob.Kind.PRODUCTS: ["name"],
    ImportJob.Kind.OPENING_STOCK: ["sku", "quantity"],
}

ALLOWED_GST = {Decimal(r) for r in ALLOWED_GST_RATES}


def _line_get(line: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        if key in line and line[key] is not None:
            return str(line[key]).strip()
    return default


def _validate_row(kind, row, company):
    errors = []
    if kind in (ImportJob.Kind.CUSTOMERS, ImportJob.Kind.SUPPLIERS, ImportJob.Kind.PRODUCTS):
        if not (row.get("name") or "").strip():
            errors.append("name is required")
        gstin = (row.get("gstin") or "").strip()
        if gstin and not GSTIN_RE.match(gstin):
            errors.append("invalid GSTIN format")
    if kind == ImportJob.Kind.PRODUCTS:
        hsn = (row.get("hsn_code") or "").strip()
        if hsn and not HSN_RE.match(hsn):
            errors.append("invalid HSN code")
        for field in ("gst_rate", "purchase_price", "selling_price"):
            value = (row.get(field) or "").strip()
            if value:
                try:
                    Decimal(value)
                except InvalidOperation:
                    errors.append(f"{field} must be a number")
    if kind == ImportJob.Kind.OPENING_STOCK:
        sku = (row.get("sku") or "").strip()
        if not sku:
            errors.append("sku is required")
        elif not Product.objects.filter(company=company, sku=sku).exists():
            errors.append(f"no product with sku '{sku}'")
        try:
            if Decimal((row.get("quantity") or "").strip() or "0") <= 0:
                errors.append("quantity must be > 0")
        except InvalidOperation:
            errors.append("quantity must be a number")
    return errors


def _as_decimal(value, default="0"):
    try:
        return Decimal(str(value if value not in (None, "") else default).strip())
    except (InvalidOperation, AttributeError):
        raise BusinessRuleError(f"Invalid number: {value!r}")


def _normalize_gst_rate(value) -> Decimal:
    rate = _as_decimal(value, "18")
    if rate not in ALLOWED_GST:
        # Snap common OCR noise to nearest allowed rate, else 18.
        nearest = min(ALLOWED_GST, key=lambda allowed: abs(allowed - rate))
        if abs(nearest - rate) <= Decimal("0.5"):
            return nearest
        return Decimal("18")
    return rate


def _bill_line_errors(line: dict) -> list[str]:
    errors = []
    if not str(line.get("name") or "").strip():
        errors.append("name is required")
    try:
        if _as_decimal(line.get("quantity"), "0") <= 0:
            errors.append("quantity must be > 0")
    except BusinessRuleError:
        errors.append("quantity must be a number")
    try:
        _as_decimal(line.get("unit_price"), "0")
    except BusinessRuleError:
        errors.append("unit_price must be a number")
    hsn = str(line.get("hsn_code") or "").strip()
    if hsn and not HSN_RE.match(hsn):
        errors.append("invalid HSN code")
    return errors


class ImportService:
    @staticmethod
    def validate(job: ImportJob):
        """Parse + validate the uploaded CSV; store preview and error report."""
        if job.kind == ImportJob.Kind.PURCHASE_BILL:
            raise BusinessRuleError("Purchase bill imports use LLM extraction, not CSV validate.")
        raw = job.file.file.open("rb").read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise BusinessRuleError("File must be UTF-8 encoded CSV.")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise BusinessRuleError("CSV file has no header row.")
        fieldnames = [f.strip().lower() for f in reader.fieldnames]
        missing = [c for c in REQUIRED_COLUMNS[job.kind] if c not in fieldnames]
        if missing:
            raise BusinessRuleError(f"Missing required columns: {', '.join(missing)}.")

        preview, errors = [], []
        for index, raw_row in enumerate(reader, start=2):  # header is row 1
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
            row_errors = _validate_row(job.kind, row, job.company)
            if row_errors:
                errors.append({"row": index, "errors": row_errors, "data": row})
            else:
                preview.append(row)

        job.total_rows = len(preview) + len(errors)
        job.valid_rows = len(preview)
        job.error_rows = len(errors)
        job.preview = preview
        job.errors = errors
        job.status = ImportJob.Status.PREVIEWED
        job.save()
        return job

    @staticmethod
    @transaction.atomic
    def commit(job: ImportJob, user):
        """Write validated rows only; failed rows stay in the error report."""
        if job.kind == ImportJob.Kind.PURCHASE_BILL:
            return BillImportService.commit(job, user)

        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Import must be previewed before commit.")
        created = 0
        for row in job.preview:
            if job.kind == ImportJob.Kind.CUSTOMERS:
                Customer.objects.create(
                    company=job.company, name=row["name"], phone=row.get("phone", ""),
                    email=row.get("email", ""), gstin=row.get("gstin", ""),
                    state=row.get("state", ""), billing_address=row.get("address", ""),
                    created_by=user, updated_by=user,
                )
            elif job.kind == ImportJob.Kind.SUPPLIERS:
                Supplier.objects.create(
                    company=job.company, name=row["name"], phone=row.get("phone", ""),
                    email=row.get("email", ""), gstin=row.get("gstin", ""),
                    state=row.get("state", ""), address=row.get("address", ""),
                    created_by=user, updated_by=user,
                )
            elif job.kind == ImportJob.Kind.PRODUCTS:
                Product.objects.create(
                    company=job.company, name=row["name"], sku=row.get("sku", ""),
                    barcode=row.get("barcode", ""), hsn_code=row.get("hsn_code", ""),
                    gst_rate=Decimal(row.get("gst_rate") or "0"),
                    purchase_price=Decimal(row.get("purchase_price") or "0"),
                    selling_price=Decimal(row.get("selling_price") or "0"),
                    reorder_level=Decimal(row.get("reorder_level") or "0"),
                    created_by=user, updated_by=user,
                )
            elif job.kind == ImportJob.Kind.OPENING_STOCK:
                product = Product.objects.get(company=job.company, sku=row["sku"])
                InventoryService.post_movement(
                    company=job.company, product=product,
                    movement_type=MovementType.OPENING_STOCK,
                    quantity=Decimal(row["quantity"]),
                    unit_cost=Decimal(row["unit_cost"]) if row.get("unit_cost") else None,
                    reference_type="import", reference_id=job.pk, user=user,
                )
            created += 1

        job.status = ImportJob.Status.COMMITTED
        job.committed_at = timezone.now()
        job.updated_by = user
        job.save()
        AuditService.log(
            company=job.company, user=user, action="IMPORT",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Imported {created} {job.kind.lower()} rows",
            metadata={"created": created, "errors": job.error_rows},
        )
        return created


class BillImportService:
    @staticmethod
    def start_extraction(job: ImportJob):
        if job.kind != ImportJob.Kind.PURCHASE_BILL:
            raise BusinessRuleError("Only purchase bill jobs can be extracted.")
        if job.status not in (ImportJob.Status.UPLOADED, ImportJob.Status.FAILED):
            raise BusinessRuleError("Extraction can only start from UPLOADED or FAILED.")
        job.status = ImportJob.Status.EXTRACTING
        job.failure_reason = ""
        job.errors = []
        job.save(update_fields=["status", "failure_reason", "errors", "updated_at"])
        from imports.tasks import extract_purchase_bill_task

        extract_purchase_bill_task.delay(job.pk)
        return job

    @staticmethod
    def apply_extraction(job: ImportJob, payload: dict):
        lines = list(payload.get("lines") or [])
        preview = {
            "supplier_name": str(payload.get("supplier_name") or "").strip(),
            "supplier_gstin": str(payload.get("supplier_gstin") or "").strip(),
            "bill_number": str(payload.get("bill_number") or "").strip(),
            "bill_date": str(payload.get("bill_date") or "").strip(),
            "lines": [],
        }
        errors = []
        for index, raw_line in enumerate(lines, start=1):
            line = {
                "name": _line_get(raw_line, "name"),
                "sku": _line_get(raw_line, "sku"),
                "hsn_code": _line_get(raw_line, "hsn_code", "hsnCode", "hsn"),
                "quantity": _line_get(raw_line, "quantity", default="1") or "1",
                "unit_price": _line_get(raw_line, "unit_price", "unitPrice", "rate", default="0") or "0",
                "gst_rate": str(_normalize_gst_rate(
                    _line_get(raw_line, "gst_rate", "gstRate", default="18") or "18"
                )),
                "mrp": _line_get(raw_line, "mrp", default="0") or "0",
                "include": bool(raw_line.get("include", True)),
            }
            line_errors = _bill_line_errors(line)
            if line_errors:
                errors.append({"row": index, "errors": line_errors, "data": line})
                line["include"] = False
            preview["lines"].append(line)

        included = [ln for ln in preview["lines"] if ln.get("include")]
        job.preview = preview
        job.errors = errors
        job.total_rows = len(preview["lines"])
        job.valid_rows = len(included)
        job.error_rows = len(errors)
        job.status = ImportJob.Status.PREVIEWED
        job.failure_reason = ""
        job.save()
        return job

    @staticmethod
    def mark_failed(job: ImportJob, reason: str):
        job.status = ImportJob.Status.FAILED
        job.failure_reason = (reason or "Extraction failed.")[:2000]
        job.save(update_fields=["status", "failure_reason", "updated_at"])
        return job

    @staticmethod
    def update_preview(job: ImportJob, data: dict, user=None):
        if job.kind != ImportJob.Kind.PURCHASE_BILL:
            raise BusinessRuleError("Preview update is only for purchase bill imports.")
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Only previewed purchase bill jobs can be edited.")

        preview = dict(job.preview or {})
        if not isinstance(preview, dict):
            preview = {"lines": []}

        if "supplier_name" in data:
            preview["supplier_name"] = str(data.get("supplier_name") or "").strip()
        if "supplier_gstin" in data:
            preview["supplier_gstin"] = str(data.get("supplier_gstin") or "").strip()
        if "bill_number" in data:
            preview["bill_number"] = str(data.get("bill_number") or "").strip()
        if "bill_date" in data:
            preview["bill_date"] = str(data.get("bill_date") or "").strip()

        if "lines" in data:
            lines_in = data.get("lines") or []
            if not isinstance(lines_in, list):
                raise BusinessRuleError("lines must be an array.")
            lines, errors = [], []
            for index, raw_line in enumerate(lines_in, start=1):
                if not isinstance(raw_line, dict):
                    continue
                line = {
                    "name": _line_get(raw_line, "name"),
                    "sku": _line_get(raw_line, "sku"),
                    "hsn_code": _line_get(raw_line, "hsn_code", "hsnCode", "hsn"),
                    "quantity": _line_get(raw_line, "quantity", default="1") or "1",
                    "unit_price": _line_get(raw_line, "unit_price", "unitPrice", "rate", default="0") or "0",
                    "gst_rate": str(_normalize_gst_rate(
                        _line_get(raw_line, "gst_rate", "gstRate", default="18") or "18"
                    )),
                    "mrp": _line_get(raw_line, "mrp", default="0") or "0",
                    "include": bool(raw_line.get("include", True)),
                }
                line_errors = _bill_line_errors(line) if line.get("include") else []
                if line_errors:
                    errors.append({"row": index, "errors": line_errors, "data": line})
                    line["include"] = False
                lines.append(line)
            preview["lines"] = lines
            job.errors = errors
            job.total_rows = len(lines)
            job.valid_rows = len([ln for ln in lines if ln.get("include")])
            job.error_rows = len(errors)

        job.preview = preview

        supplier_id = data.get("supplier_id", data.get("supplier"))
        if supplier_id is not None and supplier_id != "":
            try:
                supplier = Supplier.objects.get(pk=supplier_id, company=job.company)
            except (Supplier.DoesNotExist, ValueError, TypeError):
                raise BusinessRuleError("Invalid supplier.")
            job.supplier = supplier

        if user is not None:
            job.updated_by = user
        job.save()
        return job

    @staticmethod
    def _match_or_create_product(company, line: dict, user) -> tuple[Product, bool]:
        sku = str(line.get("sku") or "").strip()
        name = str(line.get("name") or "").strip()
        product = None
        if sku:
            product = Product.objects.filter(company=company).filter(
                Q(sku__iexact=sku) | Q(barcode__iexact=sku)
            ).first()
        if product is None and name:
            product = Product.objects.filter(company=company, name__iexact=name).first()

        unit_price = _as_decimal(line.get("unit_price"), "0")
        gst_rate = _normalize_gst_rate(line.get("gst_rate"))
        mrp = _as_decimal(line.get("mrp"), "0")
        hsn = str(line.get("hsn_code") or "").strip()

        if product is None:
            product = Product.objects.create(
                company=company,
                name=name,
                sku=sku,
                hsn_code=hsn,
                gst_rate=gst_rate,
                purchase_price=unit_price,
                selling_price=Decimal("0"),
                mrp=mrp,
                created_by=user,
                updated_by=user,
            )
            return product, True

        updates = []
        # Matched products: only fill empty HSN; never overwrite gst/price from OCR noise.
        if hsn and not product.hsn_code:
            product.hsn_code = hsn
            updates.append("hsn_code")
        if line.get("update_master"):
            if unit_price > 0 and product.purchase_price != unit_price:
                product.purchase_price = unit_price
                updates.append("purchase_price")
            if product.gst_rate != gst_rate:
                product.gst_rate = gst_rate
                updates.append("gst_rate")
            if mrp > 0 and product.mrp != mrp:
                product.mrp = mrp
                updates.append("mrp")
        if updates:
            product.updated_by = user
            updates.extend(["updated_by", "updated_at"])
            product.save(update_fields=updates)
        return product, False

    @staticmethod
    def _resolve_supplier(job: ImportJob, user) -> Supplier:
        if job.supplier_id:
            return job.supplier
        preview = job.preview if isinstance(job.preview, dict) else {}
        gstin = str(preview.get("supplier_gstin") or "").strip()
        name = str(preview.get("supplier_name") or "").strip()
        supplier = None
        if gstin:
            supplier = Supplier.objects.filter(company=job.company, gstin__iexact=gstin).first()
        if supplier is None and name:
            supplier = Supplier.objects.filter(company=job.company, name__iexact=name).first()
        if supplier is None:
            if not name:
                raise BusinessRuleError("Select a supplier before committing the purchase bill.")
            supplier = Supplier.objects.create(
                company=job.company,
                name=name,
                gstin=gstin if gstin and GSTIN_RE.match(gstin) else "",
                created_by=user,
                updated_by=user,
            )
        job.supplier = supplier
        job.save(update_fields=["supplier", "updated_at"])
        return supplier

    @staticmethod
    def _parse_bill_date(value: str, *, required: bool = False):
        value = (value or "").strip()
        if not value:
            if required:
                raise BusinessRuleError(
                    "Bill date is missing or could not be parsed. Set bill date before committing."
                )
            return timezone.localdate()
        parsed = parse_date(value)
        if parsed:
            return parsed
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise BusinessRuleError(
            f"Could not parse bill date '{value}'. Use YYYY-MM-DD or DD/MM/YYYY."
        )

    @staticmethod
    @transaction.atomic
    def commit(job: ImportJob, user):
        if job.kind != ImportJob.Kind.PURCHASE_BILL:
            raise BusinessRuleError("Not a purchase bill import.")
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Import must be previewed before commit.")

        preview = job.preview if isinstance(job.preview, dict) else {}
        lines = [ln for ln in (preview.get("lines") or []) if ln.get("include")]
        if not lines:
            raise BusinessRuleError("Select at least one valid line to commit.")

        supplier = BillImportService._resolve_supplier(job, user)
        items_data = []
        products_created = 0
        for line in lines:
            product, created = BillImportService._match_or_create_product(job.company, line, user)
            if created:
                products_created += 1
            items_data.append({
                "product": product,
                "description": product.name,
                "quantity": _as_decimal(line.get("quantity"), "1"),
                "unit_price": _as_decimal(line.get("unit_price"), "0"),
                "discount_percent": Decimal("0"),
                "gst_rate": _normalize_gst_rate(line.get("gst_rate")),
            })

        invoice = PurchaseInvoice.objects.create(
            company=job.company,
            supplier=supplier,
            purchase_type=PurchaseInvoice.PurchaseType.GST,
            invoice_date=BillImportService._parse_bill_date(
                str(preview.get("bill_date") or ""),
                required=bool(str(preview.get("bill_date") or "").strip()),
            ),
            supplier_bill_number=str(preview.get("bill_number") or "")[:64],
            notes="Created from purchase bill upload",
            attachment=job.file,
            created_by=user,
            updated_by=user,
        )
        PurchaseService.set_items(invoice, items_data, user)

        job.purchase_invoice = invoice
        job.status = ImportJob.Status.COMMITTED
        job.committed_at = timezone.now()
        job.updated_by = user
        job.save()
        AuditService.log(
            company=job.company, user=user, action="IMPORT",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Imported purchase bill → draft purchase #{invoice.pk}",
            metadata={
                "products_created": products_created,
                "lines": len(items_data),
                "purchase_invoice_id": invoice.pk,
            },
        )
        return {
            "created": len(items_data),
            "products_created": products_created,
            "purchase_invoice_id": invoice.pk,
        }

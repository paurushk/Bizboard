"""Import Service — CSV pipeline: validate → preview → commit → error report (E1.8)."""

import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.validators import GSTIN_RE, HSN_RE
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier

from .models import ImportJob

REQUIRED_COLUMNS = {
    ImportJob.Kind.CUSTOMERS: ["name"],
    ImportJob.Kind.SUPPLIERS: ["name"],
    ImportJob.Kind.PRODUCTS: ["name"],
    ImportJob.Kind.OPENING_STOCK: ["sku", "quantity"],
}


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


class ImportService:
    @staticmethod
    def validate(job: ImportJob):
        """Parse + validate the uploaded CSV; store preview and error report."""
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
            row = { (k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items() }
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

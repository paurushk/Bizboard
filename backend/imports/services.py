"""Import Service — CSV pipeline + purchase-bill LLM extraction."""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.models import CompanyGstin
from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.files import CSV_UTF8_HINT
from core.validators import ALLOWED_GST_RATES, GSTIN_RE, HSN_RE, validate_gst_rate
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier, Unit
from purchases.models import PurchaseInvoice
from purchases.services import PurchaseService
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import ImportJob, SupplierBillTemplate
from .qty_formula import (
    apply_qty_formula,
    collect_extras,
    detect_qty_clarifications,
    infer_qty_formula,
)

OCR_BILL_MIN_CONFIDENCE = float(getattr(settings, "OCR_BILL_MIN_CONFIDENCE", 0.7) or 0.7)
BILL_TEMPLATE_SIGNATURE_MATCH_THRESHOLD = 0.7

REQUIRED_COLUMNS = {
    ImportJob.Kind.CUSTOMERS: ["name"],
    ImportJob.Kind.SUPPLIERS: ["name"],
    ImportJob.Kind.PRODUCTS: ["name"],
    ImportJob.Kind.OPENING_STOCK: ["sku", "quantity"],
}

# Fuzzy header aliases for master CSV/XLSX imports (Tally / POS / Excel exports).
MASTER_COLUMN_ALIASES = {
    "name": ["name", "product name", "item", "item name", "item description", "description", "product"],
    "sku": ["sku", "item code", "product code", "pcode", "code", "itemcode"],
    "barcode": ["barcode", "ean", "upc", "bar code"],
    "hsn_code": ["hsn_code", "hsn", "hsn code", "hsn/sac", "hsn_sac"],
    "gst_rate": ["gst_rate", "gst", "gst%", "tax_rate", "tax%", "gst rate"],
    "purchase_price": ["purchase_price", "purchase price", "cost", "buy price", "purchase rate"],
    "selling_price": ["selling_price", "selling price", "sale price", "mrp", "sell price", "rate"],
    "reorder_level": ["reorder_level", "reorder level", "reorder", "min stock"],
    "quantity": ["quantity", "qty", "pcs", "pieces", "stock", "stock qty"],
    "unit_cost": ["unit_cost", "unit cost", "cost price", "opening cost"],
    "opening_stock": ["opening_stock", "opening stock", "opening qty", "opening quantity"],
    "unit": ["unit", "unit_name", "uom", "uqc"],
    "phone": ["phone", "mobile", "contact", "phone number"],
    "email": ["email", "e-mail"],
    "gstin": ["gstin", "gst no", "gstin number"],
    "state": ["state"],
    "address": ["address", "billing_address", "billing address"],
}

ALLOWED_GST = {Decimal(r) for r in ALLOWED_GST_RATES}

BULK_BATCH = 500


def _decode_csv_text(raw: bytes) -> str:
    """UTF-8 (with BOM) first, then Windows-1252 — Excel's default CSV export."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        raise BusinessRuleError(CSV_UTF8_HINT)


def resolve_master_column_mappings(fieldnames: list[str]) -> list[dict]:
    """Non-identity alias resolutions: original header → canonical field."""
    present = {(f or "").strip().lower() for f in fieldnames if f}
    mappings = []
    claimed = set()
    for field, aliases in MASTER_COLUMN_ALIASES.items():
        if field in present or field in claimed:
            continue
        for alias in aliases:
            if alias != field and alias in present:
                mappings.append({"source": alias, "target": field})
                claimed.add(field)
                break
    return mappings


def _line_get(line: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        if key in line and line[key] is not None:
            return str(line[key]).strip()
    return default


def _map_master_row(row: dict) -> dict:
    """Map fuzzy / aliased headers onto canonical master field names."""
    normalized = {(k or "").strip().lower(): ("" if v is None else str(v)).strip() for k, v in row.items()}
    mapped = dict(normalized)
    for field, aliases in MASTER_COLUMN_ALIASES.items():
        if mapped.get(field):
            continue
        for alias in aliases:
            if alias in normalized and normalized[alias]:
                mapped[field] = normalized[alias]
                break
    return mapped


def _validate_row(
    kind,
    row,
    company,
    *,
    seen_skus=None,
    seen_barcodes=None,
    existing_skus=None,
    existing_barcodes=None,
    products_by_sku=None,
    skus_with_opening=None,
):
    """Validate one CSV row. seen_* sets track within-file duplicates for products."""
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
        for field in ("gst_rate", "purchase_price", "selling_price", "reorder_level", "opening_stock", "quantity", "unit_cost"):
            value = (row.get(field) or "").strip()
            if value:
                try:
                    num = Decimal(value)
                    if field in ("purchase_price", "selling_price", "reorder_level", "unit_cost") and num < 0:
                        errors.append(f"{field} must be >= 0")
                    elif field in ("opening_stock", "quantity") and num <= 0:
                        errors.append(f"{field} must be > 0")
                except InvalidOperation:
                    errors.append(f"{field} must be a number")
        gst_rate_raw = (row.get("gst_rate") or "").strip()
        if gst_rate_raw:
            try:
                validate_gst_rate(gst_rate_raw)
            except Exception as exc:
                from django.core.exceptions import ValidationError as DjangoValidationError

                if isinstance(exc, DjangoValidationError):
                    errors.extend(list(exc.messages))
                else:
                    errors.append(str(exc))
        sku = (row.get("sku") or "").strip()
        barcode = (row.get("barcode") or "").strip()
        if sku:
            key = sku.casefold()
            if seen_skus is not None and key in seen_skus:
                errors.append(f"duplicate sku '{sku}' in file")
            elif existing_skus is not None and key in existing_skus:
                errors.append(f"sku '{sku}' already exists")
            elif existing_skus is None and Product.objects.filter(company=company, sku__iexact=sku).exists():
                errors.append(f"sku '{sku}' already exists")
            elif seen_skus is not None:
                seen_skus.add(key)
        if barcode:
            key = barcode.casefold()
            if seen_barcodes is not None and key in seen_barcodes:
                errors.append(f"duplicate barcode '{barcode}' in file")
            elif existing_barcodes is not None and key in existing_barcodes:
                errors.append(f"barcode '{barcode}' already exists")
            elif existing_barcodes is None and Product.objects.filter(company=company, barcode__iexact=barcode).exists():
                errors.append(f"barcode '{barcode}' already exists")
            elif seen_barcodes is not None:
                seen_barcodes.add(key)
    if kind == ImportJob.Kind.OPENING_STOCK:
        sku = (row.get("sku") or "").strip()
        if not sku:
            errors.append("sku is required")
        else:
            key = sku.casefold()
            if seen_skus is not None and key in seen_skus:
                errors.append(f"duplicate sku '{sku}' in file")
            elif seen_skus is not None:
                seen_skus.add(key)
            if products_by_sku is not None:
                product = products_by_sku.get(key)
            else:
                product = Product.objects.filter(company=company, sku__iexact=sku).first()
            if not product:
                errors.append(f"no product with sku '{sku}'")
            else:
                if skus_with_opening is not None:
                    already_has_opening = product.pk in skus_with_opening
                else:
                    already_has_opening = StockMovement.objects.filter(
                        company=company,
                        product=product,
                        movement_type=MovementType.OPENING_STOCK,
                    ).exclude(reference_type="import_voided").exists()
                if already_has_opening:
                    errors.append(f"opening stock already recorded for '{product.name}'")
        qty_raw = (row.get("quantity") or "").strip()
        if not qty_raw:
            errors.append("quantity is required")
        else:
            try:
                if Decimal(qty_raw) <= 0:
                    errors.append("quantity must be > 0")
            except InvalidOperation:
                errors.append("quantity must be a number")
        unit_cost_raw = (row.get("unit_cost") or "").strip()
        if unit_cost_raw:
            try:
                if Decimal(unit_cost_raw) < 0:
                    errors.append("unit_cost must be >= 0")
            except InvalidOperation:
                errors.append("unit_cost must be a number")
    return errors


def _as_decimal(value, default="0"):
    try:
        return Decimal(str(value if value not in (None, "") else default).strip())
    except (InvalidOperation, AttributeError):
        raise BusinessRuleError(f"Invalid number: {value!r}")


def _parse_extraction_confidence(value) -> float:
    try:
        confidence = float(str(value if value not in (None, "") else "1").strip())
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, confidence))


def _normalize_gst_rate(value, *, warnings: list | None = None, row: int | None = None) -> Decimal:
    """Snap OCR GST rates to an allowed slab; optionally record a warning (PUR-09)."""
    rate = _as_decimal(value, "18")
    if rate not in ALLOWED_GST:
        # Snap common OCR noise to nearest allowed rate, else 18.
        nearest = min(ALLOWED_GST, key=lambda allowed: abs(allowed - rate))
        if abs(nearest - rate) <= Decimal("0.5"):
            snapped = nearest
            reason = f"GST rate {rate} snapped to nearest allowed rate {snapped}"
        else:
            snapped = Decimal("18")
            reason = f"GST rate {rate} defaulted to 18 (not near an allowed slab)"
        if warnings is not None:
            prefix = f"Row {row}: " if row is not None else ""
            warnings.append(f"{prefix}{reason}")
        return snapped
    return rate


def _preview_bill_line(raw_line: dict, *, index: int, rate_warnings: list[str]) -> dict:
    """Build a preview line without inventing qty=1 or GST=18 for unread OCR fields."""
    line_warnings: list[str] = []
    qty = _line_get(raw_line, "quantity")
    gst_raw = _line_get(raw_line, "gst_rate", "gstRate")
    if gst_raw:
        gst_rate = str(_normalize_gst_rate(gst_raw, warnings=line_warnings, row=index))
    else:
        gst_rate = ""
    # Prefer explicit include from LLM normalize; otherwise require readable qty+GST.
    if "include" in raw_line:
        include = bool(raw_line.get("include"))
    else:
        include = bool(qty) and bool(gst_rate)
    extras = collect_extras(raw_line)
    line = {
        "name": _line_get(raw_line, "name"),
        "sku": _line_get(raw_line, "sku"),
        "hsn_code": _line_get(raw_line, "hsn_code", "hsnCode", "hsn"),
        "quantity": qty,
        "unit_price": _line_get(raw_line, "unit_price", "unitPrice", "rate", default="0") or "0",
        "gst_rate": gst_rate,
        "mrp": _line_get(raw_line, "mrp", default="0") or "0",
        "include": include,
        "cs": extras.get("cs") or _line_get(raw_line, "cs"),
        "upc": extras.get("upc") or _line_get(raw_line, "upc"),
        "printed_gross_amt": _line_get(raw_line, "printed_gross_amt"),
        "printed_taxable_amt": _line_get(raw_line, "printed_taxable_amt"),
        "extras": extras,
        "flags": list(raw_line.get("flags") or []) if isinstance(raw_line.get("flags"), list) else [],
    }
    if line_warnings:
        line["warnings"] = line_warnings
        rate_warnings.extend(line_warnings)
    return line


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


def _safe_decimal(value) -> Decimal:
    try:
        text = str(value if value not in (None, "") else "0").strip()
        return Decimal(text) if text else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _detect_clarifications(payload: dict) -> list[dict]:
    """Document-level qty-formula ambiguity (Redesign Plan §4.2/§4.3).

    Options are derived from whatever count/pack columns this bill actually
    has — not a hardcoded Cs/Pcs/UPC questionnaire.
    """
    return detect_qty_clarifications(payload.get("lines") or [])


def _infer_qty_answers(lines: list[dict], *, tolerance: Decimal) -> dict | None:
    expr = infer_qty_formula(lines, tolerance=tolerance)
    if not expr:
        return None
    return {"qty_formula": expr}


def _apply_cross_check(lines: list[dict], answers: dict, *, tolerance: Decimal) -> str:
    return apply_qty_formula(lines, answers, tolerance=tolerance)


def _refresh_line_validity(lines: list[dict]) -> list[dict]:
    """Re-evaluate include/errors after quantity recombination.

    Case-only DMS rows (Cs>0, Pcs=0) fail `quantity must be > 0` on the first
    pass; once qty is rewritten as (Cs×UPC)+Pcs they must be brought back in.
    """
    errors = []
    for index, line in enumerate(lines, start=1):
        line_errors = _bill_line_errors(line)
        if line_errors:
            line["include"] = False
            errors.append({"row": index, "errors": line_errors, "data": line})
            continue
        gst_ok = bool(str(line.get("gst_rate") or "").strip())
        try:
            qty_ok = _as_decimal(line.get("quantity"), "0") > 0
        except BusinessRuleError:
            qty_ok = False
        if qty_ok and gst_ok:
            line["include"] = True
    return errors


def _match_bill_template(company, gstin: str, column_headers: list[str]) -> SupplierBillTemplate | None:
    """GSTIN is the primary key; column signature (order-independent) guards
    against applying a stale template after the vendor changes their layout."""
    if not gstin:
        return None
    template = SupplierBillTemplate.objects.filter(company=company, gstin__iexact=gstin).first()
    if template is None:
        return None
    stored = {str(h).strip().upper() for h in (template.column_signature or [])}
    seen = {str(h).strip().upper() for h in (column_headers or [])}
    if not stored or not seen:
        return template
    overlap = len(stored & seen) / max(len(stored), 1)
    if overlap < BILL_TEMPLATE_SIGNATURE_MATCH_THRESHOLD:
        return None
    return template


def _template_answers(template: SupplierBillTemplate) -> dict:
    mapping = template.column_mapping if isinstance(template.column_mapping, dict) else {}
    if mapping.get("qty_formula"):
        return {"qty_formula": mapping["qty_formula"]}
    if template.line_total_formula == SupplierBillTemplate.LineTotalFormula.CASE_UNITS_PLUS_LOOSE:
        return {"qty_formula": "cs*upc+quantity"}
    return {"qty_formula": "quantity"}


def _resolve_import_company_gstin(company, preview: dict, *, kind: str):
    """Stamp filing identity from buyer GSTIN (sales) or primary CompanyGstin."""
    wanted = ""
    if kind == ImportJob.Kind.SALES_BILL:
        wanted = str(preview.get("buyer_gstin") or "").strip().upper()
    else:
        wanted = str(preview.get("company_gstin") or preview.get("buyer_gstin") or "").strip().upper()
        known = {
            (g or "").upper()
            for g in CompanyGstin.objects.filter(company=company, is_active=True).values_list("gstin", flat=True)
        }
        if getattr(company, "gstin", ""):
            known.add(company.gstin.upper())
        if wanted and wanted not in known:
            wanted = ""
    qs = CompanyGstin.objects.filter(company=company, is_active=True)
    if wanted:
        hit = qs.filter(gstin__iexact=wanted).first()
        if hit:
            return hit
    return qs.filter(is_primary=True).order_by("-id").first() or qs.order_by("id").first()


def _infer_direction_warning(kind: str, payload: dict, company) -> str:
    """Bill Import Redesign Plan §4.5: GSTIN-based sanity check, surfaced as a
    warning (not a block) since the user already picked purchase vs. sales by
    which upload flow they used."""
    company_gstins = {
        g.upper() for g in CompanyGstin.objects.filter(company=company, is_active=True)
        .values_list("gstin", flat=True)
    }
    if getattr(company, "gstin", ""):
        company_gstins.add(company.gstin.upper())
    if not company_gstins:
        return ""
    seller = (payload.get("supplier_gstin") or "").upper()
    buyer = (payload.get("buyer_gstin") or "").upper()
    if kind == ImportJob.Kind.PURCHASE_BILL and seller and seller in company_gstins:
        return (
            "This bill's seller GSTIN matches your company — it looks like a sales "
            "invoice you issued, not a purchase bill. Upload it from Sales instead?"
        )
    if kind == ImportJob.Kind.SALES_BILL and buyer and buyer in company_gstins:
        return (
            "This bill's buyer GSTIN matches your company — it looks like a purchase "
            "bill you received, not a sales invoice. Upload it from Purchases instead?"
        )
    return ""


BILL_COLUMN_ALIASES = {
    "name": ["name", "item", "item description", "description", "product", "product name"],
    "sku": ["sku", "pcode", "item code", "product code", "code"],
    "hsn_code": ["hsn", "hsn_code", "hsn code", "hsn/sac"],
    "quantity": ["quantity", "qty", "pcs", "pieces"],
    "unit_price": ["unit_price", "rate", "price", "pc price", "pcs price", "unit rate"],
    "gst_rate": ["gst_rate", "gst", "gst%", "tax_rate", "tax%", "gst %"],
    "mrp": ["mrp"],
    "cs": ["cs", "cases", "ctn", "cartons"],
    "upc": ["upc", "units per case", "pcs/cs"],
    "printed_gross_amt": ["printed_gross_amt", "gross amt", "gross amount", "gross", "gross value"],
}


def _xlsx_best_bill_rows(workbook) -> list[dict]:
    """Read every sheet once (read-only iterators are single-pass) and pick
    the one whose header looks like a bill line-item table.

    ChatGPT/DMS exports often put invoice meta on the first sheet and the
    actual Cs/Pcs/UPC rows on a later 'Line Items' sheet — `active` would
    miss them.
    """
    candidates: list[tuple[int, int, list[dict]]] = []
    for sheet in workbook.worksheets:
        rows_iter = sheet.iter_rows(values_only=True)
        header = [str(h or "").strip().lower() for h in (next(rows_iter, None) or [])]
        if not header:
            continue
        header_set = set(header)
        score = sum(
            1
            for token in (
                "item", "item description", "description", "particulars", "product",
                "qty", "quantity", "pcs", "hsn", "rate", "amount", "taxable",
                "sku", "code", "pcode", "mrp", "cs", "upc", "gross amt",
                "pc price", "pcs price",
            )
            if token in header_set or any(token in h for h in header_set)
        )
        data = []
        for raw_row in rows_iter:
            if raw_row is None or all(v in (None, "") for v in raw_row):
                continue
            data.append({header[i]: raw_row[i] for i in range(min(len(header), len(raw_row)))})
        candidates.append((score, len(data), data))
    if not candidates:
        return []
    scored = [c for c in candidates if c[0] >= 2]
    pool = scored or candidates
    pool.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return pool[0][2]


def _read_structured_rows(raw: bytes, filename: str) -> list[dict]:
    """Deterministic CSV/XLSX row reader for the bill-import 'I have an
    export' path (§4.1) — no LLM involved, exact by construction."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return _xlsx_best_bill_rows(workbook)

    try:
        text = _decode_csv_text(raw)
    except BusinessRuleError:
        raise
    reader = csv.DictReader(io.StringIO(text))
    return [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader]


def _map_structured_row(row: dict) -> dict:
    mapped = {}
    claimed = set()
    for field, aliases in BILL_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in row and row[alias] not in (None, ""):
                mapped[field] = row[alias]
                claimed.add(alias)
                break
    leftovers = {k: v for k, v in row.items() if k not in claimed}
    extras = collect_extras({**leftovers, "raw_columns": leftovers})
    if extras:
        mapped["extras"] = extras
        if "cs" not in mapped and extras.get("cs") is not None:
            mapped["cs"] = extras["cs"]
        if "upc" not in mapped and extras.get("upc") is not None:
            mapped["upc"] = extras["upc"]
    return mapped


class ImportService:
    @staticmethod
    def validate(job: ImportJob):
        """Parse + validate the uploaded CSV/XLSX; store preview and error report."""
        if job.kind == ImportJob.Kind.PURCHASE_BILL:
            raise BusinessRuleError("Purchase bill imports use LLM extraction, not CSV validate.")
        if job.kind in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Bill imports use a separate extraction pipeline.")
        with job.file.file.open("rb") as handle:
            raw = handle.read()
        filename = job.file.original_name or job.file.file.name or ""
        name_lower = filename.lower()
        if name_lower.endswith((".xlsx", ".xlsm")):
            rows = _read_structured_rows(raw, filename)
            if not rows and not raw:
                raise BusinessRuleError("CSV file has no header row.")
            # Reconstruct fieldnames from first row keys (already lowercased).
            fieldnames = list(rows[0].keys()) if rows else []
            if not fieldnames:
                # Empty workbook — try to detect header-only via openpyxl path returning [].
                raise BusinessRuleError("CSV file has no header row.")
        else:
            text = _decode_csv_text(raw)
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                raise BusinessRuleError("CSV file has no header row.")
            fieldnames = [f.strip().lower() for f in reader.fieldnames]
            rows = [{(k or "").strip().lower(): v for k, v in raw_row.items()} for raw_row in reader]

        # Required columns after alias expansion: accept either canonical or any alias.
        required = REQUIRED_COLUMNS[job.kind]
        available = set(fieldnames)
        for aliases in MASTER_COLUMN_ALIASES.values():
            available.update(aliases)
        # Also treat present aliased headers as satisfying canonical requirements.
        present_canonical = set(fieldnames)
        for field, aliases in MASTER_COLUMN_ALIASES.items():
            if any(a in fieldnames for a in aliases):
                present_canonical.add(field)
        missing = [c for c in required if c not in present_canonical]
        if missing:
            raise BusinessRuleError(f"Missing required columns: {', '.join(missing)}.")

        # Bulk prefetch for duplicate / existence checks (avoid per-row queries).
        existing_skus = {
            (s or "").casefold()
            for s in Product.objects.filter(company=job.company).exclude(sku="")
            .values_list("sku", flat=True)
        }
        existing_barcodes = {
            (b or "").casefold()
            for b in Product.objects.filter(company=job.company).exclude(barcode="")
            .values_list("barcode", flat=True)
        }
        products_by_sku = {
            (p.sku or "").casefold(): p
            for p in Product.objects.filter(company=job.company).exclude(sku="")
        }
        skus_with_opening = set(
            StockMovement.objects.filter(
                company=job.company,
                movement_type=MovementType.OPENING_STOCK,
            )
            .exclude(reference_type="import_voided")
            .values_list("product_id", flat=True)
        )

        preview, errors = [], []
        seen_skus, seen_barcodes = set(), set()
        for index, raw_row in enumerate(rows, start=2):  # header is row 1
            row = _map_master_row(raw_row)
            row_errors = _validate_row(
                job.kind, row, job.company,
                seen_skus=seen_skus, seen_barcodes=seen_barcodes,
                existing_skus=existing_skus, existing_barcodes=existing_barcodes,
                products_by_sku=products_by_sku, skus_with_opening=skus_with_opening,
            )
            if row_errors:
                errors.append({"row": index, "errors": row_errors, "data": row})
            else:
                preview.append(row)

        job.total_rows = len(preview) + len(errors)
        job.valid_rows = len(preview)
        job.error_rows = len(errors)
        job.preview = preview
        job.errors = errors
        job.column_mappings = resolve_master_column_mappings(fieldnames)
        job.status = ImportJob.Status.PREVIEWED
        job.save()
        return job

    @staticmethod
    @transaction.atomic
    def commit(job: ImportJob, user):
        """
        All-or-nothing write of previewed rows (duplicates caught at validate).
        Locks the ImportJob row and re-checks PREVIEWED before writing.
        """
        if job.kind in ImportJob.BILL_KINDS:
            return BillImportService.commit(job, user)

        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Import must be previewed before commit.")
        preview = job.preview if isinstance(job.preview, list) else []
        if job.kind == ImportJob.Kind.CUSTOMERS:
            created = ImportService._commit_customers(job, preview, user)
        elif job.kind == ImportJob.Kind.SUPPLIERS:
            created = ImportService._commit_suppliers(job, preview, user)
        elif job.kind == ImportJob.Kind.PRODUCTS:
            created = ImportService._commit_products(job, preview, user)
        elif job.kind == ImportJob.Kind.OPENING_STOCK:
            created = ImportService._commit_opening_stock(job, preview, user)
        else:
            raise BusinessRuleError(f"Unsupported import kind '{job.kind}'.")

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

    @staticmethod
    def _post_opening_items(job, items, user):
        if not items:
            return
        movements = InventoryService.post_opening_movements_batch(
            company=job.company,
            items=items,
            reference_type="import",
            reference_id=job.pk,
            user=user,
        )
        if job.company.accounting_enabled:
            from accounting.services import PostingService

            for movement in movements:
                PostingService.post_opening_stock(movement, user)

    @staticmethod
    def _commit_customers(job, preview, user):
        now = timezone.now()
        Customer.objects.bulk_create(
            [
                Customer(
                    company=job.company,
                    name=row["name"],
                    phone=row.get("phone", "") or "",
                    email=row.get("email", "") or "",
                    gstin=row.get("gstin", "") or "",
                    state=row.get("state", "") or "",
                    billing_address=row.get("address", "") or "",
                    created_by=user,
                    updated_by=user,
                    created_at=now,
                    updated_at=now,
                )
                for row in preview
            ],
            batch_size=BULK_BATCH,
        )
        return len(preview)

    @staticmethod
    def _commit_suppliers(job, preview, user):
        now = timezone.now()
        Supplier.objects.bulk_create(
            [
                Supplier(
                    company=job.company,
                    name=row["name"],
                    phone=row.get("phone", "") or "",
                    email=row.get("email", "") or "",
                    gstin=row.get("gstin", "") or "",
                    state=row.get("state", "") or "",
                    address=row.get("address", "") or "",
                    created_by=user,
                    updated_by=user,
                    created_at=now,
                    updated_at=now,
                )
                for row in preview
            ],
            batch_size=BULK_BATCH,
        )
        return len(preview)

    @staticmethod
    def _resolve_units(company, preview, user):
        wanted = {}
        for row in preview:
            unit_str = (row.get("unit") or row.get("unit_name") or "").strip()
            if unit_str:
                wanted[unit_str.casefold()] = unit_str
        if not wanted:
            return {}
        existing = list(Unit.objects.filter(company=company))
        by_key = {}
        for unit in existing:
            by_key[unit.name.casefold()] = unit
            by_key[unit.short_name.casefold()] = unit
        now = timezone.now()
        missing = []
        missing_keys = []
        for key, orig in wanted.items():
            if key not in by_key:
                missing_keys.append(key)
                missing.append(
                    Unit(
                        company=company,
                        name=orig.upper(),
                        short_name=orig.upper()[:10],
                        uqc_code=orig.upper()[:8],
                        created_by=user,
                        updated_by=user,
                        created_at=now,
                        updated_at=now,
                    )
                )
        if missing:
            created = Unit.objects.bulk_create(missing, batch_size=BULK_BATCH)
            for unit in created:
                by_key[unit.name.casefold()] = unit
                by_key[unit.short_name.casefold()] = unit
        return by_key

    @staticmethod
    def _commit_products(job, preview, user):
        now = timezone.now()
        units = ImportService._resolve_units(job.company, preview, user)
        products = []
        opening_specs = []
        for row in preview:
            unit_str = (row.get("unit") or row.get("unit_name") or "").strip()
            unit_obj = units.get(unit_str.casefold()) if unit_str else None
            purchase_price = Decimal(row.get("purchase_price") or "0")
            products.append(
                Product(
                    company=job.company,
                    name=row["name"],
                    sku=row.get("sku", "") or "",
                    barcode=row.get("barcode", "") or "",
                    hsn_code=row.get("hsn_code", "") or "",
                    unit=unit_obj,
                    gst_rate=Decimal(row.get("gst_rate") or "0"),
                    purchase_price=purchase_price,
                    selling_price=Decimal(row.get("selling_price") or "0"),
                    reorder_level=Decimal(row.get("reorder_level") or "0"),
                    created_by=user,
                    updated_by=user,
                    created_at=now,
                    updated_at=now,
                )
            )
            opening_stock_raw = (row.get("opening_stock") or row.get("quantity") or "").strip()
            opening_qty = Decimal("0")
            if opening_stock_raw:
                try:
                    opening_qty = Decimal(opening_stock_raw)
                except InvalidOperation:
                    opening_qty = Decimal("0")
            if opening_qty > 0:
                unit_cost_val = (
                    Decimal(row["unit_cost"])
                    if (row.get("unit_cost") or "").strip()
                    else (purchase_price if purchase_price > 0 else None)
                )
                opening_specs.append((True, opening_qty, unit_cost_val))
            else:
                opening_specs.append((False, None, None))

        created_products = Product.objects.bulk_create(products, batch_size=BULK_BATCH)
        opening_items = [
            {"product": product, "quantity": qty, "unit_cost": cost}
            for product, (has_opening, qty, cost) in zip(created_products, opening_specs)
            if has_opening
        ]
        ImportService._post_opening_items(job, opening_items, user)
        return len(preview)

    @staticmethod
    def _commit_opening_stock(job, preview, user):
        needed = {(row.get("sku") or "").strip().casefold() for row in preview}
        products_by_sku = {
            (p.sku or "").casefold(): p
            for p in Product.objects.filter(company=job.company).exclude(sku="")
            if (p.sku or "").casefold() in needed
        }
        items = []
        for row in preview:
            sku = (row.get("sku") or "").strip()
            product = products_by_sku.get(sku.casefold())
            if not product:
                raise BusinessRuleError(f"No product with sku '{sku}' found.")
            items.append({
                "product": product,
                "quantity": Decimal(row["quantity"]),
                "unit_cost": Decimal(row["unit_cost"]) if (row.get("unit_cost") or "").strip() else None,
            })
        ImportService._post_opening_items(job, items, user)
        return len(preview)

    @staticmethod
    def _movement_is_unused(movement) -> str:
        """Return an error string if this opening movement cannot be reversed, else ''."""
        from inventory.models import InventoryCostLayer

        qty = abs(Decimal(str(movement.quantity or 0)))
        if qty <= 0:
            return ""
        layers = list(
            InventoryCostLayer.objects.select_for_update().filter(source_movement=movement)
        )
        if layers:
            remaining = sum((Decimal(str(layer.qty_remaining or 0)) for layer in layers), Decimal("0"))
            if remaining < qty:
                return (
                    f"Cannot void: stock from '{movement.product.name}' has already been "
                    "used (sold/issued). Void unused rows individually, or use Adjust Stock "
                    "to correct quantities."
                )
        available = InventoryService.available_quantity(
            movement.company, movement.product, warehouse=movement.warehouse, batch=movement.batch
        )
        if available < qty:
            return (
                f"Cannot void: insufficient available stock for '{movement.product.name}' "
                "to reverse the opening quantity. Use Adjust Stock to correct quantities."
            )
        return ""

    @staticmethod
    def _reverse_import_movement(job, movement, user):
        qty = abs(Decimal(str(movement.quantity or 0)))
        if qty <= 0:
            StockMovement.objects.filter(pk=movement.pk).update(reference_type="import_voided")
            return
        InventoryService.post_movement(
            company=job.company,
            product=movement.product,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-qty,
            reason=f"Void import #{job.pk}",
            reference_type="import_void",
            reference_id=job.pk,
            user=user,
            warehouse=movement.warehouse,
            batch=movement.batch,
            skip_negative_check=False,
        )
        if job.company.accounting_enabled:
            from accounting.models import JournalEntry
            from accounting.services import PostingService

            entries = JournalEntry.objects.filter(
                company=job.company,
                source_type="STOCK_MOVEMENT",
                source_id=movement.id,
                purpose="OPENING_STOCK",
                status=JournalEntry.Status.POSTED,
            )
            for entry in entries:
                PostingService.reverse(entry, user=user)
        StockMovement.objects.filter(pk=movement.pk).update(reference_type="import_voided")

    @staticmethod
    def _cleanup_imported_product(job, product, user):
        still_referenced = product.is_referenced()
        if still_referenced:
            product.sku = ""
            product.barcode = ""
            product.status = Product.Status.INACTIVE
            product.updated_by = user
            product.save(update_fields=["sku", "barcode", "status", "updated_by", "updated_at"])
        else:
            product.delete()

    @staticmethod
    def _find_imported_product(job, sku="", name=""):
        product = None
        sku = (sku or "").strip()
        name = (name or "").strip()
        if sku:
            product = Product.objects.filter(company=job.company, sku__iexact=sku).first()
        if product is None and name:
            product = Product.objects.filter(company=job.company, name__iexact=name).first()
        return product

    @staticmethod
    @transaction.atomic
    def void(job: ImportJob, user):
        """
        Reverse a committed PRODUCTS / OPENING_STOCK import when stock layers
        are still intact (nothing sold from the imported opening qty).
        """
        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if job.kind not in (ImportJob.Kind.PRODUCTS, ImportJob.Kind.OPENING_STOCK):
            raise BusinessRuleError("Only product or opening-stock imports can be voided.")
        if job.status != ImportJob.Status.COMMITTED:
            raise BusinessRuleError("Only a committed import can be voided.")

        movements = list(
            StockMovement.objects.select_for_update()
            .filter(
                company=job.company,
                reference_type="import",
                reference_id=str(job.pk),
                movement_type=MovementType.OPENING_STOCK,
            )
            .select_related("product")
        )

        for movement in movements:
            blocked = ImportService._movement_is_unused(movement)
            if blocked:
                raise BusinessRuleError(blocked)
            ImportService._reverse_import_movement(job, movement, user)

        if job.kind == ImportJob.Kind.PRODUCTS:
            preview_rows = job.preview if isinstance(job.preview, list) else []
            for row in preview_rows:
                product = ImportService._find_imported_product(
                    job, sku=row.get("sku", ""), name=row.get("name", "")
                )
                if product is None:
                    continue
                ImportService._cleanup_imported_product(job, product, user)

        job.status = ImportJob.Status.VOIDED
        job.failure_reason = f"Voided by user at {timezone.now().isoformat()}"
        job.voided_rows = [
            {"sku": (m.product.sku or ""), "name": m.product.name}
            for m in movements
        ]
        job.updated_by = user
        job.save(update_fields=["status", "failure_reason", "voided_rows", "updated_by", "updated_at"])
        AuditService.log(
            company=job.company, user=user, action="VOID",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Voided import job #{job.pk} ({job.kind})",
            metadata={"movements_reversed": len(movements)},
        )
        return job

    @staticmethod
    @transaction.atomic
    def void_rows(job: ImportJob, user, *, skus: list[str]):
        """Reverse OPENING_STOCK (and PRODUCTS cleanup) for specific SKUs only."""
        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if job.kind not in (ImportJob.Kind.PRODUCTS, ImportJob.Kind.OPENING_STOCK):
            raise BusinessRuleError("Only product or opening-stock imports can be voided.")
        if job.status != ImportJob.Status.COMMITTED:
            raise BusinessRuleError("Only a committed import can be voided.")
        wanted = [(s or "").strip() for s in skus if (s or "").strip()]
        if not wanted:
            raise BusinessRuleError("Provide a non-empty skus array.")
        movements = list(
            StockMovement.objects.select_for_update()
            .filter(
                company=job.company,
                reference_type="import",
                reference_id=str(job.pk),
                movement_type=MovementType.OPENING_STOCK,
            )
            .select_related("product")
        )
        by_sku = {(m.product.sku or "").casefold(): m for m in movements}

        voided = list(job.voided_rows or [])
        blocked = []
        reversed_count = 0
        for sku in wanted:
            key = sku.casefold()
            movement = by_sku.get(key)
            product = ImportService._find_imported_product(job, sku=sku)
            if movement is None:
                if job.kind == ImportJob.Kind.PRODUCTS and product is not None:
                    ImportService._cleanup_imported_product(job, product, user)
                    voided.append({"sku": sku, "name": product.name})
                    continue
                blocked.append({"sku": sku, "reason": f"No imported opening-stock row found for sku '{sku}'."})
                continue
            if movement is not None:
                reason = ImportService._movement_is_unused(movement)
                if reason:
                    blocked.append({"sku": sku, "reason": reason})
                    continue
                ImportService._reverse_import_movement(job, movement, user)
                reversed_count += 1
            if job.kind == ImportJob.Kind.PRODUCTS and product is not None:
                ImportService._cleanup_imported_product(job, product, user)
            voided.append({"sku": sku, "name": getattr(product or getattr(movement, "product", None), "name", "")})

        job.voided_rows = voided
        remaining = (
            StockMovement.objects.filter(
                company=job.company,
                reference_type="import",
                reference_id=str(job.pk),
                movement_type=MovementType.OPENING_STOCK,
            ).exists()
        )
        # Full VOIDED only when every requested sku succeeded and nothing remains.
        if not remaining and not blocked and job.kind == ImportJob.Kind.OPENING_STOCK:
            job.status = ImportJob.Status.VOIDED
            job.failure_reason = f"Voided by user at {timezone.now().isoformat()}"
        job.updated_by = user
        job.save(update_fields=["status", "failure_reason", "voided_rows", "updated_by", "updated_at"])
        AuditService.log(
            company=job.company, user=user, action="VOID",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Voided {reversed_count} row(s) of import job #{job.pk}",
            metadata={"skus": wanted, "reversed": reversed_count, "blocked": blocked},
        )
        if reversed_count == 0 and blocked:
            raise BusinessRuleError(blocked[0]["reason"])
        return {"voided": [v["sku"] for v in voided], "blocked": blocked, "job": job}


class BillImportService:
    @staticmethod
    def start_extraction(job: ImportJob):
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Only purchase/sales bill jobs can be extracted.")
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
    def parse_structured_file(job: ImportJob):
        """CSV/XLSX bill-import path (§4.1) — deterministic, no LLM, no
        clarification loop (there's no OCR ambiguity to resolve)."""
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Structured bill parsing is only for bill imports.")
        with job.file.file.open("rb") as handle:
            raw = handle.read()
        filename = job.file.original_name or job.file.file.name or ""
        rows = _read_structured_rows(raw, filename)
        if not rows:
            raise BusinessRuleError("The file has no data rows.")

        raw_lines = [_map_structured_row(row) for row in rows]
        preview_lines, errors = BillImportService._build_preview_lines(raw_lines)
        answers = _infer_qty_answers(preview_lines, tolerance=Decimal("0.50")) or {}
        formula_key = _apply_cross_check(preview_lines, answers, tolerance=Decimal("0.50"))
        errors = _refresh_line_validity(preview_lines)
        preview = {
            "supplier_name": "",
            "supplier_gstin": "",
            "buyer_name": "",
            "buyer_gstin": "",
            "bill_number": "",
            "bill_date": "",
            "extraction_confidence": 1.0,
            "low_confidence_accepted": True,
            "column_headers": list(rows[0].keys()) if rows else [],
            "printed_line_count": len(preview_lines),
            "resolved_formula": formula_key,
            "lines": preview_lines,
        }
        included = [ln for ln in preview_lines if ln.get("include")]
        job.preview = preview
        job.errors = errors
        job.total_rows = len(preview_lines)
        job.valid_rows = len(included)
        job.error_rows = len(errors)
        job.clarifications = []
        job.status = ImportJob.Status.PREVIEWED
        job.failure_reason = ""
        job.save()
        return job

    @staticmethod
    def _build_preview_lines(raw_lines: list[dict]) -> tuple[list[dict], list[dict]]:
        preview_lines, errors = [], []
        rate_warnings: list[str] = []
        for index, raw_line in enumerate(raw_lines, start=1):
            line = _preview_bill_line(raw_line, index=index, rate_warnings=rate_warnings)
            if line.get("include"):
                line_errors = _bill_line_errors(line)
                if line_errors:
                    errors.append({"row": index, "errors": line_errors, "data": line})
                    line["include"] = False
            preview_lines.append(line)
        return preview_lines, errors

    @staticmethod
    def apply_extraction(job: ImportJob, payload: dict):
        raw_lines = list(payload.get("lines") or [])
        column_headers = list(payload.get("column_headers") or [])
        gstin = (
            str(payload.get("supplier_gstin") or "").strip()
            if job.kind == ImportJob.Kind.PURCHASE_BILL
            else str(payload.get("buyer_gstin") or "").strip()
        )
        # For a sales bill the "vendor" whose layout we're learning is still
        # the document's issuer (the seller) — that's who prints the columns.
        template_gstin = str(payload.get("supplier_gstin") or "").strip() or gstin
        template = _match_bill_template(job.company, template_gstin, column_headers)

        preview = {
            "supplier_name": str(payload.get("supplier_name") or "").strip(),
            "supplier_gstin": str(payload.get("supplier_gstin") or "").strip(),
            "buyer_name": str(payload.get("buyer_name") or "").strip(),
            "buyer_gstin": str(payload.get("buyer_gstin") or "").strip(),
            "bill_number": str(payload.get("bill_number") or "").strip(),
            "bill_date": str(payload.get("bill_date") or "").strip(),
            "extraction_confidence": _parse_extraction_confidence(payload.get("confidence")),
            "low_confidence_accepted": False,
            "column_headers": column_headers,
            "printed_line_count": payload.get("printed_line_count"),
            "lines": [],
        }
        direction_warning = _infer_direction_warning(job.kind, payload, job.company)
        if direction_warning:
            preview["direction_warning"] = direction_warning

        preview_lines, errors = BillImportService._build_preview_lines(raw_lines)
        tolerance = template.rounding_tolerance if template is not None else Decimal("0.50")

        if template is not None:
            job.bill_template = template
            formula_key = _apply_cross_check(
                preview_lines, _template_answers(template), tolerance=tolerance
            )
            errors = _refresh_line_validity(preview_lines)
            preview["resolved_formula"] = formula_key
            preview["lines"] = preview_lines
            job.status = ImportJob.Status.PREVIEWED
            job.clarifications = []
        else:
            inferred = _infer_qty_answers(preview_lines, tolerance=tolerance)
            if inferred is not None:
                formula_key = _apply_cross_check(preview_lines, inferred, tolerance=tolerance)
                errors = _refresh_line_validity(preview_lines)
                preview["resolved_formula"] = formula_key
                preview["resolved_answers"] = inferred
                preview["qty_formula"] = inferred.get("qty_formula")
                preview["lines"] = preview_lines
                job.clarifications = []
                job.status = ImportJob.Status.PREVIEWED
            else:
                clarifications = _detect_clarifications({
                    "column_headers": column_headers,
                    "lines": preview_lines,
                })
                if clarifications:
                    # Cross-check can't run correctly yet (quantity may still need
                    # recombining) — hold in NEEDS_CLARIFICATION until answered.
                    preview["lines"] = preview_lines
                    job.clarifications = clarifications
                    job.status = ImportJob.Status.NEEDS_CLARIFICATION
                else:
                    formula_key = _apply_cross_check(preview_lines, {}, tolerance=tolerance)
                    errors = _refresh_line_validity(preview_lines)
                    preview["resolved_formula"] = formula_key
                    preview["lines"] = preview_lines
                    job.clarifications = []
                    job.status = ImportJob.Status.PREVIEWED

        included = [ln for ln in preview["lines"] if ln.get("include")]
        job.preview = preview
        job.errors = errors
        job.total_rows = len(preview["lines"])
        job.valid_rows = len(included)
        job.error_rows = len(errors)
        job.failure_reason = ""
        job.save()
        return job

    @staticmethod
    def answer_clarifications(job: ImportJob, answers: dict, user=None):
        """Apply document-level clarification answers (§4.3), recompute
        quantities/cross-check, and move the job from NEEDS_CLARIFICATION to
        PREVIEWED."""
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Clarifications are only for bill imports.")
        if job.status != ImportJob.Status.NEEDS_CLARIFICATION:
            raise BusinessRuleError("This job has no pending clarifications.")
        if not isinstance(answers, dict):
            raise BusinessRuleError("answers must be an object of {field: value}.")

        preview = dict(job.preview or {})
        clarifications = list(job.clarifications or [])
        resolved_answers = {k: v for k, v in answers.items() if v not in (None, "")}
        for item in clarifications:
            field = item.get("field")
            if field in answers:
                item["answer"] = answers[field]
            if item.get("answer"):
                resolved_answers[field] = item["answer"]
        job.clarifications = clarifications

        preview_lines = list(preview.get("lines") or [])
        formula_key = _apply_cross_check(preview_lines, resolved_answers, tolerance=Decimal("0.50"))
        errors = _refresh_line_validity(preview_lines)
        preview["resolved_formula"] = formula_key
        preview["resolved_answers"] = resolved_answers
        preview["lines"] = preview_lines

        job.preview = preview
        job.errors = errors
        job.status = ImportJob.Status.PREVIEWED
        job.valid_rows = len([ln for ln in preview_lines if ln.get("include")])
        job.error_rows = len(errors)
        if user is not None:
            job.updated_by = user
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
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Preview update is only for bill imports.")
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Only previewed bill jobs can be edited.")

        preview = dict(job.preview or {})
        if not isinstance(preview, dict):
            preview = {"lines": []}

        if "supplier_name" in data:
            preview["supplier_name"] = str(data.get("supplier_name") or "").strip()
        if "supplier_gstin" in data:
            preview["supplier_gstin"] = str(data.get("supplier_gstin") or "").strip()
        if "customer_name" in data:
            preview["customer_name"] = str(data.get("customer_name") or "").strip()
        if "bill_number" in data:
            preview["bill_number"] = str(data.get("bill_number") or "").strip()
        if "bill_date" in data:
            preview["bill_date"] = str(data.get("bill_date") or "").strip()
        if "low_confidence_accepted" in data:
            preview["low_confidence_accepted"] = bool(data.get("low_confidence_accepted"))

        if "lines" in data:
            lines_in = data.get("lines") or []
            if not isinstance(lines_in, list):
                raise BusinessRuleError("lines must be an array.")
            lines, errors = [], []
            rate_warnings: list[str] = []
            for index, raw_line in enumerate(lines_in, start=1):
                if not isinstance(raw_line, dict):
                    continue
                line = _preview_bill_line(raw_line, index=index, rate_warnings=rate_warnings)
                # User edits may toggle include even with previously blank fields.
                if "include" in raw_line:
                    line["include"] = bool(raw_line.get("include"))
                line_errors = _bill_line_errors(line) if line.get("include") else []
                if line_errors:
                    errors.append({"row": index, "errors": line_errors, "data": line})
                    line["include"] = False
                lines.append(line)
            preview["lines"] = lines
            if rate_warnings:
                preview["warnings"] = rate_warnings
            else:
                preview.pop("warnings", None)
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

        customer_id = data.get("customer_id", data.get("customer"))
        if customer_id is not None and customer_id != "":
            try:
                customer = Customer.objects.get(pk=customer_id, company=job.company)
            except (Customer.DoesNotExist, ValueError, TypeError):
                raise BusinessRuleError("Invalid customer.")
            job.customer = customer

        if user is not None:
            job.updated_by = user
        job.save()
        return job

    @staticmethod
    def _match_or_create_product(company, line: dict, user, *, direction: str = "PURCHASE") -> tuple[Product, bool]:
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
        # A purchase bill's unit price is a cost; a sales bill's is a selling
        # price — never conflate the two on the product master.
        price_field = "purchase_price" if direction == "PURCHASE" else "selling_price"

        if product is None:
            product = Product.objects.create(
                company=company,
                name=name,
                sku=sku,
                hsn_code=hsn,
                gst_rate=gst_rate,
                purchase_price=unit_price if direction == "PURCHASE" else Decimal("0"),
                selling_price=unit_price if direction == "SALES" else Decimal("0"),
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
            if unit_price > 0 and getattr(product, price_field) != unit_price:
                setattr(product, price_field, unit_price)
                updates.append(price_field)
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
    def _resolve_customer(job: ImportJob, user) -> Customer:
        if job.customer_id:
            return job.customer
        preview = job.preview if isinstance(job.preview, dict) else {}
        gstin = str(preview.get("buyer_gstin") or "").strip()
        name = (
            str(preview.get("customer_name") or "").strip()
            or str(preview.get("buyer_name") or "").strip()
        )
        customer = None
        if gstin:
            customer = Customer.objects.filter(company=job.company, gstin__iexact=gstin).first()
        if customer is None and name:
            customer = Customer.objects.filter(company=job.company, name__iexact=name).first()
        if customer is None:
            if not name:
                raise BusinessRuleError("Select a customer before committing the sales bill.")
            customer = Customer.objects.create(
                company=job.company,
                name=name,
                gstin=gstin if gstin and GSTIN_RE.match(gstin) else "",
                created_by=user,
                updated_by=user,
            )
        job.customer = customer
        job.save(update_fields=["customer", "updated_at"])
        return customer

    @staticmethod
    def _save_bill_template(job: ImportJob, preview: dict, user):
        """Persist the confirmed column mapping / formula as this vendor's
        SupplierBillTemplate (§4.4) — learned once, applied silently on every
        later bill from the same GSTIN."""
        gstin = str(preview.get("supplier_gstin") or "").strip()
        if not gstin or not GSTIN_RE.match(gstin):
            return
        formula_key = preview.get("resolved_formula") or SupplierBillTemplate.LineTotalFormula.SIMPLE
        column_headers = preview.get("column_headers") or []
        mapping = dict(preview.get("column_mapping") or {})
        answers = preview.get("resolved_answers") if isinstance(preview.get("resolved_answers"), dict) else {}
        qty_formula = answers.get("qty_formula") or mapping.get("qty_formula")
        if qty_formula:
            mapping["qty_formula"] = qty_formula
        SupplierBillTemplate.objects.update_or_create(
            company=job.company,
            gstin=gstin,
            defaults={
                "party_name": str(preview.get("supplier_name") or "")[:255],
                "line_total_formula": formula_key,
                "column_mapping": mapping,
                "column_signature": column_headers,
                "confirmed_by": user,
                "confirmed_at": timezone.now(),
                "updated_by": user,
            },
        )

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
        for fmt in (
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d.%m.%Y",
            "%Y/%m/%d",
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d %b %Y",
            "%d %B %Y",
        ):
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
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Not a bill import.")
        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Import must be previewed before commit.")

        preview = job.preview if isinstance(job.preview, dict) else {}
        confidence = _parse_extraction_confidence(preview.get("extraction_confidence", 1))
        if confidence < OCR_BILL_MIN_CONFIDENCE and not preview.get("low_confidence_accepted"):
            raise BusinessRuleError(
                f"OCR confidence ({confidence:.2f}) is below {OCR_BILL_MIN_CONFIDENCE:.2f}. "
                "Review extracted fields and set low_confidence_accepted on preview before commit."
            )

        lines = [ln for ln in (preview.get("lines") or []) if ln.get("include")]
        if not lines:
            raise BusinessRuleError("Select at least one valid line to commit.")

        if job.kind == ImportJob.Kind.SALES_BILL:
            result = BillImportService._commit_sales(job, preview, lines, user)
        else:
            result = BillImportService._commit_purchase(job, preview, lines, user)

        # Learn this vendor's layout for next time (§4.4) — only once we have
        # a resolved formula (i.e. any clarification was actually answered,
        # or the bill needed no clarification and the SIMPLE formula applied).
        if job.bill_template_id is None:
            BillImportService._save_bill_template(job, preview, user)

        job.status = ImportJob.Status.COMMITTED
        job.committed_at = timezone.now()
        job.updated_by = user
        job.save()
        return result

    @staticmethod
    def _commit_purchase(job: ImportJob, preview: dict, lines: list[dict], user) -> dict:
        supplier = BillImportService._resolve_supplier(job, user)
        items_data = []
        products_created = 0
        for line in lines:
            product, created = BillImportService._match_or_create_product(
                job.company, line, user, direction="PURCHASE"
            )
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
            company_gstin=_resolve_import_company_gstin(job.company, preview, kind=ImportJob.Kind.PURCHASE_BILL),
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

    @staticmethod
    def _commit_sales(job: ImportJob, preview: dict, lines: list[dict], user) -> dict:
        customer = BillImportService._resolve_customer(job, user)
        items_data = []
        products_created = 0
        for line in lines:
            product, created = BillImportService._match_or_create_product(
                job.company, line, user, direction="SALES"
            )
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

        invoice = SalesInvoice.objects.create(
            company=job.company,
            customer=customer,
            company_gstin=_resolve_import_company_gstin(job.company, preview, kind=ImportJob.Kind.SALES_BILL),
            invoice_type=SalesInvoice.InvoiceType.GST,
            invoice_date=BillImportService._parse_bill_date(
                str(preview.get("bill_date") or ""),
                required=bool(str(preview.get("bill_date") or "").strip()),
            ),
            notes=f"Created from sales bill upload (bill #{str(preview.get('bill_number') or '')[:64]})",
            created_by=user,
            updated_by=user,
        )
        SalesService.set_items(invoice, items_data, user)

        job.sales_invoice = invoice
        AuditService.log(
            company=job.company, user=user, action="IMPORT",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Imported sales bill → draft sales invoice #{invoice.pk}",
            metadata={
                "products_created": products_created,
                "lines": len(items_data),
                "sales_invoice_id": invoice.pk,
            },
        )
        return {
            "created": len(items_data),
            "products_created": products_created,
            "sales_invoice_id": invoice.pk,
        }

"""Import Service — CSV pipeline + purchase-bill LLM extraction."""

import csv
import hashlib
import io
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.models import CompanyGstin
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.services.audit import AuditService
from core.services.files import CSV_UTF8_HINT
from core.services.uqc import normalize_uqc
from core.validators import ALLOWED_GST_RATES, GSTIN_RE, HSN_RE, validate_gst_rate
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from masters import gstin_rules
from masters.services import create_customer
from masters.models import Brand, Category, Customer, Product, Supplier, Unit
from purchases.models import PurchaseInvoice
from purchases.services import PurchaseService
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import ImportJob, SupplierBillTemplate
from .qty_formula import (
    apply_qty_formula,
    collect_extras,
    count_pool,
    detect_qty_clarifications,
    infer_qty_formula,
)

OCR_BILL_MIN_CONFIDENCE = float(getattr(settings, "OCR_BILL_MIN_CONFIDENCE", 0.7) or 0.7)
BILL_TEMPLATE_SIGNATURE_MATCH_THRESHOLD = 0.7
MAX_IMPORT_ROWS = 20_000
MAX_IMPORT_CELLS = 500_000

REQUIRED_COLUMNS = {
    ImportJob.Kind.CUSTOMERS: ["name"],
    ImportJob.Kind.SUPPLIERS: ["name"],
    ImportJob.Kind.PRODUCTS: ["name"],
    ImportJob.Kind.OPENING_STOCK: ["sku", "quantity"],
}

# Fuzzy header aliases for master CSV/XLSX imports (Tally / POS / Excel exports).
MASTER_COLUMN_ALIASES = {
    "name": ["name", "product name", "item", "item name", "item name*", "item description", "product"],
    "sku": ["sku", "item code", "product code", "pcode", "code", "itemcode"],
    "barcode": ["barcode", "ean", "bar code"],
    "hsn_code": ["hsn_code", "hsn", "hsn code", "hsn/sac", "hsn_sac"],
    "description": ["description", "item desc", "product description"],
    "gst_rate": ["gst_rate", "gst", "gst%", "tax_rate", "tax%", "gst rate", "gst tax rate(%)", "gst tax rate"],
    "purchase_price": ["purchase_price", "purchase price", "cost", "buy price", "purchase rate", "rate"],
    "selling_price": ["selling_price", "selling price", "sale price", "sell price", "sales price"],
    "mrp": ["mrp"],
    "wholesale_price": ["wholesale_price", "wholesale price", "wholesale rate", "wholesale"],
    "default_discount_percent": ["default_discount_percent", "discount", "discount %", "default discount"],
    "reorder_level": ["reorder_level", "reorder level", "reorder", "min stock", "low stock alert quantity"],
    "quantity": ["quantity", "qty", "pcs", "pieces", "stock", "stock qty"],
    "unit_cost": ["unit_cost", "unit cost", "cost price", "opening cost"],
    "opening_stock": ["opening_stock", "opening stock", "opening qty", "opening quantity", "current stock"],
    "unit": ["unit", "unit_name", "uom", "uqc"],
    "alternate_unit": ["alternate_unit", "alternate unit", "alt unit", "alt_uom"],
    "conversion_rate": ["conversion_rate", "conversion rate", "conversion"],
    "product_type": ["product_type", "item type", "item_type", "type"],
    "track_inventory": ["track_inventory", "track inventory", "track stock"],
    "track_batch": ["track_batch", "track batch", "batch tracking"],
    "track_serial": ["track_serial", "track serial", "serial tracking"],
    "tracking": ["tracking", "tracking mode", "tracking_mode"],
    "selling_tax_inclusive": ["selling_tax_inclusive", "sales tax inclusive", "sales tax inclusive?"],
    "purchase_tax_inclusive": ["purchase_tax_inclusive", "purchase tax inclusive"],
    "category": ["category"],
    "godown": ["godown", "warehouse", "godown name", "warehouse name"],
    "batch_no": ["batch_no", "batch no", "batch", "lot", "lot no"],
    "expiry_date": ["expiry_date", "expiry date", "expiry", "exp date"],
    "manufacturing_date": ["manufacturing_date", "manufacturing date", "mfg", "mfg date"],
    "as_of": ["as_of", "as of", "as of date", "opening date"],
    "serial_no": ["serial_no", "serial", "serial number", "serial numbers"],
    "phone": ["phone", "mobile", "contact", "phone number"],
    "email": ["email", "e-mail"],
    "gstin": ["gstin", "gst no", "gstin number"],
    "state": ["state"],
    "address": ["address", "billing_address", "billing address"],
}

# Canonical PRODUCTS template — same headers for CSV and the xlsx `items` sheet.
PRODUCTS_ITEM_COLUMNS = [
    "name", "sku", "barcode", "hsn_code", "description", "category", "unit",
    "alternate_unit", "conversion_rate", "gst_rate", "purchase_price",
    "purchase_tax_inclusive", "selling_price", "selling_tax_inclusive", "mrp",
    "wholesale_price", "default_discount_percent", "reorder_level", "product_type",
    "track_inventory", "track_batch", "track_serial", "godown", "opening_stock",
    "unit_cost", "batch_no", "expiry_date", "manufacturing_date", "as_of", "serial_no",
]
PRODUCTS_ITEM_SAMPLE_ROWS = [
    [""] * len(PRODUCTS_ITEM_COLUMNS),
]
OPENING_LOTS_COLUMNS = [
    "sku", "godown", "quantity", "as_of", "batch_no", "expiry_date", "manufacturing_date", "unit_cost",
]
OPENING_SERIALS_COLUMNS = ["sku", "godown", "serial_no", "as_of", "unit_cost"]


def products_item_columns(company=None) -> list[str]:
    from masters.custom_fields import active_defs

    columns = list(PRODUCTS_ITEM_COLUMNS)
    if company is None:
        return columns
    seen = {col.casefold() for col in columns}
    for row in active_defs(company):
        label = (row.get("label") or row.get("key") or "").strip()
        if label and label.casefold() not in seen:
            columns.append(label)
            seen.add(label.casefold())
    return columns


def products_template_csv(company=None) -> str:
    columns = products_item_columns(company)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerow([""] * len(columns))
    return buf.getvalue()


def _optional_bool(value, default=None):
    raw = str(value or "").strip().casefold()
    if not raw:
        return default
    if raw in {"yes", "true", "1", "y", "on"}:
        return True
    if raw in {"no", "false", "0", "n", "off"}:
        return False
    return default


def _is_service_type(row) -> bool:
    return str(row.get("product_type") or row.get("item_type") or "").strip().casefold() in {
        "service",
        "services",
    }


def _tracking_from_row(row) -> tuple[bool, bool]:
    tracking = str(row.get("tracking") or row.get("tracking_mode") or "").strip().casefold()
    track_batch = _optional_bool(row.get("track_batch"), default=None)
    track_serial = _optional_bool(row.get("track_serial"), default=None)
    if track_batch is None:
        track_batch = tracking in {"batch", "expiry", "batch / expiry", "batch/expiry"} or bool(
            str(row.get("batch_no") or "").strip()
        )
    if track_serial is None:
        track_serial = tracking in {"serial"} or bool(str(row.get("serial_no") or "").strip())
    return bool(track_batch), bool(track_serial)


def _custom_field_row_errors(row, header_map, defs) -> list[str]:
    from masters.custom_fields import values_from_row

    errors = []
    values = values_from_row(row, header_map)
    by_key = {d["key"]: d for d in defs if d.get("active")}
    for key, text in values.items():
        spec = by_key.get(key)
        if not spec or spec.get("type") != "list":
            continue
        options = spec.get("options") or []
        if not any(str(opt).casefold() == text.casefold() for opt in options):
            errors.append(f"'{text}' is not a valid option for '{spec.get('label') or key}'.")
    return errors


def _format_validation_detail(detail) -> str:
    if isinstance(detail, dict):
        for value in detail.values():
            return _format_validation_detail(value)
        return "Invalid custom field values."
    if isinstance(detail, (list, tuple)):
        for value in detail:
            text = _format_validation_detail(value)
            if text:
                return text
        return "Invalid custom field values."
    return str(detail)


def _custom_fields_for_commit(job, row, existing=None, *, live_keys: set | None = None) -> dict:
    from rest_framework.exceptions import ValidationError as DRFValidationError

    from masters.custom_fields import coerce_values, values_from_row

    header_map = job.custom_field_header_map or {}
    snapshot = job.custom_field_defs_snapshot or []
    if not header_map:
        return dict(existing or {})
    if live_keys is None:
        # B3-012: caller didn't precompute this (a one-off call site) -- fall
        # back to a fresh read here, same as before.
        job.company.refresh_from_db(fields=["item_custom_field_defs"])
        live_keys = {
            str(spec.get("key") or "").casefold()
            for spec in (job.company.item_custom_field_defs or [])
            if isinstance(spec, dict) and spec.get("key")
        }
    for dest in header_map.values():
        if str(dest).casefold() not in live_keys:
            raise BusinessRuleError(f"Custom field '{dest}' no longer exists.")
    values = values_from_row(row, header_map)
    try:
        return coerce_values(values, snapshot, existing, replace_active=False)
    except DRFValidationError as exc:
        raise BusinessRuleError(_format_validation_detail(exc.detail)) from exc


def _parse_serial_numbers(value) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


def _extra_serial_counts(extra_sheets) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw in (extra_sheets or {}).get("opening_serials") or []:
        row = {str(k).strip().lower(): v for k, v in (raw or {}).items()}
        sku = str(row.get("sku") or row.get("item code") or "").strip().casefold()
        serial = str(row.get("serial_no") or row.get("serial") or "").strip()
        if sku and serial:
            counts[sku] = counts.get(sku, 0) + 1
    return counts


def _lots_from_item_rows(preview: list[dict]) -> list[dict]:
    lots = []
    for row in preview:
        _track_batch, track_serial = _tracking_from_row(row)
        if track_serial or str(row.get("serial_no") or "").strip():
            continue
        lot_used = any(
            str(row.get(key) or "").strip()
            for key in ("godown", "batch_no", "expiry_date", "manufacturing_date", "as_of")
        )
        qty = str(row.get("opening_stock") or row.get("quantity") or "").strip()
        if not lot_used or not qty:
            continue
        lots.append(
            {
                "sku": row.get("sku") or "",
                "godown": row.get("godown") or "",
                "quantity": qty,
                "as_of": row.get("as_of") or "",
                "batch_no": row.get("batch_no") or "",
                "expiry_date": row.get("expiry_date") or "",
                "manufacturing_date": row.get("manufacturing_date") or "",
                "unit_cost": row.get("unit_cost") or "",
            }
        )
    return lots


def _serials_from_item_rows(preview: list[dict]) -> list[dict]:
    serials = []
    for row in preview:
        numbers = _parse_serial_numbers(row.get("serial_no"))
        if not numbers:
            continue
        for serial in numbers:
            serials.append(
                {
                    "sku": row.get("sku") or "",
                    "godown": row.get("godown") or "",
                    "serial_no": serial,
                    "as_of": row.get("as_of") or "",
                    "unit_cost": row.get("unit_cost") or "",
                }
            )
    return serials

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


def _released_barcodes(rows, products_by_sku) -> set[str]:
    """Barcodes existing products are giving up because the file assigns a different one."""
    released = set()
    for raw_row in rows:
        row = _map_master_row(raw_row)
        sku = (row.get("sku") or "").strip()
        barcode = (row.get("barcode") or "").strip()
        if not sku or not barcode:
            continue
        product = products_by_sku.get(sku.casefold())
        if product is None:
            continue
        old = (product.barcode or "").strip().casefold()
        new = barcode.casefold()
        if old and old != new:
            released.add(old)
    return released


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
    extra_serial_counts=None,
    warehouse_index=None,
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
        for field in (
            "gst_rate", "purchase_price", "selling_price", "mrp", "wholesale_price",
            "default_discount_percent", "conversion_rate", "reorder_level",
            "opening_stock", "quantity", "unit_cost",
        ):
            value = (row.get(field) or "").strip()
            if value:
                try:
                    num = Decimal(value)
                    if not num.is_finite():
                        # B3-014: Infinity parses and passes every >= 0 check.
                        errors.append(f"{field} must be a finite number")
                    elif field in (
                        "purchase_price", "selling_price", "mrp", "wholesale_price",
                        "default_discount_percent", "reorder_level", "unit_cost",
                    ) and num < 0:
                        errors.append(f"{field} must be >= 0")
                    elif field == "conversion_rate" and num <= 0:
                        errors.append("conversion_rate must be > 0")
                    elif field in ("opening_stock", "quantity") and num < 0:
                        # 0 means catalog-only (no opening lot), same as a blank cell.
                        errors.append(f"{field} must be >= 0")
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
        item_type = (row.get("product_type") or row.get("item_type") or "").strip().casefold()
        opening_raw = (row.get("opening_stock") or row.get("quantity") or "").strip()
        if item_type in {"service", "services"} and opening_raw:
            try:
                if Decimal(opening_raw) > 0:
                    errors.append("service items cannot have opening stock")
            except InvalidOperation:
                pass
        track_batch, track_serial = _tracking_from_row(row)
        if track_batch and track_serial:
            errors.append("batch and serial tracking cannot both be on")
        serials = _parse_serial_numbers(row.get("serial_no"))
        extra_serial_count = 0
        if sku:
            extra_serial_count = int((extra_serial_counts or {}).get(sku.casefold(), 0))
        opening_qty = None
        if opening_raw:
            try:
                opening_qty = Decimal(opening_raw)
            except InvalidOperation:
                opening_qty = None
        if extra_serial_count == 0:
            if track_serial and opening_qty is not None and opening_qty > 0:
                if not serials:
                    errors.append("Serial numbers are required for serial-tracked opening stock.")
                elif Decimal(len(serials)) != opening_qty:
                    errors.append("Opening quantity must equal the number of serials.")
            elif serials and not track_serial:
                errors.append("Serial numbers are only allowed when serial tracking is on.")
        if serials and len(serials) != len({value.casefold() for value in serials}):
            errors.append("Duplicate serial numbers supplied")
        batch_no = (row.get("batch_no") or "").strip()
        expiry = (row.get("expiry_date") or "").strip()
        if (track_batch or batch_no or expiry) and opening_raw:
            try:
                if Decimal(opening_raw) > 0 and (not batch_no or not expiry):
                    errors.append("Batch tracking is on but this row has no Batch no or Expiry.")
            except InvalidOperation:
                pass
        godown = (row.get("godown") or "").strip()
        if item_type in {"service", "services"} and (godown or batch_no or expiry or track_batch or track_serial):
            errors.append("service items cannot have godown, batch, or serial tracking")
        elif godown:
            # B3-023: `warehouse_index` (built once per file, not per row) is
            # preferred when the caller supplies it — avoids a `match_warehouse`
            # DB round-trip (which itself issues two queries) for every row of
            # a godown-heavy file.
            if warehouse_index is not None:
                by_key, active_names = warehouse_index
                match = by_key.get(godown.casefold())
                if match is None:
                    errors.append(f"Godown '{godown}' not found. Available: {active_names}.")
                elif not match.is_active:
                    errors.append(f"Godown '{match.name}' is inactive. Available: {active_names}.")
            else:
                from inventory.item_stock import match_warehouse

                try:
                    match_warehouse(company, godown)
                except BusinessRuleError as exc:
                    errors.append(str(getattr(exc, "detail", None) or exc))
        if sku:
            key = sku.casefold()
            if seen_skus is not None and key in seen_skus:
                errors.append(f"duplicate sku '{sku}' in file")
            elif (existing_skus is not None and key in existing_skus) or (
                existing_skus is None and Product.objects.filter(company=company, sku__iexact=sku).exists()
            ):
                if seen_skus is not None:
                    seen_skus.add(key)
                product = products_by_sku.get(key) if products_by_sku is not None else Product.objects.filter(
                    company=company, sku__iexact=sku
                ).first()
                if opening_raw:
                    try:
                        if Decimal(opening_raw) > 0:
                            already = False
                            if product is not None:
                                if skus_with_opening is not None:
                                    already = product.pk in skus_with_opening
                                else:
                                    from inventory.services import InventoryService as _Inv

                                    already = product.pk in _Inv.active_opening_product_ids(company)
                                if already:
                                    errors.append(f"opening stock already recorded for '{product.name}'")
                    except InvalidOperation:
                        pass
                # BB-000???: bulk_update() in _commit_products writes `unit`
                # straight onto the ORM object, bypassing ProductSerializer's
                # validate() entirely -- without this check here, a re-import
                # matched by SKU could silently change an existing item's
                # base unit even with stock on hand or open documents still
                # keyed to the old one (the one guard the API/UI path enforces).
                unit_str = (row.get("unit") or row.get("unit_name") or "").strip()
                if product is not None and unit_str:
                    current_short = (product.unit.short_name if product.unit_id else "").strip()
                    if current_short and current_short.casefold() != unit_str.casefold():
                        from inventory.item_stock import assert_unit_change_allowed

                        try:
                            assert_unit_change_allowed(product)
                        except BusinessRuleError as exc:
                            errors.append(
                                f"unit: cannot change base unit for '{product.name}' — "
                                f"{str(getattr(exc, 'detail', None) or exc)}"
                            )
            elif seen_skus is not None:
                seen_skus.add(key)
        if barcode:
            key = barcode.casefold()
            sku_key = sku.casefold() if sku else ""
            owner = products_by_sku.get(sku_key) if products_by_sku is not None and sku_key else None
            own_barcode = owner is not None and (owner.barcode or "").casefold() == key
            if seen_barcodes is not None and key in seen_barcodes:
                errors.append(f"duplicate barcode '{barcode}' in file")
            elif own_barcode:
                if seen_barcodes is not None:
                    seen_barcodes.add(key)
            elif existing_barcodes is not None and key in existing_barcodes:
                errors.append(f"barcode '{barcode}' already exists")
            elif existing_barcodes is None and Product.objects.filter(company=company, barcode__iexact=barcode).exclude(
                sku__iexact=sku or ""
            ).exists():
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
                    from inventory.services import InventoryService as _Inv

                    already_has_opening = product.pk in _Inv.active_opening_product_ids(company)
                if already_has_opening:
                    errors.append(f"opening stock already recorded for '{product.name}'")
                serials = _parse_serial_numbers(row.get("serial_no"))
                if product.track_serial:
                    if not serials:
                        errors.append("Serial numbers are required for serial-tracked opening stock.")
                    elif len(serials) != len({value.casefold() for value in serials}):
                        errors.append("Duplicate serial numbers supplied")
                elif serials:
                    errors.append("Serial numbers are only allowed when serial tracking is on.")
        qty_raw = (row.get("quantity") or "").strip()
        if not qty_raw:
            errors.append("quantity is required")
        else:
            try:
                qty = Decimal(qty_raw)
                if not qty.is_finite():
                    errors.append("quantity must be a finite number")
                elif qty <= 0:
                    errors.append("quantity must be > 0")
                else:
                    serials = _parse_serial_numbers(row.get("serial_no"))
                    if serials and Decimal(len(serials)) != qty:
                        errors.append("Opening quantity must equal the number of serials.")
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
    # B3-015: strip Indian-style thousands separators ("1,250" / "1,25,000")
    # so a formatted qty/rate cell doesn't fail to parse and silently drop the
    # whole line — collect_extras() already does this for extra/pack columns,
    # this is the same normalisation for the canonical quantity/unit_price path.
    raw = str(value if value not in (None, "") else default).strip()
    if "," in raw and raw.count(",") != 0:
        stripped = raw.replace(",", "")
        try:
            Decimal(stripped)
        except (InvalidOperation, AttributeError):
            pass
        else:
            raw = stripped
    try:
        result = Decimal(raw)
    except (InvalidOperation, AttributeError):
        raise BusinessRuleError(f"Invalid number: {value!r}")
    # B3-014: Decimal("Infinity") / Decimal("NaN") construct fine and slip past
    # the >= 0 guards; reject them before they reach bulk_create / post_opening.
    if not result.is_finite():
        raise BusinessRuleError(f"Invalid number: {value!r}")
    return result


def _parse_extraction_confidence(value) -> float:
    try:
        confidence = float(str(value if value not in (None, "") else "1").strip())
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, confidence))


def _normalize_gst_rate(
    value, *, warnings: list | None = None, row: int | None = None, required: bool = False,
) -> Decimal:
    """Snap OCR GST rates to an allowed slab; optionally record a warning (PUR-09)."""
    if required and value in (None, ""):
        prefix = f"Row {row}: " if row is not None else ""
        raise BusinessRuleError(f"{prefix}GST rate is required and cannot be invented.")
    # B3-001: supplier exports very commonly write the GST cell as "18%",
    # "18 %", "18.00%". Strip a trailing percent sign / whitespace before
    # parsing so a formatting quirk doesn't abort the whole upload.
    if isinstance(value, str):
        value = value.strip().rstrip("%").strip()
    rate = _as_decimal(value, "18")
    if rate not in ALLOWED_GST:
        # Snap common OCR noise to nearest allowed rate, else 18.
        nearest = min(ALLOWED_GST, key=lambda allowed: abs(allowed - rate))
        if abs(nearest - rate) <= Decimal("0.5"):
            snapped = nearest
            if warnings is not None:
                prefix = f"Row {row}: " if row is not None else ""
                warnings.append(f"{prefix}GST rate {rate} snapped to nearest allowed rate {snapped}")
            return snapped
        prefix = f"Row {row}: " if row is not None else ""
        raise BusinessRuleError(
            f"{prefix}GST rate {rate} is not an allowed slab. Enter 0, 5, 12, 18, or 28."
        )
    return rate


def _preview_bill_line(raw_line: dict, *, index: int, rate_warnings: list[str]) -> dict:
    """Build a preview line without inventing qty=1 or GST=18 for unread OCR fields."""
    line_warnings: list[str] = []
    qty = _line_get(raw_line, "quantity")
    gst_raw = _line_get(raw_line, "gst_rate", "gstRate")
    gst_unparseable = False
    if gst_raw:
        try:
            gst_rate = str(_normalize_gst_rate(gst_raw, warnings=line_warnings, row=index))
        except (BusinessRuleError, InvalidOperation):
            # B3-001: one bad GST cell must not abort the whole job — exclude
            # just this line, like every other unreadable field.
            gst_rate = ""
            gst_unparseable = True
            line_warnings.append(
                f"Row {index}: GST rate {gst_raw!r} is not a number — line excluded."
            )
    else:
        gst_rate = ""
    # Prefer explicit include from LLM normalize; otherwise require readable qty+GST.
    if "include" in raw_line and not gst_unparseable:
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
        "si": _line_get(raw_line, "si", "sl", "s_no", "sno") or str(index),
        # 24.5: only backfill the loose-piece count when the bill actually has
        # pack columns; otherwise `pcs` is not a pack concept at all.
        "pcs": _line_get(raw_line, "pcs") or (qty if (extras.get("cs") or extras.get("upc") or _line_get(raw_line, "cs") or _line_get(raw_line, "upc")) else ""),
        "discount_percent": _line_get(raw_line, "discount_percent", "discountPercent", "disc"),
        "errors": [],
    }
    bbox = raw_line.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        try:
            line["bbox"] = [round(max(0.0, min(1.0, float(x))), 4) for x in bbox]
        except (TypeError, ValueError):
            pass
    # Stable, server-owned identity (never the printed S.No). Preserved across
    # edits; assigned for new lines by _finalize_preview_lines.
    if raw_line.get("line_id") not in (None, ""):
        try:
            line["line_id"] = int(raw_line["line_id"])
        except (TypeError, ValueError):
            pass
    if line_warnings:
        line["warnings"] = line_warnings
        rate_warnings.extend(line_warnings)
    return line


def _bill_line_errors(line: dict) -> list[str]:
    """Extraction-time line problems (messages only).

    GST presence is excluded here on purpose: extraction already leaves a line
    unchecked when its rate is unreadable. Commit uses the full structured
    validator in `imports.bill_validation`.
    """
    from imports.bill_validation import line_errors

    return [e["message"] for e in line_errors(line) if e["code"] not in ("GST_REQUIRED", "GST_SLAB", "GST_NUMBER")]


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


def _apply_cross_check(
    lines: list[dict],
    answers: dict,
    *,
    tolerance: Decimal,
    reconcile_print: bool = True,
) -> str:
    return apply_qty_formula(
        lines, answers, tolerance=tolerance, reconcile_print=reconcile_print
    )


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
            line["excluded_reason"] = "; ".join(line_errors)
            errors.append({"row": index, "errors": line_errors, "data": line})
            continue
        line.pop("excluded_reason", None)
        gst_ok = bool(str(line.get("gst_rate") or "").strip())
        try:
            qty_ok = _as_decimal(line.get("quantity"), "0") > 0
        except BusinessRuleError:
            qty_ok = False
        if qty_ok and gst_ok:
            line["include"] = True
    return errors


def _signature_hash(headers) -> str:
    """Order-independent fingerprint of a bill's column headers (23.6)."""
    norm = sorted({str(h).strip().upper() for h in (headers or []) if str(h or "").strip()})
    return hashlib.sha256("|".join(norm).encode("utf-8")).hexdigest()[:40] if norm else ""


def _match_bill_template(
    company, gstin: str, column_headers: list[str], kind: str = ImportJob.Kind.PURCHASE_BILL,
) -> SupplierBillTemplate | None:
    """GSTIN + direction are the key; column signature (order-independent)
    guards against applying a stale template after the vendor changes layout,
    and lets two billing formats under one GSTIN keep separate templates."""
    if not gstin:
        return None
    qs = SupplierBillTemplate.objects.filter(
        company=company, kind=kind, gstin__iexact=gstin
    ).order_by("-confirmed_at", "-id")
    sig = _signature_hash(column_headers)
    if sig:
        exact = qs.filter(signature_hash=sig).first()
        if exact is not None:
            return exact
    seen = {str(h).strip().upper() for h in (column_headers or [])}
    for template in qs:
        stored = {str(h).strip().upper() for h in (template.column_signature or [])}
        if not stored or not seen:
            return template
        overlap = len(stored & seen) / max(len(stored), 1)
        if overlap >= BILL_TEMPLATE_SIGNATURE_MATCH_THRESHOLD:
            return template
    return None


def _template_answers(template: SupplierBillTemplate) -> dict:
    mapping = template.column_mapping if isinstance(template.column_mapping, dict) else {}
    if mapping.get("qty_formula"):
        return {"qty_formula": mapping["qty_formula"]}
    if template.line_total_formula == SupplierBillTemplate.LineTotalFormula.CASE_UNITS_PLUS_LOOSE:
        return {"qty_formula": "cs*upc+quantity"}
    return {"qty_formula": "quantity"}


def _lines_have_pack_columns(lines: list[dict]) -> bool:
    for line in lines:
        keys = set(count_pool(line))
        keys.discard("quantity")
        if keys:
            return True
    return False


def _skip_simple_qty_template(template: SupplierBillTemplate | None, lines: list[dict]) -> bool:
    """A saved SIMPLE layout is from a prior extract that never saw Cs/UPC.

    If this bill actually has pack-size columns, ignore SIMPLE so inference
    can recombine billed qty instead of treating Pcs as the full quantity.
    """
    if template is None:
        return False
    if _template_answers(template).get("qty_formula") != "quantity":
        return False
    return _lines_have_pack_columns(lines)


def _within_one_edit(a: str, b: str) -> bool:
    """True when a and b differ by at most one substitution, insertion or deletion."""
    if a == b or abs(len(a) - len(b)) > 1:
        return a == b
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def company_gstin_status(company, preview: dict, *, kind: str) -> dict:
    """Which of the company's GSTINs issued/received this bill (23.12).

    status: ok (recognised or user-chosen) | defaulted_single (one GSTIN, or the
    bill carried none) | unresolved (several GSTINs and the bill's is missing or
    not recognised). `unresolved` only blocks when BILL_IMPORT_REVIEW_V2 is on.
    """
    from core.services.feature_flags import flag_enabled

    qs = CompanyGstin.objects.filter(company=company, is_active=True)
    options = [
        {"id": g.pk, "gstin": g.gstin, "state": getattr(g, "state", "") or "", "is_primary": bool(g.is_primary)}
        for g in qs.order_by("-is_primary", "id")
    ]
    chosen = preview.get("company_gstin_id")
    if chosen not in (None, ""):
        hit = qs.filter(pk=chosen).first()
        if hit is not None:
            return {"status": "ok", "obj": hit, "options": options}
    known = {(g["gstin"] or "").upper() for g in options}
    if getattr(company, "gstin", ""):
        known.add(company.gstin.upper())
    if kind == ImportJob.Kind.SALES_BILL:
        wanted = str(preview.get("company_gstin") or preview.get("supplier_gstin") or "").strip().upper()
    else:
        wanted = str(preview.get("company_gstin") or preview.get("buyer_gstin") or "").strip().upper()
    if wanted and wanted in known:
        hit = qs.filter(gstin__iexact=wanted).first()
        if hit is not None:
            return {"status": "ok", "obj": hit, "options": options}
    default = qs.filter(is_primary=True).order_by("-id").first() or qs.order_by("id").first()
    suggestion = None
    if wanted:
        # An OCR slip of one character: offer our own GSTIN, never apply it silently.
        for option in options:
            if _within_one_edit(wanted, (option["gstin"] or "").upper()):
                suggestion = {"id": option["id"], "gstin": option["gstin"]}
                break
    if len(options) > 1 and flag_enabled(company, "BILL_IMPORT_REVIEW_V2"):
        return {"status": "unresolved", "obj": None, "options": options, "default": default, "suggestion": suggestion}
    return {"status": "defaulted_single", "obj": default, "options": options, "suggestion": suggestion}


def _resolve_import_company_gstin(company, preview: dict, *, kind: str):
    """Stamp filing identity from the bill's own GSTIN, else the primary CompanyGstin."""
    status = company_gstin_status(company, preview, kind=kind)
    if status["status"] == "unresolved":
        raise BusinessRuleError(
            "Choose which of your GSTINs issued this bill before creating the draft.",
            code="COMPANY_GSTIN_UNRESOLVED",
        )
    return status["obj"]


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
    "si": ["si", "sl", "s.no", "s no", "sno", "sr no"],
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
    # Explicit percentage headers only: a bare "discount" column is usually an amount.
    "discount_percent": [
        "discount_percent", "disc %", "disc%", "discount %", "discount%", "td %", "td%",
        "trade disc %", "trade discount %", "disc percent",
    ],
}

_INVOICE_META_ALIASES = {
    "supplier_name": ("registered name", "supplier name", "seller name", "vendor name"),
    "supplier_gstin": ("gstin", "supplier gstin", "vendor gstin"),
    "buyer_name": ("customer name", "buyer name", "bill to"),
    "buyer_gstin": ("customer gstin", "buyer gstin"),
    "bill_number": ("invoice no", "invoice number", "bill no", "bill number"),
    "bill_date": ("invoice date", "bill date"),
    "freight": ("freight", "freight charges", "packing", "packing charges", "other charges"),
    "invoice_discount": ("bill discount", "invoice discount", "cash discount"),
}


def _xlsx_kv_meta(rows: list) -> dict:
    meta: dict[str, str] = {}
    for row in rows:
        if not row or row[0] in (None, ""):
            continue
        label = str(row[0]).strip().lower().rstrip(".:")
        value = row[1] if len(row) > 1 and row[1] not in (None, "") else ""
        if not value:
            continue
        # B3-011: a genuine Excel date cell must become an ISO date string, not
        # "2026-03-15 00:00:00", so the bill date can be committed without a
        # manual edit.
        text = _cell_to_import_text(value)
        for field, aliases in _INVOICE_META_ALIASES.items():
            if label in aliases and field not in meta:
                meta[field] = text
                break
    return meta


def _xlsx_best_bill_rows(workbook) -> tuple[list[dict], dict]:
    """Read every sheet once (read-only iterators are single-pass) and pick
    the one whose header looks like a bill line-item table.

    ChatGPT/DMS exports often put invoice meta on the first sheet and the
    actual Cs/Pcs/UPC rows on a later 'Line Items' sheet — `active` would
    miss them.
    """
    candidates: list[tuple[int, int, list[dict]]] = []
    meta: dict[str, str] = {}
    for sheet in workbook.worksheets:
        # B3-004: cap what we materialise into worker memory, matching the
        # master-import path's guards. A crafted / huge bill sheet otherwise
        # loads every row and JSON-serialises it onto the job.
        materialized = []
        cells = 0
        for idx, row in enumerate(sheet.iter_rows(values_only=True)):
            if idx > MAX_IMPORT_ROWS:
                raise BusinessRuleError(
                    f"Bill import exceeds {MAX_IMPORT_ROWS} rows. Split the file and retry."
                )
            row = tuple(row)
            cells += len(row)
            if cells > MAX_IMPORT_CELLS:
                raise BusinessRuleError(
                    f"Bill import exceeds {MAX_IMPORT_CELLS} cells. Split the file and retry."
                )
            materialized.append(row)
        if not materialized:
            continue
        header = [str(h or "").strip().lower() for h in materialized[0]]
        if not any(header):
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
        for raw_row in materialized[1:]:
            if raw_row is None or all(v in (None, "") for v in raw_row):
                continue
            data.append({header[i]: raw_row[i] for i in range(min(len(header), len(raw_row)))})
        candidates.append((score, len(data), data))
        if score < 2:
            for key, value in _xlsx_kv_meta(materialized).items():
                meta.setdefault(key, value)
    if not candidates:
        return [], meta
    scored = [c for c in candidates if c[0] >= 2]
    pool = scored or candidates
    pool.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return pool[0][2], meta


def _read_structured_rows(raw: bytes, filename: str) -> list[dict]:
    rows, _meta = _read_structured_bill(raw, filename)
    return rows


def _normalize_sheet_name(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_")


def _cell_to_import_text(value) -> str:
    """Coerce Excel cell values to JSON-safe text (dates, ints, floats)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None and value.time() == time.min:
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def _sku_keys_from_rows(rows) -> set[str]:
    keys = set()
    for raw in rows or []:
        row = {str(k).strip().lower(): v for k, v in (raw or {}).items()}
        sku = _cell_to_import_text(row.get("sku") or row.get("item code") or "")
        if sku:
            keys.add(sku.casefold())
    return keys


def _prune_unmatched_extra_sheets(extra_sheets, item_rows) -> list[dict]:
    """Drop extra sheets whose SKUs match none of the item rows (mis-filled templates)."""
    notes = []
    item_skus = _sku_keys_from_rows(item_rows)
    for key in ("opening_lots", "opening_serials"):
        sheet = extra_sheets.get(key) or []
        if not sheet:
            continue
        sheet_skus = _sku_keys_from_rows(sheet)
        if sheet_skus and item_skus.isdisjoint(sheet_skus):
            extra_sheets[key] = []
            notes.append({"source": key, "target": "ignored (no matching SKUs)"})
    return notes


def _rows_from_worksheet(sheet) -> list[dict]:
    materialized = []
    cells = 0
    for idx, row in enumerate(sheet.iter_rows(values_only=True)):
        if idx > MAX_IMPORT_ROWS:
            raise BusinessRuleError(
                f"Import exceeds {MAX_IMPORT_ROWS} rows. Split the file and retry."
            )
        cells += len(row or ())
        if cells > MAX_IMPORT_CELLS:
            raise BusinessRuleError("Import spreadsheet is too large (cell cap).")
        materialized.append(tuple(row))
    if not materialized:
        return []
    header = [str(h or "").strip().lower() for h in materialized[0]]
    if not any(header):
        return []
    rows = []
    for raw_row in materialized[1:]:
        if raw_row is None or all(v in (None, "") for v in raw_row):
            continue
        rows.append(
            {
                header[i]: _cell_to_import_text(raw_row[i])
                for i in range(min(len(header), len(raw_row)))
            }
        )
    return rows


def _read_named_sheets(raw: bytes) -> dict[str, list[dict]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheets = {}
    for sheet in workbook.worksheets:
        sheets[_normalize_sheet_name(sheet.title)] = _rows_from_worksheet(sheet)
    return sheets


def _read_structured_bill(raw: bytes, filename: str) -> tuple[list[dict], dict]:
    """Deterministic CSV/XLSX row reader for the bill-import 'I have an
    export' path (§4.1) — no LLM involved, exact by construction."""
    name = (filename or "").lower()
    head = raw[:8]
    # B3-006: decide by content, not just the filename. A .xls (OLE2) file — or
    # any upload whose browser content-type is application/vnd.ms-excel — that
    # doesn't end in .xlsx falls through to the CSV branch, where cp1252
    # "decodes" the binary into garbage rows. Sniff the magic bytes first.
    is_zip = head.startswith(b"PK\x03\x04")  # xlsx/xlsm is a zip container
    is_ole2 = head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")  # legacy .xls
    if is_ole2:
        raise BusinessRuleError(
            "Legacy .xls files aren't supported — re-save as .xlsx or export CSV."
        )
    if is_zip or name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return _xlsx_best_bill_rows(workbook)

    try:
        text = _decode_csv_text(raw)
    except BusinessRuleError:
        raise
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    cells = 0
    for idx, row in enumerate(reader):
        if idx > MAX_IMPORT_ROWS:
            raise BusinessRuleError(
                f"Bill import exceeds {MAX_IMPORT_ROWS} rows. Split the file and retry."
            )
        cells += len(row)
        if cells > MAX_IMPORT_CELLS:
            raise BusinessRuleError(
                f"Bill import exceeds {MAX_IMPORT_CELLS} cells. Split the file and retry."
            )
        rows.append({(k or "").strip().lower(): v for k, v in row.items()})
    return rows, {}


# Header-level money that a flat CSV can only carry as a repeated column.
_CSV_FREIGHT_KEYS = ("freight", "freight charges", "packing", "packing charges", "other charges")
_CSV_BILL_DISCOUNT_KEYS = ("bill discount", "invoice discount", "cash discount")


def _csv_header_money(rows: list[dict]) -> dict:
    """First non-empty freight / bill-discount cell of a flat file (same value on every row)."""
    found = {}
    for target, keys in (("freight", _CSV_FREIGHT_KEYS), ("invoice_discount", _CSV_BILL_DISCOUNT_KEYS)):
        for row in rows:
            for key in keys:
                value = row.get(key)
                if value not in (None, "") and str(value).strip():
                    found[target] = str(value).strip().replace(",", "")
                    break
            if target in found:
                break
    return found


def _map_structured_row(row: dict) -> dict:
    mapped = {}
    claimed = set(_CSV_FREIGHT_KEYS) | set(_CSV_BILL_DISCOUNT_KEYS)
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


def _inclusive_flag(value) -> bool:
    return str(value or "").strip().casefold() in {"inclusive", "yes", "true", "1", "y"}


def _validate_extra_sheets(job, extra_sheets, preview) -> list[dict]:
    errors = []
    if not extra_sheets:
        return errors
    from inventory.item_stock import match_warehouse

    preview_by_sku = {
        (row.get("sku") or "").strip().casefold(): row for row in preview if row.get("sku")
    }
    preview_skus = set(preview_by_sku)
    lots = extra_sheets.get("opening_lots") or []
    serials = extra_sheets.get("opening_serials") or []
    serial_skus = set(_extra_serial_counts(extra_sheets))
    serial_skus.update(
        (row.get("sku") or "").strip().casefold()
        for row in preview
        if _tracking_from_row(row)[1]
    )
    batched_skus = set()
    for raw in lots:
        row = {str(k).strip().lower(): v for k, v in (raw or {}).items()}
        sku = str(row.get("sku") or row.get("item code") or "").strip().casefold()
        if str(row.get("batch_no") or row.get("batch no") or row.get("batch") or "").strip():
            batched_skus.add(sku)
    for index, raw in enumerate(lots, start=2):
        row = _map_master_row(raw) if not isinstance(raw, dict) else {str(k).strip().lower(): v for k, v in raw.items()}
        sku = str(row.get("sku") or row.get("item code") or "").strip()
        qty = str(row.get("quantity") or row.get("qty") or "").strip()
        batch_no = str(row.get("batch_no") or row.get("batch no") or row.get("batch") or "").strip()
        expiry = str(row.get("expiry_date") or row.get("expiry date") or row.get("expiry") or "").strip()
        godown = str(row.get("godown") or row.get("warehouse") or "").strip()
        row_errors = []
        preview_row = preview_by_sku.get(sku.casefold()) if sku else None
        item_type = str((preview_row or {}).get("product_type") or "").strip().casefold()
        if item_type in {"service", "services"}:
            row_errors.append(f"Service items cannot have opening stock (row {index}).")
        if not sku:
            row_errors.append("sku is required")
        elif sku.casefold() not in preview_skus:
            row_errors.append(f"unknown sku '{sku}' on opening_lots")
        if not qty:
            row_errors.append("quantity is required")
        if sku.casefold() in batched_skus and (not batch_no or not expiry):
            row_errors.append("Batch tracking is on but this row has no Batch no or Expiry.")
        if sku.casefold() in serial_skus:
            row_errors.append("Serial-tracked items cannot use opening_lots. List serial numbers instead.")
        if godown:
            try:
                match_warehouse(job.company, godown)
            except BusinessRuleError as exc:
                row_errors.append(str(exc.detail if hasattr(exc, "detail") else exc))
        if row_errors:
            errors.append({"row": index, "sheet": "opening_lots", "errors": row_errors, "data": row})
    for index, raw in enumerate(serials, start=2):
        row = {str(k).strip().lower(): v for k, v in (raw or {}).items()}
        sku = str(row.get("sku") or row.get("item code") or "").strip()
        serial = str(row.get("serial_no") or row.get("serial") or "").strip()
        row_errors = []
        if not sku:
            row_errors.append("sku is required")
        elif sku.casefold() not in preview_skus:
            row_errors.append(f"unknown sku '{sku}' on opening_serials")
        if not serial:
            row_errors.append("serial no is required")
        if row_errors:
            errors.append({"row": index, "sheet": "opening_serials", "errors": row_errors, "data": row})
    return errors


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
        job.file_sha256 = hashlib.sha256(raw).hexdigest()
        if (
            job.kind in (ImportJob.Kind.PRODUCTS, ImportJob.Kind.OPENING_STOCK)
            and job.file_sha256
            and ImportJob.objects.filter(
                company=job.company,
                kind=job.kind,
                file_sha256=job.file_sha256,
                status=ImportJob.Status.COMMITTED,
            ).exclude(pk=job.pk).exists()
        ):
            raise BusinessRuleError("This file was already committed. Re-upload will not post opening stock again.")
        filename = job.file.original_name or job.file.file.name or ""
        name_lower = filename.lower()
        extra_sheets = {}
        extra_sheet_notes = []
        if name_lower.endswith((".xlsx", ".xlsm")):
            if job.kind == ImportJob.Kind.PRODUCTS:
                named = _read_named_sheets(raw)
                preferred_item_sheets = ("items", "products", "bulk_upload", "sheet1")
                items_key = next((k for k in preferred_item_sheets if k in named and named[k]), None)
                if items_key:
                    rows = named[items_key]
                elif any(k in named for k in ("items", "products")):
                    raise BusinessRuleError(
                        "No item rows found. Add at least one product on the items sheet."
                    )
                else:
                    skip = {"notes", "opening_lots", "opening_serials", "openinglots", "openingserials"}
                    rows = next((v for k, v in named.items() if v and k not in skip), [])
                extra_sheets = {
                    "opening_lots": named.get("opening_lots") or named.get("openinglots") or [],
                    "opening_serials": named.get("opening_serials") or named.get("openingserials") or [],
                }
                extra_sheet_notes = _prune_unmatched_extra_sheets(extra_sheets, rows)
            else:
                rows = _read_structured_rows(raw, filename)
            if not rows:
                raise BusinessRuleError("CSV file has no header row.")
            fieldnames = list(rows[0].keys()) if rows else []
            if not fieldnames:
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
        from inventory.services import InventoryService as _InvSvc

        skus_with_opening = _InvSvc.active_opening_product_ids(job.company)

        extra_serial_counts = _extra_serial_counts(extra_sheets)

        # B3-023: build once instead of one `match_warehouse` DB round-trip
        # (itself two queries) per row for a godown-heavy file.
        from inventory.models import Warehouse

        warehouses = list(Warehouse.objects.filter(company=job.company))
        _by_key = {}
        for w in warehouses:
            _by_key[w.name.casefold()] = w
            if w.code:
                _by_key[w.code.casefold()] = w
        warehouse_index = (_by_key, ", ".join(w.name for w in warehouses if w.is_active) or "(none)")

        header_map = {}
        cf_defs = []
        if job.kind == ImportJob.Kind.PRODUCTS:
            from masters.custom_fields import active_defs, resolve_import_columns

            cf_defs = active_defs(job.company)
            header_map, cf_header_errors = resolve_import_columns(list(fieldnames), cf_defs)
            if cf_header_errors:
                raise BusinessRuleError(cf_header_errors[0])
            existing_barcodes -= _released_barcodes(rows, products_by_sku)

        preview, errors = [], []
        seen_skus, seen_barcodes = set(), set()
        for index, raw_row in enumerate(rows, start=2):  # header is row 1
            row = _map_master_row(raw_row)
            row_errors = _validate_row(
                job.kind, row, job.company,
                seen_skus=seen_skus, seen_barcodes=seen_barcodes,
                existing_skus=existing_skus, existing_barcodes=existing_barcodes,
                products_by_sku=products_by_sku, skus_with_opening=skus_with_opening,
                extra_serial_counts=extra_serial_counts, warehouse_index=warehouse_index,
            )
            if job.kind == ImportJob.Kind.PRODUCTS and header_map:
                row_errors.extend(_custom_field_row_errors(row, header_map, cf_defs))
            if row_errors:
                errors.append({"row": index, "errors": row_errors, "data": row})
            else:
                preview.append(row)

        extra_sheets = extra_sheets or {}
        inline_lots = _lots_from_item_rows(preview)
        if inline_lots:
            extra_sheets["opening_lots"] = list(extra_sheets.get("opening_lots") or []) + inline_lots
        inline_serials = _serials_from_item_rows(preview)
        if inline_serials:
            extra_sheets["opening_serials"] = list(extra_sheets.get("opening_serials") or []) + inline_serials
        extra_errors = _validate_extra_sheets(job, extra_sheets, preview)
        errors.extend(extra_errors)
        job.total_rows = len(preview) + len(errors)
        job.valid_rows = len(preview)
        job.error_rows = len(errors)
        job.preview = preview
        job.errors = errors
        job.column_mappings = resolve_master_column_mappings(fieldnames) + extra_sheet_notes
        job.extra_sheets = extra_sheets
        job.custom_field_defs_snapshot = cf_defs
        job.custom_field_header_map = header_map
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
        # R4-015 (reverted): CUSTOMERS / SUPPLIERS / OPENING_STOCK imports commit
        # PARTIALLY by design (write valid rows, report the rest — see
        # test_commit_writes_only_valid_rows / test_opening_stock_import). Only
        # PRODUCTS is all-or-nothing. Invalid rows are still skipped, never
        # written, so bad data does not land regardless.
        if job.kind == ImportJob.Kind.PRODUCTS and job.error_rows:
            raise BusinessRuleError(
                "Fix all errors before commit. Any invalid row blocks the entire job.",
                code=HelpCode.IMPORT_INVALID_ROWS,
            )
        preview = job.preview if isinstance(job.preview, list) else []
        skipped = []
        if job.kind == ImportJob.Kind.CUSTOMERS:
            created, skipped = ImportService._commit_customers(job, preview, user)
        elif job.kind == ImportJob.Kind.SUPPLIERS:
            created, skipped = ImportService._commit_suppliers(job, preview, user)
        elif job.kind == ImportJob.Kind.PRODUCTS:
            created = ImportService._commit_products(job, preview, user)
        elif job.kind == ImportJob.Kind.OPENING_STOCK:
            created = ImportService._commit_opening_stock(job, preview, user)
        else:
            raise BusinessRuleError(f"Unsupported import kind '{job.kind}'.")

        if skipped:
            # B3-018: surface "skipped (already exists)" rows in job.errors so
            # the response / error CSV shows them; created < valid_rows is no
            # longer silent.
            job.errors = list(job.errors or []) + skipped
            job.error_rows = len(job.errors)
        job.preview = preview
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
        created = 0
        existing_gstin = {
            (c.gstin or "").strip().upper()
            for c in Customer.objects.filter(company=job.company).exclude(gstin="")
        }
        existing_phone = {
            (c.phone or "").strip()
            for c in Customer.objects.filter(company=job.company).exclude(phone="")
        }
        existing_name = {
            (c.name or "").strip().lower()
            for c in Customer.objects.filter(company=job.company)
        }
        rows = []
        skipped = []  # B3-018: report duplicates instead of silently dropping
        for idx, row in enumerate(preview, start=1):
            gstin = (row.get("gstin") or "").strip().upper()
            phone = (row.get("phone") or "").strip()
            name = (row.get("name") or "").strip()
            if gstin and gstin in existing_gstin:
                skipped.append({"row": idx, "data": row, "errors": [f"skipped: a customer with GSTIN {gstin} already exists"], "skipped": True})
                continue
            if phone and phone in existing_phone:
                skipped.append({"row": idx, "data": row, "errors": [f"skipped: a customer with phone {phone} already exists"], "skipped": True})
                continue
            if name.lower() in existing_name:
                skipped.append({"row": idx, "data": row, "errors": [f"skipped: a customer named '{name}' already exists"], "skipped": True})
                continue
            # CUS-25: same GSTIN/state rules as the customer form (masters.gstin_rules).
            state = (row.get("state", "") or "").strip()
            if gstin:
                if not state:
                    state = gstin_rules.derive_state(gstin) or ""
                elif getattr(settings, "CUSTOMER_STRICT_VALIDATION", False):
                    wanted = gstin_rules.state_conflicts(gstin, state)
                    if wanted:
                        skipped.append({
                            "row": idx, "data": row, "skipped": True,
                            "errors": [f"skipped: GSTIN {gstin} belongs to {wanted}, not {state}"],
                        })
                        continue
            rows.append(
                Customer(
                    company=job.company,
                    name=row["name"],
                    phone=row.get("phone", "") or "",
                    email=row.get("email", "") or "",
                    gstin=gstin,
                    pan=gstin_rules.derive_pan(gstin),
                    state=state,
                    billing_address=row.get("address", "") or "",
                    created_by=user,
                    updated_by=user,
                    created_at=now,
                    updated_at=now,
                )
            )
            if gstin:
                existing_gstin.add(gstin)
            if phone:
                existing_phone.add(phone)
            existing_name.add(name.lower())
        if rows:
            Customer.objects.bulk_create(rows, batch_size=BULK_BATCH)
            created = len(rows)
        return created, skipped

    @staticmethod
    def _commit_suppliers(job, preview, user):
        now = timezone.now()
        existing_gstin = {
            (s.gstin or "").strip().upper()
            for s in Supplier.objects.filter(company=job.company).exclude(gstin="")
        }
        existing_phone = {
            (s.phone or "").strip()
            for s in Supplier.objects.filter(company=job.company).exclude(phone="")
        }
        existing_name = {
            (s.name or "").strip().lower()
            for s in Supplier.objects.filter(company=job.company)
        }
        rows = []
        skipped = []  # B3-018
        for idx, row in enumerate(preview, start=1):
            gstin = (row.get("gstin") or "").strip().upper()
            phone = (row.get("phone") or "").strip()
            name = (row.get("name") or "").strip()
            if gstin and gstin in existing_gstin:
                skipped.append({"row": idx, "data": row, "errors": [f"skipped: a supplier with GSTIN {gstin} already exists"], "skipped": True})
                continue
            if phone and phone in existing_phone:
                skipped.append({"row": idx, "data": row, "errors": [f"skipped: a supplier with phone {phone} already exists"], "skipped": True})
                continue
            if name.lower() in existing_name:
                skipped.append({"row": idx, "data": row, "errors": [f"skipped: a supplier named '{name}' already exists"], "skipped": True})
                continue
            rows.append(
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
            )
            if gstin:
                existing_gstin.add(gstin)
            if phone:
                existing_phone.add(phone)
            existing_name.add(name.lower())
        if rows:
            Supplier.objects.bulk_create(rows, batch_size=BULK_BATCH)
        return len(rows), skipped

    @staticmethod
    def _resolve_units(company, preview, user):
        wanted = {}
        for row in preview:
            for field in ("unit", "unit_name", "alternate_unit"):
                unit_str = (row.get(field) or "").strip()
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
                        uqc_code=normalize_uqc(orig),
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
    def _resolve_categories(company, preview, user):
        wanted = {}
        for row in preview:
            name = (row.get("category") or "").strip()
            if name:
                wanted[name.casefold()] = name
        if not wanted:
            return {}
        by_key = {
            (c.name or "").casefold(): c
            for c in Category.objects.filter(company=company)
        }
        now = timezone.now()
        missing = [
            Category(
                company=company, name=orig, created_by=user, updated_by=user,
                created_at=now, updated_at=now,
            )
            for key, orig in wanted.items()
            if key not in by_key
        ]
        if missing:
            created = Category.objects.bulk_create(missing, batch_size=BULK_BATCH)
            for category in created:
                by_key[category.name.casefold()] = category
        return by_key

    @staticmethod
    def _resolve_brands(company, preview):
        wanted = {
            (row.get("brand_code") or "").strip().casefold()
            for row in preview
            if (row.get("brand_code") or "").strip()
        }
        if not wanted:
            return {}
        return {
            (b.name or "").casefold(): b
            for b in Brand.objects.filter(company=company)
            if (b.name or "").casefold() in wanted
        }

    @staticmethod
    def _commit_products(job, preview, user):
        now = timezone.now()
        units = ImportService._resolve_units(job.company, preview, user)
        categories = ImportService._resolve_categories(job.company, preview, user)
        brands = ImportService._resolve_brands(job.company, preview)
        extra_skus = {
            str(r.get("sku") or r.get("item code") or "").strip().casefold()
            for r in (job.extra_sheets or {}).get("opening_lots") or []
        } | {
            str(r.get("sku") or r.get("item code") or "").strip().casefold()
            for r in (job.extra_sheets or {}).get("opening_serials") or []
        }
        existing_by_sku = {
            (p.sku or "").casefold(): p
            for p in Product.objects.filter(company=job.company).exclude(sku="")
        }
        # B3-012: _custom_fields_for_commit used to refresh_from_db the
        # company row and rebuild this set on every single preview row. The
        # live custom-field defs can't change mid-commit (this all runs in
        # one call), so do it once here instead.
        live_cf_keys = None
        if job.custom_field_header_map:
            job.company.refresh_from_db(fields=["item_custom_field_defs"])
            live_cf_keys = {
                str(spec.get("key") or "").casefold()
                for spec in (job.company.item_custom_field_defs or [])
                if isinstance(spec, dict) and spec.get("key")
            }
        creates = []
        create_opening = []
        updates = []
        update_opening = []
        barcode_rewrites: dict[int, str] = {}
        for row in preview:
            unit_str = (row.get("unit") or row.get("unit_name") or "").strip()
            unit_obj = units.get(unit_str.casefold()) if unit_str else None
            alt_str = (row.get("alternate_unit") or "").strip()
            alt_obj = units.get(alt_str.casefold()) if alt_str else None
            if alt_obj is not None and alt_obj == unit_obj:
                alt_obj = None
            category_str = (row.get("category") or "").strip()
            brand_str = (row.get("brand_code") or "").strip()
            purchase_price = Decimal(row.get("purchase_price") or "0")
            is_service = _is_service_type(row)
            track_batch, track_serial = _tracking_from_row(row)
            track_inventory = _optional_bool(row.get("track_inventory"), default=not is_service)
            if is_service:
                track_inventory = False
                track_batch = False
                track_serial = False
            sku_key = (row.get("sku") or "").strip().casefold()
            existing = existing_by_sku.get(sku_key) if sku_key else None
            opening_stock_raw = (row.get("opening_stock") or row.get("quantity") or "").strip()
            opening_qty = Decimal("0")
            if opening_stock_raw:
                try:
                    opening_qty = Decimal(opening_stock_raw)
                except InvalidOperation:
                    opening_qty = Decimal("0")
            if is_service or sku_key in extra_skus or track_serial:
                opening_spec = (False, None, None)
            elif opening_qty > 0:
                unit_cost_val = (
                    Decimal(row["unit_cost"])
                    if (row.get("unit_cost") or "").strip()
                    else (purchase_price if purchase_price > 0 else None)
                )
                opening_spec = (True, opening_qty, unit_cost_val)
            else:
                opening_spec = (False, None, None)
            if existing is not None:
                existing.name = row["name"]
                barcode = (row.get("barcode") or "").strip()
                if barcode:
                    old_barcode = (existing.barcode or "").strip()
                    if barcode.casefold() != old_barcode.casefold():
                        barcode_rewrites[existing.pk] = barcode
                        existing.barcode = ""
                    else:
                        existing.barcode = barcode
                if (row.get("hsn_code") or "").strip():
                    existing.hsn_code = row.get("hsn_code") or ""
                if (row.get("description") or "").strip():
                    existing.description = row.get("description") or ""
                if category_str:
                    existing.category = categories.get(category_str.casefold())
                if brand_str:
                    existing.brand = brands.get(brand_str.casefold())
                if unit_obj is not None:
                    existing.unit = unit_obj
                if alt_obj is not None:
                    existing.alternate_unit = alt_obj
                if (row.get("conversion_rate") or "").strip():
                    existing.conversion_rate = Decimal(row.get("conversion_rate") or "1")
                if (row.get("gst_rate") or "").strip():
                    existing.gst_rate = Decimal(row.get("gst_rate") or "0")
                if (row.get("purchase_price") or "").strip():
                    existing.purchase_price = purchase_price
                if (row.get("selling_price") or "").strip():
                    existing.selling_price = Decimal(row.get("selling_price") or "0")
                if (row.get("mrp") or "").strip():
                    existing.mrp = Decimal(row.get("mrp") or "0")
                if (row.get("wholesale_price") or "").strip():
                    existing.wholesale_price = Decimal(row.get("wholesale_price") or "0")
                if (row.get("default_discount_percent") or "").strip():
                    existing.default_discount_percent = Decimal(row.get("default_discount_percent") or "0")
                if (row.get("reorder_level") or "").strip():
                    existing.reorder_level = Decimal(row.get("reorder_level") or "0")
                if row.get("selling_tax_inclusive") not in (None, ""):
                    existing.selling_tax_inclusive = _inclusive_flag(row.get("selling_tax_inclusive"))
                if row.get("purchase_tax_inclusive") not in (None, ""):
                    existing.purchase_tax_inclusive = _inclusive_flag(row.get("purchase_tax_inclusive"))
                existing.custom_fields = _custom_fields_for_commit(
                    job, row, existing.custom_fields, live_keys=live_cf_keys,
                )
                existing.updated_by = user
                existing.updated_at = now
                updates.append(existing)
                update_opening.append(opening_spec)
                # R4-013: this row updated a pre-existing product — void must NOT
                # delete/deactivate it.
                row["_import_created"] = False
            else:
                row["_import_created"] = True
                creates.append(
                    Product(
                        company=job.company,
                        name=row["name"],
                        sku=row.get("sku", "") or "",
                        barcode=row.get("barcode", "") or "",
                        hsn_code=row.get("hsn_code", "") or "",
                        description=row.get("description", "") or "",
                        category=categories.get(category_str.casefold()) if category_str else None,
                        brand=brands.get(brand_str.casefold()) if brand_str else None,
                        unit=unit_obj,
                        alternate_unit=alt_obj,
                        conversion_rate=Decimal(row.get("conversion_rate") or "1"),
                        gst_rate=Decimal(row.get("gst_rate") or "0"),
                        purchase_price=purchase_price,
                        selling_price=Decimal(row.get("selling_price") or "0"),
                        mrp=Decimal(row.get("mrp") or "0"),
                        wholesale_price=Decimal(row.get("wholesale_price") or "0"),
                        default_discount_percent=Decimal(row.get("default_discount_percent") or "0"),
                        reorder_level=Decimal(row.get("reorder_level") or "0"),
                        product_type=Product.ProductType.SERVICE if is_service else Product.ProductType.GOODS,
                        track_inventory=bool(track_inventory) and not is_service,
                        track_batch=bool(track_batch) and not is_service,
                        track_serial=bool(track_serial) and not is_service,
                        selling_tax_inclusive=_inclusive_flag(row.get("selling_tax_inclusive")),
                        purchase_tax_inclusive=_inclusive_flag(row.get("purchase_tax_inclusive")),
                        custom_fields=_custom_fields_for_commit(job, row, live_keys=live_cf_keys),
                        created_by=user,
                        updated_by=user,
                        created_at=now,
                        updated_at=now,
                    )
                )
                create_opening.append(opening_spec)

        try:
            if updates:
                Product.objects.bulk_update(
                    updates,
                    [
                        "name", "barcode", "hsn_code", "description", "category", "brand",
                        "unit", "alternate_unit", "conversion_rate", "gst_rate",
                        "purchase_price", "selling_price", "mrp", "wholesale_price",
                        "default_discount_percent", "reorder_level",
                        "selling_tax_inclusive", "purchase_tax_inclusive", "custom_fields",
                        "updated_by", "updated_at",
                    ],
                    batch_size=BULK_BATCH,
                )
                if barcode_rewrites:
                    delayed = []
                    for product in updates:
                        new_barcode = barcode_rewrites.get(product.pk)
                        if not new_barcode:
                            continue
                        product.barcode = new_barcode
                        delayed.append(product)
                    if delayed:
                        Product.objects.bulk_update(delayed, ["barcode"], batch_size=BULK_BATCH)
            created_products = Product.objects.bulk_create(creates, batch_size=BULK_BATCH) if creates else []
        except IntegrityError:
            raise BusinessRuleError(
                "Could not import items because a SKU or barcode is no longer unique. Preview the file again."
            ) from None
        opening_items = [
            {"product": product, "quantity": qty, "unit_cost": cost}
            for product, (has_opening, qty, cost) in list(zip(created_products, create_opening)) + list(zip(updates, update_opening))
            if has_opening
        ]
        ImportService._post_opening_items(job, opening_items, user)
        ImportService._post_extra_opening(job, created_products, updates, user)
        return len(preview)


    @staticmethod
    def _post_extra_opening(job, created_products, updates, user):
        extra = job.extra_sheets or {}
        lots = extra.get("opening_lots") or []
        serials = extra.get("opening_serials") or []
        if not lots and not serials:
            return
        from inventory.item_stock import match_warehouse
        from inventory.services import InventoryService
        from masters.models import Product as ProductModel

        # B3-002: opening_lots / opening_serials rows for a SKU that already
        # existed (so the row landed in `updates`, not `created_products`)
        # previously had no matching entry here at all -- they passed
        # `_validate_extra_sheets` (which checks against every preview SKU,
        # created or updated) but were silently dropped at commit. Index
        # both buckets so an existing product's opening lots/serials post.
        all_products = list(created_products) + list(updates)
        by_sku = {(p.sku or "").casefold(): p for p in all_products if p.sku}
        batched_skus = {
            str(r.get("sku") or r.get("item code") or "").strip().casefold()
            for r in lots
            if str(r.get("batch_no") or r.get("batch no") or r.get("batch") or "").strip()
        }
        if batched_skus:
            ProductModel.objects.filter(
                company=job.company, sku__in=[p.sku for p in all_products if (p.sku or "").casefold() in batched_skus]
            ).update(track_batch=True)
            for product in all_products:
                if (product.sku or "").casefold() in batched_skus:
                    product.track_batch = True
        serial_skus = {str(r.get("sku") or r.get("item code") or "").strip().casefold() for r in serials}
        if serial_skus:
            ProductModel.objects.filter(
                company=job.company, sku__in=[p.sku for p in all_products if (p.sku or "").casefold() in serial_skus]
            ).update(track_serial=True)
            for product in all_products:
                if (product.sku or "").casefold() in serial_skus:
                    product.track_serial = True
        for raw in lots:
            row = {str(k).strip().lower(): v for k, v in raw.items()}
            sku = str(row.get("sku") or row.get("item code") or "").strip()
            product = by_sku.get(sku.casefold())
            if product is None:
                continue
            if product.track_serial:
                raise BusinessRuleError("Serial numbers are required for serial-tracked opening stock.")
            warehouse = match_warehouse(job.company, str(row.get("godown") or row.get("warehouse") or ""))
            qty = Decimal(str(row.get("quantity") or row.get("qty") or "0"))
            expiry_raw = str(row.get("expiry_date") or row.get("expiry") or "").strip()
            mfg_raw = str(row.get("manufacturing_date") or row.get("mfg") or "").strip()
            as_of_raw = str(row.get("as_of") or row.get("as of") or "").strip()
            expiry = parse_date(expiry_raw[:10]) if expiry_raw else None
            mfg = parse_date(mfg_raw[:10]) if mfg_raw else None
            as_of = parse_date(as_of_raw[:10]) if as_of_raw else None
            cost = row.get("unit_cost") or row.get("unit cost")
            InventoryService.post_opening(
                company=job.company,
                product=product,
                quantity=qty,
                unit_cost=cost if cost not in (None, "") else None,
                warehouse=warehouse,
                batch_no=str(row.get("batch_no") or row.get("batch") or ""),
                expiry_date=expiry,
                manufacturing_date=mfg,
                as_of=as_of,
                user=user,
                reference_type="import",
                reference_id=job.pk,
            )
        grouped = {}
        for raw in serials:
            row = {str(k).strip().lower(): v for k, v in raw.items()}
            sku = str(row.get("sku") or row.get("item code") or "").strip().casefold()
            godown = str(row.get("godown") or row.get("warehouse") or "").strip().casefold()
            grouped.setdefault((sku, godown), []).append(row)
        for (sku, _godown), rows in grouped.items():
            product = by_sku.get(sku)
            if product is None:
                continue
            warehouse = match_warehouse(job.company, str(rows[0].get("godown") or rows[0].get("warehouse") or ""))
            numbers = [str(r.get("serial_no") or r.get("serial") or "").strip() for r in rows]
            cost = rows[0].get("unit_cost")
            InventoryService.post_opening(
                company=job.company,
                product=product,
                quantity=len(numbers),
                unit_cost=cost,
                warehouse=warehouse,
                serial_numbers=numbers,
                user=user,
                reference_type="import",
                reference_id=job.pk,
            )
            # R4-014: tag the units this import created for a precise void.
            from inventory.models import SerialNumber as _SN

            _SN.objects.filter(
                company=job.company, product=product,
                serial_number__in=[n for n in numbers if n], import_job_ref__isnull=True,
            ).update(import_job_ref=job.pk)

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
            quantity = Decimal(row["quantity"])
            unit_cost = Decimal(row["unit_cost"]) if (row.get("unit_cost") or "").strip() else None
            serials = _parse_serial_numbers(row.get("serial_no"))
            if product.track_serial or serials:
                movement = InventoryService.post_opening(
                    company=job.company,
                    product=product,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    serial_numbers=serials,
                    user=user,
                    reference_type="import",
                    reference_id=job.pk,
                )
                if serials:
                    # R4-014: tag the units this import created for a precise void.
                    from inventory.models import SerialNumber

                    SerialNumber.objects.filter(
                        company=job.company, product=product,
                        serial_number__in=serials, import_job_ref__isnull=True,
                    ).update(import_job_ref=job.pk)
                if job.company.accounting_enabled:
                    from accounting.services import PostingService

                    PostingService.post_opening_stock(movement, user)
            else:
                items.append({
                    "product": product,
                    "quantity": quantity,
                    "unit_cost": unit_cost,
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
        """CR-053: compensating ADJUSTMENT only — never mutate StockMovement.reference_type."""
        qty = abs(Decimal(str(movement.quantity or 0)))
        if qty <= 0:
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

        # R4-014: serial-tracked opening stock received SerialNumber rows that
        # the movement reversal alone doesn't touch — scrap exactly the units
        # this import created (tagged with import_job_ref at commit time), plus a
        # best-effort fallback for pre-tag imports, so nothing orphans AVAILABLE.
        from inventory.models import SerialNumber

        SerialNumber.objects.filter(
            company=job.company,
            import_job_ref=job.pk,
            status=SerialNumber.Status.AVAILABLE,
        ).update(status=SerialNumber.Status.SCRAPPED, updated_by=user)

        _void_serials: list[str] = []
        for _r in (job.preview if isinstance(job.preview, list) else []):
            _void_serials += _parse_serial_numbers(_r.get("serial_no") or _r.get("serial_numbers"))
        for _r in (job.extra_sheets or {}).get("opening_serials") or []:
            _void_serials += _parse_serial_numbers(
                _r.get("serial_no") or _r.get("serial number") or _r.get("serial_numbers")
            )
        _void_serials = [s for s in {s.strip() for s in _void_serials} if s]
        if _void_serials:
            SerialNumber.objects.filter(
                company=job.company,
                serial_number__in=_void_serials,
                import_job_ref__isnull=True,
                status=SerialNumber.Status.AVAILABLE,
            ).update(status=SerialNumber.Status.SCRAPPED, updated_by=user)

        if job.kind == ImportJob.Kind.PRODUCTS:
            preview_rows = job.preview if isinstance(job.preview, list) else []
            for row in preview_rows:
                # R4-013: never delete/deactivate a product this import only
                # *updated*. Rows committed before this marker existed fall back
                # to the old (best-effort) behaviour.
                if row.get("_import_created") is False:
                    continue
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
        from collections import defaultdict

        by_sku: dict[str, list] = defaultdict(list)
        for m in movements:
            by_sku[(m.product.sku or "").casefold()].append(m)

        voided = list(job.voided_rows or [])
        blocked = []
        reversed_count = 0
        for sku in wanted:
            key = sku.casefold()
            lots = by_sku.get(key) or []
            product = ImportService._find_imported_product(job, sku=sku)
            if not lots:
                if job.kind == ImportJob.Kind.PRODUCTS and product is not None:
                    ImportService._cleanup_imported_product(job, product, user)
                    voided.append({"sku": sku, "name": product.name})
                    continue
                blocked.append({"sku": sku, "reason": f"No imported opening-stock row found for sku '{sku}'."})
                continue
            lot_blocked = False
            for movement in lots:
                reason = ImportService._movement_is_unused(movement)
                if reason:
                    blocked.append({"sku": sku, "reason": reason})
                    lot_blocked = True
                    break
            if lot_blocked:
                continue
            for movement in lots:
                ImportService._reverse_import_movement(job, movement, user)
                reversed_count += 1
            if job.kind == ImportJob.Kind.PRODUCTS and product is not None:
                ImportService._cleanup_imported_product(job, product, user)
            voided.append({
                "sku": sku,
                "name": getattr(product or getattr(lots[0], "product", None), "name", ""),
            })

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
        if not remaining and not blocked and job.kind in (
            ImportJob.Kind.OPENING_STOCK, ImportJob.Kind.PRODUCTS,
        ):
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


class StalePreviewError(BusinessRuleError):
    """The client edited a version of the preview that is no longer current."""

    status_code = 409
    default_code = "preview_stale"


BILL_PREVIEW_MAX_LINES = int(getattr(settings, "BILL_IMPORT_MAX_LINES", 500) or 500)
# Server-computed fields on a stored line that a client edit must not drop.
_CARRY_LINE_KEYS = (
    "suggested_quantity", "product_id", "create_new", "product_match", "match_key",
    "cess_rate", "cess_amount", "price_list_price", "below_price_list", "excluded_reason", "line_id",
    "printed_taxable_amt", "extras", "flags", "confidence", "bbox", "edited",
)
_NEXT_LINE_ID = "next_line_id"


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def preview_totals(job: ImportJob, preview: dict, *, intra_state: bool | None = None) -> dict:
    """Taxable / GST / cess / grand total of the included lines (23.15, 24.1).

    Runs the *same* tax engine the saved draft uses (line discounts, tax-inclusive
    base extraction, per-unit cess, freight, bill discount, round-off), on
    in-memory stand-ins, so the review screen shows the draft's real numbers.
    """
    from types import SimpleNamespace

    from core.services.tax_engine.india import compute_document_totals

    inclusive = str(preview.get("price_mode") or "").upper() == "INCLUSIVE"

    def _dec(value, default="0"):
        if value in (None, ""):
            return Decimal(default)
        try:
            return Decimal(str(value).strip().rstrip("%").strip() or default)
        except InvalidOperation:
            return Decimal(default)

    items = []
    for ln in preview.get("lines") or []:
        if not ln.get("include"):
            continue
        qty = _dec(ln.get("quantity"))
        if qty <= 0:
            continue
        price = _dec(ln.get("unit_price"))
        items.append(SimpleNamespace(
            quantity=qty,
            unit_price=price,
            unit_price_inclusive=price if inclusive else None,
            discount_percent=_dec(ln.get("discount_percent")),
            gst_rate=_dec(ln.get("gst_rate")),
            cess_rate=_dec(ln.get("cess_rate")),
            cess_amount=_dec(ln.get("cess_amount")),
            supply_nature="TAXABLE",
            taxable_amount=Decimal("0"), cgst=Decimal("0"), sgst=Decimal("0"), igst=Decimal("0"),
            cess=Decimal("0"), line_total=Decimal("0"), applied_rate=Decimal("0"),
            rate_override=False, rate_override_reason="", rate_version="",
        ))
    document = SimpleNamespace(
        price_mode="INCLUSIVE" if inclusive else "EXCLUSIVE",
        additional_charges=_dec(preview.get("additional_charges")),
        invoice_discount=_dec(preview.get("invoice_discount")),
        invoice_discount_mode="AFTER_TAX",
        auto_round_off=True,
        charges_hsn="", charges_gst_rate=Decimal("0"),
        status="DRAFT", company=job.company,
        subtotal=Decimal("0"), discount_total=Decimal("0"), taxable_total=Decimal("0"),
        cgst_total=Decimal("0"), sgst_total=Decimal("0"), igst_total=Decimal("0"),
        cess_total=Decimal("0"), round_off=Decimal("0"), grand_total=Decimal("0"),
    )
    # Only the CGST/SGST vs IGST split depends on the states; the grand total does not.
    out = {"included_lines": len(items)}
    try:
        compute_document_totals(document, items, tax_enabled=True, intra_state=intra_state is not False)
    except BusinessRuleError as exc:
        out.update(
            taxable="0.00", gst="0.00", cess="0.00", charges="0.00", invoice_discount="0.00",
            grand_total="0.00", rounded_total="0", error=str(exc.detail),
        )
        return out
    gst = document.cgst_total + document.sgst_total + document.igst_total
    out.update(
        cgst=str(_q2(document.cgst_total)),
        sgst=str(_q2(document.sgst_total)),
        igst=str(_q2(document.igst_total)),
        # INTRA / INTER when both states are known; ASSUMED_INTRA until the customer's state is.
        tax_type=("ASSUMED_INTRA" if intra_state is None else ("INTRA" if intra_state else "INTER")),
    )
    out.update(
        taxable=str(_q2(document.taxable_total)),
        gst=str(_q2(gst)),
        cess=str(_q2(document.cess_total)),
        charges=str(_q2(document.additional_charges)),
        invoice_discount=str(_q2(document.invoice_discount)),
        grand_total=str(_q2(document.grand_total)),
        rounded_total=str(document.grand_total.quantize(Decimal("1"))),
    )
    printed = preview.get("printed_total")
    if printed not in (None, ""):
        try:
            diff = _q2(_as_decimal(printed) - document.grand_total)
            out["printed_total"] = str(_q2(_as_decimal(printed)))
            out["printed_difference"] = str(diff)
            out["printed_matches"] = abs(diff) <= Decimal("1.00")
        except BusinessRuleError:
            pass
    return out


class BillImportService:
    @staticmethod
    def finalize_preview_lines(preview: dict, lines: list[dict], *, bump: bool = True) -> list[dict]:
        """Give every line a stable `line_id` and bump `preview_version` (24.5).

        `line_id` is server-owned (never the printed S.No, which repeats across
        pages). Existing ids are preserved across edits and clarification.
        """
        highest = max(
            [int(preview.get(_NEXT_LINE_ID) or 1) - 1]
            + [int(ln.get("line_id") or 0) for ln in lines if isinstance(ln, dict)]
        )
        for ln in lines:
            if isinstance(ln, dict) and not ln.get("line_id"):
                highest += 1
                ln["line_id"] = highest
        preview[_NEXT_LINE_ID] = highest + 1
        current = int(preview.get("preview_version") or 0)
        if bump or not current:
            preview["preview_version"] = current + 1
        return lines

    @staticmethod
    def enrich_preview(job: ImportJob, preview: dict) -> dict:
        """Add server-derived review aids: party match, product match per line,
        price-list deviation, company-GSTIN status, totals. Mutates `preview`
        and may bind `job.customer` / `job.supplier` on an exact match."""
        from imports import party_match
        from masters.pricing import resolve_party_price

        is_sales = job.kind == ImportJob.Kind.SALES_BILL
        lines = preview.get("lines") or []

        if is_sales:
            name = preview.get("customer_name") or preview.get("buyer_name") or ""
            gstin = preview.get("buyer_gstin") or ""
        else:
            name = preview.get("supplier_name") or ""
            gstin = preview.get("supplier_gstin") or ""
        # Autosave calls this every few seconds; only rescan the party master
        # when what the bill says about the party actually changed.
        party_key = f"{job.kind}|{gstin}|{name}"
        pm = preview.get("party_match") if preview.get("party_match_key") == party_key else None
        if pm is None:
            if is_sales:
                pm = party_match.match_customer(job.company, gstin=gstin, name=name)
            else:
                pm = party_match.match_supplier(job.company, gstin=gstin, name=name)
            preview["party_match_key"] = party_key
        if is_sales and job.customer_id is None and pm["status"] == "matched" and pm.get("exact"):
            job.customer_id = pm["id"]
        if not is_sales and job.supplier_id is None and pm["status"] == "matched" and pm.get("exact"):
            job.supplier_id = pm["id"]
        pm["bound_id"] = job.customer_id if is_sales else job.supplier_id
        preview["party_match"] = pm

        catalog = None
        customer = None
        if is_sales and job.customer_id:
            customer = Customer.objects.filter(pk=job.customer_id, company=job.company).first()
        for ln in lines:
            chosen = ln.get("product_id")
            key = f"{ln.get('sku') or ''}|{ln.get('name') or ''}|{chosen or ''}"
            if ln.get("product_match") and ln.get("match_key") == key and not (customer and customer.price_list_id):
                continue
            if catalog is None:
                catalog = party_match.build_catalog(job.company)
            if chosen and int(chosen) in catalog["by_id"]:
                match = party_match.product_match_row("matched", catalog["by_id"][int(chosen)], "chosen", 1.0)
            else:
                match = party_match.match_product(ln, catalog)
            ln["product_match"] = match
            ln["match_key"] = key
            if match.get("cess_rate") and ln.get("cess_rate") in (None, ""):
                ln["cess_rate"] = match["cess_rate"]
            if match.get("cess_amount") and ln.get("cess_amount") in (None, ""):
                ln["cess_amount"] = match["cess_amount"]
            ln.pop("price_list_price", None)
            ln.pop("below_price_list", None)
            if customer is not None and customer.price_list_id and match.get("product_id"):
                product = Product.objects.filter(pk=match["product_id"]).first()
                if product is not None:
                    try:
                        list_price, _name = resolve_party_price(
                            customer=customer, product=product, quantity=ln.get("quantity") or None
                        )
                    except Exception:  # noqa: BLE001 — a pricing lookup must not break review
                        list_price = None
                    if list_price is not None:
                        ln["price_list_price"] = str(list_price)
                        try:
                            ln["below_price_list"] = _as_decimal(ln.get("unit_price"), "0") < list_price
                        except BusinessRuleError:
                            ln["below_price_list"] = False
        status = company_gstin_status(job.company, preview, kind=job.kind)
        preview["company_gstin_status"] = {
            "status": status["status"],
            "options": status["options"],
            "resolved_id": status["obj"].pk if status.get("obj") else None,
            "suggestion": status.get("suggestion"),
        }
        preview["new_product_count"] = len(
            [
                ln for ln in lines
                if ln.get("include")
                and not ln.get("product_id")
                and (ln.get("product_match") or {}).get("status") in ("none", "candidates")
            ]
        )
        intra = None
        if is_sales and job.customer_id:
            seller_state = (status["obj"].state if status.get("obj") and getattr(status["obj"], "state", "") else "") or (
                getattr(job.company, "state", "") or ""
            )
            buyer_state = (customer.state if customer is not None else "") or ""
            if seller_state and buyer_state:
                intra = seller_state.strip().casefold() == buyer_state.strip().casefold()
        preview["totals"] = preview_totals(job, preview, intra_state=intra)
        return preview

    @staticmethod
    def start_extraction(job: ImportJob):
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Only purchase/sales bill jobs can be extracted.")
        allowed = {ImportJob.Status.UPLOADED, ImportJob.Status.FAILED}
        # B3-005: a hard worker kill (OOM / SIGKILL / lost broker message)
        # strands the job in EXTRACTING with no recovery path. Treat an
        # EXTRACTING job whose last update predates the task hard limit (plus a
        # margin) as retryable rather than permanently wedged.
        if job.status == ImportJob.Status.EXTRACTING and job.updated_at is not None:
            from django.utils import timezone as _tz

            stale_after = timedelta(seconds=480 + 120)
            if _tz.now() - job.updated_at > stale_after:
                allowed.add(ImportJob.Status.EXTRACTING)
            # 23.13: the task refreshes a heartbeat between batches; a job
            # with no heartbeat for 2 minutes is wedged, retry it early.
            beat = job.extraction_heartbeat_at
            if beat is not None and _tz.now() - beat > timedelta(seconds=120):
                allowed.add(ImportJob.Status.EXTRACTING)
        allowed.add(ImportJob.Status.CANCELLED)
        if job.status not in allowed:
            raise BusinessRuleError(
                "Extraction can only start from UPLOADED or FAILED "
                "(or a stalled EXTRACTING job)."
            )
        job.status = ImportJob.Status.EXTRACTING
        job.failure_reason = ""
        job.errors = []
        job.extraction_heartbeat_at = timezone.now()
        job.save(update_fields=["status", "failure_reason", "errors", "extraction_heartbeat_at", "updated_at"])
        from django.conf import settings
        from imports.tasks import extract_purchase_bill_task

        pk, company_id = job.pk, job.company_id
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            extract_purchase_bill_task(pk, company_id=company_id)
            job.refresh_from_db()
        else:
            from django.db import transaction as db_transaction
            db_transaction.on_commit(
                lambda: extract_purchase_bill_task.delay(pk, company_id=company_id)
            )
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
        rows, meta = _read_structured_bill(raw, filename)
        if not rows:
            raise BusinessRuleError("The file has no data rows.")

        for key, value in _csv_header_money(rows).items():
            meta.setdefault(key, value)
        raw_lines = [_map_structured_row(row) for row in rows]
        preview_lines, errors, rate_warnings = BillImportService._build_preview_lines(raw_lines)
        answers = _infer_qty_answers(preview_lines, tolerance=Decimal("0.50")) or {}
        if not answers.get("qty_formula"):
            from imports.qty_formula import _union_keys
            keys = _union_keys(preview_lines)
            if "cs" in keys and "upc" in keys:
                answers = {"qty_formula": "cs*upc+quantity"}
            elif "cs" in keys and "quantity" in keys:
                answers = {"qty_formula": "cs+quantity"}
        formula_key = _apply_cross_check(
            preview_lines, answers, tolerance=Decimal("0.50"), reconcile_print=False
        )
        errors = _refresh_line_validity(preview_lines)
        preview = {
            "supplier_name": meta.get("supplier_name") or "",
            "supplier_gstin": meta.get("supplier_gstin") or "",
            "buyer_name": meta.get("buyer_name") or "",
            "buyer_gstin": meta.get("buyer_gstin") or "",
            "bill_number": meta.get("bill_number") or "",
            "bill_date": meta.get("bill_date") or "",
            **({"additional_charges": str(meta["freight"])} if meta.get("freight") else {}),
            **({"invoice_discount": str(meta["invoice_discount"])} if meta.get("invoice_discount") else {}),
            "extraction_confidence": 1.0,
            "low_confidence_accepted": True,
            "column_headers": list(rows[0].keys()) if rows else [],
            "printed_line_count": len(preview_lines),
            "resolved_formula": formula_key,
            # B3-003: apply_extraction (the LLM path) sets resolved_answers so
            # _save_bill_template can round-trip a non-enum qty_formula (e.g.
            # "cs+quantity") into column_mapping["qty_formula"]. This
            # structured path computed `answers` above but never surfaced it,
            # so formula_enum() silently downgraded anything but the two
            # hard-coded formulas to SIMPLE and the learned template lost the
            # inference -- corrupting quantities on every later bill from the
            # same GSTIN via the LLM path's _template_answers() fallback.
            "resolved_answers": answers,
            "lines": preview_lines,
        }
        if rate_warnings:
            preview["warnings"] = rate_warnings
        # B3-021: run the GSTIN-based purchase/sales direction sanity check on
        # the structured path too (it was only wired into the LLM path).
        direction_warning = _infer_direction_warning(
            job.kind,
            {
                "supplier_gstin": preview.get("supplier_gstin"),
                "buyer_gstin": preview.get("buyer_gstin"),
            },
            job.company,
        )
        if direction_warning:
            preview["direction_warning"] = direction_warning
        BillImportService._guard_line_limit(preview_lines)
        BillImportService.finalize_preview_lines(preview, preview_lines)
        BillImportService.enrich_preview(job, preview)
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
    def _guard_line_limit(lines: list[dict]) -> None:
        if len(lines) > BILL_PREVIEW_MAX_LINES:
            raise BusinessRuleError(
                f"This bill has {len(lines)} lines; the maximum is {BILL_PREVIEW_MAX_LINES}. "
                "Split the file and upload it in parts."
            )

    @staticmethod
    def _build_preview_lines(raw_lines: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
        # B3-016: the rate_warnings list used to be built and thrown away —
        # return it so callers can surface it as preview["warnings"], the same
        # way the LLM path already does.
        preview_lines, errors = [], []
        rate_warnings: list[str] = []
        for index, raw_line in enumerate(raw_lines, start=1):
            line = _preview_bill_line(raw_line, index=index, rate_warnings=rate_warnings)
            if line.get("include"):
                line_errors = _bill_line_errors(line)
                if line_errors:
                    errors.append({"row": index, "errors": line_errors, "data": line})
                    line["include"] = False
                    line["excluded_reason"] = "; ".join(line_errors)
            preview_lines.append(line)
        return preview_lines, errors, rate_warnings

    @staticmethod
    def apply_extraction(job: ImportJob, payload: dict):
        # A cancel that landed while the AI call was running must stick.
        if ImportJob.objects.filter(pk=job.pk, status=ImportJob.Status.CANCELLED).exists():
            job.status = ImportJob.Status.CANCELLED
            return job
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
        template = _match_bill_template(job.company, template_gstin, column_headers, job.kind)

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
        # 24.1: header charges / discount / tax-mode hint read off the bill.
        for key in ("freight", "invoice_discount"):
            if str(payload.get(key) or "").strip():
                # OCR text like "Rs. 1,200" must not reach commit as an unparseable string.
                found = re.search(r"\d[\d,]*(?:\.\d+)?", str(payload[key]))
                if found is None:
                    continue
                try:
                    amount = _as_decimal(found.group(0).replace(",", ""))
                except BusinessRuleError:
                    continue
                if amount > 0:
                    preview["additional_charges" if key == "freight" else key] = str(amount)
        if str(payload.get("price_mode_hint") or "").upper() == "INCLUSIVE":
            preview["price_mode"] = "INCLUSIVE"

        # Row positions are fractions of ONE picture. A PDF is rasterised page by page and the
        # viewer shows the PDF itself, so a position there would point at the wrong place.
        file_name = (getattr(job.file, "original_name", "") or "").lower()
        file_type = (getattr(job.file, "content_type", "") or "").lower()
        if file_type == "application/pdf" or file_name.endswith(".pdf"):
            for raw in raw_lines:
                if isinstance(raw, dict):
                    raw.pop("bbox", None)
        preview_lines, errors, rate_warnings = BillImportService._build_preview_lines(raw_lines)
        if rate_warnings:
            preview["warnings"] = rate_warnings
        if payload.get("injection_flagged"):
            # SR-21 / D14: instruction-like text was detected in the bill and
            # removed upstream. Force the preview low-confidence and warn so a
            # human re-checks every value before committing.
            warnings = list(preview.get("warnings") or [])
            warnings.append(
                "Suspicious instruction-like text was detected in this bill and removed. "
                "Verify the supplier, GSTIN, bill number and every line before committing."
            )
            preview["warnings"] = warnings
            preview["injection_flagged"] = True
            preview["extraction_confidence"] = 0.0
            preview["low_confidence_accepted"] = False
        if _skip_simple_qty_template(template, preview_lines):
            template = None
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

        BillImportService._guard_line_limit(preview["lines"])
        BillImportService.finalize_preview_lines(preview, preview["lines"])
        BillImportService.enrich_preview(job, preview)
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
        # B3-019: an answer must be one of the options offered for that
        # clarification — a bogus value otherwise flows into the qty formula.
        options_by_field = {
            item.get("field"): {
                str(o.get("value"))
                for o in (item.get("options") or [])
                if isinstance(o, dict)
            }
            for item in clarifications
        }
        resolved_answers = {}
        for k, v in answers.items():
            if v in (None, ""):
                continue
            allowed = options_by_field.get(k)
            if allowed and str(v) not in allowed:
                raise BusinessRuleError(
                    f"'{v}' is not a valid answer for clarification '{k}'."
                )
            resolved_answers[k] = v
        for item in clarifications:
            field = item.get("field")
            if field in answers and str(answers[field]) in (
                options_by_field.get(field) or {str(answers[field])}
            ):
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
        BillImportService.finalize_preview_lines(preview, preview_lines)
        BillImportService.enrich_preview(job, preview)

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
        from imports import metrics

        # A user cancel (or a finished commit) wins over a late extraction failure.
        current = ImportJob.objects.filter(pk=job.pk).values_list("status", flat=True).first()
        if current in (
            ImportJob.Status.CANCELLED, ImportJob.Status.COMMITTED, ImportJob.Status.VOIDED,
        ):
            job.status = current
            return job
        metrics.record_failure(job, reason)
        job.status = ImportJob.Status.FAILED
        job.failure_reason = (reason or "Extraction failed.")[:2000]
        job.save(update_fields=["status", "failure_reason", "updated_at"])
        return job

    @staticmethod
    @transaction.atomic
    def update_preview(job: ImportJob, data: dict, user=None, *, strict_included: bool = False):
        """Edit the extracted bill (header, party, lines) before commit.

        Lines are *merged by `line_id`* (UPLOAD_SALES_BILL_REVIEW 23.1): stored
        lines the client did not send are kept, `deleted: true` removes one, and
        `is_new: true` appends one. A legacy full-array payload (no ids) is
        mapped by position and only accepted when its length matches. Included
        lines with problems are NOT silently unchecked any more; their
        structured errors are stored on the line and enforced at commit.
        `strict_included` is accepted for API symmetry: the strict gate lives
        in `BillImportService.commit`, which every caller goes through.
        """
        from imports import bill_validation

        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Preview update is only for bill imports.")
        # Lock the row and re-read it: the version check below is only a real
        # guard if two concurrent autosaves cannot both pass it.
        ImportJob.objects.select_for_update().filter(pk=job.pk).first()
        job.refresh_from_db()
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Only previewed bill jobs can be edited.")

        preview = dict(job.preview or {})
        if not isinstance(preview, dict):
            preview = {"lines": []}
        stored = [dict(ln) for ln in (preview.get("lines") or []) if isinstance(ln, dict)]
        BillImportService.finalize_preview_lines(preview, stored, bump=False)

        version_in = data.get("preview_version")
        if version_in not in (None, ""):
            try:
                version_in = int(version_in)
            except (TypeError, ValueError):
                raise BusinessRuleError("preview_version must be a number.")
            if version_in != int(preview.get("preview_version") or 1):
                raise StalePreviewError(
                    "This bill was changed elsewhere since you opened it. Reload to continue."
                )

        text_fields = (
            "supplier_name", "customer_name", "buyer_name", "bill_number", "bill_date",
        )
        for field in text_fields:
            if field in data:
                preview[field] = str(data.get(field) or "").strip()
        if "supplier_gstin" in data:
            preview["supplier_gstin"] = str(data.get("supplier_gstin") or "").strip()
        # B3-024: _resolve_customer (SALES_BILL commit) and the direction-
        # warning / import-company-GSTIN checks all key off buyer_gstin /
        # buyer_name specifically.
        if "buyer_gstin" in data:
            preview["buyer_gstin"] = str(data.get("buyer_gstin") or "").strip().upper()
        for field in ("low_confidence_accepted", "confirm_duplicate", "confirm_new_products"):
            if field in data:
                preview[field] = bool(data.get(field))
        if "confirm_non_gst" in data or "confirmNonGst" in data:
            # CR-041 / CR-137: operator opts into NON_GST when all lines are 0-rated.
            val = data.get("confirm_non_gst") if "confirm_non_gst" in data else data.get("confirmNonGst")
            preview["confirm_non_gst"] = bool(val)
        if "price_mode" in data:
            mode = str(data.get("price_mode") or "EXCLUSIVE").strip().upper()
            if mode not in ("EXCLUSIVE", "INCLUSIVE"):
                raise BusinessRuleError("price_mode must be EXCLUSIVE or INCLUSIVE.")
            preview["price_mode"] = mode
        for money in ("additional_charges", "invoice_discount", "printed_total"):
            if money in data:
                raw = data.get(money)
                if raw in (None, ""):
                    preview.pop(money, None)
                else:
                    value = _as_decimal(raw)
                    if value < 0:
                        raise BusinessRuleError(f"{money.replace('_', ' ').capitalize()} cannot be negative.")
                    preview[money] = str(value)
        if "company_gstin_id" in data:
            raw = data.get("company_gstin_id")
            if raw in (None, ""):
                preview.pop("company_gstin_id", None)
            else:
                if not CompanyGstin.objects.filter(pk=raw, company=job.company, is_active=True).exists():
                    raise BusinessRuleError("Invalid company GSTIN.")
                preview["company_gstin_id"] = int(raw)

        if "lines" in data:
            lines_in = data.get("lines") or []
            if not isinstance(lines_in, list):
                raise BusinessRuleError("lines must be an array.")
            incoming = [ln for ln in lines_in if isinstance(ln, dict)]
            rate_warnings: list[str] = []
            by_id = {int(ln["line_id"]): ln for ln in stored}
            order = [int(ln["line_id"]) for ln in stored]
            deleted: set[int] = set()
            appended: list[dict] = []

            def _merge(base: dict | None, raw: dict, index: int) -> dict:
                merged = {**(base or {}), **{k: v for k, v in raw.items() if k not in ("deleted", "is_new")}}
                # Server-owned review fields must not be treated as bill columns.
                clean = {k: v for k, v in merged.items() if k not in _CARRY_LINE_KEYS and k not in ("errors",)}
                line = _preview_bill_line(clean, index=index, rate_warnings=rate_warnings)
                if base is not None and any(
                    str(line.get(f) or "") != str(base.get(f) or "")
                    for f in ("name", "sku", "hsn_code", "quantity", "unit_price", "gst_rate", "mrp", "discount_percent")
                ):
                    merged["edited"] = True
                for key in _CARRY_LINE_KEYS:
                    if key in merged and key not in line:
                        line[key] = merged[key]
                if "include" in raw:
                    line["include"] = bool(raw.get("include"))
                if "product_id" in raw:
                    line["product_id"] = raw.get("product_id") or None
                if "create_new" in raw:
                    line["create_new"] = bool(raw.get("create_new"))
                if base is not None and base.get("line_id"):
                    line["line_id"] = base["line_id"]
                return line

            has_ids = any(ln.get("line_id") not in (None, "") for ln in incoming)
            has_new = any(ln.get("is_new") for ln in incoming)
            if not has_ids and not has_new:
                # Legacy full-array payload: positional, same length only.
                if len(incoming) != len(stored):
                    raise StalePreviewError(
                        "This bill has a different number of lines than your copy. Reload to continue."
                    )
                for index, (lid, raw) in enumerate(zip(order, incoming), start=1):
                    by_id[lid] = _merge(by_id[lid], raw, index)
            else:
                for raw in incoming:
                    lid_raw = raw.get("line_id")
                    if lid_raw in (None, ""):
                        if raw.get("deleted"):
                            continue
                        appended.append(_merge(None, raw, len(order) + len(appended) + 1))
                        continue
                    try:
                        lid = int(lid_raw)
                    except (TypeError, ValueError):
                        raise BusinessRuleError("line_id must be a number.")
                    if lid not in by_id:
                        raise StalePreviewError(
                            "A line you edited no longer exists. Reload to continue."
                        )
                    if raw.get("deleted"):
                        deleted.add(lid)
                        continue
                    by_id[lid] = _merge(by_id[lid], raw, order.index(lid) + 1)
            merged_lines = [by_id[lid] for lid in order if lid not in deleted] + appended
            BillImportService._guard_line_limit(merged_lines)
            BillImportService.finalize_preview_lines(preview, merged_lines, bump=False)
            errors = []
            for index, line in enumerate(merged_lines, start=1):
                structured = bill_validation.line_errors(line, kind=job.kind) if line.get("include") else []
                line["errors"] = structured
                if structured:
                    errors.append({
                        "row": index,
                        "errors": [e["message"] for e in structured],
                        "data": {k: v for k, v in line.items() if k != "errors"},
                    })
            preview["lines"] = merged_lines
            if rate_warnings:
                preview["warnings"] = rate_warnings
            else:
                preview.pop("warnings", None)
            job.errors = errors
            job.total_rows = len(merged_lines)
            job.valid_rows = len([ln for ln in merged_lines if ln.get("include") and not ln.get("errors")])
            job.error_rows = len(errors)

        supplier_id = data.get("supplier_id", data.get("supplier"))
        if "supplier_id" in data or "supplier" in data:
            if supplier_id in (None, ""):
                job.supplier = None
            else:
                try:
                    job.supplier = Supplier.objects.get(pk=supplier_id, company=job.company)
                except (Supplier.DoesNotExist, ValueError, TypeError):
                    raise BusinessRuleError("Invalid supplier.")

        customer_id = data.get("customer_id", data.get("customer"))
        if "customer_id" in data or "customer" in data:
            if customer_id in (None, ""):
                job.customer = None
            else:
                try:
                    job.customer = Customer.objects.get(pk=customer_id, company=job.company)
                except (Customer.DoesNotExist, ValueError, TypeError):
                    raise BusinessRuleError("Invalid customer.")

        BillImportService.finalize_preview_lines(preview, preview.get("lines") or [], bump=True)
        BillImportService.enrich_preview(job, preview)
        job.preview = preview
        if user is not None:
            job.updated_by = user
        job.save()
        return job

    @staticmethod
    def _match_or_create_product(
        company, line: dict, user, *, direction: str = "PURCHASE", catalog: dict | None = None
    ) -> tuple[Product, bool]:
        # A product the reviewer picked (or confirmed) wins over any matching.
        chosen = line.get("product_id")
        product = None
        if chosen not in (None, ""):
            product = Product.objects.filter(pk=chosen, company=company).first()
            if product is None:
                raise BusinessRuleError("The product chosen for a line no longer exists.")
        sku = str(line.get("sku") or "").strip()
        name = str(line.get("name") or "").strip()
        if product is None and sku:
            product = Product.objects.filter(company=company).filter(
                Q(sku__iexact=sku) | Q(barcode__iexact=sku)
            ).first()
        if product is None and name:
            product = Product.objects.filter(company=company, name__iexact=name).first()
        if product is None and catalog is not None:
            # The review screen showed the reviewer the normalised-name match
            # (legal suffixes, punctuation ignored); commit must bind to that
            # same product instead of creating a duplicate of it.
            from imports import party_match

            found = party_match.match_product(line, catalog)
            if found.get("status") == "matched":
                product = Product.objects.filter(pk=found["product_id"], company=company).first()

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
                # Owner decision (2026-10-12): products first seen on a sales bill are stock-
                # tracked from the start, like any item. They have no stock yet, so Complete
                # can be blocked until stock is received (flagged needs_review). A deployment
                # can switch this off with BILL_IMPORT_SALES_PRODUCTS_TRACK_INVENTORY=False.
                track_inventory=(
                    direction == "PURCHASE"
                    or bool(getattr(settings, "BILL_IMPORT_SALES_PRODUCTS_TRACK_INVENTORY", True))
                ),
                # No cost/stock yet: surface it for review (23.11).
                needs_review=True,
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
        from imports import party_match

        if job.supplier_id:
            return job.supplier
        preview = job.preview if isinstance(job.preview, dict) else {}
        gstin = str(preview.get("supplier_gstin") or "").strip()
        name = party_match.sanitize_party_name(preview.get("supplier_name") or "")
        match = party_match.match_supplier(job.company, gstin=gstin, name=name)
        supplier = None
        if match["status"] == "conflict":
            raise BusinessRuleError(
                "The supplier GSTIN and name on the bill match two different suppliers. "
                "Select the right supplier before creating the draft.",
                code="PARTY_CONFLICT",
            )
        if match["status"] == "inactive_match":
            raise BusinessRuleError(
                "; ".join(match["notes"]) or "That supplier is inactive.",
                code="PARTY_INACTIVE",
            )
        if match["status"] == "matched":
            supplier = Supplier.objects.get(pk=match["id"])
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
            job.created_supplier_id = supplier.pk
        job.supplier = supplier
        job.save(update_fields=["supplier", "created_supplier_id", "updated_at"])
        return supplier

    @staticmethod
    def _resolve_customer(job: ImportJob, user) -> Customer:
        from imports import party_match

        if job.customer_id:
            return job.customer
        preview = job.preview if isinstance(job.preview, dict) else {}
        gstin = str(preview.get("buyer_gstin") or "").strip().upper()
        name = party_match.sanitize_party_name(
            str(preview.get("customer_name") or "").strip()
            or str(preview.get("buyer_name") or "").strip()
        )
        match = party_match.match_customer(job.company, gstin=gstin, name=name)
        customer = None
        if match["status"] == "conflict":
            raise BusinessRuleError(
                "The customer GSTIN and name on the bill match two different customers. "
                "Select the right customer before creating the draft.",
                code="PARTY_CONFLICT",
            )
        if match["status"] == "inactive_match":
            raise BusinessRuleError(
                "; ".join(match["notes"]) or "That customer is inactive or blocked.",
                code="PARTY_INACTIVE",
            )
        if match["status"] == "matched":
            customer = Customer.objects.get(pk=match["id"])
        if customer is None:
            if not name:
                raise BusinessRuleError("Select a customer before committing the sales bill.")
            customer = create_customer(
                company=job.company,
                user=user,
                name=name,
                gstin=gstin if gstin and GSTIN_RE.match(gstin) else "",
            )
            job.created_customer_id = customer.pk
        job.customer = customer
        job.save(update_fields=["customer", "created_customer_id", "updated_at"])
        return customer

    @staticmethod
    def _save_bill_template(job: ImportJob, preview: dict, user):
        """Persist the confirmed column mapping / formula as this vendor's
        SupplierBillTemplate (§4.4) — learned once, applied silently on every
        later bill from the same GSTIN."""
        gstin = str(preview.get("supplier_gstin") or "").strip()
        if not gstin or not GSTIN_RE.match(gstin):
            return
        # A bill uploaded on the wrong screen must not teach the wrong
        # direction's template (23.6).
        if preview.get("direction_warning"):
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
            kind=job.kind,
            gstin=gstin,
            signature_hash=_signature_hash(column_headers),
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
    def _parse_bill_date(value: str, *, required: bool = True):
        value = (value or "").strip()
        if not value:
            if required:
                raise BusinessRuleError(
                    "Bill date is missing or could not be parsed. Set bill date before committing."
                )
            return timezone.localdate()
        # B3-011: tolerate an ISO datetime ("2026-03-15 00:00:00" / "...T00:00:00")
        # that slipped through from an Excel date cell.
        value = value.replace("T", " ").split(" ", 1)[0].strip()
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
        """CR-042: Bill commit is all-or-nothing in one atomic transaction.

        Order matters (24.2): validate the header and *every* included line
        first -- no master data is created until the whole bill is known to be
        committable. Any error aborts the transaction, leaving no partial
        drafts. Re-commit is guarded by PREVIEWED -> COMMITTED.
        """
        from imports import bill_validation, metrics

        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Not a bill import.")
        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if job.status != ImportJob.Status.PREVIEWED:
            raise BusinessRuleError("Import must be previewed before commit.")

        preview = job.preview if isinstance(job.preview, dict) else {}
        all_lines = list(preview.get("lines") or [])
        try:
            bill_validation.raise_if_invalid(job, preview, all_lines, user=user)
        except BusinessRuleError as exc:
            metrics.record_rejection(job, exc)
            raise
        lines = [ln for ln in all_lines if ln.get("include")]

        if job.kind == ImportJob.Kind.SALES_BILL:
            result = BillImportService._commit_sales(job, preview, lines, user)
        else:
            result = BillImportService._commit_purchase(job, preview, lines, user)

        excluded = [
            {"line_id": ln.get("line_id"), "name": ln.get("name"), "reason": ln.get("excluded_reason") or "unchecked"}
            for ln in all_lines
            if not ln.get("include")
        ]
        if excluded:
            AuditService.log(
                company=job.company, user=user, action="IMPORT",
                entity_type="ImportJob", entity_id=job.pk,
                description=f"{len(excluded)} bill line(s) were left out of the draft",
                metadata={
                    "event": "IMPORT_SYSTEM_EXCLUDED",
                    "excluded_lines": excluded[:100], "excluded_count": len(excluded),
                },
            )
        below = [ln.get("line_id") for ln in lines if ln.get("below_price_list")]
        if below:
            AuditService.log(
                company=job.company, user=user, action="IMPORT",
                entity_type="ImportJob", entity_id=job.pk,
                description=f"{len(below)} line(s) kept below the customer's price list",
                metadata={"event": "IMPORT_PRICE_BELOW_LIST", "line_ids": below},
            )
        if job.created_product_ids or job.created_customer_id or job.created_supplier_id:
            AuditService.log(
                company=job.company, user=user, action="IMPORT",
                entity_type="ImportJob", entity_id=job.pk,
                description="Master data created from a bill import",
                metadata={
                    "event": "IMPORT_ENTITIES_CREATED",
                    "product_ids": list(job.created_product_ids or []),
                    "customer_id": job.created_customer_id,
                    "supplier_id": job.created_supplier_id,
                },
            )
        metrics.record_commit(job, all_lines, lines, excluded)

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
    def _infer_supplier_rcm(supplier) -> bool:
        """B3-028: mirror PurchaseService._unregistered_rcm_gate -- an
        UNREGISTERED supplier, or a blank GSTIN with no explicit
        regular/composition classification, is an RCM purchase."""
        taxpayer = (getattr(supplier, "taxpayer_type", "") or "")
        blank_gstin = not (getattr(supplier, "gstin", "") or "").strip()
        registered = taxpayer in (
            Customer.TaxpayerType.REGULAR,
            Customer.TaxpayerType.COMPOSITION,
        )
        return taxpayer == Customer.TaxpayerType.UNREGISTERED or (
            blank_gstin and not registered
        )

    @staticmethod
    def _line_items(job: ImportJob, lines: list[dict], user, *, direction: str, noun: str):
        """Resolve products and build `items_data` (shared by both directions).

        Returns (items_data, products_created_ids, rate_warnings).
        """
        items_data = []
        created_ids: list[int] = []
        # B3-025: surface any commit-time rate snap on the created document.
        rate_warnings: list[str] = []
        inclusive = str((job.preview or {}).get("price_mode") or "").upper() == "INCLUSIVE"
        from imports import party_match

        catalog = party_match.build_catalog(job.company)
        for idx, line in enumerate(lines, start=1):
            if line.get("quantity") in (None, ""):
                raise BusinessRuleError(f"Quantity is required for each imported {noun} line.")
            if line.get("gst_rate") in (None, ""):
                raise BusinessRuleError(f"GST rate is required for each imported {noun} line.")
            product, created = BillImportService._match_or_create_product(
                job.company, line, user, direction=direction, catalog=catalog
            )
            if created:
                created_ids.append(product.pk)
            gst = _normalize_gst_rate(
                line.get("gst_rate"), required=True, warnings=rate_warnings, row=idx,
            )
            unit_price = _as_decimal(line.get("unit_price"), "0")
            item = {
                "product": product,
                "description": product.name,
                "quantity": _as_decimal(line.get("quantity")),
                "unit_price": unit_price,
                "discount_percent": (
                    _as_decimal(line.get("discount_percent"), "0")
                    if line.get("discount_percent") not in (None, "")
                    else Decimal("0")
                ),
                "gst_rate": gst,
            }
            # 23.4: the reviewed HSN / MRP belong on the *line*, even when the
            # product master already has its own (the master is never changed).
            hsn = str(line.get("hsn_code") or "").strip()
            if hsn and HSN_RE.match(hsn):
                item["hsn_code"] = hsn
            mrp = _as_decimal(line.get("mrp"), "0")
            if mrp > 0:
                item["mrp"] = mrp
            if line.get("cess_rate") not in (None, "", "0", "0.00"):
                item["cess_rate"] = _as_decimal(line.get("cess_rate"), "0")
            if line.get("cess_amount") not in (None, "", "0", "0.00"):
                item["cess_amount"] = _as_decimal(line.get("cess_amount"), "0")
            if inclusive and gst:
                # The printed rate already contains GST: keep it as the
                # inclusive price and store the exclusive base on the line.
                # The tax engine (apply_inclusive_prices_to_items) derives the
                # exclusive base -- net of the line discount -- from this.
                item["unit_price_inclusive"] = unit_price
            items_data.append(item)
        return items_data, created_ids, rate_warnings

    @staticmethod
    def _commit_purchase(job: ImportJob, preview: dict, lines: list[dict], user) -> dict:
        supplier = BillImportService._resolve_supplier(job, user)
        infer_rcm = BillImportService._infer_supplier_rcm(supplier)
        items_data, created_ids, rate_warnings = BillImportService._line_items(
            job, lines, user, direction="PURCHASE", noun="purchase"
        )
        products_created = len(created_ids)

        # B3-027 / CR-041: all 0-rated lines default to GST (nil-rated / exempt /
        # composition bills are still GST docs). Flip to NON_GST only when the
        # operator confirms on preview/commit (confirm_non_gst).
        all_zero = bool(items_data) and all(
            Decimal(str(it["gst_rate"] or 0)) == 0 for it in items_data
        )
        confirm_non_gst = bool(preview.get("confirm_non_gst"))
        purchase_type = (
            PurchaseInvoice.PurchaseType.NON_GST
            if all_zero and confirm_non_gst
            else PurchaseInvoice.PurchaseType.GST
        )

        notes = "Created from purchase bill upload"
        if rate_warnings:
            notes += " — " + "; ".join(rate_warnings)
        if purchase_type == PurchaseInvoice.PurchaseType.NON_GST:
            notes += " — all lines 0-rated: booked as non-GST (bill of supply, confirmed)"
        elif all_zero:
            notes += (
                " — all lines 0-rated: kept as GST (nil/exempt). "
                "Set confirm_non_gst on preview to book as NON_GST."
            )
        if infer_rcm:
            notes += " — supplier unregistered / blank GSTIN: reverse charge set, review before Complete"
        purchase_extra = {}
        if preview.get("additional_charges") not in (None, ""):
            purchase_extra["additional_charges"] = _as_decimal(preview.get("additional_charges"), "0")
        if preview.get("invoice_discount") not in (None, ""):
            purchase_extra["invoice_discount"] = _as_decimal(preview.get("invoice_discount"), "0")
        if str(preview.get("price_mode") or "").upper() in ("EXCLUSIVE", "INCLUSIVE"):
            purchase_extra["price_mode"] = str(preview["price_mode"]).upper()
        invoice = PurchaseInvoice.objects.create(
            company=job.company,
            supplier=supplier,
            company_gstin=_resolve_import_company_gstin(job.company, preview, kind=ImportJob.Kind.PURCHASE_BILL),
            purchase_type=purchase_type,
            is_reverse_charge=infer_rcm,
            invoice_date=BillImportService._parse_bill_date(
                str(preview.get("bill_date") or ""),
                required=True,
            ),
            supplier_bill_number=str(preview.get("bill_number") or "")[:64],
            notes=notes,
            attachment=job.file,
            created_by=user,
            updated_by=user,
            **purchase_extra,
        )
        PurchaseService.set_items(invoice, items_data, user)

        job.purchase_invoice = invoice
        job.created_product_ids = created_ids
        AuditService.log(
            company=job.company, user=user, action="IMPORT",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Imported purchase bill → draft purchase #{invoice.pk}",
            metadata={
                "products_created": products_created,
                "created_product_ids": created_ids,
                "lines": len(items_data),
                "purchase_invoice_id": invoice.pk,
                "purchase_type": purchase_type,
                "is_reverse_charge": infer_rcm,
                **({"gst_rate_warnings": rate_warnings} if rate_warnings else {}),
            },
        )
        return {
            "created": len(items_data),
            "products_created": products_created,
            "purchase_invoice_id": invoice.pk,
        }

    @staticmethod
    def _import_role(job: ImportJob, user) -> str:
        from accounts.models import CompanyUser

        cu = CompanyUser.objects.filter(company=job.company, user=user).first()
        return (getattr(cu, "role", "") or "").upper()

    @staticmethod
    def _commit_sales(job: ImportJob, preview: dict, lines: list[dict], user) -> dict:
        customer = BillImportService._resolve_customer(job, user)
        items_data, created_ids, rate_warnings = BillImportService._line_items(
            job, lines, user, direction="SALES", noun="sales"
        )
        products_created = len(created_ids)

        # 23.3: keep the reviewed price. The role gate already ran in
        # validation, so anyone reaching here may preserve below-list prices.
        below_list = []
        for item, line in zip(items_data, lines):
            if line.get("below_price_list"):
                item["price_override_by"] = user
                below_list.append(line.get("line_id") or line.get("name"))

        all_zero = bool(items_data) and all(
            Decimal(str(it["gst_rate"] or 0)) == 0 for it in items_data
        )
        confirm_non_gst = bool(preview.get("confirm_non_gst"))
        invoice_type = (
            SalesInvoice.InvoiceType.NON_GST
            if all_zero and confirm_non_gst
            else SalesInvoice.InvoiceType.GST
        )

        bill_number = str(preview.get("bill_number") or "")[:64]
        notes = f"Created from sales bill upload (bill #{bill_number})"
        if rate_warnings:
            notes += " — " + "; ".join(rate_warnings)
        if invoice_type == SalesInvoice.InvoiceType.NON_GST:
            notes += " — all lines 0-rated: booked as non-GST (bill of supply, confirmed)"

        invoice_date = BillImportService._parse_bill_date(
            str(preview.get("bill_date") or ""),
            required=True,
        )
        # 23.8: a historical bill still has terms; mirror the editor default
        # (customer credit days, else the standard terms) instead of "due now".
        terms_days = int(customer.credit_days or 0) or int(
            getattr(settings, "BILL_IMPORT_DEFAULT_PAYMENT_TERMS_DAYS", 30) or 0
        )
        extra_fields = {}
        if preview.get("additional_charges") not in (None, ""):
            extra_fields["additional_charges"] = _as_decimal(preview.get("additional_charges"), "0")
        if preview.get("invoice_discount") not in (None, ""):
            extra_fields["invoice_discount"] = _as_decimal(preview.get("invoice_discount"), "0")
        price_mode = str(preview.get("price_mode") or "").upper()
        if price_mode in ("EXCLUSIVE", "INCLUSIVE"):
            extra_fields["price_mode"] = price_mode
        invoice = SalesInvoice.objects.create(
            company=job.company,
            customer=customer,
            company_gstin=_resolve_import_company_gstin(job.company, preview, kind=ImportJob.Kind.SALES_BILL),
            invoice_type=invoice_type,
            invoice_date=invoice_date,
            payment_terms_days=terms_days,
            due_date=invoice_date + timedelta(days=terms_days),
            notes=notes,
            external_reference=bill_number,
            attachment=job.file,
            created_by=user,
            updated_by=user,
            **extra_fields,
        )
        # The reviewed prices must not be silently re-priced to the customer's
        # price list (23.3); deviations are recorded on the line instead.
        invoice._preserve_requested_prices = True
        invoice._price_role = BillImportService._import_role(job, user)
        SalesService.set_items(invoice, items_data, user)

        job.sales_invoice = invoice
        job.created_product_ids = created_ids
        AuditService.log(
            company=job.company, user=user, action="IMPORT",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Imported sales bill → draft sales invoice #{invoice.pk}",
            metadata={
                "products_created": products_created,
                "created_product_ids": created_ids,
                "created_customer_id": job.created_customer_id,
                "lines": len(items_data),
                "sales_invoice_id": invoice.pk,
                **({"price_below_list_lines": below_list} if below_list else {}),
                **({"gst_rate_warnings": rate_warnings} if rate_warnings else {}),
            },
        )
        return {
            "created": len(items_data),
            "products_created": products_created,
            "sales_invoice_id": invoice.pk,
        }

    # ------------------------------------------------------------------ undo
    @staticmethod
    @transaction.atomic
    def void_bill(job: ImportJob, user) -> ImportJob:
        """Undo a committed bill import while its draft is still a draft (23.14)."""
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Only bill imports can be undone here.")
        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if job.status != ImportJob.Status.COMMITTED:
            raise BusinessRuleError("Only a committed bill import can be undone.")
        if job.kind == ImportJob.Kind.SALES_BILL:
            invoice = job.sales_invoice
            draft = SalesInvoice.Status.DRAFT
        else:
            invoice = job.purchase_invoice
            draft = PurchaseInvoice.Status.DRAFT
        if invoice is not None and invoice.status != draft:
            raise BusinessRuleError(
                "The invoice created from this bill is no longer a draft, so the import "
                "cannot be undone. Cancel the invoice instead."
            )
        archived = {"products": [], "customer": None, "supplier": None, "kept": []}
        if invoice is not None:
            invoice.delete()
        now = timezone.now()
        for product in Product.objects.filter(
            company=job.company, pk__in=list(job.created_product_ids or [])
        ):
            if product.is_referenced():
                archived["kept"].append(product.pk)
                continue
            product.is_deleted = True
            product.deleted_at = now
            product.updated_by = user
            product.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])
            archived["products"].append(product.pk)
        for attr, model, key in (
            ("created_customer_id", Customer, "customer"),
            ("created_supplier_id", Supplier, "supplier"),
        ):
            pk = getattr(job, attr)
            if not pk:
                continue
            party = model.objects.filter(pk=pk, company=job.company).first()
            if party is None:
                continue
            if party.is_referenced():
                archived["kept"].append(f"{key}:{pk}")
                continue
            party.is_deleted = True
            party.deleted_at = now
            party.updated_by = user
            party.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])
            archived[key] = pk
        job.status = ImportJob.Status.VOIDED
        job.failure_reason = f"Undone by user at {now.isoformat()}"
        job.sales_invoice = None
        job.purchase_invoice = None
        job.updated_by = user
        job.save()
        AuditService.log(
            company=job.company, user=user, action="VOID",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Undid bill import #{job.pk}",
            metadata={"event": "IMPORT_VOID", **archived},
        )
        return job

    @staticmethod
    @transaction.atomic
    def cancel(job: ImportJob, user) -> ImportJob:
        """Abandon a bill import that has not been committed (23.9/23.13)."""
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Only bill imports can be cancelled.")
        # A commit finishing between our read and write must not be turned back into CANCELLED.
        ImportJob.objects.select_for_update().filter(pk=job.pk).first()
        job.refresh_from_db()
        if job.status in (
            ImportJob.Status.COMMITTED, ImportJob.Status.VOIDED, ImportJob.Status.CANCELLED,
        ):
            raise BusinessRuleError("This import can no longer be cancelled.")
        job.status = ImportJob.Status.CANCELLED
        job.failure_reason = "Cancelled by user."
        job.updated_by = user
        job.save(update_fields=["status", "failure_reason", "updated_by", "updated_at"])
        return job

    @staticmethod
    @transaction.atomic
    def switch_kind(job: ImportJob, target_kind: str, user) -> ImportJob:
        """Move a mis-uploaded bill to the other direction without re-extracting (23.20)."""
        target_kind = str(target_kind or "").upper()
        if target_kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("kind must be PURCHASE_BILL or SALES_BILL.")
        ImportJob.objects.select_for_update().filter(pk=job.pk).first()
        job.refresh_from_db()
        if job.kind == target_kind:
            return job
        if job.status not in (ImportJob.Status.PREVIEWED, ImportJob.Status.NEEDS_CLARIFICATION):
            raise BusinessRuleError("Only a bill still under review can be switched.")
        preview = dict(job.preview or {})
        # The party printed as "buyer" on a sales bill is the counter-party; on
        # a purchase bill the counter-party is the supplier. Swap the roles.
        if target_kind == ImportJob.Kind.PURCHASE_BILL:
            preview["supplier_name"], preview["buyer_name"] = (
                preview.get("buyer_name") or preview.get("supplier_name") or "",
                preview.get("supplier_name") or "",
            )
            preview["supplier_gstin"], preview["buyer_gstin"] = (
                preview.get("buyer_gstin") or preview.get("supplier_gstin") or "",
                preview.get("supplier_gstin") or "",
            )
        else:
            preview["buyer_name"], preview["supplier_name"] = (
                preview.get("supplier_name") or preview.get("buyer_name") or "",
                preview.get("buyer_name") or "",
            )
            preview["buyer_gstin"], preview["supplier_gstin"] = (
                preview.get("supplier_gstin") or preview.get("buyer_gstin") or "",
                preview.get("buyer_gstin") or "",
            )
        preview.pop("direction_warning", None)
        preview.pop("customer_name", None)
        preview.pop("party_match", None)
        preview.pop("party_match_key", None)
        job.kind = target_kind
        job.customer = None
        job.supplier = None
        warn = _infer_direction_warning(
            target_kind,
            {
                "supplier_gstin": preview.get("supplier_gstin"),
                "buyer_gstin": preview.get("buyer_gstin"),
            },
            job.company,
        )
        if warn:
            preview["direction_warning"] = warn
        for ln in preview.get("lines") or []:
            ln.pop("product_match", None)
            ln.pop("match_key", None)
        BillImportService.finalize_preview_lines(preview, preview.get("lines") or [])
        BillImportService.enrich_preview(job, preview)
        job.preview = preview
        job.updated_by = user
        job.save()
        AuditService.log(
            company=job.company, user=user, action="IMPORT",
            entity_type="ImportJob", entity_id=job.pk,
            description=f"Switched bill import to {target_kind}",
            metadata={"kind": target_kind},
        )
        return job

    @staticmethod
    def validation_report(job: ImportJob, user=None) -> dict:
        """Dry run of commit validation: every problem at once, no writes (23.2)."""
        from imports import bill_validation

        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Validation is only for bill imports.")
        preview = job.preview if isinstance(job.preview, dict) else {}
        lines = list(preview.get("lines") or [])
        included = [(i, ln) for i, ln in enumerate(lines, start=1) if ln.get("include")]
        line_problems = []
        for index, ln in included:
            errs = bill_validation.line_errors(ln, kind=job.kind)
            errs += bill_validation.line_policy_errors(job, ln, user=user)
            if errs:
                line_problems.append(
                    {"row": index, "lineId": ln.get("line_id"), "name": ln.get("name") or "", "errors": errs}
                )
        header = bill_validation.header_errors(job, preview, [ln for _, ln in included])
        header += bill_validation.policy_header_errors(job, preview, [ln for _, ln in included])
        if not included:
            header.append(
                {"field": "lines", "code": "NO_LINES", "severity": "error",
                 "message": "Select at least one valid line to commit."}
            )
        blocking_header = [e for e in header if e["severity"] == "error"]
        return {
            "ok": not line_problems and not blocking_header,
            "headerErrors": header,
            "lineErrors": line_problems,
            "summary": {
                "included": len(included),
                "excluded": len(lines) - len(included),
                "newProducts": preview.get("new_product_count", 0),
                "newParty": bool((preview.get("party_match") or {}).get("will_create")),
            },
            "totals": preview_totals(job, preview),
        }

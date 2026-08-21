"""Tally Excel/CSV migration adapter (Phase 7.0) — not live sync."""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.csv_utils import csv_safe
from core.exceptions import BusinessRuleError
from core.models import FileAsset
from core.services.billing import compute_document_totals
from core.services.files import FileService
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier, Unit

from integrations.models import IntegrationSyncRun

DISCLAIMER = (
    "BizBoard Tally one-shot export dump / CSV migration aid — not live or incremental "
    "Tally sync and not certified Tally parity. Validate totals with your CA after import."
)
OPENING_NOTE = "TALLY_OPENING"
OPENING_SKU = "__TALLY_OPENING__"


def _dec(v, default="0") -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _read_csv_rows(file_bytes: bytes) -> list[dict[str, str]]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BusinessRuleError("CSV has no header row.")
    rows = []
    for raw in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()})
    return rows


def _read_xlsx_rows(file_bytes: bytes) -> list[dict[str, str]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise BusinessRuleError("openpyxl is required for Excel uploads.") from exc
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        raise BusinessRuleError("Excel sheet is empty.")
    keys = [str(h or "").strip().lower() for h in header]
    if not any(keys):
        raise BusinessRuleError("Excel has no header row.")
    out = []
    for raw in rows_iter:
        if raw is None or all(c is None or str(c).strip() == "" for c in raw):
            continue
        row = {}
        for i, key in enumerate(keys):
            if not key:
                continue
            val = raw[i] if i < len(raw) else ""
            row[key] = "" if val is None else str(val).strip()
        out.append(row)
    return out


def _rows_from_upload(file_bytes: bytes, filename: str = "") -> list[dict[str, str]]:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or file_bytes[:2] == b"PK":
        try:
            return _read_xlsx_rows(file_bytes)
        except BusinessRuleError:
            raise
        except Exception:
            # Fall through to CSV if not actually xlsx
            pass
    return _read_csv_rows(file_bytes)


def parse_tally_masters_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    customers, suppliers, products, errors = [], [], [], []
    for i, row in enumerate(rows, start=2):
        et = (row.get("entity_type") or row.get("type") or "").lower()
        name = row.get("name") or ""
        if not et or not name:
            errors.append({"row": i, "error": "entity_type and name required"})
            continue
        if et == "customer":
            customers.append({
                "name": name,
                "phone": row.get("phone") or "",
                "gstin": row.get("gstin") or "",
                "state": row.get("state") or "",
                "opening_outstanding": str(_dec(row.get("opening_outstanding"))),
            })
        elif et == "supplier":
            suppliers.append({
                "name": name,
                "phone": row.get("phone") or "",
                "gstin": row.get("gstin") or "",
                "state": row.get("state") or "",
                "opening_outstanding": str(_dec(row.get("opening_outstanding"))),
            })
        elif et == "product":
            products.append({
                "name": name,
                "sku": row.get("sku") or f"TALLY-{i}",
                "hsn_code": row.get("hsn_code") or row.get("hsn") or "",
                "gst_rate": str(_dec(row.get("gst_rate"), "18")),
                "purchase_price": str(_dec(row.get("purchase_price"))),
                "selling_price": str(_dec(row.get("selling_price"))),
                "reorder_level": str(_dec(row.get("reorder_level"))),
                "opening_qty": str(_dec(row.get("opening_qty"))),
            })
        else:
            errors.append({"row": i, "error": f"Unknown entity_type '{et}'"})
    return {
        "customers": customers,
        "suppliers": suppliers,
        "products": products,
        "errors": errors,
        "counts": {
            "customers": len(customers),
            "suppliers": len(suppliers),
            "products": len(products),
            "errors": len(errors),
        },
        "disclaimer": DISCLAIMER,
    }


def parse_tally_masters_csv(file_bytes: bytes, filename: str = "") -> dict[str, Any]:
    return parse_tally_masters_rows(_rows_from_upload(file_bytes, filename))


def _opening_balance_product(company, user, unit: Unit) -> Product:
    product, _ = Product.objects.get_or_create(
        company=company,
        sku=OPENING_SKU,
        defaults={
            "name": "Tally Opening Balance",
            "gst_rate": Decimal("0"),
            "purchase_price": Decimal("0"),
            "selling_price": Decimal("0"),
            "unit": unit,
            "created_by": user,
        },
    )
    return product


def _create_opening_sales(company, user, customer: Customer, amount: Decimal, product: Product):
    from sales.models import SalesInvoice, SalesItem
    from sales.services import SalesService

    if amount <= 0:
        return None
    if SalesInvoice.objects.filter(
        company=company, customer=customer, notes=OPENING_NOTE, status=SalesInvoice.Status.COMPLETED,
    ).exists():
        return None
    inv = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        status=SalesInvoice.Status.DRAFT,
        invoice_date=timezone.localdate(),
        notes=OPENING_NOTE,
        is_opening_balance=True,
        created_by=user,
        updated_by=user,
    )
    SalesItem.objects.create(
        invoice=inv,
        product=product,
        description="Opening outstanding (Tally migration)",
        quantity=Decimal("1"),
        unit_price=amount,
        discount_percent=Decimal("0"),
        gst_rate=Decimal("0"),
        hsn_code="",
        unit_name="NOS",
    )
    items = list(inv.items.all())
    compute_document_totals(
        inv,
        items,
        tax_enabled=False,
        intra_state=True,
    )
    for it in items:
        it.save()
    inv.save()
    # Seed 1 unit so SALE complete works under BLOCK negative-stock policy.
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("1"),
        reason="Seed stock for TALLY_OPENING AR",
        user=user,
        skip_negative_check=True,
    )
    SalesService.complete(inv, user)
    return inv


def _create_opening_purchase(company, user, supplier: Supplier, amount: Decimal, product: Product):
    from purchases.models import PurchaseInvoice, PurchaseItem
    from purchases.services import PurchaseService

    if amount <= 0:
        return None
    if PurchaseInvoice.objects.filter(
        company=company, supplier=supplier, notes=OPENING_NOTE, status=PurchaseInvoice.Status.COMPLETED,
    ).exists():
        return None
    inv = PurchaseInvoice.objects.create(
        company=company,
        supplier=supplier,
        purchase_type=PurchaseInvoice.PurchaseType.NON_GST,
        status=PurchaseInvoice.Status.DRAFT,
        invoice_date=timezone.localdate(),
        notes=OPENING_NOTE,
        is_opening_balance=True,
        created_by=user,
        updated_by=user,
    )
    PurchaseItem.objects.create(
        invoice=inv,
        product=product,
        description="Opening outstanding (Tally migration)",
        quantity=Decimal("1"),
        unit_price=amount,
        discount_percent=Decimal("0"),
        gst_rate=Decimal("0"),
        hsn_code="",
        unit_name="NOS",
    )
    items = list(inv.items.all())
    compute_document_totals(
        inv,
        items,
        tax_enabled=False,
        intra_state=True,
    )
    for it in items:
        it.save()
    inv.save()
    PurchaseService.complete(inv, user)
    # Neutralize PURCHASE stock increase
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("-1"),
        reason="Neutralize TALLY_OPENING stock",
        user=user,
        skip_negative_check=True,
    )
    return inv


@transaction.atomic
def _reparse_sync_run_file(sync_run: IntegrationSyncRun) -> dict:
    """BB-000346: reopen stored upload bytes as monetary source of truth."""
    if not sync_run.file_id:
        raise BusinessRuleError("Sync run has no uploaded file to re-parse.")
    asset = sync_run.file
    handle = asset.file.open("rb")
    try:
        raw = handle.read()
    finally:
        handle.close()
    filename = asset.original_name or ""
    return parse_tally_masters_csv(raw, filename=filename)


def _apply_name_sku_maps(base: dict, edits: dict | None) -> dict:
    """Allow client to remap party/product names/SKUs only — never openings/qty."""
    if not edits:
        return base
    out = dict(base)
    for key in ("customers", "suppliers", "products"):
        base_rows = list(out.get(key) or [])
        edit_rows = list((edits or {}).get(key) or [])
        for i, row in enumerate(base_rows):
            if i >= len(edit_rows) or not isinstance(edit_rows[i], dict):
                continue
            e = edit_rows[i]
            if e.get("name"):
                row["name"] = str(e["name"])[:200]
            if key == "products":
                if e.get("sku"):
                    row["sku"] = str(e["sku"])[:64]
                if e.get("name"):
                    row["name"] = str(e["name"])[:200]
            # Explicitly keep monetary/qty fields from base (ignore client).
        out[key] = base_rows
    out["errors"] = list(base.get("errors") or [])
    out["disclaimer"] = DISCLAIMER
    out["counts"] = {
        "customers": len(out.get("customers") or []),
        "suppliers": len(out.get("suppliers") or []),
        "products": len(out.get("products") or []),
        "errors": len(out["errors"]),
    }
    return out


def commit_tally_preview(company, user, sync_run: IntegrationSyncRun, *, force: bool = False) -> dict:
    if sync_run.company_id != company.id:
        raise BusinessRuleError("Tenant mismatch.")
    if sync_run.status == IntegrationSyncRun.Status.COMMITTED:
        raise BusinessRuleError("Already committed.")
    # BB-000346: re-parse file; apply name/SKU maps from saved preview only.
    base = _reparse_sync_run_file(sync_run)
    preview = _apply_name_sku_maps(base, sync_run.preview or {})
    sync_run.preview = preview
    sync_run.errors = preview.get("errors") or []
    sync_run.counts = preview.get("counts") or {}
    sync_run.save(update_fields=["preview", "errors", "counts", "updated_at"])

    errors = preview.get("errors") or []
    if errors and not force:
        raise BusinessRuleError("Cannot commit while preview has errors. Clear or ignore them first.")
    if sync_run.status != IntegrationSyncRun.Status.PREVIEWED:
        if not errors:
            sync_run.status = IntegrationSyncRun.Status.PREVIEWED
            sync_run.save(update_fields=["status", "updated_at"])
        else:
            raise BusinessRuleError("Preview must be saved (PREVIEWED) before commit.")

    created = {
        "customers": 0,
        "suppliers": 0,
        "products": 0,
        "stock_movements": 0,
        "opening_ar": 0,
        "opening_ap": 0,
    }
    warnings: list[str] = []

    unit = Unit.objects.filter(company=company).first()
    if unit is None:
        unit = Unit.objects.create(
            company=company, name="NOS", short_name="NOS", uqc_code="NOS", created_by=user,
        )
    opening_product = _opening_balance_product(company, user, unit)

    for row in preview.get("customers") or []:
        cust, was_created = Customer.objects.get_or_create(
            company=company,
            name=row["name"],
            defaults={
                "phone": row.get("phone") or "",
                "gstin": row.get("gstin") or "",
                "state": row.get("state") or company.state or "",
                "created_by": user,
            },
        )
        if was_created:
            created["customers"] += 1
        amt = _dec(row.get("opening_outstanding"))
        if amt > 0 and _create_opening_sales(company, user, cust, amt, opening_product):
            created["opening_ar"] += 1

    for row in preview.get("suppliers") or []:
        sup, was_created = Supplier.objects.get_or_create(
            company=company,
            name=row["name"],
            defaults={
                "phone": row.get("phone") or "",
                "gstin": row.get("gstin") or "",
                "state": row.get("state") or company.state or "",
                "created_by": user,
            },
        )
        if was_created:
            created["suppliers"] += 1
        amt = _dec(row.get("opening_outstanding"))
        if amt > 0 and _create_opening_purchase(company, user, sup, amt, opening_product):
            created["opening_ap"] += 1

    for row in preview.get("products") or []:
        product, was_created = Product.objects.get_or_create(
            company=company,
            sku=row["sku"],
            defaults={
                "name": row["name"],
                "hsn_code": row.get("hsn_code") or "",
                "gst_rate": _dec(row.get("gst_rate"), "18"),
                "purchase_price": _dec(row.get("purchase_price")),
                "selling_price": _dec(row.get("selling_price")),
                "reorder_level": _dec(row.get("reorder_level")),
                "unit": unit,
                "created_by": user,
            },
        )
        if was_created:
            created["products"] += 1
        qty = _dec(row.get("opening_qty"))
        if qty > 0:
            try:
                InventoryService.post_movement(
                    company=company,
                    product=product,
                    movement_type=MovementType.OPENING_STOCK,
                    quantity=qty,
                    unit_cost=_dec(row.get("purchase_price")),
                    user=user,
                )
                created["stock_movements"] += 1
            except BusinessRuleError:
                warnings.append(f"Opening stock skipped for {product.sku} (already recorded).")

    sync_run.status = IntegrationSyncRun.Status.COMMITTED
    sync_run.counts = created
    sync_run.result = {"created": created, "warnings": warnings, "disclaimer": DISCLAIMER}
    sync_run.save()
    return sync_run.result


def update_tally_preview(company, sync_run: IntegrationSyncRun, preview: dict) -> IntegrationSyncRun:
    if sync_run.company_id != company.id:
        raise BusinessRuleError("Tenant mismatch.")
    if sync_run.status == IntegrationSyncRun.Status.COMMITTED:
        raise BusinessRuleError("Cannot edit a committed run.")
    # BB-000346: monetary/qty fields always from re-parsed upload; edits = name/SKU only.
    base = _reparse_sync_run_file(sync_run)
    merged = _apply_name_sku_maps(base, preview or {})
    sync_run.preview = merged
    sync_run.errors = merged.get("errors") or []
    sync_run.counts = merged.get("counts") or {}
    sync_run.status = (
        IntegrationSyncRun.Status.PREVIEWED if not sync_run.errors else IntegrationSyncRun.Status.UPLOADED
    )
    sync_run.save()
    return sync_run


def build_tally_export_csv(company, date_from=None, date_to=None) -> bytes:
    """Export sales register as Tally-friendly voucher CSV aid."""
    from sales.models import SalesInvoice

    qs = SalesInvoice.objects.filter(
        company=company,
        status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
    ).exclude(notes=OPENING_NOTE).select_related("customer").order_by("invoice_date", "id")
    if date_from:
        qs = qs.filter(invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice_date__lte=date_to)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "voucher_type", "date", "voucher_number", "party_name", "party_gstin",
        "taxable", "cgst", "sgst", "igst", "grand_total", "disclaimer",
    ])
    for inv in qs[:5000]:
        writer.writerow([
            csv_safe("Sales"),
            csv_safe(inv.invoice_date.isoformat() if inv.invoice_date else ""),
            csv_safe(inv.number or ""),
            csv_safe(inv.customer.name if inv.customer_id else ""),
            csv_safe((inv.filing_party_gstin or (inv.customer.gstin if inv.customer_id else "")) or ""),
            csv_safe(str(inv.taxable_total)),
            csv_safe(str(inv.cgst_total)),
            csv_safe(str(inv.sgst_total)),
            csv_safe(str(inv.igst_total)),
            csv_safe(str(inv.grand_total)),
            csv_safe(DISCLAIMER),
        ])
    return buf.getvalue().encode("utf-8")


def create_upload_run(company, user, uploaded_file) -> IntegrationSyncRun:
    asset = FileService.store_upload(
        company=company,
        uploaded_file=uploaded_file,
        kind=FileAsset.Kind.IMPORT,
        user=user,
    )
    raw = asset.file.read()
    if hasattr(asset.file, "seek"):
        asset.file.seek(0)
    filename = getattr(uploaded_file, "name", "") or asset.original_name or ""
    preview = parse_tally_masters_csv(raw, filename=filename)
    run = IntegrationSyncRun.objects.create(
        company=company,
        kind=IntegrationSyncRun.Kind.TALLY_IMPORT,
        status=(
            IntegrationSyncRun.Status.PREVIEWED
            if not preview["errors"]
            else IntegrationSyncRun.Status.UPLOADED
        ),
        file=asset,
        preview=preview,
        errors=preview.get("errors") or [],
        counts=preview.get("counts") or {},
        created_by=user,
    )
    return run


def _xml_escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def post_tally_xml(url: str, xml_body: str, *, timeout: int = 30) -> dict[str, Any]:
    """POST XML to Tally HTTP gateway — patch ``requests.post`` in tests."""
    import requests

    if not url:
        raise BusinessRuleError("Tally URL is not configured.")
    resp = requests.post(
        url,
        data=xml_body.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=timeout,
    )
    return {
        "status_code": resp.status_code,
        "body": resp.text,
        "ok": resp.ok,
    }


def _masters_xml(company) -> str:
    customer_names = Customer.objects.filter(company=company).order_by("name").values_list("name", flat=True)[:500]
    supplier_names = Supplier.objects.filter(company=company).order_by("name").values_list("name", flat=True)[:500]
    product_names = Product.objects.filter(company=company).order_by("name").values_list("name", flat=True)[:500]
    parts = [
        "<ENVELOPE>",
        "<HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>"
        "<TYPE>Data</TYPE><ID>All Masters</ID></HEADER>",
        "<BODY><DESC></DESC><DATA><TALLYMESSAGE>",
    ]
    for name in customer_names:
        parts.append(
            f"<LEDGER NAME=\"{_xml_escape(name)}\" RESERVEDNAME=\"\">"
            f"<PARENT>Sundry Debtors</PARENT></LEDGER>"
        )
    for name in supplier_names:
        parts.append(
            f"<LEDGER NAME=\"{_xml_escape(name)}\" RESERVEDNAME=\"\">"
            f"<PARENT>Sundry Creditors</PARENT></LEDGER>"
        )
    for name in product_names:
        parts.append(
            f"<STOCKITEM NAME=\"{_xml_escape(name)}\" RESERVEDNAME=\"\">"
            f"<BASEUNITS>NOS</BASEUNITS></STOCKITEM>"
        )
    parts.extend(["</TALLYMESSAGE></DATA></BODY></ENVELOPE>"])
    return "".join(parts)


def _vouchers_xml(company, date_from=None, date_to=None) -> str:
    from sales.models import SalesInvoice

    qs = SalesInvoice.objects.filter(
        company=company,
        status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
    ).exclude(notes=OPENING_NOTE).order_by("invoice_date", "id")
    if date_from:
        qs = qs.filter(invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice_date__lte=date_to)
    rows = qs.values("invoice_date", "number", "grand_total", "customer__name")[:5000]
    parts = [
        "<ENVELOPE>",
        "<HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>"
        "<TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>",
        "<BODY><DESC></DESC><DATA><TALLYMESSAGE>",
    ]
    for row in rows:
        inv_date = row["invoice_date"]
        parts.append(
            f"<VOUCHER VCHTYPE=\"Sales\" ACTION=\"Create\">"
            f"<DATE>{inv_date.isoformat() if inv_date else ''}</DATE>"
            f"<VOUCHERNUMBER>{_xml_escape(row.get('number') or '')}</VOUCHERNUMBER>"
            f"<PARTYLEDGERNAME>{_xml_escape(row.get('customer__name') or '')}</PARTYLEDGERNAME>"
            f"<AMOUNT>{row['grand_total']}</AMOUNT>"
            f"</VOUCHER>"
        )
    parts.extend(["</TALLYMESSAGE></DATA></BODY></ENVELOPE>"])
    return "".join(parts)


def push_masters_http(company, base_url: str | None = None) -> dict[str, Any]:
    """One-shot Tally master XML dump (not live sync)."""
    from django.conf import settings

    url = (base_url or getattr(settings, "TALLY_URL", "") or "").strip()
    xml_body = _masters_xml(company)
    result = post_tally_xml(url, xml_body)
    result["disclaimer"] = DISCLAIMER
    result["kind"] = "masters"
    result["mode"] = "export_dump"
    result["sync"] = False
    return result


def push_vouchers_http(company, base_url: str | None = None, *, date_from=None, date_to=None) -> dict[str, Any]:
    """One-shot Tally sales-voucher XML dump (not live sync)."""
    from django.conf import settings

    url = (base_url or getattr(settings, "TALLY_URL", "") or "").strip()
    xml_body = _vouchers_xml(company, date_from=date_from, date_to=date_to)
    result = post_tally_xml(url, xml_body)
    result["disclaimer"] = DISCLAIMER
    result["kind"] = "vouchers"
    result["mode"] = "export_dump"
    result["sync"] = False
    return result

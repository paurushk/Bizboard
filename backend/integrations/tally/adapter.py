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
    "BizBoard Tally one-shot export dump / CSV migration aid — not a live Tally "
    "connection and not certified Tally parity. Validate totals with your CA after import."
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
    try:
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
    finally:
        wb.close()


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
    records = len(rows)
    warning_rows = [
        r for r in customers + suppliers + products
        if _dec(r.get("opening_outstanding") or r.get("opening_qty")) < 0
    ]
    summary = {
        "records": records,
        "valid": len(customers) + len(suppliers) + len(products),
        "warnings": len(warning_rows),
        "errors": len(errors),
    }
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
        "summary": summary,
        "disclaimer": DISCLAIMER,
    }


def parse_tally_masters_csv(file_bytes: bytes, filename: str = "") -> dict[str, Any]:
    return parse_tally_masters_rows(_rows_from_upload(file_bytes, filename))


def _post_commit_recon(company, preview: dict, created: dict) -> dict:
    """Pass/fail opening stock, AR, AP vs the committed preview totals."""
    from django.db.models import Sum

    from inventory.models import StockBalance
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    expected_ar = sum(
        (_dec(r.get("opening_outstanding")) for r in (preview.get("customers") or [])),
        Decimal("0"),
    )
    expected_ap = sum(
        (_dec(r.get("opening_outstanding")) for r in (preview.get("suppliers") or [])),
        Decimal("0"),
    )
    preview_products = [
        r
        for r in (preview.get("products") or [])
        if r.get("sku") and _dec(r.get("opening_qty")) > 0
    ]
    expected_qty = sum((_dec(r.get("opening_qty")) for r in preview_products), Decimal("0"))
    cust_names = [r.get("name") for r in (preview.get("customers") or []) if r.get("name")]
    sup_names = [r.get("name") for r in (preview.get("suppliers") or []) if r.get("name")]
    books_ar = (
        SalesInvoice.objects.filter(
            company=company,
            is_opening_balance=True,
            customer__name__in=cust_names,
            status=SalesInvoice.Status.COMPLETED,
        ).aggregate(s=Sum("grand_total"))["s"]
        or Decimal("0")
    ) if cust_names else Decimal("0")
    books_ap = (
        PurchaseInvoice.objects.filter(
            company=company,
            is_opening_balance=True,
            supplier__name__in=sup_names,
            status=PurchaseInvoice.Status.COMPLETED,
        ).aggregate(s=Sum("grand_total"))["s"]
        or Decimal("0")
    ) if sup_names else Decimal("0")
    opening_invoices = SalesInvoice.objects.filter(
        company=company, is_opening_balance=True
    ).count()
    opening_bills = PurchaseInvoice.objects.filter(
        company=company, is_opening_balance=True
    ).count()
    preview_skus = [str(r.get("sku")) for r in preview_products]
    if preview_skus:
        posted_qty = StockBalance.objects.filter(
            company=company, product__sku__in=preview_skus
        ).aggregate(s=Sum("on_hand"))["s"] or Decimal("0")
    else:
        posted_qty = Decimal("0")
    ar_ok = abs(books_ar - expected_ar) <= Decimal("0.05")
    ap_ok = abs(books_ap - expected_ap) <= Decimal("0.05")
    stock_ok = abs(posted_qty - expected_qty) <= Decimal("0.05")
    return {
        "stock": {"expected": str(expected_qty), "actual": str(posted_qty), "pass": bool(stock_ok)},
        "receivables": {"expected": str(expected_ar), "actual": str(books_ar), "pass": bool(ar_ok)},
        "payables": {"expected": str(expected_ap), "actual": str(books_ap), "pass": bool(ap_ok)},
        "balances": {
            "opening_ar_docs": opening_invoices,
            "opening_ap_docs": opening_bills,
            "pass": bool(ar_ok and ap_ok),
        },
    }


def _match_or_create_party(model, *, company, row, user, warnings: list[str]):
    """B9-002: Customer/Supplier have no unique (company, name) — a tenant with
    two parties of the same name makes get_or_create raise MultipleObjectsReturned
    (→ 500, whole import rolled back). Match on imported GSTIN first, then a
    single name hit; on an ambiguous name, warn and create a fresh record rather
    than raising or silently patching the wrong party.
    """
    name = (row.get("name") or "").strip()
    gstin = (row.get("gstin") or "").strip()
    label = model.__name__
    if gstin:
        hit = model.objects.filter(company=company, gstin=gstin).first()
        if hit is not None:
            return hit, False
    name_matches = list(model.objects.filter(company=company, name=name)[:2])
    if len(name_matches) == 1:
        return name_matches[0], False
    if len(name_matches) > 1:
        warnings.append(
            f"{label} '{name}' matched {len(name_matches)}+ existing records by name — "
            "created a new record; merge manually if needed."
        )
    obj = model.objects.create(
        company=company,
        name=name,
        phone=row.get("phone") or "",
        gstin=gstin,
        state=row.get("state") or company.state or "",
        created_by=user,
    )
    return obj, True


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
        company=company,
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
        company=company,
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
    if isinstance(edits, dict) and "errors" in edits:
        out["errors"] = list(edits.get("errors") or [])
    else:
        out["errors"] = list(base.get("errors") or [])
    out["disclaimer"] = DISCLAIMER
    err = list(out.get("errors") or [])
    n_cust = len(out.get("customers") or [])
    n_sup = len(out.get("suppliers") or [])
    n_prod = len(out.get("products") or [])
    out["counts"] = {
        "customers": n_cust,
        "suppliers": n_sup,
        "products": n_prod,
        "errors": len(err),
    }
    out["summary"] = {
        "records": n_cust + n_sup + n_prod + len(err),
        "valid": n_cust + n_sup + n_prod,
        "warnings": len(out.get("warnings") or []),
        "errors": len(err),
    }
    return out


def commit_tally_preview(company, user, sync_run: IntegrationSyncRun, *, force: bool = False) -> dict:
    with transaction.atomic():
        return _commit_tally_preview_inner(company, user, sync_run, force=force)


def _commit_tally_preview_inner(company, user, sync_run: IntegrationSyncRun, *, force: bool = False) -> dict:
    del force  # force= is refused at the view; never bypass preview errors.
    sync_run = IntegrationSyncRun.objects.select_for_update().get(pk=sync_run.pk)
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
    if errors:
        raise BusinessRuleError("Cannot commit while preview has errors. Clear them and re-preview.")
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
        cust, was_created = _match_or_create_party(
            Customer, company=company, row=row, user=user, warnings=warnings,
        )
        if was_created:
            created["customers"] += 1
        else:
            dirty = []
            phone = row.get("phone") or ""
            gstin = row.get("gstin") or ""
            if gstin and not (cust.gstin or "").strip():
                cust.gstin = gstin
                dirty.append("gstin")
            elif gstin and (cust.gstin or "").strip() and cust.gstin != gstin:
                warnings.append(f"Customer '{cust.name}' GSTIN kept as {cust.gstin} (import had {gstin}).")
            if phone and not (cust.phone or "").strip():
                cust.phone = phone
                dirty.append("phone")
            if dirty:
                cust.updated_by = user
                cust.save(update_fields=dirty + ["updated_by", "updated_at"])
        amt = _dec(row.get("opening_outstanding"))
        if amt > 0 and _create_opening_sales(company, user, cust, amt, opening_product):
            created["opening_ar"] += 1

    for row in preview.get("suppliers") or []:
        sup, was_created = _match_or_create_party(
            Supplier, company=company, row=row, user=user, warnings=warnings,
        )
        if was_created:
            created["suppliers"] += 1
        else:
            dirty = []
            phone = row.get("phone") or ""
            gstin = row.get("gstin") or ""
            if gstin and not (sup.gstin or "").strip():
                sup.gstin = gstin
                dirty.append("gstin")
            elif gstin and (sup.gstin or "").strip() and sup.gstin != gstin:
                warnings.append(f"Supplier '{sup.name}' GSTIN kept as {sup.gstin} (import had {gstin}).")
            if phone and not (sup.phone or "").strip():
                sup.phone = phone
                dirty.append("phone")
            if dirty:
                sup.updated_by = user
                sup.save(update_fields=dirty + ["updated_by", "updated_at"])
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
    recon = _post_commit_recon(company, preview, created)
    sync_run.counts = created
    sync_run.result = {
        "created": created,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
        "reconciliation": recon,
        "rollback": (
            "Void this import via the existing import-void path (W0-08d): mark "
            "TALLY_OPENING invoices as opening-balance voids; do not delete journals."
        ),
    }
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
    _CAP = 5000
    total = qs.count()
    for inv in qs[:_CAP]:
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
    if total > _CAP:
        # B9-040: don't truncate silently — mark the cap so a user reconciling
        # the file knows rows are missing and narrows the date range.
        writer.writerow([
            csv_safe("TRUNCATED"),
            "", "", "", "", "", "", "", "", "",
            csv_safe(
                f"Export capped at {_CAP} of {total} vouchers — narrow the date range."
            ),
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


_XML_ILLEGAL = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)}


def _xml_escape(text: str) -> str:
    # B9-041: also strip XML-illegal C0 control chars (keep tab/newline/CR) —
    # a bad imported name would otherwise produce a document Tally rejects.
    return (
        str(text or "")
        .translate(_XML_ILLEGAL)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def post_tally_xml(url: str, xml_body: str, *, timeout: int = 30) -> dict[str, Any]:
    """POST XML to Tally HTTP gateway — patch ``requests.post`` in tests."""
    import ipaddress
    from urllib.parse import urlparse

    import requests
    from django.conf import settings

    if not url:
        raise BusinessRuleError("Tally URL is not configured.")
    allowed = (getattr(settings, "TALLY_URL", "") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BusinessRuleError("Tally URL is invalid.")
    host = parsed.hostname.lower()
    try:
        ip = ipaddress.ip_address(host)
        is_loopback = ip.is_loopback
    except ValueError:
        # B9-027: the "test env" bypass also requires DEBUG — a spoofed
        # DJANGO_ENV in a non-debug deployment no longer opens any host.
        is_loopback = (
            host in {"localhost", "127.0.0.1", "::1"}
            or host.endswith(".test")
            or host.endswith(".localhost")
            or (
                getattr(settings, "DJANGO_ENV", "") == "test"
                and bool(getattr(settings, "DEBUG", False))
            )
        )
    if allowed:
        # B9-027: compare scheme + host + port (not host only) and require the
        # request path to sit under the configured base path.
        a = urlparse(allowed)
        allowed_host = (a.hostname or "").lower()
        allowed_scheme = a.scheme or "http"
        allowed_port = a.port or (443 if allowed_scheme == "https" else 80)
        req_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        base_path = (a.path or "/").rstrip("/") or "/"
        req_path = parsed.path or "/"
        same_origin = (
            host == allowed_host
            and parsed.scheme == allowed_scheme
            and req_port == allowed_port
        )
        path_ok = req_path == base_path or req_path.startswith(base_path + "/") or base_path == "/"
        if not (same_origin and path_ok):
            raise BusinessRuleError("Tally URL is not on the server allowlist.")
    elif not is_loopback:
        raise BusinessRuleError("Tally HTTP push is limited to localhost unless TALLY_URL is set.")
    resp = requests.post(
        url,
        data=xml_body.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=timeout,
        allow_redirects=False,
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


def push_vouchers_http(
    company,
    date_from=None,
    date_to=None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """One-shot Tally voucher XML dump (not live sync)."""
    from django.conf import settings

    url = (base_url or getattr(settings, "TALLY_URL", "") or "").strip()
    xml_body = _vouchers_xml(company, date_from=date_from, date_to=date_to)
    result = post_tally_xml(url, xml_body)
    result["disclaimer"] = DISCLAIMER
    result["kind"] = "vouchers"
    result["mode"] = "export_dump"
    result["sync"] = False
    return result

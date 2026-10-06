"""Wiring that turns the planwave helpers into the remaining pass conditions."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import ItcBillCheck, PharmacyDispense, PosCartHold, UserWarehouseAccess
from .services import (
    flag_anomaly,
    itc_claimable,
    save_itc_check,
    section_16_4_status,
    section_50_interest,
    suggest_provision,
    supplier_itc_blocked,
    blocked_credit_match,
    interest_exposure,
)


def pharmacy_register_pdf(company) -> bytes:
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buf = BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.setTitle("Pharmacy register")
    y = 800
    pdf.drawString(40, y, "Schedule H / H1 / X register. A pharmacist must review this layout.")
    for line in pharmacy_register_csv(company).splitlines()[:40]:
        y -= 16
        if y < 40:
            break
        pdf.drawString(40, y, line[:110])
    pdf.save()
    return buf.getvalue()


def pharmacy_register_csv(company) -> str:
    flags = getattr(company, "feature_flags", None) or {}
    years = int(flags.get("pharmacy_retention_years") or 3)
    cutoff = timezone.now() - timedelta(days=365 * years)
    rows = PharmacyDispense.objects.filter(company=company, created_at__gte=cutoff).select_related("product")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "patient", "prescriber", "registration", "drug", "batch", "quantity", "invoice"])
    for row in rows:
        writer.writerow([
            row.created_at.date().isoformat(),
            row.patient_name,
            row.prescriber_name,
            row.prescriber_registration,
            row.product.name,
            row.batch_no,
            row.quantity,
            row.invoice_number,
        ])
    return buf.getvalue()


def section_50_csv(*, tax, excess_itc, days, on) -> str:
    result = section_50_interest(tax=Decimal(str(tax)), excess_itc=Decimal(str(excess_itc)), days=int(days), on=on)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["late_tax_interest", "excess_itc_interest", "journal_posted"])
    writer.writerow([result["late_tax_interest"], result["excess_itc_interest"], result["journal_posted"]])
    return buf.getvalue()


def classify_purchase_bill(invoice) -> ItcBillCheck:
    """Record s.16 and s.17 status. Posting is not blocked."""
    blocked = False
    on = invoice.invoice_date
    items = getattr(invoice, "items", None)
    if items is not None:
        for item in items.select_related("product"):
            product = getattr(item, "product", None)
            hsn = (getattr(item, "hsn_code", "") or getattr(product, "hsn_code", "") or "")
            category = ""
            if product is not None and getattr(product, "category_id", None) and getattr(product, "category", None):
                category = product.category.name or ""
            if blocked_credit_match(hsn=hsn, expense_category=category, on=on):
                blocked = True
    cancelled = supplier_itc_blocked(on, getattr(invoice.supplier, "gstin_cancelled_on", None))
    check = save_itc_check(
        invoice.company,
        "purchase",
        invoice.pk,
        invoice_held=True,
        goods_received=bool(getattr(invoice, "goods_received", False)),
        paid_within_180=False,
        supplier_tax_attested=False,
        return_filed_attested=False,
    )
    check.blocked_credit = blocked or cancelled
    check.deadline_status = section_16_4_status(on, claimed=check.claimed, today=timezone.localdate())
    check.save(update_fields=["blocked_credit", "deadline_status", "updated_at"])
    return check


def refresh_itc_status(company) -> int:
    """Recompute the s.16(4) status and the 180-day payment test from the bills themselves.

    The status depends on today's date, so it cannot be stored once at completion: a bill
    that was OPEN in July is TIME_BARRED after 30 November of the next year.
    """
    from django.db.models import Max, Sum

    from payments.models import PaymentAllocation
    from purchases.models import PurchaseInvoice

    checks = list(ItcBillCheck.objects.filter(company=company, source_type="purchase"))
    ids = []
    for check in checks:
        try:
            ids.append(int(check.source_id))
        except (TypeError, ValueError):
            continue
    invoices = {i.pk: i for i in PurchaseInvoice.objects.filter(company=company, pk__in=ids)}
    paid = {
        row["purchase_invoice_id"]: row
        for row in PaymentAllocation.objects.filter(
            company=company, purchase_invoice_id__in=ids, supplier_payment__isnull=False,
            receipt__isnull=True, reversed_at__isnull=True,
        ).values("purchase_invoice_id").annotate(total=Sum("amount"), last=Max("supplier_payment__payment_date"))
    }
    today = timezone.localdate()
    changed = 0
    for check in checks:
        try:
            invoice = invoices.get(int(check.source_id))
        except (TypeError, ValueError):
            invoice = None
        if invoice is None or invoice.invoice_date is None:
            continue
        status = section_16_4_status(invoice.invoice_date, claimed=check.claimed, today=today)
        row = paid.get(invoice.pk)
        within_180 = bool(
            row and row["total"] is not None and row["total"] >= (invoice.grand_total or 0)
            and row["last"] is not None and (row["last"] - invoice.invoice_date).days <= 180
        )
        if status != check.deadline_status or within_180 != check.paid_within_180:
            check.deadline_status = status
            check.paid_within_180 = within_180
            check.save(update_fields=["deadline_status", "paid_within_180", "updated_at"])
            changed += 1
    return changed


def itc_summary(company) -> dict:
    refresh_itc_status(company)
    rows = ItcBillCheck.objects.filter(company=company)
    claimable = [r for r in rows if itc_claimable(r) and not r.blocked_credit and r.deadline_status != "TIME_BARRED"]
    return {
        "claimable": len(claimable),
        "excluded": rows.count() - len(claimable),
        "blocked": rows.filter(blocked_credit=True).count(),
        "time_barred": rows.filter(deadline_status="TIME_BARRED").count(),
    }


def alert_itc_deadlines(company) -> int:
    from core.models import Notification
    from core.services.notifications import NotificationService
    from accounts.models import CompanyUser

    refresh_itc_status(company)
    sent = 0
    today = timezone.localdate()
    owner = CompanyUser.objects.filter(company=company, is_active=True, role=CompanyUser.Role.OWNER).select_related("user").first()
    if owner is None:
        return 0
    for check in ItcBillCheck.objects.filter(company=company, deadline_status__in=("DUE_60", "DUE_7", "TIME_BARRED")):
        if check.deadline_status == "TIME_BARRED" and check.claimed:
            subject = "Claimed ITC needs CA review"
        elif check.deadline_status == "TIME_BARRED":
            subject = "ITC is time-barred"
        else:
            subject = f"ITC deadline in {check.deadline_status.replace('DUE_', '')} days"
        body = f"Purchase {check.source_id}: {check.deadline_status}."
        if Notification.objects.filter(
            company=company, subject=subject, body=body, created_at__date=today,
        ).exists():
            continue  # one alert per bill per day, however often this runs
        NotificationService.send(
            company=company,
            channel=Notification.Channel.IN_APP,
            recipient=owner.user.email or str(owner.user_id),
            subject=subject,
            body=body,
            user=owner.user,
        )
        sent += 1
    return sent


def score_2b_rows(rows: list[dict]) -> list[dict]:
    from .services import gstr2b_score

    scored = []
    for row in rows:
        band = gstr2b_score(
            books_gstin=row.get("books_gstin") or "",
            return_gstin=row.get("return_gstin") or "",
            books_tax=Decimal(str(row.get("books_tax") or "0")),
            return_tax=Decimal(str(row.get("return_tax") or "0")),
        )
        blocked = bool(row.get("blocked_credit"))
        if blocked and band == "AUTO":
            band = "BLOCKED"
        scored.append({**row, "band": band, "eligible": band == "AUTO" and not blocked})
    return scored


def debtor_delays(company, customer) -> list[int]:
    """Days between the due date and the day the last receipt settled each paid invoice."""
    from django.db.models import Max

    from ledgers.services import LedgerService
    from payments.models import PaymentAllocation
    from sales.models import SalesInvoice

    rows = list(
        SalesInvoice.objects.filter(
            company=company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        )
        .exclude(due_date=None)
        .order_by("-invoice_date", "-pk")[:12]
    )
    last_paid = {
        r["sales_invoice_id"]: r["last"]
        for r in PaymentAllocation.objects.filter(
            company=company, sales_invoice_id__in=[r.pk for r in rows], receipt__isnull=False,
            supplier_payment__isnull=True, reversed_at__isnull=True,
        ).values("sales_invoice_id").annotate(last=Max("receipt__receipt_date"))
    }
    delays = []
    for row in rows:
        paid_on = last_paid.get(row.pk)
        if paid_on is None or LedgerService.sales_invoice_outstanding(row) > 0:
            continue  # still open: not a settled sample
        delays.append(max(0, (paid_on - row.due_date).days))
    return delays


def cashflow_for_customer(company, customer) -> dict:
    from .services import cashflow_forecast

    delays = debtor_delays(company, customer)
    flags = getattr(company, "feature_flags", None) or {}
    segment = float(flags.get("segment_delay_days") or 15)
    forecast = cashflow_forecast(delays, segment_average=segment)
    forecast["samples"] = len(delays)
    return forecast


def overdue_report(company) -> list[dict]:
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    today = timezone.localdate()
    out = []
    for row in SalesInvoice.objects.filter(
        company=company, status=SalesInvoice.Status.COMPLETED, due_date__lt=today,
    ).select_related("customer").order_by("due_date", "pk")[:500]:
        amount = LedgerService.sales_invoice_outstanding(row)
        if amount <= 0:
            continue  # paid or fully credited
        days = (today - row.due_date).days
        out.append({
            "invoice": row.number or str(row.pk),
            "customer": row.customer.name,
            "days": days,
            "amount": str(amount),
            "interest": str(interest_exposure(company, amount=amount, days=days)),
            "provision": str(suggest_provision(company, days_overdue=days, amount=amount)),
        })
    return out


def godown_dashboard(company) -> list[dict]:
    from django.db.models import Sum

    from inventory.models import StockBalance, Warehouse

    rows = []
    for warehouse in Warehouse.objects.filter(company=company):
        totals = StockBalance.objects.filter(company=company, warehouse=warehouse).aggregate(
            on_hand=Sum("on_hand"), reserved=Sum("reserved"),
        )
        rows.append({
            "warehouse": warehouse.pk,
            "name": warehouse.name,
            "on_hand": str(totals["on_hand"] or 0),
            "reserved": str(totals["reserved"] or 0),
        })
    return rows


def review_completed_sale(invoice) -> None:
    from sales.models import SalesInvoice

    priors = list(
        SalesInvoice.objects.filter(
            company=invoice.company, customer_id=invoice.customer_id, status=SalesInvoice.Status.COMPLETED,
        ).exclude(pk=invoice.pk).order_by("-invoice_date").values_list("grand_total", flat=True)[:12]
    )
    amounts = sorted(Decimal(str(v or 0)) for v in priors)
    median = amounts[len(amounts) // 2] if amounts else Decimal("0")
    line_discounts = []
    for line in invoice.items.all():
        line_discounts.append(Decimal(str(getattr(line, "discount_percent", 0) or 0)))
    discount = max(line_discounts) if line_discounts else Decimal("0")
    from sales.models import SalesItem

    prior_ids = list(
        SalesInvoice.objects.filter(
            company=invoice.company, customer_id=invoice.customer_id, status=SalesInvoice.Status.COMPLETED,
        ).exclude(pk=invoice.pk).order_by("-invoice_date").values_list("pk", flat=True)[:12]
    )
    prior_discounts = sorted(
        Decimal(str(v or 0))
        for v in SalesItem.objects.filter(invoice_id__in=prior_ids).values_list("discount_percent", flat=True)
    )
    median_discount = prior_discounts[len(prior_discounts) // 2] if prior_discounts else None
    flag_anomaly(
        company=invoice.company,
        kind="sale",
        subject_id=invoice.pk,
        discount=discount,
        median_discount=median_discount,
        bill=invoice.grand_total,
        median_bill=median,
    )


def commit_bulk_invoices(company, text: str, user) -> dict:
    import hashlib

    from masters.models import Customer, Product
    from sales.models import SalesInvoice
    from sales.services import SalesService

    from .models import BulkImportBatch
    from .services import parse_bulk_invoices

    dry = parse_bulk_invoices(company, text)
    if dry.get("idempotent"):
        return dry
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    # The batch row lock is held for the whole commit, so a second upload of the same file
    # waits and then sees what the first one created instead of creating everything twice.
    with transaction.atomic():
        batch = BulkImportBatch.objects.select_for_update().get(company=company, file_hash=digest)
        if batch.status == "COMMITTED":
            return {"idempotent": True, "report": batch.report}
        prior_created = list((batch.report or {}).get("created") or [])
        done_refs = {c.get("invoice_ref") for c in prior_created}
        reader = csv.DictReader(io.StringIO(text))
        groups: dict[str, list] = {}
        rejected = list(dry["report"]["rejected"])
        bad_refs = {row.get("invoice_ref") for row in rejected}
        for row in reader:
            ref = (row.get("invoice_ref") or "").strip()
            if not ref or ref in bad_refs or ref in done_refs:
                continue
            groups.setdefault(ref, []).append(row)
        created = prior_created
        for ref, lines in groups.items():
            try:
                with transaction.atomic():
                    matches = list(Customer.objects.filter(company=company, name=lines[0]["customer"])[:2])
                    if not matches:
                        raise BusinessRuleError(f"Unknown customer on {ref}.")
                    if len(matches) > 1:
                        raise BusinessRuleError(f"More than one customer is named on {ref}. Use a unique name.")
                    customer = matches[0]
                    invoice = SalesInvoice.objects.create(
                        company=company,
                        customer=customer,
                        invoice_type=SalesInvoice.InvoiceType.GST,
                        notes=lines[0].get("notes") or "",
                        created_by=user if getattr(user, "pk", None) else None,
                        updated_by=user if getattr(user, "pk", None) else None,
                    )
                    items_data = []
                    for line in lines:
                        product = Product.objects.filter(company=company, sku=line["sku"]).first()
                        if product is None:
                            raise BusinessRuleError(f"Unknown SKU {line['sku']} on {ref}.")
                        items_data.append({
                            "product": product,
                            "description": product.name,
                            "quantity": Decimal(str(line["quantity"])),
                            "unit_price": Decimal(str(line["rate"])),
                            "discount_percent": Decimal(str(line.get("discount") or "0")),
                        })
                    # Through the service, so line tax, line totals and the invoice totals are
                    # computed. Raw SalesItem rows would leave a draft with zero totals and no GST.
                    SalesService.set_items(invoice, items_data, user)
                    created.append({"invoice_ref": ref, "id": invoice.pk})
            except BusinessRuleError as exc:
                rejected.append({"invoice_ref": ref, "error": str(exc)})
            except Exception:  # noqa: BLE001 - do not echo internals to the client
                rejected.append({"invoice_ref": ref, "error": "This invoice could not be created."})
        # Only a clean run is final. With rejects the file can be fixed and uploaded again, and
        # the invoices already created are skipped on the next run.
        batch.status = "COMMITTED" if not rejected else "DRY_RUN"
        batch.report = {"created": created, "rejected": rejected}
        batch.save(update_fields=["status", "report", "updated_at"])
    return {"idempotent": False, "created": created, "rejected": rejected}


def restore_master(company, kind: str, pk: int, user):
    from masters.models import Customer, PriceList, Product, Supplier
    from inventory.models import Warehouse

    models = {
        "customer": Customer, "supplier": Supplier, "product": Product,
        "pricelist": PriceList, "warehouse": Warehouse,
    }
    model = models.get(kind)
    if model is None:
        raise BusinessRuleError("Unknown master.")
    row = model.all_objects.filter(pk=pk, company=company).first()
    if row is None:
        raise BusinessRuleError("That record was not found in this company.")
    row.is_deleted = False
    row.deleted_at = None
    row.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    from core.services.audit import AuditService

    AuditService.log(
        company=company, user=user, action="UPDATE", entity_type=kind, entity_id=str(pk),
        description="Restored a soft-deleted master.",
    )
    return row


def grant_warehouse(company, user, warehouse, *, default=False) -> UserWarehouseAccess:
    if warehouse.company_id != company.id:
        raise BusinessRuleError("Warehouse is not in this company.")
    if default:
        UserWarehouseAccess.objects.filter(company=company, user=user, is_default=True).update(is_default=False)
    row, _ = UserWarehouseAccess.objects.update_or_create(
        company=company, user=user, warehouse=warehouse, defaults={"is_default": default},
    )
    return row


def hold_pos_cart(company, *, label: str, payload: dict, hours: int = 24, user=None) -> PosCartHold:
    return PosCartHold.objects.create(
        company=company,
        label=label or "Cart",
        payload=payload or {},
        expires_at=timezone.now() + timedelta(hours=hours),
        created_by=user if getattr(user, "pk", None) else None,
    )


def release_expired_pos_holds(company=None) -> int:
    qs = PosCartHold.objects.filter(released_at__isnull=True, expires_at__lt=timezone.now())
    if company is not None:
        qs = qs.filter(company=company)
    return qs.update(released_at=timezone.now())


def catalog_rows(company, role: str) -> tuple[list[str], list[list[str]]]:
    """Item export. Purchase price is omitted for cashier, salesperson and godown roles."""
    from masters.models import Product

    from .services import cost_visible

    show_cost = cost_visible(role)
    headers = ["sku", "name", "selling_price"]
    if show_cost:
        headers.append("purchase_price")
    rows = []
    for product in Product.objects.filter(company=company).order_by("sku"):
        line = [product.sku, product.name, str(product.selling_price)]
        if show_cost:
            line.append(str(product.purchase_price))
        rows.append(line)
    return headers, rows


def catalog_csv(company, role: str) -> str:
    headers, rows = catalog_rows(company, role)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue()


def catalog_pdf(company, role: str) -> bytes:
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buf = BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.setTitle("Item catalogue")
    y = 800
    for line in catalog_csv(company, role).splitlines()[:40]:
        pdf.drawString(40, y, line[:110])
        y -= 16
        if y < 40:
            break
    pdf.save()
    return buf.getvalue()


def orphan_report() -> list[dict]:
    """Soft-deleted masters that still have live documents."""
    from masters.models import Customer, Product

    found = []
    for customer in Customer.all_objects.filter(is_deleted=True):
        if customer.sales_invoices.filter(status="COMPLETED").exists():
            found.append({"kind": "customer", "id": customer.pk, "name": customer.name})
    for product in Product.all_objects.filter(is_deleted=True):
        if product.is_referenced():
            found.append({"kind": "product", "id": product.pk, "name": product.name})
    return found

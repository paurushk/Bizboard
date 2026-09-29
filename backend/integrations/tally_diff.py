"""One-time Tally XML-shaped diff. A re-run of the same batch id does not double-post."""

from __future__ import annotations

import re
from decimal import Decimal

from django.db import transaction

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService

from .models import IntegrationSyncRun

RUPEE_TOLERANCE = Decimal("5.00")


def record_migration_diff(*, company, batch_id: str, tally_total: Decimal, books_total: Decimal, user=None):
    from accounts.models import Company

    batch_id = (batch_id or "").strip()
    if not batch_id:
        raise BusinessRuleError("migration batch id is required.")
    with transaction.atomic():
        # Lock the company row so two concurrent requests for the same batch
        # id (a double-click, or a client retry) can't both pass the
        # existence check before either has committed its IntegrationSyncRun.
        Company.objects.select_for_update().get(pk=company.pk)
        existing = IntegrationSyncRun.objects.filter(
            company=company, kind=IntegrationSyncRun.Kind.TALLY_MIGRATE, counts__batch_id=batch_id,
        ).first()
        if existing is not None:
            raise BusinessRuleError("This migration batch was already recorded.")
        diff = (Decimal(tally_total) - Decimal(books_total)).copy_abs()
        blocked = diff > RUPEE_TOLERANCE
        run = IntegrationSyncRun.objects.create(
            company=company,
            kind=IntegrationSyncRun.Kind.TALLY_MIGRATE,
            status=IntegrationSyncRun.Status.FAILED if blocked else IntegrationSyncRun.Status.PREVIEWED,
            counts={"batch_id": batch_id, "tally_total": str(tally_total), "books_total": str(books_total)},
            result={"diff": str(diff), "blocked": blocked, "tolerance": str(RUPEE_TOLERANCE)},
            created_by=user,
            updated_by=user,
        )
        AuditService.log(
            company=company,
            user=user,
            action="CREATE",
            entity_type="integrationsyncrun",
            entity_id=run.pk,
            description="tally.migration_diff",
            metadata={"batch_id": batch_id, "blocked": blocked, "diff": str(diff)},
        )
    return run


_AMOUNT = re.compile(r"<AMOUNT>([^<]+)</AMOUNT>", re.I)


def parse_tally_amounts(xml: str) -> Decimal:
    parsed: list[Decimal] = []
    for raw in _AMOUNT.findall(xml or ""):
        token = re.sub(r"\s*(dr|cr)\s*$", "", raw.strip(), flags=re.I)
        token = token.replace(",", "").strip()
        try:
            parsed.append(Decimal(token))
        except Exception as exc:
            raise BusinessRuleError(f"Could not read Tally amount '{raw.strip()}'.") from exc
    # Ledger exports carry both the debit and the credit leg. Summing the
    # signed values nets a voucher to about zero. When signs are mixed, keep
    # the positive leg, which is the amount books can be compared with.
    if any(value < 0 for value in parsed) and any(value > 0 for value in parsed):
        return sum((value for value in parsed if value > 0), Decimal("0"))
    return sum(parsed, Decimal("0"))


def books_sales_total(company) -> Decimal:
    from django.db.models import Sum

    from sales.models import SalesInvoice

    total = SalesInvoice.objects.filter(
        company=company, status=SalesInvoice.Status.COMPLETED,
    ).aggregate(total=Sum("grand_total"))["total"]
    return total or Decimal("0")


def migration_pdf_bytes(run) -> bytes:
    from io import BytesIO

    from reportlab.pdfgen import canvas

    counts = run.counts or {}
    result = run.result or {}
    buf = BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.setTitle("Tally migration difference")
    pdf.drawString(72, 760, "Tally migration difference")
    pdf.drawString(72, 730, f"Batch {counts.get('batch_id', '')}")
    pdf.drawString(72, 710, f"Tally total  {counts.get('tally_total', '')}")
    pdf.drawString(72, 690, f"Books total (completed sales invoices)  {counts.get('books_total', '')}")
    pdf.drawString(72, 670, f"Difference {result.get('diff', '')}  tolerance {result.get('tolerance', '')}")
    blocked = "Blocked — difference is above ₹5." if result.get("blocked") else "Within ₹5. Ready for the accountant to sign."
    pdf.drawString(72, 640, blocked)
    pdf.drawString(72, 580, "Chartered accountant signature")
    pdf.line(72, 560, 320, 560)
    pdf.save()
    return buf.getvalue()

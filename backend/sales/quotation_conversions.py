"""Quotation conversion ledger: record, release and reopen.

The ledger is the source of truth. ``QuotationItem.converted_quantity`` is a
cache that is always recomputed from the unreleased rows inside the quote lock,
never adjusted by adding or subtracting.
"""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled

RELEASE_FLAG = "QUOTE_CONVERSION_RELEASE"


def backfill_conversions(item_model, conversion_model, *, batch_size=1000, company=None):
    """Create one backfilled row per converted quote line that has none yet.

    Idempotent. Returns ``{company_id: unknown_row_count}``. Model classes are
    passed in so the data migration can use its historical models. ``company``
    limits the scan to one tenant (restore); without it every tenant is scanned.
    """
    from core.rls import rls_bypass

    unknown = defaultdict(int)
    with rls_bypass():
        scope = {"company_id": getattr(company, "pk", company)} if company is not None else {}
        done = set(
            conversion_model.objects.filter(**scope)
            .exclude(quotation_item=None)
            .values_list("quotation_item_id", flat=True)
            .distinct()
        )
        rows = []
        lines = (
            item_model.objects.filter(converted_quantity__gt=0, **scope)
            .select_related("quotation")
            .order_by("id")
        )
        for item in lines.iterator(chunk_size=batch_size):
            if item.id in done:
                continue
            quotation = item.quotation
            invoice_id = quotation.converted_invoice_id
            order_id = quotation.converted_order_id
            if invoice_id and not order_id:
                target, order_id = "INVOICE", None
            elif order_id and not invoice_id:
                target, invoice_id = "ORDER", None
            else:
                target, order_id, invoice_id = "UNKNOWN", None, None
                unknown[quotation.company_id] += 1
            rows.append(conversion_model(
                company_id=quotation.company_id,
                quotation_id=quotation.id,
                quotation_item_id=item.id,
                product_id=item.product_id,
                unit_price=item.unit_price,
                target=target,
                sales_order_id=order_id,
                sales_invoice_id=invoice_id,
                quantity=item.converted_quantity,
                backfilled=True,
            ))
            if len(rows) >= batch_size:
                conversion_model.objects.bulk_create(rows, batch_size=batch_size)
                rows = []
        if rows:
            conversion_model.objects.bulk_create(rows, batch_size=batch_size)
    return dict(unknown)


def _assert_same_company(quotation, *documents):
    for document in documents:
        if document is not None and document.company_id != quotation.company_id:
            raise BusinessRuleError("A quotation can only convert into documents of its own company.")


class QuotationConversionService:
    @staticmethod
    def recompute(quotation, user=None):
        """Rebuild each line's converted_quantity cache and the quote status.

        Caller holds the quote row lock.
        """
        from .models import Quotation, QuotationConversion

        totals = dict(
            QuotationConversion.objects.filter(quotation=quotation, released_at__isnull=True)
            .exclude(quotation_item=None)
            .values_list("quotation_item_id")
            .annotate(total=Sum("quantity"))
        )
        items = list(quotation.items.all())
        changed = []
        for item in items:
            value = totals.get(item.id) or Decimal("0")
            if Decimal(str(item.converted_quantity or 0)) != value:
                item.converted_quantity = value
                changed.append(item)
        if changed:
            type(items[0]).objects.bulk_update(changed, ["converted_quantity"])
        fully = bool(items) and all(
            Decimal(str(item.quantity)) - Decimal(str(item.converted_quantity or 0)) <= 0
            for item in items
        )
        # Close remaining: the unconverted quantity was abandoned on purpose, so the quote
        # stays closed whatever later releases do to the converted quantity.
        if quotation.short_closed_at is not None:
            fully = True
        fields = ["updated_at"]
        if fully and quotation.status in Quotation.OPEN_STATUSES:
            quotation.status_before_conversion = quotation.status
            quotation.status = Quotation.Status.CONVERTED
            fields += ["status", "status_before_conversion"]
        elif not fully and quotation.status == Quotation.Status.CONVERTED:
            restore = quotation.status_before_conversion or Quotation.Status.DRAFT
            if restore not in Quotation.OPEN_STATUSES:
                restore = Quotation.Status.DRAFT
            quotation.status = restore
            fields.append("status")
        if user is not None:
            quotation.updated_by = user
            fields.append("updated_by")
        quotation.save(update_fields=fields)
        return quotation

    @staticmethod
    def record(quotation, pairs, user, *, order=None, invoice=None):
        """``pairs`` is ``[(quote_item, quantity, downstream_line), ...]`` in plan order."""
        from .models import QuotationConversion

        _assert_same_company(quotation, order, invoice)
        target = QuotationConversion.Target.ORDER if order is not None else QuotationConversion.Target.INVOICE
        QuotationConversion.objects.bulk_create([
            QuotationConversion(
                company_id=quotation.company_id,
                quotation=quotation,
                quotation_item=item,
                product_id=item.product_id,
                unit_price=item.unit_price,
                target=target,
                sales_order=order,
                sales_order_item=line if order is not None else None,
                sales_invoice=invoice,
                sales_invoice_item=line if invoice is not None else None,
                quantity=qty,
                created_by=user,
            )
            for item, qty, line in pairs
        ])
        return QuotationConversionService.recompute(quotation, user)

    @staticmethod
    def _release(rows_qs, company, user, reason):
        from core.services.audit import AuditService

        from .models import Quotation

        quote_ids = sorted(set(rows_qs.values_list("quotation_id", flat=True)))
        if not quote_ids:
            return 0
        released = 0
        with transaction.atomic():
            quotes = list(Quotation.objects.select_for_update().filter(pk__in=quote_ids).order_by("pk"))
            rows = list(rows_qs.select_for_update().order_by("pk"))
            if not rows:
                return 0
            now = timezone.now()
            for row in rows:
                row.released_at = now
                row.released_by = user
                row.release_reason = reason
            type(rows[0]).objects.bulk_update(rows, ["released_at", "released_by", "release_reason"])
            released = len(rows)
            for quotation in quotes:
                quantity = sum(
                    (row.quantity for row in rows if row.quotation_id == quotation.pk), Decimal("0")
                )
                QuotationConversionService.recompute(quotation, user)
                AuditService.log(
                    action="QUOTATION_CONVERSION_RELEASED",
                    company=company,
                    user=user,
                    entity_type="Quotation",
                    entity_id=str(quotation.pk),
                    description=f"Released {quantity} converted quantity ({reason}).",
                    metadata={"reason": reason, "rows": [row.pk for row in rows if row.quotation_id == quotation.pk]},
                )
        return released

    @staticmethod
    def sweep(company=None, *, dry_run=False, user=None):
        """Release rows whose document is gone or cancelled (closure plan WP4).

        Covers releases missed while the rollout flag was off and any path that deleted
        a document without calling a hook. Backfilled UNKNOWN rows are never touched
        (an owner reopens those), and an invoice made from an order never releases the
        quote: rows for an order release only when that order is gone or cancelled.
        Safe to run twice. Returns ``{"released": n, "by_reason": {...}, "by_company": {...}}``.
        """
        from accounts.models import Company
        from core.rls import rls_bypass

        from .models import QuotationConversion, SalesInvoice, SalesOrder

        reasons = QuotationConversion.ReleaseReason
        groups = (
            (reasons.DRAFT_DELETED, {"sales_order__isnull": True, "sales_invoice__isnull": True}),
            (reasons.ORDER_CANCELLED, {"sales_order__status": SalesOrder.Status.CANCELLED}),
            (reasons.INVOICE_CANCELLED, {"sales_invoice__status": SalesInvoice.Status.CANCELLED}),
        )
        result = {"released": 0, "by_reason": {}, "by_company": {}}
        with rls_bypass():
            base = QuotationConversion.objects.filter(released_at__isnull=True).exclude(
                target=QuotationConversion.Target.UNKNOWN
            )
            if company is not None:
                base = base.filter(company_id=getattr(company, "pk", company))
            company_ids = sorted(set(base.values_list("company_id", flat=True)))
            for company_obj in Company.objects.filter(pk__in=company_ids):
                for reason, lookup in groups:
                    rows = base.filter(company_id=company_obj.pk, **lookup)
                    count = rows.count() if dry_run else QuotationConversionService._release(
                        rows, company_obj, user, reason
                    )
                    if count:
                        result["released"] += count
                        result["by_reason"][reason] = result["by_reason"].get(reason, 0) + count
                        result["by_company"][company_obj.pk] = result["by_company"].get(company_obj.pk, 0) + count
        return result

    @staticmethod
    def close_remaining(quotation, user, reason):
        """Abandon the unconverted quantity of a partly converted quote (D-16)."""
        from core.services.audit import AuditService

        from .models import Quotation

        reason = (reason or "").strip()
        if not reason:
            raise BusinessRuleError("A reason is required to close the remaining quantity.", code="reason_required")
        with transaction.atomic():
            quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
            if quotation.status not in Quotation.OPEN_STATUSES:
                raise BusinessRuleError(
                    f"Cannot close a quotation in status {quotation.status}.", code="quotation_not_closable"
                )
            if not quotation.items.filter(converted_quantity__gt=0).exists():
                raise BusinessRuleError(
                    "Nothing has been converted yet; cancel the quotation instead.", code="quotation_not_closable"
                )
            quotation.short_closed_at = timezone.now()
            quotation.short_closed_by = user
            quotation.short_close_reason = reason[:500]
            quotation.save(update_fields=["short_closed_at", "short_closed_by", "short_close_reason"])
            quotation = QuotationConversionService.recompute(quotation, user)
            AuditService.log(
                action="QUOTATION_CLOSED_REMAINING",
                company=quotation.company,
                user=user,
                entity_type="Quotation",
                entity_id=str(quotation.pk),
                description=reason[:200],
                metadata={"reason": reason[:500]},
            )
        return quotation

    @staticmethod
    def reopen_closed(quotation, user, reason):
        """Owner-only undo of Close remaining."""
        from core.services.audit import AuditService

        from .models import Quotation

        reason = (reason or "").strip()
        if not reason:
            raise BusinessRuleError("A reason is required to reopen a closed quotation.", code="reason_required")
        with transaction.atomic():
            quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
            if quotation.short_closed_at is None:
                raise BusinessRuleError("This quotation was not closed with Close remaining.")
            quotation.short_closed_at = None
            quotation.short_closed_by = None
            quotation.short_close_reason = ""
            quotation.save(update_fields=["short_closed_at", "short_closed_by", "short_close_reason"])
            quotation = QuotationConversionService.recompute(quotation, user)
            AuditService.log(
                action="QUOTATION_REOPENED_CLOSED",
                company=quotation.company,
                user=user,
                entity_type="Quotation",
                entity_id=str(quotation.pk),
                description=reason[:200],
                metadata={"reason": reason[:500]},
            )
        return quotation

    @staticmethod
    def release_for_order(order, user, reason):
        """Safe to call twice: a second call finds no unreleased rows."""
        from .models import QuotationConversion

        if order is None or not flag_enabled(order.company, RELEASE_FLAG):
            return 0
        rows = QuotationConversion.objects.filter(
            company_id=order.company_id, sales_order_id=order.pk, released_at__isnull=True
        )
        return QuotationConversionService._release(rows, order.company, user, reason)

    @staticmethod
    def release_for_invoice(invoice, user, reason):
        """Releases only quotes converted straight to this invoice, never via an order."""
        from .models import QuotationConversion

        if invoice is None or not flag_enabled(invoice.company, RELEASE_FLAG):
            return 0
        rows = QuotationConversion.objects.filter(
            company_id=invoice.company_id, sales_invoice_id=invoice.pk, released_at__isnull=True
        )
        return QuotationConversionService._release(rows, invoice.company, user, reason)

    @staticmethod
    def reopen(quotation, user, reason, conversion_ids=None):
        """Owner-only manual release (UNKNOWN backfilled rows, or rows whose
        downstream document vanished while releases were off)."""
        from .models import QuotationConversion

        reason = (reason or "").strip()
        if not reason:
            raise BusinessRuleError("A reason is required to reopen converted quantity.")
        rows = QuotationConversion.objects.filter(
            company_id=quotation.company_id, quotation=quotation, released_at__isnull=True
        )
        if conversion_ids is not None:
            rows = rows.filter(pk__in=list(conversion_ids))
        if not rows.exists():
            raise BusinessRuleError("There is no converted quantity to reopen on this quotation.")
        count = QuotationConversionService._release(
            rows, quotation.company, user, QuotationConversion.ReleaseReason.MANUAL_REOPEN
        )
        from core.services.audit import AuditService

        AuditService.log(
            action="QUOTATION_REOPENED",
            company=quotation.company,
            user=user,
            entity_type="Quotation",
            entity_id=str(quotation.pk),
            description=reason[:500],
            metadata={"released_rows": count},
        )
        return count


def latest_link(quotation, target):
    """Latest unreleased conversion document id of a kind (legacy computed links)."""
    rows = getattr(quotation, "_prefetched_objects_cache", {}).get("conversions")
    if rows is None:
        rows = list(quotation.conversions.all())
    field = "sales_invoice_id" if target == "INVOICE" else "sales_order_id"
    live = [row for row in rows if row.target == target and row.released_at is None and getattr(row, field)]
    if not live:
        return None
    return getattr(max(live, key=lambda row: row.pk), field)


# ---------------------------------------------------------------------------
# Header charges and discount on partial conversion (closure plan WP1)
# ---------------------------------------------------------------------------

_CENT = Decimal("0.01")


def _q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT)


def _line_weight(item, *, by_quantity: bool) -> Decimal:
    """Value a quote line carries when the header is shared out.

    Taxable value before the header: quantity x price x (1 - line discount).
    A line with no value weighs 0 (a free sample does not absorb a delivery
    charge), unless every line is valueless, when quantities are used.
    """
    quantity = Decimal(str(item.quantity or 0))
    if by_quantity:
        return quantity
    price = Decimal(str(item.unit_price or 0))
    discount = Decimal(str(item.discount_percent or 0))
    return max(quantity * price * (Decimal("100") - discount) / Decimal("100"), Decimal("0"))


def _converted_weight(quotation, items, *, by_quantity: bool) -> Decimal:
    """Weight already carried by live (unreleased) ledger rows."""
    import logging

    from .models import QuotationConversion

    by_id = {item.id: item for item in items}
    total = Decimal("0")
    rows = QuotationConversion.objects.filter(
        company_id=quotation.company_id, quotation=quotation, released_at__isnull=True
    )
    for row in rows:
        item = by_id.get(row.quotation_item_id)
        quantity = Decimal(str(row.quantity or 0))
        if item is not None and Decimal(str(item.quantity or 0)) > 0:
            total += quantity / Decimal(str(item.quantity)) * _line_weight(item, by_quantity=by_quantity)
        else:
            logging.getLogger("bizboard.quotations").warning(
                "live quotation conversion row %s has no usable quote line; using row value", row.pk
            )
            total += quantity if by_quantity else quantity * Decimal(str(row.unit_price or 0))
    return total


def header_shares(quotation, plan) -> tuple[Decimal, Decimal]:
    """(additional_charges, invoice_discount) for a document converting ``plan``.

    Cumulative: amount = round(T x after) - round(T x before), where before/after
    are the converted fractions of the quote's value without/with this plan. The
    documents therefore add up to the quote, to the paisa, however it is split;
    released conversions drop out of ``before`` so their share is picked up again.
    """
    charges = Decimal(str(quotation.additional_charges or 0))
    discount = Decimal(str(quotation.invoice_discount or 0))
    if charges == 0 and discount == 0:
        return Decimal("0.00"), Decimal("0.00")
    items = list(quotation.items.all())
    by_quantity = all(_line_weight(item, by_quantity=False) == 0 for item in items)
    whole = sum((_line_weight(item, by_quantity=by_quantity) for item in items), Decimal("0"))
    if whole <= 0:
        return _q2(charges), _q2(discount)
    before = min(_converted_weight(quotation, items, by_quantity=by_quantity) / whole, Decimal("1"))
    plan_weight = Decimal("0")
    for item, quantity in plan:
        line_qty = Decimal(str(item.quantity or 0))
        if line_qty > 0:
            plan_weight += Decimal(str(quantity)) / line_qty * _line_weight(item, by_quantity=by_quantity)
    after = min(before + plan_weight / whole, Decimal("1"))
    share_charges = _q2(charges * after) - _q2(charges * before)
    share_discount = _q2(discount * after) - _q2(discount * before)
    # A discount can never exceed the value it is taken from.
    plan_value = sum(
        (
            Decimal(str(quantity)) * Decimal(str(item.unit_price or 0))
            * (Decimal("100") - Decimal(str(item.discount_percent or 0))) / Decimal("100")
            for item, quantity in plan
        ),
        Decimal("0"),
    )
    if not by_quantity:
        share_discount = min(share_discount, _q2(plan_value))
    return max(share_charges, Decimal("0.00")), max(share_discount, Decimal("0.00"))

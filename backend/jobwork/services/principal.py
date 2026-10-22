"""Job work IN: we process a customer's material (MFG-26).

The principal's material is never ours: it is not in stock, not valued, not in any ledger of ours.
This is a plain quantity book per principal and item, with challans for what comes in and goes back.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.services.audit import AuditService
from masters.models import Customer, Product

from jobwork.models import JobWorkChallan, JobWorkChallanLine, JobWorkOrder, PrincipalMaterialMovement

from . import common
from .common import d, rule

K = PrincipalMaterialMovement.Kind


def _fk(model, company, value):
    found = model.objects.filter(pk=getattr(value, "pk", value), company=company).first() if value else None
    if found is None:
        raise rule("That record was not found.", "JW_BAD_REFERENCE")
    return found


@transaction.atomic
def create_order(company, user, *, customer, process="", notes="") -> JobWorkOrder:
    customer = _fk(Customer, company, customer)
    return JobWorkOrder.objects.create(
        company=company, direction=JobWorkOrder.Direction.IN, customer=customer,
        number=common.number(company, "jobwork_order", "JWI"), process=process[:200], notes=notes[:500],
        created_by=user, updated_by=user,
    )


def balance(company, principal=None, product=None) -> list[dict]:
    """Quantity of each principal's items in our hands, from the book (reversed entries left out)."""
    qs = PrincipalMaterialMovement.objects.filter(company=company, reversed=False)
    if principal is not None:
        qs = qs.filter(principal=principal)
    if product is not None:
        qs = qs.filter(product=product)
    rows = qs.values("principal_id", "principal__name", "product_id", "product__name").annotate(qty=Sum("qty"))
    return sorted(
        [
            {
                "principal": r["principal_id"], "principal_name": r["principal__name"], "product": r["product_id"],
                "product_name": r["product__name"], "qty": d(r["qty"]),
            }
            for r in rows if d(r["qty"]) != 0
        ],
        key=lambda r: (r["principal_name"], r["product_name"]),
    )


def on_hand(company, principal, product) -> Decimal:
    agg = PrincipalMaterialMovement.objects.filter(
        company=company, principal=principal, product=product, reversed=False,
    ).aggregate(t=Sum("qty"))
    return d(agg["t"])


def _record(company, user, *, principal, product, kind, qty, when, order=None, challan=None, work_order_id=None,
            reference=""):
    """One entry in the book. ``qty`` is the size of the movement; the sign follows the kind."""
    sign = 1 if kind in (K.RECEIVED, K.PRODUCED) else -1
    if sign < 0 and on_hand(company, principal, product) < d(qty):
        raise rule(
            f"Only {on_hand(company, principal, product)} of '{product.name}' belonging to {principal.name} is here.",
            "JW_PRINCIPAL_SHORT",
        )
    return PrincipalMaterialMovement.objects.create(
        company=company, principal=principal, product=product, kind=kind, qty=sign * d(qty), move_date=when,
        order=order, challan=challan, work_order_id=work_order_id, reference=reference[:64],
        created_by=user, updated_by=user,
    )


def _challan(order, user, lines, when, *, purpose, vehicle_no="", notes=""):
    company = order.company
    ch = JobWorkChallan.objects.create(
        company=company, order=order, challan_date=when, status=JobWorkChallan.Status.ISSUED,
        number=common.number(company, "jobwork_challan", "JWC"), posted_at=timezone.now(), purpose=purpose,
        vehicle_no=vehicle_no[:20], notes=notes[:500], created_by=user, updated_by=user,
    )
    for ln in lines:
        JobWorkChallanLine.objects.create(
            challan=ch, company=company, product=ln["product"], qty=ln["qty"],
            goods_kind=ln.get("goods_kind") or JobWorkChallanLine.GoodsKind.INPUT, unit_cost=None,
        )
    return ch


def _lines(company, lines):
    out = []
    for ln in lines:
        product = _fk(Product, company, ln.get("product"))
        qty = d(ln.get("qty"))
        if qty <= 0:
            raise rule("Quantity must be above zero.", "JW_BAD_QTY")
        out.append({"product": product, "qty": qty, "goods_kind": ln.get("goods_kind")})
    if not out:
        raise rule("A challan needs at least one line.", "JW_EMPTY_DOC")
    return out


def _open_in(order):
    order = JobWorkOrder.objects.select_for_update().get(pk=order.pk)
    if order.direction != JobWorkOrder.Direction.IN:
        raise rule("This is a job work order for material we send out.", "JW_WRONG_DIRECTION")
    if order.status != JobWorkOrder.Status.OPEN:
        raise rule("This job work order is closed.", "JW_ORDER_CLOSED")
    return order


@transaction.atomic
def receive_material(order, user, lines, *, challan_date=None, vehicle_no="", notes=""):
    """The principal's material arrives under their challan. Nothing is valued; the book goes up."""
    order = _open_in(order)
    company = order.company
    when = challan_date or timezone.localdate()
    lines = _lines(company, lines)
    ch = _challan(order, user, lines, when, purpose="Received for job work", vehicle_no=vehicle_no, notes=notes)
    for ln in lines:
        _record(
            company, user, principal=order.customer, product=ln["product"], kind=K.RECEIVED, qty=ln["qty"],
            when=when, order=order, challan=ch, reference=ch.number,
        )
    AuditService.log(
        action="jobwork.principal.received", company=company, user=user, entity_type="JobWorkChallan",
        entity_id=str(ch.pk), description=f"{ch.number} from {order.customer.name}",
    )
    return ch


@transaction.atomic
def return_material(order, user, lines, *, challan_date=None, vehicle_no="", notes=""):
    """Processed goods, unused material or scrap goes back to the principal under our challan."""
    order = _open_in(order)
    company = order.company
    when = challan_date or timezone.localdate()
    lines = _lines(company, lines)
    ch = _challan(order, user, lines, when, purpose="Returned after job work", vehicle_no=vehicle_no, notes=notes)
    for ln in lines:
        _record(
            company, user, principal=order.customer, product=ln["product"], kind=K.RETURNED, qty=ln["qty"],
            when=when, order=order, challan=ch, reference=ch.number,
        )
    AuditService.log(
        action="jobwork.principal.returned", company=company, user=user, entity_type="JobWorkChallan",
        entity_id=str(ch.pk), description=f"{ch.number} to {order.customer.name}",
    )
    return ch


@transaction.atomic
def record_loss(order, user, *, product, qty, when=None, reference=""):
    """Scrap or waste of the principal's material in processing."""
    order = _open_in(order)
    return _record(
        order.company, user, principal=order.customer, product=_fk(Product, order.company, product), kind=K.LOSS,
        qty=qty, when=when or timezone.localdate(), order=order, reference=reference,
    )


def consume(company, user, *, principal, product, qty, when, work_order_id, reference):
    """A work order uses the principal's material."""
    return _record(
        company, user, principal=principal, product=product, kind=K.CONSUMED, qty=qty, when=when,
        work_order_id=work_order_id, reference=reference,
    )


def produce(company, user, *, principal, product, qty, when, work_order_id, reference):
    """Processed goods made from the principal's material are now ready to go back."""
    return _record(
        company, user, principal=principal, product=product, kind=K.PRODUCED, qty=qty, when=when,
        work_order_id=work_order_id, reference=reference,
    )


def reverse_reference(company, work_order_id, reference):
    """Take back what a reversed work-order document wrote to the book."""
    return PrincipalMaterialMovement.objects.filter(
        company=company, work_order_id=work_order_id, reference=reference, reversed=False,
    ).update(reversed=True)

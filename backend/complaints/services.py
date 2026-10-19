from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.flag_observability import log_flag_event
from core.services.sequences import next_number

from .models import Complaint, SupplierComplaint

_ALLOWED = {
    Complaint.Status.OPEN: {Complaint.Status.INSPECTING},
    Complaint.Status.INSPECTING: {Complaint.Status.APPROVED, Complaint.Status.REJECTED},
    Complaint.Status.APPROVED: {Complaint.Status.RESOLVED},
    Complaint.Status.REJECTED: set(),
    Complaint.Status.RESOLVED: set(),
}
_DOC_STATUSES = {Complaint.Status.APPROVED}


def create_complaint(company, user, *, customer, category, description, source_invoice=None):
    with transaction.atomic():
        row = Complaint.objects.create(
            company=company,
            customer=customer,
            category=category,
            description=description,
            source_invoice=source_invoice,
            number=next_number(company, "COMPLAINT", prefix="RMA"),
            created_by=user,
            updated_by=user,
        )
    log_flag_event(company, "ENABLE_COMPLAINTS", "complaint_created", complaint_id=row.id)
    return row


_POSTED_CUSTOMER_DOCS = {
    "sales_return": {"COMPLETED"},
    "sales_credit_note": {"COMPLETED"},
    "replacement_order": {"CONFIRMED", "CONVERTED"},
}


def _assert_posted(complaint, specs):
    for attr, posted in specs.items():
        document = getattr(complaint, attr, None)
        if document is not None and document.status not in posted:
            raise BusinessRuleError(
                "Complete the linked document before resolving the complaint."
            )


def _clean(value):
    return str(value).strip() if value is not None else None


def _assert_outcome_reasons(complaint, new_status, inspection_notes, resolution_note, documents):
    """A rejection needs its reason; a resolution with no remedy document needs a written one (CMP-03/04)."""
    notes = inspection_notes if inspection_notes is not None else complaint.inspection_notes
    note = resolution_note if resolution_note is not None else complaint.resolution_note
    if new_status == "REJECTED" and not (notes or "").strip():
        raise BusinessRuleError("Write the reason in the inspection notes before rejecting a complaint.")
    if new_status == "RESOLVED" and not any(documents) and not (note or "").strip():
        raise BusinessRuleError(
            "No remedy document is linked. Add a resolution note explaining how this was settled."
        )


def transition_status(complaint, user, *, new_status, inspection_notes=None, resolution_note=None):
    inspection_notes = _clean(inspection_notes)
    resolution_note = _clean(resolution_note)
    with transaction.atomic():
        complaint = Complaint.objects.select_for_update().get(pk=complaint.pk)
        allowed = _ALLOWED.get(complaint.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(f"Cannot move a complaint from {complaint.status} to {new_status}.")
        if new_status == Complaint.Status.RESOLVED:
            _assert_posted(complaint, _POSTED_CUSTOMER_DOCS)
        _assert_outcome_reasons(
            complaint, new_status, inspection_notes, resolution_note,
            [complaint.sales_return_id, complaint.sales_credit_note_id, complaint.replacement_order_id],
        )
        return _write_status(
            complaint, user, new_status=new_status, inspection_notes=inspection_notes,
            resolution_note=resolution_note, action="complaint_status", entity_type="Complaint",
        )


def save_notes(complaint, user, inspection_notes):
    """Save inspection notes without moving the status, so typed notes are never lost (CMP-08)."""
    with transaction.atomic():
        row = type(complaint).objects.select_for_update().get(pk=complaint.pk)
        if row.status in _CLOSED:
            raise BusinessRuleError("A closed complaint cannot be changed.")
        row.inspection_notes = _clean(inspection_notes) or ""
        row.updated_by = user
        row.save(update_fields=["inspection_notes", "updated_by", "updated_at"])
        AuditService.log(
            action="complaint_notes", company=row.company, user=user,
            entity_type=type(row).__name__, entity_id=row.pk, metadata={},
        )
    return row


def _write_status(
    complaint, user, *, new_status, inspection_notes, action, entity_type, resolution_note=None,
):
    complaint.status = new_status
    if inspection_notes is not None:
        complaint.inspection_notes = inspection_notes
    if resolution_note is not None:
        complaint.resolution_note = resolution_note
    fields = ["status", "inspection_notes", "resolution_note", "updated_by", "updated_at"]
    if new_status == "RESOLVED":
        complaint.resolved_at = timezone.now()
        fields.append("resolved_at")
    complaint.updated_by = user
    complaint.save(update_fields=fields)
    AuditService.log(
        action=action,
        company=complaint.company,
        user=user,
        entity_type=entity_type,
        entity_id=complaint.pk,
        metadata={"status": new_status},
    )
    return complaint


def assert_document_status(complaint):
    if complaint.status not in _DOC_STATUSES:
        raise BusinessRuleError("Create a document only after the complaint is approved.")


_SUPPLIER_ALLOWED = {
    SupplierComplaint.Status.OPEN: {SupplierComplaint.Status.INSPECTING},
    SupplierComplaint.Status.INSPECTING: {SupplierComplaint.Status.APPROVED, SupplierComplaint.Status.REJECTED},
    SupplierComplaint.Status.APPROVED: {SupplierComplaint.Status.RESOLVED},
    SupplierComplaint.Status.REJECTED: set(),
    SupplierComplaint.Status.RESOLVED: set(),
}


def create_supplier_complaint(company, user, *, supplier, category, description, source_invoice=None):
    with transaction.atomic():
        row = SupplierComplaint.objects.create(
            company=company,
            supplier=supplier,
            category=category,
            description=description,
            source_invoice=source_invoice,
            number=next_number(company, "SUPPLIER_COMPLAINT", prefix="SCN"),
            created_by=user,
            updated_by=user,
        )
    log_flag_event(company, "ENABLE_COMPLAINTS", "supplier_complaint_created", complaint_id=row.id)
    return row


def transition_supplier_status(complaint, user, *, new_status, inspection_notes=None, resolution_note=None):
    inspection_notes = _clean(inspection_notes)
    resolution_note = _clean(resolution_note)
    with transaction.atomic():
        complaint = SupplierComplaint.objects.select_for_update().get(pk=complaint.pk)
        allowed = _SUPPLIER_ALLOWED.get(complaint.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(f"Cannot move a supplier complaint from {complaint.status} to {new_status}.")
        if new_status == SupplierComplaint.Status.RESOLVED:
            _assert_posted(complaint, {"purchase_debit_note": {"COMPLETED"}})
        _assert_outcome_reasons(
            complaint, new_status, inspection_notes, resolution_note, [complaint.purchase_debit_note_id],
        )
        return _write_status(
            complaint, user, new_status=new_status, inspection_notes=inspection_notes,
            resolution_note=resolution_note, action="supplier_complaint_status",
            entity_type="SupplierComplaint",
        )


_CUSTOMER_DOC_ATTRS = ("sales_return", "sales_credit_note", "replacement_order")
_SUPPLIER_DOC_ATTRS = ("purchase_debit_note",)
_CLOSED = {"RESOLVED", "REJECTED"}


def unlink_document(complaint, user, attr):
    """Detach a cancelled remedy document so a replacement can be created.

    A cancelled return or credit note can never satisfy the "complete the linked document"
    rule, so without this the complaint would be stuck for good.
    """
    allowed = _SUPPLIER_DOC_ATTRS if isinstance(complaint, SupplierComplaint) else _CUSTOMER_DOC_ATTRS
    if attr not in allowed:
        raise BusinessRuleError("Unknown document.")
    with transaction.atomic():
        row = type(complaint).objects.select_for_update().get(pk=complaint.pk)
        if row.status in _CLOSED:
            raise BusinessRuleError("A closed complaint cannot be changed.")
        document = getattr(row, attr)
        if document is None:
            raise BusinessRuleError("No document is linked.")
        if document.status != "CANCELLED":
            raise BusinessRuleError("Only a cancelled document can be unlinked. Cancel it first.")
        setattr(row, attr, None)
        row.updated_by = user
        row.save(update_fields=[attr, "updated_by", "updated_at"])
        AuditService.log(
            action="complaint_document_unlinked",
            company=row.company,
            user=user,
            entity_type=type(row).__name__,
            entity_id=row.pk,
            metadata={"document": attr, "document_id": document.pk},
        )
    return row


def _quantity(raw):
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise BusinessRuleError("Quantity must be a number.") from None
    if value <= 0:
        raise BusinessRuleError("Quantity must be greater than zero.")
    return value


def assert_within_returnable(invoice, items):
    """Refuse a return or credit note line that asks for more than can still be returned (CMP-06).

    Uses the same per-line figures as the sales-return screen, so a complaint document and a
    return made there can never both claim the same units.
    """
    from collections import defaultdict
    from decimal import Decimal

    from sales.return_service import ReturnService

    rows = ReturnService.returnable_lines(invoice)
    by_line = {row["source_item"]: row for row in rows}
    by_product = defaultdict(list)
    for row in rows:
        by_product[row["product"]].append(row)
    used = defaultdict(Decimal)
    for item in items:
        qty = _quantity(item.get("quantity"))
        source = item.get("source_item")
        if source not in (None, ""):
            row = by_line.get(int(source))
            if row is None:
                raise BusinessRuleError("That line is not on the source invoice.")
        else:
            candidates = by_product.get(int(item.get("product") or 0), [])
            if not candidates:
                raise BusinessRuleError("That product is not on the source invoice.")
            if len(candidates) > 1:
                raise BusinessRuleError("Pick the invoice line: the product is on more than one line.")
            row = candidates[0]
        key = row["source_item"]
        used[key] += qty
        if used[key] > row["returnable"]:
            raise BusinessRuleError(
                f"Only {row['returnable'].normalize():f} of {row['product_name']} can still be returned "
                f"from this invoice."
            )


def assert_within_billed(purchase_invoice, items):
    """A debit note cannot ask for more of a product than the bill carried."""
    from collections import defaultdict
    from decimal import Decimal

    billed = defaultdict(Decimal)
    names = {}
    for row in purchase_invoice.items.select_related("product"):
        billed[row.product_id] += Decimal(str(row.quantity))
        names[row.product_id] = row.product.name
    asked = defaultdict(Decimal)
    for item in items:
        product = int(item.get("product") or 0)
        if product not in billed:
            raise BusinessRuleError("That product is not on the source bill.")
        asked[product] += _quantity(item.get("quantity"))
        if asked[product] > billed[product]:
            raise BusinessRuleError(
                f"The bill carried only {billed[product].normalize():f} of {names[product]}."
            )

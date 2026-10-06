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


def transition_status(complaint, user, *, new_status, inspection_notes=None):
    with transaction.atomic():
        complaint = Complaint.objects.select_for_update().get(pk=complaint.pk)
        allowed = _ALLOWED.get(complaint.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(f"Cannot move a complaint from {complaint.status} to {new_status}.")
        if new_status == Complaint.Status.RESOLVED:
            _assert_posted(complaint, _POSTED_CUSTOMER_DOCS)
        return _write_status(
            complaint, user, new_status=new_status, inspection_notes=inspection_notes,
            action="complaint_status", entity_type="Complaint",
        )


def _write_status(complaint, user, *, new_status, inspection_notes, action, entity_type):
    complaint.status = new_status
    if inspection_notes is not None:
        complaint.inspection_notes = inspection_notes
    fields = ["status", "inspection_notes", "updated_by", "updated_at"]
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


def transition_supplier_status(complaint, user, *, new_status, inspection_notes=None):
    with transaction.atomic():
        complaint = SupplierComplaint.objects.select_for_update().get(pk=complaint.pk)
        allowed = _SUPPLIER_ALLOWED.get(complaint.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(f"Cannot move a supplier complaint from {complaint.status} to {new_status}.")
        if new_status == SupplierComplaint.Status.RESOLVED:
            _assert_posted(complaint, {"purchase_debit_note": {"COMPLETED"}})
        return _write_status(
            complaint, user, new_status=new_status, inspection_notes=inspection_notes,
            action="supplier_complaint_status", entity_type="SupplierComplaint",
        )

"""One call that lists a record's neighbours across care, jobs and contracts (XLK-03/04)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .care import CareSalesAccess
from .permissions import HasCompany, get_company_user

LIMIT = 20


def _item(kind, row, href, number=None, status=None, label=""):
    return {
        "kind": kind,
        "id": row.pk,
        "number": number if number is not None else (getattr(row, "number", "") or f"#{row.pk}"),
        "status": status if status is not None else getattr(row, "status", ""),
        "href": href,
        "label": label,
    }


def _ticket(row):
    return _item("ticket", row, f"/support/tickets/{row.pk}", label=row.subject)


def _complaint(row):
    return _item("complaint", row, f"/complaints/{row.pk}", label=row.description[:80])


def _job(row):
    return _item("job_card", row, f"/workshop/jobs/{row.pk}", label=row.registration_no or row.complaint[:80])


def _contract(row):
    return _item("contract", row, f"/contracts/{row.pk}", label=row.contract_type)


def _project(row):
    return _item("project", row, f"/projects/{row.pk}", label=row.name)


def _invoice(row):
    return _item("invoice", row, f"/sales/history/{row.pk}")


def links_for(company, entity, pk):
    from complaints.models import Complaint
    from contracts.models import Contract
    from projects.models import Project, ProjectMilestone
    from sales.models import SalesInvoice
    from support.models import Ticket
    from workshop.models import JobCard

    out = []
    if entity == "ticket":
        row = Ticket.objects.select_related("source_invoice", "contract").filter(company=company, pk=pk).first()
        if row is None:
            return None
        if row.source_invoice:
            out.append(_invoice(row.source_invoice))
        if row.contract:
            out.append(_contract(row.contract))
        out += [_complaint(x) for x in Complaint.objects.filter(company=company, ticket=row)[:LIMIT]]
        out += [_job(x) for x in JobCard.objects.filter(company=company, ticket=row)[:LIMIT]]
    elif entity == "complaint":
        row = Complaint.objects.select_related("source_invoice", "ticket").filter(company=company, pk=pk).first()
        if row is None:
            return None
        if row.source_invoice:
            out.append(_invoice(row.source_invoice))
        if row.ticket:
            out.append(_ticket(row.ticket))
        out += [_job(x) for x in JobCard.objects.filter(company=company, source_complaint=row)[:LIMIT]]
        if row.sales_credit_note_id:
            out.append(_item(
                "credit_note", row.sales_credit_note, f"/sales/credit-notes/{row.sales_credit_note_id}",
            ))
        if row.sales_return_id:
            out.append(_item("sales_return", row.sales_return, "/sales/returns"))
        if row.replacement_order_id:
            out.append(_item("sales_order", row.replacement_order, f"/sales/orders/{row.replacement_order_id}"))
    elif entity == "supplier_complaint":
        from complaints.models import SupplierComplaint

        row = SupplierComplaint.objects.select_related("source_invoice", "purchase_debit_note").filter(
            company=company, pk=pk,
        ).first()
        if row is None:
            return None
        if row.source_invoice:
            out.append(_item(
                "purchase_bill", row.source_invoice, f"/purchases/invoices/{row.source_invoice_id}",
                label=row.source_invoice.supplier.name,
            ))
        if row.purchase_debit_note:
            out.append(_item(
                "debit_note", row.purchase_debit_note, f"/purchases/debit-notes/{row.purchase_debit_note_id}",
            ))
    elif entity == "contract":
        row = Contract.objects.filter(company=company, pk=pk).first()
        if row is None:
            return None
        out += [_ticket(x) for x in Ticket.objects.filter(company=company, contract=row)[:LIMIT]]
        out += [_job(x) for x in JobCard.objects.filter(company=company, contract=row)[:LIMIT]]
        out += [_project(x) for x in Project.objects.filter(company=company, contract=row)[:LIMIT]]
    elif entity == "job_card":
        row = JobCard.objects.select_related("ticket", "source_complaint", "contract", "sales_invoice").filter(
            company=company, pk=pk,
        ).first()
        if row is None:
            return None
        for related, make in ((row.ticket, _ticket), (row.source_complaint, _complaint),
                              (row.contract, _contract), (row.sales_invoice, _invoice)):
            if related is not None:
                out.append(make(related))
    elif entity == "project":
        row = Project.objects.select_related("contract").filter(company=company, pk=pk).first()
        if row is None:
            return None
        if row.contract:
            out.append(_contract(row.contract))
        milestones = ProjectMilestone.objects.filter(project=row, sales_invoice__isnull=False).select_related(
            "sales_invoice",
        )
        out += [_invoice(m.sales_invoice) for m in milestones[:LIMIT]]
    elif entity == "invoice":
        row = SalesInvoice.objects.filter(company=company, pk=pk).first()
        if row is None:
            return None
        out += [_ticket(x) for x in Ticket.objects.filter(company=company, source_invoice=row)[:LIMIT]]
        out += [_complaint(x) for x in Complaint.objects.filter(company=company, source_invoice=row)[:LIMIT]]
        out += [_job(x) for x in JobCard.objects.filter(company=company, sales_invoice=row)[:LIMIT]]
        out += [_project(m.project) for m in ProjectMilestone.objects.filter(
            sales_invoice=row).select_related("project")[:LIMIT]]
    elif entity == "customer":
        open_ticket = [Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING]
        out += [_ticket(x) for x in Ticket.objects.filter(
            company=company, customer_id=pk, status__in=open_ticket)[:LIMIT]]
        out += [_complaint(x) for x in Complaint.objects.filter(company=company, customer_id=pk).exclude(
            status__in=("RESOLVED", "REJECTED"))[:LIMIT]]
        out += [_job(x) for x in JobCard.objects.filter(company=company, customer_id=pk).exclude(
            status__in=(JobCard.Status.CANCELLED, JobCard.Status.INVOICED))[:LIMIT]]
        out += [_contract(x) for x in Contract.objects.filter(company=company, customer_id=pk).exclude(
            status=Contract.Status.CANCELLED)[:LIMIT]]
        out += [_project(x) for x in Project.objects.filter(
            company=company, customer_id=pk, status=Project.Status.OPEN)[:LIMIT]]
    else:
        return None
    return out


class CareLinksView(APIView):
    """GET /links/?entity=ticket&id=12 — the records connected to this one."""

    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]

    def get(self, request):
        entity = (request.query_params.get("entity") or "").strip()
        raw_id = (request.query_params.get("id") or "").strip()
        if not raw_id.isdigit():
            return Response({"detail": "Give the record id."}, status=400)
        company = get_company_user(request).company
        rows = links_for(company, entity, int(raw_id))
        if rows is None:
            return Response({"detail": "Record not found."}, status=404)
        return Response(rows)

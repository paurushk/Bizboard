"""Service-quality figures for the owner: tickets, complaints, workshop and projects (XLK-06)."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .care import CareSalesAccess
from .permissions import HasCompany, get_company_user
from .services.feature_flags import flag_enabled


def _seconds(value):
    return None if value is None else int(value.total_seconds())


def _tickets(company, since):
    from support.models import Ticket

    rows = Ticket.objects.filter(company=company, created_at__gte=since)
    done = rows.filter(resolved_at__isnull=False)
    duration = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
    finished = done.count()
    met = done.filter(resolved_at__lte=F("sla_due_at")).count()
    return {
        "opened": rows.count(),
        "resolved": finished,
        "sla_met": met,
        "sla_met_percent": int(round(met * 100 / finished)) if finished else None,
        "average_resolution_seconds": _seconds(done.aggregate(avg=Avg(duration))["avg"]),
        "open_now": Ticket.objects.filter(
            company=company, status__in=["OPEN", "IN_PROGRESS", "WAITING"],
        ).count(),
    }


def _complaints(company, since):
    from complaints.models import Complaint, SupplierComplaint
    from sales.models import SalesItem

    customer = Complaint.objects.filter(company=company, created_at__gte=since)
    supplier = SupplierComplaint.objects.filter(company=company, created_at__gte=since)
    # A product that keeps coming back: complaints whose source invoice carries it.
    repeats = (
        SalesItem.objects.filter(invoice__in=customer.exclude(source_invoice=None).values("source_invoice"))
        .values("product", "product__name")
        .annotate(complaints=Count("invoice__complaints", distinct=True))
        .filter(complaints__gt=1)
        .order_by("-complaints")[:10]
    )
    return {
        "customer_total": customer.count(),
        "customer_resolved": customer.filter(status="RESOLVED").count(),
        "customer_rejected": customer.filter(status="REJECTED").count(),
        "supplier_total": supplier.count(),
        "repeat_products": [
            {"product": row["product"], "name": row["product__name"], "complaints": row["complaints"]}
            for row in repeats
        ],
        "by_supplier": list(
            supplier.values("supplier", "supplier__name").annotate(count=Count("id")).order_by("-count")[:10]
        ),
    }


def _workshop(company, since):
    from workshop.models import JobCard, JobCardLine

    jobs = JobCard.objects.filter(company=company, created_at__gte=since)
    lines = JobCardLine.objects.filter(company=company, job__in=jobs)
    free = lines.filter(covered_by_contract=True).aggregate(
        value=Sum(F("quantity") * F("product__selling_price")),
    )["value"] or Decimal("0")
    return {
        "jobs": jobs.count(),
        "invoiced": jobs.filter(status=JobCard.Status.INVOICED).count(),
        "with_contract": jobs.exclude(contract=None).count(),
        "free_lines": lines.filter(covered_by_contract=True).count(),
        "paid_lines": lines.filter(covered_by_contract=False).count(),
        "warranty_cost_at_list_price": str(Decimal(free).quantize(Decimal("0.01"))),
    }


def _projects(company):
    from projects.models import Project, ProjectMilestone

    open_projects = Project.objects.filter(company=company, status=Project.Status.OPEN)
    milestones = ProjectMilestone.objects.filter(project__in=open_projects)
    planned = milestones.aggregate(v=Sum("amount"))["v"] or Decimal("0")
    invoiced = milestones.filter(status=ProjectMilestone.Status.INVOICED).aggregate(v=Sum("amount"))["v"] or Decimal("0")
    return {
        "open_projects": open_projects.count(),
        "planned_total": str(Decimal(planned).quantize(Decimal("0.01"))),
        "invoiced_total": str(Decimal(invoiced).quantize(Decimal("0.01"))),
        "overdue_milestones": milestones.filter(
            target_completion_date__lt=timezone.localdate(),
        ).exclude(status=ProjectMilestone.Status.INVOICED).count(),
    }


class CareKpiView(APIView):
    """GET /care-kpis/?days=90"""

    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]

    def get(self, request):
        raw = request.query_params.get("days") or "90"
        days = int(raw) if str(raw).isdigit() and 0 < int(raw) <= 730 else 90
        company = get_company_user(request).company
        since = timezone.now() - timedelta(days=days)
        data = {"days": days}
        if flag_enabled(company, "ENABLE_SUPPORT_TICKETS"):
            data["tickets"] = _tickets(company, since)
        if flag_enabled(company, "ENABLE_COMPLAINTS"):
            data["complaints"] = _complaints(company, since)
        if flag_enabled(company, "ENABLE_WORKSHOP"):
            data["workshop"] = _workshop(company, since)
        if flag_enabled(company, "ENABLE_PROJECTS"):
            data["projects"] = _projects(company)
        if flag_enabled(company, "ENABLE_CONTRACTS"):
            from contracts.models import Contract

            today = timezone.localdate()
            live = Contract.objects.filter(company=company, end_date__gte=today).exclude(status="CANCELLED")
            data["contracts"] = {
                "live": live.count(),
                "expiring": live.filter(expiring_from_date__lte=today).count(),
                "expired": Contract.objects.filter(company=company, end_date__lt=today).exclude(
                    status="CANCELLED").count(),
            }
        return Response(data)


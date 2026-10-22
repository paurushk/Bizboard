"""Staff pages in Django admin for the SaaS controls that were command-only (WP-AB1, WP-PO2).

- ``/admin/ops/sms-guard/``: today's platform SMS count against the cap, and the kill switch
  (superusers only can flip it; every flip is audited).
- ``/admin/ops/saas-metrics/``: the month's SaaS numbers (``support.health.monthly_metrics``) and
  the median days to first invoice by sign-up week (WP-GR2).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone


def sms_guard_view(request):
    from core.services import sms_guard
    from core.services.audit import AuditService

    if request.method == "POST":
        if not request.user.is_superuser:
            raise PermissionDenied
        turn_on = request.POST.get("kill") == "on"
        sms_guard.set_kill_switch(turn_on)
        AuditService.log(
            action="ops.sms_kill_switch", user=request.user, entity_type="SmsGuard", entity_id=0,
            description=f"SMS kill switch turned {'on' if turn_on else 'off'} from admin.",
        )
        messages.success(request, f"SMS kill switch is now {'ON — no SMS will be sent' if turn_on else 'off'}.")
        return redirect("admin:ops_sms_guard")
    return render(request, "ops/sms_guard.html", {
        "status": sms_guard.status(),
        "can_flip": request.user.is_superuser,
        "title": "SMS spend guard",
    })


def saas_metrics_view(request):
    from core.rls import rls_bypass
    from support.health import monthly_metrics, time_to_first_invoice_by_week

    month = (request.GET.get("month") or timezone.localdate().strftime("%Y-%m")).strip()[:7]
    try:
        with rls_bypass():
            data = monthly_metrics(month)
            weeks = time_to_first_invoice_by_week(month)
    except ValueError:
        messages.error(request, "Month must look like 2026-10.")
        return redirect("admin:ops_saas_metrics")
    rows = [(key.replace("_", " "), "—" if value is None else value) for key, value in data.items()]
    return render(request, "ops/saas_metrics.html", {
        "month": month, "rows": rows, "weeks": weeks, "title": "SaaS numbers",
    })


def support_view(request, grant_id: int):
    """WP-ID4: ``/admin/ops/support-view/<grant>/`` — the read-only look at a tenant under a live grant.

    GET only; any other method is refused before anything is read (``SUPPORT_READ_ONLY``)."""
    from django.http import HttpResponseForbidden

    from support.access import SECTIONS, usable_grant, view_section

    if request.method not in ("GET", "HEAD"):
        return HttpResponseForbidden("SUPPORT_READ_ONLY: support access is read-only.")
    grant = usable_grant(grant_id, request.user)
    if grant is None:
        return HttpResponseForbidden("No live support access grant for you on this company.")
    section = request.GET.get("section") or "customers"
    if section not in SECTIONS:
        section = "customers"
    query = request.GET.get("q") or ""
    data = view_section(grant, staff_user=request.user, section=section, query=query)
    rows = [[row.get(f) for f in data["fields"]] for row in data["rows"]]
    return render(request, "ops/support_view.html", {
        "title": f"Read-only: {grant.company.name}",
        "grant": grant, "sections": list(SECTIONS), "section": section, "q": query,
        "fields": data["fields"], "rows": rows,
    })

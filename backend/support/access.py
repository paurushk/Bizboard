"""WP-ID4: customer-approved, read-only support access (Q4, founder 2026-10-22).

The owner grants access tied to one platform ticket, for at most 72 hours, to any Bizboard support
staff member or a named one (password + two-step check, like the ownership transfer). While the
grant is live, staff open the company's data in a read-only viewer in Django admin
(``/admin/ops/support-view/<grant>/``). Each look:

- runs in its own database transaction opened ``READ ONLY`` (Postgres) / ``PRAGMA query_only``
  (SQLite), so the database refuses any write — a write is raised, never swallowed;
- has the tenant GUC set for that company only and the RLS bypass cleared, both transaction-local,
  and every query also filters on the grant's company, so no other tenant is reachable;
- is recorded in ``SupportAccessLog`` *after* the read-only transaction ends.

The owner sees every look and can revoke at once; an hourly task revokes grants that ran out
(visiting only live grants), and closing the ticket revokes its grants. There is no write path and
no "act as user": this is not impersonation (``guard_no_impersonation`` still holds).
"""

from __future__ import annotations

import contextlib
import logging
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

MAX_HOURS = 72

# section -> (model label, fields shown, fields searched by ?q=)
SECTIONS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "customers": ("masters.Customer", ("id", "name", "phone", "email", "gstin", "state", "created_at"), ("name", "phone", "gstin")),
    "suppliers": ("masters.Supplier", ("id", "name", "phone", "email", "gstin", "state", "created_at"), ("name", "phone", "gstin")),
    "products": ("masters.Product", ("id", "name", "sku", "hsn_code", "unit", "sale_price", "gst_rate", "is_active"), ("name", "sku")),
    "sales": ("sales.SalesInvoice", ("id", "number", "status", "invoice_date", "customer__name", "grand_total", "created_at"), ("number", "customer__name")),
    "purchases": ("purchases.PurchaseInvoice", ("id", "number", "status", "invoice_date", "supplier__name", "grand_total", "created_at"), ("number", "supplier__name")),
    "receipts": ("payments.CustomerReceipt", ("id", "number", "status", "receipt_date", "customer__name", "amount", "mode", "created_at"), ("number", "customer__name")),
    "supplier_payments": ("payments.SupplierPayment", ("id", "number", "status", "payment_date", "supplier__name", "amount", "mode", "created_at"), ("number", "supplier__name")),
    "activity": ("core.AuditEvent", ("created_at", "action", "entity_type", "entity_id", "description", "user__email"), ("action", "entity_type", "description")),
}


def _has_path(model, path: str) -> bool:
    current = model
    for part in path.split("__"):
        try:
            field = current._meta.get_field(part)
        except FieldDoesNotExist:
            return False
        current = getattr(field, "related_model", None) or current
    return True


def live_grants(company):
    from .models import SupportAccessGrant

    return SupportAccessGrant.objects.filter(
        company=company, revoked_at__isnull=True, expires_at__gt=timezone.now(),
    )


def grant_access(*, company, owner, ticket_id: int, hours: int = MAX_HOURS, staff_email: str = ""):
    from accounts.models import User

    from .models import PlatformTicket, SupportAccessGrant

    try:
        hours = int(hours)
    except (TypeError, ValueError):
        hours = MAX_HOURS
    if hours < 1 or hours > MAX_HOURS:
        raise BusinessRuleError(f"Access can last 1 to {MAX_HOURS} hours.", code="SUPPORT_ACCESS_HOURS")
    ticket = PlatformTicket.objects.filter(company=company, pk=ticket_id).first()
    if ticket is None or ticket.status in (PlatformTicket.Status.RESOLVED,):
        raise BusinessRuleError("Pick an open support request.", code="SUPPORT_ACCESS_TICKET")
    staff = None
    if (staff_email or "").strip():
        staff = User.objects.filter(email__iexact=staff_email.strip(), is_staff=True, is_active=True).first()
        if staff is None:
            raise BusinessRuleError("That is not a Bizboard support address.", code="SUPPORT_ACCESS_STAFF")
    grant = SupportAccessGrant.objects.create(
        company=company, ticket=ticket, granted_by=owner, staff_user=staff,
        expires_at=timezone.now() + timedelta(hours=hours), created_by=owner, updated_by=owner,
    )
    _ping_ops(grant)
    return grant


def _ping_ops(grant) -> None:
    try:
        from core.services.telegram import send_ops_alert

        send_ops_alert(
            f"Company {grant.company_id} allowed read-only support access for ticket #{grant.ticket_id} "
            f"until {timezone.localtime(grant.expires_at):%d %b %H:%M}."
        )
    except Exception:  # noqa: BLE001 - the ping is a courtesy; the grant stands
        logger.exception("support access ops ping failed for grant %s", grant.pk)


def revoke(grant, *, user=None, reason: str = "owner") -> None:
    if grant.revoked_at is not None:
        return
    grant.revoked_at = timezone.now()
    grant.revoked_by = user if getattr(user, "pk", None) else None
    grant.revoke_reason = reason[:32]
    grant.save(update_fields=["revoked_at", "revoked_by", "revoke_reason", "updated_at"])


def expire_due_grants() -> int:
    """Hourly: revoke live grants that ran out or whose ticket is closed. Visits only live rows."""
    from core.rls import rls_bypass

    from .models import PlatformTicket, SupportAccessGrant

    n = 0
    with rls_bypass():
        live = SupportAccessGrant.objects.filter(revoked_at__isnull=True).select_related("ticket")
        for grant in live:
            if grant.expires_at <= timezone.now():
                revoke(grant, reason="expired")
                n += 1
            elif grant.ticket.status in (PlatformTicket.Status.RESOLVED,):
                revoke(grant, reason="ticket_closed")
                n += 1
    return n


def usable_grant(grant_id: int, staff_user):
    """The grant if this staff user may use it right now, else None."""
    from .models import SupportAccessGrant

    from core.rls import rls_bypass

    if not (getattr(staff_user, "is_staff", False) and getattr(staff_user, "is_active", False)):
        return None
    with rls_bypass():  # staff have no tenant; the grant row itself names the one company allowed
        return (
            SupportAccessGrant.objects.filter(pk=grant_id, revoked_at__isnull=True, expires_at__gt=timezone.now())
            .filter(Q(staff_user__isnull=True) | Q(staff_user=staff_user))
            .select_related("company", "ticket")
            .first()
        )


@contextlib.contextmanager
def read_only_tenant(company_id):
    """A transaction the database itself refuses to write in, scoped to one tenant."""
    if connection.vendor == "postgresql":
        # Always rolled back at the end: nothing here may be kept, and rolling back (a savepoint
        # when inside a request's transaction) also undoes READ ONLY and the two GUCs, which
        # are transaction-local and would otherwise outlive the block until the outer commit.
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                if getattr(settings, "POSTGRES_RLS_ENABLED", False):
                    cur.execute(
                        "SELECT set_config('app.rls_bypass', '', true), set_config('app.company_id', %s, true)",
                        [str(company_id)],
                    )
            try:
                yield
            finally:
                transaction.set_rollback(True)
        return
    # SQLite (local and tests): query_only is per connection, so switch it on and off on the raw
    # connection, outside Django's transaction state — a refused write must not leave it stuck on.
    connection.ensure_connection()
    raw = connection.connection
    raw.execute("PRAGMA query_only = ON")
    try:
        with transaction.atomic():
            yield
    finally:
        raw.execute("PRAGMA query_only = OFF")


def view_section(grant, *, staff_user, section: str, query: str = "", limit: int = 100) -> dict:
    """Read one section of the grant's company. Writes the access log after the read."""
    from .models import SupportAccessLog

    if section not in SECTIONS:
        raise BusinessRuleError("Unknown section.", code="SUPPORT_ACCESS_SECTION")
    label, fields, search = SECTIONS[section]
    model = apps.get_model(label)
    fields = tuple(f for f in fields if _has_path(model, f))
    search = tuple(f for f in search if _has_path(model, f))
    query = (query or "").strip()[:100]
    with read_only_tenant(grant.company_id):
        qs = model._default_manager.filter(company_id=grant.company_id)
        if query and search:
            cond = Q()
            for f in search:
                cond |= Q(**{f"{f}__icontains": query})
            qs = qs.filter(cond)
        order = "-created_at" if _has_path(model, "created_at") else "-pk"
        rows = list(qs.order_by(order).values(*fields)[:limit])
    from core.rls import company_scope

    with company_scope(grant.company_id):
        SupportAccessLog.objects.create(
            company_id=grant.company_id, grant=grant, staff_user=staff_user, section=section,
            query=query, rows_shown=len(rows),
        )
    return {"fields": fields, "rows": rows}

"""Shared rules for the customer care and jobs & contracts screens."""

from .exceptions import BusinessRuleError

# Entity -> statuses in which attachments, comments and links are frozen (FND-14).
TERMINAL_STATUSES = {
    "Ticket": {"CLOSED"},
    "Complaint": {"RESOLVED", "REJECTED"},
    "SupplierComplaint": {"RESOLVED", "REJECTED"},
    "Contract": {"CANCELLED", "EXPIRED"},
}


def assert_mutable(instance, what="This record"):
    """Refuse a comment, attachment upload or attachment delete on a finished record."""
    kind = type(instance).__name__
    status = getattr(instance, "status", "")
    if kind == "Contract":
        # The cached status can lag the dates; judge by what a reader would see.
        from django.utils import timezone

        from contracts.status import effective_contract_status

        status = effective_contract_status(
            instance.status, instance.end_date, instance.renewal_reminder_days, timezone.localdate(),
        )
    if status in TERMINAL_STATUSES.get(kind, ()):
        raise BusinessRuleError(f"{what} is {str(status).lower()}. Re-open or renew it before changing it.")


def notify_member(company, member, *, subject, body, user=None):
    """In-app note for one company member; a failed note must never undo the action behind it."""
    try:
        from core.models import Notification
        from core.services.notifications import NotificationService

        email = getattr(getattr(member, "user", None), "email", "") if member is not None else ""
        NotificationService.send(
            company=company,
            channel=Notification.Channel.IN_APP,
            recipient=email or "in-app",
            subject=subject[:255],
            body=body,
            user=user,
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("care notification failed", exc_info=True)


def _care_permission(write_permission):
    from rest_framework.permissions import SAFE_METHODS, BasePermission

    from .permissions import get_company_user

    class _CareAccess(BasePermission):
        """Any active member (a VIEWER included) may read; changing needs the module's own right."""

        message = write_permission.message if hasattr(write_permission, "message") else "Permission required."

        def has_permission(self, request, view):
            if get_company_user(request) is None:
                return False
            if request.method in SAFE_METHODS:
                return True
            return write_permission().has_permission(request, view)

    return _CareAccess


def _build_access():
    from .permissions import CanCreatePurchases, CanCreateSales

    return _care_permission(CanCreateSales), _care_permission(CanCreatePurchases)


CareSalesAccess, CarePurchaseAccess = _build_access()

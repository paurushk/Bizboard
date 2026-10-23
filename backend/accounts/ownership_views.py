"""WP-ID1: owner transfer API (accounts/ownership.py has the rules).

POST /api/v1/company/ownership/transfer/   owner; body {to_user_id, old_owner_becomes, password, code?}
POST /api/v1/company/ownership/accept/     the invited member; body {token}
POST /api/v1/company/ownership/cancel/     any current owner; cancels a pending transfer or recovery
GET  /api/v1/company/ownership/            pending transfer/recovery for this company, if any
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, IsOwner, get_company_user


def _row(t):
    if t is None:
        return None
    return {
        "id": t.pk, "kind": t.kind, "status": t.status,
        "to_email": getattr(t.to_user, "email", "") or t.recovery_email,
        "expires_at": t.expires_at, "effective_at": t.effective_at,
    }


class OwnershipView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from .models import OwnershipTransfer

        cu = get_company_user(request)
        pending = _live_pending(OwnershipTransfer, cu.company).select_related("to_user").first()
        return Response({"pending": _row(pending)})


def _live_pending(model, company):
    """The newest pending transfer or recovery that has not expired."""
    from django.db.models import Q
    from django.utils import timezone

    return model.objects.filter(company=company, status=model.Status.PENDING).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
    ).order_by("-created_at")


class OwnershipTransferView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]
    throttle_scope = "sensitive_action"

    def post(self, request):
        from billing.reauth import require_reauth

        from .ownership import start_transfer

        require_reauth(request)
        cu = get_company_user(request)
        transfer, _token = start_transfer(
            company=cu.company, from_user=request.user,
            to_user_id=request.data.get("to_user_id") or 0,
            old_owner_becomes=str(request.data.get("old_owner_becomes") or "MANAGER"),
        )
        body = {"transfer": _row(transfer)}
        from django.conf import settings

        if (getattr(settings, "DJANGO_ENV", "") or "").lower() not in ("production", "staging"):
            body["token"] = _token  # dev/test only, like invite tokens
        return Response(body, status=status.HTTP_201_CREATED)


class OwnershipAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .ownership import accept_transfer

        transfer = accept_transfer(token=str(request.data.get("token") or ""), user=request.user)
        return Response({"transfer": _row(transfer)})


class OwnershipCancelView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        from .models import OwnershipTransfer
        from .ownership import cancel

        cu = get_company_user(request)
        pending = _live_pending(OwnershipTransfer, cu.company).first()
        if pending is None:
            return Response({"detail": "Nothing pending."}, status=status.HTTP_404_NOT_FOUND)
        cancel(pending, user=request.user, reason=str(request.data.get("reason") or "Cancelled by an owner"))
        return Response({"transfer": _row(pending)})

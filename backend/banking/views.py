from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from banking.fiu_adapter import fetch_live_transactions_for_consent, fetch_transactions_for_consent
from banking.models import AaConsent, AaTransaction
from banking.serializers import AaConsentSerializer, AaIngestSerializer, AaTransactionSerializer
from banking.services import match_aa_to_receipts
from core.exceptions import BusinessRuleError
from core.permissions import CanViewPaymentSurfaces, HasCompany, IsOwner, get_company_user
from core.services.feature_flags import build_feature_flags


def _assert_aa_enabled(company) -> None:
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_ACCOUNT_AGGREGATOR"):
        raise Http404()


class AaIngestView(APIView):
    """POST /api/v1/banking/aa/ingest/ — ingest AA consent + transactions."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    @transaction.atomic
    def post(self, request):
        company = get_company_user(request).company
        _assert_aa_enabled(company)
        ser = AaIngestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        consent, _ = AaConsent.objects.update_or_create(
            company=company,
            consent_id=data["consent_id"],
            defaults={
                "status": data["status"],
                "fi_type": data["fi_type"],
                "created_by": request.user,
                "updated_by": request.user,
            },
        )

        rows = data.get("transactions") or []
        env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        # GAP-001: mock FIU is allowlisted (dev/test/local only). Empty rows must
        # not inject mocks; unset/blank env fails closed.
        mock_allowed = env in ("development", "dev", "test", "local")
        want_mock = bool(data.get("use_mock_fiu"))
        if want_mock and not mock_allowed:
            raise BusinessRuleError("Mock AA ingest is disabled outside development.")
        if want_mock:
            for mock in fetch_transactions_for_consent(
                consent_id=consent.consent_id, fi_type=consent.fi_type
            ):
                rows.append(
                    {
                        "txn_id": mock.txn_id,
                        "amount": str(mock.amount),
                        "txn_date": mock.txn_date.isoformat(),
                        "raw": mock.raw,
                    }
                )
        elif data.get("use_live_fiu"):
            for live in fetch_live_transactions_for_consent(
                consent_id=consent.consent_id, fi_type=consent.fi_type
            ):
                rows.append(
                    {
                        "txn_id": live.txn_id,
                        "amount": str(live.amount),
                        "txn_date": live.txn_date.isoformat(),
                        "raw": live.raw,
                    }
                )

        created = []
        skipped = 0
        for row in rows:
            txn_id = str(row.get("txn_id") or row.get("id") or "")
            if not txn_id:
                continue
            # B4-019: one malformed provider amount must not abort the whole
            # atomic ingest (all rows rolled back -> 500).
            try:
                amount = Decimal(str(row.get("amount") or "0").replace(",", ""))
                if not amount.is_finite():
                    raise ValueError
            except (InvalidOperation, ValueError, TypeError):
                skipped += 1
                continue
            txn_date = parse_date(str(row.get("txn_date") or "")) or consent.created_at.date()
            obj, _ = AaTransaction.objects.update_or_create(
                company=company,
                txn_id=txn_id,
                defaults={
                    "consent": consent,
                    "amount": amount,
                    "txn_date": txn_date,
                    "raw": row.get("raw") or row,
                    "created_by": request.user,
                    "updated_by": request.user,
                },
            )
            created.append(obj)

        matched = match_aa_to_receipts(company=company)
        return Response(
            {
                "consent": AaConsentSerializer(consent).data,
                "transactions": AaTransactionSerializer(created, many=True).data,
                "matched_count": matched,
            },
            status=status.HTTP_201_CREATED,
        )


class AaListView(APIView):
    """GET /api/v1/banking/aa/ — list consents and recent transactions."""

    # BB-000618 / BB-000691: bank AA is a payment surface — not VIEWER.
    permission_classes = [IsAuthenticated, HasCompany, CanViewPaymentSurfaces]

    def get(self, request):
        company = get_company_user(request).company
        _assert_aa_enabled(company)
        consents = AaConsent.objects.filter(company=company).order_by("-created_at")[:50]
        txns = AaTransaction.objects.filter(company=company).select_related("consent")[:100]
        return Response(
            {
                "consents": AaConsentSerializer(consents, many=True).data,
                "transactions": AaTransactionSerializer(txns, many=True).data,
            }
        )

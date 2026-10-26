"""D-19 (BB-139): the owner's "Refer a business" panel and the public code check."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, IsOwner, get_company_user

from . import referrals


class ReferralPanelSerializer(serializers.Serializer):
    code = serializers.CharField()
    is_active = serializers.BooleanField()
    signed_up = serializers.IntegerField(help_text="Businesses that signed up with the link (not voided).")
    qualified = serializers.IntegerField(help_text="Of those, businesses that started paying (not voided).")


class ReferralLinkView(APIView):
    """GET /api/v1/billing/referral/ — the owner's referral code and counts. Counts only: the
    referrer never sees which businesses signed up. 404 while ENABLE_SAAS_REFERRALS is off."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    @extend_schema(responses=ReferralPanelSerializer)
    def get(self, request):
        company = get_company_user(request).company
        if not referrals.enabled(company):
            raise NotFound("Referrals are not available for this company.")
        link = referrals.link_for(company, request.user)
        return Response({"code": link.code, "is_active": link.is_active, **referrals.summary(company)})


class PublicReferralCheckSerializer(serializers.Serializer):
    valid = serializers.BooleanField()


class PublicReferralCheckView(APIView):
    """GET /api/v1/billing/referral/check/<code>/ — before sign-up: is this a live referral code?
    Says only yes or no (never whose code it is). Rate-limited."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "referral_check"

    @extend_schema(responses=PublicReferralCheckSerializer)
    def get(self, request, code: str):
        from accounts.models import Company
        from core.rls import rls_bypass

        from .models import ReferralLink

        code = referrals.normalise(code)
        with rls_bypass():  # pre-login: no tenant; reads one company id
            company_id = (
                ReferralLink.objects.filter(code=code, is_active=True).values_list("company_id", flat=True).first()
                if code else None
            )
        referrer = Company.objects.filter(pk=company_id).first() if company_id else None
        return Response({"valid": referrals.enabled(referrer)})

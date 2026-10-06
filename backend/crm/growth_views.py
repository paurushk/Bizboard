from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import CanCreateSales, HasCompany, get_company_user
from core.viewsets import CompanyScopedViewSet
from masters.models import Customer

from .forecast import sync_opportunity_amount
from .models import Campaign, Opportunity, OpportunityLine, ReferralCode, ReferralReward
from .permissions import assert_crm_enabled
from .referrals import issue_referral_code, mark_reward_paid, referral_leaderboard
from .serializers import (
    CampaignSerializer,
    OpportunityLineSerializer,
    ReferralCodeSerializer,
    ReferralRewardSerializer,
)
from .campaigns import campaign_funnel, campaign_rollup


def _assert_referrals(company):
    from django.http import Http404

    from core.services.feature_flags import flag_enabled

    assert_crm_enabled(company)
    if not flag_enabled(company, "ENABLE_REFERRALS"):
        raise Http404()


class CampaignViewSet(CompanyScopedViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Campaign"

    def get_queryset(self):
        qs = super().get_queryset()
        term = (self.request.query_params.get("q") or "").strip()
        # Search on the server: the list is paged, so a filter over the loaded page misses the rest.
        return qs.filter(name__icontains=term) if term else qs

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_crm_enabled(get_company_user(request).company)

    @action(detail=True, methods=["get"])
    def funnel(self, request, pk=None):
        campaign = self.get_object()
        payload = campaign_funnel(campaign.company, campaign)
        if campaign.children.filter(company=campaign.company).exists():
            payload["rollup"] = campaign_rollup(campaign.company, campaign)
        return Response(payload)


class OpportunityLineViewSet(CompanyScopedViewSet):
    queryset = OpportunityLine.objects.select_related("product")
    serializer_class = OpportunityLineSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "OpportunityLine"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_crm_enabled(get_company_user(request).company)
        self.opportunity = get_object_or_404(
            Opportunity, company=get_company_user(request).company, pk=kwargs["opportunity_pk"],
        )

    def get_queryset(self):
        return super().get_queryset().filter(opportunity=self.opportunity)

    def perform_create(self, serializer):
        instance = serializer.save(
            company=self.company,
            opportunity=self.opportunity,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        sync_opportunity_amount(self.opportunity)
        self._audit("CREATE", instance)

    def perform_update(self, serializer):
        instance = serializer.save(updated_by=self.request.user, company=self.company)
        sync_opportunity_amount(self.opportunity)
        self._audit("UPDATE", instance)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        sync_opportunity_amount(self.opportunity)


class ReferralCodeViewSet(CompanyScopedViewSet):
    queryset = ReferralCode.objects.all()
    serializer_class = ReferralCodeSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "ReferralCode"
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _assert_referrals(get_company_user(request).company)

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Use the issue action."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=False, methods=["post"])
    def issue(self, request):
        company = self.company
        customer_id = request.data.get("referrer_customer")
        user_id = request.data.get("referrer_user")
        customer = Customer.objects.filter(company=company, pk=customer_id).first() if customer_id else None
        member = CompanyUser.objects.filter(company=company, pk=user_id).first() if user_id else None
        if customer_id and customer is None:
            return Response({"detail": "Customer was not found."}, status=400)
        if user_id and member is None:
            return Response({"detail": "Company user was not found."}, status=400)
        row = issue_referral_code(
            company,
            request.user,
            referrer_customer=customer,
            referrer_user=member,
            reward_type=request.data.get("reward_type") or "FLAT",
            reward_value=request.data.get("reward_value") or 0,
        )
        return Response(ReferralCodeSerializer(row, context={"request": request}).data, status=201)

    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        return Response(referral_leaderboard(self.company))


class ReferralRewardViewSet(CompanyScopedViewSet):
    queryset = ReferralReward.objects.all()
    serializer_class = ReferralRewardSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "ReferralReward"
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        _assert_referrals(get_company_user(request).company)

    def create(self, request, *args, **kwargs):
        return Response({"detail": "Rewards are created when an opportunity is won."}, status=405)

    def _decide(self, request, new_status):
        membership = get_company_user(request)
        if membership.role not in (CompanyUser.Role.OWNER, CompanyUser.Role.MANAGER):
            return Response({"detail": "Owner or manager role required."}, status=status.HTTP_403_FORBIDDEN)
        reward = self.get_object()
        if reward.reward_status == ReferralReward.Status.PAID:
            return Response({"detail": "A paid reward cannot be approved or rejected."}, status=400)
        if reward.reward_status == ReferralReward.Status.REJECTED:
            return Response({"detail": "A rejected reward cannot be approved."}, status=400)
        if new_status == ReferralReward.Status.APPROVED and reward.reward_status != ReferralReward.Status.PENDING:
            return Response({"detail": "Only a pending reward can be approved."}, status=400)
        reward.reward_status = new_status
        reward.updated_by = request.user
        reward.save(update_fields=["reward_status", "updated_by", "updated_at"])
        self._audit("UPDATE", reward)
        return Response(ReferralRewardSerializer(reward).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, ReferralReward.Status.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, ReferralReward.Status.REJECTED)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        membership = get_company_user(request)
        if membership.role not in (CompanyUser.Role.OWNER, CompanyUser.Role.MANAGER):
            return Response({"detail": "Owner or manager role required."}, status=status.HTTP_403_FORBIDDEN)
        def _build():
            try:
                reward = mark_reward_paid(self.get_object(), request.user)
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=400)
            self._audit("UPDATE", reward)
            return Response(ReferralRewardSerializer(reward).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="referral_reward_credit_note",
            build=_build,
        )

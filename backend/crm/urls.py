from django.urls import include, path
from core.routers import DefaultRouter

from .growth_views import CampaignViewSet, OpportunityLineViewSet, ReferralCodeViewSet, ReferralRewardViewSet
from .onboarding import CrmOnboardingView
from .views import LeadIngestJobView, LeadViewSet, OpportunityViewSet, PublicLeadFormView, WhatsAppInboundView

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="crm-lead")
router.register("opportunities", OpportunityViewSet, basename="crm-opportunity")
router.register("campaigns", CampaignViewSet, basename="crm-campaign")
router.register("referrals/codes", ReferralCodeViewSet, basename="crm-referral-code")
router.register("referrals/rewards", ReferralRewardViewSet, basename="crm-referral-reward")

urlpatterns = [
    path("onboarding/", CrmOnboardingView.as_view(), name="crm-onboarding"),
    path("public/lead-form/<str:token>/", PublicLeadFormView.as_view(), name="crm-public-lead-form"),
    path("public/whatsapp/<str:token>/", WhatsAppInboundView.as_view(), name="crm-whatsapp-inbound"),
    path("leads/ingest-jobs/<int:job_id>/", LeadIngestJobView.as_view(), name="crm-lead-ingest-job"),
    path(
        "opportunities/<int:opportunity_pk>/lines/",
        OpportunityLineViewSet.as_view({"get": "list", "post": "create"}),
        name="crm-opportunity-lines",
    ),
    path(
        "opportunities/<int:opportunity_pk>/lines/<int:pk>/",
        OpportunityLineViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="crm-opportunity-line",
    ),
    path("", include(router.urls)),
]

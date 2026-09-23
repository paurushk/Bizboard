from django.urls import include, path
from core.routers import DefaultRouter

from .views import LeadIngestJobView, LeadViewSet, OpportunityViewSet, PublicLeadFormView, WhatsAppInboundView

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="crm-lead")
router.register("opportunities", OpportunityViewSet, basename="crm-opportunity")

urlpatterns = [
    path("public/lead-form/<str:token>/", PublicLeadFormView.as_view(), name="crm-public-lead-form"),
    path("public/whatsapp/<str:token>/", WhatsAppInboundView.as_view(), name="crm-whatsapp-inbound"),
    path("leads/ingest-jobs/<int:job_id>/", LeadIngestJobView.as_view(), name="crm-lead-ingest-job"),
    path("", include(router.urls)),
]

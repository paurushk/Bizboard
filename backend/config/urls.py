from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsOwner
from core.views import HealthView, MetricsView


class GatedSchemaView(SpectacularAPIView):
    permission_classes = [IsAuthenticated, IsOwner]


class GatedSwaggerView(SpectacularSwaggerView):
    permission_classes = [IsAuthenticated, IsOwner]


from payments.urls import public_urlpatterns as payments_public_urlpatterns

api_v1_patterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("metrics/", MetricsView.as_view(), name="metrics"),
    path("auth/", include("accounts.urls_auth")),
    path("company/", include("accounts.urls_company")),
    path("", include("masters.urls")),
    path("inventory/", include("inventory.urls")),
    path("purchases/", include("purchases.urls")),
    path("sales/", include("sales.urls")),
    path("payments/", include("payments.urls")),
    path("accounting/", include("accounting.urls")),
    path("ledgers/", include("ledgers.urls")),
    path("", include("reporting.urls")),
    path("search/", include("search.urls")),
    path("imports/", include("imports.urls")),
    path("insights/", include("insights.urls")),
    path("integrations/", include("integrations.urls")),
    path("manufacturing/", include("manufacturing.urls")),
    path("payroll/", include("payroll.urls")),
    path("crm/", include("crm.urls")),
    path("banking/", include("banking.urls")),
    path("billing/", include("billing.urls")),
    path("", include("core.urls")),
] + payments_public_urlpatterns

if settings.ENABLE_API_DOCS:
    api_v1_patterns += [
        path("schema/", GatedSchemaView.as_view(), name="schema"),
        path("docs/", GatedSwaggerView.as_view(url_name="v1:schema"), name="swagger-ui"),
    ]

urlpatterns = []
if getattr(settings, "ADMIN_ENABLED", True):
    urlpatterns.append(path("admin/", admin.site.urls))
urlpatterns.append(path("api/v1/", include((api_v1_patterns, "v1"))))
# BB-000753: also expose /metrics at root for scrapers.
urlpatterns.append(path("metrics/", MetricsView.as_view(), name="metrics-root"))
# Media is never served via Django static() — use FileAsset download endpoints only.

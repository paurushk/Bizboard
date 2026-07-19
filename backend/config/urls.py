from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.views import HealthView

api_v1_patterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("accounts.urls_auth")),
    path("company/", include("accounts.urls_company")),
    path("", include("masters.urls")),
    path("inventory/", include("inventory.urls")),
    path("purchases/", include("purchases.urls")),
    path("sales/", include("sales.urls")),
    path("payments/", include("payments.urls")),
    path("ledgers/", include("ledgers.urls")),
    path("", include("reporting.urls")),
    path("search/", include("search.urls")),
    path("imports/", include("imports.urls")),
    path("", include("core.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"))),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.urls import path

from .views import (
    CustomerSalesView,
    DashboardView,
    ExportView,
    InventorySummaryView,
    ProductSalesView,
    PurchaseRegisterView,
    SalesRegisterView,
)

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("reports/sales-register/", SalesRegisterView.as_view(), name="sales-register"),
    path("reports/purchase-register/", PurchaseRegisterView.as_view(), name="purchase-register"),
    path("reports/inventory-summary/", InventorySummaryView.as_view(), name="inventory-summary"),
    path("reports/product-sales/", ProductSalesView.as_view(), name="product-sales"),
    path("reports/customer-sales/", CustomerSalesView.as_view(), name="customer-sales"),
    path("exports/<str:report>/", ExportView.as_view(), name="exports"),
]

from django.urls import path

from .views import (
    CustomerLedgerDetailView,
    CustomerLedgerListView,
    SupplierLedgerDetailView,
    SupplierLedgerListView,
)

urlpatterns = [
    path("customers/", CustomerLedgerListView.as_view(), name="customer-ledgers"),
    path("customers/<int:customer_id>/", CustomerLedgerDetailView.as_view(), name="customer-ledger-detail"),
    path("suppliers/", SupplierLedgerListView.as_view(), name="supplier-ledgers"),
    path("suppliers/<int:supplier_id>/", SupplierLedgerDetailView.as_view(), name="supplier-ledger-detail"),
]

from django.urls import path

from . import views

urlpatterns = [
    path("catalog/", views.CatalogView.as_view(), name="agents-catalog"),
    path("runs/", views.RunListCreateView.as_view(), name="agents-run-create"),
    path("runs/<int:pk>/", views.RunDetailView.as_view(), name="agents-run-detail"),
    path("proposals/", views.ProposalListView.as_view(), name="agents-proposals"),
    path("proposals/bulk-approve/", views.ProposalBulkApproveView.as_view(), name="agents-proposals-bulk-approve"),
    path("proposals/<int:pk>/", views.ProposalDetailView.as_view(), name="agents-proposal-detail"),
    path("proposals/<int:pk>/approve/", views.ProposalApproveView.as_view(), name="agents-proposal-approve"),
    path("proposals/<int:pk>/retry/", views.ProposalRetryView.as_view(), name="agents-proposal-retry"),
    path("proposals/<int:pk>/reject/", views.ProposalRejectView.as_view(), name="agents-proposal-reject"),
    path("proposals/<int:pk>/cancel/", views.ProposalCancelView.as_view(), name="agents-proposal-cancel"),
]

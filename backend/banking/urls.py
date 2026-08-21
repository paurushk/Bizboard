from django.urls import path

from banking.views import AaIngestView, AaListView

urlpatterns = [
    path("aa/ingest/", AaIngestView.as_view(), name="banking-aa-ingest"),
    path("aa/", AaListView.as_view(), name="banking-aa-list"),
]

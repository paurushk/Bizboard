"""Shared credit / debit note register behaviour: filters (CN-02 / DN-02) and CSV export (CN-11 / DN-10).

Used by the sales and purchase note viewsets. A viewset sets ``party_field`` /
``invoice_field`` (model field names) and ``export_filename``.
"""

import csv
from datetime import date

from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action

from core.csv_utils import csv_safe
from core.exceptions import BusinessRuleError


def parse_iso_date(raw, name):
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise BusinessRuleError(f"{name} must be a valid YYYY-MM-DD date.") from exc


class NoteRegisterMixin:
    # Must precede CompanyScopedViewSet in the MRO so company scoping runs first.
    # (A comment, not a docstring: inspect.getdoc would copy a docstring into every
    # viewset's OpenAPI description.)

    party_field = "customer"
    invoice_field = "sales_invoice"
    export_filename = "notes.csv"
    export_row_cap = 10000

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        for param, field in ((self.party_field, self.party_field), ("invoice", self.invoice_field)):
            if p.get(param):
                if not p[param].isascii() or not p[param].isdigit():
                    raise BusinessRuleError(f"{param} must be a numeric id.")
                qs = qs.filter(**{f"{field}_id": int(p[param])})
        d_from = parse_iso_date(p["date_from"], "date_from") if p.get("date_from") else None
        d_to = parse_iso_date(p["date_to"], "date_to") if p.get("date_to") else None
        if d_from and d_to and d_from > d_to:
            raise BusinessRuleError("date_from cannot be after date_to.")
        if d_from:
            qs = qs.filter(note_date__gte=d_from)
        if d_to:
            qs = qs.filter(note_date__lte=d_to)
        term = (p.get("search") or "").strip()
        if term:
            qs = qs.filter(
                Q(number__icontains=term)
                | Q(**{f"{self.invoice_field}__number__icontains": term})
                | Q(**{f"{self.party_field}__name__icontains": term})
            )
        return qs

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset()).order_by("-note_date", "-id")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{self.export_filename}"'
        writer = csv.writer(response)
        writer.writerow([
            "Number", "Date", "Party", "Source invoice", "Reason", "Status",
            "Taxable", "Tax", "Grand total",
        ])
        for note in qs[: self.export_row_cap]:
            party = getattr(note, self.party_field)
            invoice = getattr(note, self.invoice_field, None)
            writer.writerow([
                csv_safe(note.number), note.note_date.isoformat(),
                csv_safe(party.name), csv_safe(invoice.number if invoice else ""),
                note.reason, note.status,
                note.taxable_total,
                note.cgst_total + note.sgst_total + note.igst_total + note.cess_total,
                note.grand_total,
            ])
        return response

"""SET-02: all document number series in one call, for one GSTIN and financial year.

``GET /api/v1/company/number-series/?gstin=&fy=`` lists every series the Document Series screen shows;
``PATCH`` saves any number of them together, all or nothing. The per-document ``number-series``
endpoints stay as they are for older clients.
"""

from __future__ import annotations

import re
from datetime import date

from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CompanyGstin
from core.exceptions import BusinessRuleError, ConflictError
from core.idempotency import wrap_idempotent
from core.models import DocumentSeries
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.document_numbers import (
    DocumentNumberService,
    fy_label_for,
    gst_fy_label_for,
    resolve_series_gstin,
)
from core.services.audit import AuditService
from core.settings_audit import changes
from core.settings_writes import _TOLERANCE, _expected_updated_at  # noqa: F401  (shared parsing)

#: The series the screen shows, in screen order.
SERIES_DOC_TYPES: tuple[str, ...] = (
    "SALES_INVOICE",
    "QUOTATION",
    "SALES_ORDER",
    "DELIVERY_CHALLAN",
    "SALES_CREDIT_NOTE",
    "SALES_DEBIT_NOTE",
    "PURCHASE_INVOICE",
    "PURCHASE_ORDER",
    "GOODS_RECEIPT",
    "PURCHASE_CREDIT_NOTE",
    "PURCHASE_DEBIT_NOTE",
)

#: Documents that GST rules require to carry a serial number of at most 16 characters. We warn and
#: never block: the limit on the composed number is awaiting CA confirmation (Settings plan D-8).
GST_LENGTH_LIMIT = 16
GST_LENGTH_TYPES = frozenset({"SALES_INVOICE", "SALES_CREDIT_NOTE", "SALES_DEBIT_NOTE"})

_FY_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _fy_start(label: str) -> date:
    m = _FY_RE.match(label or "")
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise BusinessRuleError("Financial year must look like 2026-27.")
    return date(int(m.group(1)), 4, 1)


def _resolve_selection(company, gstin_param: str, fy_param: str) -> tuple[str, str | None]:
    """Return (gstin or '', on_date) for the chosen GSTIN and financial year."""
    gstin = (gstin_param or "").strip().upper()
    if gstin:
        known = {g.upper() for g in CompanyGstin.objects.filter(company=company).values_list("gstin", flat=True)}
        if company.gstin:
            known.add(company.gstin.upper())
        if gstin not in known:
            raise BusinessRuleError("That GSTIN does not belong to this company.")
    else:
        gstin = resolve_series_gstin(company) or ""
    on_date = _fy_start(fy_param) if fy_param else None
    return gstin, on_date


def _length_warning(doc_type: str, preview: str) -> str | None:
    if doc_type in GST_LENGTH_TYPES and len(preview) > GST_LENGTH_LIMIT:
        return f"This number is {len(preview)} characters. GST rules limit it to {GST_LENGTH_LIMIT}; check with your CA."
    return None


def _row(company, doc_type: str, gstin: str, on_date) -> dict:
    peek = DocumentNumberService.peek(company, doc_type, gstin=gstin or None, on_date=on_date)
    series = DocumentSeries.objects.get(
        company=company, doc_type=doc_type, gstin_key=peek["gstin_key"], fy_label=peek["fy_label"]
    )
    return {
        "doc_type": doc_type,
        "prefix": peek["prefix"],
        "next_number": peek["next_number"],
        "padding": peek["padding"],
        "preview": peek["preview"],
        "length": len(peek["preview"]),
        "length_warning": _length_warning(doc_type, peek["preview"]),
        "updated_at": series.updated_at,
    }


def _options(company) -> dict:
    gstins = sorted(
        {
            g.upper()
            for g in list(CompanyGstin.objects.filter(company=company, is_active=True).values_list("gstin", flat=True))
            + ([company.gstin] if company.gstin else [])
            if g
        }
    )
    used = set(
        DocumentSeries.objects.filter(company=company).exclude(fy_label="").values_list("fy_label", flat=True)
    )
    current = gst_fy_label_for(None)
    start = int(current[:4])
    used |= {current, f"{start - 1}-{str(start)[-2:]}", f"{start + 1}-{str(start + 2)[-2:]}"}
    return {"gstins": gstins, "fy_options": sorted(used, reverse=True)}


class NumberSeriesView(APIView):
    """Owner only."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        gstin, on_date = _resolve_selection(
            company, request.query_params.get("gstin", ""), request.query_params.get("fy", "")
        )
        with transaction.atomic():
            rows = [_row(company, doc_type, gstin, on_date) for doc_type in SERIES_DOC_TYPES]
        first = DocumentSeries.objects.filter(company=company, doc_type=SERIES_DOC_TYPES[0]).order_by("-id")
        keys = DocumentNumberService._resolve_keys(company, gstin=gstin or None, on_date=on_date)
        return Response(
            {
                "gstin": keys[0],
                "fy_label": keys[1],
                "items": rows,
                **_options(company),
                "has_series": first.exists(),
            }
        )

    def patch(self, request):
        company = get_company_user(request).company

        def _run():
            body = request.data
            gstin, on_date = _resolve_selection(company, str(body.get("gstin") or ""), str(body.get("fy") or ""))
            items = body.get("items")
            if not isinstance(items, list) or not items:
                raise BusinessRuleError("Send the series to change in 'items'.")
            problems: dict[str, str] = {}
            stale: list[str] = []
            with transaction.atomic():
                for entry in items:
                    doc_type = str((entry or {}).get("doc_type") or "")
                    if doc_type not in SERIES_DOC_TYPES:
                        problems[doc_type or "?"] = "Unknown document type."
                        continue
                    keys = DocumentNumberService._resolve_keys(company, gstin=gstin or None, on_date=on_date)
                    DocumentNumberService._ensure_series(company, doc_type, gstin_key=keys[0], fy_label=keys[1])
                    row = DocumentSeries.objects.select_for_update().get(
                        company=company, doc_type=doc_type, gstin_key=keys[0], fy_label=keys[1]
                    )
                    expected = (entry or {}).get("expected_updated_at")
                    if expected:
                        from django.utils.dateparse import parse_datetime

                        parsed = parse_datetime(str(expected))
                        if parsed is None:
                            problems[doc_type] = "expected_updated_at must be an ISO 8601 date-time."
                            continue
                        if abs(row.updated_at - parsed) > _TOLERANCE:
                            stale.append(doc_type)
                            continue
                    before = {"prefix": row.prefix, "next_number": row.next_number, "padding": row.padding}
                    try:
                        DocumentNumberService.configure(
                            company,
                            doc_type,
                            prefix=entry.get("prefix"),
                            next_number=entry.get("next_number"),
                            padding=entry.get("padding"),
                            gstin=gstin or None,
                            on_date=on_date,
                        )
                    except ValueError as exc:
                        problems[doc_type] = str(exc)
                        continue
                    row.refresh_from_db()
                    diff = changes(before, {"prefix": row.prefix, "next_number": row.next_number, "padding": row.padding})
                    if diff:
                        AuditService.log(
                            company=company,
                            user=request.user,
                            action="UPDATE",
                            entity_type="DocumentSeries",
                            entity_id=f"{doc_type}:{row.fy_label or '-'}",
                            description=doc_type,
                            metadata={"changes": diff, "doc_type": doc_type, "gstin": row.gstin_key, "fy": row.fy_label},
                        )
                if stale:
                    transaction.set_rollback(True)
                    raise ConflictError(
                        "A number series was changed after you opened it. Reload to see the latest values.",
                        code="SETTINGS_STALE",
                    )
                if problems:
                    transaction.set_rollback(True)
                    raise BusinessRuleError(
                        "Nothing was saved. " + " ".join(f"{k}: {v}" for k, v in problems.items()),
                        code="series_invalid",
                        extra={"problems": problems},
                    )
            return self.get_response_after(company, gstin, on_date)

        return wrap_idempotent(request=request, company=company, scope="number_series_save", build=_run)

    @staticmethod
    def get_response_after(company, gstin, on_date) -> Response:
        keys = DocumentNumberService._resolve_keys(company, gstin=gstin or None, on_date=on_date)
        rows = [_row(company, doc_type, gstin, on_date) for doc_type in SERIES_DOC_TYPES]
        return Response(
            {"gstin": keys[0], "fy_label": keys[1], "items": rows, **_options(company), "has_series": True}
        )


__all__ = ["NumberSeriesView", "SERIES_DOC_TYPES", "fy_label_for"]

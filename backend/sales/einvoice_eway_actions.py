"""Prepare / submit / mark-generated actions for e-Invoice and e-Way."""

from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.models import StatutoryDocumentEvent, log_statutory_event
from core.services.audit import AuditService
from core.services.gsp_adapters import get_eway_adapter, get_irp_adapter, verify_irn_result

from .einvoice_payload import (
    EinvoiceValidationError,
    build_einvoice_payload,
    build_einvoice_payload_from_note,
)
from .eway_payload import EwayValidationError, build_eway_payload_from_challan, build_eway_payload_from_invoice
from .models import DeliveryChallan, SalesCreditNote, SalesDebitNote, SalesInvoice


def _require_owner(request):
    from core.permissions import get_company_user

    cu = get_company_user(request)
    if cu is None or cu.role != "OWNER":
        raise BusinessRuleError("Only Owner can perform this action.")


def _require_audit_reason(request) -> str:
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        raise BusinessRuleError("reason is required.")
    return reason


def _require_einvoice_enabled(company):
    if not company.einvoice_enabled:
        raise BusinessRuleError("e-Invoice is not enabled for this company.")


def _require_eway_enabled(company):
    if not company.eway_enabled:
        raise BusinessRuleError("e-Way Bill is not enabled for this company.")


def _assert_sandbox_gsp_allowed(company):
    """Block sandbox IRP/e-Way adapters for live GSTINs outside local/test.

    BB-000384 / BB-000624: production/staging stay fail-closed until
    GSP_CERTIFIED=1. Certified live (or certified HTTP sandbox) may proceed.
    """
    env = (getattr(settings, "DJANGO_ENV", "development") or "development").strip().lower()
    provider = (getattr(company, "gsp_provider", None) or "").strip().lower()
    certified = getattr(settings, "GSP_CERTIFIED", False) is True
    live = getattr(settings, "GSP_LIVE_ENABLED", False) is True
    http_sandbox = getattr(settings, "GSP_HTTP_SANDBOX", False) is True

    if env in ("production", "staging"):
        if certified and (http_sandbox or live):
            return
        raise BusinessRuleError(
            "e-Invoice/e-Way GSP is not available in production/staging until live "
            "GSP HTTP is configured. Disable einvoice_enabled/eway_enabled or use "
            "development/test with sandbox only."
        )

    # Local/test: always allow sandbox adapters.
    if env in ("development", "test"):
        return
    if provider == "sandbox":
        return
    live_gstin = (company.gstin or "").strip()
    if not live_gstin:
        from accounts.models import CompanyGstin

        live_gstin = (
            CompanyGstin.objects.filter(company=company, is_active=True)
            .exclude(gstin="")
            .order_by("-is_primary", "id")
            .values_list("gstin", flat=True)
            .first()
            or ""
        ).strip()
    if live_gstin:
        raise BusinessRuleError(
            "Sandbox GSP cannot be used for live GSTIN. "
            "Configure a production GSP provider before submitting."
        )


class InvoiceEinvoiceEwayActionsMixin:
    """Mixin for SalesInvoiceViewSet — prepare/submit/mark e-Invoice and e-Way."""

    @action(detail=True, methods=["post"], url_path="prepare-einvoice")
    def prepare_einvoice(self, request, pk=None):
        invoice = self.get_object()
        try:
            payload = build_einvoice_payload(invoice)
        except EinvoiceValidationError as exc:
            invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
            invoice.einvoice_error = "; ".join(exc.errors)
            invoice.save(update_fields=["einvoice_status", "einvoice_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc

        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.READY
        invoice.einvoice_error = ""
        invoice.save(update_fields=["einvoice_status", "einvoice_error"])
        data = self.get_serializer(invoice).data
        data["payload"] = payload
        return Response(data)

    @action(detail=True, methods=["post"], url_path="submit-einvoice")
    def submit_einvoice(self, request, pk=None):
        _require_owner(request)
        invoice = self.get_object()
        _assert_sandbox_gsp_allowed(invoice.company)
        _require_einvoice_enabled(invoice.company)
        try:
            payload = build_einvoice_payload(invoice)
        except EinvoiceValidationError as exc:
            invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
            invoice.einvoice_error = "; ".join(exc.errors)
            invoice.save(update_fields=["einvoice_status", "einvoice_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc

        try:
            result = get_irp_adapter(invoice.company).submit(payload)
            verify_irn_result(result)
        except BusinessRuleError as exc:
            invoice.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
            invoice.einvoice_error = str(exc)[:500]
            invoice.save(update_fields=["einvoice_status", "einvoice_error"])
            raise
        invoice.irn = result.irn
        invoice.ack_no = result.ack_no
        invoice.ack_date = result.ack_date
        invoice.einvoice_qr = result.einvoice_qr
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.GENERATED
        invoice.einvoice_error = ""
        invoice.save(
            update_fields=[
                "irn", "ack_no", "ack_date", "einvoice_qr",
                "einvoice_status", "einvoice_error",
            ]
        )
        AuditService.log(
            company=invoice.company,
            user=request.user,
            action="UPDATE",
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            description="einvoice.submitted",
            metadata={"irn": result.irn, "ack_no": result.ack_no},
        )
        log_statutory_event(
            company=invoice.company,
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            event_type=StatutoryDocumentEvent.EventType.IRN,
            payload={"action": "submitted", "irn": result.irn, "ack_no": result.ack_no},
            user=request.user,
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="submit-einvoice-async")
    def submit_einvoice_async(self, request, pk=None):
        """Wave 17A: enqueue IRP submit; returns 202 with task id."""
        from rest_framework import status as http_status

        from .tasks import submit_einvoice_async as enqueue_irn

        _require_owner(request)
        invoice = self.get_object()
        _assert_sandbox_gsp_allowed(invoice.company)
        _require_einvoice_enabled(invoice.company)
        if invoice.irn:
            return Response(self.get_serializer(invoice).data)
        async_result = enqueue_irn.delay(invoice.pk, request.user.pk)
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.QUEUED
        invoice.save(update_fields=["einvoice_status"])
        return Response(
            {"task_id": async_result.id, "invoice_id": invoice.pk, "status": "queued"},
            status=http_status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="cancel-einvoice")
    def cancel_einvoice(self, request, pk=None):
        _require_owner(request)
        invoice = self.get_object()
        _assert_sandbox_gsp_allowed(invoice.company)
        _require_einvoice_enabled(invoice.company)
        if not invoice.irn:
            raise BusinessRuleError("No IRN to cancel.")
        get_irp_adapter(invoice.company).cancel(invoice.irn)
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.CANCELLED
        invoice.save(update_fields=["einvoice_status"])
        AuditService.log(
            company=invoice.company,
            user=request.user,
            action="UPDATE",
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            description="einvoice.cancelled",
            metadata={"irn": invoice.irn},
        )
        log_statutory_event(
            company=invoice.company,
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            event_type=StatutoryDocumentEvent.EventType.IRN,
            payload={"action": "cancelled", "irn": invoice.irn},
            user=request.user,
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-einvoice-generated")
    def mark_einvoice_generated(self, request, pk=None):
        _require_owner(request)
        invoice = self.get_object()
        _require_einvoice_enabled(invoice.company)
        reason = _require_audit_reason(request)
        irn = (request.data.get("irn") or "").strip()
        ack_no = (request.data.get("ack_no") or "").strip()
        if not irn:
            raise BusinessRuleError("irn is required.")
        if not ack_no:
            raise BusinessRuleError("ack_no is required.")

        ack_date_raw = request.data.get("ack_date")
        ack_date = parse_datetime(ack_date_raw) if ack_date_raw else None

        invoice.irn = irn
        invoice.ack_no = ack_no
        invoice.ack_date = ack_date
        if "einvoice_qr" in request.data:
            qr = (request.data.get("einvoice_qr") or "").strip()
            if qr:
                invoice.einvoice_qr = qr
        # BB-000214: distinct from GSP-verified GENERATED.
        invoice.einvoice_status = SalesInvoice.EInvoiceStatus.MANUAL_IRN
        invoice.einvoice_error = ""
        invoice.save(
            update_fields=[
                "irn", "ack_no", "ack_date", "einvoice_qr",
                "einvoice_status", "einvoice_error",
            ]
        )
        AuditService.log(
            company=invoice.company,
            user=request.user,
            action="UPDATE",
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            description="einvoice.manual_irn_attested",
            metadata={"irn": irn, "ack_no": ack_no, "reason": reason},
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="prepare-eway")
    def prepare_eway(self, request, pk=None):
        invoice = self.get_object()
        challan = None
        challan_id = request.data.get("challan_id")
        if challan_id:
            try:
                challan = DeliveryChallan.objects.get(pk=challan_id, company=invoice.company)
            except DeliveryChallan.DoesNotExist as exc:
                raise BusinessRuleError("Invalid challan.") from exc

        try:
            payload = build_eway_payload_from_invoice(
                invoice,
                vehicle_number=(request.data.get("vehicle_number") or "").strip(),
                transporter_name=(request.data.get("transporter_name") or "").strip(),
                challan=challan,
            )
        except EwayValidationError as exc:
            invoice.eway_status = SalesInvoice.EwayStatus.FAILED
            invoice.eway_error = "; ".join(exc.errors)
            invoice.save(update_fields=["eway_status", "eway_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc

        invoice.eway_status = SalesInvoice.EwayStatus.READY
        invoice.eway_error = ""
        invoice.save(update_fields=["eway_status", "eway_error"])
        data = self.get_serializer(invoice).data
        data["payload"] = payload
        return Response(data)

    @action(detail=True, methods=["post"], url_path="submit-eway")
    def submit_eway(self, request, pk=None):
        _require_owner(request)
        invoice = self.get_object()
        _assert_sandbox_gsp_allowed(invoice.company)
        _require_eway_enabled(invoice.company)
        try:
            payload = build_eway_payload_from_invoice(
                invoice,
                vehicle_number=(request.data.get("vehicle_number") or invoice.vehicle_number or "").strip(),
                transporter_name=(request.data.get("transporter_name") or invoice.transporter_name or "").strip(),
            )
        except EwayValidationError as exc:
            invoice.eway_status = SalesInvoice.EwayStatus.FAILED
            invoice.eway_error = "; ".join(exc.errors)
            invoice.save(update_fields=["eway_status", "eway_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc

        result = get_eway_adapter(invoice.company).submit(payload)
        invoice.eway_bill_no = result.eway_bill_no
        invoice.eway_valid_upto = result.eway_valid_upto
        invoice.eway_status = SalesInvoice.EwayStatus.GENERATED
        invoice.eway_error = ""
        invoice.save(update_fields=["eway_bill_no", "eway_valid_upto", "eway_status", "eway_error"])
        log_statutory_event(
            company=invoice.company,
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            event_type=StatutoryDocumentEvent.EventType.EWAY,
            payload={"action": "submitted", "eway_bill_no": result.eway_bill_no},
            user=request.user,
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="cancel-eway")
    def cancel_eway(self, request, pk=None):
        _require_owner(request)
        invoice = self.get_object()
        _assert_sandbox_gsp_allowed(invoice.company)
        _require_eway_enabled(invoice.company)
        if not invoice.eway_bill_no:
            raise BusinessRuleError("No e-Way Bill to cancel.")
        cancelled_no = invoice.eway_bill_no
        get_eway_adapter(invoice.company).cancel(cancelled_no)
        invoice.eway_status = SalesInvoice.EwayStatus.CANCELLED
        invoice.eway_bill_no = ""
        invoice.eway_valid_upto = None
        invoice.save(update_fields=["eway_status", "eway_bill_no", "eway_valid_upto"])
        log_statutory_event(
            company=invoice.company,
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            event_type=StatutoryDocumentEvent.EventType.EWAY,
            payload={"action": "cancelled", "eway_bill_no": cancelled_no},
            user=request.user,
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-eway-generated")
    def mark_eway_generated(self, request, pk=None):
        _require_owner(request)
        invoice = self.get_object()
        _require_eway_enabled(invoice.company)
        reason = _require_audit_reason(request)
        eway_bill_no = (request.data.get("eway_bill_no") or "").strip()
        if not eway_bill_no:
            raise BusinessRuleError("eway_bill_no is required.")

        valid_upto_raw = request.data.get("eway_valid_upto")
        eway_valid_upto = parse_datetime(valid_upto_raw) if valid_upto_raw else None

        invoice.eway_bill_no = eway_bill_no
        invoice.eway_valid_upto = eway_valid_upto
        # BB-000273: distinct from GSP-verified GENERATED.
        invoice.eway_status = SalesInvoice.EwayStatus.MANUAL_EWB
        invoice.eway_error = ""
        invoice.save(update_fields=["eway_bill_no", "eway_valid_upto", "eway_status", "eway_error"])
        AuditService.log(
            company=invoice.company,
            user=request.user,
            action="UPDATE",
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            description="eway.manual_ewb_attested",
            metadata={"eway_bill_no": eway_bill_no, "reason": reason},
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="amend-filing-identity")
    def amend_filing_identity(self, request, pk=None):
        """D16: Owner-only amend of filing GSTIN / place of supply (no money changes)."""
        from core.permissions import get_company_user
        from core.validators import validate_gstin
        from django.core.exceptions import ValidationError
        from reporting.gst_periods import mark_period_dirty_if_snapshotted

        invoice = self.get_object()
        cu = get_company_user(request)
        if cu.role != "OWNER":
            raise BusinessRuleError("Only Owner can amend filing identity.")
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Only completed invoices can amend filing identity.")

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise BusinessRuleError("reason is required.")

        new_gstin = request.data.get("filing_party_gstin")
        new_pos = request.data.get("filing_place_of_supply")
        before = {
            "filing_party_gstin": invoice.filing_party_gstin,
            "filing_place_of_supply": invoice.filing_place_of_supply,
        }

        # BB-000334: filing identity amend must never silently flip intra/inter
        # state classification — that changes whether CGST+SGST or IGST is owed,
        # which requires a real tax recompute (a new invoice/CN), not a relabel.
        from core.services.billing import extract_state_code

        company = invoice.company
        company_code = extract_state_code(company.gstin) or extract_state_code(company.state)
        customer_state_code = extract_state_code(invoice.customer.state)
        before_party_code = (
            extract_state_code(before["filing_party_gstin"])
            or extract_state_code(before["filing_place_of_supply"])
            or customer_state_code
        )

        candidate_gstin = before["filing_party_gstin"]
        candidate_pos = before["filing_place_of_supply"]
        if new_gstin is not None:
            candidate_gstin = (new_gstin or "").strip().upper()
        if new_pos is not None:
            candidate_pos = (new_pos or "").strip()
        after_party_code = (
            extract_state_code(candidate_gstin) or extract_state_code(candidate_pos) or customer_state_code
        )

        if (
            company_code
            and before_party_code
            and after_party_code
            and (company_code == before_party_code) != (company_code == after_party_code)
        ):
            raise BusinessRuleError(
                "This change would flip the invoice between intra-state (CGST+SGST) and "
                "inter-state (IGST), which changes the tax owed. Amending filing GSTIN/place "
                "of supply cannot alter tax — issue a credit note and a new invoice instead."
            )

        if new_gstin is not None:
            new_gstin = (new_gstin or "").strip().upper()
            if new_gstin:
                try:
                    validate_gstin(new_gstin)
                except ValidationError as exc:
                    raise BusinessRuleError(str(exc.message)) from exc
            invoice.filing_party_gstin = new_gstin
        if new_pos is not None:
            invoice.filing_place_of_supply = (new_pos or "").strip()
        invoice.save(update_fields=["filing_party_gstin", "filing_place_of_supply"])
        mark_period_dirty_if_snapshotted(invoice.company, invoice.invoice_date)
        AuditService.log(
            company=invoice.company,
            user=request.user,
            action="UPDATE",
            entity_type="salesinvoice",
            entity_id=invoice.pk,
            description="filing_identity.amended",
            metadata={"before": before, "after": {
                "filing_party_gstin": invoice.filing_party_gstin,
                "filing_place_of_supply": invoice.filing_place_of_supply,
            }, "reason": reason},
        )
        return Response(self.get_serializer(invoice).data)


class ChallanEwayActionsMixin:
    """Mixin for DeliveryChallanViewSet — prepare/mark/submit/cancel e-Way."""

    @action(detail=True, methods=["post"], url_path="prepare-eway")
    def prepare_eway(self, request, pk=None):
        challan = self.get_object()
        try:
            payload = build_eway_payload_from_challan(challan)
        except EwayValidationError as exc:
            challan.eway_status = SalesInvoice.EwayStatus.FAILED
            challan.eway_error = "; ".join(exc.errors)
            challan.save(update_fields=["eway_status", "eway_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc

        challan.eway_status = SalesInvoice.EwayStatus.READY
        challan.eway_error = ""
        challan.save(update_fields=["eway_status", "eway_error"])
        data = self.get_serializer(challan).data
        data["payload"] = payload
        return Response(data)

    @action(detail=True, methods=["post"], url_path="submit-eway")
    def submit_eway(self, request, pk=None):
        _require_owner(request)
        challan = self.get_object()
        _assert_sandbox_gsp_allowed(challan.company)
        _require_eway_enabled(challan.company)
        try:
            payload = build_eway_payload_from_challan(challan)
        except EwayValidationError as exc:
            challan.eway_status = SalesInvoice.EwayStatus.FAILED
            challan.eway_error = "; ".join(exc.errors)
            challan.save(update_fields=["eway_status", "eway_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc

        result = get_eway_adapter(challan.company).submit(payload)
        challan.eway_bill_no = result.eway_bill_no
        challan.eway_valid_upto = result.eway_valid_upto
        challan.eway_status = SalesInvoice.EwayStatus.GENERATED
        challan.eway_error = ""
        challan.save(update_fields=["eway_bill_no", "eway_valid_upto", "eway_status", "eway_error"])
        return Response(self.get_serializer(challan).data)

    @action(detail=True, methods=["post"], url_path="cancel-eway")
    def cancel_eway(self, request, pk=None):
        _require_owner(request)
        challan = self.get_object()
        _require_eway_enabled(challan.company)
        if not challan.eway_bill_no:
            raise BusinessRuleError("No e-Way Bill to cancel.")
        cancelled_no = challan.eway_bill_no
        get_eway_adapter(challan.company).cancel(cancelled_no)
        challan.eway_status = SalesInvoice.EwayStatus.CANCELLED
        challan.eway_bill_no = ""
        challan.eway_valid_upto = None
        challan.save(update_fields=["eway_status", "eway_bill_no", "eway_valid_upto"])
        return Response(self.get_serializer(challan).data)

    @action(detail=True, methods=["post"], url_path="mark-eway-generated")
    def mark_eway_generated(self, request, pk=None):
        _require_owner(request)
        challan = self.get_object()
        _require_eway_enabled(challan.company)
        reason = _require_audit_reason(request)
        eway_bill_no = (request.data.get("eway_bill_no") or "").strip()
        if not eway_bill_no:
            raise BusinessRuleError("eway_bill_no is required.")

        valid_upto_raw = request.data.get("eway_valid_upto")
        eway_valid_upto = parse_datetime(valid_upto_raw) if valid_upto_raw else None

        challan.eway_bill_no = eway_bill_no
        challan.eway_valid_upto = eway_valid_upto
        # BB-000273: distinct from GSP-verified GENERATED.
        challan.eway_status = SalesInvoice.EwayStatus.MANUAL_EWB
        challan.eway_error = ""
        challan.save(update_fields=["eway_bill_no", "eway_valid_upto", "eway_status", "eway_error"])
        AuditService.log(
            company=challan.company,
            user=request.user,
            action="UPDATE",
            entity_type="deliverychallan",
            entity_id=challan.pk,
            description="eway.manual_ewb_attested",
            metadata={"eway_bill_no": eway_bill_no, "reason": reason},
        )
        return Response(self.get_serializer(challan).data)


class NoteEinvoiceActionsMixin:
    """BB-000647: prepare/submit IRN for sales credit and debit notes."""

    @action(detail=True, methods=["post"], url_path="prepare-einvoice")
    def prepare_einvoice(self, request, pk=None):
        note = self.get_object()
        try:
            payload = build_einvoice_payload_from_note(note)
        except EinvoiceValidationError as exc:
            note.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
            note.einvoice_error = "; ".join(exc.errors)
            note.save(update_fields=["einvoice_status", "einvoice_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc
        note.einvoice_status = SalesInvoice.EInvoiceStatus.READY
        note.einvoice_error = ""
        note.save(update_fields=["einvoice_status", "einvoice_error"])
        data = self.get_serializer(note).data
        data["payload"] = payload
        return Response(data)

    @action(detail=True, methods=["post"], url_path="submit-einvoice")
    def submit_einvoice(self, request, pk=None):
        _require_owner(request)
        note = self.get_object()
        _assert_sandbox_gsp_allowed(note.company)
        _require_einvoice_enabled(note.company)
        try:
            payload = build_einvoice_payload_from_note(note)
        except EinvoiceValidationError as exc:
            note.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
            note.einvoice_error = "; ".join(exc.errors)
            note.save(update_fields=["einvoice_status", "einvoice_error"])
            raise BusinessRuleError("; ".join(exc.errors)) from exc
        try:
            result = get_irp_adapter(note.company).submit(payload)
            verify_irn_result(result)
        except BusinessRuleError as exc:
            note.einvoice_status = SalesInvoice.EInvoiceStatus.FAILED
            note.einvoice_error = str(exc)[:500]
            note.save(update_fields=["einvoice_status", "einvoice_error"])
            raise
        note.irn = result.irn
        note.ack_no = result.ack_no
        note.ack_date = result.ack_date
        note.einvoice_qr = result.einvoice_qr
        note.einvoice_status = SalesInvoice.EInvoiceStatus.GENERATED
        note.einvoice_error = ""
        note.save(
            update_fields=["irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error"]
        )
        return Response(self.get_serializer(note).data)

    @action(detail=True, methods=["post"], url_path="cancel-einvoice")
    def cancel_einvoice(self, request, pk=None):
        _require_owner(request)
        note = self.get_object()
        _assert_sandbox_gsp_allowed(note.company)
        _require_einvoice_enabled(note.company)
        if not note.irn:
            raise BusinessRuleError("No IRN to cancel.")
        get_irp_adapter(note.company).cancel(note.irn)
        note.einvoice_status = SalesInvoice.EInvoiceStatus.CANCELLED
        note.save(update_fields=["einvoice_status"])
        return Response(self.get_serializer(note).data)

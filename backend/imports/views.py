from django.http import HttpResponse, StreamingHttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import csv
import io
from django.db import transaction

from core.exceptions import BusinessRuleError
from core.csv_utils import csv_safe
from core.idempotency import (
    begin_record,
    release_record,
    request_fingerprint,
    store_record,
)
from core.models import FileAsset
from core.permissions import (
    CanCreatePurchases,
    CanCreateSales,
    CanImport,
    HasCompany,
    IsOwner,
    get_company_user,
)
from core.throttles import CompanyRateThrottle
from core.services.files import FileService
from masters.models import Customer, Supplier

from .models import ImportJob
from .serializers import ImportJobSerializer
from .services import (
    BillImportService,
    ImportService,
    OPENING_LOTS_COLUMNS,
    OPENING_SERIALS_COLUMNS,
    products_item_columns,
    products_template_csv,
)

BILL_IMAGE_PDF_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
BILL_STRUCTURED_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
BILL_CONTENT_TYPES = BILL_IMAGE_PDF_TYPES | BILL_STRUCTURED_TYPES
BILL_STRUCTURED_EXTENSIONS = (".csv", ".xlsx", ".xlsm")


class ImportJobViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ImportJobSerializer
    queryset = ImportJob.objects.all()
    permission_classes = [IsAuthenticated, HasCompany, CanImport]
    # B3-009: bill-photo/PDF extraction has real per-call LLM cost -- cap how
    # often a company can start a new bill extraction (upload or retry),
    # independent of the monthly token-budget check in extract_purchase_bill_task.
    throttle_scope = "llm_bill_extraction"

    @property
    def company(self):
        return get_company_user(self.request).company

    # 23.5: importing a bill creates a draft document, so the importer must be
    # allowed to create that document too -- one rule at the API and the UI.
    _KIND_PERMISSIONS = {
        ImportJob.Kind.SALES_BILL: (CanCreateSales, "Sales create permission is required to import sales bills."),
        ImportJob.Kind.PURCHASE_BILL: (
            CanCreatePurchases,
            "Purchases create permission is required to import purchase bills.",
        ),
    }

    def _has_kind_permission(self, kind: str) -> bool:
        entry = self._KIND_PERMISSIONS.get(kind)
        if entry is None:
            return True
        return entry[0]().has_permission(self.request, self)

    def _assert_kind_permission(self, kind: str) -> None:
        entry = self._KIND_PERMISSIONS.get(kind)
        if entry is not None and not entry[0]().has_permission(self.request, self):
            try:
                from core.services.audit import AuditService

                AuditService.log(
                    company=self.company, user=self.request.user, action="IMPORT",
                    entity_type="ImportJob", entity_id=0,
                    description=f"Bill import refused: missing create permission for {kind}",
                    metadata={"kind": kind, "event": "IMPORT_PERMISSION_DENIED"},
                )
            except Exception:  # noqa: BLE001 — auditing must never mask the 403
                pass
            raise PermissionDenied(entry[1])

    def throttled(self, request, wait):
        """Say what was limited and when to try again (bill reading costs real money)."""
        from rest_framework.exceptions import Throttled

        if getattr(self, "action", None) != "create":
            # Autosave, validate and the like fall under the general rate limit: keep its own wording.
            return super().throttled(request, wait)
        minutes = max(1, int((wait or 60) // 60) + 1)
        raise Throttled(
            wait=wait,
            detail=(
                "You have started many bill scans this hour, so scanning is paused to control "
                f"cost. Try again in about {minutes} minute(s), or upload a CSV/Excel export, "
                "which is not limited."
            ),
        )

    def get_object(self):
        job = super().get_object()
        self._assert_kind_permission(job.kind)
        return job

    def get_queryset(self):
        qs = self.queryset.filter(company=self.company).select_related("created_by", "file")
        if self.action == "list":
            params = self.request.query_params
            kind = (params.get("kind") or "").upper()
            if kind:
                qs = qs.filter(kind=kind)
            statuses = [x.strip().upper() for x in (params.get("status") or "").split(",") if x.strip()]
            if statuses:
                qs = qs.filter(status__in=statuses)
            if (params.get("mine") or "").lower() in ("1", "true", "yes"):
                qs = qs.filter(created_by=self.request.user)
            hidden = [k for k in self._KIND_PERMISSIONS if not self._has_kind_permission(k)]
            if hidden:
                qs = qs.exclude(kind__in=hidden)
        return qs

    def _upload_is_structured(self) -> bool:
        uploaded = self.request.FILES.get("file")
        if not uploaded:
            return False
        content_type = (getattr(uploaded, "content_type", "") or "").lower()
        name = (uploaded.name or "").lower()
        return content_type in BILL_STRUCTURED_TYPES or name.endswith(BILL_STRUCTURED_EXTENSIONS)

    def get_throttles(self):
        if self.action == "create":
            kind = (self.request.data.get("kind") or "").upper()
            if kind in ImportJob.BILL_KINDS and not self._upload_is_structured():
                # Only scans (image / PDF) cost money; a CSV/Excel export is not limited (S-02).
                return [CompanyRateThrottle()]
            return []
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        """Upload + validate (CSV masters) or start bill ingestion (purchase/sales bill)."""
        kind = (request.data.get("kind") or "").upper()
        if kind not in ImportJob.Kind.values:
            raise BusinessRuleError(f"kind must be one of {', '.join(ImportJob.Kind.values)}.")
        self._assert_kind_permission(kind)
        uploaded = request.FILES.get("file")
        if not uploaded:
            raise BusinessRuleError("A file is required.")

        supplier = None
        supplier_id = request.data.get("supplier_id") or request.data.get("supplier")
        if supplier_id:
            try:
                supplier = Supplier.objects.get(pk=supplier_id, company=self.company)
            except (Supplier.DoesNotExist, ValueError, TypeError):
                raise BusinessRuleError("Invalid supplier.")

        customer = None
        customer_id = request.data.get("customer_id") or request.data.get("customer")
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id, company=self.company)
            except (Customer.DoesNotExist, ValueError, TypeError):
                raise BusinessRuleError("Invalid customer.")

        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        # A bill *upload* is never idempotency-deduped — re-uploading the same
        # photo deliberately starts a fresh extraction job (the paired
        # store_record below is likewise skipped for BILL_KINDS). Only structured
        # master imports claim the key.
        use_idempotency = bool(raw_key) and kind not in ImportJob.BILL_KINDS
        claimed = None
        if use_idempotency:
            claimed = begin_record(
                company=self.company, scope="import_job_create", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed

        created_ok = False
        try:
            if kind in ImportJob.BILL_KINDS:
                content_type = (getattr(uploaded, "content_type", "") or "").lower()
                name = (uploaded.name or "").lower()
                is_structured = content_type in BILL_STRUCTURED_TYPES or name.endswith(BILL_STRUCTURED_EXTENSIONS)
                is_image_pdf = content_type in BILL_IMAGE_PDF_TYPES or name.endswith(
                    (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif")
                )
                if not (is_structured or is_image_pdf):
                    raise BusinessRuleError(
                        "Bill must be a PDF, image, CSV, or XLSX export from your "
                        + ("billing system." if kind == ImportJob.Kind.SALES_BILL else "supplier's system.")
                    )
                with transaction.atomic():
                    # CR-034: Compute file_sha256 on bill uploads
                    import hashlib

                    uploaded.seek(0)
                    file_bytes = uploaded.read()
                    uploaded.seek(0)
                    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

                    asset = FileService.store_upload(
                        company=self.company, uploaded_file=uploaded,
                        kind=FileAsset.Kind.IMPORT, user=request.user,
                    )
                    job = ImportJob.objects.create(
                        company=self.company, kind=kind, file=asset, file_sha256=sha256_hash,
                        supplier=supplier, customer=customer,
                        created_by=request.user, updated_by=request.user,
                    )
                    if is_structured:
                        BillImportService.parse_structured_file(job)
                    else:
                        # The photo/PDF goes to a third-party AI service: record that the
                        # uploader was told so and agreed, and when (23.10).
                        consent_given = str(request.data.get("ai_consent") or "").lower() in ("1", "true", "yes")
                        if not consent_given:  # S-03: never send an image without a recorded yes
                            raise BusinessRuleError(
                                "Confirm that this image may be sent to the AI service before scanning, "
                                "or upload a CSV/Excel export instead.",
                                code="AI_CONSENT_REQUIRED",
                            )
                        if consent_given:
                            from core.services.audit import AuditService

                            AuditService.log(
                                company=self.company, user=request.user, action="IMPORT",
                                entity_type="ImportJob", entity_id=job.pk,
                                description="AI processing consent given for a bill upload",
                                metadata={"event": "IMPORT_CONSENT", "kind": kind, "file_sha256": sha256_hash},
                            )
                        BillImportService.start_extraction(job)
                    job.refresh_from_db()
                    response = Response(self.get_serializer(job).data, status=status.HTTP_201_CREATED)
            else:
                # Master CSV/XLSX: atomic so a validate failure leaves no orphan job/asset.
                with transaction.atomic():
                    asset = FileService.store_upload(
                        company=self.company, uploaded_file=uploaded,
                        kind=FileAsset.Kind.IMPORT, user=request.user,
                    )
                    job = ImportJob.objects.create(
                        company=self.company, kind=kind, file=asset,
                        created_by=request.user, updated_by=request.user,
                    )
                    ImportService.validate(job)
                response = Response(self.get_serializer(job).data, status=status.HTTP_201_CREATED)

            if use_idempotency:
                store_record(
                    company=self.company,
                    scope="import_job_create",
                    raw_key=raw_key,
                    response=response,
                    resource_id=str(job.pk),
                )
                created_ok = True
            return response
        finally:
            if (
                use_idempotency
                and claimed is not None
                and not isinstance(claimed, Response)
                and not created_ok
            ):
                release_record(company=self.company, scope="import_job_create", raw_key=raw_key)
    @action(detail=True, methods=["post"], url_path="retry-extract", throttle_classes=[CompanyRateThrottle])
    def retry_extract(self, request, pk=None):
        """Re-run LLM extraction for FAILED (or UPLOADED) bill jobs."""
        job = self.get_object()
        BillImportService.start_extraction(job)
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"], url_path="clarify")
    def clarify(self, request, pk=None):
        """Answer document-level clarification questions (§4.3) and move the
        job from NEEDS_CLARIFICATION to PREVIEWED."""
        job = self.get_object()
        answers = request.data.get("answers")
        if not isinstance(answers, dict):
            raise BusinessRuleError("answers must be an object of {field: value}.")
        BillImportService.answer_clarifications(job, answers, user=request.user)
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post", "patch"], url_path="preview")
    def update_preview(self, request, pk=None):
        """Edit extracted bill preview lines / party before commit."""
        job = self.get_object()
        BillImportService.update_preview(job, request.data, user=request.user)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, HasCompany, CanImport])
    def commit(self, request, pk=None):
        """Commit requires Owner or explicit import permission (§5.5)."""
        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        if raw_key:
            # B3-013: claim an in-flight placeholder (not a bare get_record) so a
            # concurrent retry while the first commit is still running replays
            # instead of committing a second draft invoice.
            claimed = begin_record(
                company=self.company, scope="import_job_commit", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed

        try:
            job = self.get_object()
            # One atomic unit: a commit rejected by validation must leave the
            # stored preview exactly as it was (23.10).
            with transaction.atomic():
                if job.kind in ImportJob.BILL_KINDS and request.data:
                    # Allow last-minute supplier/customer / line tweaks on commit body.
                    BillImportService.update_preview(
                        job, request.data, user=request.user, strict_included=True
                    )
                    job.refresh_from_db()
                result = ImportService.commit(job, request.user)
        except Exception as exc:
            if raw_key:
                release_record(
                    company=self.company, scope="import_job_commit", raw_key=raw_key
                )
            extra = getattr(exc, "extra", None) or {}
            if isinstance(exc, BusinessRuleError) and ("lineErrors" in extra or "headerErrors" in extra):
                # Written after the atomic block rolled back, so the refusal itself is kept.
                try:
                    from core.services.audit import AuditService

                    codes = sorted(
                        {e.get("code") for r in extra.get("lineErrors", []) for e in r.get("errors", [])}
                        | {e.get("code") for e in extra.get("headerErrors", [])}
                    )
                    AuditService.log(
                        company=self.company, user=request.user, action="IMPORT",
                        entity_type="ImportJob", entity_id=pk or 0,
                        description="Bill commit refused: rows or header need fixing",
                        metadata={
                            "event": "IMPORT_REJECTED", "codes": codes,
                            "bad_lines": len(extra.get("lineErrors", [])),
                        },
                    )
                except Exception:  # noqa: BLE001 — auditing must never mask the real error
                    pass
            raise
        job.refresh_from_db()
        if isinstance(result, dict):
            response = Response({
                "created": result.get("created", 0),
                "products_created": result.get("products_created", 0),
                "purchase_invoice_id": result.get("purchase_invoice_id"),
                "sales_invoice_id": result.get("sales_invoice_id"),
                "status": job.status,
                "error_rows": job.error_rows,
            })
        else:
            response = Response(
                {"created": result, "status": job.status, "error_rows": job.error_rows}
            )
        if raw_key:
            store_record(
                company=self.company,
                scope="import_job_commit",
                raw_key=raw_key,
                response=response,
                resource_id=str(job.pk),
            )
        return response

    @action(detail=True, methods=["post"], url_path="void")
    def void_import(self, request, pk=None):
        """Owner recovery: reverse a committed import (master data, or a bill's draft)."""
        job = self.get_object()
        if job.kind in ImportJob.BILL_KINDS:
            cu = get_company_user(request)
            allowed = cu is not None and (
                cu.role in ("OWNER", "MANAGER") or job.created_by_id == request.user.pk
            )
            if not allowed:
                raise PermissionDenied("Only an owner, a manager, or the uploader can undo a bill import.")
            BillImportService.void_bill(job, request.user)
        else:
            if not IsOwner().has_permission(request, self):
                raise BusinessRuleError("Owner role required to void an import.")
            ImportService.void(job, request.user)
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"], url_path="validate")
    def validate_bill(self, request, pk=None):
        """Dry run of commit: every header/line problem at once, nothing written."""
        job = self.get_object()
        if job.kind not in ImportJob.BILL_KINDS:
            raise BusinessRuleError("Validation is only for bill imports.")
        with transaction.atomic():
            if request.data:
                BillImportService.update_preview(job, request.data, user=request.user)
            report = BillImportService.validation_report(job, request.user)
            transaction.set_rollback(True)
        return Response(report)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_import(self, request, pk=None):
        job = self.get_object()
        BillImportService.cancel(job, request.user)
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"], url_path="switch-kind")
    def switch_kind(self, request, pk=None):
        """Move a mis-uploaded bill to the other direction (purchase <-> sales)."""
        job = self.get_object()
        target = (request.data.get("kind") or "").upper()
        self._assert_kind_permission(target)
        BillImportService.switch_kind(job, target, request.user)
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["get"], url_path="file")
    def source_file(self, request, pk=None):
        """The uploaded bill, inline, for the side-by-side review viewer."""
        job = self.get_object()
        return FileService.inline_response(job.file)

    @action(detail=True, methods=["post"], url_path="void-rows")
    def void_rows(self, request, pk=None):
        """Reverse opening-stock (and product cleanup) for specific SKUs only."""
        if not IsOwner().has_permission(request, self):
            raise BusinessRuleError("Owner role required to void import rows.")
        job = self.get_object()
        skus = request.data.get("skus") or []
        if not isinstance(skus, list):
            raise BusinessRuleError("skus must be an array.")
        result = ImportService.void_rows(job, request.user, skus=[str(s) for s in skus])
        job = result["job"]
        job.refresh_from_db()
        payload = dict(self.get_serializer(job).data)
        payload["void_results"] = {"voided": result["voided"], "blocked": result["blocked"]}
        return Response(payload)

    @action(detail=True, methods=["get"], url_path="errors")
    def error_report(self, request, pk=None):
        job = self.get_object()
        fmt = (request.query_params.get("as") or request.query_params.get("format") or "").lower()
        if fmt == "csv":
            def generate():
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["row", "errors", "data"])
                yield buf.getvalue()
                for err in job.errors or []:
                    if not isinstance(err, dict):
                        continue
                    buf.seek(0)
                    buf.truncate(0)
                    msgs = err.get("errors") or []
                    msg = "; ".join(msgs) if isinstance(msgs, list) else str(msgs)
                    data = err.get("data") or {}
                    data_str = (
                        " | ".join(f"{k}={v}" for k, v in data.items() if v)
                        if isinstance(data, dict)
                        else str(data)
                    )
                    writer.writerow([err.get("row", ""), csv_safe(msg), csv_safe(data_str)])
                    yield buf.getvalue()

            filename = f"{(job.kind or 'import').lower()}_import_errors.csv"
            response = StreamingHttpResponse(generate(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        return Response({"errors": job.errors, "error_rows": job.error_rows})

    @action(detail=False, methods=["get"], url_path="template")
    def template(self, request):
        """Download the PRODUCTS template (xlsx with extra sheets, or CSV with the same item columns)."""
        kind = (request.query_params.get("kind") or "PRODUCTS").upper()
        if kind != "PRODUCTS":
            raise BusinessRuleError("An item template is currently published for PRODUCTS only.")
        company = get_company_user(request).company
        as_fmt = (request.query_params.get("as") or "").strip().lower()
        item_columns = products_item_columns(company)
        if as_fmt == "csv":
            response = HttpResponse(products_template_csv(company), content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="products_template.csv"'
            return response
        from openpyxl import Workbook

        workbook = Workbook()
        items = workbook.active
        items.title = "items"
        items.append(list(item_columns))
        items.append([""] * len(item_columns))
        items.freeze_panes = "A2"
        lots = workbook.create_sheet("opening_lots")
        lots.append(list(OPENING_LOTS_COLUMNS))
        lots.freeze_panes = "A2"
        serials = workbook.create_sheet("opening_serials")
        serials.append(list(OPENING_SERIALS_COLUMNS))
        serials.freeze_panes = "A2"
        notes = workbook.create_sheet("notes")
        notes.append(["Item import notes"])
        notes.append(["Only name is required. Other columns match Create Item: Basic, Stock, Pricing, Custom."])
        notes.append(["product_type: Goods or Service. Service rows cannot have opening stock, godown, batch, or serials."])
        notes.append(["opening_stock on this sheet posts to the default godown unless godown is filled."])
        notes.append(["track_batch Yes (or batch_no + expiry_date) posts a lot. Use opening_lots for multiple godowns/lots per SKU."])
        notes.append(["track_serial Yes with opening stock requires serial_no (comma-separated) or an opening_serials sheet. Quantity must equal the number of serials."])
        notes.append(["Blank godown uses the company default. Unknown godown names fail the whole job."])
        notes.append(["Custom field columns use the labels from Item Settings. Only active fields are included."])
        buffer = io.BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="products_import_template.xlsx"'
        return response

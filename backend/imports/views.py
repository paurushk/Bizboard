from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.models import FileAsset
from core.permissions import CanImport, HasCompany, get_company_user
from core.services.files import FileService
from masters.models import Supplier

from .models import ImportJob
from .serializers import ImportJobSerializer
from .services import BillImportService, ImportService

BILL_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}


class ImportJobViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ImportJobSerializer
    queryset = ImportJob.objects.all()
    permission_classes = [IsAuthenticated, HasCompany, CanImport]

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        return self.queryset.filter(company=self.company)

    def create(self, request, *args, **kwargs):
        """Upload + validate (CSV) or start LLM extraction (purchase bill)."""
        kind = (request.data.get("kind") or "").upper()
        if kind not in ImportJob.Kind.values:
            raise BusinessRuleError(f"kind must be one of {', '.join(ImportJob.Kind.values)}.")
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

        if kind == ImportJob.Kind.PURCHASE_BILL:
            content_type = (getattr(uploaded, "content_type", "") or "").lower()
            name = (uploaded.name or "").lower()
            ok_type = content_type in BILL_CONTENT_TYPES or name.endswith(
                (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif")
            )
            if not ok_type:
                raise BusinessRuleError("Purchase bill must be a PDF or image file.")
            asset = FileService.store_upload(
                company=self.company, uploaded_file=uploaded,
                kind=FileAsset.Kind.IMPORT, user=request.user,
            )
            job = ImportJob.objects.create(
                company=self.company, kind=kind, file=asset, supplier=supplier,
                created_by=request.user, updated_by=request.user,
            )
            BillImportService.start_extraction(job)
            job.refresh_from_db()
            return Response(self.get_serializer(job).data, status=status.HTTP_201_CREATED)

        asset = FileService.store_upload(
            company=self.company, uploaded_file=uploaded,
            kind=FileAsset.Kind.IMPORT, user=request.user,
        )
        job = ImportJob.objects.create(
            company=self.company, kind=kind, file=asset,
            created_by=request.user, updated_by=request.user,
        )
        ImportService.validate(job)
        return Response(self.get_serializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="retry-extract")
    def retry_extract(self, request, pk=None):
        """Re-run LLM extraction for FAILED (or UPLOADED) purchase-bill jobs."""
        job = self.get_object()
        BillImportService.start_extraction(job)
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post", "patch"], url_path="preview")
    def update_preview(self, request, pk=None):
        """Edit extracted purchase-bill preview lines / supplier before commit."""
        job = self.get_object()
        BillImportService.update_preview(job, request.data, user=request.user)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, HasCompany, CanImport])
    def commit(self, request, pk=None):
        """Commit requires Owner or explicit import permission (§5.5)."""
        job = self.get_object()
        if job.kind == ImportJob.Kind.PURCHASE_BILL and request.data:
            # Allow last-minute supplier / line tweaks on commit body.
            BillImportService.update_preview(job, request.data, user=request.user)
            job.refresh_from_db()
        result = ImportService.commit(job, request.user)
        job.refresh_from_db()
        if isinstance(result, dict):
            return Response({
                "created": result.get("created", 0),
                "products_created": result.get("products_created", 0),
                "purchase_invoice_id": result.get("purchase_invoice_id"),
                "status": job.status,
                "error_rows": job.error_rows,
            })
        return Response({"created": result, "status": job.status, "error_rows": job.error_rows})

    @action(detail=True, methods=["get"], url_path="errors")
    def error_report(self, request, pk=None):
        job = self.get_object()
        return Response({"errors": job.errors, "error_rows": job.error_rows})

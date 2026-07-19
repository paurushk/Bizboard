from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.models import FileAsset
from core.permissions import CanImport, HasCompany, get_company_user
from core.services.files import FileService

from .models import ImportJob
from .serializers import ImportJobSerializer
from .services import ImportService


class ImportJobViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ImportJobSerializer
    queryset = ImportJob.objects.all()
    permission_classes = [IsAuthenticated, HasCompany]

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        return self.queryset.filter(company=self.company)

    def create(self, request, *args, **kwargs):
        """Upload + validate in one step; response contains the preview."""
        kind = (request.data.get("kind") or "").upper()
        if kind not in ImportJob.Kind.values:
            raise BusinessRuleError(f"kind must be one of {', '.join(ImportJob.Kind.values)}.")
        uploaded = request.FILES.get("file")
        if not uploaded:
            raise BusinessRuleError("A CSV file is required.")
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

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, HasCompany, CanImport])
    def commit(self, request, pk=None):
        """Commit requires Owner or explicit import permission (§5.5)."""
        job = self.get_object()
        created = ImportService.commit(job, request.user)
        return Response({"created": created, "status": job.status, "error_rows": job.error_rows})

    @action(detail=True, methods=["get"], url_path="errors")
    def error_report(self, request, pk=None):
        job = self.get_object()
        return Response({"errors": job.errors, "error_rows": job.error_rows})

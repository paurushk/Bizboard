from django.http import FileResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditEvent, FileAsset, Notification
from .permissions import HasCompany, IsOwner, get_company_user
from .serializers import AuditEventSerializer, FileAssetSerializer, NotificationSerializer
from .services.files import FileService


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "version": "v1"})


class FileAssetViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FileAssetSerializer
    permission_classes = [IsAuthenticated, HasCompany]
    queryset = FileAsset.objects.all()

    def get_queryset(self):
        company = get_company_user(self.request).company
        qs = self.queryset.filter(company=company)
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def perform_create(self, serializer):
        uploaded = self.request.FILES.get("file")
        company = get_company_user(self.request).company
        serializer.instance = FileService.store_upload(
            company=company,
            uploaded_file=uploaded,
            kind=serializer.validated_data.get("kind", FileAsset.Kind.ATTACHMENT),
            user=self.request.user,
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        asset = self.get_object()
        return FileResponse(asset.file.open("rb"), as_attachment=True, filename=asset.original_name)


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, HasCompany]
    queryset = Notification.objects.all()

    def get_queryset(self):
        company = get_company_user(self.request).company
        return self.queryset.filter(company=company)


class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]
    queryset = AuditEvent.objects.all()

    def get_queryset(self):
        company = get_company_user(self.request).company
        qs = self.queryset.filter(company=company)
        action_filter = self.request.query_params.get("action")
        if action_filter:
            qs = qs.filter(action=action_filter)
        return qs

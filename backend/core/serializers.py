from rest_framework import serializers

from core.permissions import get_company_user

from .models import AuditEvent, FileAsset, Notification, StatutoryDocumentEvent


class CompanyPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """BB-000085 / BB-000672: resolve FKs only within the request company."""

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.context.get("request") if self.context else None
        if request is None:
            return qs.none()
        cu = get_company_user(request)
        if cu is None:
            return qs.none()
        return qs.filter(company=cu.company)


class AuditEventSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "action", "entity_type", "entity_id", "description",
            "metadata", "user", "user_email", "user_name", "created_at",
        ]


class FileAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = FileAsset
        fields = ["id", "kind", "file", "url", "original_name", "content_type", "size", "created_at"]
        read_only_fields = ["original_name", "content_type", "size"]

    def get_url(self, obj):
        # Points at the authenticated download action, not the raw storage
        # path — /media/ is nginx-internal-only (BUG-703) so a direct
        # obj.file.url is not fetchable by an unauthenticated client anyway.
        if not obj.file:
            return None
        request = self.context.get("request")
        path = f"/api/v1/files/{obj.id}/download/"
        return request.build_absolute_uri(path) if request else path


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "channel", "recipient", "subject", "body",
            "status", "share_link", "error", "created_at",
        ]


class StatutoryDocumentEventSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = StatutoryDocumentEvent
        fields = [
            "id", "entity_type", "entity_id", "event_type",
            "payload", "user", "user_email", "created_at",
        ]

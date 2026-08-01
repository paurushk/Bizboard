from rest_framework import serializers

from .models import AuditEvent, FileAsset, Notification


class AuditEventSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "action", "entity_type", "entity_id", "description",
            "metadata", "user", "user_email", "created_at",
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

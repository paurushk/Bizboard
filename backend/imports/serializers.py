from rest_framework import serializers

from .models import ImportJob

# Cap list payloads on the wire; full arrays stay on the job for commit / CSV export.
PREVIEW_RESPONSE_CAP = 50
ERROR_RESPONSE_CAP = 100


class ImportJobSerializer(serializers.ModelSerializer):
    preview_truncated = serializers.SerializerMethodField()
    errors_truncated = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id", "kind", "file", "status", "total_rows", "valid_rows",
            "error_rows", "preview", "errors", "preview_truncated", "errors_truncated",
            "column_mappings", "voided_rows", "clarifications", "committed_at",
            "created_at", "supplier", "customer", "purchase_invoice",
            "sales_invoice", "bill_template", "failure_reason",
        ]
        read_only_fields = [
            "file", "status", "total_rows", "valid_rows", "error_rows",
            "preview", "errors", "preview_truncated", "errors_truncated",
            "column_mappings", "voided_rows", "clarifications", "committed_at",
            "purchase_invoice", "sales_invoice", "bill_template",
            "failure_reason",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        preview = data.get("preview")
        if isinstance(preview, list) and len(preview) > PREVIEW_RESPONSE_CAP:
            data["preview"] = preview[:PREVIEW_RESPONSE_CAP]
        errors = data.get("errors")
        if isinstance(errors, list) and len(errors) > ERROR_RESPONSE_CAP:
            data["errors"] = errors[:ERROR_RESPONSE_CAP]
        return data

    def get_preview_truncated(self, instance):
        preview = instance.preview
        if isinstance(preview, list) and len(preview) > PREVIEW_RESPONSE_CAP:
            return len(preview) - PREVIEW_RESPONSE_CAP
        return 0

    def get_errors_truncated(self, instance):
        errors = instance.errors
        if isinstance(errors, list) and len(errors) > ERROR_RESPONSE_CAP:
            return len(errors) - ERROR_RESPONSE_CAP
        return 0

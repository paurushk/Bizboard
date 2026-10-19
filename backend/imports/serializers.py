from rest_framework import serializers

from .models import ImportJob

# Cap list payloads on the wire; full arrays stay on the job for commit / CSV export.
PREVIEW_RESPONSE_CAP = 50
ERROR_RESPONSE_CAP = 100


class ImportJobSerializer(serializers.ModelSerializer):
    preview_truncated = serializers.SerializerMethodField()
    errors_truncated = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField(help_text="Who uploaded it.")
    can_undo = serializers.SerializerMethodField(
        help_text="Product and opening-stock imports can be undone while their stock is unused; "
        "bills while still a draft. Customer and supplier imports cannot be undone."
    )

    def get_created_by_name(self, obj) -> str:
        user = getattr(obj, "created_by", None)
        return (getattr(user, "full_name", "") or getattr(user, "email", "")) if user else ""

    def get_can_undo(self, obj) -> bool:
        return obj.status == ImportJob.Status.COMMITTED and (
            obj.kind in (ImportJob.Kind.PRODUCTS, ImportJob.Kind.OPENING_STOCK) or obj.kind in ImportJob.BILL_KINDS
        )

    class Meta:
        model = ImportJob
        fields = [
            "id", "kind", "file", "status", "total_rows", "valid_rows",
            "error_rows", "preview", "errors", "preview_truncated", "errors_truncated",
            "column_mappings", "voided_rows", "clarifications", "committed_at",
            "created_at", "supplier", "customer", "purchase_invoice",
            "sales_invoice", "bill_template", "failure_reason",
            "file_name", "file_type", "extraction_heartbeat_at", "created_by_name", "can_undo",
        ]
        read_only_fields = [
            "file_name", "file_type", "extraction_heartbeat_at", "created_by_name", "can_undo",
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
        # Bill previews (dict) are NEVER capped: the review screen edits and
        # sends back every line, so a capped copy would let a commit overwrite
        # rows the client never saw (UPLOAD_SALES_BILL_REVIEW 23.1). The size
        # is bounded at extraction by BILL_PREVIEW_MAX_LINES instead.
        errors = data.get("errors")
        if isinstance(errors, list) and len(errors) > ERROR_RESPONSE_CAP:
            data["errors"] = errors[:ERROR_RESPONSE_CAP]
        return data

    def get_preview_truncated(self, instance):
        preview = instance.preview
        if isinstance(preview, list) and len(preview) > PREVIEW_RESPONSE_CAP:
            return len(preview) - PREVIEW_RESPONSE_CAP
        return 0

    def get_file_name(self, instance):
        asset = getattr(instance, "file", None)
        return (getattr(asset, "original_name", "") or "") if asset else ""

    def get_file_type(self, instance):
        asset = getattr(instance, "file", None)
        return (getattr(asset, "content_type", "") or "") if asset else ""

    def get_errors_truncated(self, instance):
        errors = instance.errors
        if isinstance(errors, list) and len(errors) > ERROR_RESPONSE_CAP:
            return len(errors) - ERROR_RESPONSE_CAP
        return 0

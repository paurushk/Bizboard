from rest_framework import serializers

from .models import ImportJob


class ImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = [
            "id", "kind", "file", "status", "total_rows", "valid_rows",
            "error_rows", "preview", "errors", "committed_at", "created_at",
            "supplier", "purchase_invoice", "failure_reason",
        ]
        read_only_fields = [
            "file", "status", "total_rows", "valid_rows", "error_rows",
            "preview", "errors", "committed_at", "purchase_invoice",
            "failure_reason",
        ]

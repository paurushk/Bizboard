from rest_framework import serializers

from .models import JobCard, JobCardLine


class JobCardLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCardLine
        fields = ["id", "kind", "product", "quantity", "unit_price", "serial"]
        read_only_fields = ["id"]


class JobCardSerializer(serializers.ModelSerializer):
    lines = JobCardLineSerializer(many=True, read_only=True)
    serial_history = serializers.SerializerMethodField()

    class Meta:
        model = JobCard
        fields = [
            "id", "number", "customer", "technician", "status", "complaint",
            "sales_invoice", "lines", "serial_history", "created_at",
        ]
        read_only_fields = ["id", "number", "status", "sales_invoice", "created_at"]

    def get_serial_history(self, job):
        from .history import serial_history

        return serial_history(job)

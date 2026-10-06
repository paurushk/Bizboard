from rest_framework import serializers

from .models import JobCard, JobCardLine


class JobCardLineSerializer(serializers.ModelSerializer):
    commission_amount = serializers.SerializerMethodField()

    class Meta:
        model = JobCardLine
        fields = [
            "id", "kind", "product", "quantity", "unit_price",
            "labour_minutes", "technician_commission_percent", "commission_amount",
            "serial", "batch", "batch_no",
        ]
        read_only_fields = ["id", "commission_amount"]

    def get_commission_amount(self, line):
        from .services import labour_commission_amount

        return str(labour_commission_amount(line))

    def validate_quantity(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_price(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value


class JobCardSerializer(serializers.ModelSerializer):
    lines = JobCardLineSerializer(many=True, read_only=True)
    serial_history = serializers.SerializerMethodField()

    class Meta:
        model = JobCard
        fields = [
            "id", "number", "customer", "technician", "status", "complaint",
            "registration_no", "vehicle_model", "odometer_reading",
            "service_bay", "scheduled_start", "scheduled_end",
            "sales_invoice", "lines", "serial_history", "created_at",
        ]
        read_only_fields = ["id", "number", "status", "sales_invoice", "created_at"]

    def get_serial_history(self, job):
        from .history import serial_history

        return serial_history(job)

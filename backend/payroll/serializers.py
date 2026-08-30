import re
from decimal import Decimal

from rest_framework import serializers

from .models import Employee, PayRun, PaySlip

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            "id", "name", "code", "salary", "basic", "da", "status",
            "pf_applicable", "pf_wage_ceiling", "esi_applicable", "pt_state", "tds_rate",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_salary(self, value):
        if value is None or Decimal(str(value)) < 0:
            raise serializers.ValidationError("Salary must be zero or greater.")
        return value


class PaySlipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = PaySlip
        fields = [
            "id", "employee", "employee_name", "gross", "period_days", "paid_days",
            "deductions", "net",
            "pf_employee", "esi_employee", "pt_amount", "pf_employer", "esi_employer", "tds_amount",
        ]


class PayRunSerializer(serializers.ModelSerializer):
    slips = PaySlipSerializer(many=True, read_only=True)

    class Meta:
        model = PayRun
        fields = ["id", "period", "status", "slips", "created_at", "updated_at"]
        read_only_fields = ["status", "slips", "created_at", "updated_at"]

    def validate_period(self, value):
        if not PERIOD_RE.match(str(value or "")):
            raise serializers.ValidationError("Period must be YYYY-MM.")
        return value

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        if instance is not None and instance.status == PayRun.Status.COMPLETED:
            raise serializers.ValidationError("Completed pay runs are immutable.")
        return attrs

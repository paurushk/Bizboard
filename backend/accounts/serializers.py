from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Company, CompanyUser, User


class RegisterSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class CompanySerializer(serializers.ModelSerializer):
    is_gst_registered = serializers.BooleanField(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id", "name", "legal_name", "gstin", "registration_type", "state",
            "address", "city", "pincode", "phone", "email", "upi_id",
            "bank_name", "bank_account", "bank_ifsc", "logo", "signature",
            "fy_start_month", "negative_stock_policy", "invoice_terms",
            "assume_local_state_for_blank_party", "is_gst_registered",
        ]


class CompanyUserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = CompanyUser
        fields = [
            "id", "user", "email", "full_name", "phone", "role",
            "can_manage_inventory", "can_import",
            "can_cancel_documents", "can_view_financial_reports", "can_export",
            "is_active",
        ]
        read_only_fields = ["user"]


class InviteUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=CompanyUser.Role.choices, default=CompanyUser.Role.SALES_STAFF)
    can_manage_inventory = serializers.BooleanField(default=False)
    can_import = serializers.BooleanField(default=False)
    can_cancel_documents = serializers.BooleanField(default=False)
    can_view_financial_reports = serializers.BooleanField(default=True)
    can_export = serializers.BooleanField(default=False)


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="user.id")
    email = serializers.EmailField(source="user.email")
    full_name = serializers.CharField(source="user.full_name")
    phone = serializers.CharField(source="user.phone")
    role = serializers.CharField()
    can_manage_inventory = serializers.BooleanField()
    can_import = serializers.BooleanField()
    can_cancel_documents = serializers.BooleanField()
    can_view_financial_reports = serializers.BooleanField()
    can_export = serializers.BooleanField()
    company_id = serializers.IntegerField(source="company.id")
    company = CompanySerializer()

from rest_framework import serializers

from banking.models import AaConsent, AaTransaction


class AaConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AaConsent
        fields = ["id", "consent_id", "status", "fi_type", "created_at", "updated_at"]
        read_only_fields = fields


class AaTransactionSerializer(serializers.ModelSerializer):
    consent_id = serializers.CharField(source="consent.consent_id", read_only=True)
    matched_receipt_id = serializers.IntegerField(source="matched_payment_id", read_only=True)

    class Meta:
        model = AaTransaction
        fields = [
            "id",
            "consent_id",
            "txn_id",
            "amount",
            "txn_date",
            "raw",
            "matched_receipt_id",
            "created_at",
        ]
        read_only_fields = fields


class AaIngestSerializer(serializers.Serializer):
    consent_id = serializers.CharField(max_length=128)
    fi_type = serializers.CharField(max_length=32, required=False, default="DEPOSIT")
    status = serializers.ChoiceField(
        choices=AaConsent.Status.choices, required=False, default=AaConsent.Status.ACTIVE
    )
    transactions = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    use_mock_fiu = serializers.BooleanField(required=False, default=False)
    use_live_fiu = serializers.BooleanField(required=False, default=False)

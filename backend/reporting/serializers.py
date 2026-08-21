"""Reporting serializers (Wave 17A GSTR-2B ingest)."""

from rest_framework import serializers

from .models import Gstr2bIngest


class Gstr2bIngestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gstr2bIngest
        fields = [
            "id",
            "period",
            "supplier_gstin",
            "invoice_number",
            "invoice_date",
            "taxable_value",
            "igst",
            "cgst",
            "sgst",
            "match_status",
            "itc_eligibility",
            "purchase_invoice",
            "raw",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["match_status", "purchase_invoice", "created_at", "updated_at"]

    def validate_itc_eligibility(self, value):
        if value != Gstr2bIngest.ItcEligibility.CLAIMABLE:
            return value
        inv = getattr(self.instance, "purchase_invoice", None) if self.instance else None
        if inv is None:
            raise serializers.ValidationError(
                "Cannot mark CLAIMABLE until the 2B row is matched to a purchase invoice."
            )
        from purchases.models import PurchaseInvoice

        if getattr(inv, "itc_eligibility", "") != PurchaseInvoice.ItcEligibility.CLAIMABLE:
            raise serializers.ValidationError(
                "Purchase invoice ITC must be CLAIMABLE before marking this 2B row CLAIMABLE."
            )
        return value

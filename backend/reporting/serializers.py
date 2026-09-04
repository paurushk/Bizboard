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
            "cess",
            "match_status",
            "match_class",
            "itc_eligibility",
            "ims_action",
            "ims_remark",
            "acted_at",
            "section_16_4_deadline",
            "purchase_invoice",
            "raw",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "match_status",
            "match_class",
            "ims_action",
            "acted_at",
            "section_16_4_deadline",
            "purchase_invoice",
            "created_at",
            "updated_at",
            # B5-005: identity + tax amounts + raw + remark must not be
            # rewritable via a plain PATCH — that silently moves
            # `claimable_itc_from_2b` totals with no ImsActionHistory and no
            # re-match. Only `itc_eligibility` stays writable (a real manual
            # override), and the viewset reclasses the books when it changes.
            "period",
            "supplier_gstin",
            "invoice_number",
            "invoice_date",
            "taxable_value",
            "igst",
            "cgst",
            "sgst",
            "cess",
            "ims_remark",
            "raw",
        ]

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

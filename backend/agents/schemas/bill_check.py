from rest_framework import serializers


class ComparisonRowV1(serializers.Serializer):
    field = serializers.CharField(max_length=200)
    left = serializers.CharField(max_length=64, allow_blank=True, default="")
    right = serializers.CharField(max_length=64, allow_blank=True, default="")
    mismatch = serializers.BooleanField(default=False)


class SupplierQueryPayloadV1(serializers.Serializer):
    """A message to a supplier about differences on a draft purchase bill. Copy or share only; nothing is sent."""

    supplier_id = serializers.IntegerField(min_value=1)
    supplier_name = serializers.CharField(max_length=200)
    bill_id = serializers.IntegerField(min_value=1)
    bill_number = serializers.CharField(max_length=64, allow_blank=True, default="")
    text = serializers.CharField(max_length=2000)
    internal_notes = serializers.ListField(child=serializers.CharField(max_length=300), required=False, default=list, max_length=20)
    rows = ComparisonRowV1(many=True, required=False, default=list, max_length=200)
    findings_digest = serializers.CharField(max_length=64)


class BillReviewNotePayloadV1(serializers.Serializer):
    """Findings on a draft bill that are for the owner, not the supplier (no receipt yet, unusually high amount,
    cancelled supplier GSTIN). Approving means the owner has read them."""

    bill_id = serializers.IntegerField(min_value=1)
    bill_number = serializers.CharField(max_length=64, allow_blank=True, default="")
    supplier_name = serializers.CharField(max_length=200, allow_blank=True, default="")
    internal_notes = serializers.ListField(child=serializers.CharField(max_length=300), min_length=1, max_length=20)
    rows = ComparisonRowV1(many=True, required=False, default=list, max_length=200)
    findings_digest = serializers.CharField(max_length=64)

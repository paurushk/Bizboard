from decimal import Decimal, InvalidOperation

from rest_framework import serializers

MATCH_SOURCES = ["alias", "code", "name", "phone", "fuzzy", "manual", "none"]


class AlternativeV1(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255)
    score = serializers.FloatField(required=False, default=0)


class MatchV1(serializers.Serializer):
    source = serializers.ChoiceField(choices=MATCH_SOURCES, default="none")
    score = serializers.FloatField(required=False, default=0)


class OrderLineV1(serializers.Serializer):
    """One grid row. ``raw`` is what the customer wrote; ids and quantities are what the grid edits."""

    raw = serializers.CharField(max_length=300, allow_blank=True, default="")
    raw_norm = serializers.CharField(max_length=300, allow_blank=True, default="")
    qty = serializers.CharField(max_length=20, allow_null=True, allow_blank=True, default=None)
    unit = serializers.CharField(max_length=24, allow_blank=True, default="")
    product_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    product_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    match = MatchV1(required=False, default=dict)
    alternatives = AlternativeV1(many=True, required=False, default=list, max_length=10)
    warnings = serializers.ListField(child=serializers.CharField(max_length=200), required=False, default=list, max_length=20)

    def validate_qty(self, value):
        if value in (None, ""):
            return None
        try:
            q = Decimal(str(value).strip())
        except InvalidOperation:
            raise serializers.ValidationError("Quantity must be a number.")
        if not q.is_finite() or q <= 0 or q > Decimal("1000000"):
            raise serializers.ValidationError("Quantity must be between 0.001 and 1,000,000.")
        return format(q.normalize(), "f")


class SalesOrderDraftPayloadV1(serializers.Serializer):
    """A sales order the agent read from pasted text. The server never takes prices from the text: the
    order is priced by the same rules as a hand-entered one when it is created."""

    customer_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    customer_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    customer_hint = serializers.CharField(max_length=255, allow_blank=True, default="")
    customer_match = MatchV1(required=False, default=dict)
    customer_alternatives = AlternativeV1(many=True, required=False, default=list, max_length=10)
    lines = OrderLineV1(many=True, min_length=1, max_length=100)
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")
    warnings = serializers.ListField(child=serializers.CharField(max_length=240), required=False, default=list, max_length=50)

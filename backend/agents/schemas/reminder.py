from rest_framework import serializers


class ReminderPayloadV1(serializers.Serializer):
    """A payment reminder the user reviews, copies or shares. Nothing is sent by the system in R2."""

    customer_id = serializers.IntegerField(min_value=1)
    customer_name = serializers.CharField(max_length=200)
    text = serializers.CharField(max_length=2000)
    language = serializers.ChoiceField(choices=["en", "hi"], default="en")
    tone = serializers.ChoiceField(choices=["polite", "firm"], default="polite")
    total_overdue = serializers.CharField(max_length=32)
    # "<language>:<tone>" -> text. Lets the drawer switch wording without another round trip.
    variants = serializers.DictField(child=serializers.CharField(max_length=2000), required=False, default=dict)

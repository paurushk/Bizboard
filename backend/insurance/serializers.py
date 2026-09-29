from rest_framework import serializers

from .models import Policy, PolicyOption, PolicyOptionSet, PolicyProduct


class PolicyProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyProduct
        fields = [
            "id", "name", "insurer_name", "line", "tenure_months", "sum_insured", "premium", "is_active",
        ]
        read_only_fields = ["id"]


class PolicyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyOption
        fields = ["id", "product", "chosen"]
        read_only_fields = ["id"]


class PolicyOptionSetSerializer(serializers.ModelSerializer):
    options = PolicyOptionSerializer(many=True, read_only=True)

    class Meta:
        model = PolicyOptionSet
        fields = ["id", "lead", "name", "options"]
        read_only_fields = ["id"]


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        fields = [
            "id", "number", "customer", "product", "option", "lead", "campaign", "advisor",
            "nominee", "start_date", "end_date", "status", "premium",
        ]
        read_only_fields = ["id", "number", "status", "premium", "end_date", "advisor"]

from rest_framework import serializers

from .models import Project, ProjectMilestone


class ProjectMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = [
            "id", "name", "sequence", "amount", "target_completion_date",
            "service_product", "status", "sales_invoice",
        ]
        read_only_fields = ["id", "status", "sales_invoice"]


class ProjectSerializer(serializers.ModelSerializer):
    milestones = ProjectMilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = ["id", "number", "customer", "name", "status", "milestones", "created_at"]
        read_only_fields = ["id", "number", "status", "created_at"]

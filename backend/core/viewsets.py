from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .permissions import HasCompany, get_company_user
from .services.audit import AuditService


class CompanyScopedViewSet(viewsets.ModelViewSet):
    """
    Base viewset enforcing tenant isolation: querysets filtered by the
    requesting user's company; created rows stamped with company + audit fields.
    """

    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        from billing.permissions import SubscriptionWritesAllowed

        return [*super().get_permissions(), SubscriptionWritesAllowed()]
    audit_entity: str = ""

    @property
    def company_user(self):
        return get_company_user(self.request)

    @property
    def company(self):
        return self.company_user.company

    def get_queryset(self):
        return super().get_queryset().filter(company=self.company)

    def perform_create(self, serializer):
        instance = serializer.save(
            company=self.company,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        self._audit("CREATE", instance)

    def perform_update(self, serializer):
        # BB-000084: never allow company reassignment via mass assignment.
        instance = serializer.save(updated_by=self.request.user, company=self.company)
        self._audit("UPDATE", instance)

    def perform_destroy(self, instance):
        entity_id = str(instance.pk)
        instance.delete()
        self._audit_raw("DELETE", entity_id)

    def _audit(self, action, instance):
        self._audit_raw(action, str(instance.pk))

    def _audit_raw(self, action, entity_id):
        AuditService.log(
            company=self.company,
            user=self.request.user,
            action=action,
            entity_type=self.audit_entity or self.get_queryset().model.__name__,
            entity_id=entity_id,
        )

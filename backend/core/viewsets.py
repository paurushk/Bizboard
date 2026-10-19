from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .permissions import HasCompany, get_company_user
from .services.audit import AuditService


CLIENT_SOURCES = frozenset({"quick_entry", "web", "mobile"})


def client_source(request) -> str:
    """Allow-listed `X-Client-Source` header; anything else is reported as `web`."""
    raw = (request.headers.get("X-Client-Source") or "").strip().lower()
    return raw if raw in CLIENT_SOURCES else "web"


class CompanyScopedViewSet(viewsets.ModelViewSet):
    """
    Base viewset enforcing tenant isolation: querysets filtered by the
    requesting user's company; created rows stamped with company + audit fields.
    """

    permission_classes = [IsAuthenticated, HasCompany]

    # Actions only an owner may run (delete, cancel …); the rest follow ``permission_classes``.
    owner_only_actions: tuple = ()

    def get_permissions(self):
        from billing.permissions import SubscriptionWritesAllowed

        permissions = [*super().get_permissions(), SubscriptionWritesAllowed()]
        if getattr(self, "action", None) in self.owner_only_actions:
            from .permissions import IsOwner

            permissions.append(IsOwner())
        return permissions
    audit_entity: str = ""

    @property
    def company_user(self):
        return get_company_user(self.request)

    @property
    def company(self):
        return self.company_user.company

    # Fields a free-text ``?q=`` (alias ``?search=``) matches with icontains. Empty = no search.
    search_fields: tuple = ()

    def get_queryset(self):
        qs = super().get_queryset().filter(company=self.company)
        return self.apply_search(qs)

    def apply_search(self, qs):
        """FND-01: one server-side search convention for the care and job screens."""
        if not self.search_fields:
            return qs
        params = getattr(getattr(self, "request", None), "query_params", {})
        term = (params.get("q") or params.get("search") or "").strip()[:100]
        if not term:
            return qs
        from django.db.models import Q

        query = Q()
        for field in self.search_fields:
            query |= Q(**{f"{field}__icontains": term})
        return qs.filter(query)

    def check_expected_version(self, instance):
        """FND-12: optimistic concurrency for field edits.

        A client that sends ``X-Expected-Updated-At`` (the ``updated_at`` it loaded) gets a 409 when
        the row changed since. A client that sends nothing is not checked.
        """
        expected = (self.request.headers.get("X-Expected-Updated-At") or "").strip()
        if not expected:
            return
        from django.utils.dateparse import parse_datetime

        from .exceptions import ConflictError

        sent = parse_datetime(expected)
        current = getattr(instance, "updated_at", None)
        if sent is None or current is None:
            return
        if abs((current - sent).total_seconds()) > 0.001:
            raise ConflictError("This record was changed by someone else. Reload and try again.")

    def perform_create(self, serializer):
        instance = serializer.save(
            company=self.company,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        self._audit("CREATE", instance)

    #: Set True on Settings viewsets: the audit entry then records each changed field (old and new).
    audit_changes = False

    def perform_update(self, serializer):
        self.check_expected_version(serializer.instance)
        before = None
        if self.audit_changes:
            from core.settings_audit import snapshot

            before = snapshot(serializer.instance, serializer.validated_data.keys())
        # BB-000084: never allow company reassignment via mass assignment.
        instance = serializer.save(updated_by=self.request.user, company=self.company)
        if before is not None:
            from core.settings_audit import diff_instance

            self._audit_raw("UPDATE", str(instance.pk), extra={"changes": diff_instance(instance, before.keys(), before)})
        else:
            self._audit("UPDATE", instance)

    def perform_destroy(self, instance):
        entity_id = str(instance.pk)
        instance.delete()
        self._audit_raw("DELETE", entity_id)

    def _audit(self, action, instance):
        self._audit_raw(action, str(instance.pk))

    def audit_metadata(self) -> dict:
        """Extra audit metadata for this request; subclasses override (default: none)."""
        return {}

    def _audit_raw(self, action, entity_id, extra=None):
        metadata = dict(self.audit_metadata() or {})
        if extra:
            metadata.update(extra)
        AuditService.log(
            company=self.company,
            user=self.request.user,
            action=action,
            entity_type=self.audit_entity or self.get_queryset().model.__name__,
            entity_id=entity_id,
            metadata=metadata or None,
        )

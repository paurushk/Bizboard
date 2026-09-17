"""Shared Django admin mixins."""

from django.contrib import admin


class SuperuserOnlyAdminMixin:
    """4.5 — money / tenant admin surfaces are superuser-only, not staff."""

    def has_module_permission(self, request):
        return bool(getattr(request.user, "is_superuser", False))

    def has_view_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False))

    def has_add_permission(self, request):
        return bool(getattr(request.user, "is_superuser", False))

    def has_change_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False))

    def has_delete_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False))


class SuperuserOnlyModelAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    pass

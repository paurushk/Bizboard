from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.admin import SuperuserOnlyAdminMixin

from .models import Company, CompanyUser, User


class UserAdmin(DjangoUserAdmin):
    """Custom User has no username field — reuse Django's UserAdmin but avoid
    the default fieldsets referencing 'username' and expose the raw password
    only through the read-only hashed-value widget (never as a plain
    CharField, which silently stores whatever text is typed as the new
    'hash' — BUG-116)."""

    ordering = ["email"]
    list_display = ["email", "full_name", "phone", "is_active", "is_staff"]
    search_fields = ["email", "full_name", "phone"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Company)
class CompanyAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "gstin", "state")
    search_fields = ("name", "gstin")


@admin.register(CompanyUser)
class CompanyUserAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("company", "user", "role")
    search_fields = ("user__email",)


admin.site.register(User, UserAdmin)

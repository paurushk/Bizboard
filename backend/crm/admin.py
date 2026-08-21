from django.contrib import admin

from .models import Lead, LeadActivity, Opportunity


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "phone", "email", "company")
    list_filter = ("status",)
    search_fields = ("name", "phone", "email")


@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ("lead", "kind", "created_at", "company")
    list_filter = ("kind",)


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("title", "stage", "amount", "company")
    list_filter = ("stage",)
    search_fields = ("title",)

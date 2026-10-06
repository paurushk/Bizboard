from django.contrib import admin

from .growth_metrics import growth_metrics
from .models import ShopFloorEvent


@admin.register(ShopFloorEvent)
class ShopFloorEventAdmin(admin.ModelAdmin):
    list_display = ("event", "company", "occurred_on", "journey", "success")
    list_filter = ("event", "journey")
    readonly_fields = ("event", "company", "occurred_on", "journey", "success", "created_at")

    change_list_template = "admin/insights/shopfloorevent/change_list.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        company_id = request.GET.get("company__id__exact") or request.GET.get("company__id")
        if company_id:
            from accounts.models import Company

            company = Company.objects.filter(pk=company_id).first()
            if company is not None:
                extra_context["growth_metrics"] = growth_metrics(company)
                extra_context["growth_company"] = company
        return super().changelist_view(request, extra_context=extra_context)

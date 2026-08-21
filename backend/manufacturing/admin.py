from django.contrib import admin

from .models import Bom, BomLine, WorkOrder, WorkOrderLine


class BomLineInline(admin.TabularInline):
    model = BomLine
    extra = 0


@admin.register(Bom)
class BomAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "status", "company")
    list_filter = ("status",)
    search_fields = ("name",)
    inlines = [BomLineInline]


class WorkOrderLineInline(admin.TabularInline):
    model = WorkOrderLine
    extra = 0
    readonly_fields = ("component", "qty_per_unit", "qty")


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "bom", "qty", "status", "company")
    list_filter = ("status",)
    search_fields = ("id",)
    inlines = [WorkOrderLineInline]

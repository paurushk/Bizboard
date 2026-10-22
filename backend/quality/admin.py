from django.contrib import admin

from .models import DefectCode, Inspection, InspectionTemplate, NonConformance


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("number", "product", "stage", "status", "decision", "company")
    list_filter = ("stage", "status", "decision")


admin.site.register(InspectionTemplate)
admin.site.register(NonConformance)
admin.site.register(DefectCode)

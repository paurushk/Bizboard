from django.contrib import admin

from .models import Employee, PayRun, PaySlip


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "salary", "status", "company")
    list_filter = ("status",)
    search_fields = ("code", "name")
    fieldsets = (
        (None, {
            "fields": (
                "company", "code", "name", "salary", "status",
                "pf_applicable", "pf_wage_ceiling", "esi_applicable", "pt_state",
            ),
            "description": (
                "Preview payroll: simplified PF 12% / ESI 0.75% / PT slabs. "
                "Not full statutory payroll, TDS, or HRMS."
            ),
        }),
    )


@admin.register(PayRun)
class PayRunAdmin(admin.ModelAdmin):
    list_display = ("period", "status", "company")
    list_filter = ("status",)


@admin.register(PaySlip)
class PaySlipAdmin(admin.ModelAdmin):
    list_display = ("id", "pay_run", "employee", "gross", "pf_employee", "esi_employee", "pt_amount", "net")
    search_fields = ("employee__name", "employee__code")

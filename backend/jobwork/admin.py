from django.contrib import admin

from .models import JobWorkChallan, JobWorkOrder, JobWorkReceipt

admin.site.register(JobWorkOrder)
admin.site.register(JobWorkChallan)
admin.site.register(JobWorkReceipt)

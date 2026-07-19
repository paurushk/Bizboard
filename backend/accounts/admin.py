from django.contrib import admin

from .models import Company, CompanyUser, User

admin.site.register(User)
admin.site.register(Company)
admin.site.register(CompanyUser)

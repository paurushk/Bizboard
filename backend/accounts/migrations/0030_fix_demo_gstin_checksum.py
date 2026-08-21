from django.db import migrations

_OLD = "29ABCDE1234F1Z5"
_NEW = "29ABCDE1234F1ZW"


def forwards(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    CompanyGstin = apps.get_model("accounts", "CompanyGstin")
    Company.objects.filter(gstin=_OLD).update(gstin=_NEW)
    CompanyGstin.objects.filter(gstin=_OLD).update(gstin=_NEW)


def backwards(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    CompanyGstin = apps.get_model("accounts", "CompanyGstin")
    Company.objects.filter(gstin=_NEW).update(gstin=_OLD)
    CompanyGstin.objects.filter(gstin=_NEW).update(gstin=_OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0029_company_pan_udyam"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

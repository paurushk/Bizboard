from django.db import migrations


def mark_sales_templates(apps, schema_editor):
    """Templates keyed by the company's *own* GSTIN were learned from sales bills.

    Before bill templates carried a direction, a sales bill's "supplier" GSTIN
    (the issuer, i.e. the tenant itself) was the key, while purchase templates
    are keyed by a vendor's GSTIN. So a template whose GSTIN is one of the
    company's own is a sales layout.
    """
    Template = apps.get_model("imports", "SupplierBillTemplate")
    Company = apps.get_model("accounts", "Company")
    CompanyGstin = apps.get_model("accounts", "CompanyGstin")
    for company in Company.objects.all().iterator():
        own = {(g or "").upper() for g in CompanyGstin.objects.filter(company=company).values_list("gstin", flat=True)}
        if company.gstin:
            own.add(company.gstin.upper())
        if not own:
            continue
        for template in Template.objects.filter(company=company, kind="PURCHASE_BILL"):
            if (template.gstin or "").upper() in own:
                template.kind = "SALES_BILL"
                template.save(update_fields=["kind"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("imports", "0010_bill_import_review_v2"),
        ("accounts", "0061_money_in_policy_settings"),
    ]
    operations = [migrations.RunPython(mark_sales_templates, noop)]

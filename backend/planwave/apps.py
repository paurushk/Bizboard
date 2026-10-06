from django.apps import AppConfig


class PlanwaveConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "planwave"

    def ready(self):
        from django.db.models.signals import pre_save

        from accounts.models import Company
        from complaints.models import Complaint
        from masters.models import Customer, Product, Supplier
        from purchases.models import PurchaseInvoice
        from sales.models import SalesInvoice

        from .crypto import seal_bank_account
        from .sanitize import strip_plain_text

        def _seal_company(sender, instance, **kwargs):
            instance.bank_account = seal_bank_account(instance.bank_account)

        def _seal_party_bank(sender, instance, **kwargs):
            instance.party_bank_account = seal_bank_account(getattr(instance, "party_bank_account", "") or "")

        pre_save.connect(_seal_company, sender=Company, dispatch_uid="planwave.seal_bank_account")
        pre_save.connect(_seal_party_bank, sender=Customer, dispatch_uid="planwave.seal_party_bank")
        for model in (Customer, Supplier, Product, SalesInvoice, PurchaseInvoice, Complaint):
            pre_save.connect(strip_plain_text, sender=model, dispatch_uid=f"planwave.strip.{model.__name__}")

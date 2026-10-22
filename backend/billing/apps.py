from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "SaaS Billing"

    def ready(self):
        from . import onboarding

        onboarding.connect()  # WP-GR2: checklist steps stamped from the real actions

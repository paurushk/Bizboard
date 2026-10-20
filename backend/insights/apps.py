from django.apps import AppConfig


class InsightsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "insights"
    verbose_name = "Business Insights"

    def ready(self):
        from insights import signals

        signals.connect()

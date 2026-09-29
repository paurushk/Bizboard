import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sales"

    def ready(self):
        from . import handlers  # noqa: F401
        try:
            from .pdf.styles import build_styles

            # Pre-warm ReportLab fonts and style dictionaries at boot time
            build_styles()
        except Exception:
            # Best-effort warmup -- a real font/PDF setup problem here would
            # otherwise only surface later as an unexplained PDF-generation
            # failure, with nothing pointing back at startup.
            logger.exception("sales.apps: build_styles() pre-warm failed")

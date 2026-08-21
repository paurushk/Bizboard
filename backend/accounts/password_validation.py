"""BB-000497: reject common breached passwords beyond Django's built-in list.

Full HaveIBeenPwned k-anonymity checks are an ops concern (network + rate limits);
this validator uses a local snippet of high-frequency passwords.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

# Top breached/common passwords not always caught by CommonPasswordValidator alone.
_EXTRA_COMMON = frozenset({
    "password", "password1", "password123", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "abc123", "111111", "123123", "admin", "admin123",
    "letmein", "welcome", "welcome1", "monkey", "dragon", "master", "login",
    "princess", "football", "shadow", "sunshine", "iloveyou", "trustno1",
    "baseball", "superman", "batman", "passw0rd", "p@ssw0rd", "changeme",
    "bizboard", "company123", "invoice123", "gst12345", "india123",
})


class BreachedPasswordValidator:
    """Reject passwords matching a local top-breached snippet."""

    def validate(self, password, user=None):
        normalized = (password or "").strip().lower()
        if normalized in _EXTRA_COMMON:
            raise ValidationError(
                _("This password is too common and has appeared in data breaches."),
                code="password_breached",
            )

    def get_help_text(self):
        return _("Your password cannot be a commonly breached password.")

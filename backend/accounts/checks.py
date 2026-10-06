"""Deployment checks for MFA key material. Not imported from settings.py."""

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import OperationalError, ProgrammingError


@register(Tags.security, deploy=True)
def mfa_encryption_key_ready(app_configs, **kwargs):
    if not getattr(settings, "MFA_ENFORCE_FOR_MONEY_ROLES", False):
        return []
    raw = (getattr(settings, "MFA_ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        return [
            Error(
                "MFA_ENFORCE_FOR_MONEY_ROLES is on and MFA_ENCRYPTION_KEY is empty. "
                "Set a Fernet key before the first enrolled user. "
                "Do not derive it only from SECRET_KEY in production.",
                id="accounts.E001",
            )
        ]
    first = raw.split(",")[0].strip()
    try:
        from cryptography.fernet import Fernet, InvalidToken

        from accounts.models import UserMfa

        row = UserMfa.objects.exclude(secret_enc="").order_by("pk").first()
    except (OperationalError, ProgrammingError):
        return []
    if row is None:
        return []
    try:
        Fernet(first.encode("ascii")).decrypt(row.secret_enc.encode("ascii"))
    except (InvalidToken, ValueError):
        return [
            Error(
                "The first MFA_ENCRYPTION_KEY cannot decrypt an existing UserMfa secret. "
                "Keep the previous key in the comma list (newest first) or run "
                "manage.py reencrypt_mfa_secrets before dropping it.",
                id="accounts.E002",
            )
        ]
    return []

"""Rewrite UserMfa secrets so the first MFA_ENCRYPTION_KEY can decrypt them.

The derived key (what an empty MFA_ENCRYPTION_KEY uses) is:

    urlsafe_b64encode(sha256("bizboard-mfa|" + SECRET_KEY))

Set MFA_ENCRYPTION_KEY to ``<new Fernet key>,<that derived key>`` and run this
command. It decrypts with the full list and writes with the first key. It
refuses to change anything when any row cannot be decrypted, which is what
happens if the old key was dropped first.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts import mfa
from accounts.models import UserMfa


class Command(BaseCommand):
    help = (
        "Re-encrypt every UserMfa secret with the first MFA_ENCRYPTION_KEY. "
        "Refuses to run when a row cannot be decrypted by the configured key list."
    )

    def handle(self, *args, **options):
        raw = (getattr(settings, "MFA_ENCRYPTION_KEY", "") or "").strip()
        keys = [part.strip() for part in raw.split(",") if part.strip()]
        if not keys:
            raise CommandError(
                "MFA_ENCRYPTION_KEY is empty. Set it to <new key>,<derived SECRET_KEY key> "
                "before running this command. Derived key: "
                'urlsafe_b64encode(sha256("bizboard-mfa|" + SECRET_KEY)).'
            )
        try:
            first = Fernet(keys[0].encode("ascii"))
        except ValueError as exc:
            raise CommandError("The first MFA_ENCRYPTION_KEY is not a Fernet key.") from exc
        multi = mfa._fernet()
        rows = list(UserMfa.objects.all())
        plains = []
        for row in rows:
            try:
                plains.append(multi.decrypt(row.secret_enc.encode("ascii")))
            except InvalidToken as exc:
                raise CommandError(
                    f"UserMfa id={row.pk} cannot be decrypted with the configured keys. "
                    "Put the old key back in the comma list (newest first) and run again."
                ) from exc
        with transaction.atomic():
            for row, plain in zip(rows, plains, strict=True):
                row.secret_enc = first.encrypt(plain).decode("ascii")
                row.save(update_fields=["secret_enc", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {len(rows)} MFA secret(s)."))

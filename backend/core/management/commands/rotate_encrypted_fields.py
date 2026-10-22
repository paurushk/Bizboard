"""WP-B3: re-encrypt every stored secret with the newest key, so an old key can be retired.

Key families (each lists its keys newest first; the first one encrypts):

- ``MFA_ENCRYPTION_KEY``   — Fernet list (TOTP secrets)
- ``GSP_FERNET_KEY``       — Fernet list (GSP, gateway, integration and FIU credentials)
- ``PLANWAVE_DATA_KEY`` + ``PLANWAVE_DATA_KEY_ID`` / ``PLANWAVE_RETIRED_KEYS`` — AES-GCM blobs
  ``gcm1.<key id>.<blob>`` (bank account numbers, portal secrets)

The command scans every text column of every model for values that look encrypted (a Fernet
token, or a ``gcm1.`` blob), opens each with whichever family can, and re-encrypts it with that
family's current key. Values already on the current key are left alone. It never prints a secret.

    python manage.py rotate_encrypted_fields            # dry run: counts per field
    python manage.py rotate_encrypted_fields --apply    # re-encrypt

Order for a rotation: put the new key first in the list (keep the old one after it), deploy,
run ``--apply``, check the dry run reports 0 to rotate, then remove the old key and deploy.
Tenant backup files are not rewritten: keep the old export key in the list until backups made
with it have aged out (docs/ops/SECRET_ROTATION.md).
"""

from __future__ import annotations

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

FERNET_PREFIX = "gAAAAA"
GCM_PREFIX = "gcm1."


def _fernet_families():
    from accounts import mfa
    from core.services import gsp_secrets

    return (("MFA_ENCRYPTION_KEY", mfa._fernet()), ("GSP_FERNET_KEY", gsp_secrets._fernet()))


def rotate_value(value: str) -> tuple[str | None, str | None]:
    """(new value or None if unchanged, family name or None if no family opens it)."""
    from cryptography.fernet import InvalidToken

    from planwave import crypto

    if value.startswith(GCM_PREFIX):
        try:
            _prefix, key_id, _blob = value.split(".", 2)
        except ValueError:
            return None, None
        try:
            plain = crypto.open_secret(value)
        except crypto.SealError:
            return None, None
        if key_id == crypto.current_key_id():
            return None, "PLANWAVE_DATA_KEY"
        return crypto.seal(plain), "PLANWAVE_DATA_KEY"
    if value.startswith(FERNET_PREFIX):
        for name, fernet in _fernet_families():
            try:
                fernet.decrypt(value.encode("ascii"))
            except (InvalidToken, ValueError):
                continue
            rotated = fernet.rotate(value.encode("ascii")).decode("ascii")
            # MultiFernet.rotate re-encrypts even on the current key (new IV); only report a
            # change when the token was not already readable by the first key alone.
            first = fernet._fernets[0]
            try:
                first.decrypt(value.encode("ascii"))
                return None, name
            except InvalidToken:
                return rotated, name
    return None, None


def _text_fields(model):
    return [
        f for f in model._meta.concrete_fields
        if isinstance(f, (models.CharField, models.TextField)) and not f.choices
    ]


class Command(BaseCommand):
    help = "Re-encrypt stored secrets with the newest key of each key family (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the re-encrypted values.")

    def handle(self, *args, **opts):
        from django.db.models import Q

        from core.rls import rls_bypass

        apply = opts["apply"]
        totals: dict[str, int] = {}
        unreadable = 0
        with rls_bypass():
            for model in apps.get_models():
                if model._meta.proxy or not model._meta.managed:
                    continue
                fields = _text_fields(model)
                if not fields:
                    continue
                manager = getattr(model, "all_objects", model._default_manager)
                for field in fields:
                    name = field.attname
                    cond = Q(**{f"{name}__startswith": FERNET_PREFIX}) | Q(**{f"{name}__startswith": GCM_PREFIX})
                    try:
                        rows = list(manager.filter(cond).values_list("pk", name))
                    except Exception:  # noqa: BLE001 - a table missing in this database
                        continue
                    for pk, value in rows:
                        new, family = rotate_value(value or "")
                        if family is None:
                            unreadable += 1
                            continue
                        if new is None:
                            continue
                        label = f"{model._meta.label}.{name} ({family})"
                        totals[label] = totals.get(label, 0) + 1
                        if apply:
                            manager.filter(pk=pk).update(**{name: new})
        verb = "Re-encrypted" if apply else "Would re-encrypt"
        for label, n in sorted(totals.items()):
            self.stdout.write(f"{verb} {n} value(s) in {label}")
        self.stdout.write(f"{verb} {sum(totals.values())} value(s) in total.")
        if unreadable:
            self.stdout.write(
                f"{unreadable} encrypted-looking value(s) open with no configured key; left unchanged. "
                "Check that every old key is still listed."
            )

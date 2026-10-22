"""WP-B3: every data-at-rest key can be rotated without losing what it protects."""

from io import StringIO

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.test import override_settings

pytestmark = pytest.mark.django_db

OLD = Fernet.generate_key().decode()
NEW = Fernet.generate_key().decode()


def test_gsp_credentials_survive_a_key_rotation():
    from core.services import gsp_secrets

    with override_settings(GSP_FERNET_KEY=OLD):
        token = gsp_secrets.encrypt_gsp_credentials({"api_key": "s3cret"})
    with override_settings(GSP_FERNET_KEY=f"{NEW},{OLD}"):
        assert gsp_secrets.decrypt_gsp_credentials(token) == {"api_key": "s3cret"}
    with override_settings(GSP_FERNET_KEY=NEW):
        assert gsp_secrets.decrypt_gsp_credentials(token) == {}  # old key gone: fails closed


def test_planwave_blobs_open_with_a_retired_key_and_reseal_on_the_new_one():
    import base64
    import os

    from planwave import crypto

    old = base64.urlsafe_b64encode(os.urandom(32)).decode()
    new = base64.urlsafe_b64encode(os.urandom(32)).decode()
    with override_settings(PLANWAVE_DATA_KEY=old, PLANWAVE_DATA_KEY_ID="k1", PLANWAVE_RETIRED_KEYS=""):
        blob = crypto.seal("123456789012")
    assert blob.startswith("gcm1.k1.")
    with override_settings(PLANWAVE_DATA_KEY=new, PLANWAVE_DATA_KEY_ID="k2", PLANWAVE_RETIRED_KEYS=f"k1:{old}"):
        assert crypto.open_secret(blob) == "123456789012"
        from core.management.commands.rotate_encrypted_fields import rotate_value

        rotated, family = rotate_value(blob)
        assert family == "PLANWAVE_DATA_KEY" and rotated.startswith("gcm1.k2.")
        assert crypto.open_secret(rotated) == "123456789012"
        assert rotate_value(rotated) == (None, "PLANWAVE_DATA_KEY")  # already current


def test_tenant_backups_made_with_an_old_key_still_open():
    from accounts.tenant_backup import tenant_export_fernet

    with override_settings(TENANT_EXPORT_FERNET_KEY=OLD):
        blob = tenant_export_fernet(company_id=7).encrypt(b"zip-bytes")
    with override_settings(TENANT_EXPORT_FERNET_KEY=f"{NEW},{OLD}"):
        assert tenant_export_fernet(company_id=7).decrypt(blob) == b"zip-bytes"


def test_the_command_rewrites_stored_mfa_secrets_and_is_quiet_once_done(tenant_a):
    from accounts import mfa
    from accounts.models import UserMfa

    with override_settings(MFA_ENCRYPTION_KEY=OLD):
        UserMfa.objects.create(user=tenant_a.owner, secret_enc=mfa.encrypt_secret("JBSWY3DPEHPK3PXP"))
    with override_settings(MFA_ENCRYPTION_KEY=f"{NEW},{OLD}"):
        out = StringIO()
        call_command("rotate_encrypted_fields", stdout=out)
        assert "Would re-encrypt 1 value(s) in accounts.UserMfa.secret_enc (MFA_ENCRYPTION_KEY)" in out.getvalue()
        call_command("rotate_encrypted_fields", "--apply", stdout=StringIO())
        out = StringIO()
        call_command("rotate_encrypted_fields", stdout=out)
        assert "Would re-encrypt 0 value(s) in total." in out.getvalue()
    with override_settings(MFA_ENCRYPTION_KEY=NEW):
        assert mfa.decrypt_secret(UserMfa.objects.get(user=tenant_a.owner).secret_enc) == "JBSWY3DPEHPK3PXP"

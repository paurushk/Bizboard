"""Postgres: make core_auditevent append-only at the database (F-SEC-03).

Allowed without the maintenance flag (``app.audit_maintenance = 'on'``, set only by
``core.audit_guard.audit_maintenance``):

* INSERT                                       - always
* UPDATE that only nulls ``user_id``           - user deletion (FK SET_NULL)
* UPDATE that only fills the chain columns of a row that has not been sealed yet

Everything else (any DELETE, any change to the recorded facts, re-sealing a sealed
row) raises. SQLite (dev/test) has no equivalent; the model/QuerySet guard covers it.
"""

from django.db import migrations

_FUNC = r"""
CREATE OR REPLACE FUNCTION core_auditevent_guard() RETURNS trigger AS $$
BEGIN
    IF current_setting('app.audit_maintenance', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'core_auditevent is append-only: DELETE blocked' USING ERRCODE = '42501';
    END IF;

    -- UPDATE: the recorded facts may never change.
    IF  NEW.id          IS NOT DISTINCT FROM OLD.id
    AND NEW.company_id  IS NOT DISTINCT FROM OLD.company_id
    AND NEW.action      IS NOT DISTINCT FROM OLD.action
    AND NEW.entity_type IS NOT DISTINCT FROM OLD.entity_type
    AND NEW.entity_id   IS NOT DISTINCT FROM OLD.entity_id
    AND NEW.description IS NOT DISTINCT FROM OLD.description
    AND NEW.metadata    IS NOT DISTINCT FROM OLD.metadata
    AND NEW.created_at  IS NOT DISTINCT FROM OLD.created_at THEN

        -- (a) user erased: user_id -> NULL, chain columns untouched.
        IF  NEW.user_id IS NULL
        AND NEW.chain_seq  IS NOT DISTINCT FROM OLD.chain_seq
        AND NEW.chain_prev IS NOT DISTINCT FROM OLD.chain_prev
        AND NEW.chain_hash IS NOT DISTINCT FROM OLD.chain_hash
        AND NEW.sealed_at  IS NOT DISTINCT FROM OLD.sealed_at THEN
            RETURN NEW;
        END IF;

        -- (b) sealing: only an unsealed row, only the chain columns.
        IF  OLD.sealed_at IS NULL
        AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id THEN
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION 'core_auditevent is append-only: UPDATE blocked' USING ERRCODE = '42501';
END;
$$ LANGUAGE plpgsql;
"""

_TRIGGER = """
CREATE TRIGGER core_auditevent_append_only
BEFORE UPDATE OR DELETE ON core_auditevent
FOR EACH ROW EXECUTE FUNCTION core_auditevent_guard();
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FUNC)
    schema_editor.execute("DROP TRIGGER IF EXISTS core_auditevent_append_only ON core_auditevent")
    schema_editor.execute(_TRIGGER)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS core_auditevent_append_only ON core_auditevent")
    schema_editor.execute("DROP FUNCTION IF EXISTS core_auditevent_guard()")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0043_auditevent_hash_chain"),
    ]

    operations = [migrations.RunPython(_apply, _revert)]

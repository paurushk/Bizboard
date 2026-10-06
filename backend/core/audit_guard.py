"""Append-only protection for ``core.AuditEvent`` (F-SEC-03).

Three layers, weakest to strongest:

1. **Model / QuerySet guard** (this module + ``core.models``): ``save()`` on an
   existing row, ``delete()``, ``QuerySet.update/delete/bulk_update`` raise
   ``AuditImmutableError`` unless the caller is inside ``audit_maintenance()``.
   Stops accidental and casual mutation in application code.
2. **Postgres trigger** (``core/migrations/0044_auditevent_append_only_trigger``):
   rejects UPDATE/DELETE at the database even if application code is bypassed,
   unless ``app.audit_maintenance`` is ``on`` for the transaction. Two narrow
   UPDATEs are always allowed: nulling ``user_id`` (user deletion, SET_NULL) and
   filling the chain columns of a not-yet-sealed row.
3. **Hash chain** (``core.services.audit_chain``): sealed rows are chained, so a
   change or a deletion of sealed history is detectable by ``verify_audit_chain``
   even by someone who holds the maintenance flag or direct DB access.

This is tamper-*evidence*, not tamper-proofing: an attacker with DB superuser and
the ability to rewrite the whole chain is out of scope. Pair with a DB role that
has no UPDATE/DELETE on the table (ops) and an offsite copy of the latest hash.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager

from django.db import connection, transaction


class AuditImmutableError(Exception):
    """Raised when code tries to change or delete an existing audit event."""


_maintenance: contextvars.ContextVar[bool] = contextvars.ContextVar("bizboard_audit_maintenance", default=False)


def maintenance_active() -> bool:
    return bool(_maintenance.get())


def guard(operation: str) -> None:
    if not maintenance_active():
        raise AuditImmutableError(
            f"AuditEvent is append-only: {operation} is not allowed outside audit_maintenance()."
        )


def _get_db_flag() -> str:
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.audit_maintenance', true)")
        return cur.fetchone()[0] or "off"


def _set_db_flag(value: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.audit_maintenance', %s, true)", [value])


@contextmanager
def audit_maintenance(reason: str):
    """Explicitly allow audit mutation for a documented, narrow purpose.

    ``reason`` is required so every call site states why (tenant erasure, sandbox
    teardown, chain sealing, ...). The Postgres flag is transaction-local and is
    put back to its previous value on exit (so blocks nest) even if the surrounding
    transaction continues.
    """
    if not reason:
        raise ValueError("audit_maintenance requires a reason")
    token = _maintenance.set(True)
    pg = connection.vendor == "postgresql"
    try:
        if pg:
            with transaction.atomic():
                # Restore what was there, not "off": a nested block must not switch the flag off
                # underneath the outer block that is still running.
                previous = _get_db_flag()
                _set_db_flag("on")
                try:
                    yield
                finally:
                    _set_db_flag(previous)
        else:
            yield
    finally:
        _maintenance.reset(token)

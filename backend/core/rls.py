"""Postgres RLS GUC helpers (Wave 16/19 / SYS-01). No-op unless POSTGRES_RLS_ENABLED + Postgres."""

from __future__ import annotations

import contextlib
import logging

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


def iter_company_ids():
    """Company is not FORCE-RLS; beat tasks use this then SET GUC per tenant."""
    from accounts.models import Company

    return Company.objects.values_list("id", flat=True)


def set_rls_company(company_id) -> None:
    """SET SESSION app.company_id for the current DB connection.

    Uses is_local=false so the GUC survives Django autocommit (BB-000551).
    Safe on SQLite / when RLS is off. Fail-closed when Postgres set_config fails.
    """
    if not getattr(settings, "POSTGRES_RLS_ENABLED", False):
        return
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.company_id', %s, false)",
                [str(company_id) if company_id is not None else ""],
            )
    except Exception:
        logger.exception("Failed to set RLS company GUC for company_id=%s", company_id)
        raise


def set_help_staff_all(enabled: bool) -> None:
    """SET SESSION app.help_staff_all so staff `?all=1` health can read every tenant.

    Help tables FORCE RLS with company_id = app.company_id. Without this GUC,
    staff aggregates silently return only the caller's company. Always clear
    (enabled=False) at the end of the request — pooled connections reuse GUCs.
    """
    if not getattr(settings, "POSTGRES_RLS_ENABLED", False):
        return
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.help_staff_all', %s, false)",
                ["1" if enabled else ""],
            )
    except Exception:
        logger.exception("Failed to set RLS help_staff_all GUC enabled=%s", enabled)
        raise


def set_rls_bypass(enabled: bool) -> None:
    """SET SESSION app.rls_bypass — the escape hatch for cross-tenant background
    work (beat tasks that iterate every company). The isolation policy on every
    tenant table ORs in `current_setting('app.rls_bypass', true) = '1'`.

    ALWAYS clear it (enabled=False) when the job finishes — a pooled connection
    that keeps this GUC would leak every tenant's rows to the next request. Use
    the ``rls_bypass()`` context manager rather than calling this directly.
    """
    if not getattr(settings, "POSTGRES_RLS_ENABLED", False):
        return
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.rls_bypass', %s, false)",
                ["1" if enabled else ""],
            )
    except Exception:
        logger.exception("Failed to set RLS rls_bypass GUC enabled=%s", enabled)
        raise


@contextlib.contextmanager
def rls_bypass():
    """Run a block with RLS disabled for the current connection (cross-tenant jobs).

    No-op unless POSTGRES_RLS_ENABLED + Postgres. Fail-closed: the GUC is cleared
    in ``finally`` even if the body raises.
    """
    set_rls_bypass(True)
    try:
        yield
    finally:
        try:
            set_rls_bypass(False)
        except Exception:
            logger.exception("Failed to clear RLS bypass GUC")
            raise


def clear_all_rls_gucs() -> None:
    """Reset every RLS session GUC — called by middleware at the end of a request
    so a pooled connection never carries one tenant's context into the next.
    """
    set_rls_company(None)
    set_help_staff_all(False)
    set_rls_bypass(False)

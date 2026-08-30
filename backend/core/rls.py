"""Postgres RLS GUC helpers (Wave 16/19). No-op unless POSTGRES_RLS_ENABLED + Postgres."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


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

"""Structured log line for flagged subsystems (Phase A pilot watch)."""

from __future__ import annotations

import logging

from core.services.feature_flags import flag_enabled

logger = logging.getLogger("bizboard.flags")


def log_flag_event(company, flag: str, event: str, **fields) -> None:
    """One line: tenant, flag name, whether it is on, and the core action."""
    if company is None:
        return
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info(
        "flag_event tenant_id=%s flag=%s flag_state=%s event=%s%s",
        getattr(company, "id", None),
        flag,
        "on" if flag_enabled(company, flag) else "off",
        event,
        f" {detail}" if detail else "",
        extra={
            "tenant_id": getattr(company, "id", None),
            "flag": flag,
            "flag_state": bool(flag_enabled(company, flag)),
            "event": event,
            **fields,
        },
    )

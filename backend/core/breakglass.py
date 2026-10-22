"""WP-SC2: interactive production access goes through a named, justified, logged session.

``manage.py shell`` / ``shell_plus`` / ``dbshell`` (and any command in ``BREAKGLASS_COMMANDS``)
refuse to start when ``DJANGO_ENV=production`` unless ``BREAKGLASS_SESSION_ID`` names a live
session opened with::

    python manage.py breakglass_session open --staff you@bizboard --reason "..." --ticket 123

Opening one writes ``core.BreakGlassSession`` (staff, reason, ticket, start) and posts to the ops
channel; it lasts ``BREAKGLASS_SESSION_HOURS`` (2). The quarterly access review
(``docs/ops/ACCESS_REVIEW.md``) reads these rows.

App code can't stop someone with container access from running ``python -c``. The other half is
people and hosting: no direct ``docker exec`` into production outside a session, one named DB role
per staff member, statement logging on those roles (``docs/ops/POSTGRES.md``).
"""

from __future__ import annotations

import os
import sys

DEFAULT_COMMANDS = ("shell", "shell_plus", "dbshell")


def guarded_commands() -> set[str]:
    extra = os.environ.get("BREAKGLASS_COMMANDS", "")
    return set(DEFAULT_COMMANDS) | {c.strip() for c in extra.split(",") if c.strip()}


def needs_session(argv: list[str]) -> bool:
    env = (os.environ.get("DJANGO_ENV") or "").strip().lower()
    return env == "production" and len(argv) > 1 and argv[1] in guarded_commands()


def live_session(session_id: str):
    """The open, unexpired session with this id, or None."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from core.models import BreakGlassSession

    if not session_id:
        return None
    hours = int(getattr(settings, "BREAKGLASS_SESSION_HOURS", 2) or 2)
    return (
        BreakGlassSession.objects.filter(
            public_id=session_id, ended_at__isnull=True, started_at__gte=timezone.now() - timedelta(hours=hours),
        ).first()
    )


def enforce(argv: list[str]) -> None:
    """Called by manage.py before the command runs. Exits with code 2 when access isn't allowed."""
    if not needs_session(argv):
        return
    import django

    django.setup()
    session = live_session(os.environ.get("BREAKGLASS_SESSION_ID", "").strip())
    if session is None:
        sys.stderr.write(
            f"'{argv[1]}' on production needs a break-glass session. Open one with\n"
            "  python manage.py breakglass_session open --staff <you> --reason <why> --ticket <id>\n"
            "then set BREAKGLASS_SESSION_ID to the id it prints.\n"
        )
        raise SystemExit(2)
    from core.models import BreakGlassSession

    BreakGlassSession.objects.filter(pk=session.pk).update(commands=[*session.commands, " ".join(argv[1:])[:200]])

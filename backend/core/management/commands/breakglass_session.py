"""WP-SC2: open or close a break-glass session for interactive production access."""

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Open (or end) a named, justified break-glass session for shell/dbshell on production."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["open", "end", "list"])
        parser.add_argument("--staff", help="Your staff email (required to open).")
        parser.add_argument("--reason", help="Why you need production access (required to open).")
        parser.add_argument("--ticket", help="Support ticket or incident id (required to open).")
        parser.add_argument("--id", dest="session_id", help="Session id to end.")

    def handle(self, *args, **opts):
        from core.models import BreakGlassSession

        if opts["action"] == "list":
            for row in BreakGlassSession.objects.order_by("-started_at")[:20]:
                state = "open" if row.ended_at is None else f"ended {row.ended_at:%Y-%m-%d %H:%M}"
                self.stdout.write(f"{row.public_id} {row.staff_email} {row.started_at:%Y-%m-%d %H:%M} {state} — {row.reason}")
            return
        if opts["action"] == "end":
            done = BreakGlassSession.objects.filter(public_id=opts["session_id"], ended_at__isnull=True).update(
                ended_at=timezone.now()
            )
            if not done:
                raise CommandError("No open session with that id.")
            self.stdout.write("Session ended.")
            return
        staff = (opts.get("staff") or "").strip()
        reason = (opts.get("reason") or "").strip()
        ticket = (opts.get("ticket") or "").strip()
        if not staff or len(reason) < 10 or not ticket:
            raise CommandError("--staff, --ticket and a --reason of at least 10 characters are required.")
        row = BreakGlassSession.objects.create(
            public_id=uuid.uuid4().hex, staff_email=staff[:254], reason=reason[:500], ticket=ticket[:64],
        )
        try:
            from core.services.telegram import send_ops_alert

            send_ops_alert(f"Break-glass session opened by {staff} (ticket {ticket}): {reason}")
        except Exception:  # noqa: BLE001 - the row is the record; the ping is best-effort
            pass
        self.stdout.write(f"BREAKGLASS_SESSION_ID={row.public_id}")
        self.stdout.write("Set it in your shell, run the command, then: manage.py breakglass_session end --id <id>")

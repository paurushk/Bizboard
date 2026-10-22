"""WP-AB1: SMS guard status and runtime kill switch. Runbook: docs/ops/ALERTS.md#sms-spend."""

import logging

from django.core.management.base import BaseCommand, CommandError

from core.services import sms_guard

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Show SMS guard status, or turn the runtime SMS kill switch on/off."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["status", "kill"])
        parser.add_argument("state", nargs="?", choices=["on", "off"])

    def handle(self, *args, **options):
        if options["action"] == "kill":
            if not options["state"]:
                raise CommandError("Say 'kill on' or 'kill off'.")
            on = options["state"] == "on"
            sms_guard.set_kill_switch(on)
            logger.warning("SMS runtime kill switch turned %s from the command line.", options["state"])
        s = sms_guard.status()
        self.stdout.write(
            f"kill_switch={'on' if s['kill_switch'] else 'off'} "
            f"platform_today={s['platform_today']} platform_cap={s['platform_cap'] or 'none'}"
        )

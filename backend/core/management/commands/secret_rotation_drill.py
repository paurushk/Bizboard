"""10.4 — print rotation order; --check-env fails on missing secrets. Never mutates."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.secret_rotation import ROTATION_ORDER, check_required_secrets


class Command(BaseCommand):
    help = "Secret-rotation drill: print order and optionally check env (does not rotate)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-env",
            action="store_true",
            help="Fail if a listed secret is empty or a placeholder.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Rotation order (Human performs the live cut):")
        for i, name in enumerate(ROTATION_ORDER, 1):
            self.stdout.write(f"  {i}. {name}")
        if not options["check_env"]:
            self.stdout.write("Dry-run only. Re-run with --check-env after filling secrets.")
            return
        missing = check_required_secrets()
        if missing:
            raise CommandError("Missing or placeholder: " + ", ".join(missing))
        self.stdout.write(self.style.SUCCESS("All listed secrets are present."))

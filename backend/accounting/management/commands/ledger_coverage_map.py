"""WP-F1: print or write docs/accounting/LEDGER_COVERAGE_MAP.md from accounting/coverage.py."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

TARGET = Path(settings.BASE_DIR).parent / "docs" / "accounting" / "LEDGER_COVERAGE_MAP.md"


class Command(BaseCommand):
    help = "Render the ledger coverage map (every posting source, its accounts, checks and flag)."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help=f"Write {TARGET.name} instead of printing.")

    def handle(self, *args, **opts):
        from accounting.coverage import render_markdown

        text = render_markdown()
        if opts["write"]:
            TARGET.parent.mkdir(parents=True, exist_ok=True)
            TARGET.write_text(text, encoding="utf-8", newline="\n")
            self.stdout.write(f"wrote {TARGET}")
        else:
            self.stdout.write(text)

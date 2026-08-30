"""Emit web/src/pages/help/helpCodes.json from help_codes.py (HR-8.3)."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.help_codes import ALL_HELP_CODES, ERROR_CODE_TO_INTENT, ERROR_CODE_TO_LEAF


class Command(BaseCommand):
    help = "Write helpCodes.json for the frontend CI check."

    def handle(self, *args, **options):
        payload = {
            "codes": list(ALL_HELP_CODES),
            "errorCodeToIntent": ERROR_CODE_TO_INTENT,
            "errorCodeToLeaf": ERROR_CODE_TO_LEAF,
        }
        dest = Path(settings.BASE_DIR).parent / "web" / "src" / "pages" / "help" / "helpCodes.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {dest}"))

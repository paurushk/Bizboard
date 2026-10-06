"""Write the sealed audit tip. A same-host copy is a weak control until it is stored elsewhere.

Someone who can delete audit rows on this host can rewrite this file too. Offsite
copy is out of scope (F-REL-01). The file is still worth producing so a later job
has something to copy.
"""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services import audit_chain


class Command(BaseCommand):
    help = (
        "Write the sealed audit tip to a JSON file. Refuses to write when verify() is not ok. "
        "The file on this host is a weak control until it is copied offsite (F-REL-01)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Destination path. Mode 0600 on POSIX.")

    def handle(self, *args, **options):
        res = audit_chain.verify(all_companies=True)
        if not res.ok:
            raise CommandError(
                f"Refusing to export a tip: verify reported {len(res.problems)} problem(s)."
            )
        payload = audit_chain.export_tip_payload()
        path = Path(options["out"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if os.name == "posix":
            os.chmod(path, 0o600)
        self.stdout.write(self.style.SUCCESS(f"Wrote {path} ({len(payload['companies'])} company chain(s))."))

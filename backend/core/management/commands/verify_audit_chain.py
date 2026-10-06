"""Verify the audit hash chain (F-SEC-03). Exits 1 if any sealed event was altered or removed.

``--tip`` also compares an exported tip file. That file is a weak control while it
lives on the same host as the database: anyone who can delete rows can rewrite it.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services import audit_chain


class Command(BaseCommand):
    help = (
        "Recompute the audit hash chain and report tampering. Exit status 1 on any problem. "
        "--tip compares an exported tip. A same-host tip file is a weak control until copied offsite."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, default=None, help="Verify a single company id.")
        parser.add_argument("--tip", default=None, help="JSON tip from export_audit_tip.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail when the database has a sealed company that the tip file does not list.",
        )

    def handle(self, *args, **options):
        cid = options["company"]
        res = audit_chain.verify(cid, all_companies=cid is None or options["tip"])
        problems = list(res.problems)
        if options["tip"]:
            payload = json.loads(Path(options["tip"]).read_text(encoding="utf-8"))
            failures, warnings = audit_chain.compare_tip(payload, strict=options["strict"])
            problems.extend(failures)
            for warning in warnings:
                self.stdout.write(f"WARNING {warning}")
        if not problems:
            self.stdout.write(self.style.SUCCESS(f"Audit chain OK ({res.checked} sealed event(s) checked)."))
            return
        for problem in problems[:200]:
            self.stderr.write(problem)
        raise CommandError(f"Audit chain FAILED: {len(problems)} problem(s) in {res.checked} sealed event(s).")

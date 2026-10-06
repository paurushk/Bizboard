from django.core.management.base import BaseCommand

from planwave.finish import orphan_report


class Command(BaseCommand):
    help = "List soft-deleted masters that still have live documents."

    def handle(self, *args, **options):
        rows = orphan_report()
        if not rows:
            self.stdout.write("No orphaned masters.")
            return
        for row in rows:
            self.stdout.write(f"{row['kind']} {row['id']} {row['name']}")

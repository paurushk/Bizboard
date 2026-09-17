"""Audited replay of a parked inbound webhook (9.5)."""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from billing.models import DeadLetterEvent
from billing.services import replay_dead_letter
from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Replay a pending DeadLetterEvent by primary key."

    def add_arguments(self, parser):
        parser.add_argument("pk", type=int)
        parser.add_argument("--user-id", type=int, default=None)

    def handle(self, *args, **options):
        with rls_bypass():
            event = DeadLetterEvent.objects.filter(pk=options["pk"]).first()
            if event is None:
                raise CommandError(f"DeadLetterEvent {options['pk']} not found.")
            user = None
            if options["user_id"]:
                user = User.objects.filter(pk=options["user_id"]).first()
            replayed = replay_dead_letter(event, user=user)
        self.stdout.write(self.style.SUCCESS(f"{replayed.pk} {replayed.status}"))

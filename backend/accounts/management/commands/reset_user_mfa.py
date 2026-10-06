"""Host-only break-glass for a user who lost both the phone and the recovery codes.

Not an API. There is no in-app reset that skips the second factor.
"""

from django.core.management.base import BaseCommand, CommandError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.models import User, UserMfa
from core.services.audit import AuditService


class Command(BaseCommand):
    help = "Delete one user's MFA row and blacklist their refresh tokens. Host command, not an API."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required when DJANGO_ENV is production or staging.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if settings.DJANGO_ENV in ("production", "staging") and not options["force"]:
            raise CommandError(
                "reset_user_mfa refuses to run when DJANGO_ENV is "
                f"{settings.DJANGO_ENV} unless --force is passed."
            )
        email = (options["email"] or "").strip()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No user with email {email}.")
        deleted, _ = UserMfa.objects.filter(user=user).delete()
        revoked = 0
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
            revoked += 1
        # Access tokens already issued stay valid for their lifetime unless the version moves.
        user.session_version = int(getattr(user, "session_version", 0) or 0) + 1
        user.save(update_fields=["session_version"])
        membership = user.company_memberships.filter(is_active=True).select_related("company").first()
        AuditService.log(
            company=membership.company if membership else None,
            user=user,
            action="MFA_DISABLED",
            entity_type="User",
            entity_id=user.id,
            description="reset_user_mfa host command",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared MFA for {user.email} (rows={deleted}, refresh tokens blacklisted={revoked}). "
                "The next sign-in follows enrolment when enforcement is on."
            )
        )

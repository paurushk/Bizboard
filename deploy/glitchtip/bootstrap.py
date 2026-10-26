"""Idempotent GlitchTip setup for Bizboard. Runs inside the GlitchTip image as
``./manage.py shell < /bootstrap/bootstrap.py`` (the glitchtip-init service in
docker-compose.glitchtip.yml) after every start.

Inputs are BB_* environment variables (see the compose file). Creates or
updates, never deletes: the admin user, organisation "bizboard", team "ops",
projects bizboard-api / bizboard-web with fixed public keys, the read-only ops
API token Bizboard's admin pages use, alert rules (new error, API down) and
uptime monitors on the API health endpoints. Prints the DSNs to put in the env
file and says when the env file disagrees.

Exit code 1 when a required input is missing or invalid, so a misconfigured
deploy fails loudly instead of running a tracker nobody can sign in to.
"""

import os
import re
import sys
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction

from apps.alerts.models import AlertRecipient, ProjectAlert
from apps.api_tokens.models import APIToken
from apps.organizations_ext.models import Organization, OrganizationUser, OrganizationUserRole
from apps.projects.models import Project, ProjectKey
from apps.teams.models import Team
from apps.uptime.models import Monitor, StatusPage
from apps.users.models import User

ORG_SLUG = "bizboard"
TEAM_SLUG = "ops"
PROJECTS = (("bizboard-api", "python-django", "BB_API_KEY"), ("bizboard-web", "javascript-react", "BB_WEB_KEY"))
OPS_TOKEN_LABEL = "bizboard-ops (read only)"
TOKEN_SCOPES = ("project:read", "event:read", "org:read", "team:read", "member:read")
# (name shown on the public status page and in alerts, path, former name renamed in place)
MONITORS = (
    ("Bizboard app", "/api/v1/health/", "API live"),
    ("Saving and loading data", "/api/v1/health/?ready=1", "API ready"),
)


def env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def fail(message: str) -> None:
    print(f"glitchtip-init: {message}")
    sys.exit(1)


def as_key(name: str) -> UUID | None:
    raw = env(name)
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        fail(f"{name} must be 32 hex characters (python -c \"import uuid; print(uuid.uuid4().hex)\").")


def ensure_user(email: str, *, password: str = "", superuser: bool = False) -> User:
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User(email=email, is_staff=superuser, is_superuser=superuser)
        if password:
            user.set_password(password)
        else:
            # Alert-only recipients sign in after a password reset.
            user.set_unusable_password()
        user.save()
        print(f"  created user {email}")
    return user


def ensure_member(org: Organization, team: Team, user: User, role) -> None:
    org_user = OrganizationUser.objects.filter(organization=org, user=user).first()
    if org_user is None:
        org.add_user(user, role=role)
        org_user = OrganizationUser.objects.get(organization=org, user=user)
    team.members.add(org_user)


def token_scope_bits() -> int:
    flags = list(APIToken._meta.get_field("scopes").flags)
    return sum(1 << flags.index(scope) for scope in TOKEN_SCOPES)


def ensure_alert(project: Project, name: str, *, uptime: bool, recipients) -> None:
    alert = ProjectAlert.objects.filter(project=project, name=name).first()
    if alert is None:
        alert = ProjectAlert.objects.create(
            project=project,
            name=name,
            uptime=uptime,
            timespan_minutes=None if uptime else 1,
            quantity=None if uptime else 1,
        )
        print(f"  created alert '{name}' on {project.slug}")
    for recipient_type, url in recipients:
        AlertRecipient.objects.get_or_create(alert=alert, recipient_type=recipient_type, url=url)
    # A changed or removed ntfy topic stops receiving pages; recipients added in the UI stay.
    wanted_ntfy = [url for kind, url in recipients if kind == "ntfy"]
    AlertRecipient.objects.filter(alert=alert, recipient_type="ntfy").exclude(url__in=wanted_ntfy).delete()


@transaction.atomic
def main() -> None:
    admin_email, admin_password = env("BB_ADMIN_EMAIL"), env("BB_ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        fail("set GLITCHTIP_ADMIN_EMAIL and GLITCHTIP_ADMIN_PASSWORD in the env file.")
    if len(admin_password) < 12:
        fail("GLITCHTIP_ADMIN_PASSWORD must be at least 12 characters.")
    ops_token = env("BB_OPS_TOKEN")
    if ops_token and not re.fullmatch(r"[0-9a-f]{32,64}", ops_token):
        fail("ERROR_TRACKER_TOKEN must be 32-64 lowercase hex characters "
             "(python -c \"import secrets; print(secrets.token_hex(32))\").")

    admin = ensure_user(admin_email, password=admin_password, superuser=True)

    org = Organization.objects.filter(slug=ORG_SLUG).first()
    if org is None:
        org = Organization.objects.create(name="Bizboard", slug=ORG_SLUG)
        print("  created organisation bizboard")
    team, _ = Team.objects.get_or_create(organization=org, slug=TEAM_SLUG)
    ensure_member(org, team, admin, OrganizationUserRole.OWNER)

    alert_emails = [e.strip() for e in env("BB_ALERT_EMAILS").split(",") if e.strip()]
    for email in alert_emails:
        ensure_member(org, team, ensure_user(email), OrganizationUserRole.MEMBER)

    dsn_base = env("BB_DSN_BASE_URL").rstrip("/") or "http://glitchtip:8000"
    scheme, _, host = dsn_base.partition("://")
    if scheme not in ("http", "https") or not host:
        fail("GLITCHTIP_DSN_BASE_URL must look like http://glitchtip:8000 or https://errors.<domain>.")
    dsns = {}
    projects = {}
    for slug, platform, key_var in PROJECTS:
        project = Project.objects.filter(organization=org, slug=slug).first()
        if project is None:
            project = Project.objects.create(organization=org, name=slug, slug=slug, platform=platform)
            print(f"  created project {slug}")
        project.teams.add(team)
        projects[slug] = project

        wanted = as_key(key_var)
        key = ProjectKey.objects.filter(project=project).order_by("id").first()
        if key is None:
            key = ProjectKey.objects.create(project=project, **({"public_key": wanted} if wanted else {}))
        elif wanted and key.public_key != wanted:
            key.public_key = wanted
            key.save(update_fields=["public_key"])
            print(f"  set {slug} key from the env file")
        dsns[slug] = f"{scheme}://{key.public_key.hex}@{host}/{project.id}"

    if ops_token:
        token = APIToken.objects.filter(token=ops_token).first()
        if token is None:
            APIToken.objects.create(user=admin, token=ops_token, label=OPS_TOKEN_LABEL,
                                    scopes=token_scope_bits())
            print("  created ops API token")
        elif token.user_id != admin.id:
            fail("ERROR_TRACKER_TOKEN already belongs to another GlitchTip user.")
    # A rotated ERROR_TRACKER_TOKEN must not leave the old one working.
    stale = APIToken.objects.filter(label=OPS_TOKEN_LABEL).exclude(token=ops_token)
    if stale.exists():
        stale.delete()
        print("  removed the previous ops API token")

    recipients = [("email", "")]
    if env("BB_ALERT_NTFY_URL"):
        recipients.append(("ntfy", env("BB_ALERT_NTFY_URL")))
    api_project = projects["bizboard-api"]
    ensure_alert(api_project, "Bizboard API: new error", uptime=False, recipients=recipients)
    ensure_alert(projects["bizboard-web"], "Bizboard web: new error", uptime=False, recipients=recipients)
    ensure_alert(api_project, "Bizboard API: down", uptime=True, recipients=recipients)

    monitor_base = env("BB_MONITOR_BASE_URL").rstrip("/")
    allowed = [h.strip().lower() for h in env("BB_APP_ALLOWED_HOSTS").split(",") if h.strip()]
    monitor_host = (urlsplit(monitor_base).hostname or "").lower()
    if monitor_base and allowed and not any(
        monitor_host == h or (h.startswith(".") and (monitor_host.endswith(h) or monitor_host == h[1:]))
        for h in allowed
    ):
        print(f"  WARNING: DJANGO_ALLOWED_HOSTS does not include '{monitor_host}', so the uptime "
              f"monitors will get HTTP 400 and report the API as down. Add it to DJANGO_ALLOWED_HOSTS.")
    if monitor_base:
        for name, path, former in MONITORS:
            Monitor.objects.filter(organization=org, name=former).update(name=name)
            monitor, created = Monitor.objects.get_or_create(
                organization=org,
                name=name,
                defaults={"project": api_project, "url": monitor_base + path, "monitor_type": "GET",
                          "interval": 60, "timeout": 20, "expected_status": 200, "expected_body": ""},
            )
            if not created and monitor.url != monitor_base + path:
                monitor.url = monitor_base + path
                monitor.save(update_fields=["url"])
            if created:
                print(f"  created uptime monitor '{name}' -> {monitor.url}")

    # BB-128: the public status page lists the API monitors (served at
    # /status-pages/bizboard/<slug>/; only that path needs to be public, see GLITCHTIP.md).
    status_page, created = StatusPage.objects.get_or_create(
        organization=org, name=env("BB_STATUS_PAGE_NAME") or "Bizboard", defaults={"is_public": True},
    )
    status_page.monitors.add(*Monitor.objects.filter(organization=org, name__in=[n for n, _, _ in MONITORS]))
    if created:
        print(f"  created public status page /status-pages/{ORG_SLUG}/{status_page.slug}/")

    print("glitchtip-init: ready.")
    print(f"  SENTRY_DSN={dsns['bizboard-api']}")
    print(f"  SENTRY_BROWSER_DSN={dsns['bizboard-web']}")
    print(f"  VITE_SENTRY_DSN={dsns['bizboard-web']}")
    for label, var, wanted in (("API", "BB_EXPECT_SENTRY_DSN", dsns["bizboard-api"]),
                               ("browser", "BB_EXPECT_BROWSER_DSN", dsns["bizboard-web"])):
        have = env(var)
        if not have:
            print(f"  NOTE: the {label} DSN is not set in the env file yet; use the line above.")
        elif have != wanted:
            print(f"  MISMATCH: the env file's {label} DSN differs from the project; use the line above.")
    if not ops_token:
        print("  NOTE: ERROR_TRACKER_TOKEN is empty, so Bizboard's ops error page stays off.")


main()

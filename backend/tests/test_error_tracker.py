"""Error tracker (self-hosted GlitchTip or Sentry) inside Bizboard: the read-only
client, the staff errors page, Support ID links on tickets, the tracker-down
watcher and the gate-check lines. The tracker itself is mocked; the live run is
recorded in docs/ops/GLITCHTIP.md."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest import mock

import pytest
import requests
import yaml
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings

from accounts.models import User
from core import error_tracker

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]
TRACKER = {
    "ERROR_TRACKER_API_URL": "http://glitchtip:8000",
    "ERROR_TRACKER_UI_URL": "https://errors.example.in",
    "ERROR_TRACKER_ORG": "bizboard",
    "ERROR_TRACKER_TOKEN": "a" * 64,
}
ISSUE = {
    "id": "7",
    "shortId": "BIZBOARD-API-7",
    "title": "ValueError: boom",
    "culprit": "sales.services.complete",
    "level": "error",
    "project": {"slug": "bizboard-api"},
    "count": "3",
    "firstSeen": "2026-10-23T04:00:00Z",
    "lastSeen": "2026-10-23T04:10:00Z",
    # GlitchTip 6 really returns this broken permalink (project slug in the org's place).
    "permalink": "https://errors.example.in/bizboard-api/issues/7",
}


def _resp(status=200, payload=None):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = payload
    return resp


# --- client ---------------------------------------------------------------------------------


def test_everything_is_off_without_settings(settings):
    for name in TRACKER:
        setattr(settings, name, "")
    assert error_tracker.is_configured() is False
    assert error_tracker.request_id_url("abc") is None
    assert error_tracker.fetch_issues().ok is False
    assert error_tracker.check_reachable() == (False, "not configured")


@override_settings(**TRACKER)
def test_links_use_the_ui_url_and_quote_the_query():
    assert error_tracker.request_id_url("5f0c-11") == (
        "https://errors.example.in/bizboard/issues?query=request_id%3A5f0c-11"
    )


@override_settings(**{**TRACKER, "ERROR_TRACKER_UI_URL": "https://sentry.io"})
def test_sentry_links_use_sentrys_route():
    assert error_tracker.search_url("is:unresolved") == (
        "https://sentry.io/organizations/bizboard/issues/?query=is%3Aunresolved"
    )


@pytest.mark.parametrize("value", ["", "has space", "a:b", "x" * 65, "<script>", "id OR is:resolved"])
def test_only_plain_request_ids_become_tag_searches(value):
    assert error_tracker.request_id_query(value) is None


@override_settings(**TRACKER)
def test_fetch_issues_sends_the_token_and_keeps_only_safe_fields():
    hostile = {**ISSUE, "id": "javascript:alert(1)", "shortId": "X-1", "permalink": "javascript:alert(1)"}
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, [ISSUE, hostile, "junk"])) as get:
        result = error_tracker.fetch_issues("request_id:abc", limit=500)
    assert result.ok
    assert get.call_args.args[0] == "http://glitchtip:8000/api/0/organizations/bizboard/issues/"
    assert get.call_args.kwargs["params"] == {"query": "request_id:abc", "limit": 100}
    assert get.call_args.kwargs["headers"] == {"Authorization": f"Bearer {'a' * 64}"}
    assert [i["short_id"] for i in result.issues] == ["BIZBOARD-API-7", "X-1"]
    # Built from the UI URL and the numeric id, never taken from the tracker's permalink.
    assert result.issues[0]["url"] == "https://errors.example.in/bizboard/issues/7"
    assert result.issues[1]["url"] == ""


@override_settings(**{**TRACKER, "ERROR_TRACKER_UI_URL": "https://sentry.io"})
def test_sentry_issue_links_use_sentrys_route():
    assert error_tracker.issue_url("7") == "https://sentry.io/organizations/bizboard/issues/7/"


@pytest.mark.parametrize(
    ("side_effect", "response", "error"),
    [
        (requests.ConnectTimeout("slow"), None, "unreachable (ConnectTimeout)"),
        (None, _resp(401, {"detail": "no"}), "HTTP 401"),
        (None, _resp(200, {"not": "a list"}), "unexpected response"),
    ],
)
@override_settings(**TRACKER)
def test_fetch_issues_reports_failures_without_raising(side_effect, response, error):
    with mock.patch("core.error_tracker.requests.get", side_effect=side_effect, return_value=response):
        result = error_tracker.fetch_issues()
    assert result.ok is False and result.error == error


@override_settings(**TRACKER)
def test_check_reachable_reads_the_organisation():
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, {})) as get:
        assert error_tracker.check_reachable() == (True, "ok")
    assert get.call_args.args[0] == "http://glitchtip:8000/api/0/organizations/bizboard/"
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(403)):
        assert error_tracker.check_reachable() == (False, "HTTP 403")


# --- staff errors page ----------------------------------------------------------------------


@override_settings(**TRACKER)
def test_errors_page_is_for_superusers_only(client):
    staff = User.objects.create_user(email="staff-errors@example.com", password="x-Strong-pass-1", is_staff=True)
    client.force_login(staff)
    assert client.get("/admin/ops/errors/").status_code == 403


@override_settings(**TRACKER, SENTRY_DSN="http://k@glitchtip:8000/1", SENTRY_BROWSER_DSN="")
def test_errors_page_lists_open_errors_and_wiring(client):
    root = User.objects.create_superuser(email="root-errors@example.com", password="x-Strong-pass-1")
    client.force_login(root)
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, [ISSUE])) as get:
        page = client.get("/admin/ops/errors/")
    assert page.status_code == 200
    assert get.call_args.kwargs["params"]["query"] == "is:unresolved"
    body = page.content.decode()
    assert "ValueError: boom" in body and "BIZBOARD-API-7" in body
    assert "Browser errors relayed (SENTRY_BROWSER_DSN)" in body
    assert "Open this search in the tracker" in body


@override_settings(**TRACKER)
def test_errors_page_searches_a_support_id_by_tag(client):
    root = User.objects.create_superuser(email="root-errors2@example.com", password="x-Strong-pass-1")
    client.force_login(root)
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, [])) as get:
        page = client.get("/admin/ops/errors/?q=5f0c-11")
    assert get.call_args.kwargs["params"]["query"] == "request_id:5f0c-11"
    assert "Errors for Support ID 5f0c-11" in page.content.decode()
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, [])) as get:
        client.get("/admin/ops/errors/?q=timeout on invoice")
    assert get.call_args.kwargs["params"]["query"] == "is:unresolved timeout on invoice"


def test_errors_page_explains_when_not_configured(client, settings):
    settings.ERROR_TRACKER_API_URL = ""
    root = User.objects.create_superuser(email="root-errors3@example.com", password="x-Strong-pass-1")
    client.force_login(root)
    with mock.patch("core.error_tracker.requests.get") as get:
        page = client.get("/admin/ops/errors/")
    get.assert_not_called()
    assert "Bizboard can't read the tracker yet" in page.content.decode()


@override_settings(**TRACKER)
def test_errors_page_survives_a_down_tracker(client):
    root = User.objects.create_superuser(email="root-errors4@example.com", password="x-Strong-pass-1")
    client.force_login(root)
    with mock.patch("core.error_tracker.requests.get", side_effect=requests.ConnectionError("down")):
        page = client.get("/admin/ops/errors/")
    assert page.status_code == 200
    assert "The tracker did not answer: unreachable (ConnectionError)" in page.content.decode()


# --- support tickets ------------------------------------------------------------------------


@override_settings(**TRACKER)
def test_ticket_links_its_support_id_to_matching_errors(client, tenant_a):
    from support.platform_tickets import open_ticket

    ticket = open_ticket(company=tenant_a.company, user=tenant_a.owner, subject="Invoice failed",
                         description="It showed an error", support_id="5f0c-11")
    root = User.objects.create_superuser(email="root-ticket@example.com", password="x-Strong-pass-1")
    client.force_login(root)
    with mock.patch("core.error_tracker.requests.get") as get:
        page = client.get(f"/admin/support/platformticket/{ticket.pk}/change/")
    get.assert_not_called()  # the ticket page never waits on the tracker
    body = page.content.decode()
    assert "/admin/ops/errors/?q=5f0c-11" in body
    assert "https://errors.example.in/bizboard/issues?query=request_id%3A5f0c-11" in body


def test_ticket_without_support_id_says_so():
    from support.admin import PlatformTicketAdmin
    from support.models import PlatformTicket

    admin_obj = PlatformTicketAdmin(PlatformTicket, None)
    assert admin_obj.matching_errors(PlatformTicket(support_id="")) == "No Support ID on this ticket."


# --- watcher --------------------------------------------------------------------------------


@pytest.fixture
def clean_watch_cache():
    from core.tasks import ERROR_TRACKER_DOWN_KEY, ERROR_TRACKER_FAILS_KEY

    cache.delete_many([ERROR_TRACKER_DOWN_KEY, ERROR_TRACKER_FAILS_KEY])
    yield
    cache.delete_many([ERROR_TRACKER_DOWN_KEY, ERROR_TRACKER_FAILS_KEY])


def test_watcher_is_off_without_settings(settings, clean_watch_cache):
    from core.tasks import check_error_tracker_task

    settings.ERROR_TRACKER_TOKEN = ""
    assert check_error_tracker_task() == "not configured"


@override_settings(**TRACKER)
def test_watcher_pages_once_after_two_misses_and_once_on_recovery(clean_watch_cache):
    from core.tasks import check_error_tracker_task

    with mock.patch("core.services.telegram.send_ops_alert") as page:
        with mock.patch("core.error_tracker.requests.get", side_effect=requests.ConnectionError("down")):
            assert check_error_tracker_task().startswith("down")  # one miss: a restart, not paged
            page.assert_not_called()
            assert check_error_tracker_task() == "paged"
            assert check_error_tracker_task().startswith("down")  # still down: no second page
        assert page.call_count == 1
        assert "Error tracker is not answering" in page.call_args.args[0]
        with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, {})):
            assert check_error_tracker_task() == "recovered"
            assert check_error_tracker_task() == "ok"
    assert page.call_count == 2
    assert "answering again" in page.call_args.args[0]


@override_settings(**TRACKER)
def test_one_miss_then_ok_never_pages(clean_watch_cache):
    from core.tasks import check_error_tracker_task

    with mock.patch("core.services.telegram.send_ops_alert") as page:
        with mock.patch("core.error_tracker.requests.get", side_effect=requests.ConnectionError("blip")):
            check_error_tracker_task()
        with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, {})):
            assert check_error_tracker_task() == "ok"
        with mock.patch("core.error_tracker.requests.get", side_effect=requests.ConnectionError("blip")):
            check_error_tracker_task()  # the counter was reset, so this is a first miss again
    page.assert_not_called()


def test_watcher_is_scheduled(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["core-check-error-tracker"]
    assert entry["task"] == "core.tasks.check_error_tracker_task"


# --- gate check -----------------------------------------------------------------------------


@override_settings(**TRACKER, SENTRY_BROWSER_DSN="http://k@glitchtip:8000/2")
def test_gate_check_reports_relay_and_tracker():
    out = StringIO()
    with mock.patch("core.error_tracker.requests.get", return_value=_resp(200, {})):
        call_command("observability_gate_check", stdout=out)
    text = out.getvalue()
    assert "browser_relay_configured=True" in text
    assert "error_tracker_readable=True  (ok)" in text


# --- container wiring -----------------------------------------------------------------------


def _compose(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_glitchtip_overlay_is_opt_in_pinned_and_private():
    services = _compose("docker-compose.glitchtip.yml")["services"]
    assert set(services) == {"glitchtip-db", "glitchtip", "glitchtip-init"}
    for name, svc in services.items():
        assert svc.get("profiles") == ["errors"], name
        image = svc["image"]
        assert ":" in image and not image.endswith(":latest"), name
    assert all(p.startswith("127.0.0.1:") for p in services["glitchtip"]["ports"])
    assert "./deploy/glitchtip:/bootstrap:ro" in services["glitchtip-init"]["volumes"]
    assert (ROOT / "deploy" / "glitchtip" / "bootstrap.py").is_file()
    # Never shares the app database or its volumes.
    assert "glitchtip-db:5432" in services["glitchtip"]["environment"]["DATABASE_URL"]


def test_stack_tooling_includes_the_overlay():
    assert "docker-compose.glitchtip.yml" in (ROOT / "scripts" / "compose-env.ps1").read_text(encoding="utf-8")
    deploy = (ROOT / ".github" / "workflows" / "deploy-staging.yml").read_text(encoding="utf-8")
    assert "-f docker-compose.glitchtip.yml" in deploy and "compose run --rm glitchtip-init" in deploy
    web_args = _compose("docker-compose.yml")["services"]["web"]["build"]["args"]
    assert "VITE_SENTRY_DSN" in web_args


def test_deploy_records_the_release_before_the_tracker_setup_can_fail():
    deploy = (ROOT / ".github" / "workflows" / "deploy-staging.yml").read_text(encoding="utf-8")
    assert deploy.index("> .deploy/current") < deploy.index("compose run --rm glitchtip-init")
    # Under `set -o pipefail` a piped `grep -q` can fail when it closes the pipe early.
    assert "config --services | grep" not in deploy


def test_setup_step_is_told_the_apps_allowed_hosts():
    env = _compose("docker-compose.glitchtip.yml")["services"]["glitchtip-init"]["environment"]
    assert env["BB_APP_ALLOWED_HOSTS"] == "${DJANGO_ALLOWED_HOSTS:-}"

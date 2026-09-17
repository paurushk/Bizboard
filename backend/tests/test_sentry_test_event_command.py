"""Sentry test-event command — the Go/No-Go "Sentry DSN + on-call routing
live" Final Gate is meant to be one command an operator runs after setting
SENTRY_DSN; these tests prove the command wires up correctly without
needing a real Sentry account."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command


def test_refuses_clearly_when_sentry_dsn_not_set(settings):
    settings.SENTRY_DSN = ""
    with pytest.raises(CommandError, match="SENTRY_DSN is not set"):
        call_command("sentry_test_event")


def test_sends_a_test_event_when_dsn_is_configured(settings):
    settings.SENTRY_DSN = "https://example@o0.ingest.sentry.io/0"
    out = StringIO()
    with patch("sentry_sdk.capture_message", return_value="test-event-id") as capture, \
            patch("sentry_sdk.flush") as flush:
        call_command("sentry_test_event", stdout=out)
    capture.assert_called_once()
    assert capture.call_args.kwargs.get("level") == "info"
    flush.assert_called_once()
    assert "test-event-id" in out.getvalue()
    assert "HYPERCARE.md" in out.getvalue()
    assert "OGATE_HUMAN.md" in out.getvalue()

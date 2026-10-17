"""ACS-20..24: Journals draft lifecycle, detail fields, filters, export, idempotency."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from accounting.models import Account, JournalEntry
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

J = "/api/v1/accounting/journals/"


def _acct(company, code):
    return Account.objects.get(company=company, code=code)


def _payload(books, *, amount="100.00", narration="n1", **extra):  # noqa: F811
    cash, cogs = _acct(books.company, "1100"), _acct(books.company, "5400")
    body = {
        "entry_date": timezone.localdate().isoformat(),
        "narration": narration,
        "lines": [
            {"account": cogs.id, "debit": amount, "credit": "0", "narration": "line one"},
            {"account": cash.id, "debit": "0", "credit": amount},
        ],
    }
    body.update(extra)
    return body


def _draft(books, **kw):  # noqa: F811
    resp = books.client.post(J, _payload(books, **kw), format="json")
    assert resp.status_code == 201, resp.content
    return resp.data


def test_draft_can_be_edited_and_keeps_its_number(books):  # noqa: F811
    d = _draft(books)
    body = _payload(books, amount="250.00", narration="changed", reference="REF-9")
    resp = books.client.put(f"{J}{d['id']}/", body, format="json")
    assert resp.status_code == 200, resp.content
    data = resp.data
    assert data["number"] == d["number"]
    assert data["narration"] == "changed"
    assert data["reference"] == "REF-9"
    assert sorted(l["debit"] for l in data["lines"]) == ["0.00", "250.00"]
    assert data["lines"][0]["narration"] in ("line one", "")


def test_posted_journal_cannot_be_edited_or_discarded(books):  # noqa: F811
    d = _draft(books)
    assert books.client.post(f"{J}{d['id']}/post/").status_code == 200
    resp = books.client.put(f"{J}{d['id']}/", _payload(books), format="json")
    assert resp.status_code == 400
    assert books.client.delete(f"{J}{d['id']}/").status_code == 400


def test_discard_keeps_number_and_hides_from_default_list(books):  # noqa: F811
    d = _draft(books)
    assert books.client.delete(f"{J}{d['id']}/").status_code == 204
    entry = JournalEntry.objects.get(pk=d["id"])
    assert entry.status == JournalEntry.Status.DISCARDED
    assert entry.number == d["number"]
    ids = [r["id"] for r in books.client.get(J).data["results"]]
    assert d["id"] not in ids
    shown = books.client.get(J, {"status": "DISCARDED"}).data["results"]
    assert [r["id"] for r in shown] == [d["id"]]
    assert books.client.post(f"{J}{d['id']}/post/").status_code == 400


def test_next_number_is_not_reused_after_discard(books):  # noqa: F811
    first = _draft(books)
    books.client.delete(f"{J}{first['id']}/")
    second = _draft(books)
    assert second["number"] != first["number"]


def test_client_token_makes_create_idempotent(books):  # noqa: F811
    a = books.client.post(J, _payload(books, client_token="tok-1"), format="json")
    b = books.client.post(J, _payload(books, client_token="tok-1"), format="json")
    assert a.status_code == 201 and b.status_code == 200
    assert a.data["id"] == b.data["id"]
    assert JournalEntry.objects.filter(company=books.company, client_token="tok-1").count() == 1


def test_posting_twice_reports_a_stable_code(books):  # noqa: F811
    d = _draft(books)
    assert books.client.post(f"{J}{d['id']}/post/").status_code == 200
    again = books.client.post(f"{J}{d['id']}/post/")
    assert again.status_code == 400
    assert "journal_not_draft" in again.content.decode()


def test_detail_carries_account_names_totals_and_reversal_link(books):  # noqa: F811
    d = _draft(books)
    books.client.post(f"{J}{d['id']}/post/")
    detail = books.client.get(f"{J}{d['id']}/").data
    assert detail["total_debit"] == "100.00" or float(detail["total_debit"]) == 100.0
    assert {l["account_code"] for l in detail["lines"]} == {"1100", "5400"}
    assert detail["can_edit"] is False
    rev = books.client.post(f"{J}{d['id']}/reverse/").data
    assert rev["reversal_of"] == d["id"]
    assert books.client.get(f"{J}{d['id']}/").data["reversed_entry"] == rev["id"]


def test_filters_by_status_date_number_text_and_account(books):  # noqa: F811
    old = (timezone.localdate() - timedelta(days=40)).isoformat()
    a = _draft(books, narration="rent for shop")
    b = books.client.post(J, _payload(books, narration="other", entry_date=old), format="json").data
    books.client.post(f"{J}{a['id']}/post/")
    ids = lambda **p: {r["id"] for r in books.client.get(J, p).data["results"]}  # noqa: E731
    assert ids(status="POSTED") == {a["id"]}
    assert ids(status="DRAFT") == {b["id"]}
    assert ids(date_from=(timezone.localdate() - timedelta(days=10)).isoformat()) == {a["id"]}
    assert ids(q="rent") == {a["id"]}
    assert ids(q="line one") == {a["id"], b["id"]}
    assert ids(number=a["number"]) == {a["id"]}
    assert ids(account=_acct(books.company, "5400").id) == {a["id"], b["id"]}
    assert ids(source_type="MANUAL_JOURNAL") == {a["id"]}


def test_export_csv_has_one_row_per_line_and_neutralises_formulas(books):  # noqa: F811
    _draft(books, narration="=SUM(1+1)")
    resp = books.client.get(J + "export/")
    assert resp.status_code == 200
    text = resp.content.decode()
    rows = text.strip().splitlines()
    assert len(rows) == 3
    assert "'=SUM(1+1)" in text
    xlsx = books.client.get(J + "export/", {"file": "xlsx"})
    assert xlsx.status_code == 200
    assert xlsx["Content-Type"].startswith("application/vnd.openxml")


def test_party_control_rule_still_applies_when_editing(books):  # noqa: F811
    d = _draft(books)
    ar = _acct(books.company, "1200")
    cash = _acct(books.company, "1100")
    body = {
        "entry_date": timezone.localdate().isoformat(),
        "lines": [
            {"account": ar.id, "debit": "10.00", "credit": "0"},
            {"account": cash.id, "debit": "0", "credit": "10.00"},
        ],
    }
    resp = books.client.put(f"{J}{d['id']}/", body, format="json")
    assert resp.status_code == 400

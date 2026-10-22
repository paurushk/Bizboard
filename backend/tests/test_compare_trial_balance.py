"""WP-F10: the parallel-month comparison against a Tally/Busy trial balance export."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from accounting.management.commands.compare_trial_balance import _num, compare, read_mapping, read_theirs
from tests.conftest import make_customer, make_product
from tests.test_ar_ap_agreement_matrix import _books, _sale


@pytest.mark.parametrize(("raw", "value"), [("1,180.00", "1180.00"), ("500 Cr", "-500"), ("(25)", "-25"), ("", "0"), ("₹10 Dr", "10")])
def test_amounts_parse_like_tally_prints_them(raw, value):
    assert _num(raw) == Decimal(value)


def test_debit_credit_and_balance_layouts_and_the_comparison(tmp_path):
    theirs = tmp_path / "tally.csv"
    theirs.write_text("Particulars,Debit,Credit\nCash-in-Hand,1180,\nSales Accounts,,1000\nOutput IGST,,180\nTotal,1180,1180\n", encoding="utf-8")
    mapping = tmp_path / "map.csv"
    mapping.write_text("their_ledger,account_code\nCash-in-Hand,1100\nSales Accounts,4000\n", encoding="utf-8")
    t = read_theirs(theirs)
    assert t == {"Cash-in-Hand": Decimal("1180"), "Sales Accounts": Decimal("-1000"), "Output IGST": Decimal("-180")}
    diffs, unmapped = compare(
        {"1100": Decimal("1180"), "4000": Decimal("-1000"), "2230": Decimal("-180")}, t, read_mapping(mapping), Decimal("1"),
    )
    assert unmapped == [("Output IGST", Decimal("-180"))]
    assert diffs == [("2230", Decimal("-180"), Decimal("0"), Decimal("-180"))]


@pytest.mark.django_db
def test_the_command_passes_when_the_books_agree_and_fails_when_they_do_not(tenant_a, tmp_path):
    _books(tenant_a, True)
    _sale(tenant_a, make_customer(tenant_a.company), make_product(tenant_a.company), amount="1000")
    from accounting.reports import trial_balance

    tb = trial_balance(tenant_a.company)
    lines = ["Ledger,Debit,Credit"] + [f"L{r['account_code']},{r['debit']},{r['credit']}" for r in tb["rows"]]
    (tmp_path / "theirs.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "map.csv").write_text(
        "\n".join(["their_ledger,account_code"] + [f"L{r['account_code']},{r['account_code']}" for r in tb["rows"]]) + "\n",
        encoding="utf-8",
    )
    args = ["--company", str(tenant_a.company.pk), "--as-of", timezone.localdate().isoformat(),
            "--theirs", str(tmp_path / "theirs.csv"), "--mapping", str(tmp_path / "map.csv")]
    out = StringIO()
    call_command("compare_trial_balance", *args, stdout=out)
    assert "differences=0 unmapped=0" in out.getvalue()
    first = tb["rows"][0]
    lines[1] = f"L{first['account_code']},{Decimal(first['debit']) + 50},{first['credit']}"
    (tmp_path / "theirs.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command("compare_trial_balance", *args, stdout=StringIO())

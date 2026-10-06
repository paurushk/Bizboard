"""The architecture note must name every installed project app."""

from pathlib import Path

from django.conf import settings

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture.md"
THIRD_PARTY = {
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
}
DARK = ("manufacturing", "payroll", "crm")


def test_architecture_lists_every_project_app_and_only_three_dark_modules():
    text = DOC.read_text(encoding="utf-8")
    assert "Python 3.13" in text
    labels = []
    for app in settings.INSTALLED_APPS:
        if app.startswith("django.") or app in THIRD_PARTY:
            continue
        labels.append(app.split(".")[0])
    missing = [label for label in labels if f"`{label}`" not in text]
    assert missing == []
    assert "dark modules" in text.lower()
    dark_section = text.lower().split("dark modules", 1)[1].split("installed, not dark", 1)[0]
    for name in DARK:
        assert f"`{name}`" in dark_section
    not_dark = text.lower().split("installed, not dark", 1)[1]
    for name in ("contracts", "workshop", "projects", "insurance", "banking"):
        assert f"`{name}`" in not_dark
        assert name not in dark_section

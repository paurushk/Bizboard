"""SET-20: the impact registry only names fields that really exist."""

from accounts.models import Company, CompanyStatutoryLicence, CompanyUser
from core.settings_impact import SCREEN_IMPACT, SETTING_IMPACT
from core.models import DocumentSeries
from masters.models import PriceList, Unit
from payments.models import BankAccount

PREFIX_MODELS = {
    "company": Company,
    "gst": Company,
    "money_in": Company,
    "items": Company,
    "ai": Company,
    "accounting": Company,
    "gateway": Company,
    "licence": CompanyStatutoryLicence,
    "bank": BankAccount,
    "series": DocumentSeries,
    "price_list": PriceList,
    "unit": Unit,
    "users": CompanyUser,
}
#: Registry keys that describe a group of fields or a relation rather than one column.
NOT_COLUMNS = {"price_list.items", "packs.flags", "templates.layout"}


def _field_names(model):
    return {f.name for f in model._meta.get_fields()}


def test_every_field_key_names_a_real_field():
    for key in SETTING_IMPACT:
        if key in NOT_COLUMNS:
            continue
        prefix, field = key.split(".", 1)
        model = PREFIX_MODELS[prefix]
        assert field in _field_names(model), f"{key}: {model.__name__} has no field {field}"


def test_every_screen_and_field_lists_at_least_one_consumer_except_help():
    for screen, consumers in SCREEN_IMPACT.items():
        if screen not in ("help-health", "counter-diagnostics"):
            assert consumers, screen
    for key, consumers in SETTING_IMPACT.items():
        assert consumers, key

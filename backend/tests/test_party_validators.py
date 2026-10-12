"""Party-master validators: Indian mobile numbers, GSTIN state rules, per-user throttle key."""

from types import SimpleNamespace

import pytest

from core.throttles import UserScopeRateThrottle
from core.validators import is_valid_indian_mobile
from masters import gstin_rules

KA = "29ABCDE1234F1ZW"
MH = "27AABCU9603R1ZN"


@pytest.mark.parametrize("number", [
    "9876543210", "6000000000", "9123456789", "919123456789", "+919123456789", "09123456789",
    "+91 98765-43210", " 98765 43210 ",
])
def test_valid_indian_mobiles(number):
    assert is_valid_indian_mobile(number)


@pytest.mark.parametrize("number", [
    "", None, "98765", "5123456789", "1234567890", "91912345678", "+9198765432", "98765432101", "abcdefghij",
    "0091 98765 43210", "+1 415 555 0100",
])
def test_invalid_indian_mobiles(number):
    assert not is_valid_indian_mobile(number)


def test_a_number_beginning_91_is_not_mistaken_for_a_country_code():
    assert is_valid_indian_mobile("9100000000")
    assert not is_valid_indian_mobile("91000000")


class TestGstinRules:
    def test_normalise(self):
        assert gstin_rules.normalise("  29abcde1234f1zw ") == KA
        assert gstin_rules.normalise(None) == ""

    def test_derive_state_and_pan(self):
        assert gstin_rules.derive_state(KA) == "Karnataka"
        assert gstin_rules.derive_pan(KA) == "ABCDE1234F"
        assert gstin_rules.derive_state("junk") is None
        assert gstin_rules.derive_pan("junk") == ""

    def test_codes_with_no_single_state(self):
        assert gstin_rules.derive_state("97AABCU9603R1ZX") is None
        assert gstin_rules.state_conflicts("97AABCU9603R1ZX", "Karnataka") is None

    def test_merged_union_territory_code(self):
        assert gstin_rules.derive_state("26AABCU9603R1ZX") == "Dadra and Nagar Haveli and Daman and Diu"
        assert gstin_rules.state_conflicts("26AABCU9603R1ZX", "Daman and Diu") is None
        assert gstin_rules.state_conflicts("26AABCU9603R1ZX", "dd") is None

    @pytest.mark.parametrize("gstin, state, expected", [
        (KA, "Karnataka", None),
        (KA, "KA", None),
        (KA, "  karnataka  ", None),
        (KA, "Maharashtra", "Karnataka"),
        (MH, "Karnataka", "Maharashtra"),
        (KA, "", None),
        (KA, "Somewhere odd", None),
        ("", "Karnataka", None),
    ])
    def test_state_conflicts(self, gstin, state, expected):
        assert gstin_rules.state_conflicts(gstin, state) == expected

    def test_every_listed_state_code_resolves_back_to_itself(self):
        for code, name in gstin_rules.GST_CODE_TO_STATE.items():
            assert gstin_rules.state_code_of_name(name) == code

    def test_verification_reset_clears_every_verification_field(self):
        assert gstin_rules.VERIFICATION_RESET == {
            "gstin_verification_status": "UNVERIFIED",
            "gstin_legal_name": "",
            "gstin_verified_at": None,
            "gstin_raw_payload": None,
        }


class TestUserScopeRateThrottle:
    def test_key_is_per_user_and_scope(self):
        throttle = UserScopeRateThrottle.__new__(UserScopeRateThrottle)
        throttle.scope = "gstin_verify_user"
        throttle.cache_format = "throttle_%(scope)s_%(ident)s"
        a = throttle.get_cache_key(SimpleNamespace(user=SimpleNamespace(is_authenticated=True, pk=1)), None)
        b = throttle.get_cache_key(SimpleNamespace(user=SimpleNamespace(is_authenticated=True, pk=2)), None)
        assert a != b and "gstin_verify_user" in a and "user-1" in a

    def test_an_anonymous_request_has_no_key(self):
        throttle = UserScopeRateThrottle.__new__(UserScopeRateThrottle)
        throttle.scope = "gstin_verify_user"
        throttle.cache_format = "throttle_%(scope)s_%(ident)s"
        assert throttle.get_cache_key(SimpleNamespace(user=SimpleNamespace(is_authenticated=False)), None) is None

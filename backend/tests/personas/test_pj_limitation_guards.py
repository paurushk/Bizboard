"""PJ-LIMITATION-GUARDS — the demoted D6/D10 surfaces are dark in the pilot profile.

Scope revision 2026-09-09b demoted D6 (fixed assets) and D10 (bill of entry) to
KNOWN LIMITATIONS. The pilot flag profile turns both flags off. This asserts
that even the OWNER persona — the highest-privilege role in any archetype —
gets a 404 (route not mounted), not a 403, from those endpoints.

The flag-on behaviour lives in tests/workflows/test_wf_extended_stubs.py
(WF-53, WF-57) and tests/workflows/test_wf_limitation_guards.py.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db

DARK_IN_PILOT = (
    "/api/v1/accounting/fixed-assets/",
    "/api/v1/purchases/bills-of-entry/",
)


@override_settings(ENABLE_FIXED_ASSETS=False, ENABLE_BOE=False)
def test_pj_owner_cannot_reach_demoted_routes_in_pilot_profile():
    ns = seed_archetype("trader")  # books on, owner is full-capability
    for url in DARK_IN_PILOT:
        assert ns.owner_client.get(url).status_code == 404, url
        assert ns.owner_client.post(url, {}, format="json").status_code == 404, url

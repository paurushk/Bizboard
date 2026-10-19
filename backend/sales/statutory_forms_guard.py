"""D15 / QOS-0027: ARCH-05 statutory compliance (drug licence 20B/21B, FSSAI).

No-op unless `settings.ENABLE_ARCH05_STATUTORY_FORMS` is on AND the invoice
carries at least one DRUG/FOOD-regulated line — every existing archetype and
every company that has never touched `regulated_category` sees no change.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.models import CompanyStatutoryLicence
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from masters.models import Product
from sales.statutory_snapshot import invoice_state_code, licence_covers_state

_LICENCE_TYPES_FOR_CATEGORY = {
    Product.RegulatedCategory.DRUG: (
        CompanyStatutoryLicence.LicenceType.DRUG_20B,
        CompanyStatutoryLicence.LicenceType.DRUG_21B,
    ),
    Product.RegulatedCategory.FOOD: (CompanyStatutoryLicence.LicenceType.FSSAI,),
}


def assert_statutory_licence_present(company, items, *, confirm_missing_licence=False, invoice=None) -> None:
    if not getattr(settings, "ENABLE_ARCH05_STATUTORY_FORMS", False):
        return

    regulated_categories = {
        it.product.regulated_category
        for it in items
        if it.product_id and it.product.regulated_category != Product.RegulatedCategory.NONE
    }
    if not regulated_categories:
        return

    today = timezone.localdate()
    still_valid = Q(valid_upto__isnull=True) | Q(valid_upto__gte=today)
    # SET-03: a licence covers the state of its premises. When the invoice's branch state is
    # known, only a licence with no state or the same state counts (see statutory_snapshot).
    state_code = invoice_state_code(invoice) if invoice is not None else None
    missing = []
    for category in regulated_categories:
        candidates = CompanyStatutoryLicence.objects.filter(
            still_valid,
            company=company,
            licence_type__in=_LICENCE_TYPES_FOR_CATEGORY[category],
            is_active=True,
        )
        if not any(licence_covers_state(licence, state_code) for licence in candidates):
            missing.append(category)
    if not missing:
        return

    if not confirm_missing_licence:
        labels = ", ".join(Product.RegulatedCategory(c).label for c in sorted(missing))
        where = f" for the branch's state ({state_code})" if state_code else ""
        raise BusinessRuleError(
            f"This invoice has a {labels} line but the company has no active statutory "
            f"licence on file{where}. Add the licence, or confirm to complete anyway "
            f"(confirm_missing_licence=true).",
            code=HelpCode.CONFIRM_MISSING_LICENCE,
        )

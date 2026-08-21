"""Derived onboarding state for company setup."""

from __future__ import annotations


def derive_onboarding(company) -> dict:
    """Return the company's onboarding status and data-derived step flags."""
    from masters.models import Product
    from sales.models import SalesInvoice

    tax_done = company.tax_profile_confirmed_at is not None
    shop_done = bool((company.address or "").strip())
    payments_done = bool(
        (company.bank_account or "").strip() or (company.upi_id or "").strip()
    )
    catalog_done = Product.objects.filter(company=company).exists()
    activation_done = SalesInvoice.objects.filter(
        company=company,
        status=SalesInvoice.Status.COMPLETED,
    ).exists()

    # Payments are optional and must not block catalog / first_bill.
    blocking_steps = (
        ("tax", tax_done),
        ("shop", shop_done),
        ("catalog", catalog_done),
        ("first_bill", activation_done),
    )
    first_incomplete = next((name for name, done in blocking_steps if not done), None)
    dismissed = company.onboarding_dismissed_at is not None
    any_progress = bool(
        tax_done
        or shop_done
        or catalog_done
        or payments_done
        or (company.gstin or "").strip()
    )

    if activation_done:
        status = "COMPLETED"
        step = None
    elif dismissed:
        status = "DISMISSED"
        step = first_incomplete
    elif any_progress:
        status = "IN_PROGRESS"
        step = first_incomplete
    else:
        status = "NOT_STARTED"
        step = "tax"

    # UI may still show optional payments between shop and catalog.
    ui_step = step
    if step == "catalog" and shop_done and not payments_done:
        ui_step = "payments"

    return {
        "status": status,
        "step": step,
        "ui_step": ui_step,
        "dismissed": dismissed,
        "tax_done": tax_done,
        "shop_done": shop_done,
        "payments_done": payments_done,
        "catalog_done": catalog_done,
        "activation_done": activation_done,
        "started": company.onboarding_started_at is not None,
    }


def should_force_setup(*, company, is_owner: bool, wizard_enabled: bool) -> bool:
    if not wizard_enabled or not is_owner:
        return False
    derived = derive_onboarding(company)
    return derived["status"] in ("NOT_STARTED", "IN_PROGRESS")

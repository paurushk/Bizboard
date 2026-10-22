"""Derived onboarding state for company setup."""

from __future__ import annotations


def derive_onboarding(company) -> dict:
    """Return the company's onboarding status and data-derived step flags."""
    from masters.models import Product
    from sales.models import SalesInvoice

    tax_done = company.tax_profile_confirmed_at is not None
    shop_done = bool((company.address or "").strip())
    from payments.services import invoice_bank_details

    bank = invoice_bank_details(company)
    payments_done = bool((bank["account_number"] or "").strip() or (bank["upi_id"] or "").strip())
    catalog_done = Product.objects.filter(company=company).exists()
    activation_done = SalesInvoice.objects.filter(
        company=company,
        status=SalesInvoice.Status.COMPLETED,
    ).exists()
    # ONB-CR-001: the wizard's last step saves a draft bill for the owner to review and finalise.
    # Until it is finalised activation is not done, but the owner must not be bounced back into
    # the wizard (which would offer to create yet another draft).
    first_bill_draft_id = None
    if not activation_done:
        first_bill_draft_id = (
            SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.DRAFT)
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
        )

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
        "first_bill_draft_id": first_bill_draft_id,
        "started": company.onboarding_started_at is not None,
    }


def should_force_setup(*, company, is_owner: bool, wizard_enabled: bool) -> bool:
    if not wizard_enabled or not is_owner:
        return False
    derived = derive_onboarding(company)
    if derived["step"] == "first_bill" and derived["first_bill_draft_id"]:
        return False
    return derived["status"] in ("NOT_STARTED", "IN_PROGRESS")

"""At-rest checks for the workshop, project, policy, and vendor-share rows.

These do not post money. They fail when a row disagrees with its own
invoice pointer, dates, or tenant. Insurer commission is intentionally
absent: that book is off the ledger (D17).
"""

from __future__ import annotations

from django.db.models import F

from .base import invariant


@invariant(
    "roadmap.job_card_invoice_same_company",
    consequence="A job card points at another company's invoice, or says it is invoiced without one.",
)
def job_card_invoice_same_company(company) -> list[str]:
    from workshop.models import JobCard

    out = []
    foreign = (
        JobCard.objects.filter(company=company, sales_invoice__isnull=False)
        .exclude(sales_invoice__company_id=company.id)
        .count()
    )
    if foreign:
        out.append(f"{foreign} job card(s) reference an invoice from another company")
    dangling = JobCard.objects.filter(
        company=company, status=JobCard.Status.INVOICED, sales_invoice__isnull=True,
    ).count()
    if dangling:
        out.append(f"{dangling} job card(s) are INVOICED with no invoice")
    return out


@invariant(
    "roadmap.milestone_invoice_same_company",
    consequence="A milestone points at another company's invoice, or says it is invoiced without one.",
)
def milestone_invoice_same_company(company) -> list[str]:
    from projects.models import ProjectMilestone

    out = []
    foreign = (
        ProjectMilestone.objects.filter(company=company, sales_invoice__isnull=False)
        .exclude(sales_invoice__company_id=company.id)
        .count()
    )
    if foreign:
        out.append(f"{foreign} milestone(s) reference an invoice from another company")
    dangling = ProjectMilestone.objects.filter(
        company=company, status=ProjectMilestone.Status.INVOICED, sales_invoice__isnull=True,
    ).count()
    if dangling:
        out.append(f"{dangling} milestone(s) are INVOICED with no invoice")
    return out


@invariant(
    "roadmap.policy_option_same_company",
    consequence="A policy's term or chosen option does not belong to this company.",
)
def policy_option_same_company(company) -> list[str]:
    from insurance.models import Policy

    out = []
    backwards = Policy.objects.filter(company=company, end_date__lt=F("start_date")).count()
    if backwards:
        out.append(f"{backwards} policy term(s) end before they start")
    foreign = (
        Policy.objects.filter(company=company, option__isnull=False)
        .exclude(option__company_id=company.id)
        .count()
    )
    if foreign:
        out.append(f"{foreign} policy option(s) belong to another company")
    mismatch = (
        Policy.objects.filter(company=company, option__isnull=False)
        .exclude(option__product_id=F("product_id"))
        .count()
    )
    if mismatch:
        out.append(f"{mismatch} policy option(s) are for a different product than the policy")
    return out


@invariant(
    "roadmap.vendor_share_company_is_vendor",
    consequence="A shared ticket row is stored on the wrong company, or a company shared a ticket with itself.",
)
def vendor_share_company_is_vendor(company) -> list[str]:
    from support.models import VendorTicketShare

    out = []
    wrong = VendorTicketShare.objects.filter(company=company).exclude(vendor_company_id=F("company_id")).count()
    if wrong:
        out.append(f"{wrong} share row(s) are not stored on the vendor company")
    self_share = VendorTicketShare.objects.filter(company=company, source_company_id=F("company_id")).count()
    if self_share:
        out.append(f"{self_share} share row(s) use the vendor company as the source")
    return out

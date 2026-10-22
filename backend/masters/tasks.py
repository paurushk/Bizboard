"""Scheduled customer-master jobs."""

import logging

from celery import shared_task

logger = logging.getLogger("masters.customers")

@shared_task
def customers_audit_task():
    """Monthly: run the customer health check per company and tell the owners when something needs a look."""
    from core.rls import company_ids_having, set_rls_company

    from .models import Customer

    notified = 0
    try:
        # WP-E1: only companies with customers; one company's crash never stops the rest.
        for company_id in company_ids_having(Customer):  # inline-company-loop-ok: monthly, light
            set_rls_company(company_id)
            try:
                notified += _audit_company_customers(company_id)
            except Exception:  # noqa: BLE001 - keep checking the other companies
                logger.exception("customer.audit failed company=%s", company_id)
    finally:
        set_rls_company(None)
    return {"companies_notified": notified}


def _audit_company_customers(company_id) -> int:
    from accounts.models import Company
    from core.services.telegram import notify_company_owners

    from .audit import CHECK_LABELS, audit_customers
    from .models import Customer

    findings, _companies, _fixed = audit_customers(Customer.objects.filter(company_id=company_id))
    if not findings:
        return 0
    counts = {check: len(rows) for (_cid, check), rows in findings.items()}
    logger.info("customer.audit company=%s findings=%s", company_id, counts)
    company = Company.objects.filter(pk=company_id).first()
    if company is None:
        return 0
    lines = [f"{n} {CHECK_LABELS.get(check, check)}" for check, n in sorted(counts.items())]
    notify_company_owners(
        company,
        subject="Customer list needs a look",
        body="Monthly customer check found: " + "; ".join(lines) + ". Run the customer audit for the rows.",
    )
    return 1

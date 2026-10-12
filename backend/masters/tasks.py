"""Scheduled customer-master jobs."""

import logging

from celery import shared_task

logger = logging.getLogger("masters.customers")

@shared_task
def customers_audit_task():
    """Monthly: run the customer health check per company and tell the owners when something needs a look."""
    from accounts.models import Company
    from core.rls import iter_company_ids, set_rls_company
    from core.services.telegram import notify_company_owners

    from .audit import CHECK_LABELS, audit_customers
    from .models import Customer

    notified = 0
    for company_id in list(iter_company_ids()):
        set_rls_company(company_id)
        findings, _companies, _fixed = audit_customers(Customer.objects.filter(company_id=company_id))
        if not findings:
            continue
        counts = {check: len(rows) for (_cid, check), rows in findings.items()}
        logger.info("customer.audit company=%s findings=%s", company_id, counts)
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            continue
        lines = [f"{n} {CHECK_LABELS.get(check, check)}" for check, n in sorted(counts.items())]
        notify_company_owners(
            company,
            subject="Customer list needs a look",
            body="Monthly customer check found: " + "; ".join(lines) + ". Run the customer audit for the rows.",
        )
        notified += 1
    set_rls_company(None)
    return {"companies_notified": notified}

from datetime import timedelta


def compute_contract_status(end_date, renewal_reminder_days, today) -> str:
    if end_date < today:
        return "EXPIRED"
    if end_date <= today + timedelta(days=int(renewal_reminder_days or 0)):
        return "EXPIRING"
    return "ACTIVE"


def effective_contract_status(stored_status, end_date, renewal_reminder_days, today) -> str:
    """Status a reader should trust. CANCELLED is intentional; every other
    stored value is a cache of the dates and can lag the nightly beat."""
    if stored_status == "CANCELLED":
        return "CANCELLED"
    return compute_contract_status(end_date, renewal_reminder_days, today)


def filter_by_effective_status(qs, wanted, today):
    """Queryset whose effective status is ``wanted``. Dates are evaluated in
    Python so SQLite and Postgres agree."""
    if wanted == "CANCELLED":
        return qs.filter(status="CANCELLED")
    scan = qs.exclude(status="CANCELLED").prefetch_related(None).only(
        "id", "status", "end_date", "renewal_reminder_days",
    )
    ids = [
        row.id
        for row in scan
        if effective_contract_status(row.status, row.end_date, row.renewal_reminder_days, today) == wanted
    ]
    return qs.filter(pk__in=ids)

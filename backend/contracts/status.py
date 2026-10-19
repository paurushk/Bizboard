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
    """Queryset whose effective status is ``wanted``.

    Uses the stored ``expiring_from_date`` (end date minus the reminder window), so each status is
    a plain date comparison that reads the same on SQLite and Postgres and can use an index.
    """
    if wanted == "CANCELLED":
        return qs.filter(status="CANCELLED")
    live = qs.exclude(status="CANCELLED")
    if wanted == "EXPIRED":
        return live.filter(end_date__lt=today)
    if wanted == "EXPIRING":
        return live.filter(end_date__gte=today, expiring_from_date__lte=today)
    if wanted == "ACTIVE":
        return live.filter(end_date__gte=today, expiring_from_date__gt=today)
    return qs.none()

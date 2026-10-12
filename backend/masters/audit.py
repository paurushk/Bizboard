"""Customer master health check (CUS-22), shared by `manage.py customers_audit` and the monthly task."""

from collections import defaultdict

from . import gstin_rules
from .models import Customer


CHECK_LABELS = {
    "stale_valid_status": "verified status without a verified GSTIN",
    "state_mismatch": "state that disagrees with the GSTIN",
    "duplicate_gstin": "duplicate GSTIN",
    "walk_in_anomaly": "walk-in customer with a GSTIN, credit limit or non-active status",
    "multiple_walk_ins": "more than one walk-in customer",
}


def audit_customers(qs=None, *, fix=False):
    """Return ``(findings, companies_checked, repaired)``.

    ``findings`` maps ``(company_id, check)`` to ``[(customer_id, detail)]``. With ``fix`` the only repair is
    resetting a verification status that no longer describes the stored GSTIN.
    """
    qs = Customer.objects.all() if qs is None else qs
    findings = defaultdict(list)
    by_gstin = defaultdict(list)
    walk_ins = defaultdict(list)
    companies = set()
    repaired = 0
    for c in qs.order_by("company_id", "pk").iterator(chunk_size=2000):
        companies.add(c.company_id)
        gstin = gstin_rules.normalise(c.gstin)
        stale = c.gstin_verification_status == "VALID" and (not gstin or c.gstin_verified_at is None)
        if stale:
            findings[(c.company_id, "stale_valid_status")].append((c.pk, f"status VALID, gstin={gstin!r}"))
            if fix:
                for field, value in gstin_rules.VERIFICATION_RESET.items():
                    setattr(c, field, value)
                c.save(update_fields=[*gstin_rules.VERIFICATION_RESET, "updated_at"])
                repaired += 1
        if gstin:
            wanted = gstin_rules.state_conflicts(gstin, c.state)
            if wanted:
                findings[(c.company_id, "state_mismatch")].append((c.pk, f"state {c.state!r}, GSTIN says {wanted}"))
            by_gstin[(c.company_id, gstin)].append(c.pk)
        if c.is_pos_walk_in:
            walk_ins[c.company_id].append(c.pk)
            problems = []
            if gstin:
                problems.append("has GSTIN")
            if c.credit_limit and c.credit_limit > 0:
                problems.append("has credit limit")
            if c.status != Customer.Status.ACTIVE:
                problems.append(f"status {c.status}")
            if problems:
                findings[(c.company_id, "walk_in_anomaly")].append((c.pk, ", ".join(problems)))
    for (company_id, gstin), ids in by_gstin.items():
        if len(ids) > 1:
            findings[(company_id, "duplicate_gstin")].append((ids[0], f"{gstin} on customers {ids}"))
    for company_id, ids in walk_ins.items():
        if len(ids) > 1:
            findings[(company_id, "multiple_walk_ins")].append((ids[0], f"walk-in rows {ids}"))
    return findings, companies, repaired

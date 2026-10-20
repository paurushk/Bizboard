"""DAN-08: copy set-aside state from the per-invoice / per-promise keys to one key per customer.

The feed now shows one row per customer (``AR_CUSTOMER:<customer id>``) instead of separate
collection-risk, predicted-late, promise-to-pay and credit-limit rows. This COPIES state; the old
rows stay in place, so nothing is lost if the change is rolled back.

Several old rows can belong to one customer, and ``(company, dedupe_key)`` is unique, so they are
merged: first_seen = earliest; dismissed only if every old row was; the soonest unexpired snooze
wins; the most recent assignment wins.
"""

from django.db import migrations

SOURCE_CODES = ("AR_COLLECTION_RISK", "PREDICTED_LATE_PAYMENT", "PROMISE_TO_PAY_DUE", "CREDIT_LIMIT_NEAR")


def _customer_id(apps, company_id, key):
    code, _, rest = key.partition(":")
    if code in ("AR_COLLECTION_RISK", "CREDIT_LIMIT_NEAR"):
        # "<CODE>:customer:<id>"
        parts = rest.split(":")
        if len(parts) == 2 and parts[0] == "customer" and parts[1].isdigit():
            return int(parts[1])
        return None
    if not rest.isdigit():
        return None
    if code == "PREDICTED_LATE_PAYMENT":
        SalesInvoice = apps.get_model("sales", "SalesInvoice")
        return SalesInvoice.objects.filter(company_id=company_id, pk=int(rest)).values_list("customer_id", flat=True).first()
    if code == "PROMISE_TO_PAY_DUE":
        PaymentPromise = apps.get_model("payments", "PaymentPromise")
        return PaymentPromise.objects.filter(company_id=company_id, pk=int(rest)).values_list("customer_id", flat=True).first()
    return None


def forwards(apps, schema_editor):
    State = apps.get_model("insights", "AttentionRowState")
    Outcome = apps.get_model("insights", "AttentionOutcome")

    groups = {}
    for state in State.objects.filter(dedupe_key__regex=r"^(%s):" % "|".join(SOURCE_CODES)).iterator():
        customer_id = _customer_id(apps, state.company_id, state.dedupe_key)
        if customer_id:
            groups.setdefault((state.company_id, customer_id), []).append(state)

    for (company_id, customer_id), states in groups.items():
        key = f"AR_CUSTOMER:{customer_id}"
        if State.objects.filter(company_id=company_id, dedupe_key=key).exists():
            continue
        newest = max(states, key=lambda s: s.updated_at)
        snoozes = [s.snooze_until for s in states if s.snooze_until]
        assigned = [s for s in states if s.assigned_to_id]
        latest_assigned = max(assigned, key=lambda s: s.updated_at) if assigned else None
        State.objects.create(
            company_id=company_id,
            dedupe_key=key,
            first_seen=min(s.first_seen for s in states),
            dismissed=all(s.dismissed for s in states),
            snooze_until=min(snoozes) if snoozes else None,
            snooze_reason=newest.snooze_reason,
            assigned_to_id=latest_assigned.assigned_to_id if latest_assigned else None,
            due_date=latest_assigned.due_date if latest_assigned else None,
            state_at=newest.updated_at,
        )

    outcome_groups = {}
    for outcome in Outcome.objects.filter(dedupe_key__regex=r"^(%s):" % "|".join(SOURCE_CODES)).iterator():
        customer_id = _customer_id(apps, outcome.company_id, outcome.dedupe_key)
        if customer_id:
            outcome_groups.setdefault((outcome.company_id, customer_id), []).append(outcome)
    for (company_id, customer_id), outcomes in outcome_groups.items():
        key = f"AR_CUSTOMER:{customer_id}"
        if Outcome.objects.filter(company_id=company_id, dedupe_key=key).exists():
            continue
        first = min(outcomes, key=lambda o: o.recorded_at)
        Outcome.objects.create(
            company_id=company_id,
            dedupe_key=key,
            code="AR_CUSTOMER",
            outcome=first.outcome,
            within_window=first.within_window,
            metric_improved=first.metric_improved,
            recorded_at=first.recorded_at,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("insights", "0014_attention_v2_state"),
        ("sales", "0079_salesinvoice_statutory_licences_snapshot"),
        ("payments", "0045_bankaccount_full_number_upi_print"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]

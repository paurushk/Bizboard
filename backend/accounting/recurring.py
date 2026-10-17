"""ACS-17: recurring expenses. A template says what repeats; "create due" turns each overdue date into an expense."""
from __future__ import annotations

import calendar
from datetime import date

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .expense_posting import sync_expense_posting
from .models import Expense, RecurringExpense

MAX_PER_TEMPLATE = 12


def advance(current: date, frequency: str) -> date:
    step = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}[frequency]
    month_index = current.month - 1 + step
    year = current.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(current.day, calendar.monthrange(year, month)[1]))


def due_templates(company, today: date | None = None):
    today = today or timezone.localdate()
    return RecurringExpense.objects.filter(company=company, is_active=True, next_date__lte=today).select_related("category")


def create_due(company, user, *, ids=None, today: date | None = None) -> dict:
    """Create the expenses that have come due. Safe to repeat: a template and date make one expense."""
    from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
    from reporting.gst_periods import assert_period_allows_money_amend

    today = today or timezone.localdate()
    created, skipped = [], []
    qs = due_templates(company, today)
    if ids:
        qs = qs.filter(pk__in=ids)
    for template in qs:
        made = 0
        while template.next_date <= today and made < MAX_PER_TEMPLATE:
            if template.end_date and template.next_date > template.end_date:
                template.is_active = False
                template.save(update_fields=["is_active", "updated_at"])
                break
            on = template.next_date
            exists = Expense.objects.filter(company=company, recurring_template=template, expense_date=on).first()
            if exists is None:
                try:
                    with transaction.atomic():
                        assert_period_allows_money_amend(company, on)
                        expense = Expense.objects.create(
                            company=company, category=template.category, expense_date=on, party_name=template.party_name,
                            amount=template.amount, notes=template.notes, payment_mode=template.payment_mode,
                            bank_account=template.bank_account, expense_account=template.expense_account,
                            cost_center=template.cost_center, recurring_template=template,
                            created_by=user, updated_by=user,
                        )
                        expense.number = DocumentNumberService.next_number(
                            company, "EXPENSE", gstin=resolve_series_gstin(company), on_date=on,
                        )
                        expense.save(update_fields=["number"])
                        sync_expense_posting(expense, user)
                except BusinessRuleError as exc:
                    skipped.append({"template": template.pk, "date": on.isoformat(), "reason": str(exc.detail)})
                    break
                created.append({"template": template.pk, "expense": expense.pk, "date": on.isoformat()})
            template.last_created_date = on
            template.next_date = advance(on, template.frequency)
            template.save(update_fields=["last_created_date", "next_date", "updated_at"])
            made += 1
    return {"created": created, "skipped": skipped}

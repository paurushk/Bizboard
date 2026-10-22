"""Shared bits for job work: errors, numbering, the godown that stands for a job worker's premises."""

from decimal import ROUND_HALF_UP, Decimal

from core.exceptions import BusinessRuleError
from core.services.sequences import next_number
from inventory.models import SerialNumber, Warehouse

ZERO = Decimal("0")
Q2 = Decimal("0.01")


def d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def money(v) -> Decimal:
    return d(v).quantize(Q2, rounding=ROUND_HALF_UP)


def rule(message: str, code: str) -> BusinessRuleError:
    return BusinessRuleError(message, code=code)


def number(company, scope: str, prefix: str) -> str:
    return next_number(company, scope, prefix=prefix)


def settings_for(company):
    from manufacturing.services.common import get_settings

    return get_settings(company)


def ensure_job_worker_warehouse(company, supplier) -> Warehouse:
    """The godown that holds our stock while it is at this job worker (made on first use)."""
    found = Warehouse.objects.filter(company=company, kind=Warehouse.Kind.JOB_WORKER, job_worker=supplier).first()
    if found:
        return found
    code = f"JW{supplier.pk}"
    n = 1
    while Warehouse.all_objects.filter(company=company, code=code).exists():
        n += 1
        code = f"JW{supplier.pk}-{n}"
    return Warehouse.objects.create(
        company=company, name=f"At {supplier.name}"[:100], code=code, kind=Warehouse.Kind.JOB_WORKER,
        job_worker=supplier,
    )


def move_serials(company, product, numbers, source_wh, target_wh):
    """Serial-tracked goods change godown without changing status."""
    numbers = [str(n).strip() for n in (numbers or []) if str(n).strip()]
    for value in numbers:
        row = SerialNumber.objects.select_for_update().filter(
            company=company, product=product, serial_number=value, status=SerialNumber.Status.AVAILABLE,
        ).first()
        if row is None or row.warehouse_id != source_wh.pk:
            raise rule(f"Serial number '{value}' is not available in '{source_wh.name}'.", "JW_SERIAL_UNAVAILABLE")
        row.warehouse = target_wh
        row.save(update_fields=["warehouse", "updated_at"])

"""Item / godown / expiry rules shared by API, import, and posting."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import BatchLot, StockBalance, StockMovement, Warehouse

logger = logging.getLogger(__name__)
TWOPLACES = Decimal("0.01")
FROZEN_AFTER_MOVEMENT = (
    "unit",
    "product_type",
    "track_inventory",
    "track_batch",
    "track_serial",
)


def tracks_inventory(product) -> bool:
    if getattr(product, "product_type", "GOODS") == "SERVICE":
        return False
    return bool(getattr(product, "track_inventory", True))


def business_date(company=None) -> date:
    return timezone.localdate()


def fy_floor(company, today: date | None = None) -> date:
    """First day of the company's current financial year (not the previous FY)."""
    today = today or business_date(company)
    month = int(getattr(company, "fy_start_month", 4) or 4)
    month = min(12, max(1, month))
    year = today.year - 1 if today.month < month else today.year
    return date(year, month, 1)


def lot_is_expired(lot, as_of: date | None = None) -> bool:
    """A lot is expired when expiry_date < business date (sellable on the expiry day)."""
    expiry = getattr(lot, "expiry_date", None)
    if expiry is None:
        return False
    return expiry < (as_of or business_date())


def exclusive_unit_cost(amount, gst_rate=None, *, inclusive: bool = False) -> Decimal:
    value = Decimal(str(amount or 0))
    if value < 0:
        raise BusinessRuleError("Unit cost cannot be negative.")
    if not inclusive:
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    rate = Decimal(str(gst_rate or 0))
    if rate <= 0:
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return (value / (Decimal("1") + rate / Decimal("100"))).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def opening_unit_cost(product, unit_cost=None) -> Decimal | None:
    raw = unit_cost if unit_cost is not None else product.purchase_price
    if raw is None:
        return None
    inclusive = bool(getattr(product, "purchase_tax_inclusive", False))
    return exclusive_unit_cost(raw, product.gst_rate, inclusive=inclusive)


def _alternate_unit_factor(product, unit_name: str | None = None) -> Decimal:
    """Pieces-per-alternate-unit when `unit_name` is the product's alt unit, else 1."""
    alt = getattr(product, "alternate_unit", None)
    if alt is None or not unit_name:
        return Decimal("1")
    needle = unit_name.strip().upper()
    aliases = {
        (alt.short_name or "").upper(),
        (alt.name or "").upper(),
        (getattr(alt, "uqc_code", "") or "").upper(),
    }
    if needle not in aliases:
        return Decimal("1")
    rate = Decimal(str(getattr(product, "conversion_rate", 1) or 1))
    if rate <= 0:
        raise BusinessRuleError("Conversion rate must be greater than zero.")
    return rate


def base_quantity(product, quantity, unit_name: str | None = None) -> Decimal:
    qty = Decimal(str(quantity))
    if qty <= 0:
        return qty
    factor = _alternate_unit_factor(product, unit_name)
    if factor == 1:
        return qty
    return (qty * factor).quantize(Decimal("0.001"))


def base_unit_cost(product, unit_price, unit_name: str | None = None) -> Decimal:
    """Convert a price stated in `unit_name` into a per-base-unit cost for stock layers."""
    price = Decimal(str(unit_price or 0))
    if price < 0:
        raise BusinessRuleError("Unit cost cannot be negative.")
    factor = _alternate_unit_factor(product, unit_name)
    if factor <= 0:
        raise BusinessRuleError("Conversion rate must be greater than zero.")
    return (price / factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def apply_product_type_matrix(attrs: dict, instance=None) -> dict:
    product_type = attrs.get("product_type")
    if product_type is None and instance is not None:
        product_type = instance.product_type
    product_type = product_type or "GOODS"
    if product_type == "SERVICE":
        attrs["track_inventory"] = False
        attrs["track_batch"] = False
        attrs["track_serial"] = False
        return attrs
    track_inventory = attrs.get("track_inventory")
    if track_inventory is None and instance is not None:
        track_inventory = instance.track_inventory
    if track_inventory is False:
        attrs["track_batch"] = False
        attrs["track_serial"] = False
    track_batch = attrs.get("track_batch", getattr(instance, "track_batch", False) if instance else False)
    track_serial = attrs.get("track_serial", getattr(instance, "track_serial", False) if instance else False)
    if track_batch and track_serial:
        raise BusinessRuleError("Batch tracking and serial tracking cannot both be on for the same item.")
    return attrs


def assert_tracking_unlocked(instance, attrs: dict):
    if instance is None:
        return
    if not instance.stock_movements.exists():
        return
    for field in FROZEN_AFTER_MOVEMENT:
        if field not in attrs:
            continue
        if attrs[field] != getattr(instance, field):
            raise BusinessRuleError(
                "Unit, item type, and tracking flags cannot change after stock movements exist."
            )


def resolve_warehouse(company, warehouse_id=None, *, allow_inactive: bool = False):
    if warehouse_id:
        warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company).first()
        if warehouse is None:
            raise BusinessRuleError("Invalid godown for this company.")
    else:
        from .services import InventoryService

        warehouse = InventoryService.default_warehouse(company)
    if warehouse is None:
        raise BusinessRuleError("No godown exists. Create a default godown first.")
    if not allow_inactive and not warehouse.is_active:
        raise BusinessRuleError(f"Godown '{warehouse.name}' is inactive and cannot receive stock.")
    return warehouse


def match_warehouse(company, name_or_code: str):
    raw = (name_or_code or "").strip()
    if not raw:
        return resolve_warehouse(company)
    warehouse = (
        Warehouse.objects.filter(company=company)
        .filter(Q(name__iexact=raw) | Q(code__iexact=raw))
        .first()
    )
    names = list(
        Warehouse.objects.filter(company=company, is_active=True).values_list("name", flat=True)
    )
    listed = ", ".join(names) if names else "(none)"
    if warehouse is None:
        raise BusinessRuleError(f"Godown '{raw}' not found. Available: {listed}.")
    if not warehouse.is_active:
        raise BusinessRuleError(f"Godown '{warehouse.name}' is inactive. Available: {listed}.")
    return warehouse


def get_or_create_batch(*, company, product, batch_no, expiry_date=None, manufacturing_date=None, user=None):
    number = (batch_no or "").strip()
    if not number:
        raise BusinessRuleError("Batch number is required for batch-tracked items.")
    if manufacturing_date and expiry_date and manufacturing_date > expiry_date:
        raise BusinessRuleError("Manufacturing date cannot be after expiry date.")
    existing = BatchLot.objects.filter(company=company, product=product, batch_no=number).first()
    if existing:
        if expiry_date and existing.expiry_date and existing.expiry_date != expiry_date:
            raise BusinessRuleError(
                f"Batch '{number}' already exists with expiry {existing.expiry_date.isoformat()}."
            )
        updates = []
        if expiry_date and existing.expiry_date is None:
            existing.expiry_date = expiry_date
            updates.append("expiry_date")
        if manufacturing_date and existing.manufacturing_date is None:
            existing.manufacturing_date = manufacturing_date
            updates.append("manufacturing_date")
        if updates:
            existing.save(update_fields=updates)
        return existing
    return BatchLot.objects.create(
        company=company,
        product=product,
        batch_no=number,
        expiry_date=expiry_date,
        manufacturing_date=manufacturing_date,
        created_by=user,
        updated_by=user,
    )


def validate_opening_as_of(company, as_of: date | None, expiry_date: date | None = None) -> date:
    today = business_date(company)
    as_of = as_of or today
    if as_of > today:
        raise BusinessRuleError("Opening as-of date cannot be in the future.")
    floor = fy_floor(company, today)
    if as_of < floor:
        raise BusinessRuleError(
            f"Opening as-of date cannot be before the books window starting {floor.isoformat()}."
        )
    if expiry_date and expiry_date < as_of:
        raise BusinessRuleError(
            f"Expiry {expiry_date.isoformat()} cannot be before as-of {as_of.isoformat()}."
        )
    from reporting.gst_periods import assert_period_allows_money_amend

    assert_period_allows_money_amend(company, as_of)
    return as_of


def assert_can_deactivate_warehouse(warehouse):
    if warehouse.is_default:
        raise BusinessRuleError("The default godown cannot be deactivated.")
    stocked = StockBalance.objects.filter(warehouse=warehouse).filter(
        Q(on_hand__gt=0) | Q(reserved__gt=0)
    ).exists()
    if stocked:
        raise BusinessRuleError("Transfer or write off remaining stock before deactivating this godown.")


def assert_can_delete_warehouse(warehouse):
    if warehouse.is_default:
        raise BusinessRuleError("The default godown cannot be deleted.")
    if StockMovement.objects.filter(warehouse=warehouse).exists():
        raise BusinessRuleError("This godown has stock history and cannot be deleted.")


def remaining_qty(company, product, warehouse=None, batch=None, *, unbatched_only=False) -> Decimal:
    qs = StockBalance.objects.filter(company=company, product=product)
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    if batch is not None:
        qs = qs.filter(batch=batch)
    elif unbatched_only:
        qs = qs.filter(batch__isnull=True)
    return qs.aggregate(qty=Sum("on_hand"))["qty"] or Decimal("0")


def expiry_horizon_rows(company, days: int = 30, warehouse_id=None):
    today = business_date(company)
    horizon = today + timedelta(days=max(0, int(days)))
    qs = StockBalance.objects.filter(
        company=company,
        on_hand__gt=0,
        batch__isnull=False,
        batch__expiry_date__isnull=False,
        batch__expiry_date__lte=horizon,
    ).select_related("product", "batch", "warehouse")
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    rows = []
    for balance in qs:
        expiry = balance.batch.expiry_date
        rows.append(
            {
                "id": balance.batch_id,
                "product": balance.product_id,
                "product_name": balance.product.name,
                "batch": balance.batch_id,
                "batch_no": balance.batch.batch_no,
                "expiry_date": expiry,
                "manufacturing_date": balance.batch.manufacturing_date,
                "warehouse": balance.warehouse_id,
                "warehouse_name": balance.warehouse.name,
                "on_hand": str(balance.on_hand),
                "days_to_expiry": (expiry - today).days,
                "expired": expiry < today,
            }
        )
    rows.sort(key=lambda row: (row["expiry_date"], row["batch_no"], row["id"]))
    return rows


def record_expiry_bands(company, rows, bands=(7, 30, 60, 90)):
    """Persist first-seen horizon bands (once per lot × godown × band) and email once."""
    from core.models import Notification
    from core.services.notifications import NotificationService

    from .models import ExpiryAlertLog

    pending: list[tuple[dict, int]] = []
    for row in rows:
        days = int(row["days_to_expiry"])
        covering = [band for band in bands if days <= band] if days >= 0 else []
        to_log = [0] if days < 0 else ([min(covering)] if covering else [])
        for band in to_log:
            pending.append((row, band))
    if not pending:
        return

    existing = set(
        ExpiryAlertLog.objects.filter(
            company=company,
            batch_id__in={row["batch"] for row, _ in pending},
            warehouse_id__in={row["warehouse"] for row, _ in pending},
        ).values_list("batch_id", "warehouse_id", "band_days")
    )
    new_logs = []
    new_meta = []
    seen = set(existing)
    for row, band in pending:
        key = (row["batch"], row["warehouse"], band)
        if key in seen:
            continue
        seen.add(key)
        new_logs.append(
            ExpiryAlertLog(
                company=company,
                batch_id=row["batch"],
                warehouse_id=row["warehouse"],
                band_days=band,
            )
        )
        new_meta.append((row, band))
    if new_logs:
        ExpiryAlertLog.objects.bulk_create(new_logs, ignore_conflicts=True)

    email = (getattr(company, "email", None) or "").strip()
    if not email:
        return
    for row, band in new_meta:
        horizon = "expired" if band == 0 else f"within {band} days"
        try:
            NotificationService.send(
                company=company,
                channel=Notification.Channel.EMAIL,
                recipient=email,
                subject=f"Expiry alert: {row['product_name']} ({horizon})",
                body=(
                    f"Lot {row['batch_no']} of {row['product_name']} "
                    f"at godown {row['warehouse_name']} expires on {row['expiry_date']} "
                    f"({row['on_hand']} on hand)."
                ),
            )
        except Exception:
            logger.exception(
                "Expiry alert email failed for batch %s band %s",
                row["batch"], band,
            )


# Names used by views (kept as aliases so call sites cannot drift again).
assert_warehouse_can_deactivate = assert_can_deactivate_warehouse
assert_warehouse_can_delete = assert_can_delete_warehouse
expiry_window_rows = expiry_horizon_rows

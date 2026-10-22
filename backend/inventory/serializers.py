from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.exceptions import StockCountLineChanged
from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Product

from .models import (
    BatchLot, SerialNumber, StockBalance, StockCountLine, StockCountSession,
    StockMovement, StockTransfer, StockTransferLine, Warehouse, WarehouseReorderLevel,
)


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_name", "movement_type", "quantity",
            "warehouse", "batch", "unit_cost", "reference_type", "reference_id", "reason", "reason_code",
            "created_by", "created_at",
        ]


class StockLedgerSerializer(serializers.ModelSerializer):
    """One line of the item ledger (INV-WP-13): what moved, where, why, and what it left behind."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, default=None)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    unit_cost = serializers.SerializerMethodField()
    running_balance = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id", "movement_date", "product", "product_name", "sku", "warehouse", "warehouse_name",
            "batch", "batch_no", "movement_type", "movement_type_label", "quantity", "running_balance",
            "unit_cost", "reason", "reason_code", "reference_type", "reference_id", "created_by_name", "created_at",
        ]

    def get_created_by_name(self, obj):
        user = getattr(obj, "created_by", None)
        if user is None:
            return ""
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()

    def get_unit_cost(self, obj):
        # What an item cost is not for everyone who may look at stock (a sales-only user sees
        # quantities, not margins).
        if not self.context.get("show_cost"):
            return None
        return obj.unit_cost

    def get_running_balance(self, obj):
        value = getattr(obj, "_running", None)
        if value is None:
            return None
        return value + self.context.get("opening", 0)


class StockBalanceSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    rack_code = serializers.CharField(source="product.rack_code", read_only=True, default="")
    custom_fields = serializers.JSONField(source="product.custom_fields", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)
    nearest_expiry = serializers.DateField(source="batch.expiry_date", read_only=True, default=None)
    reorder_level = serializers.SerializerMethodField()
    available = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    # INV-WP-03: only the low-stock alert rows carry this. True = this godown's own reorder rule;
    # False = company-wide total (the `warehouse` on such a row is just one godown that holds the item).
    is_warehouse_specific = serializers.SerializerMethodField()
    # INV-WP-08: also alert rows only. has_reorder_rule separates "low" (a rule, at or below it) from
    # "out of stock" (no rule, nothing left); stock_status is OUT when nothing is available at all.
    has_reorder_rule = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = StockBalance
        fields = [
            "id", "warehouse", "warehouse_name", "batch", "batch_no", "nearest_expiry",
            "product", "product_name", "sku", "rack_code", "custom_fields", "on_hand", "reserved", "available", "reorder_level",
            "is_warehouse_specific", "has_reorder_rule", "stock_status",
        ]

    def get_is_warehouse_specific(self, obj):
        return getattr(obj, "is_warehouse_specific", None)

    def get_has_reorder_rule(self, obj):
        return getattr(obj, "has_reorder_rule", None)

    def get_stock_status(self, obj):
        return getattr(obj, "stock_status", None)

    def get_reorder_level(self, obj):
        value = getattr(obj, "_reorder", None)
        if value is None:
            value = obj.product.reorder_level
        return value


    def to_representation(self, instance):
        from masters.custom_fields import defs_for_company, surface_values

        data = super().to_representation(instance)
        product = getattr(instance, "product", None)
        defs = getattr(self, "_cached_cf_defs", None)
        if defs is None:
            request = self.context.get("request")
            if request:
                try:
                    defs = defs_for_company(get_company_user(request).company)
                except Exception:
                    defs = []
            self._cached_cf_defs = defs
        data["custom_fields"] = surface_values(
            getattr(product, "custom_fields", None) if product else {},
            defs,
        )
        return data


ADJUSTMENT_REASON_CODES = (
    "DAMAGED", "COUNT_DIFFERENCE", "THEFT_LOSS", "OPENING_CORRECTION", "FOUND", "OTHER",
)


class AdjustmentSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField(max_length=255)
    reason_code = serializers.ChoiceField(choices=ADJUSTMENT_REASON_CODES, required=False, allow_blank=True, default="")
    warehouse = serializers.IntegerField(required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)
    batch_no = serializers.CharField(required=False, allow_blank=True, default="")
    date = serializers.DateField(required=False, allow_null=True)

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity cannot be zero.")
        return value


class OpeningStockSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0"), required=False)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    warehouse = serializers.IntegerField(required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)
    batch_no = serializers.CharField(required=False, allow_blank=True, default="")
    expiry_date = serializers.DateField(required=False, allow_null=True)
    manufacturing_date = serializers.DateField(required=False, allow_null=True)
    serial_numbers = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    as_of = serializers.DateField(required=False, allow_null=True)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id", "name", "code", "address", "contact_name", "contact_phone",
            "is_default", "is_active", "is_system", "kind", "job_worker", "created_at", "updated_at",
        ]
        # A job-worker godown is made by the job-work flow (MFG-24), never by hand.
        read_only_fields = ["is_system", "job_worker"]

    def validate_kind(self, value):
        if value == Warehouse.Kind.JOB_WORKER:
            raise serializers.ValidationError("A godown at a job worker is created from the job work screen.")
        return value

    def _company(self):
        if self.instance is not None:
            return self.instance.company
        request = self.context.get("request")
        return get_company_user(request).company if request else None

    def validate_name(self, value):
        value = (value or "").strip()
        company = self._company()
        if company is not None:
            clash = Warehouse.objects.filter(company=company, name__iexact=value, is_system=False)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("You already have a godown with this name.")
        return value

    def validate_code(self, value):
        value = (value or "").strip()
        company = self._company()
        if company is not None:
            clash = Warehouse.objects.filter(company=company, code__iexact=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("You already have a godown with this code.")
        return value

    def validate(self, attrs):
        # A godown that is switched off cannot be the one new stock lands in by default.
        instance = self.instance
        active = attrs.get("is_active", instance.is_active if instance is not None else True)
        default = attrs.get("is_default", instance.is_default if instance is not None else False)
        if default and not active:
            raise serializers.ValidationError("A godown that is switched off cannot be the default.")
        return attrs

    def _clear_other_defaults(self, company, exclude_pk=None):
        qs = Warehouse.objects.filter(company=company, is_default=True)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        qs.update(is_default=False)

    def create(self, validated_data):
        from django.db import transaction
        from django.db.utils import IntegrityError

        from core.exceptions import BusinessRuleError

        company = validated_data.get("company")
        try:
            with transaction.atomic():
                if validated_data.get("is_default") and company is not None:
                    self._clear_other_defaults(company)
                return super().create(validated_data)
        except IntegrityError as exc:
            raise BusinessRuleError(
                "Could not set default warehouse — another default may already exist. Retry."
            ) from exc

    def update(self, instance, validated_data):
        from django.db import transaction
        from django.db.utils import IntegrityError

        from core.exceptions import BusinessRuleError

        try:
            with transaction.atomic():
                if validated_data.get("is_default"):
                    self._clear_other_defaults(instance.company, exclude_pk=instance.pk)
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise BusinessRuleError(
                "Could not set default warehouse — another default may already exist. Retry."
            ) from exc


class BatchLotSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = BatchLot
        fields = ["id", "product", "product_name", "batch_no", "expiry_date", "manufacturing_date", "created_at"]


class StockTransferLineSerializer(serializers.ModelSerializer):
    # INV-WP-05: the list used to show a transfer with no hint of what was on it.
    product_name = serializers.CharField(source="product.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)

    class Meta:
        model = StockTransferLine
        fields = [
            "id", "product", "product_name", "batch", "batch_no", "quantity", "serial_numbers",
            "shortage_qty", "shortage_reason", "shortage_resolution",
        ]
        read_only_fields = ["shortage_qty", "shortage_reason", "shortage_resolution"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate(self, attrs):
        # B8-016: surface the batch/serial requirement at draft time instead of
        # only when `complete` fails deep in post_movement.
        product = attrs.get("product") or getattr(self.instance, "product", None)
        if product is not None:
            if getattr(product, "track_batch", False) and not (
                attrs.get("batch") or getattr(self.instance, "batch", None)
            ):
                raise serializers.ValidationError(
                    {"batch": "A batch is required for a batch-tracked product."}
                )
            if getattr(product, "track_serial", False):
                serials = attrs.get("serial_numbers")
                if serials is None and self.instance is not None:
                    serials = self.instance.serial_numbers
                qty = attrs.get("quantity")
                if qty is None and self.instance is not None:
                    qty = self.instance.quantity
                if qty is not None and len(serials or []) != int(qty):
                    raise serializers.ValidationError(
                        {"serial_numbers": "Serial count must equal the transfer quantity."}
                    )
        return attrs


class StockTransferSerializer(serializers.ModelSerializer):
    lines = StockTransferLineSerializer(many=True)
    # UXW2B-016: from_warehouse/to_warehouse are plain FK ids — the transfers list
    # showed raw numeric ids in the From/To columns with nothing to resolve them to
    # names. Same join-a-display-name pattern already used for product_name above.
    from_warehouse_name = serializers.CharField(source="from_warehouse.name", read_only=True, default=None)
    to_warehouse_name = serializers.CharField(source="to_warehouse.name", read_only=True, default=None)

    class Meta:
        model = StockTransfer
        fields = [
            "id", "number", "from_warehouse", "from_warehouse_name",
            "to_warehouse", "to_warehouse_name", "status", "transfer_date", "notes",
            "lines", "dispatched_at", "completed_at", "cancelled_at", "created_at", "updated_at",
        ]
        read_only_fields = ["number", "status", "dispatched_at", "completed_at", "cancelled_at"]

    def create(self, validated_data):
        from django.db import transaction

        request = self.context.get("request")
        company = getattr(request, "company", None) or (
            get_company_user(request).company if request else None
        )
        if company is None:
            raise serializers.ValidationError("Company context required.")
        from_wh = validated_data.get("from_warehouse")
        to_wh = validated_data.get("to_warehouse")
        if from_wh and from_wh.company_id != company.id:
            raise serializers.ValidationError({"from_warehouse": "Invalid warehouse."})
        if to_wh and to_wh.company_id != company.id:
            raise serializers.ValidationError({"to_warehouse": "Invalid warehouse."})
        if from_wh and to_wh and from_wh.id == to_wh.id:
            raise serializers.ValidationError({"to_warehouse": "Source and destination must differ."})
        if getattr(from_wh, "is_system", False) or getattr(to_wh, "is_system", False):
            raise serializers.ValidationError({"to_warehouse": "The in-transit godown is not a place to move stock to or from."})
        lines = validated_data.pop("lines")
        for line in lines:
            product = line.get("product")
            batch = line.get("batch")
            if product and product.company_id != company.id:
                raise serializers.ValidationError({"lines": "Invalid product."})
            if batch and (batch.company_id != company.id or (product and batch.product_id != product.id)):
                raise serializers.ValidationError({"lines": "Invalid batch."})
        # B8-002: validation above is already complete before any write, but
        # wrap the writes themselves too — with ATOMIC_REQUESTS off, a
        # DB-level failure partway through (e.g. bulk_create hitting a
        # constraint the checks above didn't catch) would otherwise leave a
        # transfer with no lines committed.
        with transaction.atomic():
            transfer = super().create(validated_data)
            if not transfer.number:
                from core.services.document_numbers import DocumentNumberService
                transfer.number = DocumentNumberService.next_number(company, "STOCK_TRANSFER")
                transfer.save(update_fields=["number"])
            StockTransferLine.objects.bulk_create([
                StockTransferLine(transfer=transfer, company_id=company.id, **line) for line in lines
            ])
        return transfer

    def update(self, instance, validated_data):
        from django.db import transaction

        if instance.status != StockTransfer.Status.DRAFT:
            raise serializers.ValidationError("Only draft transfers can be edited.")
        lines = validated_data.pop("lines", None)
        company = instance.company
        from_wh = validated_data.get("from_warehouse", instance.from_warehouse)
        to_wh = validated_data.get("to_warehouse", instance.to_warehouse)
        if from_wh and from_wh.company_id != company.id:
            raise serializers.ValidationError({"from_warehouse": "Invalid warehouse."})
        if to_wh and to_wh.company_id != company.id:
            raise serializers.ValidationError({"to_warehouse": "Invalid warehouse."})
        if from_wh and to_wh and from_wh.id == to_wh.id:
            raise serializers.ValidationError({"to_warehouse": "Source and destination must differ."})
        # B8-002: validate every line before instance.lines.all().delete()
        # below runs, and wrap update+delete+bulk_create in one transaction
        # so a validation failure (or a DB-level one) can't leave the
        # transfer's header updated with its lines deleted.
        if lines is not None:
            for line in lines:
                product = line.get("product")
                batch = line.get("batch")
                if product and product.company_id != company.id:
                    raise serializers.ValidationError({"lines": "Invalid product."})
                if batch and (batch.company_id != company.id or (product and batch.product_id != product.id)):
                    raise serializers.ValidationError({"lines": "Invalid batch."})
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if lines is not None:
                instance.lines.all().delete()
                StockTransferLine.objects.bulk_create([
                    StockTransferLine(transfer=instance, company_id=company.id, **line) for line in lines
                ])
        return instance


class SerialNumberSerializer(serializers.ModelSerializer):
    # UXW2B-017: product/warehouse were plain FK ids with nothing to resolve them to
    # names — the list showed raw product ids and a blank Warehouse column even when
    # a warehouse was actually set. Same join-a-display-name pattern as elsewhere.
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, default=None)
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = SerialNumber
        fields = [
            "id", "product", "product_name", "warehouse", "warehouse_name",
            "serial_number", "status", "created_at", "updated_at",
        ]


class WarehouseReorderLevelSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    warehouse = CompanyPrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = WarehouseReorderLevel
        fields = ["id", "warehouse", "warehouse_name", "product", "product_name", "reorder_level"]


class StockCountLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    product_name = serializers.CharField(source="product.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_barcode = serializers.CharField(source="product.barcode", read_only=True, default="")
    variance = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    # Review aids: what the difference is worth (at purchase price) and whether it is big enough
    # that the counter should look at it again before it is posted.
    variance_value_estimate = serializers.SerializerMethodField()
    needs_recheck = serializers.SerializerMethodField()
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), required=False)
    batch = CompanyPrimaryKeyRelatedField(
        queryset=BatchLot.objects.all(), required=False, allow_null=True,
    )
    # INV-IDR-04: send back the version you loaded; a line saved by someone else meanwhile is refused.
    version = serializers.IntegerField(required=False, min_value=0)
    filled_from_system = serializers.BooleanField(required=False)

    class Meta:
        model = StockCountLine
        fields = [
            "id", "product", "product_name", "product_sku", "product_barcode", "batch", "batch_no",
            "system_qty", "counted_qty", "variance", "held_for_review",
            "skipped", "drift_skipped", "variance_value_estimate", "needs_recheck",
            "version", "counted_at", "snapshot_at", "filled_from_system",
        ]
        extra_kwargs = {
            "counted_at": {"read_only": True},
            "snapshot_at": {"read_only": True},
            "product": {"required": False},
            "batch": {"required": False, "allow_null": True},
            "system_qty": {"read_only": True},
            "held_for_review": {"read_only": True},
            "drift_skipped": {"read_only": True},
            "skipped": {"required": False},
        }

    def get_variance_value_estimate(self, obj):
        variance = obj.variance
        if variance is None or obj.skipped:
            return None
        price = Decimal(str(getattr(obj.product, "purchase_price", 0) or 0))
        return str((variance * price).quantize(Decimal("0.01")))

    def get_needs_recheck(self, obj):
        from .stock_loss import count_line_needs_recheck

        return count_line_needs_recheck(obj)


def refresh_count_status(session):
    """COUNTED once every line is counted or deliberately skipped; back to DRAFT if that stops being true."""
    if session.status not in (StockCountSession.Status.DRAFT, StockCountSession.Status.COUNTED):
        return
    open_lines = session.lines.filter(counted_qty__isnull=True, skipped=False).exists()
    wanted = StockCountSession.Status.DRAFT if open_lines else StockCountSession.Status.COUNTED
    if session.lines.exists() and wanted != session.status:
        session.status = wanted
        session.save(update_fields=["status"])


def _assert_count_line_tenant(session, product, batch):
    if product is not None and product.company_id != session.company_id:
        raise serializers.ValidationError({"lines": "Invalid product."})
    if batch is not None and (
        batch.company_id != session.company_id or (product and batch.product_id != product.id)
    ):
        raise serializers.ValidationError({"lines": "Invalid batch."})


def _count_line_system_qty(session, product, batch):
    from .item_stock import remaining_qty

    return remaining_qty(
        session.company, product, warehouse=session.warehouse, batch=batch, unbatched_only=batch is None,
    )


def _make_count_line(session, line, *, keep_system_qty=None, keep_snapshot_at=None):
    product = line["product"]
    batch = line.get("batch")
    _assert_count_line_tenant(session, product, batch)
    # B8-011: on an edit-and-replace, keep the system_qty that was snapshotted
    # when the session was created — recomputing it live rebaselines the count
    # and defeats the variance / conflict check. Only a genuinely new
    # (product, batch) gets a fresh snapshot.
    key = (getattr(product, "pk", product), getattr(batch, "pk", batch))
    if keep_system_qty is not None and key in keep_system_qty:
        system_qty = keep_system_qty[key]
        snapshot_at = (keep_snapshot_at or {}).get(key) or timezone.now()
    else:
        system_qty = _count_line_system_qty(session, product, batch)
        snapshot_at = timezone.now()
    counted_qty = line.get("counted_qty")
    return StockCountLine(
        session=session,
        company=session.company,
        product=product,
        batch=batch,
        system_qty=system_qty,
        counted_qty=counted_qty,
        snapshot_at=snapshot_at,
        counted_at=timezone.now() if counted_qty is not None else None,
    )


class StockCountSessionSerializer(serializers.ModelSerializer):
    lines = StockCountLineSerializer(many=True, required=False)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StockCountSession
        fields = [
            "id", "warehouse", "warehouse_name", "status", "blind", "counted_on", "notes",
            "posted_at", "lines", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "posted_at"]

    def validate_warehouse(self, value):
        if getattr(value, "is_system", False):
            raise serializers.ValidationError("The in-transit godown cannot be counted.")
        if getattr(value, "kind", "NORMAL") == Warehouse.Kind.JOB_WORKER:
            raise serializers.ValidationError("Stock at a job worker is counted from the job work screen.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(instance, "blind", False) and not self.context.get("reveal_count"):
            for line in data.get("lines") or []:
                line.pop("system_qty", None)
                line.pop("variance", None)
                line.pop("expected_qty", None)
                line.pop("variance_value_estimate", None)
                line.pop("needs_recheck", None)
        return data

    def create(self, validated_data):
        from core.exceptions import BusinessRuleError

        lines = validated_data.pop("lines", None)
        # INV-IDR-04: one open count per godown. A second would count the same shelves against the same
        # lines and the later post would undo the earlier one.
        company = validated_data.get("company")
        warehouse_in = validated_data.get("warehouse")
        if company is not None and warehouse_in is not None:
            open_one = StockCountSession.objects.filter(
                company=company, warehouse=warehouse_in,
                status__in=[StockCountSession.Status.DRAFT, StockCountSession.Status.COUNTED],
            ).first()
            if open_one is not None:
                raise BusinessRuleError(
                    f"A count is already open for {warehouse_in.name} (#{open_one.pk}). Post or cancel it first.",
                    code="count_already_open",
                    extra={"session_id": open_one.pk},
                )
        session = super().create(validated_data)
        warehouse = session.warehouse
        if not lines:
            # Items with a negative balance are on the sheet too, so a count can put them right.
            balances = StockBalance.objects.filter(
                company=session.company, warehouse=warehouse,
            ).exclude(on_hand=0).select_related("product", "batch")
            taken_at = timezone.now()
            StockCountLine.objects.bulk_create([
                StockCountLine(
                    session=session,
                    company=session.company,
                    product=b.product,
                    batch=b.batch,
                    system_qty=b.on_hand,
                    snapshot_at=taken_at,
                )
                for b in balances
            ])
        else:
            StockCountLine.objects.bulk_create([
                _make_count_line(session, line) for line in lines
            ])
        return session

    def update(self, instance, validated_data):
        from django.db import transaction

        from core.exceptions import BusinessRuleError

        lines = validated_data.pop("lines", None)
        # B8-002: the status check and the tenant-check inside
        # _make_count_line (via _assert_count_line_tenant) both used to run
        # *after* super().update() had already committed the header change
        # (status check) or after instance.lines.all().delete() had already
        # run (tenant check) — a rejected edit still landed a header change,
        # or emptied the session's lines, before returning its 400.
        if lines is not None and instance.status not in (
            StockCountSession.Status.DRAFT,
            StockCountSession.Status.COUNTED,
        ):
            raise BusinessRuleError("Only a draft or counted session can be edited.")
        if lines is not None and len(lines) == 0:
            # An empty list means "no line changed", not "remove every line".
            lines = None
        if lines is not None:
            for line in lines:
                _assert_count_line_tenant(instance, line.get("product"), line.get("batch"))
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if lines is None:
                return instance
            existing = {
                row.id: row for row in instance.lines.select_related("product").select_for_update().order_by("id")
            }
            ids = [line.get("id") for line in lines]
            if ids and all(i in existing for i in ids):
                # INV-IDR-04: a counter who loaded an older version of a line must not overwrite what
                # another counter saved since. Clients that send no version are not checked.
                stale = [
                    {
                        "line_id": existing[line["id"]].pk,
                        "product_name": existing[line["id"]].product.name,
                        "counted_qty": (
                            None if existing[line["id"]].counted_qty is None else str(existing[line["id"]].counted_qty)
                        ),
                        "skipped": existing[line["id"]].skipped,
                        "version": existing[line["id"]].version,
                    }
                    for line in lines
                    if line.get("version") is not None and line["version"] != existing[line["id"]].version
                ]
                if stale:
                    raise StockCountLineChanged(stale)
                for line in lines:
                    row = existing[line["id"]]
                    fields = []
                    if "counted_qty" in line and line["counted_qty"] != row.counted_qty:
                        row.counted_qty = line["counted_qty"]
                        row.counted_at = timezone.now() if line["counted_qty"] is not None else None
                        row.filled_from_system = bool(line.get("filled_from_system", False))
                        fields += ["counted_qty", "counted_at", "filled_from_system"]
                    elif "filled_from_system" in line and bool(line["filled_from_system"]) != row.filled_from_system:
                        row.filled_from_system = bool(line["filled_from_system"])
                        fields.append("filled_from_system")
                    if "skipped" in line and bool(line["skipped"]) != row.skipped:
                        row.skipped = bool(line["skipped"])
                        fields.append("skipped")
                    if fields:
                        row.version += 1
                        row.save(update_fields=[*fields, "version"])
                refresh_count_status(instance)
                return instance
            prior_system_qty = {
                (row.product_id, row.batch_id): row.system_qty
                for row in instance.lines.all()
            }
            prior_snapshot_at = {
                (row.product_id, row.batch_id): row.snapshot_at
                for row in instance.lines.all()
            }
            instance.lines.all().delete()
            created_lines = StockCountLine.objects.bulk_create([
                _make_count_line(
                    instance, line, keep_system_qty=prior_system_qty, keep_snapshot_at=prior_snapshot_at,
                )
                for line in lines
            ])
            if created_lines and not any(line.counted_qty is None for line in created_lines):
                instance.status = StockCountSession.Status.COUNTED
                instance.save(update_fields=["status"])
        return instance

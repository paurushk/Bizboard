import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import (
    CanCreatePurchases,
    CanCreateSales,
    CanExport,
    CanManageInventory,
    CanViewFinancialReports,
    CanViewMastersCatalog,
    HasCompany,
    IsOwner,
    get_company_user,
)
from core.services.gstin_verify import apply_verification, get_gstin_provider
from core.throttles import CompanyRateThrottle, UserScopeRateThrottle
from core.viewsets import CompanyScopedViewSet

from .models import Brand, Category, Customer, ExpenseCategory, PaymentMode, PriceList, Product, Supplier, TaxRate, Unit
def _soft_destroy(instance, user):
    from django.utils import timezone

    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.updated_by = user
    instance.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])


from .serializers import (
    BrandSerializer,
    CategorySerializer,
    CustomerSerializer,
    ExpenseCategorySerializer,
    PaymentModeSerializer,
    ProductSerializer,
    PriceListSerializer,
    SupplierSerializer,
    TaxRateSerializer,
    UnitSerializer,
)

# BB-000195: short TTL list cache for hot masters reads.
_MASTERS_LIST_TTL = 60

# BB-000297/Wave 12B: masters mutation is Owner-only; list/retrieve stay HasCompany.
_MUTATE_ACTIONS = ("create", "update", "partial_update", "destroy")


class _CachedMastersListMixin:
    list_cache_kind = ""

    def _bust_list_cache(self):
        kind = getattr(self, "list_cache_kind", "") or ""
        if kind:
            cache.delete(f"masters:{kind}:{self.company.pk}")

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._bust_list_cache()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._bust_list_cache()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self._bust_list_cache()


def _barcode_svg(code: str) -> str:
    try:
        from reportlab.graphics.barcode import createBarcodeDrawing
        from reportlab.graphics import renderSVG

        drawing = createBarcodeDrawing("Code128", value=code, barHeight=50, humanReadable=True)
        return renderSVG.drawToString(drawing)
    except Exception as exc:
        raise BusinessRuleError("Could not render barcode image.") from exc


class CategoryViewSet(CompanyScopedViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class BrandViewSet(CompanyScopedViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class UnitViewSet(_CachedMastersListMixin, CompanyScopedViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    list_cache_kind = "units"

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def list(self, request, *args, **kwargs):
        key = f"masters:units:{self.company.pk}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, _MASTERS_LIST_TTL)
        return response


class TaxRateViewSet(_CachedMastersListMixin, CompanyScopedViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    list_cache_kind = "tax_rates"

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def list(self, request, *args, **kwargs):
        key = f"masters:tax_rates:{self.company.pk}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, _MASTERS_LIST_TTL)
        return response


class PaymentModeViewSet(CompanyScopedViewSet):
    queryset = PaymentMode.objects.all()
    serializer_class = PaymentModeSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class ExpenseCategoryViewSet(CompanyScopedViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


logger = logging.getLogger("masters.customers")


def _count(event: str) -> None:
    """Bump a Prometheus business-event counter (``/metrics``); never breaks the request."""
    try:
        from core.ops_metrics import bump_event

        bump_event(event)
    except Exception:  # noqa: BLE001
        logger.debug("ops_metrics.bump_failed event=%s", event)


class StaleWrite(APIException):
    """409: the row changed since the client read it. The client reloads the customer and tries again."""

    status_code = 409
    default_detail = "This customer was changed by someone else. Reload it and try again."
    default_code = "stale_write"


def _parse_version(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# Fields whose before/after values go on the customer's UPDATE audit row (CUS-24).
_CUSTOMER_TRACKED_FIELDS = (
    "name", "gstin", "state", "status", "credit_limit", "credit_days", "taxpayer_type",
    "phone", "email", "pan",
)
CUSTOMER_EXPORT_MAX_ROWS = 20000
BULK_VERIFY_MAX = 10  # x 3 calls/hour per user = the 30/hour company budget
CREDIT_TERMS_EVENT = "customer.credit_terms"


_MASKED_AUDIT_FIELDS = ("phone", "email", "pan")


def _mask_audit_value(field: str, value: str) -> str:
    """Audit trail keeps what changed, not the personal data itself (phone, email, PAN)."""
    if not value:
        return ""
    if field == "email":
        name, _, domain = value.partition("@")
        return f"{name[:1]}***@{domain}" if domain else "***"
    return "*" * max(len(value) - 4, 0) + value[-4:]


def _customer_snapshot(row):
    return {f: str(getattr(row, f, "") if getattr(row, f, "") is not None else "") for f in _CUSTOMER_TRACKED_FIELDS}


def _raise_if_gstin_clash(exc, company, gstin):
    """Two requests set the same GSTIN at once and the database constraint won: say who holds it."""
    from django.db import IntegrityError

    text = str(exc)
    # PostgreSQL names the constraint; SQLite names the columns.
    named = "uniq_customer_gstin_per_company" in text or ("masters_customer" in text and "gstin" in text)
    if isinstance(exc, IntegrityError) and named and gstin:
        other = Customer.objects.filter(company=company, gstin=gstin).only("name").first()
        who = f" to customer '{other.name}'" if other else ""
        raise ValidationError({"gstin": f"GSTIN {gstin} is already registered{who}."}) from exc


def _verification_notice(result) -> str:
    """Why a lookup did not end in a live-verified GSTIN (empty when it did)."""
    raw = result.raw or {}
    if result.status == "INVALID":
        return "The GSTIN format is not valid."
    if raw.get("error") == "provider_unavailable":
        return "The GSTIN verification service could not be reached. Try again in a few minutes."
    if raw.get("provider") == "null" or result.status == "UNVERIFIED":
        return "Live GSTIN verification is not configured, so only the format was checked."
    return ""


class CanArchiveCustomer(BasePermission):
    """Archiving or deleting a customer is an owner/manager call (founder decision 2026-10-11)."""

    message = "Only an owner or manager can archive or delete a customer."

    def has_permission(self, request, view):
        member = get_company_user(request)
        return member is not None and member.role in ("OWNER", "MANAGER")


_CUSTOMER_FILTER_PARAMS = [
    OpenApiParameter("q", str, description="Search name, phone, email or GSTIN (first 100 characters)."),
    OpenApiParameter("status", str, enum=["ACTIVE", "BLOCKED", "INACTIVE"], description="Customer status."),
]


class CustomerViewSet(CompanyScopedViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = self.get_serializer(instance).data
        # Quick Entry warns before booking for a customer on collection hold. The status only
        # matters (it only blocks Complete) when the company turned the auto hold on, so skip the
        # risk query otherwise.
        company = self.company
        if getattr(company, "auto_credit_hold_on_severe_overdue", False):
            from payments.dunning import customer_risk_snapshot

            try:
                data["collection_status"] = customer_risk_snapshot(company, instance).get("collection_status", "")
            except Exception:  # noqa: BLE001 — an advisory field must never break the customer page
                logger.exception("customer collection status failed for customer %s", instance.pk)
                data["collection_status"] = ""
        return Response(data)

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "destroy":
            return [IsAuthenticated(), HasCompany(), CanCreateSales(), CanArchiveCustomer()]
        if action in (*_MUTATE_ACTIONS, "pos_walk_in", "verify_gstin", "verify_gstin_bulk", "lookup_gstin"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action == "set_pos_walk_in":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "export":
            return [IsAuthenticated(), HasCompany(), CanViewFinancialReports(), CanExport()]
        if action in ("summary", "history"):
            return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]
        if action == "health":
            return [IsAuthenticated(), HasCompany(), CanArchiveCustomer()]
        # BB-000422: VIEWER must not browse party masters.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def get_throttles(self):
        throttles = super().get_throttles()
        action = getattr(self, "action", None)
        if action in ("verify_gstin", "lookup_gstin"):
            throttles.append(CompanyRateThrottle("gstin_verify"))
            throttles.append(UserScopeRateThrottle("gstin_verify_user"))
        elif action == "verify_gstin_bulk":
            throttles.append(CompanyRateThrottle("gstin_verify"))
            throttles.append(UserScopeRateThrottle("gstin_verify_bulk"))
        elif action == "export":
            throttles.append(CompanyRateThrottle("customers_export"))
        elif action == "summary":
            throttles.append(CompanyRateThrottle("customers_summary"))
        return throttles

    def _filtered_queryset(self):
        """The list filters (status, q, walk-in) with no ordering: shared by list, summary and export."""
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in Customer.Status.values:
                raise ValidationError({"status": f"Invalid status. Use one of: {', '.join(Customer.Status.values)}."})
            qs = qs.filter(status=status_filter)
        q = (self.request.query_params.get("search") or self.request.query_params.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q) | Q(email__icontains=q)
            )
        if self.request.query_params.get("is_pos_walk_in") in ("1", "true", "True"):
            qs = qs.filter(is_pos_walk_in=True)
        return qs

    def _outstanding_map(self):
        """One outstanding pass per request, shared by the balance sort, the rows and the exposure."""
        if not hasattr(self, "_outstanding_cache"):
            from ledgers.services import LedgerService

            self._outstanding_cache = LedgerService.bulk_customer_outstanding(self.company)
        return self._outstanding_cache

    def _exposure_map(self):
        if not hasattr(self, "_exposure_cache"):
            from ledgers.services import LedgerService

            # Books off (or GL basis not ready) the displayed outstanding IS the document figure.
            reuse = None if LedgerService._use_gl_outstanding(self.company) else self._outstanding_map()
            self._exposure_cache = LedgerService.bulk_customer_credit_exposure(self.company, documents=reuse)
        return self._exposure_cache

    def get_queryset(self):
        qs = self._filtered_queryset()
        if getattr(self, "action", None) in ("list", "retrieve"):
            qs = qs.prefetch_related("shipping_addresses")  # one query, not one per row
        sort = (self.request.query_params.get("sort") or self.request.query_params.get("ordering") or "name").lower()
        self._balance_sort = False
        if sort in ("recent", "recently_active", "-updated_at"):
            return qs.order_by("-updated_at", "name")
        if sort in ("balance", "-balance"):
            # Ordered in paginate_queryset: one SQL CASE per customer would grow with the party list.
            self._balance_sort = True
        return qs.order_by("name")

    def paginate_queryset(self, queryset):
        if not getattr(self, "_balance_sort", False):
            return super().paginate_queryset(queryset)
        balances = self._outstanding_map()
        rows = sorted(queryset.values_list("pk", "name"), key=lambda r: (-balances.get(r[0], Decimal("0")), r[1]))
        page_ids = super().paginate_queryset([pk for pk, _name in rows])
        if page_ids is None:
            return None
        by_id = queryset.in_bulk(page_ids)
        return [by_id[pk] for pk in page_ids if pk in by_id]

    @action(detail=False, methods=["post"], url_path="pos-walk-in")
    def pos_walk_in(self, request):
        """Get or create the single walk-in party. Cashiers do not set the flag themselves."""
        from django.db import IntegrityError

        name = str(request.data.get("name") or "Walk-in").strip()[:255] or "Walk-in"
        with transaction.atomic():
            row = (
                Customer.objects.select_for_update()
                .filter(company=self.company, is_pos_walk_in=True)
                .first()
            )
            if row is not None:
                return Response(self.get_serializer(row).data)
            try:
                row = Customer.objects.create(
                    company=self.company,
                    name=name,
                    status=Customer.Status.ACTIVE,
                    is_pos_walk_in=True,
                    created_by=request.user,
                    updated_by=request.user,
                )
            except IntegrityError:
                row = Customer.objects.filter(company=self.company, is_pos_walk_in=True).first()
                if row is None:
                    raise
        return Response(self.get_serializer(row).data, status=201)

    @action(detail=False, methods=["post"], url_path="set-pos-walk-in", permission_classes=[IsAuthenticated, HasCompany, IsOwner])
    def set_pos_walk_in(self, request):
        from decimal import Decimal

        from core.services.audit import AuditService

        target_id = request.data.get("customer")
        with transaction.atomic():
            target = (
                Customer.objects.select_for_update()
                .filter(company=self.company, pk=target_id)
                .first()
            )
            if target is None:
                raise BusinessRuleError("Choose a customer in this company.")
            if (target.gstin or "").strip() or Decimal(str(target.credit_limit or 0)) > 0:
                raise BusinessRuleError(
                    "The walk-in party cannot have a GSTIN or a credit limit.",
                    code="pos_walk_in_target",
                )
            if target.status != Customer.Status.ACTIVE:
                raise BusinessRuleError("The walk-in party must be Active.", code="pos_walk_in_target")
            # Lock the current walk-in rows first so two moves cannot race on the unique flag.
            list(Customer.objects.select_for_update().filter(company=self.company, is_pos_walk_in=True))
            Customer.objects.filter(company=self.company, is_pos_walk_in=True).exclude(pk=target.pk).update(
                is_pos_walk_in=False,
            )
            if not target.is_pos_walk_in:
                target.is_pos_walk_in = True
                target.updated_by = request.user
                target.save(update_fields=["is_pos_walk_in", "updated_by", "updated_at"])
        AuditService.log(
            company=self.company,
            user=request.user,
            action="UPDATE",
            entity_type="Customer",
            entity_id=str(target.pk),
            description=f"POS walk-in party set to {target.name}",
        )
        return Response(self.get_serializer(target).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.get("partial", False)
        # PUT must carry the version it was read at. PATCH may omit it (field-level merge under
        # the row lock), but a PATCH that does send one is checked like a PUT.
        if not partial or "version" in request.data:
            instance = self.get_object()
            if _parse_version(request.data.get("version")) != instance.version:
                _count("customer_stale_write")
                logger.info("customer.stale_write company=%s customer=%s stage=precheck", self.company.pk, instance.pk)
                raise StaleWrite()
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        """Reload under a row lock and write only the fields in this request.

        A concurrent PATCH of a different field therefore keeps both edits.
        The lock is taken here, after any test barrier around perform_update.
        """
        from core.services.audit import AuditService

        from . import gstin_rules

        with transaction.atomic():
            locked = Customer.all_objects.select_for_update().get(
                pk=serializer.instance.pk, company=self.company,
            )
            if self.request.method == "PUT" or "version" in self.request.data:
                # The check in update() ran before the lock. Two writers carrying version N both pass
                # it, so compare again now that this request owns the row.
                if _parse_version(self.request.data.get("version")) != locked.version:
                    _count("customer_stale_write")
                    logger.info("customer.stale_write company=%s customer=%s stage=locked", self.company.pk, locked.pk)
                    raise StaleWrite()
            data = serializer.validated_data
            addresses = data.pop("shipping_addresses", None)
            if "gstin" in data and gstin_rules.normalise(data["gstin"]) != gstin_rules.normalise(locked.gstin):
                # A concurrent GSTIN change may have landed since validate(): reset against the locked row.
                data.update(gstin_rules.VERIFICATION_RESET)
            before = _customer_snapshot(locked)
            stored = {f.attname: getattr(locked, f.attname) for f in locked._meta.concrete_fields}
            for key, value in data.items():
                setattr(locked, key, value)
            changed_fields = [a for a, old in stored.items() if getattr(locked, a) != old]
            # Nothing changed (a form re-save): no new version, no audit row, no 409 for the next editor.
            if changed_fields or addresses is not None:
                locked.version = int(locked.version or 0) + 1
                locked.updated_by = self.request.user
                try:
                    with transaction.atomic():
                        locked.save()
                except Exception as exc:  # noqa: BLE001 - narrowed in the helper; anything else is re-raised
                    _raise_if_gstin_clash(exc, self.company, locked.gstin)
                    raise
            serializer.instance = locked
            if addresses is not None:
                serializer._replace_addresses(locked, addresses)
        after = _customer_snapshot(locked)
        changes = {
            k: {
                "from": _mask_audit_value(k, before[k]) if k in _MASKED_AUDIT_FIELDS else before[k],
                "to": _mask_audit_value(k, after[k]) if k in _MASKED_AUDIT_FIELDS else after[k],
            }
            for k in before if before[k] != after[k]
        }
        if changes:
            AuditService.log(
                company=self.company, user=self.request.user, action="UPDATE", entity_type="Customer",
                entity_id=str(locked.pk), metadata={"changes": changes},
            )
        if "credit_limit" in changes or "credit_days" in changes:
            # Searchable marker for credit-term changes; the History panel shows the main event only.
            AuditService.log(
                company=self.company, user=self.request.user, action="UPDATE", entity_type="Customer",
                entity_id=str(locked.pk), description=CREDIT_TERMS_EVENT,
                metadata={k: v for k, v in changes.items() if k in ("credit_limit", "credit_days")},
            )

    def perform_destroy(self, instance):
        _soft_destroy(instance, self.request.user)
        # a soft delete is still a delete: it must leave the same audit row a hard one did
        self._audit_raw("DELETE", str(instance.pk))

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except Exception as exc:  # noqa: BLE001 - narrowed in the helper; anything else is re-raised
            _raise_if_gstin_clash(exc, self.company, serializer.validated_data.get("gstin", ""))
            raise

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # BUG-301-style fix: one bulk aggregation for the whole list instead of
        # a per-row LedgerService.customer_outstanding query (N+1).
        if getattr(self, "action", None) == "list":
            context["outstanding_by_id"] = self._outstanding_map()
            context["credit_exposure_by_id"] = self._exposure_map()
        return context

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced customer — deactivate instead (BB-000057)."""
        customer = self.get_object()
        if customer.is_pos_walk_in:
            raise BusinessRuleError(
                "The POS walk-in party cannot be deleted or deactivated. Choose another walk-in party first.",
                code="pos_walk_in_protected",
            )
        from ledgers.services import LedgerService

        owed = LedgerService.customer_outstanding(self.company, customer)
        advance = LedgerService.customer_unallocated_receipts(self.company, customer)
        if owed != 0 or advance > 0:
            _count("customer_archive_refused")
            raise BusinessRuleError(
                f"Cannot archive '{customer.name}' while they have "
                + ("an outstanding balance" if owed != 0 else "an unallocated advance")
                + ". Settle the balance or allocate the advance first.",
                code="customer_has_balance",
            )
        if customer.is_referenced():
            with transaction.atomic():
                locked = Customer.all_objects.select_for_update().get(pk=customer.pk, company=self.company)
                locked.status = Customer.Status.INACTIVE
                locked.version = int(locked.version or 0) + 1
                locked.updated_by = request.user
                locked.save(update_fields=["status", "version", "updated_by", "updated_at"])
                # An archived customer must not keep getting invoices drafted for them.
                locked.recurring_invoice_schedules.filter(is_active=True).update(is_active=False)
            self._audit("UPDATE", locked)
            return Response(
                {"detail": "Customer is referenced by documents; marked Inactive instead of deleting."},
                status=200,
            )
        return super().destroy(request, *args, **kwargs)

    def _verify_customer(self, request, customer):
        """Look the GSTIN up (outside the lock: it is a network call), then store the outcome. Returns (row, notice)."""
        gstin = (customer.gstin or "").strip()
        if not gstin:
            raise BusinessRuleError("Customer has no GSTIN.")
        result = get_gstin_provider().lookup(gstin)
        _count("customer_gstin_verify")
        logger.info(
            "customer.gstin_verify company=%s status=%s provider=%s",
            self.company.pk, result.status, (result.raw or {}).get("provider", ""),
        )
        with transaction.atomic():
            locked = Customer.all_objects.select_for_update().get(pk=customer.pk, company=self.company)
            if (locked.gstin or "").strip() != gstin:
                raise BusinessRuleError("The GSTIN changed while it was being verified. Try again.")
            apply_verification(locked, result, user=request.user, company=locked.company)
            locked.version = int(locked.version or 0) + 1
            locked.save(update_fields=["version"])
        return locked, _verification_notice(result)

    @action(detail=True, methods=["post"], url_path="verify-gstin")
    def verify_gstin(self, request, pk=None):
        locked, notice = self._verify_customer(request, self.get_object())
        data = dict(self.get_serializer(locked).data)
        data["verification_notice"] = notice
        return Response(data)

    @extend_schema(
        request=inline_serializer("CustomerVerifyBulkRequest", {"ids": drf_serializers.ListField(child=drf_serializers.IntegerField())}),
        responses=inline_serializer("CustomerVerifyBulk", {
            "results": inline_serializer("CustomerVerifyBulkRow", {
                "id": drf_serializers.IntegerField(),
                "status": drf_serializers.CharField(),
                "notice": drf_serializers.CharField(),
                "error": drf_serializers.CharField(),
            }, many=True),
        }),
    )
    @action(detail=False, methods=["post"], url_path="verify-gstin-bulk")
    def verify_gstin_bulk(self, request):
        """Verify the GSTIN of up to 10 chosen customers in one go (its own, small budget)."""
        raw = request.data.get("ids")
        if not isinstance(raw, list) or not raw:
            raise ValidationError({"ids": "Choose at least one customer."})
        try:
            ids = list(dict.fromkeys(int(i) for i in raw))
        except (TypeError, ValueError):
            raise ValidationError({"ids": "Customer ids must be numbers."}) from None
        if len(ids) > BULK_VERIFY_MAX:
            raise ValidationError({"ids": f"Verify at most {BULK_VERIFY_MAX} customers at a time."})
        rows = {c.pk: c for c in self.get_queryset().filter(pk__in=ids)}
        results = []
        for pk in ids:
            customer = rows.get(pk)
            if customer is None:
                results.append({"id": pk, "status": "", "notice": "", "error": "Customer not found."})
                continue
            try:
                locked, notice = self._verify_customer(request, customer)
                results.append({"id": pk, "status": locked.gstin_verification_status, "notice": notice, "error": ""})
            except BusinessRuleError as exc:
                results.append({"id": pk, "status": customer.gstin_verification_status, "notice": "", "error": str(exc)})
        return Response({"results": results})

    @extend_schema(
        request=inline_serializer("CustomerGstinLookupRequest", {"gstin": drf_serializers.CharField()}),
        responses=inline_serializer("CustomerGstinLookup", {
            "gstin": drf_serializers.CharField(),
            "status": drf_serializers.CharField(),
            "legal_name": drf_serializers.CharField(),
            "state": drf_serializers.CharField(),
            "pan": drf_serializers.CharField(),
            "taxpayer_type": drf_serializers.CharField(),
            "provider": drf_serializers.CharField(),
            "notice": drf_serializers.CharField(),
            "existing_customer": inline_serializer(
                "CustomerGstinLookupExisting",
                {"id": drf_serializers.IntegerField(), "name": drf_serializers.CharField()},
                allow_null=True,
            ),
        }),
    )
    @action(detail=False, methods=["post"], url_path="lookup-gstin")
    def lookup_gstin(self, request):
        """Look a GSTIN up before the customer exists, to pre-fill the form. Writes nothing."""
        from django.core.cache import cache
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.services.audit import AuditService
        from core.validators import validate_gstin

        from . import gstin_rules

        gstin = gstin_rules.normalise(request.data.get("gstin"))
        try:
            if not gstin:
                raise DjangoValidationError("Enter a GSTIN.")
            validate_gstin(gstin)
        except DjangoValidationError as exc:
            raise ValidationError({"gstin": list(exc.messages)}) from exc
        key = f"customers:gstin-lookup:{self.company.pk}:{gstin}"
        # "refresh" is the user pressing Verify & autofill: always ask the provider. Without it a recent answer is reused.
        refresh = str(request.data.get("refresh") or "").lower() in ("1", "true", "yes")
        payload = None if refresh else cache.get(key)
        if payload is None:
            result = get_gstin_provider().lookup(gstin)
            taxpayer = str(result.taxpayer_type or "").strip().upper()
            payload = {
                "gstin": gstin,
                "status": result.status,
                "legal_name": result.legal_name,
                "state": gstin_rules.derive_state(gstin) or "",
                "pan": gstin_rules.derive_pan(gstin),
                "taxpayer_type": taxpayer if taxpayer in Customer.TaxpayerType.values else "",
                "provider": (result.raw or {}).get("provider", ""),
                "notice": _verification_notice(result),
            }
            cache.set(key, payload, 60)  # a minute: enough to absorb a double click, short enough not to hide a status change
        existing = Customer.objects.filter(company=self.company, gstin=gstin).only("id", "name").first()
        _count("customer_gstin_lookup")
        logger.info(
            "customer.gstin_lookup company=%s status=%s provider=%s", self.company.pk, payload["status"], payload["provider"],
        )
        AuditService.log(
            company=self.company, user=request.user, action="LOOKUP", entity_type="Customer",
            entity_id="gstin", description="customer.gstin_lookup",
            metadata={"gstin": gstin, "status": payload["status"], "provider": payload["provider"]},
        )
        return Response({
            **payload,
            "existing_customer": {"id": existing.id, "name": existing.name} if existing else None,
        })

    @extend_schema(
        parameters=_CUSTOMER_FILTER_PARAMS,
        responses=inline_serializer("CustomerSummary", {
            "total_count": drf_serializers.IntegerField(),
            "active_count": drf_serializers.IntegerField(),
            "blocked_count": drf_serializers.IntegerField(),
            "inactive_count": drf_serializers.IntegerField(),
            "over_credit_limit_count": drf_serializers.IntegerField(),
            "total_outstanding": drf_serializers.CharField(),
            "total_unallocated_advance": drf_serializers.CharField(),
            "net_credit_exposure": drf_serializers.CharField(),
        }),
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Portfolio figures for the customers the list filters select (not just one page)."""
        rows = list(self._filtered_queryset().values_list("pk", "status", "credit_limit"))
        outstanding = self._outstanding_map()
        exposure = self._exposure_map()
        from ledgers.services import LedgerService

        advances = LedgerService.bulk_customer_advances(self.company)
        zero = Decimal("0")
        counts = {"ACTIVE": 0, "BLOCKED": 0, "INACTIVE": 0}
        total_outstanding = total_advance = net_exposure = zero
        over_limit = 0
        for pk, status, limit in rows:
            counts[status] = counts.get(status, 0) + 1
            total_outstanding += outstanding.get(pk, zero)
            total_advance += advances.get(pk, zero)
            exp = exposure.get(pk, zero)
            net_exposure += max(zero, exp)
            if limit and Decimal(str(limit)) > 0 and exp > Decimal(str(limit)):
                over_limit += 1
        return Response({
            "total_count": len(rows),
            "active_count": counts["ACTIVE"],
            "blocked_count": counts["BLOCKED"],
            "inactive_count": counts["INACTIVE"],
            "over_credit_limit_count": over_limit,
            "total_outstanding": str(total_outstanding),
            "total_unallocated_advance": str(total_advance),
            "net_credit_exposure": str(net_exposure),
        })

    @extend_schema(parameters=_CUSTOMER_FILTER_PARAMS, responses={(200, "text/csv"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"])
    def export(self, request):
        """CSV of every customer the list filters select. Streamed; refuses an oversize export."""
        import csv

        from django.http import StreamingHttpResponse

        from core.csv_utils import csv_safe
        from core.rls import stream_with_rls
        from core.services.audit import AuditService

        qs = self._filtered_queryset()
        total = qs.count()
        if total > CUSTOMER_EXPORT_MAX_ROWS:
            raise BusinessRuleError(
                f"Too many customers to export at once (limit {CUSTOMER_EXPORT_MAX_ROWS}). Narrow the filters.",
                code="export_too_large",
            )
        sort = (request.query_params.get("sort") or request.query_params.get("ordering") or "name").lower()
        by_balance = sort in ("balance", "-balance")
        if sort in ("recent", "recently_active", "-updated_at"):
            qs = qs.order_by("-updated_at", "name", "pk")
        else:
            qs = qs.order_by("name", "pk")
        outstanding = self._outstanding_map()
        exposure = self._exposure_map()

        class _Echo:
            def write(self, value):
                return value

        writer = csv.writer(_Echo())

        def rows_in_order():
            if not by_balance:
                yield from qs.iterator(chunk_size=500)
                return
            ids = [pk for pk, _n in sorted(
                qs.values_list("pk", "name"), key=lambda r: (-outstanding.get(r[0], Decimal("0")), r[1]),
            )]
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                by_id = qs.model.objects.in_bulk(chunk)
                yield from (by_id[pk] for pk in chunk if pk in by_id)

        def lines():
            yield writer.writerow([
                "Name", "Phone", "Email", "GSTIN", "GSTIN status", "Taxpayer type", "State", "Status",
                "Credit limit", "Credit days", "Outstanding", "Credit exposure",
            ])
            for c in rows_in_order():
                yield writer.writerow([
                    csv_safe(v) for v in (
                        c.name, c.phone, c.email, c.gstin, c.gstin_verification_status, c.taxpayer_type,
                        c.state, c.status, c.credit_limit, c.credit_days,
                        outstanding.get(c.pk, Decimal("0")), exposure.get(c.pk, Decimal("0")),
                    )
                ])

        _count("customer_export")
        logger.info("customer.export company=%s rows=%s", self.company.pk, total)
        AuditService.log(
            company=self.company, user=request.user, action="EXPORT", entity_type="Customer", entity_id="list",
            metadata={"filters": dict(request.query_params.items()), "rows": total},
        )
        response = StreamingHttpResponse(
            stream_with_rls(self.company.id, lines()), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = 'attachment; filename="customers.csv"'
        return response

    @extend_schema(
        responses=inline_serializer("CustomerHealth", {
            "total": drf_serializers.IntegerField(),
            "checks": inline_serializer("CustomerHealthCheck", {
                "check": drf_serializers.CharField(),
                "label": drf_serializers.CharField(),
                "count": drf_serializers.IntegerField(),
            }, many=True),
        }),
    )
    @action(detail=False, methods=["get"])
    def health(self, request):
        """Customer records that need a look (the monthly check, on demand). Owner or manager."""
        from .audit import CHECK_LABELS, audit_customers

        key = f"customers:health:{self.company.pk}"
        payload = cache.get(key)
        if payload is None:
            findings, _companies, _fixed = audit_customers(Customer.objects.filter(company=self.company))
            counts = {check: len(rows) for (_cid, check), rows in findings.items()}
            payload = {
                "total": sum(counts.values()),
                "checks": [
                    {"check": check, "label": CHECK_LABELS.get(check, check), "count": n}
                    for check, n in sorted(counts.items())
                ],
            }
            cache.set(key, payload, 600)
        return Response(payload)

    @extend_schema(
        responses=inline_serializer("CustomerHistory", {
            "results": inline_serializer("CustomerHistoryEvent", {
                "id": drf_serializers.IntegerField(),
                "at": drf_serializers.DateTimeField(),
                "user": drf_serializers.CharField(),
                "action": drf_serializers.CharField(),
                "description": drf_serializers.CharField(),
                "changes": drf_serializers.DictField(),
            }, many=True),
        }),
    )
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Who changed this customer, and what (from the audit trail)."""
        from core.models import AuditEvent

        customer = self.get_object()
        events = (
            AuditEvent.objects.filter(company=self.company, entity_type="Customer", entity_id=str(customer.pk))
            .exclude(description=CREDIT_TERMS_EVENT)  # the main UPDATE event already lists the same change
            .select_related("user")
            .order_by("-created_at", "-id")[:200]
        )
        return Response({"results": [
            {
                "id": e.id,
                "at": e.created_at.isoformat(),
                "user": (e.user.full_name or e.user.email) if e.user else "",
                "action": e.action,
                "description": e.description,
                "changes": (e.metadata or {}).get("changes") or {
                    k: v for k, v in (e.metadata or {}).items() if k in ("credit_limit", "credit_days")
                },
            }
            for e in events
        ]})


class SupplierViewSet(CompanyScopedViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def perform_destroy(self, instance):
        from core.exceptions import BusinessRuleError

        # Hard delete used to be stopped by PROTECT foreign keys. A soft delete hides the row from
        # the alive manager, so ledgers and open bills would lose a supplier that still has a balance.
        if instance.is_referenced():
            raise BusinessRuleError(
                f"Cannot delete '{instance.name}' because purchase documents reference it. Mark it Inactive instead."
            )
        _soft_destroy(instance, self.request.user)
        # a soft delete is still a delete: it must leave the same audit row a hard one did
        self._audit_raw("DELETE", str(instance.pk))

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if getattr(self, "action", None) == "verify_gstin":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse party masters.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def get_queryset(self):
        qs = super().get_queryset()
        # F2-033: the Suppliers list filter bar sends status=ACTIVE|INACTIVE.
        status_filter = (self.request.query_params.get("status") or "").upper()
        if status_filter == "ACTIVE":
            qs = qs.filter(is_active=True)
        elif status_filter == "INACTIVE":
            qs = qs.filter(is_active=False)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, "action", None) == "list":
            from ledgers.services import LedgerService

            context["outstanding_by_id"] = LedgerService.bulk_supplier_outstanding(self.company)
        return context

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced supplier — deactivate instead (BB-000057)."""
        supplier = self.get_object()
        if supplier.is_referenced():
            supplier.is_active = False
            supplier.updated_by = request.user
            supplier.save(update_fields=["is_active", "updated_by"])
            self._audit("UPDATE", supplier)
            return Response(
                {"detail": "Supplier is referenced by documents; marked inactive instead of deleting."},
                status=200,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="verify-gstin")
    def verify_gstin(self, request, pk=None):
        supplier = self.get_object()
        if not (supplier.gstin or "").strip():
            raise BusinessRuleError("Supplier has no GSTIN.")
        result = get_gstin_provider().lookup(supplier.gstin)
        apply_verification(supplier, result, user=request.user, company=supplier.company)
        return Response(self.get_serializer(supplier).data)


class ProductViewSet(_CachedMastersListMixin, CompanyScopedViewSet):
    queryset = Product.objects.select_related("category", "brand", "unit")
    serializer_class = ProductSerializer
    list_cache_kind = "products"

    def _bust_list_cache(self):
        super()._bust_list_cache()
        cache.delete(f"masters:hsn:{self.company.pk}")
        for variant in ("cost", "nocost"):
            cache.delete(f"masters:products:{self.company.pk}:{variant}")

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanManageInventory()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    @action(detail=False, methods=["post"], url_path="mark-reviewed")
    def mark_reviewed(self, request):
        """Clear the 'needs review' flag on products fixed after a bill import."""
        raw = request.data.get("ids")
        if not isinstance(raw, list) or not raw or len(raw) > 500:
            raise ValidationError({"ids": "Send between 1 and 500 product ids."})
        try:
            ids = [int(x) for x in raw]
        except (TypeError, ValueError):
            raise ValidationError({"ids": "Product ids must be numbers."}) from None
        updated = Product.objects.filter(company=self.company, pk__in=ids, needs_review=True).update(
            needs_review=False, updated_by=request.user
        )
        self._bust_list_cache()
        return Response({"updated": updated})

    @action(detail=False, methods=["get"], url_path="pos-catalog")
    def pos_catalog(self, request):
        """Paged POS fields for the offline catalogue, plus ids removed since `updated_after`."""
        from django.utils.dateparse import parse_datetime

        try:
            limit = max(1, min(int(request.query_params.get("limit") or 500), 1000))
        except (TypeError, ValueError):
            limit = 500
        try:
            offset = max(0, int(request.query_params.get("cursor") or 0))
        except (TypeError, ValueError):
            offset = 0
        updated_after = parse_datetime(str(request.query_params.get("updated_after") or ""))
        # Only sellable products go to the till. An inactive item must not be sold offline.
        alive = Product.objects.filter(company=self.company, status=Product.Status.ACTIVE).select_related("unit")
        deleted_ids = []
        if updated_after is not None:
            alive = alive.filter(updated_at__gt=updated_after)
            gone = Product.all_objects.filter(company=self.company, updated_at__gt=updated_after).filter(
                Q(is_deleted=True) | ~Q(status=Product.Status.ACTIVE)
            )
            deleted_ids = list(gone.values_list("id", flat=True)[:1000])
        page = list(alive.order_by("id")[offset:offset + limit + 1])
        more = len(page) > limit
        page = page[:limit]
        results = []
        for product in page:
            unit = getattr(product, "unit", None)
            results.append({
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "barcode": product.barcode,
                "price": str(product.selling_price),
                "gst": str(product.gst_rate),
                "hsn": product.hsn_code,
                "unit": getattr(unit, "name", "") or "",
                "track_batch": bool(product.track_batch),
                "track_serial": bool(product.track_serial),
                "product_type": product.product_type,
                "updated_at": product.updated_at,
            })
        return Response({
            "results": results,
            "deleted_ids": deleted_ids,
            "next_cursor": offset + limit if more else None,
        })

    @action(detail=False, methods=["get"], url_path="pos-price-lists")
    def pos_price_lists(self, request):
        """Price lists for the named customers, plus a list named Default."""
        from masters.models import Customer, PriceList

        raw_ids = []
        for part in str(request.query_params.get("customers") or "").split(","):
            if part.strip().isdigit():
                raw_ids.append(int(part))
        customers = list(Customer.objects.filter(company=self.company, pk__in=raw_ids))
        wanted = {row.price_list_id for row in customers if row.price_list_id}
        default = PriceList.objects.filter(
            company=self.company, is_active=True, name__iexact="Default",
        ).first()
        if default is not None:
            wanted.add(default.id)
        lists = []
        for plist in PriceList.objects.filter(company=self.company, pk__in=wanted, is_active=True):
            lists.append({
                "id": plist.id,
                "name": plist.name,
                "items": [
                    {
                        "product": item.product_id,
                        "unit_price": str(item.unit_price),
                        "min_qty": str(item.min_qty),
                        "max_qty": None if item.max_qty is None else str(item.max_qty),
                    }
                    for item in plist.items.all()[:2000]
                ],
            })
        return Response({
            "lists": lists,
            "customers": [{"id": row.id, "price_list": row.price_list_id} for row in customers],
        })

    def get_queryset(self):
        from django.db.models import Exists, OuterRef
        from inventory.models import StockMovement

        qs = super().get_queryset().annotate(
            has_movements=Exists(StockMovement.objects.filter(product_id=OuterRef("pk")))
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if (self.request.query_params.get("needs_review") or "").lower() in ("1", "true", "yes"):
            # Products created by a bill import with no cost/stock yet (23.11).
            qs = qs.filter(needs_review=True)
        raw_ids = self.request.query_params.get("ids")
        if raw_ids:
            # Quick Entry hydrates its recent-product chips by id (max 50, integers only).
            try:
                id_list = [int(part) for part in raw_ids.split(",") if part.strip()]
            except ValueError:
                raise ValidationError({"ids": "Product ids must be numbers."}) from None
            if len(id_list) > 50:
                raise ValidationError({"ids": "Ask for at most 50 products at a time."})
            qs = qs.filter(pk__in=id_list)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        from masters.custom_fields import active_defs, apply_cf_filters, build_search_q

        defs = active_defs(self.company)
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(barcode__icontains=q)
                | Q(hsn_code__icontains=q)
                | Q(salt__icontains=q)
                | Q(composition__icontains=q)
                | Q(manufacturer__icontains=q)
                | build_search_q(q, defs)
            )
        qs = apply_cf_filters(qs, self.request.query_params, defs)
        return qs

    def list(self, request, *args, **kwargs):
        # Cache the unfiltered catalog; filtered lists stay live.
        if request.query_params:
            return super().list(request, *args, **kwargs)
        # The cached rows carry item cost only for people allowed to see it.
        from core.permissions import can_see_product_cost

        key = f"masters:products:{self.company.pk}:{'cost' if can_see_product_cost(request) else 'nocost'}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, _MASTERS_LIST_TTL)
        return response

    def perform_destroy(self, instance):
        from django.db.models import ProtectedError

        from core.exceptions import BusinessRuleError

        if instance.is_referenced():
            raise BusinessRuleError(
                f"Cannot delete '{instance.name}' because it has transaction history. Deactivate it instead."
            )
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            raise BusinessRuleError(
                f"Cannot delete '{instance.name}' because related documents reference it. Deactivate it instead."
            )

    @action(detail=False, methods=["get"], url_path="custom-field-values")
    def custom_field_values(self, request):
        # B8-027: distinct_values_for_keys() scans every product row with
        # custom_fields set, in Python, on every call -- this endpoint is hit
        # on every item-form open. A per-company short-TTL cache (same
        # pattern/TTL as _CachedMastersListMixin) turns a full-catalog scan
        # into a once-per-minute cost instead of once-per-request. Values are
        # dropdown suggestions, not authoritative data, so briefly-stale
        # results after a product edit are an acceptable tradeoff.
        from masters.custom_fields import active_defs, distinct_values_for_keys

        keys = [
            row["key"]
            for row in active_defs(self.company)
            if row.get("type") == "list" and row.get("key")
        ]
        cache_key = f"masters:custom_field_values:{self.company.pk}:{','.join(sorted(keys))}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        data = distinct_values_for_keys(self.company, keys)
        cache.set(cache_key, data, _MASTERS_LIST_TTL)
        return Response(data)

    @action(detail=False, methods=["post"], url_path="generate-barcode")
    def generate_barcode(self, request):
        import secrets

        company = self.company
        for _ in range(20):
            candidate = f"BB{company.id:04d}{secrets.randbelow(10**8):08d}"
            if not Product.objects.filter(company=company, barcode=candidate).exists():
                product_id = request.data.get("product")
                if product_id:
                    product = self.get_queryset().filter(pk=product_id).first()
                    if product is None:
                        raise BusinessRuleError("Product not found.")
                    product.barcode = candidate
                    product.updated_by = request.user
                    product.save(update_fields=["barcode", "updated_by"])
                    self._bust_list_cache()
                    return Response({**self.get_serializer(product).data, "svg": _barcode_svg(candidate)})
                return Response({"barcode": candidate, "svg": _barcode_svg(candidate)})
        raise BusinessRuleError("Could not generate a unique barcode. Retry.")

    @action(detail=False, methods=["get"], url_path="barcode-image")
    def barcode_image(self, request):
        import re

        code = re.sub(r"[^A-Za-z0-9\-_]", "", (request.query_params.get("code") or "").strip())[:64]
        if not code:
            raise BusinessRuleError("code is required")
        return HttpResponse(_barcode_svg(code), content_type="image/svg+xml")

    @action(detail=False, methods=["get"], url_path="hsn-search")
    def hsn_search(self, request):
        from .hsn_catalog import search_hsn

        rows = search_hsn(request.query_params.get("q") or "", kind=request.query_params.get("kind"))
        return Response({"count": len(rows), "items": rows})

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced product (§4.5) — deactivate instead."""
        from django.db.models import ProtectedError

        product = self.get_object()
        if product.is_referenced():
            product.status = Product.Status.INACTIVE
            product.updated_by = request.user
            product.save(update_fields=["status", "updated_by"])
            self._audit("UPDATE", product)
            self._bust_list_cache()
            return Response(
                {"detail": "Product is referenced by documents; marked Inactive instead of deleting."},
                status=200,
            )
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            product.status = Product.Status.INACTIVE
            product.updated_by = request.user
            product.save(update_fields=["status", "updated_by"])
            self._audit("UPDATE", product)
            self._bust_list_cache()
            return Response(
                {"detail": "Product is protected by database constraints; marked Inactive instead of deleting."},
                status=200,
            )


class PriceListViewSet(CompanyScopedViewSet):
    queryset = PriceList.objects.prefetch_related("items__product")
    serializer_class = PriceListSerializer

    def perform_destroy(self, instance):
        _soft_destroy(instance, self.request.user)
        # a soft delete is still a delete: it must leave the same audit row a hard one did
        self._audit_raw("DELETE", str(instance.pk))

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

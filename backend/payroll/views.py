from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.viewsets import CompanyScopedViewSet

from decimal import Decimal, InvalidOperation

from .models import Employee, PayRun, PaySlip
from .permissions import assert_payroll_enabled
from .serializers import EmployeeSerializer, PayRunSerializer
from .services import cancel_pay_run, complete_pay_run


class EmployeeViewSet(CompanyScopedViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]
    audit_entity = "Employee"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_payroll_enabled(get_company_user(request).company)


class PayRunViewSet(CompanyScopedViewSet):
    queryset = PayRun.objects.prefetch_related("slips__employee")
    serializer_class = PayRunSerializer
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]
    audit_entity = "PayRun"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_payroll_enabled(get_company_user(request).company)

    def perform_update(self, serializer):
        if self.get_object().status == PayRun.Status.COMPLETED:
            raise BusinessRuleError("Completed pay runs are immutable.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status == PayRun.Status.COMPLETED:
            raise BusinessRuleError("Completed pay runs cannot be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"], url_path="lop")
    def lop(self, request, pk=None):
        """R4-008: set loss-of-pay / partial-month paid days on a DRAFT run.

        Body: {"entries": [{"employee": <id>, "paid_days": <n>}, ...]}.
        Creates/updates a placeholder PaySlip carrying `paid_days`; complete()
        then prorates the gross and statutory dues for those employees.
        """
        pay_run = self.get_object()
        if pay_run.status != PayRun.Status.DRAFT:
            return Response(
                {"detail": "Loss-of-pay can only be set on a draft pay run."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = request.data.get("entries")
        if not isinstance(entries, list) or not entries:
            return Response(
                {"detail": "entries must be a non-empty list of {employee, paid_days}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company = get_company_user(request).company
        for row in entries:
            try:
                emp = Employee.objects.get(pk=row.get("employee"), company=company)
            except (Employee.DoesNotExist, TypeError, ValueError):
                return Response(
                    {"detail": f"Invalid employee {row.get('employee')!r}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                paid = Decimal(str(row.get("paid_days") if row.get("paid_days") is not None else row.get("paidDays")))
            except (InvalidOperation, TypeError):
                return Response(
                    {"detail": "paid_days must be a number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if paid < 0:
                return Response({"detail": "paid_days cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
            from calendar import monthrange

            period = getattr(pay_run, "period", "") or ""
            try:
                year, month = int(period[:4]), int(period[5:7])
                max_days = monthrange(year, month)[1]
            except (ValueError, IndexError):
                max_days = 31
            if paid > max_days:
                return Response(
                    {"detail": f"paid_days cannot exceed {max_days} calendar days in {period}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            PaySlip.objects.update_or_create(
                pay_run=pay_run,
                company=company,
                employee=emp,
                defaults={"paid_days": paid, "gross": emp.salary, "net": Decimal("0")},
            )
        pay_run = PayRun.objects.prefetch_related("slips__employee").get(pk=pay_run.pk)
        return Response(self.get_serializer(pay_run).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        pay_run = self.get_object()
        pay_from_cash = request.data.get("pay_from_cash", True)
        if isinstance(pay_from_cash, str):
            pay_from_cash = pay_from_cash.lower() not in ("0", "false", "no")
        try:
            pay_run = complete_pay_run(pay_run, request.user, pay_from_cash=pay_from_cash)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        pay_run = PayRun.objects.prefetch_related("slips__employee").get(pk=pay_run.pk)
        return Response(self.get_serializer(pay_run).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Reverse a completed pay run (GL reverse + reopen DRAFT)."""
        with transaction.atomic():
            pay_run = PayRun.objects.select_for_update().get(pk=self.get_object().pk)
            try:
                pay_run = cancel_pay_run(pay_run, request.user)
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        pay_run = PayRun.objects.prefetch_related("slips__employee").get(pk=pay_run.pk)
        return Response(self.get_serializer(pay_run).data)

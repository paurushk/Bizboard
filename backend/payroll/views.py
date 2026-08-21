from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import DenyViewerWrite, HasCompany, get_company_user
from core.viewsets import CompanyScopedViewSet

from .models import Employee, PayRun
from .permissions import assert_payroll_enabled
from .serializers import EmployeeSerializer, PayRunSerializer
from .services import complete_pay_run


class EmployeeViewSet(CompanyScopedViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, HasCompany, DenyViewerWrite]
    audit_entity = "Employee"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_payroll_enabled(get_company_user(request).company)


class PayRunViewSet(CompanyScopedViewSet):
    queryset = PayRun.objects.prefetch_related("slips__employee")
    serializer_class = PayRunSerializer
    permission_classes = [IsAuthenticated, HasCompany, DenyViewerWrite]
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

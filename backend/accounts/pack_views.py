"""Onboarding wizard. Flags change only after an explicit confirm."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CompanyPackState
from accounts.packs import PACKS, HELD_PACKS, propose_pack, apply_pack
from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.feature_flags import flag_enabled


class PackWizardView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        if not flag_enabled(company, "ENABLE_ARCHETYPE_PACKS"):
            return Response({"detail": "Not found."}, status=404)
        state = CompanyPackState.objects.filter(company=company).first()
        answers = state.answers if state else {}
        proposed = propose_pack(answers) if answers else ""
        return Response({
            "answers": answers,
            "proposed_pack": proposed,
            "applied_pack": state.applied_pack if state else "",
            "packs": {name: list(flags) for name, flags in PACKS.items()},
            "held_packs": list(HELD_PACKS),
            "confirmed_at": state.confirmed_at.isoformat() if state and state.confirmed_at else None,
        })

    def post(self, request):
        company = get_company_user(request).company
        if not flag_enabled(company, "ENABLE_ARCHETYPE_PACKS"):
            return Response({"detail": "Not found."}, status=404)
        answers = request.data.get("answers") or {}
        if not isinstance(answers, dict):
            return Response({"detail": "answers must be an object."}, status=400)
        proposed = propose_pack(answers)
        confirm = bool(request.data.get("confirm"))
        if not confirm:
            state, _ = CompanyPackState.objects.get_or_create(company=company)
            state.answers = answers
            state.proposed_pack = proposed
            state.save(update_fields=["answers", "proposed_pack", "updated_at"])
            return Response({"proposed_pack": proposed, "applied": False})
        try:
            state = apply_pack(company, proposed, answers, request.user)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({
            "proposed_pack": state.proposed_pack,
            "applied_pack": state.applied_pack,
            "applied": True,
            "skipped_flags": getattr(state, "skipped_flags", []),
        })

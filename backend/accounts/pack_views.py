"""Onboarding wizard. Flags change only after an explicit confirm."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import CompanyPackState
from accounts.packs import PACKS, HELD_PACKS, propose_pack, apply_pack
from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.feature_flags import flag_enabled


class NavScopeView(APIView):
    """Owner toggle between the archetype-pack sidebar and every feature.

    Existing companies never have NAV_PACK_DEFAULT set, so their menu stays
    as it is until they opt in.
    """

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        company = get_company_user(request).company
        raw = request.data.get("all_features")
        if raw not in (True, False, "true", "false", 1, 0, "1", "0"):
            raise BusinessRuleError("all_features must be true or false.")
        show_all = raw in (True, "true", 1, "1")
        flags = dict(company.feature_flags or {})
        flags["NAV_PACK_DEFAULT"] = not show_all
        if not show_all:
            flags["ENABLE_ARCHETYPE_PACKS"] = True
        company.feature_flags = flags
        company.save(update_fields=["feature_flags", "updated_at"])
        return Response({
            "all_features": show_all,
            "nav_pack_default": not show_all,
        })


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

"""WP-ID1: hand a company to another owner, or recover one whose owner can't sign in.

**Self-serve transfer.** An owner (password + MFA already checked by the view) names an active
member. The member gets an emailed, single-use link valid 72 hours; on accepting they become
OWNER and the old owner becomes MANAGER (or leaves). Both are emailed; every step is audited.

**Staff-assisted recovery** (nobody can sign in as owner: they left, lost their phone, died).
Django admin only. Needs a platform ticket, a reason, a note of the proof the business gave (GST
registration email, signed letter — a person checks it; this records what was checked), and a
second staff member's approval. Then a 72-hour wait during which every current owner is emailed
and can cancel. After the wait an owner invite goes to the proven address.

A company keeps at least one active OWNER at all times (``accounts.views._active_owner_count``
guards role changes and removals; the transfer swaps roles in one transaction).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService

TRANSFER_TTL = timedelta(hours=72)
RECOVERY_DELAY = timedelta(hours=72)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _email(to: str, subject: str, body: str, company) -> None:
    from core.models import Notification
    from core.services.notifications import NotificationService

    if to:
        NotificationService.send(
            company=company, channel=Notification.Channel.EMAIL, recipient=to, subject=subject, body=body,
        )


def _owners(company):
    from .models import CompanyUser

    return CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)


def start_transfer(*, company, from_user, to_user_id: int, old_owner_becomes: str = "MANAGER"):
    """Returns (transfer, token). The token goes in the emailed link and is stored only as a hash."""
    from .models import CompanyUser, OwnershipTransfer

    if old_owner_becomes not in ("MANAGER", "LEAVE"):
        raise BusinessRuleError("Choose what your own access becomes: Manager, or leave the company.")
    target = CompanyUser.objects.filter(company=company, user_id=to_user_id, is_active=True).select_related("user").first()
    if target is None or target.user_id == from_user.pk:
        raise BusinessRuleError("Pick another active member of this company.", code="OWNERSHIP_TARGET_INVALID")
    OwnershipTransfer.objects.filter(
        company=company, status=OwnershipTransfer.Status.PENDING, kind=OwnershipTransfer.Kind.SELF_SERVE,
    ).update(status=OwnershipTransfer.Status.CANCELLED)
    token = secrets.token_urlsafe(32)
    transfer = OwnershipTransfer.objects.create(
        company=company,
        kind=OwnershipTransfer.Kind.SELF_SERVE,
        from_user=from_user,
        to_user=target.user,
        old_owner_becomes=old_owner_becomes,
        token_hash=_hash(token),
        expires_at=timezone.now() + TRANSFER_TTL,
        created_by=from_user,
        updated_by=from_user,
    )
    from django.conf import settings

    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    _email(
        target.user.email, f"{from_user.email} wants to make you the owner of {company.name}",
        f"Sign in and open this link to accept ownership of {company.name} (valid 72 hours):\n"
        f"{base}/ownership/accept?token={token}\n", company,
    )
    AuditService.log(
        company=company, user=from_user, action="ownership.transfer_started", entity_type="OwnershipTransfer",
        entity_id=transfer.pk, description=f"Ownership offered to {target.user.email}",
    )
    return transfer, token


def accept_transfer(*, token: str, user):
    from .models import CompanyUser, OwnershipTransfer

    with transaction.atomic():
        transfer = (
            OwnershipTransfer.objects.select_for_update(of=("self",))
            .filter(token_hash=_hash(token or ""), kind=OwnershipTransfer.Kind.SELF_SERVE)
            .select_related("company", "from_user", "to_user")
            .first()
        )
        if transfer is None or transfer.to_user_id != user.pk:
            raise BusinessRuleError("This ownership link is not for you.", code="OWNERSHIP_LINK_INVALID")
        if transfer.status != OwnershipTransfer.Status.PENDING or transfer.expires_at <= timezone.now():
            raise BusinessRuleError("This ownership link has expired or was cancelled.", code="OWNERSHIP_LINK_EXPIRED")
        company = transfer.company
        new_owner = CompanyUser.objects.select_for_update().get(company=company, user=user, is_active=True)
        new_owner.role = CompanyUser.Role.OWNER
        for flag, value in (CompanyUser.capability_defaults_for_role(CompanyUser.Role.MANAGER) or {}).items():
            setattr(new_owner, flag, True if flag != "can_manage_policies" else value)
        new_owner.save()
        old = CompanyUser.objects.select_for_update().filter(company=company, user=transfer.from_user, is_active=True).first()
        if old is not None:
            if transfer.old_owner_becomes == "LEAVE":
                old.is_active = False
                old.save(update_fields=["is_active"])
            else:
                old.role = CompanyUser.Role.MANAGER
                old.save(update_fields=["role"])
        transfer.status = OwnershipTransfer.Status.ACCEPTED
        transfer.completed_at = timezone.now()
        transfer.save(update_fields=["status", "completed_at", "updated_at"])
    for who in (transfer.from_user.email, user.email):
        _email(who, f"{user.email} is now the owner of {company.name}", "Ownership transfer completed.", company)
    AuditService.log(
        company=company, user=user, action="ownership.transferred", entity_type="OwnershipTransfer",
        entity_id=transfer.pk, description=f"{transfer.from_user.email} -> {user.email}",
    )
    return transfer


def request_recovery(*, company, staff_user, ticket, recovery_email: str, proof_note: str, reason: str):
    """Staff step 1 of 2. A second staff member must approve before the wait starts."""
    from .models import OwnershipTransfer

    if not getattr(staff_user, "is_staff", False):
        raise BusinessRuleError("Only Bizboard staff can start an owner recovery.")
    if ticket is None or len((proof_note or "").strip()) < 10 or len((reason or "").strip()) < 10:
        raise BusinessRuleError("A ticket, a reason and a note of the proof checked are required.")
    if "@" not in (recovery_email or ""):
        raise BusinessRuleError("Give the email address the business proved it controls.")
    transfer = OwnershipTransfer.objects.create(
        company=company,
        kind=OwnershipTransfer.Kind.STAFF_RECOVERY,
        requested_by=staff_user,
        ticket=ticket,
        recovery_email=recovery_email.strip().lower(),
        proof_note=proof_note.strip()[:1000],
        reason=reason.strip()[:500],
        expires_at=timezone.now() + timedelta(days=14),
    )
    AuditService.log(
        company=company, user=staff_user, action="ownership.recovery_requested", entity_type="OwnershipTransfer",
        entity_id=transfer.pk, description=f"Owner recovery to {transfer.recovery_email}",
        metadata={"ticket": getattr(ticket, "pk", None)},
    )
    return transfer


def approve_recovery(transfer, *, staff_user):
    """Staff step 2: a different staff member approves; current owners get 72 hours to cancel."""
    from .models import OwnershipTransfer

    if transfer.kind != OwnershipTransfer.Kind.STAFF_RECOVERY or transfer.status != OwnershipTransfer.Status.PENDING:
        raise BusinessRuleError("Only a pending recovery can be approved.")
    if transfer.approved_by_id:
        raise BusinessRuleError("Already approved.")
    if not getattr(staff_user, "is_staff", False) or staff_user.pk == transfer.requested_by_id:
        raise BusinessRuleError("A second, different staff member must approve.")
    transfer.approved_by = staff_user
    transfer.effective_at = timezone.now() + RECOVERY_DELAY
    transfer.save(update_fields=["approved_by", "effective_at", "updated_at"])
    for cu in _owners(transfer.company).select_related("user"):
        _email(
            cu.user.email, f"Owner access to {transfer.company.name} is being recovered",
            f"Bizboard support will give owner access to {transfer.recovery_email} after 72 hours. "
            "If you did not ask for this, sign in and cancel it under Settings > Users, or reply to support now.",
            transfer.company,
        )
    AuditService.log(
        company=transfer.company, user=staff_user, action="ownership.recovery_approved",
        entity_type="OwnershipTransfer", entity_id=transfer.pk, description="Second staff approval",
    )
    return transfer


def cancel(transfer, *, user, reason: str = ""):
    from .models import OwnershipTransfer

    if transfer.status != OwnershipTransfer.Status.PENDING:
        raise BusinessRuleError("Nothing to cancel.")
    transfer.status = OwnershipTransfer.Status.CANCELLED
    transfer.reason = (transfer.reason + f" | cancelled: {reason}")[:500] if reason else transfer.reason
    transfer.save(update_fields=["status", "reason", "updated_at"])
    AuditService.log(
        company=transfer.company, user=user, action="ownership.cancelled", entity_type="OwnershipTransfer",
        entity_id=transfer.pk, description=reason or "Cancelled",
    )
    return transfer


def complete_due_recoveries(now=None) -> int:
    """Beat task body: send the owner invite for approved recoveries whose wait has passed."""
    from .models import OwnershipTransfer

    now = now or timezone.now()
    done = 0
    due = OwnershipTransfer.objects.filter(
        kind=OwnershipTransfer.Kind.STAFF_RECOVERY, status=OwnershipTransfer.Status.PENDING,
        approved_by__isnull=False, effective_at__lte=now,
    ).select_related("company", "approved_by")
    for transfer in due:
        _invite_owner(transfer)
        transfer.status = OwnershipTransfer.Status.ACCEPTED
        transfer.completed_at = now
        transfer.save(update_fields=["status", "completed_at", "updated_at"])
        AuditService.log(
            company=transfer.company, user=transfer.approved_by, action="ownership.recovered",
            entity_type="OwnershipTransfer", entity_id=transfer.pk,
            description=f"Owner invite sent to {transfer.recovery_email}",
        )
        done += 1
    return done


_OWNER_CAPS = dict(
    can_manage_inventory=True, can_import=True, can_cancel_documents=True, can_view_financial_reports=True,
    can_export=True, can_create_sales=True, can_create_purchases=True, can_create_payments=True,
    can_post_journals=True,
)


def _invite_owner(transfer) -> None:
    """The normal invite link (7 days, single use): the new owner sets their own password, then MFA."""
    from accounts.views import _invite_url, _make_invite_token

    from .models import CompanyUser, User

    company = transfer.company
    with transaction.atomic():
        user = User.objects.filter(email__iexact=transfer.recovery_email).first()
        if user is None:
            user = User.objects.create_user(email=transfer.recovery_email, password=None)
            user.set_unusable_password()
            user.save(update_fields=["password"])
        membership, _ = CompanyUser.objects.update_or_create(
            company=company, user=user,
            defaults={"role": CompanyUser.Role.OWNER, "is_active": False, **_OWNER_CAPS},
        )
        token = _make_invite_token(user_id=user.id, company_id=company.id, membership_id=membership.id)
    _email(
        transfer.recovery_email, f"Owner access to {company.name}",
        f"Bizboard support has restored owner access to {company.name} for you. "
        f"Open this link within 7 days to set your password: {_invite_url(token)}",
        company,
    )

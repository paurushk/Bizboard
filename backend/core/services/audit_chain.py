"""Hash chain over ``core.AuditEvent`` (F-SEC-03): seal and verify.

Sealing is a batch job (nightly), not part of the write path, so recording an
audit event never waits on a chain lock. Each sealed row stores

    chain_seq   1, 2, 3 ... per company (sealing order, NOT insertion order)
    chain_prev  chain_hash of the previous sealed row ("" for seq 1)
    chain_hash  sha256(chain_prev + "\n" + canonical(row facts + chain_seq))

so editing a sealed row, deleting one (a gap in chain_seq / a broken link) or
reordering them is detected by ``verify``. Events recorded after the last seal are
not yet protected - the window is the seal interval.

``company_id`` and ``user_id`` are deliberately NOT hashed: user deletion nulls
``user_id`` (a legitimate change) and sandbox teardown re-parents rows to NULL.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.utils import timezone

from core.audit_guard import audit_maintenance
from core.models import AuditEvent

BATCH = 2000

# MCA Rule 11(g): an edit of each of these masters must leave an AuditEvent.
# Adding a name here without an audit call on its update path fails test_bug_acc_003.
MCA_RULE_11G_MASTERS = (
    "Customer",
    "Supplier",
    "Product",
    "Unit",
    "TaxRate",
    "PriceList",
    "Account",
    "BankAccount",
    "CompanyUser",
)


def canonical(event: AuditEvent, seq: int) -> str:
    created = event.created_at.astimezone(_dt.timezone.utc) if timezone.is_aware(event.created_at) else event.created_at
    return json.dumps(
        {
            "id": event.pk,
            "seq": seq,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "description": event.description,
            "metadata": event.metadata,
            "created_at": created.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_hash(prev: str, event: AuditEvent, seq: int) -> str:
    return hashlib.sha256(f"{prev}\n{canonical(event, seq)}".encode("utf-8")).hexdigest()


def _lock(company_id) -> None:
    """Serialise sealers for one company (Postgres advisory lock, released at commit)."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", [0x41554454, int(company_id or 0)])


def seal(company_id=None, *, batch: int = BATCH) -> int:
    """Seal every unsealed event of one company (``None`` = events with no company).

    Returns how many rows were sealed. Safe to run concurrently and repeatedly.
    """
    sealed = 0
    while True:
        with transaction.atomic():
            _lock(company_id)
            scope = AuditEvent.objects.filter(company_id=company_id)
            last = scope.filter(sealed_at__isnull=False).order_by("-chain_seq").first()
            prev_hash, seq = (last.chain_hash, last.chain_seq) if last else ("", 0)
            rows = list(scope.filter(sealed_at__isnull=True).order_by("id")[:batch])
            if not rows:
                return sealed
            now = timezone.now()
            with audit_maintenance("seal audit chain"):
                for ev in rows:
                    seq += 1
                    h = compute_hash(prev_hash, ev, seq)
                    AuditEvent.objects.filter(pk=ev.pk, sealed_at__isnull=True).update(
                        chain_seq=seq, chain_prev=prev_hash, chain_hash=h, sealed_at=now,
                    )
                    prev_hash = h
            sealed += len(rows)
        if len(rows) < batch:
            return sealed


@dataclass
class VerifyResult:
    checked: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def verify(company_id=None, *, all_companies: bool = False) -> VerifyResult:
    """Recompute the chain. ``all_companies`` walks every company plus the NULL group."""
    res = VerifyResult()
    if all_companies:
        ids = list(
            AuditEvent.objects.filter(sealed_at__isnull=False).values_list("company_id", flat=True).distinct()
        )
    else:
        ids = [company_id]
    for cid in ids:
        _verify_one(cid, res)
    return res


def _verify_one(company_id, res: VerifyResult) -> None:
    rows = AuditEvent.objects.filter(company_id=company_id, sealed_at__isnull=False).order_by("chain_seq", "id")
    prev_hash, expected_seq = "", 1
    for ev in rows.iterator(chunk_size=2000):
        res.checked += 1
        tag = f"company={company_id} seq={ev.chain_seq} id={ev.pk}"
        # Content integrity: always checkable, even for rows re-parented to NULL company.
        if compute_hash(ev.chain_prev, ev, ev.chain_seq) != ev.chain_hash:
            res.problems.append(f"{tag}: content hash mismatch (row was altered)")
        # Link integrity: only meaningful while the company's chain is intact in place.
        if company_id is not None:
            if ev.chain_seq != expected_seq:
                res.problems.append(f"{tag}: expected seq {expected_seq} (a sealed event is missing or reordered)")
                expected_seq = ev.chain_seq
            if ev.chain_prev != prev_hash:
                res.problems.append(f"{tag}: chain_prev does not match the previous event's hash")
        prev_hash, expected_seq = ev.chain_hash, expected_seq + 1


def export_tip_payload() -> dict:
    """Sealed tip per company. Caller must refuse to write this when verify() is not ok."""
    companies = []
    ids = list(
        AuditEvent.objects.filter(sealed_at__isnull=False).values_list("company_id", flat=True).distinct()
    )
    for cid in sorted(ids, key=lambda value: (value is None, value if value is not None else 0)):
        last = (
            AuditEvent.objects.filter(company_id=cid, sealed_at__isnull=False)
            .order_by("-chain_seq", "-id")
            .first()
        )
        if last is None:
            continue
        companies.append({"id": cid, "max_seq": last.chain_seq, "tip_hash": last.chain_hash})
    return {"companies": companies}


def compare_tip(payload: dict, *, strict: bool = False) -> tuple[list[str], list[str]]:
    """Compare an exported tip to the database.

    A company in the file must still have that seq and hash, and the chain must
    not be shorter. A company sealed only after the export is a warning unless
    ``strict``. Returns (failures, warnings).
    """
    failures: list[str] = []
    warnings: list[str] = []
    file_ids = set()
    for row in payload.get("companies") or []:
        cid = row.get("id")
        file_ids.add(cid)
        seq = row.get("max_seq")
        tip_hash = row.get("tip_hash") or ""
        ev = AuditEvent.objects.filter(
            company_id=cid, sealed_at__isnull=False, chain_seq=seq,
        ).first()
        db_hash = ev.chain_hash if ev is not None else ""
        if ev is None or ev.chain_hash != tip_hash:
            failures.append(
                f"company={cid} file_seq={seq} file_hash={tip_hash} db_hash={db_hash}: "
                "tip row missing or hash mismatch"
            )
            continue
        current = (
            AuditEvent.objects.filter(company_id=cid, sealed_at__isnull=False)
            .order_by("-chain_seq")
            .first()
        )
        current_seq = current.chain_seq if current is not None else 0
        if current_seq < seq:
            failures.append(
                f"company={cid} file_seq={seq} file_hash={tip_hash} db_hash={db_hash}: "
                f"chain shorter than the tip file (max_seq={current_seq})"
            )
    db_ids = set(
        AuditEvent.objects.filter(sealed_at__isnull=False).values_list("company_id", flat=True).distinct()
    )
    for cid in sorted(db_ids - file_ids, key=lambda value: (value is None, value if value is not None else 0)):
        message = f"company={cid}: sealed events exist that are not in the tip file"
        if strict:
            failures.append(message)
        else:
            warnings.append(message)
    return failures, warnings

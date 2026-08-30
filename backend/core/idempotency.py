"""BB-000610 / BB-000491 / BB-000730: durable Idempotency-Key helpers."""

from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from core.models import IdempotencyRecord

DEFAULT_TTL = 60 * 60 * 24  # retained for callers; rows are durable
IN_FLIGHT_STATUS = 0
# R1-011: how long an in-flight placeholder may be held before a retry is
# allowed to take it over. Must exceed the slowest protected operation
# (large import commit, e-invoice round-trip). Bump this, not a magic literal.
IN_FLIGHT_STALE_SECONDS = 15 * 60


class IdempotencyInFlightError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A request with this Idempotency-Key is already in progress."
    default_code = "idempotency_in_flight"


def get_record(*, company, scope: str, raw_key: str) -> IdempotencyRecord | None:
    key = (raw_key or "").strip()
    if not key or company is None:
        return None
    return IdempotencyRecord.objects.filter(company=company, scope=scope, key=key).first()


def replay_record(record: IdempotencyRecord) -> Response:
    return Response(record.body, status=record.status_code)


def _is_complete(record: IdempotencyRecord) -> bool:
    return int(record.status_code or 0) != IN_FLIGHT_STATUS


def _json_safe(value):
    """Coerce DRF ReturnDict / Decimals into JSON-field-safe plain data."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def begin_record(*, company, scope: str, raw_key: str) -> IdempotencyRecord | Response:
    """
    BB-000730: insert in-flight placeholder under unique constraint before create.

    Returns the new in-flight row when this request owns the key.
    Returns a replay Response when a completed row already exists.
    Raises IdempotencyInFlightError when another request still holds the key.
    """
    key = (raw_key or "").strip()
    if not key or company is None:
        raise ValueError("idempotency begin_record requires company and key")

    try:
        with transaction.atomic():
            return IdempotencyRecord.objects.create(
                company=company,
                scope=scope,
                key=key,
                status_code=IN_FLIGHT_STATUS,
                body={},
                resource_id="",
            )
    except IntegrityError:
        with transaction.atomic():
            existing = (
                IdempotencyRecord.objects.select_for_update()
                .filter(company=company, scope=scope, key=key)
                .order_by("id")
                .first()
            )
            if existing is None:
                try:
                    return IdempotencyRecord.objects.create(
                        company=company,
                        scope=scope,
                        key=key,
                        status_code=IN_FLIGHT_STATUS,
                        body={},
                        resource_id="",
                    )
                except IntegrityError:
                    raise IdempotencyInFlightError() from None
            if _is_complete(existing):
                return replay_record(existing)
            from django.utils import timezone

            age = (timezone.now() - existing.created_at).total_seconds()
            if age > IN_FLIGHT_STALE_SECONDS:
                existing.delete()
                try:
                    return IdempotencyRecord.objects.create(
                        company=company,
                        scope=scope,
                        key=key,
                        status_code=IN_FLIGHT_STATUS,
                        body={},
                        resource_id="",
                    )
                except IntegrityError:
                    raise IdempotencyInFlightError() from None
            raise IdempotencyInFlightError()


def release_record(*, company, scope: str, raw_key: str) -> None:
    """Drop an in-flight placeholder so the key can be retried after failure."""
    key = (raw_key or "").strip()
    if not key or company is None:
        return
    IdempotencyRecord.objects.filter(
        company=company,
        scope=scope,
        key=key,
        status_code=IN_FLIGHT_STATUS,
    ).delete()


def forget_record(*, company, scope: str, raw_key: str) -> None:
    """Drop a completed or in-flight key so the client can safely retry."""
    key = (raw_key or "").strip()
    if not key or company is None:
        return
    IdempotencyRecord.objects.filter(company=company, scope=scope, key=key).delete()


def store_record(*, company, scope: str, raw_key: str, response: Response, resource_id: str = "") -> None:
    key = (raw_key or "").strip()
    if not key or company is None:
        return
    body = getattr(response, "data", None)
    if not isinstance(body, dict):
        body = {"detail": body}
    else:
        body = dict(body)
    try:
        body = _json_safe(body)
    except (TypeError, ValueError):
        body = {"detail": str(body)}
    defaults = {
        "status_code": int(getattr(response, "status_code", 200) or 200),
        "body": body,
        "resource_id": str(resource_id or ""),
    }
    # Prefer updating the in-flight placeholder row (same unique key).
    updated = IdempotencyRecord.objects.filter(company=company, scope=scope, key=key).update(
        **defaults
    )
    if not updated:
        IdempotencyRecord.objects.update_or_create(
            company=company,
            scope=scope,
            key=key,
            defaults=defaults,
        )


def wrap_idempotent(*, request, company, scope: str, build):
    """Claim Idempotency-Key, run build(), store the outcome, release only on a
    raised exception.

    R1-010: a returned **2xx** is stored (replayed on retry, as before). A
    returned **5xx** is now *also* stored — if `build()` returned it, the handler
    ran to completion and a naive retry with the same key could double-apply a
    side effect that committed before the error. A **4xx** (deterministic client
    error — bad input, conflict, subscription gate) still releases the key so the
    client can correct and retry. A *raised* exception always releases (the
    atomic block rolled back).
    """
    raw_key = (request.headers.get("Idempotency-Key") or "").strip()
    claimed = None
    if raw_key:
        claimed = begin_record(company=company, scope=scope, raw_key=raw_key)
        if isinstance(claimed, Response):
            return claimed
    owns_key = raw_key and claimed is not None and not isinstance(claimed, Response)
    settled = False  # True once we've decided store-vs-release for this key
    try:
        response = build()
        if owns_key:
            code = int(getattr(response, "status_code", 200) or 200)
            if 200 <= code < 300 or code >= 500:
                data = getattr(response, "data", None) or {}
                inner = data
                if isinstance(data, dict) and isinstance(data.get("success"), bool) and "data" in data:
                    inner = data.get("data") or {}
                rid = (
                    str(inner.get("id") or "")
                    if (200 <= code < 300 and isinstance(inner, dict))
                    else ""
                )
                store_record(
                    company=company, scope=scope, raw_key=raw_key,
                    response=response, resource_id=rid,
                )
            else:
                release_record(company=company, scope=scope, raw_key=raw_key)
            settled = True
        return response
    finally:
        if owns_key and not settled:
            release_record(company=company, scope=scope, raw_key=raw_key)

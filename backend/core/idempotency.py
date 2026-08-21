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


class IdempotencyInFlightError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A request with this Idempotency-Key is already in progress."
    default_code = "idempotency_in_flight"


def cache_key(prefix: str, company_id: int, resource_id: int | str, raw_key: str) -> str:
    return f"{prefix}:{company_id}:{resource_id}:{raw_key}"


def get_cached_response(key: str) -> Response | None:
    """Legacy cache-key string lookup — prefer get_record()."""
    return None


def store_response(key: str, response: Response, *, ttl: int = DEFAULT_TTL) -> None:
    return None


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
            existing = get_record(company=company, scope=scope, raw_key=key)
        if existing is None:
            raise
        if _is_complete(existing):
            return replay_record(existing)
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

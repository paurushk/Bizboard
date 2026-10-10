"""Unit tests for the idempotency request fingerprint (QOS-0108). The endpoint-level behaviour
lives in test_double_submit_money_paths.py; these pin the mechanism and its edge cases."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from core.idempotency import (
    IN_FLIGHT_STALE_SECONDS,
    IdempotencyInFlightError,
    IdempotencyKeyReusedError,
    begin_record,
    request_fingerprint,
    store_record,
    wrap_idempotent,
)
from core.models import IdempotencyRecord

pytestmark = pytest.mark.django_db

PARSERS = [JSONParser(), FormParser(), MultiPartParser()]


def _req(path="/api/v1/payments/receipts/", data=None, fmt="json", method="post"):
    factory = APIRequestFactory()
    raw = getattr(factory, method)(path, data if data is not None else {}, format=fmt)
    return Request(raw, parsers=PARSERS)


# --- fingerprint -------------------------------------------------------------------

def test_same_request_same_fingerprint_and_it_is_a_sha256_hex():
    fp = request_fingerprint(_req(data={"a": 1}))
    assert fp == request_fingerprint(_req(data={"a": 1}))
    assert len(fp) == 64 and int(fp, 16) >= 0


def test_method_path_and_every_body_value_matter():
    base = request_fingerprint(_req(data={"amount": "500.00"}))
    assert base != request_fingerprint(_req(data={"amount": "500.01"}))
    assert base != request_fingerprint(_req(path="/api/v1/payments/supplier-payments/", data={"amount": "500.00"}))
    assert base != request_fingerprint(_req(data={"amount": "500.00"}, method="put"))
    assert base != request_fingerprint(_req(data={"amount": "500.00", "extra": 1}))


def test_nested_bodies_and_lists_are_compared_by_content_and_order():
    a = {"items": [{"product": 1, "quantity": "2"}, {"product": 2, "quantity": "1"}], "customer": 5}
    b = {"customer": 5, "items": [{"quantity": "2", "product": 1}, {"quantity": "1", "product": 2}]}
    assert request_fingerprint(_req(data=a)) == request_fingerprint(_req(data=b))   # dict key order is irrelevant
    swapped = {"customer": 5, "items": list(reversed(a["items"]))}
    assert request_fingerprint(_req(data=a)) != request_fingerprint(_req(data=swapped))  # line order is meaningful


def test_form_encoded_bodies_are_supported_and_stable():
    one = request_fingerprint(_req(data={"a": "1", "b": "2"}, fmt="multipart"))
    two = request_fingerprint(_req(data={"b": "2", "a": "1"}, fmt="multipart"))
    assert one == two
    assert one != request_fingerprint(_req(data={"a": "1", "b": "3"}, fmt="multipart"))


def test_uploaded_files_fingerprint_by_name_and_size_not_by_object_identity():
    def upload(name, body):
        return _req(path="/api/v1/imports/", data={"kind": "PRODUCTS", "file": SimpleUploadedFile(name, body)}, fmt="multipart")

    same_a = request_fingerprint(upload("items.csv", b"a,b\n1,2\n"))
    same_b = request_fingerprint(upload("items.csv", b"a,b\n1,2\n"))
    assert same_a == same_b, "the same file resent must not look like a different request"
    assert same_a != request_fingerprint(upload("other.csv", b"a,b\n1,2\n"))
    assert same_a != request_fingerprint(upload("items.csv", b"a,b\n1,2\n3,4\n"))


def test_unparsable_or_non_request_objects_yield_no_fingerprint_instead_of_raising():
    class Bare:
        headers = {"Idempotency-Key": "k"}

    assert request_fingerprint(Bare()) == ""
    assert request_fingerprint(None) == ""


def test_empty_body_is_a_valid_fingerprint():
    assert request_fingerprint(_req(data={})) != ""


def test_ignored_keys_drop_only_the_named_top_level_confirm_flags():
    """Complete's confirm flags are the same gesture as the first attempt, so a retry that adds
    one must reuse the key. Everything else in the body still changes the fingerprint."""
    def fp(data):
        request = _req(path="/api/v1/sales/invoices/9/complete/", data=data)
        request._idempotency_ignore_keys = frozenset({"confirm_blank_pos", "confirmBlankPos"})
        return request_fingerprint(request)

    base = fp({"note": "a"})
    assert base == fp({"note": "a", "confirm_blank_pos": True})
    assert base == fp({"note": "a", "confirmBlankPos": "true"})
    assert base != fp({"note": "b", "confirm_blank_pos": True})
    assert fp({"x": {"confirm_blank_pos": True}}) != fp({"x": {}}), "nested keys are request data"
    plain = _req(path="/api/v1/sales/invoices/9/complete/", data={"note": "a", "confirm_blank_pos": True})
    assert request_fingerprint(plain) != base, "without the opt-in nothing is ignored"


# --- begin_record -------------------------------------------------------------------

def test_first_claim_stores_the_fingerprint(tenant_a):
    rec = begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k1", fingerprint="fp-1")
    assert isinstance(rec, IdempotencyRecord) and rec.request_hash == "fp-1"


def test_replay_requires_the_same_fingerprint(tenant_a):
    begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k2", fingerprint="fp-1")
    store_record(company=tenant_a.company, scope="receipt_create", raw_key="k2", response=Response({"id": 9}, status=201))
    replay = begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k2", fingerprint="fp-1")
    assert isinstance(replay, Response) and replay.status_code == 201
    with pytest.raises(IdempotencyKeyReusedError):
        begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k2", fingerprint="fp-OTHER")


def test_a_different_request_while_the_first_is_still_in_flight_is_a_reuse_error_not_a_wait(tenant_a):
    begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k3", fingerprint="fp-1")
    with pytest.raises(IdempotencyKeyReusedError):
        begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k3", fingerprint="fp-2")
    # the identical request while in flight is the normal in-flight conflict
    with pytest.raises(IdempotencyInFlightError):
        begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k3", fingerprint="fp-1")


def test_no_fingerprint_supplied_means_no_conflict_check(tenant_a):
    begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k4", fingerprint="fp-1")
    store_record(company=tenant_a.company, scope="receipt_create", raw_key="k4", response=Response({"id": 1}))
    assert isinstance(begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k4"), Response)


def test_a_stale_non_money_claim_is_taken_over_with_the_new_fingerprint(tenant_a):
    scope = "import_job_create"  # not a money scope, so a stale in-flight row may be reclaimed
    begin_record(company=tenant_a.company, scope=scope, raw_key="k5", fingerprint="old")
    IdempotencyRecord.objects.filter(company=tenant_a.company, key="k5").update(
        created_at=timezone.now() - timedelta(seconds=IN_FLIGHT_STALE_SECONDS + 5),
    )
    # same fingerprint is the takeover case; the row is replaced and now carries the new owner's hash
    taken = begin_record(company=tenant_a.company, scope=scope, raw_key="k5", fingerprint="old")
    assert isinstance(taken, IdempotencyRecord) and taken.request_hash == "old"


def test_a_stale_money_claim_without_a_resource_stays_held(tenant_a):
    """resource_id is stored after the money commits, so an empty one proves nothing."""
    scope = "receipt_create"
    begin_record(company=tenant_a.company, scope=scope, raw_key="k6", fingerprint="fp")
    IdempotencyRecord.objects.filter(company=tenant_a.company, key="k6").update(
        created_at=timezone.now() - timedelta(seconds=IN_FLIGHT_STALE_SECONDS + 5),
    )
    with pytest.raises(IdempotencyInFlightError):
        begin_record(company=tenant_a.company, scope=scope, raw_key="k6", fingerprint="fp")
    assert IdempotencyRecord.objects.filter(company=tenant_a.company, key="k6").exists()


def test_a_stale_money_claim_that_already_names_a_resource_stays_held(tenant_a):
    scope = "receipt_create"
    begin_record(company=tenant_a.company, scope=scope, raw_key="k6b", fingerprint="fp")
    IdempotencyRecord.objects.filter(company=tenant_a.company, key="k6b").update(
        created_at=timezone.now() - timedelta(seconds=IN_FLIGHT_STALE_SECONDS + 5),
        resource_id="99",
    )
    with pytest.raises(IdempotencyInFlightError):
        begin_record(company=tenant_a.company, scope=scope, raw_key="k6b", fingerprint="fp")


def test_store_record_keeps_the_hash_set_at_claim_time(tenant_a):
    begin_record(company=tenant_a.company, scope="receipt_create", raw_key="k7", fingerprint="fp-keep")
    store_record(company=tenant_a.company, scope="receipt_create", raw_key="k7", response=Response({"id": 5}, status=201))
    assert IdempotencyRecord.objects.get(company=tenant_a.company, key="k7").request_hash == "fp-keep"


# --- wrap_idempotent ----------------------------------------------------------------

def test_wrap_idempotent_refuses_a_reused_key_without_running_the_work(tenant_a):
    calls = []

    def build():
        calls.append(1)
        return Response({"id": len(calls)}, status=201)

    def req(amount):
        r = _req(path="/api/v1/sales/invoices/9/complete/", data={"amount": amount})
        r.META["HTTP_IDEMPOTENCY_KEY"] = "wrap-1"
        return r

    first = wrap_idempotent(request=req("1"), company=tenant_a.company, scope="sales_invoice_complete", build=build)
    assert first.status_code == 201
    with pytest.raises(IdempotencyKeyReusedError):
        wrap_idempotent(request=req("2"), company=tenant_a.company, scope="sales_invoice_complete", build=build)
    replay = wrap_idempotent(request=req("1"), company=tenant_a.company, scope="sales_invoice_complete", build=build)
    assert replay.status_code == 201 and replay.data == first.data
    assert len(calls) == 1, "the guarded work must have run exactly once"


def test_a_confirm_prompt_releases_the_key_so_the_confirmed_retry_runs(tenant_a):
    """The missing-licence prompt is a 400 the user answers. Storing it would replay the refusal
    to the confirmed retry, because the confirm flag is left out of the fingerprint."""
    from core.exceptions import BusinessRuleError
    from core.help_codes import HelpCode

    calls = []

    def build():
        calls.append(1)
        if len(calls) == 1:
            raise BusinessRuleError("Confirm the missing licence.", code=HelpCode.CONFIRM_MISSING_LICENCE)
        return Response({"id": 7}, status=200)

    def req(data):
        r = _req(path="/api/v1/sales/invoices/7/complete/", data=data)
        r.META["HTTP_IDEMPOTENCY_KEY"] = "licence-1"
        r._idempotency_ignore_keys = frozenset({"confirm_missing_licence"})
        return r

    with pytest.raises(BusinessRuleError):
        wrap_idempotent(request=req({}), company=tenant_a.company, scope="sales_invoice_complete", build=build)
    second = wrap_idempotent(
        request=req({"confirm_missing_licence": True}), company=tenant_a.company,
        scope="sales_invoice_complete", build=build,
    )
    assert second.status_code == 200 and len(calls) == 2


# --- error shape -----------------------------------------------------------------------

def test_the_reuse_error_is_a_422_with_a_stable_code_and_actionable_text():
    err = IdempotencyKeyReusedError()
    assert err.status_code == 422 and err.default_code == "idempotency_key_reused"
    assert "new key" in str(err.detail).lower()


def test_a_stale_complete_claim_without_a_resource_can_be_taken_over(tenant_a):
    """Complete is guarded by the document's status, so a crashed first attempt can be finished.
    (A create scope is not: see test_a_stale_money_claim_without_a_resource_stays_held.)"""
    scope = "sales_invoice_complete"
    begin_record(company=tenant_a.company, scope=scope, raw_key="k8", fingerprint="fp")
    IdempotencyRecord.objects.filter(company=tenant_a.company, key="k8").update(
        created_at=timezone.now() - timedelta(seconds=IN_FLIGHT_STALE_SECONDS + 5),
    )
    taken = begin_record(company=tenant_a.company, scope=scope, raw_key="k8", fingerprint="fp")
    assert isinstance(taken, IdempotencyRecord)

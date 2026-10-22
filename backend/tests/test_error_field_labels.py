"""Error messages name fields the way people read them, never as raw snake_case keys."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from core.exceptions import api_exception_handler, field_label


def test_field_label():
    assert field_label("phone") == "Phone"
    assert field_label("company_name") == "Company name"
    assert field_label("companyName") == "Company name"
    assert field_label("gstin") == "GSTIN"
    assert field_label("otp_code") == "OTP code"
    assert field_label("customer_id") == "Customer ID"
    assert field_label("non_field_errors") == ""
    assert field_label("__all__") == ""


def test_drf_field_errors_get_readable_labels():
    resp = api_exception_handler(
        ValidationError(
            {
                "phone": ["Enter a valid mobile number."],
                "company_name": ["This field is required."],
                "non_field_errors": ["Pick a plan."],
                "lines": [{}, {"hsn_code": ["Unknown HSN."]}],
            }
        ),
        {},
    )
    assert resp.data["error"]["message"] == (
        "Phone: Enter a valid mobile number.; Company name: This field is required.; "
        "Pick a plan.; Lines: HSN code: Unknown HSN."
    )
    # Machine-readable keys are unchanged for forms that map errors onto fields.
    assert set(resp.data["error"]["details"]) == {"phone", "company_name", "non_field_errors", "lines"}


def test_django_validation_error_gets_readable_labels():
    resp = api_exception_handler(
        DjangoValidationError({"credit_limit": ["Must be positive."], "__all__": ["Bad row."]}), {}
    )
    assert resp.data["error"]["message"] == "Credit limit: Must be positive.; Bad row."

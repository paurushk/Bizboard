import pytest

from masters.serializers import CustomerSerializer, SupplierSerializer


@pytest.mark.django_db
def test_customer_serializer_rejects_script_name():
    ser = CustomerSerializer(data={"name": "<script>alert(1)</script>"})
    assert ser.is_valid() is False
    assert "name" in ser.errors


@pytest.mark.django_db
def test_supplier_serializer_rejects_punctuation_only_name():
    ser = SupplierSerializer(data={"name": "..."})
    assert ser.is_valid() is False
    assert "name" in ser.errors


@pytest.mark.django_db
def test_customer_serializer_accepts_a_trading_name():
    ser = CustomerSerializer(data={"name": "Ravi Stores"})
    assert ser.is_valid(), ser.errors


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["Café Traders", "शर्मा स्टोर्स"])
def test_customer_serializer_accepts_unicode_letters(name):
    ser = CustomerSerializer(data={"name": name})
    assert ser.is_valid(), ser.errors

"""Customer creation outside the Customers screen (CRM lead conversion, bill import).

One path, so a customer made from a lead or an imported bill gets the same GSTIN, state, PAN, duplicate and
name rules as one typed into the form (``CustomerSerializer.validate``).
"""

from core.exceptions import BusinessRuleError

from .models import Customer
from .serializers import CustomerSerializer


def create_customer(*, company, user, **fields) -> Customer:
    """Validate ``fields`` like the form does and create the customer; raise BusinessRuleError with the reason."""
    serializer = CustomerSerializer(data=fields, context={"company": company})
    if not serializer.is_valid():
        problems = []
        for field, messages in serializer.errors.items():
            text = messages[0] if isinstance(messages, (list, tuple)) and messages else messages
            problems.append(f"{field}: {text}")
        raise BusinessRuleError("Cannot create the customer. " + "; ".join(problems), code="customer_invalid")
    return serializer.save(company=company, created_by=user, updated_by=user)

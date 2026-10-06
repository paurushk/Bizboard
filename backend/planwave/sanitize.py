"""Strip tags from plain-text fields on save."""

from __future__ import annotations

import re

# Only real tags (an opening or closing tag name, or a comment). Text such as "<5000 and >100" stays.
_TAG = re.compile(r"</?[A-Za-z][^>]*>|<!--.*?-->", re.S)
# "name" is included for catalog rows (products, categories, brands): a tag in a product name
# is never legitimate. Customer and supplier names are skipped here: the API already rejects a
# name containing < or >, and silently rewriting a stored party name corrupts the record.
# Output escaping (React, the PDF writer) is what makes any name safe to show.
_FIELDS = (
    "notes", "description", "name", "address", "billing_address", "shipping_address",
    "remarks", "reason", "inspection_notes",
)
_PARTY_MODELS = frozenset({"Customer", "Supplier"})


def strip_plain_text(sender, instance, **kwargs):
    keep_name = getattr(sender, "__name__", "") in _PARTY_MODELS
    for name in _FIELDS:
        if name == "name" and keep_name:
            continue
        value = getattr(instance, name, None)
        if isinstance(value, str) and "<" in value:
            setattr(instance, name, _TAG.sub("", value))

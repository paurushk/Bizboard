"""WP-F2 / DIM6-04: shadow books — one ledger for every company.

Two questions used to share one switch (``Company.accounting_enabled``):

1. *Does this company's activity post to the general ledger?* — ``posts_to_ledger(company)``
2. *Does the company see accounting screens and GL-based figures?* — ``accounting_enabled``

``Company.post_ledger`` (default on, not editable by tenants) answers the first. With it on,
a company that keeps the Books switch off still gets a complete ledger in the background, so
turning books on later needs no back-fill and changes no number. Posting gates call
``posts_to_ledger``; screens, outstanding figures and the books-health severity keep reading
``accounting_enabled``.

No imports here: posting modules across the app import this at module level.
"""

from __future__ import annotations


def posts_to_ledger(company) -> bool:
    """True when documents for ``company`` must post journals (books on, or shadow books)."""
    if company is None:
        return False
    return bool(getattr(company, "accounting_enabled", False) or getattr(company, "post_ledger", False))


def is_shadow(company) -> bool:
    """Posting in the background for a company that does not see its books."""
    return posts_to_ledger(company) and not bool(getattr(company, "accounting_enabled", False))

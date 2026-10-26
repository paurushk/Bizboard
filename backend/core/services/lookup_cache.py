"""Per-operation memo for read-only lookups that cannot change while one operation runs.

Completing a sales invoice posts the sale, the cost of goods and the document number, and each
step looked up the same chart accounts and the company's series GSTIN again (BB-067: 151 queries
per Complete with the ledger on, 49 more than with it off). Inside ``lookup_cache()`` those
lookups are fetched once; outside it every call reads the database as before.

Only values that are fixed for the length of one operation belong here (account rows by code,
the company's GSTIN key). Period locks, balances and anything another transaction may change
must keep reading the database.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_store: ContextVar[dict | None] = ContextVar("bizboard_lookup_cache", default=None)
_MISSING = object()


@contextmanager
def lookup_cache():
    """Memoize lookups for the enclosed block. Nested blocks share the outer memo."""
    if _store.get() is not None:
        yield
        return
    token = _store.set({})
    try:
        yield
    finally:
        _store.reset(token)


def with_lookup_cache(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with lookup_cache():
            return func(*args, **kwargs)

    return wrapper


def cached(key, load, *, keep_none: bool = False):
    """``load()`` once per key inside ``lookup_cache()``; every time outside it.

    ``None`` is not kept unless ``keep_none``: a miss usually leads the caller to create the row.
    """
    store = _store.get()
    if store is None:
        return load()
    value = store.get(key, _MISSING)
    if value is _MISSING:
        value = load()
        if value is not None or keep_none:
            store[key] = value
    return value


def first_time(key) -> bool:
    """True the first time ``key`` is seen inside ``lookup_cache()``; always True outside it."""
    store = _store.get()
    if store is None:
        return True
    if key in store:
        return False
    store[key] = True
    return True

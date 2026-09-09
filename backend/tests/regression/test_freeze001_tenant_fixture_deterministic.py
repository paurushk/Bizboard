"""FREEZE-001 — the test tenant fixture was non-reproducible.

Symptom:  `make_tenant(slug)` set the owner phone to
          `f"9{abs(hash(slug)) % 10**9:09d}"`. CPython salts str hashing per
          process (PYTHONHASHSEED), so the same slug produced a different phone
          on every run. Any assertion or ordering that depended on it — and any
          attempt to reproduce a failure from a CI seed — was unstable.

Root cause: use of the builtin `hash()` on a str for a value that must be
          stable across processes.

Fix:      `_stable_phone()` in tests/conftest.py derives the digits from
          `zlib.crc32`, which is process-independent.

These goldens will change only if the derivation changes on purpose.
"""

from __future__ import annotations

from tests.conftest import _stable_phone


def test_stable_phone_is_process_independent_golden():
    assert _stable_phone("alpha") == "9504355690"
    assert _stable_phone("beta") == "9408645731"


def test_stable_phone_is_idempotent():
    assert _stable_phone("gamma") == _stable_phone("gamma")
    assert _stable_phone("alpha") != _stable_phone("beta")

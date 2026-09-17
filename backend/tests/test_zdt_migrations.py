"""7.7 — expand/contract: additive migrations only for this quota/DLQ cut."""

from __future__ import annotations

from django.db.migrations.operations.fields import AddField, RemoveField, RenameField
from django.db.migrations.operations.models import DeleteModel, RenameModel


_DESTRUCTIVE = (RemoveField, RenameField, DeleteModel, RenameModel)


def _ops(module_path: str):
    import importlib

    return importlib.import_module(module_path).Migration.operations


def migration_is_expand_safe(operations) -> bool:
    return not any(isinstance(op, _DESTRUCTIVE) for op in operations)


def test_plan_quota_migration_is_expand_only():
    ops = _ops("billing.migrations.0005_plan_quotas_deadletter")
    assert any(isinstance(op, AddField) for op in ops)
    assert migration_is_expand_safe(ops)


def test_expand_contract_helper_rejects_remove_field():
    assert migration_is_expand_safe([]) is True
    destructive = object.__new__(RemoveField)
    assert migration_is_expand_safe([destructive]) is False

"""Manufacturing services.

Import paths from before rev 2 keep working: ``from manufacturing.services import
release_work_order`` and friends. Each of the three lifecycle calls goes to the one-step flow
(``legacy``) or to the document flow (``flow``) according to the work order's ``issue_mode``.
"""

from manufacturing.models import WorkOrder

from . import legacy
from .bom import assert_no_bom_cycle, resolve_bom  # noqa: F401
from .legacy import (  # noqa: F401
    _component_requirements,
    _issue_batches,
    _issue_cost_total,
    _snapshot_bom,
)


def _separate(wo) -> bool:
    return wo.issue_mode == WorkOrder.IssueMode.SEPARATE


def release_work_order(wo, user, *, component_serials=None, can_backdate=True):
    if _separate(wo):
        from . import flow

        return flow.release_separate(wo, user, can_backdate=can_backdate)
    return legacy.release_work_order(wo, user, component_serials=component_serials)


def complete_work_order(wo, user, *, can_backdate=True):
    if _separate(wo):
        from . import flow

        return flow.complete_separate(wo, user, can_backdate=can_backdate)
    return legacy.complete_work_order(wo, user)


def cancel_work_order(wo, user):
    if _separate(wo):
        from . import flow

        return flow.cancel_separate(wo, user)
    return legacy.cancel_work_order(wo, user)

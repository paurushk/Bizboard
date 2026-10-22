"""MFG-01: the reference types that change how cost layers behave.

``InventoryService._apply_cost_layers`` used to decide this from two tuples written
inline. Every new document that reverses stock has to be named here, once, or its
reversal either creates a layer it should not or peels the wrong one.

A ``reference_type`` is a free string on ``StockMovement``; this module is the only
place that gives specific values a costing meaning.
"""

# Inbound movements that put stock back at a cost already known (a cancelled sale,
# a returned issue). They must NOT start a fresh FIFO layer: the caller restores the
# layers the original outbound peeled (``restore_fifo_peels``) instead.
RESTORE_INBOUND_REFS = frozenset({
    "sales_invoice_cancel",
    "sales_invoice_cancel_challan",
    "delivery_challan_cancel",
    "work_order_cancel",
    "stock_transfer_cancel",
    "purchase_return_cancel",
    "purchase_return_damaged_cancel",
    "sales_return_damaged_cancel",
    # Manufacturing (MFG-06/07/08/13)
    "mfg_return",
    "mfg_issue_reverse",
    # Job work (MFG-24)
    "jobwork_return",
    "jobwork_challan_reverse",
})

# Outbound movements that take away one specific inbound layer (the caller calls
# ``retire_source_layers``). They must NOT peel the oldest layer first.
RETIRE_SPECIFIC_LAYER_REFS = frozenset({
    "purchase_invoice_cancel",
    "purchase_invoice_edit",
    "purchase_return",
    "purchase_return_damaged",
    "stock_transfer_cancel",
    "work_order_cancel",
    "sales_return_cancel",
    # Manufacturing
    "mfg_receipt_reverse",
    "mfg_return_reverse",
    # Job work
    "jobwork_challan_reverse",
})

# Reference types manufacturing and job work are allowed to use on a stock movement.
# A test fails when a ``reference_type=`` literal in those apps is missing here.
MANUFACTURING_REFS = frozenset({
    "work_order",            # legacy auto-issue / complete
    "work_order_cancel",
    "mfg_issue",
    "mfg_issue_reverse",
    "mfg_return",
    "mfg_return_reverse",
    "mfg_receipt",
    "mfg_receipt_reverse",
    "mfg_backflush",
    "mfg_rework",
    "mfg_revalue",
    "mfg_revalue_reverse",
    "jobwork_challan",
    "jobwork_challan_reverse",
    "jobwork_receipt",
    "jobwork_return",
    "jobwork_scrap_retained",
})

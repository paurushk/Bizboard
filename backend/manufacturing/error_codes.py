"""Stable codes the manufacturing services put on a rule error (the ``code`` field of the response).

The web screens branch on these (for example to link to the document that blocks a reversal)
and the help pages explain them. The sentence beside each code is the plain-language meaning.
These are separate from ``core.help_codes``, which holds the general help-centre intents.
"""

ERROR_CODES = {
    # Recipes
    "MFG_NO_ACTIVE_BOM": "The product has no active recipe for that date.",
    "MFG_BOM_LOCKED": "A work order used this recipe revision, so it can no longer be changed.",
    "MFG_BOM_NOT_ACTIVE": "Only an active recipe can be released into a work order.",
    "MFG_BOM_CYCLE": "The recipe contains itself somewhere down its materials.",
    "MFG_BOM_SELF_COMPONENT": "A recipe cannot list its own finished good as a material.",
    "MFG_REVISION_OVERLAP": "A new revision cannot start before one that already started.",
    "MFG_BAD_LINE_UNIT": "A material's unit must be its own unit or its alternate unit.",
    "MFG_BAD_SCRAP_PCT": "Scrap percentage must be from 0 to under 100.",
    "MFG_BAD_YIELD": "Yield must be above 0 and at most 100 percent.",
    "MFG_BAD_BATCH_SIZE": "The recipe's batch size must be above zero.",
    "MFG_BAD_CONVERSION": "A unit conversion rate must be above zero.",
    "MFG_BAD_COST_SHARE": "Cost shares are wrong: co-products add up to over 100, or a by-product has a share.",
    "MFG_OUTPUT_IS_MAIN": "An output cannot be the finished good itself.",
    "MFG_OUTPUT_IS_COMPONENT": "An item cannot be both a material and an output of the same recipe.",
    "MFG_NOT_AN_ALTERNATE": "That material is not a listed alternate for the line.",
    "MFG_NO_SUCH_REPORT": "There is no report with that name.",
    "MFG_BOM_TOO_DEEP": "The recipe goes deeper than 10 levels.",
    "MFG_NO_COST_ACCESS": "Your role cannot see costs.",
    "MFG_BAD_PRIORITY": "Priority is from 1 (most urgent) to 5.",
    "MFG_BAD_DELAY_REASON": "That delay reason is not one of the listed reasons.",
    "MFG_MRP_SUPERSEDED": "A newer material plan has replaced this one.",
    "MFG_IMPORT_EMPTY": "The uploaded file has no rows.",
    "MFG_IMPORT_COLUMNS": "The uploaded file is missing required columns.",
    # Work orders
    "MFG_BAD_WO_STATUS": "The work order is in a status that cannot take this action.",
    "MFG_NO_LINES": "The work order has no materials.",
    "MFG_LEGACY_MODE": "This work order issues all its materials at release, so it has no issue documents.",
    "MFG_MODE_SWITCH_BLOCKED": "Finish or cancel released work orders before changing how materials are issued.",
    "MFG_CANCEL_REVERSE_FIRST": "Documents are posted on this work order; reverse them before cancelling.",
    "MFG_NOTHING_RECEIVED": "Post a production receipt before completing the work order.",
    # Documents
    "MFG_DOC_NOT_DRAFT": "The document has already been posted.",
    "MFG_DOC_NOT_POSTED": "Only a posted document can be reversed.",
    "MFG_EMPTY_DOC": "A document needs at least one line.",
    "MFG_REASON_REQUIRED": "A reason is needed.",
    "MFG_REVERSAL_ORDER": "Something posted later depends on this document; reverse that first.",
    "MFG_BAD_QTY": "Quantity must be above zero.",
    "MFG_BAD_REFERENCE": "A referenced record does not belong to this company.",
    "MFG_BAD_WO_LINE": "That material line is not part of this work order.",
    "MFG_LINE_NEEDS_COMPONENT": "A line must name a material or output.",
    "MFG_BAD_OUTPUT": "The output lines do not match what this work order makes.",
    "MFG_BAD_LOT_ALLOCATION": "The lot allocations do not match the quantity or the item.",
    "MFG_PRINCIPAL_MATERIAL": "Material the customer supplied is not issued from our own stock.",
    # Stock
    "MFG_SHORT_STOCK": "Not enough stock to issue.",
    "MFG_SERIALS_REQUIRED": "Serial numbers are required for this material.",
    "MFG_SERIAL_REWORK_UNSUPPORTED": "Rework and rejected units are not supported for serial-tracked items.",
    "MFG_NOTHING_TO_ISSUE": "Everything the work order needs has already been issued.",
    "MFG_EXTRA_NEEDS_REASON": "Issuing more than the order needs requires a reason.",
    "MFG_EXTRA_NEEDS_MANAGER": "Issuing this far over the plan needs a manager.",
    "MFG_APPROVAL_PENDING": "A manager has already been asked about this issue.",
    "MFG_APPROVAL_NOT_NEEDED": "This issue is within the plan, so no approval is needed.",
    "MFG_APPROVAL_NONE": "There is no open approval request on this issue.",
    "MFG_OVER_RETURN": "More is being returned than is out on the work order.",
    "MFG_OVER_RECEIPT": "The receipt would take output beyond the allowed overage on the plan.",
    "MFG_BATCH_MISMATCH": "The batch already exists with different dates.",
    # Cost
    "MFG_ZERO_COST_COMPLETE": "The materials have no cost on record, so the output cannot be valued.",
    "MFG_RECEIPT_EXCEEDS_WIP": "The receipt costs more than the materials issued so far.",
    # Dates
    "MFG_FUTURE_DATE": "A document cannot be dated in the future.",
    "MFG_BACKDATE_NEEDS_MANAGER": "Entries this far back need a manager.",
    # Shop floor
    "MFG_BAD_PERIOD": "The period is not valid: the start date must not be after the end date.",
    "MFG_BAD_PIN": "A PIN must be 4 to 8 digits.",
    "MFG_BAD_SEQUENCE": "Routing steps need unique, positive sequence numbers.",
    "MFG_BREAKDOWN_OPEN": "The machine already has an open breakdown.",
    "MFG_BREAKDOWN_CLOSED": "That breakdown is already resolved.",
    "MFG_CARD_DONE": "The job card is already finished.",
    "MFG_CARD_NOT_DONE": "Only a finished job card can be reopened.",
    "MFG_CARD_NOT_RUNNING": "The job card is not running.",
    "MFG_CARD_SUBCONTRACT": "A subcontracted step is tracked through job work, not on the floor.",
    "MFG_DOWNTIME_OPEN": "The work centre already has downtime running.",
    "MFG_DOWNTIME_CLOSED": "That downtime has already ended.",
    "MFG_LOGIN_FAILED": "The operator code or PIN is wrong.",
    "MFG_LOGIN_LOCKED": "Too many wrong PINs; try again after the lock ends.",
    "MFG_OPERATOR_EXISTS": "An operator with that code already exists.",
    "MFG_NOT_FOUND": "That record was not found.",
    "MFG_BOM_EMPTY": "A recipe needs at least one material before it can be used.",
    "MFG_BAD_INPUT": "A number, date or id in the request could not be read.",
    # Operation-wise subcontracting
    "MFG_SUBCONTRACT_NOT_STEP": "This step is done in the factory, not by a job worker.",
    "MFG_SUBCONTRACT_RAISED": "Job work has already been raised for this step.",
    "MFG_SUBCONTRACT_NO_WORKER": "Choose the job worker for this step.",
    "MFG_SUBCONTRACT_NO_LINES": "There is no material left to send.",
    "MFG_SUBCONTRACT_OPEN": "A step is still with the job worker.",
    # Standard-cost revaluation
    "MFG_REVAL_NO_STANDARD": "The item has no standard cost in force on that date.",
    "MFG_REVAL_SERIAL": "Stock tracked by serial number cannot be re-priced in bulk.",
    "MFG_REVAL_FUTURE": "A revaluation cannot use a date in the future.",
    "MFG_REVAL_NOTHING": "Stock on hand is already at the standard cost.",
    "MFG_REVAL_MOVED": "The stock has moved since it was re-priced, so the run cannot be reversed as a whole.",
}

# Not errors: journal source types and flag names that also start with MFG_.
NOT_ERROR_CODES = frozenset({
    "MFG_ABSORB", "MFG_JOBCARD", "MFG_CLOSE", "MFG_ISSUE", "MFG_RECEIPT", "MFG_RETURN",
    "MFG_REVALUE", "MFG_PLANNING", "MFG_QUALITY", "MFG_JOB_WORK", "MFG_COSTING_GL", "MFG_SHOP_FLOOR",
})

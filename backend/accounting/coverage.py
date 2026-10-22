"""WP-F1 / DIM6-02: the ledger coverage registry.

Every ``source_type`` that ``PostingService.post`` is called with must be listed here, with
the module that posts it, the accounts it touches, the invariants that check it, and the
flag (if any) that must be on for it to post. ``PostingService.post`` enforces this:
under ``LEDGER_REGISTRY_STRICT`` (test settings) an unregistered source type raises, so
the whole test suite is the completeness check; in production it is logged.

``NOT_POSTED`` lists events that move money, stock or tax but deliberately do not post,
with the reason. The Trial balance screen shows the flag-gated rows that are off for a
company as "not in the books yet" (``ledger_gaps``).

``python manage.py ledger_coverage_map --write`` regenerates
``docs/accounting/LEDGER_COVERAGE_MAP.md``; ``tests/test_ledger_coverage.py`` fails when
that file is stale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GL = ("gl.journals_balanced", "gl.trial_balance_zero", "gl.no_orphan_lines")
PARTY = (*GL, "gl.party_subledger_complete")


@dataclass(frozen=True)
class Source:
    label: str
    posted_by: str
    accounts: str
    invariants: tuple[str, ...] = GL
    flag: str | None = None
    flag_note: str = ""
    extra: dict = field(default_factory=dict)


POSTING_SOURCES: dict[str, Source] = {
    "SALES_INVOICE": Source(
        "Sales invoice", "accounting/services.py", "AR 1200 / revenue / output GST / round-off", PARTY,
    ),
    "SALES_RETURN": Source("Sales return", "accounting/services.py", "revenue / output GST / AR or cash", PARTY),
    "SALES_CREDIT_NOTE": Source("Sales credit note", "accounting/services.py", "revenue or discount / output GST / AR", PARTY),
    "SALES_DEBIT_NOTE": Source("Sales debit note", "accounting/services.py", "AR / revenue / output GST", PARTY),
    "PURCHASE_INVOICE": Source("Purchase bill", "accounting/services.py", "AP 2100 / purchases or stock / input GST", PARTY),
    "PURCHASE_RETURN": Source("Purchase return", "accounting/services.py", "AP / purchases / input GST", PARTY),
    "PURCHASE_CREDIT_NOTE": Source("Purchase credit note", "accounting/services.py", "AP / purchases / input GST", PARTY),
    "PURCHASE_DEBIT_NOTE": Source("Purchase debit note", "accounting/services.py", "AP / purchases / input GST", PARTY),
    "CUSTOMER_RECEIPT": Source("Customer receipt", "accounting/services.py", "cash or bank / AR / TDS receivable / discount", PARTY),
    "CUSTOMER_ADVANCE_REFUND": Source("Customer advance refund", "accounting/services.py", "AR (advance) / cash or bank", PARTY),
    "SUPPLIER_PAYMENT": Source("Supplier payment", "payments/services.py", "AP / cash or bank / TDS payable", PARTY),
    "PAYMENT_ALLOCATION": Source("Payment allocation", "accounting/services.py", "AR or AP party ledgers", PARTY),
    "CHEQUE_DISHONOUR": Source("Bounced cheque", "accounting/services.py", "bank / AR", PARTY),
    "POS_REFUND": Source("Point-of-sale refund", "sales/pos_refunds.py", "cash / revenue / output GST"),
    "EXPENSE": Source("Expense", "accounting/expense_posting.py", "expense heads / input GST / cash, bank or AP"),
    "PAY_RUN": Source("Payroll run", "payroll/services.py", "salary expense / payables / statutory dues"),
    "BANK_ACCOUNT": Source("Bank account opening balance", "accounting/services.py", "bank / opening balance equity"),
    "BANK_LINE_ENTRY": Source("Bank statement line booked", "accounting/bank_match.py", "bank / chosen head"),
    "BANK_RECON_WRITE_OFF": Source("Bank reconciliation write-off", "accounting/bank_match.py", "bank / write-off head"),
    "MANUAL_JOURNAL": Source("Manual journal", "accounting/views.py", "any active account"),
    "JOURNAL_REVERSAL": Source("Journal reversal", "accounting/services.py", "mirror of the reversed entry"),
    "FY_CLOSE": Source("Financial-year close", "accounting/reports.py", "P&L heads / retained earnings"),
    "EQUITY": Source("Opening equity", "accounting/reports.py", "opening balance equity"),
    "STOCK_MOVEMENT": Source(
        "Stock adjustment, count, expiry and serial write-off", "accounting/services.py",
        "inventory / stock adjustment expense",
        (*GL, "inventory.balance_equals_movements"),
        flag="ACCOUNTING_POST_STOCK_ADJUSTMENTS",
        flag_note="Off until CA sign-off (WP-F3); until then stock value changes from adjustments are not in the books.",
    ),
    "WORK_ORDER": Source(
        "Work order (legacy costing)", "manufacturing/services/legacy.py", "WIP / inventory",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_ISSUE": Source(
        "Material issued to production", "manufacturing/services/issue.py", "WIP / raw-material inventory",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_RETURN": Source(
        "Material returned from production", "manufacturing/services/issue.py", "raw-material inventory / WIP",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_RECEIPT": Source(
        "Finished goods received", "manufacturing/services/receipt.py", "finished-goods inventory / WIP",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_ABSORB": Source(
        "Overhead absorbed", "manufacturing/services/receipt.py", "WIP / overhead absorbed",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_JOBCARD": Source(
        "Job card labour and machine cost", "manufacturing/services/shopfloor.py", "WIP / labour and machine absorbed",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_CLOSE": Source(
        "Work order close variance", "manufacturing/services/flow.py", "WIP / production variance",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "MFG_REVALUE": Source(
        "Standard-cost revaluation", "manufacturing/services/revaluation.py", "inventory / revaluation reserve",
        flag="MFG_COSTING_GL", flag_note="Off until CA sign-off on production costing (QOS-0141).",
    ),
    "JW_RECEIPT": Source("Job-work receipt", "jobwork/services/out.py", "inventory / job-work charges / AP", PARTY),
    "FIXED_ASSET": Source(
        "Fixed asset acquisition, depreciation, disposal", "accounting/depreciation.py",
        "fixed assets 1600 / accumulated depreciation / depreciation expense",
        flag="ENABLE_FIXED_ASSETS",
        flag_note="Known limitation D6: track assets and post depreciation manually.",
    ),
    "BILL_OF_ENTRY": Source(
        "Import bill of entry", "purchases/boe_services.py", "inventory / customs duty / IGST input",
        flag="ENABLE_BOE", flag_note="Known limitation D10: import purchases are booked as ordinary bills.",
    ),
}

NOT_POSTED: dict[str, str] = {
    "Stock transfer between godowns": "Moves quantity only; value stays in the same inventory account.",
    "Delivery challan": "No change of ownership; the invoice posts when raised.",
    "Quotation and sales order": "Commitments, not transactions.",
    "Purchase order and goods received note": "The purchase bill posts; the GRN only moves stock.",
    "Stock reservation": "Holds quantity for an order; no value moves.",
    "Payment link created": "Posts only when the customer pays (CUSTOMER_RECEIPT).",
    "Perpetual FIFO cost of goods sold": "Out of scope (QOS-0072); COGS follows the valuation method in reports.",
}


def source(source_type: str) -> Source | None:
    return POSTING_SOURCES.get(source_type)


def ledger_gaps(company) -> list[dict]:
    """Flag-gated posting sources that are OFF for this company: shown on the Trial balance."""
    from core.services.feature_flags import flag_enabled

    seen: set[str] = set()
    out: list[dict] = []
    for src in POSTING_SOURCES.values():
        if not src.flag or src.flag in seen:
            continue
        seen.add(src.flag)
        try:
            on = flag_enabled(company, src.flag)
        except Exception:  # noqa: BLE001 - an unknown flag is treated as off
            on = False
        if not on:
            labels = [s.label for s in POSTING_SOURCES.values() if s.flag == src.flag]
            out.append({"flag": src.flag, "covers": labels, "note": src.flag_note})
    return out


def render_markdown() -> str:
    lines = [
        "# Ledger coverage map",
        "",
        "<!-- GENERATED by `python manage.py ledger_coverage_map --write` from accounting/coverage.py."
        " Do not edit by hand; tests/test_ledger_coverage.py fails when this file is stale. -->",
        "",
        "Every event that posts to the general ledger, who posts it, which accounts it touches,",
        "which invariants check it, and the flag that must be on. A flag-gated row that is off",
        "for a company is listed on that company's Trial balance as *not in the books yet*.",
        "",
        "| Source type | Event | Posted by | Accounts | Checked by | Needs flag |",
        "|---|---|---|---|---|---|",
    ]
    for st in sorted(POSTING_SOURCES):
        s = POSTING_SOURCES[st]
        flag = f"`{s.flag}` — {s.flag_note}" if s.flag else "always"
        checks = ", ".join(f"`{k}`" for k in s.invariants)
        lines.append(f"| `{st}` | {s.label} | `{s.posted_by}` | {s.accounts} | {checks} | {flag} |")
    lines += ["", "## Not posted on purpose", "", "| Event | Why |", "|---|---|"]
    for event in sorted(NOT_POSTED):
        lines.append(f"| {event} | {NOT_POSTED[event]} |")
    lines.append("")
    return "\n".join(lines)

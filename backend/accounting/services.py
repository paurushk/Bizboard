from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import Account, AccountingPeriod, JournalEntry, JournalLine


CHART = (
    ("1000", "Assets", "ASSET", False), ("1100", "Cash", "ASSET", True),
    ("1200", "Accounts Receivable", "ASSET", True),
    ("1300", "Input GST", "ASSET", False),
    ("1310", "Input CGST", "ASSET", True),
    ("1320", "Input SGST", "ASSET", True),
    ("1330", "Input IGST", "ASSET", True),
    ("1400", "Inventory", "ASSET", True),
    ("1450", "Work in Progress", "ASSET", True),
    ("1500", "Bank", "ASSET", True),
    ("2150", "Wages Payable", "LIABILITY", True),
    ("1600", "Fixed Assets", "ASSET", True), ("1650", "Accumulated Depreciation", "ASSET", True),
    ("2000", "Liabilities", "LIABILITY", False), ("2100", "Accounts Payable", "LIABILITY", True),
    ("2200", "Output GST", "LIABILITY", False),
    ("2210", "Output CGST", "LIABILITY", True),
    ("2220", "Output SGST", "LIABILITY", True),
    ("2230", "Output IGST", "LIABILITY", True),
    ("2240", "RCM CGST Payable", "LIABILITY", True),
    ("2250", "RCM SGST Payable", "LIABILITY", True),
    ("2260", "RCM IGST Payable", "LIABILITY", True),
    ("2261", "PF Payable", "LIABILITY", True),
    ("2262", "ESI Payable", "LIABILITY", True),
    ("2263", "PT Payable", "LIABILITY", True),
    ("2265", "TDS Payable", "LIABILITY", True),
    ("2266", "TCS Payable", "LIABILITY", True),
    ("1365", "TCS Receivable", "ASSET", True),
    ("2270", "Output Cess", "LIABILITY", True),
    ("1370", "Input Cess", "ASSET", True),
    ("1390", "ITC Unreviewed (suspense)", "ASSET", True),
    ("2280", "RCM Cess Payable", "LIABILITY", True),
    ("3000", "Equity", "EQUITY", False),
    ("3100", "Retained Earnings", "EQUITY", True),
    ("3200", "Opening Balance Equity", "EQUITY", True),
    ("4000", "Income", "INCOME", False),
    ("4100", "Sales", "INCOME", True), ("5000", "Expenses", "EXPENSE", False),
    ("5100", "Purchases", "EXPENSE", True),
    ("5110", "Purchase Charges", "EXPENSE", True),
    ("5200", "Bank Charges", "EXPENSE", True),
    ("5300", "Depreciation", "EXPENSE", True), ("5400", "Cost of Goods Sold", "EXPENSE", True),
    # BB-000322: explicit rounding suspense so Complete-time paise round-off is
    # never silently absorbed into Sales/Purchases/Inventory.
    ("5500", "Round Off", "EXPENSE", True),
    # BB-000459: disposal P&L — never write NBV off to Depreciation (5300).
    ("5600", "Loss on Disposal of Assets", "EXPENSE", True),
    ("5700", "Gain on Disposal of Assets", "INCOME", True),
    ("5800", "Salaries and Wages", "EXPENSE", True),
    # BB-000382: advances (unallocated cash) — not AR/AP control.
    ("2300", "Customer Advances", "LIABILITY", True),
    ("1250", "Supplier Advances", "ASSET", True),
)

# Leaf GST accounts under their xx00 parent header.
_CHART_PARENTS = {
    "1310": "1300", "1320": "1300", "1330": "1300",
    "2210": "2200", "2220": "2200", "2230": "2200",
    "2240": "2200", "2250": "2200", "2260": "2200",
    "2261": "2200", "2262": "2200", "2263": "2200",
    "2265": "2200", "2266": "2200", "1365": "1300",
    "1390": "1300",
    "2270": "2200", "2280": "2200", "1370": "1300",
    "1450": "1000",
    "2150": "2000",
    "5800": "5000",
}


def seed_chart_of_accounts(company, user=None):
    accounts = {}
    for code, name, account_type, is_control in CHART:
        account, _ = Account.objects.get_or_create(
            company=company, code=code,
            defaults={"name": name, "type": account_type, "is_system": True, "is_control": is_control,
                      "created_by": user, "updated_by": user},
        )
        accounts[code] = account
    for code, _, _, _ in CHART:
        if len(code) == 4 and code.endswith("00") and code[1:] != "000":
            accounts[code].parent = accounts[f"{code[0]}000"]
            accounts[code].save(update_fields=["parent"])
    for code, parent_code in _CHART_PARENTS.items():
        if code in accounts and parent_code in accounts:
            if accounts[code].parent_id != accounts[parent_code].id:
                accounts[code].parent = accounts[parent_code]
                accounts[code].save(update_fields=["parent"])
    return accounts


class PostingService:
    """Creates immutable, idempotent projections of operational documents.

    Trusted-internal service: callers (document complete handlers, management
    commands, Celery tasks) are responsible for authorization. HTTP views that
    expose posting must enforce RBAC (e.g. CanPostJournals / IsOwner) before
    invoking post/reverse — this class does not check actor capabilities
    (BB-000312).
    """

    @staticmethod
    def _ensure_chart(company):
        """Ensure Wave-3 GST split + RCM + disposal accounts exist (auto-seed if missing)."""
        required = (
            "1310", "1320", "1330", "1370", "2210", "2220", "2230", "2240", "2250", "2260",
            "2270", "2280",
            "1450",  # manufacturing WIP
            "2150", "5800",  # payroll wages payable + salary expense
            "5600", "5700",  # BB-000459 disposal P&L
            "2265", "2266", "1365", "1390",  # BB-000670 TDS/TCS + unreviewed ITC suspense
            "3100", "3200",
        )
        existing = set(
            Account.objects.filter(company=company, code__in=required, is_active=True)
            .values_list("code", flat=True)
        )
        if len(existing) < len(required):
            seed_chart_of_accounts(company)

    @staticmethod
    def _account(company, code):
        acct = Account.objects.filter(company=company, code=code, is_active=True).first()
        if acct is not None:
            return acct
        # Not active — either missing (seed it) or a system account was
        # deactivated/renamed (R3-011: don't 500 on every Complete — recover).
        seed_chart_of_accounts(company)
        acct = Account.objects.filter(company=company, code=code, is_active=True).first()
        if acct is not None:
            return acct
        inactive = Account.objects.filter(company=company, code=code).first()
        if inactive is not None and getattr(inactive, "is_system", False):
            inactive.is_active = True
            inactive.save(update_fields=["is_active", "updated_at"])
            return inactive
        raise BusinessRuleError(
            f"Required system ledger account '{code}' is missing or has been "
            "deactivated. Restore the chart of accounts before posting."
        )

    @classmethod
    def _tax_component_lines(cls, company, mapping, *, side, cost_center=None):
        """Build debit/credit lines for (code, amount) pairs where amount > 0."""
        lines = []
        for code, amount in mapping:
            amt = Decimal(str(amount or 0))
            if not amt:
                continue
            line = {"account": cls._account(company, code)}
            line[side] = amt
            if cost_center is not None:
                line["cost_center"] = cost_center
            lines.append(line)
        return lines

    @classmethod
    def _round_off_line(cls, company, round_off, *, side, cost_center=None):
        """
        BB-000322: explicit 5500 Round Off leg instead of silently folding
        paise rounding into Sales/Purchases/Inventory. `side` is the side the
        associated value (revenue/inventory) line normally sits on — a
        negative round_off posts to the opposite side so the entry stays
        balanced (see post_sales_invoice / post_purchase / post_note).
        """
        amt = Decimal(str(round_off or 0))
        if amt == 0:
            return None
        line = {"account": cls._account(company, "5500")}
        if amt > 0:
            line[side] = amt
        else:
            opposite = "credit" if side == "debit" else "debit"
            line[opposite] = -amt
        if cost_center is not None:
            line["cost_center"] = cost_center
        return line

    @staticmethod
    def _note_is_rcm(note) -> bool:
        """BB-000336: purchase notes inherit RCM-ness from their linked invoice."""
        invoice = getattr(note, "purchase_invoice", None)
        return bool(invoice and getattr(invoice, "is_reverse_charge", False))

    @classmethod
    def _purchase_itc_input_lines(cls, invoice, *, cgst, sgst, igst, cess, side, cost_center=None):
        """Map ITC eligibility to GL: CLAIMABLE 1310-1330, UNREVIEWED 1390, else capitalize."""
        from purchases.models import PurchaseInvoice as _PI

        itc = getattr(invoice, "itc_eligibility", None) or _PI.ItcEligibility.UNREVIEWED
        tax = (
            Decimal(str(cgst or 0))
            + Decimal(str(sgst or 0))
            + Decimal(str(igst or 0))
            + Decimal(str(cess or 0))
        )
        capitalize = itc in (_PI.ItcEligibility.INELIGIBLE, _PI.ItcEligibility.REVERSED)
        if capitalize:
            return [], tax
        if not getattr(invoice, "is_reverse_charge", False) and itc == _PI.ItcEligibility.UNREVIEWED:
            return (
                cls._tax_component_lines(
                    invoice.company, (("1390", tax),), side=side, cost_center=cost_center
                ),
                Decimal("0"),
            )
        return (
            cls._tax_component_lines(
                invoice.company,
                (("1310", cgst), ("1320", sgst), ("1330", igst), ("1370", cess)),
                side=side,
                cost_center=cost_center,
            ),
            Decimal("0"),
        )

    @classmethod
    @transaction.atomic
    def post(cls, *, company, source_type, source_id, purpose, entry_date, lines, narration="", user=None, allow_soft_closed=False):
        if not company.accounting_enabled:
            return None
        # R3-009: `uniq_accounting_source_posting` (company, source_type,
        # source_id, purpose | source_id NOT NULL & status=POSTED) is the real
        # guard against a concurrent double-post — this `.first()` is only the
        # fast path.
        existing = JournalEntry.objects.filter(
            company=company, source_type=source_type, source_id=source_id, purpose=purpose,
            status=JournalEntry.Status.POSTED,
        ).first()
        if existing:
            return existing
        debit = sum((Decimal(str(line.get("debit", 0))) for line in lines), Decimal("0"))
        credit = sum((Decimal(str(line.get("credit", 0))) for line in lines), Decimal("0"))
        if not lines or debit != credit:
            raise BusinessRuleError("Journal posting must contain balanced debit and credit lines.")
        blocking_statuses = [AccountingPeriod.Status.CLOSED]
        if not allow_soft_closed:
            blocking_statuses.append(AccountingPeriod.Status.SOFT_CLOSED)
        if AccountingPeriod.objects.filter(
            company=company, start_date__lte=entry_date, end_date__gte=entry_date,
            status__in=blocking_statuses,
        ).exists():
            raise BusinessRuleError("Cannot post to a closed accounting period.")
        # BB-000432: sequential journal numbers unique per company.
        from core.services.document_numbers import DocumentNumberService

        number = DocumentNumberService.next_number(company, "JOURNAL_ENTRY")
        from django.db import IntegrityError

        try:
            with transaction.atomic():
                entry = JournalEntry.objects.create(
                    company=company, number=number, entry_date=entry_date,
                    status=JournalEntry.Status.POSTED, source_type=source_type, source_id=source_id,
                    purpose=purpose, narration=narration, posted_at=timezone.now(), posted_by=user,
                    created_by=user, updated_by=user,
                )
        except IntegrityError:
            # R3-009: a concurrent Complete won the `uniq_accounting_source_posting`
            # race — replay its entry instead of surfacing a 400/500.
            existing = JournalEntry.objects.filter(
                company=company, source_type=source_type, source_id=source_id, purpose=purpose,
                status=JournalEntry.Status.POSTED,
            ).first()
            if existing is not None:
                return existing
            raise
        JournalLine.objects.bulk_create([
            JournalLine(
                company=entry.company,
                entry=entry,
                account=line["account"],
                debit=Decimal(str(line.get("debit", 0))),
                credit=Decimal(str(line.get("credit", 0))),
                cost_center=line.get("cost_center"),
                dimension=line.get("dimension", ""),
                customer=line.get("customer"),
                supplier=line.get("supplier"),
            )
            for line in lines
        ])
        return entry

    @classmethod
    def post_sales_invoice(cls, invoice, user=None):
        cls._ensure_chart(invoice.company)
        # BB-000448: refuse header/line tax drift before posting Output GST.
        items = list(invoice.items.all())
        line_cgst = sum((Decimal(str(getattr(li, "cgst", 0) or 0)) for li in items), Decimal("0"))
        line_sgst = sum((Decimal(str(getattr(li, "sgst", 0) or 0)) for li in items), Decimal("0"))
        line_igst = sum((Decimal(str(getattr(li, "igst", 0) or 0)) for li in items), Decimal("0"))
        line_cess = sum((Decimal(str(getattr(li, "cess", 0) or 0)) for li in items), Decimal("0"))
        hdr_cgst = Decimal(str(invoice.cgst_total or 0))
        hdr_sgst = Decimal(str(invoice.sgst_total or 0))
        hdr_igst = Decimal(str(invoice.igst_total or 0))
        hdr_cess = Decimal(str(getattr(invoice, "cess_total", 0) or 0))
        drift = (
            abs(line_cgst - hdr_cgst)
            + abs(line_sgst - hdr_sgst)
            + abs(line_igst - hdr_igst)
            + abs(line_cess - hdr_cess)
        )
        if drift > Decimal("0.05"):
            raise BusinessRuleError(
                "Invoice tax headers do not match line tax totals; cannot post GL."
            )
        round_off = Decimal(str(getattr(invoice, "round_off", 0) or 0))
        # BB-000695: sales RCM — seller does not book Output GST; AR = taxable (+charges/round).
        if getattr(invoice, "is_reverse_charge", False):
            taxable = Decimal(str(invoice.taxable_total or 0))
            charges = Decimal(str(getattr(invoice, "additional_charges", 0) or 0))
            discount = Decimal(str(getattr(invoice, "invoice_discount", 0) or 0))
            disc_mode = getattr(invoice, "invoice_discount_mode", "")
            after_tax_disc = discount if str(disc_mode).upper() == "AFTER_TAX" else Decimal("0")
            tcs_amount = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
            sales_credit = taxable + charges - after_tax_disc
            ar_amount = sales_credit + round_off + tcs_amount
            lines = [
                {
                    "account": cls._account(invoice.company, "1200"),
                    "debit": ar_amount,
                    "cost_center": invoice.cost_center,
                    "customer": invoice.customer,
                },
                {
                    "account": cls._account(invoice.company, "4100"),
                    "credit": sales_credit,
                    "cost_center": invoice.cost_center,
                },
            ]
            if tcs_amount > 0:
                lines.append({
                    "account": cls._account(invoice.company, "2266"),
                    "credit": tcs_amount,
                    "cost_center": invoice.cost_center,
                })
            round_off_line = cls._round_off_line(
                invoice.company, round_off, side="credit", cost_center=invoice.cost_center
            )
            if round_off_line:
                lines.append(round_off_line)
            return cls.post(
                company=invoice.company,
                source_type="SALES_INVOICE",
                source_id=invoice.id,
                purpose="COMPLETE",
                entry_date=invoice.invoice_date,
                user=user,
                narration=invoice.number,
                lines=lines,
            )
        # R3-015: post the Output GST legs from the LINE tax sums, so the GST
        # liability accounts tie exactly to the filed GSTR-1 line values. Any
        # (≤5 paise) header-vs-line discrepancy goes to 5500 Round Off, not
        # silently into revenue.
        tax_lines = cls._tax_component_lines(
            invoice.company,
            (
                ("2210", line_cgst),
                ("2220", line_sgst),
                ("2230", line_igst),
                ("2270", line_cess),
            ),
            side="credit",
            cost_center=invoice.cost_center,
        )
        hdr_tax = hdr_cgst + hdr_sgst + hdr_igst + hdr_cess
        line_tax = line_cgst + line_sgst + line_igst + line_cess
        tax_drift = hdr_tax - line_tax  # ±, |x| ≤ 0.05
        tax = hdr_tax
        tcs_amount = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
        tcs_folded = bool(getattr(invoice, "tcs_in_grand_total", False))
        sales_credit = invoice.grand_total - tax - round_off
        if tcs_folded:
            sales_credit = sales_credit - tcs_amount
        lines = [
            {
                "account": cls._account(invoice.company, "1200"),
                "debit": invoice.grand_total,
                "cost_center": invoice.cost_center,
                "customer": invoice.customer,
            },
            {"account": cls._account(invoice.company, "4100"), "credit": sales_credit, "cost_center": invoice.cost_center},
            *tax_lines,
        ]
        round_off_line = cls._round_off_line(invoice.company, round_off, side="credit", cost_center=invoice.cost_center)
        if round_off_line:
            lines.append(round_off_line)
        # R3-015: header-vs-line tax discrepancy → 5500, keeping the entry
        # balanced (revenue is still tied to grand_total via `tax`=hdr_tax).
        if tax_drift != 0:
            lines.append(cls._round_off_line(
                invoice.company, tax_drift, side="credit", cost_center=invoice.cost_center,
            ))
        # BB-000711: post TCS whenever collected — do not gate on ENABLE_TDS.
        # When TCS is already folded into grand_total, AR is not debited again.
        if tcs_amount > 0:
            if not tcs_folded:
                lines.append({
                    "account": cls._account(invoice.company, "1200"),
                    "debit": tcs_amount,
                    "cost_center": invoice.cost_center,
                    "customer": invoice.customer,
                })
            lines.append({
                "account": cls._account(invoice.company, "2266"),
                "credit": tcs_amount,
                "cost_center": invoice.cost_center,
            })
        return cls.post(company=invoice.company, source_type="SALES_INVOICE", source_id=invoice.id,
            purpose="COMPLETE", entry_date=invoice.invoice_date, user=user, narration=invoice.number,
            lines=lines)

    @classmethod
    def post_opening_sales_invoice(cls, invoice, user=None):
        """BB-000381: opening AR vs Opening Equity — no P&L/COGS."""
        if not invoice.grand_total:
            return None
        cls._ensure_chart(invoice.company)
        return cls.post(
            company=invoice.company,
            source_type="SALES_INVOICE",
            source_id=invoice.id,
            purpose="OPENING",
            entry_date=invoice.invoice_date,
            user=user,
            narration=f"Opening AR: {invoice.number}",
            lines=[
                {
                    "account": cls._account(invoice.company, "1200"),
                    "debit": invoice.grand_total,
                    "customer": invoice.customer,
                },
                {"account": cls._account(invoice.company, "3200"), "credit": invoice.grand_total},
            ],
        )

    @classmethod
    def post_opening_purchase_invoice(cls, invoice, user=None):
        """BB-000381: opening AP vs Opening Equity — no inventory/P&L."""
        if not invoice.grand_total:
            return None
        cls._ensure_chart(invoice.company)
        return cls.post(
            company=invoice.company,
            source_type="PURCHASE_INVOICE",
            source_id=invoice.id,
            purpose="OPENING",
            entry_date=invoice.invoice_date,
            user=user,
            narration=f"Opening AP: {invoice.number}",
            lines=[
                {"account": cls._account(invoice.company, "3200"), "debit": invoice.grand_total},
                {
                    "account": cls._account(invoice.company, "2100"),
                    "credit": invoice.grand_total,
                    "supplier": invoice.supplier,
                },
            ],
        )

    @staticmethod
    def _opening_entry_date(company, fallback=None):
        """R3-017: opening-balance journals are dated to the company's books-start
        date (or the current FY start), not the row's insert timestamp."""
        books_start = getattr(company, "books_start_date", None)
        if books_start:
            return books_start
        if fallback is not None:
            return fallback
        today = timezone.localdate()
        fy_month = int(getattr(company, "fy_start_month", 4) or 4)
        year = today.year if today.month >= fy_month else today.year - 1
        from datetime import date as _date

        return _date(year, fy_month, 1)

    @classmethod
    def post_opening_stock(cls, movement, user=None):
        """Opening inventory vs Opening Balance Equity (3200), not RE 3100."""
        qty = abs(Decimal(str(movement.quantity or 0)))
        cost = Decimal(str(movement.unit_cost or 0))
        amount = (qty * cost).quantize(Decimal("0.01"))
        if not amount:
            return None
        cls._ensure_chart(movement.company)
        entry_date = cls._opening_entry_date(movement.company)
        return cls.post(
            company=movement.company,
            source_type="STOCK_MOVEMENT",
            source_id=movement.id,
            purpose="OPENING_STOCK",
            entry_date=entry_date,
            user=user,
            narration=f"Opening stock #{movement.id}",
            lines=[
                {"account": cls._account(movement.company, "1400"), "debit": amount},
                {"account": cls._account(movement.company, "3200"), "credit": amount},
            ],
        )

    @classmethod
    def post_sales_cogs(cls, invoice, amount, user=None):
        if not amount:
            return None
        cls._ensure_chart(invoice.company)
        return cls.post(company=invoice.company, source_type="SALES_INVOICE", source_id=invoice.id,
            purpose="COGS", entry_date=invoice.invoice_date, user=user, narration=f"COGS: {invoice.number}",
            lines=[{"account": cls._account(invoice.company, "5400"), "debit": amount, "cost_center": invoice.cost_center},
                   {"account": cls._account(invoice.company, "1400"), "credit": amount, "cost_center": invoice.cost_center}])

    @classmethod
    def post_sales_return_cogs(cls, sales_return, amount, user=None):
        """BB-000380: reverse COGS on return — Dr Inventory / Cr COGS."""
        if not amount:
            return None
        company = sales_return.company
        cls._ensure_chart(company)
        cc = getattr(sales_return.sales_invoice, "cost_center", None)
        return cls.post(
            company=company,
            source_type="SALES_RETURN",
            source_id=sales_return.id,
            purpose="COGS_REVERSE",
            entry_date=sales_return.return_date,
            user=user,
            narration=f"Return COGS: {sales_return.number}",
            lines=[
                {"account": cls._account(company, "1400"), "debit": amount, "cost_center": cc},
                {"account": cls._account(company, "5400"), "credit": amount, "cost_center": cc},
            ],
        )

    @classmethod
    def post_sales_return_scrap(cls, sales_return, amount, user=None):
        """Post scrap write-off for damaged return goods — Dr 5600 Loss / Cr 1400 Inventory."""
        if not amount:
            return None
        company = sales_return.company
        cls._ensure_chart(company)
        cc = getattr(sales_return.sales_invoice, "cost_center", None)
        return cls.post(
            company=company,
            source_type="SALES_RETURN",
            source_id=sales_return.id,
            purpose="DAMAGED_SCRAP",
            entry_date=sales_return.return_date,
            user=user,
            narration=f"Damaged scrap write-off: {sales_return.number}",
            lines=[
                {"account": cls._account(company, "5600"), "debit": amount, "cost_center": cc},
                {"account": cls._account(company, "1400"), "credit": amount, "cost_center": cc},
            ],
        )

    @classmethod
    def post_receipt(cls, receipt, user=None):
        """BB-000382: unallocated cash credits Customer Advances (2300), not AR.

        Gateway MDR: bank receives amount − fee; fee posts to 5200 Bank Charges.
        """
        cls._ensure_chart(receipt.company)
        code = "1500" if receipt.bank_account_id else "1100"
        amount = Decimal(str(receipt.amount or 0))
        fee = Decimal("0")
        gp = getattr(receipt, "gateway_payment", None)
        if gp is not None:
            fee = max(Decimal("0"), Decimal(str(getattr(gp, "fee", 0) or 0)))
        if fee > amount:
            fee = amount
        bank_amt = amount - fee
        lines = []
        if bank_amt > 0:
            lines.append({"account": cls._account(receipt.company, code), "debit": bank_amt})
        if fee > 0:
            lines.append({"account": cls._account(receipt.company, "5200"), "debit": fee})
        if not lines:
            lines.append({"account": cls._account(receipt.company, code), "debit": amount})
        lines.append({
            "account": cls._account(receipt.company, "2300"),
            "credit": amount,
            "customer": receipt.customer,
        })
        return cls.post(company=receipt.company, source_type="CUSTOMER_RECEIPT", source_id=receipt.id,
            purpose="CREATE", entry_date=receipt.receipt_date, user=user, narration=receipt.number,
            lines=lines)

    @classmethod
    def post_receipt_refund(cls, receipt, user=None):
        """Refund customer receipt: Dr Customer Advances (2300) / Cr Bank (1500 or 1100)."""
        cls._ensure_chart(receipt.company)
        code = "1500" if receipt.bank_account_id else "1100"
        amount = Decimal(str(receipt.amount or 0))
        if amount <= 0:
            return None
        lines = [
            {"account": cls._account(receipt.company, "2300"), "debit": amount, "customer": receipt.customer},
            {"account": cls._account(receipt.company, code), "credit": amount},
        ]
        return cls.post(
            company=receipt.company,
            source_type="CUSTOMER_RECEIPT",
            source_id=receipt.id,
            purpose="REFUND",
            entry_date=timezone.localdate(),
            user=user,
            narration=f"Refund: {receipt.number}",
            lines=lines,
        )

    @classmethod
    def post_receipt_allocation(cls, allocation, user=None):
        """BB-000382: move Advances → AR when receipt is allocated to an invoice."""
        amount = Decimal(str(allocation.amount or 0))
        if not amount:
            return None
        company = allocation.company
        cls._ensure_chart(company)
        receipt = allocation.receipt if allocation.receipt_id else None
        customer = receipt.customer if receipt is not None else None
        entry_date = receipt.receipt_date if receipt is not None else timezone.localdate()
        return cls.post(
            company=company,
            source_type="PAYMENT_ALLOCATION",
            source_id=allocation.id,
            purpose="ALLOCATE_RECEIPT",
            entry_date=entry_date,
            user=user,
            narration=f"Allocate receipt {allocation.receipt_id} → SI {allocation.sales_invoice_id}",
            lines=[
                {"account": cls._account(company, "2300"), "debit": amount, "customer": customer},
                {"account": cls._account(company, "1200"), "credit": amount, "customer": customer},
            ],
        )

    @classmethod
    def post_purchase(cls, invoice, user=None):
        """
        BB-000322: perpetual inventory — purchases debit Inventory (1400).
        BB-000400: Inventory = Σ line taxables; additional charges → 5110 expense.
        Wave 17C capitalization policy: freight/packing on purchases expense to 5110
        by default; capitalize into 1400 only when company policy sets
        capitalize_purchase_charges (not enabled in MVP — always 5110).
        """
        cls._ensure_chart(invoice.company)
        cc = invoice.cost_center
        line_taxable = sum(
            (Decimal(str(getattr(li, "taxable_amount", 0) or getattr(li, "line_total", 0) or 0))
             for li in invoice.items.all()),
            Decimal("0"),
        )
        # Prefer explicit taxable_total when present and lines empty-sum fallback.
        header_taxable = Decimal(str(getattr(invoice, "taxable_total", 0) or 0))
        if line_taxable <= 0 and header_taxable > 0:
            line_taxable = header_taxable
        cess = Decimal(str(getattr(invoice, "cess_total", 0) or 0))
        tax = (
            Decimal(str(invoice.cgst_total or 0))
            + Decimal(str(invoice.sgst_total or 0))
            + Decimal(str(invoice.igst_total or 0))
            + cess
        )
        round_off = Decimal(str(getattr(invoice, "round_off", 0) or 0))
        charges = Decimal(str(getattr(invoice, "additional_charges", 0) or 0))
        # If charges not on header, derive residual of grand_total - tax - taxable - round_off.
        if charges <= 0:
            residual = Decimal(str(invoice.grand_total or 0)) - tax - line_taxable - round_off
            if residual >= Decimal("1"):
                charges = residual
            elif residual > 0:
                # R3-012: a sub-rupee unexplained gap is line-rounding drift, not
                # freight — keep it out of 5110 Purchase Charges and let it land
                # in 5500 Round Off so the entry still balances.
                round_off = round_off + residual
        # R3-010: an AFTER_TAX invoice-level discount is not in the taxable base,
        # so grand_total (= AP credit) sits below Σtaxable+tax+charges and the
        # value legs would not balance. Net it into inventory cost.
        _inv_discount = Decimal(str(getattr(invoice, "invoice_discount", 0) or 0))
        _disc_mode = str(getattr(invoice, "invoice_discount_mode", "") or "").upper()
        after_tax_discount = (
            _inv_discount if (_inv_discount > 0 and _disc_mode == "AFTER_TAX") else Decimal("0")
        )
        inventory_amount = line_taxable
        if getattr(invoice, "is_reverse_charge", False):
            rcm_cgst = Decimal(str(getattr(invoice, "rcm_cgst", 0) or 0))
            rcm_sgst = Decimal(str(getattr(invoice, "rcm_sgst", 0) or 0))
            rcm_igst = Decimal(str(getattr(invoice, "rcm_igst", 0) or 0))
            rcm_cess = Decimal(str(getattr(invoice, "rcm_cess", 0) or 0))
            ap_credit = Decimal(str(invoice.grand_total or 0))
            tds_amount = Decimal(str(getattr(invoice, "tds_amount", 0) or 0))
            # Always net TDS from AP when present so GL outstanding matches the
            # document ledger (do not gate AP reduction on ENABLE_TDS).
            if tds_amount > 0:
                if tds_amount > ap_credit:
                    raise BusinessRuleError("TDS amount cannot exceed purchase grand total.")
                ap_credit = ap_credit - tds_amount
            itc_lines, capitalize_rcm = cls._purchase_itc_input_lines(
                invoice,
                cgst=rcm_cgst,
                sgst=rcm_sgst,
                igst=rcm_igst,
                cess=rcm_cess,
                side="debit",
                cost_center=cc,
            )
            if capitalize_rcm:
                inventory_amount = inventory_amount + capitalize_rcm
            lines = [
                {"account": cls._account(invoice.company, "1400"), "debit": inventory_amount, "cost_center": cc},
                {
                    "account": cls._account(invoice.company, "2100"),
                    "credit": ap_credit,
                    "cost_center": cc,
                    "supplier": invoice.supplier,
                },
                *cls._tax_component_lines(
                    invoice.company,
                    (("2240", rcm_cgst), ("2250", rcm_sgst), ("2260", rcm_igst), ("2280", rcm_cess)),
                    side="credit",
                    cost_center=cc,
                ),
                *itc_lines,
            ]
            # 2265 required to balance whenever AP was netted for TDS.
            if tds_amount > 0 and Decimal(str(invoice.grand_total or 0)) - ap_credit == tds_amount:
                lines.append({
                    "account": cls._account(invoice.company, "2265"),
                    "credit": tds_amount,
                    "cost_center": cc,
                    "supplier": invoice.supplier,
                })
            if charges > 0:
                lines.insert(1, {"account": cls._account(invoice.company, "5110"), "debit": charges, "cost_center": cc})
            # BB-000702: discount already nets taxable/grand — do not orphan Cr 5110 on RCM.
            round_off_line = None
        else:
            from purchases.models import PurchaseInvoice as _PI

            itc = getattr(invoice, "itc_eligibility", None) or _PI.ItcEligibility.UNREVIEWED
            # PUR-01: only INELIGIBLE/REVERSED capitalize tax into inventory.
            # UNREVIEWED posts to 1390 suspense until marked CLAIMABLE (not Input GST).
            capitalize_tax = itc in (
                _PI.ItcEligibility.INELIGIBLE,
                _PI.ItcEligibility.REVERSED,
            )
            unreviewed = itc == _PI.ItcEligibility.UNREVIEWED
            if capitalize_tax:
                inventory_amount = inventory_amount + tax
                tax_lines = []
            elif unreviewed:
                tax_lines = cls._tax_component_lines(
                    invoice.company,
                    (("1390", tax),),
                    side="debit",
                    cost_center=cc,
                )
            else:
                tax_lines = cls._tax_component_lines(
                    invoice.company,
                    (
                        ("1310", invoice.cgst_total),
                        ("1320", invoice.sgst_total),
                        ("1330", invoice.igst_total),
                        ("1370", getattr(invoice, "cess_total", 0)),
                    ),
                    side="debit",
                    cost_center=cc,
                )
            ap_credit = Decimal(str(invoice.grand_total or 0))
            tds_amount = Decimal(str(getattr(invoice, "tds_amount", 0) or 0))
            # Always net TDS from AP when present so GL outstanding matches the
            # document ledger (do not gate AP reduction on ENABLE_TDS).
            if tds_amount > 0:
                if tds_amount > ap_credit:
                    raise BusinessRuleError("TDS amount cannot exceed purchase grand total.")
                ap_credit = ap_credit - tds_amount
            lines = [
                {"account": cls._account(invoice.company, "1400"), "debit": inventory_amount, "cost_center": cc},
                *tax_lines,
                {
                    "account": cls._account(invoice.company, "2100"),
                    "credit": ap_credit,
                    "cost_center": cc,
                    "supplier": invoice.supplier,
                },
            ]
            # 2265 required to balance whenever AP was netted for TDS.
            if tds_amount > 0 and Decimal(str(invoice.grand_total or 0)) - ap_credit == tds_amount:
                lines.append({
                    "account": cls._account(invoice.company, "2265"),
                    "credit": tds_amount,
                    "cost_center": cc,
                    "supplier": invoice.supplier,
                })
            if charges > 0:
                lines.insert(1, {"account": cls._account(invoice.company, "5110"), "debit": charges, "cost_center": cc})
                # Balance: inventory+tax+charges should equal grand_total when charges carved from taxable residual.
                # If charges were already inside grand_total and inventory is line_taxable only, AP credit stays grand_total.
        if after_tax_discount > 0:
            lines.append({
                "account": cls._account(invoice.company, "1400"),
                "credit": after_tax_discount,
                "cost_center": cc,
            })
        round_off_line = cls._round_off_line(invoice.company, round_off, side="debit", cost_center=cc)
        if round_off_line:
            lines.append(round_off_line)
        return cls.post(company=invoice.company, source_type="PURCHASE_INVOICE", source_id=invoice.id,
            purpose="COMPLETE", entry_date=invoice.invoice_date, user=user, narration=invoice.number,
            lines=lines)

    @classmethod
    def post_supplier_payment(cls, payment, user=None):
        """BB-000382: unallocated supplier payment debits Supplier Advances (1250)."""
        cls._ensure_chart(payment.company)
        code = "1500" if payment.bank_account_id else "1100"
        tds = Decimal(str(getattr(payment, "tds_amount", 0) or 0))
        bank_amount = Decimal(str(payment.amount or 0))
        advance = bank_amount + tds
        lines = [{
            "account": cls._account(payment.company, "1250"),
            "debit": advance,
            "supplier": payment.supplier,
        },
                 {"account": cls._account(payment.company, code), "credit": bank_amount}]
        if tds > 0:
            lines.append({
                "account": cls._account(payment.company, "2265"),
                "credit": tds,
                "supplier": payment.supplier,
            })
        return cls.post(company=payment.company, source_type="SUPPLIER_PAYMENT", source_id=payment.id,
            purpose="CREATE", entry_date=payment.payment_date, user=user, narration=payment.number,
            lines=lines)

    @classmethod
    def post_supplier_payment_allocation(cls, allocation, user=None):
        """BB-000382: move Supplier Advances → AP on allocation."""
        amount = Decimal(str(allocation.amount or 0))
        if not amount:
            return None
        company = allocation.company
        cls._ensure_chart(company)
        supplier = allocation.supplier_payment.supplier if allocation.supplier_payment_id else None
        pay = allocation.supplier_payment
        entry_date = pay.payment_date if pay is not None else timezone.localdate()
        return cls.post(
            company=company,
            source_type="PAYMENT_ALLOCATION",
            source_id=allocation.id,
            purpose="ALLOCATE_PAYMENT",
            entry_date=entry_date,
            user=user,
            narration=f"Allocate payment {allocation.supplier_payment_id} → PI {allocation.purchase_invoice_id}",
            lines=[
                {"account": cls._account(company, "2100"), "debit": amount, "supplier": supplier},
                {"account": cls._account(company, "1250"), "credit": amount, "supplier": supplier},
            ],
        )
    @classmethod
    def post_note(cls, note, *, source_type, direction, user=None):
        """Post completed credit/debit notes as offsets to their originating control account.

        BB-000322: purchase note value legs hit Inventory (1400), matching
        perpetual post_purchase (not the periodic 5100 Purchases expense).
        BB-000336: purchase notes against an RCM invoice reverse RCM payable
        (2240-2260) / Input ITC (1310-1330) instead of normal Input GST/AP,
        mirroring post_purchase's RCM branch.
        """
        cls._ensure_chart(note.company)
        cgst = Decimal(str(note.cgst_total or 0))
        sgst = Decimal(str(note.sgst_total or 0))
        igst = Decimal(str(note.igst_total or 0))
        cess = Decimal(str(getattr(note, "cess_total", 0) or 0))
        tax = cgst + sgst + igst + cess
        round_off = Decimal(str(getattr(note, "round_off", 0) or 0))
        date = note.note_date
        round_off_line = None
        parent = getattr(note, "sales_invoice", None) or getattr(note, "purchase_invoice", None)
        parent_sales_rcm = bool(
            direction in ("SALES_CREDIT", "SALES_DEBIT")
            and parent
            and getattr(parent, "is_reverse_charge", False)
        )
        if direction == "SALES_CREDIT":
            tcs_amt = Decimal(str(getattr(note, "tcs_amount", 0) or 0))
            if parent_sales_rcm:
                ar = Decimal(str(note.grand_total or 0)) - tax
                sales_amt = ar - round_off - tcs_amt
                lines = [
                    {"account": cls._account(note.company, "4100"), "debit": sales_amt},
                    {"account": cls._account(note.company, "1200"), "credit": ar, "customer": note.customer},
                ]
            else:
                lines = [
                    {
                        "account": cls._account(note.company, "4100"),
                        "debit": note.grand_total - tax - round_off - tcs_amt,
                    },
                    *cls._tax_component_lines(
                        note.company,
                        (("2210", cgst), ("2220", sgst), ("2230", igst), ("2270", cess)),
                        side="debit",
                    ),
                    {"account": cls._account(note.company, "1200"), "credit": note.grand_total, "customer": note.customer},
                ]
            if tcs_amt > 0:
                lines.append({"account": cls._account(note.company, "2266"), "debit": tcs_amt})
            round_off_line = cls._round_off_line(note.company, round_off, side="debit")
        elif direction == "SALES_DEBIT":
            tcs_amt = Decimal(str(getattr(note, "tcs_amount", 0) or 0))
            if parent_sales_rcm:
                ar = Decimal(str(note.grand_total or 0)) - tax
                sales_amt = ar - round_off - tcs_amt
                lines = [
                    {"account": cls._account(note.company, "1200"), "debit": ar, "customer": note.customer},
                    {"account": cls._account(note.company, "4100"), "credit": sales_amt},
                ]
            else:
                lines = [
                    {"account": cls._account(note.company, "1200"), "debit": note.grand_total, "customer": note.customer},
                    {
                        "account": cls._account(note.company, "4100"),
                        "credit": note.grand_total - tax - round_off - tcs_amt,
                    },
                    *cls._tax_component_lines(
                        note.company,
                        (("2210", cgst), ("2220", sgst), ("2230", igst), ("2270", cess)),
                        side="credit",
                    ),
                ]
            if tcs_amt > 0:
                lines.append({"account": cls._account(note.company, "2266"), "credit": tcs_amt})
            round_off_line = cls._round_off_line(note.company, round_off, side="credit")
        elif direction == "PURCHASE_CREDIT":
            charges = Decimal(str(getattr(note, "additional_charges", 0) or 0))
            inv_amt = Decimal(str(getattr(note, "taxable_total", 0) or 0))
            if inv_amt <= 0:
                inv_amt = max(note.grand_total - tax - round_off - charges, Decimal("0"))
            parent_pi = getattr(note, "purchase_invoice", None) or note
            if cls._note_is_rcm(note):
                rcm_cgst = Decimal(str(getattr(note, "rcm_cgst", 0) or 0))
                rcm_sgst = Decimal(str(getattr(note, "rcm_sgst", 0) or 0))
                rcm_igst = Decimal(str(getattr(note, "rcm_igst", 0) or 0))
                rcm_cess = Decimal(str(getattr(note, "rcm_cess", 0) or 0))
                ap_base = inv_amt + charges
                itc_lines, cap = cls._purchase_itc_input_lines(
                    parent_pi, cgst=rcm_cgst, sgst=rcm_sgst, igst=rcm_igst, cess=rcm_cess,
                    side="credit",
                )
                if cap:
                    inv_amt = inv_amt + cap
                lines = [
                    {"account": cls._account(note.company, "2100"), "debit": ap_base, "supplier": note.supplier},
                    {"account": cls._account(note.company, "1400"), "credit": inv_amt},
                    *cls._tax_component_lines(
                        note.company,
                        (("2240", rcm_cgst), ("2250", rcm_sgst), ("2260", rcm_igst), ("2280", rcm_cess)),
                        side="debit",
                    ),
                    *itc_lines,
                ]
                if charges > 0:
                    lines.append({"account": cls._account(note.company, "5110"), "credit": charges})
            else:
                itc_lines, cap = cls._purchase_itc_input_lines(
                    parent_pi, cgst=cgst, sgst=sgst, igst=igst, cess=cess, side="credit",
                )
                if cap:
                    inv_amt = inv_amt + cap
                lines = [
                    {"account": cls._account(note.company, "2100"), "debit": note.grand_total, "supplier": note.supplier},
                    {"account": cls._account(note.company, "1400"), "credit": inv_amt},
                    *itc_lines,
                ]
                if charges > 0:
                    lines.append({"account": cls._account(note.company, "5110"), "credit": charges})
            round_off_line = cls._round_off_line(note.company, round_off, side="credit")
        else:  # PURCHASE_DEBIT
            charges = Decimal(str(getattr(note, "additional_charges", 0) or 0))
            inv_amt = Decimal(str(getattr(note, "taxable_total", 0) or 0))
            if inv_amt <= 0:
                inv_amt = max(note.grand_total - tax - round_off - charges, Decimal("0"))
            parent_pi = getattr(note, "purchase_invoice", None) or note
            if cls._note_is_rcm(note):
                rcm_cgst = Decimal(str(getattr(note, "rcm_cgst", 0) or 0))
                rcm_sgst = Decimal(str(getattr(note, "rcm_sgst", 0) or 0))
                rcm_igst = Decimal(str(getattr(note, "rcm_igst", 0) or 0))
                rcm_cess = Decimal(str(getattr(note, "rcm_cess", 0) or 0))
                ap_base = inv_amt + charges
                itc_lines, cap = cls._purchase_itc_input_lines(
                    parent_pi, cgst=rcm_cgst, sgst=rcm_sgst, igst=rcm_igst, cess=rcm_cess,
                    side="debit",
                )
                if cap:
                    inv_amt = inv_amt + cap
                lines = [
                    {"account": cls._account(note.company, "1400"), "debit": inv_amt},
                    {"account": cls._account(note.company, "2100"), "credit": ap_base, "supplier": note.supplier},
                    *cls._tax_component_lines(
                        note.company,
                        (("2240", rcm_cgst), ("2250", rcm_sgst), ("2260", rcm_igst), ("2280", rcm_cess)),
                        side="credit",
                    ),
                    *itc_lines,
                ]
                if charges > 0:
                    lines.insert(1, {"account": cls._account(note.company, "5110"), "debit": charges})
            else:
                itc_lines, cap = cls._purchase_itc_input_lines(
                    parent_pi, cgst=cgst, sgst=sgst, igst=igst, cess=cess, side="debit",
                )
                if cap:
                    inv_amt = inv_amt + cap
                lines = [
                    {"account": cls._account(note.company, "1400"), "debit": inv_amt},
                    *itc_lines,
                    {"account": cls._account(note.company, "2100"), "credit": note.grand_total, "supplier": note.supplier},
                ]
                if charges > 0:
                    lines.insert(1, {"account": cls._account(note.company, "5110"), "debit": charges})
            round_off_line = cls._round_off_line(note.company, round_off, side="debit")
        if round_off_line:
            lines.append(round_off_line)
        return cls.post(company=note.company, source_type=source_type, source_id=note.id, purpose="COMPLETE",
                        entry_date=date, lines=lines, narration=note.number, user=user)

    @classmethod
    def post_work_order_release(cls, wo, amount, user=None):
        amt = Decimal(str(amount or 0))
        if amt <= 0 or not getattr(wo.company, "accounting_enabled", False):
            return None
        cls._ensure_chart(wo.company)
        entry_date = getattr(wo, "released_at", None) or timezone.localdate()
        return cls.post(
            company=wo.company,
            source_type="WORK_ORDER",
            source_id=wo.id,
            purpose="RELEASE",
            entry_date=entry_date,
            user=user,
            narration=f"WO-{wo.id} release to WIP",
            lines=[
                {"account": cls._account(wo.company, "1450"), "debit": amt},
                {"account": cls._account(wo.company, "1400"), "credit": amt},
            ],
        )

    @classmethod
    def post_work_order_complete(cls, wo, amount, user=None):
        amt = Decimal(str(amount or 0))
        if amt <= 0 or not getattr(wo.company, "accounting_enabled", False):
            return None
        cls._ensure_chart(wo.company)
        entry_date = (
            getattr(wo, "completed_at", None)
            or getattr(wo, "released_at", None)
            or timezone.localdate()
        )
        return cls.post(
            company=wo.company,
            source_type="WORK_ORDER",
            source_id=wo.id,
            purpose="COMPLETE",
            entry_date=entry_date,
            user=user,
            narration=f"WO-{wo.id} FG from WIP",
            lines=[
                {"account": cls._account(wo.company, "1400"), "debit": amt},
                {"account": cls._account(wo.company, "1450"), "credit": amt},
            ],
        )

    @classmethod
    def reverse_work_order(cls, wo, user=None):
        if not getattr(wo.company, "accounting_enabled", False):
            return
        qs = JournalEntry.objects.filter(
            company=wo.company,
            source_type="WORK_ORDER",
            source_id=wo.id,
            status=JournalEntry.Status.POSTED,
        )
        for purpose in ("COMPLETE", "RELEASE"):
            for entry in qs.filter(purpose=purpose):
                cls.reverse(entry, user=user)

    @classmethod
    def reverse(cls, entry, user=None, entry_date=None, *, allow_soft_closed=None):
        # R3-016: the real "already reversed" guard is the status check — a
        # REVERSED entry can't be reversed again. (The old `hasattr(entry,
        # "reversal_of")` test was dead: there is no such relation.)
        if entry.status != JournalEntry.Status.POSTED or entry.reversed_entry_id is not None:
            raise BusinessRuleError("Only an unreversed posted journal may be reversed.")
        if allow_soft_closed is None:
            allow_soft_closed = entry.source_type != "MANUAL_JOURNAL"
        reversal = cls.post(company=entry.company, source_type="JOURNAL_REVERSAL", source_id=entry.id,
            purpose="REVERSE", entry_date=entry_date or timezone.localdate(), user=user,
            allow_soft_closed=allow_soft_closed,
            narration=f"Reversal of {entry.number}",
            lines=[{
                "account": line.account,
                "debit": line.credit,
                "credit": line.debit,
                "cost_center": line.cost_center,
                "dimension": line.dimension,
                "customer": line.customer,
                "supplier": line.supplier,
            } for line in entry.lines.all()])
        entry.reversed_entry = reversal
        entry.status = JournalEntry.Status.REVERSED
        entry.save(update_fields=["reversed_entry", "status", "updated_at"])
        return reversal



class BooksHealthService:
    @staticmethod
    def _period_label(period_obj) -> str | None:
        if period_obj is None:
            return None
        return f"{period_obj.start_date.year:04d}-{period_obj.start_date.month:02d}"

    @staticmethod
    def _depreciation_alerts(company):
        from .models import FixedAsset

        failed = FixedAsset.objects.filter(
            company=company,
            status=FixedAsset.Status.ACTIVE,
        ).exclude(last_depreciation_error="")
        if not failed.exists():
            return []
        count = failed.count()
        return [{
            "code": "DEPRECIATION_FAILED",
            "severity": "warning",
            "message": f"{count} fixed asset(s) have depreciation posting errors.",
        }]

    @staticmethod
    def period_close_blockers(company, *, period: str | None = None) -> list[dict]:
        """Collect BooksHealth + GstHealth alerts that must block period close."""
        from reporting.gst_health import build_gst_health

        blockers: list[dict] = []
        health = BooksHealthService.control_balances(company)
        for alert in health["alerts"]:
            code = alert["code"]
            if code in ("AR_CONTROL_MISMATCH", "AP_CONTROL_MISMATCH"):
                blockers.append(alert)
            elif code == "DOCUMENT_MISSING_POSTING" and company.accounting_enabled:
                blockers.append(alert)
        gst = build_gst_health(company, period)
        blockers.extend(a for a in gst["alerts"] if a.get("severity") == "critical")
        from manufacturing.models import WorkOrder

        if WorkOrder.objects.filter(company=company, status=WorkOrder.Status.RELEASED).exists():
            blockers.append({
                "code": "OPEN_WIP",
                "severity": "error",
                "message": "Released work orders exist; complete or cancel before period close.",
            })
        return blockers

    @staticmethod
    def assert_period_close_allowed(company, *, period: str | None = None):
        blockers = BooksHealthService.period_close_blockers(company, period=period)
        if not blockers:
            return
        codes = ", ".join(sorted({a["code"] for a in blockers}))
        raise BusinessRuleError(f"Period close blocked due to health alerts: {codes}.")

    @staticmethod
    def control_balances(company):
        def net(code):
            aggregate = JournalLine.objects.filter(entry__company=company, entry__status=JournalEntry.Status.POSTED,
                account__code=code).aggregate(d=Sum("debit"), c=Sum("credit"))
            return (aggregate["d"] or Decimal("0")) - (aggregate["c"] or Decimal("0"))
        ar = net("1200")
        ap = -net("2100")
        # Unfloored tagged party nets (not bulk_* which floors at 0 for UI).
        # Untagged 1200/2100 lines stay in `ar`/`ap` GL and trip mismatch.
        def tagged_net(code, party_field):
            aggregate = JournalLine.objects.filter(
                entry__company=company,
                entry__status=JournalEntry.Status.POSTED,
                account__code=code,
                **{f"{party_field}__isnull": False},
            ).aggregate(d=Sum("debit"), c=Sum("credit"))
            return (aggregate["d"] or Decimal("0")) - (aggregate["c"] or Decimal("0"))

        expected_ar = tagged_net("1200", "customer")
        expected_ap = -tagged_net("2100", "supplier")
        alerts = []
        # R3-013: a paise of rounding (or one untagged manual-journal line)
        # must not hard-block period close. Tolerance mirrors _advance_recon_alerts.
        _CONTROL_TOLERANCE = Decimal("1.00")
        ar_healthy = abs(ar - expected_ar) <= _CONTROL_TOLERANCE
        ap_healthy = abs(ap - expected_ap) <= _CONTROL_TOLERANCE
        if not ar_healthy:
            alerts.append({"code": "AR_CONTROL_MISMATCH", "severity": "error", "message": "Accounts receivable control balance differs from customer ledger."})
        if not ap_healthy:
            alerts.append({"code": "AP_CONTROL_MISMATCH", "severity": "error", "message": "Accounts payable control balance differs from supplier ledger."})
        if AccountingPeriod.objects.filter(company=company, status=AccountingPeriod.Status.SOFT_CLOSED).exists():
            alerts.append({"code": "PERIOD_SOFT_CLOSED", "severity": "warning", "message": "One or more accounting periods are soft closed."})
        from sales.models import SalesInvoice, SalesCreditNote, SalesDebitNote
        from purchases.models import PurchaseInvoice
        from payments.models import CustomerReceipt, SupplierPayment, ReceiptStatus, SupplierPaymentStatus
        from manufacturing.models import WorkOrder
        from payroll.models import PayRun

        # BB-000364 / BB-000713: missing posting across invoices, cash, notes, payroll, WO.
        missing = False
        if company.accounting_enabled:
            def _has_missing(qs, source_type, purpose=None):
                je = JournalEntry.objects.filter(company=company, source_type=source_type)
                if purpose is not None:
                    je = je.filter(purpose=purpose)
                return qs.exclude(id__in=je.values("source_id")).exists()

            missing = (
                _has_missing(
                    SalesInvoice.objects.filter(
                        company=company,
                        status=SalesInvoice.Status.COMPLETED,
                        is_opening_balance=False,
                    ),
                    "SALES_INVOICE",
                    "COMPLETE",
                )
                or _has_missing(
                    PurchaseInvoice.objects.filter(
                        company=company,
                        status=PurchaseInvoice.Status.COMPLETED,
                        is_opening_balance=False,
                    ),
                    "PURCHASE_INVOICE",
                    "COMPLETE",
                )
                or _has_missing(
                    CustomerReceipt.objects.filter(company=company, status=ReceiptStatus.POSTED),
                    "CUSTOMER_RECEIPT",
                    "CREATE",
                )
                or _has_missing(
                    SupplierPayment.objects.filter(
                        company=company, status=SupplierPaymentStatus.POSTED
                    ),
                    "SUPPLIER_PAYMENT",
                    "CREATE",
                )
                or _has_missing(
                    SalesCreditNote.objects.filter(
                        company=company, status=SalesCreditNote.Status.COMPLETED
                    ),
                    "SALES_CREDIT_NOTE",
                    "COMPLETE",
                )
                or _has_missing(
                    SalesDebitNote.objects.filter(
                        company=company, status=SalesDebitNote.Status.COMPLETED
                    ),
                    "SALES_DEBIT_NOTE",
                    "COMPLETE",
                )
                or _has_missing(
                    PayRun.objects.filter(company=company, status=PayRun.Status.COMPLETED),
                    "PayRun",
                    "PAYROLL",
                )
                or _has_missing(
                    WorkOrder.objects.filter(
                        company=company,
                        status__in=(WorkOrder.Status.RELEASED, WorkOrder.Status.COMPLETED),
                    ),
                    "WORK_ORDER",
                    None,
                )
            )
        if missing:
            alerts.append({
                "code": "DOCUMENT_MISSING_POSTING",
                "severity": "error" if company.accounting_enabled else "warning",
                "message": "Completed documents are missing their accounting posting.",
            })
        alerts.extend(BooksHealthService._depreciation_alerts(company))
        alerts.extend(BooksHealthService._advance_recon_alerts(company))
        return {"ar": {"gl": ar, "ledger": expected_ar, "healthy": ar_healthy},
                "ap": {"gl": ap, "ledger": expected_ap, "healthy": ap_healthy}, "alerts": alerts}

    @staticmethod
    def _advance_recon_alerts(company):
        """Wave 17A: reconcile customer/supplier advance GL (2300/1250) vs unallocated cash."""
        from django.db.models import Sum

        from payments.models import (
            CustomerReceipt,
            PaymentAllocation,
            ReceiptStatus,
            SupplierPayment,
            SupplierPaymentStatus,
        )

        alerts = []
        if not company.accounting_enabled:
            return alerts

        def net(code):
            aggregate = JournalLine.objects.filter(
                entry__company=company,
                entry__status=JournalEntry.Status.POSTED,
                account__code=code,
            ).aggregate(d=Sum("debit"), c=Sum("credit"))
            return (aggregate["d"] or Decimal("0")) - (aggregate["c"] or Decimal("0"))

        # Customer advances liability 2300: credit-normal → -net is credit balance
        gl_cust_adv = -net("2300")
        receipt_total = (
            CustomerReceipt.objects.filter(company=company, status=ReceiptStatus.POSTED).aggregate(
                t=Sum("amount")
            )["t"]
            or Decimal("0")
        )
        alloc_receipt = (
            PaymentAllocation.objects.filter(
                company=company, receipt__isnull=False, reversed_at__isnull=True
            ).aggregate(t=Sum("amount"))["t"]
            or Decimal("0")
        )
        unalloc_receipt = receipt_total - alloc_receipt
        if abs(gl_cust_adv - unalloc_receipt) > Decimal("1.00"):
            alerts.append({
                "code": "CUSTOMER_ADVANCE_MISMATCH",
                "severity": "warning",
                "message": (
                    f"Customer advance GL 2300 ({gl_cust_adv}) differs from "
                    f"unallocated receipts ({unalloc_receipt})."
                ),
            })

        gl_supp_adv = net("1250")  # prepaid/advance to supplier — debit-normal
        pay_agg = SupplierPayment.objects.filter(
            company=company, status=SupplierPaymentStatus.POSTED
        ).aggregate(a=Sum("amount"), t=Sum("tds_amount"))
        pay_total = (pay_agg["a"] or Decimal("0")) + (pay_agg["t"] or Decimal("0"))
        alloc_pay = (
            PaymentAllocation.objects.filter(
                company=company, supplier_payment__isnull=False, reversed_at__isnull=True
            ).aggregate(t=Sum("amount"))["t"]
            or Decimal("0")
        )
        unalloc_pay = pay_total - alloc_pay
        if abs(gl_supp_adv - unalloc_pay) > Decimal("1.00"):
            alerts.append({
                "code": "SUPPLIER_ADVANCE_MISMATCH",
                "severity": "warning",
                "message": (
                    f"Supplier advance GL 1250 ({gl_supp_adv}) differs from "
                    f"unallocated payments ({unalloc_pay})."
                ),
            })
        return alerts

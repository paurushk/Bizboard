"""Per-invoice gross margin snapshot — persisted at invoice-complete time.

See reporting.models.InvoiceProfitSnapshot for why this is a stored table
rather than a compute-on-demand report: margin needs to stay stable even if
FIFO/valuation logic changes later, and re-deriving COGS from StockMovement
on every report request would be expensive over a wide date range.
"""

from decimal import Decimal

from core.services.billing import q2

from .models import InvoiceProfitSnapshot


class InvoiceProfitService:
    @staticmethod
    def classify_cost_basis(counts: dict) -> str:
        """Worst tier present wins — a single fallback line is enough to flag
        the whole invoice as not-fully-FIFO-costed (decision: include, flagged,
        rather than hide or silently show a falsely precise number)."""
        if not counts or not counts.get("lines"):
            return InvoiceProfitSnapshot.CostBasis.NO_COGS
        if counts.get("purchase_price_fallback"):
            return InvoiceProfitSnapshot.CostBasis.PURCHASE_PRICE_FALLBACK
        if counts.get("valuation_fallback"):
            return InvoiceProfitSnapshot.CostBasis.VALUATION_FALLBACK
        if counts.get("zero_cost"):
            return InvoiceProfitSnapshot.CostBasis.ZERO_COST
        return InvoiceProfitSnapshot.CostBasis.FIFO

    @staticmethod
    def write_snapshot(
        invoice, cogs_total: Decimal, cost_basis_counts: dict | None, user=None, *, is_backfilled: bool = False
    ) -> InvoiceProfitSnapshot:
        counts = cost_basis_counts or {}
        revenue_pre_discount = invoice.subtotal or Decimal("0")
        gross_margin = revenue_pre_discount - (cogs_total or Decimal("0"))
        # Quantize with the codebase's canonical ROUND_HALF_UP convention
        # (core.services.billing.q2, used for every other money/percentage
        # figure) instead of leaving this unquantized -- the DB column is
        # NUMERIC(7,2) either way, but relying on the DB's own rounding mode
        # can disagree with q2() by a paisa/percent-point on exact
        # half-cent boundaries.
        margin_percent = (
            q2(gross_margin / revenue_pre_discount * 100) if revenue_pre_discount else None
        )
        snapshot, _ = InvoiceProfitSnapshot.objects.update_or_create(
            sales_invoice=invoice,
            defaults={
                "company": invoice.company,
                "invoice_number": invoice.number,
                "invoice_date": invoice.invoice_date,
                "invoice_status": invoice.status,
                "customer_id": invoice.customer_id,
                "warehouse_id": invoice.warehouse_id,
                "cost_center_id": invoice.cost_center_id,
                "revenue_pre_discount": revenue_pre_discount,
                "line_discount_total": invoice.discount_total or Decimal("0"),
                "invoice_discount": invoice.invoice_discount or Decimal("0"),
                "taxable_total": invoice.taxable_total or Decimal("0"),
                "grand_total": invoice.grand_total or Decimal("0"),
                "cogs_total": cogs_total or Decimal("0"),
                "gross_margin": gross_margin,
                "margin_percent": margin_percent,
                "cost_basis": InvoiceProfitService.classify_cost_basis(counts),
                "has_cogs_lines": bool(counts.get("lines")),
                "is_backfilled": is_backfilled,
                "created_by": user,
                "updated_by": user,
            },
        )
        return snapshot

    @staticmethod
    def sync_status(invoice) -> None:
        """Status-only update for cancel/return — the original snapshot's
        monetary fields stay a correct record of the sale as originally
        posted; returns/cancels don't mutate the invoice's own totals either."""
        InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).update(invoice_status=invoice.status)

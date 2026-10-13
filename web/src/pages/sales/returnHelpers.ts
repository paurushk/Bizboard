import type { SalesInvoice } from '@/types/domain';
import { toNumber } from '@/utils/money';

/**
 * True when the credit this return issues is larger than what the customer still
 * owes on the invoice, so the excess becomes unallocated customer advance.
 *
 * Judged from the balance rather than from "received": the API derives `received`
 * as receivable minus balance, so a credit note applied earlier looks like a
 * payment and would raise this warning on an invoice nobody has paid.
 */
export function creditExceedsBalance(
  invoice: Pick<SalesInvoice, 'balance' | 'grandTotal'> | null | undefined,
  creditTotal: number | null | undefined,
): boolean {
  if (!invoice || creditTotal == null) return false;
  const balance = invoice.balance == null || invoice.balance === '' ? toNumber(invoice.grandTotal) : toNumber(invoice.balance);
  return creditTotal - balance > 0.009;
}

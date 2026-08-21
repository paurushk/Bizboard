import {
  makeLine as makeLineBase,
  type DraftLine,
} from '@/components/billing';

/** BB-000751: invoice-specific line factory (sellingPrice default). */
export function makeInvoiceLine(
  product: Parameters<typeof makeLineBase>[0],
  intraState: boolean | null,
  quantity = 1,
): DraftLine {
  return makeLineBase(product, intraState, quantity, 'sellingPrice');
}

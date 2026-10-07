import type { InvoiceDraftLine } from '@/offline/invoiceDraftCache';
import { toNumber } from '@/utils/money';

/** One invoice body for atomic cash and UPI checkout. */
export function buildAtomicPosInvoicePayload(args: {
  customer: number;
  invoiceType: string;
  priceModeInclusive: boolean;
  invoiceDate: string;
  warehouseId?: number;
  taxEnabled: boolean;
  lines: InvoiceDraftLine[];
  invoiceDiscount?: number;
  additionalCharges?: number;
  invoiceDiscountMode?: 'BEFORE_TAX' | 'AFTER_TAX';
  paymentTermsDays?: number;
}) {
  const terms = args.paymentTermsDays ?? 0;
  return {
    customer: args.customer,
    invoice_type: args.invoiceType,
    price_mode: args.priceModeInclusive ? 'INCLUSIVE' : 'EXCLUSIVE',
    invoice_date: args.invoiceDate,
    due_date: args.invoiceDate,
    payment_terms_days: terms,
    invoice_discount_mode: args.invoiceDiscountMode ?? 'AFTER_TAX',
    auto_round_off: true,
    warehouse: args.warehouseId,
    invoice_discount: args.invoiceDiscount ?? 0,
    additional_charges: args.additionalCharges ?? 0,
    items: args.lines.map((line) => ({
      product: line.productId,
      description: line.productName,
      quantity: line.quantity,
      unit_price: line.unitPrice,
      unit_price_inclusive: args.priceModeInclusive ? line.unitPrice : undefined,
      gst_rate: args.taxEnabled ? line.gstRate : 0,
      cess_rate: args.taxEnabled ? toNumber(line.cessRate) : 0,
      discount_percent: line.discountPercent ?? 0,
      unit_name: line.unitName || undefined,
      ...(line.serials?.length ? { serial_numbers: line.serials } : {}),
      ...(line.batchNo ? { batch_no: line.batchNo } : {}),
    })),
  };
}

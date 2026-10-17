/** Where a movement's document lives, so the ledger can link to it. */
export interface LedgerReference {
  label: string;
  /** Null when there is no page for that kind of document. */
  href: string | null;
}

const WORDS: Record<string, string> = {
  purchase_invoice: 'Purchase bill',
  purchase_invoice_cancel: 'Purchase bill cancelled',
  purchase_invoice_edit: 'Purchase bill edited',
  sales_invoice: 'Sales invoice',
  sales_invoice_cancel: 'Sales invoice cancelled',
  sales_invoice_cancel_challan: 'Invoice cancelled (challan)',
  delivery_challan: 'Delivery challan',
  sales_return: 'Sales return',
  sales_return_damaged: 'Sales return (damaged)',
  sales_return_cancel: 'Sales return cancelled',
  purchase_return: 'Purchase return',
  purchase_return_damaged: 'Purchase return (damaged)',
  purchase_return_cancel: 'Purchase return cancelled',
  stock_transfer: 'Stock transfer',
  stock_transfer_cancel: 'Transfer cancelled',
  stock_count: 'Stock count',
  manual_adjustment: 'Adjustment',
  expiry_write_off: 'Expiry write-off',
  serial_scrap: 'Serial scrapped',
  serial_manual_return: 'Serial returned',
  opening_stock: 'Opening stock',
  goods_receipt: 'Goods receipt',
  goods_receipt_cancel: 'Goods receipt cancelled',
  goods_receipt_unwind: 'Goods receipt unwound',
  work_order: 'Work order',
  work_order_cancel: 'Work order cancelled',
  import: 'Import',
  import_void: 'Import voided',
  import_voided: 'Import voided',
};

export function describeReference(referenceType: string, referenceId: string | number | null | undefined): LedgerReference {
  const type = (referenceType || '').trim();
  const id = referenceId == null ? '' : String(referenceId).trim();
  if (!type) return { label: '', href: null };
  const words = WORDS[type] ?? type.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  const label = id ? `${words} #${id}` : words;
  switch (type) {
    case 'sales_invoice':
    case 'sales_invoice_cancel':
      return { label, href: id ? `/sales/history/${id}` : null };
    case 'purchase_invoice':
    case 'purchase_invoice_cancel':
    case 'purchase_invoice_edit':
      return { label, href: id ? `/purchases/history/${id}` : null };
    case 'delivery_challan':
    case 'sales_invoice_cancel_challan':
      return { label, href: id ? `/sales/delivery-challans/${id}` : null };
    case 'stock_transfer':
    case 'stock_transfer_cancel':
      return { label, href: '/inventory/transfers' };
    case 'stock_count':
      return { label, href: '/inventory/stock-counts' };
    case 'sales_return':
    case 'sales_return_damaged':
    case 'sales_return_cancel':
      return { label, href: '/sales/returns' };
    default:
      return { label, href: null };
  }
}

export const MOVEMENT_TYPES = [
  'OPENING_STOCK',
  'PURCHASE',
  'SALE',
  'PURCHASE_RETURN',
  'SALES_RETURN',
  'ADJUSTMENT',
  'TRANSFER_OUT',
  'TRANSFER_IN',
  'MANUFACTURE_ISSUE',
  'MANUFACTURE_RECEIPT',
] as const;

export function typeLabel(type: string): string {
  return type
    .toLowerCase()
    .split('_')
    .map((word, i) => (i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ');
}

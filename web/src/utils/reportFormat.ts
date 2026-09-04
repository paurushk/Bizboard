/**
 * F3-074: shared formatting helpers for the tabular register-style report
 * pages (SalesReportPage / PurchaseReportPage were carrying byte-identical
 * copies of these).
 */

// F3-006: a column is a money column by its name, not by its value type.
const MONEY_COL =
  /(amount|total|value|balance|price|net|gross|payable|receivable|outstanding|discount|freight|charge|cess|tcs|tds|paid|due|mrp|cogs|profit|margin)/i;
const NOT_MONEY_COL = /(rate|percent|qty|quantity|count|hsn|sac|_?code$|number|invoices?$|bills?$|id$)/i;

export function isMoneyColumn(key: string): boolean {
  return MONEY_COL.test(key) && !NOT_MONEY_COL.test(key);
}

export function downloadReportUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

const COLUMN_HEADER_MAP: Record<string, string> = {
  invoice_number: 'Invoice No.',
  bill_number: 'Bill No.',
  invoice_date: 'Date',
  customer_name: 'Customer',
  supplier_name: 'Supplier',
  grand_total: 'Total Amount',
  taxable_amount: 'Taxable Amt',
  cgst_amount: 'CGST',
  sgst_amount: 'SGST',
  igst_amount: 'IGST',
  total_tax: 'Total Tax',
  net_total: 'Net Total',
  due_date: 'Due Date',
  payment_status: 'Payment Status',
  party_gstin: 'GSTIN',
};

export function formatColumnHeader(key: string): string {
  if (COLUMN_HEADER_MAP[key]) return COLUMN_HEADER_MAP[key];
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

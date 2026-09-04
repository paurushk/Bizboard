/** Shared draft line shape for invoice / purchase / note editors (P0-311). */
export interface DraftLine {
  key: string;
  /** Persisted line id when editing an existing document (H9-A amend). */
  lineId?: number;
  product: number;
  productName: string;
  description: string;
  sku: string;
  hsnCode: string;
  unitName: string;
  baseUnitName?: string;
  alternateUnitName?: string;
  conversionRate?: number;
  sourceItemId?: number | null;
  batchNo: string;
  batch?: number | null;
  trackBatch?: boolean;
  trackSerial?: boolean;
  /** Comma- or newline-separated serial numbers for trackSerial products. */
  serialNumbersText?: string;
  expDate: string;
  mfgDate: string;
  mrp: number;
  quantity: number;
  /** F2-012: upper bound from the source purchase line for credit/debit notes. */
  maxQty?: number;
  unitPrice: number;
  /** F2-007: set once the user types a unit price directly — a later qty change
   *  must then NOT silently re-apply the price-list rate over their override. */
  priceEdited?: boolean;
  discountPercent: number;
  discountAmount: number;
  gstRate: number;
  cessRate: number;
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  cess: number;
  lineTotal: number;
  gross: number;
  supplyNature?: 'TAXABLE' | 'NIL' | 'EXEMPT' | 'NON_GST';
}

export type DraftLinePriceField = 'sellingPrice' | 'purchasePrice';

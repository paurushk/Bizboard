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
  unitPrice: number;
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
}

export type DraftLinePriceField = 'sellingPrice' | 'purchasePrice';

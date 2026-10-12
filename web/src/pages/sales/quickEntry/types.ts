export type QuickMode = 'order' | 'bill';

export interface QuickLine {
  key: string;
  productId: number;
  name: string;
  sku: string;
  unitName: string;
  uqc: string;
  quantity: number;
  /** Catalogue price; replaced by the server-resolved price when the preview is on. */
  unitPrice: number;
  gstRate: number;
  priceListName: string;
  availableQty: number | null;
  trackInventory: boolean;
}

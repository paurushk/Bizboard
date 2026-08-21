import type { Product } from '@/types/domain';
import { roundMoney, toNumber } from '@/utils/money';
import { calculateLineTax } from '@/utils/tax';
import type { DraftLine, DraftLinePriceField } from './types';

export function todayIso(d: Date = new Date()): string {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function parseSerialNumbersText(text: string): string[] {
  return text
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function formatSerialNumbersText(numbers: string[] | undefined): string {
  return (numbers ?? []).join(', ');
}

export function makeLine(
  product: Product,
  intraState: boolean | null,
  quantity = 1,
  priceField: DraftLinePriceField = 'sellingPrice',
): DraftLine {
  const unitPrice = toNumber(
    priceField === 'purchasePrice' ? product.purchasePrice : product.sellingPrice,
  );
  const tax = calculateLineTax({
    quantity,
    unitPrice,
    gstRate: toNumber(product.gstRate),
    cessRate: 0,
    intraState,
  });
  return {
    key: `${product.id}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    product: product.id,
    productName: product.name,
    description: '',
    sku: product.sku,
    hsnCode: product.hsnCode ?? '',
    unitName: product.unitName ?? 'PCS',
    batchNo: '',
    batch: null,
    trackBatch: product.trackBatch,
    trackSerial: product.trackSerial,
    serialNumbersText: '',
    expDate: '',
    mfgDate: '',
    mrp: toNumber(product.mrp),
    quantity,
    unitPrice,
    gstRate: toNumber(product.gstRate),
    cessRate: 0,
    ...tax,
  };
}

export function recomputeLine(
  line: DraftLine,
  intraState: boolean | null,
  patch: Partial<DraftLine> = {},
): DraftLine {
  const next = { ...line, ...patch };
  const tax = calculateLineTax({
    quantity: next.quantity,
    unitPrice: next.unitPrice,
    discountPercent: next.discountPercent,
    gstRate: next.gstRate,
    cessRate: next.cessRate ?? 0,
    intraState,
  });
  return {
    ...next,
    ...tax,
  };
}

export function applyDiscountAmountPatch(
  line: DraftLine,
  intraState: boolean | null,
  patch: Partial<DraftLine>,
): DraftLine {
  if (patch.discountAmount == null) {
    return recomputeLine(line, intraState, patch);
  }
  const gross = roundMoney((patch.quantity ?? line.quantity) * (patch.unitPrice ?? line.unitPrice));
  const amount = Math.min(Math.max(0, patch.discountAmount), gross);
  const percent = gross > 0 ? roundMoney((amount / gross) * 100) : 0;
  return recomputeLine(line, intraState, {
    ...patch,
    discountPercent: percent,
    discountAmount: amount,
  });
}

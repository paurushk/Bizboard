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

export interface ParsedSerialInput {
  /** Unique, valid serials in the order they were first seen (ranges expanded). */
  serials: string[];
  /** Serials that appeared more than once in the pasted text (deduped). */
  duplicates: string[];
  /** Any `A-B` tokens that were expanded into a run of serials. */
  rangesExpanded: number;
}

const TRAILING_DIGITS = /^(.*?)(\d+)$/;
// QOS-0035: a bulk consignment scan/paste is usually printer-sequential IMEIs/
// serials ("IMEI1000-IMEI1005"); expanding a hyphenated range saves re-typing
// hundreds of them by hand. Capped at 5000 to keep a typo from hanging the UI.
const MAX_RANGE_SPAN = 5000;

function expandSerialToken(token: string): string[] {
  // Only a single hyphen is treated as a range separator — a serial whose
  // own prefix contains a hyphen (e.g. "SN-001") makes "A-B" ambiguous, so
  // that's left untouched rather than guessed at.
  const parts = token.split('-');
  if (parts.length !== 2) return [token];
  const [left, right] = parts.map((p) => p.trim());
  const leftMatch = left.match(TRAILING_DIGITS);
  const rightMatch = right.match(TRAILING_DIGITS);
  if (!leftMatch || !rightMatch) return [token];
  const [, leftPrefix, leftDigits] = leftMatch;
  const [, rightPrefix, rightDigits] = rightMatch;
  if (leftPrefix !== rightPrefix) return [token];
  const start = Number.parseInt(leftDigits, 10);
  const end = Number.parseInt(rightDigits, 10);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start || end - start > MAX_RANGE_SPAN) {
    return [token];
  }
  const width = leftDigits.length;
  const out: string[] = [];
  for (let n = start; n <= end; n += 1) {
    out.push(`${leftPrefix}${String(n).padStart(width, '0')}`);
  }
  return out;
}

/** Full parse: range expansion + de-dup, with the counts a paste-review UI needs. */
export function parseSerialInput(text: string): ParsedSerialInput {
  const tokens = text
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  let rangesExpanded = 0;
  const expanded = tokens.flatMap((token) => {
    const out = expandSerialToken(token);
    if (out.length > 1) rangesExpanded += 1;
    return out;
  });
  const seen = new Set<string>();
  const duplicateSet = new Set<string>();
  const serials: string[] = [];
  for (const serial of expanded) {
    if (seen.has(serial)) {
      duplicateSet.add(serial);
      continue;
    }
    seen.add(serial);
    serials.push(serial);
  }
  return { serials, duplicates: [...duplicateSet], rangesExpanded };
}

export function parseSerialNumbersText(text: string): string[] {
  return parseSerialInput(text).serials;
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
  const cessRate = toNumber(product.cessRate);
  const tax = calculateLineTax({
    quantity,
    unitPrice,
    gstRate: toNumber(product.gstRate),
    cessRate,
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
    baseUnitName: product.unitName ?? 'PCS',
    alternateUnitName: product.alternateUnitName,
    conversionRate: toNumber(product.conversionRate) || 1,
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
    cessRate,
    supplyNature: 'TAXABLE',
    ...tax,
  };
}

export function recomputeLine(
  line: DraftLine,
  intraState: boolean | null,
  patch: Partial<DraftLine> = {},
): DraftLine {
  const next = { ...line, ...patch };
  const nature = (next.supplyNature ?? 'TAXABLE').toUpperCase();
  if (nature !== 'TAXABLE') next.gstRate = 0;
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

export function unitSwitchPatch(line: DraftLine, nextUnit: string): Partial<DraftLine> {
  const rate = Number(line.conversionRate) || 1;
  const base = line.baseUnitName || 'PCS';
  const alt = line.alternateUnitName;
  let unitPrice = line.unitPrice;
  if (alt && rate > 0 && line.unitName !== nextUnit) {
    if (line.unitName === base && nextUnit === alt) {
      unitPrice = roundMoney(line.unitPrice * rate);
    } else if (line.unitName === alt && nextUnit === base) {
      unitPrice = roundMoney(line.unitPrice / rate);
    }
  }
  return { unitName: nextUnit, unitPrice };
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

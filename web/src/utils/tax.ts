import { roundMoney } from './money';

export type InvoiceDiscountMode = 'AFTER_TAX' | 'BEFORE_TAX';
export type PlaceOfSupply = 'intra' | 'inter' | 'unknown';

export interface LineTaxInput {
  quantity: number;
  unitPrice: number;
  discountPercent?: number;
  /** Absolute discount amount for the line (synced with percent when provided alone). */
  discountAmount?: number;
  gstRate: number;
  /** When true, split GST into CGST/SGST; otherwise IGST. */
  intraState?: boolean;
}

export interface LineTaxResult {
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  taxTotal: number;
  lineTotal: number;
  discountAmount: number;
  discountPercent: number;
  gross: number;
}

/**
 * Matches backend `core.services.billing.compute_document_totals` line tax:
 * tax = taxable * rate / 100 (unrounded); cgst = q2(tax/2); sgst = q2(tax) - cgst.
 */
export function calculateLineTax(input: LineTaxInput): LineTaxResult {
  const qty = input.quantity;
  const gross = roundMoney(qty * input.unitPrice);
  // BUG-511: the applied discount amount was already clamped to gross, but
  // the displayed percent itself wasn't — a line could show "500%" even
  // though only 100% (the full gross) was actually being discounted.
  let discountPercent = Math.min(100, Math.max(0, input.discountPercent ?? 0));
  let discountAmount =
    input.discountAmount != null
      ? roundMoney(input.discountAmount)
      : roundMoney(gross * (discountPercent / 100));

  if (input.discountAmount != null && input.discountPercent == null && gross > 0) {
    discountPercent = roundMoney((discountAmount / gross) * 100);
  } else if (input.discountPercent != null) {
    discountAmount = roundMoney(gross * (discountPercent / 100));
  }

  discountAmount = Math.min(Math.max(0, discountAmount), gross);
  const taxableAmount = roundMoney(gross - discountAmount);
  const taxRaw = taxableAmount * (input.gstRate / 100);
  const intraState = input.intraState ?? true;

  if (intraState) {
    const half = roundMoney(taxRaw / 2);
    const cgst = half;
    const sgst = roundMoney(taxRaw) - half;
    return {
      gross,
      discountAmount,
      discountPercent,
      taxableAmount,
      cgst,
      sgst,
      igst: 0,
      taxTotal: roundMoney(cgst + sgst),
      lineTotal: roundMoney(taxableAmount + cgst + sgst),
    };
  }

  const igst = roundMoney(taxRaw);
  return {
    gross,
    discountAmount,
    discountPercent,
    taxableAmount,
    cgst: 0,
    sgst: 0,
    igst,
    taxTotal: igst,
    lineTotal: roundMoney(taxableAmount + igst),
  };
}

export interface InvoiceTotalsInput {
  additionalCharges?: number;
  invoiceDiscount?: number;
  applyRoundOff?: boolean;
  invoiceDiscountMode?: InvoiceDiscountMode;
}

function applyLineTaxOnTaxable(
  taxableAmount: number,
  gstRate: number,
  intraState: boolean,
): Pick<LineTaxResult, 'cgst' | 'sgst' | 'igst' | 'taxTotal' | 'lineTotal' | 'taxableAmount'> {
  const taxRaw = taxableAmount * (gstRate / 100);
  if (intraState) {
    const half = roundMoney(taxRaw / 2);
    const cgst = half;
    const sgst = roundMoney(taxRaw) - half;
    return {
      taxableAmount,
      cgst,
      sgst,
      igst: 0,
      taxTotal: roundMoney(cgst + sgst),
      lineTotal: roundMoney(taxableAmount + cgst + sgst),
    };
  }
  const igst = roundMoney(taxRaw);
  return {
    taxableAmount,
    cgst: 0,
    sgst: 0,
    igst,
    taxTotal: igst,
    lineTotal: roundMoney(taxableAmount + igst),
  };
}

export function calculateInvoiceTotals(
  lines: Array<
    Pick<LineTaxResult, 'taxableAmount' | 'taxTotal' | 'cgst' | 'sgst' | 'igst' | 'gross' | 'discountAmount'> & {
      gstRate?: number;
      intraState?: boolean;
    }
  >,
  options: InvoiceTotalsInput | boolean = true,
): {
  subtotal: number;
  lineDiscountTotal: number;
  taxableTotal: number;
  cgstTotal: number;
  sgstTotal: number;
  igstTotal: number;
  taxTotal: number;
  additionalCharges: number;
  invoiceDiscount: number;
  roundOff: number;
  grandTotal: number;
  invoiceDiscountMode: InvoiceDiscountMode;
} {
  const opts: InvoiceTotalsInput =
    typeof options === 'boolean' ? { applyRoundOff: options } : options;
  const applyRoundOff = opts.applyRoundOff ?? true;
  const additionalCharges = roundMoney(opts.additionalCharges ?? 0);
  const invoiceDiscount = roundMoney(opts.invoiceDiscount ?? 0);
  const mode: InvoiceDiscountMode = opts.invoiceDiscountMode ?? 'AFTER_TAX';

  const subtotal = roundMoney(lines.reduce((sum, l) => sum + (l.gross ?? l.taxableAmount), 0));
  const lineDiscountTotal = roundMoney(lines.reduce((sum, l) => sum + (l.discountAmount ?? 0), 0));

  let working = lines.map((l) => ({
    taxableAmount: l.taxableAmount,
    gstRate: l.gstRate ?? 0,
    intraState: l.intraState ?? true,
    cgst: l.cgst ?? 0,
    sgst: l.sgst ?? 0,
    igst: l.igst ?? 0,
    taxTotal: l.taxTotal,
    gross: l.gross,
    discountAmount: l.discountAmount,
  }));

  if (mode === 'BEFORE_TAX' && invoiceDiscount > 0 && working.length > 0) {
    const taxableSum = roundMoney(working.reduce((s, l) => s + l.taxableAmount, 0));
    if (taxableSum > 0) {
      const remaining = Math.min(invoiceDiscount, taxableSum);
      let allocated = 0;
      working = working.map((l, i) => {
        if (i === working.length - 1) {
          const last = roundMoney(remaining - allocated);
          const taxableAmount = roundMoney(Math.max(0, l.taxableAmount - last));
          return { ...l, ...applyLineTaxOnTaxable(taxableAmount, l.gstRate, l.intraState) };
        }
        const share = roundMoney((l.taxableAmount / taxableSum) * remaining);
        const capped = Math.min(share, l.taxableAmount);
        allocated = roundMoney(allocated + capped);
        const taxableAmount = roundMoney(l.taxableAmount - capped);
        return { ...l, ...applyLineTaxOnTaxable(taxableAmount, l.gstRate, l.intraState) };
      });
    }
  }

  const taxableTotal = roundMoney(working.reduce((sum, l) => sum + l.taxableAmount, 0));
  const cgstTotal = roundMoney(working.reduce((sum, l) => sum + (l.cgst ?? 0), 0));
  const sgstTotal = roundMoney(working.reduce((sum, l) => sum + (l.sgst ?? 0), 0));
  const igstTotal = roundMoney(working.reduce((sum, l) => sum + (l.igst ?? 0), 0));
  const taxTotal = roundMoney(cgstTotal + sgstTotal + igstTotal);
  const raw =
    mode === 'BEFORE_TAX'
      ? roundMoney(taxableTotal + taxTotal + additionalCharges)
      : roundMoney(taxableTotal + taxTotal + additionalCharges - invoiceDiscount);
  const clamped = Math.max(0, raw);
  const rounded = applyRoundOff ? Math.round(clamped) : clamped;
  const roundOff = roundMoney(rounded - clamped);
  return {
    subtotal,
    lineDiscountTotal,
    taxableTotal,
    cgstTotal,
    sgstTotal,
    igstTotal,
    taxTotal,
    additionalCharges,
    invoiceDiscount,
    roundOff,
    grandTotal: rounded,
    invoiceDiscountMode: mode,
  };
}

export function extractStateCode(value?: string): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^\d{2}/.test(trimmed)) return trimmed.slice(0, 2);
  return null;
}

/** Resolve place of supply for GST; blank party → unknown (do not silently assume intra). */
export function resolvePlaceOfSupply(
  companyGstinOrState?: string,
  partyGstinOrState?: string,
): PlaceOfSupply {
  const partyRaw = (partyGstinOrState || '').trim();
  if (!partyRaw) return 'unknown';
  const companyCode = extractStateCode(companyGstinOrState);
  const partyCode = extractStateCode(partyGstinOrState);
  if (companyCode && partyCode) return companyCode === partyCode ? 'intra' : 'inter';
  const a = (companyGstinOrState || '').trim().toLowerCase();
  const b = partyRaw.toLowerCase();
  if (!a) return 'intra';
  return a === b ? 'intra' : 'inter';
}

/** Compare company GSTIN/state with party GSTIN/state for intra-state GST. */
export function isIntraState(
  companyGstinOrStateCode: string | undefined,
  partyGstinOrState: string | undefined,
): boolean {
  const place = resolvePlaceOfSupply(companyGstinOrStateCode, partyGstinOrState);
  // unknown → treat as intra for preview only; Complete must be blocked separately
  return place !== 'inter';
}

export function placeOfSupplyKnown(partyState?: string, partyGstin?: string): boolean {
  if ((partyState || '').trim()) return true;
  return extractStateCode(partyGstin) != null;
}

export function addDaysIso(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

import { roundMoney } from './money';

export interface LineTaxInput {
  quantity: number;
  unitPrice: number;
  discountPercent?: number;
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
}

/**
 * Matches backend `core.services.billing.recalculate_document` —
 * both CGST and SGST use q2(tax / 2), so odd paise may leave 0.01 unallocated.
 */
export function calculateLineTax(input: LineTaxInput): LineTaxResult {
  const qty = input.quantity;
  const discount = (input.discountPercent ?? 0) / 100;
  const gross = qty * input.unitPrice;
  const taxableAmount = roundMoney(gross * (1 - discount));
  const taxTotal = roundMoney(taxableAmount * (input.gstRate / 100));
  const intraState = input.intraState ?? true;

  if (intraState) {
    const half = roundMoney(taxTotal / 2);
    const cgst = half;
    const sgst = half;
    return {
      taxableAmount,
      cgst,
      sgst,
      igst: 0,
      taxTotal: roundMoney(cgst + sgst),
      lineTotal: roundMoney(taxableAmount + cgst + sgst),
    };
  }

  return {
    taxableAmount,
    cgst: 0,
    sgst: 0,
    igst: taxTotal,
    taxTotal,
    lineTotal: roundMoney(taxableAmount + taxTotal),
  };
}

export function calculateInvoiceTotals(
  lines: LineTaxResult[],
  applyRoundOff = true,
): {
  subtotal: number;
  taxTotal: number;
  roundOff: number;
  grandTotal: number;
} {
  const subtotal = roundMoney(lines.reduce((sum, l) => sum + l.taxableAmount, 0));
  const taxTotal = roundMoney(lines.reduce((sum, l) => sum + l.taxTotal, 0));
  const raw = roundMoney(subtotal + taxTotal);
  const rounded = applyRoundOff ? Math.round(raw) : raw;
  const roundOff = roundMoney(rounded - raw);
  return { subtotal, taxTotal, roundOff, grandTotal: rounded };
}

/** Compare company GSTIN/state prefix with party GSTIN for intra-state GST. */
export function isIntraState(
  companyGstinOrStateCode: string | undefined,
  partyGstinOrState: string | undefined,
): boolean {
  const companyCode = extractStateCode(companyGstinOrStateCode);
  const partyCode = extractStateCode(partyGstinOrState);
  if (!companyCode || !partyCode) return true;
  return companyCode === partyCode;
}

function extractStateCode(value?: string): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^\d{2}/.test(trimmed)) return trimmed.slice(0, 2);
  // State name fallback — treat unknown names as same-state unless both look like codes
  return null;
}

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
  /** Optional compensation cess % on taxable (Wave 18). */
  cessRate?: number;
  /** When true, split GST into CGST/SGST; otherwise IGST. null = unknown POS → zero tax. */
  intraState?: boolean | null;
}

export interface LineTaxResult {
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  cess: number;
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

  const cessRate = Math.max(0, input.cessRate ?? 0);
  const cess = roundMoney(taxableAmount * (cessRate / 100));

  // Unknown place of supply — do not assume intra; withhold tax until known.
  if (input.intraState === null) {
    return {
      gross,
      discountAmount,
      discountPercent,
      taxableAmount,
      cgst: 0,
      sgst: 0,
      igst: 0,
      cess: 0,
      taxTotal: 0,
      lineTotal: taxableAmount,
    };
  }

  const taxRaw = taxableAmount * (input.gstRate / 100);
  const intraState = input.intraState ?? true;

  if (intraState) {
    // BILL-01: CGST == SGST exactly for an intra-state supply (GSTN
    // validation); split symmetrically and let round-off absorb any odd paise.
    const half = roundMoney(taxRaw / 2);
    const cgst = half;
    const sgst = half;
    return {
      gross,
      discountAmount,
      discountPercent,
      taxableAmount,
      cgst,
      sgst,
      igst: 0,
      cess,
      taxTotal: roundMoney(cgst + sgst + cess),
      lineTotal: roundMoney(taxableAmount + cgst + sgst + cess),
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
    cess,
    taxTotal: roundMoney(igst + cess),
    lineTotal: roundMoney(taxableAmount + igst + cess),
  };
}

export interface InvoiceTotalsInput {
  additionalCharges?: number;
  invoiceDiscount?: number;
  applyRoundOff?: boolean;
  invoiceDiscountMode?: InvoiceDiscountMode;
  chargesHsn?: string;
  chargesGstRate?: number;
  intraState?: boolean | null;
}

export function chargesAreTaxable(opts: {
  additionalCharges?: number;
  chargesHsn?: string;
  chargesGstRate?: number;
}): boolean {
  return (
    roundMoney(opts.additionalCharges ?? 0) > 0 &&
    (opts.chargesHsn ?? '').trim().length > 0 &&
    (opts.chargesGstRate ?? 0) > 0
  );
}

function applyLineTaxOnTaxable(
  taxableAmount: number,
  gstRate: number,
  intraState: boolean | null,
  cessRate = 0,
): Pick<LineTaxResult, 'cgst' | 'sgst' | 'igst' | 'cess' | 'taxTotal' | 'lineTotal' | 'taxableAmount'> {
  const cess = roundMoney(taxableAmount * (Math.max(0, cessRate) / 100));
  if (intraState === null) {
    return {
      taxableAmount,
      cgst: 0,
      sgst: 0,
      igst: 0,
      cess: 0,
      taxTotal: 0,
      lineTotal: taxableAmount,
    };
  }
  const taxRaw = taxableAmount * (gstRate / 100);
  if (intraState) {
    // BILL-01: CGST == SGST exactly for an intra-state supply (GSTN
    // validation); split symmetrically and let round-off absorb any odd paise.
    const half = roundMoney(taxRaw / 2);
    const cgst = half;
    const sgst = half;
    return {
      taxableAmount,
      cgst,
      sgst,
      igst: 0,
      cess,
      taxTotal: roundMoney(cgst + sgst + cess),
      lineTotal: roundMoney(taxableAmount + cgst + sgst + cess),
    };
  }
  const igst = roundMoney(taxRaw);
  return {
    taxableAmount,
    cgst: 0,
    sgst: 0,
    igst,
    cess,
    taxTotal: roundMoney(igst + cess),
    lineTotal: roundMoney(taxableAmount + igst + cess),
  };
}

/** Extract exclusive taxable from tax-inclusive line (matches BE discounted-gross extract). */
export function extractExclusiveFromInclusiveLine(input: {
  quantity: number;
  unitPriceInclusive: number;
  discountPercent?: number;
  gstRate: number;
  cessRate?: number;
  cessAmount?: number;
}): { exclusiveUnitPrice: number; taxableAmount: number } {
  const qty = input.quantity;
  if (qty <= 0) {
    return { exclusiveUnitPrice: roundMoney(input.unitPriceInclusive), taxableAmount: 0 };
  }
  const lineGrossInclusive = roundMoney(qty * input.unitPriceInclusive);
  const discountAmt = roundMoney(lineGrossInclusive * ((input.discountPercent ?? 0) / 100));
  let netInclusive = roundMoney(lineGrossInclusive - discountAmt);
  const specific = roundMoney(qty * (input.cessAmount ?? 0));
  if (specific > 0) {
    netInclusive = roundMoney(Math.max(0, netInclusive - specific));
  }
  // FE-03: match `core.services.billing.extract_exclusive_from_inclusive_line` —
  // the ad-valorem cess rate stays in the extraction denominator even when a
  // per-unit specific cess is also present (specific is peeled separately, above).
  const rate = input.gstRate + (input.cessRate ?? 0);
  const taxableAmount =
    rate > 0 ? roundMoney((netInclusive * 100) / (100 + rate)) : netInclusive;
  const exclusiveUnitPrice = roundMoney(taxableAmount / qty);
  return { exclusiveUnitPrice, taxableAmount };
}

export function calculateInvoiceTotals(
  lines: Array<
    Pick<LineTaxResult, 'taxableAmount' | 'taxTotal' | 'cgst' | 'sgst' | 'igst' | 'gross' | 'discountAmount'> & {
      gstRate?: number;
      cessRate?: number;
      cess?: number;
      intraState?: boolean | null;
      /** R5-002: tax-inclusive line gross (Σ qty×MRP) so the displayed Subtotal
       *  on an inclusive-priced document reflects what the customer sees and
       *  foots to the Grand Total. */
      inclusiveGross?: number;
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
  cessTotal: number;
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

  const subtotal = roundMoney(
    lines.reduce((sum, l) => sum + (l.inclusiveGross ?? l.gross ?? l.taxableAmount), 0),
  );
  const lineDiscountTotal = roundMoney(lines.reduce((sum, l) => sum + (l.discountAmount ?? 0), 0));

  let working = lines.map((l) => ({
    taxableAmount: l.taxableAmount,
    gstRate: l.gstRate ?? 0,
    cessRate: l.cessRate ?? 0,
    // Preserve null (unknown POS); only default undefined → intra for legacy callers.
    intraState: l.intraState === null ? null : (l.intraState ?? true),
    cgst: l.cgst ?? 0,
    sgst: l.sgst ?? 0,
    igst: l.igst ?? 0,
    cess: l.cess ?? 0,
    taxTotal: l.taxTotal,
    gross: l.gross,
    discountAmount: l.discountAmount,
  }));

  if (mode === 'BEFORE_TAX' && invoiceDiscount > 0 && working.length > 0) {
    const originalTaxables = working.map((l) => l.taxableAmount);
    const taxableSum = roundMoney(originalTaxables.reduce((s, t) => s + t, 0));
    if (taxableSum > 0) {
      // FE-02: allocate the invoice-level discount exactly as
      // `core.services.billing.compute_document_totals` does — a proportional
      // pass clamped to each line's own taxable, then spread any residual across
      // the lines that still have headroom (never dump it on the last line,
      // which the backend explicitly moved away from in R1-020).
      const remaining = Math.min(invoiceDiscount, taxableSum);
      const adjusted = [...originalTaxables];
      let allocated = 0;
      for (let i = 0; i < adjusted.length; i += 1) {
        let share = roundMoney((originalTaxables[i] / taxableSum) * remaining);
        share = Math.min(share, adjusted[i]);
        adjusted[i] = roundMoney(adjusted[i] - share);
        allocated = roundMoney(allocated + share);
      }
      let residual = roundMoney(remaining - allocated);
      let guard = 0;
      while (residual > 0 && guard < adjusted.length + 2) {
        guard += 1;
        const headroom = adjusted.map((v, i) => (v > 0 ? i : -1)).filter((i) => i >= 0);
        if (headroom.length === 0) break;
        const per = roundMoney(residual / headroom.length);
        if (per <= 0) {
          for (const i of headroom) {
            if (residual <= 0) break;
            const take = Math.min(0.01, adjusted[i], residual);
            adjusted[i] = roundMoney(adjusted[i] - take);
            residual = roundMoney(residual - take);
          }
          break;
        }
        for (const i of headroom) {
          const take = Math.min(per, adjusted[i], residual);
          adjusted[i] = roundMoney(adjusted[i] - take);
          residual = roundMoney(residual - take);
        }
      }
      working = working.map((l, i) => ({
        ...l,
        ...applyLineTaxOnTaxable(adjusted[i], l.gstRate, l.intraState, l.cessRate),
      }));
    }
  }

  const taxableLines = roundMoney(working.reduce((sum, l) => sum + l.taxableAmount, 0));
  let cgstTotal = roundMoney(working.reduce((sum, l) => sum + (l.cgst ?? 0), 0));
  let sgstTotal = roundMoney(working.reduce((sum, l) => sum + (l.sgst ?? 0), 0));
  let igstTotal = roundMoney(working.reduce((sum, l) => sum + (l.igst ?? 0), 0));
  const cessTotal = roundMoney(working.reduce((sum, l) => sum + (l.cess ?? 0), 0));
  const taxableCharges = chargesAreTaxable({
    additionalCharges,
    chargesHsn: opts.chargesHsn,
    chargesGstRate: opts.chargesGstRate,
  });
  let taxableTotal = taxableLines;
  if (taxableCharges) {
    const chargeTax = applyLineTaxOnTaxable(
      additionalCharges,
      opts.chargesGstRate ?? 0,
      opts.intraState ?? null,
    );
    taxableTotal = roundMoney(taxableLines + additionalCharges);
    cgstTotal = roundMoney(cgstTotal + chargeTax.cgst);
    sgstTotal = roundMoney(sgstTotal + chargeTax.sgst);
    igstTotal = roundMoney(igstTotal + chargeTax.igst);
  }
  const taxTotal = roundMoney(cgstTotal + sgstTotal + igstTotal + cessTotal);
  const chargesInGrand = taxableCharges ? 0 : additionalCharges;
  const raw =
    mode === 'BEFORE_TAX'
      ? roundMoney(taxableTotal + taxTotal + chargesInGrand)
      : roundMoney(taxableTotal + taxTotal + chargesInGrand - invoiceDiscount);
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
    cessTotal,
    taxTotal,
    additionalCharges,
    invoiceDiscount,
    roundOff,
    grandTotal: rounded,
    invoiceDiscountMode: mode,
  };
}

// BB-000320: ported from backend/core/services/billing.py IN_STATE_NAME_TO_CODE —
// keep in sync so FE tax preview matches BE Complete posting (BB-000063).
const IN_STATE_NAME_TO_CODE: Record<string, string> = {
  'andaman and nicobar islands': '35',
  'andaman & nicobar islands': '35',
  'andhra pradesh': '37',
  'arunachal pradesh': '12',
  assam: '18',
  bihar: '10',
  chandigarh: '04',
  chhattisgarh: '22',
  'dadra and nagar haveli and daman and diu': '26',
  'dadra and nagar haveli': '26',
  'daman and diu': '26',
  delhi: '07',
  'nct of delhi': '07',
  goa: '30',
  gujarat: '24',
  haryana: '06',
  'himachal pradesh': '02',
  'jammu and kashmir': '01',
  'jammu & kashmir': '01',
  jharkhand: '20',
  karnataka: '29',
  kerala: '32',
  ladakh: '38',
  lakshadweep: '31',
  'madhya pradesh': '23',
  maharashtra: '27',
  manipur: '14',
  meghalaya: '17',
  mizoram: '15',
  nagaland: '13',
  odisha: '21',
  orissa: '21',
  puducherry: '34',
  pondicherry: '34',
  punjab: '03',
  rajasthan: '08',
  sikkim: '11',
  'tamil nadu': '33',
  telangana: '36',
  tripura: '16',
  'uttar pradesh': '09',
  uttarakhand: '05',
  'west bengal': '19',
  // Common abbreviations
  an: '35',
  ap: '37',
  ar: '12',
  as: '18',
  br: '10',
  ch: '04',
  cg: '22',
  ct: '22',
  dn: '26',
  dd: '26',
  dl: '07',
  ga: '30',
  gj: '24',
  hr: '06',
  hp: '02',
  jk: '01',
  jh: '20',
  ka: '29',
  kl: '32',
  la: '38',
  ld: '31',
  mp: '23',
  mh: '27',
  mn: '14',
  ml: '17',
  mz: '15',
  nl: '13',
  od: '21',
  or: '21',
  py: '34',
  pb: '03',
  rj: '08',
  sk: '11',
  tn: '33',
  ts: '36',
  tg: '36',
  tr: '16',
  up: '09',
  uk: '05',
  ua: '05',
  wb: '19',
  'other territory': '96',
  'other country': '96',
  foreign: '96',
  export: '96',
};

export const VALID_GST_STATE_CODES = new Set([
  ...Object.values(IN_STATE_NAME_TO_CODE),
  '96',
  '97',
]);

/**
 * Canonical GST state code from GSTIN (digits 0–1) or a mapped state name/abbr.
 * Mirrors backend `core.services.billing.extract_state_code` (BB-000320).
 */
export function extractStateCode(value?: string): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.length === 15 && /^\d{2}/.test(trimmed)) {
    const code = trimmed.slice(0, 2);
    return VALID_GST_STATE_CODES.has(code) ? code : null;
  }
  if (trimmed.length === 2 && /^\d{2}$/.test(trimmed) && VALID_GST_STATE_CODES.has(trimmed)) {
    return trimmed;
  }
  const key = trimmed.toLowerCase().replace(/\./g, '').replace(/\s+/g, ' ').trim();
  return IN_STATE_NAME_TO_CODE[key] ?? null;
}

/** Fail closed when GST tax applies but party place of supply is unknown. */
export function assertPlaceOfSupplyKnown(
  companyGstinOrState: string | undefined,
  partyGstinOrState: string | undefined,
  options?: { assumeLocalStateForBlankParty?: boolean },
): void {
  if (options?.assumeLocalStateForBlankParty && !(partyGstinOrState || '').trim()) {
    return;
  }
  if (resolvePlaceOfSupply(companyGstinOrState, partyGstinOrState) === 'unknown') {
    throw new Error(
      'Customer/supplier state or GSTIN is required for GST invoices. Add place of supply or enable assume-local in GST settings.',
    );
  }
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
  // BB-000424: never invent inter/intra from free-text string equality.
  return 'unknown';
}

/**
 * Compare company GSTIN/state with party GSTIN/state for intra-state GST.
 * Returns null when party place of supply is unknown (do not assume intra),
 * unless assumeLocalStateForBlankParty matches BE billing.is_intra_state.
 */
export function isIntraState(
  companyGstinOrStateCode: string | undefined,
  partyGstinOrState: string | undefined,
  options?: { assumeLocalStateForBlankParty?: boolean },
): boolean | null {
  const place = resolvePlaceOfSupply(companyGstinOrStateCode, partyGstinOrState);
  if (place === 'unknown') {
    // BB-000278: match BE — blank party + assume-local → treat as intra.
    if (options?.assumeLocalStateForBlankParty) return true;
    return null;
  }
  return place === 'intra';
}

export function placeOfSupplyKnown(partyState?: string, partyGstin?: string): boolean {
  // BB-000390: known only when a real state code can be extracted (not any non-empty text).
  return extractStateCode(partyState) != null || extractStateCode(partyGstin) != null;
}

export function addDaysIso(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  calculateInvoiceTotals,
  calculateLineTax,
  extractExclusiveFromInclusiveLine,
  extractStateCode,
  isIntraState,
  resolvePlaceOfSupply,
} from '@/utils/tax';

/**
 * BUG-216/724: read the single canonical fixture shared with
 * backend/tests/test_billing_totals.py instead of a hand-copied duplicate
 * that can silently drift from the backend cases.
 */
const fixturePath = path.resolve(
  __dirname,
  '../../../backend/tests/fixtures/tax_parity_cases.json',
);
const cases: Array<{
  id: string;
  level?: string;
  priceMode?: string;
  quantity: number;
  unitPrice: number;
  unitPriceInclusive?: number;
  gstRate: number;
  intraState: boolean;
  discountPercent: number;
  expected: {
    taxableAmount: number;
    cgst: number;
    sgst: number;
    igst: number;
    lineTotal: number;
    exclusiveUnitPrice?: number;
  };
}> = JSON.parse(readFileSync(fixturePath, 'utf-8')).filter(
  (c: { level?: string }) => !c.level || c.level === 'line',
);

describe('tax utils', () => {
  for (const c of cases) {
    it(`parity: ${c.id}`, () => {
      let unitPrice = c.unitPrice;
      let discountPercent = c.discountPercent;
      if (c.priceMode === 'INCLUSIVE') {
        const extracted = extractExclusiveFromInclusiveLine({
          quantity: c.quantity,
          unitPriceInclusive: c.unitPriceInclusive ?? c.unitPrice,
          discountPercent: c.discountPercent,
          gstRate: c.gstRate,
        });
        unitPrice = extracted.exclusiveUnitPrice;
        discountPercent = 0;
        if (c.expected.exclusiveUnitPrice != null) {
          expect(extracted.exclusiveUnitPrice).toBe(c.expected.exclusiveUnitPrice);
        }
      }
      const line = calculateLineTax({
        quantity: c.quantity,
        unitPrice,
        gstRate: c.gstRate,
        intraState: c.intraState,
        discountPercent,
      });
      expect(line.taxableAmount).toBe(c.expected.taxableAmount);
      expect(line.cgst).toBe(c.expected.cgst);
      expect(line.sgst).toBe(c.expected.sgst);
      expect(line.igst).toBe(c.expected.igst);
      expect(line.lineTotal).toBe(c.expected.lineTotal);
    });
  }

  it('applies discount before tax on the line', () => {
    const line = calculateLineTax({
      quantity: 1,
      unitPrice: 200,
      discountPercent: 10,
      gstRate: 5,
    });
    expect(line.taxableAmount).toBe(180);
    expect(line.taxTotal).toBe(9);
    expect(line.discountAmount).toBe(20);
  });

  it('marks blank party place of supply as unknown', () => {
    expect(resolvePlaceOfSupply('Karnataka', '')).toBe('unknown');
    expect(resolvePlaceOfSupply('29ABCDE1234F1ZW', '27AAAAA0000A1Z2')).toBe('inter');
    expect(resolvePlaceOfSupply('29ABCDE1234F1ZW', '29BBBBB0000B1ZP')).toBe('intra');
  });

  it('BB-000232: blank company place of supply is unknown', () => {
    expect(resolvePlaceOfSupply('', 'Karnataka')).toBe('unknown');
    expect(resolvePlaceOfSupply(undefined, '29BBBBB0000B1ZP')).toBe('unknown');
    expect(isIntraState('', 'Karnataka')).toBeNull();
  });

  it('BB-000033: blank party isIntraState is null, not intra', () => {
    expect(isIntraState('Karnataka', '')).toBeNull();
    expect(isIntraState('29ABCDE1234F1ZW', undefined)).toBeNull();
    expect(isIntraState('29ABCDE1234F1ZW', '29BBBBB0000B1ZP')).toBe(true);
    expect(isIntraState('29ABCDE1234F1ZW', '27AAAAA0000A1Z2')).toBe(false);
  });

  it('BB-000278: assumeLocalStateForBlankParty treats blank party as intra', () => {
    expect(
      isIntraState('Karnataka', '', { assumeLocalStateForBlankParty: true }),
    ).toBe(true);
    expect(
      isIntraState('29ABCDE1234F1ZW', undefined, { assumeLocalStateForBlankParty: true }),
    ).toBe(true);
    // Still respects known inter-state when party is present.
    expect(
      isIntraState('29ABCDE1234F1ZW', '27AAAAA0000A1Z2', {
        assumeLocalStateForBlankParty: true,
      }),
    ).toBe(false);
  });

  it('BB-000320: extractStateCode maps Indian state names/abbreviations to codes', () => {
    expect(extractStateCode('Karnataka')).toBe('29');
    expect(extractStateCode('karnataka')).toBe('29');
    expect(extractStateCode('  Karnataka  ')).toBe('29');
    expect(extractStateCode('KA')).toBe('29');
    expect(extractStateCode('Maharashtra')).toBe('27');
    expect(extractStateCode('Tamil Nadu')).toBe('33');
    expect(extractStateCode('29ABCDE1234F1ZW')).toBe('29');
    expect(extractStateCode('Atlantis')).toBeNull();
    expect(extractStateCode('')).toBeNull();
    expect(extractStateCode(undefined)).toBeNull();
  });

  it('BB-000320: isIntraState matches BE for company GSTIN vs named party state', () => {
    // Company GSTIN in Karnataka (29...) + party state name "Karnataka" → intra.
    expect(isIntraState('29ABCDE1234F1ZW', 'Karnataka')).toBe(true);
    // Party in a different named state → inter.
    expect(isIntraState('29ABCDE1234F1ZW', 'Maharashtra')).toBe(false);
  });

  it('BB-000033: unknown POS yields zero tax (no CGST split)', () => {
    const line = calculateLineTax({
      quantity: 1,
      unitPrice: 100,
      gstRate: 18,
      intraState: null,
    });
    expect(line.taxableAmount).toBe(100);
    expect(line.cgst).toBe(0);
    expect(line.sgst).toBe(0);
    expect(line.igst).toBe(0);
    expect(line.taxTotal).toBe(0);
    expect(line.lineTotal).toBe(100);
  });
});

describe('calculateInvoiceTotals', () => {
  it('BUG-418: aggregates taxable/tax across multiple lines with round-off', () => {
    const lineA = calculateLineTax({ quantity: 1, unitPrice: 10.05, gstRate: 18 });
    const lineB = calculateLineTax({ quantity: 2, unitPrice: 100, gstRate: 18 });
    const totals = calculateInvoiceTotals([lineA, lineB]);
    expect(totals.taxableTotal).toBe(210.05);
    expect(totals.cgstTotal + totals.sgstTotal).toBe(37.81);
    // 210.05 + 37.81 = 247.86 → rounds to 248
    expect(totals.grandTotal).toBe(248);
    expect(totals.roundOff).toBe(0.14);
  });

  it('BUG-418: applyRoundOff=false leaves the exact fractional total', () => {
    const line = calculateLineTax({ quantity: 1, unitPrice: 99.4, gstRate: 0 });
    const totals = calculateInvoiceTotals([line], { applyRoundOff: false });
    expect(totals.grandTotal).toBe(99.4);
    expect(totals.roundOff).toBe(0);
  });

  it('BUG-418: BEFORE_TAX invoice discount is allocated proportionally then re-taxed', () => {
    const lineA = { ...calculateLineTax({ quantity: 1, unitPrice: 100, gstRate: 18 }), gstRate: 18 };
    const lineB = { ...calculateLineTax({ quantity: 1, unitPrice: 300, gstRate: 18 }), gstRate: 18 };
    const totals = calculateInvoiceTotals([lineA, lineB], {
      applyRoundOff: false,
      invoiceDiscount: 40,
      invoiceDiscountMode: 'BEFORE_TAX',
    });
    // 40 spread proportionally over 100/400 total taxable (25/75 split) → 360 remains taxable
    expect(totals.taxableTotal).toBe(360);
    expect(totals.cgstTotal + totals.sgstTotal).toBe(64.8);
    expect(totals.grandTotal).toBe(424.8);
  });

  it('BUG-418: additional charges add to the grand total without altering taxable total', () => {
    const line = calculateLineTax({ quantity: 1, unitPrice: 100, gstRate: 18 });
    const totals = calculateInvoiceTotals([line], {
      applyRoundOff: false,
      additionalCharges: 50,
    });
    expect(totals.taxableTotal).toBe(100);
    expect(totals.grandTotal).toBe(168);
  });

  it('taxable freight requires HSN and GST rate then adds GST to totals', () => {
    const line = calculateLineTax({ quantity: 1, unitPrice: 100, gstRate: 18, intraState: true });
    const totals = calculateInvoiceTotals([{ ...line, gstRate: 18, intraState: true }], {
      applyRoundOff: false,
      additionalCharges: 50,
      chargesHsn: '9965',
      chargesGstRate: 18,
      intraState: true,
    });
    expect(totals.taxableTotal).toBe(150);
    expect(totals.cgstTotal + totals.sgstTotal).toBe(27);
    expect(totals.grandTotal).toBe(177);
  });

  it('tax-inclusive extract from discounted line gross (Phase 2)', () => {
    const { exclusiveUnitPrice, taxableAmount } = extractExclusiveFromInclusiveLine({
      quantity: 2,
      unitPriceInclusive: 118,
      discountPercent: 0,
      gstRate: 18,
    });
    expect(taxableAmount).toBe(200);
    expect(exclusiveUnitPrice).toBe(100);
  });

  it('BB-000033: calculateInvoiceTotals with unknown POS shows zero tax', () => {
    const line = {
      ...calculateLineTax({ quantity: 1, unitPrice: 100, gstRate: 18, intraState: null }),
      gstRate: 18,
      intraState: null as boolean | null,
    };
    const totals = calculateInvoiceTotals([line], { applyRoundOff: false });
    expect(totals.taxableTotal).toBe(100);
    expect(totals.cgstTotal).toBe(0);
    expect(totals.sgstTotal).toBe(0);
    expect(totals.igstTotal).toBe(0);
    expect(totals.taxTotal).toBe(0);
    expect(totals.grandTotal).toBe(100);
  });

  it('BB-000518: AFTER_TAX discount reduces grand total without changing taxable', () => {
    const line = calculateLineTax({ quantity: 1, unitPrice: 100, gstRate: 18 });
    const totals = calculateInvoiceTotals([line], {
      applyRoundOff: false,
      invoiceDiscount: 10,
      invoiceDiscountMode: 'AFTER_TAX',
    });
    expect(totals.taxableTotal).toBe(100);
    expect(totals.grandTotal).toBe(108);
  });

  it('Wave 18: cess rolls into line and invoice totals', () => {
    const line = calculateLineTax({ quantity: 1, unitPrice: 100, gstRate: 18, cessRate: 1, intraState: true });
    expect(line.cess).toBe(1);
    expect(line.lineTotal).toBe(119);
    const totals = calculateInvoiceTotals([{ ...line, gstRate: 18, cessRate: 1, intraState: true }], {
      applyRoundOff: false,
    });
    expect(totals.cessTotal).toBe(1);
    expect(totals.taxTotal).toBe(19);
    expect(totals.grandTotal).toBe(119);
  });
});

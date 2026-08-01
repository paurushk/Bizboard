import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { calculateInvoiceTotals, calculateLineTax, resolvePlaceOfSupply } from '@/utils/tax';

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
  quantity: number;
  unitPrice: number;
  gstRate: number;
  intraState: boolean;
  discountPercent: number;
  expected: { taxableAmount: number; cgst: number; sgst: number; igst: number; lineTotal: number };
}> = JSON.parse(readFileSync(fixturePath, 'utf-8'));

describe('tax utils', () => {
  for (const c of cases) {
    it(`parity: ${c.id}`, () => {
      const line = calculateLineTax({
        quantity: c.quantity,
        unitPrice: c.unitPrice,
        gstRate: c.gstRate,
        intraState: c.intraState,
        discountPercent: c.discountPercent,
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
    expect(resolvePlaceOfSupply('29ABCDE1234F1Z5', '27AAAAA0000A1Z5')).toBe('inter');
    expect(resolvePlaceOfSupply('29ABCDE1234F1Z5', '29BBBBB0000B1Z5')).toBe('intra');
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
});

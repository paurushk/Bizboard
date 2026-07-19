import { describe, expect, it } from 'vitest';
import { calculateInvoiceTotals, calculateLineTax } from '@/utils/tax';

describe('tax utils', () => {
  it('splits CGST/SGST for intra-state lines', () => {
    const line = calculateLineTax({
      quantity: 2,
      unitPrice: 100,
      gstRate: 18,
      intraState: true,
    });
    expect(line.taxableAmount).toBe(200);
    expect(line.taxTotal).toBe(36);
    expect(line.cgst).toBe(18);
    expect(line.sgst).toBe(18);
    expect(line.igst).toBe(0);
    expect(line.lineTotal).toBe(236);
  });

  it('uses IGST for inter-state lines', () => {
    const line = calculateLineTax({
      quantity: 1,
      unitPrice: 100,
      gstRate: 12,
      intraState: false,
    });
    expect(line.igst).toBe(12);
    expect(line.cgst).toBe(0);
    expect(line.sgst).toBe(0);
  });

  it('applies discount before tax', () => {
    const line = calculateLineTax({
      quantity: 1,
      unitPrice: 200,
      discountPercent: 10,
      gstRate: 5,
    });
    expect(line.taxableAmount).toBe(180);
    expect(line.taxTotal).toBe(9);
  });

  it('rounds invoice grand total', () => {
    const totals = calculateInvoiceTotals([
      calculateLineTax({ quantity: 1, unitPrice: 99.4, gstRate: 0 }),
    ]);
    expect(totals.grandTotal).toBe(99);
    expect(totals.roundOff).toBe(-0.4);
  });
});

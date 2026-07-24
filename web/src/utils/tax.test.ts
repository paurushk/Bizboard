import { describe, expect, it } from 'vitest';
import { calculateLineTax, resolvePlaceOfSupply } from '@/utils/tax';

const cases = [
  {
    id: 'odd_paise_10_05_18',
    quantity: 1,
    unitPrice: 10.05,
    gstRate: 18,
    intraState: true,
    discountPercent: 0,
    expected: { taxableAmount: 10.05, cgst: 0.9, sgst: 0.91, igst: 0, lineTotal: 11.86 },
  },
  {
    id: 'even_200_18',
    quantity: 2,
    unitPrice: 100,
    gstRate: 18,
    intraState: true,
    discountPercent: 0,
    expected: { taxableAmount: 200, cgst: 18, sgst: 18, igst: 0, lineTotal: 236 },
  },
  {
    id: 'inter_100_12',
    quantity: 1,
    unitPrice: 100,
    gstRate: 12,
    intraState: false,
    discountPercent: 0,
    expected: { taxableAmount: 100, cgst: 0, sgst: 0, igst: 12, lineTotal: 112 },
  },
];

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

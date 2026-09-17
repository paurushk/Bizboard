import { describe, expect, it } from 'vitest';
import {
  buildConvertItemsPayload,
  quotationHasRemainingAfterConvert,
  remainingQuotationQty,
} from '@/utils/quotationConvert';

describe('quotationConvert — CFT-115', () => {
  it('remaining is quoted minus already converted', () => {
    expect(remainingQuotationQty({ quantity: '10', convertedQuantity: '4' })).toBe(6);
    expect(remainingQuotationQty({ quantity: 10 })).toBe(10);
    expect(remainingQuotationQty({ quantity: '3', convertedQuantity: '3' })).toBe(0);
  });

  it('payload includes only positive convert qty and rejects over-remaining', () => {
    const lines = [
      { id: 1, quantity: '10', convertedQuantity: '4' },
      { id: 2, quantity: '5', convertedQuantity: '0' },
    ];
    expect(buildConvertItemsPayload(lines, { 1: 3, 2: 0 })).toEqual([{ id: 1, quantity: 3 }]);
    expect(() => buildConvertItemsPayload(lines, { 1: 7 })).toThrow(/exceeds remaining/);
  });

  it('detects remainder after a partial convert', () => {
    const lines = [{ id: 1, quantity: '10', convertedQuantity: '4' }];
    expect(quotationHasRemainingAfterConvert(lines, [{ id: 1, quantity: 3 }])).toBe(true);
    expect(quotationHasRemainingAfterConvert(lines, [{ id: 1, quantity: 6 }])).toBe(false);
  });
});

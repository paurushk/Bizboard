import { describe, expect, it } from 'vitest';
import type { Product } from '@/types/domain';
import {
  clampCopies,
  isCode128Encodable,
  isThermalSize,
  labelFields,
  labelItemsParam,
  labelPrice,
  MAX_COPIES,
  parseLabelItems,
} from '@/pages/inventory/labelHelpers';

describe('clampCopies', () => {
  it('keeps whole, non-negative numbers up to the cap', () => {
    expect(clampCopies('3')).toBe(3);
    expect(clampCopies('2.9')).toBe(2);
    expect(clampCopies(-4)).toBe(0);
    expect(clampCopies('abc')).toBe(0);
    expect(clampCopies(100000)).toBe(MAX_COPIES);
    expect(clampCopies(100, 50)).toBe(50);
  });
});

describe('labelPrice', () => {
  const p = (mrp: unknown, sellingPrice: unknown) => ({ mrp, sellingPrice }) as Pick<Product, 'mrp' | 'sellingPrice'>;
  it('prefers MRP', () => expect(labelPrice(p('150', '120'))).toBe('150'));
  it('does not print zero when MRP is unset', () => {
    expect(labelPrice(p('0', '120'))).toBe('120');
    expect(labelPrice(p(null, '120'))).toBe('120');
    expect(labelPrice(p(0, '120'))).toBe('120');
  });
});

describe('items link from a purchase bill', () => {
  it('round-trips, adding the lines of one item and rounding fractions up', () => {
    const param = labelItemsParam([
      { product: 12, quantity: '5.000' },
      { product: 13, quantity: '2.5' },
      { product: 12, quantity: 1 },
    ]);
    expect(param).toBe('12:6,13:3');
    expect(parseLabelItems(param)).toEqual([{ productId: 12, copies: 6 }, { productId: 13, copies: 3 }]);
  });
  it('ignores junk and caps the copies', () => {
    expect(parseLabelItems('x:3,0:2,7:99999,9')).toEqual([{ productId: 7, copies: MAX_COPIES }, { productId: 9, copies: 1 }]);
    expect(parseLabelItems(null)).toEqual([]);
  });
});

describe('thermal and sheet labels', () => {
  it('knows which sizes a thermal printer can print', () => {
    expect(isThermalSize('medium')).toBe(true);
    expect(isThermalSize('a4_3x8')).toBe(false);
  });

  it('says whether a code can be a CODE128 barcode', () => {
    expect(isCode128Encodable('8901234567890')).toBe(true);
    expect(isCode128Encodable('AB-12 x')).toBe(true);
    expect(isCode128Encodable('चाय-1')).toBe(false);
    expect(isCode128Encodable('')).toBe(false);
  });

  // The same fixtures as the server test of the ZPL file (test_inventory_idr11_labels.py): the browser
  // label and the thermal label must read the same for the same item.
  it('writes the fields the thermal label writes', () => {
    const tea = { name: 'Green Tea', barcode: '8901234567890', sku: 'LB-1', mrp: '120', sellingPrice: '100' };
    expect(labelFields(tea, { batchNo: 'B-77', expiryDate: '2027-03-31' })).toEqual({
      name: 'Green Tea', code: '8901234567890', price: 'Rs 120.00', batch: 'B-77', expiry: '2027-03-31',
    });
    expect(labelFields({ ...tea, mrp: '0', sellingPrice: '99.5' }, null)).toMatchObject({ price: 'Rs 99.50', batch: '' });
    expect(labelFields({ ...tea, barcode: '' }, null).code).toBe('LB-1');
  });
});

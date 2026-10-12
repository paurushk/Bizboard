import { describe, expect, it } from 'vitest';
import { resolveListUnitPrice } from '@/utils/priceList';

// Keep identical to SLAB_PARITY in backend/tests/test_sales_order_guards.py: the Quick Entry fallback must price a
// line the way the server will when it saves it.
const SLAB_PARITY: Array<[number, number | null]> = [
  [0.5, null],
  [1, 100],
  [9, 100],
  [10, 90],
  [49, 90],
  [50, 72],
  [500, 72],
];

const LISTS = [
  {
    id: 1,
    name: 'Tiered',
    items: [
      { product: 7, unitPrice: '100', minQty: '1', maxQty: '9', discountPct: '0' },
      { product: 7, unitPrice: '90', minQty: '10', maxQty: '49', discountPct: '0' },
      { product: 7, unitPrice: '80', minQty: '50', maxQty: null, discountPct: '10' },
    ],
  },
];

describe('resolveListUnitPrice slab parity with the server', () => {
  it.each(SLAB_PARITY)('quantity %s -> %s', (qty, expected) => {
    const hit = resolveListUnitPrice(LISTS, 1, 7, qty);
    if (expected === null) expect(hit).toBeNull();
    else {
      expect(hit?.unitPrice).toBe(expected);
      expect(hit?.listName).toBe('Tiered');
    }
  });
});

import { describe, expect, it } from 'vitest';
import { formatProductOptionLabel } from './formatProductOptionLabel';
import type { Product } from '@/types/domain';

const product = {
  id: 1,
  name: 'Widget',
  sku: 'W-1',
  unitName: 'PCS',
  status: 'ACTIVE',
} as Product;

describe('formatProductOptionLabel', () => {
  it('uses the explicit available qty argument, not a Product stock field', () => {
    expect(formatProductOptionLabel(product, 4)).toBe('Widget · W-1 · PCS · avail 4');
  });

  it('omits avail when the stock identity was not passed', () => {
    expect(formatProductOptionLabel(product)).toBe('Widget · W-1 · PCS');
  });
});

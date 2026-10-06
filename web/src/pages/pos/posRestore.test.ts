import { describe, expect, it } from 'vitest';
import { omitQueuedHeldSessions, repriceLines } from './posRestore';
import type { Product } from '@/types/domain';

function product(partial: Partial<Product> & Pick<Product, 'id'>): Product {
  return {
    name: 'Item',
    sku: 'SKU',
    sellingPrice: '10',
    status: 'ACTIVE',
    gstRate: '0',
    ...partial,
  } as Product;
}

describe('repriceLines', () => {
  it('keeps the current selling price and drops a missing product', () => {
    const kept = product({ id: 1, sellingPrice: '12' });
    const result = repriceLines(
      [
        { product: product({ id: 1, sellingPrice: '10' }), quantity: 1 },
        { product: product({ id: 2, sellingPrice: '4' }), quantity: 1 },
      ],
      new Map([[1, kept]]),
    );
    expect(result.changed).toBe(true);
    expect(result.lines).toHaveLength(1);
    expect(result.lines[0]?.product.sellingPrice).toBe('12');
  });

  it('reports no change when the price is the same', () => {
    const same = product({ id: 1, sellingPrice: '10' });
    const result = repriceLines([{ product: same, quantity: 2 }], new Map([[1, same]]));
    expect(result.changed).toBe(false);
    expect(result.lines).toHaveLength(1);
  });
});

describe('omitQueuedHeldSessions', () => {
  const sessions = {
    primary: { idempotencyKey: 'queued-1' },
    held: { idempotencyKey: null },
  };

  it('drops a session whose checkout is already in the outbox', () => {
    const result = omitQueuedHeldSessions(sessions, ['primary', 'held'], 'primary', new Set(['queued-1']));
    expect(result.droppedKeys).toEqual(['queued-1']);
    expect(result.sessionIds).toEqual(['held']);
    expect(result.activeSessionId).toBe('held');
    expect(result.sessions.primary).toBeUndefined();
  });

  it('keeps an uncommitted held bill', () => {
    const result = omitQueuedHeldSessions(sessions, ['primary', 'held'], 'held', new Set(['other']));
    expect(result.droppedCount).toBe(0);
    expect(result.sessionIds).toEqual(['primary', 'held']);
    expect(result.activeSessionId).toBe('held');
  });
});

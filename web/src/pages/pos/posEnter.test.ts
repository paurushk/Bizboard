import { describe, expect, it } from 'vitest';
import { choosePosEnter, type PosEnterProduct } from './posEnter';

const milk: PosEnterProduct = { id: 1, sku: 'MILK-FC-1L', barcode: '8901001' };
const salt: PosEnterProduct = { id: 2, sku: 'SALT-1', barcode: '8901002' };

describe('choosePosEnter', () => {
  it('selects a highlighted name and does not treat the query as a barcode', () => {
    const choice = choosePosEnter({
      query: 'milk',
      highlighted: milk,
      listOpen: true,
      catalog: [milk, salt],
      optionsStale: false,
    });
    expect(choice).toEqual({ action: 'add', productId: 1, via: 'highlight' });
  });

  it('adds the exact SKU while a fuzzy option is highlighted', () => {
    const choice = choosePosEnter({
      query: 'MILK-FC-1L',
      highlighted: salt,
      listOpen: true,
      catalog: [milk, salt],
      optionsStale: false,
    });
    expect(choice).toEqual({ action: 'add', productId: 1, via: 'exact' });
  });

  it('waits when a barcode Enter arrives before options refresh', () => {
    const choice = choosePosEnter({
      query: '8901001999',
      highlighted: salt,
      listOpen: true,
      catalog: [milk, salt],
      optionsStale: true,
    });
    expect(choice.action).toBe('wait');
  });

  it('looks up a nonsense code when nothing is highlighted', () => {
    const choice = choosePosEnter({
      query: 'nope',
      highlighted: null,
      listOpen: false,
      catalog: [milk],
      optionsStale: false,
    });
    expect(choice.action).toBe('barcode-lookup');
  });

  it('does not add a single fuzzy match when nothing is highlighted', () => {
    const choice = choosePosEnter({
      query: 'mil',
      highlighted: null,
      listOpen: true,
      catalog: [milk],
      optionsStale: false,
    });
    expect(choice.action).toBe('barcode-lookup');
  });
});

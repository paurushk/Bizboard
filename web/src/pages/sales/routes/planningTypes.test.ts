import { describe, expect, it } from 'vitest';
import {
  acknowledgementPayload,
  groupByArea,
  risksToAccept,
  roleMayAccept,
  totalsFor,
  whyNotSelectable,
  type PlanRisk,
  type PlanSummary,
} from './planningTypes';

const risk = (code: string, level: PlanRisk['level'], override: PlanRisk['override']): PlanRisk => ({ code, level, message: code, override });
const sum = (over: Partial<PlanSummary> = {}): PlanSummary => ({
  order: 1, status: 'CONFIRMED', customer: { id: 1, name: 'A', pincode: '560001' }, lines: [], lineCount: 1,
  totalQuantity: '2', grandTotal: '100.00',
  bill: { billStatus: 'order_only', paymentTermsDays: 0, onCredit: false, amountToCollect: '100.00', invoices: [] },
  risks: [], ready: true, hasWarnings: false, ...over,
});

describe('roleMayAccept', () => {
  it('follows the override level', () => {
    expect(roleMayAccept('OWNER', 'none')).toBe(false);
    expect(roleMayAccept('OWNER', 'owner')).toBe(true);
    expect(roleMayAccept('MANAGER', 'owner')).toBe(false);
    expect(roleMayAccept('MANAGER', 'manager')).toBe(true);
    expect(roleMayAccept('SALES_STAFF', 'manager')).toBe(false);
    expect(roleMayAccept('SALES_STAFF', 'any')).toBe(true);
    expect(roleMayAccept(undefined, 'any')).toBe(true);
  });
});

describe('risksToAccept / whyNotSelectable', () => {
  const s = sum({ risks: [risk('late', 'info', 'any'), risk('no_phone', 'warn', 'any'), risk('over_credit_limit', 'warn', 'manager')] });
  it('info never needs accepting', () => {
    expect(risksToAccept(s, 'OWNER').map((r) => r.code)).toEqual(['no_phone', 'over_credit_limit']);
  });
  it('a role that cannot accept a risk is stopped by it', () => {
    expect(whyNotSelectable(s, 'SALES_STAFF')?.code).toBe('over_credit_limit');
    expect(whyNotSelectable(s, 'MANAGER')).toBeNull();
  });
  it('a block with no override stops everyone', () => {
    expect(whyNotSelectable(sum({ risks: [risk('already_on_route', 'block', 'none')] }), 'OWNER')?.code).toBe('already_on_route');
  });
});

describe('acknowledgementPayload', () => {
  it('flattens to one entry per order and risk', () => {
    expect(acknowledgementPayload({ 1: { a: 'x', b: 'y' }, 2: { a: 'z' } })).toEqual([
      { order: 1, code: 'a', reason: 'x' },
      { order: 1, code: 'b', reason: 'y' },
      { order: 2, code: 'a', reason: 'z' },
    ]);
    expect(acknowledgementPayload({})).toEqual([]);
  });
});

describe('totalsFor', () => {
  it('adds quantity, value and what is to be collected', () => {
    const t = totalsFor([sum(), sum({ totalQuantity: '3', grandTotal: '50.50', bill: { ...sum().bill, amountToCollect: '0.00' } })]);
    expect(t).toEqual({ orders: 2, quantity: 5, value: 150.5, toCollect: 100 });
  });
  it('is zero for nothing', () => {
    expect(totalsFor([])).toEqual({ orders: 0, quantity: 0, value: 0, toCollect: 0 });
  });
});

describe('groupByArea', () => {
  it('orders by pincode and puts the unknown area last', () => {
    const rows = [
      sum({ order: 1, customer: { id: 1, name: 'A', pincode: '560090' } }),
      sum({ order: 2, customer: { id: 2, name: 'B', pincode: '' } }),
      sum({ order: 3, customer: { id: 3, name: 'C', pincode: '560010' } }),
      sum({ order: 4, customer: { id: 4, name: 'D', pincode: '560010' } }),
    ];
    const g = groupByArea(rows);
    expect(g.map((x) => x.pincode)).toEqual(['560010', '560090', '—']);
    expect(g[0].rows.map((r) => r.order)).toEqual([3, 4]);
  });
});

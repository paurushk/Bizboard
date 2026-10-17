import { describe, expect, it } from 'vitest';
import type { Product } from '@/types/domain';
import {
  buildReceipts,
  filterTransfers,
  lineProblem,
  openShortages,
  transitDays,
  receivedProblem,
  summarizeLines,
  transferActions,
  type LineDraft,
} from '@/pages/inventory/transferHelpers';

const product = (over: Partial<Product> = {}) => ({ id: 1, name: 'Soap', sku: 'S', ...over }) as Product;
const line = (over: Partial<LineDraft> = {}): LineDraft => ({
  key: 'a', product: product(), batch: '', qty: '2', serials: '', ...over,
});

describe('transferActions', () => {
  it('lets a draft be sent or dropped', () => {
    expect(transferActions('DRAFT', 'SALES_STAFF')).toEqual(['dispatch', 'cancel']);
  });
  it('lets goods in transit be received or pulled back', () => {
    expect(transferActions('DISPATCHED', 'SALES_STAFF')).toEqual(['receive', 'cancel']);
  });
  it('keeps undoing a received transfer to owners and managers', () => {
    expect(transferActions('COMPLETED', 'OWNER')).toEqual(['cancel']);
    expect(transferActions('COMPLETED', 'MANAGER')).toEqual(['cancel']);
    expect(transferActions('COMPLETED', 'SALES_STAFF')).toEqual([]);
    expect(transferActions('COMPLETED', undefined)).toEqual([]);
  });
  it('offers nothing on a cancelled transfer', () => {
    expect(transferActions('CANCELLED', 'OWNER')).toEqual([]);
  });
});

describe('summarizeLines', () => {
  it('counts lines and adds quantities', () => {
    expect(summarizeLines([{ quantity: '2.5' }, { quantity: 3 }])).toEqual({ count: 2, qty: 5.5 });
    expect(summarizeLines(undefined)).toEqual({ count: 0, qty: 0 });
  });
});

describe('lineProblem', () => {
  it('passes a plain line', () => {
    expect(lineProblem(line())).toBeNull();
  });
  it('wants a product and a positive quantity', () => {
    expect(lineProblem(line({ product: null }))).toEqual({ code: 'product' });
    for (const qty of ['', '0', '-1', 'x']) expect(lineProblem(line({ qty }))).toEqual({ code: 'qty' });
  });
  it('wants a batch for a batch-tracked item', () => {
    expect(lineProblem(line({ product: product({ trackBatch: true }) }))).toEqual({ code: 'batch' });
    expect(lineProblem(line({ product: product({ trackBatch: true }), batch: '7' }))).toBeNull();
  });
  it('wants as many serials as units', () => {
    const serial = product({ trackSerial: true });
    expect(lineProblem(line({ product: serial, qty: '2', serials: 'A1' }))).toEqual({ code: 'serials', qty: 2, count: 1 });
    expect(lineProblem(line({ product: serial, qty: '2', serials: 'A1, A2' }))).toBeNull();
    expect(lineProblem(line({ product: serial, qty: '2', serials: 'A1\nA2' }))).toBeNull();
  });
});

describe('buildReceipts', () => {
  const lines = [{ id: 1, quantity: '5' }, { id: 2, quantity: '3' }, { id: 3, quantity: '4' }];
  it('lists only the lines that came in short, with the reason', () => {
    const receipts = buildReceipts(lines, { '1': '3', '2': '3', '3': '' }, { '1': ' broken ' });
    expect(receipts).toEqual([{ line: 1, quantity: '3', reason: 'broken' }]);
  });
  it('is empty when everything arrived', () => {
    expect(buildReceipts(lines, { '1': '5' }, {})).toEqual([]);
  });
  it('treats a zero receipt as a shortage of the whole line', () => {
    expect(buildReceipts(lines, { '2': '0' }, {})).toEqual([{ line: 2, quantity: '0', reason: '' }]);
  });
});

describe('receivedProblem', () => {
  it('rejects more than was sent, negatives and junk, and allows blank', () => {
    expect(receivedProblem('5', '6')).toBe(true);
    expect(receivedProblem('5', '-1')).toBe(true);
    expect(receivedProblem('5', 'abc')).toBe(true);
    expect(receivedProblem('5', '')).toBe(false);
    expect(receivedProblem('5', '5')).toBe(false);
    expect(receivedProblem('5', '0')).toBe(false);
  });
});

describe('transit and shortage helpers', () => {
  it('counts whole days since dispatch and tolerates a missing time', () => {
    const now = new Date('2026-10-16T12:00:00Z');
    expect(transitDays('2026-10-13T11:00:00Z', now)).toBe(3);
    expect(transitDays('2026-10-16T08:00:00Z', now)).toBe(0);
    expect(transitDays(null, now)).toBeNull();
    expect(transitDays('garbage', now)).toBeNull();
  });

  it('lists only unsettled shortages on received transfers', () => {
    const lines = [
      { id: 1, shortageQty: '2.000', shortageResolution: '' },
      { id: 2, shortageQty: '1.000', shortageResolution: 'WRITE_OFF' },
      { id: 3, shortageQty: '0.000' },
    ];
    expect(openShortages('COMPLETED', lines).map((l) => l.id)).toEqual([1]);
    expect(openShortages('DISPATCHED', lines)).toEqual([]);
  });

  it('filters by status, by open shortage and by search text', () => {
    const rows = [
      { status: 'DRAFT', number: 'TR-1', notes: 'for festival', lines: [{ productName: 'Soap' }] },
      { status: 'COMPLETED', number: 'TR-2', notes: '', lines: [{ productName: 'Tea', shortageQty: '2', shortageResolution: '' }] },
      { status: 'COMPLETED', number: 'TR-3', notes: '', lines: [{ productName: 'Tea', shortageQty: '0' }] },
    ];
    expect(filterTransfers(rows, { status: 'DRAFT', q: '' })).toHaveLength(1);
    expect(filterTransfers(rows, { status: 'SHORT', q: '' }).map((r) => r.number)).toEqual(['TR-2']);
    expect(filterTransfers(rows, { status: '', q: 'festival' }).map((r) => r.number)).toEqual(['TR-1']);
    expect(filterTransfers(rows, { status: '', q: 'tea' })).toHaveLength(2);
  });
});

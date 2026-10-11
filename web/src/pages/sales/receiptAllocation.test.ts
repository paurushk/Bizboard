import { describe, expect, it } from 'vitest';
import { maxCashForBill, planOldestFirstAllocation } from './receiptAllocation';

describe('planOldestFirstAllocation', () => {
  const bills = [
    { id: 108, number: 'INV-108', balance: '8000', dueDate: '2026-10-01', invoiceDate: '2026-09-01' },
    { id: 104, number: 'INV-104', balance: '12000', dueDate: '2026-08-01', invoiceDate: '2026-07-01' },
    { id: 101, number: 'INV-101', balance: '500', dueDate: null, invoiceDate: '2026-06-01' },
  ];

  it('settles the oldest due invoice first and leaves a bill with no due date until last', () => {
    const plan = planOldestFirstAllocation(bills, 20500);
    expect(plan.map((row) => [row.number, row.amount, row.partial])).toEqual([
      ['INV-104', 12000, false],
      ['INV-108', 8000, false],
      ['INV-101', 500, false],
    ]);
  });

  it('returns nothing when the amount is empty', () => {
    expect(planOldestFirstAllocation(bills, 0)).toEqual([]);
  });

  it('counts the discount and TDS a receipt carries, as the server does', () => {
    // 100 cash + 10 discount clears a 110 bill exactly, not "100 of 110".
    const one = [{ id: 1, number: 'INV-1', balance: '110', dueDate: '2026-09-01', invoiceDate: '2026-08-01' }];
    expect(planOldestFirstAllocation(one, 100, { discount: 10 }).map((r) => [r.amount, r.partial])).toEqual([[100, false]]);
    // 900 cash + 100 TDS settles a 1000 bill.
    const bill = [{ id: 2, number: 'INV-2', balance: '1000', dueDate: '2026-09-01', invoiceDate: '2026-08-01' }];
    expect(planOldestFirstAllocation(bill, 900, { tds: 100 }).map((r) => [r.amount, r.partial])).toEqual([[900, false]]);
  });

  it('splits a discount across bills without losing a paisa', () => {
    const two = [
      { id: 3, number: 'INV-3', balance: '600', dueDate: '2026-09-01', invoiceDate: '2026-08-01' },
      { id: 4, number: 'INV-4', balance: '600', dueDate: '2026-09-02', invoiceDate: '2026-08-02' },
    ];
    // 1000 cash with a 200 discount settles 600 + 600 = 1200.
    const plan = planOldestFirstAllocation(two, 1000, { discount: 200 });
    expect(plan.map((r) => r.number)).toEqual(['INV-3', 'INV-4']);
    expect(plan.reduce((sum, r) => sum + r.amount, 0)).toBeCloseTo(1000, 2);
    expect(plan.every((r) => !r.partial)).toBe(true);
  });
});

describe('maxCashForBill', () => {
  it('leaves room on the bill for the TDS and discount the cash carries', () => {
    // 1,000 received with 100 TDS cannot all go to a bill of 1,000: 909.09 + 90.91 TDS settles it.
    expect(maxCashForBill('1000', 1000, { tds: 100 })).toBeCloseTo(909.09, 2);
    expect(maxCashForBill('1000', 900, { tds: 100 })).toBe(900);
  });

  it('is the lesser of the amount and the balance when nothing is withheld', () => {
    expect(maxCashForBill('400', 1000)).toBe(400);
    expect(maxCashForBill('1000', 250)).toBe(250);
    expect(maxCashForBill('1000', 0)).toBe(0);
  });
});

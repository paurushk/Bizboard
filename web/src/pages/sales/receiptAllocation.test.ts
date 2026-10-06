import { describe, expect, it } from 'vitest';
import { planOldestFirstAllocation } from './receiptAllocation';

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
});
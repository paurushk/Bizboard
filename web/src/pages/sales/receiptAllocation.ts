import { toNumber } from '@/utils/money';

export type OpenBill = {
  id: number;
  number?: string | null;
  balance: string | number;
  dueDate?: string | null;
  invoiceDate: string;
};

export type AllocationSlice = {
  id: number;
  number: string;
  amount: number;
  partial: boolean;
};

/** Same order as PaymentService.allocate_receipt_oldest_first: due date, invoice date, id. */
export function planOldestFirstAllocation(bills: OpenBill[], amount: number): AllocationSlice[] {
  if (!(amount > 0)) return [];
  const ordered = bills
    .filter((bill) => toNumber(bill.balance) > 0)
    .sort((a, b) => {
      // PostgreSQL ASC sorts NULL due dates last. An empty string sorts first and
      // would preview a different bill than the one the receipt actually settles.
      const ad = (a.dueDate || '').trim();
      const bd = (b.dueDate || '').trim();
      if (!ad !== !bd) return ad ? -1 : 1;
      if (ad !== bd) return ad < bd ? -1 : 1;
      if (a.invoiceDate !== b.invoiceDate) return a.invoiceDate < b.invoiceDate ? -1 : 1;
      return a.id - b.id;
    });
  let remaining = Math.round(amount * 100) / 100;
  const slices: AllocationSlice[] = [];
  for (const bill of ordered) {
    if (remaining <= 0) break;
    const owed = Math.round(toNumber(bill.balance) * 100) / 100;
    const take = Math.round(Math.min(remaining, owed) * 100) / 100;
    if (take <= 0) continue;
    slices.push({
      id: bill.id,
      number: bill.number || `#${bill.id}`,
      amount: take,
      partial: take + 0.001 < owed,
    });
    remaining = Math.round((remaining - take) * 100) / 100;
  }
  return slices;
}

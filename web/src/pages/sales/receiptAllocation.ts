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

const toPaise = (value: number) => Math.round(value * 100);

/**
 * The slice of a receipt's discount (or TDS) that an allocation of `cash` clears: proportional to
 * the cash share of the receipt, rounded half up to the paisa, never above what is still unapplied,
 * with the allocation that completes the receipt taking the remainder. All in paise, mirroring
 * payments.receipt_math.shares_for on the server.
 */
function shareOf(total: number, applied: number, cash: number, liveCash: number, base: number): number {
  const left = total - applied;
  if (total <= 0 || left <= 0 || cash <= 0 || base <= 0) return 0;
  const completes = liveCash + cash >= base;
  const share = completes ? left : Math.floor((cash * total * 2 + base) / (base * 2));
  return Math.max(0, Math.min(share, left));
}

/** Same order as PaymentService.allocate_receipt_oldest_first: due date, invoice date, id.
 *
 * A receipt carrying a settlement discount or customer TDS settles a bill with the cash plus the
 * discount and TDS that cash carries, exactly as the server does, so the preview shows the bills
 * the receipt will really clear.
 */
export function planOldestFirstAllocation(
  bills: OpenBill[],
  amount: number,
  extras: { discount?: number; tds?: number } = {},
): AllocationSlice[] {
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
  const base = toPaise(amount);
  const discount = toPaise(extras.discount ?? 0);
  const tds = toPaise(extras.tds ?? 0);
  let liveCash = 0;
  let liveDiscount = 0;
  let liveTds = 0;
  let remaining = base;
  const slices: AllocationSlice[] = [];
  for (const bill of ordered) {
    if (remaining <= 0) break;
    const owed = toPaise(toNumber(bill.balance));
    // Largest cash such that cash + its discount + its TDS fits inside what the bill still owes.
    let lo = 0;
    let hi = Math.min(remaining, owed);
    while (lo < hi) {
      const mid = Math.floor((lo + hi + 1) / 2);
      const d = shareOf(discount, liveDiscount, mid, liveCash, base);
      const t = shareOf(tds, liveTds, mid, liveCash, base);
      if (mid + d + t <= owed) lo = mid;
      else hi = mid - 1;
    }
    const take = lo;
    if (take <= 0) continue;
    const d = shareOf(discount, liveDiscount, take, liveCash, base);
    const t = shareOf(tds, liveTds, take, liveCash, base);
    slices.push({
      id: bill.id,
      number: bill.number || `#${bill.id}`,
      amount: take / 100,
      partial: take + d + t + 1 < owed,
    });
    liveCash += take;
    liveDiscount += d;
    liveTds += t;
    remaining -= take;
  }
  return slices;
}

/**
 * The most cash of a new receipt that one bill can take: the cash plus the discount and TDS it
 * carries must fit inside the bill's balance (a receipt of 1,000 with 100 TDS cannot be applied in
 * full to a bill of 1,000).
 */
export function maxCashForBill(
  balance: string | number,
  amount: number,
  extras: { discount?: number; tds?: number } = {},
): number {
  const [slice] = planOldestFirstAllocation(
    [{ id: 0, balance, invoiceDate: '' }],
    amount,
    extras,
  );
  return slice?.amount ?? 0;
}

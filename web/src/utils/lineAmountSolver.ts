import { roundMoney } from '@/utils/money';
import { calculateLineTax } from '@/utils/tax';

export type SolvedLinePrice = {
  unitPrice: number;
  lineTotal: number;
  /** Typed amount minus the amount the tax engine will actually save. */
  difference: number;
};

/**
 * Find a 2-decimal unit price whose forward line total matches the typed amount.
 * Uses calculateLineTax, including intra-state half-rounding.
 */
export function priceForLineAmount(args: {
  amount: number;
  quantity: number;
  discountPercent?: number;
  /** When set, the rupee discount stays fixed while the rate is solved. */
  discountAmount?: number;
  /** Price to keep when quantity is zero. */
  keepUnitPrice?: number;
  gstRate: number;
  cessRate?: number;
  intraState: boolean | null;
  inclusive?: boolean;
}): SolvedLinePrice {
  const qty = args.quantity;
  const target = roundMoney(args.amount);
  if (!(qty > 0)) {
    return { unitPrice: args.keepUnitPrice ?? 0, lineTotal: 0, difference: target };
  }
  const useRupeeDiscount = args.discountAmount != null;
  const discount = Math.min(100, Math.max(0, args.discountPercent ?? 0));
  const rupeeDiscount = Math.max(0, args.discountAmount ?? 0);
  const gstRate = args.intraState === null || args.inclusive ? 0 : Math.max(0, args.gstRate);
  const cessRate = args.inclusive ? 0 : Math.max(0, args.cessRate ?? 0);
  const discFactor = useRupeeDiscount ? 1 : 1 - discount / 100;
  const taxFactor = 1 + (gstRate + cessRate) / 100;
  const taxable = taxFactor > 0 ? target / taxFactor : target;
  const guessBase = useRupeeDiscount ? taxable + rupeeDiscount : taxable;
  const guess = discFactor > 0 ? guessBase / qty / discFactor : guessBase / qty;

  const forward = (unitPrice: number) =>
    calculateLineTax({
      quantity: qty,
      unitPrice,
      discountPercent: useRupeeDiscount ? undefined : discount,
      discountAmount: useRupeeDiscount ? rupeeDiscount : undefined,
      gstRate: args.inclusive ? 0 : args.gstRate,
      cessRate: args.inclusive ? 0 : args.cessRate,
      intraState: args.inclusive ? null : args.intraState,
    }).lineTotal;

  if (args.inclusive) {
    const unit = roundMoney(Math.max(0, guess));
    const lineTotal = forward(unit);
    return { unitPrice: unit, lineTotal, difference: roundMoney(target - lineTotal) };
  }

  let best = roundMoney(Math.max(0, guess));
  let bestTotal = forward(best);
  let bestDiff = Math.abs(bestTotal - target);
  for (let paise = -30; paise <= 30; paise += 1) {
    const price = roundMoney(Math.max(0, guess + paise / 100));
    const total = forward(price);
    const diff = Math.abs(total - target);
    if (diff < bestDiff - 1e-9) {
      best = price;
      bestTotal = total;
      bestDiff = diff;
    }
  }
  return { unitPrice: best, lineTotal: bestTotal, difference: roundMoney(target - bestTotal) };
}

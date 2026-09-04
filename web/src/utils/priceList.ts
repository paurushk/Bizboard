import { roundMoney, toNumber } from '@/utils/money';

export type PriceListSlab = {
  product: number;
  unitPrice?: string | number;
  unit_price?: string | number;
  minQty?: string | number;
  min_qty?: string | number;
  maxQty?: string | number | null;
  max_qty?: string | number | null;
  discountPct?: string | number;
  discount_pct?: string | number;
};

export type PriceListRow = {
  id: number;
  name?: string;
  isActive?: boolean;
  items?: PriceListSlab[];
};

export function resolveListUnitPrice(
  lists: PriceListRow[] | undefined,
  priceListId: number | null | undefined,
  productId: number,
  qty: number,
): { unitPrice: number; listName: string } | null {
  if (!priceListId) return null;
  const list = (lists ?? []).find((row) => Number(row.id) === Number(priceListId));
  if (!list) return null;
  const slabs = (list.items ?? []).filter((row) => Number(row.product) === Number(productId));
  if (!slabs.length) return null;
  const q = qty > 0 ? qty : 1;
  const ranked = [...slabs].sort(
    (a, b) => toNumber(b.minQty ?? b.min_qty ?? 1) - toNumber(a.minQty ?? a.min_qty ?? 1),
  );
  const hit = ranked.find((row) => {
    const minQ = toNumber(row.minQty ?? row.min_qty ?? 1);
    const maxRaw = row.maxQty ?? row.max_qty;
    const maxQ = maxRaw == null || maxRaw === '' ? null : toNumber(maxRaw);
    if (q < minQ) return false;
    if (maxQ != null && q > maxQ) return false;
    return true;
  });
  if (!hit) return null;
  let price = toNumber(hit.unitPrice ?? hit.unit_price);
  const disc = toNumber(hit.discountPct ?? hit.discount_pct);
  // F1-022: use the shared money rounding so a slab discount foots with every
  // other total on screen.
  if (disc) price = roundMoney((price * (100 - disc)) / 100);
  return { unitPrice: price, listName: list.name ?? '' };
}

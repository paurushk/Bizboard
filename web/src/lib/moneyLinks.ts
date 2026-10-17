import type { MoneyLink } from '@/api/resources';

/** Query flag every Money hub link carries, so the target page can offer the way back. */
export const MONEY_VIA = 'money';

/** `/route?filter=value&via=money` from a route and its filters. */
export function moneyHref(route: string, params: Record<string, string> = {}): string {
  const search = new URLSearchParams({ ...params, via: MONEY_VIA });
  return `${route}?${search.toString()}`;
}

export function moneyLinkHref(link: MoneyLink): string {
  return moneyHref(link.route, Object.fromEntries(new URLSearchParams(link.query)));
}

/** Price-embedded or weight-embedded barcode. Off unless the company turns the setting on. */

export interface WeightedBarcodeRule {
  prefix: string;
  type: 'weight' | 'price';
  itemDigits: number;
  valueDigits: number;
  decimals: number;
}

export function parseWeightedBarcode(
  raw: string,
  rule: WeightedBarcodeRule | null | undefined,
): { itemCode: string; weight?: number; price?: number } | null {
  if (!rule || !rule.prefix) return null;
  const code = raw.trim();
  if (!code.startsWith(rule.prefix)) return null;
  const rest = code.slice(rule.prefix.length);
  const item = rest.slice(0, rule.itemDigits);
  const value = rest.slice(rule.itemDigits, rule.itemDigits + rule.valueDigits);
  if (item.length !== rule.itemDigits || value.length !== rule.valueDigits) return null;
  if (!/^\d+$/.test(item) || !/^\d+$/.test(value)) return null;
  const number = Number(value) / 10 ** rule.decimals;
  if (!Number.isFinite(number)) return null;
  if (rule.type === 'weight') return { itemCode: item, weight: number };
  return { itemCode: item, price: number };
}

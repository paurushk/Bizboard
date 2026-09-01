/** Display names for GSTN / shop UQCs. Short code stays the stored value. */
export const UNIT_LABELS: Record<string, string> = {
  PCS: 'Pieces',
  NOS: 'Numbers',
  BOX: 'Box',
  CTN: 'Carton',
  CARTON: 'Carton',
  PKT: 'Packet',
  PAC: 'Pack',
  SET: 'Set',
  PAIR: 'Pair',
  PRS: 'Pairs',
  DOZ: 'Dozen',
  KG: 'Kilogram',
  KGS: 'Kilogram',
  GMS: 'Grams',
  LTR: 'Litre',
  MTR: 'Metre',
  ROLL: 'Roll',
  ROL: 'Roll',
  BAG: 'Bag',
  BTL: 'Bottle',
  CAN: 'Can',
  BUN: 'Bundle',
  BDL: 'Bundle',
};

/** Units offered on Add Item even before the company has a Units master row. */
export const STANDARD_UNITS = [
  'PCS',
  'NOS',
  'BOX',
  'CTN',
  'PKT',
  'SET',
  'PAIR',
  'DOZ',
  'KG',
  'GMS',
  'LTR',
  'MTR',
  'ROLL',
  'BAG',
];

export function formatUnitLabel(code: string, name?: string): string {
  const short = (code || '').trim();
  if (!short) return '';
  const key = short.toUpperCase();
  const full = (name || '').trim();
  if (full && full.toUpperCase() !== key) return `${full} (${short})`;
  const mapped = UNIT_LABELS[key];
  if (mapped && mapped.toUpperCase() !== key) return `${mapped} (${short})`;
  return short;
}

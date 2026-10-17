import type { Row } from '@/pages/phase/phaseShared';

/** The valuation API names fields a few ways over its history; read them all. */
export function normalizeValuationRow(r: Row): Row {
  return {
    ...r,
    productName: r.productName || r.product_name || r.name,
    warehouseName: r.warehouseName || r.warehouse_name,
    unitCost: r.unitCost ?? r.unit_cost ?? r.avgCost,
    value: r.value ?? r.stockValue,
    quantity: r.quantity ?? r.qty ?? r.onHand,
  };
}

/** A spreadsheet runs a cell that starts with = + - @ as a formula, so those get a leading quote. */
function cell(value: unknown): string {
  let text = value == null ? '' : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function buildValuationCsv(rows: Row[], isCost: boolean): string {
  const header = ['Product', 'Godown', 'Qty', isCost ? 'Unit cost' : 'Unit price', 'Value'];
  const lines = [header.join(',')];
  for (const r of rows) {
    lines.push([r.productName, r.warehouseName, r.quantity, r.unitCost, r.value].map(cell).join(','));
  }
  return lines.join('\r\n');
}

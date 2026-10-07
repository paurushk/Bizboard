/** ESC/POS receipt for a native printer. Desktop never sends these bytes. */

import { rasterCommand } from '@/pages/pos/escposRaster';

export interface EscPosReceipt {
  number?: string | null;
  customerName?: string;
  invoiceDate?: string;
  items?: Array<{ name?: string; quantity?: string | number; lineTotal?: string | number; hsn?: string; gstRate?: string | number; tax?: string | number }>;
  grandTotal?: string | number;
  paperColumns?: number;
  gstin?: string;
  paymentMode?: string;
  cashier?: string;
  terminal?: string;
  copies?: number;
  pulseDrawer?: boolean;
  /** Item names with non-ASCII text. Printed as an image before the cut. */
  rasterLines?: string[];
}

function pushText(out: number[], text: string) {
  const safe = text.replace(/₹/g, 'Rs');
  for (const ch of safe) {
    const code = ch.charCodeAt(0);
    out.push(code >= 32 && code < 127 ? code : 63);
  }
  out.push(0x0a);
}

/** Init, bill text, and a full cut. Not a placeholder and not a drawer kick. */
export function encodeEscPosReceipt(receipt: EscPosReceipt): Uint8Array {
  const out: number[] = [0x1b, 0x40, 0x1b, 0x61, 0x01];
  pushText(out, 'BizBoard');
  if (receipt.gstin) pushText(out, `GSTIN ${receipt.gstin}`);
  pushText(out, String(receipt.number || ''));
  if (receipt.invoiceDate) pushText(out, receipt.invoiceDate);
  if (receipt.customerName) pushText(out, receipt.customerName);
  if (receipt.cashier) pushText(out, receipt.cashier);
  if (receipt.terminal) pushText(out, receipt.terminal);
  out.push(0x1b, 0x61, 0x00);
  const width = receipt.paperColumns === 48 ? 48 : 32;
  pushText(out, '-'.repeat(width));
  for (const item of receipt.items ?? []) {
    const name = String(item.name || 'Item').slice(0, width - 10);
    const qty = String(item.quantity ?? '');
    const total = String(item.lineTotal ?? '');
    const hsn = item.hsn ? ` HSN ${item.hsn}` : '';
    pushText(out, `${name}${hsn}  ${qty}  ${total}`.slice(0, width));
  }
  pushText(out, '-'.repeat(width));
  const taxByRate = new Map<string, number>();
  for (const item of receipt.items ?? []) {
    const tax = Number(item.tax ?? 0);
    if (!Number.isFinite(tax) || tax === 0) continue;
    const rate = String(item.gstRate ?? '');
    taxByRate.set(rate, (taxByRate.get(rate) ?? 0) + tax);
  }
  for (const [rate, tax] of taxByRate) {
    pushText(out, `GST ${rate}%  Rs ${tax.toFixed(2)}`);
  }
  pushText(out, `TOTAL Rs ${receipt.grandTotal ?? ''}`);
  if (receipt.paymentMode) pushText(out, receipt.paymentMode);
  pushText(out, '');
  // The image has to come before the cut, or it prints on the next bill's paper.
  const image = receipt.rasterLines?.length ? rasterBytes(receipt.rasterLines) : null;
  if (image) {
    for (const byte of image) out.push(byte);
    out.push(0x0a);
  }
  if (receipt.pulseDrawer) out.push(0x1b, 0x70, 0x00, 0x19, 0xfa);
  out.push(0x1d, 0x56, 0x00);
  const once = Uint8Array.from(out);
  const copies = Math.max(1, Math.min(receipt.copies || 1, 3));
  if (copies === 1) return once;
  const all = new Uint8Array(once.length * copies);
  for (let i = 0; i < copies; i += 1) all.set(once, i * once.length);
  return all;
}

/** Non-ASCII lines (Hindi names) drawn to a 1-bit image. Null when there is no canvas. */
export function rasterBytes(lines: string[]): Uint8Array | null {
  if (!lines.length || typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  const width = 384;
  const height = Math.max(24, lines.length * 28);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = '#000000';
  ctx.font = '22px sans-serif';
  lines.forEach((line, index) => ctx.fillText(line, 4, 22 + index * 28));
  const pixels = ctx.getImageData(0, 0, width, height).data;
  return rasterCommand(width, height, pixels);
}

/** Scanner wedge timing and quantity prefixes (BUG-UI-002, BUG-UI-003). */

const SCANNER_GAP_MS = 50;

export function isScannerBurst(gapsMs: number[]): boolean {
  if (gapsMs.length === 0) return false;
  return gapsMs.every((gap) => gap >= 0 && gap < SCANNER_GAP_MS);
}

export function parseQtyBarcode(raw: string): { quantity: number; code: string } | null {
  const match = /^(\d+)\*(.+)$/.exec(raw.trim());
  if (!match) return null;
  const quantity = Number(match[1]);
  if (!Number.isFinite(quantity) || quantity <= 0) return null;
  return { quantity, code: match[2] };
}

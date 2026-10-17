import type { Product } from '@/types/domain';
import { toNumber } from '@/utils/money';

export type TransferStatus = 'DRAFT' | 'DISPATCHED' | 'COMPLETED' | 'CANCELLED';
export type TransferAction = 'dispatch' | 'receive' | 'cancel';

/** Roles that may undo a transfer that has already landed (mirrors StockTransferViewSet.cancel). */
const CAN_CANCEL_RECEIVED = new Set(['OWNER', 'MANAGER']);

/**
 * What the row buttons are. A draft can be sent or dropped; goods in transit can be received or
 * pulled back; a received transfer can only be undone by an owner or manager.
 */
export function transferActions(status: string, role?: string | null): TransferAction[] {
  switch (status) {
    case 'DRAFT':
      return ['dispatch', 'cancel'];
    case 'DISPATCHED':
      return ['receive', 'cancel'];
    case 'COMPLETED':
      return role && CAN_CANCEL_RECEIVED.has(role) ? ['cancel'] : [];
    default:
      return [];
  }
}

export interface TransferLineLike {
  quantity: string | number;
  shortageQty?: string | number | null;
}

/** "3 items · 120 units" for the list. */
export function summarizeLines(lines: TransferLineLike[] | undefined): { count: number; qty: number } {
  const list = lines ?? [];
  return { count: list.length, qty: list.reduce((sum, line) => sum + toNumber(line.quantity), 0) };
}

export interface LineDraft {
  key: string;
  product: Product | null;
  /** Product id waiting to be looked up (a link from planning carries ids only). */
  productId?: number;
  batch: string;
  qty: string;
  serials: string;
}

export function splitSerials(text: string): string[] {
  return text
    .split(/[,\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export type LineProblem =
  | { code: 'product' }
  | { code: 'qty' }
  | { code: 'batch' }
  | { code: 'serials'; qty: number; count: number };

/** The first thing wrong with a line, or null. Mirrors the server's draft-time checks. */
export function lineProblem(line: LineDraft): LineProblem | null {
  if (!line.product) return { code: 'product' };
  const qty = Number(line.qty);
  if (!line.qty.trim() || !Number.isFinite(qty) || qty <= 0) return { code: 'qty' };
  if (line.product.trackBatch && !line.batch) return { code: 'batch' };
  if (line.product.trackSerial) {
    const count = splitSerials(line.serials).length;
    if (count !== qty) return { code: 'serials', qty, count };
  }
  return null;
}

export interface ReceiptRow {
  line: number;
  quantity: string;
  reason: string;
}

/**
 * The `receipts` for a receive call: only lines that came in short. An empty list means "all
 * arrived as sent", which the server treats the same as no receipts at all.
 */
export function buildReceipts(
  lines: Array<{ id?: number; quantity: string | number }>,
  received: Record<string, string>,
  reasons: Record<string, string>,
): ReceiptRow[] {
  const out: ReceiptRow[] = [];
  for (const line of lines) {
    if (line.id == null) continue;
    const typed = received[String(line.id)];
    if (typed === undefined || typed.trim() === '') continue;
    if (toNumber(typed) === toNumber(line.quantity)) continue;
    out.push({ line: line.id, quantity: typed.trim(), reason: (reasons[String(line.id)] ?? '').trim() });
  }
  return out;
}

/** A received quantity the server will refuse: negative, not a number, or more than was sent. */
export function receivedProblem(sent: string | number, typed: string | undefined): boolean {
  if (typed === undefined || typed.trim() === '') return false;
  const value = Number(typed);
  return !Number.isFinite(value) || value < 0 || value > toNumber(sent);
}

/** Days a transfer has been on the road; null when the dispatch time is not known. */
export function transitDays(dispatchedAt: string | null | undefined, now: Date = new Date()): number | null {
  if (!dispatchedAt) return null;
  const sent = new Date(dispatchedAt).getTime();
  if (!Number.isFinite(sent)) return null;
  return Math.max(0, Math.floor((now.getTime() - sent) / 86_400_000));
}

/** A transfer in transit this long is worth a phone call. */
export const TRANSIT_STALE_DAYS = 3;

export interface ShortageLine {
  id?: number;
  productName?: string;
  shortageQty?: string | number | null;
  shortageReason?: string;
  shortageResolution?: string;
}

/** Lines of a received transfer whose missing quantity has not been settled yet. */
export function openShortages<L extends ShortageLine>(status: string, lines: L[] | undefined): L[] {
  if (status !== 'COMPLETED') return [];
  return (lines ?? []).filter((l) => toNumber(l.shortageQty) > 0 && !l.shortageResolution);
}

export interface TransferFilter {
  status: string;
  q: string;
}

/** Narrow the loaded list by status and a search over number, notes and item names. */
export function filterTransfers<
  R extends { status?: unknown; number?: unknown; notes?: unknown; lines?: unknown },
>(rows: R[], filter: TransferFilter): R[] {
  const needle = filter.q.trim().toLowerCase();
  return rows.filter((row) => {
    if (filter.status === 'SHORT') {
      const lines = Array.isArray(row.lines) ? (row.lines as ShortageLine[]) : [];
      if (openShortages(String(row.status), lines).length === 0) return false;
    } else if (filter.status && String(row.status) !== filter.status) {
      return false;
    }
    if (!needle) return true;
    const lines = Array.isArray(row.lines) ? (row.lines as ShortageLine[]) : [];
    const haystack = [row.number, row.notes, ...lines.map((l) => l.productName)]
      .map((x) => String(x ?? '').toLowerCase())
      .join(' ');
    return haystack.includes(needle);
  });
}

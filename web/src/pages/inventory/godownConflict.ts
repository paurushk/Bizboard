export type QtyConflict = {
  lineId: number;
  productName: string;
  serverQty: string;
  localQty: string;
  snapshotQty: string;
};

export type ConflictChoice = 'KEEP_SERVER' | 'KEEP_LOCAL' | 'CANCEL';

type HttpLike = { response?: { status?: number; data?: unknown } };

/** C-01: parse 409 STOCK_COUNT_CONFLICT from the API envelope. */
export function parseStockCountConflicts(err: unknown): QtyConflict[] | null {
  if (!err || typeof err !== 'object' || !('response' in err)) return null;
  const http = err as HttpLike;
  if (http.response?.status !== 409) return null;
  const data = http.response.data as Record<string, unknown> | undefined;
  const nested = data?.error as { code?: string; details?: Record<string, unknown> } | undefined;
  const code = nested?.code ?? data?.code;
  if (String(code) !== 'STOCK_COUNT_CONFLICT') return null;
  const details = (nested?.details ?? data ?? {}) as Record<string, unknown>;
  const raw = (details.conflicts ?? details.Conflicts ?? []) as Record<string, unknown>[];
  if (!Array.isArray(raw) || raw.length === 0) return null;
  return raw.map((row) => ({
    lineId: Number(row.lineId ?? row.line_id ?? 0),
    productName: String(row.productName ?? row.product_name ?? ''),
    serverQty: String(row.serverQty ?? row.server_qty ?? ''),
    localQty: String(row.localQty ?? row.local_qty ?? ''),
    snapshotQty: String(row.snapshotQty ?? row.snapshot_qty ?? ''),
  }));
}

export function applyConflictChoice(
  _conflicts: QtyConflict[],
  choice: Exclude<ConflictChoice, 'CANCEL'>,
): { resolve: 'KEEP_SERVER' | 'KEEP_LOCAL' } {
  return { resolve: choice };
}

export type QtyConflict = {
  lineId: number;
  productName: string;
  serverQty: string;
  localQty: string;
  snapshotQty: string;
  /** When this line's counted figure was last changed (server time), if known. */
  countedAt?: string | null;
};

/** What to do with a line whose stock moved after the count sheet was made (INV-IDR-04). */
export type LineResolution = 'ADJUST_FOR_MOVEMENTS' | 'KEEP_SERVER' | 'KEEP_LOCAL';

export type ConflictChoice = LineResolution | 'CANCEL';

type HttpLike = { response?: { status?: number; data?: unknown } };

function errorBody(err: unknown): { code: string; details: Record<string, unknown> } | null {
  if (!err || typeof err !== 'object' || !('response' in err)) return null;
  const http = err as HttpLike;
  if (http.response?.status !== 409) return null;
  const data = http.response.data as Record<string, unknown> | undefined;
  const nested = data?.error as { code?: string; details?: Record<string, unknown> } | undefined;
  return {
    code: String(nested?.code ?? data?.code ?? ''),
    details: (nested?.details ?? data ?? {}) as Record<string, unknown>,
  };
}

/** C-01: parse 409 STOCK_COUNT_CONFLICT from the API envelope. */
export function parseStockCountConflicts(err: unknown): QtyConflict[] | null {
  const body = errorBody(err);
  if (!body || body.code !== 'STOCK_COUNT_CONFLICT') return null;
  const raw = (body.details.conflicts ?? body.details.Conflicts ?? []) as Record<string, unknown>[];
  if (!Array.isArray(raw) || raw.length === 0) return null;
  return raw.map((row) => ({
    lineId: Number(row.lineId ?? row.line_id ?? 0),
    productName: String(row.productName ?? row.product_name ?? ''),
    serverQty: String(row.serverQty ?? row.server_qty ?? ''),
    localQty: String(row.localQty ?? row.local_qty ?? ''),
    snapshotQty: String(row.snapshotQty ?? row.snapshot_qty ?? ''),
    countedAt: (row.countedAt ?? row.counted_at ?? null) as string | null,
  }));
}

export type LineChanged = { lineId: number; productName: string; countedQty: string | null; version: number };

/** INV-IDR-04: 409 STOCK_COUNT_LINE_CHANGED — another counter saved these lines after they were loaded. */
export function parseStockCountLinesChanged(err: unknown): LineChanged[] | null {
  const body = errorBody(err);
  if (!body || body.code !== 'STOCK_COUNT_LINE_CHANGED') return null;
  const raw = (body.details.lines ?? []) as Record<string, unknown>[];
  if (!Array.isArray(raw) || raw.length === 0) return null;
  return raw.map((row) => ({
    lineId: Number(row.lineId ?? row.line_id ?? 0),
    productName: String(row.productName ?? row.product_name ?? ''),
    countedQty: row.countedQty == null && row.counted_qty == null ? null : String(row.countedQty ?? row.counted_qty),
    version: Number(row.version ?? 0),
  }));
}

/** One answer for every drifted line, as older queued requests send it. */
export function applyConflictChoice(
  _conflicts: QtyConflict[],
  choice: Exclude<ConflictChoice, 'CANCEL'>,
): { resolve: LineResolution } {
  return { resolve: choice };
}

/** The same answer for each conflicted line, keyed by line id (the shape the post call takes). */
export function resolutionsFor(conflicts: QtyConflict[], choice: LineResolution): Record<number, LineResolution> {
  return Object.fromEntries(conflicts.map((row) => [row.lineId, choice]));
}

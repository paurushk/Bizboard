import type { Product } from '@/types/domain';

type Line<T extends { product: Product }> = T;

/**
 * Drop held bills whose checkout was already queued in the offline outbox.
 * A queued idempotency key is a committed sale waiting to sync, not a working cart.
 */
export function omitQueuedHeldSessions<T extends { idempotencyKey: string | null }>(
  sessions: Record<string, T>,
  sessionIds: string[],
  activeSessionId: string,
  queuedKeys: ReadonlySet<string>,
): {
  sessions: Record<string, T>;
  sessionIds: string[];
  activeSessionId: string;
  droppedCount: number;
  droppedKeys: string[];
} {
  const next: Record<string, T> = {};
  const keptIds: string[] = [];
  const droppedKeys: string[] = [];
  const ordered = sessionIds.length > 0 ? sessionIds : Object.keys(sessions);
  for (const id of ordered) {
    const snap = sessions[id];
    if (!snap) continue;
    if (snap.idempotencyKey && queuedKeys.has(snap.idempotencyKey)) {
      droppedKeys.push(snap.idempotencyKey);
      continue;
    }
    next[id] = snap;
    keptIds.push(id);
  }
  const active = next[activeSessionId] ? activeSessionId : (keptIds[0] ?? '');
  return {
    sessions: next,
    sessionIds: keptIds,
    activeSessionId: active,
    droppedCount: droppedKeys.length,
    droppedKeys,
  };
}

/** Replace stored products with the current record. Drop ones the server no longer has. */
export function repriceLines<T extends { product: Product }>(
  lines: Line<T>[],
  freshById: Map<number, Product>,
): { lines: T[]; changed: boolean } {
  let changed = false;
  const next: T[] = [];
  for (const line of lines) {
    const fresh = freshById.get(line.product.id);
    if (!fresh || fresh.status === 'INACTIVE') {
      changed = true;
      continue;
    }
    if (String(fresh.sellingPrice ?? '') !== String(line.product.sellingPrice ?? '')) changed = true;
    next.push({ ...line, product: fresh });
  }
  return { lines: next, changed };
}

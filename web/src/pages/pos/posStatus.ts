export type PosChipState = 'unsaved' | 'offline' | 'saved' | 'completed' | null;

/** A-04: chip matches local cart vs queued outbox vs posted sale. */
export function posChipState(opts: {
  cartCount: number;
  hasOutbox: boolean;
  offline: boolean;
  justCompleted: boolean;
}): PosChipState {
  if (opts.justCompleted && opts.cartCount === 0) return 'completed';
  if (opts.hasOutbox) return opts.offline ? 'offline' : 'saved';
  if (opts.cartCount > 0) return opts.offline ? 'offline' : 'unsaved';
  return null;
}

export type RecoverUnpaid = { id: number; number: string };

export function unpaidRecoverFromAbort(pending: {
  invoiceId?: number;
  invoiceNumber?: string | null;
} | null): RecoverUnpaid | null {
  if (!pending?.invoiceId) return null;
  return { id: pending.invoiceId, number: pending.invoiceNumber || `#${pending.invoiceId}` };
}

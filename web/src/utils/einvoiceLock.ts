/** Mirrors backend `sales.irn_guard` live-IRN predicate (CFT-116). */
const IN_FLIGHT = new Set(['QUEUED', 'PENDING', 'IN_PROGRESS']);
const LIVE = new Set(['GENERATED', 'MANUAL_IRN']);
const NON_LIVE = new Set(['CANCELLED', 'FAILED', 'NONE', '']);

export function hasLiveIrn(doc: {
  einvoiceStatus?: string | null;
  irn?: string | null;
}): boolean {
  const status = String(doc.einvoiceStatus ?? '')
    .trim()
    .toUpperCase();
  const irn = String(doc.irn ?? '').trim();
  if (IN_FLIGHT.has(status)) return true;
  if (LIVE.has(status)) return true;
  return Boolean(irn) && !NON_LIVE.has(status);
}

/** CFT-116: line Edit is allowed only when there is no live IRN. */
export function canEditInvoiceLines(inv: {
  status?: string | null;
  einvoiceStatus?: string | null;
  irn?: string | null;
}): boolean {
  const status = String(inv.status ?? '').toUpperCase();
  if (status === 'DRAFT') return true;
  if (status === 'COMPLETED') return !hasLiveIrn(inv);
  return false;
}

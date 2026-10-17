/**
 * First-expiry-first-out: the lot to take stock from by default. Earliest expiry first, lots with
 * no expiry last, then the oldest lot (lowest id). The user can still pick another lot.
 */
export function fefoLot<T extends { id: number; expiryDate?: string | null }>(lots: T[]): T | null {
  if (lots.length === 0) return null;
  return [...lots].sort((a, b) => {
    const ax = a.expiryDate || '9999-12-31';
    const bx = b.expiryDate || '9999-12-31';
    if (ax !== bx) return ax < bx ? -1 : 1;
    return a.id - b.id;
  })[0];
}

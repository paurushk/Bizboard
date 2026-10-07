const ID_KEY = 'bb_pos_terminal_id';
const LABEL_KEY = 'bb_pos_terminal_label';

export function posTerminalId(): string {
  try {
    const existing = localStorage.getItem(ID_KEY);
    if (existing) return existing;
    const created = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `device-${Date.now()}`;
    localStorage.setItem(ID_KEY, created);
    return created;
  } catch {
    return 'device-local';
  }
}

export function posTerminalLabel(): string {
  try {
    return localStorage.getItem(LABEL_KEY) || 'Counter';
  } catch {
    return 'Counter';
  }
}

export function cashNeedsOpenShift(requireShift: boolean, shiftStatus?: string | null): boolean {
  return requireShift && shiftStatus !== 'OPEN';
}

const OUTAGE_KEY = 'bb_pos_outage_id';

export function posOutageId(): string {
  try {
    const existing = localStorage.getItem(OUTAGE_KEY);
    if (existing) return existing;
    const created = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `outage-${Date.now()}`;
    localStorage.setItem(OUTAGE_KEY, created);
    return created;
  } catch {
    return 'outage-local';
  }
}

export function clearPosOutage(): void {
  try {
    localStorage.removeItem(OUTAGE_KEY);
  } catch {
    /* private mode */
  }
}

/** Shared dirty rule for the money editors that were missing UnsavedChangesGuard. */

export function partyOrLinesDirty(partyId: number | '' | null | undefined, lineCount: number): boolean {
  return Boolean(partyId) || lineCount > 0;
}

export function dialogAmountDirty(open: boolean, hasParty: boolean, amount: string): boolean {
  return open && (hasParty || Number(amount) > 0);
}

export function returnDialogDirty(open: boolean, hasDocument: boolean, reason: string): boolean {
  return open && (hasDocument || reason.trim().length > 0);
}

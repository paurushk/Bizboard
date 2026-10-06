/**
 * Nav ids whose route cannot load at all (UX phase plan, case b).
 * A screen that loads and then errors stays in the menu and uses ModuleNotReady.
 * Every id here needs a line in docs/ux/not_ready.md.
 * GSTR-6, 7 and 8 are hidden by founder decision (GATED_MODULES plan GM-20): the pages
 * only say the return is not prepared, so the menu should not offer them.
 */
const DEFAULT_NOT_READY = ['report-gstr6', 'report-gstr7', 'report-gstr8'];
const notReadyNavIds = new Set<string>(DEFAULT_NOT_READY);

export function isNavMarkedNotReady(id: string): boolean {
  return notReadyNavIds.has(id);
}

export function markNavNotReady(id: string): void {
  notReadyNavIds.add(id);
}

/** Back to the recorded defaults (used by tests). */
export function clearNavNotReady(): void {
  notReadyNavIds.clear();
  for (const id of DEFAULT_NOT_READY) notReadyNavIds.add(id);
}

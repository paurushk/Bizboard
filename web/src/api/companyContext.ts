/**
 * WP-ID2: one active company per browser, kept safe across tabs and background sync.
 *
 * The active company id lives in localStorage, which every tab of this site shares. When a user
 * switches company in one tab, the other tabs would keep showing the old company's screens while
 * their next request goes out under the new company's X-Company-Id. So:
 *
 * - another tab reloads as soon as the stored id changes (`installCompanySwitchListener`);
 * - offline outboxes check `companyChangedFrom(draft.companyId)` before every send and leave the
 *   draft queued if the company changed, so a draft is never posted into another company.
 */
import { ACTIVE_COMPANY_STORAGE_KEY } from '@/api/client';

export function readActiveCompanyId(): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY);
    return raw && /^\d+$/.test(raw) ? raw : null;
  } catch {
    return null;
  }
}

/**
 * True when this browser has since switched to a different company than `companyId`.
 * Nothing stored yet (a single-company user, a fresh device) is not a switch.
 */
export function companyChangedFrom(companyId: number | string | null | undefined): boolean {
  const active = readActiveCompanyId();
  return companyId != null && active != null && active !== String(companyId);
}

let installed = false;

/**
 * Reload this tab when another tab switches company (the `storage` event only fires in other tabs).
 * Compared with the company this tab is showing, not just the previous stored value: a conflict
 * in another tab clears the key and then sets the new id, and both steps must still reload here.
 */
export function installCompanySwitchListener(reload: () => void = () => window.location.reload()): () => void {
  if (typeof window === 'undefined' || installed) return () => {};
  installed = true;
  let showing = readActiveCompanyId();
  const onStorage = (event: StorageEvent) => {
    if (event.key !== ACTIVE_COMPANY_STORAGE_KEY && event.key !== null) return;
    // key === null is localStorage.clear() in another tab.
    const raw = event.key === null ? null : event.newValue;
    const next = raw && /^\d+$/.test(raw) ? raw : null;
    if (showing === null) {
      // First selection on a fresh device (null -> id) is not a switch: adopt it.
      showing = next;
      return;
    }
    if (next !== showing) reload();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener('storage', onStorage);
    installed = false;
  };
}

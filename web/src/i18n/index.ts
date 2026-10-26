import { useEffect, useState } from 'react';
import { en, type MessageTree } from './en';

// WP-8 (bundle budget): English is built in; Hindi (~135 KB gzip) is its own chunk, fetched before
// the first render for a Hindi user (ensureLocaleLoaded in main.tsx) or when someone switches to it.
const catalogs: Record<string, MessageTree> = { en };
const loaders: Record<string, () => Promise<MessageTree>> = {
  hi: () => import('./hi').then((m) => m.hi as unknown as MessageTree),
};
const SUPPORTED = new Set(['en', ...Object.keys(loaders)]);

const LOCALE_STORAGE_KEY = 'bizboard:locale';

type LocaleListener = () => void;
const listeners = new Set<LocaleListener>();

function loadStoredLocale(): string {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored === 'ta' || stored === 'gu') return 'en';
    if (stored && SUPPORTED.has(stored)) return stored;
  }
  return 'en';
}

let locale = loadStoredLocale();

function getByPath(obj: unknown, path: string): string | undefined {
  const parts = path.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (current == null || typeof current !== 'object') return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === 'string' ? current : undefined;
}

/** Resolve an i18n key (dot path). English is the default catalog. */
export function t(key: string, vars?: Record<string, string | number>): string {
  const catalog = catalogs[locale] ?? en;
  const resolved = getByPath(catalog, key) ?? getByPath(en, key);
  let value = resolved ?? key;
  // F1-023: a key missing from BOTH the active catalog and the English
  // fallback previously rendered silently as the raw dot-path (e.g.
  // "status.PARTIALLY_PAID") with no signal anywhere that it was untranslated.
  if (resolved === undefined && import.meta.env.DEV) {
    console.warn(`[i18n] missing key: "${key}"`);
  }
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replaceAll(`{${k}}`, () => String(v));
    }
  }
  return value;
}

/** Like t(), but null (and no warning) when the key is not in the catalogue: for text that may come from the server instead. */
export function tOptional(key: string, vars?: Record<string, string | number>): string | null {
  const catalog = catalogs[locale] ?? en;
  const resolved = getByPath(catalog, key) ?? getByPath(en, key);
  if (resolved === undefined) return null;
  let value = resolved;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replaceAll(`{${k}}`, () => String(v));
    }
  }
  return value;
}

/** Make a catalogue available without fetching it (the test setup registers Hindi this way). */
export function registerLocale(name: string, tree: MessageTree) {
  catalogs[name] = tree;
}

async function loadLocale(name: string): Promise<void> {
  if (catalogs[name] || !loaders[name]) return;
  catalogs[name] = await loaders[name]();
}

/** Fetch the saved locale's catalogue before the first render. Offline or failed: English shows. */
export async function ensureLocaleLoaded(): Promise<void> {
  try {
    await loadLocale(locale);
  } catch {
    // English fallback (t() resolves every key against en).
  }
}

export function setLocale(next: string) {
  const resolved = SUPPORTED.has(next) ? next : 'en';
  if (resolved === locale && catalogs[resolved]) return;
  const apply = () => {
    locale = resolved;
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem(LOCALE_STORAGE_KEY, locale);
      } catch {
        // Storage quota or restricted environment
      }
    }
    listeners.forEach((fn) => fn());
  };
  if (catalogs[resolved]) {
    apply();
    return;
  }
  loadLocale(resolved).then(apply, () => {
    // Could not fetch the catalogue (offline): stay on the current locale.
  });
}

export function getLocale() {
  return locale;
}

/** FE-18: subscribe so UI can re-render without a full page reload. */
export function subscribeLocale(listener: LocaleListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Re-render the calling component when the locale changes (E2E3-034). */
export function useLocale(): string {
  const [, setTick] = useState(0);
  useEffect(() => subscribeLocale(() => setTick((n) => n + 1)), []);
  return locale;
}

export { en };
// R-084: ta/gu catalogs removed — switcher is en/hi only.
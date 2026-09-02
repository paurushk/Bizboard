import { useEffect, useState } from 'react';
import { en, type MessageTree } from './en';
import { hi } from './hi';

const catalogs: Record<string, MessageTree> = {
  en,
  hi: hi as unknown as MessageTree,
};

const LOCALE_STORAGE_KEY = 'bizboard:locale';

type LocaleListener = () => void;
const listeners = new Set<LocaleListener>();

function loadStoredLocale(): string {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored === 'ta' || stored === 'gu') return 'en';
    if (stored && catalogs[stored]) return stored;
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
  let value = getByPath(catalog, key) ?? getByPath(en, key) ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replaceAll(`{${k}}`, () => String(v));
    }
  }
  return value;
}

export function setLocale(next: string) {
  const resolved = catalogs[next] ? next : 'en';
  if (resolved === locale) return;
  locale = resolved;
  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    } catch {
      // Storage quota or restricted environment
    }
  }
  listeners.forEach((fn) => fn());
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
export { hi };
// ta / gu catalogs exist but are not GA — `loadStoredLocale` falls them back to
// 'en'. Re-export them from here only once they are wired into `catalogs`.

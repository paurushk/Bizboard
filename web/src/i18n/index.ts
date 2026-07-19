import { en, type MessageTree } from './en';

const catalogs: Record<string, MessageTree> = { en };

let locale = 'en';

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
      value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
    }
  }
  return value;
}

export function setLocale(next: string) {
  locale = catalogs[next] ? next : 'en';
}

export function getLocale() {
  return locale;
}

export { en };

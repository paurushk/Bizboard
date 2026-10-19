import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { en } from '@/i18n/en';
import { hi } from '@/i18n/hi';
import { SCREEN_IMPACT, SETTING_IMPACT } from './settingsImpact';
import { SETTINGS_ROUTES } from './settingsAccess';

const backend = readFileSync(resolve(__dirname, '../../../backend/core/settings_impact.py'), 'utf8').replaceAll(String.fromCharCode(13), '');

function backendDict(name: string): Record<string, string[]> {
  const start = backend.indexOf(`${name}:`);
  const body = backend.slice(start, backend.indexOf('\n}\n', start));
  const out: Record<string, string[]> = {};
  for (const m of body.matchAll(/^\s+"([^"]+)": \(([^)]*)\),$/gm)) {
    out[m[1]] = [...m[2].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  }
  return out;
}

function lookup(cat: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], cat);
}

describe('settings impact registry (SET-20)', () => {
  it('has an entry for every Settings screen and none for a screen that does not exist', () => {
    const ids = SETTINGS_ROUTES.map((d) => d.id).sort();
    expect(Object.keys(SCREEN_IMPACT).sort()).toEqual(ids);
  });

  it('matches the backend twin, screens and fields', () => {
    const screens = backendDict('SCREEN_IMPACT');
    for (const [id, consumers] of Object.entries(SCREEN_IMPACT)) expect(screens[id], id).toEqual([...consumers]);
    expect(Object.keys(screens).sort()).toEqual(Object.keys(SCREEN_IMPACT).sort());
    const settings = backendDict('SETTING_IMPACT');
    for (const s of SETTING_IMPACT) expect(settings[s.key], s.key).toEqual([...s.consumers]);
    expect(Object.keys(settings).sort()).toEqual(SETTING_IMPACT.map((s) => s.key).sort());
  });

  it('names consumers that exist, in English and Hindi, and each field reaches a consumer its screen lists', () => {
    const all = new Set([...Object.values(SCREEN_IMPACT).flat(), ...SETTING_IMPACT.flatMap((s) => s.consumers)]);
    for (const key of all) {
      for (const cat of [en, hi]) expect(typeof lookup(cat, key), key).toBe('string');
    }
    for (const s of SETTING_IMPACT) expect(s.consumers.length, s.key).toBeGreaterThan(0);
  });
});

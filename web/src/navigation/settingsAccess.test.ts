import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@/types/domain';
import { filterNav, navigation } from './menu';
import { SETUP_ORDER, nextSettingsStep, SETTINGS_GROUPS, SETTINGS_ROUTES, settingsRouteAllows, settingsRouteDef } from './settingsAccess';

type Globals = { __ff?: Record<string, boolean>; __helpV2?: boolean };
const g = globalThis as Globals;

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  const flags = () => (globalThis as Globals).__ff;
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) => Boolean(flags()?.[key]),
    isMoneyHubEnabled: () => flags()?.ENABLE_MONEY_HUB !== false,
    getCachedFeatureFlags: () => {
      const current = flags();
      return current && Object.keys(current).length > 0 ? current : null;
    },
  };
});

vi.mock('@/config/features', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/features')>();
  return { ...actual, isHelpV2Enabled: () => Boolean((globalThis as Globals).__helpV2) };
});

const company = { accountingEnabled: false } as unknown as User['company'];

function user(partial: Partial<User> & { role: User['role'] }): User {
  return {
    id: 1,
    email: 'u@x.test',
    fullName: 'U',
    canManageInventory: false,
    canImport: false,
    companyId: 1,
    company,
    ...partial,
  } as User;
}

const PERSONAS: Record<string, User> = {
  owner: user({ role: 'OWNER' }),
  ownerAccountingOn: user({ role: 'OWNER', company: { accountingEnabled: true } as unknown as User['company'] }),
  manager: user({ role: 'MANAGER', canImport: true, canExport: true }),
  accountant: user({ role: 'ACCOUNTANT', canExport: true, canViewFinancialReports: true }),
  salesStaff: user({ role: 'SALES_STAFF', canCreateSales: true }),
  importOnly: user({ role: 'SALES_STAFF', canImport: true }),
  exportOnly: user({ role: 'VIEWER', canExport: true }),
  viewer: user({ role: 'VIEWER' }),
  platformStaff: user({ role: 'VIEWER', isStaff: true }),
};

const FLAG_SETS: Array<Record<string, boolean>> = [
  {},
  { ENABLE_ARCHETYPE_PACKS: true },
  { ENABLE_TELEGRAM: true },
  { ENABLE_AI: true, ENABLE_TALLY: true, ENABLE_ACCOUNTING: true },
  {
    ENABLE_ARCHETYPE_PACKS: true,
    ENABLE_TELEGRAM: true,
    ENABLE_AI: true,
    ENABLE_TALLY: true,
    ENABLE_ACCOUNTING: true,
  },
];

function menuPaths(u: User): Set<string> {
  const settings = filterNav(u).find((item) => item.id === 'settings');
  return new Set((settings?.children ?? []).map((child) => child.path as string));
}

afterEach(() => {
  g.__ff = undefined;
  g.__helpV2 = undefined;
});

describe('settings access list (SET-01)', () => {
  it('has unique ids and paths under /settings', () => {
    const ids = SETTINGS_ROUTES.map((d) => d.id);
    const paths = SETTINGS_ROUTES.map((d) => d.path);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
    for (const path of paths) expect(path.startsWith('/settings/')).toBe(true);
  });

  it('feeds the sidebar: same ids, paths and order', () => {
    const settings = navigation.find((item) => item.id === 'settings');
    const children = (settings?.children ?? []).filter((c) => c.id !== 'settings-hub');
    expect(children.map((c) => [c.id, c.path])).toEqual(SETTINGS_ROUTES.map((d) => [d.id, d.path]));
    expect(settings?.children?.[0]).toMatchObject({ id: 'settings-hub', path: '/settings', exact: true });
  });

  it('requires a written reason for every route that is not the same as its menu rule', () => {
    for (const def of SETTINGS_ROUTES) {
      if (def.route) expect(def.routeLooserBecause, def.id).toBeTruthy();
      else expect(def.routeLooserBecause, def.id).toBeUndefined();
    }
  });

  it('lists the documented exceptions and nothing else', () => {
    expect(SETTINGS_ROUTES.filter((d) => d.route).map((d) => d.id).sort()).toEqual(
      ['accounting-settings', 'ai-settings', 'help-health', 'tally'].sort(),
    );
  });

  it('throws on an unknown id instead of leaving a route unguarded', () => {
    expect(() => settingsRouteDef('nope')).toThrow();
  });
});

describe('settings groups (SET-15)', () => {
  it('puts every screen in a known group and keeps each group together, in group order', () => {
    const order = SETTINGS_GROUPS.map((g) => g.id);
    const seq = SETTINGS_ROUTES.map((d) => order.indexOf(d.group));
    expect(seq.every((i) => i >= 0)).toBe(true);
    expect([...seq].sort((a, b) => a - b)).toEqual(seq);
  });

  it('gives each sidebar screen its group heading key', () => {
    const settings = navigation.find((item) => item.id === 'settings');
    for (const def of SETTINGS_ROUTES) {
      const child = settings?.children?.find((c) => c.id === def.id);
      expect(child?.group, def.id).toBe(SETTINGS_GROUPS.find((g) => g.id === def.group)?.labelKey);
    }
  });
});

describe('set-up order (SET-19)', () => {
  it('lists only real screens, once each', () => {
    const ids = new Set(SETTINGS_ROUTES.map((d) => d.id));
    expect(new Set(SETUP_ORDER).size).toBe(SETUP_ORDER.length);
    for (const id of SETUP_ORDER) expect(ids.has(id), id).toBe(true);
  });

  it('moves an owner from Company to GST, and skips screens they cannot open', () => {
    g.__ff = {};
    expect(nextSettingsStep('/settings/company', PERSONAS.owner)?.id).toBe('gst');
    expect(nextSettingsStep('/settings/users', PERSONAS.owner)).toBeNull();
    expect(nextSettingsStep('/settings/backup', PERSONAS.owner)).toBeNull();
    expect(nextSettingsStep('/settings', PERSONAS.owner)).toBeNull();
    // A manager who may manage GST but not owner-only screens goes on to licences, then stops.
    const gstManager = user({ role: 'MANAGER', canManageGst: true } as Partial<User> & { role: User['role'] });
    const step = nextSettingsStep('/settings/gst', gstManager);
    expect(step === null || settingsRouteAllows(step.id, gstManager)).toBe(true);
  });
});

describe('sidebar and router agree (SET-01)', () => {
  it('never shows a link the router would refuse, for every persona and flag set', () => {
    for (const flags of FLAG_SETS) {
      for (const helpV2 of [false, true]) {
        g.__ff = flags;
        g.__helpV2 = helpV2;
        for (const [name, u] of Object.entries(PERSONAS)) {
          const shown = menuPaths(u);
          for (const def of SETTINGS_ROUTES) {
            if (shown.has(def.path)) {
              expect(
                settingsRouteAllows(def.id, u),
                `${def.id} is in the sidebar for ${name} with ${JSON.stringify(flags)} but the route refuses`,
              ).toBe(true);
            }
          }
        }
      }
    }
  });

  it('only lets the route be wider than the sidebar where an exception is written down', () => {
    for (const flags of FLAG_SETS) {
      for (const helpV2 of [false, true]) {
        g.__ff = flags;
        g.__helpV2 = helpV2;
        for (const [name, u] of Object.entries(PERSONAS)) {
          const shown = menuPaths(u);
          for (const def of SETTINGS_ROUTES) {
            if (!shown.has(def.path) && settingsRouteAllows(def.id, u)) {
              expect(
                def.route,
                `${def.id} opens for ${name} with ${JSON.stringify(flags)} but is hidden in the sidebar, and has no documented exception`,
              ).toBeDefined();
            }
          }
        }
      }
    }
  });

  it('keeps pack-wizard behind its flag in the router too (it was owner-only before)', () => {
    g.__ff = {};
    expect(settingsRouteAllows('pack-wizard', PERSONAS.owner)).toBe(false);
    g.__ff = { ENABLE_ARCHETYPE_PACKS: true };
    expect(settingsRouteAllows('pack-wizard', PERSONAS.owner)).toBe(true);
    expect(settingsRouteAllows('pack-wizard', PERSONAS.manager)).toBe(false);
  });

  it('keeps accounting and AI settings reachable while their sidebar links are hidden', () => {
    g.__ff = {};
    expect(settingsRouteAllows('accounting-settings', PERSONAS.owner)).toBe(true);
    expect(settingsRouteAllows('ai-settings', PERSONAS.owner)).toBe(true);
    expect(settingsRouteAllows('accounting-settings', PERSONAS.salesStaff)).toBe(false);
    expect(settingsRouteAllows('ai-settings', PERSONAS.manager)).toBe(false);
  });

  it('keeps Telegram owner-only and behind its flag in the router, like the sidebar link', () => {
    g.__ff = {};
    expect(settingsRouteAllows('telegram', PERSONAS.owner)).toBe(false);
    g.__ff = { ENABLE_TELEGRAM: true };
    expect(settingsRouteAllows('telegram', PERSONAS.owner)).toBe(true);
    expect(settingsRouteAllows('telegram', PERSONAS.manager)).toBe(false);
    expect(settingsRouteAllows('telegram', PERSONAS.importOnly)).toBe(false);
    expect(settingsRouteAllows('telegram', PERSONAS.viewer)).toBe(false);
  });

  it('opens Help & health to platform staff without any Settings capability', () => {
    g.__ff = {};
    expect(settingsRouteAllows('help-health', PERSONAS.platformStaff)).toBe(true);
    expect(settingsRouteAllows('help-health', PERSONAS.viewer)).toBe(false);
  });
});

describe('App.tsx registers every Settings route through the shared list (SET-01)', () => {
  const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8');

  it('has no hand-written settings/* route', () => {
    expect(source.match(/path="settings\//g) ?? []).toEqual([]);
  });

  it('registers each listed screen exactly once', () => {
    for (const def of SETTINGS_ROUTES) {
      const matches = source.match(new RegExp(`settingsRoute\\('${def.id}'`, 'g')) ?? [];
      expect(matches.length, def.id).toBe(1);
    }
  });
});

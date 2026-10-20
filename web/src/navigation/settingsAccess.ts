import { isAccountingFeatureEnabled, isAiInsightsEnabled, isHelpV2Enabled, isTallyEnabled } from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import type { User } from '@/types/domain';
import { canAccessSettings, canExport, canImport, canManageGst, canManageUsers, isOwner } from '@/utils/permissions';

/**
 * SET-01: the one list of Settings screens. The sidebar (`menu.ts`) and the router (`App.tsx`)
 * both read it, so a screen cannot be shown in one and guarded differently in the other by
 * accident. Where the route is deliberately looser than the menu, the entry says why in
 * `routeLooserBecause`, and `settingsAccess.test.ts` fails if any other difference appears.
 *
 * Access here is the front-end gate only. The API enforces its own permission on every call.
 */
export type SettingsGroupId = 'business' | 'payments' | 'documents' | 'people' | 'plan';

/** SET-15: the five groups, in sidebar and hub order. */
export const SETTINGS_GROUPS: readonly { id: SettingsGroupId; labelKey: string }[] = [
  { id: 'business', labelKey: 'settingsGroups.business' },
  { id: 'payments', labelKey: 'settingsGroups.payments' },
  { id: 'documents', labelKey: 'settingsGroups.documents' },
  { id: 'people', labelKey: 'settingsGroups.people' },
  { id: 'plan', labelKey: 'settingsGroups.plan' },
];

export interface SettingsRouteDef {
  /** Which group heading the screen sits under. */
  group: SettingsGroupId;
  /** Sidebar item id (also used for help and flags). */
  id: string;
  labelKey: string;
  /** Absolute path, e.g. `/settings/company`. */
  path: string;
  /** Who sees the sidebar link. */
  menu: (user: User | null) => boolean;
  /** Who may open the route. Defaults to `menu`. */
  route?: (user: User | null) => boolean;
  /** Required whenever `route` is given: why the route is not the same as the menu. */
  routeLooserBecause?: string;
}

const ownerWithAccountingOffered = (user: User | null): boolean =>
  canManageUsers(user) &&
  (Boolean(user?.company?.accountingEnabled) || isAccountingFeatureEnabled(user?.company?.accountingEnabled));

export const SETTINGS_ROUTES: readonly SettingsRouteDef[] = [
  { id: 'company', labelKey: 'nav.company', path: '/settings/company', menu: canManageUsers, group: 'business' },
  { id: 'gst', labelKey: 'nav.gst', path: '/settings/gst', menu: canManageGst, group: 'business' },
  { id: 'statutory-licences', labelKey: 'nav.statutoryLicences', path: '/settings/statutory-licences', menu: canManageGst, group: 'business' },
  { id: 'bank-accounts', labelKey: 'nav.bankAccounts', path: '/settings/bank-accounts', menu: canManageUsers, group: 'payments' },
  { id: 'payment-gateway', labelKey: 'nav.paymentGateway', path: '/settings/payment-gateway', menu: canManageUsers, group: 'payments' },
  { id: 'money-in-rules', labelKey: 'nav.moneyInRules', path: '/settings/money-in', menu: canManageUsers, group: 'payments' },
  { id: 'price-lists', labelKey: 'nav.priceLists', path: '/settings/price-lists', menu: canManageUsers, group: 'payments' },
  {
    id: 'accounting-settings',
    labelKey: 'nav.accounting',
    path: '/settings/accounting',
    menu: ownerWithAccountingOffered,
    route: canManageUsers,
    routeLooserBecause:
      'This screen is where an owner turns accounting on, and the "Enable accounting" links on the limited-access pages point here, so it must open even while the sidebar link is hidden.',
    group: 'payments',
  },
  { id: 'series', labelKey: 'nav.seriesSettings', path: '/settings/series', menu: canManageUsers, group: 'documents' },
  { id: 'templates', labelKey: 'nav.invoiceTemplates', path: '/settings/templates', menu: canManageUsers, group: 'documents' },
  { id: 'units', labelKey: 'nav.units', path: '/settings/units', menu: canManageUsers, group: 'documents' },
  { id: 'item-settings', labelKey: 'nav.itemSettings', path: '/settings/items', menu: canManageUsers, group: 'documents' },
  { id: 'users', labelKey: 'nav.users', path: '/settings/users', menu: canManageUsers, group: 'people' },
  { id: 'import', labelKey: 'nav.importData', path: '/settings/import', menu: canImport, group: 'people' },
  {
    id: 'tally',
    labelKey: 'nav.tallyMigration',
    path: '/settings/tally',
    menu: (user) => canImport(user) && isTallyEnabled(),
    route: canImport,
    routeLooserBecause:
      'When Tally is not switched on the sidebar link is hidden, but the page opens and says so, instead of a bare "forbidden" for someone with an old bookmark.',
    group: 'people',
  },
  { id: 'backup', labelKey: 'nav.backupExport', path: '/settings/backup', menu: canExport, group: 'people' },
  { id: 'billing', labelKey: 'nav.billing', path: '/settings/billing', menu: canManageUsers, group: 'plan' },
  {
    id: 'ai-settings',
    labelKey: 'nav.aiSettings',
    path: '/settings/ai',
    menu: (user) => canManageUsers(user) && isAiInsightsEnabled(),
    route: canManageUsers,
    routeLooserBecause:
      'The "Enable" link on the limited-access page points here, so the route must open while the sidebar link is hidden. The screen cannot switch AI on (Bizboard controls that per company); it explains this.',
    group: 'plan',
  },
  {
    id: 'pack-wizard',
    labelKey: 'nav.packWizard',
    path: '/settings/packs',
    // The API answers 404 for this screen unless the pack flag is on, so the route follows the menu.
    menu: (user) => user?.role === 'OWNER' && isRuntimeFlagEnabled('ENABLE_ARCHETYPE_PACKS'),
    group: 'plan',
  },
  {
    id: 'telegram',
    labelKey: 'nav.telegram',
    path: '/settings/telegram',
    // Owner only, and only while the Telegram flag is on; the route follows the sidebar link.
    menu: (user) => canManageUsers(user) && isRuntimeFlagEnabled('ENABLE_TELEGRAM'),
    group: 'plan',
  },
  {
    id: 'counter-diagnostics',
    labelKey: 'nav.counterDiagnostics',
    path: '/settings/counter-diagnostics',
    // Owner only; the figures are the counter's own journey counts.
    menu: (user) => Boolean(user && isOwner(user.role)),
    group: 'plan',
  },
  {
    id: 'help-health',
    labelKey: 'nav.helpHealth',
    path: '/settings/help',
    menu: (user) => Boolean(user && (isOwner(user.role) || user.isStaff) && isHelpV2Enabled()),
    route: (user) => Boolean(user && (isOwner(user.role) || user.isStaff)),
    routeLooserBecause: 'The page itself checks the Help v2 flag and shows the forbidden page when it is off.',
    group: 'plan',
  },
];

const BY_ID = new Map(SETTINGS_ROUTES.map((def) => [def.id, def]));

export function settingsRouteDef(id: string): SettingsRouteDef {
  const def = BY_ID.get(id);
  if (!def) throw new Error(`Unknown settings route: ${id}`);
  return def;
}

/** Router guard for one Settings screen: Settings access first, then the screen's own rule. */
export function settingsRouteAllows(id: string, user: User | null): boolean {
  const def = settingsRouteDef(id);
  if (id === 'help-health') {
    // Platform staff reach Help & health even without any Settings capability.
    return (def.route ?? def.menu)(user);
  }
  return canAccessSettings(user) && (def.route ?? def.menu)(user);
}

/**
 * SET-19: the order a new owner would usually set things up in. After a save, the Settings frame
 * offers the next screen in this list that the person may open. Screens not listed offer none.
 */
export const SETUP_ORDER: readonly string[] = [
  'company',
  'gst',
  'statutory-licences',
  'bank-accounts',
  'payment-gateway',
  'money-in-rules',
  'series',
  'templates',
  'units',
  'item-settings',
  'price-lists',
  'users',
];

/** The settings screen whose path is `pathname`, or null (the hub, or not a settings path). */
export function settingsDefForPath(pathname: string): SettingsRouteDef | null {
  const clean = pathname.replace(/\/+$/, '');
  return SETTINGS_ROUTES.find((def) => clean === def.path || clean.startsWith(`${def.path}/`)) ?? null;
}

export function nextSettingsStep(pathname: string, user: User | null): SettingsRouteDef | null {
  const current = settingsDefForPath(pathname);
  if (!current) return null;
  const at = SETUP_ORDER.indexOf(current.id);
  if (at < 0) return null;
  for (const id of SETUP_ORDER.slice(at + 1)) {
    if (settingsRouteAllows(id, user) && settingsRouteDef(id).menu(user)) return settingsRouteDef(id);
  }
  return null;
}

/** SET-21: which audit area each screen's "Recent changes" reads (see `accounts/settings_history.py`). */
export const HISTORY_AREAS: Readonly<Record<string, string>> = {
  company: 'company',
  gst: 'gst',
  'statutory-licences': 'licences',
  'bank-accounts': 'banks',
  'payment-gateway': 'gateway',
  'money-in-rules': 'money_in',
  series: 'series',
  units: 'units',
  'price-lists': 'price_lists',
  users: 'users',
  'accounting-settings': 'accounting',
  'pack-wizard': 'packs',
  'item-settings': 'items',
};

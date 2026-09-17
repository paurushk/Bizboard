import type { ContextHelpPage } from '../types';
import { INVENTORY_HELP } from './inventory';
import { MORE_HELP } from './more';
import { PAYMENTS_HELP } from './payments';
import { PURCHASE_HELP } from './purchases';
import { REPORTS_HELP, SETTINGS_HELP } from './reports';
import { SALES_HELP } from './sales';
import { SCREEN_VARIANTS } from './screens';

/** Shared family drafts used only as helpVariant() bases — not routed. */
const HIDDEN_BASE_IDS = new Set([
  'gst-return',
  'books-report',
  'manufacturing',
  'payroll',
  'crm',
]);

const ALL: ContextHelpPage[] = [
  ...SALES_HELP,
  ...PURCHASE_HELP,
  ...INVENTORY_HELP,
  ...PAYMENTS_HELP,
  ...REPORTS_HELP,
  ...SETTINGS_HELP,
  ...MORE_HELP,
  ...SCREEN_VARIANTS,
].filter((page) => !HIDDEN_BASE_IDS.has(page.id));

const BY_ID = new Map(ALL.map((page) => [page.id, page]));

export function getContextHelpPage(id: string | undefined): ContextHelpPage | undefined {
  if (!id) return undefined;
  return BY_ID.get(id);
}

export function listContextHelpPageIds(): string[] {
  return ALL.map((page) => page.id);
}

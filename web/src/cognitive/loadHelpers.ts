import { inferInvoiceTypeFromParty } from '@/pages/sales/invoiceDefaults';
import { extractStateCode } from '@/utils/tax';

/** BUG-COG-001. Null means leave the select as the user left it. */
export function resolveInvoiceType(args: {
  isEdit: boolean;
  touched: boolean;
  savedType?: string | null;
  registrationType?: string | null;
  customerGstin?: string | null;
}): 'GST' | 'NON_GST' | 'RETAIL' | null {
  if (args.isEdit) {
    const saved = args.savedType;
    if (saved === 'GST' || saved === 'NON_GST' || saved === 'RETAIL' || saved === 'TAX') {
      return saved === 'TAX' ? 'GST' : saved;
    }
    return null;
  }
  if (args.touched) return null;
  return inferInvoiceTypeFromParty({
    registrationType: args.registrationType,
    customerGstin: args.customerGstin,
  });
}

export const BANK_MATCH_DATE_TOLERANCE_DAYS = 14;

export type BankCandidate = {
  id: unknown;
  type?: string;
  amount?: unknown;
  date?: string | null;
};

/** BUG-COG-017. Exactly one same-amount candidate inside the statement window. */
export function uniqueSameAmountCandidate<T extends BankCandidate>(
  lineAmount: number,
  lineDate: string | null | undefined,
  candidates: T[],
): T | null {
  const hits = candidates.filter((candidate) => {
    const amount = Number(candidate.amount);
    if (!Number.isFinite(amount)) return false;
    if (Math.abs(Math.abs(lineAmount) - Math.abs(amount)) > 0.01) return false;
    if (!lineDate || !candidate.date) return true;
    const left = Date.parse(lineDate);
    const right = Date.parse(candidate.date);
    if (!Number.isFinite(left) || !Number.isFinite(right)) return true;
    const days = Math.abs(left - right) / 86_400_000;
    return days <= BANK_MATCH_DATE_TOLERANCE_DAYS;
  });
  return hits.length === 1 ? hits[0] : null;
}

export type PlacePrompt =
  | { ask: false; code: string | null }
  | { ask: true; reason: 'conflict'; gstinCode: string; addressCode: string }
  | { ask: true; reason: 'missing' };

/** BUG-COG-007. A GSTIN state is an answer. Ask only on a clash or a blank. */
export function decidePlaceOfSupply(gstin?: string | null, addressState?: string | null): PlacePrompt {
  const gstinCode = extractStateCode(gstin || undefined);
  const addressCode = extractStateCode(addressState || undefined);
  if (gstinCode && addressCode && gstinCode !== addressCode) {
    return { ask: true, reason: 'conflict', gstinCode, addressCode };
  }
  if (gstinCode) return { ask: false, code: gstinCode };
  if (addressCode) return { ask: false, code: addressCode };
  return { ask: true, reason: 'missing' };
}

export type StatutoryInput = {
  supplyType?: string | null;
  companyGstinId?: number | '' | null;
  costCenterId?: number | '' | null;
  ecommerceGstin?: string | null;
  reverseCharge?: boolean;
};

/** BUG-COG-004. Chips for non-defaults. The drawer stays available. */
export function statutoryChipIds(flags: StatutoryInput): string[] {
  const chips: string[] = [];
  const supply = (flags.supplyType || 'B2B').toUpperCase();
  if (supply !== 'B2B') chips.push(`supply:${supply}`);
  if (flags.companyGstinId) chips.push('gstin');
  if (flags.costCenterId) chips.push('cost');
  if ((flags.ecommerceGstin || '').trim()) chips.push('ecom');
  if (flags.reverseCharge) chips.push('rcm');
  return chips;
}

/** Shop-language chip for the invoice type. The stored enum is unchanged. */
export function invoiceTypeChipKey(type: string, hasGstin: boolean): string {
  if (type === 'NON_GST') return 'billing.nonGstInvoice';
  if (type === 'TAX') return 'billing.taxInvoice';
  if (type === 'GST' && hasGstin) return 'cog.billGstinCustomer';
  return 'cog.billWalkIn';
}

/** One active godown is text. Two or more, or a saved non-default godown, stay a select. */
export function showGodownSelect(args: {
  activeCount: number;
  isEdit: boolean;
  selectedId: number | '' | null;
  defaultId: number | '' | null;
}): boolean {
  if (args.activeCount >= 2) return true;
  if (!args.isEdit || args.activeCount === 0) return false;
  const selected = args.selectedId === '' || args.selectedId == null ? null : Number(args.selectedId);
  const fallback = args.defaultId === '' || args.defaultId == null ? null : Number(args.defaultId);
  if (selected == null || fallback == null) return false;
  return selected !== fallback;
}

export function statutoryChipLabel(id: string): string {
  switch (id) {
    case 'supply:SEZWP':
      return 'cog.chipSezwp';
    case 'supply:SEZWOP':
      return 'cog.chipSezwop';
    case 'supply:EXPWP':
      return 'cog.chipExpwp';
    case 'supply:EXPWOP':
      return 'cog.chipExpwop';
    case 'supply:DEXP':
      return 'cog.chipDexp';
    case 'gstin':
      return 'cog.chipGstin';
    case 'cost':
      return 'cog.chipCost';
    case 'ecom':
      return 'cog.chipEcom';
    case 'rcm':
      return 'cog.chipRcm';
    default:
      return 'cog.chipRcm';
  }
}

export function prefillReturnLines<T extends { quantity: number; included?: boolean; maxQty: number }>(
  lines: T[],
  full = false,
): T[] {
  return lines.map((line) => ({
    ...line,
    included: true,
    quantity: full ? line.maxQty : 0,
  }));
}

export function fillPurchaseFromProduct(
  product: {
    name: string;
    description?: string | null;
    hsnCode?: string | null;
    gstRate?: string | number | null;
    purchasePrice?: string | number | null;
  },
  typedRate?: number | null,
): { description: string; hsnCode: string; gstRate: number; unitPrice: number; source: 'item' } {
  const master = Number(product.purchasePrice);
  const unitPrice = typedRate != null && Number.isFinite(typedRate) ? typedRate : Number.isFinite(master) ? master : 0;
  return {
    description: (product.description || product.name || '').trim(),
    hsnCode: (product.hsnCode || '').trim(),
    gstRate: Number(product.gstRate) || 0,
    unitPrice,
    source: 'item',
  };
}

export type JobTemplate = 'cashier' | 'store' | 'bookkeeper' | 'owner' | 'custom';

export type JobCaps = {
  canCreateSales: boolean;
  canCreatePurchases: boolean;
  canCreatePayments: boolean;
  canViewFinancialReports: boolean;
  canExport: boolean;
  canManageInventory: boolean;
  canImport: boolean;
  canCancelDocuments: boolean;
};

const JOB_OFF: JobCaps = {
  canCreateSales: false,
  canCreatePurchases: false,
  canCreatePayments: false,
  canViewFinancialReports: false,
  canExport: false,
  canManageInventory: false,
  canImport: false,
  canCancelDocuments: false,
};

/** BUG-COG-011. Fills the eight checkboxes. Custom returns null so the grid stays as typed. */
export function capsForJobTemplate(template: JobTemplate): JobCaps | null {
  if (template === 'custom') return null;
  if (template === 'cashier') return { ...JOB_OFF, canCreateSales: true, canCreatePayments: true };
  if (template === 'store') return { ...JOB_OFF, canCreatePurchases: true, canManageInventory: true };
  if (template === 'bookkeeper') {
    return {
      ...JOB_OFF,
      canCreatePurchases: true,
      canCreatePayments: true,
      canViewFinancialReports: true,
      canExport: true,
    };
  }
  return {
    canCreateSales: true,
    canCreatePurchases: true,
    canCreatePayments: true,
    canViewFinancialReports: true,
    canExport: true,
    canManageInventory: true,
    canImport: true,
    canCancelDocuments: true,
  };
}

export function primaryPostedAction(args: {
  status: string;
  balance: number;
  canPay: boolean;
}): 'complete' | 'pay' | 'share' {
  if (args.status === 'DRAFT') return 'complete';
  if (args.status === 'COMPLETED' && args.balance > 0.009 && args.canPay) return 'pay';
  return 'share';
}

export function slaChipModel(args: {
  status: string;
  slaDueAt?: string | null;
  createdAt?: string | null;
  now: number;
}): { kind: 'none' | 'paused' | 'remaining' | 'breached'; minutes: number; elapsedMinutes: number } {
  if (!args.slaDueAt) return { kind: 'none', minutes: 0, elapsedMinutes: 0 };
  const due = Date.parse(args.slaDueAt);
  const opened = args.createdAt ? Date.parse(args.createdAt) : args.now;
  const elapsedMinutes = Number.isFinite(opened) ? Math.max(0, Math.round((args.now - opened) / 60000)) : 0;
  if (args.status === 'WAITING') return { kind: 'paused', minutes: 0, elapsedMinutes };
  if (!Number.isFinite(due)) return { kind: 'none', minutes: 0, elapsedMinutes };
  const minutes = Math.round((due - args.now) / 60000);
  if (minutes < 0) return { kind: 'breached', minutes: Math.abs(minutes), elapsedMinutes };
  return { kind: 'remaining', minutes, elapsedMinutes };
}

/** Visible window for a master table. A 5,000-row list still paints only `size` rows. */
export function visibleRowSlice(count: number, start: number, size: number): number[] {
  const from = Math.max(0, Math.min(start, count));
  const to = Math.min(count, from + Math.max(0, size));
  return Array.from({ length: Math.max(0, to - from) }, (_, index) => from + index);
}

export function scanShouldStealFocus(activeTag: string | null, searchFocused: boolean): boolean {
  if (searchFocused || !activeTag) return true;
  const tag = activeTag.toUpperCase();
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return false;
  return true;
}

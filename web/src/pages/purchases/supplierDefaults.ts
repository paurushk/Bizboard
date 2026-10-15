import type { PurchaseInvoice } from '@/types/domain';

/**
 * What a shop last chose for each supplier, so the next bill from that supplier starts the same way
 * (ITC treatment, reverse charge, payment terms) instead of asking the same three questions again.
 * Stored in this browser only: a convenience, never a source of truth.
 */
export type SupplierDefaults = {
  itcEligibility: NonNullable<PurchaseInvoice['itcEligibility']>;
  isReverseCharge: boolean;
  paymentTermsDays: number;
  /** Last TDS section / rate used with this supplier (empty when none). */
  tdsSection?: string;
  tdsRate?: number;
};

const key = (companyId: number) => `bizboard:purchase:supplierDefaults:${companyId}`;

function readAll(companyId: number): Record<string, SupplierDefaults> {
  try {
    const raw = localStorage.getItem(key(companyId));
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, SupplierDefaults>) : {};
  } catch {
    return {};
  }
}

export function loadSupplierDefaults(companyId: number, supplierId: number): SupplierDefaults | null {
  const found = readAll(companyId)[String(supplierId)];
  if (!found) return null;
  const days = Number(found.paymentTermsDays);
  return {
    itcEligibility: found.itcEligibility,
    isReverseCharge: Boolean(found.isReverseCharge),
    paymentTermsDays: Number.isFinite(days) && days >= 0 ? days : 0,
    tdsSection: typeof found.tdsSection === 'string' ? found.tdsSection : '',
    tdsRate: Number.isFinite(Number(found.tdsRate)) ? Number(found.tdsRate) : 0,
  };
}

export function saveSupplierDefaults(companyId: number, supplierId: number, value: SupplierDefaults): void {
  try {
    const all = readAll(companyId);
    all[String(supplierId)] = value;
    localStorage.setItem(key(companyId), JSON.stringify(all));
  } catch {
    // Private mode or full storage: the next bill simply starts from the usual defaults.
  }
}

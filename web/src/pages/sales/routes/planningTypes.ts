/** Shapes and small rules for the route planning screens (hardening plan R7). The server decides; this reads. */

export type RiskLevel = 'block' | 'warn' | 'info';
export type RiskOverride = 'none' | 'owner' | 'manager' | 'any';

export type PlanRisk = {
  code: string;
  level: RiskLevel;
  message: string;
  override: RiskOverride;
  severity?: string;
  /** Preflight only: whether someone has accepted this risk on the route already. */
  acknowledged?: boolean;
  acknowledgedReason?: string;
  canAccept?: boolean;
};

export type PlanSummary = {
  order: number;
  number?: string | null;
  status: string;
  orderDate?: string | null;
  expectedDelivery?: string | null;
  customer: { id: number; name: string; phone?: string; pincode?: string; state?: string; status?: string; hasLocation?: boolean };
  deliveryAddress?: string;
  lines: Array<{ product: number; name: string; quantity: string; unit?: string; available: string | null; short: string }>;
  lineCount: number;
  totalQuantity: string;
  grandTotal: string;
  bill: {
    billStatus: string;
    paymentTermsDays: number;
    onCredit: boolean;
    amountToCollect: string;
    invoices: Array<{ id: number; number?: string; status?: string; grandTotal?: string; balance?: string }>;
  };
  risks: PlanRisk[];
  ready: boolean;
  hasWarnings: boolean;
  money?: {
    outstanding?: string;
    overdue?: string;
    availableCredit?: string | null;
    collectionStatus?: string;
    creditLimit?: string;
    exposure?: string | null;
  };
  lowMarginProducts?: string[];
};

export type Acknowledgements = Record<number, Record<string, string>>;

/** Whether someone in this role may accept a risk (mirrors the server; the server is the authority). */
export function roleMayAccept(role: string | undefined, override: RiskOverride): boolean {
  if (override === 'none') return false;
  if (override === 'owner') return role === 'OWNER';
  if (override === 'manager') return role === 'OWNER' || role === 'MANAGER';
  return true;
}

/** Risks that must be accepted (with a reason) before this order can go on a route. */
export function risksToAccept(summary: PlanSummary, role: string | undefined): PlanRisk[] {
  return summary.risks.filter((r) => r.level !== 'info' && roleMayAccept(role, r.override));
}

/** Why this order cannot be ticked, or null when it can (possibly after accepting its risks). */
export function whyNotSelectable(summary: PlanSummary, role: string | undefined): PlanRisk | null {
  return summary.risks.find((r) => r.level !== 'info' && !roleMayAccept(role, r.override)) ?? null;
}

/** The request body for the server: one entry per accepted risk. */
export function acknowledgementPayload(acks: Acknowledgements): Array<{ order: number; code: string; reason: string }> {
  const out: Array<{ order: number; code: string; reason: string }> = [];
  for (const [order, codes] of Object.entries(acks)) {
    for (const [code, reason] of Object.entries(codes)) out.push({ order: Number(order), code, reason });
  }
  return out;
}

export function totalsFor(summaries: PlanSummary[]) {
  const sum = (pick: (s: PlanSummary) => string) => summaries.reduce((acc, s) => acc + (Number(pick(s)) || 0), 0);
  return {
    orders: summaries.length,
    quantity: sum((s) => s.totalQuantity),
    value: sum((s) => s.grandTotal),
    toCollect: sum((s) => s.bill.amountToCollect),
  };
}

/** Stable area order for the "group by area" view: pincode, then order number. */
export function groupByArea(rows: PlanSummary[]): Array<{ pincode: string; rows: PlanSummary[] }> {
  const groups = new Map<string, PlanSummary[]>();
  for (const row of rows) {
    const key = (row.customer.pincode ?? '').trim() || '—';
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === '—' ? 1 : b === '—' ? -1 : a.localeCompare(b)))
    .map(([pincode, list]) => ({ pincode, rows: list }));
}

/** Shapes and small rules shared by the delivery-route screens (hardening plan R5). */

export type StopBill = {
  orderTotal?: string;
  paymentTermsDays?: number;
  billStatus?: 'order_only' | 'challan' | 'draft_invoice' | 'invoiced' | 'paid';
  invoices?: Array<{ id: number; number?: string; status?: string; grandTotal?: string; balance?: string }>;
  amountToCollect?: string;
  onCredit?: boolean;
  advanceAvailable?: string;
};

export type RouteStop = {
  id: number;
  salesOrder: number;
  orderNumber?: string;
  customerName?: string;
  customer?: number;
  customerPhone?: string;
  deliveryAddress?: string;
  status?: string;
  sequence?: number;
  notes?: string;
  completionSource?: string;
  receivedByName?: string;
  collectedCash?: string | number;
  collectedUpi?: string | number;
  upiReference?: string;
  customerReceipt?: number | null;
  /** The live invoice behind a stop that did not deliver: it stands until a sales return is recorded. */
  activeInvoice?: { id: number; number?: string } | null;
  bill?: StopBill | null;
  /** What went out on the order's challan and can still come back (null when nothing can). */
  returnableLines?: Array<{ product: number; productName: string; quantity: string }> | null;
};

export type RouteWarning = { code: string; route: number; number?: string; message: string };

export type RouteProgress = {
  stopsTotal: number;
  pending: number;
  delivered: number;
  failed: number;
  collected: string;
  needsAttention: string[];
};

export type RouteHandover = {
  status?: string;
  expectedCash?: string | number;
  expectedUpi?: string | number;
  countedCash?: string | number;
  countedUpi?: string | number;
  varianceAmount?: string | number;
  varianceNote?: string;
};

export type RouteRow = {
  id: number;
  number?: string;
  routeDate?: string;
  vehicleNumber?: string;
  driverName?: string;
  driver?: number | null;
  status?: string;
  notes?: string;
  rollup?: { expectedProfit?: string | number } | null;
  realizedProfit?: string | number | null;
  invoicedStopCount?: number | null;
  stopCount?: number | null;
  stops?: RouteStop[];
  warnings?: RouteWarning[];
  progress?: RouteProgress;
  cashHandover?: RouteHandover | null;
};

/** Outcomes the office can record for a stop, in the order they are offered. */
export const STOP_OUTCOMES = ['DELIVERED', 'FAILED', 'REJECTED', 'RETURNED'] as const;
export type StopOutcome = (typeof STOP_OUTCOMES)[number];

export const RECORDED_STATUSES = new Set<string>(STOP_OUTCOMES);

/** What the office has to look at on a route, as the words the screen uses. */
export const ATTENTION_LABEL_KEYS: Record<string, string> = {
  failed_stops: 'routes.attention.failedStops',
  cash_unverified: 'routes.attention.cashUnverified',
  cash_variance_unexplained: 'routes.attention.cashVarianceUnexplained',
  ready_to_close: 'routes.attention.readyToClose',
};

/** Sort key: routes that need the office come first, newest first within each group. */
export function routeSortKey(row: RouteRow): [number, string] {
  const attention = (row.progress?.needsAttention ?? []).filter((a) => a !== 'ready_to_close');
  return [attention.length > 0 ? 0 : 1, String(row.routeDate ?? '')];
}

export function sortRoutes(rows: RouteRow[]): RouteRow[] {
  return [...rows].sort((a, b) => {
    const [ga, da] = routeSortKey(a);
    const [gb, db] = routeSortKey(b);
    if (ga !== gb) return ga - gb;
    if (da !== db) return da < db ? 1 : -1;
    return (b.id ?? 0) - (a.id ?? 0);
  });
}

export type OutcomeFormValues = {
  outcome: StopOutcome;
  receivedBy: string;
  cash: string;
  upi: string;
  upiReference: string;
  reason: string;
  note: string;
  byOffice: boolean;
  code: string;
  /** product id -> quantity that came back, as typed. */
  returned: Record<number, string>;
  /** On a delivered stop: some of it came back. */
  someCameBack: boolean;
};

/** Checks the outcome form before anything is sent. Returns the first problem, or null. */
export function validateOutcome(
  values: OutcomeFormValues,
  opts: { changing: boolean; returnable?: Array<{ product: number; quantity: string }> | null },
): string | null {
  const cash = values.cash.trim() === '' ? 0 : Number(values.cash);
  const upi = values.upi.trim() === '' ? 0 : Number(values.upi);
  if (opts.changing && values.reason.trim().length < 3) return 'routes.errors.reasonNeeded';
  if (values.outcome === 'DELIVERED') {
    if (!values.receivedBy.trim()) return 'routes.errors.receiverNeeded';
    if (!Number.isFinite(cash) || cash < 0 || !Number.isFinite(upi) || upi < 0) return 'routes.errors.amountInvalid';
    if (upi > 0 && !values.upiReference.trim()) return 'routes.errors.upiReferenceNeeded';
  }
  if (cameBack(values)) {
    for (const line of opts.returnable ?? []) {
      const typed = values.returned[line.product];
      const qty = typed == null || typed.trim() === '' ? 0 : Number(typed);
      if (!Number.isFinite(qty) || qty < 0) return 'routes.errors.returnedInvalid';
      if (qty > Number(line.quantity)) return 'routes.errors.returnedTooMany';
    }
  }
  return null;
}

/** True when this outcome should send quantities that came back. */
export function cameBack(values: Pick<OutcomeFormValues, 'outcome' | 'someCameBack'>): boolean {
  return values.outcome === 'DELIVERED' ? values.someCameBack : true;
}

/** The lines to send for goods that came back, or undefined to mean "all of it" / nothing. */
export function returnedLinesPayload(
  values: OutcomeFormValues,
  returnable: Array<{ product: number; quantity: string }> | null | undefined,
): Array<{ product: number; quantity: string }> | undefined {
  if (!returnable || returnable.length === 0 || !cameBack(values)) return undefined;
  return returnable
    .map((line) => ({ product: line.product, quantity: (values.returned[line.product] ?? line.quantity).trim() || '0' }))
    .filter((line) => Number(line.quantity) > 0);
}

import { apiClient, unwrapData } from '@/api/client';
import { withMocks } from '@/api/legacy/common';
import type { CustomerReceipt } from '@/types/domain';

/** Decimal strings from the API. Format with formatMoney; add with toNumber. */
type Money = string | number;
type CountAmount = { count: number; amount: Money };
/** `query` is a ready query string (filter names are snake_case and must not be camel-cased). */
export type MoneyLink = { route: string; query: string };

export type MoneyAgeing = {
  current: Money;
  /** The renderer camel-cases days_1_30 to days130, as on the dashboard. */
  days130: Money;
  days3160: Money;
  days6190: Money;
  days90Plus: Money;
};

export type MoneyBills = {
  outstanding: Money;
  bills: CountAmount;
  /** Held in the party total but not on an open bill: opening balances, adjustments, GL difference. */
  notOnABill: Money;
  overdue: CountAmount;
  dueSoon: CountAmount;
  ageing: MoneyAgeing;
};

export type MoneyAction = {
  kind: 'chase_customer' | 'pay_supplier' | 'broken_promise' | 'clear_cheque_in' | 'clear_cheque_out';
  partyId: number;
  partyName: string;
  reference: string;
  amount: Money;
  days: number;
  link: MoneyLink;
};

export type MoneyPosition = {
  asOf: string;
  basis: { receivable: 'GL' | 'DOCUMENTS'; payable: 'GL' | 'DOCUMENTS' };
  net: { receivable: Money; payable: Money; net: Money } | null;
  cash: {
    cleared: Money;
    byAccount: Array<{ id: number; name: string; balance: Money }>;
    inflowMtd: Money;
  } | null;
  moneyIn: {
    bills: MoneyBills | null;
    advances: CountAmount | null;
    chequesPending: CountAmount | null;
    chequesBounced: (CountAmount & { windowDays: number }) | null;
    tdsReceivable: (CountAmount & { olderThan30Days: number }) | null;
    promises: { due: CountAmount; broken: CountAmount } | null;
    unmatchedBankCredits: CountAmount | null;
    gatewayAwaitingBooks: CountAmount | null;
    paymentLinksOpen: CountAmount | null;
  };
  moneyOut: {
    bills: MoneyBills | null;
    advancesPaid: CountAmount | null;
    chequesIssuedPending: CountAmount | null;
    unmatchedBankDebits: CountAmount | null;
  };
  reconciliation:
    | { available: false; reason: string }
    | {
        available: true;
        basis: 'GL' | 'DOCUMENTS';
        glReceivable: Money;
        glPayable: Money;
        advancesReceived: Money;
        differenceReceivable: Money;
        differencePayable: Money;
      }
    | null;
  actions: MoneyAction[] | null;
  /** Names of sections that could not be computed. Their tiles say so; they never read as zero. */
  partial: string[];
};

export type MoneyTimeline = {
  asOf: string;
  days: number;
  basis: 'DUE_DATE';
  note: string;
  openingCash: Money;
  inflow: Money;
  outflow: Money;
  closingCash: Money;
  lowestBalance: Money;
  overdueNow: { in: Money; out: Money };
  beyondHorizon: { in: Money; out: Money };
  timeline: Array<{
    date: string;
    inflow: Money;
    outflow: Money;
    balance: Money;
    items: Array<{
      side: 'in' | 'out';
      party: string;
      reference: string;
      amount: Money;
      promised: boolean;
      estimate?: boolean;
    }>;
  }>;
};

export type MoneyStatutory = {
  asOf: string;
  items: Array<{
    kind: 'tds_payable' | 'gst_payable';
    label: string;
    period: string;
    amount: string | null;
    dueDate: string;
    estimate: boolean;
    link: MoneyLink;
  }>;
  unavailable: string[];
  note: string;
};

const ZERO = { count: 0, amount: '0.00' };
const EMPTY_BILLS: MoneyBills = {
  outstanding: '0.00',
  bills: ZERO,
  notOnABill: '0.00',
  overdue: ZERO,
  dueSoon: ZERO,
  ageing: { current: '0.00', days130: '0.00', days3160: '0.00', days6190: '0.00', days90Plus: '0.00' },
};
const mockPosition = (): MoneyPosition => ({
  asOf: new Date().toISOString().slice(0, 10),
  basis: { receivable: 'DOCUMENTS', payable: 'DOCUMENTS' },
  net: { receivable: '0.00', payable: '0.00', net: '0.00' },
  cash: { cleared: '0.00', byAccount: [], inflowMtd: '0.00' },
  moneyIn: {
    bills: EMPTY_BILLS,
    advances: ZERO,
    chequesPending: ZERO,
    chequesBounced: { ...ZERO, windowDays: 30 },
    tdsReceivable: { ...ZERO, olderThan30Days: 0 },
    promises: { due: ZERO, broken: ZERO },
    unmatchedBankCredits: ZERO,
    gatewayAwaitingBooks: ZERO,
    paymentLinksOpen: ZERO,
  },
  moneyOut: { bills: EMPTY_BILLS, advancesPaid: ZERO, chequesIssuedPending: ZERO, unmatchedBankDebits: ZERO },
  reconciliation: { available: false, reason: 'books_off' },
  actions: [],
  partial: [],
});

export async function getMoneyPosition(): Promise<MoneyPosition> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/money/position/');
    return unwrapData<MoneyPosition>(data);
  }, mockPosition);
}

export async function getMoneyTimeline(days = 30): Promise<MoneyTimeline> {
  return withMocks(
    async () => {
      const { data } = await apiClient.get('/money/timeline/', { params: { days } });
      return unwrapData<MoneyTimeline>(data);
    },
    () => ({
      asOf: new Date().toISOString().slice(0, 10),
      days,
      basis: 'DUE_DATE' as const,
      note: '',
      openingCash: '0.00',
      inflow: '0.00',
      outflow: '0.00',
      closingCash: '0.00',
      lowestBalance: '0.00',
      overdueNow: { in: '0.00', out: '0.00' },
      beyondHorizon: { in: '0.00', out: '0.00' },
      timeline: [],
    }),
  );
}

export async function getMoneyStatutory(): Promise<MoneyStatutory> {
  return withMocks(
    async () => {
      const { data } = await apiClient.get('/money/statutory/');
      return unwrapData<MoneyStatutory>(data);
    },
    () => ({ asOf: new Date().toISOString().slice(0, 10), items: [], unavailable: [], note: '' }),
  );
}

export type SupplierPaymentSummary = {
  count: number;
  paid: Money;
  chequesPending: Money;
  advance: Money;
  excludedCount: number;
  /** Null unless the caller may view financial reports. */
  payable: Money | null;
  overdue: Money | null;
};

export type SupplierPaymentFilterParams = {
  supplier?: number | string;
  mode?: string;
  status?: string;
  cheque_status?: string;
  advance?: string;
  date_from?: string;
  date_to?: string;
};

export async function getSupplierPaymentsSummary(
  params?: SupplierPaymentFilterParams,
): Promise<SupplierPaymentSummary> {
  return withMocks(
    async () => {
      const { data } = await apiClient.get('/payments/supplier-payments/summary/', { params });
      return unwrapData<SupplierPaymentSummary>(data);
    },
    { count: 0, paid: '0.00', chequesPending: '0.00', advance: '0.00', excludedCount: 0, payable: null, overdue: null },
  );
}

/** Record (or undo) that the customer's TDS certificate arrived. Posts nothing to the ledger. */
export async function setReceiptTdsCertificate(
  id: number,
  payload: { received: boolean; receivedOn?: string; reference?: string },
): Promise<CustomerReceipt> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/tds-certificate/`, {
    received: payload.received,
    received_on: payload.receivedOn,
    reference: payload.reference,
  });
  return unwrapData<CustomerReceipt>(data);
}

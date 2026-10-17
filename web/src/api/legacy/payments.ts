import { apiClient, idempotencyHeaders, unwrapData } from '../client';
import {
  mockAccountingBankReconSessions,
  mockBankStatements,
  mockCollectionRisk,
  mockPaymentLinks,
  mockReceipts,
  mockReconLines,
} from '@/mocks/data';
import type {
  AdvanceRefund,
  BulkAllocateResult,
  CustomerReceipt,
  CustomerReceiptCreated,
  PaymentAllocation,
  PaymentPromise,
  ReceiptSummary,
  SupplierPayment,
} from '@/types/domain';
import { withMocks, fetchPage, fetchAllPagesMasters, getBlob, toQueryParams, type PageResult, type PageParams } from './common';

/** Open (unresolved) payment promises for the company, or all when `all: true`. */
export async function listPaymentPromises(params?: {
  all?: boolean;
  invoice?: number;
  customer?: number;
}): Promise<PaymentPromise[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/payments/promises/', {
      params: {
        ...(params?.all ? { all: '1' } : {}),
        ...(params?.invoice ? { invoice: params.invoice } : {}),
        ...(params?.customer ? { customer: params.customer } : {}),
      },
    });
    const unwrapped = unwrapData<PaymentPromise[] | { results?: PaymentPromise[] }>(data);
    if (Array.isArray(unwrapped)) return unwrapped;
    if (unwrapped && Array.isArray((unwrapped as { results?: PaymentPromise[] }).results)) {
      return (unwrapped as { results: PaymentPromise[] }).results;
    }
    return [];
  }, []);
}

export async function createPaymentPromise(payload: {
  customer: number;
  invoice?: number | null;
  promisedDate: string;
  promisedAmount: string;
  note?: string;
}): Promise<PaymentPromise> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/promises/', payload);
    return unwrapData<PaymentPromise>(data);
  }, {
    id: Date.now(),
    customer: payload.customer,
    invoice: payload.invoice ?? null,
    promisedDate: payload.promisedDate,
    note: payload.note ?? '',
    resolved: false,
  });
}

export async function resolvePaymentPromise(id: number): Promise<PaymentPromise> {
  return withMocks(async () => {
    const { data } = await apiClient.post(`/payments/promises/${id}/resolve/`);
    return unwrapData<PaymentPromise>(data);
  }, {
    id,
    customer: 0,
    promisedDate: '',
    resolved: true,
  });
}

export async function listReceiptsPage(
  params?: PageParams,
): Promise<PageResult<CustomerReceipt>> {
  return withMocks(async () => fetchPage<CustomerReceipt>('/payments/receipts/', params), {
    results: mockReceipts,
    count: mockReceipts.length,
    next: null,
    previous: null,
  });
}

export async function createReceipt(
  payload: {
    customer: number;
    amount: number | string;
    mode: string;
    receiptDate?: string;
    reference?: string;
    utr?: string;
    bankAccount?: number;
    notes?: string;
    chequeNumber?: string;
    chequeBankName?: string;
    chequeDate?: string;
    chequeImage?: number;
    settlementDiscount?: number | string;
    /** Income tax the customer deducted at source (194C/J/Q...). */
    tdsDeducted?: number | string;
    tdsSection?: string;
    allocateOldest?: boolean;
    paidFromTill?: boolean;
    /** Apply to one invoice in the same transaction as the receipt. */
    salesInvoice?: number;
    allocateAmount?: number | string;
  },
  options?: { idempotencyKey?: string },
): Promise<CustomerReceiptCreated> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/receipts/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<CustomerReceiptCreated>(data);
  }, {
    id: Date.now(),
    customer: payload.customer,
    amount: payload.amount,
    mode: payload.mode as CustomerReceipt['mode'],
    receiptDate: payload.receiptDate ?? new Date().toISOString().slice(0, 10),
    allocated: 0,
    unallocated: payload.amount,
  });
}

export async function voidReceipt(
  id: number,
  reason: string,
  options?: { idempotencyKey?: string },
): Promise<CustomerReceipt> {
  const { data } = await apiClient.post(
    `/payments/receipts/${id}/void/`,
    { reason },
    { headers: idempotencyHeaders(options?.idempotencyKey) },
  );
  return unwrapData<CustomerReceipt>(data);
}

/** Correct the descriptive fields of a posted receipt. Money fields need void and re-enter. */
export async function editReceipt(
  id: number,
  changes: { notes?: string; reference?: string; utr?: string; bankAccount?: number | null },
): Promise<CustomerReceipt> {
  const { data } = await apiClient.patch(`/payments/receipts/${id}/`, changes);
  return unwrapData<CustomerReceipt>(data);
}

/** Hand back part or all of the unallocated money on a receipt, without voiding it. */
export async function refundAdvance(
  id: number,
  payload: {
    amount: number | string;
    mode: 'CASH' | 'UPI' | 'BANK';
    reason: string;
    refundDate?: string;
    bankAccount?: number;
    utr?: string;
    paidFromTill?: boolean;
  },
  options?: { idempotencyKey?: string },
): Promise<AdvanceRefund> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/refund-advance/`, payload, {
    headers: idempotencyHeaders(options?.idempotencyKey),
  });
  return unwrapData<AdvanceRefund>(data);
}

export async function voidAdvanceRefund(
  id: number,
  reason: string,
  options?: { idempotencyKey?: string },
): Promise<AdvanceRefund> {
  const { data } = await apiClient.post(
    `/payments/advance-refunds/${id}/void/`,
    { reason },
    { headers: idempotencyHeaders(options?.idempotencyKey) },
  );
  return unwrapData<AdvanceRefund>(data);
}

/** Manager: void a cash receipt that was counted in a closed till and record why on that till. */
export async function correctClosedTill(id: number, reason: string): Promise<CustomerReceipt> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/correct-closed-till/`, { reason });
  return unwrapData<CustomerReceipt>(data);
}

/** Move money that landed on the walk-in account to the customer who paid. */
export async function reassignReceiptCustomer(
  id: number,
  payload: { customer: number; reason: string },
): Promise<CustomerReceipt> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/reassign-customer/`, payload);
  return unwrapData<CustomerReceipt>(data);
}

/** Apply several advances oldest-bill-first. One result row per receipt. */
export async function bulkAllocateReceipts(
  ids: number[],
  options: { idempotencyKey: string },
): Promise<BulkAllocateResult[]> {
  const { data } = await apiClient.post(
    '/payments/receipts/bulk-allocate/',
    { ids },
    { headers: idempotencyHeaders(options.idempotencyKey) },
  );
  return unwrapData<{ results: BulkAllocateResult[] }>(data).results;
}

export type ReceiptSendResult = {
  mode: 'cloud' | 'link' | 'device' | string;
  status?: string;
  documentUrl?: string;
  text?: string;
  shareLink?: string;
};

/** Send the receipt voucher to the customer by WhatsApp or email. An empty recipient is a device share. */
export async function sendReceipt(
  id: number,
  payload: { channel: 'whatsapp' | 'email'; recipient?: string },
): Promise<ReceiptSendResult> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/send/`, payload);
  return unwrapData<ReceiptSendResult>(data);
}

/** Same filter keys as listReceiptsPage (`q`, `mode`, `status`, `date_from`, `date_to`). */
export type ReceiptFilterParams = Pick<PageParams, 'q'> & {
  mode?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  /** `true`: matched to a bank line; `false`: not matched. */
  reconciled?: string;
  /** PENDING_CLEARANCE, CLEARED or BOUNCED (cheque receipts only). */
  cheque_status?: string;
  /** `true`: live receipts with money not yet applied to a bill. */
  advance?: string;
  /** Sort column, `-` prefix for descending: receipt_date, amount, number, customer__name, status. */
  ordering?: string;
};

export async function getCustomerReceipt(id: number | string): Promise<CustomerReceipt> {
  const { data } = await apiClient.get(`/payments/receipts/${id}/`);
  return unwrapData<CustomerReceipt>(data);
}

export async function getReceiptsSummary(params?: ReceiptFilterParams): Promise<ReceiptSummary> {
  return withMocks(
    async () => {
      const { data } = await apiClient.get('/payments/receipts/summary/', { params: toQueryParams(params) });
      return unwrapData<ReceiptSummary>(data);
    },
    () => {
      const total = mockReceipts.reduce((sum, row) => sum + Number(row.amount), 0);
      const allocated = mockReceipts.reduce((sum, row) => sum + Number(row.allocated), 0);
      return {
        count: mockReceipts.length,
        collected: total,
        chequesPending: 0,
        allocated,
        advance: Math.max(total - allocated, 0),
        excludedCount: 0,
      };
    },
  );
}

export async function exportReceiptsCsv(params?: ReceiptFilterParams): Promise<Blob> {
  return getBlob('/payments/receipts/export/', toQueryParams(params));
}

export type ReceiptVoucherLayout = 'A4' | 'THERMAL';
export type ReceiptVoucherLang = 'en' | 'hi';

export async function fetchReceiptVoucher(
  id: number,
  layout: ReceiptVoucherLayout = 'A4',
  lang: ReceiptVoucherLang = 'en',
): Promise<Blob> {
  return getBlob(`/payments/receipts/${id}/voucher/`, { layout, lang });
}

export async function setReceiptChequeStatus(id: number, chequeStatus: string): Promise<CustomerReceipt> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/set-cheque-status/`, { chequeStatus });
  return unwrapData<CustomerReceipt>(data);
}

export async function setSupplierPaymentChequeStatus(id: number, chequeStatus: string): Promise<SupplierPayment> {
  const { data } = await apiClient.post(`/payments/supplier-payments/${id}/set-cheque-status/`, { chequeStatus });
  return unwrapData<SupplierPayment>(data);
}

export async function unallocatePayment(id: number, reason?: string): Promise<PaymentAllocation> {
  const { data } = await apiClient.post(
    `/payments/allocations/${id}/unallocate/`,
    reason === undefined ? {} : { reason },
  );
  return unwrapData<PaymentAllocation>(data);
}

export async function listAllocationsPage(
  params?: PageParams & { sales_invoice?: number; purchase_invoice?: number },
): Promise<PageResult<PaymentAllocation>> {
  return fetchPage<PaymentAllocation>('/payments/allocations/', params);
}

export async function createAllocation(
  payload: {
    receipt?: number;
    supplierPayment?: number;
    salesInvoice?: number;
    purchaseInvoice?: number;
    amount: number | string;
  },
  options?: { idempotencyKey?: string },
): Promise<PaymentAllocation> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/allocations/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<PaymentAllocation>(data);
  }, { id: Date.now(), ...payload, amount: payload.amount });
}

export async function listPaymentLinks(params?: Record<string, string>): Promise<import('@/types/domain').PaymentLink[]> {
  return fetchAllPagesMasters<import('@/types/domain').PaymentLink>('/payments/links/', params);
}

export async function listPaymentLinksPage(params?: PageParams): Promise<PageResult<import('@/types/domain').PaymentLink>> {
  return fetchPage<import('@/types/domain').PaymentLink>('/payments/links/', params);
}

export const listAllPaymentLinks = () =>
  withMocks(
    () => fetchAllPagesMasters<import('@/types/domain').PaymentLink>('/payments/links/'),
    mockPaymentLinks,
  );
export const createPaymentLink = (payload: Record<string, unknown>) =>
  apiClient.post('/payments/links/', payload).then(({ data }) => unwrapData<import('@/types/domain').PaymentLink>(data));
export const cancelPaymentLink = (id: number) => apiClient.post(`/payments/links/${id}/cancel/`).then(({ data }) => unwrapData(data));
export const markPaymentLinkSent = (id: number) => apiClient.post(`/payments/links/${id}/mark-sent/`).then(({ data }) => unwrapData(data));
export const sharePaymentLink = (id: number, payload: { channel: string; recipient: string }) =>
  apiClient.post(`/payments/links/${id}/share/`, payload).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const listGatewayPayments = (paymentLink?: number) =>
  fetchAllPagesMasters<Record<string, unknown>>(
    '/payments/gateway-payments/',
    paymentLink ? { payment_link: String(paymentLink) } : undefined,
  );

export async function listGatewayPaymentsPage(
  params?: PageParams & { paymentLink?: number; status?: string },
): Promise<PageResult<Record<string, unknown>>> {
  const { paymentLink, status, ...pageParams } = params ?? {};
  const query = {
    ...pageParams,
    ...(paymentLink != null ? { payment_link: String(paymentLink) } : {}),
    ...(status ? { status } : {}),
  };
  return fetchPage<Record<string, unknown>>('/payments/gateway-payments/', query);
}
export const refundGatewayPayment = (id: number, payload?: { amount?: number; reason?: string }) =>
  apiClient.post(`/payments/gateway-payments/${id}/refund/`, payload ?? {}).then(({ data }) => unwrapData(data));
export const retryGatewayPaymentBooks = (id: number) =>
  apiClient.post(`/payments/gateway-payments/${id}/retry-books/`).then(({ data }) => unwrapData(data));
export interface CustomerRiskRow {
  customerId: number;
  customerName?: string;
  outstanding: number | string;
  overdueAmount: number | string;
  status: string;
  ageing?: Record<string, number | string>;
}

// QOS-0038: company-wide collection risk, for the dashboard "needs attention" card.
export async function listCollectionRisk(): Promise<CustomerRiskRow[]> {
  return withMocks(async () => {
    const { data } = await apiClient.get('/payments/collection-risk/');
    const body = unwrapData<{ results?: Record<string, unknown>[] } | Record<string, unknown>[]>(data);
    const rows = Array.isArray(body) ? body : body?.results ?? [];
    return rows.map((r) => ({
      customerId: Number(r.customer_id ?? r.customerId ?? 0),
      customerName: (r.customer_name ?? r.customerName) as string | undefined,
      outstanding: (r.outstanding as number | string) ?? 0,
      overdueAmount: (r.overdue_amount ?? r.overdueAmount) as number | string ?? 0,
      status: String(r.collection_status ?? r.status ?? ''),
      ageing: (r.ageing as Record<string, number | string> | undefined) ?? undefined,
    }));
  }, mockCollectionRisk);
}

export async function listBankStatements(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  return fetchAllPagesMasters<Record<string, unknown>>('/payments/statements/', params);
}

export async function listBankStatementsPage(params?: PageParams): Promise<PageResult<Record<string, unknown>>> {
  return withMocks(async () => fetchPage<Record<string, unknown>>('/payments/statements/', params), {
    results: mockBankStatements,
    count: mockBankStatements.length,
    next: null,
    previous: null,
  });
}
export const getBankStatement = (id: number) =>
  apiClient.get(`/payments/statements/${id}/`).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const uploadBankStatement = (form: FormData) => apiClient.post('/payments/statements/upload/', form).then(({ data }) => unwrapData(data));
export const commitBankStatement = (id: number) => apiClient.post(`/payments/statements/${id}/commit/`).then(({ data }) => unwrapData(data));
export const listRecon = () =>
  withMocks(
    () =>
      apiClient.get('/payments/recon/').then(({ data }) => {
        const body = unwrapData<{ results?: Record<string, unknown>[] } | Record<string, unknown>[]>(data);
        if (Array.isArray(body)) return body;
        return body?.results ?? [];
      }),
    mockReconLines,
  );
export type ReconReviewItem = {
  match: number;
  line: number;
  lineDate: string;
  lineAmount: string;
  bankAccount: string;
  receipt: number;
  receiptNumber: string;
  customerName: string;
  reason: string;
};
/** Matches whose receipt later bounced: the bank took the money back, so they need another look. */
export const listReconNeedsReview = () =>
  apiClient
    .get('/payments/recon/needs-review/')
    .then(({ data }) => unwrapData<{ results: ReconReviewItem[] }>(data).results);
/** Link the bank's cheque-return debit line to the bounced receipt. */
export const matchReconReturn = (payload: { line: number; receipt: number }) =>
  apiClient.post('/payments/recon/match-return/', payload).then(({ data }) => unwrapData(data));
export const confirmRecon = (payload: Record<string, unknown>) => apiClient.post('/payments/recon/confirm/', payload).then(({ data }) => unwrapData(data));
// QOS-0039: confirm every EXACT-class suggestion on the unmatched queue in one call.
export const bulkAcceptExactMatches = () =>
  apiClient.post('/payments/recon/bulk-accept-exact/').then(({ data }) =>
    unwrapData<{ accepted: { line: number; match: number }[]; accepted_count: number }>(data),
  );
export const unmatchRecon = (line: number) => apiClient.post('/payments/recon/unmatch/', { line }).then(({ data }) => unwrapData(data));
export const createReceiptFromReconLine = (payload: Record<string, unknown>) => apiClient.post('/payments/recon/create-receipt-from-line/', payload).then(({ data }) => unwrapData(data));
export const getGatewaySettings = () => apiClient.get('/payments/gateway-settings/').then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const updateGatewaySettings = (payload: Record<string, unknown>) => apiClient.patch('/payments/gateway-settings/', payload).then(({ data }) => unwrapData(data));
export const getPublicPaymentLink = (token: string) => apiClient.get(`/public/pay/${token}/`).then(({ data }) => unwrapData<Record<string, unknown>>(data));

export function requestCustomerPortalLink(body: { email?: string; phone?: string }) {
  return apiClient.post('/public/customer-portal/request-link/', body).then(({ data }) =>
    unwrapData<{ detail: string; debugToken?: string }>(data),
  );
}

export function getCustomerPortal(token: string) {
  return apiClient.get(`/public/customer-portal/${token}/`).then(({ data }) => unwrapData<{
    customerName: string;
    expiresAt: string;
    complaintsEnabled?: boolean;
    invoices: Array<{
      id: number;
      number: string;
      invoiceDate: string;
      status: string;
      amount: string;
      outstanding: string;
      payPath: string | null;
    }>;
    receipts?: Array<{
      id: number;
      number: string;
      receiptDate: string;
      amount: string;
      mode: string;
    }>;
  }>(data));
}

export function downloadCustomerPortalReceipt(token: string, receiptId: number, lang: 'en' | 'hi' = 'en') {
  return apiClient
    .get(`/public/customer-portal/${token}/receipts/${receiptId}/voucher/`, { params: { lang }, responseType: 'blob' })
    .then(({ data }) => data as Blob);
}

export function downloadCustomerPortalInvoice(token: string, invoiceId: number) {
  return apiClient.get(`/public/customer-portal/${token}/invoices/${invoiceId}/pdf/`, { responseType: 'blob' }).then(({ data }) => data as Blob);
}

export function startCustomerPortalPayment(token: string, invoiceId: number) {
  return apiClient.post(`/public/customer-portal/${token}/invoices/${invoiceId}/pay/`).then(({ data }) => unwrapData<{ payPath: string }>(data));
}

export function submitPortalComplaint(
  token: string,
  body: { description: string; category: string },
  key: string,
) {
  return apiClient.post(
    `/public/customer-portal/${token}/complaints/`,
    body,
    { headers: idempotencyHeaders(key) },
  ).then(({ data }) => unwrapData<{ id: number; number: string }>(data));
}

export const listAccountingBankReconSessions = () =>
  withMocks(
    () => fetchAllPagesMasters<Record<string, unknown>>('/accounting/bank-recon-sessions/'),
    mockAccountingBankReconSessions,
  );
export const createAccountingBankReconSession = (payload: Record<string, unknown>) => apiClient.post('/accounting/bank-recon-sessions/', payload).then(({ data }) => unwrapData(data));
export type ReconSummary = {
  statementDate: string;
  statementClosingBalance: string | null;
  glBalanceAsAt: string;
  reconciledTotal: string;
  outstandingDeposits: string;
  outstandingPayments: string;
  unrecordedBankItems: string;
  adjustedBankBalance: string | null;
  adjustedBookBalance: string;
  difference: string | null;
  statementLines: number;
  matchedLines: number;
  openLines: number;
};
export type ReconSession = {
  id: number;
  account: number;
  accountName: string;
  statement: number;
  statementName: string;
  status: string;
  statementDate: string | null;
  statementClosingBalance: string | null;
  difference: string | null;
  finalisedAt: string | null;
  finalisedByName: string;
  createdAt: string;
  summary: ReconSummary | null;
};
export type ReconStatementLine = { id: number; txnDate: string; narration: string; utr: string; amount: string; matchStatus: string };
export type ReconLedgerLine = { id: number; entryId: number; entryNumber: string; entryDate: string; narration: string; signedAmount: string };
export type ReconSuggestion = {
  bankLine: number;
  journalLine: number;
  score: number;
  dateGap: number;
  sharedWords: string[];
  amount: string;
  confidence: 'high' | 'medium' | 'low';
};
export const listBankReconSessions = (params?: Record<string, string>) =>
  fetchPage<ReconSession>('/accounting/bank-recon-sessions/', { pageSize: 100, ...params });
export const getBankReconSession = (id: number) =>
  apiClient.get(`/accounting/bank-recon-sessions/${id}/`).then(({ data }) => unwrapData<ReconSession>(data));
export const patchBankReconSession = (id: number, payload: Record<string, unknown>) =>
  apiClient.patch(`/accounting/bank-recon-sessions/${id}/`, payload).then(({ data }) => unwrapData<ReconSession>(data));
export const listReconStatementLines = (id: number, params?: PageParams) =>
  fetchPage<ReconStatementLine>(`/accounting/bank-recon-sessions/${id}/statement-lines/`, params);
export const listReconLedgerLines = (id: number, params?: PageParams) =>
  fetchPage<ReconLedgerLine>(`/accounting/bank-recon-sessions/${id}/ledger-lines/`, params);
export const matchManyRecon = (id: number, payload: { journalLines: number[]; bankLines: number[] }) =>
  apiClient.post(`/accounting/bank-recon-sessions/${id}/match-many/`, payload).then(({ data }) => unwrapData(data));
export const unmatchGlRecon = (id: number, bankLine: number) =>
  apiClient.post(`/accounting/bank-recon-sessions/${id}/unmatch/`, { bankLine }).then(({ data }) => unwrapData(data));
export const getReconSuggestions = (id: number) =>
  apiClient.get(`/accounting/bank-recon-sessions/${id}/suggestions/`).then(({ data }) => unwrapData<{ results: ReconSuggestion[] }>(data).results);
export const acceptReconSuggestions = (id: number, payload: { confidence?: string; pairs?: Array<{ bankLine: number; journalLine: number }>; preview?: boolean }) =>
  apiClient.post(`/accounting/bank-recon-sessions/${id}/accept-suggestions/`, payload).then(({ data }) => unwrapData<{ matched?: number; count?: number; failed?: unknown[] }>(data));
export const createReconEntry = (id: number, payload: { bankLine: number; account: number; narration?: string; entryDate?: string }) =>
  apiClient.post(`/accounting/bank-recon-sessions/${id}/create-entry/`, payload).then(({ data }) => unwrapData(data));
export const finaliseRecon = (id: number, writeOff: boolean) =>
  apiClient.post(`/accounting/bank-recon-sessions/${id}/finalise/`, { writeOff }).then(({ data }) => unwrapData<ReconSession>(data));
export const reopenRecon = (id: number, reason: string) =>
  apiClient.post(`/accounting/bank-recon-sessions/${id}/reopen/`, { reason }).then(({ data }) => unwrapData<ReconSession>(data));
export const reconReportFile = (id: number, file: 'xlsx' | 'pdf') =>
  getBlob(`/accounting/bank-recon-sessions/${id}/report/`, { file });
export const matchAccountingBankRecon = (id: number, payload: Record<string, unknown>) => apiClient.post(`/accounting/bank-recon-sessions/${id}/match/`, payload).then(({ data }) => unwrapData(data));

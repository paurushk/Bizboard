import { apiClient, idempotencyHeaders, unwrapData } from '../client';
import { mockReceipts } from '@/mocks/data';
import type { CustomerReceipt, PaymentAllocation } from '@/types/domain';
import { withMocks, fetchPage, fetchMoneyListFirstPage, fetchAllPagesMasters, type PageResult, type PageParams } from './common';

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
  },
  options?: { idempotencyKey?: string },
): Promise<CustomerReceipt> {
  return withMocks(async () => {
    const { data } = await apiClient.post('/payments/receipts/', payload, {
      headers: idempotencyHeaders(options?.idempotencyKey),
    });
    return unwrapData<CustomerReceipt>(data);
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

export async function voidReceipt(id: number, reason = ''): Promise<CustomerReceipt> {
  const { data } = await apiClient.post(`/payments/receipts/${id}/void/`, reason ? { reason } : {});
  return unwrapData<CustomerReceipt>(data);
}

export async function unallocatePayment(id: number): Promise<PaymentAllocation> {
  const { data } = await apiClient.post(`/payments/allocations/${id}/unallocate/`, {});
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
  return fetchMoneyListFirstPage<import('@/types/domain').PaymentLink>('/payments/links/', params);
}

export async function listPaymentLinksPage(params?: PageParams): Promise<PageResult<import('@/types/domain').PaymentLink>> {
  return fetchPage<import('@/types/domain').PaymentLink>('/payments/links/', params);
}

export const listAllPaymentLinks = () =>
  fetchAllPagesMasters<import('@/types/domain').PaymentLink>('/payments/links/');
export const createPaymentLink = (payload: Record<string, unknown>) =>
  apiClient.post('/payments/links/', payload).then(({ data }) => unwrapData<import('@/types/domain').PaymentLink>(data));
export const cancelPaymentLink = (id: number) => apiClient.post(`/payments/links/${id}/cancel/`).then(({ data }) => unwrapData(data));
export const markPaymentLinkSent = (id: number) => apiClient.post(`/payments/links/${id}/mark-sent/`).then(({ data }) => unwrapData(data));
export const sharePaymentLink = (id: number, payload: { channel: string; recipient: string }) =>
  apiClient.post(`/payments/links/${id}/share/`, payload).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const listGatewayPayments = (paymentLink?: number) =>
  fetchMoneyListFirstPage<Record<string, unknown>>(
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
export async function listBankStatements(params?: Record<string, string>): Promise<Record<string, unknown>[]> {
  return fetchMoneyListFirstPage<Record<string, unknown>>('/payments/statements/', params);
}

export async function listBankStatementsPage(params?: PageParams): Promise<PageResult<Record<string, unknown>>> {
  return fetchPage<Record<string, unknown>>('/payments/statements/', params);
}
export const getBankStatement = (id: number) =>
  apiClient.get(`/payments/statements/${id}/`).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const uploadBankStatement = (form: FormData) => apiClient.post('/payments/statements/upload/', form).then(({ data }) => unwrapData(data));
export const commitBankStatement = (id: number) => apiClient.post(`/payments/statements/${id}/commit/`).then(({ data }) => unwrapData(data));
export const listRecon = () =>
  apiClient.get('/payments/recon/').then(({ data }) => {
    const body = unwrapData<{ results?: Record<string, unknown>[] } | Record<string, unknown>[]>(data);
    if (Array.isArray(body)) return body;
    return body?.results ?? [];
  });
export const confirmRecon = (payload: Record<string, unknown>) => apiClient.post('/payments/recon/confirm/', payload).then(({ data }) => unwrapData(data));
export const createReceiptFromReconLine = (payload: Record<string, unknown>) => apiClient.post('/payments/recon/create-receipt-from-line/', payload).then(({ data }) => unwrapData(data));
export const getGatewaySettings = () => apiClient.get('/payments/gateway-settings/').then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const updateGatewaySettings = (payload: Record<string, unknown>) => apiClient.patch('/payments/gateway-settings/', payload).then(({ data }) => unwrapData(data));
export const getPublicPaymentLink = (token: string) => apiClient.get(`/public/pay/${token}/`).then(({ data }) => unwrapData<Record<string, unknown>>(data));
export const listAccountingBankReconSessions = () =>
  fetchAllPagesMasters<Record<string, unknown>>('/accounting/bank-recon-sessions/');
export const createAccountingBankReconSession = (payload: Record<string, unknown>) => apiClient.post('/accounting/bank-recon-sessions/', payload).then(({ data }) => unwrapData(data));
export const matchAccountingBankRecon = (id: number, payload: Record<string, unknown>) => apiClient.post(`/accounting/bank-recon-sessions/${id}/match/`, payload).then(({ data }) => unwrapData(data));

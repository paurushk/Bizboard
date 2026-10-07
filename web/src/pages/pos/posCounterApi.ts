import { apiClient, unwrapData } from '@/api/client';
import { todayIso } from '@/components/billing';

export interface PosSettings {
  tenderAccounts: Record<string, number>;
  maxLineDiscount: string;
  expiredLotPolicy: 'BLOCK' | 'REASON' | string;
  pinConfigured: boolean;
  walkInCustomerId: number | null;
  periodBlocked?: boolean;
  periodMessage?: string;
  requireOpenShift?: boolean;
  offlineCredit?: boolean;
  returnWindowDays?: number;
  catalogWarnHours?: number;
  catalogBlockHours?: number;
}

export interface PosHoldRow {
  id: number;
  label: string;
  payload: { cart?: unknown[]; at?: number };
}

export interface CashShiftToday {
  shift: {
    id: number;
    status: string;
    openingFloat: string;
    cashDropped: string;
    expectedCash?: string;
    countedCash?: string;
  } | null;
}

export async function getPosSettings(): Promise<PosSettings> {
  const { data } = await apiClient.get('/sales/pos/settings/');
  return unwrapData<PosSettings>(data);
}

export async function postPosEvent(body: {
  kind: 'drawer_open' | 'discount' | 'upi_received' | 'price_change';
  detail?: string;
  invoiceId?: number | string;
}): Promise<void> {
  await apiClient.post('/sales/pos/events/', {
    kind: body.kind,
    detail: body.detail,
    invoice_id: body.invoiceId,
  });
}

export async function listPosHolds(): Promise<PosHoldRow[]> {
  const { data } = await apiClient.get('/plan/pos-holds/');
  const rows = unwrapData<PosHoldRow[]>(data);
  return Array.isArray(rows) ? rows : [];
}

export async function createPosHold(label: string, payload: Record<string, unknown>): Promise<{ id: number }> {
  const { data } = await apiClient.post('/plan/pos-holds/', { label, payload });
  return unwrapData<{ id: number }>(data);
}

export async function releasePosHold(id: string | number): Promise<void> {
  await apiClient.delete('/plan/pos-holds/', { params: { id } });
}

export async function printShiftSummary(shiftId: number): Promise<void> {
  const { data } = await apiClient.get(`/accounting/cash-shifts/${shiftId}/summary/`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(data as Blob);
  window.open(url, '_blank', 'noopener');
}

export async function getTodayShift(terminalId?: string): Promise<CashShiftToday> {
  const { data } = await apiClient.get('/accounting/cash-shifts/today/', {
    params: terminalId ? { terminal_id: terminalId } : undefined,
  });
  return unwrapData<CashShiftToday>(data);
}

export async function openTodayShift(openingFloat: string, terminal?: { id: string; label: string }): Promise<void> {
  const businessDate = todayIso();
  await apiClient.post('/accounting/cash-shifts/', {
    opening_float: openingFloat,
    business_date: businessDate,
    terminal_id: terminal?.id,
    terminal_label: terminal?.label,
  });
}

export async function dropShiftCash(id: number, amount: string): Promise<void> {
  await apiClient.post(`/accounting/cash-shifts/${id}/drop/`, { amount });
}

export async function closeTodayShift(
  id: number,
  denominations: Record<string, number>,
): Promise<{ expectedCash?: string; countedCash?: string; variance?: string; status?: string }> {
  const { data } = await apiClient.post(`/accounting/cash-shifts/${id}/close/`, { denominations });
  return unwrapData(data);
}

export async function collectPosPayment(body: {
  invoice: number;
  mode: string;
  amount: number | string;
  reference?: string;
  notes?: string;
}): Promise<void> {
  await apiClient.post('/sales/pos/collect/', body);
}

export async function returnPosBill(body: {
  invoice: number;
  exchange?: boolean;
  reason?: string;
  ownerPin?: string;
  refundMode?: 'CASH' | 'BANK' | 'ADVANCE' | 'SPLIT';
  lines?: Array<{ source_item: number; quantity: string }>;
}): Promise<{ id: number; number?: string; exchange: boolean; customerId: number }> {
  const { data } = await apiClient.post('/sales/pos/return/', {
    invoice: body.invoice,
    exchange: body.exchange ? true : undefined,
    reason: body.reason,
    owner_pin: body.ownerPin || undefined,
    refund_mode: body.refundMode,
    lines: body.lines,
  });
  return unwrapData(data);
}

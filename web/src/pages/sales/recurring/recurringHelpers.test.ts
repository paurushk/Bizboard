import { describe, expect, it } from 'vitest';
import type { RecurringRunNowResult, RecurringSchedule } from '@/api/legacy/sales';
import {
  buildPayload,
  emptyForm,
  formFromSchedule,
  formIsValid,
  fromLocalInput,
  newLine,
  runDocumentRoute,
  runOutcome,
  toLocalInput,
} from './recurringHelpers';

function schedule(over: Partial<RecurringSchedule> = {}): RecurringSchedule {
  return {
    id: 5,
    customer: 7,
    customerName: 'Ravi',
    customerStatus: 'ACTIVE',
    companyGstin: null,
    cadence: 'MONTHLY',
    nextRunAt: '2027-01-31T04:30:20Z',
    isActive: true,
    lineTemplate: { items: [{ product: 3, quantity: 2, unitPrice: 100 }] },
    notes: 'hello',
    stopStage: 'INVOICE',
    autoComplete: false,
    additionalCharges: '0.00',
    invoiceDiscount: '0.00',
    invoiceDiscountMode: 'AFTER_TAX',
    priceMode: 'EXCLUSIVE',
    endDate: null,
    maxOccurrences: null,
    totalRunsCount: 0,
    lastError: '',
    anchorDay: 31,
    pausedReason: '',
    managedByContract: null,
    hasRuns: false,
    nextFutureRunAt: '2027-01-31T04:30:20Z',
    ...over,
  };
}

function runResult(over: Partial<RecurringRunNowResult> = {}): RecurringRunNowResult {
  return {
    ok: true,
    runId: 1,
    invoiceId: 11,
    salesOrderId: null,
    deliveryChallanId: null,
    stopStage: 'INVOICE',
    periodKey: '2026-10',
    status: 'DRAFT',
    documentNumber: null,
    alreadyExisted: false,
    completionError: '',
    ...over,
  };
}

describe('recurring payloads', () => {
  it('keeps the next run out of an edit that did not change it, so the anchor day is not reset', () => {
    const original = schedule();
    const form = formFromSchedule(original);
    const payload = buildPayload(form, original);
    expect('nextRunAt' in payload).toBe(false);
    expect(payload.lineTemplate).toEqual({ items: [{ product: 3, quantity: 2, unitPrice: 100 }] });

    const changed = buildPayload({ ...form, nextRunAt: '2027-03-31T10:00' }, original);
    expect(changed.nextRunAt).toBe(fromLocalInput('2027-03-31T10:00'));
  });

  it('sends only the fields a contract-managed schedule allows', () => {
    const original = schedule({ managedByContract: { id: 1, number: 'CON-1' } });
    const form = { ...formFromSchedule(original), cadence: 'WEEKLY', autoComplete: true, notes: 'n' };
    expect(buildPayload(form, original)).toEqual({ autoComplete: true, notes: 'n' });
  });

  it('creates active, with null term fields when blank, and never auto-completes an order stage', () => {
    const form = {
      ...emptyForm(),
      customerId: 7,
      nextRunAt: '2027-01-05T09:00',
      stopStage: 'SALES_ORDER',
      autoComplete: true,
      lines: [newLine({ productId: 3, qty: '2', price: '' })],
    };
    const payload = buildPayload(form, null);
    expect(payload).toMatchObject({
      customer: 7,
      isActive: true,
      autoComplete: false,
      endDate: null,
      maxOccurrences: null,
      lineTemplate: { items: [{ product: 3, quantity: 2, unitPrice: undefined }] },
    });
  });

  it('validates the form', () => {
    const ok = { ...emptyForm(), customerId: 1, nextRunAt: '2027-01-05T09:00', lines: [newLine({ productId: 2 })] };
    expect(formIsValid(ok)).toBe(true);
    expect(formIsValid({ ...ok, customerId: null })).toBe(false);
    expect(formIsValid({ ...ok, lines: [newLine()] })).toBe(false);
    expect(formIsValid({ ...ok, maxRuns: '0' })).toBe(false);
    expect(formIsValid({ ...ok, lines: [newLine({ productId: 2, price: '-1' })] })).toBe(false);
  });

  it('round-trips a local date-time', () => {
    const local = toLocalInput(fromLocalInput('2027-05-06T07:08'));
    expect(local).toBe('2027-05-06T07:08');
  });
});

describe('run outcome', () => {
  it('links a draft invoice', () => {
    const out = runOutcome(runResult());
    expect(out.severity).toBe('success');
    expect(out.to).toBe('/sales/history/11');
  });

  it('says completed when auto-complete finished the invoice', () => {
    const out = runOutcome(runResult({ status: 'COMPLETED', documentNumber: 'INV-9' }));
    expect(out.text).toContain('INV-9');
    expect(out.text.toLowerCase()).toContain('completed');
  });

  it('warns when completion failed and the invoice was left as a draft', () => {
    const out = runOutcome(runResult({ completionError: 'credit limit' }));
    expect(out.severity).toBe('warning');
    expect(out.text).toContain('credit limit');
  });

  it('reports an already generated period as information, not success', () => {
    expect(runOutcome(runResult({ alreadyExisted: true })).severity).toBe('info');
  });

  it('points order and challan stages at their own pages', () => {
    expect(runOutcome(runResult({ invoiceId: null, salesOrderId: 4 })).to).toBe('/sales/orders/4');
    expect(runOutcome(runResult({ invoiceId: null, deliveryChallanId: 4 })).to).toBe('/sales/delivery-challans/4');
  });

  it('routes history rows to their documents', () => {
    const base = { id: 1, periodKey: 'p', createdAt: '', isManual: false, completionError: '', documentNumber: null, status: 'DRAFT', einvoiceStatus: null };
    expect(runDocumentRoute({ ...base, documentType: 'invoice', documentId: 3 })).toBe('/sales/history/3');
    expect(runDocumentRoute({ ...base, documentType: 'sales_order', documentId: 6 })).toBe('/sales/orders/6');
    expect(runDocumentRoute({ ...base, documentType: null, documentId: null })).toBeNull();
  });
});

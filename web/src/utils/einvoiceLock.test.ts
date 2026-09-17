import { describe, expect, it } from 'vitest';
import { canEditInvoiceLines, hasLiveIrn } from '@/utils/einvoiceLock';

describe('hasLiveIrn — CFT-116', () => {
  it('treats GENERATED and MANUAL_IRN as live', () => {
    expect(hasLiveIrn({ einvoiceStatus: 'GENERATED', irn: 'abc' })).toBe(true);
    expect(hasLiveIrn({ einvoiceStatus: 'MANUAL_IRN', irn: 'abc' })).toBe(true);
    expect(hasLiveIrn({ einvoiceStatus: 'MANUAL_IRN' })).toBe(true);
  });

  it('treats in-flight statuses as live', () => {
    expect(hasLiveIrn({ einvoiceStatus: 'QUEUED' })).toBe(true);
  });

  it('allows cancelled / failed / none', () => {
    expect(hasLiveIrn({ einvoiceStatus: 'CANCELLED', irn: 'old' })).toBe(false);
    expect(hasLiveIrn({ einvoiceStatus: 'FAILED', irn: 'old' })).toBe(false);
    expect(hasLiveIrn({ einvoiceStatus: 'NONE' })).toBe(false);
    expect(hasLiveIrn({})).toBe(false);
  });

  it('canEditInvoiceLines is false on completed invoices with a live IRN', () => {
    expect(canEditInvoiceLines({ status: 'DRAFT', einvoiceStatus: 'GENERATED', irn: 'x' })).toBe(true);
    expect(canEditInvoiceLines({ status: 'COMPLETED' })).toBe(true);
    expect(canEditInvoiceLines({ status: 'COMPLETED', einvoiceStatus: 'GENERATED', irn: 'x' })).toBe(
      false,
    );
    expect(canEditInvoiceLines({ status: 'CANCELLED' })).toBe(false);
  });
});

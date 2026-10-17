import { describe, expect, it, vi } from 'vitest';
import type { QueryClient } from '@tanstack/react-query';
import type { LineItem } from '@/types/domain';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { registerGlobalConfirm } from '@/utils/confirmBridge';
import { invalidateNoteQueries, invalidatePurchaseNoteQueries } from '@/utils/noteQueries';
import { canIssueNotes } from '@/utils/permissions';
import { noteItemsToSourceLines } from './invoiceSourceLines';

function invoiceLine(id: number, product: number, quantity: number, hsnCode = '8517'): LineItem {
  return { id, product, quantity, unitPrice: 100, gstRate: 18, hsnCode } as unknown as LineItem;
}

describe('noteItemsToSourceLines — NEW-09', () => {
  it('keeps each note line pointed at its own invoice line, not at the note line id', () => {
    const invoiceItems = [invoiceLine(10, 5, 4), invoiceLine(11, 5, 9)];
    const noteItems = [{ id: 900, product: 5, quantity: 2, unitPrice: 100, gstRate: 18, sourceItem: 11 }] as unknown as LineItem[];
    const [line] = noteItemsToSourceLines(noteItems, invoiceItems);
    expect(line.sourceItemId).toBe(11);
    expect(line.lineId).toBe(900);
    // The cap comes from the named invoice line (9), not the last line of the same product.
    expect(line.maxQty).toBe(9);
  });

  it('does not invent a source line when the note line has none', () => {
    const [line] = noteItemsToSourceLines(
      [{ id: 901, product: 5, quantity: 1, unitPrice: 100, gstRate: 18 }] as unknown as LineItem[],
      [invoiceLine(10, 5, 4)],
    );
    expect(line.sourceItemId).toBeUndefined();
    expect(line.maxQty).toBe(4);
  });

  it('carries the HSN so the table can flag a missing one (DEP-05)', () => {
    const [line] = noteItemsToSourceLines(
      [{ id: 902, product: 5, quantity: 1, unitPrice: 1, gstRate: 0, hsnCode: '' }] as unknown as LineItem[],
      [invoiceLine(10, 5, 4)],
    );
    expect(line.hsnCode).toBe('');
  });
});

describe('completeWithConfirms with an in-app prompt — DN-04', () => {
  const needsConfirm = (codes: string[]) => ({
    response: { data: { error: { details: { confirm_codes: codes } } } },
  });

  it('asks once for all pending confirmations and retries with every flag set', async () => {
    const nativeConfirm = vi.spyOn(window, 'confirm');
    const ask = vi.fn(async () => true);
    const complete = vi
      .fn()
      .mockRejectedValueOnce(needsConfirm(['confirm_cn_on_paid_invoice', 'confirm_cn_price_override']))
      .mockResolvedValueOnce('done');
    await expect(completeWithConfirms(complete, {}, ask)).resolves.toBe('done');
    expect(ask).toHaveBeenCalledTimes(1);
    expect(ask.mock.calls[0][0]).toHaveLength(2);
    expect(nativeConfirm).not.toHaveBeenCalled();
    expect(complete).toHaveBeenLastCalledWith({ confirmPaidInvoice: true, confirmPriceOverride: true });
    nativeConfirm.mockRestore();
  });

  it('stops and surfaces the original error when the user says no', async () => {
    const err = needsConfirm(['confirm_additional_debit']);
    const complete = vi.fn().mockRejectedValue(err);
    await expect(completeWithConfirms(complete, {}, async () => false)).rejects.toBe(err);
    expect(complete).toHaveBeenCalledTimes(1);
  });
});

describe('completeWithConfirms with the app-wide dialog — DN-04', () => {
  const needsConfirm = { response: { data: { error: { details: { confirm_codes: ['confirm_no_rcm'] } } } } };

  it('uses the registered dialog for callers that pass none, never window.confirm', async () => {
    const nativeConfirm = vi.spyOn(window, 'confirm');
    const ask = vi.fn(async () => true);
    registerGlobalConfirm(ask);
    try {
      const complete = vi.fn().mockRejectedValueOnce(needsConfirm).mockResolvedValueOnce('ok');
      await expect(completeWithConfirms(complete)).resolves.toBe('ok');
      expect(ask).toHaveBeenCalledTimes(1);
      expect(nativeConfirm).not.toHaveBeenCalled();
    } finally {
      registerGlobalConfirm(null);
      nativeConfirm.mockRestore();
    }
  });

  it('falls back to window.confirm when no dialog is registered', async () => {
    const nativeConfirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const complete = vi.fn().mockRejectedValueOnce(needsConfirm).mockResolvedValueOnce('ok');
    await expect(completeWithConfirms(complete)).resolves.toBe('ok');
    expect(nativeConfirm).toHaveBeenCalledTimes(1);
    nativeConfirm.mockRestore();
  });
});

describe('invalidatePurchaseNoteQueries — DEP-12', () => {
  it('refreshes the purchase note list, bills and supplier money screens', () => {
    const invalidateQueries = vi.fn();
    invalidatePurchaseNoteQueries({ invalidateQueries } as unknown as QueryClient, 'credit');
    const keys = invalidateQueries.mock.calls.map((call) => (call[0] as { queryKey: string[] }).queryKey[0]);
    for (const expected of ['purchase-credit-notes', 'purchases', 'purchase-invoice', 'suppliers', 'supplier-ledger']) {
      expect(keys).toContain(expected);
    }
    expect(keys).not.toContain('purchase-debit-notes');
  });
});

describe('invalidateNoteQueries — CN-12 / DN-11', () => {
  it('refreshes the note list, the invoice, the customer and the money screens', () => {
    const invalidateQueries = vi.fn();
    invalidateNoteQueries({ invalidateQueries } as unknown as QueryClient, 'debit');
    const keys = invalidateQueries.mock.calls.map((call) => (call[0] as { queryKey: string[] }).queryKey[0]);
    for (const expected of [
      'sales-debit-notes', 'sales-invoices', 'sales-invoice', 'customer', 'customer-360', 'receipts', 'invoice-notes',
    ]) {
      expect(keys).toContain(expected);
    }
    expect(keys).not.toContain('sales-credit-notes');
  });
});

describe('canIssueNotes — CN-03 / DN-03', () => {
  const user = (role: string, extra: Record<string, unknown> = {}) =>
    ({ id: 1, email: 'x@x.test', fullName: 'X', role, companyId: 1, ...extra }) as never;

  it('allows owner, accountant, and anyone with the sales flag', () => {
    expect(canIssueNotes(user('OWNER'))).toBe(true);
    expect(canIssueNotes(user('ACCOUNTANT'))).toBe(true);
    expect(canIssueNotes(user('SALES_STAFF', { canCreateSales: true }))).toBe(true);
  });

  it('refuses viewers, unflagged staff, and no user', () => {
    expect(canIssueNotes(user('VIEWER', { canCreateSales: true }))).toBe(false);
    expect(canIssueNotes(user('SALES_STAFF'))).toBe(false);
    expect(canIssueNotes(null)).toBe(false);
  });
});

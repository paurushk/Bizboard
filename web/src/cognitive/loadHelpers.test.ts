import { describe, expect, it } from 'vitest';
import {
  capsForJobTemplate,
  decidePlaceOfSupply,
  fillPurchaseFromProduct,
  invoiceTypeChipKey,
  prefillReturnLines,
  showGodownSelect,
  primaryPostedAction,
  resolveInvoiceType,
  scanShouldStealFocus,
  slaChipModel,
  statutoryChipIds,
  uniqueSameAmountCandidate,
  visibleRowSlice,
} from './loadHelpers';

describe('resolveInvoiceType', () => {
  it('posts GST for a regular company and a GSTIN customer while untouched', () => {
    expect(resolveInvoiceType({
      isEdit: false,
      touched: false,
      registrationType: 'REGULAR',
      customerGstin: '27ABCDE1234F1Z5',
    })).toBe('GST');
  });

  it('posts RETAIL when the customer has no GSTIN', () => {
    expect(resolveInvoiceType({
      isEdit: false,
      touched: false,
      registrationType: 'REGULAR',
      customerGstin: '',
    })).toBe('RETAIL');
  });

  it('does not overwrite a type the user set', () => {
    expect(resolveInvoiceType({
      isEdit: false,
      touched: true,
      registrationType: 'REGULAR',
      customerGstin: '27ABCDE1234F1Z5',
    })).toBeNull();
  });

  it('loads the saved type in edit mode', () => {
    expect(resolveInvoiceType({
      isEdit: true,
      touched: false,
      savedType: 'RETAIL',
      registrationType: 'REGULAR',
      customerGstin: '27ABCDE1234F1Z5',
    })).toBe('RETAIL');
  });

  it('keeps a composition company on the company rule', () => {
    expect(resolveInvoiceType({
      isEdit: false,
      touched: false,
      registrationType: 'COMPOSITION',
      customerGstin: '27ABCDE1234F1Z5',
    })).toBe('NON_GST');
  });
});

describe('uniqueSameAmountCandidate', () => {
  const lineDate = '2026-04-10';

  it('applies the only same-amount candidate inside the date window', () => {
    const only = { id: 1, type: 'receipt', amount: 500, date: '2026-04-12' };
    expect(uniqueSameAmountCandidate(500, lineDate, [
      only,
      { id: 2, type: 'receipt', amount: 80, date: '2026-04-11' },
    ])).toEqual(only);
  });

  it('leaves two same-amount candidates queued', () => {
    expect(uniqueSameAmountCandidate(500, lineDate, [
      { id: 1, type: 'receipt', amount: 500, date: '2026-04-09' },
      { id: 2, type: 'receipt', amount: 500, date: '2026-04-11' },
    ])).toBeNull();
  });
});

describe('decidePlaceOfSupply', () => {
  it('uses the GSTIN state and does not ask when the address is blank', () => {
    expect(decidePlaceOfSupply('27ABCDE1234F1Z5', '')).toEqual({ ask: false, code: '27' });
  });

  it('uses the address state when the GSTIN is empty', () => {
    expect(decidePlaceOfSupply('', '24')).toEqual({ ask: false, code: '24' });
  });

  it('asks when GSTIN and address name different states', () => {
    const decision = decidePlaceOfSupply('27ABCDE1234F1Z5', '24');
    expect(decision.ask).toBe(true);
    if (decision.ask && decision.reason === 'conflict') {
      expect(decision.gstinCode).toBe('27');
      expect(decision.addressCode).toBe('24');
    }
  });

  it('asks when both are empty', () => {
    expect(decidePlaceOfSupply('', '')).toEqual({ ask: true, reason: 'missing' });
  });
});

describe('invoice type chip and godown select', () => {
  it('names a GSTIN bill and a walk-in without changing the enum', () => {
    expect(invoiceTypeChipKey('GST', true)).toBe('cog.billGstinCustomer');
    expect(invoiceTypeChipKey('RETAIL', false)).toBe('cog.billWalkIn');
    expect(invoiceTypeChipKey('NON_GST', false)).toBe('billing.nonGstInvoice');
  });

  it('hides the godown select for one godown and shows it for two or a non-default edit', () => {
    expect(showGodownSelect({ activeCount: 1, isEdit: false, selectedId: 1, defaultId: 1 })).toBe(false);
    expect(showGodownSelect({ activeCount: 2, isEdit: false, selectedId: 1, defaultId: 1 })).toBe(true);
    expect(showGodownSelect({ activeCount: 1, isEdit: true, selectedId: 9, defaultId: 1 })).toBe(true);
    expect(showGodownSelect({ activeCount: 1, isEdit: true, selectedId: 1, defaultId: 1 })).toBe(false);
  });
});

describe('statutoryChipIds', () => {
  it('shows nothing on a plain bill', () => {
    expect(statutoryChipIds({ supplyType: 'B2B' })).toEqual([]);
  });

  it('shows a chip for reverse charge and SEZ', () => {
    expect(statutoryChipIds({ supplyType: 'SEZWP', reverseCharge: true })).toEqual(['supply:SEZWP', 'rcm']);
  });
});

describe('purchase and return helpers', () => {
  it('fills description, HSN, GST, and rate, and keeps a typed rate', () => {
    expect(fillPurchaseFromProduct({
      name: 'Tea',
      description: 'Assam tea',
      hsnCode: '0902',
      gstRate: 5,
      purchasePrice: 40,
    })).toMatchObject({ description: 'Assam tea', hsnCode: '0902', gstRate: 5, unitPrice: 40 });
    expect(fillPurchaseFromProduct({
      name: 'Tea',
      hsnCode: '0902',
      gstRate: 5,
      purchasePrice: 40,
    }, 55).unitPrice).toBe(55);
  });

  it('copies return lines with a blank quantity', () => {
    const lines = prefillReturnLines([{ maxQty: 3, quantity: 3, included: false }]);
    expect(lines[0]).toMatchObject({ included: true, quantity: 0 });
    expect(prefillReturnLines([{ maxQty: 3, quantity: 0 }], true)[0].quantity).toBe(3);
  });
});

describe('access, actions, sla, window, focus', () => {
  it('cashier cannot open financial reports', () => {
    const caps = capsForJobTemplate('cashier');
    expect(caps?.canCreateSales).toBe(true);
    expect(caps?.canViewFinancialReports).toBe(false);
    expect(capsForJobTemplate('custom')).toBeNull();
  });

  it('ranks payment when a balance remains and the user can take it', () => {
    expect(primaryPostedAction({ status: 'COMPLETED', balance: 10, canPay: true })).toBe('pay');
    expect(primaryPostedAction({ status: 'COMPLETED', balance: 10, canPay: false })).toBe('share');
    expect(primaryPostedAction({ status: 'COMPLETED', balance: 0, canPay: true })).toBe('share');
    expect(primaryPostedAction({ status: 'DRAFT', balance: 10, canPay: true })).toBe('complete');
  });

  it('separates a paused clock from a breach', () => {
    const now = Date.parse('2026-04-10T12:00:00Z');
    expect(slaChipModel({
      status: 'WAITING',
      slaDueAt: '2026-04-10T13:00:00Z',
      createdAt: '2026-04-10T10:00:00Z',
      now,
    }).kind).toBe('paused');
    expect(slaChipModel({
      status: 'OPEN',
      slaDueAt: '2026-04-10T11:00:00Z',
      createdAt: '2026-04-10T10:00:00Z',
      now,
    }).kind).toBe('breached');
  });

  it('paints a window of a 5000-row table', () => {
    expect(visibleRowSlice(5000, 100, 20)).toHaveLength(20);
    expect(visibleRowSlice(5000, 100, 20)[0]).toBe(100);
  });

  it('keeps keystrokes in a quantity field', () => {
    expect(scanShouldStealFocus('INPUT', false)).toBe(false);
    expect(scanShouldStealFocus('INPUT', true)).toBe(true);
  });
});

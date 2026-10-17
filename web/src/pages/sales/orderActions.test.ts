import { describe, expect, it } from 'vitest';
import {
  NO_ORDER_ACTIONS,
  isOrderPickableForChallan,
  orderActions,
  orderStatusParam,
} from './orderActions';

const owner = { gatesOn: false, canWrite: true, canCancel: true };

describe('orderActions — one table for the list and the editor (T-2.1, H-05/H-06)', () => {
  it('DRAFT with order checks off: confirm, invoice, challan and cancel', () => {
    expect(orderActions('DRAFT', owner)).toEqual({
      confirm: true,
      createInvoice: true,
      createChallan: true,
      cancel: true,
    });
  });

  it('DRAFT with order checks on: must confirm first, so no invoice or challan', () => {
    expect(orderActions('DRAFT', { ...owner, gatesOn: true })).toEqual({
      confirm: true,
      createInvoice: false,
      createChallan: false,
      cancel: true,
    });
  });

  it.each([false, true])('CONFIRMED (checks on = %s): invoice, challan and cancel — never a dead end', (gatesOn) => {
    expect(orderActions('CONFIRMED', { ...owner, gatesOn })).toEqual({
      confirm: false,
      createInvoice: true,
      createChallan: true,
      cancel: true,
    });
  });

  it('PARTIALLY_CONVERTED: the remainder can still go out, but the order cannot be cancelled', () => {
    expect(orderActions('PARTIALLY_CONVERTED', owner)).toEqual({
      confirm: false,
      createInvoice: true,
      createChallan: true,
      cancel: false,
    });
  });

  it.each(['CONVERTED', 'CANCELLED', 'SHIPPED', '', undefined, null])('%s offers nothing', (status) => {
    expect(orderActions(status, owner)).toEqual(NO_ORDER_ACTIONS);
  });

  it('a user who cannot create sales gets no create action, and one who cannot cancel gets no cancel', () => {
    const viewer = { gatesOn: false, canWrite: false, canCancel: false };
    for (const status of ['DRAFT', 'CONFIRMED', 'PARTIALLY_CONVERTED']) {
      expect(orderActions(status, viewer)).toEqual(NO_ORDER_ACTIONS);
    }
    const noCancel = orderActions('CONFIRMED', { gatesOn: true, canWrite: true, canCancel: false });
    expect(noCancel.cancel).toBe(false);
    expect(noCancel.createInvoice).toBe(true);
  });
});

describe('orderStatusParam — the Open and Closed filters', () => {
  it('Open means every order with something left to do', () => {
    expect(orderStatusParam('OPEN')).toBe('DRAFT,CONFIRMED,PARTIALLY_CONVERTED');
  });

  it('Closed means converted or cancelled (an order is never "COMPLETED")', () => {
    expect(orderStatusParam('CLOSED')).toBe('CONVERTED,CANCELLED');
  });

  it('passes a plain status through and treats empty as all', () => {
    expect(orderStatusParam('CONFIRMED')).toBe('CONFIRMED');
    expect(orderStatusParam('')).toBeUndefined();
    expect(orderStatusParam(undefined)).toBeUndefined();
  });
});

describe('the challan editor picker offers only orders that can go out', () => {
  it('a confirmed or partly processed order can be linked to a challan; a draft only with order checks off', () => {
    expect(isOrderPickableForChallan('CONFIRMED', true)).toBe(true);
    expect(isOrderPickableForChallan('PARTIALLY_CONVERTED', true)).toBe(true);
    expect(isOrderPickableForChallan('DRAFT', false)).toBe(true);
    expect(isOrderPickableForChallan('DRAFT', true)).toBe(false);
    expect(isOrderPickableForChallan('CONVERTED', false)).toBe(false);
    expect(isOrderPickableForChallan('CANCELLED', false)).toBe(false);
    expect(isOrderPickableForChallan(undefined, false)).toBe(false);
  });
});

import axios from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { completeWithConfirms } from './completeWithConfirms';
import { registerGlobalReason } from './confirmBridge';
import { withGstinHoldOverride } from './overrideRetry';

function apiError(code: string, details: Record<string, unknown> = {}) {
  const err = new axios.AxiosError('Request failed');
  err.response = {
    status: 400,
    data: { success: false, error: { code, message: 'blocked', details } },
  } as never;
  return err;
}

describe('owner overrides during Complete (B-01 / B-02)', () => {
  afterEach(() => {
    registerGlobalReason(null);
    vi.restoreAllMocks();
  });

  it('asks for a reason on a 3-way mismatch and retries with the override', async () => {
    const ask = vi.fn().mockResolvedValue('Supplier agreed a rate rise');
    registerGlobalReason(ask);
    const complete = vi
      .fn()
      .mockRejectedValueOnce(apiError('THREE_WAY_MATCH_FAILED', { breaches: ['product 4: rate differs'], canOverride: true }))
      .mockResolvedValueOnce({ ok: true });

    await expect(completeWithConfirms(complete)).resolves.toEqual({ ok: true });
    expect(ask).toHaveBeenCalledTimes(1);
    expect(ask.mock.calls[0][0].body).toContain('product 4: rate differs');
    expect(complete.mock.calls[1][0]).toMatchObject({
      confirmThreeWayOverride: true,
      threeWayReason: 'Supplier agreed a rate rise',
    });
  });

  it('does not offer the override to a role that cannot give it', async () => {
    const ask = vi.fn();
    registerGlobalReason(ask);
    const complete = vi.fn().mockRejectedValue(apiError('THREE_WAY_MATCH_FAILED', { breaches: ['x'], canOverride: false }));
    await expect(completeWithConfirms(complete)).rejects.toThrow(/Owner or Manager/);
    expect(ask).not.toHaveBeenCalled();
    expect(complete).toHaveBeenCalledTimes(1);
  });

  it('releases a cancelled-GSTIN block with a reason', async () => {
    const ask = vi.fn().mockResolvedValue('Supplier re-registered, certificate attached');
    registerGlobalReason(ask);
    const complete = vi
      .fn()
      .mockRejectedValueOnce(apiError('SUPPLIER_GSTIN_CANCELLED', { supplierName: 'Acme', cancelledOn: '2026-04-01' }))
      .mockResolvedValueOnce({ ok: true });
    await expect(completeWithConfirms(complete)).resolves.toEqual({ ok: true });
    expect(ask.mock.calls[0][0].body).toContain('Acme');
    expect(complete.mock.calls[1][0]).toMatchObject({
      gstinCancelOverride: true,
      gstinCancelReason: 'Supplier re-registered, certificate attached',
    });
  });

  it('leaves the bill alone when the reason dialog is dismissed', async () => {
    registerGlobalReason(vi.fn().mockResolvedValue(null));
    const complete = vi.fn().mockRejectedValue(apiError('SUPPLIER_GSTIN_CANCELLED'));
    await expect(completeWithConfirms(complete)).rejects.toBeTruthy();
    expect(complete).toHaveBeenCalledTimes(1);
  });

  it('retries a held payment once with the override and reason', async () => {
    registerGlobalReason(vi.fn().mockResolvedValue('Owner approved'));
    const pay = vi
      .fn()
      .mockRejectedValueOnce(apiError('SUPPLIER_GSTIN_CANCELLED', { supplierName: 'Acme', cancelledOn: '2026-04-01' }))
      .mockResolvedValueOnce('paid');
    await expect(withGstinHoldOverride(pay)).resolves.toBe('paid');
    expect(pay.mock.calls[0][0]).toEqual({});
    expect(pay.mock.calls[1][0]).toEqual({ gstinHoldOverride: true, gstinHoldReason: 'Owner approved' });
  });

  it('does not intercept other payment errors', async () => {
    const pay = vi.fn().mockRejectedValue(apiError('business_rule_violation'));
    await expect(withGstinHoldOverride(pay)).rejects.toBeTruthy();
    expect(pay).toHaveBeenCalledTimes(1);
  });
});

// C-13: every confirmation the purchase service can ask for must have an on-screen prompt.
describe('purchase confirm codes', () => {
  const SERVER_CONFIRM_CODES = [
    'place_of_supply_unresolved',
    'confirm_duplicate_bill',
    'confirm_no_rcm',
    'GSTIN_TOTAL_CHANGED',
  ];
  it.each(SERVER_CONFIRM_CODES)('prompts %s in the app dialog', async (code) => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const complete = vi.fn().mockRejectedValueOnce(apiError(code)).mockResolvedValueOnce('ok');
    await expect(completeWithConfirms(complete)).resolves.toBe('ok');
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(confirm.mock.calls[0][0]).not.toMatch(/^billing\./);
  });
});

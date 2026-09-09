import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { completeWithConfirms } from './completeWithConfirms';

function axiosConfirmError(code: string, confirmCodes?: string[]) {
  const err = new axios.AxiosError('Request failed with status code 409');
  err.response = {
    status: 409,
    data: {
      success: false,
      error: {
        code,
        message: 'need confirm',
        details: confirmCodes ? { confirmCodes, code, message: 'need confirm' } : { detail: 'need confirm' },
      },
    },
  } as never;
  return err;
}

describe('completeWithConfirms', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('sets every flag from details.confirm_codes and retries once', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const complete = vi
      .fn()
      .mockRejectedValueOnce(
        axiosConfirmError('confirm_no_rcm', ['confirm_no_rcm', 'confirm_duplicate_bill']),
      )
      .mockResolvedValueOnce({ ok: true });

    await expect(completeWithConfirms(complete)).resolves.toEqual({ ok: true });
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(complete).toHaveBeenCalledTimes(2);
    expect(complete.mock.calls[1][0]).toMatchObject({
      confirmNoRcm: true,
      confirmDuplicateBill: true,
    });
  });

  it('prompts one-at-a-time codes up to len(flagFor)+1', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const complete = vi
      .fn()
      .mockRejectedValueOnce(axiosConfirmError('confirm_no_rcm'))
      .mockRejectedValueOnce(axiosConfirmError('confirm_duplicate_bill'))
      .mockResolvedValueOnce({ ok: true });

    await expect(completeWithConfirms(complete)).resolves.toEqual({ ok: true });
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(complete).toHaveBeenCalledTimes(3);
    expect(complete.mock.calls[2][0]).toMatchObject({
      confirmNoRcm: true,
      confirmDuplicateBill: true,
    });
  });

  it('rethrows when the operator declines', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const err = axiosConfirmError('confirm_additional_debit');
    const complete = vi.fn().mockRejectedValue(err);
    await expect(completeWithConfirms(complete)).rejects.toBe(err);
    expect(complete).toHaveBeenCalledTimes(1);
  });

  it('maps confirm_cn_on_paid_invoice and confirm_cn_price_override (CR-096)', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const complete = vi
      .fn()
      .mockRejectedValueOnce(
        axiosConfirmError('confirm_cn_on_paid_invoice', [
          'confirm_cn_on_paid_invoice',
          'confirm_cn_price_override',
        ]),
      )
      .mockResolvedValueOnce({ ok: true });

    await expect(completeWithConfirms(complete)).resolves.toEqual({ ok: true });
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(complete).toHaveBeenCalledTimes(2);
    expect(complete.mock.calls[1][0]).toMatchObject({
      confirmPaidInvoice: true,
      confirmPriceOverride: true,
    });
  });
});

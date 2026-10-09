import { afterEach, describe, expect, it, vi } from 'vitest';
import { isAllowedPaymentUrl, isAllowedShareUrl, shareOnThisDevice } from '@/utils/safeUrl';

describe('safeUrl', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
  it('allows WhatsApp share hosts', () => {
    expect(isAllowedShareUrl('https://wa.me/919999999999')).toBe(true);
    expect(isAllowedShareUrl('https://wa.me/?text=Hello')).toBe(true);
    expect(isAllowedShareUrl('https://api.whatsapp.com/send?phone=91')).toBe(true);
  });

  it('opens a phone-less wa.me link on desktop and does not call navigator.share', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    const share = vi.fn();
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
      share,
      canShare: () => true,
    });
    await shareOnThisDevice({ text: 'Hello' });
    expect(share).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledWith(
      'https://wa.me/?text=Hello',
      '_blank',
      'noopener,noreferrer',
    );
    open.mockRestore();
  });

  it('shares the already-fetched PDF on a phone, and treats dismiss as success', async () => {
    const file = new File(['%PDF'], 'inv.pdf', { type: 'application/pdf' });
    const share = vi.fn(async () => undefined);
    const canShare = vi.fn((data?: ShareData) => Boolean(data?.files?.length));
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile',
      share,
      canShare,
    });
    await shareOnThisDevice({ text: 'Hello', file });
    expect(share).toHaveBeenCalledWith({ files: [file], text: 'Hello' });

    share.mockRejectedValueOnce(Object.assign(new Error('dismissed'), { name: 'AbortError' }));
    await expect(shareOnThisDevice({ text: 'Hello', file })).resolves.toBeUndefined();
  });

  it('blocks javascript share URLs', () => {
    expect(isAllowedShareUrl('javascript:alert(1)')).toBe(false);
  });

  it('BB-000211: allows Razorpay / UPI payment URLs', () => {
    expect(isAllowedPaymentUrl('https://rzp.io/i/abc')).toBe(true);
    expect(isAllowedPaymentUrl('https://api.razorpay.com/v1/invoices/inv')).toBe(true);
    expect(isAllowedPaymentUrl('upi://pay?pa=shop@upi&am=10')).toBe(true);
    expect(isAllowedPaymentUrl('/pay/token-abc')).toBe(true);
  });

  it('BB-000211: rejects evil payment hosts and javascript', () => {
    expect(isAllowedPaymentUrl('https://evil.com/pay')).toBe(false);
    expect(isAllowedPaymentUrl('javascript:alert(1)')).toBe(false);
    expect(isAllowedPaymentUrl('')).toBe(false);
  });

  // F1-016: the allow/deny boundary cases the review flagged as untested.
  it('allows a .rzp.io subdomain, not just the bare host', () => {
    expect(isAllowedPaymentUrl('https://checkout.rzp.io/pay')).toBe(true);
    expect(isAllowedPaymentUrl('https://notrzp.io/pay')).toBe(false);
  });

  it('rejects a upi: intent whose payee VPA is not plausible', () => {
    expect(isAllowedPaymentUrl('upi://pay?pa=not-a-vpa&am=10')).toBe(false);
    expect(isAllowedPaymentUrl('upi://pay')).toBe(false);
  });

  it('allows http:/localhost/.bizboard.local only in a dev build (DEV=true under vitest)', () => {
    expect(isAllowedPaymentUrl('http://localhost:3000/pay/tok')).toBe(true);
    expect(isAllowedPaymentUrl('http://checkout.bizboard.local/pay')).toBe(true);
    expect(isAllowedShareUrl('http://localhost:3000')).toBe(true);
  });

  it('rejects a newline-obfuscated javascript: scheme (java\\nscript:)', () => {
    // The startsWith('javascript:') prefix check alone would miss this — the
    // URL-parse fallback (WHATWG strips control chars, so this parses to a
    // real "javascript:" protocol) is what actually blocks it.
    expect(isAllowedPaymentUrl('java\nscript:alert(1)')).toBe(false);
    expect(isAllowedShareUrl('java\nscript:alert(1)')).toBe(false);
  });
});

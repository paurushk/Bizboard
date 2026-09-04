import { describe, expect, it } from 'vitest';
import { isAllowedPaymentUrl, isAllowedShareUrl } from '@/utils/safeUrl';

describe('safeUrl', () => {
  it('allows WhatsApp share hosts', () => {
    expect(isAllowedShareUrl('https://wa.me/919999999999')).toBe(true);
    expect(isAllowedShareUrl('https://api.whatsapp.com/send?phone=91')).toBe(true);
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

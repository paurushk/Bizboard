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
});

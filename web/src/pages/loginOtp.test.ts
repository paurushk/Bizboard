import { describe, expect, it } from 'vitest';
import { formatOtpHint, isOtpLoginEnabled } from '@/pages/loginOtp';

describe('loginOtp helpers (BUG-628 / P0-108)', () => {
  it('shows Dev OTP only when DEV and debugCode are both present', () => {
    expect(formatOtpHint({ detail: 'sent', debugCode: '999111' }, true)).toBe('Dev OTP: 999111');
    expect(formatOtpHint({ detail: 'sent', debugCode: '999111' }, false)).toBe('sent');
    expect(formatOtpHint({ detail: 'sent' }, true)).toBe('sent');
  });

  it('hides OTP login in production unless VITE_ENABLE_OTP is set', () => {
    expect(isOtpLoginEnabled(false, undefined)).toBe(false);
    expect(isOtpLoginEnabled(false, 'false')).toBe(false);
    expect(isOtpLoginEnabled(false, 'true')).toBe(true);
    expect(isOtpLoginEnabled(true, undefined)).toBe(true);
  });
});

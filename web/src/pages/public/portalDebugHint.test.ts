import { describe, expect, it } from 'vitest';
import { formatPortalDebugHint } from './portalDebugHint';

describe('formatPortalDebugHint (F1-011, mirrors loginOtp.formatOtpHint)', () => {
  it('shows the dev link only when DEV and debugToken are both present', () => {
    expect(formatPortalDebugHint({ detail: 'sent', debugToken: 'abc123' }, true)).toBe(
      'Dev portal link: /portal/abc123',
    );
    expect(formatPortalDebugHint({ detail: 'sent', debugToken: 'abc123' }, false)).toBeNull();
    expect(formatPortalDebugHint({ detail: 'sent' }, true)).toBeNull();
  });
});

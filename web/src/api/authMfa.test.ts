import { beforeEach, describe, expect, it, vi } from 'vitest';

// F-SEC-02 API layer, with the network faked. The server answers in camelCase (the camel-case
// renderer), so the fakes below use `mfaRequired` / `mfaToken` / `recoveryCodes` like the wire does.
const post = vi.fn();
const get = vi.fn();
vi.mock('./client', () => ({
  shouldUseMocks: () => false,
  apiClient: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
  unwrapData: (x: { data?: unknown }) => (x && typeof x === 'object' && 'data' in x ? x.data : x),
}));

const setAccessToken = vi.fn();
vi.mock('@/auth/session', () => ({
  getStoredUser: vi.fn(),
  setAccessToken: (...a: unknown[]) => setAccessToken(...a),
}));

const ENVELOPE = (data: unknown) => ({ data: { success: true, data } });
const USER = { id: 1, email: 'o@example.test', role: 'OWNER' };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('login() with two-step verification', () => {
  it('throws MfaRequiredError carrying the challenge token instead of a session', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ mfaRequired: true, mfaToken: 'tok-abc', methods: ['totp'] }));
    const { login, MfaRequiredError } = await import('./auth');
    const err = await login({ email: 'o@example.test', password: 'pw' }).catch((e) => e);
    expect(err).toBeInstanceOf(MfaRequiredError);
    expect((err as InstanceType<typeof MfaRequiredError>).mfaToken).toBe('tok-abc');
    // no session was established and no profile was fetched with a token that does not exist
    expect(setAccessToken).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });

  it('throws MfaEnrollmentRequiredError and does not start a session', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ mfaEnrollmentRequired: true, enrolToken: 'enrol-1', expiresIn: 600 }));
    const { login, MfaEnrollmentRequiredError } = await import('./auth');
    const err = await login({ email: 'o@example.test', password: 'pw' }).catch((e) => e);
    expect(err).toBeInstanceOf(MfaEnrollmentRequiredError);
    expect((err as InstanceType<typeof MfaEnrollmentRequiredError>).enrolToken).toBe('enrol-1');
    expect(setAccessToken).not.toHaveBeenCalled();
  });

  it('still returns the user and tokens when there is no second factor', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ user: USER, access: 'a1' }));
    const { login } = await import('./auth');
    const res = await login({ email: 'o@example.test', password: 'pw' });
    expect(res.user.email).toBe('o@example.test');
    expect(res.tokens.access).toBe('a1');
  });

  it('a flag without a token is not treated as a challenge (cannot strand the user)', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ mfaRequired: true, user: USER, access: 'a1' }));
    const { login } = await import('./auth');
    await expect(login({ email: 'o@example.test', password: 'pw' })).resolves.toBeTruthy();
  });
});

describe('verifyOtp() with two-step verification', () => {
  it('also hands back a challenge instead of a session', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ mfaRequired: true, mfaToken: 'tok-otp' }));
    const { verifyOtp, MfaRequiredError } = await import('./auth');
    const err = await verifyOtp('+919999999999', '123456').catch((e) => e);
    expect(err).toBeInstanceOf(MfaRequiredError);
    expect(setAccessToken).not.toHaveBeenCalled();
  });
});

describe('verifyMfaLogin()', () => {
  it('posts the challenge token with a code and returns the session', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ user: USER, access: 'a2' }));
    const { verifyMfaLogin } = await import('./auth');
    const res = await verifyMfaLogin('tok-abc', { code: '123456' });
    expect(post).toHaveBeenCalledWith('/auth/mfa/verify/', {
      mfaToken: 'tok-abc',
      code: '123456',
      recoveryCode: undefined,
    });
    expect(res.user.id).toBe(1);
    expect(setAccessToken).toHaveBeenCalledWith('a2');
  });

  it('sends a recovery code under recoveryCode, not code', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ user: USER, access: 'a3' }));
    const { verifyMfaLogin } = await import('./auth');
    await verifyMfaLogin('tok-abc', { recoveryCode: 'ABCDE-FGHJK' });
    expect(post).toHaveBeenCalledWith('/auth/mfa/verify/', {
      mfaToken: 'tok-abc',
      code: undefined,
      recoveryCode: 'ABCDE-FGHJK',
    });
  });

  it('in cookie mode (access: null) uses the cookie marker and the returned profile', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ user: USER, access: null }));
    const { verifyMfaLogin } = await import('./auth');
    const res = await verifyMfaLogin('tok-abc', { code: '000000' });
    expect(res.tokens.access).toBe('cookie');
    expect(res.user.email).toBe('o@example.test');
  });

  it('propagates a wrong-code failure so the page can show it', async () => {
    post.mockRejectedValueOnce(Object.assign(new Error('401'), { response: { status: 401 } }));
    const { verifyMfaLogin } = await import('./auth');
    await expect(verifyMfaLogin('tok-abc', { code: '111111' })).rejects.toMatchObject({
      response: { status: 401 },
    });
  });
});

describe('MFA management calls', () => {
  it('getMfaStatus reads the status envelope', async () => {
    get.mockResolvedValueOnce(ENVELOPE({ enabled: true, pendingSetup: false, recoveryCodesRemaining: 9 }));
    const { getMfaStatus } = await import('./auth');
    expect(await getMfaStatus()).toEqual({ enabled: true, pendingSetup: false, recoveryCodesRemaining: 9 });
    expect(get).toHaveBeenCalledWith('/auth/mfa/status/');
  });

  it('startMfaSetup returns the secret, uri and QR', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ secret: 'ABC', otpauthUri: 'otpauth://x', qrPng: 'data:image/png;base64,AA' }));
    const { startMfaSetup } = await import('./auth');
    const res = await startMfaSetup();
    expect(res.secret).toBe('ABC');
    expect(post).toHaveBeenCalledWith('/auth/mfa/setup/', {});
  });

  it('confirmMfa returns the one-time recovery codes', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ enabled: true, recoveryCodes: ['AAAAA-BBBBB'] }));
    const { confirmMfa } = await import('./auth');
    expect(await confirmMfa('123456')).toEqual(['AAAAA-BBBBB']);
    expect(post).toHaveBeenCalledWith('/auth/mfa/confirm/', { code: '123456' });
  });

  it('disableMfa sends the password with the code', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ enabled: false }));
    const { disableMfa } = await import('./auth');
    await disableMfa('pw', { code: '654321' });
    expect(post).toHaveBeenCalledWith('/auth/mfa/disable/', { password: 'pw', code: '654321', recoveryCode: undefined });
  });

  it('regenerateMfaRecoveryCodes returns a fresh set', async () => {
    post.mockResolvedValueOnce(ENVELOPE({ recoveryCodes: ['CCCCC-DDDDD'] }));
    const { regenerateMfaRecoveryCodes } = await import('./auth');
    expect(await regenerateMfaRecoveryCodes('pw', '654321')).toEqual(['CCCCC-DDDDD']);
    expect(post).toHaveBeenCalledWith('/auth/mfa/recovery-codes/', { password: 'pw', code: '654321' });
  });
});

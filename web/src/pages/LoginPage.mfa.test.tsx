import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MfaEnrollmentRequiredError, MfaRequiredError } from '@/api/auth';
import { setLocale, t } from '@/i18n';
import { LoginPage } from '@/pages/LoginPage';

const auth = vi.hoisted(() => ({
  login: vi.fn(),
  loginWithOtp: vi.fn(),
  completeMfaLogin: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    login: auth.login,
    loginWithOtp: auth.loginWithOtp,
    completeMfaLogin: auth.completeMfaLogin,
    isAuthenticated: false,
  }),
}));

const mfaApi = vi.hoisted(() => ({
  startMfaSetup: vi.fn(),
  confirmMfa: vi.fn(),
}));

vi.mock('@/api/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/auth')>();
  return { ...actual, startMfaSetup: mfaApi.startMfaSetup, confirmMfa: mfaApi.confirmMfa };
});

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function signInWithPassword() {
  await userEvent.type(screen.getByLabelText(/email/i), 'owner@example.test');
  await userEvent.type(screen.getByLabelText(/^password/i), 'Secret123!');
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
}

describe('LoginPage two-step verification', () => {
  beforeEach(() => {
    auth.login.mockReset();
    auth.loginWithOtp.mockReset();
    auth.completeMfaLogin.mockReset();
  });

  it('goes straight home when the account has no second factor', async () => {
    auth.login.mockResolvedValue(undefined);
    renderLogin();
    await signInWithPassword();
    expect(await screen.findByText('home')).toBeTruthy();
    expect(screen.queryByText(/two-step verification/i)).toBeNull();
  });

  it('shows the code step instead of an error when the server asks for a second factor', async () => {
    auth.login.mockRejectedValue(new MfaRequiredError('tok-123'));
    renderLogin();
    await signInWithPassword();
    expect(await screen.findByText(/enter the 6-digit code/i)).toBeTruthy();
    expect(screen.getByLabelText(/authentication code/i)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    // the password form is gone, so the password is not retyped or resubmitted
    expect(screen.queryByLabelText(/^password/i)).toBeNull();
  });

  it('submits the code with the challenge token and then navigates home', async () => {
    auth.login.mockRejectedValue(new MfaRequiredError('tok-123'));
    auth.completeMfaLogin.mockResolvedValue(undefined);
    renderLogin();
    await signInWithPassword();
    await userEvent.type(await screen.findByLabelText(/authentication code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /verify and sign in/i }));
    await waitFor(() => expect(auth.completeMfaLogin).toHaveBeenCalledWith('tok-123', { code: '123456' }));
    expect(await screen.findByText('home')).toBeTruthy();
  });

  it('sends a recovery code as recoveryCode, not code', async () => {
    auth.login.mockRejectedValue(new MfaRequiredError('tok-123'));
    auth.completeMfaLogin.mockResolvedValue(undefined);
    renderLogin();
    await signInWithPassword();
    await userEvent.click(await screen.findByRole('button', { name: /use a recovery code instead/i }));
    await userEvent.type(screen.getByLabelText(/recovery code/i), 'ABCDE-FGHJK');
    await userEvent.click(screen.getByRole('button', { name: /verify and sign in/i }));
    await waitFor(() =>
      expect(auth.completeMfaLogin).toHaveBeenCalledWith('tok-123', { recoveryCode: 'ABCDE-FGHJK' }),
    );
  });

  it('keeps the user on the code step with a clear message after a wrong code (401)', async () => {
    auth.login.mockRejectedValue(new MfaRequiredError('tok-123'));
    auth.completeMfaLogin.mockRejectedValue({ response: { status: 401 }, isAxiosError: true });
    renderLogin();
    await signInWithPassword();
    await userEvent.type(await screen.findByLabelText(/authentication code/i), '000000');
    await userEvent.click(screen.getByRole('button', { name: /verify and sign in/i }));
    expect(await screen.findByText(/that code did not work/i)).toBeTruthy();
    expect(screen.getByLabelText(/authentication code/i)).toBeTruthy();
  });

  it('lets the user go back to the password form', async () => {
    auth.login.mockRejectedValue(new MfaRequiredError('tok-123'));
    renderLogin();
    await signInWithPassword();
    await userEvent.click(await screen.findByRole('button', { name: /back to sign in/i }));
    expect(await screen.findByLabelText(/^password/i)).toBeTruthy();
  });

  it('opens enrolment when the server requires it and does not show an error', async () => {
    auth.login.mockRejectedValue(new MfaEnrollmentRequiredError('enrol-1'));
    renderLogin();
    await signInWithPassword();
    expect(await screen.findByText(/set up two-step verification/i)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByLabelText(/^password/i)).toBeNull();
  });

  it('ONB-CR-003: forced enrolment shows the QR, then brings the sign-in form back', async () => {
    auth.login.mockRejectedValue(new MfaEnrollmentRequiredError('enrol-1'));
    mfaApi.startMfaSetup.mockResolvedValue({
      secret: 'KEY123',
      otpauthUri: 'otpauth://x',
      qrPng: 'data:image/png;base64,AAA',
    });
    mfaApi.confirmMfa.mockResolvedValue(['AAAAA-11111', 'BBBBB-22222']);
    const { container } = renderLogin();
    await signInWithPassword();
    await userEvent.click(await screen.findByRole('button', { name: t('auth.mfa.enable') }));
    await waitFor(() => expect(mfaApi.startMfaSetup).toHaveBeenCalledWith('enrol-1'));
    expect(container.querySelector('img[src="data:image/png;base64,AAA"]')).not.toBeNull();
    await userEvent.type(screen.getByLabelText(t('auth.mfa.enterCode')), '123456');
    await userEvent.click(screen.getByRole('button', { name: t('auth.mfa.confirm') }));
    expect(await screen.findByText('AAAAA-11111')).toBeTruthy();
    // codes on screen: the sign-in form stays hidden until they are acknowledged
    expect(screen.queryByLabelText(/^password/i)).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: t('auth.mfa.recoveryDone') }));
    expect(screen.getByText(t('auth.mfa.enrolDone'))).toBeTruthy();
    expect(await screen.findByLabelText(/^password/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy();
  });

  it('a genuine login failure still shows an error, not the code step', async () => {
    auth.login.mockRejectedValue(new Error('Invalid credentials'));
    renderLogin();
    await signInWithPassword();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByLabelText(/authentication code/i)).toBeNull();
  });
});

describe('LoginPage Hindi validation', () => {
  beforeEach(() => {
    auth.login.mockReset();
    auth.loginWithOtp.mockReset();
    auth.completeMfaLogin.mockReset();
  });
  afterEach(() => setLocale('en'));

  it('shows the Hindi email message when the address is not an email', async () => {
    setLocale('hi');
    renderLogin();
    await userEvent.type(screen.getByLabelText(t('auth.email')), 'not-an-email');
    await userEvent.type(screen.getByLabelText(t('auth.password')), 'Secret123!');
    await userEvent.click(screen.getByRole('button', { name: t('auth.login') }));
    expect(await screen.findByText(t('cog.validEmail'))).toBeTruthy();
    expect(auth.login).not.toHaveBeenCalled();
  });

  it('shows Hindi phone and OTP messages on the mobile tab', async () => {
    setLocale('hi');
    renderLogin();
    await userEvent.click(screen.getByRole('tab', { name: t('auth.otpLogin') }));
    await userEvent.type(screen.getByLabelText(t('auth.phone')), '123');
    await userEvent.type(screen.getByLabelText(t('auth.otp')), '12');
    await userEvent.click(screen.getByRole('button', { name: t('auth.verifyOtp') }));
    expect(await screen.findByText(t('cog.validPhone'))).toBeTruthy();
    expect(screen.getByText(t('cog.enterOtp'))).toBeTruthy();
    expect(auth.loginWithOtp).not.toHaveBeenCalled();
  });
});

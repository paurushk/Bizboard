import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { RegisterPage } from '@/pages/RegisterPage';

const registerMock = vi.fn();

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    register: registerMock,
    isAuthenticated: false,
  }),
}));

describe('RegisterPage Hindi validation', () => {
  afterEach(() => setLocale('en'));

  it('shows Hindi messages for company, email, state, and the emailed code', async () => {
    setLocale('hi');
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText(t('auth.email')), 'not-an-email');
    await userEvent.type(screen.getByLabelText(t('auth.verificationCode')), '12');
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(await screen.findByText(t('auth.companyRequired'))).toBeTruthy();
    expect(screen.getByText(t('cog.validEmail'))).toBeTruthy();
    expect(screen.getByText(t('auth.stateRequired'))).toBeTruthy();
    expect(screen.getByText(t('auth.emailCode'))).toBeTruthy();
  });
});

describe('RegisterPage mobile number', () => {
  afterEach(() => registerMock.mockReset());

  const fillRequired = async () => {
    await userEvent.type(screen.getByLabelText(t('auth.companyName')), 'Shri Krishna Enterprises');
    await userEvent.type(screen.getByLabelText(t('auth.email')), 'owner@example.com');
    await userEvent.type(screen.getByLabelText(t('auth.verificationCode')), '123456');
    await userEvent.type(screen.getByLabelText(t('auth.password')), 'long-enough-1');
    await userEvent.click(screen.getByLabelText(t('auth.state')));
    await userEvent.click(await screen.findByRole('option', { name: 'Uttar Pradesh' }));
    await userEvent.click(screen.getByRole('checkbox'));
  };

  it('sends +91 with the 10 digits even when typed with a leading 0', async () => {
    registerMock.mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
    await fillRequired();
    const phone = screen.getByLabelText(t('auth.phone'));
    await userEvent.type(phone, '098765 43210');
    expect((phone as HTMLInputElement).value).toBe('9876543210');
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(registerMock).toHaveBeenCalledTimes(1);
    expect(registerMock.mock.calls[0][0].phone).toBe('+919876543210');
  });

  it('shows a short number error under the field and does not submit', async () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
    await fillRequired();
    await userEvent.type(screen.getByLabelText(t('auth.phone')), '98765');
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(await screen.findByText(t('phoneField.invalidIndia'))).toBeTruthy();
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('puts a server phone error under the field, not in the banner', async () => {
    registerMock.mockRejectedValue(
      Object.assign(new Error('bad'), {
        isAxiosError: true,
        response: {
          status: 400,
          data: { success: false, error: { code: 'validation_error', message: 'Validation failed.', details: { phone: ['Server says no'] } } },
        },
      }),
    );
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
    await fillRequired();
    await userEvent.type(screen.getByLabelText(t('auth.phone')), '9876543210');
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(await screen.findByText('Server says no')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('still shows the banner when a field error carries no message', async () => {
    registerMock.mockRejectedValue(
      Object.assign(new Error('bad'), {
        isAxiosError: true,
        response: {
          status: 400,
          data: { success: false, error: { code: 'validation_error', message: 'Validation failed.', details: { phone: [] } } },
        },
      }),
    );
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
    await fillRequired();
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(await screen.findByRole('alert')).toBeTruthy();
  });

  it('needs the Terms and Privacy agreement before it submits (WP-H5)', async () => {
    registerMock.mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
    await fillRequired();
    await userEvent.click(screen.getByRole('checkbox')); // untick
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(await screen.findByText(t('auth.acceptTermsRequired'))).toBeTruthy();
    expect(registerMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    expect(registerMock).toHaveBeenCalledTimes(1);
    expect(registerMock.mock.calls[0][0].acceptTerms).toBe(true);
  });
});

const referral = vi.hoisted(() => ({ check: vi.fn() }));
vi.mock('@/api/billing', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/billing')>()),
  checkReferralCode: (code: string) => referral.check(code),
}));

/** D-19: a ?ref= code is checked, shown as an invitation, and sent with the sign-up. */
describe('RegisterPage referral link', () => {
  afterEach(() => {
    registerMock.mockReset();
    referral.check.mockReset();
    sessionStorage.clear();
  });

  it('says the visitor was invited and sends the code with the sign-up', async () => {
    referral.check.mockResolvedValue(true);
    registerMock.mockResolvedValue(undefined);
    render(
      <MemoryRouter initialEntries={['/register?ref=ab-cd2345']}>
        <RegisterPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(t('auth.referralInvited'))).toBeTruthy();
    expect(referral.check).toHaveBeenCalledWith('abcd2345');
    await userEvent.type(screen.getByLabelText(t('auth.companyName')), 'Shri Krishna Enterprises');
    await userEvent.type(screen.getByLabelText(t('auth.email')), 'owner@example.com');
    await userEvent.type(screen.getByLabelText(t('auth.verificationCode')), '123456');
    await userEvent.type(screen.getByLabelText(t('auth.password')), 'long-enough-1');
    await userEvent.click(screen.getByLabelText(t('auth.state')));
    await userEvent.click(await screen.findByRole('option', { name: 'Uttar Pradesh' }));
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: t('auth.register') }));
    await vi.waitFor(() => expect(registerMock).toHaveBeenCalled());
    expect(registerMock.mock.calls[0][0]).toMatchObject({ referralCode: 'abcd2345' });
  });

  it('shows nothing for an unknown code and never blocks the form', async () => {
    referral.check.mockResolvedValue(false);
    render(
      <MemoryRouter initialEntries={['/register?ref=NOPE']}>
        <RegisterPage />
      </MemoryRouter>,
    );
    await vi.waitFor(() => expect(referral.check).toHaveBeenCalled());
    expect(screen.queryByText(t('auth.referralInvited'))).toBeNull();
    expect(screen.getByRole('button', { name: t('auth.register') })).toBeTruthy();
  });
});

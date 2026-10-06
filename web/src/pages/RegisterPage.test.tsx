import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { RegisterPage } from '@/pages/RegisterPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    register: vi.fn(),
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

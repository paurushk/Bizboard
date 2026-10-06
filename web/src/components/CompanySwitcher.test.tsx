import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompanySwitcher } from '@/components/CompanySwitcher';

const state = vi.hoisted(() => ({
  error: null as string | null,
  memberships: [] as Array<{ companyId: number; companyName: string; isActiveSelection: boolean }>,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1 } }),
}));

vi.mock('@/hooks/useCompanySwitcher', () => ({
  useCompanySwitcher: () => ({
    memberships: state.memberships,
    hasMultiple: state.memberships.length > 1,
    loading: false,
    switchCompany: vi.fn(),
    error: state.error,
  }),
}));

vi.mock('@/pages/help/HelpWhyLink', () => ({ HelpWhyLink: () => null }));

describe('CompanySwitcher error banner', () => {
  beforeEach(() => {
    state.error = null;
    state.memberships = [];
  });

  it('shows nothing when there is no error', () => {
    render(<CompanySwitcher />);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows the error, and hides it once dismissed', async () => {
    state.error = 'Could not load your companies';
    render(<CompanySwitcher />);
    expect(await screen.findByText('Could not load your companies')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /close/i }));
    await waitFor(() => expect(screen.queryByText('Could not load your companies')).toBeNull());
  });

  it('shows the banner again when a different error arrives after a dismissal', async () => {
    state.error = 'First problem';
    const { rerender } = render(<CompanySwitcher />);
    await userEvent.click(await screen.findByRole('button', { name: /close/i }));
    await waitFor(() => expect(screen.queryByText('First problem')).toBeNull());

    state.error = 'Second problem';
    rerender(<CompanySwitcher />);
    expect(await screen.findByText('Second problem')).toBeTruthy();
  });

  it('keeps an error dismissed while the same error is still reported', async () => {
    state.error = 'Same problem';
    const { rerender } = render(<CompanySwitcher />);
    await userEvent.click(await screen.findByRole('button', { name: /close/i }));
    await waitFor(() => expect(screen.queryByText('Same problem')).toBeNull());
    rerender(<CompanySwitcher />);
    expect(screen.queryByText('Same problem')).toBeNull();
  });

  it('offers the company picker only when there is more than one company', () => {
    state.memberships = [{ companyId: 1, companyName: 'Acme', isActiveSelection: true }];
    const { rerender } = render(<CompanySwitcher />);
    expect(screen.queryByRole('combobox')).toBeNull();

    state.memberships = [
      { companyId: 1, companyName: 'Acme', isActiveSelection: true },
      { companyId: 2, companyName: 'Beta', isActiveSelection: false },
    ];
    rerender(<CompanySwitcher />);
    expect(screen.getByRole('combobox')).toBeTruthy();
  });
});

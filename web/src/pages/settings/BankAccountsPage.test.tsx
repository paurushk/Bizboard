import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { BankAccountsPage } from '@/pages/settings/BankAccountsPage';

vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

const api = vi.hoisted(() => ({
  listAllBankAccounts: vi.fn(),
  createBankAccount: vi.fn(),
  updateBankAccount: vi.fn(),
  deactivateBankAccount: vi.fn(),
  revealBankAccountNumber: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const MAIN = {
  id: 1,
  name: 'HDFC Current',
  accountType: 'CURRENT',
  accountNumberMasked: 'XXXXXXXX9012',
  hasFullNumber: true,
  ifsc: 'HDFC0001234',
  upiId: 'shop@okhdfc',
  openingBalance: '500.00',
  openingAsOf: '2026-04-01',
  openingLocked: true,
  isDefault: true,
  isActive: true,
  printOnInvoices: true,
};
const OLD = {
  id: 2,
  name: 'Old savings',
  accountType: 'SAVINGS',
  accountNumberMasked: 'XXXX1111',
  hasFullNumber: false,
  ifsc: '',
  upiId: '',
  openingBalance: '0',
  openingLocked: false,
  isDefault: false,
  isActive: true,
  printOnInvoices: false,
};
const OFF = { ...OLD, id: 3, name: 'Closed one', isActive: false };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BankAccountsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const rowOf = async (text: string) => (await screen.findByText(text)).closest('tr') as HTMLElement;

describe('BankAccountsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listAllBankAccounts.mockResolvedValue([MAIN, OLD, OFF]);
  });

  it('shows the masked number, whether the full number is saved, and the account chips', async () => {
    renderPage();
    const main = await rowOf('HDFC Current');
    expect(within(main).getByText('XXXXXXXX9012')).toBeTruthy();
    expect(within(main).getByText(t('banks.fullNumberSaved'))).toBeTruthy();
    expect(within(main).getByText(t('banks.chipDefault'))).toBeTruthy();
    expect(within(main).getByText(t('banks.chipInvoices'))).toBeTruthy();
    const old = await rowOf('Old savings');
    expect(within(old).getByText(t('banks.noFullNumber'))).toBeTruthy();
    expect(within(await rowOf('Closed one')).getByText(t('banks.chipOff'))).toBeTruthy();
  });

  it('only offers Switch on for a switched-off account and never for default actions', async () => {
    renderPage();
    const off = await rowOf('Closed one');
    expect(within(off).getByRole('button', { name: t('banks.switchOn') })).toBeTruthy();
    expect(within(off).queryByRole('button', { name: t('banks.makeDefault') })).toBeNull();
    const main = await rowOf('HDFC Current');
    expect(within(main).queryByRole('button', { name: t('banks.makeDefault') })).toBeNull();
    // No full number saved, so it cannot be offered for invoices.
    const old = await rowOf('Old savings');
    expect(within(old).queryByRole('button', { name: t('banks.useOnInvoices') })).toBeNull();
  });

  it('makes an account the default', async () => {
    api.updateBankAccount.mockResolvedValue({});
    renderPage();
    const old = await rowOf('Old savings');
    await userEvent.click(within(old).getByRole('button', { name: t('banks.makeDefault') }));
    expect(api.updateBankAccount).toHaveBeenCalledWith(2, { is_default: true });
  });

  it('creates an account with the full number and UPI ID', async () => {
    api.createBankAccount.mockResolvedValue({});
    renderPage();
    await screen.findByText('HDFC Current');
    await userEvent.click(screen.getByRole('button', { name: t('banks.add') }));
    await userEvent.type(screen.getByLabelText(new RegExp(`^${t('banks.name')}`)), 'ICICI');
    await userEvent.type(screen.getByLabelText(t('banks.accountNumber')), '998877665544');
    await userEvent.type(screen.getByLabelText(t('banks.ifsc')), 'icic0002222');
    await userEvent.type(screen.getByLabelText(t('banks.upi')), 'new@okicici');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.createBankAccount).toHaveBeenCalled());
    expect(api.createBankAccount).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'ICICI',
        account_number: '998877665544',
        ifsc: 'ICIC0002222',
        upi_id: 'new@okicici',
        print_on_invoices: false,
      }),
      // A key for this create, so a double-click or retry adds one account.
      expect.objectContaining({ 'Idempotency-Key': expect.any(String) }),
    );
  });

  it('keeps the saved number when editing without typing one, and locks the opening balance after activity', async () => {
    api.updateBankAccount.mockResolvedValue({});
    renderPage();
    const main = await rowOf('HDFC Current');
    await userEvent.click(within(main).getByRole('button', { name: t('banks.edit') }));
    expect((screen.getByLabelText(t('banks.opening')) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText(t('banks.openingLocked'))).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.updateBankAccount).toHaveBeenCalled());
    const [id, body] = api.updateBankAccount.mock.calls[0];
    expect(id).toBe(1);
    expect(body).not.toHaveProperty('account_number');
    expect(body).not.toHaveProperty('opening_balance');
  });

  it('shows the full number only on request', async () => {
    api.revealBankAccountNumber.mockResolvedValue({ accountNumber: '123456789012' });
    renderPage();
    const main = await rowOf('HDFC Current');
    await userEvent.click(within(main).getByRole('button', { name: t('banks.edit') }));
    expect(screen.queryByText('123456789012')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: t('banks.showNumber') }));
    expect(await screen.findByText('123456789012')).toBeTruthy();
    expect(api.revealBankAccountNumber).toHaveBeenCalledWith(1);
  });

  it('refuses a bad IFSC before calling the server', async () => {
    renderPage();
    await screen.findByText('HDFC Current');
    await userEvent.click(screen.getByRole('button', { name: t('banks.add') }));
    await userEvent.type(screen.getByLabelText(new RegExp(`^${t('banks.name')}`)), 'X');
    await userEvent.type(screen.getByLabelText(t('banks.ifsc')), 'BAD');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(await screen.findByText(t('banks.ifscInvalid'))).toBeTruthy();
    expect(api.createBankAccount).not.toHaveBeenCalled();
  });

  it('hides the number fields for a cash box', async () => {
    renderPage();
    await screen.findByText('HDFC Current');
    await userEvent.click(screen.getByRole('button', { name: t('banks.add') }));
    await userEvent.click(screen.getByLabelText(t('banks.type')));
    await userEvent.click(await screen.findByRole('option', { name: t('banks.typeCashBox') }));
    expect(screen.queryByLabelText(t('banks.accountNumber'))).toBeNull();
    expect(screen.queryByText(t('banks.useOnInvoices'))).toBeNull();
  });

  it('switches an account off after confirmation and shows the server reason when refused', async () => {
    api.deactivateBankAccount.mockRejectedValueOnce(new Error('Make another account the default first.'));
    renderPage();
    const old = await rowOf('Old savings');
    await userEvent.click(within(old).getByRole('button', { name: t('banks.switchOff') }));
    expect(screen.getByText(t('banks.switchOffTitle'))).toBeTruthy();
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('banks.switchOff') }));
    expect(api.deactivateBankAccount).toHaveBeenCalledWith(2);
    expect(await screen.findByText(/Make another account the default first/)).toBeTruthy();
  });

  it('shows an error with Retry when the list cannot load', async () => {
    api.listAllBankAccounts.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByText('HDFC Current')).toBeNull();
  });
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { AccountingSettingsPage } from '@/pages/phase/AccountingExtraPages';

vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/components/AccountingBackfillBanner', () => ({ AccountingBackfillBanner: () => null }));
vi.mock('@/components/accounting/ExpensePostingSettings', () => ({ ExpensePostingSettings: () => null }));

const api = vi.hoisted(() => ({
  getAccountingSettings: vi.fn(),
  updateAccountingSettings: vi.fn(),
  getAccountingDisablePreflight: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const PREFLIGHT = {
  accountingEnabled: true,
  postedJournals: 42,
  firstEntryDate: '2026-04-02',
  lastEntryDate: '2026-10-15',
  closedPeriods: 0,
  softClosedPeriods: 1,
  latestClosedPeriodEnd: null,
  backfillRunning: false,
  blockers: [] as string[],
  canDisable: true,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AccountingSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AccountingSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAccountingSettings.mockResolvedValue({ accountingEnabled: true });
    api.getAccountingDisablePreflight.mockResolvedValue(PREFLIGHT);
    api.updateAccountingSettings.mockResolvedValue({ accountingEnabled: false });
  });

  it('shows the current state and only the button that applies', async () => {
    renderPage();
    expect(await screen.findByText(t('acctSettings.statusOn'))).toBeTruthy();
    expect(screen.getByRole('button', { name: t('acctSettings.switchOffButton') })).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('sweep2.enableAccounting') })).toBeNull();
  });

  it('shows neither button while the state is loading, so a quick click cannot hit the wrong one', async () => {
    let resolve: (v: { accountingEnabled: boolean }) => void = () => undefined;
    api.getAccountingSettings.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderPage();
    expect(screen.queryByRole('button', { name: t('sweep2.enableAccounting') })).toBeNull();
    expect(screen.queryByRole('button', { name: t('acctSettings.switchOffButton') })).toBeNull();
    resolve({ accountingEnabled: true });
    expect(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') })).toBeTruthy();
  });

  it('offers Enable, and no switch-off, while the books are off', async () => {
    api.getAccountingSettings.mockResolvedValue({ accountingEnabled: false });
    renderPage();
    expect(await screen.findByText(t('acctSettings.statusOff'))).toBeTruthy();
    expect(screen.getByRole('button', { name: t('sweep2.enableAccounting') })).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('acctSettings.switchOffButton') })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: t('sweep2.enableAccounting') }));
    expect(api.updateAccountingSettings).toHaveBeenCalledWith({ accountingEnabled: true });
  });

  it('shows what switching off does, and needs a reason and the acknowledgement', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(t('acctSettings.entriesPosted', { count: '42', from: '2026-04-02', to: '2026-10-15' }))).toBeTruthy();
    expect(within(dialog).getByText(t('acctSettings.softClosed', { count: '1' }))).toBeTruthy();
    const go = within(dialog).getByRole('button', { name: t('acctSettings.switchOff') }) as HTMLButtonElement;
    expect(go.disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(new RegExp(t('acctSettings.reasonLabel').slice(0, 15))), 'Moving away');
    expect(go.disabled).toBe(true); // posted entries: acknowledgement still needed
    await userEvent.click(within(dialog).getByRole('checkbox'));
    expect(go.disabled).toBe(false);
    await userEvent.click(go);
    await waitFor(() => expect(api.updateAccountingSettings).toHaveBeenCalled());
    expect(api.updateAccountingSettings).toHaveBeenCalledWith({
      accountingEnabled: false,
      reason: 'Moving away',
      acknowledge: true,
    });
  });

  it('says the ledger keeps posting when the company has shadow books (WP-F2)', async () => {
    api.getAccountingDisablePreflight.mockResolvedValue({ ...PREFLIGHT, postLedger: true });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(t('acctSettings.whatItDoesShadow'))).toBeTruthy();
    expect(within(dialog).queryByText(t('acctSettings.whatItDoes'))).toBeNull();
    expect(within(dialog).getByText(t('acctSettings.understandShadow'))).toBeTruthy();
  });

  it('needs no acknowledgement when nothing has been posted', async () => {
    api.getAccountingDisablePreflight.mockResolvedValue({ ...PREFLIGHT, postedJournals: 0, firstEntryDate: null, lastEntryDate: null, softClosedPeriods: 0 });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(t('acctSettings.noEntries'))).toBeTruthy();
    expect(within(dialog).queryByRole('checkbox')).toBeNull();
    await userEvent.type(within(dialog).getByLabelText(new RegExp(t('acctSettings.reasonLabel').slice(0, 15))), 'Mistake');
    expect((within(dialog).getByRole('button', { name: t('acctSettings.switchOff') }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('refuses outright when a period is closed: no reason box, no way to proceed', async () => {
    api.getAccountingDisablePreflight.mockResolvedValue({
      ...PREFLIGHT,
      closedPeriods: 1,
      latestClosedPeriodEnd: '2026-03-31',
      blockers: ['closed_period'],
      canDisable: false,
    });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(t('acctSettings.blockedClosed', { date: '2026-03-31' }))).toBeTruthy();
    expect(within(dialog).queryByLabelText(new RegExp(t('acctSettings.reasonLabel').slice(0, 15)))).toBeNull();
    expect((within(dialog).getByRole('button', { name: t('acctSettings.switchOff') }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.updateAccountingSettings).not.toHaveBeenCalled();
  });

  it('says so when a back-fill is running', async () => {
    api.getAccountingDisablePreflight.mockResolvedValue({
      ...PREFLIGHT,
      backfillRunning: true,
      blockers: ['backfill_running'],
      canDisable: false,
    });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    expect(await screen.findByText(t('acctSettings.blockedBackfill'))).toBeTruthy();
  });

  it('shows the server reason inside the dialog when the switch-off is refused', async () => {
    api.updateAccountingSettings.mockRejectedValueOnce(new Error('A back-fill is running.'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(await within(dialog).findByLabelText(new RegExp(t('acctSettings.reasonLabel').slice(0, 15))), 'x');
    await userEvent.click(within(dialog).getByRole('checkbox'));
    await userEvent.click(within(dialog).getByRole('button', { name: t('acctSettings.switchOff') }));
    expect(await within(dialog).findByText('A back-fill is running.')).toBeTruthy();
  });

  it('shows an error with Retry when the check cannot be loaded, and cannot be confirmed', async () => {
    api.getAccountingDisablePreflight.mockRejectedValue(new Error('down'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('acctSettings.switchOffButton') }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect((within(dialog).getByRole('button', { name: t('acctSettings.switchOff') }) as HTMLButtonElement).disabled).toBe(true);
  });
});

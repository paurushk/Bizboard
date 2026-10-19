import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { MoneyInRulesPage } from '@/pages/settings/MoneyInRulesPage';

vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

const api = vi.hoisted(() => ({
  previewSettingsChange: vi.fn(),
  getMoneyInRules: vi.fn(),
  updateMoneyInRules: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const RULES = {
  requirePaymentReference: false,
  autoMatchBankExact: false,
  chequeAllocationOnClearance: false,
  cash269stMode: 'warn',
  advanceGstTreatment: 'none',
  advanceGstDefaultRate: null,
  dunningEnabled: false,
  dunningDays: [3, 7, 14],
  dunningMaxReminders: 3,
  dunningQuietHoursStart: 21,
  dunningQuietHoursEnd: 8,
  autoCreditHoldOnSevereOverdue: false,
  updatedAt: '2026-10-19T10:00:00Z',
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MoneyInRulesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MoneyInRulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getMoneyInRules.mockResolvedValue(RULES);
    api.updateMoneyInRules.mockResolvedValue(RULES);
    api.previewSettingsChange.mockResolvedValue([{ key: 'cash_days_over_limit', params: { count: 2, blocked: true } }]);
  });

  it('shows the saved rules and saves a change through the rules endpoint only', async () => {
    renderPage();
    const hold = await screen.findByRole('checkbox', { name: /hold cheques as advances until they clear/i });
    expect((hold as HTMLInputElement).checked).toBe(false);
    expect(screen.getByLabelText(/cash limit check/i).textContent).toBe('Warn');
    const save = screen.getAllByRole('button', { name: t('common.save') })[0];
    expect((save as HTMLButtonElement).disabled).toBe(true);

    await userEvent.click(hold);
    await userEvent.click(screen.getByLabelText(/gst on advances/i));
    await userEvent.click(await screen.findByRole('option', { name: /services/i }));
    await userEvent.type(await screen.findByLabelText(/default gst rate on advances/i), '18');
    expect(screen.getByText(t('settingsShell.unsaved'))).toBeTruthy();
    await userEvent.click(screen.getAllByRole('button', { name: t('common.save') })[0]);

    await waitFor(() => expect(api.updateMoneyInRules).toHaveBeenCalledTimes(1));
    expect(api.updateMoneyInRules.mock.calls[0][0]).toMatchObject({
      cheque_allocation_on_clearance: true,
      cash_269st_mode: 'warn',
      advance_gst_treatment: 'services',
      advance_gst_default_rate: '18',
    });
    expect(await screen.findByText(t('settingsShell.saved'))).toBeTruthy();
  });

  it('previews the cash limit change with how many past days it would have refused', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    await userEvent.click(await screen.findByLabelText(/cash limit check/i));
    await userEvent.click(await screen.findByRole('option', { name: t('receipts.policyCashBlock') }));
    await userEvent.click(screen.getAllByRole('button', { name: t('common.save') })[0]);
    await waitFor(() => expect(confirm).toHaveBeenCalled());
    expect(String(confirm.mock.calls[0][0])).toContain(t('settingsPreview.cash_days_over_limit_block', { count: '2' }));
    expect(api.previewSettingsChange).toHaveBeenCalledWith('cash_269st', { cash_269st_mode: 'block' });
    expect(api.updateMoneyInRules).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it('sends no advance GST rate unless the treatment is services', async () => {
    renderPage();
    const hold = await screen.findByRole('checkbox', { name: /hold cheques as advances until they clear/i });
    await userEvent.click(hold);
    await userEvent.click(screen.getAllByRole('button', { name: t('common.save') })[0]);
    await waitFor(() => expect(api.updateMoneyInRules).toHaveBeenCalled());
    expect(api.updateMoneyInRules.mock.calls[0][0].advance_gst_default_rate).toBeNull();
  });

  it('shows the server reason when a save is refused and keeps the changes', async () => {
    api.updateMoneyInRules.mockRejectedValueOnce(new Error('The advance GST rate must be between 0 and 40.'));
    renderPage();
    const hold = await screen.findByRole('checkbox', { name: /hold cheques as advances until they clear/i });
    await userEvent.click(hold);
    await userEvent.click(screen.getAllByRole('button', { name: t('common.save') })[0]);
    expect(await screen.findByText(/must be between 0 and 40/)).toBeTruthy();
    expect((hold as HTMLInputElement).checked).toBe(true);
  });

  it('shows an error with Retry when the rules cannot load, never an editable blank form', async () => {
    api.getMoneyInRules.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('sends the time the rules were loaded with every save', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('checkbox', { name: /hold cheques as advances until they clear/i }));
    await userEvent.click(screen.getAllByRole('button', { name: t('common.save') })[0]);
    await waitFor(() => expect(api.updateMoneyInRules).toHaveBeenCalledTimes(1));
    expect(api.updateMoneyInRules.mock.calls[0][0].expected_updated_at).toBe('2026-10-19T10:00:00Z');
  });

  describe('reminders and credit hold (SET-17)', () => {
    const saveButtons = () => screen.getAllByRole('button', { name: t('common.save') });

    it('saves only the reminder fields from its own Save, leaving the cash rules out', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('checkbox', { name: t('settings.autoCreditHold') }));
      await userEvent.click(saveButtons()[1]);
      await waitFor(() => expect(api.updateMoneyInRules).toHaveBeenCalledTimes(1));
      const sent = api.updateMoneyInRules.mock.calls[0][0];
      expect(sent).toMatchObject({ auto_credit_hold_on_severe_overdue: true, dunning_days: [3, 7, 14] });
      expect(sent).not.toHaveProperty('cash_269st_mode');
    });

    it('asks before turning reminders on, and does not save when declined', async () => {
      window.confirm = vi.fn(() => false);
      renderPage();
      await userEvent.click(await screen.findByRole('checkbox', { name: t('settings.dunningEnabled') }));
      await userEvent.click(saveButtons()[1]);
      expect(window.confirm).toHaveBeenCalled();
      expect(api.updateMoneyInRules).not.toHaveBeenCalled();
    });

    it('saves after the owner agrees', async () => {
      window.confirm = vi.fn(() => true);
      renderPage();
      await userEvent.click(await screen.findByRole('checkbox', { name: t('settings.dunningEnabled') }));
      await userEvent.click(saveButtons()[1]);
      await waitFor(() => expect(api.updateMoneyInRules).toHaveBeenCalledTimes(1));
      expect(api.updateMoneyInRules.mock.calls[0][0].dunning_enabled).toBe(true);
    });

    it('refuses reminder days that are not whole numbers, with a reason', async () => {
      renderPage();
      const days = await screen.findByLabelText(t('settings.dunningDays'));
      await userEvent.clear(days);
      await userEvent.type(days, '3, x');
      await userEvent.click(saveButtons()[1]);
      expect(await screen.findByText(t('collections.daysInvalid'))).toBeTruthy();
      expect(api.updateMoneyInRules).not.toHaveBeenCalled();
    });
  });
});

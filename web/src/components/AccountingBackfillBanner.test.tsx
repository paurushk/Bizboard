import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingBackfillBanner } from '@/components/AccountingBackfillBanner';
import { t } from '@/i18n';

const api = vi.hoisted(() => ({
  settings: { accountingEnabled: true, accountingBackfillNeeded: true } as Record<string, unknown>,
  postAccountingBackfill: vi.fn(),
  getAccountingBackfillStatus: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  getAccountingSettings: async () => api.settings,
  listAccounts: async () => [{ id: 1, code: '1000', name: 'Cash' }],
  postAccountingBackfill: (...args: unknown[]) => api.postAccountingBackfill(...args),
  getAccountingBackfillStatus: (...args: unknown[]) => api.getAccountingBackfillStatus(...args),
}));

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const invalidate = vi.spyOn(qc, 'invalidateQueries');
  render(
    <QueryClientProvider client={qc}>
      <AccountingBackfillBanner />
    </QueryClientProvider>,
  );
  return { invalidate };
}

const previewButton = () => screen.findByRole('button', { name: t('phase.accountingBackfillPreview') });
const postButton = () => screen.findByRole('button', { name: t('phase.accountingBackfillPost') });

describe('AccountingBackfillBanner', () => {
  beforeEach(() => {
    api.settings = { accountingEnabled: true, accountingBackfillNeeded: true };
    api.postAccountingBackfill.mockReset();
    api.getAccountingBackfillStatus.mockReset();
  });

  it('says nothing when no back-fill is needed', async () => {
    api.settings = { accountingEnabled: true, accountingBackfillNeeded: false };
    const { invalidate } = mount();
    await waitFor(() => expect(invalidate).not.toHaveBeenCalled());
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('offers a preview and a post when a back-fill is needed', async () => {
    mount();
    expect(await screen.findByText(t('phase.accountingBackfillNeeded'))).toBeTruthy();
    expect(await previewButton()).toBeTruthy();
    expect(await postButton()).toBeTruthy();
  });

  it('shows what a dry run would do, without posting', async () => {
    api.postAccountingBackfill.mockResolvedValue({ status: 'done', wouldPost: 7, trialBalanceBalanced: true, inventoryVariance: '0' });
    const { invalidate } = mount();
    await userEvent.click(await previewButton());

    expect(api.postAccountingBackfill).toHaveBeenCalledWith({ dry_run: true });
    expect(await screen.findByText(/7/)).toBeTruthy();
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ['accounting-settings'] });
  });

  it('runs a confirmed back-fill as a job, shows it running, then shows the result and refreshes the books', async () => {
    api.postAccountingBackfill.mockResolvedValue({ status: 'running' });
    api.getAccountingBackfillStatus.mockResolvedValue({ status: 'done', wouldPost: 12, trialBalanceBalanced: true });
    const { invalidate } = mount();
    await userEvent.click(await postButton());

    expect(api.postAccountingBackfill).toHaveBeenCalledWith({ confirm: true });
    await waitFor(() => expect(api.getAccountingBackfillStatus).toHaveBeenCalled());
    expect(await screen.findByText(/12/)).toBeTruthy();
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['accounting-settings'] }));
    expect(screen.queryByText(new RegExp(t('phase.accountingBackfillRunning')))).toBeNull();
  });

  it('keeps the buttons off while the job is running', async () => {
    api.postAccountingBackfill.mockResolvedValue({ status: 'running' });
    api.getAccountingBackfillStatus.mockResolvedValue({ status: 'running' });
    mount();
    await userEvent.click(await postButton());
    expect(await screen.findByText(new RegExp(t('phase.accountingBackfillRunning')))).toBeTruthy();
    expect(await postButton()).toBeDisabled();
    expect(await previewButton()).toBeDisabled();
  });

  it('shows the failure and stops running when the job fails', async () => {
    api.postAccountingBackfill.mockResolvedValue({ status: 'running' });
    api.getAccountingBackfillStatus.mockResolvedValue({ status: 'failed', error: 'Period is locked' });
    mount();
    await userEvent.click(await postButton());

    expect(await screen.findByText(/Period is locked/)).toBeTruthy();
    expect(screen.queryByText(new RegExp(t('phase.accountingBackfillRunning')))).toBeNull();
    expect(await postButton()).toBeEnabled();
  });

  it('shows the error when the request itself is refused', async () => {
    api.postAccountingBackfill.mockRejectedValue(new Error('Not allowed'));
    mount();
    await userEvent.click(await previewButton());
    expect(await screen.findByText(/Not allowed/)).toBeTruthy();
  });
});

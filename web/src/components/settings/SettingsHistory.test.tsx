import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsHistory } from '@/components/settings/SettingsHistory';
import { t } from '@/i18n';

const api = vi.hoisted(() => ({ getSettingsHistory: vi.fn() }));
vi.mock('@/api/resources', () => api);

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SettingsHistory area="series" />
    </QueryClientProvider>,
  );
}

describe('SettingsHistory (SET-21)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSettingsHistory.mockResolvedValue({
      area: 'series',
      items: [
        {
          id: 1, at: '2026-10-19T10:00:00Z', who: 'Asha', action: 'UPDATE', entity: 'DocumentSeries', what: 'SALES_INVOICE',
          changes: [{ field: 'prefix', from: 'INV', to: 'TAX' }, { field: 'payment_keys', changed: true }],
        },
      ],
    });
  });

  it('loads nothing until opened, then shows who changed what from and to', async () => {
    renderIt();
    expect(api.getSettingsHistory).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: t('settingsHistory.open') }));
    expect(await screen.findByText(/Asha/)).toBeTruthy();
    expect(screen.getByText(/INV → TAX/)).toBeTruthy();
    expect(api.getSettingsHistory).toHaveBeenCalledWith('series');
  });

  it('never shows a value for a secret, only that it changed', async () => {
    renderIt();
    await userEvent.click(screen.getByRole('button', { name: t('settingsHistory.open') }));
    expect(await screen.findByText(/payment keys:.*value not shown/)).toBeTruthy();
  });

  it('says so when nothing has changed yet, and shows an error with Retry when it cannot load', async () => {
    api.getSettingsHistory.mockResolvedValueOnce({ area: 'series', items: [] });
    const first = renderIt();
    await userEvent.click(screen.getByRole('button', { name: t('settingsHistory.open') }));
    expect(await screen.findByText(t('settingsHistory.none'))).toBeTruthy();
    first.unmount();
    api.getSettingsHistory.mockRejectedValue(new Error('down'));
    renderIt();
    await userEvent.click(screen.getByRole('button', { name: t('settingsHistory.open') }));
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });
});

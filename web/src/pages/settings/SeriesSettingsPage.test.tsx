import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { SeriesSettingsPage } from '@/pages/settings/SeriesSettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), patch: vi.fn() },
  getErrorMessage: (err: unknown) => (err instanceof Error ? err.message : 'error'),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SeriesSettingsPage Hindi names', () => {
  afterEach(() => setLocale('en'));

  it('shows catalog series names and the save label in Hindi', async () => {
    setLocale('hi');
    const { apiClient } = await import('@/api/client');
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { prefix: 'INV', nextNumber: 12, padding: 4, preview: 'INV-0012' },
    } as never);
    let release: (value: unknown) => void = () => {};
    vi.mocked(apiClient.patch).mockImplementation(
      () => new Promise((resolve) => {
        release = resolve;
      }),
    );

    wrap(<SeriesSettingsPage />);
    expect(await screen.findByText(t('cog.seriesSales'))).toBeTruthy();
    expect(screen.getByText(t('cog.seriesGrn'))).toBeTruthy();
    expect(screen.queryByText('Sales Invoices')).toBeNull();

    const configure = screen.getAllByRole('button', { name: t('sweep2.configure') })[0];
    await userEvent.click(configure);
    expect(screen.getByText(t('cog.configureSeries', { name: t('cog.seriesSales') }))).toBeTruthy();
    const save = screen.getByRole('button', { name: t('cog.saveConfiguration') });
    await userEvent.click(save);
    expect(await screen.findByRole('button', { name: t('cog.savingConfig') })).toBeTruthy();
    release({ data: {} });
  });
});

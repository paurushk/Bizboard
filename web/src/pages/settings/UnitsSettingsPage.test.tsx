import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { UnitsSettingsPage } from '@/pages/settings/UnitsSettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 9 } }),
}));

const api = vi.hoisted(() => ({
  listUnits: vi.fn(),
  getUnitUsage: vi.fn(),
  createUnit: vi.fn(),
  updateUnit: vi.fn(),
  deleteUnit: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const UNITS = [
  { id: 1, name: 'Dozen', shortName: 'doz', uqcCode: 'DOZ' },
  { id: 2, name: 'Kilogram', shortName: 'kg', uqcCode: 'KGS' },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <UnitsSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const rowOf = async (name: string) => (await screen.findByText(name)).closest('tr') as HTMLElement;

describe('UnitsSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listUnits.mockResolvedValue(UNITS);
    api.getUnitUsage.mockResolvedValue({ '1': 12 });
    api.deleteUnit.mockResolvedValue(undefined);
  });

  it('shows how many items use each unit', async () => {
    renderPage();
    expect(within(await rowOf('Dozen')).getByText('12')).toBeTruthy();
    expect(within(await rowOf('Kilogram')).getByText(t('units.usedByNone'))).toBeTruthy();
  });

  it('offers Delete only for a unit nothing uses', async () => {
    renderPage();
    expect(within(await rowOf('Dozen')).queryByRole('button', { name: t('units.delete') })).toBeNull();
    expect(within(await rowOf('Kilogram')).getByRole('button', { name: t('units.delete') })).toBeTruthy();
  });

  it('deletes an unused unit only after confirmation', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Kilogram')).getByRole('button', { name: t('units.delete') }));
    expect(api.deleteUnit).not.toHaveBeenCalled();
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t('units.delete') }));
    await waitFor(() => expect(api.deleteUnit).toHaveBeenCalledWith(2));
  });

  it('shows the server reason when a delete is refused', async () => {
    api.deleteUnit.mockRejectedValueOnce(new Error('3 item(s) use the unit.'));
    renderPage();
    await userEvent.click(within(await rowOf('Kilogram')).getByRole('button', { name: t('units.delete') }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t('units.delete') }));
    expect(await screen.findByText(/3 item\(s\) use the unit/)).toBeTruthy();
  });

  it('says so and offers no delete when usage cannot be counted', async () => {
    api.getUnitUsage.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByText(t('units.usageUnavailable'))).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('units.delete') })).toBeNull();
  });
});

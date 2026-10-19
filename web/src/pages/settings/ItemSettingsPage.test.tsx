import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { ItemSettingsPage } from '@/pages/settings/ItemSettingsPage';

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 9 } }) }));

const api = vi.hoisted(() => ({
  getCompany: vi.fn(),
  getCustomFieldUsage: vi.fn(),
  updateCompany: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ItemSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ItemSettingsPage custom field usage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getCompany.mockResolvedValue({
      itemCustomFieldDefs: [{ key: 'colour', label: 'Colour', type: 'text', active: true, options: [] }],
    });
    api.getCustomFieldUsage.mockResolvedValue({ colour: 12 });
  });

  it('shows how many items hold a value for a saved field', async () => {
    renderPage();
    expect(await screen.findByText(t('customFieldUsage.usedOn', { count: '12' }), { exact: false })).toBeTruthy();
  });

  it('says what removing a field hides before it is removed', async () => {
    renderPage();
    await screen.findByText(t('customFieldUsage.usedOn', { count: '12' }), { exact: false });
    await userEvent.click(screen.getByRole('button', { name: t('sweep.remove') }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(t('customFieldUsage.removeUsed', { count: '12' }))).toBeTruthy();
  });

  it('says so when no item holds a value', async () => {
    api.getCustomFieldUsage.mockResolvedValue({});
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('sweep.remove') }));
    expect(within(await screen.findByRole('dialog')).getByText(t('customFieldUsage.removeUnused'))).toBeTruthy();
  });

  it('warns that the count is unavailable rather than claiming nothing is used', async () => {
    api.getCustomFieldUsage.mockRejectedValue(new Error('down'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('sweep.remove') }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(t('customFieldUsage.unavailable'))).toBeTruthy();
    expect(within(dialog).queryByText(t('customFieldUsage.removeUnused'))).toBeNull();
  });
});

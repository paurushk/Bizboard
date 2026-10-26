import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';
import { DataRetentionPanel } from './DataRetentionPanel';

const api = vi.hoisted(() => ({ getCompany: vi.fn(), updateCompany: vi.fn(), blocked: false }));
vi.mock('@/api/resources', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/resources')>()),
  getCompany: () => api.getCompany(),
  updateCompany: (payload: unknown) => api.updateCompany(payload),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: api.blocked, isLoading: false }),
}));

const mount = () => renderRoutes([{ path: '/', element: <DataRetentionPanel /> }], '/');

/** D-13: the owner sets how long a read-only account is kept, and sees when it will be deleted. */
describe('DataRetentionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.blocked = false;
    api.updateCompany.mockResolvedValue({});
  });

  it('saves a new period within 30 to 3650 days, with the version stamp', async () => {
    api.getCompany.mockResolvedValue({ id: 1, updatedAt: 'v1', dataRetentionDays: 90, dataDeletionDueAt: null });
    const user = userEvent.setup();
    mount();
    const field = await screen.findByLabelText('Keep data for (days)');
    await user.clear(field);
    await user.type(field, '10');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await user.clear(field);
    await user.type(field, '180');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledWith({ dataRetentionDays: 180, expected_updated_at: 'v1' }));
    expect(await screen.findByText('Saved.')).toBeInTheDocument();
  });

  it('warns with the deletion date once the account is read-only, and locks the period', async () => {
    api.blocked = true;
    api.getCompany.mockResolvedValue({
      id: 1, dataRetentionDays: 90, readOnlySince: '2026-10-01T00:00:00Z', dataDeletionDueAt: '2026-12-30T00:00:00Z',
    });
    mount();
    expect(await screen.findByText(/will be deleted on/)).toBeInTheDocument();
    expect(screen.getByLabelText('Keep data for (days)')).toBeDisabled();
    expect(screen.getByText(/cannot be changed while the account is read-only/)).toBeInTheDocument();
  });
});

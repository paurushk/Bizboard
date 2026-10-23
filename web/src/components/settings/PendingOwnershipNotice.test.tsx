import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';
import { failedReconciliation } from '@/api/legacyImport';
import { PendingOwnershipNotice } from './PendingOwnershipNotice';

const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  apiClient: client,
}));

beforeEach(() => {
  vi.clearAllMocks();
  client.post.mockResolvedValue({ data: {} });
});

describe('WP-ID1 pending ownership notice (review fix)', () => {
  it('shows a staff recovery and lets an owner cancel it', async () => {
    client.get.mockResolvedValueOnce({
      data: { pending: { id: 3, kind: 'STAFF_RECOVERY', status: 'PENDING', toEmail: 'new@x.in',
        expiresAt: '2026-11-01T00:00:00Z', effectiveAt: '2026-10-26T00:00:00Z' } },
    }).mockResolvedValue({ data: { pending: null } });
    const user = userEvent.setup();
    renderRoutes([{ path: '/', element: <PendingOwnershipNotice /> }], '/');
    expect(await screen.findByText(/giving owner access to new@x.in/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(client.post).toHaveBeenCalledWith('/company/ownership/cancel/', {}));
  });

  it('shows nothing when nothing is pending', async () => {
    client.get.mockResolvedValue({ data: { pending: null } });
    const view = renderRoutes([{ path: '/', element: <PendingOwnershipNotice /> }], '/');
    await waitFor(() => expect(client.get).toHaveBeenCalled());
    expect(view.container.querySelector('[role="alert"]')).toBeNull();
  });
});

describe('WP-GR1b reconciliation result (review fix)', () => {
  it('lists the sections whose totals did not tie', () => {
    expect(failedReconciliation({ syncRunId: 1, result: { reconciliation: {
      stock: { pass: true }, receivables: { pass: false }, payables: { pass: true },
    } } })).toEqual(['receivables']);
    expect(failedReconciliation(undefined)).toEqual([]);
  });
});

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SharedTicket } from '@/api/care';
import { SharedTicketsPage } from '@/pages/support/SharedTicketsPage';
import { a11yViolations, renderRoutes, setViewport } from '@/test/careHarness';

vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isSupportTicketsEnabled: () => true,
}));

const mocks = vi.hoisted(() => ({ role: 'OWNER' as string }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'v@x.test', fullName: 'Vendor', role: mocks.role, canCreateSales: true, companyId: 9 } }),
}));

const api = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), replies: vi.fn(), reply: vi.fn() }));
vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  sharedTickets: api,
}));

const row: SharedTicket = {
  id: 4, sourceCompanyName: 'Acme Traders', sourceNumber: 'TKT-000012', subject: 'Printer jams', status: 'IN_PROGRESS',
  description: 'Paper tray', sharedAt: '2026-10-18T08:00:00Z', replyCount: 1,
};

function page(initial = '/support/shared') {
  return renderRoutes(
    [
      { path: '/support/shared', element: <SharedTicketsPage /> },
      { path: '/support/shared/:id', element: <SharedTicketsPage /> },
    ],
    initial,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'OWNER';
  setViewport(1280);
  api.list.mockResolvedValue({ results: [row], count: 1, next: null, previous: null });
  api.get.mockResolvedValue(row);
  api.replies.mockResolvedValue([{ id: 1, body: 'Send the model number', authorName: 'Vendor', createdAt: '2026-10-18T09:00:00Z' }]);
  api.reply.mockResolvedValue({ id: 2 });
});

describe('SharedTicketsPage', () => {
  it('lists what other companies shared, with who sent it and how many replies', async () => {
    page();
    expect(await screen.findByText(/TKT-000012 · Printer jams/)).toBeInTheDocument();
    expect(screen.getByText('Acme Traders')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /TKT-000012/ })).toHaveAttribute('href', '/support/shared/4');
  });

  it('sends the status filter and the search to the server', async () => {
    const user = userEvent.setup();
    page();
    await screen.findByText(/TKT-000012/);
    await user.type(screen.getByRole('searchbox'), 'printer');
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ q: 'printer' })));
    await user.click(screen.getByRole('combobox', { name: 'Status' }));
    await user.click(await screen.findByRole('option', { name: 'In progress' }));
    await waitFor(() => expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ status: 'IN_PROGRESS' })));
  });

  it('opens the shared ticket itself, not the company own tickets', async () => {
    page('/support/shared/4');
    const detail = within(await screen.findByRole('region', { name: 'Shared ticket details' }));
    expect(await detail.findByText('Paper tray')).toBeInTheDocument();
    expect(detail.getByText('Send the model number')).toBeInTheDocument();
  });

  it('sends a reply to the company that shared the ticket', async () => {
    const user = userEvent.setup();
    page('/support/shared/4');
    const detail = within(await screen.findByRole('region', { name: 'Shared ticket details' }));
    expect(await detail.findByRole('button', { name: 'Send reply' })).toBeDisabled();
    await user.type(detail.getByLabelText('Reply'), 'Which printer model is it?');
    await user.click(detail.getByRole('button', { name: 'Send reply' }));
    await waitFor(() => expect(api.reply).toHaveBeenCalledWith(4, 'Which printer model is it?'));
    expect(await detail.findByText('Reply sent.')).toBeInTheDocument();
  });

  it('says so when the description was not shared', async () => {
    api.get.mockResolvedValue({ ...row, description: undefined });
    page('/support/shared/4');
    expect(await screen.findByText('The description was not shared.')).toBeInTheDocument();
  });

  it('explains a ticket that is no longer shared instead of showing a bare error', async () => {
    api.get.mockRejectedValue(new Error('gone'));
    page('/support/shared/4');
    expect(await screen.findByText('This ticket is no longer shared with you.')).toBeInTheDocument();
  });

  it('shows an empty inbox with words', async () => {
    api.list.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    page();
    expect(await screen.findByText(/No tickets have been shared with you yet/i)).toBeInTheDocument();
  });

  it('does not offer replying to a viewer', async () => {
    mocks.role = 'VIEWER';
    page('/support/shared/4');
    const detail = within(await screen.findByRole('region', { name: 'Shared ticket details' }));
    await detail.findByText('Paper tray');
    expect(detail.queryByRole('button', { name: 'Send reply' })).not.toBeInTheDocument();
  });

  it('has no serious accessibility problems', async () => {
    const view = page('/support/shared/4');
    await screen.findByText('Paper tray');
    expect(await a11yViolations(view.container)).toEqual([]);
  });
});

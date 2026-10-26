import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { a11yViolations, renderRoutes } from '@/test/careHarness';
import { ContactSupportPage } from './ContactSupportPage';
import { OwnershipTransferDialog } from '@/components/settings/OwnershipTransferDialog';
import { BizboardInvoicesPanel } from '@/components/billing/BizboardInvoicesPanel';

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { companyId: 1 } }) }));

const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  apiClient: client,
  getLastRequestId: () => 'req-123',
  getRecentErrorCodes: () => ['PDF_FAILED'],
}));
vi.mock('@/api/resources', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/resources')>()),
  uploadFile: vi.fn(async () => ({ id: 77 })),
}));

beforeEach(() => {
  vi.clearAllMocks();
  client.get.mockImplementation(async (url: string) => {
    if (url === '/support/platform-tickets/') return { data: [] };
    if (url === '/billing/invoices/') {
      return { data: [{ id: 5, kind: 'INVOICE', number: 'BB2627-000001', createdAt: '2026-10-01', total: '1180', taxableAmount: '1000', buyerGstin: '27AAAPL1234C1ZE' }] };
    }
    if (url === '/billing/tds-claims/') return { data: { claims: [], sections: [{ code: '194J-2', label: '194J 2%', rate: '2' }] } };
    return { data: {} };
  });
  client.post.mockResolvedValue({ data: { id: 1 } });
});

describe('WP-PO3 contact support', () => {
  it('lets the person rate a resolved request 1-5 when the survey is on (BB-136)', async () => {
    const user = userEvent.setup();
    client.get.mockImplementation(async (url: string) => {
      if (url === '/support/platform-tickets/') {
        return { data: [
          { id: 4, subject: 'Printer', status: 'RESOLVED', satisfactionScore: null },
          { id: 3, subject: 'GST', status: 'RESOLVED', satisfactionScore: 5 },
          { id: 2, subject: 'Open one', status: 'OPEN', satisfactionScore: null },
        ] };
      }
      if (url === '/support/satisfaction/nps-due/') return { data: { due: false, enabled: true } };
      return { data: {} };
    });
    renderRoutes([{ path: '/help/contact', element: <ContactSupportPage /> }], '/help/contact');
    expect(await screen.findByText('You rated this 5 out of 5.')).toBeInTheDocument();
    expect(screen.getAllByRole('group', { name: 'How was the help on this request?' })).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: '4 out of 5' }));
    await waitFor(() =>
      expect(client.post).toHaveBeenCalledWith('/support/satisfaction/', { kind: 'CSAT', score: 4, comment: '', platform_ticket: 4 }),
    );
  });

  it('offers no rating while the survey is off', async () => {
    client.get.mockImplementation(async (url: string) => {
      if (url === '/support/platform-tickets/') return { data: [{ id: 4, subject: 'Printer', status: 'RESOLVED', satisfactionScore: null }] };
      if (url === '/support/satisfaction/nps-due/') return { data: { due: false, enabled: false } };
      return { data: {} };
    });
    renderRoutes([{ path: '/help/contact', element: <ContactSupportPage /> }], '/help/contact');
    expect(await screen.findByText(/Printer/)).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'How was the help on this request?' })).toBeNull();
  });

  it('sends the Support ID, screen and error codes, never form contents', async () => {
    const user = userEvent.setup();
    const view = renderRoutes([{ path: '/help/contact', element: <ContactSupportPage /> }], '/help/contact');
    await user.type(screen.getByLabelText('What do you need help with?'), 'Cannot print invoice');
    await user.click(screen.getByRole('button', { name: 'Send to support' }));
    await waitFor(() => expect(client.post).toHaveBeenCalled());
    const [url, body] = client.post.mock.calls[0];
    expect(url).toBe('/support/platform-tickets/');
    expect(body).toMatchObject({ subject: 'Cannot print invoice', support_id: 'req-123', error_codes: ['PDF_FAILED'], severity: 'P2' });
    expect(await a11yViolations(view.container)).toEqual([]);
  });

  it('prefills a Tally import request from the Tally page link (WP-GR1a)', async () => {
    renderRoutes([{ path: '/help/contact', element: <ContactSupportPage /> }], '/help/contact?topic=tally-import');
    expect(screen.getByLabelText('What do you need help with?')).toHaveValue('Please switch on Tally import for our company');
  });
});

describe('WP-ID1 ownership offer', () => {
  it('needs the password and sends the chosen member', async () => {
    const user = userEvent.setup();
    renderRoutes(
      [{ path: '/', element: <OwnershipTransferDialog member={{ user: 42, email: 'next@alpha.test' }} onClose={() => undefined} /> }],
      '/',
    );
    const send = screen.getByRole('button', { name: 'Send ownership offer' });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText('Your password'), 'Owner-Pass-123');
    await user.click(send);
    await waitFor(() => expect(client.post).toHaveBeenCalledWith(
      '/company/ownership/transfer/', expect.objectContaining({ to_user_id: 42, password: 'Owner-Pass-123', old_owner_becomes: 'MANAGER' }),
    ));
    expect(await screen.findByText(/Offer sent to next@alpha.test/)).toBeInTheDocument();
  });
});

describe('WP-BL1/BL2 Bizboard invoices panel', () => {
  it('lists invoices and only sends a TDS claim with invoices, a section and Form 16A', async () => {
    const user = userEvent.setup();
    const { container } = renderRoutes([{ path: '/', element: <BizboardInvoicesPanel companyKey={1} /> }], '/');
    expect(await screen.findByText(/Invoice BB2627-000001/)).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Send claim' });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByLabelText('TDS section'));
    await user.click(await screen.findByRole('option', { name: '194J 2%' }));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['%PDF'], '16a.pdf', { type: 'application/pdf' }));
    await user.click(submit);
    await waitFor(() => expect(client.post).toHaveBeenCalledWith(
      '/billing/tds-claims/', { invoice_ids: [5], section: '194J-2', certificate_id: 77, settle_by: 'CREDIT' },
    ));
  });

  it('offers a refund instead of renewal credit on an accepted claim (Q5)', async () => {
    const user = userEvent.setup();
    client.get.mockImplementation(async (url: string) => {
      if (url === '/billing/invoices/') return { data: [] };
      if (url === '/billing/tds-claims/') {
        return {
          data: {
            claims: [{ id: 9, status: 'VERIFIED', section: '194J-2', rate: '2', taxableTotal: '1000', amount: '20', quarter: '2026-27 Q2', invoiceNumbers: [], reviewNote: '', createdAt: '2026-10-01', settleBy: 'CREDIT', creditRemaining: '20' }],
            sections: [],
          },
        };
      }
      return { data: {} };
    });
    renderRoutes([{ path: '/', element: <BizboardInvoicesPanel companyKey={1} /> }], '/');
    expect(await screen.findByText(/still to come off renewals/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Refund the rest instead' }));
    await waitFor(() => expect(client.post).toHaveBeenCalledWith('/billing/tds-claims/9/refund/'));
  });
});

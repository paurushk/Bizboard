import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseDetailPage } from '@/pages/purchases/PurchaseDetailPage';
import { registerGlobalConfirm } from '@/utils/confirmBridge';
import type { PurchaseInvoice } from '@/types/domain';

const { getPurchase, completePurchase, cancelPurchase, recordPurchasePayment, downloadPurchasePdf } = vi.hoisted(() => ({
  getPurchase: vi.fn(),
  downloadPurchasePdf: vi.fn(),
  recordPurchasePayment: vi.fn(),
  completePurchase: vi.fn(),
  cancelPurchase: vi.fn(),
}));

vi.mock('@/api/resources', () => ({ getPurchase, completePurchase, cancelPurchase, recordPurchasePayment, downloadPurchasePdf }));

vi.mock('@/components/agents/AgentPrepareButton', () => ({
  AgentPrepareButton: (p: { agentKind?: string; dedupeKey: string }) => <button type="button" data-testid="agent-check">{p.agentKind}:{p.dedupeKey}</button>,
}));

let role = 'OWNER';
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role, companyId: 9 } }),
}));

function bill(over: Partial<PurchaseInvoice>): PurchaseInvoice {
  return {
    id: 5,
    number: 'PUR-0005',
    status: 'DRAFT',
    purchaseType: 'GST',
    supplierName: 'Mega Suppliers',
    invoiceDate: '2026-10-01',
    grandTotal: '100.00',
    balance: '100.00',
    taxableTotal: '100.00',
    items: [],
    ...over,
  } as PurchaseInvoice;
}

function renderPage(state?: unknown) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[{ pathname: '/purchases/history/5', state }]}>
        <Routes>
          <Route path="/purchases/history/:id" element={<PurchaseDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  registerGlobalConfirm(null);
  vi.clearAllMocks();
});

describe('PurchaseDetailPage', () => {
  it('keeps completion warnings visible after completing a draft', async () => {
    getPurchase.mockResolvedValue(bill({ status: 'DRAFT' }));
    completePurchase.mockResolvedValue(
      bill({ status: 'COMPLETED', warnings: ['Supplier bill number already used on PUR-0002.', 'ITC is unreviewed.'] }),
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /complete/i }));
    expect(await screen.findByText(/already used on PUR-0002/)).toBeInTheDocument();
    expect(screen.getByText(/ITC is unreviewed/)).toBeInTheDocument();
  });

  it('shows no warning alert when completion returns none', async () => {
    getPurchase.mockResolvedValue(bill({ status: 'DRAFT' }));
    completePurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /complete/i }));
    await waitFor(() => expect(completePurchase).toHaveBeenCalled());
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  describe('cancelling a bill (WP-2)', () => {
    const paid = {
      status: 'COMPLETED',
      payments: [
        { allocation: 1, payment: 11, number: 'PAY-1', date: '2026-10-02', mode: 'CASH', amount: '40.00' },
        { allocation: 2, payment: 12, number: 'PAY-2', date: '2026-10-03', mode: 'UPI', amount: '10.00' },
      ],
    } as Partial<PurchaseInvoice>;

    it('opens an in-app dialog and does nothing until it is confirmed', async () => {
      const nativeConfirm = vi.spyOn(window, 'confirm');
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
      expect(await screen.findByRole('dialog')).toBeInTheDocument();
      expect(nativeConfirm).not.toHaveBeenCalled();
      expect(cancelPurchase).not.toHaveBeenCalled();
    });

    it('keeping the bill closes the dialog without cancelling', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
      await userEvent.click(await within(await screen.findByRole('dialog')).findByRole('button', { name: /^cancel$/i }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      expect(cancelPurchase).not.toHaveBeenCalled();
    });

    it('cancels a bill with no payments without unlinking anything', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      cancelPurchase.mockResolvedValue(bill({ status: 'CANCELLED' }));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
      await userEvent.click(await screen.findByRole('button', { name: /cancel bill/i }));
      await waitFor(() => expect(cancelPurchase).toHaveBeenCalledTimes(1));
      expect(cancelPurchase).toHaveBeenCalledWith(5, { reverseAllocations: false });
    });

    it('explains that payments stay as supplier advance, then unlinks them', async () => {
      getPurchase.mockResolvedValue(bill(paid));
      cancelPurchase.mockResolvedValue(bill({ status: 'CANCELLED' }));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByText(/2 payment\(s\)/)).toBeInTheDocument();
      expect(within(dialog).getByText(/advance/i)).toBeInTheDocument();
      await userEvent.click(within(dialog).getByRole('button', { name: /cancel bill/i }));
      await waitFor(() => expect(cancelPurchase).toHaveBeenCalledWith(5, { reverseAllocations: true }));
      expect(await screen.findByText(/kept as supplier advance/i)).toBeInTheDocument();
    });

    it('shows the server reason when cancelling is refused', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      cancelPurchase.mockRejectedValue(new Error('Cannot cancel a purchase with completed returns.'));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
      await userEvent.click(await screen.findByRole('button', { name: /cancel bill/i }));
      expect(await screen.findByText(/completed returns/)).toBeInTheDocument();
    });
  });

  describe('bill context (WP-4)', () => {
    it('lists the payments allocated to the bill', async () => {
      getPurchase.mockResolvedValue(
        bill({
          status: 'COMPLETED',
          supplierBillNumber: 'SB-77',
          dueDate: '2026-11-01',
          payments: [{ allocation: 1, payment: 11, number: 'PAY-1', date: '2026-10-02', mode: 'CASH', amount: '40.00' }],
        } as Partial<PurchaseInvoice>),
      );
      renderPage();
      expect(await screen.findByText('PAY-1')).toBeInTheDocument();
      expect(screen.getByText(/SB-77/)).toBeInTheDocument();
      expect(screen.getByText(/2026-11-01/)).toBeInTheDocument();
    });

    it('says so when no payment is allocated yet', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED', payments: [] } as Partial<PurchaseInvoice>));
      renderPage();
      expect(await screen.findByText(/no payment is allocated/i)).toBeInTheDocument();
    });

    it('links the order, receipt and notes the bill is tied to', async () => {
      getPurchase.mockResolvedValue(
        bill({
          status: 'COMPLETED',
          relatedDocuments: {
            sourceOrders: [{ id: 3, number: 'PO-3', status: 'CONVERTED' }],
            sourceReceipts: [{ id: 4, number: 'GRN-4', status: 'COMPLETED' }],
            returns: [],
            creditNotes: [{ id: 6, number: 'PCN-6', status: 'DRAFT' }],
            debitNotes: [],
          },
        } as Partial<PurchaseInvoice>),
      );
      renderPage();
      const order = await screen.findByRole('link', { name: /PO-3/ });
      expect(order).toHaveAttribute('href', '/purchases/orders/3');
      expect(screen.getByRole('link', { name: /GRN-4/ })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /PCN-6/ })).toHaveAttribute('href', '/purchases/credit-notes/6');
    });

    it('says so when nothing is linked', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage();
      expect(await screen.findByText(/nothing is linked/i)).toBeInTheDocument();
    });

    it('downloads the PDF of a completed bill', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      downloadPurchasePdf.mockResolvedValue(new Blob(['x']));
      const createObjectURL = vi.fn(() => 'blob:x');
      Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /download pdf/i }));
      await waitFor(() => expect(downloadPurchasePdf).toHaveBeenCalledWith(5));
    });

    it('does not offer a PDF for a draft', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'DRAFT' }));
      renderPage();
      await screen.findByText('PUR-0005');
      expect(screen.queryByRole('button', { name: /download pdf/i })).not.toBeInTheDocument();
    });
  });

  describe('recording a payment from the bill (WP-4)', () => {
    it('offers Record payment only while something is owed', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED', balance: '0.00' }));
      renderPage();
      await screen.findByText('PUR-0005');
      expect(screen.queryByRole('button', { name: /record payment/i })).not.toBeInTheDocument();
    });

    it('pre-fills the balance and sends one atomic request', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED', balance: '60.00' }));
      recordPurchasePayment.mockResolvedValue(bill({ status: 'COMPLETED', balance: '0.00' }));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /record payment/i }));
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByLabelText(/^amount$/i)).toHaveValue('60.00');
      await userEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
      await waitFor(() => expect(recordPurchasePayment).toHaveBeenCalledTimes(1));
      const [id, body, opts] = recordPurchasePayment.mock.calls[0];
      expect(id).toBe(5);
      expect(body).toMatchObject({ amount: 60, mode: 'CASH' });
      expect(opts.idempotencyKey).toBeTruthy();
    });

    it('refuses an amount above what is owed before calling the server', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED', balance: '60.00' }));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /record payment/i }));
      const dialog = await screen.findByRole('dialog');
      const amount = within(dialog).getByLabelText(/^amount$/i);
      await userEvent.clear(amount);
      await userEvent.type(amount, '61');
      await userEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
      expect(await within(dialog).findByText(/between 0 and/i)).toBeInTheDocument();
      expect(recordPurchasePayment).not.toHaveBeenCalled();
    });

    it('keeps the dialog open and shows the server reason when it refuses', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED', balance: '60.00' }));
      recordPurchasePayment.mockRejectedValue(new Error('Supplier GSTIN is cancelled.'));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /record payment/i }));
      const dialog = await screen.findByRole('dialog');
      await userEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
      expect(await within(dialog).findByText(/GSTIN is cancelled/)).toBeInTheDocument();
    });
  });

  describe('who can edit (WP-4)', () => {
    it('hides Edit on a completed bill from a non-owner', async () => {
      role = 'MANAGER';
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage();
      await screen.findByText('PUR-0005');
      expect(screen.queryByRole('link', { name: /^edit$/i })).not.toBeInTheDocument();
      role = 'OWNER';
    });

    it('shows Edit on a completed bill to the owner', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage();
      expect(await screen.findByRole('link', { name: /^edit$/i })).toBeInTheDocument();
    });

    it('shows a message handed over by the page that sent the user here', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'DRAFT' }));
      renderPage({ message: 'Draft purchase bill PUR-0005 created from the order.' });
      expect(await screen.findByText(/created from the order/)).toBeInTheDocument();
    });
  });

  describe('payment the server refused after completing (WP-1)', () => {
    const retry = {
      paymentRetry: { payNow: { amount: 40, mode: 'CASH' }, message: 'Allocation 40 exceeds invoice open outstanding 10.' },
    };

    it('shows a persistent banner with the reason and the amount', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage(retry);
      expect(await screen.findByText(/payment of .*40.* was not recorded/i)).toBeInTheDocument();
      expect(screen.getByText(/exceeds invoice open outstanding 10/)).toBeInTheDocument();
    });

    it('retries through the atomic endpoint and clears the banner on success', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      recordPurchasePayment.mockResolvedValue(bill({ status: 'COMPLETED', balance: '60.00' }));
      renderPage(retry);
      await userEvent.click(await screen.findByRole('button', { name: /retry payment/i }));
      await waitFor(() => expect(recordPurchasePayment).toHaveBeenCalledTimes(1));
      expect(recordPurchasePayment.mock.calls[0][0]).toBe(5);
      expect(recordPurchasePayment.mock.calls[0][1]).toEqual({ amount: 40, mode: 'CASH' });
      expect(recordPurchasePayment.mock.calls[0][2].idempotencyKey).toBeTruthy();
      await waitFor(() => expect(screen.queryByText(/was not recorded/i)).not.toBeInTheDocument());
    });

    it('keeps the banner and shows the new reason when the retry fails', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      recordPurchasePayment.mockRejectedValue(new Error('Supplier GSTIN is cancelled.'));
      renderPage(retry);
      await userEvent.click(await screen.findByRole('button', { name: /retry payment/i }));
      expect(await screen.findByText(/Supplier GSTIN is cancelled/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry payment/i })).toBeInTheDocument();
    });

    it('can be dismissed', async () => {
      getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
      renderPage(retry);
      await userEvent.click(await screen.findByRole('button', { name: /dismiss/i }));
      expect(screen.queryByText(/was not recorded/i)).not.toBeInTheDocument();
    });
  });

  it('offers the bill check on a draft bill only, for someone who can write', async () => {
    getPurchase.mockResolvedValue(bill({ status: 'DRAFT' }));
    renderPage();
    expect(await screen.findByTestId('agent-check')).toHaveTextContent('BILL_CHECK:BILL_CHECK:5');
  });

  it('has no bill check on a completed bill', async () => {
    getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
    renderPage();
    await screen.findByText('PUR-0005');
    expect(screen.queryByTestId('agent-check')).toBeNull();
  });

  it('has no bill check for a viewer', async () => {
    role = 'VIEWER';
    getPurchase.mockResolvedValue(bill({ status: 'DRAFT' }));
    renderPage();
    await screen.findByText('PUR-0005');
    expect(screen.queryByTestId('agent-check')).toBeNull();
    role = 'OWNER';
  });
});

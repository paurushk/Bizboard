import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseDetailPage } from '@/pages/purchases/PurchaseDetailPage';
import { registerGlobalConfirm } from '@/utils/confirmBridge';
import type { PurchaseInvoice } from '@/types/domain';

const { getPurchase, completePurchase, cancelPurchase, recordPurchasePayment } = vi.hoisted(() => ({
  getPurchase: vi.fn(),
  recordPurchasePayment: vi.fn(),
  completePurchase: vi.fn(),
  cancelPurchase: vi.fn(),
}));

vi.mock('@/api/resources', () => ({ getPurchase, completePurchase, cancelPurchase, recordPurchasePayment }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
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

  it('cancel asks through the in-app dialog and does nothing when declined', async () => {
    const ask = vi.fn().mockResolvedValue(false);
    registerGlobalConfirm(ask);
    const nativeConfirm = vi.spyOn(window, 'confirm');
    getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1));
    expect(nativeConfirm).not.toHaveBeenCalled();
    expect(cancelPurchase).not.toHaveBeenCalled();
  });

  it('cancels exactly once when the in-app dialog is accepted', async () => {
    registerGlobalConfirm(vi.fn().mockResolvedValue(true));
    getPurchase.mockResolvedValue(bill({ status: 'COMPLETED' }));
    cancelPurchase.mockResolvedValue(bill({ status: 'CANCELLED' }));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(cancelPurchase).toHaveBeenCalledTimes(1));
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
});

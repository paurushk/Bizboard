import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseNoteEditorPage } from '@/pages/purchases/PurchaseNoteEditorPage';
import { registerGlobalConfirm } from '@/utils/confirmBridge';

// Purchase review: cancelling a COMPLETED note from its editor reverses ledger entries, so it asks first.

const api = vi.hoisted(() => ({
  getPurchaseCreditNote: vi.fn(),
  cancelPurchaseCreditNote: vi.fn(),
  getCompany: vi.fn(),
  getSupplier: vi.fn(),
  listPurchasesPage: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9, canCreatePurchases: true, canCancel: true },
  }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/utils/permissions', async (orig) => ({
  ...(await orig<typeof import('@/utils/permissions')>()),
  canCreatePurchases: () => true,
  canCancelDocuments: () => true,
}));
vi.mock('@/hooks/usePartySearch', () => ({
  useSupplierSearch: () => ({ options: [], setQuery: vi.fn(), isFetching: false, enabled: true }),
  useCustomerSearch: () => ({ options: [], setQuery: vi.fn(), isFetching: false, enabled: true }),
}));
vi.mock('@/api/resources', async (orig) => ({ ...(await orig<typeof import('@/api/resources')>()), ...api }));

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/purchases/credit-notes/5']}>
        <Routes>
          <Route path="/purchases/credit-notes/:id" element={<PurchaseNoteEditorPage kind="credit" />} />
          <Route path="/purchases/credit-notes" element={<div>list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('purchase note editor cancel', () => {
  afterEach(() => registerGlobalConfirm(null));

  it('asks before cancelling a completed note and does nothing when declined', async () => {
    api.getPurchaseCreditNote.mockResolvedValue({
      id: 5, number: 'PCN-1', status: 'COMPLETED', supplier: 3, noteDate: '2026-09-01', reason: 'CORRECTION_OF_INVOICE',
      items: [], subtotal: 0, discountTotal: 0, taxableTotal: 0, cgstTotal: 0, sgstTotal: 0, igstTotal: 0, roundOff: 0, grandTotal: 0,
    });
    api.getCompany.mockResolvedValue({ id: 9, name: 'Shop', isGstRegistered: false });
    api.getSupplier.mockResolvedValue({ id: 3, name: 'Acme' });
    api.listPurchasesPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    api.cancelPurchaseCreditNote.mockResolvedValue({});

    const ask = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    registerGlobalConfirm(ask);
    const user = userEvent.setup();
    mount();
    const button = await screen.findByRole('button', { name: /cancel document/i });
    await user.click(button);
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1));
    expect(api.cancelPurchaseCreditNote).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: /cancel document/i }));
    await waitFor(() => expect(api.cancelPurchaseCreditNote).toHaveBeenCalledWith(5));
  });
});

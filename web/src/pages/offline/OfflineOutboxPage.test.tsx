import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OfflineOutboxPage } from '@/pages/offline/OfflineOutboxPage';
import { t } from '@/i18n';

const state = vi.hoisted(() => ({
  user: { id: 1, companyId: 9 } as { id: number; companyId?: number } | null,
  listDrafts: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: state.user }),
}));

vi.mock('@/offline/invoiceDraftCache', () => ({
  PURCHASE_AUTOSAVE_KEY: 'purchase-editor-draft',
  listDrafts: (...args: unknown[]) => state.listDrafts(...args),
  removeDraft: vi.fn(async () => undefined),
  flushOutbox: vi.fn(async () => ({ flushed: 0, failed: 0, errors: [] })),
  isFlushableDraft: () => true,
}));

vi.mock('@/offline/flushPosCheckout', () => ({ flushPosDraft: vi.fn() }));
vi.mock('@/pages/sales/invoice/useInvoiceOffline', () => ({ flushInvoiceDraft: vi.fn() }));
vi.mock('@/pages/purchases/usePurchaseOffline', () => ({ flushPurchaseDraft: vi.fn() }));
vi.mock('@/pages/inventory/useStockOffline', () => ({ flushStockDraft: vi.fn() }));
vi.mock('@/pages/pos/printPosThermal', () => ({ printPosThermalOrWarn: vi.fn(async () => null) }));

const draft = (id: string, kind: string, extra: Record<string, unknown> = {}) => ({
  id,
  kind,
  savedAt: '2026-09-30T10:00:00.000Z',
  idempotencyKey: `key-${id}`,
  ...extra,
});

function mount() {
  return render(
    <MemoryRouter>
      <OfflineOutboxPage />
    </MemoryRouter>,
  );
}

describe('OfflineOutboxPage', () => {
  beforeEach(() => {
    state.user = { id: 1, companyId: 9 };
    state.listDrafts.mockReset();
    state.listDrafts.mockResolvedValue([]);
  });

  it('lists what is waiting to sync for the signed-in user and company', async () => {
    state.listDrafts.mockResolvedValue([draft('d-1', 'pos'), draft('d-2', 'invoice')]);
    mount();
    expect(await screen.findByText('d-1')).toBeTruthy();
    expect(screen.getByText('d-2')).toBeTruthy();
    expect(state.listDrafts).toHaveBeenCalledWith(9, 1);
    expect(screen.queryByText(t('offlineOutbox.empty'))).toBeNull();
  });

  it('says so when nothing is waiting', async () => {
    mount();
    expect(await screen.findByText(t('offlineOutbox.empty'))).toBeTruthy();
  });

  it('shows the empty message instead of failing when the stored drafts cannot be read', async () => {
    state.listDrafts.mockRejectedValue(new Error('IndexedDB blocked'));
    mount();
    expect(await screen.findByText(t('offlineOutbox.empty'))).toBeTruthy();
  });

  it('does not read any drafts when nobody is signed in to a company', async () => {
    state.user = { id: 1 };
    mount();
    expect(await screen.findByText(t('offlineOutbox.empty'))).toBeTruthy();
    expect(state.listDrafts).not.toHaveBeenCalled();
  });

  it('shows a rejected draft with the reason', async () => {
    state.listDrafts.mockResolvedValue([draft('d-9', 'invoice', { conflict: { code: 'period_closed', message: 'Period is closed' } })]);
    mount();
    expect(await screen.findByText(/Period is closed/)).toBeTruthy();
  });

  it('shows another user after the signed-in user changes', async () => {
    state.listDrafts.mockImplementation(async (_company: number, user: number) =>
      user === 1 ? [draft('mine', 'pos')] : [draft('theirs', 'pos')],
    );
    const view = mount();
    expect(await screen.findByText('mine')).toBeTruthy();

    state.user = { id: 2, companyId: 9 };
    view.rerender(
      <MemoryRouter>
        <OfflineOutboxPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('theirs')).toBeTruthy());
    expect(screen.queryByText('mine')).toBeNull();
  });
});

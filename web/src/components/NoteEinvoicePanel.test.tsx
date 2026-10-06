import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NoteEinvoicePanel } from '@/components/NoteEinvoicePanel';
import { t } from '@/i18n';
import type { SalesCreditNote, SalesDebitNote } from '@/types/domain';

const api = vi.hoisted(() => ({
  prepareCreditNoteEinvoice: vi.fn(),
  prepareDebitNoteEinvoice: vi.fn(),
  submitCreditNoteEinvoice: vi.fn(),
  submitDebitNoteEinvoice: vi.fn(),
  cancelCreditNoteEinvoice: vi.fn(),
  cancelDebitNoteEinvoice: vi.fn(),
}));

vi.mock('@/api/resources', () => api);

const credit = (id: number, extra: Record<string, unknown> = {}) =>
  ({ id, number: `CN-${id}`, einvoiceStatus: 'NONE', ...extra }) as unknown as SalesCreditNote;
const debit = (id: number) => ({ id, number: `DN-${id}`, einvoiceStatus: 'NONE' }) as unknown as SalesDebitNote;

function tree(ui: ReactElement) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>;
}

const downloadButton = () => screen.queryByRole('button', { name: t('sweep2.downloadJson') });

describe('NoteEinvoicePanel', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.prepareCreditNoteEinvoice.mockResolvedValue({ payload: { Irn: 'x' } });
    api.prepareDebitNoteEinvoice.mockResolvedValue({ payload: { Irn: 'y' } });
  });

  it('prepares the payload for a credit note and then offers its JSON', async () => {
    const onMessage = vi.fn();
    render(tree(<NoteEinvoicePanel kind="credit" note={credit(3)} onMessage={onMessage} />));
    expect(downloadButton()).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: t('einvoice.preparePayload') }));
    await waitFor(() => expect(downloadButton()).toBeTruthy());
    expect(api.prepareCreditNoteEinvoice).toHaveBeenCalledWith(3);
    expect(api.prepareDebitNoteEinvoice).not.toHaveBeenCalled();
    expect(onMessage).toHaveBeenCalled();
  });

  it('uses the debit note service for a debit note', async () => {
    render(tree(<NoteEinvoicePanel kind="debit" note={debit(8)} />));
    await userEvent.click(screen.getByRole('button', { name: t('einvoice.preparePayload') }));
    await waitFor(() => expect(api.prepareDebitNoteEinvoice).toHaveBeenCalledWith(8));
    expect(api.prepareCreditNoteEinvoice).not.toHaveBeenCalled();
  });

  it('drops the prepared payload when the page moves to a different note', async () => {
    const { rerender } = render(tree(<NoteEinvoicePanel kind="credit" note={credit(3)} />));
    await userEvent.click(screen.getByRole('button', { name: t('einvoice.preparePayload') }));
    await waitFor(() => expect(downloadButton()).toBeTruthy());

    rerender(tree(<NoteEinvoicePanel kind="credit" note={credit(4)} />));
    expect(downloadButton()).toBeNull();
  });

  it('keeps the prepared payload when the same note is shown again', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (note: SalesCreditNote) => (
      <QueryClientProvider client={client}>
        <NoteEinvoicePanel kind="credit" note={note} />
      </QueryClientProvider>
    );
    const { rerender } = render(view(credit(3)));
    await userEvent.click(screen.getByRole('button', { name: t('einvoice.preparePayload') }));
    await waitFor(() => expect(downloadButton()).toBeTruthy());

    rerender(view(credit(3, { notes: 'refreshed' })));
    expect(downloadButton()).toBeTruthy();
  });

  it('reports a refusal to the page instead of showing a payload', async () => {
    api.prepareCreditNoteEinvoice.mockRejectedValue(new Error('Note is not completed'));
    const onError = vi.fn();
    render(tree(<NoteEinvoicePanel kind="credit" note={credit(3)} onError={onError} />));
    await userEvent.click(screen.getByRole('button', { name: t('einvoice.preparePayload') }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith('Note is not completed'));
    expect(downloadButton()).toBeNull();
  });

  it('offers cancellation only once an IRN has been generated', () => {
    const { unmount } = render(tree(<NoteEinvoicePanel kind="credit" note={credit(3)} />));
    expect(screen.queryByRole('button', { name: t('sweep2.cancelIrn') })).toBeNull();
    unmount();
    render(tree(<NoteEinvoicePanel kind="credit" note={credit(3, { einvoiceStatus: 'GENERATED', irn: 'IRN-9' })} />));
    expect(screen.getByRole('button', { name: t('sweep2.cancelIrn') })).toBeTruthy();
    expect(screen.getByText(/IRN-9/)).toBeTruthy();
  });
});

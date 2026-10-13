import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RecentBillUploads } from './RecentBillUploads';

const api = vi.hoisted(() => ({
  listBillImportJobs: vi.fn(),
  cancelImport: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const job = (id: number, over: Record<string, unknown> = {}) => ({
  id,
  kind: 'SALES_BILL',
  status: 'PREVIEWED',
  fileName: `bill-${id}.png`,
  createdAt: '2026-07-05T10:00:00Z',
  ...over,
});

function show(onResume = vi.fn(), kind: 'SALES_BILL' | 'PURCHASE_BILL' = 'SALES_BILL') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <RecentBillUploads kind={kind} onResume={onResume} />
    </QueryClientProvider>,
  );
  return { ...view, onResume };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listBillImportJobs.mockResolvedValue([job(1), job(2, { fileName: 'lost-tab.pdf', status: 'FAILED' })]);
  api.cancelImport.mockResolvedValue({ id: 1, status: 'CANCELLED' });
});

describe('RecentBillUploads', () => {
  it('asks for the unfinished uploads of its own kind', async () => {
    show(vi.fn(), 'PURCHASE_BILL');
    await screen.findByText('Recent uploads');
    expect(api.listBillImportJobs).toHaveBeenCalledWith('PURCHASE_BILL');
  });

  it('lists each upload with its file name and status', async () => {
    show();
    expect(await screen.findByText(/bill-1\.png/)).toBeInTheDocument();
    expect(screen.getByText(/lost-tab\.pdf/)).toBeInTheDocument();
  });

  it('shows nothing when there is nothing to resume', async () => {
    api.listBillImportJobs.mockResolvedValue([]);
    const { container } = show();
    await waitFor(() => expect(api.listBillImportJobs).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('shows at most ten uploads', async () => {
    api.listBillImportJobs.mockResolvedValue(Array.from({ length: 14 }, (_, i) => job(i + 1)));
    show();
    await screen.findByText(/bill-1\.png/);
    expect(screen.getAllByRole('button', { name: 'Resume' })).toHaveLength(10);
  });

  it('resumes the chosen upload', async () => {
    const { onResume } = show();
    await screen.findByText(/bill-1\.png/);
    await userEvent.click(screen.getAllByRole('button', { name: 'Resume' })[1]);
    expect(onResume).toHaveBeenCalledWith(2);
  });

  it('asks before discarding, and does nothing when you back out', async () => {
    show();
    await screen.findByText(/bill-1\.png/);
    await userEvent.click(screen.getAllByRole('button', { name: 'Discard' })[0]);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Discard this upload?')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.cancelImport).not.toHaveBeenCalled();
  });

  it('discards the upload after confirming and reloads the list', async () => {
    show();
    await screen.findByText(/bill-1\.png/);
    await userEvent.click(screen.getAllByRole('button', { name: 'Discard' })[0]);
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Discard' }));
    await waitFor(() => expect(api.cancelImport).toHaveBeenCalledWith(1));
    await waitFor(() => expect(api.listBillImportJobs.mock.calls.length).toBeGreaterThan(1));
  });

  it('says why a discard failed and keeps the upload listed', async () => {
    api.cancelImport.mockRejectedValue(
      new AxiosError('x', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 400,
        data: { error: { message: 'This import can no longer be cancelled.' } },
        statusText: '',
        headers: {},
        config: {} as never,
      }),
    );
    show();
    await screen.findByText(/bill-1\.png/);
    await userEvent.click(screen.getAllByRole('button', { name: 'Discard' })[0]);
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Discard' }));
    expect(await screen.findByText('This import can no longer be cancelled.')).toBeInTheDocument();
    expect(screen.getByText(/bill-1\.png/)).toBeInTheDocument();
  });
});

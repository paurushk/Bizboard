import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockCountPage } from '@/pages/inventory/StockCountPage';

const api = vi.hoisted(() => ({
  listStockCounts: vi.fn(),
  getStockCount: vi.fn(),
  updateStockCount: vi.fn(),
  reviewStockCount: vi.fn(),
  addStockCountLine: vi.fn(),
  postStockCount: vi.fn(),
  cancelStockCount: vi.fn(),
  createStockCount: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  listWarehouses: async () => [{ id: 1, name: 'Main' }],
  listReorderLevels: async () => [],
  listBatches: async () => [],
  completeTransfer: vi.fn(),
  createReorderLevel: vi.fn(),
  listStockCounts: (...a: unknown[]) => api.listStockCounts(...a),
  getStockCount: (...a: unknown[]) => api.getStockCount(...a),
  updateStockCount: (...a: unknown[]) => api.updateStockCount(...a),
  reviewStockCount: (...a: unknown[]) => api.reviewStockCount(...a),
  addStockCountLine: (...a: unknown[]) => api.addStockCountLine(...a),
  postStockCount: (...a: unknown[]) => api.postStockCount(...a),
  cancelStockCount: (...a: unknown[]) => api.cancelStockCount(...a),
  createStockCount: (...a: unknown[]) => api.createStockCount(...a),
}));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER' } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({ useVisibleCustomFieldDefs: () => [] }));
const listDrafts = vi.hoisted(() => vi.fn());
vi.mock('@/offline/invoiceDraftCache', () => ({ enqueueDraft: vi.fn(), listDrafts: (...a: unknown[]) => listDrafts(...a) }));
const tea = { id: 9, name: 'Tea', sku: 'TEA', trackBatch: false };
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '', setProductQuery: () => undefined, options: [tea], isFetching: false,
    truncated: false, helperText: undefined, enabled: true, count: 1,
  }),
}));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));

const line = (over: Record<string, unknown>) => ({
  id: 1, product: 1, productName: 'Soap', batch: null, batchNo: null, systemQty: '10', countedQty: null,
  variance: null, heldForReview: false, skipped: false, driftSkipped: false, ...over,
});
const session = (over: Record<string, unknown> = {}) => ({
  id: 7, warehouse: 1, warehouseName: 'Main', status: 'DRAFT', blind: false, notes: '',
  lines: [line({ id: 1, productName: 'Soap' }), line({ id: 2, product: 2, productName: 'Rice' })],
  ...over,
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StockCountPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openSession(user: ReturnType<typeof userEvent.setup>, opened = session()) {
  api.listStockCounts.mockResolvedValue([{ id: 7, warehouseName: 'Main', status: opened.status, notes: '' }]);
  api.getStockCount.mockResolvedValue(opened);
  renderPage();
  await user.click(await screen.findByRole('button', { name: opened.status === 'POSTED' ? 'View' : 'Count' }));
  return screen.findByRole('dialog');
}

/** Answers the in-app confirmation (the window.confirm replacement), checking what it says. */
async function answerConfirm(user: ReturnType<typeof userEvent.setup>, ok: boolean, text: string) {
  const dialog = await screen.findByRole('dialog', { name: 'Confirm' });
  expect(dialog.textContent).toContain(text);
  await user.click(within(dialog).getByRole('button', { name: ok ? 'Confirm' : 'Cancel' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Confirm' })).toBeNull());
}

describe('StockCountPage', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    listDrafts.mockReset();
    listDrafts.mockResolvedValue([]);
  });

  it('counts a scanned barcode and says so when the code is not in this count', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(
      user,
      session({ lines: [line({ id: 1, productName: 'Soap', productSku: 'SOAP', productBarcode: '890100' })] }),
    );
    const box = within(dialog).getByLabelText('Scan or type a barcode');
    await user.type(box, '890100{Enter}');
    await user.type(box, '890100{Enter}');
    expect((within(dialog).getByLabelText('Counted') as HTMLInputElement).value).toBe('2');
    await user.type(box, 'ZZZ{Enter}');
    expect(within(dialog).getByText('No line with the code ZZZ in this count.')).toBeTruthy();
  });

  it('says what a posted count did and links to the stock ledger', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8' }), line({ id: 2, product: 2, productName: 'Rice', countedQty: '10' }),
    ] }));
    api.reviewStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8', variance: '-2', varianceValueEstimate: '-20.00' }),
      line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', variance: '0', varianceValueEstimate: '0.00' }),
    ] }));
    api.postStockCount.mockResolvedValue(session({ status: 'POSTED', warehouse: 1, lines: [
      line({ id: 1, countedQty: '8', variance: '-2', varianceValueEstimate: '-20.00' }),
      line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', variance: '0', varianceValueEstimate: '0.00' }),
    ] }));
    const user = userEvent.setup();
    const dialog = await openSession(user);
    const [soap, rice] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '8');
    await user.type(rice, '10');
    await user.click(within(dialog).getByRole('button', { name: 'Review differences' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Post variances' }));
    await answerConfirm(user, true, 'items change');
    expect(await screen.findByText(/Count posted: 1 lines adjusted/)).toBeTruthy();
    expect((await screen.findByRole('link', { name: 'View stock ledger' })).getAttribute('href')).toBe('/inventory/ledger?warehouse=1');
  });

  it('shows a Queued chip for a count saved on this device and not sent yet', async () => {
    listDrafts.mockResolvedValue([{ kind: 'stock_count', payload: { sessionId: 7 }, idempotencyKey: 'stock-count-7' }]);
    api.listStockCounts.mockResolvedValue([{ id: 7, warehouseName: 'Main', status: 'COUNTED', notes: '' }]);
    renderPage();
    expect(await screen.findByText('Queued')).toBeTruthy();
    expect(await screen.findByText(/· 1 pending/)).toBeTruthy();
  });

  it('asks which lot a scanned code was when the item has several lots', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(
      user,
      session({
        lines: [
          line({ id: 1, productName: 'Milk', batchNo: 'L1', productSku: 'MILK', productBarcode: '555' }),
          line({ id: 2, productName: 'Milk', batchNo: 'L2', productSku: 'MILK', productBarcode: '555' }),
        ],
      }),
    );
    await user.type(within(dialog).getByLabelText('Scan or type a barcode'), '555{Enter}');
    const chooser = await screen.findByRole('dialog', { name: 'Which lot did you count?' });
    await user.click(within(chooser).getByRole('button', { name: /Milk · L2/ }));
    const boxes = within(dialog).getAllByLabelText('Counted') as HTMLInputElement[];
    expect(boxes.map((b) => b.value)).toEqual(['', '1']);
  });

  it('sends only the lines that changed, each with the version it was loaded at', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'DRAFT', lines: [
      line({ id: 1, countedQty: '8', version: 1 }), line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', version: 3 }),
    ] }));
    const user = userEvent.setup();
    const dialog = await openSession(user, session({
      lines: [line({ id: 1, version: 0 }), line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', version: 3 })],
    }));
    await user.type(within(dialog).getAllByLabelText('Counted')[0], '8');
    await user.click(within(dialog).getByRole('button', { name: 'Save counts' }));
    await waitFor(() => expect(api.updateStockCount).toHaveBeenCalledTimes(1));
    expect(api.updateStockCount).toHaveBeenCalledWith(7, {
      lines: [{ id: 1, countedQty: '8', skipped: false, version: 0 }],
    });
  });

  it('does not call the server when nothing changed', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(user);
    await user.click(within(dialog).getByRole('button', { name: 'Save counts' }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.updateStockCount).not.toHaveBeenCalled();
  });

  it('says so, and shows the other counter figure, when a line was changed by someone else', async () => {
    const refused = new AxiosError('conflict');
    refused.response = {
      status: 409, statusText: '', headers: {}, config: {} as never,
      data: { error: { code: 'STOCK_COUNT_LINE_CHANGED', details: { lines: [
        { lineId: 1, productName: 'Soap', countedQty: '9', version: 2 },
      ] } } },
    };
    api.updateStockCount.mockRejectedValue(refused);
    const user = userEvent.setup();
    const dialog = await openSession(user);
    await user.type(within(dialog).getAllByLabelText('Counted')[0], '7');
    api.getStockCount.mockResolvedValue(session({ lines: [
      line({ id: 1, countedQty: '9', version: 2 }), line({ id: 2, product: 2, productName: 'Rice' }),
    ] }));
    await user.click(within(dialog).getByRole('button', { name: 'Save counts' }));
    expect(await within(dialog).findByText(/Another counter changed Soap/)).toBeTruthy();
    await waitFor(() => expect((within(dialog).getAllByLabelText('Counted')[0] as HTMLInputElement).value).toBe('9'));
  });

  it('lets each drifted line have its own answer and posts them together', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8' }), line({ id: 2, product: 2, productName: 'Rice', countedQty: '10' }),
    ] }));
    api.reviewStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8', variance: '-2', varianceValueEstimate: '-20.00' }),
      line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', variance: '0', varianceValueEstimate: '0.00' }),
    ] }));
    const drift = new AxiosError('conflict');
    drift.response = {
      status: 409, statusText: '', headers: {}, config: {} as never,
      data: { error: { code: 'STOCK_COUNT_CONFLICT', details: { conflicts: [
        { lineId: 1, productName: 'Soap', serverQty: '5', localQty: '8', snapshotQty: '10' },
        { lineId: 2, productName: 'Rice', serverQty: '9', localQty: '10', snapshotQty: '10' },
      ] } } },
    };
    api.postStockCount.mockRejectedValueOnce(drift).mockResolvedValue({});
    const user = userEvent.setup();
    const dialog = await openSession(user);
    const [soap, rice] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '8');
    await user.type(rice, '10');
    await user.click(within(dialog).getByRole('button', { name: 'Review differences' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Post variances' }));
    await answerConfirm(user, true, 'items change');

    const modal = await screen.findByRole('dialog', { name: 'Stock changed on the server' });
    const answers = within(modal).getAllByLabelText('What should happen to this line?');
    expect(answers).toHaveLength(2);
    await user.click(answers[0]);
    await user.click(await screen.findByRole('option', { name: /Leave this line alone/ }));
    await user.click(within(modal).getByRole('button', { name: 'Post count' }));
    await waitFor(() =>
      expect(api.postStockCount).toHaveBeenLastCalledWith(
        7,
        { resolutions: { 1: 'KEEP_SERVER', 2: 'ADJUST_FOR_MOVEMENTS' }, recheckedLineIds: [] },
        { idempotencyKey: expect.any(String) },
      ),
    );
  });

  it('marks a line the counter confirmed from the system quantity in the review', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '10', filledFromSystem: true }), line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', filledFromSystem: true }),
    ] }));
    api.reviewStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '10', variance: '0', varianceValueEstimate: '0.00', filledFromSystem: true }),
      line({ id: 2, product: 2, productName: 'Rice', countedQty: '9', variance: '-1', varianceValueEstimate: '-10.00', filledFromSystem: false }),
    ] }));
    const user = userEvent.setup();
    const dialog = await openSession(user);
    await user.click(within(dialog).getByRole('button', { name: 'Count equals system' }));
    await user.click(within(dialog).getByRole('button', { name: 'Review differences' }));
    await waitFor(() => expect(api.updateStockCount).toHaveBeenCalled());
    const sent = api.updateStockCount.mock.calls[0][1] as { lines: Array<{ filledFromSystem?: boolean }> };
    expect(sent.lines.every((row) => row.filledFromSystem === true)).toBe(true);
    expect(await within(dialog).findByText('Not counted: system quantity')).toBeTruthy();
  });

  it('fills every open line with the system quantity in one click', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(user);
    await user.click(within(dialog).getByRole('button', { name: 'Count equals system' }));
    const boxes = within(dialog).getAllByLabelText('Counted') as HTMLInputElement[];
    expect(boxes.map((b) => b.value)).toEqual(['10', '10']);
    expect(within(dialog).queryByRole('button', { name: 'Count equals system' })).toBeNull();
  });

  it('does not offer "count equals system" in a blind count, which hides the system quantity', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(
      user,
      session({ blind: true, lines: [line({ id: 1, systemQty: undefined })] }),
    );
    expect(within(dialog).queryByRole('button', { name: 'Count equals system' })).toBeNull();
  });

  it('will not offer the review until every line is counted or skipped', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(user);
    const review = within(dialog).getByRole('button', { name: 'Review differences' }) as HTMLButtonElement;
    expect(review.disabled).toBe(true);
    expect(within(dialog).getByText('2 lines still need a count or a skip.')).toBeTruthy();
    const [soap, rice] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '9');
    await user.type(rice, '10');
    expect(review.disabled).toBe(false);
  });

  it('shows every difference before posting and holds large ones until they are rechecked', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8' }), line({ id: 2, product: 2, productName: 'Rice', countedQty: '10' }),
    ] }));
    api.reviewStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8', variance: '-2', varianceValueEstimate: '-10000.00', needsRecheck: true }),
      line({ id: 2, product: 2, productName: 'Rice', countedQty: '10', variance: '0', varianceValueEstimate: '0.00' }),
    ] }));
    api.postStockCount.mockResolvedValue({});
    const user = userEvent.setup();
    const dialog = await openSession(user);
    const [soap, rice] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '8');
    await user.type(rice, '10');
    await user.click(within(dialog).getByRole('button', { name: 'Review differences' }));

    expect(await within(dialog).findByText(/1 items differ/)).toBeTruthy();
    expect(within(dialog).getByText(/1 lines are large differences/)).toBeTruthy();
    expect(api.updateStockCount).toHaveBeenCalledWith(7, {
      lines: [
        { id: 1, countedQty: '8', skipped: false },
        { id: 2, countedQty: '10', skipped: false },
      ],
    });
    const post = within(dialog).getByRole('button', { name: 'Post variances' }) as HTMLButtonElement;
    expect(post.disabled).toBe(true);
    await user.click(within(dialog).getByRole('checkbox', { name: 'Rechecked' }));
    expect(post.disabled).toBe(false);
    await user.click(post);
    await answerConfirm(user, true, '1 items change');
    await waitFor(() => expect(api.postStockCount).toHaveBeenCalledWith(7, { recheckedLineIds: [1] }, { idempotencyKey: expect.any(String) }));
  });

  it('says a count is waiting for the owner when the server holds it for approval', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [line({ id: 1, countedQty: '8' })] }));
    api.reviewStockCount.mockResolvedValue(session({ status: 'COUNTED', lines: [
      line({ id: 1, countedQty: '8', variance: '-2', varianceValueEstimate: '-500.00', needsRecheck: false }),
    ] }));
    api.postStockCount.mockResolvedValue({ status: 'PENDING', approvalId: 9 });
    const user = userEvent.setup();
    const dialog = await openSession(user);
    const [soap, rice] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '8');
    await user.type(rice, '10');
    await user.click(within(dialog).getByRole('button', { name: 'Review differences' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Post variances' }));
    await answerConfirm(user, true, '1 items change');
    expect(await screen.findByText(/waiting for the owner to approve/i)).toBeTruthy();
  });

  it('lets a part count skip the lines it is not counting', async () => {
    api.updateStockCount.mockResolvedValue(session({ status: 'COUNTED' }));
    api.reviewStockCount.mockResolvedValue(session({ status: 'COUNTED' }));
    const user = userEvent.setup();
    const dialog = await openSession(user);
    const [soap] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '9');
    await user.click(within(dialog).getByRole('button', { name: 'Skip all uncounted' }));
    const review = within(dialog).getByRole('button', { name: 'Review differences' }) as HTMLButtonElement;
    expect(review.disabled).toBe(false);
    await user.click(review);
    await waitFor(() =>
      expect(api.updateStockCount).toHaveBeenCalledWith(7, {
        lines: [
          { id: 1, countedQty: '9', skipped: false },
          { id: 2, countedQty: null, skipped: true },
        ],
      }),
    );
  });

  it('counts an item that is not on the sheet', async () => {
    api.addStockCountLine.mockResolvedValue(session());
    const user = userEvent.setup();
    const dialog = await openSession(user);
    await user.click(within(dialog).getByRole('combobox', { name: 'Item' }));
    await user.click(await screen.findByRole('option', { name: /Tea/ }));
    await user.type(within(dialog).getByLabelText('Counted quantity'), '4');
    await user.click(within(dialog).getByRole('button', { name: 'Add to count' }));
    await waitFor(() =>
      expect(api.addStockCountLine).toHaveBeenCalledWith(7, { product: 9, batch: undefined, countedQty: '4' }),
    );
  });

  it('asks before cancelling a count and before closing with typed counts', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(user);
    await user.click(within(dialog).getByRole('button', { name: 'Cancel count' }));
    await answerConfirm(user, false, 'Nothing has been posted');
    expect(api.cancelStockCount).not.toHaveBeenCalled();

    const [soap] = within(dialog).getAllByLabelText('Counted');
    await user.type(soap, '3');
    await user.click(within(dialog).getByRole('button', { name: 'Close' }));
    await answerConfirm(user, false, 'Close without saving the counts you typed?');
    expect(screen.getByRole('dialog', { name: /count/i })).toBeTruthy();
  });

  it('says which lines of a posted count were not reconciled', async () => {
    const user = userEvent.setup();
    const dialog = await openSession(
      user,
      session({ status: 'POSTED', lines: [line({ id: 1, countedQty: '8', driftSkipped: true }), line({ id: 2, countedQty: '10' })] }),
    );
    expect(within(dialog).getByText(/1 lines were left out because stock moved/)).toBeTruthy();
    expect(within(dialog).getByText('Not reconciled')).toBeTruthy();
  });

  it('can start a blind count', async () => {
    api.listStockCounts.mockResolvedValue([]);
    api.createStockCount.mockResolvedValue(session({ blind: true }));
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'New count' }));
    const create = await screen.findByRole('dialog');
    await user.click(within(create).getByRole('combobox', { name: 'Godown' }));
    await user.click(await screen.findByRole('option', { name: 'Main' }));
    await user.click(within(create).getByRole('checkbox', { name: /Blind count/ }));
    await user.click(within(create).getByRole('button', { name: 'Start count' }));
    await waitFor(() => expect(api.createStockCount).toHaveBeenCalledWith({ warehouse: 1, notes: '', blind: true }));
  });
});

describe('StockCountPage autosave', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
    listDrafts.mockReset();
    listDrafts.mockResolvedValue([]);
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('saves the counts by itself a few seconds after the last edit', async () => {
    api.updateStockCount.mockResolvedValue(session({ lines: [
      line({ id: 1, countedQty: '8', version: 1 }), line({ id: 2, product: 2, productName: 'Rice' }),
    ] }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openSession(user);
    await user.type(within(dialog).getAllByLabelText('Counted')[0], '8');
    expect(api.updateStockCount).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/saves by itself/)).toBeTruthy();
    await vi.advanceTimersByTimeAsync(5200);
    await waitFor(() => expect(api.updateStockCount).toHaveBeenCalledTimes(1));
    expect(api.updateStockCount).toHaveBeenCalledWith(7, {
      lines: [{ id: 1, countedQty: '8', skipped: false, version: undefined }],
    });
    expect(await within(dialog).findByText(/^Saved /)).toBeTruthy();
  });

  it('keeps a figure typed while a save is in flight', async () => {
    let finish: (value: unknown) => void = () => undefined;
    api.updateStockCount.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openSession(user);
    const [soap, rice] = within(dialog).getAllByLabelText('Counted') as HTMLInputElement[];
    await user.type(soap, '8');
    await vi.advanceTimersByTimeAsync(5200);
    await waitFor(() => expect(api.updateStockCount).toHaveBeenCalledTimes(1));
    await user.type(rice, '6'); // typed after the save left
    finish(session({ lines: [
      line({ id: 1, countedQty: '8', version: 1 }), line({ id: 2, product: 2, productName: 'Rice' }),
    ] }));
    // The save landed, and the figure typed after it left is still there and still waiting to be saved.
    await waitFor(() => expect(within(dialog).getByText(/saves by itself/)).toBeTruthy());
    expect((within(dialog).getAllByLabelText('Counted')[1] as HTMLInputElement).value).toBe('6');
  });

  it('says the counts are not saved when the background save fails, without an error box', async () => {
    api.updateStockCount.mockRejectedValue(new Error('Network Error'));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openSession(user);
    await user.type(within(dialog).getAllByLabelText('Counted')[0], '8');
    await vi.advanceTimersByTimeAsync(5200);
    expect(await within(dialog).findByText(/Not saved yet\. It tries again/)).toBeTruthy();
    expect(within(dialog).queryByRole('alert')).toBeNull();
  });
});


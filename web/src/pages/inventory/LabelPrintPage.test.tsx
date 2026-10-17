import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LabelPrintPage } from '@/pages/inventory/LabelPrintPage';
import type { Product } from '@/types/domain';

const PRODUCT: Product = {
  id: 1,
  name: 'H&S Basic Cool',
  sku: 'SHMP-100',
  barcode: '8901030123456',
  sellingPrice: '120',
  mrp: '150',
} as Product;

const setProductQuery = vi.fn();
const getProduct = vi.hoisted(() => vi.fn());
const listMissingBarcode = vi.hoisted(() => vi.fn());
const downloadLabelsZpl = vi.hoisted(() => vi.fn());
const generateBarcode = vi.hoisted(() => vi.fn());
const downloadLabelZpl = vi.hoisted(() => vi.fn());
const listBatches = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  getProduct: (...a: unknown[]) => getProduct(...a),
  listMissingBarcode: (...a: unknown[]) => listMissingBarcode(...a),
  downloadLabelsZpl: (...a: unknown[]) => downloadLabelsZpl(...a),
  generateBarcode: (...a: unknown[]) => generateBarcode(...a),
  downloadLabelZpl: (...a: unknown[]) => downloadLabelZpl(...a),
  listBatches: (...a: unknown[]) => listBatches(...a),
}));

const auth = vi.hoisted(() => ({ role: 'OWNER', canManageInventory: false }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1, role: auth.role, canManageInventory: auth.canManageInventory } }),
}));

vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '',
    setProductQuery,
    options: [PRODUCT],
    isFetching: false,
    truncated: false,
    helperText: undefined,
    enabled: true,
    count: 1,
  }),
}));

function wrap(ui: ReactElement, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LabelPrintPage — QOS-0047', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.role = 'OWNER';
    auth.canManageInventory = false;
  });

  it('shows the empty state and a disabled print button with no products added', () => {
    wrap(<LabelPrintPage />);
    expect(screen.getByText('Add a product to start building a label sheet.')).toBeTruthy();
    const printButton = screen.getByRole('button', { name: /print 0 label/i });
    expect(printButton).toBeDisabled();
  });

  it('adding a product renders one label card with its barcode value and price', async () => {
    const { container } = wrap(<LabelPrintPage />);
    const input = screen.getByLabelText(/add a product/i);
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'H&S' } });

    const option = await screen.findByText('H&S Basic Cool (SHMP-100)');
    fireEvent.click(option);

    await waitFor(() => {
      expect(container.querySelectorAll('.label-card')).toHaveLength(1);
    });
    // Selecting adds the row immediately and clears the box for the next
    // scan — guards against the picked label getting stuck in the box.
    expect(input).toHaveValue('');
    // MRP is preferred over selling price on the label.
    expect(screen.getByText(/150/)).toBeTruthy();
    const printButton = screen.getByRole('button', { name: /print 1 label/i });
    expect(printButton).not.toBeDisabled();
  });

  it('raising copies to 3 renders 3 label cards', async () => {
    const { container } = wrap(<LabelPrintPage />);
    const input = screen.getByLabelText(/add a product/i);
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'H&S' } });
    fireEvent.click(await screen.findByText('H&S Basic Cool (SHMP-100)'));
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(1));

    const copiesInput = screen.getByDisplayValue('1');
    fireEvent.change(copiesInput, { target: { value: '3' } });

    await waitFor(() => {
      expect(container.querySelectorAll('.label-card')).toHaveLength(3);
    });
    expect(screen.getByRole('button', { name: /print 3 label/i })).toBeTruthy();
  });

  async function addPrimary(user: ReturnType<typeof userEvent.setup>) {
    const input = screen.getByLabelText(/add a product/i);
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: 'H&S' } });
    fireEvent.click(await screen.findByText('H&S Basic Cool (SHMP-100)'));
    return user;
  }

  it('picking the same item again adds one more copy and says so', async () => {
    const { container } = wrap(<LabelPrintPage />);
    const user = userEvent.setup();
    await addPrimary(user);
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(1));
    await addPrimary(user);
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(2));
    expect(screen.getByText('Added one more copy of H&S Basic Cool.')).toBeTruthy();
  });

  it('never prints zero on the label when the MRP is not set', async () => {
    PRODUCT.mrp = '0';
    try {
      const { container } = wrap(<LabelPrintPage />);
      await addPrimary(userEvent.setup());
      await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(1));
      expect(container.querySelector('.label-card')?.textContent).toContain('120');
    } finally {
      PRODUCT.mrp = '150';
    }
  });

  it('caps copies at the most the page will print', async () => {
    wrap(<LabelPrintPage />);
    await addPrimary(userEvent.setup());
    const copies = await screen.findByDisplayValue('1');
    fireEvent.change(copies, { target: { value: '99999' } });
    await waitFor(() => expect(screen.getByDisplayValue('200')).toBeTruthy());
    expect(screen.getByText('Most 200 at a time')).toBeTruthy();
  });

  it('resizes the label', async () => {
    const user = userEvent.setup();
    const { container } = wrap(<LabelPrintPage />);
    await addPrimary(user);
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(1));
    await user.click(screen.getByRole('combobox', { name: 'Label size' }));
    await user.click(await screen.findByRole('option', { name: /Large/ }));
    await waitFor(() => expect(getComputedStyle(container.querySelector('.label-card') as Element).width).toBe('4in'));
  });

  it('loads the items of a purchase bill with a label for each unit received', async () => {
    getProduct.mockImplementation(async (id: number) => ({ ...PRODUCT, id, name: `Item ${id}`, sku: `S${id}` }));
    const { container } = wrap(<LabelPrintPage />, '/inventory/labels?items=5:3,6:2');
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(5));
    expect(screen.getByText(/2 items added from the purchase bill/)).toBeTruthy();
  });

  it('adds the items that have no barcode and says how many were left out', async () => {
    listMissingBarcode.mockResolvedValue({
      count: 250,
      results: [{ ...PRODUCT, id: 7, name: 'Loose rice', sku: 'R7', barcode: '', status: 'ACTIVE' }],
    });
    const { container } = wrap(<LabelPrintPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Add all items without a barcode' }));
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(1));
    expect(screen.getByText(/1 of 250 items with no barcode added/)).toBeTruthy();
  });

  it('gives the sheet items without a barcode one, after asking, and shows it on the label', async () => {
    listMissingBarcode.mockResolvedValue({
      count: 1,
      results: [{ ...PRODUCT, id: 7, name: 'Loose rice', sku: 'R7', barcode: '', status: 'ACTIVE' }],
    });
    generateBarcode.mockResolvedValue({ barcode: 'BB000100000042' });
    const user = userEvent.setup();
    wrap(<LabelPrintPage />);
    await user.click(screen.getByRole('button', { name: 'Add all items without a barcode' }));
    await user.click(await screen.findByRole('button', { name: 'Give 1 items a barcode' }));
    const confirm = await screen.findByRole('dialog', { name: 'Confirm' });
    expect(confirm.textContent).toContain('never reused');
    await user.click(within(confirm).getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(generateBarcode).toHaveBeenCalledWith(7));
    expect(await screen.findByText('1 items now have a barcode.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Give \d+ items a barcode/ })).toBeNull();
  });

  it('lets a salesperson print labels but not change the items', async () => {
    auth.role = 'SALES_STAFF';
    listMissingBarcode.mockResolvedValue({
      count: 1,
      results: [{ ...PRODUCT, id: 7, name: 'Loose rice', sku: 'R7', barcode: '', status: 'ACTIVE' }],
    });
    const user = userEvent.setup();
    const { container } = wrap(<LabelPrintPage />);
    await user.click(screen.getByRole('button', { name: 'Add all items without a barcode' }));
    await waitFor(() => expect(container.querySelectorAll('.label-card')).toHaveLength(1));
    expect(screen.queryByRole('button', { name: /Give \d+ items a barcode/ })).toBeNull();
  });

  it('warns on a row whose code cannot be printed as a barcode', async () => {
    const original = PRODUCT.barcode;
    PRODUCT.barcode = 'चाय-1';
    try {
      wrap(<LabelPrintPage />);
      await addPrimary(userEvent.setup());
      expect(await screen.findByText('Code cannot be a barcode')).toBeTruthy();
    } finally {
      PRODUCT.barcode = original;
    }
  });

  it('sends the chosen size and lot with the thermal file, and can send every row as one file', async () => {
    downloadLabelZpl.mockResolvedValue({ url: 'blob:zpl' });
    downloadLabelsZpl.mockResolvedValue({ url: 'blob:all' });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const user = userEvent.setup();
    wrap(<LabelPrintPage />);
    await addPrimary(user);
    await user.click(screen.getByRole('combobox', { name: 'Label size' }));
    await user.click(await screen.findByRole('option', { name: /Large/ }));
    await user.click(screen.getByRole('button', { name: 'ZPL file' }));
    await waitFor(() => expect(downloadLabelZpl).toHaveBeenCalledWith(1, 1, { size: 'large', batch: null }));
    await user.click(screen.getByRole('button', { name: 'Download all as one ZPL file' }));
    await waitFor(() => expect(downloadLabelsZpl).toHaveBeenCalledWith([{ product: 1, copies: 1, batch: null }], { size: 'large' }));
    click.mockRestore();
  });

  it('a sticker-sheet template lays labels out on a grid, has no ZPL, and can print a test page', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const user = userEvent.setup();
    const { container } = wrap(<LabelPrintPage />);
    await addPrimary(user);
    await user.click(screen.getByRole('combobox', { name: 'Label size' }));
    await user.click(await screen.findByRole('option', { name: /3 x 8/ }));
    await waitFor(() => expect(getComputedStyle(container.querySelector('.label-card') as Element).width).toBe('70mm'));
    expect(getComputedStyle(container.querySelector('.label-sheet') as Element).display).toBe('grid');
    expect(screen.getByRole('button', { name: 'ZPL file' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Print a test page' }));
    await waitFor(() => expect(print).toHaveBeenCalledTimes(1));
    print.mockRestore();
  });

  it('downloads a ZPL file for the thermal printer, limited to what the server allows', async () => {
    downloadLabelZpl.mockResolvedValue({ url: 'blob:zpl' });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    wrap(<LabelPrintPage />);
    await addPrimary(userEvent.setup());
    fireEvent.change(await screen.findByDisplayValue('1'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: 'ZPL file' }));
    await waitFor(() => expect(downloadLabelZpl).toHaveBeenCalledWith(1, 50, { size: 'small', batch: null }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    click.mockRestore();
  });
});

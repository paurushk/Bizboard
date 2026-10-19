import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { PriceListsPage } from '@/pages/settings/PriceListsPage';

vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    options: [
      { id: 7, name: 'Basmati Rice', sku: 'RICE-1' },
      { id: 8, name: 'Toor Dal', sku: 'DAL-1' },
    ],
    isFetching: false,
    setProductQuery: vi.fn(),
    helperText: '',
    productQuery: '',
    truncated: false,
    enabled: true,
    count: 2,
  }),
}));

const api = vi.hoisted(() => ({
  listPriceLists: vi.fn(),
  createPriceList: vi.fn(),
  updatePriceList: vi.fn(),
  listPriceListCustomers: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const WHOLESALE = {
  id: 1,
  name: 'Wholesale',
  isActive: true,
  itemCount: 1,
  customerCount: 2,
  items: [{ product: 7, productName: 'Basmati Rice', productSku: 'RICE-1', minQty: '1', maxQty: '10', unitPrice: '90', discountPct: '5' }],
};
const RETAIL = { id: 2, name: 'Retail', isActive: true, itemCount: 0, customerCount: 0, items: [] };
const OLD = { id: 3, name: 'Old', isActive: false, itemCount: 0, customerCount: 3, items: [] };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PriceListsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const rowOf = async (text: string) => (await screen.findByText(text)).closest('tr') as HTMLElement;

describe('PriceListsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listPriceLists.mockResolvedValue([WHOLESALE, RETAIL, OLD]);
    api.updatePriceList.mockResolvedValue({});
    api.listPriceListCustomers.mockResolvedValue([{ id: 1, name: 'Amit Traders' }, { id: 2, name: 'Zed Stores' }]);
  });

  it('shows each list with its slab and customer counts and whether it is on', async () => {
    renderPage();
    const wholesale = await rowOf('Wholesale');
    expect(within(wholesale).getByText(t('priceLists.chipOn'))).toBeTruthy();
    expect(within(await rowOf('Old')).getByText(t('priceLists.chipOff'))).toBeTruthy();
    expect(within(wholesale).getAllByText('1').length).toBeGreaterThan(0);
    expect(within(wholesale).getAllByText('2').length).toBeGreaterThan(0);
  });

  it('switches off a list nobody uses straight away', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Retail')).getByRole('button', { name: t('priceLists.switchOff') }));
    expect(api.updatePriceList).toHaveBeenCalledWith(2, { is_active: false });
    expect(api.listPriceListCustomers).not.toHaveBeenCalled();
  });

  it('names the customers before switching off a list they use, and then confirms', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Wholesale')).getByRole('button', { name: t('priceLists.switchOff') }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(t('priceLists.offBody', { count: '2' }), { exact: false })).toBeTruthy();
    expect(within(dialog).getByText(/Amit Traders, Zed Stores/)).toBeTruthy();
    expect(api.updatePriceList).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: t('priceLists.switchOff') }));
    await waitFor(() =>
      expect(api.updatePriceList).toHaveBeenCalledWith(1, { is_active: false, confirm_customers: true }),
    );
  });

  it('switches a list back on', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Old')).getByRole('button', { name: t('priceLists.switchOn') }));
    expect(api.updatePriceList).toHaveBeenCalledWith(3, { is_active: true });
  });

  it('shows the server reason if a switch-off is refused', async () => {
    api.updatePriceList.mockRejectedValueOnce(new Error('3 customer(s) use this price list.'));
    renderPage();
    await userEvent.click(within(await rowOf('Retail')).getByRole('button', { name: t('priceLists.switchOff') }));
    expect(await screen.findByText(/3 customer\(s\) use this price list/)).toBeTruthy();
  });

  it('shows existing slabs with the item name, and keeps a slab discount when saving', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Wholesale')).getByRole('button', { name: t('priceLists.editSlabs') }));
    const dialog = await screen.findByRole('dialog');
    expect((within(dialog).getByLabelText(t('sweep.product')) as HTMLInputElement).value).toBe('Basmati Rice (RICE-1)');
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.saveSlabs') }));
    await waitFor(() => expect(api.updatePriceList).toHaveBeenCalled());
    expect(api.updatePriceList.mock.calls[0][1].items).toEqual([
      { product: 7, minQty: 1, maxQty: 10, unitPrice: 90, discountPct: 5 },
    ]);
  });

  it('picks an item for a new slab through the search, not a fixed first page', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Retail')).getByRole('button', { name: t('priceLists.editSlabs') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.addSlab') }));
    await userEvent.click(within(dialog).getByLabelText(t('sweep.product')));
    await userEvent.click(await screen.findByRole('option', { name: /Toor Dal/ }));
    await userEvent.type(within(dialog).getByLabelText(t('sweep.unitPrice')), '120');
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.saveSlabs') }));
    await waitFor(() => expect(api.updatePriceList).toHaveBeenCalled());
    expect(api.updatePriceList.mock.calls[0][1].items[0]).toMatchObject({ product: 8, unitPrice: 120, minQty: 1, maxQty: null });
  });

  it('lists every problem at once and saves nothing until they are fixed', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Retail')).getByRole('button', { name: t('priceLists.editSlabs') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.addSlab') }));
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.saveSlabs') }));
    expect(await within(dialog).findByText(t('priceLists.problemProduct', { n: '1' }))).toBeTruthy();
    expect(within(dialog).getByText(t('priceLists.problemPrice', { n: '1' }))).toBeTruthy();
    expect(api.updatePriceList).not.toHaveBeenCalled();
  });

  it('says a slab overlaps another for the same item', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Wholesale')).getByRole('button', { name: t('priceLists.editSlabs') }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.addSlab') }));
    const products = within(dialog).getAllByLabelText(t('sweep.product'));
    await userEvent.click(products[1]);
    await userEvent.click(await screen.findByRole('option', { name: /Basmati Rice/ }));
    await userEvent.type(within(dialog).getAllByLabelText(t('sweep.unitPrice'))[1], '85');
    await userEvent.click(within(dialog).getByRole('button', { name: t('sweep2.saveSlabs') }));
    expect(await within(dialog).findByText(t('priceLists.problemOverlap', { n: '2' }))).toBeTruthy();
  });

  it('shows an error with Retry when the lists cannot load', async () => {
    api.listPriceLists.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });
});

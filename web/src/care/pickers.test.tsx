import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';
import { CatalogPicker, InvoicePicker, WarehousePicker } from './pickers';

const resources = vi.hoisted(() => ({ listProductsPage: vi.fn(), listSalesInvoicesPage: vi.fn(), listWarehouses: vi.fn() }));
vi.mock('@/api/resources', () => resources);

function show(element: React.ReactElement) {
  return renderRoutes([{ path: '/', element }], '/');
}

beforeEach(() => {
  vi.clearAllMocks();
  resources.listProductsPage.mockResolvedValue({ results: [{ id: 3, name: 'Brake pad', sku: 'BP-1' }], count: 1, next: null, previous: null });
  resources.listSalesInvoicesPage.mockResolvedValue({ results: [{ id: 30, number: 'INV-30', invoiceDate: '2026-10-01' }], count: 1, next: null, previous: null });
});

describe('pickers', () => {
  it('find parts and services by name from separate lists', async () => {
    const user = userEvent.setup();
    show(<CatalogPicker kind="GOODS" value={null} onChange={() => undefined} />);
    await user.click(screen.getByRole('combobox', { name: 'Part' }));
    expect(await screen.findByRole('option', { name: 'Brake pad · BP-1' })).toBeInTheDocument();
    expect(resources.listProductsPage).toHaveBeenCalledWith(expect.objectContaining({ product_type: 'GOODS', status: 'ACTIVE' }));
  });

  it('ask for any product when the kind is open', async () => {
    const user = userEvent.setup();
    show(<CatalogPicker kind="ANY" value={null} onChange={() => undefined} />);
    await user.click(screen.getByRole('combobox', { name: 'Product' }));
    await screen.findByRole('option', { name: /Brake pad/ });
    expect(resources.listProductsPage.mock.calls[0][0]).not.toHaveProperty('product_type');
  });

  it('offer only completed invoices of the chosen customer, found by number', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    show(<InvoicePicker customerId={5} value={null} onChange={onChange} />);
    await user.click(screen.getByRole('combobox', { name: 'Invoice' }));
    await user.click(await screen.findByRole('option', { name: /INV-30/ }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 30 }));
    expect(resources.listSalesInvoicesPage).toHaveBeenCalledWith(expect.objectContaining({ customer: 5, status: 'COMPLETED' }));
  });

  it('stay switched off until a customer is chosen', () => {
    show(<InvoicePicker customerId={null} value={null} onChange={() => undefined} />);
    expect(screen.getByRole('combobox', { name: 'Invoice' })).toBeDisabled();
  });
});

describe('WarehousePicker', () => {
  it('is hidden for a company with one godown', async () => {
    resources.listWarehouses.mockResolvedValue([{ id: 1, name: 'Main', isActive: true }]);
    const view = show(<WarehousePicker value={null} onChange={() => undefined} />);
    await waitFor(() => expect(resources.listWarehouses).toHaveBeenCalled());
    expect(view.container).toBeEmptyDOMElement();
  });

  it('lets a company with several godowns choose, or keep the default', async () => {
    resources.listWarehouses.mockResolvedValue([{ id: 1, name: 'Main', isActive: true }, { id: 2, name: 'Workshop store', isActive: true }]);
    const onChange = vi.fn();
    const user = userEvent.setup();
    show(<WarehousePicker value={null} onChange={onChange} />);
    await user.click(await screen.findByRole('combobox', { name: 'Take parts from' }));
    await user.click(await screen.findByRole('option', { name: 'Workshop store' }));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('stays out of the way when the person cannot read warehouses', async () => {
    resources.listWarehouses.mockRejectedValue(new Error('403'));
    const view = show(<WarehousePicker value={null} onChange={() => undefined} />);
    await waitFor(() => expect(resources.listWarehouses).toHaveBeenCalled());
    expect(view.container).toBeEmptyDOMElement();
  });
});

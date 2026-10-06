import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ItemFormDialog } from '@/pages/inventory/ItemFormDialog';

type ProductPayload = {
  name: string;
  sku?: string;
  sellingPrice?: number | string;
  purchasePrice?: number | string;
  gstRate?: number | string;
};

const { createProductMock, authCompany } = vi.hoisted(() => ({
  createProductMock: vi.fn(async (payload: ProductPayload) => ({
    id: 101,
    name: payload.name,
    sku: payload.sku,
    sellingPrice: payload.sellingPrice,
    purchasePrice: payload.purchasePrice,
    gstRate: payload.gstRate,
  })),
  authCompany: {
    itemCustomFieldDefs: undefined as
      | Array<{ key: string; label: string; type: 'text'; active: boolean }>
      | undefined,
  },
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'owner@bizboard.test',
      fullName: 'Owner',
      role: 'OWNER',
      companyId: 9,
      company: { registrationType: 'REGULAR', itemCustomFieldDefs: authCompany.itemCustomFieldDefs },
    },
  }),
}));

vi.mock('@/api/resources', () => ({
  createProduct: (payload: ProductPayload) => createProductMock(payload),
  updateProduct: vi.fn(),
  createOpeningStock: vi.fn(),
  createWarehouse: vi.fn(),
  fetchBarcodeImage: vi.fn(),
  generateBarcode: vi.fn(async () => ({ barcode: 'AUTO-BAR-123' })),
  getCompany: async () => ({ id: 9, name: 'Acme Corp', registrationType: 'REGULAR' }),
  listCategories: async () => [],
  listBrands: async () => [],
  listStock: async () => [],
  listUnits: async () => [{ id: 1, name: 'Pieces', shortName: 'PCS' }],
  listWarehouses: async () => [{ id: 1, name: 'Main Godown' }],
  searchHsn: async () => ({ items: [] }),
}));

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ItemFormDialog (CW-PR-4)', () => {
  it('renders Core Essentials Hero section with name, prices, GST rate, unit, and HSN', async () => {
    renderWithClient(
      <ItemFormDialog
        open={true}
        product={null}
        existingNames={[]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    // Hero title
    expect(screen.getByText(/Core Essentials/i)).toBeInTheDocument();

    // Verify fields in Hero
    expect(screen.getByRole('textbox', { name: /^Name/i })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /Selling Price/i })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /Purchase Price/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^GST rate/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Unit/i)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /HSN code/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Stock details/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add opening stock, lots or serials/i })).toBeInTheDocument();
  });

  it('creates an item using Hero section and SKU without visiting Stock or Pricing tabs', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();

    renderWithClient(
      <ItemFormDialog
        open={true}
        product={null}
        existingNames={[]}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    // Fill Hero fields
    const nameInput = screen.getByRole('textbox', { name: /^Name/i });
    await user.type(nameInput, 'Parle-G Biscuit');

    const sellingPriceInput = screen.getByRole('spinbutton', { name: /Selling Price/i });
    await user.clear(sellingPriceInput);
    await user.type(sellingPriceInput, '20');

    // Tab 1 (Basic details) is open by default: fill SKU
    const skuInput = screen.getByRole('textbox', { name: /SKU \/ Item Code/i });
    await user.type(skuInput, 'BIS-001');

    // Click Save item directly without visiting Tab 2 or Tab 3
    const saveButton = screen.getByRole('button', { name: /^Save item/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(createProductMock).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Parle-G Biscuit',
          sku: 'BIS-001',
          sellingPrice: 20,
        }),
      );
      expect(onSaved).toHaveBeenCalled();
    });
  });

  it('switches to Pricing tab when wholesale price is invalid and Save is clicked', async () => {
    const user = userEvent.setup();

    renderWithClient(
      <ItemFormDialog
        open={true}
        product={null}
        existingNames={[]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    // Fill valid Hero fields
    const nameInput = screen.getByRole('textbox', { name: /^Name/i });
    await user.type(nameInput, 'Notebook A4');

    const skuInput = screen.getByRole('textbox', { name: /SKU \/ Item Code/i });
    await user.type(skuInput, 'NOTE-A4');

    // Switch to Pricing details tab
    const pricingTab = screen.getByRole('tab', { name: /Pricing details/i });
    await user.click(pricingTab);

    // Enter negative wholesale price
    const wholesaleInput = screen.getByRole('spinbutton', { name: /Wholesale price/i });
    fireEvent.change(wholesaleInput, { target: { value: '-15' } });

    // Switch back to Basic details tab
    const basicTab = screen.getByRole('tab', { name: /Basic details/i });
    await user.click(basicTab);

    // Click Save item
    const saveButton = screen.getByRole('button', { name: /^Save item/i });
    await user.click(saveButton);

    // Should automatically switch back to Pricing details tab and show error
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Pricing details/i })).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByText(/Wholesale price cannot be negative/i)).toBeInTheDocument();
    });
  });
});

describe('ItemFormDialog form lifecycle', () => {
  const PRODUCT_A = {
    id: 11,
    name: 'Alpha Soap',
    sku: 'AL-1',
    sellingPrice: 30,
    purchasePrice: 20,
    gstRate: 18,
    status: 'ACTIVE',
    unitName: 'PCS',
  };
  const PRODUCT_B = { ...PRODUCT_A, id: 12, name: 'Beta Shampoo', sku: 'BE-1', sellingPrice: 90 };

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const dialog = (open: boolean, product: typeof PRODUCT_A | null = null) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ItemFormDialog open={open} product={product as never} existingNames={[]} onClose={vi.fn()} onSaved={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const nameBox = () => screen.getByRole('textbox', { name: /^Name/i }) as HTMLInputElement;

  it('opens an existing item with its saved details', async () => {
    render(dialog(true, PRODUCT_A));
    await waitFor(() => expect(nameBox().value).toBe('Alpha Soap'));
  });

  it('shows the other item when the dialog is pointed at a different one', async () => {
    const { rerender } = render(dialog(true, PRODUCT_A));
    await waitFor(() => expect(nameBox().value).toBe('Alpha Soap'));
    rerender(dialog(true, PRODUCT_B));
    await waitFor(() => expect(nameBox().value).toBe('Beta Shampoo'));
  });

  it('starts empty each time it is opened for a new item', async () => {
    const user = userEvent.setup();
    const { rerender } = render(dialog(true));
    await user.type(nameBox(), 'Half typed');
    expect(nameBox().value).toBe('Half typed');

    rerender(dialog(false));
    rerender(dialog(true));
    await waitFor(() => expect(nameBox().value).toBe(''));
  });

  it('does not wipe what the user typed when the page re-renders with the same item', async () => {
    const user = userEvent.setup();
    const { rerender } = render(dialog(true));
    await user.type(nameBox(), 'Keep me');
    rerender(dialog(true));
    rerender(dialog(true));
    expect(nameBox().value).toBe('Keep me');
  });

  it('does not carry one item into the next when the dialog is closed between them', async () => {
    const { rerender } = render(dialog(true, PRODUCT_A));
    await waitFor(() => expect(nameBox().value).toBe('Alpha Soap'));
    rerender(dialog(false, PRODUCT_A));
    rerender(dialog(true, PRODUCT_B));
    await waitFor(() => expect(nameBox().value).toBe('Beta Shampoo'));
    expect(screen.queryByDisplayValue('Alpha Soap')).toBeNull();
  });

  it('keeps the item name when custom fields are applied as the dialog opens', async () => {
    authCompany.itemCustomFieldDefs = [{ key: 'color', label: 'Color', type: 'text', active: true }];
    try {
      const product = {
        ...PRODUCT_A,
        id: 21,
        name: 'Premium Tea 500g',
        sku: 'TEA-500',
        customFields: { color: 'Red' },
      };
      const { rerender } = render(dialog(false));
      rerender(dialog(true, product));
      await waitFor(() => expect(nameBox().value).toBe('Premium Tea 500g'));
    } finally {
      authCompany.itemCustomFieldDefs = undefined;
    }
  });

  it('fills the default godown when opening stock is added to a new item', async () => {
    const user = userEvent.setup();
    render(dialog(true));
    await user.click(screen.getByRole('button', { name: /Add opening stock, lots or serials/i }));
    expect(await screen.findByText('Main Godown')).toBeTruthy();
  });
});

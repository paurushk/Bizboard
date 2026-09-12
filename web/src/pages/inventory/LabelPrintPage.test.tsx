import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('LabelPrintPage — QOS-0047', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});

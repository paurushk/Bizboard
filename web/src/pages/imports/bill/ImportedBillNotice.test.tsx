import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ImportedBillNotice } from './ImportedBillNotice';

const api = vi.hoisted(() => ({
  openAuthenticatedFile: vi.fn(async () => undefined),
  voidImport: vi.fn(async () => ({ id: 5, status: 'VOIDED' })),
}));
vi.mock('@/api/resources', () => api);
const NAV = vi.fn();
vi.mock('react-router-dom', async (orig) => {
  const actual = await orig<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => NAV };
});

function show(props: Partial<ComponentProps<typeof ImportedBillNotice>> = {}) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ImportedBillNotice uploadPath="/sales/bill-upload" isDraft {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('ImportedBillNotice', () => {
  it('renders nothing for a document that did not come from a bill', () => {
    const { container } = show();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the source bill number and opens the file through the invoice, not the files API', async () => {
    show({ reference: 'SB-77', hasSourceBill: true, sourceBillPath: '/sales/invoices/9/source-bill/' });
    expect(screen.getByText(/Source bill no\. SB-77/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Original bill' }));
    expect(api.openAuthenticatedFile).toHaveBeenCalledWith('/sales/invoices/9/source-bill/');
  });

  it('points at the products that still need cost and stock', () => {
    show({ productsCreated: 3, importJobId: 5 });
    expect(screen.getByText(/3 product\(s\) were created from this bill/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review these products' })).toHaveAttribute(
      'href',
      '/inventory/products?needsReview=1',
    );
  });

  it('says how many lines keep a below-price-list price', () => {
    show({ belowListLines: 2, reference: 'SB-1' });
    expect(screen.getByText(/2 line\(s\) keep a price below the customer's price list/)).toBeInTheDocument();
  });

  it('undoes the import after a confirmation and returns to the upload screen', async () => {
    show({ reference: 'SB-1', importJobId: 5 });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Undo this import' }));
    expect(screen.getByText('Undo this import?')).toBeInTheDocument();
    const confirmButtons = screen.getAllByRole('button', { name: 'Undo this import' });
    await user.click(confirmButtons[confirmButtons.length - 1]);
    await waitFor(() => expect(api.voidImport).toHaveBeenCalledWith(5));
    await waitFor(() => expect(NAV).toHaveBeenCalledWith('/sales/bill-upload?job=5'));
  });

  it('offers no undo once the document is no longer a draft', () => {
    show({ reference: 'SB-1', importJobId: 5, isDraft: false });
    expect(screen.queryByRole('button', { name: 'Undo this import' })).not.toBeInTheDocument();
  });
});

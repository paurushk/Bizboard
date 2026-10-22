import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { OrderRenderer } from './OrderRenderer';
import { isOrderReady, isPayloadReady } from './ready';

vi.mock('@/hooks/usePartySearch', () => ({
  useCustomerSearch: () => ({ query: '', setQuery: vi.fn(), options: [{ id: 3, name: 'Sharma Traders' }], isFetching: false }),
}));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '', setProductQuery: vi.fn(), isFetching: false, helperText: undefined,
    options: [{ id: 9, name: 'Sugar 50kg bag' }, { id: 10, name: 'Toor Dal 1kg' }],
  }),
}));

const LINE = { raw: '2 chini', rawNorm: 'chini', qty: '2', unit: 'kg', productId: null, productName: '', match: { source: 'none', score: 0 },
  alternatives: [{ id: 9, name: 'Sugar 50kg bag' }, { id: 10, name: 'Toor Dal 1kg' }], warnings: ['Only 1 available in stock.'] };
const BASE = { customerId: null, customerName: '', customerHint: 'Sharma ji', customerAlternatives: [{ id: 3, name: 'Sharma Traders' }], warnings: ['Pick the customer.'], lines: [LINE] };

function setup(value: Record<string, unknown> = BASE, disabled = false) {
  const onChange = vi.fn();
  render(<OrderRenderer value={value} onChange={onChange} disabled={disabled} />);
  return onChange;
}

describe('OrderRenderer', () => {
  it('shows what was written, the warnings and the customer hint', () => {
    setup();
    expect(screen.getByText('Written: 2 chini')).toBeInTheDocument();
    expect(screen.getByText('Only 1 available in stock.')).toBeInTheDocument();
    expect(screen.getByText('Pick the customer.')).toBeInTheDocument();
    expect(screen.getByText('Written: Sharma ji')).toBeInTheDocument();
  });

  it('picking a customer suggestion writes camelCase keys and marks the match manual', async () => {
    const onChange = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Sharma Traders' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      customerId: 3, customerName: 'Sharma Traders', customerMatch: { source: 'manual', score: 1 },
    }));
  });

  it('picking a product suggestion fills that line only', async () => {
    const two = { ...BASE, lines: [LINE, { ...LINE, raw: '1 dal' }] };
    const onChange = setup(two);
    await userEvent.click(screen.getAllByRole('button', { name: 'Toor Dal 1kg' })[0]);
    const next = onChange.mock.calls[0][0] as { lines: Array<Record<string, unknown>> };
    expect(next.lines[0]).toMatchObject({ productId: 10, productName: 'Toor Dal 1kg', match: { source: 'manual', score: 1 } });
    expect(next.lines[1].productId).toBeNull();
  });

  it('editing a quantity changes only that line', async () => {
    const onChange = setup();
    const box = screen.getByLabelText('Qty 1');
    fireEvent.change(box, { target: { value: '7' } });
    const next = onChange.mock.calls[0][0] as { lines: Array<Record<string, unknown>>; customerId: unknown };
    expect(next.lines[0].qty).toBe('7');
    expect(next.lines[0].raw).toBe('2 chini');
  });

  it('marks an invalid quantity and explains why the order cannot be created yet', () => {
    setup({ ...BASE, lines: [{ ...LINE, qty: '0' }] });
    expect(screen.getByLabelText('Qty 1')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/Pick the customer and a product and quantity for every line/)).toBeInTheDocument();
  });

  it('has no incomplete note once everything is filled in', () => {
    setup({ ...BASE, customerId: 3, customerName: 'Sharma Traders', lines: [{ ...LINE, productId: 9, productName: 'Sugar 50kg bag' }] });
    expect(screen.queryByText(/Pick the customer and a product/)).toBeNull();
  });

  it('is read-only when disabled', () => {
    setup(BASE, true);
    expect(screen.getByLabelText('Qty 1')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Sharma Traders' })).toHaveAttribute('aria-disabled', 'true');
  });
});

describe('isOrderReady', () => {
  const ok = { customerId: 1, lines: [{ productId: 2, qty: '1' }] };
  it.each([
    ['ready', ok, true],
    ['no customer', { ...ok, customerId: null }, false],
    ['no lines', { ...ok, lines: [] }, false],
    ['blank qty', { ...ok, lines: [{ productId: 2, qty: ' ' }] }, false],
    ['null qty', { ...ok, lines: [{ productId: 2, qty: null }] }, false],
    ['negative qty', { ...ok, lines: [{ productId: 2, qty: '-1' }] }, false],
    ['text qty', { ...ok, lines: [{ productId: 2, qty: 'abc' }] }, false],
    ['decimal qty', { ...ok, lines: [{ productId: 2, qty: '2.5' }] }, true],
    ['no product', { ...ok, lines: [{ productId: null, qty: '1' }] }, false],
  ])('%s', (_name, value, expected) => {
    expect(isOrderReady(value as Record<string, unknown>)).toBe(expected);
  });

  it('only gates the order renderer', () => {
    expect(isPayloadReady('message', {})).toBe(true);
    expect(isPayloadReady('lines', {})).toBe(true);
    expect(isPayloadReady('order', {})).toBe(false);
  });
});

describe('OrderRenderer matched values', () => {
  it('shows the matched customer and product names in their boxes, not blank ones', () => {
    render(
      <OrderRenderer
        disabled={false}
        onChange={vi.fn()}
        value={{ customerId: 3, customerName: 'Sharma Traders', lines: [{ ...LINE, productId: 9, productName: 'Sugar 50kg bag' }] }}
      />,
    );
    expect(screen.getByLabelText('Customer')).toHaveValue('Sharma Traders');
    expect(screen.getByLabelText(/Product: 2 chini/)).toHaveValue('Sugar 50kg bag');
  });
});

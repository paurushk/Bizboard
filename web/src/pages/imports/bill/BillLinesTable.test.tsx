import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BillLinesTable, WINDOW_THRESHOLD } from './BillLinesTable';
import type { EditorLine } from './billLines';

// jsdom has no layout, so the real windowing draws nothing: draw a fixed window.
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({
    children,
    rowCount,
    scrollToIndex,
  }: {
    children: (a: unknown) => unknown;
    rowCount: number;
    scrollToIndex?: number | null;
  }) => (
    <div data-testid="windowed" data-count={rowCount} data-scroll-to={scrollToIndex ?? ''}>
      {children({
        rows: Array.from({ length: Math.min(rowCount, 12) }, (_, i) => ({
          index: i, start: i * 64, end: (i + 1) * 64, size: 64, key: i,
        })),
        totalSize: rowCount * 64,
        measureElement: () => undefined,
      }) as never}
    </div>
  ),
}));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({ options: [], setProductQuery: vi.fn() }),
}));

function row(id: number, over: Partial<EditorLine> = {}): EditorLine {
  return {
    clientKey: `line-${id}`,
    lineId: id,
    si: String(id),
    name: `Item ${id}`,
    quantity: '2',
    unitPrice: '100',
    gstRate: '18',
    hsnCode: '3402',
    include: true,
    flags: [],
    errors: [],
    productMatch: { status: 'none', productId: null, candidates: [] },
    ...over,
  };
}

const handlers = {
  onToggleExpand: vi.fn(),
  onChange: vi.fn(),
  onDelete: vi.fn(),
  onActiveRow: vi.fn(),
};

function show(lines: EditorLine[], over: Partial<React.ComponentProps<typeof BillLinesTable>> = {}) {
  return render(
    <BillLinesTable
      lines={lines}
      visibleKeys={lines.map((l) => l.clientKey)}
      expanded={new Set()}
      showAdvanced={false}
      showPack={false}
      showDiscount={false}
      priceInclusive={false}
      {...handlers}
      {...over}
    />,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('BillLinesTable', () => {
  it('draws a collapsed summary row per line, with the computed line total', () => {
    show([row(1), row(2, { quantity: '1' })]);
    expect(screen.getByText('Item 1')).toBeInTheDocument();
    expect(screen.getByText('236.00')).toBeInTheDocument();
    expect(screen.getByText('118.00')).toBeInTheDocument();
  });

  it('opens a collapsed row on click and from the keyboard', async () => {
    show([row(1)]);
    const summary = screen.getByRole('button', { name: 'Expand row to edit details' });
    await userEvent.click(summary);
    expect(handlers.onToggleExpand).toHaveBeenCalledWith('line-1', true);
    summary.focus();
    await userEvent.keyboard('{Enter}');
    expect(handlers.onToggleExpand).toHaveBeenCalledTimes(2);
  });

  it('ticks a row in or out without opening it', async () => {
    show([row(1)]);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Include, row 1' }));
    expect(handlers.onChange).toHaveBeenCalledWith('line-1', { include: false });
    expect(handlers.onToggleExpand).not.toHaveBeenCalled();
  });

  it('labels every field of an open row with its column and row number', () => {
    // The number in the label is the row's place on the bill (1-based), not its id.
    show([row(1), row(9)], { expanded: new Set(['line-9']) });
    expect(screen.getByRole('textbox', { name: /^name, row 2$/i })).toHaveValue('Item 9');
    expect(screen.getByRole('spinbutton', { name: /^qty, row 2$/i })).toHaveValue(2);
    expect(screen.getByRole('spinbutton', { name: /^gst %, row 2$/i })).toHaveValue(18);
    expect(screen.getByRole('button', { name: 'Collapse row 2' })).toBeInTheDocument();
  });

  it('passes an edit up with the row key and the changed field', async () => {
    show([row(1)], { expanded: new Set(['line-1']) });
    await userEvent.type(screen.getByRole('spinbutton', { name: /^qty, row 1$/i }), '5');
    expect(handlers.onChange).toHaveBeenLastCalledWith('line-1', { quantity: '25' });
  });

  it('collapses an open row and deletes a row', async () => {
    show([row(1)], { expanded: new Set(['line-1']) });
    await userEvent.click(screen.getByRole('button', { name: 'Collapse row 1' }));
    expect(handlers.onToggleExpand).toHaveBeenCalledWith('line-1', false);
    await userEvent.click(screen.getByRole('button', { name: 'Delete row 1' }));
    expect(handlers.onDelete).toHaveBeenCalledWith('line-1');
  });

  it('forces a row with a problem open and shows what is wrong, in red', () => {
    show([row(1, { gstRate: '', hsnCode: '123' })]);
    expect(screen.getByText('Choose the GST rate.')).toBeInTheDocument();
    expect(screen.getByText('HSN code must be 2, 4, 6 or 8 digits.')).toBeInTheDocument();
    // no collapse button: it cannot be hidden while it is wrong
    expect(screen.queryByRole('button', { name: 'Collapse row 1' })).not.toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: /^gst %, row 1$/i })).toHaveAttribute('aria-invalid', 'true');
  });

  it('does not nag about a row that is left out', () => {
    show([row(1, { include: false, gstRate: '' })]);
    expect(screen.queryByText('Choose the GST rate.')).not.toBeInTheDocument();
  });

  it('prefers the server message and shows why a row was left out at extraction', () => {
    show(
      [
        row(1, {
          include: false,
          excludedReason: 'invalid HSN code',
          flags: ['Recomputed amount does not match the printed one'],
        }),
      ],
    );
    expect(screen.getByText('Left out: invalid HSN code')).toBeInTheDocument();
    expect(screen.getByText(/Recomputed amount does not match/)).toBeInTheDocument();
  });

  it('shows the pack, advanced and discount columns only when asked', () => {
    const { rerender } = show([row(1)]);
    for (const name of ['Cs', 'Pcs', 'UPC', 'HSN', 'SKU', 'Disc %']) {
      expect(screen.queryByRole('columnheader', { name }), name).not.toBeInTheDocument();
    }
    rerender(
      <BillLinesTable
        lines={[row(1)]}
        visibleKeys={['line-1']}
        expanded={new Set()}
        showAdvanced
        showPack
        showDiscount
        priceInclusive={false}
        {...handlers}
      />,
    );
    for (const name of ['Cs', 'Pcs', 'UPC', 'HSN', 'SKU', 'Disc %']) {
      expect(screen.getByRole('columnheader', { name }), name).toBeInTheDocument();
    }
  });

  it('treats the price as GST-inclusive when told to', () => {
    show([row(1, { unitPrice: '118' })], { priceInclusive: true });
    expect(screen.getByText('236.00')).toBeInTheDocument();
  });

  it('only shows the rows it is given, in that order', () => {
    const lines = [row(1), row(2), row(3)];
    show(lines, { visibleKeys: ['line-3', 'line-1'] });
    const shown = screen
      .getAllByRole('button', { name: 'Expand row to edit details' })
      .map((r) => r.textContent ?? '');
    expect(shown).toHaveLength(2);
    expect(shown[0]).toContain('Item 3');
    expect(shown[1]).toContain('Item 1');
  });

  it('says so when there is nothing to show', () => {
    show([row(1)], { visibleKeys: [] });
    expect(screen.getByText('No lines extracted. Edit or re-upload.')).toBeInTheDocument();
  });

  it('tells the page which row the pointer is on', async () => {
    show([row(1)]);
    const summary = screen.getByRole('button', { name: 'Expand row to edit details' });
    await userEvent.hover(summary);
    expect(handlers.onActiveRow).toHaveBeenCalledWith('line-1');
    await userEvent.unhover(summary);
    expect(handlers.onActiveRow).toHaveBeenLastCalledWith(null);
  });

  describe('product matching', () => {
    it('shows a matched product, and warns when it needs a batch', () => {
      show(
        [
          row(1, {
            productMatch: { status: 'matched', productId: 9, name: 'Lux Soap', trackBatch: true, candidates: [] },
          }),
        ],
        { expanded: new Set(['line-1']) },
      );
      expect(screen.getByText('Matches Lux Soap')).toBeInTheDocument();
      expect(screen.getByText('Needs a batch when you complete the invoice')).toBeInTheDocument();
    });

    it('shows a new product as new', () => {
      show([row(1)], { expanded: new Set(['line-1']) });
      expect(screen.getByText('New product')).toBeInTheDocument();
    });

    it('offers similar products and lets the reviewer choose one or create a new one', async () => {
      show(
        [
          row(1, {
            productMatch: {
              status: 'candidates',
              productId: null,
              candidates: [{ id: 5, name: 'Olay Natural Aura 40g', sku: 'OLAY-1', score: 0.9 }],
            },
          }),
        ],
        { expanded: new Set(['line-1']) },
      );
      await userEvent.click(screen.getByRole('button', { name: 'Similar: Olay Natural Aura 40g' }));
      expect(handlers.onChange).toHaveBeenCalledWith(
        'line-1',
        expect.objectContaining({
          productId: 5,
          createNew: false,
          productMatch: expect.objectContaining({ status: 'matched', name: 'Olay Natural Aura 40g' }),
        }),
      );
      await userEvent.click(screen.getByRole('button', { name: 'Create as new' }));
      expect(handlers.onChange).toHaveBeenLastCalledWith('line-1', { createNew: true });
    });

    it('treats a line marked "create as new" as new, with no suggestions left', () => {
      show(
        [
          row(1, {
            createNew: true,
            productMatch: { status: 'candidates', productId: null, candidates: [{ id: 5, name: 'Olay' }] },
          }),
        ],
        { expanded: new Set(['line-1']) },
      );
      expect(screen.getByText('New product')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Similar: Olay' })).not.toBeInTheDocument();
    });

    it('requires a choice when only similar products exist and strict review is on', () => {
      const candidates = row(1, {
        productMatch: { status: 'candidates', productId: null, candidates: [{ id: 5, name: 'Olay' }] },
      });
      const { unmount } = show([candidates]);
      expect(screen.queryByText('Choose product')).not.toBeInTheDocument();
      unmount();
      show([candidates], { productChoiceRequired: true });
      expect(screen.getByText('Choose product', { selector: 'span' })).toBeInTheDocument();
    });

    it('opens a product picker from the row', async () => {
      show([row(1)], { expanded: new Set(['line-1']) });
      await userEvent.click(screen.getByRole('button', { name: 'Choose product' }));
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByLabelText('Search products')).toBeInTheDocument();
    });
  });

  it('marks a line kept below the customer price list', () => {
    show([row(1, { belowPriceList: true, priceListPrice: '120.00' })], { expanded: new Set(['line-1']) });
    expect(screen.getByText('Below price list (120.00)')).toBeInTheDocument();
  });

  it('shows a hint to apply a pack-derived quantity', async () => {
    show([row(1, { packQtyHint: '27' })], { expanded: new Set(['line-1']) });
    await userEvent.click(screen.getByText('pack = 27 · apply'));
    expect(handlers.onChange).toHaveBeenCalledWith('line-1', { quantity: '27', packQtyHint: undefined });
  });

  describe('large bills', () => {
    const many = (n: number) => Array.from({ length: n }, (_, i) => row(i + 1));

    it('draws a bill at the threshold whole', () => {
      show(many(WINDOW_THRESHOLD));
      expect(screen.queryByTestId('windowed')).not.toBeInTheDocument();
      expect(screen.getByText(`Item ${WINDOW_THRESHOLD}`)).toBeInTheDocument();
    });

    it('windows a bill above the threshold', () => {
      show(many(WINDOW_THRESHOLD + 50));
      expect(screen.getByTestId('windowed')).toHaveAttribute('data-count', String(WINDOW_THRESHOLD + 50));
      expect(screen.getByText('Item 12')).toBeInTheDocument();
      expect(screen.queryByText('Item 13')).not.toBeInTheDocument();
    });

    it('asks the window to scroll to the row being edited', () => {
      const lines = many(WINDOW_THRESHOLD + 50);
      show(lines, { focusKey: 'line-120' });
      expect(screen.getByTestId('windowed')).toHaveAttribute('data-scroll-to', '119');
    });
  });
});

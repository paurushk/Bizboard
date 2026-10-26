import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import axe from 'axe-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setLocale } from '@/i18n';
import { AttentionPage } from '@/pages/AttentionPage';

const { dismissAttentionRow, getLearningReport, listAttentionRows, reopenAttentionRow, snoozeAttentionRow } = vi.hoisted(() => ({
  reopenAttentionRow: vi.fn(async () => undefined),
  listAttentionRows: vi.fn(async (..._args: unknown[]) => [{
    code: 'DEAD_STOCK',
    severity: 'warning',
    title: 'Dead stock',
    moneyImpactPaise: 10000,
    currency: 'INR',
    reason: 'No sales',
    actionLabel: 'Fix',
    actionHref: '/inventory/products',
    sourceTicket: 'B-05',
    entityRef: { type: 'product', id: 3 },
    dedupeKey: 'DEAD_STOCK:3',
    firstSeen: '2026-09-20T00:00:00Z',
    snoozeUntil: null,
  }]),
  dismissAttentionRow: vi.fn(async () => ({ dedupeKey: 'DEAD_STOCK:3', dismissed: true })),
  getLearningReport: vi.fn(async () => ({
    acted: 2, metricImproved: 1, windowDays: 7, thresholdsChanged: false,
  })),
  snoozeAttentionRow: vi.fn(async () => ({})),
}));

vi.mock('@/config/featureFlags', () => ({
  useFeatureFlagEpoch: () => 0,
  isRuntimeFlagEnabled: () => false,
  getCachedFeatureFlags: () => null,
}));

vi.mock('@/api/resources', () => ({
  getAttentionFeed: async (...args: unknown[]) => {
    const result = (await listAttentionRows(...args)) as unknown[] | { rows: unknown[] };
    if (!Array.isArray(result)) return { count: result.rows.length, totalCount: result.rows.length, nextOffset: null, ...result };
    return { rows: result, count: result.length, totalCount: result.length, nextOffset: null };
  },
  markAttentionSeen: vi.fn(async () => undefined),
  reopenAttentionRow: (...args: unknown[]) => reopenAttentionRow(...args),
  getLearningReport: () => getLearningReport(),
  dismissAttentionRow: (...args: unknown[]) => dismissAttentionRow(...args),
  snoozeAttentionRow: (...args: unknown[]) => snoozeAttentionRow(...args),
  assignAttentionRow: vi.fn(),
  listTeamMembers: vi.fn(async () => []),
  TEAM_MEMBERS_QUERY_KEY: ['company-users', 'team'],
}));

describe('AttentionPage', () => {
  it('lists a problem and dismisses it without snoozing', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AttentionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByText(/Learning report/)).not.toBeInTheDocument();
    expect(await screen.findByText('Dead stock')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(dismissAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3'));
    expect(snoozeAttentionRow).not.toHaveBeenCalled();
  });

  it('asks why a possible duplicate payment is not one, and sends the reason', async () => {
    const user = userEvent.setup();
    listAttentionRows.mockResolvedValueOnce([{
      code: 'DUPLICATE_PAYMENT',
      severity: 'warning',
      title: 'Possible duplicate receipt',
      moneyImpactPaise: 10000,
      currency: 'INR',
      reason: '2 receipts',
      actionLabel: 'Review receipts',
      actionHref: '/sales/receipts',
      sourceTicket: 'B-05',
      entityRef: { type: 'customer', id: 4 },
      dedupeKey: 'DUPLICATE_PAYMENT:4:2026-10-01:100.00:none',
      firstSeen: '2026-10-01T00:00:00Z',
      snoozeUntil: null,
    }]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AttentionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Possible duplicate receipt')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    const confirm = screen.getAllByRole('button', { name: 'Dismiss' }).pop() as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(dismissAttentionRow).not.toHaveBeenCalledWith('DUPLICATE_PAYMENT:4:2026-10-01:100.00:none');
    await user.type(screen.getByLabelText(/why is this not a duplicate/i), 'two real payments');
    await user.click(confirm);
    await waitFor(() =>
      expect(dismissAttentionRow).toHaveBeenCalledWith('DUPLICATE_PAYMENT:4:2026-10-01:100.00:none', 'two real payments'),
    );
  });

  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AttentionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('shows the error and never the all-clear message when the feed fails to load', async () => {
    listAttentionRows.mockRejectedValueOnce(new Error('feed down'));
    renderPage();
    expect(await screen.findByText(/feed down/i)).toBeInTheDocument();
    expect(screen.queryByText('Nothing needs attention right now.')).toBeNull();
  });

  it('shows the all-clear message only after a successful empty load', async () => {
    listAttentionRows.mockResolvedValueOnce([]);
    renderPage();
    expect(await screen.findByText('Nothing needs attention right now.')).toBeInTheDocument();
  });

  it('keeps the typed reason and shows the server message when a duplicate-payment dismiss fails', async () => {
    const user = userEvent.setup();
    listAttentionRows.mockResolvedValueOnce([{
      code: 'DUPLICATE_PAYMENT', severity: 'warning', title: 'Possible duplicate receipt', moneyImpactPaise: 10000,
      currency: 'INR', reason: '2 receipts', actionLabel: 'Review', actionHref: '/sales/receipts', sourceTicket: 'B-05',
      entityRef: { type: 'customer', id: 4 }, dedupeKey: 'DUPLICATE_PAYMENT:4:x', firstSeen: '2026-10-01T00:00:00Z', snoozeUntil: null,
    }]);
    dismissAttentionRow.mockRejectedValueOnce(new Error('Server said no'));
    renderPage();
    await screen.findByText('Possible duplicate receipt');
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    await user.type(screen.getByLabelText(/why is this not a duplicate/i), 'two real payments');
    await user.click(screen.getAllByRole('button', { name: 'Dismiss' }).pop() as HTMLButtonElement);
    expect(await screen.findByText(/Server said no/)).toBeInTheDocument();
    expect(screen.getByLabelText(/why is this not a duplicate/i)).toHaveValue('two real payments');
  });

  it('hides Dismiss on a row the server marks as not dismissible, but keeps Snooze', async () => {
    listAttentionRows.mockResolvedValueOnce([{
      code: 'GST_RATE_EXPOSURE', severity: 'warning', title: 'GST rate exposure', moneyImpactPaise: 0,
      currency: 'INR', reason: 'x', actionLabel: 'Review', actionHref: '/reports/gst-rate-exposure', sourceTicket: 'B-06',
      entityRef: { type: 'company', id: 1 }, dedupeKey: 'GST_RATE_EXPOSURE:1', firstSeen: null, snoozeUntil: null,
      dismissible: false, snoozable: true, assignable: true, requiresReason: false,
    }]);
    renderPage();
    await screen.findByText('GST rate exposure');
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
    expect(screen.getByRole('button', { name: /snooze/i })).toBeInTheDocument();
  });

  it('offers Undo after a dismiss and reopens the row', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Dead stock');
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    await user.click(await screen.findByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(reopenAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3'));
  });

  it('asks the server for the Snoozed list and lets the user reopen a row', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Dead stock');
    await user.click(screen.getByRole('tab', { name: /snoozed/i }));
    await waitFor(() =>
      expect(listAttentionRows).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'snoozed' })),
    );
    await user.click(await screen.findByRole('button', { name: 'Reopen' }));
    await waitFor(() => expect(reopenAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3'));
  });

  it('sends the chosen severity filter to the server', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Dead stock');
    await user.click(screen.getByLabelText(/severity/i));
    await user.click(await screen.findByRole('option', { name: /critical/i }));
    await waitFor(() =>
      expect(listAttentionRows).toHaveBeenLastCalledWith(expect.objectContaining({ severity: 'critical' })),
    );
  });

  it('uses the server text when a translation needs values the row does not carry', async () => {
    listAttentionRows.mockResolvedValueOnce([{
      code: 'AR_CUSTOMER', severity: 'warning', title: 'Ravi Traders: overdue', moneyImpactPaise: 100000,
      currency: 'INR', reason: 'Overdue', actionLabel: 'Send Reminder', actionHref: '/payments/collections', sourceTicket: 'DAN-08',
      entityRef: { type: 'customer', id: 1 }, dedupeKey: 'AR_CUSTOMER:1', firstSeen: null, snoozeUntil: null,
      params: {}, amountBasis: 'overdue',
    }]);
    renderPage();
    expect(await screen.findByText('Ravi Traders: overdue')).toBeInTheDocument();
    expect(screen.getByText('Send Reminder')).toBeInTheDocument();
    expect(screen.getByText('overdue')).toBeInTheDocument();
  });

  it('translates a known action label and builds a title from its values', async () => {
    listAttentionRows.mockResolvedValueOnce([{
      code: 'AR_CUSTOMER', severity: 'warning', title: 'x', moneyImpactPaise: 100000,
      currency: 'INR', reason: 'Overdue', actionLabel: 'Open collections', actionHref: '/payments/collections', sourceTicket: 'DAN-08',
      entityRef: { type: 'customer', id: 1 }, dedupeKey: 'AR_CUSTOMER:1', firstSeen: null, snoozeUntil: null,
      params: { customer: 'Ravi Traders', count: 3 },
    }]);
    renderPage();
    expect(await screen.findByText('Ravi Traders: 3 receivable issues')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open collections' })).toBeInTheDocument();
  });

  it('describes each action button by its row so repeated buttons are not anonymous', async () => {
    renderPage();
    const title = await screen.findByText('Dead stock');
    const button = screen.getByRole('button', { name: 'Dismiss' });
    expect(button.getAttribute('aria-describedby')).toBe(title.id);
  });

  async function violations() {
    const results = await axe.run(document.body, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
  }

  it('has no accessibility violations on the list', async () => {
    renderPage();
    await screen.findByText('Dead stock');
    expect(await violations()).toEqual([]);
  });

  describe('on a phone', () => {
    const original = window.matchMedia;
    afterEach(() => {
      window.matchMedia = original;
    });

    it('shows each problem as a card with the same actions, and no table', async () => {
      const user = userEvent.setup();
      window.matchMedia = ((query: string) => ({
        matches: query.includes('max-width'),
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      })) as unknown as typeof window.matchMedia;
      renderPage();
      await screen.findByText('Dead stock');
      expect(screen.queryByRole('table')).toBeNull();
      expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0);
      await user.click(screen.getByRole('button', { name: 'Dismiss' }));
      await waitFor(() => expect(dismissAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3'));
      expect(await violations()).toEqual([]);
    });
  });

  describe('Phase E behaviour', () => {
    const ROW = {
      code: 'DEAD_STOCK', severity: 'warning', title: 'Dead stock', moneyImpactPaise: 10000, currency: 'INR',
      reason: 'No sales', actionLabel: 'Fix', actionHref: '/inventory/products', sourceTicket: 'B-05',
      entityRef: { type: 'product', id: 3 }, dedupeKey: 'DEAD_STOCK:3', firstSeen: null, snoozeUntil: null,
    };
    beforeEach(() => sessionStorage.clear());

    it('says so when a row the person went to fix is gone on return', async () => {
      sessionStorage.setItem('bb_attention_left', JSON.stringify({ key: 'GONE:1', title: 'Old problem' }));
      listAttentionRows.mockResolvedValueOnce([ROW]);
      renderPage();
      expect(await screen.findByText('Resolved: Old problem')).toBeInTheDocument();
      expect(sessionStorage.getItem('bb_attention_left')).toBeNull();
    });

    it('stays quiet when the row is still there', async () => {
      sessionStorage.setItem('bb_attention_left', JSON.stringify({ key: 'DEAD_STOCK:3', title: 'Dead stock' }));
      listAttentionRows.mockResolvedValueOnce([ROW]);
      renderPage();
      await screen.findByText('Dead stock');
      expect(screen.queryByText(/^Resolved:/)).toBeNull();
    });

    it('does not claim a row is resolved when the list is incomplete', async () => {
      sessionStorage.setItem('bb_attention_left', JSON.stringify({ key: 'GONE:1', title: 'Old problem' }));
      listAttentionRows.mockResolvedValueOnce({ rows: [ROW], degraded: true });
      renderPage();
      await screen.findByText('Dead stock');
      expect(screen.queryByText(/^Resolved:/)).toBeNull();
    });

    it('remembers the row when Fix is followed', async () => {
      const user = userEvent.setup();
      listAttentionRows.mockResolvedValueOnce([ROW]);
      renderPage();
      await user.click(await screen.findByRole('link', { name: 'Fix' }));
      expect(JSON.parse(sessionStorage.getItem('bb_attention_left')!)).toEqual({ key: 'DEAD_STOCK:3', title: 'Dead stock' });
    });

    it('warns when a check cut its list short', async () => {
      listAttentionRows.mockResolvedValueOnce({ rows: [ROW], truncatedCodes: ['IRN_FAILED', 'AR_COLLECTION_RISK'] });
      renderPage();
      expect(await screen.findByText(/only their first items \(2 kinds\)/)).toBeInTheDocument();
    });

    it('lets the person snooze for a length of their own', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByText('Dead stock');
      await user.click(screen.getByRole('button', { name: /snooze/i }));
      await user.click(screen.getByRole('combobox', { name: /snooze for/i }));
      await user.click(await screen.findByRole('option', { name: /another length/i }));
      const days = await screen.findByLabelText('Days');
      await user.clear(days);
      await user.type(days, '45');
      await user.type(screen.getByLabelText(/^reason/i), 'Supplier abroad');
      await user.click(screen.getAllByRole('button', { name: /snooze/i }).pop() as HTMLButtonElement);
      await waitFor(() => expect(snoozeAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3', 'Supplier abroad', 45));
    });

    it('refuses a custom length outside 1 to 90 days', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByText('Dead stock');
      await user.click(screen.getByRole('button', { name: /snooze/i }));
      await user.click(screen.getByRole('combobox', { name: /snooze for/i }));
      await user.click(await screen.findByRole('option', { name: /another length/i }));
      const days = await screen.findByLabelText('Days');
      await user.clear(days);
      await user.type(days, '120');
      await user.type(screen.getByLabelText(/^reason/i), 'x');
      expect((screen.getAllByRole('button', { name: /snooze/i }).pop() as HTMLButtonElement).disabled).toBe(true);
    });

    it('can be driven from the keyboard, and focus returns to the button after a dialog closes', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByText('Dead stock');
      const snoozeButton = screen.getByRole('button', { name: /snooze/i });
      snoozeButton.focus();
      await user.keyboard('{Enter}');
      expect(await screen.findByRole('dialog')).toBeInTheDocument();
      await user.keyboard('{Escape}');
      await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
      await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: /snooze/i })));
    });

    it('says so while offline instead of going silent', async () => {
      onlineManager.setOnline(false);
      try {
        renderPage();
        expect(await screen.findByText(/You are offline/)).toBeInTheDocument();
        expect(screen.queryByText('Nothing needs attention right now.')).toBeNull();
      } finally {
        onlineManager.setOnline(true);
      }
    });

    it('renders the whole page in Hindi, including a long translated row, without losing any action', async () => {
      const user = userEvent.setup();
      listAttentionRows.mockResolvedValueOnce([{
        code: 'WALK_IN_UNALLOCATED_RECEIPT', severity: 'warning', title: 'Receipt R-1 is on the walk-in account', moneyImpactPaise: 250000,
        currency: 'INR', reason: 'x', actionLabel: 'Allocate or reassign', actionHref: '/sales/receipts', sourceTicket: 'B-05',
        entityRef: { type: 'payment', id: 1 }, dedupeKey: 'WALK_IN_UNALLOCATED_RECEIPT:1', firstSeen: null, snoozeUntil: null,
        amountBasis: 'amount', params: { number: 'R-1', amount: '2500', date: '2026-10-01' },
      }]);
      setLocale('hi');
      try {
        renderPage();
        expect(await screen.findByText('रसीद R-1 वॉक-इन खाते पर है')).toBeInTheDocument();
        expect(screen.getByText(/₹2500 को मिला|₹2500 received|₹2500/)).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /स्थगित/ })).toBeInTheDocument();
        expect(screen.getByRole('columnheader', { name: 'शामिल राशि' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'आवंटित या पुनः असाइन करें' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'खारिज करें' })).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'स्थगित करें' }));
        expect(await screen.findByRole('dialog')).toBeInTheDocument();
      } finally {
        setLocale('en');
      }
    });
  });
});

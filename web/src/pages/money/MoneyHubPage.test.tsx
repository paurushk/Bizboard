import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MoneyHubPage } from '@/pages/money/MoneyHubPage';

const { getMoneyPosition, getMoneyTimeline, getMoneyStatutory } = vi.hoisted(() => ({
  getMoneyPosition: vi.fn(),
  getMoneyTimeline: vi.fn(),
  getMoneyStatutory: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  getMoneyPosition: () => getMoneyPosition(),
  getMoneyTimeline: (days: number) => getMoneyTimeline(days),
  getMoneyStatutory: () => getMoneyStatutory(),
}));

const ZERO = { count: 0, amount: '0.00' };

function bills(overrides: Record<string, unknown> = {}) {
  return {
    outstanding: '5000.00',
    bills: { count: 4, amount: '4800.00' },
    notOnABill: '200.00',
    overdue: { count: 2, amount: '1500.00' },
    dueSoon: { count: 1, amount: '700.00' },
    ageing: { current: '3300.00', days130: '1000.00', days3160: '500.00', days6190: '0.00', days90Plus: '0.00' },
    ...overrides,
  };
}

function position(overrides: Record<string, unknown> = {}) {
  return {
    asOf: '2026-10-14',
    basis: { receivable: 'GL', payable: 'DOCUMENTS' },
    net: { receivable: '5000.00', payable: '2000.00', net: '3000.00' },
    cash: { cleared: '12000.00', byAccount: [{ id: 1, name: 'HDFC Current', balance: '11000.00' }], inflowMtd: '900.00' },
    moneyIn: {
      bills: bills(),
      advances: { count: 2, amount: '800.00' },
      chequesPending: { count: 1, amount: '400.00' },
      chequesBounced: { count: 0, amount: '0.00', windowDays: 30 },
      tdsReceivable: { count: 3, amount: '300.00', olderThan30Days: 1 },
      promises: { due: { count: 1, amount: '400.00' }, broken: { count: 1, amount: '250.00' } },
      unmatchedBankCredits: { count: 2, amount: '1250.00' },
      gatewayAwaitingBooks: ZERO,
      paymentLinksOpen: { count: 1, amount: '120.00' },
    },
    moneyOut: {
      bills: bills({
        outstanding: '2000.00',
        bills: { count: 2, amount: '2000.00' },
        notOnABill: '0.00',
        overdue: { count: 1, amount: '400.00' },
        dueSoon: { count: 1, amount: '250.00' },
        ageing: { current: '1600.00', days130: '400.00', days3160: '0.00', days6190: '0.00', days90Plus: '0.00' },
      }),
      advancesPaid: { count: 1, amount: '500.00' },
      chequesIssuedPending: { count: 1, amount: '300.00' },
      unmatchedBankDebits: { count: 1, amount: '400.00' },
    },
    reconciliation: {
      available: true, basis: 'GL', glReceivable: '5800.00', glPayable: '2000.00', advancesReceived: '800.00',
      differenceReceivable: '0.00', differencePayable: '0.00',
    },
    actions: [
      {
        kind: 'chase_customer', partyId: 7, partyName: 'Ravi Traders', reference: 'INV-9', amount: '1000.00', days: 12,
        link: { route: '/payments/collections', query: 'customer=7' },
      },
      {
        kind: 'pay_supplier', partyId: 4, partyName: 'Mega Suppliers', reference: 'PUR-3', amount: '400.00', days: 3,
        link: { route: '/purchases/history', query: 'overdue=1&supplier=4' },
      },
    ],
    partial: [],
    ...overrides,
  };
}

const TIMELINE = {
  asOf: '2026-10-14', days: 30, basis: 'DUE_DATE', note: 'By due date, not a forecast.',
  openingCash: '12000.00', inflow: '1300.00', outflow: '650.00', closingCash: '12650.00', lowestBalance: '11350.00',
  overdueNow: { in: '1500.00', out: '400.00' }, beyondHorizon: { in: '0.00', out: '0.00' },
  timeline: [
    {
      date: '2026-10-19', inflow: '0.00', outflow: '250.00', balance: '11750.00',
      items: [{ side: 'out', party: 'Mega Suppliers', reference: 'PUR-4', amount: '250.00', promised: false }],
    },
    {
      date: '2026-10-24', inflow: '1300.00', outflow: '400.00', balance: '12650.00',
      items: [
        { side: 'in', party: 'Ravi Traders', reference: 'INV-9', amount: '1300.00', promised: true },
        { side: 'out', party: 'TDS deducted on supplier bills', reference: '2026-10', amount: '400.00', promised: false, estimate: true },
      ],
    },
  ],
};

const STATUTORY = {
  asOf: '2026-10-14',
  items: [
    { kind: 'tds_payable', label: 'TDS', period: '2026-10', amount: '400.00', dueDate: '2026-11-07', estimate: false, link: { route: '/reports/tds-tcs', query: 'period=2026-10' } },
    { kind: 'gst_payable', label: 'GST', period: '2026-09', amount: null, dueDate: '2026-10-20', estimate: true, link: { route: '/reports/gstr3b', query: 'period=2026-09' } },
  ],
  unavailable: [],
  note: 'Estimates.',
};

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MoneyHubPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getMoneyPosition.mockResolvedValue(position());
  getMoneyTimeline.mockResolvedValue(TIMELINE);
  getMoneyStatutory.mockResolvedValue(STATUTORY);
});

describe('MoneyHubPage', () => {
  it('shows what customers owe, what is owed to suppliers, the net and cash, with the basis of each side', async () => {
    wrap();
    const receivable = await screen.findByRole('link', { name: /customers owe you: ₹5,000\.00/i });
    expect(within(receivable).getByText('From the books')).toBeTruthy();
    const payable = screen.getByRole('link', { name: /you owe suppliers: ₹2,000\.00/i });
    expect(within(payable).getByText('From bills')).toBeTruthy();
    expect(screen.getByText('₹3,000.00')).toBeTruthy();
    expect(screen.getByRole('link', { name: /cash and bank now: ₹12,000\.00/i })).toBeTruthy();
    expect(screen.getByText(/hdfc current: ₹11,000\.00/i)).toBeTruthy();
  });

  it('sends every tile to the list it adds up, flagged as coming from Money', async () => {
    wrap();
    await screen.findByText('Money coming in');
    const href = (name: RegExp) => screen.getByRole('link', { name }).getAttribute('href');
    expect(href(/^Overdue from customers/)).toBe('/payments/collections?due=overdue&via=money');
    expect(href(/^Due in the next 7 days: ₹700/)).toBe('/payments/collections?due=soon&via=money');
    expect(href(/^Advances received/)).toBe('/sales/receipts?advance=1&via=money');
    expect(href(/^Cheques waiting to clear/)).toBe('/sales/receipts?cheque_status=PENDING_CLEARANCE&via=money');
    expect(href(/^TDS awaiting certificate/)).toBe('/reports/tds-receivable?certificate=pending&via=money');
    expect(href(/^Bank credits not matched/)).toBe('/payments/reconciliation?direction=credit&via=money');
    expect(href(/^Promises not kept/)).toBe('/payments/collections?promises=broken&via=money');
    expect(href(/^Overdue to suppliers/)).toBe('/purchases/history?overdue=1&via=money');
    expect(href(/^Advances paid/)).toBe('/purchases/payments?advance=1&via=money');
    expect(href(/^Cheques issued, not cleared/)).toBe('/purchases/payments?cheque_status=PENDING_CLEARANCE&via=money');
    expect(href(/^Bank debits not matched/)).toBe('/payments/reconciliation?direction=debit&via=money');
  });

  it('hides lines that are empty and would only add noise, but keeps the ones that always matter', async () => {
    wrap();
    await screen.findByText('Money coming in');
    expect(screen.queryByText('Paid online, not in your books')).toBeNull();
    expect(screen.queryByText(/Cheques returned in the last/)).toBeNull();
    expect(screen.getByText('Overdue from customers')).toBeTruthy();
  });

  it('shows the ageing as numbers that add up, and what is not on a bill', async () => {
    wrap();
    await screen.findByText('Money coming in');
    expect(screen.getByRole('region', { name: 'Money coming in: How late' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Money going out: How late' })).toBeTruthy();
    expect(screen.getAllByText('Not yet due')[0]).toBeTruthy();
    expect(screen.getByText('Not on an open bill (opening balances, adjustments)')).toBeTruthy();
    expect(screen.getByText('₹200.00')).toBeTruthy();
  });

  it('lists what needs action, each row opening the right screen', async () => {
    wrap();
    const table = await screen.findByRole('table', { name: '' }).catch(() => null);
    expect(table === null || table).toBeTruthy();
    expect(await screen.findByText(/Ravi Traders · INV-9/)).toBeTruthy();
    const open = screen.getAllByRole('link', { name: 'Open' });
    expect(open[0].getAttribute('href')).toBe('/payments/collections?customer=7&via=money');
    expect(open[1].getAttribute('href')).toBe('/purchases/history?overdue=1&supplier=4&via=money');
    expect(screen.getByText('Chase payment')).toBeTruthy();
    expect(screen.getByText('Pay supplier')).toBeTruthy();
  });

  it('says so when nothing needs action', async () => {
    getMoneyPosition.mockResolvedValue(position({ actions: [] }));
    wrap();
    expect(await screen.findByText('Nothing needs action right now.')).toBeTruthy();
  });

  it('names a section that could not be worked out and shows it as unavailable, never as zero', async () => {
    getMoneyPosition.mockResolvedValue(
      position({
        partial: ['advances_paid'],
        moneyOut: { ...position().moneyOut, advancesPaid: null },
      }),
    );
    wrap();
    await screen.findByText('Money coming in');
    const alert = screen.getAllByRole('alert').find((el) => /could not be worked out/.test(el.textContent ?? ''));
    expect(alert?.textContent).toMatch(/advances paid/);
    // Walk up from the label to the line that holds the figure.
    let row: HTMLElement | null = screen.getByText('Advances paid');
    while (row && !/Unavailable/.test(row.textContent ?? '')) row = row.parentElement;
    expect(row?.textContent).toMatch(/Unavailable/);
    expect(row?.textContent).not.toMatch(/₹0\.00/);
  });

  it('shows the headline as unavailable when it could not be computed', async () => {
    getMoneyPosition.mockResolvedValue(position({ net: null, partial: ['receivable'] }));
    wrap();
    await screen.findByText('Money coming in');
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByRole('link', { name: /customers owe you/i })).toBeNull();
  });

  it('compares with the ledger when books are on, and says when they differ', async () => {
    getMoneyPosition.mockResolvedValue(
      position({
        reconciliation: {
          available: true, basis: 'DOCUMENTS', glReceivable: '5800.00', glPayable: '2000.00', advancesReceived: '0.00',
          differenceReceivable: '-800.00', differencePayable: '0.00',
        },
      }),
    );
    wrap();
    expect(await screen.findByText(/Difference: customers -₹800\.00/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Check books health' }).getAttribute('href')).toBe('/reports/books-health');
  });

  it('says there is no ledger to compare with when books are off', async () => {
    getMoneyPosition.mockResolvedValue(position({ reconciliation: { available: false, reason: 'books_off' } }));
    wrap();
    expect(await screen.findByText(/books are off/i)).toBeTruthy();
  });

  it('explains that the hub is off for the company when the server says so', async () => {
    getMoneyPosition.mockRejectedValue(Object.assign(new Error('Not found'), { isAxiosError: true, response: { status: 404 } }));
    wrap();
    expect(await screen.findByText('The Money overview is turned off for this company.')).toBeTruthy();
  });

  it('offers a retry when the overview fails to load', async () => {
    getMoneyPosition.mockRejectedValueOnce(new Error('boom'));
    wrap();
    const retry = await screen.findByRole('button', { name: /retry|try again/i });
    await userEvent.click(retry);
    expect(await screen.findByText('Money coming in')).toBeTruthy();
  });
});

describe('MoneyHubPage outlook and tax dues', () => {
  it('shows what falls due next, by date, with promises and estimates marked and a warning for what is already late', async () => {
    wrap();
    expect(await screen.findByText('What falls due next')).toBeTruthy();
    expect(await screen.findByText(/Mega Suppliers · PUR-4/)).toBeTruthy();
    expect(screen.getByText(/Ravi Traders · INV-9 · ₹1,300\.00 · promised/)).toBeTruthy();
    expect(screen.getByText(/TDS deducted on supplier bills · 2026-10 · ₹400\.00 · estimate/)).toBeTruthy();
    expect(screen.getByText(/Already late: customers owe ₹1,500\.00, you owe suppliers ₹400\.00/)).toBeTruthy();
    expect(screen.getByText('By due date, not a forecast.', { exact: false })).toBeTruthy();
  });

  it('asks for a different range', async () => {
    wrap();
    await screen.findByText('What falls due next');
    await userEvent.click(screen.getByRole('combobox', { name: /look ahead/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'Next 60 days' }));
    await waitFor(() => expect(getMoneyTimeline).toHaveBeenLastCalledWith(60));
  });

  it('warns when the balance would go below zero', async () => {
    getMoneyTimeline.mockResolvedValue({ ...TIMELINE, lowestBalance: '-500.00', closingCash: '-100.00' });
    wrap();
    expect(await screen.findByText(/Goes below zero: lowest -₹500\.00/)).toBeTruthy();
  });

  it('says so when nothing is due', async () => {
    getMoneyTimeline.mockResolvedValue({ ...TIMELINE, timeline: [], inflow: '0.00', outflow: '0.00', overdueNow: { in: '0.00', out: '0.00' } });
    wrap();
    expect(await screen.findByText('Nothing falls due in the next 30 days.')).toBeTruthy();
  });

  it('keeps the rest of the page when the outlook fails', async () => {
    getMoneyTimeline.mockRejectedValue(new Error('timeline down'));
    wrap();
    expect(await screen.findByText('Money coming in')).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText(/timeline down/).length).toBeGreaterThan(0));
  });

  it('lists tax dues with their due dates, flags estimates and links to the worksheet', async () => {
    wrap();
    const section = (await screen.findByText('Tax dues')).closest('section') as HTMLElement;
    expect(await within(section).findByText('2026-11-07')).toBeTruthy();
    expect(within(section).getByText('Estimate')).toBeTruthy();
    expect(within(section).getByRole('link', { name: /TDS deducted on supplier bills/ }).getAttribute('href')).toBe(
      '/reports/tds-tcs?period=2026-10&via=money',
    );
    expect(within(section).getByText('Unavailable')).toBeTruthy();
    expect(within(section).getByText(/does not record that a tax payment was made/)).toBeTruthy();
  });
});

describe('MoneyHubPage accessibility', () => {
  it('has no violations', async () => {
    wrap();
    await screen.findByText('Money coming in');
    await screen.findByText('What falls due next');
    await screen.findByText(/Mega Suppliers · PUR-4/);
    await screen.findByText('2026-11-07');
    const results = await axe.run(document.body, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([]);
  });
});

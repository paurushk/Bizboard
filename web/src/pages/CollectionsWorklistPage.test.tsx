import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CollectionsWorklistPage } from '@/pages/CollectionsWorklistPage';
import type { PaymentPromise } from '@/types/domain';

// Payment-promise worklist section: company-wide open promises, soonest
// first, with an overdue flag and a resolve action gated to
// OWNER/MANAGER/ACCOUNTANT (mirrors the backend gate in
// payments.promise_to_pay — see canManagePaymentPromises).

function isoDaysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

const OWNER_USER = { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 };
const SALES_STAFF_USER = {
  id: 2,
  email: 'staff@x.test',
  fullName: 'Staff',
  role: 'SALES_STAFF',
  companyId: 9,
};
let currentUser: Record<string, unknown> = OWNER_USER;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: currentUser }),
}));

const listOpenInvoices = vi.fn(async () => [] as Array<{
  invoiceId: number;
  invoiceNumber: string;
  customerName: string;
  daysOverdue: number;
  amountReceived: string;
  outstanding: string;
  customerOutstanding: string;
}>);
const listCollectionsWorklist = vi.fn(async () => [] as Array<{
  invoiceId: number;
  invoiceNumber: string;
  customerName: string;
  dueDate: string;
  outstanding: string;
  predictedDaysLate: number | null;
  confident: boolean;
}>);
const flags = { predictive: false };

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) => key === 'ENABLE_PREDICTIVE_DUNNING' && flags.predictive,
  };
});

vi.mock('@/api/osPlan', () => ({
  listCollectionsWorklist: () => listCollectionsWorklist(),
  listOpenInvoices: () => listOpenInvoices(),
}));

const listPaymentPromises = vi.fn(async () => [] as PaymentPromise[]);
const resolvePaymentPromise = vi.fn(async (id: number) => ({ id, resolved: true }) as PaymentPromise);
const getCompany = vi.fn(async () => ({ name: 'Test Agency', upiId: 'agency@upi' }));
const openShareUrl = vi.fn();

vi.mock('@/utils/safeUrl', () => ({
  openShareUrl: (url: string) => openShareUrl(url),
}));

vi.mock('@/api/resources', () => ({
  listPaymentPromises: () => listPaymentPromises(),
  resolvePaymentPromise: (id: number) => resolvePaymentPromise(id),
  getCompany: () => getCompany(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const SOON_PROMISE: PaymentPromise = {
  id: 1,
  customer: 10,
  customerName: 'Later Customer',
  invoice: 100,
  invoiceNumber: 'INV-0100',
  promisedDate: isoDaysFromNow(5),
  note: 'Will pay after payday',
  resolved: false,
};

const OVERDUE_PROMISE: PaymentPromise = {
  id: 2,
  customer: 11,
  customerName: 'Overdue Customer',
  invoice: null,
  promisedDate: isoDaysFromNow(-2),
  note: 'Promised last week',
  resolved: false,
};

const TODAY_PROMISE: PaymentPromise = {
  id: 3,
  customer: 12,
  customerName: 'Due Today Customer',
  promisedDate: isoDaysFromNow(0),
  note: 'Pays at closing',
  resolved: false,
};

describe('CollectionsWorklistPage — payment promises worklist', () => {
  afterEach(() => {
    currentUser = OWNER_USER;
    listPaymentPromises.mockReset();
    resolvePaymentPromise.mockReset();
    listOpenInvoices.mockReset();
    listOpenInvoices.mockResolvedValue([]);
    listCollectionsWorklist.mockReset();
    listCollectionsWorklist.mockResolvedValue([]);
    flags.predictive = false;
  });

  it('renders open promises sorted soonest-first and flags overdue/today rows', async () => {
    listPaymentPromises.mockResolvedValue([SOON_PROMISE, OVERDUE_PROMISE, TODAY_PROMISE]);
    wrap(<CollectionsWorklistPage />);

    await screen.findByText('Later Customer');
    const rows = await screen.findAllByRole('row');
    // rows[0] is the header row.
    const bodyRowText = rows.slice(1).map((row) => row.textContent ?? '');
    const overdueIdx = bodyRowText.findIndex((text) => text.includes('Overdue Customer'));
    const todayIdx = bodyRowText.findIndex((text) => text.includes('Due Today Customer'));
    const laterIdx = bodyRowText.findIndex((text) => text.includes('Later Customer'));
    expect(overdueIdx).toBeLessThan(todayIdx);
    expect(todayIdx).toBeLessThan(laterIdx);

    // Overdue and due-today rows are visually flagged; the soonest-in-future one is not.
    // Past-due is overdue; a promise for today is "due today", not overdue.
    expect(screen.getAllByText('Overdue').length).toBe(1);
    expect(screen.getAllByText('Due today').length).toBe(1);
    expect(screen.getByText('INV-0100')).toBeTruthy();
  });

  it('shows the resolve action for OWNER/MANAGER/ACCOUNTANT and removes the row once resolved', async () => {
    listPaymentPromises.mockResolvedValueOnce([OVERDUE_PROMISE]);
    listPaymentPromises.mockResolvedValueOnce([]);
    currentUser = OWNER_USER;
    wrap(<CollectionsWorklistPage />);

    await screen.findByText('Overdue Customer');
    const resolveBtn = screen.getByRole('button', { name: /mark as resolved/i });
    await userEvent.click(resolveBtn);

    expect(resolvePaymentPromise).toHaveBeenCalledWith(2);
    await waitFor(() => expect(screen.queryByText('Overdue Customer')).toBeNull());
  });

  it('hides the resolve action for a role without manage permission but still renders the list', async () => {
    currentUser = SALES_STAFF_USER;
    listPaymentPromises.mockResolvedValue([SOON_PROMISE]);
    wrap(<CollectionsWorklistPage />);

    await screen.findByText('Later Customer');
    expect(screen.queryByRole('button', { name: /mark as resolved/i })).toBeNull();
  });

  it('shows invoice outstanding, days overdue, and amount received on an open invoice', async () => {
    listOpenInvoices.mockResolvedValue([{
      invoiceId: 9,
      invoiceNumber: 'INV-OPEN',
      customerName: 'Open Customer',
      daysOverdue: 4,
      amountReceived: '40.00',
      outstanding: '60.00',
      customerOutstanding: '60.00',
    }]);
    listPaymentPromises.mockResolvedValue([]);
    wrap(<CollectionsWorklistPage />);
    expect(await screen.findByText('INV-OPEN')).toBeTruthy();
    expect(screen.getByText('4')).toBeTruthy();
    expect(screen.getByText('Invoice balance')).toBeTruthy();
    expect(screen.getByText('Customer total')).toBeTruthy();
    expect(screen.getAllByText(/60/).length).toBeGreaterThan(0);
    expect(screen.queryByText('Usually late')).toBeNull();
    expect(listCollectionsWorklist).not.toHaveBeenCalled();
  });

  it('loads the predictive list only when that flag is on', async () => {
    flags.predictive = true;
    listCollectionsWorklist.mockResolvedValue([{
      invoiceId: 3,
      invoiceNumber: 'INV-LATE',
      customerName: 'Late Customer',
      dueDate: '2026-09-01',
      outstanding: '10.00',
      predictedDaysLate: 2,
      confident: true,
    }]);
    listPaymentPromises.mockResolvedValue([]);
    wrap(<CollectionsWorklistPage />);
    expect(await screen.findByText('Usually late')).toBeTruthy();
    expect(screen.getByText('INV-LATE')).toBeTruthy();
  });

  it('shows an empty state instead of crashing when there are no open promises', async () => {
    listPaymentPromises.mockResolvedValue([]);
    wrap(<CollectionsWorklistPage />);

    expect(await screen.findByText('No open payment promises company-wide.')).toBeTruthy();
  });
});

describe('Smart Aging Cohorts & WhatsApp Dunning Engine (Sprint 1.2)', () => {
  beforeEach(() => {
    openShareUrl.mockReset();
    listPaymentPromises.mockResolvedValue([]);
    listOpenInvoices.mockResolvedValue([
      {
        invoiceId: 10,
        invoiceNumber: 'INV-10',
        customerName: 'Upcoming Customer',
        customerPhone: '9876543210',
        daysOverdue: 0,
        amountReceived: '0.00',
        outstanding: '1000.00',
        customerOutstanding: '1000.00',
      },
      {
        invoiceId: 11,
        invoiceNumber: 'INV-11',
        customerName: 'Critical Customer',
        customerPhone: '9876543211',
        daysOverdue: 50,
        amountReceived: '0.00',
        outstanding: '5000.00',
        customerOutstanding: '5000.00',
      },
    ]);
  });

  it('renders 4 Aging Cohort KPI cards with total outstanding', async () => {
    wrap(<CollectionsWorklistPage />);
    expect(await screen.findByText('Due soon (0–3 days)')).toBeTruthy();
    expect(screen.getByText('Overdue 1–15 days (urgent)')).toBeTruthy();
    expect(screen.getByText('Overdue 16–45 days (firm)')).toBeTruthy();
    expect(screen.getByText('Overdue 45+ days (escalate)')).toBeTruthy();
  });

  it('filters invoice rows when a cohort card is clicked', async () => {
    wrap(<CollectionsWorklistPage />);
    expect(await screen.findByText('Upcoming Customer')).toBeTruthy();
    expect(screen.getByText('Critical Customer')).toBeTruthy();

    // Click Critical 45D+ cohort card
    const criticalCard = screen.getByText('Overdue 45+ days (escalate)');
    await userEvent.click(criticalCard);

    // Only Critical Customer should remain
    expect(screen.getByText('Critical Customer')).toBeTruthy();
    expect(screen.queryByText('Upcoming Customer')).toBeNull();
  });

  it('shows each cohort total and invoice count on its own card', async () => {
    wrap(<CollectionsWorklistPage />);
    const soon = (await screen.findByText('Due soon (0–3 days)')).closest('button') as HTMLElement;
    const critical = screen.getByText('Overdue 45+ days (escalate)').closest('button') as HTMLElement;
    expect(within(soon).getByText('1 invoices')).toBeTruthy();
    expect(within(critical).getByText('1 invoices')).toBeTruthy();
    expect(within(critical).getByText(/5,000/)).toBeTruthy();
    // A cohort with nothing in it still shows, with a zero count.
    const urgent = screen.getByText('Overdue 1–15 days (urgent)').closest('button') as HTMLElement;
    expect(within(urgent).getByText('0 invoices')).toBeTruthy();
  });

  it('marks the chosen cohort as pressed and clears the filter when clicked again', async () => {
    wrap(<CollectionsWorklistPage />);
    const critical = (await screen.findByText('Overdue 45+ days (escalate)')).closest('button') as HTMLElement;
    expect(critical.getAttribute('aria-pressed')).toBe('false');

    await userEvent.click(critical);
    expect(critical.getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryByText('Upcoming Customer')).toBeNull();

    await userEvent.click(critical);
    expect(critical.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('Upcoming Customer')).toBeTruthy();
    expect(screen.getByText('Critical Customer')).toBeTruthy();
  });

  it('switches straight from one cohort to another', async () => {
    wrap(<CollectionsWorklistPage />);
    const critical = (await screen.findByText('Overdue 45+ days (escalate)')).closest('button') as HTMLElement;
    const soon = screen.getByText('Due soon (0–3 days)').closest('button') as HTMLElement;

    await userEvent.click(critical);
    await userEvent.click(soon);
    expect(soon.getAttribute('aria-pressed')).toBe('true');
    expect(critical.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('Upcoming Customer')).toBeTruthy();
    expect(screen.queryByText('Critical Customer')).toBeNull();
  });

  it('opens WhatsApp Nudge dialog with tailored dunning message and UPI link', async () => {
    wrap(<CollectionsWorklistPage />);
    const nudgeBtns = await screen.findAllByRole('button', { name: /whatsapp reminder/i });
    expect(nudgeBtns.length).toBeGreaterThan(0);

    // Click WhatsApp Nudge on Critical Customer (second row)
    await userEvent.click(nudgeBtns[1]);

    // Dialog should open
    expect(await screen.findByText(/WhatsApp reminder — Critical Customer/i)).toBeTruthy();
    const preview = screen.getByLabelText(/whatsapp message preview/i) as HTMLTextAreaElement;
    expect(preview.value).toContain('URGENT NOTICE');
    expect(preview.value).toContain('severely overdue for 50 days');
    expect(preview.value).toContain('upi://pay?pa=agency%40upi');

    // Click Send WhatsApp
    const sendBtn = screen.getByRole('button', { name: /send on whatsapp/i });
    await userEvent.click(sendBtn);

    expect(openShareUrl).toHaveBeenCalledWith(
      expect.stringContaining('https://wa.me/919876543211?text='),
    );
  });
});

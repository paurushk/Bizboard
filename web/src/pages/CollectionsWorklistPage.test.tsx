import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/config/featureFlags', () => ({
  isRuntimeFlagEnabled: (key: string) => key === 'ENABLE_PREDICTIVE_DUNNING' && flags.predictive,
}));

vi.mock('@/api/osPlan', () => ({
  listCollectionsWorklist: () => listCollectionsWorklist(),
  listOpenInvoices: () => listOpenInvoices(),
}));

const listPaymentPromises = vi.fn(async () => [] as PaymentPromise[]);
const resolvePaymentPromise = vi.fn(async (id: number) => ({ id, resolved: true }) as PaymentPromise);

vi.mock('@/api/resources', () => ({
  listPaymentPromises: () => listPaymentPromises(),
  resolvePaymentPromise: (id: number) => resolvePaymentPromise(id),
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

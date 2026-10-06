export type OpportunityAmountRow = {
  customer?: number | null;
  amount?: string | number | null;
};

export type OpportunityPage = {
  results: OpportunityAmountRow[];
  next: string | null;
};

export type OpportunitySum = { total: number; truncated: boolean };

/** Sum this customer's opportunity amounts across every page. Stops if a page repeats or after 50 pages. */
export async function sumCustomerOpportunityValue(
  customerId: number,
  load: (page: number) => Promise<OpportunityPage>,
): Promise<OpportunitySum> {
  let page = 1;
  let total = 0;
  let truncated = false;
  const seen = new Set<number>();
  while (!seen.has(page)) {
    seen.add(page);
    const data = await load(page);
    for (const row of data.results) {
      if (row.customer !== customerId) continue;
      const amount = Number(row.amount || 0);
      if (Number.isFinite(amount)) total += amount;
    }
    if (!data.next) break;
    if (seen.size >= 50) {
      truncated = true;
      break;
    }
    page += 1;
  }
  return { total, truncated };
}

export function customerNextAction(input: {
  recommended?: string | null;
  outstanding?: string | number | null;
  openTickets?: number;
  /** Tickets have not loaded yet, so "nothing waiting" would be a guess. */
  ticketsPending?: boolean;
}): string {
  const recommended = (input.recommended || '').trim();
  if (recommended) return recommended;
  const due = Number(input.outstanding || 0);
  if (Number.isFinite(due) && due > 0) return 'due';
  if (input.ticketsPending) return '';
  if ((input.openTickets ?? 0) > 0) return 'ticket';
  return 'quiet';
}

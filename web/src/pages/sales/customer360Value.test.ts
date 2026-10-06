import { describe, expect, it, vi } from 'vitest';
import { customerNextAction, sumCustomerOpportunityValue } from './customer360Value';

describe('sumCustomerOpportunityValue', () => {
  it('adds this customer across pages and ignores other customers', async () => {
    const load = vi.fn(async (page: number) => {
      if (page === 1) {
        return {
          results: [
            { customer: 4, amount: '10' },
            { customer: 9, amount: '99' },
          ],
          next: 'page-2',
        };
      }
      return { results: [{ customer: 4, amount: '2.5' }], next: null };
    });
    await expect(sumCustomerOpportunityValue(4, load)).resolves.toEqual({ total: 12.5, truncated: false });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('stops after 50 pages and marks the total as partial', async () => {
    const load = vi.fn(async (page: number) => ({
      results: [{ customer: 4, amount: '1' }],
      next: page >= 60 ? null : 'more',
    }));
    await expect(sumCustomerOpportunityValue(4, load)).resolves.toEqual({ total: 50, truncated: true });
    expect(load).toHaveBeenCalledTimes(50);
  });
});

describe('customerNextAction', () => {
  it('keeps a server recommendation, otherwise dues, then an open ticket', () => {
    expect(customerNextAction({ recommended: 'Call tomorrow', outstanding: '10' })).toBe('Call tomorrow');
    expect(customerNextAction({ outstanding: '10' })).toBe('due');
    expect(customerNextAction({ outstanding: '0', openTickets: 1 })).toBe('ticket');
    expect(customerNextAction({})).toBe('quiet');
    expect(customerNextAction({ ticketsPending: true })).toBe('');
  });

  it('ignores amounts that are not numbers', async () => {
    const load = vi.fn(async () => ({
      results: [
        { customer: 4, amount: 'nope' },
        { customer: 4, amount: '3' },
      ],
      next: null,
    }));
    await expect(sumCustomerOpportunityValue(4, load)).resolves.toEqual({ total: 3, truncated: false });
  });
});

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { selectableAccounts } from '@/components/accounting/accountOptions';
import type { AccountingAccount } from '@/types/domain';

const accounts: AccountingAccount[] = [
  { id: 1, code: '1100', name: 'Cash', type: 'ASSET', isActive: true },
  { id: 2, code: '5400', name: 'Cost of Goods Sold', type: 'EXPENSE', isActive: true },
  { id: 3, code: '5999', name: 'Old Suspense', type: 'EXPENSE', isActive: false },
];

describe('selectableAccounts', () => {
  it('hides inactive accounts unless asked', () => {
    expect(selectableAccounts(accounts).map((a) => a.code)).toEqual(['1100', '5400']);
    expect(selectableAccounts(accounts, { allowInactive: true })).toHaveLength(3);
  });

  it('filters by type', () => {
    expect(selectableAccounts(accounts, { types: ['ASSET'] }).map((a) => a.code)).toEqual(['1100']);
  });

  it('copes with no data', () => {
    expect(selectableAccounts(undefined)).toEqual([]);
  });
});

describe('AccountSelect', () => {
  it('finds an account by code or name and reports its id', async () => {
    const onChange = vi.fn();
    render(<AccountSelect accounts={accounts} value="" onChange={onChange} label="Account" />);
    await userEvent.type(screen.getByRole('combobox', { name: 'Account' }), 'cost');
    await userEvent.click(await screen.findByRole('option', { name: /5400 — Cost of Goods Sold/ }));
    expect(onChange).toHaveBeenCalledWith('2');
  });

  it('does not offer an inactive account', async () => {
    render(<AccountSelect accounts={accounts} value="" onChange={vi.fn()} label="Account" />);
    await userEvent.type(screen.getByRole('combobox', { name: 'Account' }), 'suspense');
    expect(screen.queryByRole('option', { name: /5999/ })).toBeNull();
  });

  it('keeps a saved but now inactive account visible', () => {
    render(<AccountSelect accounts={accounts} value="3" onChange={vi.fn()} label="Account" />);
    expect((screen.getByRole('combobox', { name: 'Account' }) as HTMLInputElement).value).toBe('5999 — Old Suspense');
  });
});

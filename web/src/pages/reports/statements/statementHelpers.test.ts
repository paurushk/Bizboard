import { describe, expect, it } from 'vitest';
import { splitBalanceSheet, visibleLines, type ScheduleIii } from './statementHelpers';

const schedule: ScheduleIii = {
  sections: [
    { key: 'non_current_assets', label: 'Non-current assets', amount: '1000.00', lines: [] },
    { key: 'current_assets', label: 'Current assets', amount: '4000.00', lines: [] },
    {
      key: 'equity', label: 'Equity', amount: '3000.00',
      lines: [
        { key: 'other_equity', label: 'Other equity', amount: '2000.00' },
        // current earnings sit inside Equity already
        { key: 'surplus_in_profit_and_loss', label: 'Surplus', amount: '1000.00' },
      ],
    },
    { key: 'non_current_liabilities', label: 'NCL', amount: '0.00', lines: [] },
    { key: 'current_liabilities', label: 'Current liabilities', amount: '2000.00', lines: [] },
  ],
};

describe('splitBalanceSheet', () => {
  it('compares assets with equity plus liabilities without adding profit a second time', () => {
    const r = splitBalanceSheet(schedule);
    expect(r.totalAssets).toBe(5000);
    expect(r.totalEquityLiabilities).toBe(5000);
    expect(r.difference).toBe(0);
  });

  it('reports the gap when the sides differ', () => {
    const r = splitBalanceSheet({
      sections: [schedule.sections[0], { key: 'current_liabilities', label: 'CL', amount: '300', lines: [] }],
    });
    expect(r.difference).toBe(700);
  });

  it('handles a missing schedule', () => {
    const r = splitBalanceSheet(undefined);
    expect(r.assets).toEqual([]);
    expect(r.difference).toBe(0);
  });
});

describe('visibleLines', () => {
  it('drops empty Schedule III headings but keeps lines with an amount or accounts', () => {
    const lines = visibleLines({
      key: 's', label: 's', amount: '5',
      lines: [
        { key: 'a', label: 'a', amount: '0.00' },
        { key: 'b', label: 'b', amount: '5.00' },
        { key: 'c', label: 'c', amount: '0.00', accounts: [{ code: '1', name: 'x', amount: '0' }] },
      ],
    });
    expect(lines.map((l) => l.key)).toEqual(['b', 'c']);
  });
});

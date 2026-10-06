import { describe, expect, it } from 'vitest';
import { booksBannerState, booksTotalsTrusted } from './booksState';

describe('booksBannerState', () => {
  const base = { loaded: true, accountingEnabled: true, backfillNeeded: false, accountCount: 12 };

  it('waits until settings have loaded', () => {
    expect(booksBannerState({ ...base, loaded: false })).toBe('unknown');
  });

  it('stays quiet when books are off', () => {
    expect(booksBannerState({ ...base, accountingEnabled: false, accountCount: 0 })).toBe('off');
  });

  it('says there is no chart before it talks about back-fill', () => {
    expect(booksBannerState({ ...base, accountCount: 0, backfillNeeded: true })).toBe('no-chart');
  });

  it('says older documents are not posted when the chart exists', () => {
    expect(booksBannerState({ ...base, backfillNeeded: true })).toBe('backfill');
  });

  it('ties when books are on, the chart exists, and back-fill is done', () => {
    expect(booksBannerState(base)).toBe('ties');
  });
});

describe('booksTotalsTrusted', () => {
  it('hides totals only when the chart is missing or back-fill is still needed', () => {
    expect(booksTotalsTrusted('no-chart')).toBe(false);
    expect(booksTotalsTrusted('backfill')).toBe(false);
    expect(booksTotalsTrusted('ties')).toBe(true);
    expect(booksTotalsTrusted('off')).toBe(true);
  });
});

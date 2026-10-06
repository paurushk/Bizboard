import { describe, expect, it } from 'vitest';
import { dateRangeForPreset } from './HistoryFilterBar';

describe('Indian financial year presets', () => {
  const may = new Date(2026, 4, 15);
  const february = new Date(2027, 1, 2);

  it('current FY runs 1 April to 31 March', () => {
    expect(dateRangeForPreset('currentFY', may)).toEqual({ dateFrom: '2026-04-01', dateTo: '2027-03-31' });
    expect(dateRangeForPreset('currentFY', february)).toEqual({ dateFrom: '2026-04-01', dateTo: '2027-03-31' });
  });

  it('previous FY is the year before', () => {
    expect(dateRangeForPreset('previousFY', may)).toEqual({ dateFrom: '2025-04-01', dateTo: '2026-03-31' });
  });

  it('quarters follow the GST year', () => {
    expect(dateRangeForPreset('q1', may)).toEqual({ dateFrom: '2026-04-01', dateTo: '2026-06-30' });
    expect(dateRangeForPreset('q2', may)).toEqual({ dateFrom: '2026-07-01', dateTo: '2026-09-30' });
    expect(dateRangeForPreset('q3', may)).toEqual({ dateFrom: '2026-10-01', dateTo: '2026-12-31' });
    expect(dateRangeForPreset('q4', february)).toEqual({ dateFrom: '2027-01-01', dateTo: '2027-03-31' });
  });
});

import { describe, expect, it } from 'vitest';
import { gstinStatusColor, gstinStatusLabelKey } from '@/utils/gstinStatus';

describe('gstinStatusColor', () => {
  it.each([
    ['VALID', 'success'],
    ['verified', 'success'],
    ['INVALID', 'error'],
    ['CANCELLED', 'error'],
    ['SUSPENDED', 'error'],
    ['FAILED', 'error'],
    ['UNVERIFIED', 'warning'],
    [undefined, 'warning'],
    ['SOMETHING_NEW', 'default'],
  ])('%s -> %s', (status, color) => {
    expect(gstinStatusColor(status)).toBe(color);
  });

  it('labels unknown statuses as unverified', () => {
    expect(gstinStatusLabelKey('SOMETHING_NEW')).toBe('customers.gstinStatusUnverified');
    expect(gstinStatusLabelKey('VALID')).toBe('customers.gstinStatusValid');
  });
});

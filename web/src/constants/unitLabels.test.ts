import { describe, expect, it } from 'vitest';
import { formatUnitLabel, STANDARD_UNITS } from '@/constants/unitLabels';
import { GST_RATE_OPTIONS } from '@/utils/gst';

describe('unit labels', () => {
  it('shows carton and pieces with full names', () => {
    expect(formatUnitLabel('CTN')).toContain('Carton');
    expect(formatUnitLabel('PCS')).toContain('Pieces');
    expect(STANDARD_UNITS).toContain('CTN');
  });
});

describe('GST rate labels', () => {
  it('describes every slab', () => {
    for (const option of GST_RATE_OPTIONS) {
      expect(option.label.length).toBeGreaterThan(2);
      expect(option.label).toMatch(/%/);
    }
    expect(GST_RATE_OPTIONS.find((o) => o.value === '5')?.label).toMatch(/Essential/i);
    expect(GST_RATE_OPTIONS.find((o) => o.value === '12')?.label).toMatch(/Processed/i);
    expect(GST_RATE_OPTIONS.find((o) => o.value === '40')?.label).toMatch(/Sin|demerit/i);
  });
});

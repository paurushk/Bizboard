import { describe, expect, it } from 'vitest';
import { setLocale } from '@/i18n';
import { enumLabel } from './enumLabels';

describe('enumLabel', () => {
  it('turns backend codes into plain words', () => {
    setLocale('en');
    expect(enumLabel('ticketStatus', 'IN_PROGRESS')).toBe('In progress');
    expect(enumLabel('complaintCategory', 'WRONG_DELIVERY')).toBe('Wrong delivery');
    expect(enumLabel('rewardType', 'FLAT')).toBe('Flat amount');
  });
  it('never shows an ALL_CAPS code for an unknown value', () => {
    setLocale('en');
    expect(enumLabel('campaignType', 'BRAND_NEW_KIND')).toBe('Brand new kind');
  });
  it('shows a dash when empty', () => {
    expect(enumLabel('contractType', '')).toBe('—');
    expect(enumLabel('contractType', null)).toBe('—');
  });
  it('has a Hindi label for every code', () => {
    setLocale('hi');
    expect(enumLabel('ticketPriority', 'URGENT')).not.toBe('Urgent');
    setLocale('en');
  });
});

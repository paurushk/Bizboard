import { describe, expect, it } from 'vitest';
import { en, hi } from '@/i18n';

type Bag = Record<string, string>;
const enQuick = (en as unknown as { quickEntry: Bag }).quickEntry;
const hiQuick = (hi as unknown as { quickEntry: Bag }).quickEntry;
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('quickEntry strings', () => {
  it('Hindi has every English key and no extras', () => {
    expect(Object.keys(hiQuick).sort()).toEqual(Object.keys(enQuick).sort());
  });

  it('every string is filled in, and Hindi keeps the same {placeholders}', () => {
    for (const key of Object.keys(enQuick)) {
      expect(enQuick[key].trim(), `en ${key}`).not.toBe('');
      expect(hiQuick[key].trim(), `hi ${key}`).not.toBe('');
      expect(placeholders(hiQuick[key]), `placeholders of ${key}`).toEqual(placeholders(enQuick[key]));
    }
  });

  it('Hindi is actually translated (not a copy of the English)', () => {
    const copied = Object.keys(enQuick).filter((key) => hiQuick[key] === enQuick[key] && /[A-Za-z]{3,}/.test(enQuick[key].replace(/\{\w+\}/g, '')));
    expect(copied).toEqual([]);
  });

  it('has the labels the screen and the help refer to', () => {
    for (const key of [
      'saveAndNext', 'saveAndOpen', 'saveBillAndNext', 'saveBillAndOpen', 'modeOrder', 'modeBill',
      'priceNote', 'estimatedTax', 'lowStock', 'creditHold', 'creditExceeded', 'shipTo', 'resume', 'discard',
      'savedOrder', 'savedOrderConfirmed', 'savedOrderNeedsApproval', 'savedOrderConfirmUnknown', 'savedBill',
      'quickOrder', 'quickEntryShort',
    ]) {
      expect(enQuick[key], key).toBeTruthy();
    }
  });
});

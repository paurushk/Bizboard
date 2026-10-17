import { describe, expect, it } from 'vitest';
import {
  applyScan,
  fillableLineCount,
  fillWithSystemQty,
  canPostReview,
  effectiveCounted,
  hasUnsavedCounts,
  lineIsOpen,
  openLineCount,
  summarizeReview,
  type CountLine,
} from '@/pages/inventory/countHelpers';

const line = (over: Partial<CountLine>): CountLine => ({ id: 1, productName: 'Soap', ...over });

describe('what is still open', () => {
  it('needs a number unless the line is skipped', () => {
    expect(lineIsOpen(line({}), {}, {})).toBe(true);
    expect(lineIsOpen(line({ countedQty: '3' }), {}, {})).toBe(false);
    expect(lineIsOpen(line({}), { '1': '0' }, {})).toBe(false);
    expect(lineIsOpen(line({}), {}, { '1': true })).toBe(false);
    expect(lineIsOpen(line({ skipped: true }), {}, {})).toBe(false);
    expect(lineIsOpen(line({ skipped: true }), {}, { '1': false })).toBe(true);
  });
  it('counts them', () => {
    const lines = [line({ id: 1 }), line({ id: 2, countedQty: '1' }), line({ id: 3 })];
    expect(openLineCount(lines, {}, {})).toBe(2);
    expect(openLineCount(lines, { '1': '5' }, { '3': true })).toBe(0);
  });
  it('prefers what was typed to what is saved', () => {
    expect(effectiveCounted(line({ countedQty: '3' }), { '1': '4' })).toBe('4');
    expect(effectiveCounted(line({ countedQty: '3' }), {})).toBe('3');
    expect(effectiveCounted(line({}), {})).toBe('');
  });
});

describe('hasUnsavedCounts', () => {
  const lines = [line({ id: 1, countedQty: '3' }), line({ id: 2 })];
  it('is false when nothing differs from what is saved', () => {
    expect(hasUnsavedCounts(lines, {}, {})).toBe(false);
    expect(hasUnsavedCounts(lines, { '1': '3' }, {})).toBe(false);
    expect(hasUnsavedCounts(lines, { '2': '' }, {})).toBe(false);
  });
  it('sees a changed number or a changed skip', () => {
    expect(hasUnsavedCounts(lines, { '1': '4' }, {})).toBe(true);
    expect(hasUnsavedCounts(lines, { '2': '1' }, {})).toBe(true);
    expect(hasUnsavedCounts(lines, {}, { '2': true })).toBe(true);
  });
});

describe('summarizeReview', () => {
  it('totals gains and losses and counts what needs a recheck', () => {
    const summary = summarizeReview([
      line({ id: 1, variance: '-2', varianceValueEstimate: '-10000.00', needsRecheck: true }),
      line({ id: 2, variance: '1', varianceValueEstimate: '40.00' }),
      line({ id: 3, variance: '0', varianceValueEstimate: '0.00' }),
      line({ id: 4, skipped: true }),
    ]);
    expect(summary).toEqual({ changed: 2, gain: 40, loss: 10000, recheck: 1, skipped: 1 });
  });
});

describe('canPostReview', () => {
  const lines = [
    line({ id: 1, variance: '-2', needsRecheck: true }),
    line({ id: 2, variance: '-1' }),
    line({ id: 3, needsRecheck: true, skipped: true }),
  ];
  it('waits for every flagged line to be ticked', () => {
    expect(canPostReview(lines, {})).toBe(false);
    expect(canPostReview(lines, { '1': true })).toBe(true);
  });
  it('is open when nothing is flagged', () => {
    expect(canPostReview([line({ id: 2, variance: '1' })], {})).toBe(true);
  });
});

describe('count automation', () => {
  const lines = [
    { id: 1, productName: 'Soap', productSku: 'SOAP', productBarcode: '890100', systemQty: '10', countedQty: null },
    { id: 2, productName: 'Rice', productSku: 'RICE', productBarcode: '', systemQty: '4', countedQty: '4' },
    { id: 3, productName: 'Tea', productSku: 'TEA', productBarcode: '', systemQty: null, countedQty: null },
  ];

  it('fills only open lines whose system quantity is visible', () => {
    expect(fillableLineCount(lines, {}, {})).toBe(1);
    expect(fillWithSystemQty(lines, {}, {})).toEqual({ '1': '10' });
    expect(fillWithSystemQty(lines, {}, { '1': true })).toEqual({});
  });

  it('counts one unit per scan, by barcode or by code', () => {
    const first = applyScan(lines, {}, {}, ' 890100 ');
    expect(first?.line.id).toBe(1);
    expect(first?.typed).toEqual({ '1': '1' });
    expect(applyScan(lines, first!.typed, {}, '890100')?.typed).toEqual({ '1': '2' });
    expect(applyScan(lines, {}, {}, 'rice')?.typed).toEqual({ '2': '5' });
  });

  it('knows an unknown code, and ignores skipped lines', () => {
    expect(applyScan(lines, {}, {}, 'nope')).toBeNull();
    expect(applyScan(lines, {}, { '1': true }, '890100')).toBeNull();
    expect(applyScan(lines, {}, {}, '  ')).toBeNull();
  });
});

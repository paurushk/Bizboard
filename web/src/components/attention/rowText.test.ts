import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { en } from '@/i18n/en';
import { setLocale } from '@/i18n';
import type { AttentionRow } from '@/types/domain';
import { attentionActionLabel, attentionReason, attentionTitle } from './rowText';

function row(code: string, params: Record<string, unknown>, extra: Partial<AttentionRow> = {}): AttentionRow {
  return {
    code, severity: 'warning', title: 'SERVER TITLE', moneyImpactPaise: 0, currency: 'INR', reason: 'SERVER REASON',
    actionLabel: 'Fix', actionHref: '/x', sourceTicket: 'T', entityRef: { type: 'company', id: 1 },
    dedupeKey: `${code}:1`, firstSeen: null, snoozeUntil: null, params, ...extra,
  };
}

afterEach(() => setLocale('en'));

describe('attention row text', () => {
  it('builds a title and reason from values, in English and Hindi', () => {
    const r = row('SALE_BELOW_COST', { product: 'Tea', price: '40', cost: '50' });
    expect(attentionTitle(r)).toBe('Tea sold below cost');
    expect(attentionReason(r)).toBe('Sold at ₹40 vs cost ₹50.');
    setLocale('hi');
    expect(attentionTitle(r)).toBe('Tea लागत से कम पर बिका');
    expect(attentionReason(r)).toBe('₹40 पर बिका, लागत ₹50।');
  });

  it('picks the variant a row names', () => {
    const r = row('LOW_STOCK_FAST_MOVER', { variant: 'transfer', product: 'Rice', qty: '5', from: 'Main' });
    expect(attentionTitle(r)).toContain('Suggested transfer 5 from Main');
    const none = row('DUPLICATE_PAYMENT', { variant: 'no_ref', count: 2, amount: '100', date: '2026-10-01' });
    expect(attentionTitle(none)).toBe('Possible duplicate receipt');
    expect(attentionReason(none)).toContain('no reference');
  });

  it('uses the same sentence for title and reason when the server did', () => {
    const r = row('AP_DUE_7D', { amount: '900' }, { title: 'Supplier bills', reason: 'Supplier bills' });
    expect(attentionReason(r)).toBe(attentionTitle(r));
    expect(attentionReason(r)).toBe('Supplier bills due in 7 days (~₹900).');
  });

  it('translates collection status and step codes', () => {
    const r = row('AR_COLLECTION_RISK', { customer: 'Ravi', status: 'overdue_severe', amount: '500', step: 'send_link' });
    expect(attentionTitle(r)).toBe('Ravi: overdue severe');
    expect(attentionReason(r)).toBe('Ravi overdue ₹500. Next: send link.');
    setLocale('hi');
    expect(attentionTitle(r)).toBe('Ravi: गंभीर बकाया');
  });

  it('rebuilds a merged customer row from its signals, and falls back for what it cannot translate', () => {
    const merged = row('AR_CUSTOMER', {
      customer: 'Ravi', count: 2,
      signals: [
        { code: 'AR_COLLECTION_RISK', params: { customer: 'Ravi', status: 'overdue', amount: '500', step: 'send_link' }, title: 't1', reason: 'r1' },
        { code: 'SOMETHING_UNKNOWN', params: {}, title: 't2', reason: 'server only' },
      ],
    });
    expect(attentionTitle(merged)).toBe('Ravi: 2 receivable issues');
    expect(attentionReason(merged)).toBe('Ravi overdue ₹500. Next: send link. server only');
    const single = row('AR_CUSTOMER', {
      customer: 'Ravi', count: 1,
      signals: [{ code: 'PREDICTED_LATE_PAYMENT', params: { customer: 'Ravi', days: 5, owed: '100', due: '2026-10-30' }, title: 't', reason: 'r' }],
    });
    expect(attentionTitle(single)).toBe('Ravi usually pays 5 days late');
  });

  it('keeps a person\'s own wording and falls back when values are missing', () => {
    const withNote = row('PROMISE_TO_PAY_DUE', { variant: 'amount_note', titleVariant: 'amount', customer: 'Ravi', amount: '100', note: 'Will pay Friday' });
    expect(attentionTitle(withNote)).toBe('Ravi promised to pay ₹100 today');
    expect(attentionReason(withNote)).toBe('Will pay Friday');
    expect(attentionTitle(row('SALE_BELOW_COST', {}))).toBe('SERVER TITLE');
    expect(attentionTitle(row('NOT_IN_CATALOGUE', { a: 1 }))).toBe('SERVER TITLE');
  });

  it('translates known action labels and keeps unknown ones', () => {
    expect(attentionActionLabel({ actionLabel: 'Send Link' })).toBe('Send link');
    expect(attentionActionLabel({ actionLabel: 'Something Else' })).toBe('Something Else');
    setLocale('hi');
    expect(attentionActionLabel({ actionLabel: 'Open invoice' })).toBe('बिल खोलें');
  });
});

describe('catalogue completeness', () => {
  // GST_GUARDRAIL text comes from the GST health module's own messages, so it is shown as the server wrote it.
  const SERVER_TEXT = new Set(['GST_GUARDRAIL', 'EINVOICE_FAILED', 'EINVOICE_PENDING', 'GSTR2B_UNMATCHED']);

  it('has an entry for every code a detector can emit', () => {
    const doc = readFileSync(resolve(__dirname, '../../../../docs/ATTENTION_DEDUPE_KEYS.md'), 'utf-8');
    const block = doc.slice(doc.indexOf('## Codes'), doc.indexOf('Every code above'));
    const codes = block.match(/\b[A-Z][A-Z0-9_]{3,}\b/g)!.filter((c) => c.includes('_') && !['NON_DISMISSIBLE', 'REASON_REQUIRED_CODES'].includes(c));
    expect(codes.length).toBeGreaterThan(35);
    const catalogue = (en as unknown as { attention: { rows: Record<string, unknown> } }).attention.rows;
    const missing = codes.filter((c) => !SERVER_TEXT.has(c) && !(c in catalogue));
    expect(missing).toEqual([]);
  });
});

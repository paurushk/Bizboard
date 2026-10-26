import { describe, expect, it } from 'vitest';
import { FAQ_CATEGORIES, FAQ_ITEMS } from './faqContent';

/** BB-108: the account and subscription answers added for SaaS Phase 1/2 stay in the Help centre. */
const ACCOUNT_IDS = [
  'plan-change',
  'autopay-mandate',
  'payment-failed',
  'bizboard-gst-invoice',
  'bizboard-tds-claim',
  'cancel-subscription',
  'download-all-data',
  'import-busy-vyapar-marg',
  'two-step-verification',
  'signed-in-devices',
  'google-sign-in',
  'transfer-ownership',
  'owner-lost-access',
  'contact-support',
  'support-access',
  'getting-started-checklist',
];

describe('account and subscription FAQ', () => {
  it('has every account answer, once, in a category the Help page shows', () => {
    const byId = new Map(FAQ_ITEMS.map((item) => [item.id, item]));
    for (const id of ACCOUNT_IDS) {
      const item = byId.get(id);
      expect(item, id).toBeDefined();
      expect(FAQ_CATEGORIES).toContain(item!.category);
    }
    expect(new Set(FAQ_ITEMS.map((item) => item.id)).size).toBe(FAQ_ITEMS.length);
  });

  it('covers subscription questions beyond the trial', () => {
    const billing = FAQ_ITEMS.filter((item) => item.category === 'Subscription & billing');
    expect(billing.length).toBeGreaterThanOrEqual(7);
    expect(FAQ_ITEMS.length).toBeGreaterThanOrEqual(250);
  });
});

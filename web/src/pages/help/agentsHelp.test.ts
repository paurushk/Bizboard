import { describe, expect, it } from 'vitest';
import { FAQ_CATEGORIES, FAQ_ITEMS } from './faqContent';

describe('Business agents help', () => {
  const items = FAQ_ITEMS.filter((i) => i.category === 'Business agents');

  it('has its own category on the Help page', () => {
    expect(FAQ_CATEGORIES).toContain('Business agents');
    expect(items.length).toBeGreaterThanOrEqual(25);
  });

  it('covers the module overview, safety, each of the four agents, and troubleshooting', () => {
    const ids = new Set(items.map((i) => i.id));
    for (const id of [
      'agents-what-are', 'agents-safety', 'agents-switch-on', 'agents-ai-or-rules', 'agents-review-approve',
      'agents-failed-stale', 'agents-collections', 'agents-order-intake', 'agents-inventory', 'agents-bill-check',
      'agents-tax-wording', 'agents-not-showing', 'agents-wrong-draft',
    ]) {
      expect(ids.has(id), id).toBe(true);
    }
  });

  it('every entry is searchable and ids are namespaced', () => {
    for (const i of items) {
      expect(i.id.startsWith('agents-'), i.id).toBe(true);
      expect((i.keywords ?? []).length, i.id).toBeGreaterThan(2);
    }
  });
});

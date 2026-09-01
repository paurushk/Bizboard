import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expand } from './synonyms';
import { resolveHelpQuery } from './resolver';
import { FIELD_TEST_FIXTURES, RESOLVER_FIXTURES, STATE_FIXTURES } from './resolverFixtures';
import {
  ERROR_CODE_TO_INTENT,
  HELP_INTENTS,
  intentForErrorCode,
  leafForErrorCode,
} from './intents';
import helpCodes from './helpCodes.json';
import faqV0Snapshot from './faqV0Snapshot.json';
import { FAQ_CATEGORIES, FAQ_ITEMS } from './faqContent';
import { interpolateDestination, userHasHelpPermission } from './helpPermissions';
import { buildHelpSearchHits, isNearExactSkuOrParty } from './searchHits';
import { AMBIGUITY_MAP } from './ambiguityMap';
import { findDiagnosisPath } from './DiagnosisPicker';
import { en } from '@/i18n/en';
import type { SearchResult } from '@/types/domain';
import type { User } from '@/types/domain';
import type { HelpDiagnosisLeaf } from './types';

describe('synonyms', () => {
  it('expand("godown") includes warehouse and store', () => {
    const set = expand('godown');
    expect(set.has('warehouse')).toBe(true);
    expect(set.has('store')).toBe(true);
  });

  it('expand("khol") includes open', () => {
    expect(expand('khol').has('open')).toBe(true);
  });

  it('expand("nahi ban raha") includes can\'t create', () => {
    const set = expand('nahi ban raha');
    expect(set.has("can't create") || set.has('cannot')).toBe(true);
  });

  it('multi-word n-grams in a query reach the synonym index', () => {
    expect(resolveHelpQuery('nahi ban raha').intent?.intentId).toBe('cannot-complete-invoice');
    expect(resolveHelpQuery("can't create invoice").intent?.intentId).toBe('cannot-complete-invoice');
  });

  it('delete/void/undo and unit/uom groups resolve', () => {
    expect(resolveHelpQuery('delete invoice').intent?.intentId).toBe('edit-completed-invoice');
    expect(resolveHelpQuery('void bill').intent?.intentId).toBe('edit-completed-invoice');
    expect(resolveHelpQuery('how units work').intent?.intentId).toBe('unit-conversion-rate');
    expect(resolveHelpQuery('unit setup').intent?.intentId).toBe('unit-conversion-rate');
  });
});

describe('resolver fixtures', () => {
  it('hits ≥90% top-1 including Hinglish', () => {
    const hits = RESOLVER_FIXTURES.filter((row) => {
      const resolved = resolveHelpQuery(row.query);
      return resolved.intent?.intentId === row.intentId;
    });
    const rate = hits.length / RESOLVER_FIXTURES.length;
    const misses = RESOLVER_FIXTURES.filter((row) => resolveHelpQuery(row.query).intent?.intentId !== row.intentId).map(
      (row) => `${row.query} → ${resolveHelpQuery(row.query).intent?.intentId ?? resolveHelpQuery(row.query).state} (want ${row.intentId})`,
    );
    expect(rate, misses.join('\n')).toBeGreaterThanOrEqual(0.9);
  });

  it('why can\'t i sell this → sell-blocked', () => {
    expect(resolveHelpQuery("why can't i sell this").intent?.intentId).toBe('sell-blocked');
  });

  it('gstn / invioce / recieve resolve via fuzzy+synonyms', () => {
    expect(resolveHelpQuery('gstn').intent?.intentId).toBe('add-gstin');
    expect(resolveHelpQuery('invioce unit').intent?.intentId).toBe('unit-conversion-rate');
    expect(resolveHelpQuery('recieve not applying').intent?.intentId).toBe('payment-wont-allocate');
  });

  it('has ≥120 fixture phrases', () => {
    expect(RESOLVER_FIXTURES.length).toBeGreaterThanOrEqual(120);
  });

  it('each intent has ≥2 non-English userQueries', () => {
    const nonEn = /[\u0900-\u097F]|nahi|kaise|kaha|kyun|kya|maal|gudam|peti|galla|dalu|kare|ho raha|kitne|galat|gudam/i;
    for (const intent of HELP_INTENTS) {
      const hits = intent.userQueries.filter((q) => nonEn.test(q) || /[\u0900-\u097F]/.test(q));
      expect(hits.length, intent.intentId).toBeGreaterThanOrEqual(2);
    }
  });

  it('field-test unseen phrasings hit 100% top-1', () => {
    const userQuerySet = new Set(HELP_INTENTS.flatMap((i) => i.userQueries.map((q) => q.toLowerCase())));
    for (const row of FIELD_TEST_FIXTURES) {
      expect(userQuerySet.has(row.query.toLowerCase()), row.query).toBe(false);
    }
    const hits = FIELD_TEST_FIXTURES.filter(
      (row) => resolveHelpQuery(row.query).intent?.intentId === row.intentId,
    );
    const misses = FIELD_TEST_FIXTURES.filter(
      (row) => resolveHelpQuery(row.query).intent?.intentId !== row.intentId,
    ).map((row) => `${row.query} → ${resolveHelpQuery(row.query).intent?.intentId ?? resolveHelpQuery(row.query).state}`);
    expect(hits.length / FIELD_TEST_FIXTURES.length, misses.join('\n')).toBe(1);
  });

  it('at least 40 resolver fixtures are novel (not copies of userQueries)', () => {
    const userQuerySet = new Set(HELP_INTENTS.flatMap((i) => i.userQueries.map((q) => q.toLowerCase())));
    const novel = RESOLVER_FIXTURES.filter((row) => !userQuerySet.has(row.query.toLowerCase()));
    expect(novel.length).toBeGreaterThanOrEqual(40);
  });

  it('resolver state matches state fixtures', () => {
    for (const row of STATE_FIXTURES) {
      expect(resolveHelpQuery(row.query).state, row.query).toBe(row.state);
    }
  });

  it('scores never invent chips without the ambiguity map', () => {
    const result = resolveHelpQuery('gst');
    expect(result.state).toBe('ambiguous');
    expect(result.chips.length).toBeGreaterThan(0);
    const close = resolveHelpQuery('complete invoice gstin stock');
    if (close.state === 'ambiguous') {
      expect(close.chips.every((c) => c.id.includes(':')) || close.chips.length === 0).toBe(true);
    }
  });
});

describe('help codes vs intents', () => {
  it('every intent errorCode is in helpCodes.json', () => {
    const codes = new Set(helpCodes.codes);
    for (const intent of HELP_INTENTS) {
      for (const code of intent.errorCodes) {
        expect(codes.has(code), `${intent.intentId} unknown code ${code}`).toBe(true);
      }
    }
  });

  it('FE map matches generated JSON', () => {
    expect(ERROR_CODE_TO_INTENT).toEqual(helpCodes.errorCodeToIntent);
  });

  it('maps 403 permission_denied', () => {
    expect(intentForErrorCode('permission_denied')).toBe('login-cant-do-this');
  });

  it('maps error codes to diagnosis leaves (HR-3.3)', () => {
    expect(leafForErrorCode('inactive_product')).toBe('inactive');
    expect(leafForErrorCode('blocked_customer')).toBe('blocked-party');
    expect(leafForErrorCode('insufficient_stock')).toBeUndefined();
    expect(helpCodes.errorCodeToLeaf.credit_limit_exceeded).toBe('credit');
  });
});

describe('v0 FAQ fold-in still present when flag off', () => {
  const V0_IDS = [
    'base-vs-alternate-unit',
    'reserved-vs-on-hand',
    'stock-shows-but-insufficient',
    'unit-conversion-rate',
    'unit-field-blank-on-edit',
  ] as const;

  it('keeps the five original v0 FAQ ids', () => {
    const ids = new Set(FAQ_ITEMS.map((i) => i.id));
    for (const id of V0_IDS) {
      expect(ids.has(id), id).toBe(true);
    }
  });

  it('original v0 question/keyword snapshot stays byte-identical', () => {
    const byId = Object.fromEntries(
      FAQ_ITEMS.map((item) => [
        item.id,
        {
          id: item.id,
          category: item.category,
          question: item.question,
          keywords: item.keywords ?? [],
        },
      ]),
    );
    for (const snap of faqV0Snapshot) {
      expect(byId[snap.id]).toEqual(snap);
    }
  });

  it('every FAQ id is unique and every category is listed', () => {
    const ids = FAQ_ITEMS.map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    const categories = new Set(FAQ_CATEGORIES);
    for (const item of FAQ_ITEMS) {
      expect(categories.has(item.category), item.id).toBe(true);
    }
  });

  it('FAQ t: tokens resolve in en.ts', () => {
    const src = readFileSync(resolve(__dirname, './faqContent.tsx'), 'utf8');
    const found = [...src.matchAll(/\*\*t:([^*]+)\*\*/g)].map((m) => m[1]);
    expect(found.length).toBeGreaterThan(0);
    for (const key of found) {
      expect(hasI18nKey(en, key), `FAQ missing i18n key ${key}`).toBe(true);
    }
  });
});

describe('nextStep permission + interpolation', () => {
  const owner = {
    id: 1,
    email: 'o@x.test',
    fullName: 'Owner',
    role: 'OWNER' as const,
    canManageInventory: true,
    canImport: true,
    companyId: 1,
  } as User;

  const staff = { ...owner, role: 'SALES_STAFF' as const, canCreateSales: true };

  it('owner may open GST settings', () => {
    expect(userHasHelpPermission(owner, 'owner')).toBe(true);
    expect(userHasHelpPermission(staff, 'owner')).toBe(false);
  });

  it('cancel destination interpolates invoice id', () => {
    expect(interpolateDestination('/sales/history/:id?helpAction=cancel', { id: 12 })).toBe(
      '/sales/history/12?helpAction=cancel',
    );
  });
});

describe('universal search help hits', () => {
  it('how do i add gstin yields add-gstin', () => {
    const hits = buildHelpSearchHits('how do i add gstin', []);
    expect(hits.some((h) => h.id === 'add-gstin')).toBe(true);
  });

  it('exact SKU match suppresses Help', () => {
    const records: SearchResult[] = [
      { id: 1, type: 'product', title: 'SOAP-1', path: '/inventory/products' },
    ];
    expect(isNearExactSkuOrParty(records, 'SOAP-1')).toBe(true);
    expect(buildHelpSearchHits('SOAP-1', records)).toEqual([]);
  });

  it('InsightsAssistant deep-links with source=assistant', () => {
    const src = readFileSync(resolve(__dirname, '../insights/InsightsAssistantPage.tsx'), 'utf8');
    expect(src).toContain('source=assistant');
  });

  it('CODEOWNERS uses the GitHub handle paurushk', () => {
    const owners = readFileSync(resolve(__dirname, '../../../../.github/CODEOWNERS'), 'utf8');
    expect(owners).toContain('@paurushk');
    expect(owners).not.toMatch(/(^|\s)@paurush(\s|$)/);
    expect(owners).toContain('web/src/pages/help/**');
    expect(owners).toContain('backend/core/help_views.py');
  });

  it('Help health can mark a stuck note resolved', () => {
    const src = readFileSync(resolve(__dirname, './HelpHealthPage.tsx'), 'utf8');
    expect(src).toContain('resolveHelpFeedback');
    expect(src).toContain("t('help.markResolved')");
  });

  it('gap intents are authored (Purchases / books / trial / offline)', () => {
    const ids = new Set(HELP_INTENTS.map((i) => i.intentId));
    for (const id of [
      'purchase-bill-blocked',
      'books-journal-blocked',
      'trial-ended-readonly',
      'offline-outbox-stuck',
    ]) {
      expect(ids.has(id), id).toBe(true);
      const intent = HELP_INTENTS.find((i) => i.intentId === id)!;
      expect(intent.answer.hi, id).toBeTruthy();
      expect(intent.nextStep?.destination, id).toBeTruthy();
      expect(intent.errorCodes).toEqual([]);
    }
  });
});

function hasI18nKey(tree: unknown, path: string): boolean {
  let current: unknown = tree;
  for (const part of path.split('.')) {
    if (current == null || typeof current !== 'object') return false;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === 'string';
}

function walkDiagnosis(nodes: HelpDiagnosisLeaf[] | undefined, visit: (leaf: HelpDiagnosisLeaf) => void) {
  for (const node of nodes ?? []) {
    visit(node);
    walkDiagnosis(node.children, visit);
  }
}

describe('HR-8.2 / HR-8.3 content CI', () => {
  it('cited i18n keys exist in en.ts', () => {
    for (const intent of HELP_INTENTS) {
      expect(intent.citedKeys?.length, intent.intentId).toBeGreaterThan(0);
      for (const key of intent.citedKeys ?? []) {
        expect(hasI18nKey(en, key), `${intent.intentId} missing ${key}`).toBe(true);
      }
    }
  });

  it('every diagnosis leaf intentId and relatedIntents resolve', () => {
    const ids = new Set(HELP_INTENTS.map((i) => i.intentId));
    for (const intent of HELP_INTENTS) {
      for (const related of intent.relatedIntents ?? []) {
        expect(ids.has(related), `${intent.intentId} orphan relatedIntents ${related}`).toBe(true);
      }
      walkDiagnosis(intent.diagnosis, (leaf) => {
        if (leaf.intentId) {
          expect(ids.has(leaf.intentId), `${intent.intentId} leaf ${leaf.id} → ${leaf.intentId}`).toBe(true);
        }
      });
    }
  });

  it('every ambiguity-chip intentId resolves (HR-8.2)', () => {
    const ids = new Set(HELP_INTENTS.map((i) => i.intentId));
    for (const [key, chips] of Object.entries(AMBIGUITY_MAP)) {
      for (const chip of chips) {
        expect(ids.has(chip.intentId), `${key} chip ${chip.intentId}`).toBe(true);
      }
    }
  });

  it('P0 answers include Hindi', () => {
    for (const intent of HELP_INTENTS) {
      expect(intent.answer.hi, intent.intentId).toBeTruthy();
    }
  });

  it('error skip-picker leaf exists on the mapped intent', () => {
    const sell = HELP_INTENTS.find((i) => i.intentId === 'sell-blocked');
    expect(findDiagnosisPath(sell!, 'inactive').map((l) => l.id)).toEqual(['inactive']);
    expect(findDiagnosisPath(sell!, 'blocked-party').map((l) => l.id)).toEqual(['blocked-party']);
  });

  it('citedKeys appear as t: tokens and every t: token is cited', () => {
    for (const intent of HELP_INTENTS) {
      const chunks: string[] = [
        intent.answer.en,
        intent.answer.hi ?? '',
        intent.action.en,
        intent.action.hi ?? '',
        intent.resolution.en,
        intent.resolution.hi ?? '',
        intent.nextStep?.fallback ?? '',
        intent.nextStep?.escalation ?? '',
        ...(intent.prevention ?? []).map((p) => p.text),
      ];
      walkDiagnosis(intent.diagnosis, (leaf) => {
        chunks.push(leaf.answer ?? '', leaf.action ?? '', leaf.resolution ?? '');
      });
      const text = chunks.join('\n');
      const found = [...text.matchAll(/\*\*t:([^*]+)\*\*/g)].map((m) => m[1]);
      for (const key of intent.citedKeys ?? []) {
        expect(text, `${intent.intentId} missing t:${key}`).toContain(`t:${key}`);
      }
      for (const key of found) {
        expect(intent.citedKeys, `${intent.intentId} uncited t:${key}`).toContain(key);
        expect(hasI18nKey(en, key), `${intent.intentId} t:${key} not in en.ts`).toBe(true);
      }
    }
  });
});

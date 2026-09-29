import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { en } from './en';
import { hi } from './hi';

function lookup(tree: object, path: string): string | undefined {
  const value = path.split('.').reduce<unknown>((current, part) => {
    if (current == null || typeof current !== 'object') return undefined;
    return (current as Record<string, unknown>)[part];
  }, tree);
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function read(tree: object, path: string): string {
  const value = lookup(tree, path);
  if (value === undefined) {
    throw new Error(`${path} is missing`);
  }
  return value;
}

const KEYS = [
  'common.whatsappShare',
  'common.whatsappSend',
  'einvoice.submittedSandbox',
  'einvoice.submitSandbox',
  'offlineOutbox.subtitle',
  'tally.disclaimer',
  'reports.tdsSubtitle',
  'growth.campaignHonesty',
  'growth.pipelineHonesty',
  'growth.ticketsInternal',
  'growth.insuranceDesk',
  'growth.projectMilestone',
  'growth.jobCard',
  'growth.valueCopiesToSchedule',
  'growth.markPaidHint',
  'osPlan.trailingMean',
  'osPlan.screenOnly',
  'routes.heuristic',
  'stockValuation.methodWavg',
  'stockValuation.methodFifo',
  'customer360.complaints',
  'customer360.none',
  'billing.invoiceCompleted',
  'billing.gstGuardBlockingTitle',
  'billing.completeDisabledCreditLimit',
  'pos.title',
  'pos.subtitle',
];

describe('plan copy is in both catalogs', () => {
  it('keeps Hindi strings for the honesty labels', () => {
    for (const key of KEYS) {
      const english = read(en, key);
      const hindi = read(hi, key);
      expect(hindi).not.toBe(key);
      expect(hindi).not.toBe(english);
    }
    expect(read(en, 'offlineOutbox.subtitle')).toMatch(/Signing out/);
    expect(read(hi, 'offlineOutbox.subtitle')).toMatch(/साइन आउट/);
    expect(read(en, 'einvoice.submittedSandbox')).not.toMatch(/filed|GSTN|IRP portal/i);
    expect(read(en, 'tally.disclaimer')).toMatch(/imported once/i);
  });

  it('has a Hindi sentence for every static label on invoice, POS, and e-invoice', () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), '..');
    const files = [
      'pages/sales/NewInvoicePage.tsx',
      'pages/pos/PosPage.tsx',
      'components/EinvoiceEwayPanel.tsx',
    ];
    const pattern = /\bt\(\s*['"]([a-zA-Z0-9_.]+)['"]/g;
    const keys = new Set<string>();
    for (const file of files) {
      const source = readFileSync(join(root, file), 'utf8');
      for (const match of source.matchAll(pattern)) {
        keys.add(match[1]);
      }
    }
    expect(keys.size).toBeGreaterThan(10);
    const missing: string[] = [];
    for (const key of keys) {
      const english = lookup(en, key);
      const hindi = lookup(hi, key);
      const sentence = Boolean(english && /[A-Za-z]/.test(english) && english.includes(' '));
      if (
        !english
        || !hindi
        || hindi === key
        || (sentence && hindi === english)
        || (sentence && !/[\u0900-\u097F]/.test(hindi))
      ) {
        missing.push(key);
      }
    }
    expect(missing).toEqual([]);
  });
});

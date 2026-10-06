import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Text between JSX tags was moved onto en/hi on 2026-10-01. A new English phrase in these screens fails here.
 * Brand names and code identifiers stay as they are.
 */
const SWEPT = [
  'src/components/ChallanEwayPanel.tsx',
  'src/components/EinvoiceEwayPanel.tsx',
  'src/components/NoteEinvoicePanel.tsx',
  'src/components/RecordInvoicePaymentDialog.tsx',
  'src/pages/NotFoundPage.tsx',
  'src/pages/insights/InsightsAssistantPage.tsx',
  'src/pages/insights/InsightsCashflowPage.tsx',
  'src/pages/inventory/ItemFormDialog.tsx',
  'src/pages/inventory/StockCountPage.tsx',
  'src/pages/phase/AccountingExtraPages.tsx',
  'src/pages/phase/AccountingReportsPages.tsx',
  'src/pages/phase/BankingPhasePages.tsx',
  'src/pages/phase/InventoryPhasePages.tsx',
  'src/pages/public/PublicPayPage.tsx',
  'src/pages/purchases/NewPurchasePage.tsx',
  'src/pages/sales/InvoiceDetailPage.tsx',
  'src/pages/sales/NewInvoicePage.tsx',
  'src/pages/settings/BillingPage.tsx',
  'src/pages/settings/ImportPage.tsx',
  'src/pages/settings/SeriesSettingsPage.tsx',
  'src/pages/settings/TallyMigrationPage.tsx',
  'src/pages/settings/UsersSettingsPage.tsx',
];

// Provider and brand names are not translated.
const ALLOWED = new Set(['Cashfree', 'Razorpay']);

const JSX_TEXT = /([>])\s*([A-Z][a-z]+(?:[ ,.'/&-]+[A-Za-z0-9%()]+){0,8}[.!?:]?)\s*</g;

describe('i18n JSX text ratchet', () => {
  it('keeps swept screens free of hard-coded English between tags', () => {
    const hits: string[] = [];
    for (const rel of SWEPT) {
      const text = readFileSync(resolve(process.cwd(), rel), 'utf8');
      for (const match of text.matchAll(JSX_TEXT)) {
        const phrase = match[2];
        if (phrase.length >= 3 && !ALLOWED.has(phrase)) hits.push(`${rel}: ${phrase}`);
      }
    }
    expect(hits).toEqual([]);
  });
});

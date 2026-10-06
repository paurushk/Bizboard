import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/** A3-3: these screens were moved onto en/hi. A new English label="..." fails the ratchet. */
const SWEPT = [
  'src/pages/inventory/ItemFormDialog.tsx',
  'src/pages/inventory/ProductsPage.tsx',
  'src/pages/inventory/CurrentStockPage.tsx',
  'src/pages/inventory/StockCountPage.tsx',
  'src/pages/settings/UsersSettingsPage.tsx',
  'src/pages/settings/GstSettingsPage.tsx',
  'src/pages/sales/InvoiceDetailPage.tsx',
  'src/pages/inventory/LowStockPage.tsx',
  'src/pages/insights/InsightsHubPage.tsx',
  'src/components/billing/DraftLineTable.tsx',
  'src/components/ChallanEwayPanel.tsx',
  'src/components/DocumentTaxSummary.tsx',
  'src/pages/CollectionsWorklistPage.tsx',
  'src/pages/inventory/StockAdjustmentPage.tsx',
  'src/pages/phase/AccountingExtraPages.tsx',
  'src/pages/phase/AccountingReportsPages.tsx',
  'src/pages/phase/InventoryPhasePages.tsx',
  'src/pages/public/LeadFormPage.tsx',
  'src/pages/purchases/NewPurchasePage.tsx',
  'src/pages/purchases/PurchaseDetailPage.tsx',
  'src/pages/reports/Gstr9ReportPage.tsx',
  'src/pages/reports/InventoryReportPage.tsx',
  'src/pages/sales/NewInvoicePage.tsx',
  'src/pages/sales/ReceiptsPage.tsx',
  'src/pages/settings/BillingPage.tsx',
  'src/pages/settings/CompanySettingsPage.tsx',
  'src/pages/settings/GstSettingsPage.tsx',
  'src/pages/settings/InvoiceTemplatesPage.tsx',
  'src/pages/settings/ItemSettingsPage.tsx',
  'src/pages/settings/SeriesSettingsPage.tsx',
  'src/pages/settings/UnitsSettingsPage.tsx',
];

describe('i18n literal ratchet', () => {
  it('keeps swept screens free of hard-coded English field labels', () => {
    const hits: string[] = [];
    for (const rel of SWEPT) {
      const text = readFileSync(resolve(process.cwd(), rel), 'utf8');
      const matches = text.match(/label="[A-Za-z][^"]*"/g) ?? [];
      for (const match of matches) hits.push(`${rel}: ${match}`);
    }
    expect(hits).toEqual([]);
  });
});

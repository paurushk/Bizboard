import {
  isAccountingFeatureEnabled,
  isAiInsightsEnabled,
  isCrmEnabled,
  isGstrReportsEnabled,
  isManufacturingEnabled,
  isPayrollEnabled,
  isPosEnabled,
  isTallyEnabled,
} from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import type { User } from '@/types/domain';
import {
  canAccessSettings,
  canAdjustInventory,
  canCreatePayments,
  canCreatePurchases,
  canCreateSales,
  canImport,
  canManageGst,
  canExport,
  canManageUsers,
  canUseAiAssistant,
  canViewAiInsights,
  canViewFinancialReports,
  canViewInventorySurfaces,
  canViewPurchaseSurfaces,
  canViewSalesSurfaces,
} from '@/utils/permissions';

export interface NavItem {
  id: string;
  labelKey: string;
  path?: string;
  children?: NavItem[];
  visible?: (user: User | null) => boolean;
}

function posVisible(user: User | null): boolean {
  return isPosEnabled() && canCreateSales(user);
}

export const navigation: NavItem[] = [
  { id: 'dashboard', labelKey: 'nav.dashboard', path: '/', visible: canViewFinancialReports },
  { id: 'pos', labelKey: 'nav.pos', path: '/pos', visible: posVisible },
  {
    id: 'insights',
    labelKey: 'nav.insights',
    visible: (user) => isAiInsightsEnabled() && canViewAiInsights(user),
    children: [
      { id: 'insights-hub', labelKey: 'nav.insightsHub', path: '/insights' },
      { id: 'insights-health', labelKey: 'nav.insightsHealth', path: '/insights/health' },
      { id: 'insights-cashflow', labelKey: 'nav.insightsCashflow', path: '/insights/cashflow' },
      { id: 'insights-alerts', labelKey: 'nav.insightsAlerts', path: '/insights/alerts' },
      {
        id: 'insights-assistant',
        labelKey: 'nav.insightsAssistant',
        path: '/insights/assistant',
        visible: (user) => isAiInsightsEnabled() && canUseAiAssistant(user),
      },
    ],
  },
  {
    id: 'sales',
    labelKey: 'nav.sales',
    children: [
      { id: 'new-invoice', labelKey: 'nav.newInvoice', path: '/sales/new', visible: canCreateSales },
      // UXW2B-015 follow-up: these five had no `visible` guard at all — the
      // route layer gates them on canViewSalesSurfaces (App.tsx), so a
      // zero/view-only-permission user saw them as normal sidebar links that
      // dead-ended into "Access denied" on click (and were listed as
      // "reachable" on the Forbidden landing page, which is what surfaced this).
      { id: 'sales-history', labelKey: 'nav.salesHistory', path: '/sales/history', visible: canViewSalesSurfaces },
      { id: 'quotations', labelKey: 'nav.quotations', path: '/sales/quotations', visible: canCreateSales },
      { id: 'receipts', labelKey: 'nav.receipts', path: '/sales/receipts', visible: canCreatePayments },
      { id: 'sales-returns', labelKey: 'nav.salesReturns', path: '/sales/returns', visible: canCreateSales },
      { id: 'credit-notes', labelKey: 'nav.creditNotes', path: '/sales/credit-notes', visible: canViewSalesSurfaces },
      { id: 'debit-notes', labelKey: 'nav.debitNotes', path: '/sales/debit-notes', visible: canViewSalesSurfaces },
      { id: 'sales-orders', labelKey: 'nav.salesOrders', path: '/sales/orders', visible: canViewSalesSurfaces },
      { id: 'delivery-challans', labelKey: 'nav.deliveryChallans', path: '/sales/delivery-challans', visible: canViewSalesSurfaces },
      { id: 'recurring-invoices', labelKey: 'nav.recurringInvoices', path: '/sales/recurring', visible: canCreateSales },
      { id: 'customers', labelKey: 'nav.customers', path: '/sales/customers', visible: canViewSalesSurfaces },
    ],
  },
  {
    id: 'purchases',
    labelKey: 'nav.purchases',
    children: [
      { id: 'new-purchase', labelKey: 'nav.newPurchase', path: '/purchases/new', visible: canCreatePurchases },
      // UXW2B-015 follow-up — same gap as Sales above: route guard is
      // canViewPurchaseSurfaces (App.tsx), nav had no guard at all.
      { id: 'purchase-history', labelKey: 'nav.purchaseHistory', path: '/purchases/history', visible: canViewPurchaseSurfaces },
      {
        id: 'bill-upload',
        labelKey: 'nav.uploadBill',
        path: '/purchases/bill-upload',
        visible: canImport,
      },
      {
        id: 'supplier-payments',
        labelKey: 'nav.supplierPayments',
        path: '/purchases/payments',
        visible: canCreatePayments,
      },
      { id: 'purchase-returns', labelKey: 'nav.purchaseReturns', path: '/purchases/returns', visible: canCreatePurchases },
      { id: 'purchase-credit-notes', labelKey: 'nav.purchaseCreditNotes', path: '/purchases/credit-notes', visible: canViewPurchaseSurfaces },
      { id: 'purchase-debit-notes', labelKey: 'nav.purchaseDebitNotes', path: '/purchases/debit-notes', visible: canViewPurchaseSurfaces },
      { id: 'purchase-orders', labelKey: 'nav.purchaseOrders', path: '/purchases/orders', visible: canViewPurchaseSurfaces },
      { id: 'suppliers', labelKey: 'nav.suppliers', path: '/purchases/suppliers', visible: canViewPurchaseSurfaces },
    ],
  },
  {
    id: 'payments',
    labelKey: 'nav.payments',
    visible: canCreatePayments,
    children: [
      { id: 'payment-links', labelKey: 'nav.paymentLinks', path: '/payments/links' },
      { id: 'bank-statements', labelKey: 'nav.bankStatements', path: '/payments/statements' },
      { id: 'payment-recon', labelKey: 'nav.bankReconciliation', path: '/payments/reconciliation' },
      { id: 'cash-book-payments', labelKey: 'nav.cashBook', path: '/reports/cash-book' },
    ],
  },
  {
    id: 'inventory',
    labelKey: 'nav.inventory',
    // UXW2B-015 follow-up: these four had no `visible` guard at all — the route
    // layer (App.tsx RoleRoute) gates them on canViewInventorySurfaces, same
    // BUG-624 class as the `reports` section above (nav shows an item the route
    // guard then rejects, a guaranteed dead-end click — and specifically why a
    // brand-new zero-permission Sales Staff account saw these listed as
    // "reachable" on the Forbidden landing page when they were not).
    children: [
      { id: 'products', labelKey: 'nav.products', path: '/inventory/products', visible: canViewInventorySurfaces },
      { id: 'current-stock', labelKey: 'nav.currentStock', path: '/inventory/stock', visible: canViewInventorySurfaces },
      {
        id: 'stock-adjustment',
        labelKey: 'nav.stockAdjustment',
        path: '/inventory/adjustments',
        visible: canAdjustInventory,
      },
      { id: 'low-stock', labelKey: 'nav.lowStock', path: '/inventory/low-stock', visible: canViewInventorySurfaces },
      { id: 'warehouses', labelKey: 'nav.warehouses', path: '/inventory/warehouses', visible: canAdjustInventory },
      { id: 'stock-transfers', labelKey: 'nav.stockTransfers', path: '/inventory/transfers', visible: canAdjustInventory },
      { id: 'expiry-alerts', labelKey: 'nav.expiryAlerts', path: '/inventory/expiry-alerts', visible: canViewInventorySurfaces },
      { id: 'serials', labelKey: 'nav.serials', path: '/inventory/serials', visible: canAdjustInventory },
    ],
  },
  {
    id: 'manufacturing',
    labelKey: 'nav.manufacturing',
    visible: (user) => canManageUsers(user) && isManufacturingEnabled(),
    children: [
      { id: 'boms', labelKey: 'nav.boms', path: '/manufacturing/boms' },
      { id: 'work-orders', labelKey: 'nav.workOrders', path: '/manufacturing/work-orders' },
    ],
  },
  {
    id: 'payroll',
    labelKey: 'nav.payroll',
    visible: (user) => canManageUsers(user) && isPayrollEnabled(),
    children: [
      { id: 'employees', labelKey: 'nav.employees', path: '/payroll/employees' },
      { id: 'pay-runs', labelKey: 'nav.payRuns', path: '/payroll/pay-runs' },
    ],
  },
  {
    id: 'crm',
    labelKey: 'nav.crm',
    visible: (user) => canManageUsers(user) && isCrmEnabled(),
    children: [
      { id: 'leads', labelKey: 'nav.leads', path: '/crm/leads' },
      { id: 'opportunities', labelKey: 'nav.opportunities', path: '/crm/opportunities' },
    ],
  },
  {
    id: 'reports',
    labelKey: 'nav.reports',
    // BUG-624: without this, every user saw the Reports section even
    // though the route layer (App.tsx RoleRoute) rejects anyone without
    // canViewFinancialReports — a guaranteed dead-end click.
    visible: canViewFinancialReports,
    children: [
      { id: 'report-sales', labelKey: 'nav.salesReports', path: '/reports/sales' },
      { id: 'report-purchases', labelKey: 'nav.purchaseReports', path: '/reports/purchases' },
      { id: 'report-inventory', labelKey: 'nav.inventoryReports', path: '/reports/inventory' },
      { id: 'customer-ledger', labelKey: 'nav.customerLedger', path: '/reports/customer-ledger' },
      { id: 'supplier-ledger', labelKey: 'nav.supplierLedger', path: '/reports/supplier-ledger' },
      {
        id: 'report-gstr1',
        labelKey: 'nav.gstr1',
        path: '/reports/gstr1',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-gstr3b',
        labelKey: 'nav.gstr3b',
        path: '/reports/gstr3b',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-gstr9',
        labelKey: 'nav.gstr9',
        path: '/reports/gstr9',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-gstr2b',
        labelKey: 'nav.gstr2b',
        path: '/reports/gstr2b',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-statutory-events',
        labelKey: 'nav.statutoryEvents',
        path: '/reports/statutory-events',
      },
      {
        id: 'report-gst-health',
        labelKey: 'nav.gstHealth',
        path: '/reports/gst-health',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-tds-tcs',
        labelKey: 'nav.tdsTcs',
        path: '/reports/tds-tcs',
        visible: () => isRuntimeFlagEnabled('ENABLE_TDS'),
      },
      { id: 'cash-book', labelKey: 'nav.cashBook', path: '/reports/cash-book' },
      { id: 'stock-valuation', labelKey: 'nav.stockValuation', path: '/reports/stock-valuation' },
      {
        id: 'trial-balance',
        labelKey: 'nav.trialBalance',
        path: '/reports/trial-balance',
        visible: (user) =>
          isAccountingFeatureEnabled() && Boolean(user?.company?.accountingEnabled),
      },
      {
        id: 'profit-and-loss',
        labelKey: 'nav.profitAndLoss',
        path: '/reports/profit-and-loss',
        visible: (user) =>
          isAccountingFeatureEnabled() && Boolean(user?.company?.accountingEnabled),
      },
      {
        id: 'balance-sheet',
        labelKey: 'nav.balanceSheet',
        path: '/reports/balance-sheet',
        visible: (user) =>
          isAccountingFeatureEnabled() && Boolean(user?.company?.accountingEnabled),
      },
      {
        id: 'books-health',
        labelKey: 'nav.booksHealth',
        path: '/reports/books-health',
        visible: (user) =>
          isAccountingFeatureEnabled() && Boolean(user?.company?.accountingEnabled),
      },
    ],
  },
  {
    id: 'settings',
    labelKey: 'nav.settings',
    visible: canAccessSettings,
    children: [
      {
        id: 'bank-accounts',
        labelKey: 'nav.bankAccounts',
        path: '/settings/bank-accounts',
        visible: canManageUsers,
      },
      {
        id: 'payment-gateway',
        labelKey: 'nav.paymentGateway',
        path: '/settings/payment-gateway',
        visible: canManageUsers,
      },
      {
        id: 'billing',
        labelKey: 'nav.billing',
        path: '/settings/billing',
        visible: canManageUsers,
      },
      {
        id: 'price-lists',
        labelKey: 'nav.priceLists',
        path: '/settings/price-lists',
        visible: canManageUsers,
      },
      {
        id: 'accounting-settings',
        labelKey: 'nav.accounting',
        path: '/settings/accounting',
        visible: (user) => canManageUsers(user) && isAccountingFeatureEnabled(),
      },
      {
        id: 'company',
        labelKey: 'nav.company',
        path: '/settings/company',
        visible: canManageUsers,
      },
      {
        id: 'ai-settings',
        labelKey: 'nav.aiSettings',
        path: '/settings/ai',
        visible: (user) => canManageUsers(user) && isAiInsightsEnabled(),
      },
      {
        id: 'gst',
        labelKey: 'nav.gst',
        path: '/settings/gst',
        visible: canManageGst,
      },
      {
        id: 'units',
        labelKey: 'nav.units',
        path: '/settings/units',
        visible: canManageUsers,
      },
      {
        id: 'templates',
        labelKey: 'nav.invoiceTemplates',
        path: '/settings/templates',
        visible: canManageUsers,
      },
      {
        id: 'users',
        labelKey: 'nav.users',
        path: '/settings/users',
        visible: canManageUsers,
      },
      {
        id: 'import',
        labelKey: 'nav.importData',
        path: '/settings/import',
        visible: canImport,
      },
      {
        id: 'tally',
        labelKey: 'nav.tallyMigration',
        path: '/settings/tally',
        visible: (user) => canImport(user) && isTallyEnabled(),
      },
      {
        id: 'backup',
        labelKey: 'nav.backupExport',
        path: '/settings/backup',
        visible: canExport,
      },
    ],
  },
  {
    id: 'accounting',
    labelKey: 'nav.accounting',
    visible: (user) =>
      Boolean(user?.company?.accountingEnabled) &&
      isAccountingFeatureEnabled() &&
      canViewFinancialReports(user),
    children: [
      { id: 'chart-of-accounts', labelKey: 'nav.chartOfAccounts', path: '/accounting/accounts' },
      { id: 'journals', labelKey: 'nav.journals', path: '/accounting/journals' },
      { id: 'cost-centers', labelKey: 'nav.costCenters', path: '/accounting/cost-centers' },
      { id: 'fixed-assets', labelKey: 'nav.fixedAssets', path: '/accounting/fixed-assets' },
      { id: 'accounting-periods', labelKey: 'nav.accountingPeriods', path: '/accounting/periods' },
      { id: 'accounting-recon', labelKey: 'nav.bankReconciliation', path: '/accounting/bank-reconciliation' },
    ],
  },
];

export function filterNav(user: User | null): NavItem[] {
  return navigation
    .filter((item) => (item.visible ? item.visible(user) : true))
    .map((item) => ({
      ...item,
      children: item.children?.filter((child) =>
        child.visible ? child.visible(user) : true,
      ),
    }))
    .filter((item) => !item.children || item.children.length > 0);
}

// UXW2B-015: many leaf nav items (Sales History, Credit/Debit Notes, Sales/Purchase
// Orders, Delivery Challans, …) have no per-item `visible` guard in `navigation`
// above — they rely on the *route* guard (RoleRoute in App.tsx) to actually block
// access. `filterNav` alone isn't enough to know a path really works; reproduce
// the relevant route guards here too so this never points at a page that
// immediately bounces the user back to this same landing.
export function isReallyReachable(user: User | null, path: string): boolean {
  if (path === '/') return canViewFinancialReports(user);
  if (path.startsWith('/sales/') || path === '/pos') return canViewSalesSurfaces(user);
  if (path.startsWith('/purchases/')) return canViewPurchaseSurfaces(user);
  return true;
}

/** First sidebar path the user can open (BB-000528 limited-role landing). */
export function findFirstNavPath(user: User | null): string | null {
  const nav = filterNav(user);
  for (const item of nav) {
    if (item.path && item.path !== '/' && isReallyReachable(user, item.path)) return item.path;
    const child = item.children?.find((c) => c.path && isReallyReachable(user, c.path));
    if (child?.path) return child.path;
  }
  return null;
}

import {
  isAccountingFeatureEnabled,
  isAiInsightsEnabled,
  isComplaintsEnabled,
  isContractsEnabled,
  isCrmEnabled,
  isReferralsEnabled,
  isSupportTicketsEnabled,
  isWorkshopEnabled,
  isProjectsEnabled,
  isInsuranceEnabled,
  isGstrReportsEnabled,
  isManufacturingEnabled,
  isPayrollEnabled,
  isPosEnabled,
  isTallyEnabled,
  isHelpV2Enabled,
  isTdsEnabled,
} from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { isNavMarkedNotReady } from '@/navigation/notReadyNav';

/**
 * Surfaces the frozen release hides. Each one shows only when its own runtime
 * flag is on: the deployment env flag is the ceiling, and a company can be granted
 * the flag where the backend allows it. Every flag defaults off, so a production or
 * pilot profile is unchanged; demo and staging turn them on (see
 * `manage.py enable_full_demo` and docs/UX_MASTER_EXECUTION_PLAN.md).
 * Support tickets, insurance and contracts also keep their own `visible` checks.
 */
const FLAG_GATED_NAV: Record<string, string> = {
  'bills-of-entry': 'ENABLE_BOE',
  telegram: 'ENABLE_TELEGRAM',
  'fixed-assets': 'ENABLE_FIXED_ASSETS',
  tickets: 'ENABLE_SUPPORT_TICKETS',
  'shared-tickets': 'ENABLE_SUPPORT_TICKETS',
  insurance: 'ENABLE_INSURANCE',
  contracts: 'ENABLE_CONTRACTS',
  // The frozen release ships GSTR-1 and GSTR-3B worksheets only.
  'report-gstr2b': 'ENABLE_GSTR_EXTENDED',
  'report-gstr4': 'ENABLE_GSTR_EXTENDED',
  'report-gstr6': 'ENABLE_GSTR_EXTENDED',
  'report-gstr7': 'ENABLE_GSTR_EXTENDED',
  'report-gstr8': 'ENABLE_GSTR_EXTENDED',
  'report-gstr9': 'ENABLE_GSTR_EXTENDED',
};
/** Hidden only while a new company is still on the archetype-pack sidebar. */
const PACK_HIDDEN_SECTIONS = new Set([
  'insights',
  'manufacturing',
  'payroll',
  'crm',
  'complaints',
  'supplier-complaints',
  'tickets',
  'shared-tickets',
  'job-cards',
  'projects',
  'insurance',
  'contracts',
]);
import type { User } from '@/types/domain';
import {
  canAccessPos,
  canAccessSettings,
  canAdjustInventory,
  canCreatePayments,
  canCreatePurchases,
  canCreateSales,
  canImport,
  canManageCrm,
  canManageGst,
  canExport,
  canManageUsers,
  canUseAiAssistant,
  canViewAiInsights,
  canViewFinancialReports,
  canViewInventorySurfaces,
  canViewPurchaseSurfaces,
  canViewSalesSurfaces,
  canViewPaymentSurfaces,
  canViewBankRecon,
  isOwner,
} from '@/utils/permissions';

export interface NavItem {
  id: string;
  labelKey: string;
  path?: string;
  children?: NavItem[];
  visible?: (user: User | null) => boolean;
}

function posVisible(user: User | null): boolean {
  return (isPosEnabled() || isRuntimeFlagEnabled('ENABLE_POS')) && canAccessPos(user);
}

/** R-063 / R-087: AA nav stays hidden until the flag and a future consent bit are both on. */
function accountAggregatorNavVisible(user: User | null): boolean {
  return (
    canViewBankRecon(user) &&
    isRuntimeFlagEnabled('ENABLE_ACCOUNT_AGGREGATOR') &&
    isRuntimeFlagEnabled('ENABLE_AA_CONSENT')
  );
}

export const navigation: NavItem[] = [
  { id: 'dashboard', labelKey: 'nav.dashboard', path: '/', visible: canViewFinancialReports },
  { id: 'attention', labelKey: 'nav.attention', path: '/attention', visible: canViewFinancialReports },
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
      { id: 'sales-history', labelKey: 'nav.salesHistory', path: '/sales/history', visible: canViewSalesSurfaces },
      { id: 'quotations', labelKey: 'nav.quotations', path: '/sales/quotations', visible: canViewSalesSurfaces },
      { id: 'receipts', labelKey: 'nav.receipts', path: '/sales/receipts', visible: canViewPaymentSurfaces },
      { id: 'customers', labelKey: 'nav.customers', path: '/sales/customers', visible: canViewSalesSurfaces },
      {
        id: 'sales-more',
        labelKey: 'nav.more',
        children: [
          { id: 'quick-entry', labelKey: 'nav.quickEntry', path: '/sales/quick-entry', visible: canCreateSales },
          { id: 'sales-bill-upload', labelKey: 'nav.uploadSalesBill', path: '/sales/bill-upload', visible: canImport },
          { id: 'sales-returns', labelKey: 'nav.salesReturns', path: '/sales/returns', visible: canViewSalesSurfaces },
          { id: 'credit-notes', labelKey: 'nav.creditNotes', path: '/sales/credit-notes', visible: canViewSalesSurfaces },
          { id: 'debit-notes', labelKey: 'nav.debitNotes', path: '/sales/debit-notes', visible: canViewSalesSurfaces },
          { id: 'sales-orders', labelKey: 'nav.salesOrders', path: '/sales/orders', visible: canViewSalesSurfaces },
          { id: 'delivery-challans', labelKey: 'nav.deliveryChallans', path: '/sales/delivery-challans', visible: canViewSalesSurfaces },
          { id: 'delivery-routes', labelKey: 'nav.deliveryRoutes', path: '/sales/delivery-routes', visible: canViewSalesSurfaces },
          { id: 'recurring-invoices', labelKey: 'nav.recurringInvoices', path: '/sales/recurring', visible: canViewSalesSurfaces },
        ],
      },
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
      { id: 'purchase-returns', labelKey: 'nav.purchaseReturns', path: '/purchases/returns', visible: canViewPurchaseSurfaces },
      { id: 'purchase-credit-notes', labelKey: 'nav.purchaseCreditNotes', path: '/purchases/credit-notes', visible: canViewPurchaseSurfaces },
      { id: 'purchase-debit-notes', labelKey: 'nav.purchaseDebitNotes', path: '/purchases/debit-notes', visible: canViewPurchaseSurfaces },
      { id: 'purchase-orders', labelKey: 'nav.purchaseOrders', path: '/purchases/orders', visible: canViewPurchaseSurfaces },
      { id: 'goods-receipts', labelKey: 'nav.goodsReceipts', path: '/purchases/grns', visible: canViewPurchaseSurfaces },
      { id: 'bills-of-entry', labelKey: 'nav.billsOfEntry', path: '/purchases/bills-of-entry', visible: canViewPurchaseSurfaces },
      { id: 'suppliers', labelKey: 'nav.suppliers', path: '/purchases/suppliers', visible: canViewPurchaseSurfaces },
    ],
  },
  {
    id: 'payments',
    labelKey: 'nav.payments',
    visible: canViewPaymentSurfaces,
    children: [
      { id: 'payment-links', labelKey: 'nav.paymentLinks', path: '/payments/links', visible: canCreatePayments },
      {
        id: 'customer-portal',
        labelKey: 'nav.customerPortal',
        path: '/portal',
        visible: (user) => canCreateSales(user) && isRuntimeFlagEnabled('ENABLE_CUSTOMER_PORTAL'),
      },
      {
        id: 'collections',
        labelKey: 'nav.collections',
        path: '/payments/collections',
        visible: canViewFinancialReports,
      },
      { id: 'bank-statements', labelKey: 'nav.bankStatements', path: '/payments/statements', visible: canCreatePayments },
      { id: 'payment-recon', labelKey: 'nav.bankReconciliation', path: '/payments/reconciliation', visible: canViewBankRecon },
      {
        id: 'account-aggregator',
        labelKey: 'nav.accountAggregator',
        path: '/payments/account-aggregator',
        visible: accountAggregatorNavVisible,
      },
      { id: 'cash-book-payments', labelKey: 'nav.cashBook', path: '/reports/cash-book', visible: canViewFinancialReports },
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
      {
        id: 'purchase-planning',
        labelKey: 'nav.purchasePlanning',
        path: '/inventory/purchase-planning',
        visible: (user) => canViewInventorySurfaces(user) && isRuntimeFlagEnabled('ENABLE_PURCHASE_PLANNING'),
      },
      {
        id: 'demand-forecast',
        labelKey: 'nav.demandForecast',
        path: '/inventory/demand-forecast',
        visible: canViewInventorySurfaces,
      },
      { id: 'label-print', labelKey: 'nav.labelPrint', path: '/inventory/labels', visible: canAdjustInventory },
      { id: 'warehouses', labelKey: 'nav.warehouses', path: '/inventory/warehouses', visible: canAdjustInventory },
      { id: 'stock-counts', labelKey: 'nav.stockCounts', path: '/inventory/stock-counts', visible: canAdjustInventory },
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
    visible: (user) => canManageCrm(user) && isCrmEnabled(),
    children: [
      { id: 'leads', labelKey: 'nav.leads', path: '/crm/leads' },
      { id: 'crm-onboarding', labelKey: 'nav.crmOnboarding', path: '/crm/onboarding' },
      { id: 'opportunities', labelKey: 'nav.opportunities', path: '/crm/opportunities' },
      { id: 'campaigns', labelKey: 'nav.campaigns', path: '/crm/campaigns' },
      { id: 'pipeline', labelKey: 'nav.pipeline', path: '/crm/pipeline' },
      {
        id: 'referrals',
        labelKey: 'nav.referrals',
        path: '/crm/referrals',
        visible: () => isReferralsEnabled(),
      },
    ],
  },
  {
    id: 'complaints',
    labelKey: 'nav.complaints',
    path: '/complaints',
    visible: (user) => canCreateSales(user) && isComplaintsEnabled(),
  },
  {
    id: 'supplier-complaints',
    labelKey: 'nav.supplierComplaints',
    path: '/complaints/suppliers',
    visible: (user) => canCreatePurchases(user) && isComplaintsEnabled(),
  },
  {
    id: 'tickets',
    labelKey: 'nav.tickets',
    path: '/support/tickets',
    visible: (user) => canCreateSales(user) && isSupportTicketsEnabled(),
  },
  {
    id: 'shared-tickets',
    labelKey: 'nav.sharedTickets',
    path: '/support/shared',
    visible: (user) => canCreateSales(user) && isSupportTicketsEnabled(),
  },
  {
    id: 'job-cards',
    labelKey: 'nav.jobCards',
    path: '/workshop/jobs',
    visible: (user) => canCreateSales(user) && isWorkshopEnabled(),
  },
  {
    id: 'projects',
    labelKey: 'nav.projects',
    path: '/projects',
    visible: (user) => canCreateSales(user) && isProjectsEnabled(),
  },
  {
    id: 'insurance',
    labelKey: 'nav.insurance',
    path: '/insurance',
    visible: (user) => user?.canManagePolicies === true && isInsuranceEnabled(),
  },
  {
    id: 'contracts',
    labelKey: 'nav.contracts',
    path: '/contracts',
    visible: (user) => canCreateSales(user) && isContractsEnabled(),
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
      { id: 'report-discounts', labelKey: 'nav.discountReport', path: '/reports/discounts' },
      { id: 'report-invoice-profit', labelKey: 'nav.invoiceProfitReport', path: '/reports/invoice-profit' },
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
        id: 'report-gstr4',
        labelKey: 'nav.gstr4',
        path: '/reports/gstr4',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-cmp08',
        labelKey: 'nav.cmp08',
        path: '/reports/cmp08',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-gstr6',
        labelKey: 'nav.gstr6',
        path: '/reports/gstr6',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-gstr7',
        labelKey: 'nav.gstr7',
        path: '/reports/gstr7',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-gstr8',
        labelKey: 'nav.gstr8',
        path: '/reports/gstr8',
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
        id: 'report-missing-docs',
        labelKey: 'nav.missingDocuments',
        path: '/reports/missing-documents',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-ca-needs',
        labelKey: 'nav.caNeeds',
        path: '/ca-needs?view=client',
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
        id: 'report-gst-rate-exposure',
        labelKey: 'nav.gstRateExposure',
        path: '/reports/gst-rate-exposure',
        visible: () => isGstrReportsEnabled(),
      },
      {
        id: 'report-tds-tcs',
        labelKey: 'nav.tdsTcs',
        path: '/reports/tds-tcs',
        visible: () => isTdsEnabled(),
      },
      { id: 'cash-book', labelKey: 'nav.cashBook', path: '/reports/cash-book' },
      { id: 'day-book', labelKey: 'nav.dayBook', path: '/reports/day-book' },
      { id: 'stock-valuation', labelKey: 'nav.stockValuation', path: '/reports/stock-valuation' },
      {
        id: 'trial-balance',
        labelKey: 'nav.trialBalance',
        path: '/reports/trial-balance',
        visible: (user) =>
          Boolean(user?.company?.accountingEnabled) || isAccountingFeatureEnabled(user?.company?.accountingEnabled),
      },
      {
        id: 'profit-and-loss',
        labelKey: 'nav.profitAndLoss',
        path: '/reports/profit-and-loss',
        visible: (user) =>
          Boolean(user?.company?.accountingEnabled) || isAccountingFeatureEnabled(user?.company?.accountingEnabled),
      },
      {
        id: 'balance-sheet',
        labelKey: 'nav.balanceSheet',
        path: '/reports/balance-sheet',
        visible: (user) =>
          Boolean(user?.company?.accountingEnabled) || isAccountingFeatureEnabled(user?.company?.accountingEnabled),
      },
      {
        id: 'books-health',
        labelKey: 'nav.booksHealth',
        path: '/reports/books-health',
        visible: (user) =>
          Boolean(user?.company?.accountingEnabled) || isAccountingFeatureEnabled(user?.company?.accountingEnabled),
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
        id: 'pack-wizard',
        labelKey: 'nav.packWizard',
        path: '/settings/packs',
        visible: (user) => user?.role === 'OWNER' && isRuntimeFlagEnabled('ENABLE_ARCHETYPE_PACKS'),
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
        visible: (user) =>
          canManageUsers(user) &&
          (Boolean(user?.company?.accountingEnabled) || isAccountingFeatureEnabled(user?.company?.accountingEnabled)),
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
        id: 'statutory-licences',
        labelKey: 'nav.statutoryLicences',
        path: '/settings/statutory-licences',
        visible: canManageGst,
      },
      {
        id: 'help-health',
        labelKey: 'nav.helpHealth',
        path: '/settings/help',
        visible: (user) =>
          Boolean(user && (isOwner(user.role) || user.isStaff) && isHelpV2Enabled()),
      },
      {
        id: 'series',
        labelKey: 'nav.seriesSettings',
        path: '/settings/series',
        visible: canManageUsers,
      },
      {
        id: 'units',
        labelKey: 'nav.units',
        path: '/settings/units',
        visible: canManageUsers,
      },
      {
        id: 'item-settings',
        labelKey: 'nav.itemSettings',
        path: '/settings/items',
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
      {
        id: 'telegram',
        labelKey: 'nav.telegram',
        path: '/settings/telegram',
        visible: (user) => canManageUsers(user),
      },
    ],
  },
  {
    id: 'accounting',
    labelKey: 'nav.accounting',
    visible: (user) =>
      Boolean(user?.company?.accountingEnabled) &&
      isAccountingFeatureEnabled(user?.company?.accountingEnabled) &&
      canViewFinancialReports(user),
    children: [
      { id: 'chart-of-accounts', labelKey: 'nav.chartOfAccounts', path: '/accounting/accounts' },
      { id: 'journals', labelKey: 'nav.journals', path: '/accounting/journals' },
      { id: 'cost-centers', labelKey: 'nav.costCenters', path: '/accounting/cost-centers' },
      { id: 'fixed-assets', labelKey: 'nav.fixedAssets', path: '/accounting/fixed-assets' },
      { id: 'accounting-periods', labelKey: 'nav.accountingPeriods', path: '/accounting/periods' },
      { id: 'accounting-recon', labelKey: 'nav.bankReconciliation', path: '/accounting/bank-reconciliation' },
      { id: 'expenses', labelKey: 'nav.expenses', path: '/accounting/expenses' },
      { id: 'day-book-accounting', labelKey: 'nav.dayBook', path: '/reports/day-book' },
    ],
  },
  { id: 'help', labelKey: 'nav.help', path: '/help' },
  { id: 'offline-outbox', labelKey: 'nav.offlineOutbox', path: '/offline-outbox', visible: (user) => Boolean(user) },
];

function navItemHidden(id: string): boolean {
  if (isNavMarkedNotReady(id)) return true;
  const gate = FLAG_GATED_NAV[id];
  if (gate && !isRuntimeFlagEnabled(gate)) return true;
  if (isRuntimeFlagEnabled('NAV_PACK_DEFAULT') && PACK_HIDDEN_SECTIONS.has(id)) return true;
  return false;
}

function filterChildren(children: NavItem[] | undefined, user: User | null): NavItem[] | undefined {
  if (!children) return undefined;
  return children
    .filter((child) => !navItemHidden(child.id) && (child.visible ? child.visible(user) : true))
    .map((child) => ({ ...child, children: filterChildren(child.children, user) }))
    .filter((child) => !child.children || child.children.length > 0);
}

export function filterNav(user: User | null): NavItem[] {
  return navigation
    .filter((item) => !navItemHidden(item.id) && (item.visible ? item.visible(user) : true))
    .map((item) => ({
      ...item,
      children: filterChildren(item.children, user),
    }))
    .filter((item) => !item.children || item.children.length > 0);
}

export function isReallyReachable(user: User | null, path: string): boolean {
  if (path === '/pos' && posVisible(user)) return true;
  const nav = filterNav(user);
  for (const item of nav) {
    if (item.path && pathMatches(item.path, path)) return true;
    if (item.children?.some((child) => childMatches(child, path))) return true;
  }
  return false;
}

export function isNavPathActive(pathname: string, navPath?: string): boolean {
  if (!navPath) return false;
  return pathMatches(navPath, pathname);
}

function pathMatches(navPath: string, path: string): boolean {
  const clean = (path.split('?')[0] || '/').replace(/\/+$/, '') || '/';
  // F1-015: nav paths may carry a query string (e.g. '/ca-needs?view=client').
  // Compare on the pathname only, or the CA-needs surface is never "reachable"
  // and a user landed there falls through to LimitedAccessLanding.
  // R-065: nested history (`/sales/history/123`) must highlight Sales History.
  const navClean = (navPath.split('?')[0] || '/').replace(/\/+$/, '') || '/';
  if (navClean === clean) return true;
  if (navClean !== '/' && clean.startsWith(`${navClean}/`)) return true;
  return false;
}

function childMatches(child: NavItem, path: string): boolean {
  if (child.path && pathMatches(child.path, path)) return true;
  return Boolean(child.children?.some((nested) => childMatches(nested, path)));
}

function firstReachablePath(item: NavItem, user: User | null): string | null {
  if (item.path && item.path !== '/' && isReallyReachable(user, item.path)) return item.path;
  for (const child of item.children ?? []) {
    const found = firstReachablePath(child, user);
    if (found) return found;
  }
  return null;
}

/** First sidebar path the user can open (BB-000528 limited-role landing). */
export function findFirstNavPath(user: User | null): string | null {
  for (const item of filterNav(user)) {
    const found = firstReachablePath(item, user);
    if (found) return found;
  }
  return null;
}

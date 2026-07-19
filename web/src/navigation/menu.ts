import type { User } from '@/types/domain';
import {
  canAccessSettings,
  canAdjustInventory,
  canImport,
  canManageGst,
  canManageUsers,
} from '@/utils/permissions';

export interface NavItem {
  id: string;
  labelKey: string;
  path?: string;
  children?: NavItem[];
  visible?: (user: User | null) => boolean;
}

export const navigation: NavItem[] = [
  { id: 'dashboard', labelKey: 'nav.dashboard', path: '/' },
  {
    id: 'sales',
    labelKey: 'nav.sales',
    children: [
      { id: 'new-invoice', labelKey: 'nav.newInvoice', path: '/sales/new' },
      { id: 'sales-history', labelKey: 'nav.salesHistory', path: '/sales/history' },
      { id: 'quotations', labelKey: 'nav.quotations', path: '/sales/quotations' },
      { id: 'receipts', labelKey: 'nav.receipts', path: '/sales/receipts' },
      { id: 'sales-returns', labelKey: 'nav.salesReturns', path: '/sales/returns' },
      { id: 'customers', labelKey: 'nav.customers', path: '/sales/customers' },
    ],
  },
  {
    id: 'purchases',
    labelKey: 'nav.purchases',
    children: [
      { id: 'new-purchase', labelKey: 'nav.newPurchase', path: '/purchases/new' },
      { id: 'purchase-history', labelKey: 'nav.purchaseHistory', path: '/purchases/history' },
      { id: 'supplier-payments', labelKey: 'nav.supplierPayments', path: '/purchases/payments' },
      { id: 'purchase-returns', labelKey: 'nav.purchaseReturns', path: '/purchases/returns' },
      { id: 'suppliers', labelKey: 'nav.suppliers', path: '/purchases/suppliers' },
    ],
  },
  {
    id: 'inventory',
    labelKey: 'nav.inventory',
    children: [
      { id: 'products', labelKey: 'nav.products', path: '/inventory/products' },
      { id: 'current-stock', labelKey: 'nav.currentStock', path: '/inventory/stock' },
      {
        id: 'stock-adjustment',
        labelKey: 'nav.stockAdjustment',
        path: '/inventory/adjustments',
        visible: canAdjustInventory,
      },
      { id: 'low-stock', labelKey: 'nav.lowStock', path: '/inventory/low-stock' },
    ],
  },
  {
    id: 'reports',
    labelKey: 'nav.reports',
    children: [
      { id: 'report-sales', labelKey: 'nav.salesReports', path: '/reports/sales' },
      { id: 'report-purchases', labelKey: 'nav.purchaseReports', path: '/reports/purchases' },
      { id: 'report-inventory', labelKey: 'nav.inventoryReports', path: '/reports/inventory' },
      { id: 'customer-ledger', labelKey: 'nav.customerLedger', path: '/reports/customer-ledger' },
      { id: 'supplier-ledger', labelKey: 'nav.supplierLedger', path: '/reports/supplier-ledger' },
    ],
  },
  {
    id: 'settings',
    labelKey: 'nav.settings',
    visible: canAccessSettings,
    children: [
      {
        id: 'company',
        labelKey: 'nav.company',
        path: '/settings/company',
        visible: canManageUsers,
      },
      {
        id: 'gst',
        labelKey: 'nav.gst',
        path: '/settings/gst',
        visible: canManageGst,
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
        id: 'backup',
        labelKey: 'nav.backupExport',
        path: '/settings/backup',
        visible: canManageUsers,
      },
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

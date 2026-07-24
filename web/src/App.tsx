import { Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { AppShell } from '@/layouts/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { NewInvoicePage } from '@/pages/sales/NewInvoicePage';
import { SalesHistoryPage } from '@/pages/sales/SalesHistoryPage';
import { InvoiceDetailPage } from '@/pages/sales/InvoiceDetailPage';
import { QuotationsPage } from '@/pages/sales/QuotationsPage';
import { ReceiptsPage } from '@/pages/sales/ReceiptsPage';
import { CustomersPage } from '@/pages/sales/CustomersPage';
import { SalesReturnsPage } from '@/pages/sales/SalesReturnsPage';
import { NewPurchasePage } from '@/pages/purchases/NewPurchasePage';
import { PurchaseHistoryPage } from '@/pages/purchases/PurchaseHistoryPage';
import { SupplierPaymentsPage } from '@/pages/purchases/SupplierPaymentsPage';
import { SuppliersPage } from '@/pages/purchases/SuppliersPage';
import { PurchaseReturnsPage } from '@/pages/purchases/PurchaseReturnsPage';
import { PurchaseBillUploadPage } from '@/pages/purchases/PurchaseBillUploadPage';
import { PurchaseDetailPage } from '@/pages/purchases/PurchaseDetailPage';
import { ProductsPage } from '@/pages/inventory/ProductsPage';
import { CurrentStockPage } from '@/pages/inventory/CurrentStockPage';
import { StockAdjustmentPage } from '@/pages/inventory/StockAdjustmentPage';
import { LowStockPage } from '@/pages/inventory/LowStockPage';
import { SalesReportPage } from '@/pages/reports/SalesReportPage';
import { PurchaseReportPage } from '@/pages/reports/PurchaseReportPage';
import { InventoryReportPage } from '@/pages/reports/InventoryReportPage';
import { CustomerLedgerPage } from '@/pages/reports/CustomerLedgerPage';
import { SupplierLedgerPage } from '@/pages/reports/SupplierLedgerPage';
import { CompanySettingsPage } from '@/pages/settings/CompanySettingsPage';
import { GstSettingsPage } from '@/pages/settings/GstSettingsPage';
import { InvoiceTemplatesPage } from '@/pages/settings/InvoiceTemplatesPage';
import { UsersSettingsPage } from '@/pages/settings/UsersSettingsPage';
import { ImportPage } from '@/pages/settings/ImportPage';
import { BackupExportPage } from '@/pages/settings/BackupExportPage';
import {
  canAccessSettings,
  canAdjustInventory,
  canImport,
  canManageGst,
  canManageUsers,
  canViewFinancialReports,
} from '@/utils/permissions';
import type { User } from '@/types/domain';
import { ForbiddenPage } from '@/pages/ForbiddenPage';

function ProtectedRoute() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

function RoleRoute({
  allow,
}: {
  allow: (user: User | null) => boolean;
}) {
  const { user } = useAuth();
  if (!allow(user)) {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}

/** Force remount when switching create ↔ edit or between invoice ids. */
function SalesInvoiceEditor() {
  const { id } = useParams();
  return <NewInvoicePage key={id ?? 'new'} />;
}

function PurchaseInvoiceEditor() {
  const { id } = useParams();
  return <NewPurchasePage key={id ?? 'new'} />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="sales/new" element={<SalesInvoiceEditor />} />
          <Route path="sales/history" element={<SalesHistoryPage />} />
          <Route path="sales/history/:id/edit" element={<SalesInvoiceEditor />} />
          <Route path="sales/history/:id" element={<InvoiceDetailPage />} />
          <Route path="sales/quotations" element={<QuotationsPage />} />
          <Route path="sales/receipts" element={<ReceiptsPage />} />
          <Route path="sales/returns" element={<SalesReturnsPage />} />
          <Route path="sales/customers" element={<CustomersPage />} />
          <Route path="purchases/new" element={<PurchaseInvoiceEditor />} />
          <Route path="purchases/history" element={<PurchaseHistoryPage />} />
          <Route path="purchases/history/:id/edit" element={<PurchaseInvoiceEditor />} />
          <Route path="purchases/history/:id" element={<PurchaseDetailPage />} />
          <Route element={<RoleRoute allow={canImport} />}>
            <Route path="purchases/bill-upload" element={<PurchaseBillUploadPage />} />
          </Route>
          <Route path="purchases/payments" element={<SupplierPaymentsPage />} />
          <Route path="purchases/returns" element={<PurchaseReturnsPage />} />
          <Route path="purchases/suppliers" element={<SuppliersPage />} />
          <Route path="inventory/products" element={<ProductsPage />} />
          <Route path="inventory/stock" element={<CurrentStockPage />} />
          <Route element={<RoleRoute allow={canAdjustInventory} />}>
            <Route path="inventory/adjustments" element={<StockAdjustmentPage />} />
          </Route>
          <Route path="inventory/low-stock" element={<LowStockPage />} />
          <Route element={<RoleRoute allow={canViewFinancialReports} />}>
            <Route path="reports/sales" element={<SalesReportPage />} />
            <Route path="reports/purchases" element={<PurchaseReportPage />} />
            <Route path="reports/inventory" element={<InventoryReportPage />} />
            <Route path="reports/customer-ledger" element={<CustomerLedgerPage />} />
            <Route path="reports/supplier-ledger" element={<SupplierLedgerPage />} />
          </Route>          <Route element={<RoleRoute allow={canAccessSettings} />}>
            <Route element={<RoleRoute allow={canManageUsers} />}>
              <Route path="settings/company" element={<CompanySettingsPage />} />
              <Route path="settings/templates" element={<InvoiceTemplatesPage />} />
              <Route path="settings/users" element={<UsersSettingsPage />} />
              <Route path="settings/backup" element={<BackupExportPage />} />
            </Route>
            <Route element={<RoleRoute allow={canManageGst} />}>
              <Route path="settings/gst" element={<GstSettingsPage />} />
            </Route>
            <Route element={<RoleRoute allow={canImport} />}>
              <Route path="settings/import" element={<ImportPage />} />
            </Route>
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

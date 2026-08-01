import { lazy, Suspense } from 'react';
import { Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom';
import { CircularProgress, Box } from '@mui/material';
import { useAuth } from '@/auth/AuthContext';
import { AppShell } from '@/layouts/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { DashboardPage } from '@/pages/DashboardPage';
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

const NewInvoicePage = lazy(() => import('@/pages/sales/NewInvoicePage').then((m) => ({ default: m.NewInvoicePage })));
const SalesHistoryPage = lazy(() => import('@/pages/sales/SalesHistoryPage').then((m) => ({ default: m.SalesHistoryPage })));
const InvoiceDetailPage = lazy(() => import('@/pages/sales/InvoiceDetailPage').then((m) => ({ default: m.InvoiceDetailPage })));
const QuotationsPage = lazy(() => import('@/pages/sales/QuotationsPage').then((m) => ({ default: m.QuotationsPage })));
const ReceiptsPage = lazy(() => import('@/pages/sales/ReceiptsPage').then((m) => ({ default: m.ReceiptsPage })));
const CustomersPage = lazy(() => import('@/pages/sales/CustomersPage').then((m) => ({ default: m.CustomersPage })));
const SalesReturnsPage = lazy(() => import('@/pages/sales/SalesReturnsPage').then((m) => ({ default: m.SalesReturnsPage })));
const NewPurchasePage = lazy(() => import('@/pages/purchases/NewPurchasePage').then((m) => ({ default: m.NewPurchasePage })));
const PurchaseHistoryPage = lazy(() => import('@/pages/purchases/PurchaseHistoryPage').then((m) => ({ default: m.PurchaseHistoryPage })));
const SupplierPaymentsPage = lazy(() => import('@/pages/purchases/SupplierPaymentsPage').then((m) => ({ default: m.SupplierPaymentsPage })));
const SuppliersPage = lazy(() => import('@/pages/purchases/SuppliersPage').then((m) => ({ default: m.SuppliersPage })));
const PurchaseReturnsPage = lazy(() => import('@/pages/purchases/PurchaseReturnsPage').then((m) => ({ default: m.PurchaseReturnsPage })));
const PurchaseBillUploadPage = lazy(() => import('@/pages/purchases/PurchaseBillUploadPage').then((m) => ({ default: m.PurchaseBillUploadPage })));
const PurchaseDetailPage = lazy(() => import('@/pages/purchases/PurchaseDetailPage').then((m) => ({ default: m.PurchaseDetailPage })));
const ProductsPage = lazy(() => import('@/pages/inventory/ProductsPage').then((m) => ({ default: m.ProductsPage })));
const CurrentStockPage = lazy(() => import('@/pages/inventory/CurrentStockPage').then((m) => ({ default: m.CurrentStockPage })));
const StockAdjustmentPage = lazy(() => import('@/pages/inventory/StockAdjustmentPage').then((m) => ({ default: m.StockAdjustmentPage })));
const LowStockPage = lazy(() => import('@/pages/inventory/LowStockPage').then((m) => ({ default: m.LowStockPage })));
const SalesReportPage = lazy(() => import('@/pages/reports/SalesReportPage').then((m) => ({ default: m.SalesReportPage })));
const PurchaseReportPage = lazy(() => import('@/pages/reports/PurchaseReportPage').then((m) => ({ default: m.PurchaseReportPage })));
const InventoryReportPage = lazy(() => import('@/pages/reports/InventoryReportPage').then((m) => ({ default: m.InventoryReportPage })));
const CustomerLedgerPage = lazy(() => import('@/pages/reports/CustomerLedgerPage').then((m) => ({ default: m.CustomerLedgerPage })));
const SupplierLedgerPage = lazy(() => import('@/pages/reports/SupplierLedgerPage').then((m) => ({ default: m.SupplierLedgerPage })));
const CompanySettingsPage = lazy(() => import('@/pages/settings/CompanySettingsPage').then((m) => ({ default: m.CompanySettingsPage })));
const GstSettingsPage = lazy(() => import('@/pages/settings/GstSettingsPage').then((m) => ({ default: m.GstSettingsPage })));
const InvoiceTemplatesPage = lazy(() => import('@/pages/settings/InvoiceTemplatesPage').then((m) => ({ default: m.InvoiceTemplatesPage })));
const UsersSettingsPage = lazy(() => import('@/pages/settings/UsersSettingsPage').then((m) => ({ default: m.UsersSettingsPage })));
const ImportPage = lazy(() => import('@/pages/settings/ImportPage').then((m) => ({ default: m.ImportPage })));
const BackupExportPage = lazy(() => import('@/pages/settings/BackupExportPage').then((m) => ({ default: m.BackupExportPage })));

function RouteFallback() {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="40vh">
      <CircularProgress />
    </Box>
  );
}

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
    <Suspense fallback={<RouteFallback />}>
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
            </Route>
            <Route element={<RoleRoute allow={canAccessSettings} />}>
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
    </Suspense>
  );
}

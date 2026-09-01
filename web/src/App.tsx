import { lazy, Suspense } from 'react';
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { CircularProgress, Box } from '@mui/material';
import { useAuth } from '@/auth/AuthContext';
import {
  isAccountingFeatureEnabled,
  isAiInsightsEnabled,
  isCrmEnabled,
  isGstrReportsEnabled,
  isManufacturingEnabled,
  isPayrollEnabled,
  isPosEnabled,
  isTallyEnabled,
  isTdsEnabled,
} from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { AppShell } from '@/layouts/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { ForgotPasswordPage } from '@/pages/ForgotPasswordPage';
import { ResetPasswordPage } from '@/pages/ResetPasswordPage';
import { AcceptInvitePage } from '@/pages/AcceptInvitePage';
import { HomePage } from '@/pages/HomePage';
import { LimitedAccessLanding } from '@/pages/LimitedAccessLanding';
import { NotFoundPage } from '@/pages/NotFoundPage';
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
  canManageManufacturing,
  canManagePayroll,
  canManageCrm,
  canViewAiInsights,
  canUseAiAssistant,
  canViewFinancialReports,
  canViewInventorySurfaces,
  canViewPurchaseSurfaces,
  canViewSalesSurfaces,
  canViewPaymentSurfaces,
  canViewBankRecon,
  isOwner,
} from '@/utils/permissions';
import type { User } from '@/types/domain';

const NewInvoicePage = lazy(() => import('@/pages/sales/NewInvoicePage').then((m) => ({ default: m.NewInvoicePage })));
const SalesBillUploadPage = lazy(() => import('@/pages/sales/SalesBillUploadPage').then((m) => ({ default: m.SalesBillUploadPage })));
const SalesHistoryPage = lazy(() => import('@/pages/sales/SalesHistoryPage').then((m) => ({ default: m.SalesHistoryPage })));
const InvoiceDetailPage = lazy(() => import('@/pages/sales/InvoiceDetailPage').then((m) => ({ default: m.InvoiceDetailPage })));
const QuotationsPage = lazy(() => import('@/pages/sales/QuotationsPage').then((m) => ({ default: m.QuotationsPage })));
const ReceiptsPage = lazy(() => import('@/pages/sales/ReceiptsPage').then((m) => ({ default: m.ReceiptsPage })));
const CustomersPage = lazy(() => import('@/pages/sales/CustomersPage').then((m) => ({ default: m.CustomersPage })));
const SalesReturnsPage = lazy(() => import('@/pages/sales/SalesReturnsPage').then((m) => ({ default: m.SalesReturnsPage })));
const CreditNotesPage = lazy(() => import('@/pages/sales/CreditNotesPage').then((m) => ({ default: m.CreditNotesPage })));
const NewCreditNotePage = lazy(() => import('@/pages/sales/NewCreditNotePage').then((m) => ({ default: m.NewCreditNotePage })));
const DebitNotesPage = lazy(() => import('@/pages/sales/DebitNotesPage').then((m) => ({ default: m.DebitNotesPage })));
const NewDebitNotePage = lazy(() => import('@/pages/sales/NewDebitNotePage').then((m) => ({ default: m.NewDebitNotePage })));
const SalesOrdersPage = lazy(() => import('@/pages/sales/SalesOrdersPage').then((m) => ({ default: m.SalesOrdersPage })));
const NewSalesOrderPage = lazy(() => import('@/pages/sales/NewSalesOrderPage').then((m) => ({ default: m.NewSalesOrderPage })));
const DeliveryChallansPage = lazy(() => import('@/pages/sales/DeliveryChallansPage').then((m) => ({ default: m.DeliveryChallansPage })));
const NewDeliveryChallanPage = lazy(() => import('@/pages/sales/NewDeliveryChallanPage').then((m) => ({ default: m.NewDeliveryChallanPage })));
const NewPurchasePage = lazy(() => import('@/pages/purchases/NewPurchasePage').then((m) => ({ default: m.NewPurchasePage })));
const PurchaseHistoryPage = lazy(() => import('@/pages/purchases/PurchaseHistoryPage').then((m) => ({ default: m.PurchaseHistoryPage })));
const SupplierPaymentsPage = lazy(() => import('@/pages/purchases/SupplierPaymentsPage').then((m) => ({ default: m.SupplierPaymentsPage })));
const SuppliersPage = lazy(() => import('@/pages/purchases/SuppliersPage').then((m) => ({ default: m.SuppliersPage })));
const PurchaseReturnsPage = lazy(() => import('@/pages/purchases/PurchaseReturnsPage').then((m) => ({ default: m.PurchaseReturnsPage })));
const PurchaseCreditNotesPage = lazy(() => import('@/pages/purchases/PurchaseCreditNotesPage').then((m) => ({ default: m.PurchaseCreditNotesPage })));
const NewPurchaseCreditNotePage = lazy(() => import('@/pages/purchases/NewPurchaseCreditNotePage').then((m) => ({ default: m.NewPurchaseCreditNotePage })));
const PurchaseDebitNotesPage = lazy(() => import('@/pages/purchases/PurchaseDebitNotesPage').then((m) => ({ default: m.PurchaseDebitNotesPage })));
const NewPurchaseDebitNotePage = lazy(() => import('@/pages/purchases/NewPurchaseDebitNotePage').then((m) => ({ default: m.NewPurchaseDebitNotePage })));
const PurchaseOrdersPage = lazy(() => import('@/pages/purchases/PurchaseOrdersPage').then((m) => ({ default: m.PurchaseOrdersPage })));
const NewPurchaseOrderPage = lazy(() => import('@/pages/purchases/NewPurchaseOrderPage').then((m) => ({ default: m.NewPurchaseOrderPage })));
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
const Gstr1ReportPage = lazy(() => import('@/pages/reports/GstReturnPage').then((m) => ({ default: m.Gstr1ReportPage })));
const Gstr3bReportPage = lazy(() => import('@/pages/reports/GstReturnPage').then((m) => ({ default: m.Gstr3bReportPage })));
const Gstr6ReportPage = lazy(() => import('@/pages/reports/GstReturnPage').then((m) => ({ default: m.Gstr6ReportPage })));
const Gstr7ReportPage = lazy(() => import('@/pages/reports/GstReturnPage').then((m) => ({ default: m.Gstr7ReportPage })));
const Gstr8ReportPage = lazy(() => import('@/pages/reports/GstReturnPage').then((m) => ({ default: m.Gstr8ReportPage })));
const Gstr9ReportPage = lazy(() => import('@/pages/reports/Gstr9ReportPage').then((m) => ({ default: m.Gstr9ReportPage })));
const GstHealthPage = lazy(() => import('@/pages/reports/GstHealthPage').then((m) => ({ default: m.GstHealthPage })));
const GstRateExposurePage = lazy(() => import('@/pages/reports/GstRateExposurePage').then((m) => ({ default: m.GstRateExposurePage })));
const Gstr2bPage = lazy(() => import('@/pages/reports/Gstr2bPage').then((m) => ({ default: m.Gstr2bPage })));
const MissingDocumentsPage = lazy(() =>
  import('@/pages/reports/MissingDocumentsPage').then((m) => ({ default: m.MissingDocumentsPage })),
);
const StatutoryEventsPage = lazy(() => import('@/pages/reports/StatutoryEventsPage').then((m) => ({ default: m.StatutoryEventsPage })));
const InsightsHubPage = lazy(() => import('@/pages/insights/InsightsHubPage').then((m) => ({ default: m.InsightsHubPage })));
const InsightsAlertsPage = lazy(() => import('@/pages/insights/InsightsAlertsPage').then((m) => ({ default: m.InsightsAlertsPage })));
const InsightsHealthPage = lazy(() => import('@/pages/insights/InsightsHealthPage').then((m) => ({ default: m.InsightsHealthPage })));
const InsightsCashflowPage = lazy(() => import('@/pages/insights/InsightsCashflowPage').then((m) => ({ default: m.InsightsCashflowPage })));
const InsightsAssistantPage = lazy(() => import('@/pages/insights/InsightsAssistantPage').then((m) => ({ default: m.InsightsAssistantPage })));
const AttentionPage = lazy(() => import('@/pages/AttentionPage').then((m) => ({ default: m.AttentionPage })));
const TallyMigrationPage = lazy(() => import('@/pages/settings/TallyMigrationPage').then((m) => ({ default: m.TallyMigrationPage })));
const AiSettingsPage = lazy(() => import('@/pages/settings/AiSettingsPage').then((m) => ({ default: m.AiSettingsPage })));
const CompanySettingsPage = lazy(() => import('@/pages/settings/CompanySettingsPage').then((m) => ({ default: m.CompanySettingsPage })));
const GstSettingsPage = lazy(() => import('@/pages/settings/GstSettingsPage').then((m) => ({ default: m.GstSettingsPage })));
const UnitsSettingsPage = lazy(() => import('@/pages/settings/UnitsSettingsPage').then((m) => ({ default: m.UnitsSettingsPage })));
const InvoiceTemplatesPage = lazy(() => import('@/pages/settings/InvoiceTemplatesPage').then((m) => ({ default: m.InvoiceTemplatesPage })));
const UsersSettingsPage = lazy(() => import('@/pages/settings/UsersSettingsPage').then((m) => ({ default: m.UsersSettingsPage })));
const ImportPage = lazy(() => import('@/pages/settings/ImportPage').then((m) => ({ default: m.ImportPage })));
const BackupExportPage = lazy(() => import('@/pages/settings/BackupExportPage').then((m) => ({ default: m.BackupExportPage })));
const BillingPage = lazy(() => import('@/pages/settings/BillingPage').then((m) => ({ default: m.BillingPage })));
const BankAccountsPage = lazy(() => import('@/pages/settings/BankAccountsPage').then((m) => ({ default: m.BankAccountsPage })));
const PaymentGatewayPage = lazy(() => import('@/pages/settings/PaymentGatewayPage').then((m) => ({ default: m.PaymentGatewayPage })));
const PaymentLinksPage = lazy(() => import('@/pages/payments/PaymentLinksPage').then((m) => ({ default: m.PaymentLinksPage })));
const BankStatementsPage = lazy(() => import('@/pages/payments/BankStatementsPage').then((m) => ({ default: m.BankStatementsPage })));
const BankReconPage = lazy(() => import('@/pages/payments/BankReconPage').then((m) => ({ default: m.BankReconPage })));
const CashBookPage = lazy(() => import('@/pages/reports/CashBookPage').then((m) => ({ default: m.CashBookPage })));
const WarehousesPage = lazy(() => import('@/pages/inventory/WarehousesPage').then((m) => ({ default: m.WarehousesPage })));
const StockTransferPage = lazy(() => import('@/pages/inventory/StockTransferPage').then((m) => ({ default: m.StockTransferPage })));
const ExpiryAlertsPage = lazy(() => import('@/pages/inventory/ExpiryAlertsPage').then((m) => ({ default: m.ExpiryAlertsPage })));
const StockCountPage = lazy(() => import('@/pages/inventory/StockCountPage').then((m) => ({ default: m.StockCountPage })));
const SerialsPage = lazy(() => import('@/pages/inventory/SerialsPage').then((m) => ({ default: m.SerialsPage })));
const StockValuationPage = lazy(() => import('@/pages/reports/StockValuationPage').then((m) => ({ default: m.StockValuationPage })));
const PriceListsPage = lazy(() => import('@/pages/settings/PriceListsPage').then((m) => ({ default: m.PriceListsPage })));
const ItemSettingsPage = lazy(() => import('@/pages/settings/ItemSettingsPage').then((m) => ({ default: m.ItemSettingsPage })));
const AccountingSettingsPage = lazy(() => import('@/pages/settings/AccountingSettingsPage').then((m) => ({ default: m.AccountingSettingsPage })));
const ChartOfAccountsPage = lazy(() => import('@/pages/accounting/ChartOfAccountsPage').then((m) => ({ default: m.ChartOfAccountsPage })));
const JournalsPage = lazy(() => import('@/pages/accounting/JournalsPage').then((m) => ({ default: m.JournalsPage })));
const TrialBalancePage = lazy(() => import('@/pages/reports/TrialBalancePage').then((m) => ({ default: m.TrialBalancePage })));
const ProfitAndLossPage = lazy(() => import('@/pages/reports/ProfitAndLossPage').then((m) => ({ default: m.ProfitAndLossPage })));
const BalanceSheetPage = lazy(() => import('@/pages/reports/BalanceSheetPage').then((m) => ({ default: m.BalanceSheetPage })));
const BooksHealthPage = lazy(() => import('@/pages/reports/BooksHealthPage').then((m) => ({ default: m.BooksHealthPage })));
const AccountingBankReconPage = lazy(() => import('@/pages/accounting/AccountingBankReconPage').then((m) => ({ default: m.AccountingBankReconPage })));
const CostCentersPage = lazy(() => import('@/pages/accounting/CostCentersPage').then((m) => ({ default: m.CostCentersPage })));
const FixedAssetsPage = lazy(() => import('@/pages/accounting/FixedAssetsPage').then((m) => ({ default: m.FixedAssetsPage })));
const PeriodsPage = lazy(() => import('@/pages/accounting/PeriodsPage').then((m) => ({ default: m.PeriodsPage })));
const RecurringInvoicesPage = lazy(() => import('@/pages/sales/RecurringInvoicesPage').then((m) => ({ default: m.RecurringInvoicesPage })));
const TdsTcsReportsPage = lazy(() => import('@/pages/reports/TdsTcsReportsPage').then((m) => ({ default: m.TdsTcsReportsPage })));
const PublicPayPage = lazy(() => import('@/pages/public/PublicPayPage').then((m) => ({ default: m.PublicPayPage })));
const BomsPage = lazy(() =>
  import('@/pages/manufacturing/BomsPage').then((m) => ({ default: m.BomsPage })),
);
const WorkOrdersPage = lazy(() =>
  import('@/pages/manufacturing/WorkOrdersPage').then((m) => ({ default: m.WorkOrdersPage })),
);
const EmployeesPage = lazy(() =>
  import('@/pages/payroll/EmployeesPage').then((m) => ({ default: m.EmployeesPage })),
);
const PayRunsPage = lazy(() =>
  import('@/pages/payroll/PayRunsPage').then((m) => ({ default: m.PayRunsPage })),
);
const LeadsPage = lazy(() => import('@/pages/crm/LeadsPage').then((m) => ({ default: m.LeadsPage })));
const OpportunitiesPage = lazy(() =>
  import('@/pages/crm/OpportunitiesPage').then((m) => ({ default: m.OpportunitiesPage })),
);
const PosPage = lazy(() => import('@/pages/pos/PosPage').then((m) => ({ default: m.PosPage })));
const OfflineOutboxPage = lazy(() =>
  import('@/pages/offline/OfflineOutboxPage').then((m) => ({ default: m.OfflineOutboxPage })),
);
const SetupWizardPage = lazy(() => import('@/pages/setup/SetupWizardPage').then((m) => ({ default: m.SetupWizardPage })));
const HelpPage = lazy(() => import('@/pages/help/HelpPage').then((m) => ({ default: m.HelpPage })));
const HelpHealthPage = lazy(() => import('@/pages/help/HelpHealthPage').then((m) => ({ default: m.HelpHealthPage })));

function RouteFallback() {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="40vh">
      <CircularProgress />
    </Box>
  );
}

function ProtectedRoute() {
  const { isAuthenticated, authReady } = useAuth();
  const location = useLocation();
  if (!authReady) {
    return <RouteFallback />;
  }
  if (!isAuthenticated) {
    // UXW2-002: preserve deep link so login returns user to the interrupted page.
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

function RoleRoute({
  allow,
}: {
  allow: (user: User | null) => boolean;
}) {
  const { user, authReady } = useAuth();
  if (!authReady) {
    return <RouteFallback />;
  }
  if (!allow(user)) {
    return <LimitedAccessLanding />;
  }
  return <Outlet />;
}

function allowHelpHealth(user: User | null): boolean {
  if (!user) return false;
  return isOwner(user.role) || Boolean(user.isStaff);
}

function allowAiInsights(user: User | null): boolean {
  return isAiInsightsEnabled() && canViewAiInsights(user);
}

function allowAiAssistant(user: User | null): boolean {
  return isAiInsightsEnabled() && canUseAiAssistant(user);
}

function allowGstrReports(user: User | null): boolean {
  return isGstrReportsEnabled() && canViewFinancialReports(user);
}

function allowTdsReports(user: User | null): boolean {
  return isTdsEnabled() && canViewFinancialReports(user);
}

function allowManufacturing(user: User | null): boolean {
  return canManageManufacturing(user) && isManufacturingEnabled();
}

function allowPayroll(user: User | null): boolean {
  return canManagePayroll(user) && isPayrollEnabled();
}

function allowCrm(user: User | null): boolean {
  return canManageCrm(user) && isCrmEnabled();
}

function allowAccounting(user: User | null): boolean {
  return (
    isAccountingFeatureEnabled() &&
    Boolean(user?.company?.accountingEnabled) &&
    canViewFinancialReports(user)
  );
}

function allowAccountingSettings(user: User | null): boolean {
  return canManageUsers(user);
}

function allowAiSettings(user: User | null): boolean {
  return canManageUsers(user);
}

function allowTally(user: User | null): boolean {
  return isTallyEnabled() && canImport(user);
}

function allowPos(user: User | null): boolean {
  return (isPosEnabled() || isRuntimeFlagEnabled('ENABLE_POS')) && canCreateSales(user);
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

function SalesOrderEditor() {
  const { id } = useParams();
  return <NewSalesOrderPage key={id ?? 'new'} />;
}

function DeliveryChallanEditor() {
  const { id } = useParams();
  return <NewDeliveryChallanPage key={id ?? 'new'} />;
}

function PurchaseOrderEditor() {
  const { id } = useParams();
  return <NewPurchaseOrderPage key={id ?? 'new'} />;
}

function CreditNoteEditor() {
  const { id } = useParams();
  return <NewCreditNotePage key={id ?? 'new'} />;
}

function DebitNoteEditor() {
  const { id } = useParams();
  return <NewDebitNotePage key={id ?? 'new'} />;
}

function PurchaseCreditNoteEditor() {
  const { id } = useParams();
  return <NewPurchaseCreditNotePage key={id ?? 'new'} />;
}

function PurchaseDebitNoteEditor() {
  const { id } = useParams();
  return <NewPurchaseDebitNotePage key={id ?? 'new'} />;
}

export function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/invite" element={<AcceptInvitePage />} />
        <Route path="/pay/:token" element={<PublicPayPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<RoleRoute allow={(user) => user?.role === 'OWNER'} />}>
            <Route path="setup" element={<SetupWizardPage />} />
          </Route>
          <Route element={<AppShell />}>
            <Route path="reports/profit-loss" element={<Navigate to="/reports/profit-and-loss" replace />} />
            <Route path="accounting/chart-of-accounts" element={<Navigate to="/accounting/accounts" replace />} />
            <Route path="accounting/bank-recon" element={<Navigate to="/accounting/bank-reconciliation" replace />} />
            <Route path="sales/quotations/new" element={<Navigate to="/sales/quotations?create=1" replace />} />
            <Route path="sales/returns/new" element={<Navigate to="/sales/returns?create=1" replace />} />
            <Route path="purchases/returns/new" element={<Navigate to="/purchases/returns?create=1" replace />} />
            <Route index element={<HomePage />} />
            <Route path="offline-outbox" element={<OfflineOutboxPage />} />
            <Route path="help" element={<HelpPage />} />
            <Route element={<RoleRoute allow={allowHelpHealth} />}>
              <Route path="settings/help" element={<HelpHealthPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowAiInsights} />}>
              <Route path="insights" element={<InsightsHubPage />} />
              <Route path="insights/alerts" element={<InsightsAlertsPage />} />
              <Route path="insights/health" element={<InsightsHealthPage />} />
              <Route path="insights/cashflow" element={<InsightsCashflowPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowAiAssistant} />}>
              <Route path="insights/assistant" element={<InsightsAssistantPage />} />
            </Route>
            <Route element={<RoleRoute allow={canCreateSales} />}>
              <Route path="sales/new" element={<SalesInvoiceEditor />} />
              <Route path="sales/history/:id/edit" element={<SalesInvoiceEditor />} />
            </Route>
            <Route element={<RoleRoute allow={canImport} />}>
              <Route path="sales/bill-upload" element={<SalesBillUploadPage />} />
              <Route path="sales/upload" element={<Navigate to="/sales/bill-upload" replace />} />
            </Route>
            <Route element={<RoleRoute allow={allowPos} />}>
              <Route path="pos" element={<PosPage />} />
            </Route>
            <Route element={<RoleRoute allow={canViewSalesSurfaces} />}>
              <Route path="sales/history" element={<SalesHistoryPage />} />
              <Route path="sales/history/:id" element={<InvoiceDetailPage />} />
              <Route path="sales/credit-notes" element={<CreditNotesPage />} />
              <Route path="sales/debit-notes" element={<DebitNotesPage />} />
              <Route path="sales/orders" element={<SalesOrdersPage />} />
              <Route path="sales/delivery-challans" element={<DeliveryChallansPage />} />
              <Route path="sales/recurring" element={<RecurringInvoicesPage />} />
              <Route path="sales/customers" element={<CustomersPage />} />
            </Route>
            {/* BB-000480: list & detail surfaces use view ACL; create stay on canCreateSales. */}
            <Route element={<RoleRoute allow={canViewSalesSurfaces} />}>
              <Route path="sales/quotations" element={<QuotationsPage />} />
              <Route path="sales/returns" element={<SalesReturnsPage />} />
              <Route path="sales/credit-notes/:id" element={<CreditNoteEditor />} />
              <Route path="sales/debit-notes/:id" element={<DebitNoteEditor />} />
              <Route path="sales/orders/:id" element={<SalesOrderEditor />} />
              <Route path="sales/delivery-challans/:id" element={<DeliveryChallanEditor />} />
            </Route>
            <Route element={<RoleRoute allow={canCreateSales} />}>
              <Route path="sales/credit-notes/new" element={<CreditNoteEditor />} />
              <Route path="sales/debit-notes/new" element={<DebitNoteEditor />} />
              <Route path="sales/orders/new" element={<SalesOrderEditor />} />
              <Route path="sales/delivery-challans/new" element={<DeliveryChallanEditor />} />
            </Route>
            <Route element={<RoleRoute allow={canViewPaymentSurfaces} />}>
              <Route path="sales/receipts" element={<ReceiptsPage />} />
            </Route>
            <Route element={<RoleRoute allow={canViewBankRecon} />}>
              <Route path="payments/reconciliation" element={<BankReconPage />} />
              <Route path="payments/recon" element={<Navigate to="/payments/reconciliation" replace />} />
            </Route>
            <Route element={<RoleRoute allow={canCreatePayments} />}>
              <Route path="purchases/payments" element={<SupplierPaymentsPage />} />
              <Route path="payments/links" element={<PaymentLinksPage />} />
              <Route path="payments/statements" element={<BankStatementsPage />} />
            </Route>
            <Route element={<RoleRoute allow={canViewPurchaseSurfaces} />}>
              <Route path="purchases/returns" element={<PurchaseReturnsPage />} />
            </Route>
            <Route element={<RoleRoute allow={canCreatePurchases} />}>
              <Route path="purchases/new" element={<PurchaseInvoiceEditor />} />
              <Route path="purchases/history/:id/edit" element={<PurchaseInvoiceEditor />} />
              <Route path="purchases/credit-notes/new" element={<PurchaseCreditNoteEditor />} />
              <Route path="purchases/debit-notes/new" element={<PurchaseDebitNoteEditor />} />
              <Route path="purchases/orders/new" element={<PurchaseOrderEditor />} />
            </Route>
            <Route element={<RoleRoute allow={canViewPurchaseSurfaces} />}>
              <Route path="purchases/history" element={<PurchaseHistoryPage />} />
              <Route path="purchases/history/:id" element={<PurchaseDetailPage />} />
              <Route path="purchases/credit-notes" element={<PurchaseCreditNotesPage />} />
              <Route path="purchases/credit-notes/:id" element={<PurchaseCreditNoteEditor />} />
              <Route path="purchases/debit-notes" element={<PurchaseDebitNotesPage />} />
              <Route path="purchases/debit-notes/:id" element={<PurchaseDebitNoteEditor />} />
              <Route path="purchases/orders" element={<PurchaseOrdersPage />} />
              <Route path="purchases/orders/:id" element={<PurchaseOrderEditor />} />
              <Route path="purchases/suppliers" element={<SuppliersPage />} />
            </Route>
            <Route element={<RoleRoute allow={canImport} />}>
              <Route path="purchases/bill-upload" element={<PurchaseBillUploadPage />} />
              <Route path="purchases/upload" element={<Navigate to="/purchases/bill-upload" replace />} />
            </Route>
            <Route element={<RoleRoute allow={canViewInventorySurfaces} />}>
              <Route path="inventory/products" element={<ProductsPage />} />
              <Route path="inventory/stock" element={<CurrentStockPage />} />
              <Route path="inventory/low-stock" element={<LowStockPage />} />
              <Route path="inventory/expiry-alerts" element={<ExpiryAlertsPage />} />
              <Route path="inventory/expiry" element={<Navigate to="/inventory/expiry-alerts" replace />} />
            </Route>
            <Route element={<RoleRoute allow={canAdjustInventory} />}>
              <Route path="inventory/adjustments" element={<StockAdjustmentPage />} />
              <Route path="inventory/warehouses" element={<WarehousesPage />} />
              <Route path="inventory/stock-counts" element={<StockCountPage />} />
              <Route path="inventory/count" element={<Navigate to="/inventory/stock-counts" replace />} />
              <Route path="inventory/transfers" element={<StockTransferPage />} />
              <Route path="inventory/serials" element={<SerialsPage />} />
            </Route>
            <Route element={<RoleRoute allow={canViewFinancialReports} />}>
              <Route path="attention" element={<AttentionPage />} />
              <Route path="reports/sales" element={<SalesReportPage />} />
              <Route path="reports/purchases" element={<PurchaseReportPage />} />
              <Route path="reports/inventory" element={<InventoryReportPage />} />
              <Route path="reports/customer-ledger" element={<CustomerLedgerPage />} />
              <Route path="reports/supplier-ledger" element={<SupplierLedgerPage />} />
              <Route path="reports/statutory-events" element={<StatutoryEventsPage />} />
              <Route path="reports/cash-book" element={<CashBookPage />} />
              <Route path="reports/stock-valuation" element={<StockValuationPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowTdsReports} />}>
              <Route path="reports/tds-tcs" element={<TdsTcsReportsPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowAccounting} />}>
              <Route path="reports/trial-balance" element={<TrialBalancePage />} />
              <Route path="reports/profit-and-loss" element={<ProfitAndLossPage />} />
              <Route path="reports/balance-sheet" element={<BalanceSheetPage />} />
              <Route path="reports/books-health" element={<BooksHealthPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowGstrReports} />}>
              <Route path="reports/gstr1" element={<Gstr1ReportPage />} />
              <Route path="reports/gstr3b" element={<Gstr3bReportPage />} />
              <Route path="reports/gstr6" element={<Gstr6ReportPage />} />
              <Route path="reports/gstr7" element={<Gstr7ReportPage />} />
              <Route path="reports/gstr8" element={<Gstr8ReportPage />} />
              <Route path="reports/gstr9" element={<Gstr9ReportPage />} />
              <Route path="reports/gstr2b" element={<Gstr2bPage />} />
              <Route path="reports/missing-documents" element={<MissingDocumentsPage />} />
              <Route path="ca-needs" element={<MissingDocumentsPage />} />
              <Route path="reports/gst-health" element={<GstHealthPage />} />
              <Route path="reports/gst-rate-exposure" element={<GstRateExposurePage />} />
            </Route>
            <Route element={<RoleRoute allow={canAccessSettings} />}>
              <Route element={<RoleRoute allow={canManageUsers} />}>
                <Route path="settings/company" element={<CompanySettingsPage />} />
                <Route path="settings/units" element={<UnitsSettingsPage />} />
                <Route path="settings/items" element={<ItemSettingsPage />} />
                <Route path="settings/templates" element={<InvoiceTemplatesPage />} />
                <Route path="settings/users" element={<UsersSettingsPage />} />
                <Route path="settings/bank-accounts" element={<BankAccountsPage />} />
                <Route path="settings/payment-gateway" element={<PaymentGatewayPage />} />
                <Route path="settings/billing" element={<BillingPage />} />
                <Route path="settings/price-lists" element={<PriceListsPage />} />
              </Route>
              <Route element={<RoleRoute allow={canExport} />}>
                <Route path="settings/backup" element={<BackupExportPage />} />
              </Route>
              <Route element={<RoleRoute allow={allowAiSettings} />}>
                <Route path="settings/ai" element={<AiSettingsPage />} />
              </Route>
              <Route element={<RoleRoute allow={allowAccountingSettings} />}>
                <Route path="settings/accounting" element={<AccountingSettingsPage />} />
              </Route>
              <Route element={<RoleRoute allow={canManageGst} />}>
                <Route path="settings/gst" element={<GstSettingsPage />} />
              </Route>
              <Route element={<RoleRoute allow={canImport} />}>
                <Route path="settings/import" element={<ImportPage />} />
              </Route>
              <Route element={<RoleRoute allow={allowTally} />}>
                <Route path="settings/tally" element={<TallyMigrationPage />} />
              </Route>
            </Route>
            <Route element={<RoleRoute allow={allowAccounting} />}>
              <Route path="accounting/accounts" element={<ChartOfAccountsPage />} />
              <Route path="accounting/journals" element={<JournalsPage />} />
              <Route path="accounting/bank-reconciliation" element={<AccountingBankReconPage />} />
              <Route path="accounting/cost-centers" element={<CostCentersPage />} />
              <Route path="accounting/fixed-assets" element={<FixedAssetsPage />} />
              <Route path="accounting/periods" element={<PeriodsPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowManufacturing} />}>
              <Route path="manufacturing" element={<Navigate to="/manufacturing/boms" replace />} />
              <Route path="manufacturing/boms" element={<BomsPage />} />
              <Route path="manufacturing/work-orders" element={<WorkOrdersPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowPayroll} />}>
              <Route path="payroll" element={<Navigate to="/payroll/employees" replace />} />
              <Route path="payroll/employees" element={<EmployeesPage />} />
              <Route path="payroll/pay-runs" element={<PayRunsPage />} />
            </Route>
            <Route element={<RoleRoute allow={allowCrm} />}>
              <Route path="crm" element={<Navigate to="/crm/leads" replace />} />
              <Route path="crm/leads" element={<LeadsPage />} />
              <Route path="crm/opportunities" element={<OpportunitiesPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

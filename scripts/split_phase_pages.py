"""Split remaining PhasePages.tsx exports into domain files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web" / "src" / "pages" / "phase"
src = (ROOT / "PhasePages.tsx").read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)

header = "".join(lines[:34]) + "\n"
chunks = {
    "BankingPhasePages.tsx": (46, 689),
    "InventoryPhasePages.tsx": (690, 1083),
    "AccountingExtraPages.tsx": (1084, len(lines)),
}
for name, (start, end) in chunks.items():
    body = "".join(lines[start - 1 : end])
    (ROOT / name).write_text(header + body, encoding="utf-8")

(ROOT / "PhasePages.tsx").write_text(
    """export { JournalsPage } from '@/pages/phase/JournalsPage';
export { FixedAssetsPage } from '@/pages/phase/FixedAssetsPage';
export { PeriodsPage } from '@/pages/phase/PeriodsPage';
export {
  ChartOfAccountsPage,
  TrialBalancePage,
  ProfitAndLossPage,
  BalanceSheetPage,
  BooksHealthPage,
} from '@/pages/phase/AccountingReportsPages';
export {
  BankAccountsPage,
  PaymentGatewayPage,
  PaymentLinksPage,
  BankStatementsPage,
  BankReconPage,
  CashBookPage,
} from '@/pages/phase/BankingPhasePages';
export {
  WarehousesPage,
  StockTransferPage,
  ExpiryAlertsPage,
  SerialsPage,
  StockValuationPage,
  PriceListsPage,
} from '@/pages/phase/InventoryPhasePages';
export {
  AccountingSettingsPage,
  AccountingBankReconPage,
  CostCentersPage,
} from '@/pages/phase/AccountingExtraPages';
""",
    encoding="utf-8",
)
print("split ok")

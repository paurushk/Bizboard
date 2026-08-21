export type Role = 'OWNER' | 'SALES_STAFF' | 'ACCOUNTANT' | 'VIEWER';

export interface BankAccount {
  id: number;
  name: string;
  accountNumberMasked?: string;
  ifsc?: string;
  accountType?: string;
  openingBalance?: string | number;
  openingAsOf?: string;
  isDefault?: boolean;
  isActive?: boolean;
}

export interface PaymentLink {
  id: number;
  token: string;
  salesInvoice?: number | null;
  invoiceNumber?: string;
  customer?: number | null;
  customerName?: string;
  amount: string | number;
  allowPartial: boolean;
  status: string;
  expiresAt?: string;
  provider?: string;
  providerShortUrl?: string;
  publicPath?: string;
}

export interface Warehouse {
  id: number;
  name: string;
  code: string;
  address?: string;
  isDefault?: boolean;
  isActive?: boolean;
}

export interface StockTransfer {
  id: number;
  number?: string;
  fromWarehouse: number;
  toWarehouse: number;
  status: string;
  notes?: string;
  lines: Array<{ id?: number; product: number; batch?: number | null; serialNumbers?: string[]; quantity: string | number }>;
}

export interface BatchLot {
  id: number;
  product: number;
  productName?: string;
  batchNo: string;
  expiryDate?: string | null;
  manufacturingDate?: string | null;
}

export interface AccountingAccount {
  id: number;
  code: string;
  name: string;
  type: string;
  parent?: number | null;
  isSystem?: boolean;
  isControl?: boolean;
  isActive?: boolean;
}

export interface JournalEntry {
  id: number;
  number?: string;
  entryDate: string;
  status: string;
  narration?: string;
  lines: Array<{ id?: number; account: number; debit: string | number; credit: string | number; costCenter?: number | null }>;
}

export type DocumentStatus = 'DRAFT' | 'COMPLETED' | 'CANCELLED' | 'RETURNED' | 'CONVERTED';

export type NoteReason =
  | 'SALES_RETURN'
  | 'POST_SALE_DISCOUNT'
  | 'DEFICIENCY_IN_SERVICE'
  | 'CORRECTION_OF_INVOICE'
  | 'OTHERS';

export type CustomerStatus = 'ACTIVE' | 'BLOCKED';
export type ProductStatus = 'ACTIVE' | 'INACTIVE';

export type InvoiceType = 'GST' | 'TAX' | 'RETAIL' | 'NON_GST';
export type SupplyType = 'B2B' | 'SEZWP' | 'SEZWOP' | 'EXPWP' | 'EXPWOP' | 'DEXP';
export type PurchaseType = 'GST' | 'NON_GST';

export type PaymentMode = 'CASH' | 'UPI' | 'BANK' | 'CARD' | 'CREDIT';

export type PdfStatus = 'NONE' | 'QUEUED' | 'READY' | 'FAILED';

export type MovementType =
  | 'OPENING_STOCK'
  | 'PURCHASE'
  | 'SALE'
  | 'PURCHASE_RETURN'
  | 'SALES_RETURN'
  | 'ADJUSTMENT';

export type ImportJobStatus =
  | 'UPLOADED'
  | 'EXTRACTING'
  | 'NEEDS_CLARIFICATION'
  | 'PREVIEWED'
  | 'COMMITTED'
  | 'FAILED'
  | 'VOIDED';
export type ImportKind =
  | 'CUSTOMERS'
  | 'SUPPLIERS'
  | 'PRODUCTS'
  | 'OPENING_STOCK'
  | 'PURCHASE_BILL'
  | 'SALES_BILL';

export type RegistrationType = 'REGULAR' | 'COMPOSITION' | 'UNREGISTERED';
export type NegativeStockPolicy = 'BLOCK' | 'WARN';
export type PriceMode = 'EXCLUSIVE' | 'INCLUSIVE';
export type GstinVerificationStatus = 'UNVERIFIED' | 'VERIFIED' | 'INVALID' | 'FAILED' | string;

export interface User {
  id: number;
  email: string;
  fullName: string;
  phone?: string;
  role: Role;
  canManageInventory: boolean;
  canImport: boolean;
  canCancelDocuments?: boolean;
  canViewFinancialReports?: boolean;
  canExport?: boolean;
  canViewAiInsights?: boolean;
  canUseAiAssistant?: boolean;
  canCreateSales?: boolean;
  canCreatePurchases?: boolean;
  canCreatePayments?: boolean;
  canPostJournals?: boolean;
  companyId: number;
  company?: Company;
}

export interface Company {
  id: number;
  name: string;
  legalName?: string;
  gstin?: string;
  registrationType: RegistrationType;
  state: string;
  address?: string;
  city?: string;
  pincode?: string;
  phone?: string;
  email?: string;
  upiId?: string;
  bankName?: string;
  bankAccount?: string;
  bankIfsc?: string;
  fyStartMonth?: number;
  negativeStockPolicy: NegativeStockPolicy;
  invoiceTerms?: string;
  assumeLocalStateForBlankParty?: boolean;
  isGstRegistered?: boolean;
  gstinVerificationStatus?: GstinVerificationStatus;
  gstinLegalName?: string;
  pan?: string;
  panVerificationStatus?: string;
  panLegalName?: string;
  panVerifiedAt?: string | null;
  udyam?: string;
  udyamVerificationStatus?: string;
  udyamEnterpriseName?: string;
  udyamVerifiedAt?: string | null;
  gspProvider?: string;
  gspCredentialsConfigured?: boolean;
  einvoiceEnabled?: boolean;
  ewayEnabled?: boolean;
  ewayThresholdAmount?: string | number;
  aatoTurnover?: string | number | null;
  logo?: number | null;
  signature?: number | null;
  aiFeaturesEnabled?: boolean;
  aiMonthlyTokenBudget?: number | null;
  openingCashBalance?: string | number | null;
  openingCashAsOf?: string | null;
  dailySummaryEmailEnabled?: boolean;
  accountingEnabled?: boolean;
  onboardingDismissedAt?: string | null;
  taxProfileConfirmedAt?: string | null;
  onboardingStartedAt?: string | null;
  onboarding?: {
    status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'DISMISSED';
    step: 'tax' | 'shop' | 'payments' | 'catalog' | 'first_bill' | null;
    uiStep?: 'tax' | 'shop' | 'payments' | 'catalog' | 'first_bill' | null;
    dismissed: boolean;
    taxDone: boolean;
    shopDone: boolean;
    paymentsDone: boolean;
    catalogDone: boolean;
    activationDone: boolean;
    started: boolean;
  };
}

export interface Customer {
  id: number;
  name: string;
  phone?: string;
  email?: string;
  gstin?: string;
  billingAddress?: string;
  shippingAddress?: string;
  state?: string;
  status: CustomerStatus;
  creditLimit?: string | number;
  creditDays?: number;
  notes?: string;
  outstanding?: string | number;
  gstinVerificationStatus?: GstinVerificationStatus;
  gstinLegalName?: string;
  priceList?: number | null;
}

export interface Supplier {
  id: number;
  name: string;
  phone?: string;
  email?: string;
  gstin?: string;
  address?: string;
  state?: string;
  isActive: boolean;
  notes?: string;
  outstanding?: string | number;
  gstinVerificationStatus?: GstinVerificationStatus;
  gstinLegalName?: string;
}

export interface Unit {
  id: number;
  name: string;
  shortName?: string;
  uqcCode?: string;
}

export interface Product {
  id: number;
  name: string;
  sku: string;
  barcode?: string;
  hsnCode?: string;
  description?: string;
  category?: number | null;
  categoryName?: string;
  brand?: number | null;
  brandName?: string;
  unit?: number | null;
  unitName?: string;
  gstRate: string | number;
  purchasePrice: string | number;
  sellingPrice: string | number;
  mrp?: string | number;
  reorderLevel: string | number;
  trackBatch?: boolean;
  trackSerial?: boolean;
  status: ProductStatus;
  onHand?: string | number;
  reserved?: string | number;
  available?: string | number;
}

export interface LineItem {
  id?: number;
  product: number;
  productName?: string;
  description?: string;
  quantity: string | number;
  unitPrice: string | number;
  unitPriceInclusive?: string | number | null;
  discountPercent?: string | number;
  gstRate?: string | number;
  cessRate?: string | number;
  hsnCode?: string;
  mrp?: string | number;
  unitName?: string;
  batch?: number | null;
  batchNo?: string;
  expDate?: string | null;
  mfgDate?: string | null;
  serialNumbers?: string[];
  taxableAmount?: string | number;
  cgst?: string | number;
  sgst?: string | number;
  igst?: string | number;
  cess?: string | number;
  lineTotal?: string | number;
}

export interface DocumentTotals {
  subtotal: string | number;
  discountTotal: string | number;
  taxableTotal: string | number;
  cgstTotal: string | number;
  sgstTotal: string | number;
  igstTotal: string | number;
  cessTotal?: string | number;
  roundOff: string | number;
  grandTotal: string | number;
}

export type EinvoiceStatus = 'NONE' | 'READY' | 'GENERATED' | 'FAILED' | 'CANCELLED';
export type EwayStatus = 'NONE' | 'READY' | 'GENERATED' | 'FAILED' | 'CANCELLED';

export interface SalesInvoice extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  invoiceType: InvoiceType;
  supplyType?: SupplyType;
  customer: number;
  customerName?: string;
  warehouse?: number | null;
  costCenter?: number | null;
  invoiceDate: string;
  dueDate?: string | null;
  paymentTermsDays?: number;
  additionalCharges?: string | number;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  termsText?: string;
  includeBankDetails?: boolean;
  includePaymentQr?: boolean;
  includeTerms?: boolean;
  signature?: number | null;
  items: LineItem[];
  pdfStatus?: PdfStatus;
  pdfFile?: number | null;
  received?: string | number;
  balance?: string | number;
  completedAt?: string | null;
  cancelledAt?: string | null;
  warnings?: string[];
  einvoiceStatus?: EinvoiceStatus;
  irn?: string;
  ackNo?: string;
  ackDate?: string | null;
  einvoiceQr?: string;
  einvoiceError?: string;
  ewayStatus?: EwayStatus;
  ewayBillNo?: string;
  ewayValidUpto?: string | null;
  ewayError?: string;
  priceMode?: PriceMode;
  tcsSection?: string;
  tcsRate?: string | number;
  tcsAmount?: string | number;
  filingPartyGstin?: string;
  filingPlaceOfSupply?: string;
  vehicleNumber?: string;
  transporterName?: string;
  transporterId?: string;
  transportDistanceKm?: string | number | null;
  isReverseCharge?: boolean;
  ecommerceOperatorGstin?: string;
  companyGstin?: number | null;
}

export interface Quotation extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  invoiceType: InvoiceType;
  customer?: number | null;
  customerName?: string;
  quotationDate: string;
  validUntil?: string | null;
  notes?: string;
  items: LineItem[];
  convertedInvoice?: number | null;
}

export interface SalesReturn extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  customer: number;
  customerName?: string;
  salesInvoice: number;
  returnDate: string;
  reason?: string;
  items: LineItem[];
}

export interface SalesCreditNote extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  customer: number;
  customerName?: string;
  salesInvoice: number;
  invoiceNumber?: string;
  noteDate: string;
  reason: NoteReason;
  reasonDetail?: string;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  items: LineItem[];
  pdfStatus?: PdfStatus;
  completedAt?: string | null;
  cancelledAt?: string | null;
  einvoiceStatus?: EinvoiceStatus;
  irn?: string;
  ackNo?: string;
  ackDate?: string | null;
  einvoiceQr?: string;
  einvoiceError?: string;
}

export interface SalesDebitNote extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  customer: number;
  customerName?: string;
  salesInvoice: number;
  invoiceNumber?: string;
  noteDate: string;
  reason: NoteReason;
  reasonDetail?: string;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  items: LineItem[];
  pdfStatus?: PdfStatus;
  completedAt?: string | null;
  cancelledAt?: string | null;
  einvoiceStatus?: EinvoiceStatus;
  irn?: string;
  ackNo?: string;
  ackDate?: string | null;
  einvoiceQr?: string;
  einvoiceError?: string;
}

export interface SalesOrder extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  customer: number;
  customerName?: string;
  invoiceType: InvoiceType;
  orderDate: string;
  expectedDelivery?: string | null;
  paymentTermsDays?: number;
  additionalCharges?: string | number;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  termsText?: string;
  items: LineItem[];
  convertedInvoice?: number | null;
}

export interface DeliveryChallan extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  customer: number;
  customerName?: string;
  salesOrder?: number | null;
  challanDate: string;
  vehicleNumber?: string;
  transporterName?: string;
  notes?: string;
  items: LineItem[];
  pdfStatus?: PdfStatus;
  completedAt?: string | null;
  cancelledAt?: string | null;
  ewayStatus?: EwayStatus;
  ewayBillNo?: string;
  ewayValidUpto?: string | null;
  ewayError?: string;
}

export interface PurchaseInvoice extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  purchaseType: PurchaseType;
  supplier: number;
  supplierName?: string;
  warehouse?: number | null;
  costCenter?: number | null;
  invoiceDate: string;
  dueDate?: string | null;
  paymentTermsDays?: number;
  additionalCharges?: string | number;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  supplierBillNumber?: string;
  notes?: string;
  termsText?: string;
  includeBankDetails?: boolean;
  includePaymentQr?: boolean;
  includeTerms?: boolean;
  signature?: number | null;
  attachment?: number | null;
  items: LineItem[];
  paid?: string | number;
  balance?: string | number;
  outstanding?: string | number;
  completedAt?: string | null;
  cancelledAt?: string | null;
  priceMode?: PriceMode;
  isReverseCharge?: boolean;
  itcEligibility?: 'CLAIMABLE' | 'INELIGIBLE' | 'REVERSED';
  rcmTaxable?: string | number;
  rcmCgst?: string | number;
  rcmSgst?: string | number;
  rcmIgst?: string | number;
  tdsSection?: string;
  tdsRate?: string | number;
  tdsAmount?: string | number;
}

export interface PurchaseReturn extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  supplier: number;
  supplierName?: string;
  purchaseInvoice: number;
  returnDate: string;
  reason?: string;
  items: LineItem[];
}

export interface PurchaseCreditNote extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  supplier: number;
  supplierName?: string;
  purchaseInvoice?: number | null;
  supplierNoteNumber?: string;
  noteDate: string;
  reason: NoteReason;
  reasonDetail?: string;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  items: LineItem[];
  completedAt?: string | null;
  cancelledAt?: string | null;
}

export interface PurchaseDebitNote extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  supplier: number;
  supplierName?: string;
  purchaseInvoice?: number | null;
  supplierNoteNumber?: string;
  noteDate: string;
  reason: NoteReason;
  reasonDetail?: string;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  items: LineItem[];
  completedAt?: string | null;
  cancelledAt?: string | null;
}

export interface PurchaseOrder extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  supplier: number;
  supplierName?: string;
  purchaseType: PurchaseType;
  orderDate: string;
  expectedDelivery?: string | null;
  paymentTermsDays?: number;
  additionalCharges?: string | number;
  invoiceDiscount?: string | number;
  invoiceDiscountMode?: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff?: boolean;
  notes?: string;
  termsText?: string;
  items: LineItem[];
  convertedPurchase?: number | null;
}

export interface AdjustableInvoiceSummary {
  invoiceId: number;
  invoiceNumber?: string;
  grandTotal: string | number;
  outstanding: string | number;
}

export interface CustomerReceipt {
  id: number;
  number?: string | null;
  customer: number;
  customerName?: string;
  amount: string | number;
  mode: PaymentMode;
  receiptDate: string;
  reference?: string;
  notes?: string;
  allocated: string | number;
  utr?: string;
  utrWarning?: string | null;
  bankAccount?: number | null;
  bankAccountName?: string;
  source?: string;
  status?: string;
  unallocated: string | number;
}

export interface SupplierPayment {
  id: number;
  number?: string | null;
  supplier: number;
  supplierName?: string;
  amount: string | number;
  mode: PaymentMode;
  paymentDate: string;
  reference?: string;
  notes?: string;
  allocated: string | number;
  unallocated: string | number;
  status?: string;
}

export interface PaymentAllocation {
  id: number;
  receipt?: number | null;
  supplierPayment?: number | null;
  salesInvoice?: number | null;
  purchaseInvoice?: number | null;
  amount: string | number;
  reversedAt?: string | null;
  createdAt?: string;
}

export interface StockBalance {
  id?: number;
  product: number;
  warehouse?: number;
  productName: string;
  sku: string;
  onHand: string | number;
  reserved: string | number;
  available: string | number;
  reorderLevel: string | number;
}

export interface StockAdjustment {
  product: number;
  quantity: number;
  reason: string;
  warehouse?: number;
}

export interface OpeningStockInput {
  product: number;
  quantity: number;
  unit_cost?: number;
  warehouse?: number;
  batch?: number;
}

export interface LedgerEntry {
  date: string;
  type: string;
  number?: string;
  /** Internal journal-voucher number (UXW2B-005) — secondary detail, shown only if it differs from `number`. */
  jvNumber?: string;
  referenceId?: number;
  debit: string | number;
  credit: string | number;
  balance: string | number;
}

export interface LedgerStatement {
  customerId?: number;
  customerName?: string;
  supplierId?: number;
  supplierName?: string;
  outstanding: string | number;
  entries: LedgerEntry[];
}

export interface DashboardKpis {
  salesToday: { total: string | number; count: number };
  salesThisMonth: { total: string | number; count: number };
  purchasesThisMonth: { total: string | number; count: number };
  receivables: string | number;
  payables: string | number;
  cashPosition?: string | number;
  cash_position?: string | number;
  lowStockCount: number;
  receivablesAging?: {
    current: string | number;
    days130?: string | number;
    days1_30?: string | number;
    days_1_30?: string | number;
    days3160?: string | number;
    days31_60?: string | number;
    days_31_60?: string | number;
    days6190?: string | number;
    days61_90?: string | number;
    days_61_90?: string | number;
    days90Plus?: string | number;
    days_90_plus?: string | number;
  };
  recentInvoices?: Array<{
    id: number;
    number?: string;
    customer?: string;
    date: string;
    status: string;
    grandTotal: string | number;
  }>;
}

export interface SearchResult {
  id: number | string;
  type: 'invoice' | 'customer' | 'product' | 'supplier';
  title: string;
  subtitle?: string;
  path: string;
}

export interface ImportPreviewRow {
  rowNumber?: number;
  data?: Record<string, string>;
  errors?: string[];
  warnings?: string[];
  [key: string]: unknown;
}

export interface PurchaseBillLinePreview {
  name: string;
  sku?: string;
  hsnCode?: string;
  quantity: string;
  unitPrice: string;
  gstRate: string;
  mrp?: string;
  include?: boolean;
  flags?: string[];
}

export interface BillClarificationOption {
  value: string;
  label: string;
}

export interface BillClarification {
  field: string;
  question: string;
  options: BillClarificationOption[];
  answer: string | null;
}

export interface PurchaseBillPreview {
  supplierName?: string;
  supplierGstin?: string;
  buyerName?: string;
  buyerGstin?: string;
  customerName?: string;
  billNumber?: string;
  billDate?: string;
  extractionConfidence?: number;
  lowConfidenceAccepted?: boolean;
  columnHeaders?: string[];
  printedLineCount?: number;
  resolvedFormula?: string;
  directionWarning?: string;
  warnings?: string[];
  lines: PurchaseBillLinePreview[];
}

export interface ImportJob {
  id: number;
  kind: ImportKind;
  file?: number;
  status: ImportJobStatus;
  totalRows: number;
  validRows: number;
  errorRows: number;
  preview: ImportPreviewRow[] | PurchaseBillPreview | Record<string, unknown>[];
  errors?: unknown[];
  previewTruncated?: number;
  errorsTruncated?: number;
  columnMappings?: { source: string; target: string }[];
  voidedRows?: { sku?: string; name?: string }[];
  clarifications?: BillClarification[];
  committedAt?: string | null;
  createdAt?: string;
  supplier?: number | null;
  customer?: number | null;
  purchaseInvoice?: number | null;
  salesInvoice?: number | null;
  billTemplate?: number | null;
  failureReason?: string;
}

export interface PurchaseBillCommitResult {
  created: number;
  productsCreated: number;
  purchaseInvoiceId?: number;
  salesInvoiceId?: number;
  status: ImportJobStatus;
  errorRows: number;
}

export interface CompanyUser {
  id: number;
  user: number;
  email: string;
  fullName: string;
  phone?: string;
  role: Role;
  canManageInventory: boolean;
  canImport: boolean;
  canCancelDocuments?: boolean;
  canViewFinancialReports?: boolean;
  canExport?: boolean;
  canCreateSales?: boolean;
  canCreatePurchases?: boolean;
  canCreatePayments?: boolean;
  canPostJournals?: boolean;
  isActive: boolean;
  inviteUrl?: string;
  inviteToken?: string;
}

export interface ReportRow {
  [key: string]: unknown;
}

export interface ReportResponse {
  rows: ReportRow[];
  totals?: Record<string, string | number>;
}

export interface AuthTokens {
  access: string;
  /** Optional: refresh is httpOnly cookie; body refresh is legacy/mock only. */
  refresh?: string;
}

export interface ApiEnvelope<T> {
  success?: boolean;
  data: T;
  meta?: Record<string, unknown>;
}

export interface Paginated<T> {
  results: T[];
  count: number;
  next?: string | null;
  previous?: string | null;
}

export type AlertSeverity = 'critical' | 'warning' | 'info' | string;

export interface BusinessAlert {
  id: number;
  code: string;
  severity: AlertSeverity;
  message: string;
  subjectKey?: string;
  payload?: Record<string, unknown>;
  status: string;
  snoozedUntil?: string | null;
  ctaPath?: string;
}

export interface DailyBusinessSummary {
  id: number;
  summaryDate: string;
  kpis: Record<string, string | number>;
  alertCodes: string[];
  narrative: string;
  promptVersion?: string;
}

export interface HealthFactor {
  key: string;
  label: string;
  score: number;
  weight: number;
  detail?: string;
}

export interface BusinessHealth {
  score: string | number;
  grade: string;
  factors: HealthFactor[];
  limitedData: boolean;
  asOf: string;
  salesCount?: number;
  mtdSales?: string | number;
  priorMonthSales?: string | number;
}

export interface BusinessHealthSnapshot {
  id: number;
  asOf: string;
  score: string | number;
  grade: string;
  factors: HealthFactor[];
  limitedData: boolean;
}

export interface CashflowPoint {
  date: string;
  inflow: string;
  outflow: string;
  net: string;
  cumulative: string;
  endingCash: string;
  low: string;
  high: string;
}

export interface CashflowForecast {
  horizonDays: number;
  mode: string;
  series: CashflowPoint[];
  meta: Record<string, unknown>;
  runId?: number;
  modelVersion?: string;
}

export interface GrowthHint {
  code: string;
  title: string;
  impactEstimate?: string | null;
  message: string;
  ctaPath: string;
  severity?: AlertSeverity;
}

export interface AssistantMessage {
  id: number;
  role: string;
  content: string;
  citations?: { path: string; label: string }[];
  proposedAction?: Record<string, unknown> | null;
  createdAt?: string;
}

export interface AssistantThread {
  id: number;
  title: string;
  createdAt?: string;
  messages?: AssistantMessage[];
}


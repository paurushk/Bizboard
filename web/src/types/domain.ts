export type Role = 'OWNER' | 'SALES_STAFF';

export type DocumentStatus = 'DRAFT' | 'COMPLETED' | 'CANCELLED' | 'RETURNED' | 'CONVERTED';

export type CustomerStatus = 'ACTIVE' | 'BLOCKED';
export type ProductStatus = 'ACTIVE' | 'INACTIVE';

export type InvoiceType = 'GST' | 'TAX' | 'RETAIL' | 'NON_GST';
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
  | 'PREVIEWED'
  | 'COMMITTED'
  | 'FAILED';
export type ImportKind =
  | 'CUSTOMERS'
  | 'SUPPLIERS'
  | 'PRODUCTS'
  | 'OPENING_STOCK'
  | 'PURCHASE_BILL';

export type RegistrationType = 'REGULAR' | 'COMPOSITION' | 'UNREGISTERED';
export type NegativeStockPolicy = 'BLOCK' | 'WARN';

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
  logo?: number | null;
  signature?: number | null;
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
  discountPercent?: string | number;
  gstRate?: string | number;
  hsnCode?: string;
  mrp?: string | number;
  unitName?: string;
  batchNo?: string;
  expDate?: string | null;
  mfgDate?: string | null;
  taxableAmount?: string | number;
  cgst?: string | number;
  sgst?: string | number;
  igst?: string | number;
  lineTotal?: string | number;
}

export interface DocumentTotals {
  subtotal: string | number;
  discountTotal: string | number;
  taxableTotal: string | number;
  cgstTotal: string | number;
  sgstTotal: string | number;
  igstTotal: string | number;
  roundOff: string | number;
  grandTotal: string | number;
}

export interface SalesInvoice extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  invoiceType: InvoiceType;
  customer: number;
  customerName?: string;
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

export interface PurchaseInvoice extends DocumentTotals {
  id: number;
  number?: string | null;
  status: DocumentStatus;
  purchaseType: PurchaseType;
  supplier: number;
  supplierName?: string;
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
}

export interface PaymentAllocation {
  id: number;
  receipt?: number | null;
  supplierPayment?: number | null;
  salesInvoice?: number | null;
  purchaseInvoice?: number | null;
  amount: string | number;
  createdAt?: string;
}

export interface StockBalance {
  id?: number;
  product: number;
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
}

export interface LedgerEntry {
  date: string;
  type: string;
  number?: string;
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
}

export interface PurchaseBillPreview {
  supplierName?: string;
  supplierGstin?: string;
  billNumber?: string;
  billDate?: string;
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
  committedAt?: string | null;
  createdAt?: string;
  supplier?: number | null;
  purchaseInvoice?: number | null;
  failureReason?: string;
}

export interface PurchaseBillCommitResult {
  created: number;
  productsCreated: number;
  purchaseInvoiceId: number;
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
  isActive: boolean;
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
  refresh: string;
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

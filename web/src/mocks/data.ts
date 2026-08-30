import type {
  Company,
  CompanyUser,
  Customer,
  CustomerReceipt,
  DashboardKpis,
  Product,
  PurchaseInvoice,
  Quotation,
  SalesInvoice,
  SearchResult,
  StockBalance,
  Supplier,
  SupplierPayment,
  User,
} from '@/types/domain';

export const mockViewerUser: User = {
  id: 99,
  email: 'viewer@bizboard.local',
  fullName: 'Demo Viewer',
  role: 'VIEWER',
  companyId: 1,
  canManageInventory: false,
  canImport: false,
  canViewFinancialReports: false,
  canCreateSales: false,
  canCreatePurchases: false,
  canCreatePayments: false,
};

export const mockUser: User = {
  id: 1,
  email: 'owner@bizboard.local',
  fullName: 'Demo Owner',
  role: 'OWNER',
  companyId: 1,
  canManageInventory: true,
  canImport: true,
  canCancelDocuments: true,
  canViewFinancialReports: true,
  canExport: true,
};

export const mockSalesUser: User = {
  id: 2,
  email: 'sales@bizboard.local',
  fullName: 'Demo Sales',
  role: 'SALES_STAFF',
  companyId: 1,
  canManageInventory: false,
  canImport: false,
  canCancelDocuments: false,
  canViewFinancialReports: true,
  canExport: false,
};

export const mockUsers: CompanyUser[] = [
  {
    id: 1,
    user: 1,
    email: mockUser.email,
    fullName: mockUser.fullName,
    role: 'OWNER',
    canManageInventory: true,
    canImport: true,
    isActive: true,
  },
  {
    id: 2,
    user: 2,
    email: mockSalesUser.email,
    fullName: mockSalesUser.fullName,
    role: 'SALES_STAFF',
    canManageInventory: false,
    canImport: false,
    isActive: true,
  },
];

export const mockCompany: Company = {
  id: 1,
  name: 'Demo Mart',
  legalName: 'Demo Traders Pvt Ltd',
  address: '12 Market Road',
  city: 'Pune',
  state: 'Maharashtra',
  pincode: '411001',
  phone: '9876543210',
  email: 'hello@demomart.local',
  upiId: 'demomart@upi',
  bankName: 'Demo Bank',
  bankAccount: '1234567890',
  bankIfsc: 'DEMO0001234',
  gstin: '27AABCU9603R1ZM',
  registrationType: 'REGULAR',
  negativeStockPolicy: 'WARN',
  isGstRegistered: true,
  taxProfileConfirmedAt: '2026-01-01T00:00:00Z',
  onboardingStartedAt: '2026-01-01T00:00:00Z',
  onboarding: {
    status: 'COMPLETED',
    step: null,
    uiStep: null,
    dismissed: false,
    taxDone: true,
    shopDone: true,
    paymentsDone: true,
    catalogDone: true,
    activationDone: true,
    started: true,
  },
  itemCustomFieldDefs: [
    {
      key: 'brandForm',
      label: 'Brand form',
      type: 'list',
      active: true,
      options: ['Strip', 'Bottle', 'Tube'],
    },
    { key: 'color', label: 'Color', type: 'text', active: true },
    { key: 'brandCode', label: 'Brand code', type: 'text', active: true },
  ],
};

mockUser.company = mockCompany;
mockSalesUser.company = mockCompany;
mockViewerUser.company = mockCompany;

export const mockCustomers: Customer[] = [
  {
    id: 1,
    name: 'Rahul Stores',
    phone: '9000000001',
    status: 'ACTIVE',
    outstanding: 3500,
    gstin: '27AABCR1234A1Z5',
    state: 'Maharashtra',
  },
  {
    id: 2,
    name: 'Blocked Walk-in',
    phone: '9000000002',
    status: 'BLOCKED',
    outstanding: 0,
  },
];

export const mockSuppliers: Supplier[] = [
  {
    id: 1,
    name: 'Western Distributors',
    phone: '9111111111',
    gstin: '27AABCS9876B1Z2',
    outstanding: 12000,
    isActive: true,
    state: 'Maharashtra',
  },
];

export const mockProducts: Product[] = [
  {
    id: 1,
    name: 'Premium Tea 500g',
    sku: 'TEA-500',
    barcode: '8901234567890',
    hsnCode: '0902',
    unitName: 'PCS',
    sellingPrice: 250,
    purchasePrice: 180,
    gstRate: 5,
    reorderLevel: 10,
    status: 'ACTIVE',
    available: 40,
    customFields: { brandForm: 'Strip', color: 'Red', brandCode: 'TEA' },
  },
  {
    id: 2,
    name: 'Cooking Oil 1L',
    sku: 'OIL-1L',
    barcode: '8901234567891',
    hsnCode: '1507',
    unitName: 'PCS',
    sellingPrice: 180,
    purchasePrice: 140,
    gstRate: 5,
    reorderLevel: 20,
    status: 'ACTIVE',
    available: 15,
    customFields: { brandForm: 'Bottle', color: 'Gold', brandCode: 'OIL' },
  },
  {
    id: 3,
    name: 'Steel Bottle',
    sku: 'BTL-01',
    barcode: '8901234567892',
    hsnCode: '7323',
    unitName: 'PCS',
    sellingPrice: 499,
    purchasePrice: 320,
    gstRate: 18,
    reorderLevel: 5,
    status: 'ACTIVE',
    available: 3,
  },
];

const zeroTotals = {
  subtotal: 0,
  discountTotal: 0,
  taxableTotal: 0,
  cgstTotal: 0,
  sgstTotal: 0,
  igstTotal: 0,
  roundOff: 0,
  grandTotal: 5250,
};

export const mockInvoices: SalesInvoice[] = [
  {
    id: 1,
    number: 'INV-2026-0001',
    invoiceType: 'GST',
    status: 'COMPLETED',
    customer: 1,
    customerName: 'Rahul Stores',
    invoiceDate: '2026-07-18',
    items: [
      {
        id: 1,
        product: 1,
        productName: 'Premium Tea 500g',
        quantity: 10,
        unitPrice: 250,
        discountPercent: 0,
        gstRate: 5,
        taxableAmount: 2500,
        cgst: 62.5,
        sgst: 62.5,
        igst: 0,
        lineTotal: 2625,
      },
    ],
    ...zeroTotals,
    taxableTotal: 2500,
    cgstTotal: 62.5,
    sgstTotal: 62.5,
    grandTotal: 2625,
    pdfStatus: 'READY',
  },
];

export const mockQuotations: Quotation[] = [
  {
    id: 1,
    number: 'QUO-0001',
    status: 'DRAFT',
    invoiceType: 'GST',
    customer: 1,
    customerName: 'Rahul Stores',
    quotationDate: '2026-07-17',
    items: [],
    ...zeroTotals,
    grandTotal: 1000,
  },
];

export const mockPurchases: PurchaseInvoice[] = [
  {
    id: 1,
    number: 'PUR-2026-0001',
    status: 'COMPLETED',
    purchaseType: 'GST',
    supplier: 1,
    supplierName: 'Western Distributors',
    invoiceDate: '2026-07-15',
    items: [],
    ...zeroTotals,
    grandTotal: 15000,
    outstanding: 12000,
  },
];

export const mockReceipts: CustomerReceipt[] = [
  {
    id: 1,
    number: 'RCT-0001',
    customer: 1,
    customerName: 'Rahul Stores',
    amount: 2000,
    mode: 'UPI',
    receiptDate: '2026-07-18',
    allocated: 2000,
    unallocated: 0,
  },
];

export const mockSupplierPayments: SupplierPayment[] = [
  {
    id: 1,
    number: 'PAY-0001',
    supplier: 1,
    supplierName: 'Western Distributors',
    amount: 3000,
    mode: 'BANK',
    paymentDate: '2026-07-16',
    allocated: 3000,
    unallocated: 0,
  },
];

export const mockStock: StockBalance[] = mockProducts.map((p, i) => ({
  id: i + 1,
  product: p.id,
  productName: p.name,
  sku: p.sku,
  onHand: Number(p.available ?? 0),
  reserved: 0,
  available: Number(p.available ?? 0),
  reorderLevel: Number(p.reorderLevel),
  customFields: p.customFields,
}));

export const mockDashboard: DashboardKpis = {
  salesToday: { total: 2625, count: 1 },
  salesThisMonth: { total: 45000, count: 12 },
  purchasesThisMonth: { total: 28000, count: 4 },
  receivables: 12500,
  payables: 12000,
  lowStockCount: 1,
  productCount: 8,
  invoiceCount: 12,
};

export const mockSearchResults: SearchResult[] = [
  {
    id: 1,
    type: 'invoice',
    title: 'INV-2026-0001',
    subtitle: 'Rahul Stores',
    path: '/sales/history/1',
  },
  {
    id: 1,
    type: 'customer',
    title: 'Rahul Stores',
    path: '/sales/customers',
  },
  {
    id: 1,
    type: 'product',
    title: 'Premium Tea 500g',
    subtitle: 'TEA-500',
    path: '/inventory/products',
  },
];

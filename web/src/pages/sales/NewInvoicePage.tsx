import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type HTMLAttributes } from 'react';
import { flushSync } from 'react-dom';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Collapse from '@mui/material/Collapse';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TableCell from '@mui/material/TableCell';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  completeSalesInvoice,
  createProduct,
  createSalesInvoice,
  getCompany,
  getCustomer,
  getProduct,
  listCompanyGstins,
  getSalesInvoice,
  getSalesInvoiceNumberSeries,
  listCustomersPage,
  listCollectionRisk,
  listBatches,
  listCostCenters,
  listPriceLists,
  listProductsPage,
  listSalesInvoicesPage,
  listStock,
  listWarehouses,
  searchProducts,
  updateCustomer,
  updateSalesInvoice,
  uploadFile,
  downloadInvoicePdf,
  downloadInvoicePreviewPdf,
} from '@/api/resources';
import { getErrorMessage, isNetworkError, userGestureIdempotencyKey } from '@/api/client';
import { classifyCompleteFailure, runInvoiceCompleteJourney, trackShopFloor } from '@/lib/telemetry';
import { useAuth } from '@/auth/AuthContext';
import {
  enqueueDraft,
  listDrafts,
  OUTBOX_WARNING_DISMISS_KEY,
} from '@/offline/invoiceDraftCache';
import { isValidHsnSac } from '@/utils/gst';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { exactBarcodeOrSku, filterProductsForPicker } from '@/utils/productPick';
import { canAccessPos, canCreatePayments, canCreateSales, canImport, canViewFinancialReports } from '@/utils/permissions';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { DocumentTaxSummary } from '@/components/DocumentTaxSummary';
import { t, useLocale } from '@/i18n';
import { preferredInvoiceType, companyStepIncompleteNeedsGst, resolvedSeriesGstin } from '@/onboarding/taxHints';
import { jsonSnapshot, useEditorBaseline } from '@/pages/sales/invoice/editorDirty';
import { creditLineView } from '@/pages/sales/creditLine';
import { decidePlaceOfSupply, invoiceTypeChipKey, showGodownSelect, statutoryChipIds, statutoryChipLabel } from '@/cognitive/loadHelpers';
import { lineSkipsStockGate } from '@/pages/pos/posRules';
import { chooseInvoiceDefaults, inferInvoiceTypeFromParty } from '@/pages/sales/invoiceDefaults';
import { readDraft, removeDraft as removeDeviceDraft, writeDraft } from '@/lib/deviceDraft';
import {
  firstCompleteDisabledReason,
  previewAllowsComplete,
  serialCountMatchesQty,
} from '@/completeGates/completeBlockers';
import type { InvoiceType, PaymentMode, PriceMode, Product, SalesInvoice } from '@/types/domain';
import { creditLimitExceeded as billExceedsCreditLimit } from '@/utils/creditExposure';
import { amountInWords } from '@/utils/amountInWords';
import { formatMoney, roundMoney, toNumber } from '@/utils/money';
import { isCollectionHoldStatus } from '@/utils/collectionHold';
import { hasLiveIrn } from '@/utils/einvoiceLock';
import { CreditHoldChip } from '@/components/CreditHoldChip';
import { resolveListUnitPrice } from '@/utils/priceList';
import {
  addDaysIso,
  calculateInvoiceTotals,
  calculateLineTax,
  extractExclusiveFromInclusiveLine,
  isIntraState,
  type InvoiceDiscountMode,
} from '@/utils/tax';

import {
  CompactField,
  DocumentEditorShell,
  DraftLineTable,
  formatSerialNumbersText,
  NumericField,
  parseSerialInput,
  parseSerialNumbersText,
  primarySaveAction,
  recomputeLine,
  todayIso,
  useBillingSaveFeedback,
  useDebouncedValue,
  type DraftLine,
} from '@/components/billing';
import { InvoicePartyPanel } from '@/pages/sales/invoice/InvoicePartyPanel';
import { FieldHelpTip } from '@/contextHelp';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import {
  InvoiceQuickSettingsDialog,
  SHOW_PURCHASE_PRICE_KEY,
} from '@/components/InvoiceQuickSettingsDialog';
import { activeCustomFieldDefs } from '@/pages/inventory/itemCustomFieldDefaults';
import { makeInvoiceLine } from '@/pages/sales/invoice/makeInvoiceLine';
import { ProfitDetailsDialog } from '@/components/ProfitDetailsDialog';
import { ShareInvoiceDialog } from '@/components/ShareInvoiceDialog';
import { completeWithConfirms } from '@/utils/completeWithConfirms';

const COL_PREFS_KEY = 'bizboard.billing.batchCols';

/** Thrown to stop a save while the owner answers the amend dialog. Not an error to show. */
class AmendPending extends Error {}

async function completeInvoiceWithConfirms(
  id: number,
  base: {
    confirmSalesRcm?: boolean;
    amountReceived?: number;
    paymentMode?: PaymentMode;
    chequeNumber?: string;
    chequeBankName?: string;
    chequeDate?: string;
    chequeImage?: number | null;
    idempotencyKey?: string;
  },
): Promise<SalesInvoice> {
  // F2-035: delegate to the shared completeWithConfirms loop instead of a
  // hand-nested try/catch that only recovered one confirm code per level —
  // GSTIN_TOTAL_CHANGED then place_of_supply_unresolved (or a third code) at
  // the second retry used to rethrow instead of prompting.
  return runInvoiceCompleteJourney(() =>
    completeWithConfirms((extra) => completeSalesInvoice(id, { ...base, ...extra })),
  );
}

export function NewInvoicePage() {
  useLocale();
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const location = useLocation();
  const fromBillUpload = Boolean(
    (location.state as { fromBillUpload?: boolean } | null)?.fromBillUpload,
  );
  const qc = useQueryClient();
  const { user, login } = useAuth();
  const canSeeMargin = canViewFinancialReports(user);
  const canTakePayment = canCreatePayments(user);
  const isOwner = user?.role === 'OWNER';
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const barcodeRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [skipLeaveGuard, setSkipLeaveGuard] = useState(false);

  const [lines, setLines] = useState<DraftLine[]>([]);
  const [deviceDraft, setDeviceDraft] = useState<{
    lines: DraftLine[];
    customerId: number | '';
  } | null>(null);
  const [priceDrift, setPriceDrift] = useState<{
    lines: DraftLine[];
    updated: DraftLine[];
    drifts: { name: string; from: string; to: string }[];
    customerId: number | '';
  } | null>(null);
  const [reauthEmail, setReauthEmail] = useState('');
  const [reauthPassword, setReauthPassword] = useState('');
  const completeKeyRef = useRef<string | null>(null);
  // Signature of the body the key was minted for. A changed body needs a new key.
  const completeSigRef = useRef('');
  const amendConfirmedRef = useRef(false);
  const [amendConfirm, setAmendConfirm] = useState<'draft' | 'complete' | 'complete_new' | 'draft_new' | 'save' | null>(null);
  const lostCompleteRef = useRef(false);
  const [reauthOpen, setReauthOpen] = useState(false);
  const [profitOpen, setProfitOpen] = useState(false);
  const [savedForShare, setSavedForShare] = useState<{ id: number; number: string } | null>(null);
  const [shareAfterSave, setShareAfterSave] = useState(false);
  const [autoPrint, setAutoPrint] = useState(() => {
    try {
      return localStorage.getItem('bizboard.invoiceAutoPrint') === '1';
    } catch {
      return false;
    }
  });
  const [previewMode, setPreviewMode] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [draftChecked, setDraftChecked] = useState(false);
  const [productQuery, setProductQuery] = useState('');
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const debouncedProductQuery = useDebouncedValue(productQuery, 300);
  const {
    message,
    error,
    errorSource,
    setError,
    clearFeedback,
    flashSaveAndNew,
    flashError,
    flashWarning,
  } = useBillingSaveFeedback();
  useEffect(() => {
    const flashed = (location.state as { message?: unknown } | null)?.message;
    if (typeof flashed === 'string' && flashed.trim()) setError(flashed);
  }, [location.state, setError]);
  const [editingStatus, setEditingStatus] = useState<SalesInvoice['status'] | null>(null);
  const [loadedEdit, setLoadedEdit] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [outboxBanner, setOutboxBanner] = useState<string | null>(null);
  const [offline, setOffline] = useState(
    typeof navigator !== 'undefined' ? !navigator.onLine : false,
  );
  const [hasOutboxItems, setHasOutboxItems] = useState(false);
  const [hideOutboxWarn, setHideOutboxWarn] = useState(
    () =>
      typeof localStorage !== 'undefined' &&
      localStorage.getItem(OUTBOX_WARNING_DISMISS_KEY) === '1',
  );

  const [customerId, setCustomerId] = useState<number | ''>('');
  const [manualName, setManualName] = useState('');
  const [customerQuery, setCustomerQuery] = useState('');
  const debouncedCustomerQuery = useDebouncedValue(customerQuery, 300);
  const [warehouseId, setWarehouseId] = useState<number | ''>('');
  const [companyGstinId, setCompanyGstinId] = useState<number | ''>('');
  const [costCenterId, setCostCenterId] = useState<number | ''>('');
  const [invoiceType, setInvoiceType] = useState<InvoiceType>('NON_GST');
  const [invoiceTypeTouched, setInvoiceTypeTouched] = useState(false);
  const [showInvoiceType, setShowInvoiceType] = useState(false);
  const [posPick, setPosPick] = useState<'gstin' | 'address' | ''>('');
  const [supplyType, setSupplyType] = useState<import('@/types/domain').SupplyType>('B2B');
  const [isReverseCharge, setIsReverseCharge] = useState(false);
  const [confirmSalesRcm, setConfirmSalesRcm] = useState(false);
  const [ecommerceOperatorGstin, setEcommerceOperatorGstin] = useState('');
  const [priceMode, setPriceMode] = useState<PriceMode>('EXCLUSIVE');
  const [invoiceDate, setInvoiceDate] = useState(todayIso());
  const [paymentTermsDays, setPaymentTermsDays] = useState(30);
  const [dueDate, setDueDate] = useState(() => addDaysIso(todayIso(), 30));
  // F2-008: once the user (or a loaded invoice) sets an explicit due date, stop
  // recomputing it from invoiceDate + terms.
  const [dueDateTouched, setDueDateTouched] = useState(false);
  const [showPaymentTerms, setShowPaymentTerms] = useState(true);
  const [showAdvancedTax, setShowAdvancedTax] = useState(false);

  // BUG-514: prefix/nextNumber are read-only display-only previews (the
  // fields are permanently disabled below) — the series-editing machinery
  // that used to accompany them was dead code, since it could never be
  // triggered through this UI.
  const [prefix, setPrefix] = useState('INV');
  const [nextNumber, setNextNumber] = useState(1);

  const [notes, setNotes] = useState('');
  const [termsText, setTermsText] = useState('');
  const [showNotes, setShowNotes] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  const [showBank, setShowBank] = useState(false);
  const [showQr, setShowQr] = useState(false);
  const [showTcs, setShowTcs] = useState(false);
  const [tcsSection, setTcsSection] = useState('');
  const [tcsRate, setTcsRate] = useState(0);
  const [tcsAmount, setTcsAmount] = useState(0);
  const [tcsAmountManual, setTcsAmountManual] = useState(false);

  const [additionalCharges, setAdditionalCharges] = useState(0);
  const [chargesHsn, setChargesHsn] = useState('');
  const [chargesGstRate, setChargesGstRate] = useState(0);
  const [invoiceDiscount, setInvoiceDiscount] = useState(0);
  const [invoiceDiscountMode, setInvoiceDiscountMode] = useState<InvoiceDiscountMode>('AFTER_TAX');
  const [autoRoundOff, setAutoRoundOff] = useState(true);
  const [amountReceived, setAmountReceived] = useState(0);
  const editorSnapshot = jsonSnapshot({
    manualName,
    additionalCharges,
    chargesHsn,
    chargesGstRate,
    invoiceDiscount,
    amountReceived,
    notes,
    lines,
    customerId,
  });
  const { dirty: editorDirty, rearm: rearmEditorBaseline } = useEditorBaseline(
    editorSnapshot,
    !isEdit || loadedEdit,
  );
  const [paymentMode, setPaymentMode] = useState<PaymentMode>('CASH');
  const [cheque, setCheque] = useState<ChequePaymentValues>({ chequeNumber: '', chequeBankName: '', chequeDate: '' });
  const [invoiceCustomFields, setInvoiceCustomFields] = useState<Record<string, string>>({});
  const [markFullyPaid, setMarkFullyPaid] = useState(false);

  const [showBatchCols, setShowBatchCols] = useState(() => {
    try {
      return localStorage.getItem(COL_PREFS_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showPurchasePrice, setShowPurchasePrice] = useState(() => {
    try {
      return localStorage.getItem(SHOW_PURCHASE_PRICE_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [itemDialogOpen, setItemDialogOpen] = useState(false);
  const [itemDialogError, setItemDialogError] = useState<string | null>(null);
  const [itemDialogErrorSource, setItemDialogErrorSource] = useState<unknown>(null);
  const [itemForm, setItemForm] = useState({
    name: '',
    sku: '',
    unitName: 'PCS',
    hsnCode: '',
    sellingPrice: '',
    purchasePrice: '',
    mrp: '',
    gstRate: '18',
  });
  const [signatureUrl, setSignatureUrl] = useState<string | null>(null);
  const [signatureId, setSignatureId] = useState<number | null>(null);

  useEffect(() => {
    const onReauth = () => setReauthOpen(true);
    window.addEventListener('bizboard:invoice-reauth', onReauth);
    return () => window.removeEventListener('bizboard:invoice-reauth', onReauth);
  }, []);

  useEffect(() => {
    const onOnline = () => setOffline(false);
    const onOffline = () => setOffline(true);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    if (!companyId || !userId) return;
    void listDrafts(companyId, userId).then((drafts) => {
      setHasOutboxItems(drafts.some((d) => d.kind === 'invoice' || d.kind === 'pos'));
    });
  }, [companyId, userId, outboxBanner]);

  if (!isEdit && companyId && userId && !draftChecked) {
    const read = readDraft<{ lines: DraftLine[]; customerId: number | '' }>(companyId, userId, 'sales-invoice');
    if (read.ok && read.payload.lines?.length) {
      setDeviceDraft(read.payload);
    }
    setDraftChecked(true);
  }

  useEffect(() => {
    if (!deviceDraft) return;
    let live = true;
    queueMicrotask(() => {
      if (live) trackShopFloor('draft_restored', { feature: 'form' });
    });
    return () => {
      live = false;
    };
  }, [deviceDraft]);

  useEffect(() => {
    if (!draftChecked || isEdit || !companyId || !userId || deviceDraft) return;
    if (lines.length === 0) {
      removeDeviceDraft(companyId, userId, 'sales-invoice');
      return;
    }
    writeDraft(companyId, userId, 'sales-invoice', {
      // Cost is not part of the bill. Keep it out of browser storage.
      lines: lines.map((line) => ({ ...line, purchasePrice: undefined })),
      customerId,
    });
  }, [draftChecked, isEdit, companyId, userId, deviceDraft, lines, customerId]);
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const recentBills = useQuery({
    queryKey: ['sales-invoices', 'defaults'],
    queryFn: () => listSalesInvoicesPage({ status: 'COMPLETED', pageSize: 5 }),
    enabled: !isEdit,
  });
  const [defaultsApplied, setDefaultsApplied] = useState(false);
  if (!isEdit && !invoiceTypeTouched && company.data && !recentBills.isLoading && !defaultsApplied) {
    const choice = chooseInvoiceDefaults({
      invoices: (recentBills.data?.results ?? []).map((row) => ({
        invoiceType: row.invoiceType,
        priceMode: row.priceMode,
        customerName: row.customerName,
      })),
      registrationType: company.data.registrationType,
      companyPriceMode: company.data.priceMode,
    });
    setDefaultsApplied(true);
    setInvoiceType(choice.invoiceType);
    setPriceMode(choice.priceMode);
    setPaymentTermsDays(choice.paymentTermsDays);
  }
  const customers = useQuery({
    queryKey: ['customers-search', debouncedCustomerQuery],
    queryFn: () => listCustomersPage({ q: debouncedCustomerQuery.trim() || undefined, pageSize: 50 }),
  });
  const selectedCustomerQuery = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: Boolean(customerId),
  });
  const collectionRisk = useQuery({
    queryKey: ['collection-risk'],
    queryFn: listCollectionRisk,
    retry: false,
  });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const companyGstins = useQuery({ queryKey: ['company-gstins'], queryFn: listCompanyGstins });
  const costCenters = useQuery({
    queryKey: ['cost-centers'],
    queryFn: listCostCenters,
    enabled: Boolean(company.data?.accountingEnabled),
  });
  const priceLists = useQuery({ queryKey: ['price-lists'], queryFn: listPriceLists });
  const batches = useQuery({ queryKey: ['batches'], queryFn: () => listBatches() });
  const series = useQuery({
    queryKey: ['sales-invoice-number-series'],
    queryFn: getSalesInvoiceNumberSeries,
    enabled: !isEdit,
  });
  const existingInvoice = useQuery({
    queryKey: ['sales-invoice', editId],
    queryFn: () => getSalesInvoice(editId as number),
    enabled: isEdit,
  });
  const productCatalog = useQuery({
    queryKey: ['product-picker', cfFilters],
    queryFn: () => listProductsPage({ page: 1, pageSize: 50, cf: cfFilters }),
  });
  const products = useQuery({
    queryKey: ['product-search', debouncedProductQuery, cfFilters],
    queryFn: () => searchProducts(debouncedProductQuery, { cf: cfFilters }),
    enabled: debouncedProductQuery.length >= 1,
  });
  const stockBalances = useQuery({
    queryKey: ['stock'],
    queryFn: () => listStock(),
    staleTime: 60_000,
  });
  const availableByProduct = useMemo(() => {
    // F2-009: the BLOCK gate must compare against the SELECTED warehouse, not
    // the company-wide total — stock sitting in another godown doesn't help the
    // line being sold from `warehouseId` (and the backend re-checks per-godown).
    const wh = warehouseId ? Number(warehouseId) : null;
    const map = new Map<number, number>();
    for (const s of stockBalances.data ?? []) {
      if (wh != null && Number(s.warehouse) !== wh) continue;
      const id = Number(s.product);
      map.set(id, (map.get(id) ?? 0) + toNumber(s.available));
    }
    return map;
  }, [stockBalances.data, warehouseId]);
  const stockShortfalls = useMemo(() => {
    if (company.data?.negativeStockPolicy !== 'BLOCK') return [];
    const needed = new Map<number, { name: string; qty: number }>();
    for (const l of lines) {
      if (lineSkipsStockGate(l)) continue;
      const prev = needed.get(l.product);
      needed.set(l.product, {
        name: l.productName,
        qty: (prev?.qty ?? 0) + toNumber(l.quantity),
      });
    }
    const out: { name: string; required: number; available: number }[] = [];
    for (const [id, row] of needed) {
      const avail = availableByProduct.get(id) ?? 0;
      if (row.qty > avail + 1e-9) {
        out.push({ name: row.name, required: row.qty, available: avail });
      }
    }
    return out;
  }, [lines, availableByProduct, company.data?.negativeStockPolicy]);

  const [appliedSeriesKey, setAppliedSeriesKey] = useState('');
  if (!isEdit && series.data) {
    const seriesKey = `${series.data.prefix}|${series.data.nextNumber}`;
    if (appliedSeriesKey !== seriesKey) {
      setAppliedSeriesKey(seriesKey);
      setPrefix(series.data.prefix);
      setNextNumber(series.data.nextNumber);
    }
  }

  const [seenEditId, setSeenEditId] = useState(editId);
  if (seenEditId !== editId) {
    setSeenEditId(editId);
    setLoadedEdit(false);
    clearFeedback();
  }

  useEffect(() => {
    if (!existingInvoice.data || loadedEdit) return;
    let cancelled = false;
    queueMicrotask(() => {
    if (cancelled || !existingInvoice.data) return;
    const inv = existingInvoice.data;
    if (inv.status === 'CANCELLED' || inv.status === 'RETURNED') {
      setError(inv.status === 'RETURNED' ? t('billing.cannotEditReturned') : t('billing.cannotEditCancelled'));
      setLoadedEdit(true);
      return;
    }
    setEditingStatus(inv.status);
    setCustomerId(inv.customer);
    setWarehouseId(inv.warehouse ?? '');
    setCompanyGstinId((inv as { companyGstin?: number | null }).companyGstin ?? '');
    setCostCenterId(inv.costCenter ?? '');
    setInvoiceType(inv.invoiceType);
    setSupplyType((inv.supplyType as import('@/types/domain').SupplyType) || 'B2B');
    setIsReverseCharge(Boolean(inv.isReverseCharge));
    setConfirmSalesRcm(false);
    setEcommerceOperatorGstin(inv.ecommerceOperatorGstin ?? '');
    setPriceMode((inv.priceMode as PriceMode) || 'EXCLUSIVE');
    setInvoiceDate(inv.invoiceDate);
    setPaymentTermsDays(inv.paymentTermsDays ?? 0);
    setDueDate(inv.dueDate ?? addDaysIso(inv.invoiceDate, inv.paymentTermsDays ?? 0));
    // A saved invoice carries an authoritative due date — don't let the
    // invoiceDate/terms effect overwrite it on edit-hydration (F2-008).
    setDueDateTouched(Boolean(inv.dueDate));
    setShowPaymentTerms(Boolean(inv.dueDate || inv.paymentTermsDays));
    setNotes(inv.notes ?? '');
    setShowNotes(Boolean(inv.notes));
    setTermsText(inv.termsText ?? '');
    setShowTerms(Boolean(inv.includeTerms || inv.termsText));
    setShowBank(Boolean(inv.includeBankDetails));
    setShowQr(Boolean(inv.includePaymentQr));
    setAdditionalCharges(toNumber(inv.additionalCharges));
    setChargesHsn(inv.chargesHsn ?? '');
    setChargesGstRate(toNumber(inv.chargesGstRate));
    setInvoiceDiscount(toNumber(inv.invoiceDiscount));
    setInvoiceDiscountMode((inv.invoiceDiscountMode as InvoiceDiscountMode) || 'AFTER_TAX');
    setInvoiceCustomFields((inv.customFields as Record<string, string> | undefined) ?? {});
    setTcsSection(inv.tcsSection ?? '');
    setTcsRate(toNumber(inv.tcsRate));
    setTcsAmount(toNumber(inv.tcsAmount));
    setTcsAmountManual(Boolean(inv.tcsAmountManual));
    setShowTcs(Boolean(inv.tcsSection || toNumber(inv.tcsAmount)));
    setAutoRoundOff(inv.autoRoundOff ?? true);
    setSignatureId(inv.signature ?? null);
    if (inv.number?.trim()) {
      const raw = inv.number.trim();
      const dash = raw.lastIndexOf('-');
      const slash = raw.lastIndexOf('/');
      const cut = Math.max(dash, slash);
      if (cut > 0) {
        setPrefix(raw.slice(0, cut));
        setNextNumber(Number(raw.slice(cut + 1)) || 1);
      } else {
        setPrefix('');
        setNextNumber(Number(raw.replace(/\D/g, '')) || 1);
      }
    }
    const companyState = company.data?.gstin || company.data?.state || '';
    const party = selectedCustomerQuery.data?.id === inv.customer ? selectedCustomerQuery.data : undefined;
    const partyState = party?.gstin || party?.state || '';
    const mapped: DraftLine[] = (inv.items ?? []).map((item, idx) => {
      const qty = toNumber(item.quantity);
      const inclusiveMode = (inv.priceMode as PriceMode) === 'INCLUSIVE';
      const unitPrice = inclusiveMode
        ? toNumber(item.unitPriceInclusive ?? item.unitPrice)
        : toNumber(item.unitPrice);
      const discountPercent = toNumber(item.discountPercent);
      const gstRate = toNumber(item.gstRate);
      const cessRate = toNumber(item.cessRate);
      const effectiveUnit =
        inclusiveMode && gstRate > 0
          ? extractExclusiveFromInclusiveLine({
              quantity: qty,
              unitPriceInclusive: unitPrice,
              discountPercent,
              gstRate,
              cessRate,
            }).exclusiveUnitPrice
          : unitPrice;
      const tax = calculateLineTax({
        quantity: qty,
        unitPrice: effectiveUnit,
        discountPercent: inclusiveMode ? 0 : discountPercent,
        gstRate,
        cessRate,
        intraState: isIntraState(companyState, partyState, {
          assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty,
        }),
      });
      return {
        key: `edit-${item.id ?? idx}-${item.product}`,
        lineId: item.id,
        product: item.product,
        productName: item.productName ?? item.description ?? `Product #${item.product}`,
        description: item.description && item.description !== item.productName ? item.description : '',
        sku: '',
        hsnCode: item.hsnCode ?? '',
        unitName: item.unitName ?? 'PCS',
        baseUnitName: (products.data ?? []).find((p) => p.id === item.product)?.unitName ?? 'PCS',
        alternateUnitName: (products.data ?? []).find((p) => p.id === item.product)?.alternateUnitName,
        conversionRate: toNumber((products.data ?? []).find((p) => p.id === item.product)?.conversionRate) || 1,
        batchNo: item.batchNo ?? '',
        batch: item.batch ?? null,
        trackBatch: Boolean(
          (products.data ?? []).find((p) => p.id === item.product)?.trackBatch ?? item.batch,
        ),
        trackSerial: Boolean(
          (products.data ?? []).find((p) => p.id === item.product)?.trackSerial
            ?? (item as { serialNumbers?: string[] }).serialNumbers?.length,
        ),
        productType: (products.data ?? []).find((p) => p.id === item.product)?.productType,
        trackInventory: (products.data ?? []).find((p) => p.id === item.product)?.trackInventory,
        purchasePrice: toNumber((products.data ?? []).find((p) => p.id === item.product)?.purchasePrice),
        serialNumbersText: formatSerialNumbersText((item as { serialNumbers?: string[] }).serialNumbers),
        expDate: item.expDate ?? '',
        mfgDate: item.mfgDate ?? '',
        mrp: toNumber(item.mrp),
        quantity: qty,
        unitPrice,
        gstRate,
        cessRate,
        supplyNature: item.supplyNature ?? 'TAXABLE',
        ...tax,
      };
    });
    setLines(mapped);
    setLoadedEdit(true);
    });
    return () => {
      cancelled = true;
    };
  }, [
    existingInvoice.data,
    loadedEdit,
    company.data,
    selectedCustomerQuery.data,
    products.data,
    setError,
  ]);

  if (!isEdit && !warehouseId && warehouses.data) {
    const defaultWarehouse = warehouses.data.find((warehouse) => warehouse.isDefault);
    if (defaultWarehouse) setWarehouseId(defaultWarehouse.id);
  }
  const [termsSeeded, setTermsSeeded] = useState(false);
  if (!isEdit && !termsSeeded && company.data) {
    setTermsSeeded(true);
    if (!termsText && company.data.invoiceTerms) setTermsText(company.data.invoiceTerms);
  }
  const [seenCompanyForSignature, setSeenCompanyForSignature] = useState<typeof company.data>();
  if (company.data && company.data !== seenCompanyForSignature) {
    const firstLoad = seenCompanyForSignature == null;
    setSeenCompanyForSignature(company.data);
    if (firstLoad && company.data.signature) setSignatureId(company.data.signature);
  }
  if (!dueDateTouched) {
    const nextDue = addDaysIso(invoiceDate, paymentTermsDays || 0);
    if (dueDate !== nextDue) setDueDate(nextDue);
  }

  useEffect(() => {
    try {
      localStorage.setItem(COL_PREFS_KEY, showBatchCols ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [showBatchCols]);

  const selectedCustomer =
    selectedCustomerQuery.data
    ?? (customers.data?.results ?? []).find((c) => c.id === Number(customerId));
  // The type follows the party until the user picks one. Adjusting state while
  // rendering (guarded so it converges) avoids an extra render from an effect.
  const inferredInvoiceType =
    !isEdit && !invoiceTypeTouched && company.data && selectedCustomer
      ? inferInvoiceTypeFromParty({
          registrationType: company.data.registrationType,
          customerGstin: selectedCustomer.gstin,
        })
      : null;
  if (inferredInvoiceType !== null && inferredInvoiceType !== invoiceType) {
    setInvoiceType(inferredInvoiceType);
  }
  // Plain values, not the decision object, so the memoised totals below depend on primitives only.
  const {
    ask: posAsk,
    reason: posReason,
    addressCode: posAddressCode,
    gstinCode: posGstinCode,
  } = decidePlaceOfSupply(selectedCustomer?.gstin, selectedCustomer?.state) as {
    ask: boolean;
    reason?: string;
    addressCode?: string;
    gstinCode?: string;
  };
  const posConflict = posAsk && posReason === 'conflict';
  const partyPlace = posConflict
    ? posPick === 'address'
      ? posAddressCode
      : posPick === 'gstin'
        ? posGstinCode
        : undefined
    : selectedCustomer?.gstin || selectedCustomer?.state;
  const companyPlace = company.data?.gstin || company.data?.state;
  const assumeLocalForBlank = !!company.data?.assumeLocalStateForBlankParty;
  const intraState = useMemo(
    () => isIntraState(companyPlace, partyPlace, { assumeLocalStateForBlankParty: assumeLocalForBlank }),
    [companyPlace, partyPlace, assumeLocalForBlank],
  );

  const lineTaxes = useMemo(
    () =>
      lines.map((l) => {
        const nature = (l.supplyNature ?? 'TAXABLE').toUpperCase();
        const gstRate =
          invoiceType === 'NON_GST' ||
          supplyType === 'EXPWOP' ||
          supplyType === 'SEZWOP' ||
          nature !== 'TAXABLE'
            ? 0
            : l.gstRate;
        let unitPrice = l.unitPrice;
        if (priceMode === 'INCLUSIVE' && gstRate > 0) {
          unitPrice = extractExclusiveFromInclusiveLine({
            quantity: l.quantity,
            unitPriceInclusive: l.unitPrice,
            discountPercent: l.discountPercent,
            gstRate,
            cessRate: invoiceType === 'NON_GST' ? 0 : l.cessRate ?? 0,
          }).exclusiveUnitPrice;
          return calculateLineTax({
            quantity: l.quantity,
            unitPrice,
            discountPercent: 0,
            gstRate,
            cessRate: invoiceType === 'NON_GST' ? 0 : l.cessRate ?? 0,
            intraState,
          });
        }
        return calculateLineTax({
          quantity: l.quantity,
          unitPrice,
          discountPercent: l.discountPercent,
          gstRate,
          cessRate: invoiceType === 'NON_GST' ? 0 : l.cessRate ?? 0,
          intraState,
        });
      }),
    [lines, intraState, invoiceType, priceMode, supplyType],
  );

  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((l, i) => ({
          ...l,
          gstRate:
            invoiceType === 'NON_GST' ||
            supplyType === 'EXPWOP' ||
            supplyType === 'SEZWOP' ||
            (lines[i]?.supplyNature ?? 'TAXABLE') !== 'TAXABLE'
              ? 0
              : lines[i]?.gstRate ?? 0,
          cessRate:
            invoiceType === 'NON_GST' || supplyType === 'EXPWOP' || supplyType === 'SEZWOP'
              ? 0
              : lines[i]?.cessRate ?? 0,
          // R5-002: on inclusive pricing the exclusive line gross would make the
          // on-screen Subtotal disagree with the printed total — feed the
          // inclusive gross so it reconciles.
          inclusiveGross:
            priceMode === 'INCLUSIVE'
              ? roundMoney((lines[i]?.quantity ?? 0) * (lines[i]?.unitPrice ?? 0))
              : undefined,
          intraState,
        })),
        {
          additionalCharges,
          chargesHsn,
          chargesGstRate,
          invoiceDiscount,
          applyRoundOff: autoRoundOff,
          invoiceDiscountMode,
          intraState,
        },
      ),
    [lineTaxes, lines, additionalCharges, chargesHsn, chargesGstRate, invoiceDiscount, autoRoundOff, invoiceDiscountMode, intraState, invoiceType, supplyType, priceMode],
  );

  const posKnown =
    invoiceType === 'NON_GST' ||
    !company.data?.isGstRegistered ||
    company.data?.assumeLocalStateForBlankParty ||
    !posAsk ||
    (posReason === 'conflict' && posPick !== '');

  // R5-001: the backend blocks an AFTER_TAX invoice discount on B2B GST
  // invoices — keep the form in sync so the preview total matches Complete.
  const blockAfterTaxDiscount =
    invoiceType !== 'NON_GST' && Boolean((selectedCustomer?.gstin || '').trim());
  if (blockAfterTaxDiscount && invoiceDiscountMode === 'AFTER_TAX') {
    setInvoiceDiscountMode('BEFORE_TAX');
  }

  const alreadyPostedOnThisBill =
    editingStatus === 'COMPLETED'
      ? toNumber(existingInvoice.data?.balance ?? existingInvoice.data?.grandTotal ?? 0)
      : 0;
  const ledgerExposure =
    selectedCustomer?.creditExposure != null
      ? toNumber(selectedCustomer.creditExposure)
      : toNumber(selectedCustomer?.outstanding ?? 0);
  const projectedCreditBase = Math.max(0, ledgerExposure - alreadyPostedOnThisBill);
  const creditLimitExceeded = billExceedsCreditLimit({
    limit: toNumber(selectedCustomer?.creditLimit),
    outstanding: ledgerExposure,
    draftTotal: totals.grandTotal,
    alreadyPosted: alreadyPostedOnThisBill,
  });
  const creditLimitBanner = useMemo(() => {
    if (!selectedCustomer) return null;
    const limit = toNumber(selectedCustomer.creditLimit);
    if (limit <= 0) return null;
    const view = creditLineView({
      limit,
      outstanding: projectedCreditBase,
      billTotal: totals.grandTotal,
    });
    if (!view) return null;
    return (
      <Alert severity={view.severity}>
        {t('phase1.creditLine', {
          outstanding: formatMoney(view.outstanding),
          limit: formatMoney(view.limit),
          available: formatMoney(view.available),
        })}
      </Alert>
    );
  }, [selectedCustomer, totals.grandTotal, projectedCreditBase]);

  const creditHold = Boolean(
    customerId &&
      isCollectionHoldStatus(
        (collectionRisk.data ?? []).find((r) => r.customerId === Number(customerId))?.status,
      ),
  );
  const collectionHoldBanner = useMemo(() => {
    if (!creditHold) return null;
    return (
      <Alert severity="error">
        <CreditHoldChip /> {t('phase1.creditHoldBanner')}
      </Alert>
    );
  }, [creditHold]);

  const resetForm = () => {
    // BUG-500 / P0-311: do NOT call clearFeedback here — Save & New sets the
    // success flash then resets fields in the same tick; wiping feedback would
    //     batch-erase the message before paint. Use useBillingSaveFeedback.
    rearmEditorBaseline();
    completeKeyRef.current = null;
    completeSigRef.current = '';
    lostCompleteRef.current = false;
    setLines([]);
    setManualName('');
    setSkipLeaveGuard(false);
    if (companyId && userId) removeDeviceDraft(companyId, userId, 'sales-invoice');
    setCustomerId('');
    setWarehouseId(warehouses.data?.find((warehouse) => warehouse.isDefault)?.id ?? '');
    setCostCenterId('');
    setInvoiceType(preferredInvoiceType(company.data?.registrationType));
    setInvoiceTypeTouched(false);
    setPriceMode('EXCLUSIVE');
    setInvoiceDate(todayIso());
    setPaymentTermsDays(30);
    setNotes('');
    setShowNotes(false);
    setShowTerms(false);
    setShowBank(false);
    setShowQr(false);
    setAdditionalCharges(0);
    setChargesHsn('');
    setChargesGstRate(0);
    setInvoiceDiscount(0);
    setInvoiceDiscountMode('AFTER_TAX');
    setAmountReceived(0);
    setMarkFullyPaid(false);
    setPaymentMode('CASH');
    // F2-005: reset every statutory field too — leaving these set carried
    // reverse-charge / TCS / e-commerce GSTIN / a non-default stamped GSTIN
    // onto the next, unrelated invoice (wrong GST filing).
    setCompanyGstinId('');
    setSupplyType('B2B');
    setIsReverseCharge(false);
    setConfirmSalesRcm(false);
    setEcommerceOperatorGstin('');
    setShowTcs(false);
    setTcsSection('');
    setTcsRate(0);
    setTcsAmount(0);
    void qc.invalidateQueries({ queryKey: ['sales-invoice-number-series'] });
    barcodeRef.current?.focus();
  };

  const buildPayload = useCallback(() => ({
    customer: Number(customerId),
    warehouse: warehouseId ? Number(warehouseId) : undefined,
    companyGstin: companyGstinId ? Number(companyGstinId) : undefined,
    costCenter: costCenterId ? Number(costCenterId) : undefined,
    invoiceType,
    supplyType,
    isReverseCharge,
    ecommerceOperatorGstin: ecommerceOperatorGstin.trim() || undefined,
    priceMode,
    invoiceDate,
    dueDate,
    paymentTermsDays,
    additionalCharges,
    chargesHsn: chargesHsn.trim() || undefined,
    chargesGstRate: chargesGstRate || undefined,
    invoiceDiscount,
    invoiceDiscountMode,
    autoRoundOff,
    notes,
    termsText: showTerms ? termsText : '',
    includeBankDetails: showBank,
    includePaymentQr: showQr,
    includeTerms: showTerms,
    signature: signatureId,
    customFields: invoiceCustomFields,
    tcsSection,
    tcsRate,
    ...(tcsAmountManual ? { tcsAmount } : {}),
    items: lines.map((l) => ({
      ...(l.lineId != null ? { id: l.lineId } : {}),
      product: l.product,
      description: l.description || l.productName,
      quantity: l.quantity,
      unitPrice: priceMode === 'INCLUSIVE' ? undefined : l.unitPrice,
      unitPriceInclusive: priceMode === 'INCLUSIVE' ? l.unitPrice : undefined,
      discountPercent: l.discountPercent,
      gstRate:
        invoiceType === 'NON_GST' ||
        supplyType === 'EXPWOP' ||
        supplyType === 'SEZWOP' ||
        (l.supplyNature ?? 'TAXABLE') !== 'TAXABLE'
          ? 0
          : l.gstRate,
      cessRate:
        invoiceType === 'NON_GST' || supplyType === 'EXPWOP' || supplyType === 'SEZWOP'
          ? 0
          : l.cessRate ?? 0,
      supplyNature: l.supplyNature ?? 'TAXABLE',
      batch: l.batch ?? undefined,
      batchNo: l.batchNo || undefined,
      unitName: l.unitName || undefined,
      expDate: l.expDate || null,
      mfgDate: l.mfgDate || null,
      ...(l.trackSerial && l.serialNumbersText?.trim()
        ? { serialNumbers: parseSerialNumbersText(l.serialNumbersText) }
        : {}),
    })),
  }), [
    additionalCharges, autoRoundOff, chargesGstRate, chargesHsn, companyGstinId, costCenterId,
    customerId, dueDate, ecommerceOperatorGstin, invoiceCustomFields, invoiceDate, invoiceDiscount, invoiceDiscountMode,
    invoiceType, isReverseCharge, lines, notes, paymentTermsDays, priceMode, showBank, showQr,
    showTerms, signatureId, supplyType, tcsAmountManual, tcsAmount, tcsRate, tcsSection, termsText, warehouseId,
  ]);

  const previewOnline = typeof navigator === 'undefined' || navigator.onLine;
  // F2-030: buildPayload() maps every line and builds nested item objects —
  // memoize it so the preview payload is only rebuilt when an input that
  // actually feeds it changes, not on every render of a large invoice.
  const previewPayload = useMemo(() => buildPayload(), [buildPayload]);
  const preview = usePreviewTotals(
    'sales',
    previewOnline && customerId && lines.some((l) => l.product)
      ? (previewPayload as Record<string, unknown>)
      : null,
  );

  const previewPayloadKey = JSON.stringify(previewPayload);
  useEffect(() => {
    const savedCopy = editingStatus === 'COMPLETED' && editId;
    const canPreviewDraft = Boolean(customerId) && lines.some((line) => line.product);
    if (!previewMode || (!savedCopy && !canPreviewDraft)) return;
    let revoke = '';
    let cancelled = false;
    const timer = window.setTimeout(() => {
      const run = savedCopy
        ? downloadInvoicePdf(editId!)
        : downloadInvoicePreviewPdf(previewPayload as Record<string, unknown>);
      void run
        .then((blob) => {
          if (cancelled) return;
          revoke = URL.createObjectURL(blob);
          setPdfPreviewUrl(revoke);
        })
        .catch(() => {
          if (!cancelled) setPdfPreviewUrl(null);
        });
    }, savedCopy ? 0 : 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (revoke) URL.revokeObjectURL(revoke);
      setPdfPreviewUrl(null);
    };
  }, [previewMode, editingStatus, editId, previewPayloadKey, customerId, lines, previewPayload]);

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete' | 'complete_new' | 'draft_new' | 'save') => {
      if (!customerId) throw new Error(t('billing.customerRequired'));
      if (lines.length === 0) throw new Error(t('billing.addAtLeastOneItem'));

      const shouldComplete = mode === 'complete' || mode === 'complete_new';
      if (shouldComplete && invoiceType !== 'NON_GST' && companyStepIncompleteNeedsGst(company.data)) {
        throw new Error(t('billing.gstinRequiredBeforeGstComplete'));
      }
      if (shouldComplete && invoiceType !== 'NON_GST' && intraState === null) {
        throw new Error(t('billing.placeOfSupplyRequired'));
      }
      if (shouldComplete && isReverseCharge && !confirmSalesRcm) {
        throw new Error(t('billing.confirmSalesRcmRequired'));
      }
      if (shouldComplete && creditHold) {
        throw new Error(t('phase1.creditHoldBanner'));
      }
      if (shouldComplete && creditLimitExceeded) {
        throw new Error(t('billing.completeDisabledCreditLimit'));
      }
      if (shouldComplete && lines.some((l) => toNumber(l.quantity) <= 0)) {
        throw new Error(t('billing.completeDisabledZeroQty'));
      }
      const missingSerial = lines.find(
        (l) => l.trackSerial && !serialCountMatchesQty(l.serialNumbersText, l.quantity),
      );
      if (shouldComplete && missingSerial) {
        throw new Error(
          t('billing.completeDisabledMissingSerial', { name: missingSerial.productName }),
        );
      }
      const payload = buildPayload();
      // PD-01: one fresh Idempotency-Key per user gesture. Network auto-retry
      // reuses the request header; an offline queue+flush reuses draft.idempotencyKey.
      const sig = JSON.stringify([mode, payload, paymentMode, amountReceived, cheque]);
      if (completeKeyRef.current && completeSigRef.current !== sig) completeKeyRef.current = null;
      const key = completeKeyRef.current ?? userGestureIdempotencyKey();
      completeKeyRef.current = key;
      completeSigRef.current = sig;
      let invoice: SalesInvoice;
      let completeWarning: string | null = null;
      const paymentOnComplete =
        shouldComplete && canTakePayment && paymentMode !== 'CREDIT' && amountReceived > 0
          ? {
              amountReceived,
              paymentMode,
              ...(paymentMode === 'CHEQUE'
                ? {
                    chequeNumber: cheque.chequeNumber,
                    chequeBankName: cheque.chequeBankName,
                    chequeDate: cheque.chequeDate || undefined,
                    chequeImage: cheque.chequeImage ?? undefined,
                  }
                : {}),
            }
          : {};
      // Complete can fail in two ways. If the server answered, that answer is final for
      // this key, so a fixed retry needs a new one. If the response was lost, the server
      // may have committed: look before reporting a failure, and keep the key so a retry
      // replays instead of posting twice.
      const completeOrWarn = async (current: SalesInvoice): Promise<SalesInvoice> => {
        try {
          const done = await completeInvoiceWithConfirms(current.id, {
            confirmSalesRcm: isReverseCharge && confirmSalesRcm,
            idempotencyKey: key,
            ...paymentOnComplete,
          });
          lostCompleteRef.current = false;
          return done;
        } catch (err) {
          if ((err as { response?: { status?: number } }).response?.status === 401) throw err;
          if (isNetworkError(err) || !navigator.onLine) {
            try {
              const fresh = await getSalesInvoice(current.id);
              if (fresh.status === 'COMPLETED') {
                lostCompleteRef.current = false;
                return fresh;
              }
            } catch {
              /* still unreachable */
            }
            lostCompleteRef.current = true;
            completeWarning = t('billing.completeResponseLost');
            return current;
          }
          completeKeyRef.current = null;
          completeWarning = getErrorMessage(err);
          return current;
        }
      };
      const queueOffline = async () => {
        if (!companyId || !userId) return;
        await enqueueDraft(companyId, userId, {
          kind: 'invoice',
          payload: {
            ...(payload as Record<string, unknown>),
            ...(editingStatus ? { status: editingStatus } : {}),
            ...(editingStatus === 'COMPLETED'
              ? { confirmAmend: true, expectedAmendRevision: existingInvoice.data?.amendRevision ?? 0 }
              : {}),
            _completeIntent: shouldComplete,
            _confirmSalesRcm: isReverseCharge && confirmSalesRcm,
            _amountReceived: amountReceived,
            _paymentMode: paymentMode,
            _chequeNumber: cheque.chequeNumber,
            _chequeBankName: cheque.chequeBankName,
            _chequeDate: cheque.chequeDate,
            _chequeImage: cheque.chequeImage ?? null,
            _customerId: Number(customerId),
          },
          idempotencyKey: key,
          invoiceId: isEdit && editId ? editId : null,
          completeIntent: shouldComplete,
          customerId: Number(customerId),
          paymentMode,
        });
        setOutboxBanner(t('billing.savedOffline'));
      };
      try {
        if (isEdit && editId) {
          // H9-A: completed invoices need Owner + confirm_amend for money-field edits.
          if (editingStatus === 'COMPLETED') {
            if (!isOwner) {
              throw new Error(
                'Only an Owner can amend a completed invoice. Use a return for stock corrections, not price fixes.',
              );
            }
            if (!amendConfirmedRef.current) {
              // Ask in a dialog; its Confirm button runs this save again.
              setAmendConfirm(mode);
              throw new AmendPending();
            }
            amendConfirmedRef.current = false;
            if (hasLiveIrn(existingInvoice.data ?? {})) {
              throw new Error(t('einvoice.lineAmendBlocked'));
            }
            invoice = await updateSalesInvoice(editId, {
              ...payload,
              confirmAmend: true,
              expectedAmendRevision: existingInvoice.data?.amendRevision ?? 0,
            });
          } else {
            const settled = lostCompleteRef.current ? await getSalesInvoice(editId) : null;
            if (settled?.status === 'COMPLETED') {
              lostCompleteRef.current = false;
              invoice = settled;
            } else {
              invoice = await updateSalesInvoice(editId, payload);
            }
          }
          // mode 'save' (completed edit) persists without completing — same path as draft.
          if (shouldComplete && invoice.status === 'DRAFT') {
            invoice = await completeOrWarn(invoice);
          }
        } else {
          invoice = await createSalesInvoice(payload, { idempotencyKey: key });
          if (shouldComplete) {
            invoice = await completeOrWarn(invoice);
          }
        }
      } catch (err) {
        if (err instanceof AmendPending) throw err;
        if (isNetworkError(err) || !navigator.onLine) {
          await queueOffline();
          throw new Error(t('billing.savedOffline'));
        }
        throw err;
      }

      let paymentWarning: string | null = completeWarning;
      if (invoice.warnings?.length) {
        paymentWarning = [paymentWarning, ...invoice.warnings].filter(Boolean).join(' ');
      }
      return { invoice, mode, paymentWarning, completeWarning };
    },
    onSuccess: async ({ invoice, mode, paymentWarning, completeWarning }) => {
      const stayOnForm =
        (mode === 'complete' || mode === 'complete_new') && Boolean(completeWarning) && invoice.status !== 'COMPLETED';
      if (!stayOnForm) flushSync(() => setSkipLeaveGuard(true));
      flashWarning(paymentWarning ?? null);
      void qc.invalidateQueries({ queryKey: ['sales-invoice-number-series'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoice.id] });
      const label = invoice.number?.trim() ? invoice.number : `#${invoice.id}`;

      if (mode === 'complete_new' && invoice.status === 'COMPLETED') {
        completeKeyRef.current = null;
        setSavedForShare({ id: invoice.id, number: label });
        flashSaveAndNew(t('billing.invoiceSavedNext', { label }), paymentWarning);
        if (autoPrint) {
          void downloadInvoicePdf(invoice.id).then((blob) => {
            const url = URL.createObjectURL(blob);
            const frame = document.createElement('iframe');
            frame.style.display = 'none';
            frame.src = url;
            document.body.appendChild(frame);
            frame.onload = () => {
              frame.contentWindow?.print();
              window.setTimeout(() => {
                frame.remove();
                URL.revokeObjectURL(url);
              }, 60_000);
            };
          }).catch(() => undefined);
        }
        resetForm();
        navigate('/sales/new', { replace: true });
        return;
      }
      if (mode === 'draft_new') {
        flashSaveAndNew(t('billing.draftSaved', { label }), paymentWarning);
        resetForm();
        return;
      }

      const flash =
        invoice.status === 'COMPLETED'
          ? t('billing.invoiceSaved', { label })
          : paymentWarning
            ? t('billing.draftSavedCompleteFailed', { label, warning: paymentWarning })
            : t('billing.draftSaved', { label });

      // Warm list cache before SPA navigate so history isn't blank until hard
      // refresh. F2-026: the history page keys on ['sales-invoices', page] with
      // page 1 and pageSize 50 — warm that exact key, not the bare one.
      void qc
        .prefetchQuery({
          queryKey: ['sales-invoices', 1],
          queryFn: () => listSalesInvoicesPage({ page: 1, pageSize: 50 }),
          staleTime: 0,
        })
        .catch(() => qc.invalidateQueries({ queryKey: ['sales-invoices'] }));

      if (mode === 'complete' && invoice.status === 'COMPLETED') {
        completeKeyRef.current = null;
        navigate(`/sales/history/${invoice.id}`, {
          replace: true,
          state: { message: flash },
        });
        return;
      }

      if ((mode === 'complete' || mode === 'complete_new') && completeWarning && invoice.status !== 'COMPLETED') {
        setError(completeWarning);
        if (!isEdit && invoice.id) {
          navigate(`/sales/history/${invoice.id}/edit`, { replace: true });
        }
        return;
      }

      navigate('/sales/history', {
        replace: true,
        state: {
          message: flash,
        },
      });
    },
    onError: (err) => {
      if (err instanceof AmendPending) return;
      amendConfirmedRef.current = false;
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 401) {
        setReauthOpen(true);
        return;
      }
      const msg = getErrorMessage(err);
      if (msg === t('billing.savedOffline')) return;
      if (classifyCompleteFailure(err) === 'validation') trackShopFloor('form_validation_failed', { feature: 'form' });
      flashError(err);
    },
  });

  const itemMutation = useMutation({
    mutationFn: () =>
      createProduct({
        name: itemForm.name.trim(),
        sku: itemForm.sku.trim(),
        unitName: itemForm.unitName || 'PCS',
        hsnCode: itemForm.hsnCode.trim(),
        sellingPrice: Number(itemForm.sellingPrice) || 0,
        mrp: Number(itemForm.mrp) || 0,
        gstRate: Number(itemForm.gstRate) || 0,
        purchasePrice: showPurchasePrice && canSeeMargin ? Number(itemForm.purchasePrice) || 0 : 0,
        reorderLevel: 0,
        status: 'ACTIVE',
      }),
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ['products'] });
      void qc.invalidateQueries({ queryKey: ['product-search'] });
      setLines((prev) => [...prev, makeInvoiceLine(p, intraState)]);
      setItemDialogOpen(false);
      setItemDialogError(null);
      setItemForm({
        name: '',
        sku: '',
        unitName: 'PCS',
        hsnCode: '',
        sellingPrice: '',
        purchasePrice: '',
        mrp: '',
        gstRate: '18',
      });
    },
    onError: (err) => {
      setItemDialogError(getErrorMessage(err));
      setItemDialogErrorSource(err);
    },
  });

  const addProduct = (product: Product | null) => {
    if (!product || editingStatus === 'COMPLETED') return;
    if (product.status !== 'ACTIVE') {
      setError('Cannot sell inactive product');
      return;
    }
    setLines((prev) => {
      const existing = prev.find((l) => l.product === product.id && !l.batchNo);
      const priceListId = selectedCustomer?.priceList;
      const qty = existing ? existing.quantity + 1 : 1;
      const resolved = resolveListUnitPrice(
        priceLists.data as import('@/utils/priceList').PriceListRow[] | undefined,
        priceListId,
        product.id,
        qty,
      );
      if (existing) {
        return prev.map((l) =>
          l.key === existing.key
            ? recomputeLine(l, intraState, {
                quantity: qty,
                ...(resolved ? { unitPrice: resolved.unitPrice } : {}),
              })
            : l,
        );
      }
      const line = makeInvoiceLine(product, intraState);
      return [...prev, resolved ? recomputeLine(line, intraState, { unitPrice: resolved.unitPrice }) : line];
    });
    setProductQuery('');
    setError(null);
  };

  const lastScan = useRef('');
  const scanChain = useRef<Promise<void>>(Promise.resolve());
  const highlightedItem = useRef<Product | null>(null);
  useEffect(() => {
    const query = productQuery.trim();
    if (!query) {
      lastScan.current = '';
      return;
    }
    // Wait until the results belong to what is in the box now. Otherwise typing
    // "ABC-1" would add the product whose SKU is exactly "ABC" on the third key.
    if (debouncedProductQuery.trim() !== query) return;
    const pool = (debouncedProductQuery.length >= 1 ? products.data : productCatalog.data?.results) ?? [];
    const hit = exactBarcodeOrSku(pool, query);
    if (!hit || hit.status !== 'ACTIVE') return;
    const mark = `${hit.id}:${query}`;
    if (lastScan.current === mark) return;
    lastScan.current = mark;
    addProduct(hit);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- addProduct is re-created each render; the guard above keys on the query.
  }, [productQuery, products.data, productCatalog.data, debouncedProductQuery]);

  const updateLine = (
    key: string,
    patch: Partial<DraftLine>,
    opts?: { fromDiscountAmount?: boolean },
  ) => {
    setLines((prev) =>
      prev.map((l) => {
        if (l.key !== key) return l;
        let nextPatch = patch;
        // A caller-supplied unitPrice is a direct user edit — remember it so a
        // later qty change doesn't clobber the override (F2-007).
        if (patch.unitPrice != null) {
          nextPatch = { ...patch, priceEdited: true };
        }
        if (opts?.fromDiscountAmount && nextPatch.discountAmount != null) {
          nextPatch = { ...nextPatch, discountLockedToAmount: true };
        } else if (patch.discountPercent != null) {
          nextPatch = { ...nextPatch, discountLockedToAmount: false };
        }
        if (patch.quantity != null && patch.unitPrice == null && !l.priceEdited) {
          const resolved = resolveListUnitPrice(
            priceLists.data as import('@/utils/priceList').PriceListRow[] | undefined,
            selectedCustomer?.priceList,
            l.product,
            Number(patch.quantity),
          );
          if (resolved) nextPatch = { ...nextPatch, unitPrice: resolved.unitPrice };
        }
        const changesGross =
          nextPatch.quantity != null || nextPatch.unitPrice != null;
        if (
          (opts?.fromDiscountAmount && nextPatch.discountAmount != null) ||
          // F2-032: a qty/price change on a line that carries an absolute
          // discount amount must re-derive the percent against the new gross,
          // not recompute the amount from the now-stale percent.
          (changesGross && (l.discountAmount ?? 0) > 0)
        ) {
          const gross = roundMoney((nextPatch.quantity ?? l.quantity) * (nextPatch.unitPrice ?? l.unitPrice));
          const rawAmount = nextPatch.discountAmount ?? l.discountAmount ?? 0;
          const amount = Math.min(Math.max(0, rawAmount), gross);
          const percent = gross > 0 ? Math.min(100, roundMoney((amount / gross) * 100)) : 0;
          return recomputeLine(l, intraState, {
            ...nextPatch,
            discountPercent: percent,
            discountAmount: amount,
          });
        }
        return recomputeLine(l, intraState, nextPatch);
      }),
    );
  };

  // BUG-513/F3-015: the tab-close/refresh warning now lives in
  // UnsavedChangesGuard itself (rendered below with the same `when`), so
  // every page that renders the guard gets it for free instead of each
  // hand-rolling its own beforeunload listener.

  const activeCustomers = (customers.data?.results ?? []).filter((c) => c.status === 'ACTIVE');
  const canSave = lines.length > 0 && Boolean(customerId) && !saveMutation.isPending;
  const isCompletedEdit = editingStatus === 'COMPLETED';
  // FE-07: if the server preview endpoint keeps erroring, don't strand a valid
  // invoice — allow Complete with the on-device totals (the server recomputes
  // authoritative totals on save regardless) but surface that it happened.
  const previewFellBack = previewOnline && !preview.ready && preview.error != null;
  const gstinRequiredForGst =
    invoiceType !== 'NON_GST' && companyStepIncompleteNeedsGst(company.data);
  const missingSerialLine =
    lines.find((l) => l.trackSerial && !serialCountMatchesQty(l.serialNumbersText, l.quantity)) ??
    null;
  const zeroQty = lines.some((l) => l.product && toNumber(l.quantity) <= 0);
  const rcmUnconfirmed = isReverseCharge && invoiceType !== 'NON_GST' && !confirmSalesRcm;
  const stockBlocked = !isCompletedEdit && stockShortfalls.length > 0;
  const previewPending = previewOnline && !preview.ready && preview.error == null;
  const liveIrnLock = Boolean(
    isCompletedEdit && existingInvoice.data && hasLiveIrn(existingInvoice.data),
  );
  const completeDisabledReason = firstCompleteDisabledReason({
    canSave,
    partyRole: 'customer',
    posKnown,
    gstinRequired: gstinRequiredForGst,
    missingSerialName: missingSerialLine?.productName ?? null,
    stockBlocked,
    creditHold,
    creditLimitExceeded,
    rcmUnconfirmed,
    zeroQty,
    previewPending,
    irnLocked: liveIrnLock,
  });
  const canComplete =
    canSave &&
    posKnown &&
    !gstinRequiredForGst &&
    !missingSerialLine &&
    !stockBlocked &&
    !creditHold &&
    !creditLimitExceeded &&
    !rcmUnconfirmed &&
    !zeroQty &&
    previewAllowsComplete(previewOnline, preview.ready, preview.error);

  const renderBlockerFocusButton = () => {
    if (missingSerialLine) {
      return (
        <Button
          size="small"
          variant="contained"
          color="warning"
          onClick={() => {
            const el = document.getElementById(`serial-input-${missingSerialLine.key}`);
            if (el) {
              el.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
              el.focus();
            }
          }}
        >
          {t('billing.focusSerialAction')}
        </Button>
      );
    }
    if (stockBlocked) {
      return (
        <Button
          size="small"
          variant="contained"
          color="warning"
          onClick={() => {
            const el = document.getElementById('stock-shortfall-alert');
            el?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
          }}
        >
          {t('billing.reviewStockAction')}
        </Button>
      );
    }
    if (!posKnown) {
      return (
        <Button
          size="small"
          variant="contained"
          color="warning"
          onClick={() => {
            const el =
              document.getElementById('customer-pos-editor') ||
              document.getElementById('customer-state-select');
            if (el) {
              el.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
              const input = el.querySelector('input') || el;
              (input as HTMLElement)?.focus();
            }
          }}
        >
          {t('billing.setCustomerStateAction')}
        </Button>
      );
    }
    return null;
  };
  const shownTotals = preview.totals
    ? {
        ...totals,
        subtotal: preview.totals.subtotal,
        taxableTotal: preview.totals.taxableTotal,
        cgstTotal: preview.totals.cgstTotal,
        sgstTotal: preview.totals.sgstTotal,
        igstTotal: preview.totals.igstTotal,
        cessTotal: preview.totals.cessTotal,
        taxTotal: preview.totals.taxTotal,
        roundOff: preview.totals.roundOff,
        grandTotal: preview.totals.grandTotal,
        tcsAmount: preview.totals.tcsAmount ?? 0,
        amountDue: preview.totals.amountDue ?? preview.totals.grandTotal,
        rcmTaxable: preview.totals.rcmTaxable,
        rcmCgst: preview.totals.rcmCgst,
        rcmSgst: preview.totals.rcmSgst,
        rcmIgst: preview.totals.rcmIgst,
        rcmCess: preview.totals.rcmCess,
      }
    : totals;

  const rcmDisplay = useMemo(() => {
    if (!isReverseCharge || invoiceType === 'NON_GST') return null;
    const fromPreview = Boolean(preview.totals);
    const rcmCgst = fromPreview ? (preview.totals?.rcmCgst ?? 0) : shownTotals.cgstTotal;
    const rcmSgst = fromPreview ? (preview.totals?.rcmSgst ?? 0) : shownTotals.sgstTotal;
    const rcmIgst = fromPreview ? (preview.totals?.rcmIgst ?? 0) : shownTotals.igstTotal;
    const rcmCess = fromPreview ? (preview.totals?.rcmCess ?? 0) : (shownTotals.cessTotal ?? 0);
    return {
      rcmTaxTotal: roundMoney(rcmCgst + rcmSgst + rcmIgst + rcmCess),
      rcmCgst,
      rcmSgst,
      rcmIgst,
      payable: shownTotals.grandTotal,
    };
  }, [isReverseCharge, invoiceType, preview.totals, shownTotals]);

  const shownAmountDue = 'amountDue' in shownTotals ? (shownTotals as { amountDue?: number }).amountDue : shownTotals.grandTotal;
  const amountDueNow = shownAmountDue ?? shownTotals.grandTotal;
  const tenderCounts = canTakePayment && paymentMode !== 'CREDIT';
  const cashChange =
    tenderCounts && paymentMode === 'CASH' && amountReceived > amountDueNow
      ? roundMoney(amountReceived - amountDueNow)
      : 0;
  const balance = cashChange > 0 ? 0 : roundMoney(Math.max(0, amountDueNow - (tenderCounts ? amountReceived : 0)));

  if (markFullyPaid) {
    const paid = shownAmountDue ?? shownTotals.grandTotal;
    if (amountReceived !== paid) setAmountReceived(paid);
  }
  const primarySave = primarySaveAction({ isEdit, editingStatus });
  const canAmendMoney = isCompletedEdit && isOwner && !liveIrnLock;

  // F2-050: keep the shortcut handler's inputs in a ref so the keydown listener
  // is registered exactly once (no per-render add/remove churn), and add a
  // synchronous submit guard so a fast double Ctrl+S can't enqueue twice before
  // React commits `isPending`.
  const kbdRef = useRef({
    canSave: false,
    canComplete: false,
    primaryMode: primarySave.mode,
    isPending: saveMutation.isPending,
    mutate: saveMutation.mutate,
    markPaid: () => undefined as void,
  });
  useLayoutEffect(() => {
    kbdRef.current = {
      canSave,
      canComplete,
      primaryMode: primarySave.mode,
      isPending: saveMutation.isPending,
      mutate: saveMutation.mutate,
      markPaid: () => {
        if (!canTakePayment) return;
        setMarkFullyPaid(true);
        setAmountReceived(amountDueNow);
      },
    };
  });
  const kbdSubmittingRef = useRef(false);
  useEffect(() => {
    if (!saveMutation.isPending) kbdSubmittingRef.current = false;
  }, [saveMutation.isPending]);

  useEffect(() => {
    // Wave 18D (BB-000182): billing keyboard shortcuts — see README Wave 18 note.
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target?.closest('[role=dialog]') ||
        target?.tagName === 'TEXTAREA' ||
        target?.isContentEditable
      ) {
        return;
      }
      const meta = e.ctrlKey || e.metaKey;
      const kbd = kbdRef.current;
      if (meta && e.key.toLowerCase() === 's' && !e.shiftKey) {
        e.preventDefault();
        if (!kbd.isPending && !kbdSubmittingRef.current && kbd.canSave) {
          kbdSubmittingRef.current = true;
          kbd.mutate('draft');
        }
        return;
      }
      // FE-19: Complete files GST, posts the GL entry and decrements stock — do
      // not let a stray Ctrl+Enter while typing in a line field trigger it.
      const inEditableField =
        target?.tagName === 'INPUT' || target?.tagName === 'SELECT';
      if (
        meta &&
        e.key === 'Enter' &&
        !e.shiftKey &&
        !inEditableField &&
        kbd.canComplete &&
        kbd.primaryMode === 'complete'
      ) {
        e.preventDefault();
        if (!kbd.isPending && !kbdSubmittingRef.current) {
          kbdSubmittingRef.current = true;
          kbd.mutate('complete');
        }
        return;
      }
      if (meta && e.shiftKey && e.key.toLowerCase() === 'l') {
        e.preventDefault();
        barcodeRef.current?.focus();
        return;
      }
      if (e.altKey && !meta && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        kbd.markPaid();
        return;
      }
      if (e.key === 'F2') {
        e.preventDefault();
        barcodeRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const onSignaturePick = async (file: File | null) => {
    if (!file) return;
    try {
      const uploaded = await uploadFile(file, 'ATTACHMENT');
      // FE-09: attach the signature to *this* invoice only. It used to also call
      // updateCompany({ signature }) which silently changed the company-wide
      // default for every future document. Set the default from Settings instead.
      setSignatureId(uploaded.id);
      setSignatureUrl(uploaded.url ?? null);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  if (isEdit && existingInvoice.isLoading) return <LoadingState />;
  if (isEdit && existingInvoice.isError) {
    return (
      <ErrorState
        message={getErrorMessage(existingInvoice.error)}
        error={existingInvoice.error}
        onRetry={() => void existingInvoice.refetch()}
      />
    );
  }
  if (isEdit && existingInvoice.isSuccess && !existingInvoice.data) return <EmptyState />;
  if (isEdit && (editingStatus === 'CANCELLED' || existingInvoice.data?.status === 'CANCELLED')) {
    return (
      <ErrorState
        message={t('billing.cannotEditCancelled')}
        onRetry={() => navigate(`/sales/history/${editId}`)}
      />
    );
  }
  if (isEdit && existingInvoice.data?.status === 'RETURNED') {
    return (
      <ErrorState
        message={t('billing.cannotEditReturned')}
        onRetry={() => navigate(`/sales/history/${editId}`)}
      />
    );
  }

  return (
    <DocumentEditorShell
      partyRole="customer"
      title={
        editingStatus === 'COMPLETED'
          ? t('billing.amendTitle')
          : isEdit || deviceDraft
            ? t('billing.draftEditTitle')
            : t('billing.title')
      }
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canComplete}
      primaryDisabledExtra={isCompletedEdit && (!isOwner || liveIrnLock)}
      primaryDisabledReason={completeDisabledReason}
      onFocusMissing={() => {
        document.getElementById(customerId ? 'billing-item-input' : 'billing-party-input')?.focus();
      }}
      isEdit={isEdit}
      extraActions={
        <>
          {isEdit && canSeeMargin ? (
            <Button variant="outlined" size="small" onClick={() => setProfitOpen(true)}>
              {t('invoiceDetail.profitDetails')}
            </Button>
          ) : null}
          {canImport(user) ? (
            <Button component={RouterLink} to="/sales/bill-upload" variant="outlined" size="small">
              {t('nav.uploadSalesBill')}
            </Button>
          ) : null}
        </>
      }
      showDraftButton={!isEdit || editingStatus === 'DRAFT'}
      backTo={isEdit ? `/sales/history/${editId}` : null}
      message={message ?? outboxBanner}
      messageAction={
        savedForShare ? (
          <Stack direction="row" spacing={1}>
            <Button
              color="inherit"
              size="small"
              onClick={() => {
                void downloadInvoicePdf(savedForShare.id).then((blob) => {
                  const url = URL.createObjectURL(blob);
                  const frame = document.createElement('iframe');
                  frame.style.display = 'none';
                  frame.src = url;
                  document.body.appendChild(frame);
                  frame.onload = () => frame.contentWindow?.print();
                }).catch((err) => setError(getErrorMessage(err)));
              }}
            >
              {t('invoiceDetail.printPdf')}
            </Button>
            <Button color="inherit" size="small" onClick={() => setShareAfterSave(true)}>
              {t('common.share')}
            </Button>
          </Stack>
        ) : undefined
      }
      error={error || preview.error}
      errorSource={errorSource}
      onDismissError={() => setError(null)}
      documentId={isEdit ? editId ?? undefined : undefined}
      multiGodown={(warehouses.data?.length ?? 0) > 1}
      warning={
        liveIrnLock
          ? t('einvoice.lineAmendBlocked')
          : previewFellBack
          ? t('billing.previewUnavailableClientTotals')
          : fromBillUpload
          ? t('billUpload.reviewOnEditDisclaimerSales')
          : isEdit && editingStatus === 'COMPLETED' && lines.some((l) => l.trackBatch || l.trackSerial)
            ? t('billing.completedBatchLocked')
            : isEdit && editingStatus === 'COMPLETED'
            ? t('billing.editingCompletedWarning')
            : null
      }
      infoBanner={
        <Stack spacing={1}>
          <Typography variant="body2">{t('billing.threeStarts')}</Typography>
          {canAccessPos(user) ? (
            <Typography variant="body2">
              {t('billing.taxInvoiceNotTill')}{' '}
              <Link component={RouterLink} to="/pos">{t('nav.pos')}</Link>
            </Typography>
          ) : null}
          {deviceDraft ? (
            <Alert
              severity="info"
              action={
                <Stack direction="row" spacing={1}>
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => {
                      void (async () => {
                        const fetched = await Promise.all(
                          deviceDraft.lines.map(async (line) => {
                            try {
                              return { line, product: await getProduct(line.product), failed: false, err: null as unknown };
                            } catch (err) {
                              const status = (err as { response?: { status?: number } })?.response?.status;
                              // A product the server no longer has is dropped; anything else keeps the draft.
                              return { line, product: null, failed: status !== 404, err: err as unknown };
                            }
                          }),
                        );
                        const failure = fetched.find((row) => row.failed);
                        if (failure) {
                          setError(getErrorMessage(failure.err));
                          return;
                        }
                        rearmEditorBaseline();
                        const next: DraftLine[] = [];
                        const updated: DraftLine[] = [];
                        const drifts: { name: string; from: string; to: string }[] = [];
                        // The draft's party may not be on the first page of the party list, and its
                        // price list decides what "today's price" means.
                        let customer = (customers.data?.results ?? []).find(
                          (c) => c.id === Number(deviceDraft.customerId),
                        );
                        if (!customer && deviceDraft.customerId) {
                          try {
                            customer = await getCustomer(Number(deviceDraft.customerId));
                          } catch {
                            customer = undefined;
                          }
                        }
                        for (const { line, product } of fetched) {
                          if (!product) continue;
                          const listed = resolveListUnitPrice(
                            priceLists.data as import('@/utils/priceList').PriceListRow[] | undefined,
                            customer?.priceList,
                            product.id,
                            toNumber(line.quantity) || 1,
                          );
                          const currentPrice = listed?.unitPrice ?? toNumber(product.sellingPrice);
                          const draftPrice = toNumber(line.unitPrice);
                          if (!line.priceEdited && draftPrice > 0 && Math.abs(draftPrice - currentPrice) > 0.01) {
                            drifts.push({
                              name: product.name,
                              from: formatMoney(draftPrice),
                              to: formatMoney(currentPrice),
                            });
                          }
                          if ((line.hsnCode || '') !== (product.hsnCode || '') || Math.abs(toNumber(line.gstRate) - toNumber(product.gstRate)) > 0.01) {
                            drifts.push({
                              name: `${product.name} HSN/GST`,
                              from: `${line.hsnCode || '—'} @ ${line.gstRate}%`,
                              to: `${product.hsnCode || '—'} @ ${product.gstRate}%`,
                            });
                          }
                          next.push({
                            ...line,
                            unitPrice: line.priceEdited ? line.unitPrice : (draftPrice > 0 ? draftPrice : currentPrice),
                            productName: product.name,
                            sku: product.sku,
                            productType: product.productType,
                            trackInventory: product.trackInventory,
                            purchasePrice: toNumber(product.purchasePrice),
                          });
                          updated.push({
                            ...line,
                            unitPrice: line.priceEdited ? line.unitPrice : currentPrice,
                            gstRate: toNumber(product.gstRate),
                            hsnCode: product.hsnCode ?? line.hsnCode,
                            productName: product.name,
                            sku: product.sku,
                            productType: product.productType,
                            trackInventory: product.trackInventory,
                            purchasePrice: toNumber(product.purchasePrice),
                          });
                        }
                        if (drifts.length) {
                          setPriceDrift({ lines: next, updated, drifts, customerId: deviceDraft.customerId });
                          return;
                        }
                        setLines(next);
                        if (deviceDraft.customerId) setCustomerId(deviceDraft.customerId);
                        setDeviceDraft(null);
                      })();
                    }}
                  >
                    {t('billing.restoreDraft')}
                  </Button>
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => {
                      if (companyId && userId) removeDeviceDraft(companyId, userId, 'sales-invoice');
                      setDeviceDraft(null);
                    }}
                  >
                    {t('pos.discardBill')}
                  </Button>
                </Stack>
              }
            >
              {t('pos.pricesUpdated')}
            </Alert>
          ) : null}
          {collectionHoldBanner}
          {creditLimitBanner}
        </Stack>
      }
      saving={saveMutation.isPending}
      onPrimarySave={() => saveMutation.mutate(primarySave.mode)}
      onSaveAndNew={() => saveMutation.mutate('complete_new')}
      onSaveDraftAndNew={() => saveMutation.mutate('draft_new')}
      onDraft={() => saveMutation.mutate('draft')}
      onOpenShortcuts={() => setShortcutsOpen(true)}
      onOpenSettings={() => setSettingsOpen(true)}
    >
      <Stack spacing={2}>
      <UnsavedChangesGuard when={!skipLeaveGuard && editorDirty} />
      <Stack direction="row" spacing={1}>
        <Button size="small" variant={previewMode ? 'outlined' : 'contained'} onClick={() => setPreviewMode(false)}>
          {t('billing.editMode')}
        </Button>
        <Button size="small" variant={previewMode ? 'contained' : 'outlined'} onClick={() => setPreviewMode(true)}>
          {t('billing.previewMode')}
        </Button>
      </Stack>
      {previewMode ? (
        <Stack spacing={1} aria-label={t('billing.previewMode')}>
          {preview.totals ? (
            <>
              <Typography>{selectedCustomer?.name}</Typography>
              <Typography>{formatMoney(preview.totals.grandTotal)}</Typography>
              <Typography>{amountInWords(preview.totals.grandTotal ?? 0)}</Typography>
            </>
          ) : null}
          {pdfPreviewUrl ? (
            <iframe
              title={t('billing.previewMode')}
              src={pdfPreviewUrl}
              style={{ width: '100%', minHeight: 720, border: 0 }}
            />
          ) : (
            <Typography variant="body2" color="text.secondary">
              {t('billing.previewPreparing')}
            </Typography>
          )}
        </Stack>
      ) : null}
      {previewMode ? null : (
      <>
      {gstinRequiredForGst ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" component={RouterLink} to="/settings/gst">
              {t('billing.openGstSettings')}
            </Button>
          }
        >
          {t('billing.gstinRequiredBeforeGstComplete')}
        </Alert>
      ) : null}
      {offline || hasOutboxItems || Boolean(outboxBanner) ? (
        !hideOutboxWarn || offline ? (
          <Alert
            severity="warning"
            onClose={
              offline
                ? undefined
                : () => {
                    localStorage.setItem(OUTBOX_WARNING_DISMISS_KEY, '1');
                    setHideOutboxWarn(true);
                  }
            }
          >
            {t('billing.outboxPlaintextWarning')}
          </Alert>
        ) : null
      ) : null}
      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <InvoicePartyPanel
            selectedCustomer={selectedCustomer}
            editingStatus={editingStatus}
            options={activeCustomers}
            query={customerQuery}
            onQueryChange={setCustomerQuery}
            onSelect={(v) => {
              setCustomerId(v?.id ?? '');
              // Only a real credit period replaces the default terms; a credit limit alone just
              // reveals the terms so they can be reviewed (it must not zero the default days).
              if (v && Number(v.creditDays) > 0) setPaymentTermsDays(Number(v.creditDays));
              if (v && (Number(v.creditDays) > 0 || toNumber(v.creditLimit) > 0)) setShowPaymentTerms(true);
            }}
            loading={customers.isFetching}
            requirePlaceOfSupply={
              invoiceType !== 'NON_GST' &&
              Boolean(company.data?.isGstRegistered) &&
              !company.data?.assumeLocalStateForBlankParty
            }
            onCustomerCreated={(c) => {
              setCustomerId(c.id);
              if (c.creditDays) setPaymentTermsDays(c.creditDays);
            }}
            onCustomerUpdated={(c) => {
              setCustomerId(c.id);
            }}
            onError={(msg) => setError(msg)}
            manualName={manualName}
            onManualNameChange={setManualName}
          />
          {selectedCustomer
            ? activeCustomFieldDefs(company.data?.partyCustomFieldDefs).map((def) => (
                <TextField
                  key={`${selectedCustomer.id}-${def.key}`}
                  size="small"
                  label={def.label}
                  defaultValue={selectedCustomer.customFields?.[def.key] ?? ''}
                  onBlur={(e) => {
                    const value = e.target.value;
                    const next = { ...(selectedCustomer.customFields ?? {}), [def.key]: value };
                    void updateCustomer(selectedCustomer.id, { customFields: next }).catch((err) =>
                      setError(getErrorMessage(err)),
                    );
                  }}
                />
              ))
            : null}

          <Stack spacing={1.5} sx={{ flex: 1, minWidth: 280 }}>
            <Typography variant="body2" color="text.secondary">
              {isEdit
                ? t('billing.invoiceNumberFixed')
                : t('billing.nextBillCaption', {
                    number: `${prefix}-${String(nextNumber).padStart(series?.data?.padding ?? 5, '0')}`,
                  })}
            </Typography>
            {resolvedSeriesGstin(company.data) ? (
              <Typography variant="caption" color="text.secondary">
                {t('billing.seriesGstin', { gstin: resolvedSeriesGstin(company.data) })}
              </Typography>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <CompactField
                label={t('billing.invoiceDate')}
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ width: 140 }}
              />
              {showInvoiceType ? (
              <CompactField
                select
                label={t('billing.invoiceType')}
                value={invoiceType}
                onChange={(e) => {
                  setInvoiceTypeTouched(true);
                  setInvoiceType(e.target.value as InvoiceType);
                }}
                sx={{ minWidth: 140 }}
              >
                {company.data?.registrationType === 'REGULAR'
                  ? [
                      <MenuItem key="GST" value="GST">
                        <ListItemText primary={t('billing.gstInvoice')} secondary={t('billing.invoiceTypeGst')} />
                      </MenuItem>,
                      <MenuItem key="TAX" value="TAX">
                        <ListItemText primary={t('billing.taxInvoice')} secondary={t('billing.invoiceTypeTax')} />
                      </MenuItem>,
                      <MenuItem key="RETAIL" value="RETAIL">
                        <ListItemText primary={t('billing.retailInvoice')} secondary={t('billing.invoiceTypeRetail')} />
                      </MenuItem>,
                    ]
                  : null}
                <MenuItem value="NON_GST">
                  <ListItemText primary={t('billing.nonGstInvoice')} secondary={t('billing.invoiceTypeNonGst')} />
                </MenuItem>
              </CompactField>
              ) : (
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip
                    size="small"
                    label={t(invoiceTypeChipKey(invoiceType, Boolean((selectedCustomer?.gstin || '').trim())))}
                  />
                  <Button size="small" onClick={() => setShowInvoiceType(true)}>{t('cog.changeBillType')}</Button>
                </Stack>
              )}
              {invoiceType !== 'NON_GST' ? (
                <Chip
                  size="small"
                  clickable
                  label={priceMode === 'INCLUSIVE' ? t('billing.priceIncludesGst') : t('billing.priceBeforeGst')}
                  onClick={() => setShowAdvancedTax(true)}
                />
              ) : null}
              {(() => {
                const activeGodowns = (warehouses.data ?? []).filter((warehouse) => warehouse.isActive !== false);
                const defaultGodown = activeGodowns.find((warehouse) => warehouse.isDefault) ?? activeGodowns[0];
                const revealGodown = showGodownSelect({
                  activeCount: activeGodowns.length,
                  isEdit,
                  selectedId: warehouseId,
                  defaultId: defaultGodown?.id ?? '',
                });
                if (!revealGodown) {
                  return (
                    <Stack direction="row" alignItems="center" spacing={0.5}>
                      <Typography variant="body2">
                        {t('cog.onlyGodown', { name: defaultGodown?.name ?? '' })}
                      </Typography>
                      <FieldHelpTip slot="godown" title={t('help.godownTip')} />
                    </Stack>
                  );
                }
                return (
                  <Stack direction="row" alignItems="center" spacing={0.25} sx={{ minWidth: 140 }}>
                    <CompactField
                      select
                      label={t('billing.godown')}
                      value={warehouseId}
                      onChange={(e) => setWarehouseId(e.target.value ? Number(e.target.value) : '')}
                      sx={{ minWidth: 140, flex: 1 }}
                    >
                      {activeGodowns.map((warehouse) => (
                        <MenuItem key={warehouse.id} value={warehouse.id}>
                          {warehouse.name}{warehouse.isDefault ? t('billing.defaultGodown') : ''}
                        </MenuItem>
                      ))}
                    </CompactField>
                    <FieldHelpTip slot="godown" title={t('help.godownTip')} />
                  </Stack>
                );
              })()}
            </Stack>

            {posAsk && posReason === 'conflict' ? (
              <Alert severity="warning">
                {t('cog.posConflict', { gstinState: posGstinCode ?? '', addressState: posAddressCode ?? '' })}
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button size="small" variant={posPick === 'gstin' ? 'contained' : 'outlined'} onClick={() => setPosPick('gstin')}>
                    {t('cog.useGstinState')} — {isIntraState(company.data?.state || company.data?.gstin, posGstinCode) ? t('billing.taxIntraStateHint') : t('billing.taxInterStateHint')}
                  </Button>
                  <Button size="small" variant={posPick === 'address' ? 'contained' : 'outlined'} onClick={() => setPosPick('address')}>
                    {t('cog.useAddressState')} — {isIntraState(company.data?.state || company.data?.gstin, posAddressCode) ? t('billing.taxIntraStateHint') : t('billing.taxInterStateHint')}
                  </Button>
                </Stack>
              </Alert>
            ) : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {statutoryChipIds({
                supplyType,
                companyGstinId,
                costCenterId,
                ecommerceGstin: ecommerceOperatorGstin,
                reverseCharge: isReverseCharge,
              }).map((chip) => (
                <Chip key={chip} size="small" label={t(statutoryChipLabel(chip))} onClick={() => setShowAdvancedTax(true)} />
              ))}
            </Stack>

            <Link
              component="button"
              type="button"
              variant="caption"
              onClick={() => setShowAdvancedTax((v) => !v)}
              sx={{ alignSelf: 'flex-start', mt: 0.5 }}
            >
              {showAdvancedTax ? `− ${t('billing.lessTaxOptions')}` : `+ ${t('billing.moreTaxOptions')}`}
            </Link>

            <Collapse in={showAdvancedTax}>
              <Stack spacing={1.5} sx={{ p: 1.5, border: '1px dashed', borderColor: 'divider', borderRadius: 1, mt: 1 }}>
                <Typography variant="caption" fontWeight={600} color="text.secondary">
                  {t('billing.statutoryHeading')}
                </Typography>
                {invoiceType !== 'NON_GST' ? (
                  <CompactField
                    select
                    label={t('billing.priceMode')}
                    value={priceMode}
                    onChange={(e) => setPriceMode(e.target.value as PriceMode)}
                    disabled={isCompletedEdit && !canAmendMoney}
                    sx={{ minWidth: 140 }}
                  >
                    <MenuItem value="EXCLUSIVE">{t('billing.taxExclusive')}</MenuItem>
                    <MenuItem value="INCLUSIVE">{t('billing.taxInclusive')}</MenuItem>
                  </CompactField>
                ) : null}
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {invoiceType !== 'NON_GST' ? (
                    <CompactField
                      select
                      label={t('billing.supplyType')}
                      value={supplyType}
                      onChange={(e) =>
                        setSupplyType(e.target.value as import('@/types/domain').SupplyType)
                      }
                      sx={{ minWidth: 160 }}
                    >
                      <MenuItem value="B2B">{t('billing.supplyB2b')}</MenuItem>
                      <MenuItem value="SEZWP">{t('billing.supplySezwp')}</MenuItem>
                      <MenuItem value="SEZWOP">{t('billing.supplySezwop')}</MenuItem>
                      <MenuItem value="EXPWP">{t('billing.supplyExpwp')}</MenuItem>
                      <MenuItem value="EXPWOP">{t('billing.supplyExpwop')}</MenuItem>
                      <MenuItem value="DEXP">{t('billing.supplyDexp')}</MenuItem>
                    </CompactField>
                  ) : null}
                  {(companyGstins.data ?? []).length > 0 ? (
                    <CompactField
                      select
                      label={t('billing.companyGstin')}
                      value={companyGstinId}
                      onChange={(e) => setCompanyGstinId(e.target.value ? Number(e.target.value) : '')}
                      sx={{ minWidth: 160 }}
                    >
                      <MenuItem value="">{t('billing.primaryGstin')}</MenuItem>
                      {(companyGstins.data ?? []).filter((row) => row.isActive !== false && row.is_active !== false).map((row) => (
                        <MenuItem key={row.id} value={row.id}>
                          {row.gstin}{(row.isPrimary || row.is_primary) ? ' (primary)' : ''}
                        </MenuItem>
                      ))}
                    </CompactField>
                  ) : null}
                  <CompactField
                    select
                    label={t('billing.costCenter')}
                    value={costCenterId}
                    onChange={(e) => setCostCenterId(e.target.value ? Number(e.target.value) : '')}
                    sx={{ minWidth: 140 }}
                  >
                    <MenuItem value="">{t('sweep2.none')}</MenuItem>
                    {(costCenters.data ?? []).map((cc) => (
                      <MenuItem key={String(cc.id)} value={Number(cc.id)}>
                        {String(cc.code ?? cc.name ?? cc.id)}
                      </MenuItem>
                    ))}
                  </CompactField>
                  {invoiceType !== 'NON_GST' ? (
                    <CompactField
                      label={t('billing.ecommerceGstin')}
                      value={ecommerceOperatorGstin}
                      onChange={(e) => setEcommerceOperatorGstin(e.target.value.toUpperCase())}
                      placeholder={t('billing.optionalSupecom')}
                      sx={{ minWidth: 180 }}
                    />
                  ) : null}
                </Stack>
                {invoiceType !== 'NON_GST' ? (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={isReverseCharge}
                          onChange={(e) => {
                            setIsReverseCharge(e.target.checked);
                            if (!e.target.checked) setConfirmSalesRcm(false);
                          }}
                        />
                      }
                      label={t('billing.salesReverseCharge')}
                    />
                    {isReverseCharge ? (
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={confirmSalesRcm}
                            onChange={(e) => setConfirmSalesRcm(e.target.checked)}
                          />
                        }
                        label={t('billing.confirmSalesRcm')}
                      />
                    ) : null}
                  </Stack>
                ) : null}
              </Stack>
            </Collapse>
            {showPaymentTerms ? (
              <Box
                sx={{
                  border: '1px dashed',
                  borderColor: 'divider',
                  borderRadius: 1,
                  p: 1.5,
                  position: 'relative',
                }}
              >
                <IconButton
                  size="small"
                  sx={{ position: 'absolute', top: 4, right: 4 }}
                  onClick={() => setShowPaymentTerms(false)}
                  aria-label={t('common.close')}
                >
                  ×
                </IconButton>
                <Typography variant="caption" color="text.secondary">
                  {t('billing.paymentDetails')}
                </Typography>
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <NumericField
                    label={t('billing.paymentTerms')}
                    value={paymentTermsDays}
                    onValueChange={(n) => setPaymentTermsDays(Math.max(0, Math.floor(n)))}
                    min={0}
                    emptyAs={0}
                    fullWidth
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">{t('billing.days')}</InputAdornment>
                      ),
                    }}
                  />
                  <CompactField
                    label={t('billing.dueDate')}
                    type="date"
                    value={dueDate}
                    onChange={(e) => {
                      setDueDateTouched(true);
                      setDueDate(e.target.value);
                    }}
                    InputLabelProps={{ shrink: true }}
                  />
                </Stack>
              </Box>
            ) : (
              <Link
                component="button"
                type="button"
                underline="hover"
                onClick={() => setShowPaymentTerms(true)}
              >
                + {t('billing.paymentDetails')}
              </Link>
            )}
          </Stack>
        </Stack>
      </Paper>

      <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
        {stockShortfalls.length > 0 && !isCompletedEdit ? (
          <Box id="stock-shortfall-alert">
            <HelpErrorAlert
              sx={{ m: 2 }}
              message="Insufficient stock (policy BLOCK). Reduce quantity or add stock before Complete:"
              code="insufficient_stock"
              invoiceId={isEdit ? editId ?? undefined : undefined}
            >
              {stockShortfalls.map((s) => (
                <Typography key={s.name} variant="body2" component="span" display="block">
                  {s.name}: available {s.available}, required {s.required}.
                </Typography>
              ))}
            </HelpErrorAlert>
          </Box>
        ) : null}
        <DraftLineTable
          availableByProduct={availableByProduct}
          blockNegativeStock={company.data?.negativeStockPolicy === 'BLOCK'}
          intraState={intraState}
          priceInclusive={priceMode === 'INCLUSIVE'}
          showItemPurchasePrice={showPurchasePrice && canSeeMargin}
          lines={
            preview.totals?.items && preview.totals.items.length === lines.length
              ? lines.map((line, i) => ({
                  ...line,
                  gstRate: preview.totals!.items![i].gstRate ?? line.gstRate,
                  rateNotice: preview.totals!.items![i].rateOverrideReason || line.rateNotice,
                }))
              : lines
          }
          taxes={
            preview.totals?.items && preview.totals.items.length === lineTaxes.length
              ? lineTaxes.map((tax, i) => {
                  const item = preview.totals!.items![i];
                  const gst = (item.cgst || 0) + (item.sgst || 0) + (item.igst || 0) + (item.cess || 0);
                  return {
                    ...tax,
                    taxableAmount: item.taxableAmount,
                    cgst: item.cgst,
                    sgst: item.sgst,
                    igst: item.igst,
                    cess: item.cess,
                    taxTotal: gst,
                    lineTotal: item.lineTotal,
                  };
                })
              : lineTaxes
          }
          showCess={invoiceType !== 'NON_GST'}
          qtyDisabled={isCompletedEdit}
          moneyDisabled={isCompletedEdit && !canAmendMoney}
          deleteDisabled={isCompletedEdit}
          showBatchSlot={showBatchCols || lines.some((line) => line.trackBatch)}
          showSerialSlot={lines.some((line) => line.trackSerial)}
          showSupplyNature={invoiceType !== 'NON_GST'}
          onUpdate={updateLine}
          onDelete={(key) => setLines((prev) => prev.filter((x) => x.key !== key))}
          onFocusAdd={() => barcodeRef.current?.focus()}
          renderBatchSlot={(line) => (
            <>
              <TableCell>
                {line.trackBatch ? (
                  <Autocomplete
                    size="small"
                    options={(batches.data ?? []).filter((lot) => Number(lot.product) === line.product)}
                    getOptionLabel={(lot) => `${lot.batchNo}${lot.expiryDate ? ` · exp ${lot.expiryDate}` : ''}`}
                    value={(batches.data ?? []).find((lot) => Number(lot.id) === line.batch) ?? null}
                    onChange={(_, lot) => updateLine(line.key, {
                      batch: lot ? Number(lot.id) : null,
                      batchNo: lot?.batchNo ?? '',
                    })}
                    renderInput={(params) => <TextField {...params} placeholder={t('sweep.fefoBatch')} helperText={t('sweep.fefoHelp')} />}
                  />
                ) : (
                  <CompactField value={line.batchNo} onChange={(e) => updateLine(line.key, { batchNo: e.target.value })} />
                )}
              </TableCell>
              <TableCell>
                <CompactField
                  type="date"
                  value={line.expDate}
                  onChange={(e) => updateLine(line.key, { expDate: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </TableCell>
              <TableCell>
                <CompactField
                  type="date"
                  value={line.mfgDate}
                  onChange={(e) => updateLine(line.key, { mfgDate: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </TableCell>
            </>
          )}
          renderSerialSlot={(line) => {
            const serialMismatch =
              Boolean(line.trackSerial) &&
              !serialCountMatchesQty(line.serialNumbersText, line.quantity);
            return (
            <TableCell>
              {line.trackSerial ? (
                <CompactField
                  id={`serial-input-${line.key}`}
                  inputProps={{ id: `serial-input-${line.key}` }}
                  multiline
                  minRows={1}
                  maxRows={3}
                  required
                  error={serialMismatch}
                  placeholder="SN-001, SN-002"
                  value={line.serialNumbersText ?? ''}
                  onChange={(e) => updateLine(line.key, { serialNumbersText: e.target.value })}
                  helperText={
                    serialMismatch
                      ? t('billing.completeDisabledMissingSerial', { name: line.productName })
                      : [
                          `${parseSerialNumbersText(line.serialNumbersText ?? '').length} serial(s)`,
                          parseSerialInput(line.serialNumbersText ?? '').duplicates.length
                            ? t('erp.serialDuplicatesDropped', {
                                count: parseSerialInput(line.serialNumbersText ?? '').duplicates.length,
                              })
                            : '',
                        ].filter(Boolean).join(' · ')
                  }
                />
              ) : null}
            </TableCell>
            );
          }}
        />


        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          sx={{ p: 1.5 }}
          alignItems="stretch"
        >
          <Box
            sx={{
              flex: 1,
              border: '1px dashed',
              borderColor: 'primary.light',
              borderRadius: 1,
              px: 2,
              py: 1.5,
              display: 'flex',
              alignItems: 'center',
              gap: 2,
            }}
          >
            <Stack spacing={1} sx={{ flex: 1 }}>
              <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
              <Autocomplete<Product>
              id="billing-item-input"
              sx={{ flex: 1 }}
              options={(
                (debouncedProductQuery.length >= 1 ? products.data : productCatalog.data?.results) ?? []
              )}
              filterOptions={(options, state) => filterProductsForPicker(options, state.inputValue)}
              loading={products.isFetching || productCatalog.isFetching}
              noOptionsText={t('common.noResults')}
              inputValue={productQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') setProductQuery(v);
              }}
              onChange={(_, v) => addProduct(v)}
              // Set inside the arrow-key handler itself, so an Enter that follows at once
              // already knows a row is chosen. The DOM attribute can lag behind it.
              onHighlightChange={(_, option) => {
                highlightedItem.current = option;
              }}
              disabled={isCompletedEdit}
              getOptionLabel={(o) =>
                `${formatProductOptionLabel(o, availableByProduct.get(Number(o.id)))}${
                  showPurchasePrice && canSeeMargin
                    ? ` · ${t('billing.itemPurchasePrice')} ${formatMoney(toNumber(o.purchasePrice))}`
                    : ''
                }`
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  inputRef={barcodeRef}
                  placeholder={`+ ${t('billing.addItem')} / ${t('billing.searchProduct')}`}
                  autoFocus
                  disabled={isCompletedEdit}
                  helperText={t('billing.scanEnterHint')}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter') return;
                    // Enter on a highlighted search row picks that item. A bare Enter is a barcode scan.
                    if (highlightedItem.current || (e.target as HTMLInputElement).getAttribute('aria-activedescendant')) return;
                    e.preventDefault();
                    e.stopPropagation();
                    const code = productQuery.trim();
                    if (!code) return;
                    // Clear now so the next scan starts on an empty box. Every scan keeps its
                    // own lookup; results are applied in scan order, none is dropped.
                    setProductQuery('');
                    const lookup = searchProducts(code).catch(() => null);
                    scanChain.current = scanChain.current.then(async () => {
                      const rows = await lookup;
                      if (rows == null) {
                        setError(t('billing.barcodeNotFound'));
                        return;
                      }
                      const q = code.toLowerCase();
                      const exact = rows.filter(
                        (p) =>
                          p.status === 'ACTIVE' &&
                          ((p.barcode ?? '').toLowerCase() === q || (p.sku ?? '').toLowerCase() === q),
                      );
                      if (exact.length === 1) addProduct(exact[0]);
                      else if (exact.length === 0) setError(t('billing.barcodeNotFound'));
                      else setError(t('billing.barcodeAmbiguous', { code }));
                    });
                  }}
                />
              )}
            />
            </Stack>
            <Link
              component="button"
              type="button"
              underline="hover"
              disabled={isCompletedEdit || !canCreateSales(user)}
              onClick={() => {
                if (isCompletedEdit || !canCreateSales(user)) return;
                setItemDialogError(null);
                setItemDialogOpen(true);
              }}
              sx={{ whiteSpace: 'nowrap' }}
            >
              + {t('billing.createItem')}
            </Link>
          </Box>
          <Button
            variant="outlined"
            startIcon={<QrCodeScannerIcon />}
            disabled={isCompletedEdit}
            onClick={() => barcodeRef.current?.focus()}
            sx={{ whiteSpace: 'nowrap' }}
          >
            {t('billing.scanBarcode')}
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ px: 2, pb: 1, display: 'block' }}>
          {t('billing.shortcutsBar')}
        </Typography>

        <Box
          sx={{
            px: 2,
            py: 1.5,
            bgcolor: 'action.hover',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 3,
            flexWrap: 'wrap',
          }}
        >
          <Typography fontWeight={700}>
            {t('billing.subtotal')} {formatMoney(shownTotals.subtotal)}
          </Typography>
          <Typography>
            {t('billing.tax')} {formatMoney(shownTotals.taxTotal)}
          </Typography>
          {shownTotals.cessTotal > 0 ? (
            <Typography>
              {t('billing.cess')} {formatMoney(shownTotals.cessTotal)}
            </Typography>
          ) : null}
          <Typography fontWeight={700}>
            {t('billing.totalAmount')} {formatMoney(shownTotals.grandTotal)}
          </Typography>
          {canSeeMargin && preview.totals?.estimatedMargin != null ? (
            <Tooltip
              title={
                <Stack spacing={0.5}>
                  <span>
                    {preview.totals.marginEstimatePartial
                      ? t('billing.estimatedMarginPartialHint')
                      : t('billing.estimatedMarginHint')}
                  </span>
                  {(preview.totals.marginLines ?? []).map((line) => (
                    <span key={`${line.productId}-${line.name}`}>
                      {line.name}
                      {line.missing || line.unitCost == null
                        ? `: ${t('billing.noCostYet')}`
                        : `: ${formatMoney(line.unitCost)} × ${line.quantity} = ${formatMoney(line.lineCost ?? 0)}`}
                    </span>
                  ))}
                </Stack>
              }
            >
              <Typography color="text.secondary">
                {preview.totals.marginEstimatePartial ? '~' : ''}
                {t('billing.estimatedMargin')} {formatMoney(preview.totals.estimatedMargin)}
                {preview.totals.estimatedMarginPercent != null
                  ? ` (${preview.totals.estimatedMarginPercent.toFixed(1)}%)`
                  : ''}
                {preview.totals.estimatedCogs != null
                  ? ` ${t('billing.estimatedMarginOnCost', { cost: formatMoney(preview.totals.estimatedCogs) })}`
                  : ''}
              </Typography>
            </Tooltip>
          ) : null}
          {isEdit && canSeeMargin ? (
            <Button size="small" variant="text" onClick={() => setProfitOpen(true)}>
              {t('invoiceDetail.profitDetails')}
            </Button>
          ) : null}
        </Box>
      </Paper>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems="flex-start">
        <Stack spacing={1} sx={{ flex: 1, minWidth: 220 }}>
          {!(showNotes || showTerms) ? (
            <Button
              variant="outlined"
              onClick={() => {
                setShowNotes(true);
                setShowTerms(true);
              }}
              sx={{ minHeight: 44, justifyContent: 'flex-start' }}
            >
              {t('billing.notesAndTerms')}
            </Button>
          ) : (
            <Stack spacing={1}>
              <CompactField
                label={t('billing.addNotes')}
                multiline
                minRows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <CompactField
                label={t('billing.addTerms')}
                multiline
                minRows={3}
                value={termsText}
                onChange={(e) => setTermsText(e.target.value)}
              />
            </Stack>
          )}

          {invoiceType !== 'NON_GST' ? (
            !showTcs ? (
              <Button
                variant="outlined"
                onClick={() => setShowTcs(true)}
                sx={{ minHeight: 44, justifyContent: 'flex-start' }}
              >
                {t('billing.tcsShow')}
              </Button>
            ) : (
              <Paper variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="subtitle2">{t('billing.tcsCollected')}</Typography>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }}>
                  <TextField size="small" label={t('billing.tdsSection')} value={tcsSection} onChange={(e) => setTcsSection(e.target.value)} placeholder="206C" />
                  <TextField size="small" type="number" label={t('billing.tdsRate')} inputProps={{ min: 0, max: 100, step: 0.01 }} value={tcsRate || ''} onChange={(e) => setTcsRate(Math.min(100, Math.max(0, Number(e.target.value) || 0)))} />
                  <TextField size="small" type="number" label={t('billing.tcsAmount')} inputProps={{ min: 0 }} value={tcsAmount || ''} onChange={(e) => { setTcsAmountManual(true); setTcsAmount(Math.max(0, Number(e.target.value) || 0)); }} />
                </Stack>
              </Paper>
            )
          ) : null}

          {!(showBank || showQr) ? (
            <Button
              variant="outlined"
              onClick={() => {
                setShowBank(true);
                setShowQr(true);
              }}
              sx={{ minHeight: 44, justifyContent: 'flex-start' }}
            >
              {t('billing.bankAndUpi')}
            </Button>
          ) : (
            <Stack spacing={1}>
              <Paper variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="subtitle2">{t('billing.bankDetails')}</Typography>
                {company.data?.bankName || company.data?.bankAccount ? (
                  <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>
                    {[
                      company.data.bankName,
                      company.data.bankAccount ? `A/C ${company.data.bankAccount}` : null,
                      company.data.bankIfsc ? `IFSC ${company.data.bankIfsc}` : null,
                    ]
                      .filter(Boolean)
                      .join('\n')}
                  </Typography>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t('billing.noBankConfigured')}{' '}
                    <Link component={RouterLink} to="/settings/company">
                      {t('sweep2.company')}
                    </Link>
                  </Typography>
                )}
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="subtitle2">{t('billing.paymentQr')}</Typography>
                {company.data?.upiId ? (
                  <Typography variant="body2">UPI: {company.data.upiId}</Typography>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t('billing.noUpiConfigured')}
                  </Typography>
                )}
              </Paper>
            </Stack>
          )}
        </Stack>

        {activeCustomFieldDefs(company.data?.invoiceCustomFieldDefs).map((def) => (
          <TextField
            key={def.key}
            size="small"
            label={def.label}
            value={invoiceCustomFields[def.key] ?? ''}
            onChange={(e) =>
              setInvoiceCustomFields((prev) => ({ ...prev, [def.key]: e.target.value }))
            }
          />
        ))}

        <DocumentTaxSummary
          totals={shownTotals}
          additionalCharges={additionalCharges}
          onAdditionalChargesChange={setAdditionalCharges}
          chargesHsn={chargesHsn}
          onChargesHsnChange={setChargesHsn}
          chargesGstRate={chargesGstRate}
          onChargesGstRateChange={setChargesGstRate}
          invoiceDiscount={invoiceDiscount}
          onInvoiceDiscountChange={setInvoiceDiscount}
          invoiceDiscountMode={invoiceDiscountMode}
          onInvoiceDiscountModeChange={setInvoiceDiscountMode}
          blockAfterTaxDiscount={blockAfterTaxDiscount}
          autoRoundOff={autoRoundOff}
          onAutoRoundOffChange={setAutoRoundOff}
          posKnown={posKnown}
          isCompletedEdit={isCompletedEdit}
          canAmendMoney={canAmendMoney}
          extraAlerts={
            rcmDisplay ? (
              <Alert severity="info">
                Reverse charge: tax liability {formatMoney(rcmDisplay.rcmTaxTotal)} (CGST{' '}
                {formatMoney(rcmDisplay.rcmCgst)}, SGST {formatMoney(rcmDisplay.rcmSgst)}, IGST{' '}
                {formatMoney(rcmDisplay.rcmIgst)}). Receivable (excl. tax):{' '}
                {formatMoney(rcmDisplay.payable)}.
              </Alert>
            ) : null
          }
        >
            {canTakePayment ? (
            <>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography>{t('billing.amountReceived')}</Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={markFullyPaid}
                    onChange={(e) => {
                      setMarkFullyPaid(e.target.checked);
                      if (e.target.checked) setAmountReceived(amountDueNow);
                    }}
                    size="small"
                  />
                }
                label={t('billing.markFullyPaid')}
              />
            </Stack>
            <FormControlLabel
              control={
                <Checkbox
                  checked={autoPrint}
                  onChange={(e) => {
                    setAutoPrint(e.target.checked);
                    try {
                      localStorage.setItem('bizboard.invoiceAutoPrint', e.target.checked ? '1' : '0');
                    } catch {
                      // The choice still applies for this visit.
                    }
                  }}
                  size="small"
                />
              }
              label={t('billing.autoPrint')}
            />
            <Stack direction="row" spacing={1}>
              <NumericField
                value={amountReceived}
                onValueChange={(n) => {
                  setMarkFullyPaid(false);
                  setAmountReceived(n);
                }}
                min={0}
                // Cash may be more than the bill; the difference is change.
                // Card, UPI, bank, and cheque cannot exceed the amount due.
                max={paymentMode === 'CASH' ? undefined : amountDueNow}
                decimals={2}
                placeholder={t('billing.enterPaymentAmount')}
                inputProps={{ 'aria-label': t('billing.amountReceived') }}
                InputProps={{
                  startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                }}
              />
              <CompactField
                select
                value={paymentMode}
                onChange={(e) => {
                  const next = e.target.value as PaymentMode;
                  setPaymentMode(next);
                  if (next !== 'CASH' && amountReceived > amountDueNow) {
                    setAmountReceived(amountDueNow);
                  }
                }}
                sx={{ maxWidth: 120 }}
                SelectProps={{ SelectDisplayProps: { 'aria-label': t('billing.paymentMode') } as HTMLAttributes<HTMLDivElement> }}
              >
                <MenuItem value="CASH">{t('sweep2.cash')}</MenuItem>
                <MenuItem value="UPI">UPI</MenuItem>
                <MenuItem value="BANK">{t('sweep2.bank')}</MenuItem>
                <MenuItem value="CARD">{t('sweep2.card')}</MenuItem>
                <MenuItem value="CREDIT">{t('sweep2.credit')}</MenuItem>
                <MenuItem value="CHEQUE">{t('sweep2.cheque')}</MenuItem>
              </CompactField>
            </Stack>
            {paymentMode === 'CHEQUE' ? <ChequePaymentFields value={cheque} onChange={setCheque} /> : null}
            {cashChange > 0 ? (
              <>
                <Typography sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t('billing.cashTendered')}</span>
                  <span>{formatMoney(amountReceived)}</span>
                </Typography>
                <Typography sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t('billing.amountApplied')}</span>
                  <span>{formatMoney(Math.min(amountReceived, amountDueNow))}</span>
                </Typography>
                <Typography sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t('billing.changeGiven')}</span>
                  <span>{formatMoney(cashChange)}</span>
                </Typography>
              </>
            ) : null}
            <Typography
              fontWeight={700}
              color={balance <= 0 ? 'success.main' : 'text.primary'}
              sx={{ display: 'flex', justifyContent: 'space-between' }}
            >
              <span>{t('billing.balanceAmount')}</span>
              <span>{formatMoney(balance)}</span>
            </Typography>
            </>
            ) : (
            <Typography
              fontWeight={700}
              sx={{ display: 'flex', justifyContent: 'space-between' }}
            >
              <span>{t('billing.balanceAmount')}</span>
              <span>{formatMoney(amountDueNow)}</span>
            </Typography>
            )}

            <Divider />
            <Typography variant="body2" color="text.secondary">
              {t('billing.authorizedSignatory')} <strong>{company.data?.name ?? '…'}</strong>
            </Typography>
            <Box
              sx={{
                border: '1px dashed',
                borderColor: 'primary.light',
                borderRadius: 1,
                p: 2,
                textAlign: 'center',
                minHeight: 72,
              }}
            >
              {signatureUrl ? (
                <Box
                  component="img"
                  src={signatureUrl}
                  alt="Signature"
                  sx={{ maxHeight: 64, maxWidth: '100%' }}
                />
              ) : (
                <Link
                  component="button"
                  type="button"
                  underline="hover"
                  onClick={() => fileInputRef.current?.click()}
                >
                  + {t('billing.addSignature')}
                </Link>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => void onSignaturePick(e.target.files?.[0] ?? null)}
              />
            </Box>
        </DocumentTaxSummary>
      </Stack>

      </>
      )}
      <ProfitDetailsDialog
        invoiceId={isEdit && editId ? editId : null}
        open={profitOpen}
        onClose={() => setProfitOpen(false)}
      />
      <ShareInvoiceDialog
        open={shareAfterSave}
        invoiceId={savedForShare?.id ?? null}
        onClose={() => setShareAfterSave(false)}
      />
      <Dialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('billing.shortcutsTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('billing.shortcuts')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShortcutsOpen(false)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

      <InvoiceQuickSettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        showBatchCols={showBatchCols}
        onShowBatchColsChange={setShowBatchCols}
        showPurchasePrice={showPurchasePrice}
        onShowPurchasePriceChange={(next) => {
          setShowPurchasePrice(next);
          try {
            localStorage.setItem(SHOW_PURCHASE_PRICE_KEY, next ? '1' : '0');
          } catch {
            // ignore
          }
        }}
      />

      {canSave && !canComplete && completeDisabledReason ? (
        <Paper
          elevation={2}
          sx={{
            p: 1.5,
            mb: 1,
            bgcolor: 'warning.light',
            border: '1px solid',
            borderColor: 'warning.main',
            borderRadius: 1,
          }}
        >
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems="center" spacing={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <WarningAmberIcon color="warning" />
              <Typography variant="body2" fontWeight={600}>
                {completeDisabledReason}
              </Typography>
            </Stack>
            {renderBlockerFocusButton()}
          </Stack>
        </Paper>
      ) : null}

      <Dialog
        open={itemDialogOpen}
        onClose={() => {
          setItemDialogOpen(false);
          setItemDialogError(null);
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('billing.createItem')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {itemDialogError ? (
              <HelpErrorAlert message={itemDialogError} error={itemDialogErrorSource} />
            ) : null}
            <TextField
              required
              label={t('common.name')}
              value={itemForm.name}
              onChange={(e) => setItemForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('products.skuRequired')}
              value={itemForm.sku}
              onChange={(e) => setItemForm((f) => ({ ...f, sku: e.target.value }))}
              helperText={t('billing.skuMustBeUnique')}
              required
            />
            <TextField
              select
              label={t('products.unit')}
              value={itemForm.unitName}
              onChange={(e) => setItemForm((f) => ({ ...f, unitName: e.target.value }))}
            >
              {['PCS', 'BOX', 'KG', 'MTR', 'LTR', 'NOS', 'PKT', 'SET'].map((u) => (
                <MenuItem key={u} value={u}>
                  {u}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('billing.hsn')}
              value={itemForm.hsnCode}
              onChange={(e) => setItemForm((f) => ({ ...f, hsnCode: e.target.value }))}
              error={Boolean(itemForm.hsnCode) && !isValidHsnSac(itemForm.hsnCode)}
              helperText={
                Boolean(itemForm.hsnCode) && !isValidHsnSac(itemForm.hsnCode)
                  ? t('billing.hsnSacDigits')
                  : undefined
              }
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label={t('billing.sellingPrice')}
                type="number"
                fullWidth
                value={itemForm.sellingPrice}
                onChange={(e) => setItemForm((f) => ({ ...f, sellingPrice: e.target.value }))}
              />
              {showPurchasePrice && canSeeMargin ? (
                <TextField
                  label={t('billing.itemPurchasePrice')}
                  type="number"
                  fullWidth
                  value={itemForm.purchasePrice}
                  onChange={(e) => setItemForm((f) => ({ ...f, purchasePrice: e.target.value }))}
                />
              ) : null}
              <TextField
                label={t('items.mrp')}
                type="number"
                fullWidth
                value={itemForm.mrp}
                onChange={(e) => setItemForm((f) => ({ ...f, mrp: e.target.value }))}
              />
              <TextField
                label={t('products.gstPercent')}
                type="number"
                fullWidth
                value={itemForm.gstRate}
                onChange={(e) => setItemForm((f) => ({ ...f, gstRate: e.target.value }))}
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            type="button"
            onClick={() => {
              setItemDialogOpen(false);
              setItemDialogError(null);
            }}
          >
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            variant="contained"
            disabled={
              !itemForm.name.trim() ||
              !itemForm.sku.trim() ||
              itemMutation.isPending ||
              (Boolean(itemForm.hsnCode) && !isValidHsnSac(itemForm.hsnCode))
            }
            onClick={() => {
              setItemDialogError(null);
              itemMutation.mutate();
            }}
          >
            {t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(priceDrift)} onClose={() => setPriceDrift(null)}>
        <DialogTitle>{t('billing.priceDriftTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={0.5} sx={{ mt: 1 }}>
            {priceDrift?.drifts.map((row) => (
              <Typography key={`${row.name}-${row.from}`} variant="body2">
                {row.name}: {row.from} → {row.to}
              </Typography>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              if (!priceDrift) return;
              setLines(priceDrift.lines);
              if (priceDrift.customerId) setCustomerId(priceDrift.customerId);
              setDeviceDraft(null);
              setPriceDrift(null);
            }}
          >
            {t('billing.keepDraftPrices')}
          </Button>
          <Button
            variant="contained"
            onClick={() => {
              if (!priceDrift) return;
              setLines(priceDrift.updated.map((line) => recomputeLine(line, intraState)));
              if (priceDrift.customerId) setCustomerId(priceDrift.customerId);
              setDeviceDraft(null);
              setPriceDrift(null);
            }}
          >
            {t('billing.updateCurrentPrices')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={amendConfirm != null} onClose={() => setAmendConfirm(null)} aria-labelledby="amend-confirm-title">
        <DialogTitle id="amend-confirm-title">{t('billing.amendCompletedTitle')}</DialogTitle>
        <DialogContent>
          <Typography>{t('billing.confirmAmendCompleted')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAmendConfirm(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            autoFocus
            onClick={() => {
              const mode = amendConfirm;
              setAmendConfirm(null);
              if (!mode) return;
              amendConfirmedRef.current = true;
              saveMutation.mutate(mode);
            }}
          >
            {t('billing.amendCompletedConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={reauthOpen} onClose={() => setReauthOpen(false)}>
        <DialogTitle>{t('billing.signInToContinue')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1, minWidth: 280 }}>
            <TextField label={t('auth.email')} value={reauthEmail} onChange={(e) => setReauthEmail(e.target.value)} />
            <TextField label={t('auth.password')} type="password" value={reauthPassword} onChange={(e) => setReauthPassword(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReauthOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => {
              void login(reauthEmail, reauthPassword).then(() => {
                setReauthOpen(false);
                setReauthPassword('');
              }).catch((err) => setError(getErrorMessage(err)));
            }}
          >
            {t('auth.login')}
          </Button>
        </DialogActions>
      </Dialog>
      </Stack>
    </DocumentEditorShell>
  );
}


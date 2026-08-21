import { useEffect, useMemo, useRef, useState } from 'react';
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
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TableCell from '@mui/material/TableCell';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import Alert from '@mui/material/Alert';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import {
  completePurchase,
  createAllocation,
  createProduct,
  createPurchase,
  createSupplier,
  createSupplierPayment,
  getCompany,
  getPurchase,
  getPurchaseNumberSeries,
  getSupplier,
  listSuppliersPage,
  listPurchasesPage,
  listBatches,
  listCostCenters,
  searchProducts,
  listStock,
  listWarehouses,
  updateCompany,
  updatePurchase,
  updateSupplier,
  uploadFile,
} from '@/api/resources';
import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import { isValidGstin, isValidHsnSac } from '@/utils/gst';
import { useAuth } from '@/auth/AuthContext';
import {
  clearPurchaseDraft,
  loadPurchaseDraft,
  OUTBOX_PLAINTEXT_WARNING,
  OUTBOX_WARNING_DISMISS_KEY,
  savePurchaseDraft,
} from '@/offline/invoiceDraftCache';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { DocumentTaxSummary } from '@/components/DocumentTaxSummary';
import { PartySelectPanel } from '@/components/PartySelectPanel';
import { StateSelect } from '@/components/StateSelect';
import { t } from '@/i18n';
import type { PaymentMode, PriceMode, Product, PurchaseInvoice, PurchaseType } from '@/types/domain';
import { formatMoney, roundMoney, toNumber } from '@/utils/money';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { canImport } from '@/utils/permissions';
import {
  addDaysIso,
  calculateInvoiceTotals,
  calculateLineTax,
  extractExclusiveFromInclusiveLine,
  isIntraState,
  placeOfSupplyKnown,
  type InvoiceDiscountMode,
} from '@/utils/tax';

import {
  CompactField,
  DocumentEditorShell,
  DraftLineTable,
  formatSerialNumbersText,
  makeLine as makeLineBase,
  NumericField,
  parseSerialNumbersText,
  primarySaveAction,
  recomputeLine,
  todayIso,
  useBillingSaveFeedback,
  useDebouncedValue,
  type DraftLine,
} from '@/components/billing';

const COL_PREFS_KEY = 'bizboard.billing.batchCols';

function makeLine(
  product: Parameters<typeof makeLineBase>[0],
  intraState: boolean | null,
  quantity = 1,
): DraftLine {
  return makeLineBase(product, intraState, quantity, 'purchasePrice');
}

export function NewPurchasePage() {
  const { user } = useAuth();
  const isOwner = user?.role === 'OWNER';
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const barcodeRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const skipAutosaveRef = useRef(false);
  const [offline, setOffline] = useState(
    typeof navigator !== 'undefined' ? !navigator.onLine : false,
  );
  const [pendingDraft, setPendingDraft] = useState<{
    savedAt: string;
    payload: Record<string, unknown>;
  } | null>(null);
  const [hasLocalDraft, setHasLocalDraft] = useState(false);
  const [hideOutboxWarn, setHideOutboxWarn] = useState(
    () =>
      typeof localStorage !== 'undefined' &&
      localStorage.getItem(OUTBOX_WARNING_DISMISS_KEY) === '1',
  );

  const [lines, setLines] = useState<DraftLine[]>([]);
  const [productQuery, setProductQuery] = useState('');
  const debouncedProductQuery = useDebouncedValue(productQuery, 300);
  const {
    message,
    error,
    setError,
    clearFeedback,
    flashSaveAndNew,
    flashError,
    flashWarning,
  } = useBillingSaveFeedback();
  const [editingStatus, setEditingStatus] = useState<PurchaseInvoice['status'] | null>(null);
  const [loadedEdit, setLoadedEdit] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const [supplierId, setSupplierId] = useState<number | ''>('');
  const [supplierQuery, setSupplierQuery] = useState('');
  const debouncedSupplierQuery = useDebouncedValue(supplierQuery, 300);
  const [warehouseId, setWarehouseId] = useState<number | ''>('');
  const [costCenterId, setCostCenterId] = useState<number | ''>('');
  const [purchaseType, setPurchaseType] = useState<PurchaseType>('GST');
  const [priceMode, setPriceMode] = useState<PriceMode>('EXCLUSIVE');
  const [isReverseCharge, setIsReverseCharge] = useState(false);
  const [itcEligibility, setItcEligibility] = useState<'CLAIMABLE' | 'INELIGIBLE' | 'REVERSED'>('CLAIMABLE');
  const [supplierBillNumber, setSupplierBillNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(todayIso());
  const [paymentTermsDays, setPaymentTermsDays] = useState(30);
  const [dueDate, setDueDate] = useState(() => addDaysIso(todayIso(), 30));
  const [showPaymentTerms, setShowPaymentTerms] = useState(true);

  // BUG-502/514: prefix/nextNumber are read-only display-only previews, same
  // as the Sales invoice form — this field used to be live-editable here and,
  // if touched, would permanently reassign the company's purchase numbering
  // sequence via updatePurchaseNumberSeries on save.
  const [prefix, setPrefix] = useState('PUR');
  const [nextNumber, setNextNumber] = useState(1);

  const [notes, setNotes] = useState('');
  const [termsText, setTermsText] = useState('');
  const [showNotes, setShowNotes] = useState(false);
  const [showTerms, setShowTerms] = useState(true);
  const [showBank, setShowBank] = useState(false);
  const [showQr, setShowQr] = useState(false);
  const [showTds, setShowTds] = useState(false);
  const [tdsSection, setTdsSection] = useState('');
  const [tdsRate, setTdsRate] = useState(0);
  const [tdsAmount, setTdsAmount] = useState(0);

  const [additionalCharges, setAdditionalCharges] = useState(0);
  const [invoiceDiscount, setInvoiceDiscount] = useState(0);
  const [invoiceDiscountMode, setInvoiceDiscountMode] = useState<InvoiceDiscountMode>('AFTER_TAX');
  const [autoRoundOff, setAutoRoundOff] = useState(true);
  const [amountPaid, setAmountPaid] = useState(0);
  const [paymentMode, setPaymentMode] = useState<PaymentMode>('CASH');
  const [markFullyPaid, setMarkFullyPaid] = useState(false);

  const [showBatchCols, setShowBatchCols] = useState(() => {
    try {
      return localStorage.getItem(COL_PREFS_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [partyDialogOpen, setPartyDialogOpen] = useState(false);
  const [itemDialogOpen, setItemDialogOpen] = useState(false);
  const [itemDialogError, setItemDialogError] = useState<string | null>(null);
  const [partyForm, setPartyForm] = useState<{
    id?: number;
    name: string;
    phone: string;
    gstin: string;
    state: string;
  }>({ name: '', phone: '', gstin: '', state: '' });
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [itemForm, setItemForm] = useState({
    name: '',
    sku: '',
    hsnCode: '',
    purchasePrice: '',
    mrp: '',
    gstRate: '18',
  });
  const [signatureUrl, setSignatureUrl] = useState<string | null>(null);
  const [signatureId, setSignatureId] = useState<number | null>(null);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const suppliers = useQuery({
    queryKey: ['suppliers-search', debouncedSupplierQuery],
    queryFn: () => listSuppliersPage({ q: debouncedSupplierQuery, pageSize: 50 }),
    enabled: debouncedSupplierQuery.trim().length >= 2,
  });
  const selectedSupplierQuery = useQuery({
    queryKey: ['supplier', supplierId],
    queryFn: () => getSupplier(supplierId as number),
    enabled: Boolean(supplierId),
  });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const costCenters = useQuery({ queryKey: ['cost-centers'], queryFn: listCostCenters });
  const batches = useQuery({ queryKey: ['batches'], queryFn: () => listBatches() });
  const series = useQuery({
    queryKey: ['purchase-invoice-number-series'],
    queryFn: getPurchaseNumberSeries,
    enabled: !isEdit,
  });
  const existingInvoice = useQuery({
    queryKey: ['purchase-invoice', editId],
    queryFn: () => getPurchase(editId as number),
    enabled: isEdit,
  });
  const products = useQuery({
    queryKey: ['product-search', debouncedProductQuery],
    queryFn: () => searchProducts(debouncedProductQuery),
    enabled: debouncedProductQuery.length >= 1,
  });
  const stockBalances = useQuery({
    queryKey: ['stock'],
    queryFn: listStock,
    staleTime: 60_000,
  });
  const availableByProduct = useMemo(() => {
    const map = new Map<number, number>();
    for (const s of stockBalances.data ?? []) {
      const id = Number(s.product);
      map.set(id, (map.get(id) ?? 0) + toNumber(s.available ?? s.onHand));
    }
    return map;
  }, [stockBalances.data]);

  useEffect(() => {
    if (!series.data || isEdit) return;
    setPrefix(series.data.prefix);
    setNextNumber(series.data.nextNumber);
  }, [series.data, isEdit]);

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

  // FE-08: offer restore of local purchase draft on mount (new documents only).
  useEffect(() => {
    if (isEdit || !companyId || !userId) return;
    void (async () => {
      const draft = await loadPurchaseDraft(companyId, userId);
      if (!draft?.payload) return;
      const p = draft.payload;
      const draftLines = (p.lines as DraftLine[] | undefined) ?? [];
      if (!draftLines.length && !p.supplierId) return;
      setPendingDraft({ savedAt: draft.savedAt, payload: p });
      setHasLocalDraft(true);
    })();
  }, [isEdit, companyId, userId]);

  // FE-08: autosave purchase editor draft (debounced).
  useEffect(() => {
    if (isEdit || !companyId || !userId || skipAutosaveRef.current) return;
    if (!lines.length && !supplierId) return;
    const timer = window.setTimeout(() => {
      void savePurchaseDraft(companyId, userId, {
        supplierId,
        purchaseType,
        priceMode,
        invoiceDate,
        supplierBillNumber,
        notes,
        lines,
        additionalCharges,
        invoiceDiscount,
        invoiceDiscountMode,
      }).then(() => setHasLocalDraft(true));
    }, 600);
    return () => window.clearTimeout(timer);
  }, [
    isEdit,
    companyId,
    userId,
    supplierId,
    purchaseType,
    priceMode,
    invoiceDate,
    supplierBillNumber,
    notes,
    lines,
    additionalCharges,
    invoiceDiscount,
    invoiceDiscountMode,
  ]);

  useEffect(() => {
    setLoadedEdit(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (!existingInvoice.data || loadedEdit) return;
    const inv = existingInvoice.data;
    if (inv.status === 'CANCELLED') {
      setError('This purchase cannot be edited.');
      // BUG-517: without this, an unrelated cache invalidation (e.g. of
      // `suppliers`) while this page stays mounted re-runs this effect and
      // re-fires setError, unlike the equivalent Sales branch.
      setLoadedEdit(true);
      return;
    }
    setEditingStatus(inv.status);
    setSupplierId(inv.supplier);
    setWarehouseId(inv.warehouse ?? '');
    setCostCenterId(inv.costCenter ?? '');
    setPurchaseType(inv.purchaseType);
    setPriceMode((inv.priceMode as PriceMode) || 'EXCLUSIVE');
    setIsReverseCharge(!!inv.isReverseCharge);
    setItcEligibility(inv.itcEligibility ?? 'CLAIMABLE');
    setSupplierBillNumber(inv.supplierBillNumber ?? '');
    setInvoiceDate(inv.invoiceDate);
    setPaymentTermsDays(inv.paymentTermsDays ?? 0);
    setDueDate(inv.dueDate ?? addDaysIso(inv.invoiceDate, inv.paymentTermsDays ?? 0));
    setShowPaymentTerms(Boolean(inv.dueDate || inv.paymentTermsDays));
    setNotes(inv.notes ?? '');
    setShowNotes(Boolean(inv.notes));
    setTermsText(inv.termsText ?? '');
    setShowTerms(Boolean(inv.includeTerms || inv.termsText));
    setShowBank(Boolean(inv.includeBankDetails));
    setShowQr(Boolean(inv.includePaymentQr));
    setAdditionalCharges(toNumber(inv.additionalCharges));
    setInvoiceDiscount(toNumber(inv.invoiceDiscount));
    setInvoiceDiscountMode((inv.invoiceDiscountMode as InvoiceDiscountMode) || 'AFTER_TAX');
    setTdsSection(inv.tdsSection ?? '');
    setTdsRate(toNumber(inv.tdsRate));
    setTdsAmount(toNumber(inv.tdsAmount));
    setShowTds(Boolean(inv.tdsSection || toNumber(inv.tdsAmount)));
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
    const selected = selectedSupplierQuery.data;
    const partyState =
      (selected && selected.id === inv.supplier
        ? selected.gstin || selected.state
        : '') || '';
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
        batchNo: item.batchNo ?? '',
        batch: item.batch ?? null,
        trackBatch: Boolean(
          (products.data ?? []).find((p) => p.id === item.product)?.trackBatch ?? item.batch,
        ),
        trackSerial: Boolean(
          (products.data ?? []).find((p) => p.id === item.product)?.trackSerial
            ?? (item as { serialNumbers?: string[] }).serialNumbers?.length,
        ),
        serialNumbersText: formatSerialNumbersText((item as { serialNumbers?: string[] }).serialNumbers),
        expDate: item.expDate ?? '',
        mfgDate: item.mfgDate ?? '',
        mrp: toNumber(item.mrp),
        quantity: qty,
        unitPrice,
        gstRate,
        cessRate,
        ...tax,
      };
    });
    setLines(mapped);
    setLoadedEdit(true);
  }, [existingInvoice.data, loadedEdit, company.data?.gstin, company.data?.state, selectedSupplierQuery.data, products.data]);

  useEffect(() => {
    if (!isEdit && !warehouseId) {
      const defaultWarehouse = warehouses.data?.find((warehouse) => warehouse.isDefault);
      if (defaultWarehouse) setWarehouseId(defaultWarehouse.id);
    }
  }, [isEdit, warehouseId, warehouses.data]);

  useEffect(() => {
    if (company.data?.signature) {
      setSignatureId(company.data.signature);
    }
  }, [company.data, isEdit]);

  useEffect(() => {
    if (isEdit || termsText) return;
    setTermsText(
      '1. Goods received are subject to inspection and approval.\n2. Payment as per agreed terms.\n3. All disputes are subject to local jurisdiction.',
    );
  }, [isEdit, termsText]);

  useEffect(() => {
    setDueDate(addDaysIso(invoiceDate, paymentTermsDays || 0));
  }, [invoiceDate, paymentTermsDays]);

  useEffect(() => {
    try {
      localStorage.setItem(COL_PREFS_KEY, showBatchCols ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [showBatchCols]);

  const selectedSupplier = selectedSupplierQuery.data ?? null;
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedSupplier?.gstin || selectedSupplier?.state,
    { assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty },
  );

  const lineTaxes = useMemo(
    () =>
      lines.map((l) => {
        const gstRate = purchaseType === 'NON_GST' ? 0 : l.gstRate;
        let unitPrice = l.unitPrice;
        if (priceMode === 'INCLUSIVE' && gstRate > 0) {
          unitPrice = extractExclusiveFromInclusiveLine({
            quantity: l.quantity,
            unitPriceInclusive: l.unitPrice,
            discountPercent: l.discountPercent,
            gstRate,
          }).exclusiveUnitPrice;
          return calculateLineTax({
            quantity: l.quantity,
            unitPrice,
            discountPercent: 0,
            gstRate,
            cessRate: purchaseType === 'NON_GST' ? 0 : l.cessRate ?? 0,
            intraState,
          });
        }
        return calculateLineTax({
          quantity: l.quantity,
          unitPrice,
          discountPercent: l.discountPercent,
          gstRate,
          cessRate: purchaseType === 'NON_GST' ? 0 : l.cessRate ?? 0,
          intraState,
        });
      }),
    [lines, intraState, purchaseType, priceMode],
  );

  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((l, i) => ({
          ...l,
          gstRate: purchaseType === 'NON_GST' ? 0 : lines[i]?.gstRate ?? 0,
          cessRate: purchaseType === 'NON_GST' ? 0 : lines[i]?.cessRate ?? 0,
          intraState,
        })),
        {
          additionalCharges,
          invoiceDiscount,
          applyRoundOff: autoRoundOff,
          invoiceDiscountMode,
        },
      ),
    [lineTaxes, lines, additionalCharges, invoiceDiscount, autoRoundOff, invoiceDiscountMode, intraState, purchaseType],
  );

  const rcmPreview = useMemo(() => {
    if (!isReverseCharge || purchaseType === 'NON_GST') return null;
    const charges = roundMoney(additionalCharges);
    const discount = roundMoney(invoiceDiscount);
    const taxable = totals.taxableTotal;
    const rawPayable =
      invoiceDiscountMode === 'BEFORE_TAX'
        ? roundMoney(taxable + charges)
        : roundMoney(taxable + charges - discount);
    const clamped = Math.max(0, rawPayable);
    const payable = autoRoundOff ? Math.round(clamped) : roundMoney(clamped);
    return {
      rcmTaxable: totals.taxableTotal,
      rcmTaxTotal: totals.taxTotal,
      rcmCgst: totals.cgstTotal,
      rcmSgst: totals.sgstTotal,
      rcmIgst: totals.igstTotal,
      payable,
    };
  }, [
    isReverseCharge,
    purchaseType,
    totals,
    additionalCharges,
    invoiceDiscount,
    invoiceDiscountMode,
    autoRoundOff,
  ]);

  // BUG-508/421: mirrors NewInvoicePage's posKnown gate — without it, a
  // purchase from a supplier with no state/GSTIN on file silently defaults
  // to intra-state CGST/SGST with no warning, risking incorrect ITC.
  const posKnown =
    purchaseType === 'NON_GST' ||
    !company.data?.isGstRegistered ||
    company.data?.assumeLocalStateForBlankParty ||
    placeOfSupplyKnown(selectedSupplier?.state, selectedSupplier?.gstin);

  const displayGrandTotal = rcmPreview?.payable ?? totals.grandTotal;

  const balance = roundMoney(Math.max(0, displayGrandTotal - amountPaid));

  useEffect(() => {
    if (markFullyPaid) setAmountPaid(displayGrandTotal);
  }, [markFullyPaid, displayGrandTotal]);

  const resetForm = () => {
    // BUG-501 / P0-311: do NOT call clearFeedback here — Save & New sets the
    // success flash then resets fields in the same tick. See useBillingSaveFeedback.
    setIdempotencyKey(null);
    setLines([]);
    setSupplierId('');
    setWarehouseId(warehouses.data?.find((warehouse) => warehouse.isDefault)?.id ?? '');
    setCostCenterId('');
    setPurchaseType('GST');
    setPriceMode('EXCLUSIVE');
    setIsReverseCharge(false);
    setItcEligibility('CLAIMABLE');
    setSupplierBillNumber('');
    setInvoiceDate(todayIso());
    setPaymentTermsDays(30);
    setNotes('');
    setShowNotes(false);
    setShowTerms(true);
    setShowBank(false);
    setShowQr(false);
    setAdditionalCharges(0);
    setInvoiceDiscount(0);
    setAmountPaid(0);
    setMarkFullyPaid(false);
    setPaymentMode('CASH');
    if (companyId && userId) {
      void clearPurchaseDraft(companyId, userId).then(() => setHasLocalDraft(false));
    }
    void qc.invalidateQueries({ queryKey: ['purchase-invoice-number-series'] });
    barcodeRef.current?.focus();
  };

  const applyPendingDraft = () => {
    if (!pendingDraft) return;
    const p = pendingDraft.payload;
    skipAutosaveRef.current = true;
    if (p.supplierId) setSupplierId(Number(p.supplierId));
    if (p.purchaseType) setPurchaseType(p.purchaseType as PurchaseType);
    if (p.priceMode) setPriceMode(p.priceMode as PriceMode);
    if (typeof p.invoiceDate === 'string') setInvoiceDate(p.invoiceDate);
    if (typeof p.supplierBillNumber === 'string') setSupplierBillNumber(p.supplierBillNumber);
    if (typeof p.notes === 'string') setNotes(p.notes);
    if (Array.isArray(p.lines)) setLines(p.lines as DraftLine[]);
    if (typeof p.additionalCharges === 'number') setAdditionalCharges(p.additionalCharges);
    if (typeof p.invoiceDiscount === 'number') setInvoiceDiscount(p.invoiceDiscount);
    if (p.invoiceDiscountMode) setInvoiceDiscountMode(p.invoiceDiscountMode as InvoiceDiscountMode);
    setPendingDraft(null);
    window.setTimeout(() => {
      skipAutosaveRef.current = false;
    }, 800);
  };

  const buildPayload = () => ({
    supplier: Number(supplierId),
    warehouse: warehouseId ? Number(warehouseId) : undefined,
    costCenter: costCenterId ? Number(costCenterId) : undefined,
    purchaseType,
    priceMode,
    isReverseCharge,
    itcEligibility,
    invoiceDate,
    dueDate,
    paymentTermsDays,
    additionalCharges,
    invoiceDiscount,
    invoiceDiscountMode,
    autoRoundOff,
    supplierBillNumber,
    notes,
    termsText: showTerms ? termsText : '',
    includeBankDetails: showBank,
    includePaymentQr: showQr,
    includeTerms: showTerms,
    signature: signatureId,
    ...(isRuntimeFlagEnabled('ENABLE_TDS')
      ? { tdsSection, tdsRate, tdsAmount }
      : {}),
    items: lines.map((l) => ({
      ...(l.lineId != null ? { id: l.lineId } : {}),
      product: l.product,
      description: l.description || l.productName,
      quantity: l.quantity,
      unitPrice: priceMode === 'INCLUSIVE' ? undefined : l.unitPrice,
      unitPriceInclusive: priceMode === 'INCLUSIVE' ? l.unitPrice : undefined,
      discountPercent: l.discountPercent,
      gstRate: purchaseType === 'NON_GST' ? 0 : l.gstRate,
      cessRate: purchaseType === 'NON_GST' ? 0 : l.cessRate ?? 0,
      batch: l.batch ?? undefined,
      batchNo: l.batchNo || undefined,
      expDate: l.expDate || null,
      mfgDate: l.mfgDate || null,
      ...(l.trackSerial && l.serialNumbersText?.trim()
        ? { serialNumbers: parseSerialNumbersText(l.serialNumbersText) }
        : {}),
    })),
  });

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete' | 'complete_new' | 'save') => {
      if (!supplierId) throw new Error('Supplier is required');
      if (lines.length === 0) throw new Error('Add at least one item');

      const shouldComplete = mode === 'complete' || mode === 'complete_new';
      if (shouldComplete && purchaseType !== 'NON_GST' && intraState === null) {
        throw new Error(
          'Supplier state or GSTIN is required for GST purchases. Update the supplier or enable assume-local in GST settings.',
        );
      }
      const payload = buildPayload();
      const key = idempotencyKey ?? newIdempotencyKey();
      setIdempotencyKey(key);
      let invoice: PurchaseInvoice;
      let completeWarning: string | null = null;
      if (isEdit && editId) {
        // H9-A: completed purchases need Owner + confirm_amend for money-field edits.
        if (editingStatus === 'COMPLETED') {
          if (!isOwner) {
            throw new Error(
              'Only an Owner can amend a completed purchase. Use a return for stock corrections, not price fixes.',
            );
          }
          if (!window.confirm(t('billing.confirmAmendCompleted'))) {
            throw new Error('Amend cancelled');
          }
          invoice = await updatePurchase(editId, { ...payload, confirmAmend: true });
        } else {
          invoice = await updatePurchase(editId, payload);
        }
        // mode 'save' (completed edit) persists without completing — same path as draft.
        if (shouldComplete && invoice.status === 'DRAFT') {
          try {
            invoice = await completePurchase(invoice.id);
          } catch (err) {
            completeWarning = getErrorMessage(err);
          }
        }
      } else {
        invoice = await createPurchase(payload, { idempotencyKey: key });
        if (shouldComplete) {
          try {
            invoice = await completePurchase(invoice.id);
          } catch (err) {
            completeWarning = getErrorMessage(err);
          }
        }
      }

      let paymentWarning: string | null = completeWarning;
      if (shouldComplete && amountPaid > 0 && invoice.status === 'COMPLETED') {
        const already = toNumber(invoice.paid);
        const toAllocate = Math.max(0, amountPaid - already);
        if (toAllocate > 0) {
          try {
            const payment = await createSupplierPayment({
              supplier: Number(supplierId),
              amount: toAllocate,
              mode: paymentMode,
              paymentDate: invoiceDate,
              notes: `Against ${invoice.number ?? invoice.id}`,
            });
            await createAllocation({
              supplierPayment: payment.id,
              purchaseInvoice: invoice.id,
              amount: toAllocate,
            });
          } catch (err) {
            paymentWarning = [paymentWarning, getErrorMessage(err)].filter(Boolean).join(' ');
          }
        }
      }
      return { invoice, mode, paymentWarning };
    },
    onSuccess: async ({ invoice, mode, paymentWarning }) => {
      flashWarning(paymentWarning ?? null);
      void qc.invalidateQueries({ queryKey: ['purchase-invoice-number-series'] });
      void qc.invalidateQueries({ queryKey: ['purchase-invoice', invoice.id] });
      if (companyId && userId) {
        void clearPurchaseDraft(companyId, userId).then(() => setHasLocalDraft(false));
      }
      const label = invoice.number?.trim() ? invoice.number : `Draft #${invoice.id}`;

      if (mode === 'complete_new' && invoice.status === 'COMPLETED') {
        flashSaveAndNew(`Purchase ${label} saved — start the next one`, paymentWarning);
        resetForm();
        navigate('/purchases/new', { replace: true });
        return;
      }

      const totalQty = lines.reduce((acc, l) => acc + (Number(l.quantity) || 0), 0);
      const flash =
        invoice.status === 'COMPLETED'
          ? `Purchase ${label} saved — ${totalQty} items added to stock`
          : `Draft ${label} saved${paymentWarning ? ` — complete failed: ${paymentWarning}` : ''}`;

      try {
        await qc.fetchQuery({
          queryKey: ['purchases'],
          queryFn: () => listPurchasesPage(),
          staleTime: 0,
        });
      } catch {
        void qc.invalidateQueries({ queryKey: ['purchases'] });
      }

      navigate('/purchases/history', {
        replace: true,
        state: {
          message: flash,
          ...(paymentWarning ? { paymentWarning } : {}),
        },
      });
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const partyMutation = useMutation({
    mutationFn: async () => {
      const gstin = partyForm.gstin.trim().toUpperCase();
      if (gstin) {
        if (!isValidGstin(gstin)) throw new Error('Enter a valid 15-character GSTIN.');
        const existing = await listSuppliersPage({ gstin, pageSize: 5 });
        if (
          existing.results.some(
            (s) =>
              (s.gstin ?? '').toUpperCase() === gstin &&
              (!partyForm.id || s.id !== partyForm.id),
          )
        ) {
          throw new Error('A supplier with this GSTIN already exists.');
        }
      }
      if (partyForm.id) {
        return updateSupplier(partyForm.id, {
          name: partyForm.name.trim(),
          phone: partyForm.phone,
          gstin: gstin || partyForm.gstin,
          state: partyForm.state,
        });
      }
      return createSupplier({
        name: partyForm.name.trim(),
        phone: partyForm.phone,
        gstin: gstin || partyForm.gstin,
        state: partyForm.state,
        isActive: true,
      });
    },
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ['suppliers-search'] });
      void qc.invalidateQueries({ queryKey: ['supplier', c.id] });
      setSupplierId(c.id);
      setPartyDialogOpen(false);
      setPartyForm({ id: undefined, name: '', phone: '', gstin: '', state: '' });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const itemMutation = useMutation({
    mutationFn: () =>
      createProduct({
        name: itemForm.name.trim(),
        sku: itemForm.sku.trim(),
        hsnCode: itemForm.hsnCode.trim(),
        purchasePrice: Number(itemForm.purchasePrice) || 0,
        // UXW2B-003: default selling price to MRP, not purchase price — mirroring
        // purchase price silently created zero-margin items on every quick-add.
        sellingPrice: Number(itemForm.mrp) || Number(itemForm.purchasePrice) || 0,
        mrp: Number(itemForm.mrp) || 0,
        gstRate: Number(itemForm.gstRate) || 0,
        reorderLevel: 0,
        status: 'ACTIVE',
      }),
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ['products'] });
      void qc.invalidateQueries({ queryKey: ['product-search'] });
      setLines((prev) => [...prev, makeLine(p, intraState)]);
      setItemDialogOpen(false);
      setItemDialogError(null);
      setItemForm({
        name: '',
        sku: '',
        hsnCode: '',
        purchasePrice: '',
        mrp: '',
        gstRate: '18',
      });
    },
    onError: (err) => setItemDialogError(getErrorMessage(err)),
  });

  const addProduct = (product: Product | null) => {
    if (!product || editingStatus === 'COMPLETED') return;
    if (product.status !== 'ACTIVE') {
      setError('Cannot purchase inactive product');
      return;
    }
    setLines((prev) => {
      const existing = prev.find((l) => l.product === product.id && !l.batchNo);
      if (existing) {
        return prev.map((l) =>
          l.key === existing.key
            ? recomputeLine(l, intraState, { quantity: l.quantity + 1 })
            : l,
        );
      }
      return [...prev, makeLine(product, intraState)];
    });
    setProductQuery('');
    setError(null);
  };

  const updateLine = (
    key: string,
    patch: Partial<DraftLine>,
    opts?: { fromDiscountAmount?: boolean },
  ) => {
    setLines((prev) =>
      prev.map((l) => {
        if (l.key !== key) return l;
        if (opts?.fromDiscountAmount && patch.discountAmount != null) {
          const gross = roundMoney((patch.quantity ?? l.quantity) * (patch.unitPrice ?? l.unitPrice));
          const amount = Math.min(Math.max(0, patch.discountAmount), gross);
          const percent = gross > 0 ? roundMoney((amount / gross) * 100) : 0;
          return recomputeLine(l, intraState, {
            ...patch,
            discountPercent: percent,
            discountAmount: amount,
          });
        }
        return recomputeLine(l, intraState, patch);
      }),
    );
  };

  useEffect(() => {
    // BUG-513: same guard as NewInvoicePage.
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (lines.length === 0) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [lines.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.ctrlKey || e.metaKey;
      if (meta && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (!saveMutation.isPending) saveMutation.mutate('complete');
      }
      if (meta && e.key === 'Enter') {
        e.preventDefault();
        if (!saveMutation.isPending) saveMutation.mutate('complete_new');
      }
      if (e.key === 'F2') {
        e.preventDefault();
        barcodeRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [saveMutation.isPending, saveMutation.mutate]);

  const activeSuppliers = (suppliers.data?.results ?? []).filter(
    (c) => c.isActive !== false && (c as unknown as { is_active?: boolean }).is_active !== false,
  );
  const canSave = lines.length > 0 && Boolean(supplierId) && !saveMutation.isPending;
  const canComplete = canSave && posKnown;
  const primarySave = primarySaveAction({ isEdit, editingStatus });
  const isCompletedEdit = editingStatus === 'COMPLETED';
  const canAmendMoney = isCompletedEdit && isOwner;

  const onSignaturePick = async (file: File | null) => {
    if (!file) return;
    try {
      const uploaded = await uploadFile(file, 'ATTACHMENT');
      setSignatureId(uploaded.id);
      setSignatureUrl(uploaded.url ?? null);
      await updateCompany({ signature: uploaded.id });
      void qc.invalidateQueries({ queryKey: ['company'] });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <DocumentEditorShell
      title={isEdit ? t('billing.purchaseEditTitle') : t('billing.purchaseTitle')}
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canComplete}
      primaryDisabledExtra={isCompletedEdit && !isOwner}
      isEdit={isEdit}
      showDraftButton={!isEdit || editingStatus === 'DRAFT'}
      backTo={isEdit ? '/purchases/history' : null}
      message={message}
      error={error}
      warning={
        isEdit && editingStatus === 'COMPLETED' ? t('billing.editingCompletedWarning') : null
      }
      saving={saveMutation.isPending}
      onPrimarySave={() => saveMutation.mutate(primarySave.mode)}
      onSaveAndNew={() => saveMutation.mutate('complete_new')}
      onDraft={() => saveMutation.mutate('draft')}
      onOpenShortcuts={() => setShortcutsOpen(true)}
      onOpenSettings={() => setSettingsOpen(true)}
      extraActions={
        canImport(user) ? (
          <Button
            component={RouterLink}
            to="/purchases/bill-upload"
            variant="outlined"
            size="small"
            color="warning"
          >
            {t('billing.uploadBill')}
          </Button>
        ) : null
      }
    >
      <Stack spacing={2}>
      {pendingDraft ? (
        <Alert
          severity="info"
          action={
            <Stack direction="row" spacing={1}>
              <Button color="inherit" size="small" onClick={applyPendingDraft}>
                {t('billing.restoreDraft')}
              </Button>
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  setPendingDraft(null);
                  if (companyId && userId) {
                    void clearPurchaseDraft(companyId, userId).then(() => setHasLocalDraft(false));
                  }
                }}
              >
                {t('common.cancel')}
              </Button>
            </Stack>
          }
        >
          {t('billing.restorePurchaseDraft', {
            when: new Date(pendingDraft.savedAt).toLocaleString(),
          })}
        </Alert>
      ) : null}
      {(offline || hasLocalDraft) && !isEdit && (!hideOutboxWarn || offline) ? (
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
          {OUTBOX_PLAINTEXT_WARNING}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <PartySelectPanel
            label={t('billing.billFrom')}
            selectedParty={selectedSupplier}
            editingStatus={editingStatus}
            onClear={() => setSupplierId('')}
            options={activeSuppliers}
            query={supplierQuery}
            onQueryChange={setSupplierQuery}
            onSelect={(v) => setSupplierId(v?.id ?? '')}
            loading={suppliers.isFetching}
            onCreatePartyClick={() => {
              setPartyForm({ id: undefined, name: '', phone: '', gstin: '', state: '' });
              setPartyDialogOpen(true);
            }}
            onEditPartyClick={() => {
              if (!selectedSupplier) return;
              setPartyForm({
                id: selectedSupplier.id,
                name: selectedSupplier.name ?? '',
                phone: selectedSupplier.phone ?? '',
                gstin: selectedSupplier.gstin ?? '',
                state: selectedSupplier.state ?? '',
              });
              setPartyDialogOpen(true);
            }}
          />

          <Stack spacing={1.5} sx={{ flex: 1, minWidth: 280 }}>
            <Stack direction="row" spacing={1}>
              <CompactField
                label={t('billing.invoicePrefix')}
                value={prefix}
                InputProps={{ readOnly: true }}
                disabled
                sx={{ width: 120 }}
              />
              <NumericField
                label={t('billing.invoiceNumber')}
                value={nextNumber}
                onValueChange={() => undefined}
                min={1}
                emptyAs={1}
                fullWidth
                disabled
                helperText={
                  isEdit
                    ? 'Purchase number is fixed when editing'
                    : `${t('billing.nextNumberHint')}: ${prefix}-${String(nextNumber).padStart(series?.data?.padding ?? 5, '0')}`
                }
              />
            </Stack>
            <CompactField
              select
              label="Warehouse"
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value ? Number(e.target.value) : '')}
            >
              {(warehouses.data ?? []).filter((warehouse) => warehouse.isActive !== false).map((warehouse) => (
                <MenuItem key={warehouse.id} value={warehouse.id}>
                  {warehouse.name}{warehouse.isDefault ? ' (default)' : ''}
                </MenuItem>
              ))}
            </CompactField>
            <CompactField
              select
              label="Cost center"
              value={costCenterId}
              onChange={(e) => setCostCenterId(e.target.value ? Number(e.target.value) : '')}
            >
              <MenuItem value="">None</MenuItem>
              {(costCenters.data ?? []).map((cc) => (
                <MenuItem key={String(cc.id)} value={Number(cc.id)}>
                  {String(cc.code ?? cc.name ?? cc.id)}
                </MenuItem>
              ))}
            </CompactField>
            <Stack direction="row" spacing={1}>
              <CompactField
                label={t('billing.purchaseInvDate')}
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <CompactField
                select
                label={t('billing.purchaseType')}
                value={purchaseType}
                onChange={(e) => setPurchaseType(e.target.value as PurchaseType)}
              >
                <MenuItem value="GST">GST</MenuItem>
                <MenuItem value="NON_GST">Non-GST</MenuItem>
              </CompactField>
              {purchaseType === 'GST' ? (
                <CompactField
                  select
                  label="Price mode"
                  value={priceMode}
                  onChange={(e) => setPriceMode(e.target.value as PriceMode)}
                  disabled={isCompletedEdit && !canAmendMoney}
                >
                  <MenuItem value="EXCLUSIVE">Tax exclusive</MenuItem>
                  <MenuItem value="INCLUSIVE">Tax inclusive</MenuItem>
                </CompactField>
              ) : null}
            </Stack>
            {purchaseType === 'GST' ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={isReverseCharge}
                    onChange={(e) => setIsReverseCharge(e.target.checked)}
                    disabled={isCompletedEdit && !canAmendMoney}
                  />
                }
                label="Reverse charge (RCM)"
              />
            ) : null}
            {purchaseType === 'GST' ? (
              <CompactField
                select
                label={t('billing.itcEligibility')}
                value={itcEligibility}
                onChange={(e) =>
                  setItcEligibility(e.target.value as 'CLAIMABLE' | 'INELIGIBLE' | 'REVERSED')
                }
                disabled={isCompletedEdit && !canAmendMoney}
              >
                <MenuItem value="CLAIMABLE">Claimable</MenuItem>
                <MenuItem value="INELIGIBLE">Ineligible</MenuItem>
                <MenuItem value="REVERSED">Reversed</MenuItem>
              </CompactField>
            ) : null}
            <CompactField
              label={t('billing.originalInvNo')}
              value={supplierBillNumber}
              onChange={(e) => setSupplierBillNumber(e.target.value)}
            />
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
                  aria-label="dismiss"
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
                    onChange={(e) => setDueDate(e.target.value)}
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

      <Paper sx={{ overflow: 'auto' }}>
        <DraftLineTable
          lines={lines}
          taxes={lineTaxes}
          showCess={purchaseType !== 'NON_GST'}
          qtyDisabled={isCompletedEdit}
          moneyDisabled={isCompletedEdit && !canAmendMoney}
          deleteDisabled={isCompletedEdit}
          showBatchSlot={showBatchCols || lines.some((line) => line.trackBatch)}
          showSerialSlot={lines.some((line) => line.trackSerial)}
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
                    renderInput={(params) => <TextField {...params} placeholder="FEFO batch" helperText="Leave blank to use FEFO" />}
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
          renderSerialSlot={(line) => (
            <TableCell>
              {line.trackSerial ? (
                <CompactField
                  multiline
                  minRows={1}
                  maxRows={3}
                  placeholder="SN-001, SN-002"
                  value={line.serialNumbersText ?? ''}
                  onChange={(e) => updateLine(line.key, { serialNumbersText: e.target.value })}
                  helperText={`${parseSerialNumbersText(line.serialNumbersText ?? '').length} serial(s)`}
                />
              ) : null}
            </TableCell>
          )}
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
            <Autocomplete<Product>
              sx={{ flex: 1 }}
              options={(products.data ?? []).filter((p) => p.status === 'ACTIVE')}
              loading={products.isFetching}
              inputValue={productQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') setProductQuery(v);
              }}
              onChange={(_, v) => addProduct(v)}
              disabled={isCompletedEdit}
              getOptionLabel={(o) =>
                formatProductOptionLabel(o, availableByProduct.get(Number(o.id)))
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  inputRef={barcodeRef}
                  placeholder={`+ ${t('billing.addItem')} / ${t('billing.searchProduct')}`}
                  autoFocus
                  disabled={isCompletedEdit}
                />
              )}
            />
            <Link
              component="button"
              type="button"
              underline="hover"
              disabled={isCompletedEdit || !isOwner}
              onClick={() => {
                if (isCompletedEdit || !isOwner) return;
                setItemDialogError(null);
                setItemDialogOpen(true);
              }}
              sx={{ whiteSpace: 'nowrap' }}
              title={!isOwner ? 'Only the company owner can create products.' : undefined}
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
            {t('billing.subtotal')} {formatMoney(totals.subtotal)}
          </Typography>
          <Typography>
            {t('billing.tax')} {formatMoney(totals.taxTotal)}
          </Typography>
          {totals.cessTotal > 0 ? (
            <Typography>
              {t('billing.cess')} {formatMoney(totals.cessTotal)}
            </Typography>
          ) : null}
          <Typography fontWeight={700}>
            {t('billing.totalAmount')}{' '}
            {formatMoney(rcmPreview ? rcmPreview.payable : totals.grandTotal)}
          </Typography>
        </Box>
      </Paper>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems="flex-start">
        <Stack spacing={1} sx={{ flex: 1, minWidth: 220 }}>
          {!showNotes ? (
            <Link
              component="button"
              type="button"
              underline="hover"
              onClick={() => setShowNotes(true)}
            >
              + {t('billing.addNotes')}
            </Link>
          ) : null}
          <Collapse in={showNotes}>
            <CompactField
              label={t('billing.addNotes')}
              multiline
              minRows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Collapse>

          {!showTerms ? (
            <Link
              component="button"
              type="button"
              underline="hover"
              onClick={() => setShowTerms(true)}
            >
              + {t('billing.addTerms')}
            </Link>
          ) : null}
          <Collapse in={showTerms}>
            <CompactField
              label={t('billing.addTerms')}
              multiline
              minRows={3}
              value={termsText}
              onChange={(e) => setTermsText(e.target.value)}
            />
          </Collapse>

          {isRuntimeFlagEnabled('ENABLE_TDS') ? (
            <>
              {!showTds ? (
                <Link component="button" type="button" underline="hover" onClick={() => setShowTds(true)}>
                  + TDS (194C / 194J / 194Q)
                </Link>
              ) : (
                <Paper variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2">TDS withheld</Typography>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }}>
                    <TextField size="small" label="Section" value={tdsSection} onChange={(e) => setTdsSection(e.target.value)} placeholder="194C" />
                    <TextField size="small" type="number" label="Rate %" value={tdsRate || ''} onChange={(e) => setTdsRate(Number(e.target.value) || 0)} />
                    <TextField size="small" type="number" label="TDS amount" value={tdsAmount || ''} onChange={(e) => setTdsAmount(Number(e.target.value) || 0)} />
                  </Stack>
                </Paper>
              )}
            </>
          ) : null}

          {!showBank ? (
            <Link
              component="button"
              type="button"
              underline="hover"
              onClick={() => setShowBank(true)}
            >
              + {t('billing.addBank')}
            </Link>
          ) : (
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
                    Company
                  </Link>
                </Typography>
              )}
            </Paper>
          )}

          {!showQr ? (
            <Link
              component="button"
              type="button"
              underline="hover"
              onClick={() => setShowQr(true)}
            >
              + {t('billing.addPaymentQr')}
            </Link>
          ) : (
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
          )}
        </Stack>

        <DocumentTaxSummary
          totals={totals}
          displayGrandTotal={displayGrandTotal}
          totalLabel={rcmPreview ? 'Payable (RCM, excl. tax)' : t('billing.totalAmount')}
          additionalCharges={additionalCharges}
          onAdditionalChargesChange={setAdditionalCharges}
          invoiceDiscount={invoiceDiscount}
          onInvoiceDiscountChange={setInvoiceDiscount}
          invoiceDiscountMode={invoiceDiscountMode}
          onInvoiceDiscountModeChange={setInvoiceDiscountMode}
          autoRoundOff={autoRoundOff}
          onAutoRoundOffChange={setAutoRoundOff}
          posKnown={posKnown}
          partyRole="supplier"
          isCompletedEdit={isCompletedEdit}
          canAmendMoney={canAmendMoney}
          extraAlerts={
            rcmPreview ? (
              <Alert severity="info">
                Reverse charge: tax liability {formatMoney(rcmPreview.rcmTaxTotal)} (CGST{' '}
                {formatMoney(rcmPreview.rcmCgst)}, SGST {formatMoney(rcmPreview.rcmSgst)}, IGST{' '}
                {formatMoney(rcmPreview.rcmIgst)}). Payable to supplier (excl. tax):{' '}
                {formatMoney(rcmPreview.payable)}.
              </Alert>
            ) : null
          }
        >
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography>{t('billing.amountPaid')}</Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={markFullyPaid}
                    onChange={(e) => {
                      setMarkFullyPaid(e.target.checked);
                      if (e.target.checked) setAmountPaid(displayGrandTotal);
                    }}
                    size="small"
                  />
                }
                label={t('billing.markFullyPaid')}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <NumericField
                value={amountPaid}
                onValueChange={(n) => {
                  setMarkFullyPaid(false);
                  setAmountPaid(n);
                }}
                min={0}
                decimals={2}
                placeholder={t('billing.enterPaymentAmount')}
                InputProps={{
                  startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                }}
              />
              <CompactField
                select
                value={paymentMode}
                onChange={(e) => setPaymentMode(e.target.value as PaymentMode)}
                sx={{ maxWidth: 120 }}
              >
                <MenuItem value="CASH">Cash</MenuItem>
                <MenuItem value="UPI">UPI</MenuItem>
                <MenuItem value="BANK">Bank</MenuItem>
                <MenuItem value="CARD">Card</MenuItem>
                <MenuItem value="CREDIT">Credit</MenuItem>
              </CompactField>
            </Stack>
            <Typography
              fontWeight={700}
              color={balance <= 0 ? 'success.main' : 'text.primary'}
              sx={{ display: 'flex', justifyContent: 'space-between' }}
            >
              <span>{t('billing.balanceAmount')}</span>
              <span>{formatMoney(balance)}</span>
            </Typography>

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


      <Dialog open={settingsOpen} onClose={() => setSettingsOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('billing.settings')}</DialogTitle>
        <DialogContent>
          <FormControlLabel
            control={
              <Checkbox
                checked={showBatchCols}
                onChange={(e) => setShowBatchCols(e.target.checked)}
              />
            }
            label={t('billing.showBatchColumns')}
          />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('billing.shortcuts')}
          </Typography>
          <Button
            sx={{ mt: 2 }}
            component={RouterLink}
            to="/settings/templates"
            onClick={() => setSettingsOpen(false)}
          >
            {t('nav.invoiceTemplates')}
          </Button>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSettingsOpen(false)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('billing.shortcutsTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('billing.shortcuts')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShortcutsOpen(false)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={partyDialogOpen}
        onClose={() => setPartyDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {partyForm.id ? 'Edit Supplier' : t('billing.createParty')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              required
              label={t('common.name')}
              value={partyForm.name}
              onChange={(e) => setPartyForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('common.phone')}
              value={partyForm.phone}
              onChange={(e) => setPartyForm((f) => ({ ...f, phone: e.target.value }))}
            />
            <TextField
              label="GSTIN"
              value={partyForm.gstin}
              onChange={(e) => setPartyForm((f) => ({ ...f, gstin: e.target.value }))}
            />
            <StateSelect
              value={partyForm.state}
              onChange={(state) => setPartyForm((f) => ({ ...f, state }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPartyDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!partyForm.name.trim() || partyMutation.isPending}
            onClick={() => partyMutation.mutate()}
          >
            {partyForm.id ? t('common.save') : t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>

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
            {itemDialogError ? <Alert severity="error">{itemDialogError}</Alert> : null}
            <TextField
              required
              label={t('common.name')}
              value={itemForm.name}
              onChange={(e) => setItemForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label="SKU"
              value={itemForm.sku}
              onChange={(e) => setItemForm((f) => ({ ...f, sku: e.target.value }))}
              helperText="Must be unique if set"
            />
            <TextField
              label="HSN"
              value={itemForm.hsnCode}
              onChange={(e) => setItemForm((f) => ({ ...f, hsnCode: e.target.value }))}
              error={Boolean(itemForm.hsnCode) && !isValidHsnSac(itemForm.hsnCode)}
              helperText={
                Boolean(itemForm.hsnCode) && !isValidHsnSac(itemForm.hsnCode)
                  ? 'HSN/SAC must be 4, 6, or 8 digits'
                  : undefined
              }
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Purchase price"
                type="number"
                fullWidth
                value={itemForm.purchasePrice}
                onChange={(e) => setItemForm((f) => ({ ...f, purchasePrice: e.target.value }))}
              />
              <TextField
                label="MRP"
                type="number"
                fullWidth
                value={itemForm.mrp}
                onChange={(e) => setItemForm((f) => ({ ...f, mrp: e.target.value }))}
              />
              <TextField
                label="GST %"
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
      </Stack>
    </DocumentEditorShell>
  );
}


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
import { Link as RouterLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  completeSalesInvoice,
  createAllocation,
  createProduct,
  createReceipt,
  createSalesInvoice,
  getCompany,
  getCustomer,
  listCompanyGstins,
  getSalesInvoice,
  getSalesInvoiceNumberSeries,
  listCustomersPage,
  listBatches,
  listCostCenters,
  listPriceLists,
  listProductsPage,
  listSalesInvoicesPage,
  listStock,
  listWarehouses,
  searchProducts,
  updateSalesInvoice,
  uploadFile,
} from '@/api/resources';
import { getErrorMessage, isNetworkError, userGestureIdempotencyKey } from '@/api/client';
import { trackInvoiceComplete } from '@/lib/telemetry';
import { useAuth } from '@/auth/AuthContext';
import {
  enqueueDraft,
  listDrafts,
  OUTBOX_WARNING_DISMISS_KEY,
} from '@/offline/invoiceDraftCache';
import { isValidHsnSac } from '@/utils/gst';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { canCreateSales } from '@/utils/permissions';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { DocumentTaxSummary } from '@/components/DocumentTaxSummary';
import { t } from '@/i18n';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import type { InvoiceType, PaymentMode, PriceMode, Product, SalesInvoice } from '@/types/domain';
import { formatMoney, roundMoney, toNumber } from '@/utils/money';
import { resolveListUnitPrice } from '@/utils/priceList';
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
  NumericField,
  parseSerialNumbersText,
  primarySaveAction,
  recomputeLine,
  todayIso,
  useBillingSaveFeedback,
  useDebouncedValue,
  type DraftLine,
} from '@/components/billing';
import { InvoicePartyPanel } from '@/pages/sales/invoice/InvoicePartyPanel';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { HelpHint } from '@/pages/help/HelpHint';
import { makeInvoiceLine } from '@/pages/sales/invoice/makeInvoiceLine';
import { useInvoiceOffline } from '@/pages/sales/invoice/useInvoiceOffline';
import { completeWithConfirms } from '@/utils/completeWithConfirms';

const COL_PREFS_KEY = 'bizboard.billing.batchCols';

async function completeInvoiceWithConfirms(
  id: number,
  base: { confirmSalesRcm?: boolean },
): Promise<SalesInvoice> {
  // F2-035: delegate to the shared completeWithConfirms loop instead of a
  // hand-nested try/catch that only recovered one confirm code per level —
  // GSTIN_TOTAL_CHANGED then place_of_supply_unresolved (or a third code) at
  // the second retry used to rethrow instead of prompting.
  const started = Date.now();
  const invoice = await completeWithConfirms((extra) => completeSalesInvoice(id, { ...base, ...extra }));
  trackInvoiceComplete(Date.now() - started);
  return invoice;
}

export function NewInvoicePage() {
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const location = useLocation();
  const fromBillUpload = Boolean(
    (location.state as { fromBillUpload?: boolean } | null)?.fromBillUpload,
  );
  const qc = useQueryClient();
  const { user } = useAuth();
  const isOwner = user?.role === 'OWNER';
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const barcodeRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const skipLeaveGuard = useRef(false);

  const [lines, setLines] = useState<DraftLine[]>([]);
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
  const [customerQuery, setCustomerQuery] = useState('');
  const debouncedCustomerQuery = useDebouncedValue(customerQuery, 300);
  const [warehouseId, setWarehouseId] = useState<number | ''>('');
  const [companyGstinId, setCompanyGstinId] = useState<number | ''>('');
  const [costCenterId, setCostCenterId] = useState<number | ''>('');
  const [invoiceType, setInvoiceType] = useState<InvoiceType>('NON_GST');
  const [invoiceTypeTouched, setInvoiceTypeTouched] = useState(false);
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
  const dueDateTouched = useRef(false);
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

  const [additionalCharges, setAdditionalCharges] = useState(0);
  const [chargesHsn, setChargesHsn] = useState('');
  const [chargesGstRate, setChargesGstRate] = useState(0);
  const [invoiceDiscount, setInvoiceDiscount] = useState(0);
  const [invoiceDiscountMode, setInvoiceDiscountMode] = useState<InvoiceDiscountMode>('AFTER_TAX');
  const [autoRoundOff, setAutoRoundOff] = useState(true);
  const [amountReceived, setAmountReceived] = useState(0);
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
  const [itemDialogOpen, setItemDialogOpen] = useState(false);
  const [itemDialogError, setItemDialogError] = useState<string | null>(null);
  const [itemDialogErrorSource, setItemDialogErrorSource] = useState<unknown>(null);
  const [itemForm, setItemForm] = useState({
    name: '',
    sku: '',
    unitName: 'PCS',
    hsnCode: '',
    sellingPrice: '',
    mrp: '',
    gstRate: '18',
  });
  const [signatureUrl, setSignatureUrl] = useState<string | null>(null);
  const [signatureId, setSignatureId] = useState<number | null>(null);

  useInvoiceOffline(companyId, userId, setOutboxBanner);

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

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  useEffect(() => {
    if (isEdit || invoiceTypeTouched || !company.data) return;
    setInvoiceType(preferredInvoiceType(company.data.registrationType));
  }, [company.data, isEdit, invoiceTypeTouched]);
  const customers = useQuery({
    queryKey: ['customers-search', debouncedCustomerQuery],
    queryFn: () => listCustomersPage({ q: debouncedCustomerQuery.trim() || undefined, pageSize: 50 }),
  });
  const selectedCustomerQuery = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: Boolean(customerId),
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
      map.set(id, (map.get(id) ?? 0) + toNumber(s.available ?? s.onHand));
    }
    return map;
  }, [stockBalances.data, warehouseId]);
  const stockShortfalls = useMemo(() => {
    if (company.data?.negativeStockPolicy !== 'BLOCK') return [];
    const needed = new Map<number, { name: string; qty: number }>();
    for (const l of lines) {
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

  useEffect(() => {
    if (!series.data || isEdit) return;
    setPrefix(series.data.prefix);
    setNextNumber(series.data.nextNumber);
  }, [series.data, isEdit]);

  useEffect(() => {
    // Remount-safe: when switching /sales/new ↔ /sales/history/:id/edit, reset hydrate flag.
    setLoadedEdit(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (!existingInvoice.data || loadedEdit) return;
    const inv = existingInvoice.data;
    if (inv.status === 'CANCELLED' || inv.status === 'RETURNED') {
      setError('This invoice cannot be edited.');
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
    dueDateTouched.current = Boolean(inv.dueDate);
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
    setTcsSection(inv.tcsSection ?? '');
    setTcsRate(toNumber(inv.tcsRate));
    setTcsAmount(toNumber(inv.tcsAmount));
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
  }, [
    existingInvoice.data,
    loadedEdit,
    company.data,
    selectedCustomerQuery.data,
    products.data,
    setError,
  ]);

  useEffect(() => {
    if (!isEdit && !warehouseId) {
      const defaultWarehouse = warehouses.data?.find((warehouse) => warehouse.isDefault);
      if (defaultWarehouse) setWarehouseId(defaultWarehouse.id);
    }
  }, [isEdit, warehouseId, warehouses.data]);

  useEffect(() => {
    if (company.data?.invoiceTerms && !termsText && !isEdit) {
      setTermsText(company.data.invoiceTerms);
    }
    if (company.data?.signature) {
      setSignatureId(company.data.signature);
    }
  }, [company.data, termsText, isEdit]);

  useEffect(() => {
    if (dueDateTouched.current) return;
    setDueDate(addDaysIso(invoiceDate, paymentTermsDays || 0));
  }, [invoiceDate, paymentTermsDays]);

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
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedCustomer?.gstin || selectedCustomer?.state,
    { assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty },
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
    placeOfSupplyKnown(selectedCustomer?.state, selectedCustomer?.gstin);

  // R5-001: the backend blocks an AFTER_TAX invoice discount on B2B GST
  // invoices — keep the form in sync so the preview total matches Complete.
  const blockAfterTaxDiscount =
    invoiceType !== 'NON_GST' && Boolean((selectedCustomer?.gstin || '').trim());
  useEffect(() => {
    if (blockAfterTaxDiscount && invoiceDiscountMode === 'AFTER_TAX') {
      setInvoiceDiscountMode('BEFORE_TAX');
    }
  }, [blockAfterTaxDiscount, invoiceDiscountMode]);

  const balance = roundMoney(Math.max(0, totals.grandTotal - amountReceived));

  const creditLimitBanner = useMemo(() => {
    if (!selectedCustomer) return null;
    const limit = toNumber(selectedCustomer.creditLimit);
    if (limit <= 0) return null;
    const outstanding = toNumber(selectedCustomer.outstanding ?? 0);
    const exposure = outstanding + totals.grandTotal;
    if (exposure < limit * 0.9) return null;
    const pct = limit > 0 ? Math.round((exposure / limit) * 100) : 0;
    return (
      <Alert severity="warning">
        {t('phase1.creditLimitWarning', {
          exposure: formatMoney(exposure),
          limit: formatMoney(limit),
          pct: String(pct),
        })}
      </Alert>
    );
  }, [selectedCustomer, totals.grandTotal]);

  const resetForm = () => {
    // BUG-500 / P0-311: do NOT call clearFeedback here — Save & New sets the
    // success flash then resets fields in the same tick; wiping feedback would
    // batch-erase the message before paint. Use useBillingSaveFeedback.
    setLines([]);
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

  const buildPayload = () => ({
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
    tcsSection,
    tcsRate,
    tcsAmount,
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
  });

  const previewOnline = typeof navigator === 'undefined' || navigator.onLine;
  const preview = usePreviewTotals(
    'sales',
    previewOnline && customerId && lines.some((l) => l.product)
      ? (buildPayload() as Record<string, unknown>)
      : null,
  );

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete' | 'complete_new' | 'save') => {
      if (!customerId) throw new Error(t('billing.customerRequired'));
      if (lines.length === 0) throw new Error(t('billing.addAtLeastOneItem'));

      const shouldComplete = mode === 'complete' || mode === 'complete_new';
      if (shouldComplete && invoiceType !== 'NON_GST' && intraState === null) {
        throw new Error(t('billing.placeOfSupplyRequired'));
      }
      if (shouldComplete && isReverseCharge && !confirmSalesRcm) {
        throw new Error(t('billing.confirmSalesRcmRequired'));
      }
      const payload = buildPayload();
      // PD-01: one fresh Idempotency-Key per user gesture. Network auto-retry
      // reuses the request header; an offline queue+flush reuses draft.idempotencyKey.
      const key = userGestureIdempotencyKey();
      let invoice: SalesInvoice;
      let completeWarning: string | null = null;
      const queueOffline = async () => {
        if (!companyId || !userId) return;
        await enqueueDraft(companyId, userId, {
          kind: 'invoice',
          payload: {
            ...(payload as Record<string, unknown>),
            ...(editingStatus ? { status: editingStatus } : {}),
            ...(editingStatus === 'COMPLETED' ? { confirmAmend: true } : {}),
            _completeIntent: shouldComplete,
            _confirmSalesRcm: isReverseCharge && confirmSalesRcm,
            _amountReceived: amountReceived,
            _paymentMode: paymentMode,
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
            if (!window.confirm(t('billing.confirmAmendCompleted'))) {
              throw new Error('Amend cancelled');
            }
            invoice = await updateSalesInvoice(editId, { ...payload, confirmAmend: true });
          } else {
            invoice = await updateSalesInvoice(editId, payload);
          }
          // mode 'save' (completed edit) persists without completing — same path as draft.
          if (shouldComplete && invoice.status === 'DRAFT') {
            try {
              invoice = await completeInvoiceWithConfirms(invoice.id, {
                confirmSalesRcm: isReverseCharge && confirmSalesRcm,
              });
            } catch (err) {
              completeWarning = getErrorMessage(err);
            }
          }
        } else {
          invoice = await createSalesInvoice(payload, { idempotencyKey: key });
          if (shouldComplete) {
            try {
              invoice = await completeInvoiceWithConfirms(invoice.id, {
                confirmSalesRcm: isReverseCharge && confirmSalesRcm,
              });
            } catch (err) {
              completeWarning = getErrorMessage(err);
            }
          }
        }
      } catch (err) {
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
      if (shouldComplete && amountReceived > 0 && invoice.status === 'COMPLETED') {
        const already = toNumber(invoice.received);
        const toAllocate = Math.max(0, amountReceived - already);
        if (toAllocate > 0) {
          try {
            const receipt = await createReceipt(
              {
                customer: Number(customerId),
                amount: toAllocate,
                mode: paymentMode,
                receiptDate: invoiceDate,
                notes: `Against ${invoice.number ?? invoice.id}`,
              },
              { idempotencyKey: `${key}-receipt` },
            );
            await createAllocation(
              {
                receipt: receipt.id,
                salesInvoice: invoice.id,
                amount: toAllocate,
              },
              { idempotencyKey: `${key}-alloc` },
            );
          } catch (err) {
            paymentWarning = [paymentWarning, getErrorMessage(err)].filter(Boolean).join(' ');
          }
        }
      }
      return { invoice, mode, paymentWarning };
    },
    onSuccess: async ({ invoice, mode, paymentWarning }) => {
      skipLeaveGuard.current = true;
      flashWarning(paymentWarning ?? null);
      void qc.invalidateQueries({ queryKey: ['sales-invoice-number-series'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoice.id] });
      const label = invoice.number?.trim() ? invoice.number : `#${invoice.id}`;

      if (mode === 'complete_new' && invoice.status === 'COMPLETED') {
        flashSaveAndNew(t('billing.invoiceSavedNext', { label }), paymentWarning);
        resetForm();
        navigate('/sales/new', { replace: true });
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
      try {
        await qc.fetchQuery({
          queryKey: ['sales-invoices', 1],
          queryFn: () => listSalesInvoicesPage({ page: 1, pageSize: 50 }),
          staleTime: 0,
        });
      } catch {
        void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      }

      navigate('/sales/history', {
        replace: true,
        state: {
          message: flash,
        },
      });
    },
    onError: (err) => {
      const msg = getErrorMessage(err);
      if (msg === t('billing.savedOffline')) return;
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
        purchasePrice: 0,
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
  const canComplete =
    canSave &&
    posKnown &&
    (isCompletedEdit || stockShortfalls.length === 0) &&
    (!previewOnline || preview.ready || previewFellBack);
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
      }
    : totals;

  useEffect(() => {
    if (markFullyPaid) setAmountReceived(shownTotals.grandTotal);
  }, [markFullyPaid, shownTotals.grandTotal]);
  const primarySave = primarySaveAction({ isEdit, editingStatus });
  const canAmendMoney = isCompletedEdit && isOwner;

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
  });
  kbdRef.current = {
    canSave,
    canComplete,
    primaryMode: primarySave.mode,
    isPending: saveMutation.isPending,
    mutate: saveMutation.mutate,
  };
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
      title={isEdit ? t('billing.editTitle') : t('billing.title')}
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canComplete}
      primaryDisabledExtra={isCompletedEdit && !isOwner}
      isEdit={isEdit}
      showDraftButton={!isEdit || editingStatus === 'DRAFT'}
      backTo={isEdit ? `/sales/history/${editId}` : null}
      message={message ?? outboxBanner}
      error={error || preview.error}
      errorSource={errorSource}
      documentId={isEdit ? editId ?? undefined : undefined}
      multiGodown={(warehouses.data?.length ?? 0) > 1}
      warning={
        previewFellBack
          ? t('billing.previewUnavailableClientTotals')
          : fromBillUpload
          ? t('billUpload.reviewOnEditDisclaimerSales')
          : isEdit && editingStatus === 'COMPLETED' && lines.some((l) => l.trackBatch || l.trackSerial)
            ? t('billing.completedBatchLocked')
            : isEdit && editingStatus === 'COMPLETED'
            ? t('billing.editingCompletedWarning')
            : null
      }
      infoBanner={creditLimitBanner}
      saving={saveMutation.isPending}
      onPrimarySave={() => saveMutation.mutate(primarySave.mode)}
      onSaveAndNew={() => saveMutation.mutate('complete_new')}
      onDraft={() => saveMutation.mutate('draft')}
      onOpenShortcuts={() => setShortcutsOpen(true)}
      onOpenSettings={() => setSettingsOpen(true)}
    >
      <Stack spacing={2}>
      <UnsavedChangesGuard when={!skipLeaveGuard.current && (lines.length > 0 || Boolean(customerId))} />
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
              if (v?.creditDays) setPaymentTermsDays(v.creditDays);
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
                    ? 'Invoice number is fixed when editing'
                    : `${t('billing.nextNumberHint')}: ${prefix}-${String(nextNumber).padStart(series?.data?.padding ?? 5, '0')}`
                }
              />
            </Stack>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <CompactField
                label={t('billing.invoiceDate')}
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ width: 140 }}
              />
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
                {company.data?.registrationType === 'REGULAR' ? (
                  <>
                    <MenuItem value="GST">GST Invoice</MenuItem>
                    <MenuItem value="TAX">Tax Invoice</MenuItem>
                    <MenuItem value="RETAIL">Retail Invoice</MenuItem>
                  </>
                ) : null}
                <MenuItem value="NON_GST">Non-GST Invoice</MenuItem>
              </CompactField>
              {invoiceType !== 'NON_GST' ? (
                <HelpHint intent="wrong-gst-on-invoice" slot="tax-inclusive">
                  <CompactField
                    select
                    label="Price mode"
                    value={priceMode}
                    onChange={(e) => setPriceMode(e.target.value as PriceMode)}
                    disabled={isCompletedEdit && !canAmendMoney}
                    sx={{ minWidth: 140 }}
                  >
                    <MenuItem value="EXCLUSIVE">Tax exclusive</MenuItem>
                    <MenuItem value="INCLUSIVE">Tax inclusive</MenuItem>
                  </CompactField>
                </HelpHint>
              ) : null}
              <CompactField
                select
                label={t('nav.warehouses')}
                value={warehouseId}
                onChange={(e) => setWarehouseId(e.target.value ? Number(e.target.value) : '')}
                sx={{ minWidth: 140 }}
              >
                {(warehouses.data ?? []).filter((warehouse) => warehouse.isActive !== false).map((warehouse) => (
                  <MenuItem key={warehouse.id} value={warehouse.id}>
                    {warehouse.name}{warehouse.isDefault ? ' (default)' : ''}
                  </MenuItem>
                ))}
              </CompactField>
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
                  Statutory Export, SEZ & RCM Details
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {invoiceType !== 'NON_GST' ? (
                    <CompactField
                      select
                      label="Supply type"
                      value={supplyType}
                      onChange={(e) =>
                        setSupplyType(e.target.value as import('@/types/domain').SupplyType)
                      }
                      sx={{ minWidth: 160 }}
                    >
                      <MenuItem value="B2B">B2B / regular</MenuItem>
                      <MenuItem value="SEZWP">SEZ with payment</MenuItem>
                      <MenuItem value="SEZWOP">SEZ without payment</MenuItem>
                      <MenuItem value="EXPWP">Export with payment</MenuItem>
                      <MenuItem value="EXPWOP">Export without payment</MenuItem>
                      <MenuItem value="DEXP">Deemed export</MenuItem>
                    </CompactField>
                  ) : null}
                  {(companyGstins.data ?? []).length > 0 ? (
                    <CompactField
                      select
                      label="Company GSTIN"
                      value={companyGstinId}
                      onChange={(e) => setCompanyGstinId(e.target.value ? Number(e.target.value) : '')}
                      sx={{ minWidth: 160 }}
                    >
                      <MenuItem value="">Primary / default</MenuItem>
                      {(companyGstins.data ?? []).filter((row) => row.isActive !== false && row.is_active !== false).map((row) => (
                        <MenuItem key={row.id} value={row.id}>
                          {row.gstin}{(row.isPrimary || row.is_primary) ? ' (primary)' : ''}
                        </MenuItem>
                      ))}
                    </CompactField>
                  ) : null}
                  <CompactField
                    select
                    label="Cost center"
                    value={costCenterId}
                    onChange={(e) => setCostCenterId(e.target.value ? Number(e.target.value) : '')}
                    sx={{ minWidth: 140 }}
                  >
                    <MenuItem value="">None</MenuItem>
                    {(costCenters.data ?? []).map((cc) => (
                      <MenuItem key={String(cc.id)} value={Number(cc.id)}>
                        {String(cc.code ?? cc.name ?? cc.id)}
                      </MenuItem>
                    ))}
                  </CompactField>
                  {invoiceType !== 'NON_GST' ? (
                    <CompactField
                      label="e-Commerce operator GSTIN"
                      value={ecommerceOperatorGstin}
                      onChange={(e) => setEcommerceOperatorGstin(e.target.value.toUpperCase())}
                      placeholder="Optional SUPECOM"
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
                      label="Sales reverse charge (RCM)"
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
                    onChange={(e) => {
                      dueDateTouched.current = true;
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

      <Paper sx={{ overflow: 'auto' }}>
        {stockShortfalls.length > 0 && !isCompletedEdit ? (
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
        ) : null}
        <DraftLineTable
          lines={lines}
          taxes={lineTaxes}
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
            <Stack spacing={1} sx={{ flex: 1 }}>
              <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
              <Autocomplete<Product>
              sx={{ flex: 1 }}
              options={(
                (debouncedProductQuery.length >= 1 ? products.data : productCatalog.data?.results) ?? []
              ).filter((p) => p.status === 'ACTIVE')}
              loading={products.isFetching || productCatalog.isFetching}
              noOptionsText={t('common.noResults')}
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

          {invoiceType !== 'NON_GST' ? (
            <>
              {!showTcs ? (
                <Link component="button" type="button" underline="hover" onClick={() => setShowTcs(true)}>
                  + TCS (206C)
                </Link>
              ) : (
                <Paper variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2">TCS collected (206C)</Typography>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }}>
                    <TextField size="small" label="Section" value={tcsSection} onChange={(e) => setTcsSection(e.target.value)} placeholder="206C" />
                    <TextField size="small" type="number" label="Rate %" inputProps={{ min: 0, max: 100, step: 0.01 }} value={tcsRate || ''} onChange={(e) => setTcsRate(Math.min(100, Math.max(0, Number(e.target.value) || 0)))} />
                    <TextField size="small" type="number" label="TCS amount" inputProps={{ min: 0 }} value={tcsAmount || ''} onChange={(e) => setTcsAmount(Math.max(0, Number(e.target.value) || 0))} />
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
        >
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography>{t('billing.amountReceived')}</Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={markFullyPaid}
                    onChange={(e) => {
                      setMarkFullyPaid(e.target.checked);
                      if (e.target.checked) setAmountReceived(shownTotals.grandTotal);
                    }}
                    size="small"
                  />
                }
                label={t('billing.markFullyPaid')}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <NumericField
                value={amountReceived}
                onValueChange={(n) => {
                  setMarkFullyPaid(false);
                  setAmountReceived(n);
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

      <Dialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('billing.shortcutsTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('billing.shortcuts')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShortcutsOpen(false)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

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
              label="HSN"
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
                label="Selling price"
                type="number"
                fullWidth
                value={itemForm.sellingPrice}
                onChange={(e) => setItemForm((f) => ({ ...f, sellingPrice: e.target.value }))}
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
      </Stack>
    </DocumentEditorShell>
  );
}


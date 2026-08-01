import { useEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode } from 'react';
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
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import SettingsIcon from '@mui/icons-material/Settings';
import Alert from '@mui/material/Alert';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import {
  completeSalesInvoice,
  createAllocation,
  createCustomer,
  createProduct,
  createReceipt,
  createSalesInvoice,
  getCompany,
  getSalesInvoice,
  getSalesInvoiceNumberSeries,
  listCustomers,
  listSalesInvoicesPage,
  searchProducts,
  updateCompany,
  updateSalesInvoice,
  uploadFile,
} from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import type { Customer, InvoiceType, PaymentMode, Product, SalesInvoice } from '@/types/domain';
import { formatMoney, roundMoney, toNumber } from '@/utils/money';
import {
  addDaysIso,
  calculateInvoiceTotals,
  calculateLineTax,
  isIntraState,
  placeOfSupplyKnown,
  type InvoiceDiscountMode,
} from '@/utils/tax';

interface DraftLine {
  key: string;
  product: number;
  productName: string;
  description: string;
  sku: string;
  hsnCode: string;
  unitName: string;
  batchNo: string;
  expDate: string;
  mfgDate: string;
  mrp: number;
  quantity: number;
  unitPrice: number;
  discountPercent: number;
  discountAmount: number;
  gstRate: number;
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  lineTotal: number;
  gross: number;
}

const COL_PREFS_KEY = 'bizboard.invoice.columns.showBatch';

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function makeLine(product: Product, intraState: boolean, quantity = 1): DraftLine {
  const tax = calculateLineTax({
    quantity,
    unitPrice: toNumber(product.sellingPrice),
    gstRate: toNumber(product.gstRate),
    intraState,
  });
  return {
    key: `${product.id}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    product: product.id,
    productName: product.name,
    description: '',
    sku: product.sku,
    hsnCode: product.hsnCode ?? '',
    unitName: product.unitName ?? 'PCS',
    batchNo: '',
    expDate: '',
    mfgDate: '',
    mrp: toNumber(product.mrp),
    quantity,
    unitPrice: toNumber(product.sellingPrice),
    gstRate: toNumber(product.gstRate),
    ...tax,
  };
}

function recomputeLine(
  line: DraftLine,
  intraState: boolean,
  patch: Partial<DraftLine> = {},
): DraftLine {
  const next = { ...line, ...patch };
  const tax = calculateLineTax({
    quantity: next.quantity,
    unitPrice: next.unitPrice,
    discountPercent: next.discountPercent,
    gstRate: next.gstRate,
    intraState,
  });
  return {
    ...next,
    ...tax,
  };
}

function CompactField(props: ComponentProps<typeof TextField>) {
  return <TextField size="small" variant="outlined" fullWidth {...props} />;
}

/** Text decimal field — avoids leading-zero glitch of controlled type="number". */
function NumericField({
  value,
  onValueChange,
  min = 0,
  emptyAs = 0,
  decimals,
  fullWidth = false,
  sx,
  InputProps,
  inputProps,
  ...rest
}: Omit<ComponentProps<typeof TextField>, 'value' | 'onChange' | 'type'> & {
  value: number;
  onValueChange: (n: number) => void;
  min?: number;
  emptyAs?: number;
  decimals?: number;
}) {
  const [text, setText] = useState(() => formatNumericText(value, decimals));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(formatNumericText(value, decimals));
  }, [value, focused, decimals]);

  return (
    <TextField
      size="small"
      variant="outlined"
      fullWidth={fullWidth}
      {...rest}
      value={text}
      onFocus={(e) => {
        setFocused(true);
        rest.onFocus?.(e);
      }}
      onBlur={(e) => {
        setFocused(false);
        const parsed = parseNumericText(text, { min, emptyAs, decimals });
        setText(formatNumericText(parsed, decimals));
        onValueChange(parsed);
        rest.onBlur?.(e);
      }}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw !== '' && !/^\d*\.?\d*$/.test(raw)) return;
        setText(raw);
        if (raw === '' || raw === '.') {
          onValueChange(emptyAs);
          return;
        }
        const n = Number(raw);
        if (!Number.isFinite(n)) return;
        onValueChange(Math.max(min, n));
      }}
      inputProps={{ inputMode: 'decimal', ...inputProps }}
      InputProps={InputProps}
      sx={sx}
    />
  );
}

function formatNumericText(value: number, decimals?: number): string {
  if (!Number.isFinite(value)) return '';
  if (value === 0) return '';
  if (decimals != null) return String(roundMoney(value));
  return String(value);
}

function parseNumericText(
  text: string,
  opts: { min: number; emptyAs: number; decimals?: number },
): number {
  const trimmed = text.trim();
  if (trimmed === '' || trimmed === '.') return opts.emptyAs;
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return opts.emptyAs;
  const clamped = Math.max(opts.min, n);
  return opts.decimals != null ? roundMoney(clamped) : clamped;
}

export function NewInvoicePage() {
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const barcodeRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [lines, setLines] = useState<DraftLine[]>([]);
  const [productQuery, setProductQuery] = useState('');
  const debouncedProductQuery = useDebouncedValue(productQuery, 300);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingStatus, setEditingStatus] = useState<SalesInvoice['status'] | null>(null);
  const [loadedEdit, setLoadedEdit] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const [customerId, setCustomerId] = useState<number | ''>('');
  const [invoiceType, setInvoiceType] = useState<InvoiceType>('GST');
  const [invoiceDate, setInvoiceDate] = useState(todayIso());
  const [paymentTermsDays, setPaymentTermsDays] = useState(30);
  const [dueDate, setDueDate] = useState(() => addDaysIso(todayIso(), 30));
  const [showPaymentTerms, setShowPaymentTerms] = useState(true);

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

  const [additionalCharges, setAdditionalCharges] = useState(0);
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
  const [partyDialogOpen, setPartyDialogOpen] = useState(false);
  const [itemDialogOpen, setItemDialogOpen] = useState(false);
  const [partyForm, setPartyForm] = useState({ name: '', phone: '', gstin: '', state: '' });
  const [itemForm, setItemForm] = useState({
    name: '',
    sku: '',
    hsnCode: '',
    sellingPrice: '',
    mrp: '',
    gstRate: '18',
  });
  const [signatureUrl, setSignatureUrl] = useState<string | null>(null);
  const [signatureId, setSignatureId] = useState<number | null>(null);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
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
  const products = useQuery({
    queryKey: ['product-search', debouncedProductQuery],
    queryFn: () => searchProducts(debouncedProductQuery),
    enabled: debouncedProductQuery.length >= 1,
  });

  useEffect(() => {
    if (!series.data || isEdit) return;
    setPrefix(series.data.prefix);
    setNextNumber(series.data.nextNumber);
  }, [series.data, isEdit]);

  useEffect(() => {
    // Remount-safe: when switching /sales/new ↔ /sales/history/:id/edit, reset hydrate flag.
    setLoadedEdit(false);
    setError(null);
    setMessage(null);
  }, [editId]);

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
    setInvoiceType(inv.invoiceType);
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
    const partyState =
      customers.data?.find((c) => c.id === inv.customer)?.gstin
      || customers.data?.find((c) => c.id === inv.customer)?.state
      || '';
    const mapped: DraftLine[] = (inv.items ?? []).map((item, idx) => {
      const qty = toNumber(item.quantity);
      const unitPrice = toNumber(item.unitPrice);
      const discountPercent = toNumber(item.discountPercent);
      const gstRate = toNumber(item.gstRate);
      const tax = calculateLineTax({
        quantity: qty,
        unitPrice,
        discountPercent,
        gstRate,
        intraState: isIntraState(companyState, partyState),
      });
      return {
        key: `edit-${item.id ?? idx}-${item.product}`,
        product: item.product,
        productName: item.productName ?? item.description ?? `Product #${item.product}`,
        description: item.description && item.description !== item.productName ? item.description : '',
        sku: '',
        hsnCode: item.hsnCode ?? '',
        unitName: item.unitName ?? 'PCS',
        batchNo: item.batchNo ?? '',
        expDate: item.expDate ?? '',
        mfgDate: item.mfgDate ?? '',
        mrp: toNumber(item.mrp),
        quantity: qty,
        unitPrice,
        gstRate,
        ...tax,
      };
    });
    setLines(mapped);
    setLoadedEdit(true);
  }, [existingInvoice.data, loadedEdit, company.data?.state, customers.data]);

  useEffect(() => {
    if (company.data?.invoiceTerms && !termsText && !isEdit) {
      setTermsText(company.data.invoiceTerms);
    }
    if (company.data?.signature) {
      setSignatureId(company.data.signature);
    }
  }, [company.data, termsText, isEdit]);

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

  const selectedCustomer = (customers.data ?? []).find((c) => c.id === Number(customerId));
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedCustomer?.gstin || selectedCustomer?.state,
  );

  const lineTaxes = useMemo(
    () =>
      lines.map((l) =>
        calculateLineTax({
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          discountPercent: l.discountPercent,
          gstRate: invoiceType === 'NON_GST' ? 0 : l.gstRate,
          intraState,
        }),
      ),
    [lines, intraState, invoiceType],
  );

  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((l, i) => ({
          ...l,
          gstRate: invoiceType === 'NON_GST' ? 0 : lines[i]?.gstRate ?? 0,
          intraState,
        })),
        {
          additionalCharges,
          invoiceDiscount,
          applyRoundOff: autoRoundOff,
          invoiceDiscountMode,
        },
      ),
    [lineTaxes, lines, additionalCharges, invoiceDiscount, autoRoundOff, invoiceDiscountMode, intraState, invoiceType],
  );

  const posKnown =
    invoiceType === 'NON_GST' ||
    !company.data?.isGstRegistered ||
    company.data?.assumeLocalStateForBlankParty ||
    placeOfSupplyKnown(selectedCustomer?.state, selectedCustomer?.gstin);

  const balance = roundMoney(Math.max(0, totals.grandTotal - amountReceived));

  useEffect(() => {
    if (markFullyPaid) setAmountReceived(totals.grandTotal);
  }, [markFullyPaid, totals.grandTotal]);

  const resetForm = () => {
    // BUG-500: message/error are intentionally NOT cleared here — this is
    // called from the "Save & New" success handler right after it sets a
    // confirmation flash message, and clearing it in the same tick (React
    // batches both updates) silently wiped that message (and any
    // payment-allocation warning) before it was ever shown.
    setLines([]);
    setCustomerId('');
    setInvoiceType('GST');
    setInvoiceDate(todayIso());
    setPaymentTermsDays(30);
    setNotes('');
    setShowNotes(false);
    setShowTerms(false);
    setShowBank(false);
    setShowQr(false);
    setAdditionalCharges(0);
    setInvoiceDiscount(0);
    setInvoiceDiscountMode('AFTER_TAX');
    setAmountReceived(0);
    setMarkFullyPaid(false);
    setPaymentMode('CASH');
    void qc.invalidateQueries({ queryKey: ['sales-invoice-number-series'] });
    barcodeRef.current?.focus();
  };

  const buildPayload = () => ({
    customer: Number(customerId),
    invoiceType,
    invoiceDate,
    dueDate,
    paymentTermsDays,
    additionalCharges,
    invoiceDiscount,
    invoiceDiscountMode,
    autoRoundOff,
    notes,
    termsText: showTerms ? termsText : '',
    includeBankDetails: showBank,
    includePaymentQr: showQr,
    includeTerms: showTerms,
    signature: signatureId,
    items: lines.map((l) => ({
      product: l.product,
      description: l.description || l.productName,
      quantity: l.quantity,
      unitPrice: l.unitPrice,
      discountPercent: l.discountPercent,
      gstRate: invoiceType === 'NON_GST' ? 0 : l.gstRate,
      batchNo: l.batchNo || undefined,
      expDate: l.expDate || null,
      mfgDate: l.mfgDate || null,
    })),
  });

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete' | 'complete_new') => {
      if (!customerId) throw new Error('Customer is required');
      if (lines.length === 0) throw new Error('Add at least one item');

      const payload = buildPayload();
      let invoice: SalesInvoice;
      let completeWarning: string | null = null;
      if (isEdit && editId) {
        invoice = await updateSalesInvoice(editId, payload);
        if (mode !== 'draft' && invoice.status === 'DRAFT') {
          try {
            invoice = await completeSalesInvoice(invoice.id);
          } catch (err) {
            completeWarning = getErrorMessage(err);
          }
        }
      } else {
        invoice = await createSalesInvoice(payload);
        if (mode !== 'draft') {
          try {
            invoice = await completeSalesInvoice(invoice.id);
          } catch (err) {
            // Invoice exists as draft — still open it; don't leave user on a blank form.
            completeWarning = getErrorMessage(err);
          }
        }
      }

      let paymentWarning: string | null = completeWarning;
      if (mode !== 'draft' && amountReceived > 0 && invoice.status === 'COMPLETED') {
        const already = toNumber(invoice.received);
        const toAllocate = Math.max(0, amountReceived - already);
        if (toAllocate > 0) {
          try {
            const receipt = await createReceipt({
              customer: Number(customerId),
              amount: toAllocate,
              mode: paymentMode,
              receiptDate: invoiceDate,
              notes: `Against ${invoice.number ?? invoice.id}`,
            });
            await createAllocation({
              receipt: receipt.id,
              salesInvoice: invoice.id,
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
      setError(paymentWarning ?? null);
      void qc.invalidateQueries({ queryKey: ['sales-invoice-number-series'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoice.id] });
      const label = invoice.number?.trim() ? invoice.number : `Draft #${invoice.id}`;

      if (mode === 'complete_new' && invoice.status === 'COMPLETED') {
        setMessage(`Invoice ${label} saved — start the next one`);
        resetForm();
        navigate('/sales/new', { replace: true });
        return;
      }

      const flash =
        invoice.status === 'COMPLETED'
          ? `Invoice ${label} saved`
          : `Draft ${label} saved${paymentWarning ? ` — complete failed: ${paymentWarning}` : ''}`;

      // Warm list cache before SPA navigate so history isn't blank until hard refresh.
      try {
        await qc.fetchQuery({
          queryKey: ['sales-invoices'],
          queryFn: () => listSalesInvoicesPage(),
          staleTime: 0,
        });
      } catch {
        void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      }

      navigate('/sales/history', {
        replace: true,
        state: {
          message: flash,
          ...(paymentWarning ? { paymentWarning } : {}),
        },
      });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const partyMutation = useMutation({
    mutationFn: () =>
      createCustomer({
        name: partyForm.name.trim(),
        phone: partyForm.phone,
        gstin: partyForm.gstin,
        state: partyForm.state,
        status: 'ACTIVE',
      }),
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ['customers'] });
      setCustomerId(c.id);
      setPartyDialogOpen(false);
      setPartyForm({ name: '', phone: '', gstin: '', state: '' });
      if (c.creditDays) setPaymentTermsDays(c.creditDays);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const itemMutation = useMutation({
    mutationFn: () =>
      createProduct({
        name: itemForm.name.trim(),
        sku: itemForm.sku,
        hsnCode: itemForm.hsnCode,
        sellingPrice: Number(itemForm.sellingPrice) || 0,
        mrp: Number(itemForm.mrp) || 0,
        gstRate: Number(itemForm.gstRate) || 0,
        purchasePrice: 0,
        reorderLevel: 0,
        status: 'ACTIVE',
      }),
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ['products'] });
      setLines((prev) => [...prev, makeLine(p, intraState)]);
      setItemDialogOpen(false);
      setItemForm({
        name: '',
        sku: '',
        hsnCode: '',
        sellingPrice: '',
        mrp: '',
        gstRate: '18',
      });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const addProduct = (product: Product | null) => {
    if (!product) return;
    if (product.status !== 'ACTIVE') {
      setError('Cannot sell inactive product');
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
    // BUG-513: warn before an accidental tab close/refresh discards a
    // half-built invoice — no confirmation existed at all previously.
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

  const activeCustomers = (customers.data ?? []).filter((c) => c.status === 'ACTIVE');
  const canSave = lines.length > 0 && Boolean(customerId) && !saveMutation.isPending;
  const canComplete = canSave && posKnown;

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

  if (isEdit && existingInvoice.isLoading) return <LoadingState />;
  if (isEdit && existingInvoice.isError) {
    return (
      <ErrorState
        message={getErrorMessage(existingInvoice.error)}
        onRetry={() => void existingInvoice.refetch()}
      />
    );
  }
  if (isEdit && existingInvoice.isSuccess && !existingInvoice.data) return <EmptyState />;

  return (
    <Stack spacing={2} sx={{ pb: 4 }}>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        flexWrap="wrap"
        gap={1}
      >
        <Typography variant="h4">
          {isEdit ? t('billing.editTitle') : t('billing.title')}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title={t('billing.shortcuts')}>
            <IconButton size="small" aria-label="shortcuts" onClick={() => setShortcutsOpen(true)}>
              <KeyboardIcon />
            </IconButton>
          </Tooltip>
          <Button
            startIcon={<SettingsIcon />}
            variant="outlined"
            size="small"
            onClick={() => setSettingsOpen(true)}
          >
            {t('billing.settings')}
          </Button>
          <Button
            variant="contained"
            disabled={isEdit && editingStatus === 'COMPLETED' ? !canSave : !canComplete}
            onClick={() =>
              saveMutation.mutate(
                isEdit && editingStatus === 'COMPLETED' ? 'draft' : 'complete',
              )
            }
          >
            {/* BUG-507: this button completes/finalizes the document unless
                editing an already-COMPLETED one — label it accordingly so
                editing a draft doesn't say "Save" while silently finalizing it. */}
            {isEdit && editingStatus === 'COMPLETED'
              ? t('common.save')
              : isEdit
                ? t('billing.saveAndComplete')
                : t('billing.save')}
          </Button>
          <Button
            variant="outlined"
            disabled={!canComplete || isEdit}
            onClick={() => saveMutation.mutate('complete_new')}
          >
            {t('billing.saveAndNew')}
          </Button>
          {(!isEdit || editingStatus === 'DRAFT') && (
            <Button size="small" disabled={!canSave} onClick={() => saveMutation.mutate('draft')}>
              {t('common.draft')}
            </Button>
          )}
          {isEdit ? (
            <Button size="small" component={RouterLink} to={`/sales/history/${editId}`}>
              {t('common.back')}
            </Button>
          ) : null}
        </Stack>
      </Stack>

      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {isEdit && editingStatus === 'COMPLETED' ? (
        <Alert severity="warning">{t('billing.editingCompletedWarning')}</Alert>
      ) : null}

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Box
            sx={{
              flex: 1.2,
              border: '1px dashed',
              borderColor: 'primary.light',
              borderRadius: 1,
              p: 2,
              minHeight: 120,
            }}
          >
            <Typography variant="caption" color="text.secondary">
              {t('billing.billTo')}
            </Typography>
            {selectedCustomer ? (
              <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                  <Box>
                    <Typography fontWeight={700}>{selectedCustomer.name}</Typography>
                    {selectedCustomer.phone ? (
                      <Typography variant="body2" color="text.secondary">
                        {selectedCustomer.phone}
                      </Typography>
                    ) : null}
                    {selectedCustomer.gstin ? (
                      <Typography variant="body2" color="text.secondary">
                        GSTIN: {selectedCustomer.gstin}
                      </Typography>
                    ) : null}
                    {selectedCustomer.billingAddress ? (
                      <Typography variant="body2" color="text.secondary">
                        {selectedCustomer.billingAddress}
                      </Typography>
                    ) : null}
                  </Box>
                  {editingStatus !== 'COMPLETED' ? (
                    <Button size="small" onClick={() => setCustomerId('')}>
                      Change
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
            ) : (
              <Stack spacing={1} sx={{ mt: 1 }}>
                <Autocomplete<Customer>
                  options={activeCustomers}
                  getOptionLabel={(o) => o.name}
                  value={null}
                  onChange={(_, v) => {
                    setCustomerId(v?.id ?? '');
                    if (v?.creditDays) setPaymentTermsDays(v.creditDays);
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label={t('billing.customer')}
                      placeholder="Search or select customer…"
                    />
                  )}
                />
                <Link
                  component="button"
                  type="button"
                  underline="hover"
                  onClick={() => setPartyDialogOpen(true)}
                >
                  + {t('billing.createParty')}
                </Link>
              </Stack>
            )}
          </Box>

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
            <Stack direction="row" spacing={1}>
              <CompactField
                label={t('billing.invoiceDate')}
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <CompactField
                select
                label={t('billing.invoiceType')}
                value={invoiceType}
                onChange={(e) => setInvoiceType(e.target.value as InvoiceType)}
              >
                <MenuItem value="GST">GST Invoice</MenuItem>
                <MenuItem value="TAX">Tax Invoice</MenuItem>
                <MenuItem value="RETAIL">Retail Invoice</MenuItem>
                <MenuItem value="NON_GST">Non-GST Invoice</MenuItem>
              </CompactField>
            </Stack>
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
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell width={48}>{t('billing.no')}</TableCell>
              <TableCell sx={{ minWidth: 180 }}>{t('billing.items')}</TableCell>
              <TableCell width={90}>{t('billing.hsn')}</TableCell>
              {showBatchCols ? (
                <>
                  <TableCell width={90}>{t('billing.batchNo')}</TableCell>
                  <TableCell width={110}>{t('billing.expDate')}</TableCell>
                  <TableCell width={110}>{t('billing.mfgDate')}</TableCell>
                </>
              ) : null}
              <TableCell width={80} align="right">
                {t('billing.mrp')}
              </TableCell>
              <TableCell width={130}>{t('billing.qty')}</TableCell>
              <TableCell width={110} align="right">
                {t('billing.price')}
              </TableCell>
              <TableCell width={200}>{t('billing.discount')}</TableCell>
              <TableCell width={100}>{t('billing.tax')}</TableCell>
              <TableCell width={100} align="right">
                {t('billing.amount')}
              </TableCell>
              <TableCell width={72} />
            </TableRow>
          </TableHead>
          <TableBody>
            {lines.map((line, idx) => {
              const tax = lineTaxes[idx];
              const mrpOff =
                line.mrp > 0 && line.unitPrice < line.mrp
                  ? roundMoney(((line.mrp - line.unitPrice) / line.mrp) * 100)
                  : null;
              return (
                <TableRow key={line.key} hover>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>
                    <Typography fontWeight={600} variant="body2">
                      {line.productName}
                    </Typography>
                    <CompactField
                      placeholder="Description (optional)"
                      value={line.description}
                      onChange={(e) => updateLine(line.key, { description: e.target.value })}
                      sx={{ mt: 0.5 }}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{line.hsnCode || '—'}</Typography>
                  </TableCell>
                  {showBatchCols ? (
                    <>
                      <TableCell>
                        <CompactField
                          value={line.batchNo}
                          onChange={(e) => updateLine(line.key, { batchNo: e.target.value })}
                        />
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
                  ) : null}
                  <TableCell align="right">
                    <Typography variant="body2">
                      {line.mrp > 0 ? formatMoney(line.mrp) : '—'}
                    </Typography>
                    {mrpOff != null ? (
                      <Typography variant="caption" color="success.main" title="Savings vs MRP (not line discount)">
                        {mrpOff}% vs MRP
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 110 }}>
                      <NumericField
                        value={line.quantity}
                        onValueChange={(n) =>
                          updateLine(line.key, { quantity: n > 0 ? n : 1 })
                        }
                        min={0}
                        emptyAs={1}
                        fullWidth={false}
                        sx={{ width: 80, minWidth: 80 }}
                      />
                      <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                        {line.unitName}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <NumericField
                      value={line.unitPrice}
                      onValueChange={(n) => updateLine(line.key, { unitPrice: n })}
                      min={0}
                      decimals={2}
                      fullWidth={false}
                      sx={{ width: 96, minWidth: 96 }}
                    />
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} sx={{ minWidth: 180 }}>
                      <NumericField
                        value={line.discountPercent}
                        onValueChange={(n) =>
                          updateLine(line.key, { discountPercent: Math.min(100, n) })
                        }
                        min={0}
                        decimals={2}
                        fullWidth={false}
                        sx={{ width: 88, minWidth: 88 }}
                        InputProps={{
                          endAdornment: <InputAdornment position="end">%</InputAdornment>,
                        }}
                      />
                      <NumericField
                        value={line.discountAmount}
                        onValueChange={(n) =>
                          updateLine(line.key, { discountAmount: n }, { fromDiscountAmount: true })
                        }
                        min={0}
                        decimals={2}
                        fullWidth={false}
                        sx={{ width: 96, minWidth: 96 }}
                        InputProps={{
                          startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                        }}
                      />
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {invoiceType === 'NON_GST' || line.gstRate <= 0 ? '0%' : `${line.gstRate}%`}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      (₹ {(tax?.taxTotal ?? 0).toFixed(2)})
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography fontWeight={600}>{formatMoney(tax?.lineTotal ?? 0)}</Typography>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row">
                      <IconButton
                        size="small"
                        color="primary"
                        aria-label="add row"
                        onClick={() => barcodeRef.current?.focus()}
                      >
                        <AddIcon fontSize="small" />
                      </IconButton>
                      <IconButton
                        size="small"
                        aria-label={t('common.remove')}
                        onClick={() => setLines((prev) => prev.filter((x) => x.key !== line.key))}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>

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
              onInputChange={(_, v) => setProductQuery(v)}
              onChange={(_, v) => addProduct(v)}
              getOptionLabel={(o) =>
                `${o.name} · ${o.sku}${o.unitName ? ` · ${o.unitName}` : ''}`
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  inputRef={barcodeRef}
                  placeholder={`+ ${t('billing.addItem')} / ${t('billing.searchProduct')}`}
                  autoFocus
                />
              )}
            />
            <Link
              component="button"
              type="button"
              underline="hover"
              onClick={() => setItemDialogOpen(true)}
              sx={{ whiteSpace: 'nowrap' }}
            >
              + {t('billing.createItem')}
            </Link>
          </Box>
          <Button
            variant="outlined"
            startIcon={<QrCodeScannerIcon />}
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
          <Typography fontWeight={700}>
            {t('billing.totalAmount')} {formatMoney(totals.grandTotal)}
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

        <Paper sx={{ p: 2, width: '100%', maxWidth: 420, ml: { md: 'auto' } }}>
          <Stack spacing={1.25}>
            <Row
              label={`+ ${t('billing.additionalCharges')}`}
              value={
                <NumericField
                  value={additionalCharges}
                  onValueChange={setAdditionalCharges}
                  min={0}
                  decimals={2}
                  fullWidth={false}
                  InputProps={{
                    startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                  }}
                  sx={{ maxWidth: 140 }}
                />
              }
            />
            <Row label={t('billing.taxableAmount')} value={formatMoney(totals.taxableTotal)} />
            {totals.cgstTotal > 0 ? (
              <Row label={t('billing.cgst')} value={formatMoney(totals.cgstTotal)} />
            ) : null}
            {totals.sgstTotal > 0 ? (
              <Row label={t('billing.sgst')} value={formatMoney(totals.sgstTotal)} />
            ) : null}
            {totals.igstTotal > 0 ? (
              <Row label={t('billing.igst')} value={formatMoney(totals.igstTotal)} />
            ) : null}
            <Row
              label={t('billing.invoiceDiscount')}
              value={
                <Stack direction="row" spacing={1} alignItems="center">
                  <CompactField
                    select
                    value={invoiceDiscountMode}
                    onChange={(e) => setInvoiceDiscountMode(e.target.value as InvoiceDiscountMode)}
                    sx={{ minWidth: 180 }}
                  >
                    <MenuItem value="AFTER_TAX">{t('billing.invoiceDiscountAfterTax')}</MenuItem>
                    <MenuItem value="BEFORE_TAX">{t('billing.invoiceDiscountBeforeTax')}</MenuItem>
                  </CompactField>
                  <NumericField
                    value={invoiceDiscount}
                    onValueChange={setInvoiceDiscount}
                    min={0}
                    decimals={2}
                    fullWidth={false}
                    InputProps={{
                      startAdornment: <InputAdornment position="start">₹</InputAdornment>,
                    }}
                    sx={{ maxWidth: 120 }}
                  />
                </Stack>
              }
            />
            {!posKnown ? (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {t('billing.placeOfSupplyRequired')}
              </Alert>
            ) : null}
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <FormControlLabel
                control={
                  <Checkbox
                    checked={autoRoundOff}
                    onChange={(e) => setAutoRoundOff(e.target.checked)}
                    size="small"
                  />
                }
                label={t('billing.autoRoundOff')}
              />
              <Typography variant="body2">{formatMoney(totals.roundOff)}</Typography>
            </Stack>
            <Divider />
            <Row label={t('billing.totalAmount')} value={formatMoney(totals.grandTotal)} bold />
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography>{t('billing.amountReceived')}</Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={markFullyPaid}
                    onChange={(e) => {
                      setMarkFullyPaid(e.target.checked);
                      if (e.target.checked) setAmountReceived(totals.grandTotal);
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
          </Stack>
        </Paper>
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
        open={partyDialogOpen}
        onClose={() => setPartyDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('billing.createParty')}</DialogTitle>
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
            <TextField
              label={t('auth.state')}
              value={partyForm.state}
              onChange={(e) => setPartyForm((f) => ({ ...f, state: e.target.value }))}
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
            {t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={itemDialogOpen} onClose={() => setItemDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('billing.createItem')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
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
            />
            <TextField
              label="HSN"
              value={itemForm.hsnCode}
              onChange={(e) => setItemForm((f) => ({ ...f, hsnCode: e.target.value }))}
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
          <Button onClick={() => setItemDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!itemForm.name.trim() || itemMutation.isPending}
            onClick={() => itemMutation.mutate()}
          >
            {t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

function Row({
  label,
  value,
  bold,
}: {
  label: string;
  value: ReactNode;
  bold?: boolean;
}) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
      <Typography fontWeight={bold ? 700 : 400}>{label}</Typography>
      {typeof value === 'string' || typeof value === 'number' ? (
        <Typography fontWeight={bold ? 700 : 500}>{value}</Typography>
      ) : (
        value
      )}
    </Box>
  );
}

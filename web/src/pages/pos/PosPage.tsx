/**
 * Wave 18D — POS MVP counter mode (BB-000181).
 * Not a full retail suite; uses standard sales invoice + receipt APIs.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import RemoveIcon from '@mui/icons-material/Remove';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import { useQuery } from '@tanstack/react-query';
import {
  completeSalesInvoice,
  createAllocation,
  createCustomer,
  createReceipt,
  createSalesInvoice,
  deleteSalesInvoice,
  downloadInvoiceThermalPdf,
  getCompany,
  getCustomer,
  getUpiQr,
  listCustomersPage,
  listStock,
  searchProducts,
} from '@/api/resources';
import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { isPosEnabled } from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { NumericField, todayIso, useDebouncedValue } from '@/components/billing';
import { LoadingState } from '@/components/PageState';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { filledCustomFieldPreview } from '@/pages/inventory/itemCustomFieldDefaults';
import { PageShell } from '@/pages/phase/phaseShared';
import { t, useLocale } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  enqueueDraft,
  flushOutbox,
  listDrafts,
  removeDraft,
  OUTBOX_WARNING_DISMISS_KEY,
  type InvoiceDraftLine,
} from '@/offline/invoiceDraftCache';
import type { Customer, PaymentMode, Product } from '@/types/domain';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import { printBlob } from '@/utils/blob';
import { isAllowedPaymentUrl } from '@/utils/safeUrl';
import { formatMoney, toNumber } from '@/utils/money';
import {
  calculateLineTax,
  calculateInvoiceTotals,
  extractExclusiveFromInclusiveLine,
  isIntraState,
} from '@/utils/tax';

interface CartLine {
  key: string;
  product: Product;
  quantity: number;
  discountPercent: number;
}

interface UpiPending {
  invoiceId: number;
  invoiceNumber: string;
  customer: number;
  amount: number;
  key?: string;
  upiQr: Record<string, string> | null;
}

function posEnabled(): boolean {
  return isPosEnabled() || isRuntimeFlagEnabled('ENABLE_POS');
}

function draftLinesFromCart(cart: CartLine[], taxEnabled: boolean): InvoiceDraftLine[] {
  return cart.map((line) => ({
    productId: line.product.id,
    productName: line.product.name,
    sku: line.product.sku,
    quantity: line.quantity,
    unitPrice: toNumber(line.product.sellingPrice),
    gstRate: taxEnabled ? toNumber(line.product.gstRate) : 0,
    discountPercent: line.discountPercent || 0,
  }));
}

export function PosPage() {
  useLocale();
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const searchRef = useRef<HTMLInputElement>(null);

  const [cart, setCart] = useState<CartLine[]>([]);
  const [productQuery, setProductQuery] = useState('');
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const debouncedQuery = useDebouncedValue(productQuery, 250);
  const [customerId, setCustomerId] = useState<number | ''>('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(() =>
    typeof navigator !== 'undefined' ? !navigator.onLine : false,
  );
  const [hasOutboxItems, setHasOutboxItems] = useState(false);
  const [hideOutboxWarn, setHideOutboxWarn] = useState(
    () =>
      typeof localStorage !== 'undefined' &&
      localStorage.getItem(OUTBOX_WARNING_DISMISS_KEY) === '1',
  );
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [cashTendered, setCashTendered] = useState<number | ''>('');
  const [upiPending, setUpiPending] = useState<UpiPending | null>(null);
  const flushGuard = useRef(false);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const taxEnabled = preferredInvoiceType(company.data?.registrationType) !== 'NON_GST';
  const posInvoiceType = taxEnabled ? 'RETAIL' : 'NON_GST';
  const customers = useQuery({
    queryKey: ['pos-customers'],
    queryFn: () => listCustomersPage({ pageSize: 100 }),
  });
  const selectedCustomer = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: Boolean(customerId),
  });
  const hasCf = Object.values(cfFilters).some((values) => values.length);
  const products = useQuery({
    queryKey: ['pos-product-search', debouncedQuery, cfFilters],
    queryFn: () => searchProducts(debouncedQuery, { cf: cfFilters }),
    enabled: debouncedQuery.length >= 1 || hasCf,
  });
  const stockBalances = useQuery({
    queryKey: ['stock'],
    queryFn: () => listStock(),
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

  const activeCustomers = useMemo(() => {
    const rows = (customers.data?.results ?? []).filter((c) => c.status === 'ACTIVE');
    return [...rows].sort((a, b) => {
      const aw = /walk[\s-]?in/i.test(a.name) ? 0 : 1;
      const bw = /walk[\s-]?in/i.test(b.name) ? 0 : 1;
      return aw - bw || a.name.localeCompare(b.name);
    });
  }, [customers.data?.results]);

  const walkInCustomer = useMemo(
    () => activeCustomers.find((c) => /walk[\s-]?in/i.test(c.name)),
    [activeCustomers],
  );

  useEffect(() => {
    if (!customerId && walkInCustomer?.id) {
      setCustomerId(walkInCustomer.id);
    }
  }, [walkInCustomer, customerId]);

  useEffect(() => {
    void listDrafts(companyId, userId).then((drafts) => {
      setHasOutboxItems(drafts.some((row) => row.kind === 'pos' || row.kind === 'invoice'));
      const draft = [...drafts].reverse().find((row) => row.kind === 'pos');
      if (!draft || navigator.onLine) return;
      if (!draft.lines || draft.customerId == null) return;
      setIdempotencyKey(draft.idempotencyKey);
      setCustomerId(draft.customerId);
      setCart(
        draft.lines.map((line) => ({
          key: `${line.productId}-${line.sku}`,
          product: {
            id: line.productId,
            name: line.productName,
            sku: line.sku,
            sellingPrice: line.unitPrice,
            gstRate: line.gstRate,
            purchasePrice: 0,
            reorderLevel: 0,
            status: 'ACTIVE',
          } as Product,
          quantity: line.quantity,
          discountPercent: line.discountPercent ?? 0,
        })),
      );
      setMessage(t('pos.recoveredDraft'));
    });
  }, [companyId, userId]);

  const intraState = useMemo(() => {
    const party = selectedCustomer.data;
    return isIntraState(company.data?.gstin ?? company.data?.state, party?.gstin ?? party?.state, {
      assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty,
    });
  }, [company.data, selectedCustomer.data]);

  const isInclusive = company.data?.priceMode === 'INCLUSIVE';

  const lineTaxes = useMemo(
    () =>
      cart.map((line) => {
        let unitPrice = toNumber(line.product.sellingPrice);
        let discountPercent = line.discountPercent || 0;
        if (isInclusive) {
          const extracted = extractExclusiveFromInclusiveLine({
            quantity: line.quantity,
            unitPriceInclusive: unitPrice,
            discountPercent,
            gstRate: taxEnabled ? toNumber(line.product.gstRate) : 0,
            cessRate: toNumber((line.product as { cessRate?: number }).cessRate),
          });
          unitPrice = extracted.exclusiveUnitPrice;
          discountPercent = 0;
        }
        return calculateLineTax({
          quantity: line.quantity,
          unitPrice,
          gstRate: taxEnabled ? toNumber(line.product.gstRate) : 0,
          cessRate: toNumber((line.product as { cessRate?: number }).cessRate),
          discountPercent,
          intraState,
        });
      }),
    [cart, intraState, isInclusive, taxEnabled],
  );

  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((tax, i) => ({
          ...tax,
          gstRate: taxEnabled ? toNumber(cart[i]?.product.gstRate) : 0,
          intraState,
        })),
        { applyRoundOff: true },
      ),
    [lineTaxes, cart, intraState, taxEnabled],
  );

  const tenderedAmount =
    cashTendered === '' ? totals.grandTotal : toNumber(cashTendered);
  const changeDue = Math.max(0, tenderedAmount - totals.grandTotal);

  const addProduct = (product: Product | null) => {
    if (!product || product.status !== 'ACTIVE') return;
    setCart((prev) => {
      const existing = prev.find((l) => l.product.id === product.id);
      if (existing) {
        return prev.map((l) =>
          l.key === existing.key ? { ...l, quantity: l.quantity + 1 } : l,
        );
      }
      return [
        ...prev,
        { key: `${product.id}-${Date.now()}`, product, quantity: 1, discountPercent: 0 },
      ];
    });
    setProductQuery('');
    setError(null);
    searchRef.current?.focus();
  };

  const tryAddByBarcode = async () => {
    const q = productQuery.trim();
    if (!q) return;
    let matches: Product[] = [];
    try {
      matches = (await searchProducts(q)).filter((p) => p.status === 'ACTIVE');
    } catch {
      matches = (products.data ?? []).filter((p) => p.status === 'ACTIVE');
    }
    const exact =
      matches.find((p) => (p.barcode ?? '').toLowerCase() === q.toLowerCase()) ??
      matches.find((p) => p.sku.toLowerCase() === q.toLowerCase()) ??
      (matches.length === 1 ? matches[0] : undefined);
    if (exact) {
      addProduct(exact);
      return;
    }
    setError(t('pos.barcodeNotFound', { q }));
  };

  const updateQty = (key: string, quantity: number) => {
    if (quantity <= 0) {
      setCart((prev) => prev.filter((l) => l.key !== key));
      return;
    }
    setCart((prev) => prev.map((l) => (l.key === key ? { ...l, quantity } : l)));
  };

  const updateDiscount = (key: string, discountPercent: number) => {
    const clamped = Math.min(100, Math.max(0, discountPercent));
    setCart((prev) => prev.map((l) => (l.key === key ? { ...l, discountPercent: clamped } : l)));
  };

  const clearCart = () => {
    setCart([]);
    if (idempotencyKey) void removeDraft(companyId, userId, idempotencyKey);
    setIdempotencyKey(null);
    setCashTendered('');
    setUpiPending(null);
    setMessage(null);
    setError(null);
    searchRef.current?.focus();
  };

  const finishSale = useCallback(
    async (completed: { id: number; number?: string | null }, key?: string) => {
      try {
        const blob = await downloadInvoiceThermalPdf(completed.id);
        printBlob(blob);
      } catch {
        // Thermal print fallback
      }
      if (key) await removeDraft(companyId, userId, key);
      setCart([]);
      setIdempotencyKey(null);
      setCashTendered('');
      setUpiPending(null);
      setMessage(t('pos.saleComplete', { number: completed.number ?? `#${completed.id}` }));
    },
    [companyId, userId],
  );

  const createCompletedInvoice = useCallback(
    async (lines: InvoiceDraftLine[], customer: number, key?: string) => {
      const invoiceDate = todayIso();
      const isInclusive = company.data?.priceMode === 'INCLUSIVE';
      const invoice = await createSalesInvoice(
        {
          customer,
          invoiceType: posInvoiceType,
          priceMode: isInclusive ? 'INCLUSIVE' : 'EXCLUSIVE',
          invoiceDate,
          dueDate: invoiceDate,
          paymentTermsDays: 0,
          autoRoundOff: true,
          items: lines.map((line) => ({
            product: line.productId,
            description: line.productName,
            quantity: line.quantity,
            unitPrice: line.unitPrice,
            unitPriceInclusive: isInclusive ? line.unitPrice : undefined,
            gstRate: taxEnabled ? line.gstRate : 0,
            discountPercent: line.discountPercent ?? 0,
          })),
        },
        { idempotencyKey: key },
      );
      try {
        return await completeSalesInvoice(invoice.id);
      } catch (err) {
        try {
          await deleteSalesInvoice(invoice.id);
        } catch {
          /* leftover draft if delete is blocked */
        }
        throw err;
      }
    },
    [company.data?.priceMode, posInvoiceType, taxEnabled],
  );

  const performCashCheckout = useCallback(
    async (lines: InvoiceDraftLine[], customer: number, key?: string) => {
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const completed = await createCompletedInvoice(lines, customer, key);
        const invoiceDate = todayIso();
        const receiptKey = key ? `${key}-receipt` : undefined;
        const invoiceTotal = toNumber(completed.grandTotal);
        const receipt = await createReceipt(
          {
            customer,
            amount: invoiceTotal,
            mode: 'CASH',
            receiptDate: invoiceDate,
            notes: `POS — ${completed.number ?? completed.id}`,
          },
          { idempotencyKey: receiptKey },
        );
        await createAllocation({
          receipt: receipt.id,
          salesInvoice: completed.id,
          amount: invoiceTotal,
        });
        await finishSale(completed, key);
      } catch (err) {
        setError(getErrorMessage(err));
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [createCompletedInvoice, finishSale],
  );

  /** Offline flush / recovery: complete sale with receipt for queued cash drafts. */
  const performCheckout = useCallback(
    async (mode: PaymentMode, lines: InvoiceDraftLine[], customer: number, key?: string) => {
      if (mode === 'UPI') {
        // Offline UPI drafts sync as unpaid completed invoices; cashier confirms later.
        setBusy(true);
        setError(null);
        try {
          const completed = await createCompletedInvoice(lines, customer, key);
          if (key) await removeDraft(companyId, userId, key);
          setCart([]);
          setIdempotencyKey(null);
          setMessage(
            t('pos.syncedUnpaid', { number: String(completed.number ?? `#${completed.id}`) }),
          );
        } catch (err) {
          setError(getErrorMessage(err));
          throw err;
        } finally {
          setBusy(false);
        }
        return;
      }
      await performCashCheckout(lines, customer, key);
    },
    [companyId, createCompletedInvoice, performCashCheckout, userId],
  );

  const startUpiCheckout = useCallback(
    async (lines: InvoiceDraftLine[], customer: number, key?: string) => {
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const completed = await createCompletedInvoice(lines, customer, key);
        const invoiceTotal = toNumber(completed.grandTotal);
        let upiQr: Record<string, string> | null = null;
        try {
          upiQr = await getUpiQr({ salesInvoice: completed.id });
        } catch (err) {
          setError(t('pos.upiQrFailed', { error: getErrorMessage(err) }));
        }
        setUpiPending({
          invoiceId: completed.id,
          invoiceNumber: String(completed.number ?? completed.id),
          customer,
          amount: invoiceTotal,
          key,
          upiQr,
        });
      } catch (err) {
        setError(getErrorMessage(err));
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [createCompletedInvoice],
  );

  const confirmUpiPayment = useCallback(async () => {
    if (!upiPending) return;
    setBusy(true);
    setError(null);
    try {
      const receiptKey = upiPending.key ? `${upiPending.key}-receipt` : newIdempotencyKey();
      const receipt = await createReceipt(
        {
          customer: upiPending.customer,
          amount: upiPending.amount,
          mode: 'UPI',
          receiptDate: todayIso(),
          notes: `POS UPI — ${upiPending.invoiceNumber}`,
        },
        { idempotencyKey: receiptKey },
      );
      await createAllocation({
        receipt: receipt.id,
        salesInvoice: upiPending.invoiceId,
        amount: upiPending.amount,
      });
      await finishSale(
        { id: upiPending.invoiceId, number: upiPending.invoiceNumber },
        upiPending.key,
      );
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }, [finishSale, upiPending]);

  const flushPendingDraft = useCallback(async () => {
    if (flushGuard.current || !navigator.onLine || !companyId || !userId) return;
    flushGuard.current = true;
    try {
      const result = await flushOutbox(
        companyId,
        userId,
        async (draft) => {
          await performCheckout(
            draft.paymentMode ?? 'CASH',
            draft.lines ?? [],
            draft.customerId ?? 0,
            draft.idempotencyKey,
          );
        },
        (draft) => draft.kind === 'pos',
      );
      if (result.failed > 0) {
        setError(
          t('pos.syncFailedDetail', {
            failed: String(result.failed),
            errors: result.errors.slice(0, 3).join(' · '),
          }),
        );
      } else if (result.flushed > 0) {
        setMessage(t('pos.syncedOfflineSales', { count: String(result.flushed) }));
      }
    } finally {
      flushGuard.current = false;
    }
  }, [companyId, performCheckout, userId]);

  useEffect(() => {
    const onOnline = () => {
      setOffline(false);
      void flushPendingDraft();
    };
    const onOffline = () => setOffline(true);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    if (navigator.onLine) void flushPendingDraft();
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, [flushPendingDraft]);

  const checkout = useCallback(
    async (mode: PaymentMode) => {
      if (writesBlocked) {
        setError(t('billing.writesBlocked'));
        return;
      }
      let effectiveCustomerId = customerId;
      if (!effectiveCustomerId) {
        if (walkInCustomer) {
          effectiveCustomerId = walkInCustomer.id;
          setCustomerId(walkInCustomer.id);
        } else {
          try {
            const created = await createCustomer({ name: t('pos.walkInCustomer'), status: 'ACTIVE' });
            effectiveCustomerId = created.id;
            setCustomerId(created.id);
          } catch {
            setError(t('pos.selectCustomer'));
            return;
          }
        }
      }
      if (cart.length === 0) {
        setError(t('pos.cartEmpty'));
        return;
      }
      if (mode === 'CASH' && tenderedAmount + 1e-9 < totals.grandTotal) {
        setError(t('pos.tenderTooLow'));
        return;
      }
      if (mode === 'UPI' && !navigator.onLine) {
        setError(t('pos.upiNeedsConnection'));
        return;
      }

      const lines = draftLinesFromCart(cart, taxEnabled);
      const key = idempotencyKey ?? newIdempotencyKey();
      setIdempotencyKey(key);

      if (!navigator.onLine) {
        const saved = await enqueueDraft(companyId, userId, {
          kind: 'pos',
          payload: { customer: Number(effectiveCustomerId), items: lines, paymentMode: mode },
          idempotencyKey: key,
          customerId: Number(effectiveCustomerId),
          paymentMode: mode,
          lines,
        });
        setIdempotencyKey(saved.idempotencyKey);
        setMessage(t('pos.savedOffline'));
        setError(null);
        return;
      }

      if (mode === 'UPI') {
        await startUpiCheckout(lines, Number(effectiveCustomerId), key);
        return;
      }
      await performCashCheckout(lines, Number(effectiveCustomerId), key);
    },
    [
      cart,
      companyId,
      customerId,
      idempotencyKey,
      performCashCheckout,
      startUpiCheckout,
      tenderedAmount,
      totals.grandTotal,
      userId,
      walkInCustomer,
      writesBlocked,
    ],
  );

  if (!posEnabled()) {
    return (
      <PageShell title={t('pos.title')}>
        <Typography>{t('pos.disabled')}</Typography>
      </PageShell>
    );
  }

  if (company.isLoading || customers.isLoading) return <LoadingState />;

  const upiIntent =
    upiPending?.upiQr?.intentUrl && isAllowedPaymentUrl(String(upiPending.upiQr.intentUrl))
      ? String(upiPending.upiQr.intentUrl)
      : '';
  const upiPng = upiPending?.upiQr?.qrPngBase64 || upiPending?.upiQr?.qr_png_base64;

  return (
    <PageShell title={t('pos.title')} subtitle={t('pos.subtitle')}>
      {offline || hasOutboxItems ? (
        !hideOutboxWarn || offline ? (
          <Alert
            severity="warning"
            sx={{ mb: 1 }}
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
      {offline ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {t('pos.offlineBanner')}
        </Alert>
      ) : null}
      {message ? (
        <Alert severity="success" onClose={() => setMessage(null)} sx={{ mb: 1 }}>
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} onClose={() => setError(null)} sx={{ mb: 1 }} />
      ) : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Paper variant="outlined" sx={{ flex: 1, p: 2 }}>
          <Stack spacing={2}>
            <TextField
              select
              label={t('pos.customer')}
              size="small"
              value={customerId === '' ? '' : customerId}
              onChange={(e) => {
                const v = e.target.value;
                setCustomerId(v === '' ? '' : Number(v));
              }}
              fullWidth
            >
              <MenuItem value="">
                <em>{t('pos.selectCustomerPlaceholder')}</em>
              </MenuItem>
              {walkInCustomer ? (
                <MenuItem value={walkInCustomer.id}>{t('pos.walkInNamed', { name: walkInCustomer.name })}</MenuItem>
              ) : null}
              {activeCustomers
                .filter((c) => c.id !== walkInCustomer?.id)
                .map((c: Customer) => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.name}
                    {c.phone ? ` · ${c.phone}` : ''}
                  </MenuItem>
                ))}
            </TextField>

            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
              <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
              <Autocomplete<Product>
                sx={{ flex: 1, minWidth: 220 }}
                options={(products.data ?? []).filter((p) => p.status === 'ACTIVE')}
                loading={products.isFetching}
                inputValue={productQuery}
                onInputChange={(_, v, reason) => {
                  if (reason === 'input' || reason === 'clear') setProductQuery(v);
                }}
                onChange={(_, v) => addProduct(v)}
                getOptionLabel={(o) =>
                  formatProductOptionLabel(o, availableByProduct.get(Number(o.id)))
                }
                renderOption={(props, option) => {
                  const extra = filledCustomFieldPreview(option.customFields, customDefs);
                  return (
                    <li {...props} key={option.id}>
                      <Box>
                        <Typography variant="body2">
                          {formatProductOptionLabel(option, availableByProduct.get(Number(option.id)))}
                        </Typography>
                        {extra ? (
                          <Typography variant="caption" color="text.secondary">
                            {extra}
                          </Typography>
                        ) : null}
                      </Box>
                    </li>
                  );
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    inputRef={searchRef}
                    size="small"
                    placeholder={t('pos.scanOrSearch')}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        void tryAddByBarcode();
                      }
                    }}
                  />
                )}
              />
              <IconButton onClick={() => searchRef.current?.focus()} aria-label={t('a11y.focusScanner')}>
                <QrCodeScannerIcon />
              </IconButton>
            </Box>

            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('pos.item')}</TableCell>
                  <TableCell align="right">{t('pos.qty')}</TableCell>
                  <TableCell align="right">{t('pos.discPercent')}</TableCell>
                  <TableCell align="right">{t('pos.price')}</TableCell>
                  <TableCell align="right">{t('pos.total')}</TableCell>
                  <TableCell width={48} />
                </TableRow>
              </TableHead>
              <TableBody>
                {cart.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography variant="body2" color="text.secondary">
                        {t('pos.addItemsHint')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  cart.map((line) => {
                    const tax = calculateLineTax({
                      quantity: line.quantity,
                      unitPrice: toNumber(line.product.sellingPrice),
                      gstRate: taxEnabled ? toNumber(line.product.gstRate) : 0,
                      discountPercent: line.discountPercent || 0,
                      intraState,
                    });
                    return (
                      <TableRow key={line.key}>
                        <TableCell>
                          <Typography variant="body2">{line.product.name}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {line.product.sku}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
                            <IconButton size="small" onClick={() => updateQty(line.key, line.quantity - 1)}>
                              <RemoveIcon fontSize="small" />
                            </IconButton>
                            <NumericField
                              value={line.quantity}
                              onValueChange={(n) => updateQty(line.key, n)}
                              min={1}
                              emptyAs={1}
                              fullWidth={false}
                              sx={{ width: 56 }}
                            />
                            <IconButton size="small" onClick={() => updateQty(line.key, line.quantity + 1)}>
                              <AddIcon fontSize="small" />
                            </IconButton>
                          </Stack>
                        </TableCell>
                        <TableCell align="right">
                          <NumericField
                            value={line.discountPercent}
                            onValueChange={(n) => updateDiscount(line.key, n)}
                            min={0}
                            emptyAs={0}
                            fullWidth={false}
                            sx={{ width: 64 }}
                          />
                        </TableCell>
                        <TableCell align="right">{formatMoney(line.product.sellingPrice)}</TableCell>
                        <TableCell align="right">{formatMoney(tax.lineTotal)}</TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => updateQty(line.key, 0)} aria-label={t('common.remove')}>
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ width: { xs: '100%', md: 320 }, p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="h6">{t('pos.tender')}</Typography>
            <Divider />
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">{t('pos.subtotal')}</Typography>
              <Typography>{formatMoney(totals.subtotal)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">{t('pos.tax')}</Typography>
              <Typography>{formatMoney(totals.taxTotal)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="h6">{t('pos.total')}</Typography>
              <Typography variant="h6">{formatMoney(totals.grandTotal)}</Typography>
            </Stack>
            <NumericField
              label={t('pos.cashTendered')}
              value={cashTendered === '' ? totals.grandTotal : cashTendered}
              onValueChange={(n) => setCashTendered(n)}
              min={0}
              emptyAs={totals.grandTotal}
              size="small"
              fullWidth
            />
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              <Chip
                label={t('pos.exact')}
                size="small"
                clickable
                onClick={() => setCashTendered(totals.grandTotal)}
                color={cashTendered === totals.grandTotal ? 'primary' : 'default'}
              />
              {[100, 200, 500, 2000].map((amt) => (
                <Chip
                  key={amt}
                  label={`₹${amt}`}
                  size="small"
                  clickable
                  onClick={() => setCashTendered(amt)}
                  color={cashTendered === amt ? 'primary' : 'default'}
                />
              ))}
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">{t('pos.change')}</Typography>
              <Typography>{formatMoney(changeDue)}</Typography>
            </Stack>
            <Divider />
            <Button
              variant="contained"
              size="large"
              disabled={writesBlocked || busy || cart.length === 0 || Boolean(upiPending)}
              onClick={() => void checkout('CASH')}
            >
              {t('pos.cashPay', { amount: formatMoney(totals.grandTotal) })}
            </Button>
            <Button
              variant="outlined"
              size="large"
              disabled={writesBlocked || busy || cart.length === 0 || Boolean(upiPending)}
              onClick={() => void checkout('UPI')}
            >
              {t('pos.upiPay', { amount: formatMoney(totals.grandTotal) })}
            </Button>
            <Button
              variant="text"
              color="inherit"
              disabled={busy || (cart.length === 0 && !upiPending)}
              onClick={clearCart}
            >
              {t('pos.clearCart')}
            </Button>
          </Stack>
        </Paper>
      </Stack>

      <Dialog
        open={Boolean(upiPending)}
        onClose={() => undefined}
        maxWidth="xs"
        fullWidth
        TransitionProps={{ onExited: () => searchRef.current?.focus() }}
      >
        <DialogTitle>{t('pos.upiTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              {t('pos.upiScanHint', {
                number: upiPending?.invoiceNumber ?? '',
                amount: formatMoney(upiPending?.amount ?? 0),
              })}
            </Typography>
            {upiIntent && upiPng ? (
              <Box
                component="img"
                alt={t('pos.upiQrAlt')}
                src={`data:image/png;base64,${upiPng}`}
                sx={{ width: 200, height: 200, alignSelf: 'center', border: 1, borderColor: 'divider' }}
              />
            ) : null}
            {upiIntent ? (
              <Typography variant="caption" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {upiIntent}
              </Typography>
            ) : (
              <Alert severity="warning">{t('pos.qrUnavailable')}</Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            disabled={busy}
            onClick={() => {
              setMessage(t('pos.leftUnpaid', { number: upiPending?.invoiceNumber ?? '' }));
              setUpiPending(null);
              setIdempotencyKey(null);
              setCart([]);
            }}
          >
            {t('pos.collectLater')}
          </Button>
          <Button variant="contained" disabled={busy} onClick={() => void confirmUpiPayment()}>
            {t('pos.paymentReceived')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

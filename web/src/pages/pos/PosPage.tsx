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
import { isPosEnabled } from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { NumericField, todayIso, useDebouncedValue } from '@/components/billing';
import { LoadingState } from '@/components/PageState';
import { PageShell } from '@/pages/phase/phaseShared';
import {
  enqueueDraft,
  flushOutbox,
  listDrafts,
  removeDraft,
  OUTBOX_PLAINTEXT_WARNING,
  OUTBOX_WARNING_DISMISS_KEY,
  type InvoiceDraftLine,
} from '@/offline/invoiceDraftCache';
import type { Customer, PaymentMode, Product } from '@/types/domain';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { formatMoney, toNumber } from '@/utils/money';
import { printBlob } from '@/utils/blob';
import { isAllowedPaymentUrl } from '@/utils/safeUrl';
import { calculateLineTax, calculateInvoiceTotals, isIntraState } from '@/utils/tax';

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

function draftLinesFromCart(cart: CartLine[]): InvoiceDraftLine[] {
  return cart.map((line) => ({
    productId: line.product.id,
    productName: line.product.name,
    sku: line.product.sku,
    quantity: line.quantity,
    unitPrice: toNumber(line.product.sellingPrice),
    gstRate: toNumber(line.product.gstRate),
    discountPercent: line.discountPercent || 0,
  }));
}

export function PosPage() {
  const { user } = useAuth();
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const searchRef = useRef<HTMLInputElement>(null);

  const [cart, setCart] = useState<CartLine[]>([]);
  const [productQuery, setProductQuery] = useState('');
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
  const customers = useQuery({
    queryKey: ['pos-customers'],
    queryFn: () => listCustomersPage({ pageSize: 100 }),
  });
  const selectedCustomer = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: Boolean(customerId),
  });
  const products = useQuery({
    queryKey: ['pos-product-search', debouncedQuery],
    queryFn: () => searchProducts(debouncedQuery),
    enabled: debouncedQuery.length >= 1,
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
      setMessage('Recovered offline draft — tap Pay to sync when online.');
    });
  }, [companyId, userId]);

  const intraState = useMemo(() => {
    const party = selectedCustomer.data;
    return isIntraState(company.data?.gstin ?? company.data?.state, party?.gstin ?? party?.state, {
      assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty,
    });
  }, [company.data, selectedCustomer.data]);

  const lineTaxes = useMemo(
    () =>
      cart.map((line) =>
        calculateLineTax({
          quantity: line.quantity,
          unitPrice: toNumber(line.product.sellingPrice),
          gstRate: toNumber(line.product.gstRate),
          discountPercent: line.discountPercent || 0,
          intraState,
        }),
      ),
    [cart, intraState],
  );

  const totals = useMemo(
    () =>
      calculateInvoiceTotals(
        lineTaxes.map((tax, i) => ({
          ...tax,
          gstRate: toNumber(cart[i]?.product.gstRate),
          intraState,
        })),
        { applyRoundOff: true },
      ),
    [lineTaxes, cart, intraState],
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
    let matches = (products.data ?? []).filter((p) => p.status === 'ACTIVE');
    if (debouncedQuery !== q || products.isFetching) {
      try {
        matches = (await searchProducts(q)).filter((p) => p.status === 'ACTIVE');
      } catch {
        // use whatever is already loaded
      }
    }
    const exact =
      matches.find((p) => (p.barcode ?? '').toLowerCase() === q.toLowerCase()) ??
      matches.find((p) => p.sku.toLowerCase() === q.toLowerCase()) ??
      (matches.length === 1 ? matches[0] : undefined);
    if (exact) {
      addProduct(exact);
      return;
    }
    setError(`No product found for barcode “${q}”.`);
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
      setMessage(`Sale complete — ${completed.number ?? `#${completed.id}`}`);
    },
    [companyId, userId],
  );

  const createCompletedInvoice = useCallback(
    async (lines: InvoiceDraftLine[], customer: number, key?: string) => {
      const invoiceDate = todayIso();
      const invoice = await createSalesInvoice(
        {
          customer,
          invoiceType: 'RETAIL',
          invoiceDate,
          dueDate: invoiceDate,
          paymentTermsDays: 0,
          autoRoundOff: true,
          items: lines.map((line) => ({
            product: line.productId,
            description: line.productName,
            quantity: line.quantity,
            unitPrice: line.unitPrice,
            gstRate: line.gstRate,
            discountPercent: line.discountPercent ?? 0,
          })),
        },
        { idempotencyKey: key },
      );
      return completeSalesInvoice(invoice.id);
    },
    [],
  );

  const performCashCheckout = useCallback(
    async (lines: InvoiceDraftLine[], customer: number, key?: string) => {
      const taxes = lines.map((line) =>
        calculateLineTax({
          quantity: line.quantity,
          unitPrice: line.unitPrice,
          gstRate: line.gstRate,
          discountPercent: line.discountPercent ?? 0,
          intraState,
        }),
      );
      const saleTotal = calculateInvoiceTotals(
        taxes.map((tax, i) => ({
          ...tax,
          gstRate: lines[i]?.gstRate ?? 0,
          intraState,
        })),
        { applyRoundOff: true },
      ).grandTotal;

      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const completed = await createCompletedInvoice(lines, customer, key);
        const invoiceDate = todayIso();
        const receiptKey = key ? `${key}-receipt` : undefined;
        const receipt = await createReceipt(
          {
            customer,
            amount: saleTotal,
            mode: 'CASH',
            receiptDate: invoiceDate,
            notes: `POS — ${completed.number ?? completed.id}`,
          },
          { idempotencyKey: receiptKey },
        );
        await createAllocation({
          receipt: receipt.id,
          salesInvoice: completed.id,
          amount: saleTotal,
        });
        await finishSale(completed, key);
      } catch (err) {
        setError(getErrorMessage(err));
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [createCompletedInvoice, finishSale, intraState],
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
            `Synced unpaid invoice ${completed.number ?? `#${completed.id}`} — collect UPI from invoice detail.`,
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
      const taxes = lines.map((line) =>
        calculateLineTax({
          quantity: line.quantity,
          unitPrice: line.unitPrice,
          gstRate: line.gstRate,
          discountPercent: line.discountPercent ?? 0,
          intraState,
        }),
      );
      const saleTotal = calculateInvoiceTotals(
        taxes.map((tax, i) => ({
          ...tax,
          gstRate: lines[i]?.gstRate ?? 0,
          intraState,
        })),
        { applyRoundOff: true },
      ).grandTotal;

      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const completed = await createCompletedInvoice(lines, customer, key);
        let upiQr: Record<string, string> | null = null;
        try {
          upiQr = await getUpiQr({ salesInvoice: completed.id });
        } catch (err) {
          setError(`Invoice created but UPI QR failed: ${getErrorMessage(err)}`);
        }
        setUpiPending({
          invoiceId: completed.id,
          invoiceNumber: String(completed.number ?? completed.id),
          customer,
          amount: saleTotal,
          key,
          upiQr,
        });
        setCart([]);
      } catch (err) {
        setError(getErrorMessage(err));
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [createCompletedInvoice, intraState],
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
          `Offline sync failed (${result.failed}): ${result.errors.slice(0, 3).join(' · ')}`,
        );
      } else if (result.flushed > 0) {
        setMessage(`Synced ${result.flushed} offline sale(s).`);
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
      let effectiveCustomerId = customerId;
      if (!effectiveCustomerId) {
        if (walkInCustomer) {
          effectiveCustomerId = walkInCustomer.id;
          setCustomerId(walkInCustomer.id);
        } else {
          try {
            const created = await createCustomer({ name: 'Walk-in Customer', status: 'ACTIVE' });
            effectiveCustomerId = created.id;
            setCustomerId(created.id);
          } catch {
            setError('Select a customer (or Walk-in) before checkout.');
            return;
          }
        }
      }
      if (cart.length === 0) {
        setError('Cart is empty');
        return;
      }
      if (mode === 'CASH' && tenderedAmount + 1e-9 < totals.grandTotal) {
        setError('Amount tendered must be at least the total.');
        return;
      }
      if (mode === 'UPI' && !navigator.onLine) {
        setError('UPI needs a connection to show the payment QR. Use Cash offline, or reconnect.');
        return;
      }

      const lines = draftLinesFromCart(cart);
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
        setMessage('Saved offline — will sync when you are back online.');
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
    ],
  );

  if (!posEnabled()) {
    return (
      <PageShell title="Point of Sale">
        <Typography>Enable with VITE_ENABLE_POS or runtime ENABLE_POS.</Typography>
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
    <PageShell title="Point of Sale" subtitle="Fast counter billing · Press F2 to scan barcode">
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
            {OUTBOX_PLAINTEXT_WARNING}
          </Alert>
        ) : null
      ) : null}
      {offline ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          You are offline. Cash sales will be queued locally and synced when connection returns.
        </Alert>
      ) : null}
      {message ? (
        <Alert severity="success" onClose={() => setMessage(null)} sx={{ mb: 1 }}>
          {message}
        </Alert>
      ) : null}
      {error ? (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 1 }}>
          {error}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Paper variant="outlined" sx={{ flex: 1, p: 2 }}>
          <Stack spacing={2}>
            <TextField
              select
              label="Customer"
              size="small"
              value={customerId === '' ? '' : customerId}
              onChange={(e) => {
                const v = e.target.value;
                setCustomerId(v === '' ? '' : Number(v));
              }}
              fullWidth
            >
              <MenuItem value="">
                <em>Select customer…</em>
              </MenuItem>
              {walkInCustomer ? (
                <MenuItem value={walkInCustomer.id}>Walk-in — {walkInCustomer.name}</MenuItem>
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

            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <Autocomplete<Product>
                sx={{ flex: 1 }}
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
                renderInput={(params) => (
                  <TextField
                    {...params}
                    inputRef={searchRef}
                    size="small"
                    placeholder="Scan barcode or search product"
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
              <IconButton onClick={() => searchRef.current?.focus()} aria-label="Focus scanner">
                <QrCodeScannerIcon />
              </IconButton>
            </Box>

            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Item</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell align="right">Disc %</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Total</TableCell>
                  <TableCell width={48} />
                </TableRow>
              </TableHead>
              <TableBody>
                {cart.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography variant="body2" color="text.secondary">
                        Scan or search to add items.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  cart.map((line) => {
                    const tax = calculateLineTax({
                      quantity: line.quantity,
                      unitPrice: toNumber(line.product.sellingPrice),
                      gstRate: toNumber(line.product.gstRate),
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
                          <IconButton size="small" onClick={() => updateQty(line.key, 0)} aria-label="Remove">
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
            <Typography variant="h6">Tender</Typography>
            <Divider />
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">Subtotal</Typography>
              <Typography>{formatMoney(totals.subtotal)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">Tax</Typography>
              <Typography>{formatMoney(totals.taxTotal)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="h6">Total</Typography>
              <Typography variant="h6">{formatMoney(totals.grandTotal)}</Typography>
            </Stack>
            <NumericField
              label="Cash tendered"
              value={cashTendered === '' ? totals.grandTotal : cashTendered}
              onValueChange={(n) => setCashTendered(n)}
              min={0}
              emptyAs={totals.grandTotal}
              size="small"
              fullWidth
            />
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              <Chip
                label="Exact"
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
              <Typography color="text.secondary">Change</Typography>
              <Typography>{formatMoney(changeDue)}</Typography>
            </Stack>
            <Divider />
            <Button
              variant="contained"
              size="large"
              disabled={busy || cart.length === 0 || Boolean(upiPending)}
              onClick={() => void checkout('CASH')}
            >
              Cash — {formatMoney(totals.grandTotal)}
            </Button>
            <Button
              variant="outlined"
              size="large"
              disabled={busy || cart.length === 0 || Boolean(upiPending)}
              onClick={() => void checkout('UPI')}
            >
              UPI — {formatMoney(totals.grandTotal)}
            </Button>
            <Button
              variant="text"
              color="inherit"
              disabled={busy || (cart.length === 0 && !upiPending)}
              onClick={clearCart}
            >
              Clear cart
            </Button>
          </Stack>
        </Paper>
      </Stack>

      <Dialog open={Boolean(upiPending)} onClose={() => undefined} maxWidth="xs" fullWidth>
        <DialogTitle>UPI payment</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              Invoice {upiPending?.invoiceNumber} — scan to pay{' '}
              {formatMoney(upiPending?.amount ?? 0)}. Confirm only after payment is received.
            </Typography>
            {upiIntent && upiPng ? (
              <Box
                component="img"
                alt="UPI QR"
                src={`data:image/png;base64,${upiPng}`}
                sx={{ width: 200, height: 200, alignSelf: 'center', border: 1, borderColor: 'divider' }}
              />
            ) : null}
            {upiIntent ? (
              <Typography variant="caption" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {upiIntent}
              </Typography>
            ) : (
              <Alert severity="warning">
                QR unavailable — open the invoice and generate UPI QR, or retry after fixing UPI settings.
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            disabled={busy}
            onClick={() => {
              setMessage(
                `Invoice ${upiPending?.invoiceNumber} left unpaid — collect later from invoice detail.`,
              );
              setUpiPending(null);
              setIdempotencyKey(null);
            }}
          >
            Collect later
          </Button>
          <Button variant="contained" disabled={busy} onClick={() => void confirmUpiPayment()}>
            Payment received
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

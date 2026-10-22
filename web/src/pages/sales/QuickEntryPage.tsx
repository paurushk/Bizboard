import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';
import {
  createSalesInvoice,
  createSalesOrder,
  getCompany,
  getCustomer,
  getQuickEntryRecents,
  getStockHints,
  listPriceLists,
  listProductsByIds,
} from '@/api/resources';
import { confirmSalesOrder } from '@/api/osPlan';
import { getErrorCode, getErrorMessage, newIdempotencyKey } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { CreditHoldChip } from '@/components/CreditHoldChip';
import { EmptyState } from '@/components/PageState';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { todayIso } from '@/components/billing/lineHelpers';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';
import { PasteOrderPanel } from '@/components/agents/PasteOrderPanel';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useProductSearch, PRODUCT_SEARCH_MIN_CHARS } from '@/hooks/useProductSearch';
import { PageTitle } from '@/contextHelp';
import { trackShopFloor } from '@/lib/telemetry';
import { t, useLocale } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { inferInvoiceTypeFromParty } from '@/pages/sales/invoiceDefaults';
import { invalidateInvoiceSideEffects, invalidateSalesOrderSideEffects } from '@/pages/sales/invalidateInvoiceSideEffects';
import { QuickLineRow } from '@/pages/sales/quickEntry/QuickLineRow';
import { forgetRecentSkus, loadRecentSkus, saveRecentSku, type RecentSku } from '@/pages/sales/quickEntry/recentSkus';
import type { QuickLine, QuickMode } from '@/pages/sales/quickEntry/types';
import { useQuickEntryDraft, type QuickEntryDraft } from '@/pages/sales/quickEntry/useQuickEntryDraft';
import type { Customer, Product } from '@/types/domain';
import { collectionHoldFor } from '@/pages/sales/quickEntry/customerHold';
import { creditLimitExceeded } from '@/utils/creditExposure';
import { resolveListUnitPrice } from '@/utils/priceList';
import { formatMoney, toNumber } from '@/utils/money';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { canCreateSales } from '@/utils/permissions';
import { formatQuantity } from '@/utils/quantity';

const CUSTOMER_MIN_CHARS = 2;
const MODE_KEY = 'bizboard:quick-entry-mode';
const CLIENT_SOURCE = 'quick_entry';

interface SavedDoc {
  kind: QuickMode;
  id: number;
  ref: string;
  confirmed: boolean;
  needsApproval?: string;
  /** The order saved but confirming it did not complete (network/server) — it is still a draft. */
  confirmUnknown?: boolean;
}

/**
 * True when the server refused on a business or validation rule (400/422), e.g. a credit or margin gate.
 * A lost connection, 5xx, 409 (request in flight), 429 (rate limit) or 401/403 says nothing about the order.
 */
function isRuleRefusal(error: unknown): boolean {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return status === 400 || status === 422;
}

function readMode(companyId: number): QuickMode {
  try {
    return localStorage.getItem(`${MODE_KEY}:${companyId}`) === 'bill' ? 'bill' : 'order';
  } catch {
    return 'order';
  }
}

function lineFromProduct(product: Product): QuickLine {
  return {
    key: `${product.id}-${Date.now()}`,
    productId: product.id,
    name: product.name,
    sku: product.sku ?? '',
    unitName: product.unitName ?? '',
    uqc: product.unitUqc ?? '',
    quantity: 1,
    unitPrice: toNumber(product.sellingPrice),
    gstRate: toNumber(product.gstRate ?? 0),
    priceListName: '',
    availableQty: null,
    trackInventory: product.trackInventory !== false,
  };
}

/**
 * QOS-0048 / Quick Order Entry. A keyboard-light booking sheet for a field rep: the rep's recent
 * customers and products as one-tap chips, a typeable quantity with +/- steppers, and Save & next.
 *
 * Prices, GST and cess are NOT sent: the server resolves them (customer price list, slab, live product
 * rates), so a stale device value can never override a contracted price (QOE-00). With the price
 * preview flag on, the screen shows exactly what the server will save (QOE-01).
 */
export function QuickEntryPage() {
  useLocale();
  useFeatureFlagEpoch();
  const { user } = useAuth();
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();

  const orderFlag = isRuntimeFlagEnabled('QUICK_ENTRY_ORDER_MODE');
  const autoConfirmFlag = isRuntimeFlagEnabled('QUICK_ENTRY_AUTO_CONFIRM');
  const previewFlag = isRuntimeFlagEnabled('QUICK_ENTRY_PRICE_PREVIEW');

  const [pickedCustomer, setPickedCustomer] = useState<Customer | null>(null);
  const [prefillDismissed, setPrefillDismissed] = useState(false);
  const [lines, setLines] = useState<QuickLine[]>([]);
  const [recentSkus, setRecentSkus] = useState<RecentSku[]>(() => loadRecentSkus(companyId));
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [preferredMode, setPreferredMode] = useState<QuickMode>(() => readMode(companyId));
  const [note, setNote] = useState('');
  const [shipToId, setShipToId] = useState<number | ''>('');
  const [lastSaved, setLastSaved] = useState<SavedDoc | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [navTarget, setNavTarget] = useState<string | null>(null);
  const [removed, setRemoved] = useState<{ line: QuickLine; index: number } | null>(null);

  // ?customer=<id> pre-selects an active customer until the rep clears or replaces it.
  const prefillCustomerId = Number(searchParams.get('customer')) || 0;
  const prefillCustomer = useQuery({
    queryKey: ['customer', prefillCustomerId],
    queryFn: () => getCustomer(prefillCustomerId),
    enabled: prefillCustomerId > 0 && !pickedCustomer && !prefillDismissed,
    retry: false,
  });
  const customer: Customer | null =
    pickedCustomer ??
    (!prefillDismissed && prefillCustomer.data && prefillCustomer.data.status === 'ACTIVE' ? prefillCustomer.data : null);
  const setCustomer = (next: Customer | null) => {
    setPickedCustomer(next);
    // A delivery address belongs to one customer; never carry it over to another.
    setShipToId('');
    if (!next) setPrefillDismissed(true);
  };

  const customerSearch = useCustomerSearch({ selected: customer, activeOnly: true });
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct });

  const company = useQuery({ queryKey: ['company', companyId], queryFn: getCompany, staleTime: 5 * 60_000 });
  const customerDetail = useQuery({
    queryKey: ['customer', customer?.id],
    queryFn: () => getCustomer(customer!.id),
    enabled: Boolean(customer?.id),
  });
  const fullCustomer: Customer | null = customerDetail.data ?? customer;

  // ---- mode: Order is gated by the rollout flag (orders carry their own price mode, like bills) ----
  const orderAllowed = orderFlag;
  const mode: QuickMode = orderAllowed ? preferredMode : 'bill';
  const chooseMode = (next: QuickMode) => {
    setPreferredMode(next);
    try {
      localStorage.setItem(`${MODE_KEY}:${companyId}`, next);
    } catch {
      /* best effort */
    }
  };

  // A customer picked from a recent chip is only {id, name} until the full record arrives. The invoice type
  // depends on the customer's GSTIN for a regular company, so wait for it rather than guess RETAIL.
  const customerKnown = !customer || customerDetail.isSuccess || customerDetail.isError;
  const typeKnown =
    Boolean(company.data) && (company.data?.registrationType !== 'REGULAR' || customerKnown);
  const invoiceType = typeKnown
    ? inferInvoiceTypeFromParty({
        registrationType: company.data!.registrationType,
        customerGstin: fullCustomer?.gstin,
      })
    : undefined;
  const priceMode = company.data?.priceMode === 'INCLUSIVE' ? 'INCLUSIVE' : 'EXCLUSIVE';

  // ---- recents: the rep's own customers/products, active only ----
  const recents = useQuery({
    queryKey: ['quick-entry-recent', companyId, userId],
    queryFn: getQuickEntryRecents,
  });
  const recentCustomers = (recents.data?.customers ?? []).slice(0, 6);

  const recentIds = useMemo(() => {
    const ids: number[] = [];
    for (const id of [...recentSkus.map((p) => p.id), ...(recents.data?.products ?? []).map((p) => p.id)]) {
      if (!ids.includes(id)) ids.push(id);
    }
    return ids.slice(0, 8);
  }, [recentSkus, recents.data?.products]);

  const recentProductsQuery = useQuery({
    queryKey: ['products', 'recent', companyId, recentIds.join(',')],
    queryFn: async () => {
      const rows = await listProductsByIds(recentIds);
      // Forget products that are gone or inactive so a rejected item never lingers on the device.
      const live = new Set(rows.filter((p) => p.status === 'ACTIVE').map((p) => p.id));
      const dead = recentIds.filter((id) => !live.has(id));
      if (dead.length > 0) forgetRecentSkus(companyId, dead);
      return rows;
    },
    enabled: recentIds.length > 0,
  });
  const recentProducts = useMemo(() => {
    const byId = new Map((recentProductsQuery.data ?? []).filter((p) => p.status === 'ACTIVE').map((p) => [p.id, p]));
    return recentIds.map((id) => byId.get(id)).filter((p): p is Product => Boolean(p));
  }, [recentProductsQuery.data, recentIds]);

  // ---- company switch: component state survives a cache clear, so reset it explicitly ----
  const seenCompany = useRef(companyId);
  useEffect(() => {
    if (seenCompany.current === companyId) return;
    seenCompany.current = companyId;
    setCustomer(null);
    setLines([]);
    setPendingProduct(null);
    setSaveError(null);
    setNote('');
    setShipToId('');
    setLastSaved(null);
    setRecentSkus(loadRecentSkus(companyId));
    setPreferredMode(readMode(companyId));
  }, [companyId]);

  // ---- lines ----
  const addLine = useCallback(
    (product: Product) => {
      setRecentSkus(saveRecentSku(companyId, product));
      setLines((current) => {
        const existing = current.find((l) => l.productId === product.id);
        if (existing) {
          return current.map((l) => (l.productId === product.id ? { ...l, quantity: l.quantity + 1 } : l));
        }
        return [...current, lineFromProduct(product)];
      });
      setPendingProduct(null);
      productSearch.setProductQuery('');
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [companyId],
  );

  const setQuantity = (key: string, quantity: number) =>
    setLines((current) => current.map((l) => (l.key === key ? { ...l, quantity } : l)));

  const removeLine = (key: string) => {
    const index = lines.findIndex((l) => l.key === key);
    if (index < 0) return;
    setRemoved({ line: lines[index], index });
    setLines((current) => current.filter((l) => l.key !== key));
  };

  const undoRemove = () => {
    if (!removed) return;
    setLines((current) => {
      if (current.some((l) => l.productId === removed.line.productId)) return current;
      const next = [...current];
      next.splice(Math.min(removed.index, next.length), 0, removed.line);
      return next;
    });
    setRemoved(null);
  };

  // ---- prefill from Customer 360 / stock pages: ?customer=<id>&product=<id> ----
  const prefillProductId = Number(searchParams.get('product')) || 0;
  const prefillProductDone = useRef(false);
  const prefillProduct = useQuery({
    queryKey: ['products', 'prefill', prefillProductId],
    queryFn: () => listProductsByIds([prefillProductId]),
    enabled: prefillProductId > 0,
    retry: false,
  });
  useEffect(() => {
    const found = prefillProduct.data?.[0];
    if (!found || prefillProductDone.current || found.status !== 'ACTIVE') return;
    prefillProductDone.current = true;
    addLine(found);
  }, [prefillProduct.data, addLine]);

  // ---- stock hints (tracked products only) ----
  const hintIds = Array.from(new Set([...lines.map((l) => l.productId), ...recentIds])).sort((a, b) => a - b);
  const stockHints = useQuery({
    queryKey: ['quick-entry-stock', hintIds.join(',')],
    queryFn: () => getStockHints(hintIds),
    enabled: hintIds.length > 0,
  });
  // A short line is only a hard stop when the company blocks negative stock.
  const stockBlocks = company.data?.negativeStockPolicy !== 'WARN';

  // Price-list fallback when the server preview is off: show the customer's list/slab price.
  const needsListFallback = !previewFlag && Boolean(customer) && Boolean(fullCustomer?.priceList) && lines.length > 0;
  const priceLists = useQuery({
    queryKey: ['price-lists', companyId],
    queryFn: listPriceLists,
    enabled: needsListFallback,
    staleTime: 5 * 60_000,
  });

  // ---- server price + tax preview (QOE-01) ----
  const previewBody = useMemo(() => {
    if (!previewFlag || !customer || lines.length === 0) return null;
    return {
      customer: customer.id,
      ...(invoiceType ? { invoice_type: invoiceType } : {}),
      price_mode: priceMode,
      auto_round_off: true,
      items: lines.map((l) => ({ product: l.productId, quantity: l.quantity })),
    };
  }, [previewFlag, customer, lines, invoiceType, priceMode]);
  const preview = usePreviewTotals('sales', previewBody);

  const viewLines: QuickLine[] = useMemo(
    () =>
      lines.map((l, i) => {
        const row = preview.ready ? preview.totals?.items?.[i] : undefined;
        const hint = stockHints.data?.[String(l.productId)];
        const listed = !row
          ? resolveListUnitPrice(priceLists.data, fullCustomer?.priceList, l.productId, l.quantity)
          : null;
        return {
          ...l,
          unitPrice:
            row && row.product === l.productId && row.unitPrice != null
              ? row.unitPrice
              : listed
                ? listed.unitPrice
                : l.unitPrice,
          gstRate: row && row.product === l.productId && row.gstRate != null ? row.gstRate : l.gstRate,
          priceListName: row?.appliedPriceListName ?? listed?.listName ?? '',
          unitName: row?.unitName || l.unitName,
          uqc: row?.uqcCode || l.uqc,
          availableQty: hint != null ? Number(hint) : null,
        };
      }),
    [lines, preview.ready, preview.totals, stockHints.data, priceLists.data, fullCustomer?.priceList],
  );

  const subtotal = viewLines.reduce((sum, l) => sum + l.quantity * l.unitPrice, 0);
  const serverTotals = preview.ready ? preview.totals : null;
  // Without the server preview, estimate GST from each line's rate so the total is not misleadingly pre-tax.
  const taxable = invoiceType !== 'NON_GST';
  const estimatedTax = taxable
    ? viewLines.reduce((sum, l) => {
        const gross = l.quantity * l.unitPrice;
        const rate = l.gstRate / 100;
        return sum + (priceMode === 'INCLUSIVE' ? gross - gross / (1 + rate) : gross * rate);
      }, 0)
    : 0;
  const estimatedTotal = priceMode === 'INCLUSIVE' ? subtotal : subtotal + estimatedTax;
  const grandTotal = serverTotals ? serverTotals.grandTotal : estimatedTotal;

  // ---- credit context (advisory; the server gates at confirm) ----
  const creditLimit = toNumber(fullCustomer?.creditLimit);
  const onHold = collectionHoldFor(fullCustomer);
  const overLimit =
    Boolean(fullCustomer) &&
    creditLimitExceeded({ limit: creditLimit, outstanding: toNumber(fullCustomer?.creditExposure), draftTotal: grandTotal });
  const shippingAddresses = fullCustomer?.shippingAddresses ?? [];

  // ---- draft persistence (QOE-14) ----
  const draftState: QuickEntryDraft | null = useMemo(
    () =>
      lines.length > 0
        ? {
            customerId: customer?.id ?? null,
            customerName: customer?.name ?? '',
            mode: preferredMode,
            note,
            shipToId: shipToId === '' ? null : shipToId,
            lines: lines.map((l) => ({ productId: l.productId, quantity: l.quantity })),
          }
        : null,
    [lines, customer, preferredMode, note, shipToId],
  );
  const draft = useQuickEntryDraft(companyId, userId, draftState);

  const resumeDraft = async () => {
    const saved = draft.resumable;
    if (!saved) return;
    try {
      const [products, restoredCustomer] = await Promise.all([
        listProductsByIds(saved.lines.map((l) => l.productId)),
        saved.customerId ? getCustomer(saved.customerId).catch(() => null) : Promise.resolve(null),
      ]);
      const restored = saved.lines
        .map((l) => {
          const product = products.find((p) => p.id === l.productId && p.status === 'ACTIVE');
          return product ? { ...lineFromProduct(product), quantity: l.quantity } : null;
        })
        .filter((l): l is QuickLine => l !== null);
      setLines(restored);
      if (restoredCustomer && restoredCustomer.status === 'ACTIVE') setCustomer(restoredCustomer);
      setNote(saved.note ?? '');
      if (saved.shipToId) setShipToId(saved.shipToId);
      if (saved.mode) setPreferredMode(saved.mode);
      trackShopFloor('draft_restored', { feature: 'quick_entry' });
      draft.clear();
    } catch (e) {
      // Keep the saved draft so the rep can try again; say why nothing came back.
      setSaveError(e);
    }
  };

  // ---- save: one idempotency key per attempt, reused on retry until the order changes (QOE-05) ----
  const attemptRef = useRef<{ sig: string; key: string } | null>(null);
  const inFlightRef = useRef(false);

  const signature = JSON.stringify({
    c: customer?.id,
    m: mode,
    n: note,
    s: shipToId,
    t: invoiceType,
    p: priceMode,
    l: lines.map((l) => [l.productId, l.quantity]),
  });
  const attemptKey = () => {
    if (!attemptRef.current || attemptRef.current.sig !== signature) {
      attemptRef.current = { sig: signature, key: newIdempotencyKey() };
    }
    return attemptRef.current.key;
  };

  const save = useMutation({
    mutationFn: async (_after: 'next' | 'open'): Promise<SavedDoc> => {
      const key = attemptKey();
      const items = lines.map((l) => ({ product: l.productId, quantity: l.quantity }));
      const options = { idempotencyKey: key, clientSource: CLIENT_SOURCE };
      if (mode === 'order') {
        const order = await createSalesOrder(
          {
            customer: customer!.id,
            ...(invoiceType ? { invoiceType } : {}),
            priceMode,
            orderDate: todayIso(),
            ...(note.trim() ? { notes: note.trim() } : {}),
            ...(shipToId ? { shipTo: Number(shipToId) } : {}),
            items,
          },
          options,
        );
        let confirmed = false;
        let needsApproval: string | undefined;
        let confirmUnknown = false;
        if (autoConfirmFlag) {
          try {
            await confirmSalesOrder(order.id, undefined, { idempotencyKey: `${key}-confirm` });
            confirmed = true;
          } catch (e) {
            if (getErrorCode(e) === 'order_already_confirmed') confirmed = true;
            // Only a rule the server enforced means "needs approval"; anything else (dropped connection,
            // 5xx, 409, 429, 403) is unknown, so tell the rep to check the order instead of blaming a rule.
            else if (isRuleRefusal(e)) needsApproval = getErrorMessage(e);
            else confirmUnknown = true;
          }
        }
        return { kind: 'order', id: order.id, ref: order.number || `#${order.id}`, confirmed, needsApproval, confirmUnknown };
      }
      const invoice = await createSalesInvoice(
        {
          customer: customer!.id,
          ...(invoiceType ? { invoiceType } : {}),
          priceMode,
          ...(note.trim() ? { notes: note.trim() } : {}),
          items,
        },
        options,
      );
      return { kind: 'bill', id: invoice.id, ref: invoice.number || `#${invoice.id}`, confirmed: false };
    },
    onSuccess: (doc, after) => {
      setSaveError(null);
      attemptRef.current = null;
      draft.clear();
      void qc.invalidateQueries({ queryKey: ['quick-entry-recent', companyId, userId] });
      if (doc.kind === 'order') invalidateSalesOrderSideEffects(qc, doc.id, customer?.id);
      else invalidateInvoiceSideEffects(qc, doc.id);
      const path = doc.kind === 'order' ? `/sales/orders/${doc.id}` : `/sales/history/${doc.id}`;
      if (after === 'open') {
        setLeaving(true);
        setNavTarget(path);
        return;
      }
      setLastSaved(doc);
      setLines([]);
      setCustomer(null);
      setNote('');
      setShipToId('');
    },
    onError: (e) => {
      setSaveError(e);
      trackShopFloor('form_validation_failed', {
        feature: 'quick_entry',
        failureReason: getErrorCode(e) ? 'help_code' : 'unknown',
      });
    },
    onSettled: () => {
      inFlightRef.current = false;
    },
  });

  // Navigate only after `leaving` has committed so the leave guard no longer blocks.
  useEffect(() => {
    if (leaving && navTarget) navigate(navTarget);
  }, [leaving, navTarget, navigate]);

  const submit = (after: 'next' | 'open') => {
    if (inFlightRef.current || !customer || lines.length === 0) return;
    inFlightRef.current = true;
    setLastSaved(null);
    save.mutate(after);
  };

  if (!canCreateSales(user)) return <ForbiddenPage />;

  const labels =
    mode === 'order'
      ? { next: t('quickEntry.saveAndNext'), open: t('quickEntry.saveAndOpen') }
      : { next: t('quickEntry.saveBillAndNext'), open: t('quickEntry.saveBillAndOpen') };
  const canSave = Boolean(customer) && lines.length > 0 && !save.isPending && customerKnown;
  const gstinMissing =
    company.data?.registrationType === 'REGULAR' &&
    !(company.data as { gstin?: string }).gstin &&
    invoiceType !== 'NON_GST' &&
    mode === 'bill';

  return (
    <Stack spacing={2} sx={{ maxWidth: 480, mx: 'auto', pb: 8 }}>
      <UnsavedChangesGuard when={lines.length > 0 && !leaving} interceptLinks />
      <PageTitle variant="h5">{t('quickEntry.pageTitle')}</PageTitle>

      {draft.resumable ? (
        <Alert
          severity="info"
          action={
            <Stack direction="row" spacing={0.5}>
              <Button color="inherit" size="small" onClick={() => void resumeDraft()}>
                {t('quickEntry.resume')}
              </Button>
              <Button color="inherit" size="small" onClick={draft.clear}>
                {t('quickEntry.discard')}
              </Button>
            </Stack>
          }
        >
          {draft.resumable.customerName
            ? t('quickEntry.resumeTitle', { name: draft.resumable.customerName })
            : t('quickEntry.resumeNoCustomer')}
        </Alert>
      ) : null}

      {lastSaved ? (
        <Alert
          severity={lastSaved.needsApproval || lastSaved.confirmUnknown ? 'warning' : 'success'}
          onClose={() => setLastSaved(null)}
          action={
            <Button
              color="inherit"
              size="small"
              component={RouterLink}
              to={lastSaved.kind === 'order' ? `/sales/orders/${lastSaved.id}` : `/sales/history/${lastSaved.id}`}
            >
              {t('quickEntry.viewDocument')}
            </Button>
          }
        >
          {lastSaved.kind === 'bill'
            ? t('quickEntry.savedBill', { ref: lastSaved.ref })
            : lastSaved.needsApproval
              ? t('quickEntry.savedOrderNeedsApproval', { ref: lastSaved.ref, reason: lastSaved.needsApproval })
              : lastSaved.confirmUnknown
                ? t('quickEntry.savedOrderConfirmUnknown', { ref: lastSaved.ref })
                : lastSaved.confirmed
                ? t('quickEntry.savedOrderConfirmed', { ref: lastSaved.ref })
                : t('quickEntry.savedOrder', { ref: lastSaved.ref })}
        </Alert>
      ) : null}

      {saveError ? <HelpErrorAlert error={saveError} /> : null}
      {recents.isError ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => void recents.refetch()}>
              {t('quickEntry.retry')}
            </Button>
          }
        >
          {t('quickEntry.recentsError')}
        </Alert>
      ) : null}

      {orderAllowed ? (
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography variant="body2" color="text.secondary">
            {t('quickEntry.mode')}
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={mode}
            onChange={(_, next: QuickMode | null) => next && chooseMode(next)}
            aria-label={t('quickEntry.mode')}
          >
            <ToggleButton value="order" sx={{ minHeight: 44 }}>
              {t('quickEntry.modeOrder')}
            </ToggleButton>
            <ToggleButton value="bill" sx={{ minHeight: 44 }}>
              {t('quickEntry.modeBill')}
            </ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      ) : null}

      {mode === 'order' ? <PasteOrderPanel /> : null}

      <Paper sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" component="p" color="text.secondary" gutterBottom>
          {t('quickEntry.customer')}
        </Typography>
        {customer ? (
          <>
            <Chip label={customer.name} onDelete={() => setCustomer(null)} color="primary" sx={{ mb: 1 }} />
            {onHold ? <CreditHoldChip /> : null}
            {onHold ? (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {t('quickEntry.creditHold')}
              </Alert>
            ) : overLimit ? (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {t('quickEntry.creditExceeded')}
              </Alert>
            ) : null}
          </>
        ) : (
          <>
            {recentCustomers.length > 0 ? (
              <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mb: 1 }}>
                {recentCustomers.map((c) => (
                  <Chip
                    key={c.id}
                    label={c.name}
                    onClick={() => setCustomer({ id: c.id, name: c.name } as Customer)}
                    variant="outlined"
                  />
                ))}
              </Stack>
            ) : null}
            <Autocomplete<Customer>
              options={customerSearch.options}
              loading={customerSearch.isFetching}
              filterOptions={(opts) => opts}
              inputValue={customerSearch.query}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear' || reason === 'reset') customerSearch.setQuery(v);
              }}
              onChange={(_, value) => setCustomer(value)}
              getOptionLabel={(c) => c.name}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              renderInput={(params) => (
                <TextField
                  {...params}
                  size="small"
                  label={t('quickEntry.searchCustomer')}
                  helperText={
                    customerSearch.query.trim().length > 0 && customerSearch.query.trim().length < CUSTOMER_MIN_CHARS
                      ? t('quickEntry.typeMore', { n: CUSTOMER_MIN_CHARS })
                      : undefined
                  }
                />
              )}
            />
          </>
        )}
      </Paper>

      <Paper sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" component="p" color="text.secondary" gutterBottom>
          {t('quickEntry.addItem')}
        </Typography>
        {recentProducts.length > 0 ? (
          <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mb: 1 }}>
            {recentProducts.map((p) => {
              const inOrder = lines.find((l) => l.productId === p.id);
              const avail = stockHints.data?.[String(p.id)];
              return (
                <Chip
                  key={p.id}
                  label={`${p.name}${p.sku ? ` · ${p.sku}` : ''}${avail != null ? ` · ${t('quickEntry.avail', { n: formatQuantity(Number(avail)) })}` : ''}${inOrder ? ` ${t('quickEntry.inOrder', { n: formatQuantity(inOrder.quantity) })}` : ''}`}
                  onClick={() => addLine(p)}
                  variant={inOrder ? 'filled' : 'outlined'}
                  color={inOrder ? 'primary' : 'default'}
                />
              );
            })}
          </Stack>
        ) : null}
        <Autocomplete<Product>
          options={productSearch.options}
          loading={productSearch.isFetching}
          filterOptions={(opts) => opts}
          inputValue={productSearch.productQuery}
          onInputChange={(_, v, reason) => {
            if (reason === 'input' || reason === 'clear' || reason === 'reset') productSearch.setProductQuery(v);
          }}
          value={pendingProduct}
          onChange={(_, value) => value && addLine(value)}
          getOptionLabel={(p) => formatProductOptionLabel(p)}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField
              {...params}
              size="small"
              label={t('quickEntry.searchProduct')}
              helperText={
                productSearch.helperText ??
                (productSearch.productQuery.trim().length > 0 &&
                productSearch.productQuery.trim().length < PRODUCT_SEARCH_MIN_CHARS
                  ? t('quickEntry.typeMore', { n: PRODUCT_SEARCH_MIN_CHARS })
                  : undefined)
              }
            />
          )}
        />
      </Paper>

      {lines.length === 0 ? (
        <EmptyState description={t('quickEntry.empty')} />
      ) : (
        <Stack spacing={1}>
          {viewLines.map((line) => (
            <QuickLineRow
              key={line.key}
              line={line}
              stockBlocks={stockBlocks}
              onQuantity={setQuantity}
              onRemove={removeLine}
            />
          ))}
        </Stack>
      )}

      {lines.length > 0 ? (
        <Paper sx={{ p: 1.5, position: 'sticky', bottom: 8 }} elevation={4}>
          {mode === 'order' && shippingAddresses.length > 1 ? (
            <TextField
              select
              fullWidth
              size="small"
              label={t('quickEntry.shipTo')}
              value={shipToId}
              onChange={(e) => setShipToId(e.target.value === '' ? '' : Number(e.target.value))}
              sx={{ mb: 1 }}
            >
              <MenuItem value="">—</MenuItem>
              {shippingAddresses.map((a) => (
                <MenuItem key={a.id ?? a.address} value={a.id ?? ''}>
                  {(a.label ? `${a.label}: ` : '') + a.address}
                </MenuItem>
              ))}
            </TextField>
          ) : null}
          <TextField
            fullWidth
            size="small"
            label={t('quickEntry.note')}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            inputProps={{ maxLength: 500 }}
            sx={{ mb: 1 }}
          />
          {serverTotals ? (
            <Stack spacing={0.25} sx={{ mb: 1 }}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="body2">{t('quickEntry.subtotal')}</Typography>
                <Typography variant="body2">{formatMoney(serverTotals.taxableTotal || serverTotals.subtotal)}</Typography>
              </Stack>
              {serverTotals.taxTotal ? (
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="body2">{t('quickEntry.tax')}</Typography>
                  <Typography variant="body2">{formatMoney(serverTotals.taxTotal)}</Typography>
                </Stack>
              ) : null}
              {serverTotals.roundOff ? (
                <Stack direction="row" justifyContent="space-between">
                  <Typography variant="body2">{t('quickEntry.roundOff')}</Typography>
                  <Typography variant="body2">{formatMoney(serverTotals.roundOff)}</Typography>
                </Stack>
              ) : null}
            </Stack>
          ) : null}
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
            <Typography variant="subtitle1" component="p">{t('common.total')}</Typography>
            <Typography variant="h6" component="p">{formatMoney(grandTotal)}</Typography>
          </Stack>
          {!serverTotals ? (
            <>
              {estimatedTax > 0 ? (
                <Typography variant="body2" color="text.secondary" component="div">
                  {t('quickEntry.estimatedTax', { amount: formatMoney(estimatedTax) })}
                </Typography>
              ) : null}
              <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
                {preview.pending ? t('quickEntry.pricing') : t('quickEntry.priceNote')}
              </Typography>
            </>
          ) : null}
          {gstinMissing ? (
            <Alert severity="warning" sx={{ mb: 1 }}>
              {t('quickEntry.gstinMissing')}
            </Alert>
          ) : null}
          {!customer ? (
            <Alert severity="info" sx={{ mb: 1 }}>
              {t('quickEntry.pickCustomerFirst')}
            </Alert>
          ) : null}
          <Stack spacing={1}>
            <Button fullWidth variant="contained" size="large" disabled={!canSave} onClick={() => submit('next')}>
              {labels.next}
            </Button>
            <Button fullWidth variant="outlined" disabled={!canSave} onClick={() => submit('open')}>
              {labels.open}
            </Button>
          </Stack>
        </Paper>
      ) : null}

      <Snackbar
        open={Boolean(removed)}
        autoHideDuration={5000}
        onClose={() => setRemoved(null)}
        message={removed ? t('quickEntry.removed', { name: removed.line.name }) : ''}
        action={
          <Button color="inherit" size="small" onClick={undoRemove}>
            {t('quickEntry.undo')}
          </Button>
        }
      />
    </Stack>
  );
}

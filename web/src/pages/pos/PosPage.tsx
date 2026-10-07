/**
 * Wave 18D — POS MVP counter mode (BB-000181).
 * Not a full retail suite; uses standard sales invoice + receipt APIs.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type HTMLAttributes } from 'react';
import Alert from '@mui/material/Alert';
import Collapse from '@mui/material/Collapse';
import AlertTitle from '@mui/material/AlertTitle';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Tooltip from '@mui/material/Tooltip';
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
import TableContainer from '@mui/material/TableContainer';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import RemoveIcon from '@mui/icons-material/Remove';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { HonestyBanner } from '@/components/HonestyBanner';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { legacyPosCartKey, readDraft, removeDraft as removeDeviceDraft, writeDraft } from '@/lib/deviceDraft';
import { buildAtomicPosInvoicePayload } from '@/pages/pos/posCheckoutPayload';
import { choosePosEnter } from '@/pages/pos/posEnter';
import { isScannerBurst, parseQtyBarcode } from '@/pages/pos/scanInput';
import { playScanTone } from '@/pages/pos/scanSounds';
import { omitQueuedHeldSessions, repriceLines } from '@/pages/pos/posRestore';
import {
  clearCashPendingStorage,
  clearUpiPendingStorage,
  isSerialOrBatchRuleError,
  persistCashPending,
  persistUpiPending,
  posCashSettlementPhase,
  posChipState,
  resolveSaleGestureKey,
  restoreCashPending,
  restoreUpiPending,
  serialsMatchAddQty,
  unpaidRecoverFromAbort,
  type PosCashPendingSnapshot,
  type PosUpiPendingSnapshot,
} from '@/pages/pos/posStatus';
import { printPosThermalOrWarn } from '@/pages/pos/printPosThermal';
import { PosTillStrip } from '@/pages/pos/PosTillStrip';
import { cashNeedsOpenShift, clearPosOutage, posOutageId, posTerminalId, posTerminalLabel } from '@/pages/pos/posTerminal';
import { useTill } from '@/pages/pos/useTill';
import { collectPosPayment, createPosHold, getPosSettings, listPosHolds, postPosEvent, releasePosHold, returnPosBill } from '@/pages/pos/posCounterApi';
import { DRAWER_KICK, isNative, printEscPos, readScaleWeight } from '@/lib/native';
import {
  createCustomer,
  getCompany,
  getCustomer,
  getProduct,
  getSalesInvoice,
  getUpiQr,
  listBatches,
  listCustomersPage,
  listPriceLists,
  listProductsPage,
  listSalesInvoicesPage,
  listStock,
  listWarehouses,
  posCheckout,
  searchProducts,
  shareInvoice,
  uploadFile,
} from '@/api/resources';
import {
  getErrorCode,
  getErrorDetails,
  getErrorMessage,
  userGestureIdempotencyKey,
} from '@/api/client';
import { trackShopFloor, trackInvoiceComplete, trackJourneyStarted, trackJourneyFailed, classifyCompleteFailure } from '@/lib/telemetry';
import { onNetworkOnline, scanBarcode } from '@/lib/native';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { isPosEnabled } from '@/config/features';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { NumericField, parseSerialNumbersText, todayIso, useDebouncedValue } from '@/components/billing';
import { availablePosBatches, expiryForChosenBatch } from '@/pages/pos/posBatchExpiry';
import {
  availableInWarehouse,
  discountModeForCustomer,
  lineSkipsStockGate,
  offlineTenderAllowed,
  offlineCreditBlock,
  samePosLine,
} from '@/pages/pos/posRules';
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
  isFlushableDraft,
  listDrafts,
  removeDraft,
  OUTBOX_WARNING_DISMISS_KEY,
  type InvoiceDraftLine,
} from '@/offline/invoiceDraftCache';
import { flushPosBatch, flushPosDraft } from '@/offline/flushPosCheckout';
import { catalogAgeHours, catalogSellBlocked, findLocalCatalog, priceListMissing, syncPosCatalog, syncPosPriceLists } from '@/offline/posCatalog';
import type { PaymentMode, Product } from '@/types/domain';
import { formatProductOptionLabel } from '@/utils/formatProductOptionLabel';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import { posPayDisabledReason } from '@/completeGates/completeBlockers';
import { isAllowedPaymentUrl, openShareUrl } from '@/utils/safeUrl';
import { formatMoney, roundMoney, toNumber } from '@/utils/money';
import { formatUnitLabel } from '@/constants/unitLabels';
import { resolveListUnitPrice } from '@/utils/priceList';
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
  unitName: string;
  serialNumbers?: string[];
  batchNo?: string;
  /** Outbox snapshot already stored the alt-unit price; do not convert again. */
  priceAlreadyConverted?: boolean;
  priceOverride?: number;
  /** Shown when an offline sync of this line failed. */
  syncError?: string;
}

const EMPTY_CHEQUE: ChequePaymentValues = { chequeNumber: '', chequeBankName: '', chequeDate: '' };

function posLineUnitPrice(
  product: Product,
  qty: number,
  unitName: string,
  unitPriceFor: (productId: number, qty: number, sellingPrice?: string | number) => number,
  priceAlreadyConverted = false,
): number {
  const base = unitPriceFor(product.id, qty, product.sellingPrice);
  if (priceAlreadyConverted) return base;
  const alt = product.alternateUnitName;
  const rate = toNumber(product.conversionRate) || 1;
  if (alt && unitName === alt && rate > 0) return roundMoney(base * rate);
  return base;
}

type UpiPending = PosUpiPendingSnapshot;

type CashPending = PosCashPendingSnapshot;

type PosBillSession = {
  id: string;
  cart: CartLine[];
  customerId: number | '';
  warehouseId: number | '';
  cashTendered: number | '';
  idempotencyKey: string | null;
  upiPending: UpiPending | null;
  cashPending: CashPending | null;
  walkInName: string;
  serverTenderTotal: number | null;
  cheque: ChequePaymentValues;
  invoiceDiscount: number;
  additionalCharges: number;
};

function posEnabled(): boolean {
  return isPosEnabled() || isRuntimeFlagEnabled('ENABLE_POS');
}

function draftLinesFromCart(
  cart: CartLine[],
  taxEnabled: boolean,
  unitPriceFor: (productId: number, qty: number) => number,
): InvoiceDraftLine[] {
  return cart.map((line) => ({
    productId: line.product.id,
    productName: line.product.name,
    sku: line.product.sku,
    quantity: line.quantity,
    unitPrice: line.priceOverride ?? posLineUnitPrice(
      line.product,
      line.quantity,
      line.unitName,
      unitPriceFor,
      line.priceAlreadyConverted,
    ),
    gstRate: taxEnabled ? toNumber(line.product.gstRate) : 0,
    cessRate: taxEnabled ? toNumber((line.product as { cessRate?: number }).cessRate) : 0,
    discountPercent: line.discountPercent || 0,
    unitName: line.unitName,
    serials: line.serialNumbers,
    batchNo: line.batchNo,
  }));
}

async function fetchPosPreviewGrandTotal(args: {
  customerId?: number | '';
  invoiceType: string;
  priceModeInclusive: boolean;
  taxEnabled: boolean;
  cart: CartLine[];
  unitPriceFor: (productId: number, qty: number) => number;
  invoiceDiscount?: number;
  additionalCharges?: number;
}): Promise<number> {
  const { previewSalesTotals } = await import('@/api/legacy/sales');
  const previewLines = draftLinesFromCart(args.cart, args.taxEnabled, args.unitPriceFor);
  const preview = await previewSalesTotals({
    ...(args.customerId ? { customer: Number(args.customerId) } : {}),
    invoice_type: args.invoiceType,
    price_mode: args.priceModeInclusive ? 'INCLUSIVE' : 'EXCLUSIVE',
    items: previewLines.map((l) => ({
      product: l.productId,
      quantity: l.quantity,
      unit_price: l.unitPrice,
      ...(args.priceModeInclusive ? { unit_price_inclusive: l.unitPrice } : {}),
      gst_rate: l.gstRate,
      cess_rate: l.cessRate,
      discount_percent: l.discountPercent,
      unit_name: l.unitName,
    })),
    auto_round_off: true,
    invoice_discount: args.invoiceDiscount ?? 0,
    additional_charges: args.additionalCharges ?? 0,
  });
  if (typeof preview.grandTotal !== 'number' || !Number.isFinite(preview.grandTotal)) {
    throw new Error('Invalid preview total');
  }
  return preview.grandTotal;
}

function HotkeyBadge({ text }: { text: string }) {
  return (
    <Box
      component="span"
      sx={{
        ml: 1,
        px: 0.6,
        py: 0.1,
        borderRadius: 0.75,
        border: '1px solid',
        borderColor: 'inherit',
        opacity: 0.8,
        fontSize: '0.7rem',
        fontWeight: 700,
        letterSpacing: 0.5,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        lineHeight: 1,
      }}
    >
      {text}
    </Box>
  );
}

/** Keystroke clock for scanner-burst detection. Module level so the render rules see no impure call. */
const scanClockMs = () => performance.now();

export function PosPage() {
  useLocale();
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const companyId = user?.companyId ?? 0;
  const userId = user?.id ?? 0;
  const queryClient = useQueryClient();
  const searchRef = useRef<HTMLInputElement>(null);
  const scanGaps = useRef<number[]>([]);
  const scanLast = useRef(0);
  const scanBuf = useRef('');
  const customerSelectRef = useRef<HTMLInputElement>(null);
  const cartRef = useRef<CartLine[]>([]);
  const heldLineCountRef = useRef(0);
  const sessionIdsRef = useRef<string[]>(['primary']);
  const activeSessionIdRef = useRef('primary');
  const restoreSessionRef = useRef<(snap: PosBillSession) => void>(() => {});
  const highlightedRef = useRef<Product | null>(null);
  const [scanListOpen, setScanListOpen] = useState(false);
  const [nameOnlySale, setNameOnlySale] = useState(false);
  const [serialsOpen, setSerialsOpen] = useState(false);
  const [draftWriteFailed, setDraftWriteFailed] = useState(false);
  const [draftReady, setDraftReady] = useState(false);
  const pricedRef = useRef(false);

  // QOS-0040: remember the till's last-used tender so the common case (a till
  // that is ~all UPI, or ~all cash) does not re-pick it every sale. Emphasis +
  // autofocus move to the remembered button; it stays a one-key change.
  const POS_LAST_METHOD_KEY = 'bizboard:pos-last-method';
  const [lastMethod, setLastMethod] = useState<PaymentMode>(() => {
    try {
      const saved = localStorage.getItem(`${POS_LAST_METHOD_KEY}:${companyId}`);
      if (saved === 'UPI' || saved === 'BANK' || saved === 'CARD' || saved === 'CREDIT' || saved === 'CHEQUE') {
        return saved;
      }
      return 'CASH';
    } catch {
      return 'CASH';
    }
  });
  const rememberMethod = useCallback((m: PaymentMode) => {
    setLastMethod(m);
    try {
      localStorage.setItem(`${POS_LAST_METHOD_KEY}:${companyId}`, m);
    } catch {
      // quota / private mode — non-fatal
    }
  }, [companyId]);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [heldCarts, setHeldCarts] = useState<{ id: string; label: string; cart: CartLine[]; at: number }[]>([]);
  const [customerQuery, setCustomerQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [showAdjust, setShowAdjust] = useState(false);
  const [showMoreTenders, setShowMoreTenders] = useState(false);
  const [ownerPin, setOwnerPin] = useState('');
  const [refundMode, setRefundMode] = useState<'CASH' | 'BANK' | 'ADVANCE' | 'SPLIT'>('CASH');
  const [applyAdvanceNext, setApplyAdvanceNext] = useState(false);
  const [pharmacyPatient, setPharmacyPatient] = useState('');
  const [pharmacyPrescriber, setPharmacyPrescriber] = useState('');
  const [pharmacyRegistration, setPharmacyRegistration] = useState('');
  const [pharmacyNote, setPharmacyNote] = useState('');
  const [salespersonId, setSalespersonId] = useState('');
  const [returnPick, setReturnPick] = useState<{
    invoice: number;
    exchange: boolean;
    lines: Array<{ id: number; name: string; take: string }>;
  } | null>(null);
  const [prescriptionFileId, setPrescriptionFileId] = useState<number | null>(null);
  const [expiredReason, setExpiredReason] = useState('');
  const [paymentRef, setPaymentRef] = useState('');
  const [recentBills, setRecentBills] = useState<{ id: number; number: string }[]>([]);
  const [upiArmed, setUpiArmed] = useState(false);
  const [pricePrompt, setPricePrompt] = useState<{ key: string; price: number; reason: string } | null>(null);
  const [pinPrompt, setPinPrompt] = useState<{
    mode: PaymentMode;
    opts?: {
      confirmBlankPos?: boolean;
      confirmWalkIn?: boolean;
      confirmTotalsMismatch?: boolean;
      shortCollectAmount?: number;
      splitPayments?: Array<{ mode: string; amount: string }>;
    };
  } | null>(null);
  const [drawerAsk, setDrawerAsk] = useState(false);
  const [scaleReady] = useState(() => typeof navigator !== 'undefined' && 'serial' in navigator);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'F2') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const batchProductIds = useMemo(
    () => [...new Set(cart.filter((line) => line.product.trackBatch).map((line) => line.product.id))],
    [cart],
  );
  const batchLots = useQuery({
    queryKey: ['pos-batch-lots', batchProductIds],
    enabled: batchProductIds.length > 0,
    queryFn: async () => (await Promise.all(batchProductIds.map((id) => listBatches(id)))).flat(),
  });

  const [productQuery, setProductQuery] = useState('');
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const debouncedQuery = useDebouncedValue(productQuery, 250);
  const [customerId, setCustomerId] = useState<number | ''>('');
  const [busy, setBusy] = useState(false);
  const [confirmClearCartOpen, setConfirmClearCartOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** Dedicated credit-limit-exceeded banner (not the generic error toast) —
   * SalesService.complete() raises this for a POS checkout that would push a
   * customer's exposure over their credit_limit. */
  const [creditLimitBanner, setCreditLimitBanner] = useState<{
    customerName?: string;
    creditLimit?: string;
    currentExposure?: string;
    invoiceTotal?: string;
  } | null>(null);
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
  const [splitCash, setSplitCash] = useState(0);
  const [cheque, setCheque] = useState<ChequePaymentValues>(EMPTY_CHEQUE);
  const [invoiceDiscount, setInvoiceDiscount] = useState(0);
  const [additionalCharges, setAdditionalCharges] = useState(0);
  const [sessionIds, setSessionIds] = useState<string[]>(['primary']);
  const [activeSessionId, setActiveSessionId] = useState('primary');
  const sessionStore = useRef<Record<string, PosBillSession>>({});
  const [upiPending, setUpiPending] = useState<UpiPending | null>(null);
  const [cashPending, setCashPending] = useState<CashPending | null>(null);
  const [waOffer, setWaOffer] = useState<{ invoiceId: number; phone: string } | null>(null);
  const [blankPosMode, setBlankPosMode] = useState<PaymentMode | null>(null);
  const [unpaidRecover, setUnpaidRecover] = useState<{ id: number; number: string } | null>(null);
  const [walkInConfirmMode, setWalkInConfirmMode] = useState<PaymentMode | null>(null);
  const [walkInName, setWalkInName] = useState('');
  const [saleJustCompleted, setSaleJustCompleted] = useState(false);
  const lastCompletedSaleRef = useRef<{ id: number; number?: string | null; whatsappOffer?: { phone?: string } } | null>(null);
  const [serialInput, setSerialInput] = useState('');
  const [warehouseId, setWarehouseId] = useState<number | ''>('');
  const [serialBatchError, setSerialBatchError] = useState<{
    mode: PaymentMode;
    message: string;
  } | null>(null);
  const flushGuard = useRef(false);
  /** CR-112: sync double-submit guard (busy state alone is too late). */
  const checkoutGuard = useRef(false);
  /** SR-54 / H-02: pointer interactions since the current cart was started —
   * a keyboard-and-scanner-only checkout ends with 0. Reset on first line. */
  const pointerCount = useRef(0);
  /** CR-111: last successful server preview grand total for tender UI. */
  const [serverTenderTotal, setServerTenderTotal] = useState<number | null>(null);
  const [tenderPreviewFailed, setTenderPreviewFailed] = useState(false);
  const [totalsReconcile, setTotalsReconcile] = useState<{
    shown: number;
    billed: number;
    mode: PaymentMode;
    splitPayments?: Array<{ mode: string; amount: string }>;
  } | null>(null);
  /** Split tender must survive the totals / blank-POS confirm dialogs. */
  const splitHold = useRef<Array<{ mode: string; amount: string }> | undefined>(undefined);
  const [thermalWarn, setThermalWarn] = useState<{ invoiceId: number; number: string } | null>(null);
  const [isFlushing, setIsFlushing] = useState(false);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const taxEnabled = preferredInvoiceType(company.data?.registrationType) !== 'NON_GST';
  const posInvoiceType = taxEnabled ? 'RETAIL' : 'NON_GST';
  const debouncedCustomer = useDebouncedValue(customerQuery, 250);
  const customerSearch = useQuery({
    queryKey: ['pos-customer-search', debouncedCustomer],
    queryFn: () => listCustomersPage({ q: debouncedCustomer, pageSize: 20, status: 'ACTIVE' }),
    enabled: debouncedCustomer.trim().length >= 1,
  });
  const posSettings = useQuery({
    queryKey: ['pos-settings', companyId],
    queryFn: getPosSettings,
    enabled: companyId > 0,
  });
  const recentServer = useQuery({
    queryKey: ['pos-recent-bills', companyId],
    queryFn: () => listSalesInvoicesPage({ pageSize: 5, status: 'COMPLETED' }),
    enabled: companyId > 0,
  });
  const catalogProbe = useQuery({
    queryKey: ['pos-catalog-count', companyId],
    queryFn: () => listProductsPage({ pageSize: 1 }),
    enabled: companyId > 0,
  });
  const selectedCustomer = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: Boolean(customerId),
  });
  const priceLists = useQuery({ queryKey: ['price-lists'], queryFn: listPriceLists });
  const unitPriceFor = useCallback(
    (productId: number, qty: number, sellingPrice?: string | number) => {
      const hit = resolveListUnitPrice(
        priceLists.data,
        selectedCustomer.data?.priceList,
        productId,
        qty,
      );
      if (hit) return hit.unitPrice;
      return toNumber(sellingPrice);
    },
    [priceLists.data, selectedCustomer.data?.priceList],
  );
  const cartPreviewKey = useDebouncedValue(
    JSON.stringify({
      cart: cart.map((l) => [l.key, l.quantity, l.discountPercent, l.unitName]),
      customerId,
      invoiceDiscount,
      additionalCharges,
    }),
    400,
  );
  useEffect(() => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) return;
    if (cart.length === 0) return;
    let cancelled = false;
    void fetchPosPreviewGrandTotal({
      customerId: customerId ? Number(customerId) : undefined,
      invoiceType: posInvoiceType,
      priceModeInclusive: company.data?.priceMode === 'INCLUSIVE',
      taxEnabled,
      cart,
      unitPriceFor: (id, qty) =>
        unitPriceFor(id, qty, cart.find((l) => l.product.id === id)?.product.sellingPrice),
      invoiceDiscount,
      additionalCharges,
    })
      .then((total) => {
        if (cancelled) return;
        setServerTenderTotal(total);
        setTenderPreviewFailed(false);
      })
      .catch(() => {
        if (!cancelled) setTenderPreviewFailed(true);
      });
    return () => {
      cancelled = true;
    };
    // cartPreviewKey is the debounce trigger; cart is read inside.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartPreviewKey, posInvoiceType, taxEnabled, company.data?.priceMode, unitPriceFor]);
  const hasCf = Object.values(cfFilters).some((values) => values.length);
  const products = useQuery({
    queryKey: ['pos-product-search', debouncedQuery, cfFilters],
    queryFn: () => searchProducts(debouncedQuery, { cf: cfFilters }),
    enabled: debouncedQuery.length >= 1 || hasCf,
  });
  const stockBalances = useQuery({
    queryKey: ['stock', warehouseId],
    queryFn: () => listStock(warehouseId ? { warehouse: Number(warehouseId) } : {}),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
  const tillToday = useTill(posTerminalId());
  const tillShift = tillToday.data?.shift;
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });

  if (!warehouseId && warehouses.data?.length) {
    const fallback = warehouses.data.find((row) => row.isDefault) ?? warehouses.data[0];
    if (fallback && warehouseId !== fallback.id) setWarehouseId(fallback.id);
  }
  const availableByProduct = useMemo(
    () => availableInWarehouse(stockBalances.data ?? [], warehouseId),
    [stockBalances.data, warehouseId],
  );

  useEffect(() => {
    if (!stockBalances.data || warehouseId === '') return;
    // Stock arrives after the line was added, so the earliest lot is filled in once it lands.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCart((prev) => {
      let changed = false;
      const next = prev.map((line) => {
        if (!line.product.trackBatch || String(line.batchNo ?? '').trim()) return line;
        const lots = availablePosBatches(stockBalances.data ?? [], line.product.id, warehouseId);
        if (!lots.length) return line;
        changed = true;
        return { ...line, batchNo: lots[0].batchNo };
      });
      return changed ? next : prev;
    });
  }, [stockBalances.data, warehouseId]);

  const posStockBlocked = useMemo(() => {
    if (company.data?.negativeStockPolicy !== 'BLOCK') return false;
    if (!stockBalances.data || stockBalances.isError) return false;
    const needed = new Map<number, number>();
    for (const line of cart) {
      if (lineSkipsStockGate(line.product)) continue;
      needed.set(line.product.id, (needed.get(line.product.id) ?? 0) + toNumber(line.quantity));
    }
    for (const [id, qty] of needed) {
      if (qty > (availableByProduct.get(id) ?? 0) + 1e-9) return true;
    }
    return false;
  }, [cart, availableByProduct, company.data?.negativeStockPolicy, stockBalances.data, stockBalances.isError]);
  const posMissingBatch = cart.some((l) => l.product.trackBatch && !String(l.batchNo ?? '').trim());
  const posMissingSerial = cart.some(
    (l) => l.product.trackSerial && (l.serialNumbers ?? []).length !== Math.trunc(l.quantity),
  );

  const activeCustomers = useMemo(() => {
    const rows = (customerSearch.data?.results ?? []).filter((c) => c.status === 'ACTIVE' && !c.isPosWalkIn);
    return rows.sort((a, b) => a.name.localeCompare(b.name));
  }, [customerSearch.data?.results]);

  const walkInLookup = useQuery({
    queryKey: ['pos-walk-in', companyId],
    queryFn: () => listCustomersPage({ pageSize: 1, is_pos_walk_in: '1' }),
    enabled: companyId > 0,
  });
  const walkInCustomer = useMemo(
    () => walkInLookup.data?.results?.[0] ?? activeCustomers.find((c) => c.isPosWalkIn),
    [activeCustomers, walkInLookup.data],
  );
  useEffect(() => {
    if (!companyId || !userId) return;
    let cancelled = false;
    void (async () => {
      const storageKey = `bb_pos_holds:${companyId}:${userId}`;
      const migratedKey = `bb_pos_sessions_parked:${companyId}:${userId}`;
      try {
        const raw = sessionStorage.getItem(storageKey);
        const local = raw ? JSON.parse(raw) as { label?: string; cart?: CartLine[]; at?: number }[] : [];
        for (const row of local) {
          if (row.cart?.length) await createPosHold(row.label || 'Cart', { cart: row.cart, at: row.at });
        }
        sessionStorage.removeItem(storageKey);
      } catch {
        /* the server list replaces the device store */
      }
      if (!sessionStorage.getItem(migratedKey)) {
        sessionStorage.setItem(migratedKey, '1');
        try {
          const read = readDraft<{
            sessions: Record<string, PosBillSession>;
            activeSessionId: string;
            sessionIds: string[];
          }>(companyId, userId, 'pos-sessions');
          if (read.ok) {
            const ids = (read.payload.sessionIds?.length
              ? read.payload.sessionIds
              : [read.payload.activeSessionId]).filter(Boolean);
            const activeId = read.payload.activeSessionId;
            for (const id of ids) {
              if (id === activeId) continue;
              const extra = read.payload.sessions?.[id];
              if (extra?.cart?.length) {
                await createPosHold(t('pos.holdCart'), { cart: extra.cart, at: Date.now() });
              }
            }
          }
        } catch {
          sessionStorage.removeItem(migratedKey);
        }
      }
      try {
        const rows = await listPosHolds();
        if (cancelled) return;
        setHeldCarts(rows.map((row) => ({
          id: String(row.id),
          label: row.label,
          cart: Array.isArray(row.payload?.cart) ? row.payload.cart as CartLine[] : [],
          at: Number(row.payload?.at) || Date.now(),
        })));
      } catch {
        /* offline: nothing to recall until the server answers */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [companyId, userId]);
  useEffect(() => {
    const onFocus = () => {
      void queryClient.invalidateQueries({ queryKey: ['stock'] });
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [queryClient]);

  // Not while the cashier chose "name only": that choice is exactly "no saved customer".
  if (!customerId && !nameOnlySale && walkInCustomer?.id) setCustomerId(walkInCustomer.id);

  useEffect(() => {
    void listDrafts(companyId, userId).then((drafts) => {
      setHasOutboxItems(drafts.some((row) => row.kind === 'pos' || row.kind === 'invoice'));
      const queuedKeys = new Set(drafts.map((row) => row.idempotencyKey).filter(Boolean));
      const purged = omitQueuedHeldSessions(
        sessionStore.current,
        sessionIdsRef.current,
        activeSessionIdRef.current,
        queuedKeys,
      );
      if (purged.droppedCount > 0) {
        if (purged.sessionIds.length === 0) {
          const emptyId = 'primary';
          const empty: PosBillSession = {
            id: emptyId,
            cart: [],
            customerId: '',
            warehouseId: '',
            cashTendered: '',
            idempotencyKey: null,
            upiPending: null,
            cashPending: null,
            walkInName: '',
            serverTenderTotal: null,
            cheque: EMPTY_CHEQUE,
            invoiceDiscount: 0,
            additionalCharges: 0,
          };
          sessionStore.current = { [emptyId]: empty };
          setSessionIds([emptyId]);
          setActiveSessionId(emptyId);
          restoreSessionRef.current(empty);
          heldLineCountRef.current = 0;
        } else {
          sessionStore.current = purged.sessions;
          setSessionIds(purged.sessionIds);
          setActiveSessionId(purged.activeSessionId);
          const snap = purged.sessions[purged.activeSessionId];
          if (snap) {
            restoreSessionRef.current(snap);
            heldLineCountRef.current = snap.cart.length;
          }
        }
      }
      const draft = [...drafts].reverse().find((row) => row.kind === 'pos');
      if (!draft || navigator.onLine) return;
      if (!draft.lines?.length) return;
      if (draft.idempotencyKey && purged.droppedKeys.includes(draft.idempotencyKey)) return;
      if (heldLineCountRef.current > 0) return;
      setIdempotencyKey(draft.idempotencyKey);
      if (draft.customerId) setCustomerId(draft.customerId);
      const pendingName = String(draft.pendingCustomerName || draft.payload?.pendingCustomerName || '').trim();
      if (!draft.customerId && pendingName) setWalkInName(pendingName);
      const recoveredWh = Number(draft.payload?.warehouse || 0);
      if (recoveredWh) setWarehouseId(recoveredWh);
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
            trackSerial: Boolean(line.serials?.length),
          } as Product,
          quantity: line.quantity,
          discountPercent: line.discountPercent ?? 0,
          unitName: line.unitName || 'PCS',
          serialNumbers: line.serials,
          priceAlreadyConverted: true,
        })),
      );
      setMessage(t('pos.recoveredDraft'));
    });
  }, [companyId, userId]);

  const intraState = useMemo(() => {
    const party = selectedCustomer.data;
    const resolved = isIntraState(
      company.data?.gstin ?? company.data?.state,
      party?.gstin ?? party?.state,
      { assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty },
    );
    // F2-027: a blank-place-of-supply walk-in RETAIL sale is completed with
    // confirmBlankPos, and the server then applies assume-local (CGST+SGST).
    // Show that tax in the tender panel so the displayed total matches what
    // will actually post — otherwise the cash receipt is booked larger than
    // the cash taken (till shortage on every such sale).
    if (resolved === null && taxEnabled) return true;
    return resolved;
  }, [company.data, selectedCustomer.data, taxEnabled]);

  const isInclusive = company.data?.priceMode === 'INCLUSIVE';

  const lineTaxes = useMemo(
    () =>
      cart.map((line) => {
        let unitPrice = posLineUnitPrice(
          line.product,
          line.quantity,
          line.unitName,
          unitPriceFor,
          line.priceAlreadyConverted,
        );
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
    [cart, intraState, isInclusive, taxEnabled, unitPriceFor],
  );

  const totals = useMemo(
    () =>
        calculateInvoiceTotals(
        lineTaxes.map((tax, i) => ({
          ...tax,
          gstRate: taxEnabled ? toNumber(cart[i]?.product.gstRate) : 0,
          intraState,
        })),
        {
          applyRoundOff: true,
          invoiceDiscount,
          additionalCharges,
          invoiceDiscountMode: discountModeForCustomer(Boolean(selectedCustomer.data?.gstin)),
        },
      ),
    [lineTaxes, cart, intraState, taxEnabled, invoiceDiscount, additionalCharges, selectedCustomer.data?.gstin],
  );

  const tenderedAmount =
    cashTendered === '' ? (serverTenderTotal ?? totals.grandTotal) : toNumber(cashTendered);
  // CR-111: drive change/labels from server gate total when available.
  const gateTotal = serverTenderTotal ?? totals.grandTotal;

  const captureSession = useCallback((): PosBillSession => ({
    id: activeSessionId,
    cart,
    customerId,
    warehouseId,
    cashTendered,
    idempotencyKey,
    upiPending,
    cashPending,
    walkInName,
    serverTenderTotal,
    cheque,
    invoiceDiscount,
    additionalCharges,
  }), [
    activeSessionId, additionalCharges, cart, cashPending, cashTendered, cheque, customerId,
    idempotencyKey, invoiceDiscount, serverTenderTotal, upiPending, walkInName, warehouseId,
  ]);

  const restoreSession = useCallback((snap: PosBillSession) => {
    setCart(snap.cart);
    setCustomerId(snap.customerId);
    setWarehouseId(snap.warehouseId);
    setCashTendered(snap.cashTendered);
    setIdempotencyKey(snap.idempotencyKey);
    setUpiPending(snap.upiPending);
    setCashPending(snap.cashPending);
    setWalkInName(snap.walkInName);
    setNameOnlySale(Boolean(snap.walkInName) && snap.customerId === '');
    setServerTenderTotal(snap.serverTenderTotal);
    setCheque(snap.cheque);
    setInvoiceDiscount(snap.invoiceDiscount);
    setAdditionalCharges(snap.additionalCharges);
  }, []);
  useLayoutEffect(() => {
    cartRef.current = cart;
    sessionIdsRef.current = sessionIds;
    activeSessionIdRef.current = activeSessionId;
    restoreSessionRef.current = restoreSession;
  });

  useEffect(() => {
    if (!companyId || !userId || draftReady) return;
    let cancelled = false;
    queueMicrotask(() => {
    if (cancelled) return;
    const read = readDraft<{
      sessions: Record<string, PosBillSession>;
      activeSessionId: string;
      sessionIds: string[];
    }>(companyId, userId, 'pos-sessions');
    if (read.ok) {
      sessionStore.current = read.payload.sessions ?? {};
      const ids = (read.payload.sessionIds?.length ? read.payload.sessionIds : [read.payload.activeSessionId]).filter(Boolean);
      sessionIdsRef.current = ids;
      setSessionIds(ids);
      const snap = read.payload.sessions?.[read.payload.activeSessionId];
      if (snap) {
        trackShopFloor('draft_restored', { feature: 'pos' });
        const activeId = snap.id || read.payload.activeSessionId;
        activeSessionIdRef.current = activeId;
        restoreSession(snap);
        setActiveSessionId(activeId);
        heldLineCountRef.current = snap.cart?.length ?? 0;
        const activeIdForTabs = snap.id || read.payload.activeSessionId;
        if (ids.some((id) => id !== activeIdForTabs)) setSessionIds([activeIdForTabs]);
      } else {
        heldLineCountRef.current = 0;
      }
    } else {
      try {
        const rawLegacy = localStorage.getItem(legacyPosCartKey(companyId));
        if (rawLegacy) {
          const parsed = JSON.parse(rawLegacy);
          if (Array.isArray(parsed) && parsed.length > 0) {
            trackShopFloor('draft_restored', { feature: 'pos' });
            setCart(parsed);
            heldLineCountRef.current = parsed.length;
          }
        }
      } catch {
        /* ignore legacy parse error */
      }
    }
    setDraftReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [companyId, userId, draftReady, restoreSession]);

  useEffect(() => {
    if (!draftReady || !companyId || !userId) return;
    sessionStore.current[activeSessionId] = captureSession();
    const result = writeDraft(companyId, userId, 'pos-sessions', {
      sessions: sessionStore.current,
      activeSessionId,
      sessionIds,
    });
    setDraftWriteFailed(!result.ok);
  }, [draftReady, companyId, userId, activeSessionId, sessionIds, captureSession]);

  useEffect(() => {
    if (!draftReady || pricedRef.current) return;
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
    const ids = new Set<number>();
    for (const snap of Object.values(sessionStore.current)) {
      for (const line of snap.cart ?? []) ids.add(line.product.id);
    }
    for (const line of cartRef.current) ids.add(line.product.id);
    if (ids.size === 0) {
      pricedRef.current = true;
      return;
    }
    pricedRef.current = true;
    void (async () => {
      const fresh = new Map<number, Product>();
      await Promise.all(
        [...ids].map(async (id) => {
          try {
            fresh.set(id, await getProduct(id));
          } catch (err) {
            const status =
              err && typeof err === 'object' && 'response' in err
                ? (err as { response?: { status?: number } }).response?.status
                : undefined;
            if (status === 404) return;
            const prior =
              cartRef.current.find((line) => line.product.id === id)?.product ??
              Object.values(sessionStore.current)
                .flatMap((snap) => snap.cart)
                .find((line) => line.product.id === id)?.product;
            if (prior) fresh.set(id, prior);
          }
        }),
      );
      const activeId = activeSessionIdRef.current;
      let inactiveChanged = false;
      const nextStore: Record<string, PosBillSession> = { ...sessionStore.current };
      for (const [id, snap] of Object.entries(sessionStore.current)) {
        if (id === activeId) continue;
        const priced = repriceLines(snap.cart, fresh);
        if (priced.changed) inactiveChanged = true;
        nextStore[id] = { ...snap, cart: priced.lines };
      }
      sessionStore.current = nextStore;
      setCart((prev) => {
        const priced = repriceLines(prev, fresh);
        if (priced.changed || inactiveChanged) {
          queueMicrotask(() => setMessage(t('pos.pricesUpdated')));
        }
        return priced.lines;
      });
    })();
  }, [draftReady]);

  const switchSession = useCallback((id: string) => {
    if (id === activeSessionId) return;
    sessionStore.current[activeSessionId] = captureSession();
    const next = sessionStore.current[id] ?? {
      id,
      cart: [],
      customerId: '',
      warehouseId: '',
      cashTendered: '',
      idempotencyKey: null,
      upiPending: null,
      cashPending: null,
      walkInName: '',
      serverTenderTotal: null,
      cheque: EMPTY_CHEQUE,
      invoiceDiscount: 0,
      additionalCharges: 0,
    };
    restoreSession(next);
    setActiveSessionId(id);
  }, [activeSessionId, captureSession, restoreSession]);

  const recallHold = useCallback((row: { id: string; cart: CartLine[] }) => {
    void (async () => {
      const current = cartRef.current;
      if (current.length > 0) {
        const parked = await createPosHold(t('pos.holdCart'), { cart: current, at: Date.now() });
        setHeldCarts((prev) => [
          ...prev.filter((item) => item.id !== row.id),
          { id: String(parked.id), label: t('pos.holdCart'), cart: current, at: Date.now() },
        ]);
      } else {
        setHeldCarts((prev) => prev.filter((item) => item.id !== row.id));
      }
      await releasePosHold(row.id);
      setCart(row.cart);
      searchRef.current?.focus();
    })().catch((err) => setError(getErrorMessage(err)));
  }, []);

  const holdAndCreateSession = useCallback(() => {
    if (cart.length === 0) return;
    void createPosHold(t('pos.holdCart'), { cart, at: Date.now() }).then((created) => {
      setHeldCarts((prev) => [...prev, { id: String(created.id), label: t('pos.holdCart'), cart, at: Date.now() }]);
      setCart([]);
      searchRef.current?.focus();
    }).catch((err) => setError(getErrorMessage(err)));
  }, [cart]);

  // CR-091 / CR-106 / CR-108 / CR-109: restore mid-settlement after reload.
  useEffect(() => {
    if (!companyId || !userId) return;
    let cancelled = false;
    queueMicrotask(() => {
    if (cancelled) return;
    const restoredCash = restoreCashPending(companyId, userId);
    if (restoredCash) {
      setCashPending(restoredCash);
      if (restoredCash.key) setIdempotencyKey(restoredCash.key);
      const recovered = unpaidRecoverFromAbort(restoredCash);
      if (recovered) setUnpaidRecover(recovered);
    }
    const restoredUpi = restoreUpiPending(companyId, userId);
    if (restoredUpi && !restoredCash) {
      setUpiPending(restoredUpi);
      if (restoredUpi.key) setIdempotencyKey(restoredUpi.key);
      const recovered = unpaidRecoverFromAbort(restoredUpi);
      if (recovered) setUnpaidRecover(recovered);
    }
    });
    return () => {
      cancelled = true;
    };
  }, [companyId, userId]);

  const changeDue = Math.max(0, tenderedAmount - gateTotal);

  useEffect(() => {
    // SR-54 / H-02: count pointer (mouse / touch / pen) presses on the POS page.
    const onPointer = () => {
      pointerCount.current += 1;
    };
    window.addEventListener('pointerdown', onPointer, { passive: true });
    return () => window.removeEventListener('pointerdown', onPointer);
  }, []);

  const tenderResetKey = `${cart.length}:${customerId}:${totals.grandTotal}`;
  const [seenTenderKey, setSeenTenderKey] = useState(tenderResetKey);
  if (seenTenderKey !== tenderResetKey) {
    setSeenTenderKey(tenderResetKey);
    setServerTenderTotal(null);
    setTenderPreviewFailed(false);
  }

  const addProduct = (product: Product | null, quantity = 1, opts?: { fromScan?: boolean }) => {
    if (!product || product.status !== 'ACTIVE') return;
    if (companyId && catalogSellBlocked(catalogAgeHours(companyId), posSettings.data?.catalogBlockHours ?? 72)) {
      setError(t('pos.catalogueStale', { hours: String(Math.floor(catalogAgeHours(companyId) ?? 0)) }));
      return;
    }
    if (cashPending || upiPending) {
      setError(t('pos.finishPendingSettlement'));
      return;
    }
    if (product.trackBatch || product.trackSerial) {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        setError(t('pos.offlineLotBlocked'));
        return;
      }
    }
    let incomingSerials: string[] | undefined;
    if (product.trackSerial) {
      incomingSerials = serialsMatchAddQty(serialInput, 1) ?? undefined;
      if (!incomingSerials) {
        setError(t('pos.serialRequired'));
        return;
      }
    }
    if (cart.length === 0) pointerCount.current = 0; // new cart → reset the H-02 counter
    trackShopFloor('pos_line_added');
    setSaleJustCompleted(false);
    setCart((prev) => {
      const lotsForMerge = product.trackBatch
        ? availablePosBatches(stockBalances.data ?? [], product.id, warehouseId)
        : [];
      const incomingBatch = product.trackBatch ? lotsForMerge[0]?.batchNo : undefined;
      const existing = prev.find((l) =>
        samePosLine(
          { productId: l.product.id, batchNo: l.batchNo, trackBatch: l.product.trackBatch },
          { productId: product.id, batchNo: incomingBatch, trackBatch: product.trackBatch },
        ),
      );
      if (existing) {
        return prev.map((l) =>
          l.key === existing.key
            ? {
                ...l,
                quantity: l.quantity + quantity,
                serialNumbers: incomingSerials
                  ? [...(l.serialNumbers ?? []), ...incomingSerials]
                  : l.serialNumbers,
              }
            : l,
        );
      }
      const lots = product.trackBatch
        ? availablePosBatches(stockBalances.data ?? [], product.id, warehouseId)
        : [];
      return [
        ...prev,
        {
          key: `${product.id}-${Date.now()}`,
          product,
          quantity,
          discountPercent: 0,
          unitName: product.unitName || 'PCS',
          serialNumbers: incomingSerials,
          batchNo: lots[0]?.batchNo,
        },
      ];
    });
    setSerialInput('');
    setProductQuery('');
    setError(null);
    const active = typeof document !== 'undefined' ? document.activeElement : null;
    const isEditingLine = active && (active.tagName === 'INPUT' || active.tagName === 'SELECT') && active !== searchRef.current;
    if (opts?.fromScan || !isEditingLine) {
      searchRef.current?.focus();
    }
  };

  const noteScanKey = (key: string) => {
    const now = scanClockMs();
    if (scanLast.current) scanGaps.current.push(now - scanLast.current);
    scanLast.current = now;
    if (key === 'Enter') {
      const burst = isScannerBurst(scanGaps.current);
      const raw = scanBuf.current;
      scanGaps.current = [];
      scanBuf.current = '';
      scanLast.current = 0;
      return { burst, raw };
    }
    if (key.length === 1) scanBuf.current += key;
    return null;
  };

  const tryAddByBarcode = async (raw?: string) => {
    const parsed = parseQtyBarcode((raw ?? productQuery).trim());
    const q = parsed?.code ?? (raw ?? productQuery).trim();
    const qty = parsed?.quantity ?? 1;
    if (!q) return;
    let matches: Product[] = [];
    try {
      if (typeof navigator !== 'undefined' && navigator.onLine === false && companyId) {
        const local = await findLocalCatalog(companyId, q);
        if (local) {
          addProduct({
            id: local.id,
            name: local.name,
            sku: local.sku,
            barcode: local.barcode,
            sellingPrice: local.price,
            gstRate: local.gst,
            hsnCode: local.hsn,
            unitName: local.unit,
            trackBatch: local.trackBatch,
            trackSerial: local.trackSerial,
            status: 'ACTIVE',
          } as Product, qty, { fromScan: true });
          return;
        }
      }
      matches = (await searchProducts(q)).filter((p) => p.status === 'ACTIVE');
    } catch {
      matches = (products.data ?? []).filter((p) => p.status === 'ACTIVE');
    }
    // F2-052: only auto-add on an exact barcode/SKU hit. A partial search that
    // happens to return a single fuzzy match must NOT be added silently.
    const exact =
      matches.find((p) => (p.barcode ?? '').toLowerCase() === q.toLowerCase()) ??
      matches.find((p) => p.sku.toLowerCase() === q.toLowerCase());
    if (exact) {
      addProduct(exact, qty, { fromScan: true });
      try {
        playScanTone('ok');
      } catch {
        /* audio blocked */
      }
      return;
    }
    setError(t('pos.barcodeNotFound', { q }));
  };

  const updateQty = (key: string, quantity: number) => {
    if (quantity <= 0) {
      setCart((prev) => prev.filter((l) => l.key !== key));
      return;
    }
    const line = cart.find((l) => l.key === key);
    if (line?.product.trackSerial) {
      const have = (line.serialNumbers ?? []).length;
      if (quantity > have) {
        const extra = serialsMatchAddQty(serialInput, quantity - have);
        if (!extra) {
          setError(t('pos.serialRequired'));
          return;
        }
        setCart((prev) =>
          prev.map((l) =>
            l.key === key
              ? { ...l, quantity, serialNumbers: [...(l.serialNumbers ?? []), ...extra] }
              : l,
          ),
        );
        setSerialInput('');
        return;
      }
      setCart((prev) =>
        prev.map((l) =>
          l.key === key
            ? { ...l, quantity, serialNumbers: (l.serialNumbers ?? []).slice(0, quantity) }
            : l,
        ),
      );
      return;
    }
    setCart((prev) => prev.map((l) => (l.key === key ? { ...l, quantity } : l)));
  };

  const updateDiscount = (key: string, discountPercent: number) => {
    const clamped = Math.min(100, Math.max(0, discountPercent));
    setCart((prev) => prev.map((l) => (l.key === key ? { ...l, discountPercent: clamped } : l)));
  };

  const clearCart = useCallback(() => {
    setCart([]);
    if (idempotencyKey) void removeDraft(companyId, userId, idempotencyKey);
    setIdempotencyKey(null);
    setCashTendered('');
    // A split entered for the last bill must not pre-fill the next customer's.
    setSplitCash(0);
    splitHold.current = undefined;
    setCashPending(null);
    clearCashPendingStorage(companyId, userId);
    setUpiPending(null);
    clearUpiPendingStorage(companyId, userId);
    setServerTenderTotal(null);
    setThermalWarn(null);
    setMessage(null);
    setError(null);
    setCreditLimitBanner(null);
    setWaOffer(null);
    searchRef.current?.focus();
  }, [companyId, idempotencyKey, userId]);

  /** Route a checkout failure to the dedicated credit-limit banner instead of
   * the generic error toast when that's what it is; otherwise unchanged. */
  const lastPayMode = useRef<PaymentMode>('CASH');

  const handleCheckoutError = useCallback((err: unknown) => {
    // The owner PIN approves one attempt. A wrong or used PIN must not ride along on the next bill.
    setOwnerPin('');
    if (getErrorCode(err) === 'pos_totals_mismatch') {
      const details = getErrorDetails(err) ?? {};
      const shown = Number(details.clientTotal ?? details.client_total);
      const billed = Number(details.serverTotal ?? details.server_total);
      if (Number.isFinite(shown) && Number.isFinite(billed)) {
        setTotalsReconcile({
          shown,
          billed,
          mode: lastPayMode.current,
          splitPayments: splitHold.current,
        });
        setError(null);
        return;
      }
    }
    if (getErrorCode(err) === 'credit_limit_exceeded') {
      const details = (getErrorDetails(err) ?? {}) as Record<string, unknown>;
      // The API renderer camelCases every response body, so the error extra
      // (built server-side as customer_name/credit_limit/...) arrives here as
      // customerName/creditLimit/... — check both camelCase and snake_case.
      const customerName = details.customerName ?? details.customer_name;
      const creditLimit = details.creditLimit ?? details.credit_limit;
      const currentExposure = details.currentExposure ?? details.current_exposure;
      const invoiceTotal = details.invoiceTotal ?? details.invoice_total;
      setCreditLimitBanner({
        customerName: typeof customerName === 'string' ? customerName : undefined,
        creditLimit: typeof creditLimit === 'string' ? creditLimit : undefined,
        currentExposure:
          typeof currentExposure === 'string' ? currentExposure : undefined,
        invoiceTotal: typeof invoiceTotal === 'string' ? invoiceTotal : undefined,
      });
      return;
    }
    setError(getErrorMessage(err));
  }, []);

  const finishSale = useCallback(
    async (completed: { id: number; number?: string | null; whatsappOffer?: { phone?: string } }, key?: string) => {
      lastCompletedSaleRef.current = completed;
      setOwnerPin('');
      setExpiredReason('');
      const warn = await printPosThermalOrWarn(completed);
      setThermalWarn(warn);
      setRecentBills((prev) => [
        { id: completed.id, number: String(completed.number ?? `#${completed.id}`) },
        ...prev.filter((row) => row.id !== completed.id),
      ].slice(0, 5));
      void queryClient.invalidateQueries({ queryKey: ['stock'] });
      void queryClient.invalidateQueries({ queryKey: ['pos-recent-bills', companyId] });
      if (walkInCustomer?.id) setCustomerId(walkInCustomer.id);
      setNameOnlySale(false);
      setWalkInName('');
      if (key) await removeDraft(companyId, userId, key);
      setCart([]);
      setIdempotencyKey(null);
      setCashTendered('');
      setCashPending(null);
      clearCashPendingStorage(companyId, userId);
      setUpiPending(null);
      clearUpiPendingStorage(companyId, userId);
      setServerTenderTotal(null);
      setMessage(t('pos.saleComplete', { number: completed.number ?? `#${completed.id}` }));
      setSaleJustCompleted(true);
      searchRef.current?.focus();
      const phone = (
        completed.whatsappOffer?.phone ||
        selectedCustomer.data?.phone ||
        ''
      ).replace(/\D/g, '');
      if (phone.length >= 10) {
        setWaOffer({ invoiceId: completed.id, phone });
      } else {
        setWaOffer(null);
      }
    },
    [companyId, queryClient, selectedCustomer.data?.phone, userId, walkInCustomer],
  );

  const sendWaMutation = useMutation({
    mutationFn: (offer: { invoiceId: number; phone: string }) =>
      shareInvoice(offer.invoiceId, { channel: 'WHATSAPP', recipient: offer.phone }),
    onSuccess: (res) => {
      const mode = res.mode ?? (res.status === 'SENT' ? 'cloud' : 'link');
      if (mode === 'cloud' && res.status === 'SENT') {
        setMessage(t('common.whatsappCloudSent'));
      } else if (res.error) {
        setMessage(t('common.whatsappFallbackWarn'));
      } else {
        setMessage(t('common.whatsappLinkHint'));
      }
      if (res.shareLink && mode !== 'cloud') {
        try {
          openShareUrl(res.shareLink);
        } catch {
          /* clickable recovery is the invoice share page */
        }
      }
      setWaOffer(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const performCashCheckout = useCallback(
    async (
      lines: InvoiceDraftLine[],
      customer: number,
      key?: string,
      confirmBlankPos = false,
      extras?: {
        confirmTotalsMismatch?: boolean;
        shortCollectAmount?: number;
        expectedTotal?: number;
        paymentMode?: PaymentMode;
        cheque?: ChequePaymentValues;
        payments?: Array<{ mode: string; amount: string }>;
      },
    ) => {
      setBusy(true);
      setError(null);
      setCreditLimitBanner(null);
      setMessage(null);
      const settlement: CashPending | null =
        posCashSettlementPhase(cashPending) === 'receipt_alloc' ? cashPending : null;
      try {
        let completed: { id: number; number?: string | null; grandTotal?: string | number };
        if (settlement) {
          completed = {
            id: settlement.invoiceId,
            number: settlement.invoiceNumber,
            grandTotal: settlement.amount,
          };
        } else {
          const invoiceDate = todayIso();
          const isInclusive = company.data?.priceMode === 'INCLUSIVE';
          const tenderedVal =
            extras?.shortCollectAmount != null
              ? extras.shortCollectAmount
              : cashTendered !== ''
                ? Number(cashTendered)
                : undefined;
          const started = Date.now();
          trackJourneyStarted('invoice_complete', 'pos');
          try {
            const atomicRes = await posCheckout(
              {
                confirm_blank_pos: confirmBlankPos,
                invoice: buildAtomicPosInvoicePayload({
                  customer,
                  invoiceType: posInvoiceType,
                  priceModeInclusive: isInclusive,
                  invoiceDate,
                  warehouseId: warehouseId ? Number(warehouseId) : undefined,
                  taxEnabled,
                  lines,
                  invoiceDiscount,
                  additionalCharges,
                  invoiceDiscountMode: discountModeForCustomer(Boolean(selectedCustomer.data?.gstin)),
                  paymentTermsDays: extras?.paymentMode === 'CREDIT' ? (selectedCustomer.data?.creditDays ?? 0) : 0,
                }),
                owner_pin: ownerPin || undefined,
                expired_lot_reason: expiredReason || undefined,
                terminal_id: posTerminalId(),
                terminal_label: posTerminalLabel(),
                apply_advance: applyAdvanceNext ? 'all' : undefined,
                pharmacy_patient: pharmacyPatient || undefined,
                pharmacy_prescriber: pharmacyPrescriber || undefined,
                pharmacy_registration: pharmacyRegistration || undefined,
                pharmacy_prescription: pharmacyNote || undefined,
                pharmacy_prescription_file: prescriptionFileId || undefined,
                salesperson: /^\d+$/.test(salespersonId) ? salespersonId : undefined,
                payment: {
                  mode: extras?.paymentMode ?? 'CASH',
                  tendered_amount: tenderedVal,
                  amount: extras?.shortCollectAmount,
                  expected_total: extras?.expectedTotal,
                  confirm_totals_mismatch: Boolean(extras?.confirmTotalsMismatch),
                  reference: paymentRef || undefined,
                  cheque_number: extras?.cheque?.chequeNumber || undefined,
                  cheque_bank_name: extras?.cheque?.chequeBankName || undefined,
                  cheque_date: extras?.cheque?.chequeDate || undefined,
                  cheque_image: extras?.cheque?.chequeImage || undefined,
                },
                ...(extras?.payments && extras.payments.length >= 2
                  ? { payments: extras.payments }
                  : {}),
              },
              { idempotencyKey: key },
            );
            trackInvoiceComplete(Date.now() - started, pointerCount.current);
            pointerCount.current = 0;
            completed = atomicRes?.invoice ?? atomicRes;
            await finishSale(completed, key);
            setApplyAdvanceNext(false);
            return;
          } catch (err) {
            trackJourneyFailed('invoice_complete', classifyCompleteFailure(err), {
              durationMs: Date.now() - started,
              feature: 'pos',
            });
            throw err;
          }
        }
        const invoiceTotal = toNumber(completed.grandTotal);
        const collected =
          extras?.shortCollectAmount != null && extras.shortCollectAmount > 0
            ? extras.shortCollectAmount
            : invoiceTotal;
        const tenderedVal = cashTendered ? Number(cashTendered) : 0;
        let receiptNotes = `POS — ${completed.number ?? completed.id}`;
        if (tenderedVal > collected) {
          const changeVal = (tenderedVal - collected).toFixed(2);
          receiptNotes += ` · Tendered: ₹${tenderedVal.toFixed(2)}, Change: ₹${changeVal}`;
        }
        await collectPosPayment({
          invoice: completed.id,
          mode: 'CASH',
          amount: collected,
          notes: receiptNotes,
        });
        await finishSale(completed, key);
      } catch (err) {
        if (settlement) {
          setCashPending(settlement);
          persistCashPending(companyId, userId, settlement);
          const recovered = unpaidRecoverFromAbort(settlement);
          if (recovered) setUnpaidRecover(recovered);
        }
        handleCheckoutError(err);
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [
      additionalCharges,
      cashPending,
      cashTendered,
      company.data,
      companyId,
      finishSale,
      handleCheckoutError,
      invoiceDiscount,
      ownerPin,
      expiredReason,
      applyAdvanceNext,
      pharmacyPatient,
      pharmacyPrescriber,
      pharmacyRegistration,
      pharmacyNote,
      salespersonId,
      paymentRef,
      posInvoiceType,
      prescriptionFileId,
      selectedCustomer.data,
      taxEnabled,
      userId,
      warehouseId,
    ],
  );

  const startUpiCheckout = useCallback(
    async (lines: InvoiceDraftLine[], customer: number, key?: string, confirmBlankPos = false) => {
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const invoiceTotal = gateTotal;
        let upiQr: Record<string, string> | null = null;
        try {
          upiQr = await getUpiQr({ amount: invoiceTotal, note: 'POS Sale' });
        } catch (err) {
          setError(t('pos.upiQrFailed', { error: getErrorMessage(err) }));
        }
        const pending: UpiPending = {
          customer,
          amount: invoiceTotal,
          key,
          upiQr,
          lines,
          confirmBlankPos,
          invoiceDiscount,
          additionalCharges,
        };
        setUpiPending(pending);
        persistUpiPending(companyId, userId, pending);
      } catch (err) {
        setError(getErrorMessage(err));
        throw err;
      } finally {
        setBusy(false);
      }
    },
    [additionalCharges, companyId, gateTotal, invoiceDiscount, userId],
  );

  const confirmUpiPayment = useCallback(async () => {
    if (!upiPending) return;
    setBusy(true);
    setError(null);
    setCreditLimitBanner(null);
    try {
      if (upiPending.invoiceId) {
        await collectPosPayment({
          invoice: upiPending.invoiceId,
          mode: 'UPI',
          amount: upiPending.amount,
          reference: paymentRef || undefined,
          notes: `POS UPI — ${upiPending.invoiceNumber}`,
        });
        await finishSale(
          { id: upiPending.invoiceId, number: upiPending.invoiceNumber },
          upiPending.key,
        );
      } else {
        const invoiceDate = todayIso();
        const isInclusive = company.data?.priceMode === 'INCLUSIVE';
        const checkoutLines =
          (upiPending.lines as InvoiceDraftLine[] | undefined) ||
          draftLinesFromCart(cart, taxEnabled, (id, qty) =>
            unitPriceFor(id, qty, cart.find((l) => l.product.id === id)?.product.sellingPrice),
          );
        const started = Date.now();
        trackJourneyStarted('invoice_complete', 'pos');
        try {
          const atomicRes = await posCheckout(
            {
              confirm_blank_pos: Boolean(upiPending.confirmBlankPos),
              invoice: buildAtomicPosInvoicePayload({
                customer: upiPending.customer,
                invoiceType: posInvoiceType,
                priceModeInclusive: isInclusive,
                invoiceDate,
                warehouseId: warehouseId ? Number(warehouseId) : undefined,
                taxEnabled,
                lines: checkoutLines,
                invoiceDiscount: upiPending.invoiceDiscount ?? invoiceDiscount,
                additionalCharges: upiPending.additionalCharges ?? additionalCharges,
              }),
              owner_pin: ownerPin || undefined,
              expired_lot_reason: expiredReason || undefined,
              terminal_id: posTerminalId(),
              terminal_label: posTerminalLabel(),
              payment: {
                mode: 'UPI',
                reference: paymentRef || undefined,
                amount: upiPending.amount,
                // CR-111: re-verify the amount quoted when the QR was shown
                // against the server's authoritative total at confirm time —
                // UPI previously skipped this gate entirely (cash-only bug).
                expected_total: upiPending.amount,
              },
            },
            { idempotencyKey: upiPending.key },
          );
          trackInvoiceComplete(Date.now() - started, pointerCount.current);
          pointerCount.current = 0;
          await finishSale(atomicRes.invoice, upiPending.key);
          void postPosEvent({
            kind: 'upi_received',
            invoiceId: atomicRes.invoice.id,
            detail: `UPI ${upiPending.amount}`,
          });
        } catch (err) {
          trackJourneyFailed('invoice_complete', classifyCompleteFailure(err), {
            durationMs: Date.now() - started,
            feature: 'pos',
          });
          throw err;
        }
      }
      setUpiPending(null);
      clearUpiPendingStorage(companyId, userId);
    } catch (err) {
      handleCheckoutError(err);
    } finally {
      setBusy(false);
    }
  }, [
    additionalCharges,
    cart,
    company.data,
    companyId,
    finishSale,
    handleCheckoutError,
    expiredReason,
    invoiceDiscount,
    ownerPin,
    paymentRef,
    posInvoiceType,
    taxEnabled,
    unitPriceFor,
    upiPending,
    userId,
    warehouseId,
  ]);

  const flushPendingDraft = useCallback(async () => {
    // CR-004: mutual exclusion with active checkout
    if (flushGuard.current || checkoutGuard.current || !navigator.onLine || !companyId || !userId) return;
    flushGuard.current = true;
    setIsFlushing(true);
    const thermalWarns: Array<{ invoiceId: number; number: string }> = [];
    try {
      const queued = (await listDrafts(companyId, userId))
        .filter((draft) => draft.kind === 'pos' && isFlushableDraft(draft) && Number(draft.customerId || draft.payload?.customer || 0) > 0)
        .slice(0, 50);
      if (queued.length > 1) {
        // Bulk sync first. A bill it refuses is left in the outbox, and the one-by-one pass
        // below retries it with the full error handling. A transport failure falls through too.
        try {
          const batch = await flushPosBatch(queued);
          const failed = new Set(batch.errors.map((row) => row.index));
          for (let index = 0; index < queued.length; index += 1) {
            if (!failed.has(index)) await removeDraft(companyId, userId, queued[index].idempotencyKey);
          }
          for (const invoice of batch.invoices) {
            if (!invoice.id) continue;
            const warn = await printPosThermalOrWarn({ id: Number(invoice.id), number: invoice.number });
            if (warn) thermalWarns.push(warn);
          }
        } catch {
          /* the single-bill pass below will retry every draft */
        }
      }
      const result = await flushOutbox(
        companyId,
        userId,
        async (draft) => {
          const completed = await flushPosDraft(draft);
          if (completed?.id) {
            const warn = await printPosThermalOrWarn({
              id: Number(completed.id),
              number: completed.number,
            });
            if (warn) thermalWarns.push(warn);
          }
        },
        (draft) => draft.kind === 'pos' && isFlushableDraft(draft),
      );
      if (result.failed > 0) {
        trackShopFloor('offline_flush_fail');
        const failedDraft = result.failedDrafts?.[0];
        if (failedDraft?.lines?.length) {
          const restored: CartLine[] = [];
          for (const line of failedDraft.lines) {
            try {
              const product = await getProduct(line.productId);
              restored.push({
                key: `${product.id}-${restored.length}`,
                product,
                quantity: line.quantity,
                discountPercent: line.discountPercent ?? 0,
                unitName: line.unitName || product.unitName || 'PCS',
                serialNumbers: line.serials,
                batchNo: line.batchNo,
                priceOverride: line.unitPrice,
                priceAlreadyConverted: true,
                syncError: result.errors[0] || t('pos.lineSyncFailed'),
              });
            } catch {
              /* the line stays in the outbox */
            }
          }
          if (restored.length) setCart(restored);
        }
        setError(
          t('pos.syncReopened', {
            error: result.errors.slice(0, 2).join(' · '),
          }),
        );
      } else if (result.flushed > 0) {
        setCart([]);
        setCashTendered('');
        setWalkInName('');
        setIdempotencyKey(null);
        setMessage(t('pos.syncedOfflineSales', { count: String(result.flushed) }));
      }
      if (thermalWarns.length > 0) {
        // CR-118: surface all thermal print failures across multi-flush
        const labels = thermalWarns.map((w) => w.number).join(', ');
        setError((prev) =>
          prev
            ? `${prev} · Thermal print failed: ${labels}`
            : `Thermal print failed: ${labels}`,
        );
      }
    } finally {
      flushGuard.current = false;
      setIsFlushing(false);
      if ((typeof navigator === 'undefined' || navigator.onLine) && companyId && userId) {
        const left = await listDrafts(companyId, userId);
        if (!left.some((draft) => draft.kind === 'pos')) clearPosOutage();
      }
    }
  }, [companyId, userId]);

  // The catalogue follows the company, not the customer: switching customer must not re-download it.
  useEffect(() => {
    if (!companyId || (typeof navigator !== 'undefined' && navigator.onLine === false)) return undefined;
    void syncPosCatalog(companyId).catch(() => undefined);
    const timer = window.setInterval(() => {
      if (typeof navigator === 'undefined' || navigator.onLine) {
        void syncPosCatalog(companyId).catch(() => undefined);
      }
    }, 15 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [companyId]);

  useEffect(() => {
    if (!companyId || (typeof navigator !== 'undefined' && navigator.onLine === false)) return undefined;
    const customers = customerId ? [Number(customerId)] : [];
    void syncPosPriceLists(companyId, customers).catch(() => undefined);
    if (customerId) {
      localStorage.setItem(`bb_pos_credit_cached:${companyId}:${customerId}`, new Date().toISOString());
    }
    const timer = window.setInterval(() => {
      if (typeof navigator === 'undefined' || navigator.onLine) {
        void syncPosPriceLists(companyId, customers).catch(() => undefined);
      }
    }, 15 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [companyId, customerId]);

  useEffect(() => {
    const onOnline = () => {
      setOffline(false);
      void flushPendingDraft();
    };
    const onOffline = () => {
      posOutageId();
      setOffline(true);
    };
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    // SR-34: the DOM online event is unreliable inside the Android WebView —
    // also flush when @capacitor/network reports connectivity is back.
    const unsubNative = onNetworkOnline(onOnline);
    if (navigator.onLine) void flushPendingDraft();
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      unsubNative();
    };
  }, [flushPendingDraft]);

  const checkout = useCallback(
    async (mode: PaymentMode, opts?: {
      confirmBlankPos?: boolean;
      confirmWalkIn?: boolean;
      confirmTotalsMismatch?: boolean;
      shortCollectAmount?: number;
      splitPayments?: Array<{ mode: string; amount: string }>;
    }) => {
      lastPayMode.current = mode;
      if (opts?.splitPayments) {
        splitHold.current = opts.splitPayments;
      } else if (!opts?.confirmBlankPos && !opts?.confirmTotalsMismatch && !opts?.confirmWalkIn) {
        splitHold.current = undefined;
      }
      const splitPayments = splitHold.current;
      if (writesBlocked) {
        setError(t('billing.writesBlocked'));
        return;
      }
      if (posStockBlocked) {
        setError(t('billing.completeDisabledInsufficientStock'));
        return;
      }
      if (posMissingBatch) {
        setError(t('billing.completeDisabledMissingBatch'));
        setSerialBatchError({ mode, message: t('billing.completeDisabledMissingBatch') });
        return;
      }
      if (posMissingSerial) {
        setError(t('pos.serialRequired'));
        setSerialBatchError({ mode, message: t('pos.serialRequired') });
        return;
      }
      if (posSettings.data?.periodBlocked) {
        setError(posSettings.data.periodMessage || t('pos.periodClosed'));
        return;
      }
      const pricedBelowCost = cart.some((line) => {
        const price = line.priceOverride ?? unitPriceFor(line.product.id, line.quantity, line.product.sellingPrice);
        const cost = toNumber(line.product.purchasePrice);
        return cost > 0 && price + 1e-9 < cost;
      });
      const cap = toNumber(posSettings.data?.maxLineDiscount ?? 100);
      const overCap = cart.some((line) => (line.discountPercent || 0) > cap + 1e-9);
      if ((pricedBelowCost || overCap) && !ownerPin) {
        if (!posSettings.data?.pinConfigured) {
          setError(t('pos.pinNotSet'));
          return;
        }
        setPinPrompt({ mode, opts });
        return;
      }
      // Confirm-dialog retries must not be blocked by the busy flag from the
      // attempt that opened the dialog — that attempt returns before React
      // has committed setBusy(false).
      if (
        !opts?.confirmBlankPos &&
        !opts?.confirmWalkIn &&
        (checkoutGuard.current || flushGuard.current || busy || isFlushing)
      ) {
        return;
      }
      // CR-119: block a new cart sale while mid-settlement is outstanding.
      if (upiPending) {
        setError(t('pos.finishPendingUpi'));
        return;
      }
      if (cashPending && mode !== 'CASH') {
        setError(t('pos.finishPendingCash'));
        return;
      }
      checkoutGuard.current = true;
      const key = resolveSaleGestureKey(idempotencyKey, userGestureIdempotencyKey);
      setIdempotencyKey(key);
      setBusy(true);
      try {
      // CR-106: cashPending resume — skip cart/tender/blank gates; reuse restored key.
      if (cashPending && mode === 'CASH') {
        if (!navigator.onLine) {
          setError(t('pos.finishPaymentOnline'));
          return;
        }
        const resumeKey = resolveSaleGestureKey(
          cashPending.key || key,
          userGestureIdempotencyKey,
        );
        setIdempotencyKey(resumeKey);
        await performCashCheckout([], cashPending.customer, resumeKey, false);
        return;
      }

      let effectiveCustomerId = customerId;
      const typedName = walkInName.trim();
      const online = typeof navigator === 'undefined' || navigator.onLine;
      // Typed name only applies when no party is selected — leftover text must not override B2B.
      if (typedName && !effectiveCustomerId) {
        const existingNamed = activeCustomers.find(
          (c) => c.name.trim().toLowerCase() === typedName.toLowerCase(),
        );
        if (existingNamed) {
          effectiveCustomerId = existingNamed.id;
          setCustomerId(existingNamed.id);
        } else if (online) {
          try {
            const created = await createCustomer({ name: typedName, status: 'ACTIVE' });
            effectiveCustomerId = created.id;
            setCustomerId(created.id);
            setWalkInName('');
          } catch {
            setError(t('pos.selectCustomer'));
            return;
          }
        }
      } else if (!effectiveCustomerId) {
        if (walkInCustomer) {
          if (!opts?.confirmWalkIn) {
            setWalkInConfirmMode(mode);
            checkoutGuard.current = false;
            setBusy(false);
            return;
          }
          effectiveCustomerId = walkInCustomer.id;
          setCustomerId(walkInCustomer.id);
        } else if (online) {
          try {
            let created: { id: number };
            try {
              created = await createCustomer({ name: t('pos.walkInCustomer'), status: 'ACTIVE', isPosWalkIn: true });
            } catch (createErr) {
              // Another counter may have just created the one walk-in party.
              const again = await listCustomersPage({ pageSize: 1, is_pos_walk_in: '1' });
              const found = again.results?.[0];
              if (!found) throw createErr;
              created = found;
            }
            effectiveCustomerId = created.id;
            setCustomerId(created.id);
          } catch {
            setError(t('pos.selectCustomer'));
            return;
          }
        }
      }
      if (mode === 'CREDIT' && walkInCustomer && Number(effectiveCustomerId) === walkInCustomer.id) {
        setError(t('pos.creditNeedsName'));
        return;
      }
      if (cart.length === 0) {
        setError(t('pos.cartEmpty'));
        return;
      }
      // CR-111: online cash/UPI use server preview as till gate (and display source).
      // Walk-in customer id is resolved above before this gate so the first-pass skip
      // cannot bypass a known-customer-id requirement.
      let tenderGateTotal = gateTotal;
      const shownTotal = totals.grandTotal;
      if (navigator.onLine && effectiveCustomerId) {
        try {
          const previewTotal = await fetchPosPreviewGrandTotal({
            customerId: Number(effectiveCustomerId),
            invoiceType: posInvoiceType,
            priceModeInclusive: company.data?.priceMode === 'INCLUSIVE',
            taxEnabled,
            cart,
            unitPriceFor: (id, qty) =>
              unitPriceFor(id, qty, cart.find((l) => l.product.id === id)?.product.sellingPrice),
            invoiceDiscount,
            additionalCharges,
          });
          tenderGateTotal = previewTotal;
          setServerTenderTotal(previewTotal);
          setTenderPreviewFailed(false);
          if (
            Math.abs(previewTotal - shownTotal) > 0.05 &&
            !opts?.confirmTotalsMismatch
          ) {
            setTotalsReconcile({
              shown: shownTotal,
              billed: previewTotal,
              mode,
              splitPayments,
            });
            checkoutGuard.current = false;
            setBusy(false);
            return;
          }
        } catch {
          setTenderPreviewFailed(true);
          setError(t('pos.tenderPreviewRetry'));
          return;
        }
      }
      const exactTender =
        opts?.shortCollectAmount != null
          ? opts.shortCollectAmount
          : cashTendered === ''
            ? tenderGateTotal
            : tenderedAmount;
      if (
        mode === 'CASH' &&
        !splitPayments?.length &&
        exactTender + 1e-9 < tenderGateTotal &&
        opts?.shortCollectAmount == null
      ) {
        setError(t('pos.tenderTooLow'));
        return;
      }
      let settledSplit = splitPayments;
      if (settledSplit && settledSplit.length >= 2) {
        if (!navigator.onLine) {
          setError(t('pos.upiNeedsConnection'));
          return;
        }
        const cash = roundMoney(Number(settledSplit[0].amount) || 0);
        const upi = roundMoney(tenderGateTotal - cash);
        if (!(cash > 0) || !(upi > 0)) {
          setError(t('pos.tenderTooLow'));
          return;
        }
        settledSplit = [
          { mode: 'CASH', amount: cash.toFixed(2) },
          { mode: settledSplit[1].mode || 'UPI', amount: upi.toFixed(2) },
        ];
        splitHold.current = settledSplit;
      }
      if (mode === 'CHEQUE' && (!cheque.chequeNumber.trim() || !cheque.chequeBankName.trim())) {
        setError(t('billing.chequeNumber'));
        return;
      }
      if (mode === 'UPI' && !navigator.onLine) {
        setError(t('pos.upiNeedsConnection'));
        return;
      }

      const cust =
        selectedCustomer.data?.id === Number(effectiveCustomerId)
          ? selectedCustomer.data
          : activeCustomers.find((c) => c.id === Number(effectiveCustomerId)) || walkInCustomer;
      const blankPos =
        taxEnabled &&
        !String(cust?.state || '').trim() &&
        !String((cust as { gstin?: string } | undefined)?.gstin || '').trim();
      const assumedWalkIn =
        Boolean(company.data?.assumeLocalStateForBlankParty) &&
        Boolean(walkInCustomer) &&
        Number(effectiveCustomerId) === walkInCustomer?.id;
      if (blankPos && !opts?.confirmBlankPos && !assumedWalkIn) {
        setBlankPosMode(mode);
        checkoutGuard.current = false;
        setBusy(false);
        return;
      }

      const lines = draftLinesFromCart(cart, taxEnabled, (id, qty) =>
        unitPriceFor(id, qty, cart.find((l) => l.product.id === id)?.product.sellingPrice),
      );

      if (!navigator.onLine && (opts?.splitPayments || !offlineTenderAllowed(mode, {
        offlineCredit: Boolean(posSettings.data?.offlineCredit),
        namedCustomer: Boolean(effectiveCustomerId) && Number(effectiveCustomerId) !== walkInCustomer?.id,
      }))) {
        setError(t('pos.offlineCashOnly', { mode: opts?.splitPayments ? 'UPI' : mode }));
        return;
      }

      if (!navigator.onLine && mode === 'CREDIT') {
        const named = Boolean(effectiveCustomerId) && Number(effectiveCustomerId) !== walkInCustomer?.id;
        const cacheRaw = companyId ? localStorage.getItem(`bb_pos_credit_cached:${companyId}:${effectiveCustomerId}`) : null;
        const outageKey = posOutageId();
        const priorRaw = companyId ? localStorage.getItem(`bb_pos_offline_credit:${companyId}:${posTerminalId()}:${outageKey}:${effectiveCustomerId}`) : null;
        let prior: { total?: number; count?: number } = {};
        try {
          prior = priorRaw ? JSON.parse(priorRaw) as { total?: number; count?: number } : {};
        } catch {
          prior = {};
        }
        const billTotal = lines.reduce((sum, line) => sum + Number(line.unitPrice) * Number(line.quantity), 0);
        const blocked = offlineCreditBlock({
          enabled: Boolean(posSettings.data?.offlineCredit),
          named,
          stopCredit: selectedCustomer.data?.status === 'BLOCKED',
          billTotal,
          priorTotal: Number(prior.total || 0),
          priorCount: Number(prior.count || 0),
          cacheAgeMs: cacheRaw ? Date.now() - Date.parse(cacheRaw) : null,
        });
        if (blocked) {
          setError(blocked);
          return;
        }
      }

      if (!navigator.onLine && companyId) {
        const listId = Number((selectedCustomer.data as { priceList?: number } | undefined)?.priceList || 0);
        if (priceListMissing(companyId, listId || null)) {
          setError(t('pos.priceListMissing'));
          return;
        }
      }

      if (!navigator.onLine) {
        const pendingName =
          !effectiveCustomerId
            ? typedName || t('pos.walkInCustomer')
            : undefined;
        try {
          await enqueueDraft(companyId, userId, {
            kind: 'pos',
            payload: {
              customer: Number(effectiveCustomerId) || 0,
              items: lines,
              paymentMode: mode,
              offlineCredit: mode === 'CREDIT',
              shiftId: tillShift?.id,
              terminalId: posTerminalId(),
              outageId: posOutageId(),
              creditCachedAt: companyId ? localStorage.getItem(`bb_pos_credit_cached:${companyId}:${effectiveCustomerId}`) : undefined,
              pendingCustomerName: pendingName,
              warehouse: warehouseId ? Number(warehouseId) : undefined,
            },
            idempotencyKey: key,
            customerId: Number(effectiveCustomerId) || undefined,
            pendingCustomerName: pendingName,
            paymentMode: mode,
            lines,
          });
          trackShopFloor('offline_enqueue');
          if (mode === 'CREDIT' && companyId && effectiveCustomerId) {
            const billTotal = lines.reduce((sum, line) => sum + Number(line.unitPrice) * Number(line.quantity), 0);
            const storeKey = `bb_pos_offline_credit:${companyId}:${posTerminalId()}:${posOutageId()}:${effectiveCustomerId}`;
            let priorTotals = { total: 0, count: 0 };
            try {
              priorTotals = JSON.parse(localStorage.getItem(storeKey) || '') as { total: number; count: number };
            } catch {
              priorTotals = { total: 0, count: 0 };
            }
            localStorage.setItem(storeKey, JSON.stringify({
              total: Number(priorTotals.total || 0) + billTotal,
              count: Number(priorTotals.count || 0) + 1,
            }));
          }
          setIdempotencyKey(null);
          setCart([]);
          setCashTendered('');
          setWalkInName('');
          setCustomerId('');
          setMessage(t('pos.savedOffline', { id: key.slice(0, 8) }));
          setError(null);
        } catch (err) {
          if (String((err as Error)?.message || err) === 'OUTBOX_STORAGE_FULL') {
            setError(t('pos.storageFull'));
            return;
          }
          throw err;
        }
        return;
      }

      if (!effectiveCustomerId) {
        setError(t('pos.selectCustomer'));
        return;
      }

      if (mode === 'UPI') {
        await startUpiCheckout(lines, Number(effectiveCustomerId), key, Boolean(opts?.confirmBlankPos));
        return;
      }
      await performCashCheckout(
        lines,
        Number(effectiveCustomerId),
        key,
        Boolean(opts?.confirmBlankPos),
        {
          confirmTotalsMismatch: Boolean(opts?.confirmTotalsMismatch),
          shortCollectAmount: opts?.shortCollectAmount,
          payments: settledSplit,
          expectedTotal: tenderGateTotal,
          paymentMode: mode,
          cheque,
        },
      );
      } catch (err) {
        // handleCheckoutError (invoked inside performCashCheckout /
        // confirmUpiPayment) already routed a credit_limit_exceeded failure
        // to the dedicated banner above — don't also surface it as a
        // generic error toast (double-error-surface regression).
        if (
          getErrorCode(err) !== 'credit_limit_exceeded' &&
          getErrorCode(err) !== 'pos_totals_mismatch'
        ) {
          const msg = getErrorMessage(err);
          setError(msg);
          if (isSerialOrBatchRuleError(msg)) {
            setSerialBatchError({ mode, message: msg });
          }
        }
      } finally {
        setBusy(false);
        checkoutGuard.current = false;
      }
    },
    [
      activeCustomers,
      additionalCharges,
      busy,
      cart,
      cashPending,
      cashTendered,
      cheque,
      company.data,
      companyId,
      customerId,
      gateTotal,
      idempotencyKey,
      invoiceDiscount,
      isFlushing,
      performCashCheckout,
      posInvoiceType,
      posMissingBatch,
      posMissingSerial,
      posStockBlocked,
      selectedCustomer.data,
      startUpiCheckout,
      taxEnabled,
      tillShift,
      tenderedAmount,
      totals.grandTotal,
      unitPriceFor,
      upiPending,
      userId,
      ownerPin,
      posSettings.data,
      walkInCustomer,
      walkInName,
      warehouseId,
      writesBlocked,
    ],
  );

  const cashPayDisabled =
    writesBlocked ||
    busy ||
    isFlushing ||
    Boolean(upiPending) ||
    cashNeedsOpenShift(Boolean(posSettings.data?.requireOpenShift), tillShift?.status) ||
    (cart.length === 0 && !cashPending) ||
    (cart.length > 0 && (posStockBlocked || posMissingBatch || posMissingSerial));
  const upiPayDisabled =
    writesBlocked ||
    busy ||
    isFlushing ||
    tenderPreviewFailed ||
    Boolean(cashPending) ||
    (cart.length === 0 && !upiPending) ||
    (cart.length > 0 && (posStockBlocked || posMissingBatch || posMissingSerial));
  const cashPayReason = posPayDisabledReason({
    mode: 'CASH',
    writesBlocked,
    busy: busy || isFlushing,
    upiPending: Boolean(upiPending),
    stockBlocked: posStockBlocked,
    missingBatch: posMissingBatch,
    missingSerial: posMissingSerial,
  });
  const upiPayReason = posPayDisabledReason({
    mode: 'UPI',
    writesBlocked,
    busy: busy || isFlushing,
    cashPending: Boolean(cashPending),
    tenderPreviewFailed,
    stockBlocked: posStockBlocked,
    missingBatch: posMissingBatch,
    missingSerial: posMissingSerial,
  });

  // F1-F10 Keyboard-First POS Turbo Engine
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Never steal keys while a confirmation dialog is open
      if (document.querySelector('[role="dialog"]')) return;
      // A held key must not re-fire a payment or clear the cart.
      if (e.repeat) return;

      const el = document.activeElement as HTMLElement | null;
      const inBatch = el?.getAttribute('data-pos-batch') === '1';

      if (e.key === 'F2') {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
        return;
      }
      if (inBatch) return;

      if (e.key === 'F1') {
        e.preventDefault();
        if (!cashPayDisabled && (cart.length > 0 || cashPending)) {
          rememberMethod('CASH');
          void checkout('CASH');
        }
        return;
      }
      if (e.key === 'F3') {
        e.preventDefault();
        customerSelectRef.current?.focus();
        return;
      }
      if (e.key === 'F4') {
        e.preventDefault();
        if (!cashPayDisabled && cart.length > 0) {
          rememberMethod('CARD');
          void checkout('CARD');
        }
        return;
      }
      if (e.key === 'F6') {
        e.preventDefault();
        if (!upiPayDisabled && cart.length > 0) {
          rememberMethod('UPI');
          void checkout('UPI');
        }
        return;
      }
      if (e.key === 'F7') {
        e.preventDefault();
        if (!cashPayDisabled && cart.length > 0) {
          rememberMethod('CREDIT');
          void checkout('CREDIT');
        }
        return;
      }
      if (e.key === 'F8') {
        e.preventDefault();
        holdAndCreateSession();
        return;
      }
      if (e.key === 'F9') {
        e.preventDefault();
        const next = heldCarts[0];
        if (next) recallHold(next);
        return;
      }
      if (e.key === 'F10') {
        e.preventDefault();
        if (cart.length > 0) {
          setConfirmClearCartOpen(true);
        }
        return;
      }
      if (e.key === 'F11' || (e.ctrlKey && e.altKey && e.key.toLowerCase() === 'p')) {
        if (!lastCompletedSaleRef.current) return;
        e.preventDefault();
        void printPosThermalOrWarn(lastCompletedSaleRef.current);
        return;
      }

      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      if (e.key === 'b' || e.key === 'B') {
        e.preventDefault();
        holdAndCreateSession();
        return;
      }
      const n = Number(e.key);
      if (n >= 1 && n <= 9) {
        const id = sessionIds[n - 1];
        if (id) {
          e.preventDefault();
          switchSession(id);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [
    activeSessionId,
    cart.length,
    cashPayDisabled,
    cashPending,
    checkout,
    clearCart,
    heldCarts,
    holdAndCreateSession,
    recallHold,
    rememberMethod,
    sessionIds,
    switchSession,
    upiPayDisabled,
  ]);

  if (!posEnabled()) {
    return (
      <PageShell title={t('pos.title')}>
        <Typography>{t('pos.disabled')}</Typography>
      </PageShell>
    );
  }

  if (company.isLoading || walkInLookup.isLoading) return <LoadingState />;

  const upiIntent =
    upiPending?.upiQr?.intentUrl && isAllowedPaymentUrl(String(upiPending.upiQr.intentUrl))
      ? String(upiPending.upiQr.intentUrl)
      : '';
  const upiPng = upiPending?.upiQr?.qrPngBase64 || upiPending?.upiQr?.qr_png_base64;
  const openWarehouses = (warehouses.data ?? []).filter((row) => row.isActive !== false);
  const periodClosed = Boolean(posSettings.data?.periodBlocked);
  const serverBills = (recentServer.data?.results ?? []).map((inv) => ({
    id: inv.id,
    number: String(inv.number ?? `#${inv.id}`),
  }));
  const reprintBills = [...recentBills, ...serverBills]
    .filter((bill, index, all) => all.findIndex((row) => row.id === bill.id) === index)
    .slice(0, 5);
  const hsnGap = Boolean(selectedCustomer.data?.gstin && company.data?.einvoiceEnabled)
    && cart.some((line) => !String(line.product.hsnCode || '').trim());
  const creditCeiling = toNumber(selectedCustomer.data?.creditLimit);
  const creditLeft = creditCeiling > 0
    ? creditCeiling - toNumber(selectedCustomer.data?.outstanding)
    : null;
  const expiredOnCart = cart.some((line) => {
    const expiry = expiryForChosenBatch(
      availablePosBatches(stockBalances.data ?? [], line.product.id, warehouseId),
      line.batchNo ?? '',
    );
    return Boolean(expiry && expiry < todayIso());
  });
  const expiredBlocksPay = expiredOnCart && (
    posSettings.data?.expiredLotPolicy === 'BLOCK' || !expiredReason.trim()
  );
  const needsBank = (mode: string) => mode === 'UPI' || mode === 'CARD' || mode === 'BANK' || mode === 'CHEQUE';
  const bankMissing = (mode: string) => Boolean(
    posSettings.data && needsBank(mode) && !posSettings.data.tenderAccounts?.[mode],
  );

  return (
    <PageShell title={t('pos.title')} subtitle={t('pos.subtitle')}>
      <UnsavedChangesGuard
        when={cart.length > 0}
        title={t('pos.leaveTitle')}
        body={t('pos.leaveBody')}
        leaveLabel={t('pos.discardBill')}
        onLeave={() => {
          // Discard the bill on screen only. The other bills opened in this counter session keep
          // their items; wiping the whole store lost every held bill on one "Discard".
          setCart([]);
          const rest = Object.fromEntries(
            Object.entries(sessionStore.current).filter(([id]) => id !== activeSessionId),
          );
          sessionStore.current = rest;
          if (!companyId || !userId) return;
          const keep = Object.keys(rest).filter((id) => (rest[id].cart ?? []).length > 0);
          if (keep.length === 0) {
            removeDeviceDraft(companyId, userId, 'pos-sessions');
          } else {
            const kept = Object.fromEntries(keep.map((id) => [id, rest[id]]));
            writeDraft(companyId, userId, 'pos-sessions', { sessions: kept, activeSessionId: keep[0], sessionIds: keep });
          }
        }}
      />
      {offline ? <HonestyBanner messageKey="honesty.posCounter" /> : null}
      {draftWriteFailed ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {t('pos.draftSaveDisabled')}
        </Alert>
      ) : null}
      <Typography variant="body2" color="text.secondary">
        {t('billing.threeStarts')}
      </Typography>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
        {sessionIds.length > 1 ? (
          <Tabs
            value={activeSessionId}
            onChange={(_, id) => switchSession(String(id))}
            variant="scrollable"
            scrollButtons="auto"
          >
            {sessionIds.map((id, idx) => (
              <Tab key={id} value={id} label={t('pos.billN', { n: idx + 1 })} />
            ))}
          </Tabs>
        ) : null}
        <Button size="small" variant="outlined" endIcon={<HotkeyBadge text="F8" />} onClick={holdAndCreateSession} disabled={cart.length === 0}>
          {t('pos.holdBill')}
        </Button>
      </Stack>
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
      {companyId && (catalogAgeHours(companyId) ?? 0) >= (posSettings.data?.catalogWarnHours ?? 24) && catalogAgeHours(companyId) != null ? (
        <Alert severity={catalogSellBlocked(catalogAgeHours(companyId), posSettings.data?.catalogBlockHours ?? 72) ? 'error' : 'warning'} sx={{ mb: 1 }}>
          {t('pos.catalogueStale', { hours: String(Math.floor(catalogAgeHours(companyId) ?? 0)) })}
        </Alert>
      ) : null}
      {message ? (
        <Alert
          severity="success"
          onClose={() => {
            setMessage(null);
            setWaOffer(null);
          }}
          sx={{ mb: 1 }}
          action={
            waOffer ? (
              <Button
                color="inherit"
                size="small"
                disabled={sendWaMutation.isPending}
                onClick={() => sendWaMutation.mutate(waOffer)}
              >
                {t('pos.sendWhatsAppBill')}
              </Button>
            ) : undefined
          }
        >
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} onClose={() => setError(null)} sx={{ mb: 1 }} />
      ) : null}
      {creditLimitBanner ? (
        <Alert
          severity="error"
          variant="filled"
          onClose={() => setCreditLimitBanner(null)}
          sx={{ mb: 1 }}
        >
          <AlertTitle>{t('pos.creditLimitTitle')}</AlertTitle>
          {creditLimitBanner.customerName
            ? t('pos.creditLimitBody', { customer: creditLimitBanner.customerName })
            : t('pos.creditLimitBodyGeneric')}
          {creditLimitBanner.creditLimit &&
          creditLimitBanner.currentExposure &&
          creditLimitBanner.invoiceTotal ? (
            <Typography variant="body2" sx={{ mt: 0.5, opacity: 0.9 }}>
              {t('pos.creditLimitNumbers', {
                limit: creditLimitBanner.creditLimit,
                exposure: creditLimitBanner.currentExposure,
                total: creditLimitBanner.invoiceTotal,
              })}
            </Typography>
          ) : null}
        </Alert>
      ) : null}
      {thermalWarn ? (
        <Alert
          severity="warning"
          onClose={() => setThermalWarn(null)}
          sx={{ mb: 1 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={async () => {
                const warn = await printPosThermalOrWarn({
                  id: thermalWarn.invoiceId,
                  number: thermalWarn.number,
                });
                if (!warn) {
                  setThermalWarn(null);
                }
              }}
            >
              {t('sweep2.retryPrint')}
            </Button>
          }
        >
          Thermal receipt print failed for invoice {thermalWarn.number}.
        </Alert>
      ) : null}
      {(() => {
        const chip = posChipState({
          cartCount: cart.length,
          hasOutbox: hasOutboxItems,
          offline,
          justCompleted: saleJustCompleted,
        });
        if (!chip) return null;
        const labels = {
          unsaved: t('pos.chipUnsaved'),
          offline: t('pos.chipOffline'),
          saved: t('pos.chipSaved'),
          completed: t('pos.chipCompleted'),
        };
        const colors = {
          unsaved: 'warning',
          offline: 'warning',
          saved: 'info',
          completed: 'success',
        } as const;
        return (
          <Chip
            size="small"
            color={colors[chip]}
            label={labels[chip]}
            sx={{ mb: 1 }}
            data-testid="pos-status-chip"
          />
        );
      })()}
      {unpaidRecover ? (
        <Alert
          severity="info"
          sx={{ mb: 1 }}
          action={
            <Button
              color="inherit"
              size="small"
              disabled={busy || bankMissing('UPI')}
              onClick={() => {
                setBusy(true);
                void (async () => {
                  const invoice = await getSalesInvoice(unpaidRecover.id);
                  const amount = toNumber(invoice.balance);
                  await collectPosPayment({
                    invoice: invoice.id,
                    mode: 'UPI',
                    amount,
                    reference: paymentRef || undefined,
                    notes: `POS collect ${invoice.number ?? invoice.id}`,
                  });
                  setUnpaidRecover(null);
                  setMessage(t('pos.collectUpi'));
                })().catch((err) => setError(getErrorMessage(err))).finally(() => setBusy(false));
              }}
            >
              {t('pos.collectUpi')}
            </Button>
          }
          onClose={() => setUnpaidRecover(null)}
        >
          {t('pos.leftUnpaid', { number: unpaidRecover.number })}
        </Alert>
      ) : null}
      <PosTillStrip
        onClosed={() => {
          if (walkInCustomer?.id) setCustomerId(walkInCustomer.id);
          setNameOnlySale(false);
          setWalkInName('');
        }}
      />
      {openWarehouses.length === 0 ? (
        <Alert severity="info" sx={{ mb: 1 }} action={<Button component={RouterLink} to="/inventory/warehouses">{t('pos.setupGodown')}</Button>}>
          {t('pos.noWarehouse')}
        </Alert>
      ) : null}
      {catalogProbe.data?.count === 0 ? (
        <Alert severity="info" sx={{ mb: 1 }} action={<Button component={RouterLink} to="/inventory/products">{t('pos.setupItems')}</Button>}>
          {t('pos.catalogEmpty')}
        </Alert>
      ) : null}
      {periodClosed ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {posSettings.data?.periodMessage || t('pos.periodClosed')}
        </Alert>
      ) : null}
      {!walkInCustomer ? (
        <Alert severity="info" sx={{ mb: 1 }} action={<Button component={RouterLink} to="/sales/customers">{t('pos.setupWalkIn')}</Button>}>
          {t('pos.noWalkIn')}
        </Alert>
      ) : null}
      {hsnGap ? (
        <Alert severity="warning" sx={{ mb: 1 }} action={<Button component={RouterLink} to="/inventory/products">{t('pos.setupItems')}</Button>}>
          {t('pos.hsnMissing')}
        </Alert>
      ) : null}
      {heldCarts.length > 0 ? (
      <Stack direction="row" spacing={1} sx={{ mb: 1 }} flexWrap="wrap">
        {heldCarts.map((row) => (
          <Button
            key={row.id}
            size="small"
            onClick={() => recallHold(row)}
          >
            {t('pos.recallCart')} {row.cart.length}
          </Button>
        ))}
      </Stack>
      ) : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ maxWidth: '100%', minWidth: 0 }}>
        <Paper variant="outlined" sx={{ flex: 1, p: { xs: 1.5, sm: 2 }, maxWidth: '100%', minWidth: 0, overflow: 'hidden' }}>
          <Stack spacing={2}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
              <Button size="small" onClick={() => setShowFilters((open) => !open)}>{t('pos.showFilters')}</Button>
              <Collapse in={showFilters} sx={{ width: '100%' }}>
                <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
              </Collapse>
              <Autocomplete<Product>
                sx={{ flex: 1, minWidth: 220 }}
                options={(products.data ?? []).filter((p) => p.status === 'ACTIVE')}
                loading={products.isFetching}
                inputValue={productQuery}
                open={scanListOpen && productQuery.trim().length > 0}
                onOpen={() => setScanListOpen(true)}
                onClose={() => setScanListOpen(false)}
                onHighlightChange={(_, option) => {
                  highlightedRef.current = option;
                }}
                onInputChange={(_, v, reason) => {
                  if (reason === 'input' || reason === 'clear') setProductQuery(v);
                }}
                onChange={(_, v) => {
                  if (v) addProduct(v);
                }}
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
                    inputProps={{
                      ...params.inputProps,
                      'aria-label': t('pos.scanOrSearch'),
                      'aria-keyshortcuts': 'F2',
                    }}
                    onKeyDown={(e) => {
                      const scanned = noteScanKey(e.key);
                      if (e.key !== 'Enter') return;
                      if (scanned?.burst && scanned.raw) {
                        e.preventDefault();
                        e.stopPropagation();
                        void tryAddByBarcode(scanned.raw);
                        return;
                      }
                      e.preventDefault();
                      e.stopPropagation();
                      const catalog = (products.data ?? []).filter((p) => p.status === 'ACTIVE');
                      const choice = choosePosEnter({
                        query: productQuery,
                        highlighted: highlightedRef.current,
                        listOpen: scanListOpen,
                        catalog,
                        optionsStale: productQuery.trim() !== debouncedQuery.trim(),
                      });
                      if (choice.action === 'wait') {
                        window.setTimeout(() => {
                          void tryAddByBarcode();
                        }, 260);
                        return;
                      }
                      if (choice.action === 'add') {
                        const product =
                          catalog.find((p) => p.id === choice.productId) ??
                          (highlightedRef.current?.id === choice.productId ? highlightedRef.current : null);
                        if (product) addProduct(product);
                        return;
                      }
                      void tryAddByBarcode();
                    }}
                  />
                )}
              />
              <IconButton
                aria-label={t('a11y.focusScanner')}
                onClick={() => {
                  void (async () => {
                    const code = await scanBarcode();
                    if (code) {
                      setProductQuery(code);
                      await tryAddByBarcode(code);
                      return;
                    }
                    searchRef.current?.focus();
                  })();
                }}
              >
                <QrCodeScannerIcon />
              </IconButton>
            </Box>
            {debouncedQuery.trim() && products.data && products.data.filter((p) => p.status === 'ACTIVE').length === 0 ? (
              <Alert
                severity="info"
                action={<Button component={RouterLink} to="/inventory/products">{t('pos.setupItems')}</Button>}
              >
                {t('pos.noProducts')}
              </Alert>
            ) : null}
            {scaleReady || isNative() ? (
              <Stack direction="row" spacing={1}>
                {scaleReady ? (
                  <Button
                    size="small"
                    onClick={() => {
                      void readScaleWeight().then((weight) => {
                        if (weight == null || weight <= 0) return;
                        setCart((prev) => {
                          if (!prev.length) return prev;
                          const last = prev[prev.length - 1];
                          return prev.map((row, index) => index === prev.length - 1 ? { ...row, quantity: weight, key: last.key } : row);
                        });
                      });
                    }}
                  >
                    {t('cog.readScale')}
                  </Button>
                ) : null}
                {isNative() ? (
                  <Button
                    size="small"
                    onClick={() => setDrawerAsk(true)}
                  >
                    {t('cog.openDrawer')}
                  </Button>
                ) : null}
              </Stack>
            ) : null}

            <Stack component="fieldset" spacing={1} sx={{ border: 0, p: 0, m: 0 }}>
              <Typography component="legend" variant="caption">{t('pos.prescription')}</Typography>
              <TextField size="small" label={t('pos.prescription')} value={pharmacyPatient} onChange={(event) => setPharmacyPatient(event.target.value)} placeholder="Patient" />
              <TextField size="small" value={pharmacyPrescriber} onChange={(event) => setPharmacyPrescriber(event.target.value)} placeholder="Prescriber" />
              <TextField size="small" value={pharmacyRegistration} onChange={(event) => setPharmacyRegistration(event.target.value)} placeholder="Registration" />
              <TextField size="small" value={pharmacyNote} onChange={(event) => setPharmacyNote(event.target.value)} placeholder="Prescription number" />
              <input
                type="file"
                accept="image/*,.pdf"
                aria-label={t('pos.prescription')}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  void uploadFile(file).then((asset) => setPrescriptionFileId(asset.id)).catch((err) => setError(getErrorMessage(err)));
                }}
              />
              <TextField size="small" label="Salesperson" value={salespersonId} onChange={(event) => setSalespersonId(event.target.value)} />
            </Stack>

            <TableContainer sx={{ maxWidth: '100%', overflowX: 'auto' }}>
              <Table size="small" aria-label={t('pos.cart')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('pos.item')}</TableCell>
                  <TableCell>{t('pos.itemCode')}</TableCell>
                  <TableCell>{t('billing.hsn')}</TableCell>
                  <TableCell align="right">{t('billing.mrp')}</TableCell>
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
                    <TableCell colSpan={9}>
                      <Typography variant="body2" color="text.secondary">
                        {t('pos.addItemsHint')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  cart.map((line) => {
                    const unitPrice = posLineUnitPrice(
                      line.product,
                      line.quantity,
                      line.unitName,
                      unitPriceFor,
                      line.priceAlreadyConverted,
                    );
                    const listHit = resolveListUnitPrice(
                      priceLists.data,
                      selectedCustomer.data?.priceList,
                      line.product.id,
                      line.quantity,
                    );
                    const tax = calculateLineTax({
                      quantity: line.quantity,
                      unitPrice,
                      gstRate: taxEnabled ? toNumber(line.product.gstRate) : 0,
                      discountPercent: line.discountPercent || 0,
                      intraState,
                    });
                    return (
                      <TableRow key={line.key}>
                        <TableCell>
                          <Typography variant="body2">{line.product.name}</Typography>
                          {line.syncError ? (
                            <Typography variant="caption" color="error" display="block" role="alert">
                              {line.syncError}
                            </Typography>
                          ) : null}
                          {(() => {
                            const onHand = availableByProduct.get(line.product.id) ?? 0;
                            const blocked =
                              company.data?.negativeStockPolicy === 'BLOCK' && line.quantity > onHand + 1e-9;
                            return (
                              <>
                                {blocked ? (
                                  <Typography variant="caption" color="error" display="block">
                                    {t('pos.warehouseQtyBlock', { n: onHand })}
                                  </Typography>
                                ) : null}
                              </>
                            );
                          })()}
                          {listHit?.listName ? (
                            <Chip size="small" label={`List: ${listHit.listName}`} sx={{ ml: 0.5, height: 20 }} />
                          ) : null}
                          {line.product.trackSerial ? (
                            <TextField
                              size="small"
                              value={(line.serialNumbers ?? []).join(', ')}
                              onChange={(e) => {
                                const serialNumbers = parseSerialNumbersText(e.target.value);
                                setCart((prev) =>
                                  prev.map((row) =>
                                    row.key === line.key
                                      ? {
                                          ...row,
                                          serialNumbers,
                                          quantity: serialNumbers.length || row.quantity,
                                        }
                                      : row,
                                  ),
                                );
                              }}
                              placeholder={t('pos.serials')}
                              sx={{ mt: 0.5 }}
                            />
                          ) : null}
                          {line.product.trackBatch ? (
                            <>
                            {(() => {
                              const choices = availablePosBatches(
                                stockBalances.data ?? [],
                                line.product.id,
                                warehouseId,
                              );
                              const current = String(line.batchNo ?? '').trim();
                              const match = choices.find(
                                (lot) => lot.batchNo.toLowerCase() === current.toLowerCase(),
                              );
                              const selectValue = match?.batchNo ?? '';
                              const qtyLabel = (qty: number) =>
                                Number.isInteger(qty) ? String(qty) : String(Math.round(qty * 1000) / 1000);
                              return (
                                <TextField
                                  select
                                  size="small"
                                  required
                                  error={!selectValue}
                                  value={selectValue}
                                  disabled={stockBalances.isLoading || choices.length === 0}
                                  onChange={(e) =>
                                    setCart((prev) =>
                                      prev.map((row) =>
                                        row.key === line.key ? { ...row, batchNo: e.target.value } : row,
                                      ),
                                    )
                                  }
                                  helperText={choices.length === 0 && !stockBalances.isLoading ? t('pos.batchNone') : undefined}
                                  SelectProps={{
                                    displayEmpty: true,
                                    SelectDisplayProps: Object.assign({} as HTMLAttributes<HTMLDivElement>, {
                                      'data-pos-batch': '1',
                                    }),
                                  }}
                                  sx={{ mt: 0.5, minWidth: 200 }}
                                >
                                  <MenuItem value="" disabled>
                                    {t('pos.batchSelect')}
                                  </MenuItem>
                                  {choices.map((lot) => (
                                    <MenuItem key={lot.batchNo} value={lot.batchNo}>
                                      {lot.expiryDate
                                        ? t('pos.batchOptionExpiry', {
                                            batch: lot.batchNo,
                                            date: lot.expiryDate,
                                            qty: qtyLabel(lot.available),
                                          })
                                        : t('pos.batchOption', {
                                            batch: lot.batchNo,
                                            qty: qtyLabel(lot.available),
                                          })}
                                    </MenuItem>
                                  ))}
                                </TextField>
                              );
                            })()}
                            {(() => {
                              const expiry = expiryForChosenBatch(
                                (batchLots.data ?? []).filter((lot) => lot.product === line.product.id),
                                line.batchNo ?? '',
                              );
                              return expiry ? (
                                <Typography variant="caption" display="block" color="text.secondary">
                                  {t('pos.expiryTag', { date: expiry })}
                                </Typography>
                              ) : null;
                            })()}
                            </>
                          ) : null}
                        </TableCell>
                        <TableCell>{line.product.sku || '—'}</TableCell>
                        <TableCell>{line.product.hsnCode || '—'}</TableCell>
                        <TableCell align="right">{formatMoney(line.product.mrp ?? 0)}</TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
                            <IconButton
                              size="small"
                              onClick={() => updateQty(line.key, line.quantity - 1)}
                              aria-label={t('quickEntry.decrease')}
                              sx={{ minWidth: { xs: 48, sm: 40 }, minHeight: { xs: 48, sm: 40 } }}
                            >
                              <RemoveIcon fontSize="small" />
                            </IconButton>
                            <NumericField
                              value={line.quantity}
                              onValueChange={(n) => updateQty(line.key, n)}
                              min={1}
                              emptyAs={1}
                              fullWidth={false}
                              inputProps={{ 'aria-label': t('pos.qty'), 'data-pos-qty': '1' }}
                              onKeyDown={(e) => {
                                if (e.key === 'Escape') {
                                  e.preventDefault();
                                  searchRef.current?.focus();
                                  return;
                                }
                                const scanned = noteScanKey(e.key);
                                if (scanned?.burst && scanned.raw) {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  void tryAddByBarcode(scanned.raw);
                                }
                              }}
                              sx={{ width: 56 }}
                            />
                            <IconButton
                              size="small"
                              onClick={() => updateQty(line.key, line.quantity + 1)}
                              aria-label={t('quickEntry.increase')}
                              sx={{ minWidth: { xs: 48, sm: 40 }, minHeight: { xs: 48, sm: 40 } }}
                            >
                              <AddIcon fontSize="small" />
                            </IconButton>
                            {line.product.alternateUnitName ? (
                              <TextField
                                select
                                size="small"
                                value={line.unitName}
                                onChange={(e) =>
                                  setCart((prev) =>
                                    prev.map((row) =>
                                      row.key === line.key ? { ...row, unitName: e.target.value } : row,
                                    ),
                                  )
                                }
                                sx={{ width: 110 }}
                              >
                                {[line.product.unitName || 'PCS', line.product.alternateUnitName]
                                  .filter((unit, index, all) => Boolean(unit) && all.indexOf(unit) === index)
                                  .map((unit) => (
                                    <MenuItem key={unit} value={unit}>
                                      {formatUnitLabel(unit)}
                                    </MenuItem>
                                  ))}
                              </TextField>
                            ) : (
                              <Typography variant="caption" color="text.secondary">
                                {formatUnitLabel(line.unitName || line.product.unitName || 'PCS')}
                              </Typography>
                            )}
                          </Stack>
                        </TableCell>
                        <TableCell align="right">
                          <NumericField
                            value={line.discountPercent}
                            onValueChange={(n) => updateDiscount(line.key, n)}
                            min={0}
                            emptyAs={0}
                            fullWidth={false}
                            inputProps={{ 'aria-label': t('pos.lineDiscount') }}
                            sx={{ width: 64 }}
                          />
                        </TableCell>
                        <TableCell align="right">
                          <NumericField
                            value={line.priceOverride ?? unitPrice}
                            onValueChange={(n) => {
                              const list = posLineUnitPrice(line.product, line.quantity, line.unitName, unitPriceFor, line.priceAlreadyConverted);
                              if (Math.abs(n - list) < 0.001) {
                                setCart((prev) => prev.map((row) => row.key === line.key ? { ...row, priceOverride: undefined } : row));
                                return;
                              }
                              setPricePrompt({ key: line.key, price: n, reason: '' });
                            }}
                            min={0}
                            emptyAs={unitPrice}
                            fullWidth={false}
                            inputProps={{ 'aria-label': t('pos.price') }}
                            sx={{ width: 88 }}
                          />
                        </TableCell>
                        <TableCell align="right">{formatMoney(tax.lineTotal)}</TableCell>
                        <TableCell>
                          <IconButton size="small" onClick={() => updateQty(line.key, 0)} aria-label={t('common.remove')} sx={{ minWidth: { xs: 48, sm: 40 }, minHeight: { xs: 48, sm: 40 } }}>
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
            </TableContainer>
            <Autocomplete
              options={[...(walkInCustomer ? [walkInCustomer] : []), ...activeCustomers]}
              getOptionLabel={(option) => option.id === walkInCustomer?.id
                ? t('pos.walkInNamed', { name: option.name })
                : option.name}
              filterOptions={(options) => options}
              inputValue={customerQuery}
              onInputChange={(_, value, reason) => {
                if (reason === 'input' || reason === 'clear') setCustomerQuery(value);
              }}
              value={
                selectedCustomer.data?.id === customerId
                  ? selectedCustomer.data
                  : walkInCustomer?.id === customerId
                    ? walkInCustomer
                    : null
              }
              isOptionEqualToValue={(option, value) => option.id === value.id}
              onChange={(_, option) => {
                setCustomerId(option?.id ?? '');
                setCustomerQuery('');
                if (option) {
                  setWalkInName('');
                  setNameOnlySale(false);
                }
              }}
              renderOption={(props, option) => (
                <li {...props} key={option.id}>
                  <Box>
                    <Typography variant="body2">
                      {option.id === walkInCustomer?.id ? t('pos.walkInNamed', { name: option.name }) : option.name}
                    </Typography>
                    {option.phone && option.id !== walkInCustomer?.id ? (
                      <Typography variant="caption" color="text.secondary">{option.phone}</Typography>
                    ) : null}
                  </Box>
                </li>
              )}
              renderInput={(params) => (
                <TextField
                  {...params}
                  inputRef={customerSelectRef}
                  label={t('pos.customer')}
                  size="small"
                  placeholder={t('pos.selectCustomerPlaceholder')}
                />
              )}
            />
            {creditLeft != null ? (
              <Typography variant="caption" color={creditLeft < gateTotal ? 'warning.main' : 'text.secondary'}>
                {t('pos.creditLeft', { amount: formatMoney(creditLeft) })}
              </Typography>
            ) : null}
            {nameOnlySale ? (
              <TextField
                size="small"
                label={t('pos.orTypeCustomerName')}
                value={walkInName}
                onChange={(e) => setWalkInName(e.target.value)}
                placeholder={t('pos.cashWalkInPlaceholder')}
                helperText={t('pos.typedNameHint')}
                fullWidth
              />
            ) : (
              <Button
                size="small"
                onClick={() => {
                  setNameOnlySale(true);
                  setCustomerId('');
                }}
              >
                {t('pos.nameOnlySale')}
              </Button>
            )}
            {openWarehouses.length > 1 ? (
            <TextField
              select
              size="small"
              label={t('pos.godown')}
              value={warehouseId === '' ? '' : warehouseId}
              onChange={(e) => setWarehouseId(e.target.value === '' ? '' : Number(e.target.value))}
              fullWidth
            >
              {openWarehouses.map((row) => (
                  <MenuItem key={row.id} value={row.id}>
                    {row.name}{row.isDefault ? ' (default)' : ''}
                  </MenuItem>
                ))}
            </TextField>
            ) : null}
            {serialsOpen || cart.some((line) => line.product.trackSerial) ? (
              <TextField
                size="small"
                label={t('pos.serials')}
                value={serialInput}
                onChange={(e) => setSerialInput(e.target.value)}
                placeholder={t('erp.serialNumbersHint')}
                fullWidth
              />
            ) : (
              <Button size="small" onClick={() => setSerialsOpen(true)}>
                {t('pos.serials')}
              </Button>
            )}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ width: { xs: '100%', md: 320 }, maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', p: { xs: 1.5, sm: 2 }, position: { xs: 'sticky', md: 'sticky' }, bottom: 8, zIndex: 2, bgcolor: 'background.paper', maxHeight: { xs: '70vh', md: 'none' }, overflow: 'auto' }}>
          <Stack spacing={2}>
            <Typography variant="h6">{t('pos.tender')}</Typography>
            <Divider />
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">{t('pos.subtotal')}</Typography>
              <Typography>{formatMoney(totals.subtotal)}</Typography>
            </Stack>
            {taxEnabled && (totals.cgstTotal > 0 || totals.sgstTotal > 0 || totals.igstTotal > 0) ? (
              <Stack direction="row" justifyContent="space-between">
                <Typography color="text.secondary">{t('pos.tax')}</Typography>
                <Typography>{formatMoney(totals.taxTotal || totals.cgstTotal + totals.sgstTotal + totals.igstTotal)}</Typography>
              </Stack>
            ) : null}
            {totals.roundOff ? (
              <Stack direction="row" justifyContent="space-between">
                <Typography color="text.secondary">{t('pos.roundOff')}</Typography>
                <Typography>{formatMoney(totals.roundOff)}</Typography>
              </Stack>
            ) : null}
            {taxEnabled && totals.cgstTotal <= 0 && totals.sgstTotal <= 0 && totals.igstTotal <= 0 ? (
              <Stack direction="row" justifyContent="space-between">
                <Typography color="text.secondary">{t('pos.tax')}</Typography>
                <Typography>{formatMoney(totals.taxTotal)}</Typography>
              </Stack>
            ) : null}
            {taxEnabled && intraState == null ? (
              <Typography variant="caption" color="warning.main">
                {t('pos.blankPosTaxHint')}
              </Typography>
            ) : null}
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="h6">{t('pos.total')}</Typography>
              <Typography variant="h6" aria-live="polite">
                {formatMoney(gateTotal)}
              </Typography>
            </Stack>
            <Button size="small" onClick={() => setShowAdjust((open) => !open)}>{t('pos.adjustBill')}</Button>
            <Collapse in={showAdjust}>
              <Stack spacing={1}>
            <NumericField
              label={t('pos.billDiscount')}
              value={invoiceDiscount}
              onValueChange={(n) => setInvoiceDiscount(Math.max(0, n))}
              min={0}
              emptyAs={0}
              size="small"
              fullWidth
            />
            <NumericField
              label={t('pos.addCharge')}
              value={additionalCharges}
              onValueChange={(n) => setAdditionalCharges(Math.max(0, n))}
              min={0}
              emptyAs={0}
              size="small"
              fullWidth
            />
              </Stack>
            </Collapse>
            {expiredOnCart && posSettings.data?.expiredLotPolicy !== 'BLOCK' ? (
              <TextField
                size="small"
                label={t('pos.expiredReason')}
                value={expiredReason}
                onChange={(e) => setExpiredReason(e.target.value)}
                fullWidth
                required
              />
            ) : null}
            {company.data?.requirePaymentReference ? (
              <TextField
                size="small"
                label={t('pos.paymentRef')}
                value={paymentRef}
                onChange={(e) => setPaymentRef(e.target.value)}
                fullWidth
              />
            ) : null}
            {posSettings.data?.pinConfigured ? (
              <TextField
                size="small"
                label={t('pos.ownerPin')}
                type="password"
                value={ownerPin}
                onChange={(e) => setOwnerPin(e.target.value)}
                fullWidth
                autoComplete="off"
              />
            ) : null}
            <NumericField
              label={t('pos.cashTendered')}
              value={cashTendered === '' ? gateTotal : cashTendered}
              onValueChange={(n) => setCashTendered(n)}
              min={0}
              emptyAs={gateTotal}
              size="small"
              fullWidth
            />
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              <Chip
                label={t('pos.exact')}
                size="small"
                clickable
                onClick={() => setCashTendered(gateTotal)}
                color={cashTendered === gateTotal || cashTendered === '' ? 'primary' : 'default'}
              />
              {[100, 200, 500, 2000].map((amt) => (
                <Chip
                  key={amt}
                  label={`+₹${amt}`}
                  size="small"
                  clickable
                  // F2-051: notes build up the tender (500 + 500) — additive,
                  // not absolute, so an ₹850 bill isn't dropped below total.
                  onClick={() =>
                    setCashTendered((prev) => {
                      const base = prev === '' ? 0 : toNumber(prev);
                      return base + amt;
                    })
                  }
                />
              ))}
              <Chip
                label={t('common.clear')}
                size="small"
                clickable
                variant="outlined"
                onClick={() => setCashTendered('')}
              />
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography color="text.secondary">{t('pos.change')}</Typography>
              <Typography>{formatMoney(changeDue)}</Typography>
            </Stack>
            <NumericField
              label={t('pos.splitCash')}
              value={splitCash}
              onValueChange={(n) => setSplitCash(n)}
              min={0}
              emptyAs={0}
              size="small"
              fullWidth
            />
            <Button
              variant="outlined"
              size="large"
              disabled={cashPayDisabled || offline || hsnGap || expiredBlocksPay || periodClosed || bankMissing('UPI') || !(splitCash > 0) || splitCash >= gateTotal - 0.01}
              onClick={() => {
                const cash = roundMoney(splitCash);
                const upi = roundMoney(gateTotal - cash);
                void checkout('CASH', {
                  splitPayments: [
                    { mode: 'CASH', amount: cash.toFixed(2) },
                    { mode: 'UPI', amount: upi.toFixed(2) },
                  ],
                });
              }}
            >
              {t('pos.splitPay', { cash: formatMoney(splitCash || 0), upi: formatMoney(Math.max(0, gateTotal - (splitCash || 0))) })}
            </Button>
            <Divider />
            {cashPayReason ? (
              <Alert id="pos-tender-blocker" severity="warning">
                {cashPayReason}
              </Alert>
            ) : null}
            <Tooltip title={cashPayDisabled ? cashPayReason || '' : ''}>
              <span>
            <Button
              variant={lastMethod === 'CASH' ? 'contained' : 'outlined'}
              autoFocus={lastMethod === 'CASH'}
              size="large"
              disabled={cashPayDisabled || hsnGap || expiredBlocksPay || periodClosed}
              aria-describedby={cashPayDisabled && cashPayReason ? 'pos-tender-blocker' : undefined}
              sx={{ minHeight: 48, display: lastMethod === 'CASH' || showMoreTenders ? undefined : 'none' }}
              endIcon={<HotkeyBadge text="F1" />}
              onClick={() => {
                rememberMethod('CASH');
                void checkout('CASH');
              }}
            >
              {cashPending
                ? t('pos.finishPayment', { amount: formatMoney(cashPending.amount) })
                : t('pos.cashPay', { amount: formatMoney(gateTotal) })}
            </Button>
              </span>
            </Tooltip>
            <Tooltip title={upiPayDisabled ? upiPayReason || '' : ''}>
              <span>
            <Button
              variant={lastMethod === 'UPI' ? 'contained' : 'outlined'}
              autoFocus={lastMethod === 'UPI'}
              size="large"
              disabled={upiPayDisabled || offline || hsnGap || expiredBlocksPay || periodClosed || bankMissing('UPI')}
              aria-describedby={upiPayDisabled && upiPayReason ? 'pos-tender-blocker' : undefined}
              sx={{ minHeight: 48, display: lastMethod === 'UPI' || showMoreTenders ? undefined : 'none' }}
              endIcon={<HotkeyBadge text="F6" />}
              onClick={() => {
                rememberMethod('UPI');
                void checkout('UPI');
              }}
            >
              {t('pos.upiPay', { amount: formatMoney(gateTotal) })}
            </Button>
              </span>
            </Tooltip>
            {lastMethod === 'CHEQUE' ? <ChequePaymentFields value={cheque} onChange={setCheque} /> : null}
            <Button size="small" onClick={() => setShowMoreTenders((open) => !open)}>{t('pos.moreTenders')}</Button>
            {bankMissing(lastMethod) ? (
              <Alert severity="warning">{t('pos.bankMissing', { mode: lastMethod })}</Alert>
            ) : null}
            {(['BANK', 'CARD', 'CREDIT', 'CHEQUE'] as PaymentMode[]).map((mode) => (
              <Button
                key={mode}
                variant={lastMethod === mode ? 'contained' : 'outlined'}
                size="large"
                sx={{ minHeight: 48, display: lastMethod === mode || showMoreTenders ? undefined : 'none' }}
                disabled={cashPayDisabled || hsnGap || expiredBlocksPay || periodClosed || offline || bankMissing(mode) || (mode === 'CREDIT' && Boolean(walkInCustomer) && customerId === walkInCustomer?.id)}
                endIcon={
                  mode === 'CARD' ? (
                    <HotkeyBadge text="F4" />
                  ) : mode === 'CREDIT' ? (
                    <HotkeyBadge text="F7" />
                  ) : undefined
                }
                onClick={() => {
                  if (mode === 'CHEQUE' && lastMethod !== 'CHEQUE') {
                    rememberMethod(mode);
                    return;
                  }
                  rememberMethod(mode);
                  void checkout(mode);
                }}
              >
                {mode === 'BANK'
                  ? t('pos.bankPay', { amount: formatMoney(gateTotal) })
                  : mode === 'CARD'
                    ? t('pos.cardPay', { amount: formatMoney(gateTotal) })
                    : mode === 'CREDIT'
                      ? t('pos.creditPay', { amount: formatMoney(gateTotal) })
                      : t('pos.chequePay', { amount: formatMoney(gateTotal) })}
              </Button>
            ))}
            {reprintBills.length > 0 ? (
              <Stack spacing={0.5}>
                <Typography variant="caption">{t('pos.lastBills')}</Typography>
                <label>
                  {t('pos.refundMode')}
                  <select value={refundMode} onChange={(event) => setRefundMode(event.target.value as 'CASH' | 'BANK' | 'ADVANCE' | 'SPLIT')}>
                    <option value="CASH">{t('pos.refundCash')}</option>
                    <option value="BANK">{t('pos.refundBank')}</option>
                    <option value="ADVANCE">{t('pos.refundAdvance')}</option>
                    <option value="SPLIT">{t('pos.refundSplit')}</option>
                  </select>
                </label>
                {reprintBills.map((bill) => (
                  <Stack key={bill.id} direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2">{bill.number}</Typography>
                    <Button size="small" onClick={() => { void printPosThermalOrWarn(bill); }}>{t('pos.reprintBill')}</Button>
                  </Stack>
                ))}
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    disabled={busy}
                    onClick={() => {
                      const bill = reprintBills[0];
                      if (!bill) return;
                      setBusy(true);
                      void getSalesInvoice(bill.id)
                        .then((invoice) => {
                          setReturnPick({
                            invoice: bill.id,
                            exchange: false,
                            lines: (invoice.items ?? []).filter((item) => item.id).map((item) => ({
                              id: Number(item.id),
                              name: item.productName || item.description || String(item.id),
                              take: String(item.quantity),
                            })),
                          });
                        })
                        .catch((err) => setError(getErrorMessage(err)))
                        .finally(() => setBusy(false));
                    }}
                  >
                    {t('pos.returnBill')}
                  </Button>
                  <Button
                    size="small"
                    disabled={busy}
                    onClick={() => {
                      const bill = reprintBills[0];
                      if (!bill) return;
                      setBusy(true);
                      void getSalesInvoice(bill.id)
                        .then((invoice) => {
                          setReturnPick({
                            invoice: bill.id,
                            exchange: true,
                            lines: (invoice.items ?? []).filter((item) => item.id).map((item) => ({
                              id: Number(item.id),
                              name: item.productName || item.description || String(item.id),
                              take: String(item.quantity),
                            })),
                          });
                        })
                        .catch((err) => setError(getErrorMessage(err)))
                        .finally(() => setBusy(false));
                    }}
                  >
                    {t('pos.exchangeBill')}
                  </Button>
                </Stack>
              </Stack>
            ) : null}
            <Button
              variant="text"
              color="inherit"
              disabled={busy || isFlushing || (cart.length === 0 && !upiPending && !cashPending)}
              endIcon={<HotkeyBadge text="F10" />}
              onClick={() => {
                if (cart.length > 0) setConfirmClearCartOpen(true);
              }}
            >
              {t('pos.clearCart')}
            </Button>
          </Stack>
        </Paper>
      </Stack>

      <Dialog
        open={Boolean(serialBatchError)}
        onClose={() => setSerialBatchError(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('pos.confirmSerialBatchTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {serialBatchError?.message || t('pos.confirmSerialBatchBody')}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSerialBatchError(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => {
              const mode = serialBatchError?.mode;
              setSerialBatchError(null);
              // CR-113: retry original failure only — do not auto-confirm blank POS / walk-in.
              if (mode) void checkout(mode);
            }}
          >
            {t('pos.confirmSerialBatchAction')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(totalsReconcile)}
        onClose={() => setTotalsReconcile(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('pos.totalsChangedTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {totalsReconcile
              ? t('pos.totalsChangedBody', {
                  shown: formatMoney(totalsReconcile.shown),
                  billed: formatMoney(totalsReconcile.billed),
                })
              : null}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Button onClick={() => setTotalsReconcile(null)}>{t('common.cancel')}</Button>
          <Button
            variant="outlined"
            onClick={() => {
              const rec = totalsReconcile;
              setTotalsReconcile(null);
              if (!rec) return;
              setCashTendered('');
              void checkout(rec.mode, {
                confirmWalkIn: true,
                confirmTotalsMismatch: true,
                splitPayments: rec.splitPayments,
              });
            }}
          >
            {totalsReconcile
              ? t('pos.totalsReCollect', { amount: formatMoney(totalsReconcile.billed) })
              : null}
          </Button>
          {totalsReconcile?.splitPayments ? null : (
          <Button
            variant="contained"
            onClick={() => {
              const rec = totalsReconcile;
              setTotalsReconcile(null);
              if (!rec) return;
              void checkout(rec.mode, {
                confirmWalkIn: true,
                confirmTotalsMismatch: true,
                shortCollectAmount: rec.shown,
              });
            }}
          >
            {totalsReconcile
              ? t('pos.totalsShortCollect', { amount: formatMoney(totalsReconcile.shown) })
              : null}
          </Button>
          )}
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(blankPosMode)}
        onClose={() => setBlankPosMode(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('pos.confirmBlankPosTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {t('pos.confirmBlankPosBody')}
          </Typography>
          {taxEnabled ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {t('pos.confirmBlankPosTaxNote')}
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBlankPosMode(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => {
              const mode = blankPosMode;
              setBlankPosMode(null);
              if (mode) {
                void checkout(mode, {
                  confirmBlankPos: true,
                  confirmWalkIn: true,
                  splitPayments: splitHold.current,
                });
              }
            }}
          >
            {t('pos.confirmBlankPosAction')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={returnPick != null} onClose={() => setReturnPick(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{returnPick?.exchange ? t('pos.exchangeBill') : t('pos.returnBill')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(returnPick?.lines ?? []).map((line) => (
              <TextField
                key={line.id}
                size="small"
                label={line.name}
                value={line.take}
                onChange={(event) => {
                  const take = event.target.value;
                  setReturnPick((prev) => prev && ({
                    ...prev,
                    lines: prev.lines.map((row) => row.id === line.id ? { ...row, take } : row),
                  }));
                }}
              />
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReturnPick(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (!returnPick) return;
              const lines = returnPick.lines
                .filter((line) => Number(line.take) > 0)
                .map((line) => ({ source_item: line.id, quantity: line.take }));
              setBusy(true);
              void returnPosBill({
                invoice: returnPick.invoice,
                exchange: returnPick.exchange,
                reason: returnPick.exchange ? 'Counter exchange' : 'Counter return',
                ownerPin,
                refundMode,
                lines,
              })
                .then((result) => {
                  if (returnPick.exchange) {
                    setApplyAdvanceNext(true);
                    if (result.customerId) setCustomerId(result.customerId);
                  }
                  setMessage(returnPick.exchange ? t('pos.exchangeBill') : t('pos.returnBill'));
                  setReturnPick(null);
                  void queryClient.invalidateQueries({ queryKey: ['stock'] });
                })
                .catch((err) => setError(getErrorMessage(err)))
                .finally(() => setBusy(false));
            }}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(pricePrompt)} onClose={() => setPricePrompt(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('pos.priceReason')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            label={t('pos.priceReason')}
            value={pricePrompt?.reason ?? ''}
            onChange={(e) => setPricePrompt((prev) => prev ? { ...prev, reason: e.target.value } : prev)}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPricePrompt(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!pricePrompt?.reason.trim()}
            onClick={() => {
              if (!pricePrompt?.reason.trim()) return;
              setCart((prev) => prev.map((row) => row.key === pricePrompt.key ? { ...row, priceOverride: pricePrompt.price } : row));
              setPricePrompt(null);
            }}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(pinPrompt)} onClose={() => setPinPrompt(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('pos.belowCostPin')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            type="password"
            label={t('pos.ownerPin')}
            value={ownerPin}
            onChange={(e) => setOwnerPin(e.target.value)}
            autoComplete="off"
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPinPrompt(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!ownerPin.trim()}
            onClick={() => {
              const pending = pinPrompt;
              setPinPrompt(null);
              if (pending) void checkout(pending.mode, pending.opts);
            }}
          >
            {t('pos.ownerPin')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={drawerAsk} onClose={() => setDrawerAsk(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('pos.drawerConfirm')}</DialogTitle>
        <DialogContent>
          <Typography>{t('pos.drawerConfirmBody')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDrawerAsk(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => {
              setDrawerAsk(false);
              void printEscPos(DRAWER_KICK).then((mode) => {
                if (mode === 'native') {
                  void postPosEvent({ kind: 'drawer_open', detail: 'Drawer opened from the counter' });
                }
              });
            }}
          >
            {t('pos.drawerConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirmClearCartOpen}
        title={t('pos.confirmClearCartTitle')}
        body={t('pos.confirmClearCartBody')}
        confirmLabel={t('pos.confirmClearCartAction')}
        confirmColor="error"
        onClose={() => setConfirmClearCartOpen(false)}
        onConfirm={() => {
          setConfirmClearCartOpen(false);
          clearCart();
        }}
      />
      <Dialog
        open={Boolean(walkInConfirmMode)}
        onClose={() => setWalkInConfirmMode(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('pos.confirmWalkInTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {t('pos.confirmWalkInBody')}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWalkInConfirmMode(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => {
              const mode = walkInConfirmMode;
              setWalkInConfirmMode(null);
              if (mode) {
                void checkout(mode, { confirmWalkIn: true, splitPayments: splitHold.current });
              }
            }}
          >
            {t('pos.confirmWalkInAction')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(upiPending)}
        onClose={(_event, reason) => {
          if (reason === 'backdropClick' || reason === 'escapeKeyDown') return;
          setUpiPending(null);
          clearUpiPendingStorage(companyId, userId);
        }}
        disableEscapeKeyDown
        TransitionProps={{ onExited: () => searchRef.current?.focus() }}
      >
        <DialogTitle>{t('pos.upiTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              {upiPending?.invoiceNumber
                ? t('pos.upiScanHint', {
                    number: upiPending.invoiceNumber,
                    amount: formatMoney(upiPending.amount ?? 0),
                  })
                : t('pos.upiPay', { amount: formatMoney(upiPending?.amount ?? 0) })}
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
              if (upiPending?.invoiceId) {
                const recovered = unpaidRecoverFromAbort(upiPending);
                if (recovered) setUnpaidRecover(recovered);
                setMessage(t('pos.leftUnpaid', { number: upiPending.invoiceNumber ?? '' }));
                setIdempotencyKey(null);
                setCart([]);
              }
              setUpiPending(null);
              clearUpiPendingStorage(companyId, userId);
            }}
          >
            {upiPending?.invoiceId ? t('pos.collectLater') : t('common.cancel')}
          </Button>
          {!upiArmed ? (
            <Button variant="outlined" disabled={busy} onClick={() => setUpiArmed(true)}>
              {t('pos.upiConfirmAmount', { amount: formatMoney(upiPending?.amount ?? 0) })}
            </Button>
          ) : (
            <Button variant="contained" disabled={busy} onClick={() => void confirmUpiPayment()}>
              {t('pos.paymentReceived')}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

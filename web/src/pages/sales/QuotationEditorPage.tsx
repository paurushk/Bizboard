import { useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import Skeleton from '@mui/material/Skeleton';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  createCustomer,
  createQuotation,
  downloadSalesDocumentPdf,
  duplicateQuotation,
  getCompany,
  getCustomer,
  getQuotation,
  getStockHints,
  listPriceLists,
  quotationLifecycle,
  searchSalespeople,
  updateQuotation,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { NumericField, todayIso } from '@/components/billing';
import { ShareQuotationDialog } from '@/components/ShareQuotationDialog';
import { StatusChip } from '@/components/StatusChip';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { PageTitle } from '@/contextHelp';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useNotices } from '@/hooks/useNotices';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ConvertQuotationDialog } from '@/pages/sales/ConvertQuotationDialog';
import { useQuotationConvert } from '@/pages/sales/useQuotationConvert';
import type { Customer, InvoiceType, Product, Quotation } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreateSales, canViewFinancialReports } from '@/utils/permissions';
import { resolveListUnitPrice, type PriceListRow } from '@/utils/priceList';
import { OPEN_QUOTATION_STATUSES } from '@/utils/quotationExpiry';
import {
  buildQuotationPayload,
  buildQuotationPreviewBody,
  type QuotationFormLine,
  type QuotationPayloadMode,
} from '@/utils/quotationPayload';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { triggerBlobDownload } from '@/utils/blob';
import { createIdempotencyKeyFor } from '@/utils/idempotencyKeyFor';

type EditorLine = QuotationFormLine & {
  key: string;
  name: string;
  /** The user typed this price, so a price list must not overwrite it. */
  priceEdited: boolean;
  priceListName: string;
};

type EditorForm = {
  quotationDate: string;
  validUntil: string;
  salesman: string;
  salesmanName: string;
  salesChannel: string;
  deliveryAddress: string;
  addressTouched: boolean;
  notes: string;
  termsText: string;
  paymentTermsDays: number;
  additionalCharges: number;
  chargesHsn: string;
  chargesGstRate: number;
  invoiceDiscount: number;
  invoiceDiscountMode: 'AFTER_TAX' | 'BEFORE_TAX';
  autoRoundOff: boolean;
  lines: EditorLine[];
};

const EMPTY_FORM: EditorForm = {
  quotationDate: '',
  validUntil: '',
  salesman: '',
  salesmanName: '',
  salesChannel: '',
  deliveryAddress: '',
  addressTouched: false,
  notes: '',
  termsText: '',
  paymentTermsDays: 0,
  additionalCharges: 0,
  chargesHsn: '',
  chargesGstRate: 0,
  invoiceDiscount: 0,
  invoiceDiscountMode: 'AFTER_TAX',
  autoRoundOff: true,
  lines: [],
};

function formFromQuote(q: Quotation): EditorForm {
  return {
    quotationDate: q.quotationDate || todayIso(),
    validUntil: q.validUntil ?? '',
    salesman: q.salesman ? String(q.salesman) : '',
    salesmanName: (q as { salesmanName?: string }).salesmanName ?? '',
    salesChannel: q.salesChannel ?? '',
    deliveryAddress: q.deliveryAddress ?? '',
    addressTouched: true,
    notes: q.notes ?? '',
    termsText: q.termsText ?? '',
    paymentTermsDays: q.paymentTermsDays ?? 0,
    additionalCharges: toNumber(q.additionalCharges),
    chargesHsn: q.chargesHsn ?? '',
    chargesGstRate: toNumber(q.chargesGstRate),
    invoiceDiscount: toNumber(q.invoiceDiscount),
    invoiceDiscountMode: q.invoiceDiscountMode ?? 'AFTER_TAX',
    autoRoundOff: q.autoRoundOff ?? true,
    lines: (q.items ?? []).map((item, idx) => {
      const extra = item as { hsnCode?: string; cessRate?: string | number; unitPriceInclusive?: string | number | null };
      return {
        key: `line-${item.id ?? idx}`,
        id: item.id,
        productId: item.product,
        name: item.productName ?? '',
        qty: toNumber(item.quantity),
        unitPrice: toNumber(item.unitPrice),
        discountPercent: toNumber(item.discountPercent),
        expectedPrice: toNumber(item.expectedPrice),
        gstRate: toNumber(item.gstRate),
        hsnCode: extra.hsnCode || undefined,
        cessRate: extra.cessRate ? toNumber(extra.cessRate) : undefined,
        unitPriceInclusive: extra.unitPriceInclusive != null ? toNumber(extra.unitPriceInclusive) : null,
        priceEdited: true,
        priceListName: '',
      };
    }),
  };
}

export function QuotationEditorPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { id: idParam } = useParams();
  const quoteId = idParam && /^\d+$/.test(idParam) ? Number(idParam) : null;
  const isNew = quoteId == null;
  const canCreate = canCreateSales(user);
  const showCost = canViewFinancialReports(user);
  useFeatureFlagEpoch();
  const lifecycleOn = isRuntimeFlagEnabled('QUOTE_LIFECYCLE');
  const notices = useNotices();

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const quoteQuery = useQuery({
    queryKey: ['quotation', quoteId],
    queryFn: () => getQuotation(quoteId as number),
    enabled: quoteId != null,
    retry: false,
  });
  const quote = quoteQuery.data;
  const loadedCustomer = useQuery({
    queryKey: ['customer', quote?.customer],
    queryFn: () => getCustomer(quote!.customer as number),
    enabled: Boolean(quote?.customer),
  });
  const priceLists = useQuery({ queryKey: ['price-lists'], queryFn: listPriceLists, enabled: canCreate });

  const [form, setForm] = useState<EditorForm>({ ...EMPTY_FORM, quotationDate: todayIso() });
  const [pickedCustomer, setPickedCustomer] = useState<Customer | null>(null);
  const customer: Customer | null =
    pickedCustomer ?? (quote?.customer ? (loadedCustomer.data ?? null) : null);
  const [baseline, setBaseline] = useState<string | null>(null);
  const [hydratedKey, setHydratedKey] = useState('');
  const [qtyError, setQtyError] = useState(false);
  const [leavePrompt, setLeavePrompt] = useState(false);

  // Fill the form from the saved quotation once per load, during render.
  const hydrateKey = quote ? `${quote.id}:${quote.status}:${quote.grandTotal}:${quote.shortClosedAt ?? ''}` : '';
  if (quote && hydratedKey !== hydrateKey) {
    const next = formFromQuote(quote);
    setHydratedKey(hydrateKey);
    setForm(next);
    setPickedCustomer(null);
    setBaseline(JSON.stringify({ form: next, customerId: quote.customer ?? null }));
  }
  const dirtyKey = JSON.stringify({ form, customerId: customer?.id ?? quote?.customer ?? null });
  const effectiveBaseline = baseline ?? (isNew ? JSON.stringify({ form: { ...EMPTY_FORM, quotationDate: todayIso() }, customerId: null }) : dirtyKey);
  const dirty = dirtyKey !== effectiveBaseline;

  const status = quote?.status ?? 'DRAFT';
  const partial = (quote?.items ?? []).some((item) => toNumber(item.convertedQuantity) > 0);
  const closed = Boolean(quote?.shortClosedAt);
  const editableStatus = status === 'DRAFT' || (status === 'SENT' && lifecycleOn);
  const readOnly = !isNew && (!editableStatus || closed);
  const headerLocked = !canCreate || readOnly;
  const linesLocked = headerLocked || partial;
  const invoiceType: InvoiceType = quote?.invoiceType ?? preferredInvoiceType(company.data?.registrationType);

  const patch = (change: Partial<EditorForm>) => setForm((f) => ({ ...f, ...change }));
  const updateLine = (key: string, change: Partial<EditorLine>) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l) => (l.key === key ? { ...l, ...change } : l)) }));

  // ---- customer
  const customerSearch = useCustomerSearch({ selected: customer });
  const [newPartyName, setNewPartyName] = useState('');
  const chooseCustomer = (next: Customer | null) => {
    setPickedCustomer(next);
    setForm((f) => {
      let lines = f.lines;
      // A customer's price list prices the lines the user has not priced by hand.
      if (next?.priceList) {
        lines = lines.map((l) => {
          if (l.priceEdited) return l;
          const hit = resolveListUnitPrice(priceLists.data as PriceListRow[] | undefined, next.priceList, l.productId, l.qty);
          return hit ? { ...l, unitPrice: hit.unitPrice, priceListName: hit.listName } : { ...l, priceListName: '' };
        });
      }
      const address = !f.addressTouched && next ? (next.shippingAddress ?? '') : f.deliveryAddress;
      return { ...f, lines, deliveryAddress: address };
    });
  };

  // ---- salesperson (server search; the payroll list is owner-only)
  const [salesQuery, setSalesQuery] = useState('');
  const debouncedSales = useDebouncedValue(salesQuery, 250);
  const salespeople = useQuery({
    queryKey: ['salespeople', debouncedSales],
    queryFn: () => searchSalespeople(debouncedSales),
    enabled: canCreate,
  });
  const salesmanValue = form.salesman ? { id: Number(form.salesman), name: form.salesmanName, code: '' } : null;
  const salesRows = salespeople.data ?? [];
  const salesOptions =
    salesmanValue && !salesRows.some((r) => r.id === salesmanValue.id) ? [salesmanValue, ...salesRows] : salesRows;

  // ---- lines
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [pendingQty, setPendingQty] = useState(1);
  const [pendingPrice, setPendingPrice] = useState(0);
  const [pendingDiscount, setPendingDiscount] = useState(0);
  const cf = useProductCfFilters();
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct, cf: cf.cfFilters });

  const pickProduct = (product: Product | null) => {
    setPendingProduct(product);
    if (!product) {
      setPendingPrice(0);
      return;
    }
    const hit = resolveListUnitPrice(priceLists.data as PriceListRow[] | undefined, customer?.priceList, product.id, pendingQty);
    setPendingPrice(hit ? hit.unitPrice : toNumber(product.sellingPrice));
  };
  const addLine = () => {
    if (!pendingProduct || !(pendingQty > 0)) return;
    const hit = resolveListUnitPrice(priceLists.data as PriceListRow[] | undefined, customer?.priceList, pendingProduct.id, pendingQty);
    setForm((f) => ({
      ...f,
      lines: [
        ...f.lines,
        {
          key: `new-${pendingProduct.id}-${Date.now()}`,
          productId: pendingProduct.id,
          name: pendingProduct.name,
          qty: pendingQty,
          unitPrice: pendingPrice,
          discountPercent: pendingDiscount,
          expectedPrice: toNumber(pendingProduct.purchasePrice),
          gstRate: toNumber(pendingProduct.gstRate),
          priceEdited: !hit || hit.unitPrice !== pendingPrice,
          priceListName: hit && hit.unitPrice === pendingPrice ? hit.listName : '',
        },
      ],
    }));
    setPendingProduct(null);
    setPendingQty(1);
    setPendingPrice(0);
    setPendingDiscount(0);
  };

  const lineTotal = (l: EditorLine) => l.qty * l.unitPrice * (1 - l.discountPercent / 100);
  const subtotal = form.lines.reduce((acc, l) => acc + lineTotal(l), 0);
  const estimatedGst = form.lines.reduce((acc, l) => acc + lineTotal(l) * (l.gstRate / 100), 0);
  const estimatedTotal = Math.round(subtotal + estimatedGst + form.additionalCharges - form.invoiceDiscount);

  // ---- stock hint (default godown)
  const productIds = useMemo(() => [...new Set(form.lines.map((l) => l.productId))].sort((a, b) => a - b), [form.lines]);
  const stock = useQuery({
    queryKey: ['stock-hints', productIds],
    queryFn: () => getStockHints(productIds),
    enabled: canCreate && !linesLocked && productIds.length > 0,
  });

  // ---- totals from the server's tax engine
  const formState = {
    customerId: customer?.id ?? 0,
    quotationDate: form.quotationDate,
    validUntil: form.validUntil,
    salesman: form.salesman,
    salesChannel: form.salesChannel,
    deliveryAddress: form.deliveryAddress,
    invoiceType,
    lines: form.lines,
    notes: form.notes,
    termsText: form.termsText,
    paymentTermsDays: form.paymentTermsDays,
    additionalCharges: form.additionalCharges,
    chargesHsn: form.chargesHsn,
    chargesGstRate: form.chargesGstRate,
    invoiceDiscount: form.invoiceDiscount,
    invoiceDiscountMode: form.invoiceDiscountMode,
    autoRoundOff: form.autoRoundOff,
  };
  const previewOnline = typeof navigator === 'undefined' || navigator.onLine;
  const previewBody =
    previewOnline && customer?.id && form.lines.length > 0 && !readOnly && !partial
      ? buildQuotationPreviewBody(formState, { supplyType: quote?.supplyType, companyGstin: quote?.companyGstin })
      : null;
  const preview = usePreviewTotals('sales', previewBody);
  const serverTotals = preview.ready ? preview.totals : null;

  // ---- save
  const createKey = useRef(createIdempotencyKeyFor());
  const saveMutation = useMutation({
    mutationFn: async () => {
      const mode: QuotationPayloadMode = isNew ? 'create' : partial ? 'edit-partially-converted' : 'edit';
      if (mode !== 'edit-partially-converted') {
        if (!customer?.id) throw new Error(t('billing.customerRequired'));
        if (form.lines.length === 0) throw new Error(t('billing.addAtLeastOneItem'));
        if (form.lines.some((l) => !(l.qty > 0))) {
          setQtyError(true);
          throw new Error(t('billing.qtyMustBePositive'));
        }
      }
      if (form.validUntil && form.quotationDate && form.validUntil < form.quotationDate) {
        throw new Error(t('phase1.quotationValidityBeforeDate'));
      }
      const payload = buildQuotationPayload(formState, mode, { includeCost: showCost });
      return isNew ? createQuotation(payload, createKey.current(payload)) : updateQuotation(quoteId as number, payload);
    },
    onSuccess: (saved) => {
      createKey.current = createIdempotencyKeyFor();
      void qc.invalidateQueries({ queryKey: ['quotations'] });
      void qc.invalidateQueries({ queryKey: ['quotation'] });
      setBaseline(dirtyKey);
      void navigate('/sales/quotations', {
        state: { message: t('phase1.quotationSavedTotal', { total: formatMoney(saved.grandTotal) }) },
      });
    },
    onError: (err) => notices.fail(getErrorMessage(err)),
  });

  // ---- other actions
  const convert = useQuotationConvert({ onDone: notices.success });
  const [shareOpen, setShareOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reopenReason, setReopenReason] = useState('');
  const reopenMutation = useMutation({
    mutationFn: () => quotationLifecycle(quoteId as number, 'reopen-for-changes', reopenReason.trim()),
    onSuccess: () => {
      setReopenOpen(false);
      setReopenReason('');
      void qc.invalidateQueries({ queryKey: ['quotation', quoteId] });
      void qc.invalidateQueries({ queryKey: ['quotations'] });
    },
    onError: (err) => {
      setReopenOpen(false);
      notices.fail(getErrorMessage(err));
    },
  });
  const duplicateMutation = useMutation({
    mutationFn: () => duplicateQuotation(quoteId as number),
    onSuccess: (copy) => {
      void qc.invalidateQueries({ queryKey: ['quotations'] });
      void navigate(`/sales/quotations/${copy.id}`, { state: { message: t('phase1.quotationDuplicated') } });
    },
    onError: (err) => notices.fail(getErrorMessage(err)),
  });
  const downloadPdf = () => {
    if (!quote) return;
    void downloadSalesDocumentPdf('quotation', quote.id)
      .then((blob) => triggerBlobDownload(blob, `${quote.number || quote.id}.pdf`))
      .catch((err) => notices.fail(getErrorMessage(err)));
  };

  const canSave =
    canCreate && !readOnly && !saveMutation.isPending && !quoteQuery.isLoading &&
    (partial || (Boolean(customer) && form.lines.length > 0));
  const canConvert = !isNew && canCreate && quote != null && OPEN_QUOTATION_STATUSES.includes(status) && !closed;
  const title = isNew ? t('phase1.newQuotation') : readOnly ? t('phase1.viewQuotation') : t('phase1.editQuotation');

  if (quoteQuery.isError) {
    return (
      <Stack spacing={2}>
        <PageTitle>{t('nav.quotations')}</PageTitle>
        <HelpErrorAlert message={getErrorMessage(quoteQuery.error)} />
        <Button onClick={() => void navigate('/sales/quotations')}>{t('common.back')}</Button>
      </Stack>
    );
  }
  if (!isNew && quoteQuery.isLoading) {
    return (
      <Stack spacing={2} aria-busy="true">
        <Skeleton variant="text" width={240} height={40} />
        <Skeleton variant="rounded" height={160} />
        <Skeleton variant="rounded" height={240} />
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <UnsavedChangesGuard
        when={dirty && !saveMutation.isSuccess}
        interceptLinks
        prompt={leavePrompt}
        body={t('phase1.quotationUnsavedBody')}
        onStay={() => setLeavePrompt(false)}
        onLeave={() => {
          setLeavePrompt(false);
          void navigate('/sales/quotations');
        }}
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <PageTitle>{title}</PageTitle>
          {quote?.number ? <Typography variant="h6">{quote.number}</Typography> : null}
          {quote ? <StatusChip tone={documentStatusTone(status)} labelKey={statusLabelKey(status)} /> : null}
          {closed ? <Chip size="small" color="warning" label={t('phase1.quotationClosedChip')} /> : null}
        </Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button onClick={() => (dirty ? setLeavePrompt(true) : void navigate('/sales/quotations'))}>
            {t('common.back')}
          </Button>
          {!isNew ? (
            <Button variant="outlined" onClick={downloadPdf}>{t('common.download')}</Button>
          ) : null}
          {!isNew && canCreate && status !== 'CANCELLED' && status !== 'REJECTED' ? (
            <Button variant="outlined" onClick={() => setShareOpen(true)}>{t('phase1.quotationShare')}</Button>
          ) : null}
          {!isNew && canCreate ? (
            <Button variant="outlined" disabled={duplicateMutation.isPending} onClick={() => duplicateMutation.mutate()}>
              {t('phase1.quotationDuplicate')}
            </Button>
          ) : null}
          {canConvert ? (
            <>
              <Button variant="outlined" disabled={dirty} onClick={() => convert.open(quote, 'order')}>
                {t('common.toOrder')}
              </Button>
              <Button variant="outlined" disabled={dirty} onClick={() => convert.open(quote, 'invoice')}>
                {t('common.convert')}
              </Button>
            </>
          ) : null}
          {canCreate && !readOnly ? (
            <Button variant="contained" disabled={!canSave} onClick={() => { notices.clear(); saveMutation.mutate(); }}>
              {t('common.save')}
            </Button>
          ) : null}
        </Stack>
      </Stack>

      {notices.message ? <Alert severity="success" onClose={notices.clear}>{notices.message}</Alert> : null}
      {notices.error ? <HelpErrorAlert message={notices.error} /> : null}
      {readOnly && !closed ? (
        <Alert
          severity="info"
          action={
            lifecycleOn && canCreate && (status === 'ACCEPTED' || status === 'REJECTED') ? (
              <Button color="inherit" size="small" onClick={() => setReopenOpen(true)}>
                {t('phase1.quotationReopen')}
              </Button>
            ) : undefined
          }
        >
          {lifecycleOn && (status === 'ACCEPTED' || status === 'REJECTED')
            ? t('phase1.quotationReopenBanner', { status: t(statusLabelKey(status)) })
            : t('phase1.quotationReadOnly', { status: t(statusLabelKey(status)) })}
        </Alert>
      ) : null}
      {closed ? (
        <Alert severity="warning">
          {t('phase1.quotationClosedChip')}: {quote?.shortCloseReason}
        </Alert>
      ) : null}
      {status === 'SENT' && lifecycleOn && !readOnly ? (
        <Alert severity="info">{t('phase1.quotationEditSentNotice')}</Alert>
      ) : null}
      {partial && !readOnly ? <Alert severity="info">{t('phase1.quotationLinesLocked')}</Alert> : null}
      {quote?.copiedFrom ? (
        <Typography variant="body2" color="text.secondary">
          <Button size="small" variant="text" onClick={() => void navigate(`/sales/quotations/${quote.copiedFrom}`)}>
            {t('phase1.quotationCopiedFrom', { number: `#${quote.copiedFrom}` })}
          </Button>
        </Typography>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Autocomplete
            options={customerSearch.options}
            getOptionLabel={(o) => o.name}
            filterOptions={(opts) => opts}
            value={customer}
            disabled={linesLocked}
            onChange={(_, v) => chooseCustomer(v)}
            onInputChange={(_, v) => customerSearch.setQuery(v)}
            loading={customerSearch.isFetching}
            renderInput={(params) => (
              <TextField
                {...params}
                required
                label={t('billing.customer')}
                helperText={!customerSearch.enabled ? t('common.typeToSearch') : undefined}
              />
            )}
          />
          {!linesLocked ? (
            <Stack direction="row" spacing={1}>
              <TextField size="small" label={t('billing.addParty')} value={newPartyName} onChange={(e) => setNewPartyName(e.target.value)} />
              <Button
                size="small"
                disabled={!newPartyName.trim()}
                onClick={() => {
                  void createCustomer({ name: newPartyName.trim(), status: 'ACTIVE' })
                    .then((c) => {
                      chooseCustomer(c);
                      setNewPartyName('');
                    })
                    .catch((err) => notices.fail(getErrorMessage(err)));
                }}
              >
                {t('common.add')}
              </Button>
            </Stack>
          ) : null}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              type="date"
              size="small"
              sx={{ flex: 1 }}
              label={t('phase1.quotationDate')}
              InputLabelProps={{ shrink: true }}
              value={form.quotationDate}
              disabled={linesLocked}
              onChange={(e) => patch({ quotationDate: e.target.value })}
            />
            <TextField
              type="date"
              size="small"
              sx={{ flex: 1 }}
              label={t('billing.validUntil')}
              InputLabelProps={{ shrink: true }}
              inputProps={{ min: form.quotationDate || undefined }}
              value={form.validUntil}
              disabled={headerLocked}
              onChange={(e) => patch({ validUntil: e.target.value })}
            />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <Autocomplete
              sx={{ flex: 1 }}
              size="small"
              options={salesOptions}
              disabled={headerLocked}
              loading={salespeople.isFetching}
              filterOptions={(opts) => opts}
              getOptionLabel={(o) => o.name}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              value={salesmanValue}
              onInputChange={(_, v, reason) => {
                if (reason === 'input') setSalesQuery(v);
              }}
              onChange={(_, v) => patch({ salesman: v ? String(v.id) : '', salesmanName: v?.name ?? '' })}
              renderInput={(params) => <TextField {...params} label={t('billing.salesman')} />}
            />
            <TextField
              select
              size="small"
              sx={{ flex: 1 }}
              label={t('billing.salesChannel')}
              value={form.salesChannel}
              disabled={headerLocked}
              onChange={(e) => patch({ salesChannel: e.target.value })}
            >
              <MenuItem value="">{t('common.none')}</MenuItem>
              <MenuItem value="WALK_IN">{t('billing.channelWalkIn')}</MenuItem>
              <MenuItem value="ONLINE">{t('billing.channelOnline')}</MenuItem>
              <MenuItem value="DISTRIBUTOR">{t('billing.channelDistributor')}</MenuItem>
            </TextField>
          </Stack>
          <TextField
            size="small"
            multiline
            minRows={2}
            label={t('billing.deliveryAddress')}
            value={form.deliveryAddress}
            disabled={headerLocked}
            onChange={(e) => patch({ deliveryAddress: e.target.value, addressTouched: true })}
          />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, overflow: 'auto' }}>
        {showCost && serverTotals?.estimatedMargin != null ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {t('billing.expectedProfit')}: {formatMoney(serverTotals.estimatedMargin)}
          </Typography>
        ) : null}
        {form.lines.length > 0 ? (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
                <TableCell align="right">{t('billing.unitPrice')}</TableCell>
                {showCost ? <TableCell align="right">{t('billing.expectedPrice')}</TableCell> : null}
                <TableCell align="right">{t('billing.discountPercent')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {form.lines.map((l) => {
                const available = stock.data?.[String(l.productId)];
                const short = available != null && l.qty > toNumber(available);
                return (
                  <TableRow key={l.key}>
                    <TableCell>
                      {l.name}
                      {l.priceListName ? (
                        <Typography variant="caption" display="block" color="text.secondary">
                          {t('phase1.quotationPriceListApplied')}: {l.priceListName}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      <NumericField
                        size="small"
                        value={l.qty}
                        decimals={3}
                        min={0}
                        emptyAs={0}
                        disabled={linesLocked}
                        error={qtyError && !(l.qty > 0)}
                        helperText={
                          qtyError && !(l.qty > 0)
                            ? t('billing.qtyMustBePositive')
                            : short
                              ? t('phase1.quotationStockOnly', { qty: toNumber(available) })
                              : undefined
                        }
                        onValueChange={(n) => {
                          setQtyError(false);
                          updateLine(l.key, { qty: n });
                        }}
                        sx={{ width: 110 }}
                        inputProps={{ 'aria-label': t('billing.qty') }}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <NumericField
                        size="small"
                        value={l.unitPrice}
                        decimals={2}
                        min={0}
                        disabled={linesLocked}
                        onValueChange={(n) => updateLine(l.key, { unitPrice: n, priceEdited: true, priceListName: '' })}
                        sx={{ width: 110 }}
                        inputProps={{ 'aria-label': t('billing.unitPrice') }}
                      />
                    </TableCell>
                    {showCost ? (
                      <TableCell align="right">
                        <NumericField
                          size="small"
                          value={l.expectedPrice}
                          decimals={2}
                          min={0}
                          disabled={linesLocked}
                          onValueChange={(n) => updateLine(l.key, { expectedPrice: n })}
                          sx={{ width: 110 }}
                          inputProps={{ 'aria-label': t('billing.expectedPrice') }}
                        />
                      </TableCell>
                    ) : null}
                    <TableCell align="right">
                      <NumericField
                        size="small"
                        value={l.discountPercent}
                        decimals={2}
                        min={0}
                        max={100}
                        disabled={linesLocked}
                        onValueChange={(n) => updateLine(l.key, { discountPercent: n })}
                        sx={{ width: 90 }}
                        inputProps={{ 'aria-label': t('billing.discountPercent') }}
                      />
                    </TableCell>
                    <TableCell align="right">{formatMoney(lineTotal(l))}</TableCell>
                    <TableCell align="right">
                      <IconButton
                        size="small"
                        aria-label={t('common.remove')}
                        disabled={linesLocked}
                        onClick={() => setForm((f) => ({ ...f, lines: f.lines.filter((x) => x.key !== l.key) }))}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : null}

        {!linesLocked ? (
          <Stack spacing={1} sx={{ mt: form.lines.length ? 2 : 0 }}>
            {cf.filterBar}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
              <Autocomplete
                sx={{ flex: 1 }}
                options={productSearch.options}
                loading={productSearch.isFetching}
                filterOptions={(opts) => opts}
                inputValue={productSearch.productQuery}
                onInputChange={(_, v, reason) => {
                  if (reason === 'input' || reason === 'clear' || reason === 'reset') productSearch.setProductQuery(v);
                }}
                getOptionLabel={(o) => `${o.name} · ${o.sku}`}
                value={pendingProduct}
                onChange={(_, v) => pickProduct(v)}
                renderInput={(params) => (
                  <TextField {...params} label={t('nav.products')} helperText={productSearch.helperText} />
                )}
              />
              <NumericField label={t('billing.qty')} value={pendingQty} decimals={3} min={0} onValueChange={setPendingQty} sx={{ width: 100 }} />
              <NumericField label={t('billing.unitPrice')} value={pendingPrice} decimals={2} min={0} onValueChange={setPendingPrice} sx={{ width: 110 }} />
              <NumericField label={t('billing.discountPercent')} value={pendingDiscount} decimals={2} min={0} max={100} onValueChange={setPendingDiscount} sx={{ width: 90 }} />
              <Button variant="outlined" disabled={!pendingProduct || !(pendingQty > 0)} onClick={addLine}>
                {t('common.add')}
              </Button>
            </Stack>
          </Stack>
        ) : null}
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>{t('phase1.quotationCommercial')}</Typography>
        <Stack spacing={2}>
          <TextField
            size="small"
            multiline
            minRows={2}
            label={t('phase1.quotationNotes')}
            value={form.notes}
            disabled={headerLocked}
            onChange={(e) => patch({ notes: e.target.value })}
          />
          <TextField
            size="small"
            multiline
            minRows={3}
            label={t('phase1.quotationTermsText')}
            value={form.termsText}
            disabled={headerLocked}
            onChange={(e) => patch({ termsText: e.target.value })}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <NumericField
              label={t('phase1.quotationPaymentDays')}
              value={form.paymentTermsDays}
              decimals={0}
              min={0}
              max={365}
              disabled={linesLocked}
              onValueChange={(n) => patch({ paymentTermsDays: Math.round(n) })}
              sx={{ flex: 1 }}
            />
            <NumericField
              label={t('billing.additionalCharges')}
              value={form.additionalCharges}
              decimals={2}
              min={0}
              disabled={linesLocked}
              onValueChange={(n) => patch({ additionalCharges: n })}
              sx={{ flex: 1 }}
            />
            <TextField
              size="small"
              label={t('billing.chargesHsn')}
              value={form.chargesHsn}
              disabled={linesLocked}
              inputProps={{ maxLength: 8 }}
              onChange={(e) => patch({ chargesHsn: e.target.value })}
              sx={{ flex: 1 }}
            />
            <NumericField
              label={t('billing.chargesGstRate')}
              value={form.chargesGstRate}
              decimals={2}
              min={0}
              max={40}
              disabled={linesLocked}
              onValueChange={(n) => patch({ chargesGstRate: n })}
              sx={{ flex: 1 }}
            />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
            <NumericField
              label={t('billing.invoiceDiscount')}
              value={form.invoiceDiscount}
              decimals={2}
              min={0}
              disabled={linesLocked}
              onValueChange={(n) => patch({ invoiceDiscount: n })}
              sx={{ flex: 1 }}
            />
            <TextField
              select
              size="small"
              label={t('phase1.quotationDiscountMode')}
              value={form.invoiceDiscountMode}
              disabled={linesLocked}
              onChange={(e) => patch({ invoiceDiscountMode: e.target.value as 'AFTER_TAX' | 'BEFORE_TAX' })}
              sx={{ flex: 1 }}
            >
              <MenuItem value="AFTER_TAX">{t('billing.invoiceDiscountAfterTax')}</MenuItem>
              <MenuItem value="BEFORE_TAX">{t('billing.invoiceDiscountBeforeTax')}</MenuItem>
            </TextField>
            <FormControlLabel
              sx={{ flex: 1 }}
              control={
                <Switch
                  checked={form.autoRoundOff}
                  disabled={linesLocked}
                  onChange={(e) => patch({ autoRoundOff: e.target.checked })}
                />
              }
              label={t('billing.autoRoundOff')}
            />
          </Stack>
          {partial ? <Typography variant="caption" color="text.secondary">{t('phase1.quotationPartialGstNote')}</Typography> : null}
        </Stack>
      </Paper>

      {quote?.conversions && quote.conversions.length > 0 ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>{t('phase1.quotationConversions')}</Typography>
          <Stack spacing={0.5}>
            {quote.conversions.map((c) => {
              const label = c.documentNumber || (c.documentId != null ? `#${c.documentId}` : '—');
              const path =
                c.documentId == null ? null : c.target === 'ORDER' ? `/sales/orders/${c.documentId}` : c.target === 'INVOICE' ? `/sales/history/${c.documentId}` : null;
              return (
                <Stack key={c.id} direction="row" spacing={1} alignItems="center">
                  {path ? (
                    <Button size="small" variant="text" onClick={() => void navigate(path)}>{label}</Button>
                  ) : (
                    <Typography variant="body2">{label}</Typography>
                  )}
                  <Typography variant="body2" color="text.secondary">
                    {toNumber(c.quantity)}
                    {c.documentStatus ? ` · ${c.documentStatus}` : ''}
                  </Typography>
                  {c.releasedAt ? (
                    <Typography variant="caption" color="warning.main">
                      {t('phase1.quotationConversionReleased')} {c.releasedAt.slice(0, 10)}
                      {c.releaseReason ? ` · ${c.releaseReason}` : ''}
                    </Typography>
                  ) : null}
                </Stack>
              );
            })}
          </Stack>
        </Paper>
      ) : null}

      {form.lines.length > 0 && !partial && !readOnly ? (
        <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
          <Stack spacing={0.5} alignItems="flex-end" aria-live="polite">
            {serverTotals ? (
              <>
                <Typography variant="body2">{t('billing.taxableAmount')}: {formatMoney(serverTotals.taxableTotal)}</Typography>
                {serverTotals.intraState ? (
                  <>
                    <Typography variant="body2" color="text.secondary">{t('billing.cgst')}: {formatMoney(serverTotals.cgstTotal)}</Typography>
                    <Typography variant="body2" color="text.secondary">{t('billing.sgst')}: {formatMoney(serverTotals.sgstTotal)}</Typography>
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary">{t('billing.igst')}: {formatMoney(serverTotals.igstTotal)}</Typography>
                )}
                {serverTotals.cessTotal > 0 ? (
                  <Typography variant="body2" color="text.secondary">{t('billing.cess')}: {formatMoney(serverTotals.cessTotal)}</Typography>
                ) : null}
                {serverTotals.roundOff !== 0 ? (
                  <Typography variant="body2" color="text.secondary">{t('billing.roundOff')}: {formatMoney(serverTotals.roundOff)}</Typography>
                ) : null}
                <Typography variant="subtitle1" fontWeight="bold">{t('billing.grandTotal')}: {formatMoney(serverTotals.grandTotal)}</Typography>
              </>
            ) : (
              <>
                <Typography variant="body2">{t('billing.taxableAmount')}: {formatMoney(subtotal)}</Typography>
                <Typography variant="body2" color="text.secondary">{t('billing.estimatedTax')}: {formatMoney(estimatedGst)}</Typography>
                <Typography variant="subtitle1" fontWeight="bold">{t('common.total')}: {formatMoney(estimatedTotal)}</Typography>
                <Chip size="small" color="warning" variant="outlined" label={t('phase1.quotationEstimated')} />
                {preview.error ? (
                  <Typography variant="caption" color="text.secondary">{t('billing.previewUnavailableClientTotals')}</Typography>
                ) : null}
              </>
            )}
            {preview.pending ? <CircularProgress size={14} aria-label={t('common.loading')} /> : null}
          </Stack>
        </Paper>
      ) : null}

      <ShareQuotationDialog
        open={shareOpen}
        quotation={quote ? { id: quote.id, number: quote.number } : null}
        companyName={company.data?.name ?? ''}
        onClose={() => setShareOpen(false)}
        onShared={() => {
          void qc.invalidateQueries({ queryKey: ['quotation', quoteId] });
          void qc.invalidateQueries({ queryKey: ['quotations'] });
        }}
      />
      <ConvertQuotationDialog
        quotation={convert.target?.quotation ?? null}
        mode={convert.target?.mode ?? null}
        pending={convert.pending}
        error={convert.error}
        onClose={convert.close}
        onConfirm={convert.confirm}
      />
      <Dialog open={reopenOpen} onClose={() => setReopenOpen(false)} aria-labelledby="reopen-quotation-title">
        <DialogTitle id="reopen-quotation-title">{t('phase1.quotationReopen')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            required
            size="small"
            sx={{ mt: 1 }}
            label={t('phase1.quotationReasonLabel')}
            value={reopenReason}
            inputProps={{ maxLength: 500 }}
            onChange={(e) => setReopenReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReopenOpen(false)}>{t('common.close')}</Button>
          <Button variant="contained" disabled={!reopenReason.trim() || reopenMutation.isPending} onClick={() => reopenMutation.mutate()}>
            {t('common.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

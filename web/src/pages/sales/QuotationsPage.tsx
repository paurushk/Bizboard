import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import DeleteIcon from '@mui/icons-material/Delete';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelQuotation,
  convertQuotation,
  convertQuotationChain,
  convertQuotationToOrder,
  createCustomer,
  createQuotation,
  downloadSalesDocumentPdf,
  getCompany,
  getCustomer,
  getQuotation,
  listQuotationsPage,
  listSalesInvoicesPage,
  updateQuotation,
} from '@/api/resources';
import { listEmployeesPage } from '@/api/payroll';
import { todayIso } from '@/components/billing';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import {
  EMPTY_HISTORY_FILTERS,
  HistoryFilterBar,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { StatusChip } from '@/components/StatusChip';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useAuth } from '@/auth/AuthContext';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { Customer, Product, Quotation } from '@/types/domain';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import { formatMoney, expectedProfitAmount, toNumber } from '@/utils/money';
import { canCreateSales } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ConvertQuotationDialog } from '@/pages/sales/ConvertQuotationDialog';
import { quotationHasRemainingAfterConvert, type ConvertLinePayload } from '@/utils/quotationConvert';
import { triggerBlobDownload } from '@/utils/blob';

interface DraftLine {
  key: string;
  product: Product;
  qty: number;
  // F2-039: quotations always quoted the current catalog price with no way
  // to negotiate/volume-price a line — the primary purpose of a quotation.
  unitPrice: number;
  discountPercent: number;
  expectedPrice: number;
}

const emptyForm = { customer: null as Customer | null, lines: [] as DraftLine[] };

const PAGE_SIZE = 50;

export function QuotationsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canCreate = canCreateSales(user);
  const navigate = useNavigate();
  const { id: editParam } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const debouncedQ = useDebouncedValue(filters.q, 300);
  const statusParam =
    filters.status === 'OPEN'
      ? 'DRAFT'
      : filters.status === 'CLOSED'
        ? 'CONVERTED'
        : filters.status === 'CANCELLED'
          ? 'CANCELLED'
          : filters.status || undefined;
  const query = useQuery({
    queryKey: ['quotations', page, statusParam, debouncedQ, filters.dateFrom, filters.dateTo],
    queryFn: () =>
      listQuotationsPage({
        page,
        pageSize: PAGE_SIZE,
        status: statusParam,
        q: debouncedQ || undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      }),
  });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const employees = useQuery({ queryKey: ['employees-mini'], queryFn: async () => (await listEmployeesPage({ pageSize: 100 })).results });
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const cf = useProductCfFilters();
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct, cf: cf.cfFilters });

  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(emptyForm.customer);
  // F2-025: search-as-you-type instead of loading every customer up front.
  const customerSearch = useCustomerSearch({ selected: customer });
  // BUG-523: quotations were hardcoded to exactly one line item — this is
  // now a real multi-line list, matching how invoices/purchases work.
  const [lines, setLines] = useState<DraftLine[]>(emptyForm.lines);
  const [pendingQty, setPendingQty] = useState('1');
  const [pendingUnitPrice, setPendingUnitPrice] = useState('');
  const [pendingDiscountPercent, setPendingDiscountPercent] = useState('0');
  const [quotationDate, setQuotationDate] = useState(todayIso());
  const [validUntil, setValidUntil] = useState('');
  const [salesman, setSalesman] = useState('');
  const [salesChannel, setSalesChannel] = useState('');
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [isPartiallyConverted, setIsPartiallyConverted] = useState(false);
  const [expectedProfit, setExpectedProfit] = useState<unknown>(null);
  const [newPartyName, setNewPartyName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // An inbound ?create=1 opens the dialog; the effect below then strips the param.
  if (canCreate && searchParams.get('create') === '1' && !open) setOpen(true);

  useEffect(() => {
    if (!canCreate || searchParams.get('create') !== '1') return;
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    setSearchParams(next, { replace: true });
  }, [canCreate, searchParams, setSearchParams]);

  useEffect(() => {
    const id = Number(editParam);
    if (!Number.isFinite(id) || id <= 0) return;
    let cancelled = false;
    void getQuotation(id)
      .then(async (q) => {
        if (cancelled) return;
        setEditingId(q.id);
        setOpen(true);
        setQuotationDate(q.quotationDate || todayIso());
        setValidUntil(q.validUntil ?? '');
        setExpectedProfit(q.expectedProfit);
        setSalesman(q.salesman ? String(q.salesman) : '');
        setSalesChannel((q as { salesChannel?: string }).salesChannel ?? '');
        setDeliveryAddress((q as { deliveryAddress?: string }).deliveryAddress ?? '');
        setIsPartiallyConverted((q.items ?? []).some((item) => toNumber(item.convertedQuantity) > 0));
        if (q.customer) {
          try {
            const c = await getCustomer(q.customer);
            if (!cancelled) setCustomer(c);
          } catch {
            setCustomer({ id: q.customer, name: q.customerName ?? '', status: 'ACTIVE' });
          }
        }
        setLines(
          (q.items ?? []).map((item, idx) => ({
            key: `edit-${item.id ?? idx}`,
            product: {
              id: item.product,
              name: item.productName ?? '',
              sku: '',
              sellingPrice: item.unitPrice,
              purchasePrice: (item as { expectedPrice?: string | number }).expectedPrice ?? 0,
              gstRate: item.gstRate,
              status: 'ACTIVE',
            } as Product,
            qty: toNumber(item.quantity),
            unitPrice: toNumber(item.unitPrice),
            discountPercent: toNumber(item.discountPercent),
            expectedPrice: toNumber((item as { expectedPrice?: string | number }).expectedPrice),
          })),
        );
      })
      .catch((err) => setError(getErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [editParam]);

  const resetDialog = () => {
    setCustomer(null);
    setLines([]);
    setPendingProduct(null);
    setPendingQty('1');
    setPendingUnitPrice('');
    setPendingDiscountPercent('0');
    setQuotationDate(todayIso());
    setValidUntil('');
    setSalesman('');
    setSalesChannel('');
    setDeliveryAddress('');
    setEditingId(null);
    setIsPartiallyConverted(false);
    setExpectedProfit(null);
    setNewPartyName('');
    productSearch.setProductQuery('');
    if (editParam) {
      void navigate('/sales/quotations', { replace: true });
    }
  };

  const addLine = () => {
    if (!pendingProduct) return;
    const qty = Math.max(0.001, toNumber(pendingQty) || 0.001);
    const unitPrice = Math.max(0, toNumber(pendingUnitPrice) || 0);
    const discountPercent = Math.min(100, Math.max(0, toNumber(pendingDiscountPercent) || 0));
    setLines((prev) => [
      ...prev,
      { key: `${pendingProduct.id}-${Date.now()}`, product: pendingProduct, qty, unitPrice, discountPercent, expectedPrice: toNumber(pendingProduct.purchasePrice) },
    ]);
    setPendingProduct(null);
    setPendingQty('1');
    setPendingUnitPrice('');
    setPendingDiscountPercent('0');
  };

  const updateLine = (key: string, patch: Partial<Pick<DraftLine, 'qty' | 'unitPrice' | 'discountPercent' | 'expectedPrice'>>) => {
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  };

  const lineTotal = (l: DraftLine) => l.qty * l.unitPrice * (1 - l.discountPercent / 100);

  const subtotal = lines.reduce((acc, l) => acc + lineTotal(l), 0);
  const estimatedGst = lines.reduce(
    (acc, l) => acc + lineTotal(l) * (toNumber(l.product.gstRate) / 100),
    0,
  );
  const grandTotal = Math.round(subtotal + estimatedGst);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!customer?.id) throw new Error(t('billing.selectCustomerRequired', 'Select a customer before saving.'));
      if (lines.length === 0) throw new Error('Add at least one product');
      const payload = {
        customer: customer.id,
        quotationDate: editingId ? quotationDate : todayIso(),
        validUntil: validUntil || null,
        salesman: salesman ? Number(salesman) : null,
        salesChannel,
        deliveryAddress,
        invoiceType: preferredInvoiceType(company.data?.registrationType),
        items: lines.map((l) => ({
          product: l.product.id,
          quantity: l.qty,
          unitPrice: l.unitPrice,
          discountPercent: l.discountPercent,
          expectedPrice: l.expectedPrice,
          gstRate: toNumber(l.product.gstRate),
        })),
      };
      return editingId ? updateQuotation(editingId, payload) : createQuotation(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setMessage(editingId ? t('phase1.saved') : 'Quotation created');
      resetDialog();
      void qc.invalidateQueries({ queryKey: ['quotations'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelQuotation(id),
    onSuccess: () => {
      setMessage(t('status.quotationCancelled', 'Quotation cancelled'));
      void qc.invalidateQueries({ queryKey: ['quotations'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [convertTarget, setConvertTarget] = useState<{
    quotation: Quotation;
    mode: 'invoice' | 'order';
  } | null>(null);
  const convertMutation = useMutation({
    mutationFn: ({ id, items, confirmExpired }: { id: number; items: ConvertLinePayload[]; confirmExpired?: boolean }) =>
      convertQuotation(id, { items, confirmExpired }),
    onSuccess: async (invoice, vars) => {
      const remaining = quotationHasRemainingAfterConvert(
        convertTarget?.quotation.items ?? [],
        vars.items,
      );
      setConvertingId(null);
      setConvertTarget(null);
      void qc.invalidateQueries({ queryKey: ['quotations'] });
      if (remaining) {
        setMessage(t('common.convertedPartialInvoice', { id: invoice.id }));
        return;
      }
      const flash = `Converted to draft invoice #${invoice.id}`;
      setMessage(flash);
      try {
        await qc.fetchQuery({
          queryKey: ['sales-invoices'],
          queryFn: () => listSalesInvoicesPage(),
          staleTime: 0,
        });
      } catch {
        void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      }
      void navigate('/sales/history', { state: { message: flash } });
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const convertToOrderMutation = useMutation({
    mutationFn: ({ id, items, confirmExpired }: { id: number; items: ConvertLinePayload[]; confirmExpired?: boolean }) =>
      convertQuotationToOrder(id, { items, confirmExpired }),
    onSuccess: async (order, vars) => {
      const remaining = quotationHasRemainingAfterConvert(
        convertTarget?.quotation.items ?? [],
        vars.items,
      );
      setConvertingId(null);
      setConvertTarget(null);
      void qc.invalidateQueries({ queryKey: ['quotations'] });
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      if (remaining) {
        setMessage(t('common.convertedPartialOrder', { id: order.id }));
        return;
      }
      const flash = `Converted to draft sales order #${order.id}`;
      setMessage(flash);
      void navigate('/sales/orders', { state: { message: flash } });
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const quotations = query.data?.results ?? [];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.quotations')}</PageTitle>
        {canCreate ? (
          <Button variant="contained" onClick={() => setOpen(true)}>
            {t('phase1.newQuotation')}
          </Button>
        ) : null}
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      <HistoryFilterBar
        value={filters}
        onChange={(next) => {
          setFilters(next);
          setPage(1);
        }}
        dateRangePresets
        statusOptions={[
          { value: 'OPEN', label: t('status.OPEN') },
          { value: 'CLOSED', label: t('status.converted') },
          { value: 'CANCELLED', label: t('status.cancelled', 'Cancelled') },
        ]}
      />
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {quotations.length === 0 && query.isSuccess ? <EmptyState description={t('empty.quotations')} /> : null}
      {quotations.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.validUntil', 'Valid Until')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {quotations.map((q) => {
                const isExpired = Boolean(q.validUntil && q.validUntil < todayIso());
                const isConvertible = q.status === 'DRAFT' && canCreate;
                const canCancel =
                  isConvertible &&
                  (q.items ?? []).every((it) => toNumber((it as { convertedQuantity?: number | string }).convertedQuantity) === 0);

                return (
                  <TableRow key={q.id}>
                    <TableCell>{q.number ?? '—'}</TableCell>
                    <TableCell>{q.quotationDate}</TableCell>
                    <TableCell>
                      {q.validUntil ? (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <span>{q.validUntil}</span>
                          {isExpired && q.status === 'DRAFT' ? (
                            <Typography variant="caption" sx={{ color: 'error.main', fontWeight: 'bold' }}>
                              ({t('status.expired', 'Expired')})
                            </Typography>
                          ) : null}
                        </Stack>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>{q.customerName ?? '—'}</TableCell>
                    <TableCell>
                      <StatusChip
                        tone={documentStatusTone(q.status)}
                        labelKey={statusLabelKey(q.status)}
                      />
                    </TableCell>
                    <TableCell align="right">{formatMoney(q.grandTotal)}</TableCell>
                    <TableCell align="right">
                      {isConvertible ? (
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          <Button
                            size="small"
                            variant="text"
                            onClick={() => {
                              void downloadSalesDocumentPdf('quotation', q.id)
                                .then((blob) => triggerBlobDownload(blob, `${q.number || q.id}.pdf`))
                                .catch((err) => setError(getErrorMessage(err)));
                            }}
                          >
                            {t('common.download')}
                          </Button>
                          <Button
                            size="small"
                            variant="text"
                            onClick={() => navigate(`/sales/quotations/${q.id}`)}
                          >
                            {t('common.edit')}
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={
                              (convertMutation.isPending || convertToOrderMutation.isPending) &&
                              convertingId === q.id
                            }
                            onClick={() => {
                              setError(null);
                              setConvertingId(q.id);
                              setConvertTarget({ quotation: q, mode: 'order' });
                            }}
                          >
                            {t('common.toOrder')}
                          </Button>
                          <Button
                            size="small"
                            disabled={
                              (convertMutation.isPending || convertToOrderMutation.isPending) &&
                              convertingId === q.id
                            }
                            onClick={() => {
                              setError(null);
                              setConvertingId(q.id);
                              setConvertTarget({ quotation: q, mode: 'invoice' });
                            }}
                          >
                            {t('common.convert')}
                          </Button>
                          {canCancel ? (
                            <Button
                              size="small"
                              color="error"
                              variant="text"
                              disabled={cancelMutation.isPending}
                              onClick={() => {
                                if (window.confirm(t('common.confirmCancelQuotation', 'Are you sure you want to cancel this quotation?'))) {
                                  cancelMutation.mutate(q.id);
                                }
                              }}
                            >
                              {t('common.cancel')}
                            </Button>
                          ) : null}
                        </Stack>
                      ) : (
                        <Button
                          size="small"
                          variant="text"
                          onClick={() => {
                            void downloadSalesDocumentPdf('quotation', q.id)
                              .then((blob) => triggerBlobDownload(blob, `${q.number || q.id}.pdf`))
                              .catch((err) => setError(getErrorMessage(err)));
                          }}
                        >
                          {t('common.download')}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          resetDialog();
        }}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>{editingId ? t('common.edit') : t('phase1.newQuotation')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            {isPartiallyConverted ? (
              <Alert severity="info">
                {t('billing.quotationLinesLocked', 'Line items are locked because this quotation has already been partially converted.')}
              </Alert>
            ) : null}
            <Autocomplete
              options={customerSearch.options}
              getOptionLabel={(o) => o.name}
              filterOptions={(opts) => opts}
              value={customer}
              disabled={!canCreate}
              onChange={(_, v) => {
                setCustomer(v);
                if (v && !deliveryAddress) {
                  setDeliveryAddress((v as Customer & { shippingAddress?: string }).shippingAddress ?? '');
                }
              }}
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
            {canCreate ? (
              <Stack direction="row" spacing={1}>
                <TextField
                  size="small"
                  label={t('billing.addParty')}
                  value={newPartyName}
                  onChange={(e) => setNewPartyName(e.target.value)}
                />
                <Button
                  size="small"
                  disabled={!newPartyName.trim()}
                  onClick={() => {
                    void createCustomer({ name: newPartyName.trim(), status: 'ACTIVE' }).then((c) => {
                      setCustomer(c);
                      setNewPartyName('');
                    }).catch((err) => setError(getErrorMessage(err)));
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
                label={t('common.date', 'Quotation Date')}
                InputLabelProps={{ shrink: true }}
                value={quotationDate}
                disabled={!canCreate}
                onChange={(e) => setQuotationDate(e.target.value)}
              />
              <TextField
                type="date"
                size="small"
                sx={{ flex: 1 }}
                label={t('billing.validUntil')}
                InputLabelProps={{ shrink: true }}
                value={validUntil}
                disabled={!canCreate}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                select
                size="small"
                sx={{ flex: 1 }}
                label={t('billing.salesman')}
                value={salesman}
                disabled={!canCreate}
                onChange={(e) => setSalesman(e.target.value)}
              >
                <MenuItem value="">{t('common.all')}</MenuItem>
                {(employees.data ?? []).map((emp) => (
                  <MenuItem key={emp.id} value={emp.id}>{emp.name}</MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                sx={{ flex: 1 }}
                label={t('billing.salesChannel')}
                value={salesChannel}
                disabled={!canCreate}
                onChange={(e) => setSalesChannel(e.target.value)}
              >
                <MenuItem value="">{t('common.all')}</MenuItem>
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
              value={deliveryAddress}
              disabled={!canCreate}
              onChange={(e) => setDeliveryAddress(e.target.value)}
            />
            {expectedProfitAmount(expectedProfit) != null ? (
              <Typography variant="body2" color="text.secondary">
                {t('billing.expectedProfit')}: {formatMoney(expectedProfitAmount(expectedProfit))}
              </Typography>
            ) : null}

            {lines.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('nav.products')}</TableCell>
                    <TableCell align="right">{t('billing.qty')}</TableCell>
                    <TableCell align="right">{t('billing.unitPrice')}</TableCell>
                    <TableCell align="right">{t('billing.expectedPrice', 'Est. Cost')}</TableCell>
                    <TableCell align="right">{t('billing.discountPercent')}</TableCell>
                    <TableCell align="right">{t('common.total')}</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {lines.map((l) => (
                    <TableRow key={l.key}>
                      <TableCell>{l.product.name}</TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={l.qty}
                          disabled={isPartiallyConverted || !canCreate}
                          onChange={(e) => updateLine(l.key, { qty: Math.max(0.001, toNumber(e.target.value) || 0.001) })}
                          sx={{ width: 90 }}
                          inputProps={{ min: 0.001, step: 'any', 'aria-label': t('billing.qty') }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={l.unitPrice}
                          disabled={isPartiallyConverted || !canCreate}
                          onChange={(e) => updateLine(l.key, { unitPrice: Math.max(0, toNumber(e.target.value) || 0) })}
                          sx={{ width: 100 }}
                          inputProps={{ min: 0, step: '0.01', 'aria-label': t('billing.unitPrice') }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={l.expectedPrice}
                          disabled={isPartiallyConverted || !canCreate}
                          onChange={(e) => updateLine(l.key, { expectedPrice: Math.max(0, toNumber(e.target.value) || 0) })}
                          sx={{ width: 100 }}
                          inputProps={{ min: 0, step: '0.01', 'aria-label': t('billing.expectedPrice') }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={l.discountPercent}
                          disabled={isPartiallyConverted || !canCreate}
                          onChange={(e) =>
                            updateLine(l.key, {
                              discountPercent: Math.min(100, Math.max(0, toNumber(e.target.value) || 0)),
                            })
                          }
                          sx={{ width: 80 }}
                          inputProps={{ min: 0, max: 100, step: '0.01', 'aria-label': t('billing.discountPercent') }}
                        />
                      </TableCell>
                      <TableCell align="right">{formatMoney(lineTotal(l))}</TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          aria-label={t('common.remove')}
                          disabled={isPartiallyConverted || !canCreate}
                          onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}

            {canCreate && !isPartiallyConverted ? (
              <Stack spacing={1}>
                {cf.filterBar}
                <Stack direction="row" spacing={1} alignItems="center">
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
                    onChange={(_, v) => {
                      setPendingProduct(v);
                      setPendingUnitPrice(v ? String(toNumber(v.sellingPrice)) : '');
                    }}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label={t('nav.products')}
                        helperText={productSearch.helperText}
                      />
                    )}
                  />
                  <TextField
                    type="number"
                    label={t('billing.qty')}
                    value={pendingQty}
                    onChange={(e) => setPendingQty(e.target.value)}
                    sx={{ width: 100 }}
                    inputProps={{ min: 0.001, step: 'any' }}
                  />
                  <TextField
                    type="number"
                    label={t('billing.unitPrice')}
                    value={pendingUnitPrice}
                    onChange={(e) => setPendingUnitPrice(e.target.value)}
                    sx={{ width: 110 }}
                    inputProps={{ min: 0, step: '0.01' }}
                  />
                  <TextField
                    type="number"
                    label={t('billing.discountPercent')}
                    value={pendingDiscountPercent}
                    onChange={(e) => setPendingDiscountPercent(e.target.value)}
                    sx={{ width: 90 }}
                    inputProps={{ min: 0, max: 100, step: '0.01' }}
                  />
                  <Button variant="outlined" disabled={!pendingProduct} onClick={addLine}>
                    {t('common.add')}
                  </Button>
                </Stack>
              </Stack>
            ) : null}

            {lines.length > 0 ? (
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'background.default' }}>
                <Stack spacing={0.5} alignItems="flex-end">
                  <Typography variant="body2">{t('common.subtotal', 'Subtotal')}: {formatMoney(subtotal)}</Typography>
                  <Typography variant="body2" color="text.secondary">{t('billing.estimatedTax', 'Est. GST')}: {formatMoney(estimatedGst)}</Typography>
                  <Typography variant="subtitle1" fontWeight="bold">{t('common.total', 'Total')}: {formatMoney(grandTotal)}</Typography>
                </Stack>
              </Paper>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setOpen(false);
              resetDialog();
            }}
          >
            {t('common.cancel')}
          </Button>
          {canCreate ? (
            <Button
              variant="contained"
              disabled={!customer || lines.length === 0 || createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {t('common.save')}
            </Button>
          ) : null}
        </DialogActions>
      </Dialog>
      <ConvertQuotationDialog
        quotation={convertTarget?.quotation ?? null}
        mode={convertTarget?.mode ?? null}
        pending={convertMutation.isPending || convertToOrderMutation.isPending}
        error={error}
        onClose={() => {
          setConvertTarget(null);
          setConvertingId(null);
        }}
        onConfirm={(items, confirmExpired) => {
          if (!convertTarget) return;
          if (convertTarget.mode === 'order') {
            convertToOrderMutation.mutate({ id: convertTarget.quotation.id, items, confirmExpired });
          } else {
            convertMutation.mutate({ id: convertTarget.quotation.id, items, confirmExpired });
          }
        }}
      />
    </Stack>
  );
}

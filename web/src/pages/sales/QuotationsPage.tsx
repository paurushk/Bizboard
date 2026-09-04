import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
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
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  convertQuotation,
  convertQuotationToOrder,
  createQuotation,
  getCompany,
  listQuotationsPage,
  listSalesInvoicesPage,
} from '@/api/resources';
import { todayIso } from '@/components/billing';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import type { Customer, Product } from '@/types/domain';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreateSales } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

interface DraftLine {
  key: string;
  product: Product;
  qty: number;
}

const emptyForm = { customer: null as Customer | null, lines: [] as DraftLine[] };

const PAGE_SIZE = 50;

export function QuotationsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canCreate = canCreateSales(user);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['quotations', page],
    queryFn: () => listQuotationsPage({ page, pageSize: PAGE_SIZE }),
  });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
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
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!canCreate || searchParams.get('create') !== '1') return;
    setOpen(true);
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    setSearchParams(next, { replace: true });
  }, [canCreate, searchParams, setSearchParams]);

  const resetDialog = () => {
    setCustomer(null);
    setLines([]);
    setPendingProduct(null);
    setPendingQty('1');
    productSearch.setProductQuery('');
  };

  const addLine = () => {
    if (!pendingProduct) return;
    // BUG-526: quantity must be a positive number, not 0/negative.
    const qty = Math.max(1, Math.floor(Number(pendingQty)) || 1);
    setLines((prev) => [...prev, { key: `${pendingProduct.id}-${Date.now()}`, product: pendingProduct, qty }]);
    setPendingProduct(null);
    setPendingQty('1');
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (lines.length === 0) throw new Error('Add at least one product');
      return createQuotation({
        customer: customer?.id,
        quotationDate: todayIso(),
        invoiceType: preferredInvoiceType(company.data?.registrationType),
        items: lines.map((l) => ({
          product: l.product.id,
          quantity: l.qty,
          unitPrice: toNumber(l.product.sellingPrice),
          gstRate: toNumber(l.product.gstRate),
        })),
      });
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Quotation created');
      // BUG-524: previously the dialog state was never reset, so reopening
      // it showed the last quotation's customer/product/qty pre-filled.
      resetDialog();
      void qc.invalidateQueries({ queryKey: ['quotations'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const [convertingId, setConvertingId] = useState<number | null>(null);
  const convertMutation = useMutation({
    mutationFn: (id: number) => convertQuotation(id),
    onSuccess: async (invoice) => {
      const flash = `Converted to draft invoice #${invoice.id}`;
      setMessage(flash);
      setConvertingId(null);
      void qc.invalidateQueries({ queryKey: ['quotations'] });
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
    mutationFn: (id: number) => convertQuotationToOrder(id),
    onSuccess: async (order) => {
      const flash = `Converted to draft sales order #${order.id}`;
      setMessage(flash);
      setConvertingId(null);
      void qc.invalidateQueries({ queryKey: ['quotations'] });
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
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
        <Typography variant="h4">{t('nav.quotations')}</Typography>
        {canCreate ? (
          <Button variant="contained" onClick={() => setOpen(true)}>
            {t('phase1.newQuotation')}
          </Button>
        ) : null}
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {quotations.length === 0 && query.isSuccess ? <EmptyState description={t('empty.quotations')} /> : null}
      {quotations.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {quotations.map((q) => (
                <TableRow key={q.id}>
                  <TableCell>{q.number ?? '—'}</TableCell>
                  <TableCell>{q.quotationDate}</TableCell>
                  <TableCell>{q.customerName ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(q.status)}
                      labelKey={statusLabelKey(q.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(q.grandTotal)}</TableCell>
                  <TableCell align="right">
                    {q.status === 'DRAFT' && canCreate ? (
                      <Stack direction="row" spacing={1} justifyContent="flex-end">
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={
                            (convertMutation.isPending || convertToOrderMutation.isPending) &&
                            convertingId === q.id
                          }
                          onClick={() => {
                            if (!window.confirm(t('common.confirmToOrder'))) return;
                            setConvertingId(q.id);
                            convertToOrderMutation.mutate(q.id);
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
                            if (!window.confirm(t('common.confirmConvert'))) return;
                            setConvertingId(q.id);
                            convertMutation.mutate(q.id);
                          }}
                        >
                          {t('common.convert')}
                        </Button>
                      </Stack>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
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
        maxWidth="sm"
      >
        <DialogTitle>New quotation</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <Autocomplete
              options={customerSearch.options}
              getOptionLabel={(o) => o.name}
              filterOptions={(opts) => opts}
              value={customer}
              onChange={(_, v) => setCustomer(v)}
              onInputChange={(_, v) => customerSearch.setQuery(v)}
              loading={customerSearch.isFetching}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('billing.customer')}
                  helperText={!customerSearch.enabled ? t('common.typeToSearch') : undefined}
                />
              )}
            />

            {lines.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('nav.products')}</TableCell>
                    <TableCell align="right">{t('billing.qty')}</TableCell>
                    <TableCell align="right">{t('common.total')}</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {lines.map((l) => (
                    <TableRow key={l.key}>
                      <TableCell>{l.product.name}</TableCell>
                      <TableCell align="right">{l.qty}</TableCell>
                      <TableCell align="right">
                        {formatMoney(l.qty * toNumber(l.product.sellingPrice))}
                      </TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          aria-label={t('common.remove')}
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
                  if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
                }}
                getOptionLabel={(o) => `${o.name} · ${o.sku}`}
                value={pendingProduct}
                onChange={(_, v) => setPendingProduct(v)}
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
                inputProps={{ min: 1 }}
              />
              <Button variant="outlined" disabled={!pendingProduct} onClick={addLine}>
                {t('common.add')}
              </Button>
            </Stack>
            </Stack>
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
          <Button
            variant="contained"
            disabled={lines.length === 0 || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

import Alert from '@mui/material/Alert';
import { useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { createSupplier, getCompany, getSupplierPriceHistory, listSuppliersPage, updateSupplier, verifySupplierGstin } from '@/api/resources';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useProductSearch } from '@/hooks/useProductSearch';
import type { Product } from '@/types/domain';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { StatusChip } from '@/components/StatusChip';
import {
  HistoryFilterBar,
  EMPTY_HISTORY_FILTERS,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { partyNameError } from '@/utils/partyName';
import type { Supplier } from '@/types/domain';
import { isValidGstin, isValidIndianPhone } from '@/utils/gst';
import { getStateFromGstin } from '@/utils/indianStates';
import { placeOfSupplyKnown } from '@/utils/tax';
import { formatMoney } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { gstinStatusColor, gstinStatusLabelKey } from '@/utils/gstinStatus';

const SUPPLIERS_PAGE_SIZE = 50;
const emptyForm = { name: '', phone: '', email: '', gstin: '', state: '', address: '' };

export function SuppliersPage() {
  useFeatureFlagEpoch();
  const showPrices = isRuntimeFlagEnabled('ENABLE_SUPPLIER_PRICE_HISTORY');
  const qc = useQueryClient();
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [nameTouched, setNameTouched] = useState(false);
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const [page, setPage] = useState(1);
  const debouncedQ = useDebouncedValue(filters.q, 300).trim();
  // PB-03: the server searches and pages, so a company with thousands of suppliers loads one page at a time.
  const query = useQuery({
    queryKey: ['suppliers', 'page', page, debouncedQ, filters.status],
    queryFn: () =>
      listSuppliersPage({
        page,
        pageSize: SUPPLIERS_PAGE_SIZE,
        q: debouncedQ || undefined,
        status: filters.status || undefined,
      }),
    placeholderData: keepPreviousData,
  });
  const [priceSupplier, setPriceSupplier] = useState<Supplier | null>(null);
  const [priceProduct, setPriceProduct] = useState<Product | null>(null);
  const productSearch = useProductSearch({ activeOnly: true, selected: priceProduct });
  const priceHistory = useQuery({
    queryKey: ['supplier-price-history', priceSupplier?.id, priceProduct?.id],
    queryFn: () => getSupplierPriceHistory(priceSupplier!.id, priceProduct!.id),
    enabled: Boolean(showPrices && priceSupplier && priceProduct),
  });
  const visibleSuppliers = useMemo(() => query.data?.results ?? [], [query.data]);
  const filtersActive = Boolean(filters.q.trim() || filters.status);

  // F2-054: mirror CustomersPage — when GST is on and assume-local is off,
  // require a place of supply (State or GSTIN) before a supplier can be saved,
  // otherwise the friction only surfaces later as a blocked purchase Complete.
  const requirePlaceOfSupply =
    !!company.data?.isGstRegistered && !company.data?.assumeLocalStateForBlankParty;
  const placeOfSupplyOk =
    !requirePlaceOfSupply || placeOfSupplyKnown(form.state, form.gstin);
  const canSave =
    Boolean(form.name.trim()) && partyNameError(form.name) == null && placeOfSupplyOk;

  const saveMutation = useMutation({
    mutationFn: async () => {
      const gstin = form.gstin.trim().toUpperCase();
      if (gstin && !isValidGstin(gstin)) {
        throw new Error(t('purchaseEditor.gstinInvalid'));
      }
      const payload = { ...form, gstin: gstin || form.gstin };
      if (editing) return updateSupplier(editing.id, payload);
      return createSupplier({ ...payload, isActive: true });
    },
    onSuccess: async (saved) => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      setError(null);
      // A slow in-flight list request can finish after this create and write
      // the pre-create empty list back over the cache. Cancel it, show the
      // saved row immediately, then refresh from the server.
      await qc.cancelQueries({ queryKey: ['suppliers'] });
      qc.setQueryData<Supplier[]>(['suppliers'], (prev) => {
        const list = (prev ?? []).filter((row) => row.id !== saved.id);
        return [saved, ...list];
      });
      void qc.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: (s: Supplier) => updateSupplier(s.id, { isActive: !s.isActive }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['suppliers'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const verifyMutation = useMutation({
    mutationFn: (id: number) => verifySupplierGstin(id),
    onSuccess: () => {
      setError(null);
      setNotice(t('purchaseReview.supplierVerified'));
      void qc.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.suppliers')}</PageTitle>
        <Button
          variant="contained"
          onClick={() => {
            setEditing(null);
            setForm(emptyForm);
            setNameTouched(false);
            setOpen(true);
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {notice ? (
        <Alert severity="success" onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      ) : null}
      {(query.data && query.data.count > 0) || filtersActive ? (
        <HistoryFilterBar
          value={filters}
          onChange={(next) => {
            setFilters(next);
            setPage(1);
          }}
          showDateRange={false}
          statusOptions={[
            { value: 'ACTIVE', label: t('status.active') },
            { value: 'INACTIVE', label: t('status.inactive') },
          ]}
        />
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data && visibleSuppliers.length === 0 && filtersActive ? (
        <EmptyState title={t('common.noResults')} />
      ) : null}
      {query.data && query.data.count === 0 && !filtersActive ? (
        <EmptyState
          description={t('purchaseReview.addSuppliersHint')}
          action={
            <Button
              variant="contained"
              onClick={() => {
                setEditing(null);
                setForm(emptyForm);
                setNameTouched(false);
                setOpen(true);
              }}
            >
              {t('empty.addSupplier')}
            </Button>
          }
        />
      ) : null}
      {visibleSuppliers.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.phone')}</TableCell>
                <TableCell>{t('purchaseReview.colGstin')}</TableCell>
                <TableCell>{t('purchaseReview.colGstinStatus')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('sweep2.outstanding')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleSuppliers.map((s) => (
                <TableRow key={s.id}>
                  <TableCell
                    sx={{
                      position: { xs: 'sticky', md: 'static' },
                      left: 0,
                      zIndex: 1,
                      bgcolor: 'background.paper',
                      minWidth: 120,
                    }}
                  >
                    {s.name}
                  </TableCell>
                  <TableCell>{s.phone ?? '—'}</TableCell>
                  <TableCell>
                    {s.gstin ?? '—'}
                    {s.gstinLegalName ? (
                      <Typography variant="caption" display="block" color="text.secondary">
                        {s.gstinLegalName}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {s.gstin ? (
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Chip
                          size="small"
                          label={t(gstinStatusLabelKey(s.gstinVerificationStatus))}
                          color={gstinStatusColor(s.gstinVerificationStatus)}
                        />
                        <Button
                          size="small"
                          disabled={verifyMutation.isPending}
                          onClick={() => verifyMutation.mutate(s.id)}
                        >
                          {t('sweep2.verify')}
                        </Button>
                      </Stack>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={s.isActive ? 'success' : 'default'}
                      label={s.isActive ? t('status.ACTIVE') : t('status.INACTIVE')}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(s.outstanding ?? 0)}</TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => {
                        setEditing(s);
                        setForm({
                          name: s.name,
                          phone: s.phone ?? '',
                          email: s.email ?? '',
                          gstin: s.gstin ?? '',
                          state: s.state ?? '',
                          address: s.address ?? '',
                        });
                        setNameTouched(false);
                        setOpen(true);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                    {showPrices ? (
                      <Button size="small" onClick={() => { setPriceSupplier(s); setPriceProduct(null); }}>
                        {t('supplierPrices.title')}
                      </Button>
                    ) : null}
                    <Button
                      size="small"
                      disabled={toggleMutation.isPending}
                      onClick={() => toggleMutation.mutate(s)}
                    >
                      {s.isActive ? t('common.deactivate') : t('common.activate')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Button size="small" disabled={page <= 1 || query.isFetching} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            {t('common.previous')}
          </Button>
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button size="small" disabled={!query.data.next || query.isFetching} onClick={() => setPage((p) => p + 1)}>
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('purchaseReview.editSupplier') : t('purchaseReview.createSupplier')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              placeholder={t('billing.supplierNamePrompt')}
              onBlur={() => setNameTouched(true)}
              error={nameTouched && (!form.name.trim() || partyNameError(form.name) != null)}
              helperText={
                nameTouched && !form.name.trim()
                  ? 'Supplier name is required'
                  : nameTouched && partyNameError(form.name)
                    ? t('billing.partyNameInvalid')
                    : undefined
              }
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('common.phone')}
              value={form.phone}
              error={Boolean(form.phone.trim() && !isValidIndianPhone(form.phone))}
              helperText={
                form.phone.trim() && !isValidIndianPhone(form.phone)
                  ? 'Enter a valid 10-digit Indian mobile number'
                  : undefined
              }
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            />
            <TextField
              label={t('common.email')}
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
            <TextField
              label="GSTIN"
              value={form.gstin}
              error={Boolean(form.gstin.trim() && form.gstin.trim().length === 15 && !isValidGstin(form.gstin.trim()))}
              helperText={
                form.gstin.trim() && form.gstin.trim().length === 15 && !isValidGstin(form.gstin.trim())
                  ? 'Invalid 15-digit GSTIN checksum/format'
                  : undefined
              }
              onChange={(e) => {
                const val = e.target.value.toUpperCase().trim();
                const matchedState = getStateFromGstin(val);
                setForm((f) => ({
                  ...f,
                  gstin: val,
                  state: matchedState && !f.state ? matchedState : f.state,
                }));
              }}
            />
            <StateSelect
              value={form.state}
              onChange={(state) => setForm((f) => ({ ...f, state }))}
            />
            <TextField
              label={t('sweep.address')}
              value={form.address}
              onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Tooltip
            title={
              !form.name.trim()
                ? 'Enter supplier name to save'
                : !placeOfSupplyOk
                  ? 'Enter the supplier State or GSTIN (GST is enabled for this company)'
                  : ''
            }
          >
            <span>
              <Button
                variant="contained"
                disabled={!canSave || saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                {t('common.save')}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>
      <Dialog open={priceSupplier != null} onClose={() => setPriceSupplier(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('supplierPrices.title')} — {priceSupplier?.name}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={productSearch.options}
              value={priceProduct}
              onChange={(_e, value) => setPriceProduct(value)}
              onInputChange={(_e, value) => productSearch.setProductQuery(value)}
              getOptionLabel={(option) => option.name}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              renderInput={(params) => <TextField {...params} label={t('supplierPrices.product')} />}
            />
            {priceHistory.data ? (
              <Stack spacing={0.5}>
                <Typography variant="body2">
                  {t('supplierPrices.leadTime')}: {priceHistory.data.leadTimeDays ?? '—'}
                </Typography>
                <Typography variant="body2">
                  {t('supplierPrices.fillRate')}: {priceHistory.data.fillRate ?? '—'}
                </Typography>
                {priceHistory.data.overReceipt ? (
                  <Typography variant="body2">{t('supplierPrices.overReceipt')}</Typography>
                ) : null}
              </Stack>
            ) : null}
            {priceHistory.isLoading ? <LoadingState /> : null}
            {priceProduct && priceHistory.data && priceHistory.data.rows.length === 0 ? (
              <Typography>{t('supplierPrices.empty')}</Typography>
            ) : null}
            {priceHistory.data && priceHistory.data.rows.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('supplierPrices.date')}</TableCell>
                    <TableCell>{t('supplierPrices.source')}</TableCell>
                    <TableCell align="right">{t('supplierPrices.qty')}</TableCell>
                    <TableCell align="right">{t('supplierPrices.price')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {priceHistory.data.rows.map((row) => (
                    <TableRow key={`${row.source}-${row.documentNumber}-${row.documentDate}`}>
                      <TableCell>{row.documentDate}</TableCell>
                      <TableCell>
                        {row.source === 'PURCHASE_ORDER' ? t('supplierPrices.order') : t('supplierPrices.invoice')}
                        {' '}{row.documentNumber}
                      </TableCell>
                      <TableCell align="right">{row.quantity}</TableCell>
                      <TableCell align="right">{formatMoney(row.unitPrice)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPriceSupplier(null)}>{t('common.cancel')}</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
